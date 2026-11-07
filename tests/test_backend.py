import numpy as np
import pyarrow as pa
import pytest
from fastapi.testclient import TestClient

from backend import main, omdb
from backend.catalog import Catalog
from builder.embed import DIMS

FILMS = [  # tmdb_id, title, language, cast, genres, obscurity
    (1, "Alpha", "en", ["Ann", "Bob"], ["Comedy"], 0.1),
    (2, "Beta", "fr", ["Cyd"], ["Drama"], 0.9),
    (3, "Gamma", "en", ["Bob"], ["Horror"], 0.5),
    (4, "Delta", "ja", ["Dee"], ["Comedy"], 0.7),
    (5, "Epsilon", "en", ["Eve"], ["Drama"], 0.3),
    (6, "Zeta", "en", ["Fay"], ["Comedy"], 0.2),
]


def fake_catalog():
    vecs = np.zeros((len(FILMS), DIMS), dtype=np.float16)
    for n in range(len(FILMS)):
        vecs[n, 0] = 1 - n * 0.1  # film 1 is the closest match to every query, then 2, 3, ...
    cols = {
        "tmdb_id": [f[0] for f in FILMS], "imdb_id": [f"tt{f[0]}" for f in FILMS], "title": [f[1] for f in FILMS],
        "original_title": [f[1] for f in FILMS], "year": [2000] * 6, "runtime": [100] * 6,
        "language": [f[2] for f in FILMS], "genres": [f[4] for f in FILMS], "overview": ["A film."] * 6,
        "tagline": [None] * 6, "poster_path": ["/p.jpg"] * 6, "imdb_rating": [7.0] * 6, "imdb_votes": [1000] * 6,
        "director": [["Dir"]] * 6, "cast": [f[3] for f in FILMS], "providers_in": [[]] * 6,
        "mood_tags": [["tense"]] * 6, "effect": ["tension"] * 6, "pace": ["medium"] * 6, "intensity": [3] * 6,
        "watch_when": ["you want a ride."] * 6, "obscurity": [f[5] for f in FILMS],
    }
    table = pa.table(cols).append_column("vec", pa.FixedSizeListArray.from_arrays(pa.array(vecs.ravel()), DIMS))
    return Catalog(table, "test")


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("FLICKFIND_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("OMDB_API_KEY", raising=False)  # tests never call the real OMDb
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-bytes-long!")
    query = np.zeros(DIMS, dtype=np.float32)
    query[0] = 1
    monkeypatch.setattr(main, "embed_query", lambda text: query)
    main.app.dependency_overrides[main.get_catalog] = fake_catalog
    client = TestClient(main.app)
    token = client.post("/auth/register", json={"email": "a@b.co", "password": "password1", "name": "A"}).json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
    main.app.dependency_overrides.clear()


def recommend(api, session="s1"):
    return [f["tmdb_id"] for f in api.post("/recommend", json={"message": "x", "session": session}).json()["films"]]


def test_auth(api):
    assert api.post("/auth/register", json={"email": "A@B.co", "password": "password1", "name": "A"}).status_code == 409
    assert api.post("/auth/login", json={"email": "a@b.co", "password": "wrong-pass"}).status_code == 401
    assert api.post("/auth/login", json={"email": "a@b.co", "password": "password1"}).status_code == 200
    assert api.get("/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_library_films_never_recommended_and_no_repeats(api):
    assert recommend(api) == [1, 2, 3, 4, 5]
    assert recommend(api) == [6]  # Find more: same session, nothing repeats
    api.put("/library/6", json={"status": "watchlist"})
    api.put("/library/2", json={"status": "watched", "rating": 3})
    api.put("/library/3", json={"status": "blocked", "block_reason": "other"})
    assert recommend(api, "s2") == [1, 4, 5]


def test_unblock_brings_film_back(api):
    api.put("/library/1", json={"status": "blocked", "block_reason": "theme"})
    assert 1 not in recommend(api)
    api.delete("/library/1")
    assert 1 in recommend(api, "s2")


def test_block_reasons(api):
    assert api.put("/library/1", json={"status": "blocked"}).status_code == 422  # a reason is required
    api.put("/library/2", json={"status": "blocked", "block_reason": "language"})  # French: avoid French
    assert api.put("/library/4", json={"status": "blocked", "block_reason": "actor",
                                       "block_detail": "Nobody"}).status_code == 422
    api.put("/library/1", json={"status": "blocked", "block_reason": "actor", "block_detail": "Bob"})
    assert recommend(api) == [4, 5, 6]  # 3 has Bob too; 2 is French
    seen = api.put("/library/5", json={"status": "blocked", "block_reason": "watched"}).json()
    assert seen["library"]["status"] == "watched"  # "already watched" is saved as watched


def test_preferences_and_avoided_genres(api):
    assert api.put("/me/preferences", json={"genres_like": ["Comedy"], "genres_avoid": ["Comedy"]}).status_code == 422
    assert api.put("/me/preferences", json={"genres_avoid": ["Sci-Fi"]}).status_code == 422  # not in the catalog
    me = api.put("/me/preferences", json={"genres_like": ["Drama"], "genres_avoid": ["Comedy"], "about": "hi"}).json()
    assert me["genres_avoid"] == ["Comedy"] and me["about"] == "hi"
    assert recommend(api) == [2, 3, 5]


def test_niche_drift(api):
    assert api.get("/me").json()["niche"] == 0.25
    api.put("/library/2", json={"status": "watched", "rating": 5})  # obscurity 0.9
    assert api.get("/me").json()["niche"] == pytest.approx(0.25 + 0.1 * (0.9 - 0.25), abs=1e-3)
    before = api.get("/me").json()["niche"]
    api.put("/library/3", json={"status": "watched", "rating": 2})  # a low rating doesn't move it
    assert api.get("/me").json()["niche"] == before
    api.put("/library/1", json={"status": "blocked", "block_reason": "mainstream"})
    assert api.get("/me").json()["niche"] == pytest.approx(before + 0.1, abs=1e-3)


def test_library_lists_and_ratings(api):
    api.put("/library/2", json={"status": "watched", "rating": 4, "mood_match": 5, "mindset": "quiet evening"})
    watched = api.get("/library", params={"status": "watched"}).json()
    assert [f["tmdb_id"] for f in watched] == [2]
    assert watched[0]["ratings"]["flickfind"] == 4 and watched[0]["library"]["mindset"] == "quiet evening"
    assert api.get("/library", params={"status": "watchlist"}).json() == []
    assert api.get("/films/999").status_code == 404


def test_rotten_tomatoes_cached_and_capped(api, monkeypatch):
    calls = []
    monkeypatch.setenv("OMDB_API_KEY", "fake")
    monkeypatch.setattr(omdb, "fetch", lambda imdb_id, key: calls.append(imdb_id) or {"tt1": 91, "tt2": None}.get(imdb_id, 50))
    assert api.get("/films/1").json()["ratings"]["rotten_tomatoes"] == 91
    assert api.get("/films/2").json()["ratings"]["rotten_tomatoes"] is None  # OMDb has no RT score for it
    api.get("/films/1")
    assert calls == ["tt1", "tt2"]  # the second look at film 1 came from the cache

    monkeypatch.setattr(omdb, "PER_REQUEST", 2)
    films = recommend(api)  # 5 cards, 2 already cached, at most 2 fetched now
    assert len(calls) == 4 and len(films) == 5

    def broken(imdb_id, key):
        raise RuntimeError("Request limit reached!")
    monkeypatch.setattr(omdb, "fetch", broken)
    monkeypatch.setattr(omdb, "_paused_on", None)
    assert api.get("/films/6").json()["ratings"]["rotten_tomatoes"] is None  # a failure never breaks the card
    assert omdb._paused_on is not None  # and pauses OMDb calls for the rest of the day


def test_effects_for():
    from backend.intent import effects_for
    assert effects_for("I'm sad and want to laugh") == ["lift"]
    assert effects_for("I want a good cry") == ["catharsis"]
    assert effects_for("a cosy film for a rainy evening") == ["comfort"]
    assert effects_for("something tense, then a laugh") == ["tension", "lift"]
    assert effects_for("long week, I want to switch off") == ["escape"]
    assert effects_for("I feel numb and don't want to be cheered up") == ["numb"]
    assert effects_for("anything really") == []


def small_catalog(vecs, effects, obscurity, ratings):
    """A catalog of len(vecs) films whose vectors, effects, obscurity and IMDb ratings are given."""
    n = len(vecs)
    v = np.zeros((n, DIMS), dtype=np.float16)
    v[:, :len(vecs[0])] = vecs
    v /= np.linalg.norm(v.astype(np.float32), axis=1, keepdims=True)
    cols = {"tmdb_id": list(range(1, n + 1)), "language": ["en"] * n, "cast": [[]] * n, "genres": [[]] * n,
            "effect": effects, "obscurity": obscurity, "imdb_rating": ratings}
    return Catalog(pa.table(cols).append_column("vec", pa.FixedSizeListArray.from_arrays(pa.array(v.ravel()), DIMS)), "t")


def test_ranking_effect_popularity_and_variety():
    q = np.zeros(DIMS, dtype=np.float32)
    q[0] = 1
    ids = lambda hits: [i for i, _ in hits]  # noqa: E731

    # equal mood match: the film with the asked-for effect wins
    c = small_catalog([[1, 0.1], [1, 0.1]], ["lift", "catharsis"], [0.5, 0.5], [7.0, 7.0])
    assert ids(c.search(q, k=1, effects=["catharsis"])) == [2]

    # a famous, well-rated film just behind an obscure one: Normal users get the famous one, Niche users the closer fit
    c = small_catalog([[1, 0.15], [1, 0.25]], ["lift", "lift"], [0.95, 0.0], [6.0, 8.5])
    assert ids(c.search(q, k=1, niche=0.25)) == [2]
    assert ids(c.search(q, k=1, niche=1.0)) == [1]

    # films 1 and 2 are near-copies off to one side of the query, film 3 is about as close on the other side:
    # without variety the picks are 1, 2; with it, 1, 3
    c = small_catalog([[1, 0.3, 0], [1, 0.31, 0], [1, 0, 0.32]], ["lift"] * 3, [0.5] * 3, [7.0] * 3)
    assert ids(c.search(q, k=2)) == [1, 3]
