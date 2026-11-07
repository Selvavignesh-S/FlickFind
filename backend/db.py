"""User data in SQLite: accounts, each user's film library (watchlist / watched / blocked) and what was shown.

One row per user and film in `library`: a film is on the watchlist, watched, or blocked, never two at once.
Title, year and poster are copied in when a row is saved, so a library still shows films that later leave the catalog.
"""
import os
import sqlite3

from builder.common import DATA

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash BLOB NOT NULL,
    name TEXT NOT NULL,
    about TEXT NOT NULL DEFAULT '',
    genres_like TEXT NOT NULL DEFAULT '[]',   -- JSON list
    genres_avoid TEXT NOT NULL DEFAULT '[]',  -- JSON list
    niche REAL NOT NULL DEFAULT 0.5,          -- 0 = mainstream, 0.5 = no lean (new users), 1 = niche; learned from activity
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS library (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tmdb_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('watchlist', 'watched', 'blocked')),
    title TEXT NOT NULL,
    year INTEGER,
    poster_path TEXT,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    mood_match INTEGER CHECK (mood_match BETWEEN 1 AND 5),  -- niche question: how well it matched the mood
    mindset TEXT,                                           -- niche question: what mindset to watch it in
    block_reason TEXT CHECK (block_reason IN ('language', 'theme', 'actor', 'mainstream', 'other')),
    block_detail TEXT,                                      -- the language code or actor name for those reasons
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, tmdb_id)
);
CREATE TABLE IF NOT EXISTS shown (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session TEXT NOT NULL,
    tmdb_id INTEGER NOT NULL,
    shown_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, session, tmdb_id)
);
CREATE TABLE IF NOT EXISTS web_finds (          -- films found beyond the catalog; builder.curate adds them
    tmdb_id INTEGER PRIMARY KEY,
    imdb_id TEXT,
    title TEXT NOT NULL,
    year INTEGER,
    request TEXT NOT NULL,                      -- the request that found it
    found_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS omdb (               -- Rotten Tomatoes cache (backend/omdb.py)
    imdb_id TEXT PRIMARY KEY,
    rotten_tomatoes INTEGER,                    -- NULL: OMDb has no RT score for the film
    fetched_at TEXT NOT NULL
);
"""


def connect():
    con = sqlite3.connect(os.environ.get("FLICKFIND_DB", DATA / "flickfind.db"))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con
