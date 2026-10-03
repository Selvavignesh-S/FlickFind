from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from pgvector.sqlalchemy import Vector
from database import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    watcher_tier = Column(String, default="BASIC_WATCHER", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    persona_vector_data = Column(Vector(768), nullable=True)


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    imdb_id = Column(String, nullable=True)

    title = Column(String, nullable=False)
    original_title = Column(String, nullable=True)
    tagline = Column(Text, nullable=True)
    overview = Column(Text, nullable=True)
    genres = Column(String, nullable=True)

    release_year = Column(Integer, nullable=False)
    release_date = Column(String, nullable=True)
    status = Column(String, nullable=True)
    runtime = Column(Integer, nullable=True, default=0)
    original_language = Column(String, nullable=True)

    budget = Column(Float, nullable=True, default=0.0)
    revenue = Column(Float, nullable=True, default=0.0)
    imdb_rating = Column(Float, nullable=False, default=0.0)
    imdb_votes = Column(Integer, nullable=True, default=0)
    popularity = Column(Float, nullable=True, default=0.0)

    director = Column(String, nullable=True)
    director_of_photography = Column(String, nullable=True)
    music_composer = Column(String, nullable=True)
    movie_cast = Column(Text, nullable=True)
    writers = Column(Text, nullable=True)
    producers = Column(Text, nullable=True)
    production_companies = Column(Text, nullable=True)
    production_countries = Column(String, nullable=True)

    poster_path = Column(String, nullable=True)
    title_tagline_overview = Column(Text, nullable=True)
    token_count = Column(Integer, nullable=True)

    hit_count = Column(Integer, default=0, nullable=False)
    mood_vector_data = Column(Vector(768), nullable=True)


class UserWatchlist(Base):
    __tablename__ = "user_watchlists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    movie_id = Column(Integer, index=True, nullable=False)
    added_at = Column(DateTime, default=utc_now, nullable=False)


class UserWatchedHistory(Base):
    __tablename__ = "user_watched_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    movie_id = Column(Integer, index=True, nullable=False)
    rating = Column(Float, nullable=True)
    critic_review = Column(Text, nullable=True)
    watched_at = Column(DateTime, default=utc_now, nullable=False)


class UserDislikedFilter(Base):
    __tablename__ = "user_disliked_filters"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    movie_id = Column(Integer, index=True, nullable=False)
    rejection_reason = Column(String, nullable=False)
    flagged_at = Column(DateTime, default=utc_now, nullable=False)