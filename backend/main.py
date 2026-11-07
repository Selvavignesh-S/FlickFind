"""FlickFind API.

Run: uv run uvicorn backend.main:app --reload --port 8000
Accounts, preferences, the film library (watchlist / watched / blocked) and a first, LLM-free recommend route.
"""
import datetime
import json
import os
from functools import cache
from typing import Literal

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from backend import db, omdb
from backend.catalog import NEUTRAL, POSTER, Catalog
from backend.understand import query_for

NICHE_QUESTIONS_AT = 0.6  # niche users get the extra "watched" questions
app = FastAPI(title="FlickFind")
# shortcut: any origin, fine while the API is only reachable on your laptop / tailnet; list the app's origins if hosted
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@cache
def get_catalog():
    return Catalog.load()


def get_db():
    con = db.connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


# ---- accounts ----

def make_token(user_id):
    exp = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)
    return jwt.encode({"sub": str(user_id), "exp": exp}, os.environ["JWT_SECRET"], algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
                 con=Depends(get_db)):
    try:
        user_id = int(jwt.decode(creds.credentials, os.environ["JWT_SECRET"], algorithms=["HS256"])["sub"])
    except (AttributeError, jwt.PyJWTError):
        raise HTTPException(401, "Please log in again")
    user = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(401, "Please log in again")
    return user


class Signup(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=72)  # bcrypt only reads the first 72 bytes
    name: str = Field(min_length=1, max_length=60)

    @field_validator("email")
    @classmethod
    def looks_like_email(cls, v):
        v = v.strip().lower()
        if "@" not in v.strip("@"):
            raise ValueError("not an email address")
        return v


class Login(BaseModel):
    email: str
    password: str


@app.post("/auth/register")
def register(body: Signup, con=Depends(get_db)):
    if con.execute("SELECT 1 FROM users WHERE email = ?", (body.email,)).fetchone():
        raise HTTPException(409, "An account with this email already exists")
    pw = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt())
    cur = con.execute("INSERT INTO users (email, password_hash, name, niche) VALUES (?, ?, ?, ?)",
                      (body.email, pw, body.name, NEUTRAL))  # every new user starts with no lean either way
    return {"token": make_token(cur.lastrowid)}


@app.post("/auth/login")
def login(body: Login, con=Depends(get_db)):
    user = con.execute("SELECT id, password_hash FROM users WHERE email = ?", (body.email.strip().lower(),)).fetchone()
    if user is None or not bcrypt.checkpw(body.password.encode(), user["password_hash"]):
        raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(user["id"])}


# ---- profile and preferences ----

def profile(user):
    return {"id": user["id"], "email": user["email"], "name": user["name"], "about": user["about"],
            "genres_like": json.loads(user["genres_like"]), "genres_avoid": json.loads(user["genres_avoid"]),
            "niche": round(user["niche"], 3), "taste": taste_label(user["niche"]),
            "niche_questions": user["niche"] >= NICHE_QUESTIONS_AT}


def taste_label(n):
    return "Mainstream" if n < 0.4 else "Niche" if n > NICHE_QUESTIONS_AT else "Balanced"


class Preferences(BaseModel):
    about: str = Field(default="", max_length=2000)
    genres_like: list[str] = Field(default=[], max_length=30)
    genres_avoid: list[str] = Field(default=[], max_length=30)


@app.get("/me")
def me(user=Depends(current_user)):
    return profile(user)


@app.put("/me/preferences")
def set_preferences(body: Preferences, user=Depends(current_user), con=Depends(get_db), catalog=Depends(get_catalog)):
    known = set(catalog.all_genres())
    if unknown := (set(body.genres_like) | set(body.genres_avoid)) - known:
        raise HTTPException(422, f"Unknown genres: {', '.join(sorted(unknown))}")
    if both := set(body.genres_like) & set(body.genres_avoid):
        raise HTTPException(422, f"A genre can't be both liked and avoided: {', '.join(sorted(both))}")
    con.execute("UPDATE users SET about = ?, genres_like = ?, genres_avoid = ? WHERE id = ?",
                (body.about.strip(), json.dumps(body.genres_like), json.dumps(body.genres_avoid), user["id"]))
    return profile(con.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone())


@app.get("/genres")
def genres(catalog=Depends(get_catalog)):
    return catalog.all_genres()


# ---- films and the library ----

def with_state(cards, user_id, con):
    """Add the user's library state and the FlickFind rating (average of FlickFind users' stars) to cards."""
    if not cards:
        return cards
    ids = [c["tmdb_id"] for c in cards]
    marks = ",".join("?" * len(ids))
    mine = {r["tmdb_id"]: dict(r) for r in con.execute(
        f"SELECT tmdb_id, status, rating, block_reason FROM library WHERE user_id = ? AND tmdb_id IN ({marks})",
        (user_id, *ids))}
    stars = {r[0]: (r[1], r[2]) for r in con.execute(
        f"SELECT tmdb_id, AVG(rating), COUNT(rating) FROM library WHERE rating IS NOT NULL AND tmdb_id IN ({marks}) "
        "GROUP BY tmdb_id", ids)}
    rt = omdb.scores([c.get("imdb_id") for c in cards], con)
    for c in cards:
        avg, n = stars.get(c["tmdb_id"], (None, 0))
        c["ratings"] = {"imdb": c.get("imdb_rating"), "rotten_tomatoes": rt.get(c.get("imdb_id")),
                        "flickfind": round(avg, 1) if avg else None, "flickfind_votes": n}
        c["library"] = mine.get(c["tmdb_id"])
    return cards


@app.get("/films/{tmdb_id}")
def film(tmdb_id: int, user=Depends(current_user), con=Depends(get_db), catalog=Depends(get_catalog)):
    if tmdb_id not in catalog:
        raise HTTPException(404, "Film not found")
    return with_state(catalog.cards([tmdb_id]), user["id"], con)[0]


@app.get("/library")
def library(status: Literal["watchlist", "watched", "blocked"], user=Depends(current_user), con=Depends(get_db),
            catalog=Depends(get_catalog)):
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM library WHERE user_id = ? AND status = ? ORDER BY updated_at DESC", (user["id"], status))]
    cards = {c["tmdb_id"]: c for c in with_state(catalog.cards([r["tmdb_id"] for r in rows if r["tmdb_id"] in catalog]),
                                                  user["id"], con)}
    out = []
    for r in rows:  # a film that left the catalog still shows, from the copy saved in its row
        card = cards.get(r["tmdb_id"]) or {"tmdb_id": r["tmdb_id"], "title": r["title"], "year": r["year"],
                                           "poster": r["poster_path"] and POSTER + r["poster_path"],
                                           "library": r, "missing": True}
        card["library"] = r
        out.append(card)
    return out


class LibraryUpdate(BaseModel):
    status: Literal["watchlist", "watched", "blocked"]
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    mood_match: int | None = Field(default=None, ge=1, le=5)
    mindset: str | None = Field(default=None, max_length=500)
    # "watched" as a block reason = "I've already seen it": saved as watched, not blocked
    block_reason: Literal["language", "watched", "theme", "actor", "mainstream", "other"] | None = None
    block_detail: str | None = Field(default=None, max_length=200)


@app.put("/library/{tmdb_id}")
def save_to_library(tmdb_id: int, body: LibraryUpdate, user=Depends(current_user), con=Depends(get_db),
                    catalog=Depends(get_catalog)):
    if tmdb_id not in catalog:
        raise HTTPException(404, "Film not found")
    film = catalog.cards([tmdb_id])[0]
    status, reason, detail = body.status, body.block_reason, body.block_detail
    if status == "blocked":
        if reason is None:
            raise HTTPException(422, "Tell us why you're rejecting this film")
        if reason == "watched":
            status, reason = "watched", None
        elif reason == "language":
            detail = film["language"]
        elif reason == "actor" and detail not in film["cast"]:
            raise HTTPException(422, "Pick one of this film's actors")
    else:
        reason = detail = None

    niche = user["niche"]
    if reason == "mainstream":
        niche = min(1.0, niche + 0.1)
    elif status == "watched" and (body.rating or 0) >= 4:  # loving a film pulls the lean toward it: famous or obscure
        niche += 0.1 * (film["obscurity"] - niche)
    # shortcut: no daily cap on niche drift yet; add one in P4 if a burst of ratings swings it too far
    con.execute("UPDATE users SET niche = ? WHERE id = ?", (niche, user["id"]))
    con.execute("""INSERT INTO library (user_id, tmdb_id, status, title, year, poster_path, rating, comment, mood_match,
                       mindset, block_reason, block_detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (user_id, tmdb_id) DO UPDATE SET status = excluded.status, rating = excluded.rating,
                       comment = excluded.comment, mood_match = excluded.mood_match, mindset = excluded.mindset,
                       block_reason = excluded.block_reason, block_detail = excluded.block_detail,
                       updated_at = CURRENT_TIMESTAMP""",
                (user["id"], tmdb_id, status, film["title"], film["year"], film["poster_path"],
                 body.rating if status == "watched" else None, body.comment if status == "watched" else None,
                 body.mood_match if status == "watched" else None, body.mindset if status == "watched" else None,
                 reason, detail))
    return with_state([film], user["id"], con)[0]


@app.delete("/library/{tmdb_id}")
def remove_from_library(tmdb_id: int, user=Depends(current_user), con=Depends(get_db)):
    """Remove from the watchlist, unwatch, or unblock."""
    con.execute("DELETE FROM library WHERE user_id = ? AND tmdb_id = ?", (user["id"], tmdb_id))
    return {"ok": True}


# ---- recommendations ----

class Ask(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    session: str = Field(min_length=1, max_length=64)  # one chat; "Find more" repeats the call with the same session


@app.post("/recommend")
def recommend(body: Ask, user=Depends(current_user), con=Depends(get_db), catalog=Depends(get_catalog)):
    """Up to 5 films for a message, never repeating within a session.

    shortcut: one LLM call (the imagined ideal film) + vector search; P3 adds clarifying questions, taste profiles
    from ratings and the second LLM call that checks the fit and writes the "why".
    """
    lib = con.execute("SELECT tmdb_id, block_reason, block_detail FROM library WHERE user_id = ?",
                      (user["id"],)).fetchall()
    shown = [r[0] for r in con.execute("SELECT tmdb_id FROM shown WHERE user_id = ? AND session = ?",
                                       (user["id"], body.session))]
    query, effects = query_for(body.message)
    hits = catalog.search(
        query, k=5,
        exclude=[r["tmdb_id"] for r in lib] + shown,  # watchlist, watched and blocked films never come back
        avoid_languages={r["block_detail"] for r in lib if r["block_reason"] == "language"},
        avoid_actors={r["block_detail"] for r in lib if r["block_reason"] == "actor"},
        avoid_genres=json.loads(user["genres_avoid"]),
        effects=effects, niche=user["niche"])
    con.executemany("INSERT OR IGNORE INTO shown (user_id, session, tmdb_id) VALUES (?, ?, ?)",
                    [(user["id"], body.session, i) for i, _ in hits])
    cards = with_state(catalog.cards([i for i, _ in hits]), user["id"], con)
    for c, (_, score) in zip(cards, hits):
        c["score"], c["why"] = round(score, 3), c["watch_when"]
    return {"films": cards}

