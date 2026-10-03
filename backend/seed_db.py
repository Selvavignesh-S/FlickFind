import sys
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal, engine, Base
from models import Movie
from ai_service import ai_engine

load_dotenv()

MOCK_MOVIES = [
    {
        "id": 27205,
        "title": "Inception",
        "release_year": 2010,
        "imdb_rating": 8.8,
        "imdb_votes": 2500000,
        "popularity": 120.5,
        "director": "Christopher Nolan",
        "runtime": 148,
        "genres": "Action, Sci-Fi, Adventure",
        "overview": "A thief who steals corporate secrets through dream-sharing technology is tasked with planting an idea into the mind of a CEO."
    },
    {
        "id": 11324,
        "title": "Shutter Island",
        "release_year": 2010,
        "imdb_rating": 8.2,
        "imdb_votes": 1400000,
        "popularity": 95.4,
        "director": "Martin Scorsese",
        "runtime": 138,
        "genres": "Drama, Thriller, Mystery",
        "overview": "A U.S. Marshal investigates the disappearance of a patient from an asylum on a remote island, uncovering dark secrets."
    },
    {
        "id": 157336,
        "title": "Interstellar",
        "release_year": 2014,
        "imdb_rating": 8.7,
        "imdb_votes": 2000000,
        "popularity": 150.2,
        "director": "Christopher Nolan",
        "runtime": 169,
        "genres": "Adventure, Drama, Sci-Fi",
        "overview": "A team of explorers travels through a wormhole in space in an attempt to ensure humanity's survival."
    },
    {
        "id": 210577,
        "title": "Gone Girl",
        "release_year": 2014,
        "imdb_rating": 8.1,
        "imdb_votes": 1000000,
        "popularity": 80.1,
        "director": "David Fincher",
        "runtime": 149,
        "genres": "Drama, Mystery, Thriller",
        "overview": "With his wife's disappearance becoming the focus of a media circus, a man finds himself scrutinized as suspect."
    }
]


def seed_database():
    db: Session = SessionLocal()

    db.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    db.commit()
    Base.metadata.create_all(bind=engine)

    existing_count = db.query(Movie).count()
    if existing_count > 0:
        if "--force" not in sys.argv:
            print(f"[Seeder] Database already contains {existing_count} records.")
            print("         Skipping seed to protect data. Use '--force' to overwrite.")
            db.close()
            return
        print(f"[Seeder] Truncating {existing_count} existing records...")
        db.execute(text("TRUNCATE TABLE movies RESTART IDENTITY CASCADE;"))
        db.commit()

    ai_engine.load_model()
    print("[Seeder] Generating embeddings and inserting mock movies...")

    for item in MOCK_MOVIES:
        context = f"{item['title']} directed by {item['director']}. Genres: {item['genres']}. Overview: {item['overview']}"
        vector = ai_engine.generate_vector(context)

        db.add(Movie(
            id=item["id"],
            title=item["title"],
            release_year=item["release_year"],
            imdb_rating=item["imdb_rating"],
            imdb_votes=item["imdb_votes"],
            popularity=item["popularity"],
            director=item["director"],
            runtime=item["runtime"],
            genres=item["genres"],
            overview=item["overview"],
            mood_vector_data=vector,
        ))

    db.commit()
    db.close()
    print("[Seeder] Seeding completed successfully.")


if __name__ == "__main__":
    seed_database()