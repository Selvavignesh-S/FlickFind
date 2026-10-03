import os
import gc
import json
import time
from urllib.parse import urlparse
from dotenv import load_dotenv
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import pyarrow.parquet as pq

load_dotenv()


def get_db_connection_params():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        parsed = urlparse(db_url)
        return {
            "dbname": parsed.path.lstrip("/"),
            "user": parsed.username,
            "password": parsed.password,
            "host": parsed.hostname,
            "port": str(parsed.port or 5432),
        }
    return {
        "dbname": os.getenv("POSTGRES_DB", "flickfind_db"),
        "user": os.getenv("POSTGRES_USER", "flickadmin"),
        "password": os.getenv("POSTGRES_PASSWORD", "flicksecretpassword"),
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": os.getenv("POSTGRES_PORT", "5433"),
    }


PARQUET_FILE = os.getenv("PARQUET_FILE", "movies_raw.parquet")

COLUMN_TARGETS = [
    "id", "imdb_id", "title", "original_title", "tagline", "overview", "genres",
    "release_date", "status", "runtime", "original_language", "budget", "revenue",
    "vote_average", "vote_count", "popularity", "director", "director_of_photography",
    "music_composer", "movie_cast", "writers", "producers", "production_companies",
    "production_countries", "poster_path", "title_tagline_overview", "token_count", "embedding",
]

INSERT_SQL = """
    INSERT INTO movies (
        id, imdb_id, title, original_title, tagline, overview, genres,
        release_year, release_date, status, runtime, original_language, budget, revenue,
        imdb_rating, imdb_votes, popularity, director, director_of_photography, music_composer,
        movie_cast, writers, producers, production_companies, production_countries, poster_path,
        title_tagline_overview, token_count, hit_count, mood_vector_data
    ) VALUES %s
    ON CONFLICT (id) DO NOTHING;
"""


def build_row(row):
    try:
        raw_embedding = row.embedding
        if isinstance(raw_embedding, str):
            vector_array = json.loads(raw_embedding)
        elif isinstance(raw_embedding, list):
            vector_array = raw_embedding
        else:
            return None

        if len(vector_array) != 768:
            return None

        def s(val):
            return str(val) if pd.notna(val) else None

        return (
            int(row.id),
            s(row.imdb_id),
            str(row.title),
            s(row.original_title),
            s(row.tagline),
            s(row.overview),
            s(row.genres),
            int(row.release_year),
            s(row.release_date),
            s(row.status),
            int(row.runtime),
            s(row.original_language),
            float(row.budget),
            float(row.revenue),
            float(row.imdb_rating),
            int(row.imdb_votes),
            float(row.popularity),
            s(row.director),
            s(row.director_of_photography),
            s(row.music_composer),
            s(row.movie_cast),
            s(row.writers),
            s(row.producers),
            s(row.production_companies),
            s(row.production_countries),
            s(row.poster_path),
            s(row.title_tagline_overview),
            int(row.token_count) if pd.notna(row.token_count) else None,
            0,
            str(vector_array),
        )
    except Exception:
        return None


def seed_database_complete_warehouse():
    if not os.path.exists(PARQUET_FILE):
        print(f"Error: '{PARQUET_FILE}' not found.")
        return

    start_time = time.time()
    db_config = get_db_connection_params()

    print(f"Connecting to PostgreSQL ({db_config['host']}:{db_config['port']}/{db_config['dbname']})...")
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    conn.commit()

    parquet_file = pq.ParquetFile(PARQUET_FILE)
    total_inserted = 0

    for batch in parquet_file.iter_batches(batch_size=15000, columns=COLUMN_TARGETS):
        df = batch.to_pandas()
        df = df.dropna(subset=["id", "title", "embedding"])

        df["release_year"] = pd.to_datetime(df["release_date"], errors="coerce").dt.year.fillna(2000).astype(int)
        df["imdb_rating"] = df["vote_average"].fillna(0.0).astype(float)
        df["imdb_votes"] = df["vote_count"].fillna(0).astype(int)
        df["runtime"] = df["runtime"].fillna(0).astype(int)
        df["budget"] = df["budget"].fillna(0.0).astype(float)
        df["revenue"] = df["revenue"].fillna(0.0).astype(float)
        df["popularity"] = df["popularity"].fillna(0.0).astype(float)
        df["id"] = df["id"].astype(int)

        rows = [r for row in df.itertuples() if (r := build_row(row)) is not None]

        if rows:
            execute_values(cursor, INSERT_SQL, rows, page_size=1000)
            total_inserted += len(rows)
            print(f"Ingested batch: {total_inserted} total records.")

        del df, rows
        gc.collect()

    conn.commit()
    cursor.close()
    conn.close()

    elapsed = time.time() - start_time
    print(f"Seeding complete: {total_inserted} records in {elapsed:.2f}s.")


if __name__ == "__main__":
    seed_database_complete_warehouse()
