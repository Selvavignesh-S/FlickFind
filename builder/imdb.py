"""Step 1: download IMDb's dataset files and keep feature-length films.

Output: data/build/imdb_candidates.parquet
Run:    uv run python -m builder.imdb
"""
import time

import duckdb
import httpx

from builder.common import BUILD, RAW

FILES = ["title.basics.tsv.gz", "title.ratings.tsv.gz"]
MIN_VOTES = 20  # loose first cut; the real per-group floors are chosen in curate.py
OUT = BUILD / "imdb_candidates.parquet"


def download(name):
    """Fetch one IMDb file, reusing a copy younger than a day (IMDb refreshes daily)."""
    path = RAW / name
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        return path
    tmp = path.with_name(name + ".part")
    with httpx.stream("GET", f"https://datasets.imdbws.com/{name}", timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.rename(path)
    return path


def main():
    basics, ratings = (download(n) for n in FILES)
    con = duckdb.connect()
    # IMDb TSVs use \N for null and contain stray quotes, so quoting is disabled.
    con.execute(f"""
        COPY (
            SELECT b.tconst AS imdb_id, b.titleType AS title_type,
                   b.primaryTitle AS title, b.originalTitle AS original_title,
                   TRY_CAST(b.startYear AS INT) AS year,
                   TRY_CAST(b.runtimeMinutes AS INT) AS runtime,
                   b.genres AS imdb_genres,
                   r.averageRating AS imdb_rating, r.numVotes AS imdb_votes
            FROM read_csv('{basics}', delim='\t', quote='', escape='', nullstr='\\N',
                          header=true, all_varchar=true) b
            JOIN read_csv('{ratings}', delim='\t', header=true) r USING (tconst)
            WHERE b.titleType IN ('movie', 'tvMovie') AND b.isAdult = '0'
              AND TRY_CAST(b.runtimeMinutes AS INT) >= 60
              AND r.numVotes >= {MIN_VOTES}
        ) TO '{OUT}' (FORMAT parquet)""")

    print(f"Wrote {OUT}")
    print(con.execute(f"SELECT title_type, count(*) FROM '{OUT}' GROUP BY 1 ORDER BY 2 DESC").fetchall())
    for floor in (20, 50, 100, 200, 500, 1000, 5000):
        n = con.execute(f"SELECT count(*) FROM '{OUT}' WHERE imdb_votes >= {floor}").fetchone()[0]
        print(f"  >= {floor:>5} votes: {n:>7,}")


if __name__ == "__main__":
    main()
