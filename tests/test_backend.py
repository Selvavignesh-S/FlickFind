import json
import os
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


EXTRA = {  # tmdb_id: director, production countries, year, runtime, documentary, animation, original title
    1: ("Quentin Tarantino", ["US"], 1994, 154, False, False, "Alpha"),
    2: ("Agnès Varda", ["FR"], 1962, 90, False, False, "Cléo de 5 à 7"),
    3: ("Bong Joon-ho", ["KR"], 2019, 132, False, False, "Gamma"),
    4: ("Hayao Miyazaki", ["JP"], 2001, 125, False, True, "Delta"),
    5: ("Quentin Tarantino", ["US"], 2003, 111, False, False, "Epsilon"),
    6: ("Anand Patwardhan", ["IN"], 1992, 85, True, False, "Zeta"),
}


def fake_table():
    vecs = np.zeros((len(FILMS), DIMS), dtype=np.float16)
    for n in range(len(FILMS)):
        vecs[n, 0] = 1 - n * 0.1  # film 1 is the closest match to every query, then 2, 3, ...
    cols = {
        "tmdb_id": [f[0] for f in FILMS], "imdb_id": [f"tt{f[0]}" for f in FILMS], "title": [f[1] for f in FILMS],
        "original_title": [EXTRA[f[0]][6] for f in FILMS], "year": [EXTRA[f[0]][2] for f in FILMS],
        "runtime": [EXTRA[f[0]][3] for f in FILMS], "countries": [EXTRA[f[0]][1] for f in FILMS],
        "documentary": [EXTRA[f[0]][4] for f in FILMS], "animation": [EXTRA[f[0]][5] for f in FILMS],
        "companies": [["Studio Ghibli"] if f[0] == 4 else [] for f in FILMS],
        "language": [f[2] for f in FILMS], "genres": [f[4] for f in FILMS], "overview": ["A film."] * 6,
        "tagline": [None] * 6, "poster_path": ["/p.jpg"] * 6, "imdb_rating": [7.0] * 6, "imdb_votes": [1000] * 6,
        "director": [[EXTRA[f[0]][0]] for f in FILMS], "cast": [f[3] for f in FILMS], "providers_in": [[]] * 6,
        "mood_tags": [["tense"]] * 6, "effect": ["tension"] * 6, "pace": ["medium"] * 6, "intensity": [3] * 6,
        "watch_when": ["you want a ride."] * 6, "obscurity": [f[5] for f in FILMS], "group": ["english"] * 6,
    }
    return pa.table(cols).append_column("vec", pa.FixedSizeListArray.from_arrays(pa.array(vecs.ravel()), DIMS))


def fake_catalog():
    return Catalog(fake_table(), "test")


@pytest.fixture(autouse=True)
def no_llm_calls(monkeypatch):
    """Tests never reach Gemini or Groq (network, quota); a test that needs an answer stubs it."""
    from backend import understand

    def blocked(message, *args, **kwargs):
        raise AssertionError("a test tried to call a real LLM")
    monkeypatch.setattr(understand, "ask_gemini", blocked)
    monkeypatch.setattr(understand, "ask_groq", blocked)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("FLICKFIND_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("OMDB_API_KEY", raising=False)  # tests never call the real OMDb
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-bytes-long!")
    query = np.zeros(DIMS, dtype=np.float32)
    query[0] = 1
    plain = {"query_vec": query, "effects": [], "allowed": None, "exclude": [], "understood": [], "notes": [],
             "asked_genres": [], "clarify": None}
    monkeypatch.setattr(main, "prepare", lambda catalog, text, about="": dict(plain))
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
    me = api.get("/me").json()
    assert (me["niche"], me["taste"], me["niche_questions"]) == (0.5, "Balanced", False)  # new users: no lean
    api.put("/library/1", json={"status": "watched", "rating": 5})  # a famous film (obscurity 0.1) pulls mainstream
    assert api.get("/me").json()["niche"] == pytest.approx(0.5 + 0.1 * (0.1 - 0.5), abs=1e-3)
    api.put("/library/2", json={"status": "watched", "rating": 5})  # an obscure one (0.9) pulls the other way
    assert api.get("/me").json()["niche"] == pytest.approx(0.46 + 0.1 * (0.9 - 0.46), abs=1e-3)
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


def small_catalog(vecs, effects, obscurity, ratings, groups=None):
    """A catalog of len(vecs) films whose vectors, effects, obscurity, IMDb ratings (and language groups) are given."""
    n = len(vecs)
    v = np.zeros((n, DIMS), dtype=np.float16)
    v[:, :len(vecs[0])] = vecs
    v /= np.linalg.norm(v.astype(np.float32), axis=1, keepdims=True)
    cols = {"tmdb_id": list(range(1, n + 1)), "title": [f"F{i}" for i in range(n)], "original_title": [None] * n,
            "language": ["en"] * n, "cast": [[]] * n, "genres": [[]] * n, "director": [[]] * n, "countries": [[]] * n,
            "year": [2000] * n, "runtime": [100] * n, "documentary": [False] * n, "animation": [False] * n,
            "effect": effects, "obscurity": obscurity, "imdb_rating": ratings, "imdb_votes": [1000] * n,
            "group": groups or ["english"] * n}
    return Catalog(pa.table(cols).append_column("vec", pa.FixedSizeListArray.from_arrays(pa.array(v.ravel()), DIMS)), "t")


def test_ranking_effect_lean_quality_and_variety(monkeypatch):
    q = np.zeros(DIMS, dtype=np.float32)
    q[0] = 1
    ids = lambda hits: [i for i, _ in hits]  # noqa: E731

    # equal mood match: the film with the asked-for effect wins
    c = small_catalog([[1, 0.1], [1, 0.1]], ["lift", "catharsis"], [0.5, 0.5], [7.0, 7.0])
    assert ids(c.search(q, k=1, effects=["catharsis"])) == [2]

    # a little-known film fits slightly better than a famous one: a new user gets the better fit; only a learned
    # mainstream lean brings the famous one forward, and a niche lean keeps the better fit
    c = small_catalog([[1, 0.15], [1, 0.25]], ["lift", "lift"], [0.95, 0.0], [7.0, 7.0])
    assert ids(c.search(q, k=1)) == [1]
    assert ids(c.search(q, k=1, niche=0.0)) == [2]
    assert ids(c.search(q, k=1, niche=1.0)) == [1]

    # equal fit, one Indian film rated 7.0 and one English film rated 6.8: quality is judged within each language,
    # where 7.0 is the lowest of the Indian films and 6.8 the highest of the English ones, so the English film wins
    away = [0, 0, 1]
    c = small_catalog([[1, 0.2, 0], [1, 0.2, 0], away, away, away, away], ["lift"] * 6, [0.5] * 6,
                      [7.0, 6.8, 7.5, 8.0, 5.0, 6.0], ["indian", "english", "indian", "indian", "english", "english"])
    assert ids(c.search(q, k=1)) == [2]

    # outside the shortlist of best fits nothing gets in, however good or famous
    from backend import catalog as catalog_module
    monkeypatch.setattr(catalog_module, "SHORTLIST", 1)
    c = small_catalog([[1, 0.1], [1, 0.2]], ["lift", "lift"], [0.9, 0.0], [5.0, 9.0])
    assert ids(c.search(q, k=2, niche=0.0)) == [1]
    monkeypatch.undo()

    # films 1 and 2 are near-copies off to one side of the query, film 3 is about as close on the other side:
    # without variety the picks are 1, 2; with it, 1, 3
    c = small_catalog([[1, 0.3, 0], [1, 0.31, 0], [1, 0, 0.32]], ["lift"] * 3, [0.5] * 3, [7.0] * 3)
    assert ids(c.search(q, k=2)) == [1, 3]

    # a remake with the same title as an earlier pick is skipped
    c = small_catalog([[1, 0.1], [1, 0.12], [1, 0.3]], ["lift"] * 3, [0.5] * 3, [7.0] * 3)
    c.title_key = ["drishyam", "drishyam", "papanasam"]
    assert ids(c.search(q, k=2)) == [1, 3]


def test_query_rewrite_fallbacks_and_cache(monkeypatch):
    from backend import understand
    monkeypatch.setattr(understand, "_cache", {})
    texts = []
    monkeypatch.setattr(understand, "embed_query", lambda t: texts.append(t) or np.ones(DIMS, dtype=np.float32))
    plan = {"effects": ["catharsis", "made-up"], "genres": ["Drama", "Nope"], "mood_tags": ["tender", "bittersweet", "x"],
            "pace": "glacial", "watch_when": "Watch this when you need to let it out.", "keywords": ["loss", "family"],
            "synopsis": "A widower and his daughter learn to talk again.", "rules": {}, "like": []}
    calls = []
    catalog = fake_catalog()

    def down(message, *args, **kwargs):
        calls.append("gemini")
        raise RuntimeError("429 quota")
    monkeypatch.setattr(understand, "ask_gemini", down)
    monkeypatch.setattr(understand, "ask_groq", lambda m, *a, **kw: calls.append("groq") or dict(plan))

    p = understand.prepare(catalog, "I want a good cry")  # Gemini down: Groq answered
    assert p["effects"] == ["catharsis"] and p["allowed"].all() and p["notes"] == []
    assert texts[-1].startswith("Drama. Mood: tender, bittersweet. Effect: catharsis. Pace: medium. Watch this when you")
    assert "good cry" not in texts[-1]  # the search text is the imagined film, not the message
    understand.prepare(catalog, "I want a good cry")
    assert calls == ["gemini", "groq"]  # the second time came from the cache (Groq's first model answered)

    monkeypatch.setattr(understand, "ask_groq", down)
    calls.clear()
    p = understand.prepare(catalog, "make me laugh")  # all down: raw message + keyword rules, and the app is told
    assert calls == ["gemini", "gemini", "gemini"]  # Gemini, then both Groq models were tried (the stub logs "gemini")
    assert (p["effects"], p["allowed"], texts[-1]) == (["lift"], None, "make me laugh") and p["notes"]
    monkeypatch.setattr(understand, "ask_gemini", lambda m, *a: dict(plan))
    assert understand.prepare(catalog, "make me laugh")["effects"] == ["catharsis"]  # a failure was not cached


def test_rules_filter_the_catalog():
    c = fake_catalog()
    ids = lambda mask: [int(i) for i in c.ids[mask]]  # noqa: E731
    assert ids(c.rules_mask({"directors": ["tarantino"]})[0]) == [1, 5]  # surname, any case
    assert ids(c.rules_mask({"directors": ["Bong Joon Ho"]})[0]) == [3]  # hyphen or not
    assert ids(c.rules_mask({"countries": ["IN"]})[0]) == [6]  # made in India (in English)
    assert ids(c.rules_mask({"countries": ["IN"], "languages": ["hi", "ta"]})[0]) == []  # both must hold
    assert ids(c.rules_mask({"languages": ["fr"]})[0]) == [2]
    assert ids(c.rules_mask({"year_from": 1990, "year_to": 1999})[0]) == [1, 6]
    assert ids(c.rules_mask({"max_runtime": 90})[0]) == [2, 6]
    assert ids(c.rules_mask({"genres": ["Comedy"], "animation": True})[0]) == [4]
    assert ids(c.rules_mask({"documentary": False, "directors": ["Anand Patwardhan"]})[0]) == []
    ok, understood, notes = c.rules_mask({"directors": ["Quentin Tarantino", "Nobody Atall"]})
    assert ids(ok) == [1, 5] and understood == ["directed by Quentin Tarantino"]
    assert notes == ["No films directed by Nobody Atall are in the catalog yet."]
    assert ids(c.rules_mask({"studios": ["ghibli"]})[0]) == [4]
    ok, _, notes = c.rules_mask({"studios": ["A24"]})
    assert ids(ok) == [] and notes == ["No films from A24 are in the catalog yet."]
    assert ids(c.rules_mask({})[0]) == [1, 2, 3, 4, 5, 6]  # no rules: everything


def test_find_title():
    c = fake_catalog()
    assert c.find_title("cleo de 5 a 7") == 1  # original title, accents ignored (index 1 = film 2)
    assert c.find_title("ALPHA") == 0
    assert c.find_title("No Such Film") is None


def test_references_and_rules_in_recommend(api, monkeypatch):
    from backend import understand
    monkeypatch.setattr(understand, "_cache", {})
    monkeypatch.setattr(understand, "embed_query", lambda t: np.eye(1, DIMS, 0, dtype=np.float32)[0])
    base = {"effects": ["tension"], "genres": ["Drama"], "mood_tags": ["tense", "bleak"], "pace": "medium",
            "watch_when": "x", "keywords": ["a", "b", "c"], "synopsis": "y"}
    answers = {
        "tarantino films": {**base, "rules": {"directors": ["Quentin Tarantino"]}, "like": []},
        "like alpha": {**base, "rules": {}, "like": [{"title": "Alpha"}, {"title": "Missing Film"}]},
        "nolan films": {**base, "rules": {"directors": ["Christopher Nolan"]}, "like": []},
        "a comedy please": {**base, "rules": {"genres": ["Comedy"]}, "like": []},
    }
    monkeypatch.setattr(understand, "ask_gemini", lambda m, *a: dict(answers[m]))
    monkeypatch.setattr(main, "prepare", understand.prepare)
    ask = lambda m, s: api.post("/recommend", json={"message": m, "session": s}).json()  # noqa: E731

    r = ask("tarantino films", "s1")
    assert [f["tmdb_id"] for f in r["films"]] == [1, 5] and r["understood"] == ["directed by Quentin Tarantino"]
    assert ask("tarantino films", "s1")["films"] == []  # Find more: all of his films were shown

    r = ask("like alpha", "s2")
    assert 1 not in [f["tmdb_id"] for f in r["films"]] and len(r["films"]) == 5  # the reference isn't recommended
    assert r["understood"][0] == "like Alpha (1994)" and "Missing Film" in r["notes"][0]

    r = ask("nolan films", "s3")
    assert r["films"] == [] and r["notes"] == ["No films directed by Christopher Nolan are in the catalog yet."]

    api.put("/me/preferences", json={"genres_avoid": ["Comedy"]})
    assert [f["tmdb_id"] for f in ask("a comedy please", "s4")["films"]] == [1, 4, 6]  # asked by name: shown anyway


def test_fit_check_and_clarifying_question(api, monkeypatch):
    from backend import fitcheck, understand
    monkeypatch.setattr(understand, "_cache", {})
    monkeypatch.setattr(understand, "embed_query", lambda t: np.eye(1, DIMS, 0, dtype=np.float32)[0])
    base = {"effects": ["lift"], "genres": ["Comedy"], "mood_tags": ["funny", "joyful"], "pace": "fast",
            "watch_when": "x", "keywords": ["a", "b", "c"], "synopsis": "y", "rules": {}, "like": []}
    plans = {"cheer me up": {**base, "clarify": {"question": "", "options": []}},
             "i'm sad": {**base, "clarify": {"question": "Lift your mood or have a good cry?",
                                             "options": ["Lift my mood", "A good cry"]}}}
    fits = {1: 9, 2: 4, 3: 8, 4: 6, 5: 10, 6: 7}  # film 2 and 4 don't fit; 6 is more than 2 below the best (10)

    def llm(message, system=understand.SYSTEM, schema=None):  # stands in for Gemini: the message arrives undated
        if system == fitcheck.SYSTEM:
            ids = [c["id"] for c in json.loads(message)["candidates"]]
            return {"films": [{"id": i, "fit": fits[i], "why": f"Because {i}."} for i in ids]}
        return dict(plans[message])
    monkeypatch.setattr(understand, "ask_gemini", llm)
    monkeypatch.setattr(main, "prepare", understand.prepare)
    ask = lambda m, s, **kw: api.post("/recommend", json={"message": m, "session": s, **kw}).json()  # noqa: E731

    r = ask("cheer me up", "s1")
    assert [(f["tmdb_id"], f["why"]) for f in r["films"]] == [(5, "Because 5."), (1, "Because 1."), (3, "Because 3.")]
    assert r["more"] and r["question"] is None
    r = ask("cheer me up", "s1")  # every candidate was judged, so Find more has nothing left
    assert r["films"] == [] and not r["more"]

    r = ask("i'm sad", "s2")  # too vague: a question instead of films, and nothing counts as seen
    assert r["films"] == [] and r["options"] == ["Lift my mood", "A good cry"]
    assert len(ask("i'm sad", "s2", clarify=False)["films"]) == 3  # "just show me something"


def test_fit_check_falls_back_without_llm(api):
    films = api.post("/recommend", json={"message": "x", "session": "s"}).json()["films"]  # LLMs blocked in tests
    assert len(films) == 5 and films[0]["why"] == "Watch this when you want a ride."


def test_taste_reorders_equal_fits():
    q = np.zeros(DIMS, dtype=np.float32)
    q[0] = 1
    ids = lambda hits: [i for i, _ in hits]  # noqa: E731
    # three films that fit the request exactly as well, pointing different ways otherwise
    c = small_catalog([[1, 0.3, 0], [1, 0, 0.3], [1, -0.3, 0]], ["lift"] * 3, [0.5] * 3, [7.0] * 3)
    assert c.taste({}) is None and c.taste({999: 1.0}) is None  # nothing rated: no taste at all
    assert ids(c.search(q, k=1, liked=c.taste({2: 1.0}))) == [2]  # close to a loved film: first
    assert ids(c.search(q, k=1, disliked=c.taste({1: 1.0}))) == [3]  # the film furthest from a disliked one: first
    c.genres = [[], ["Comedy"], []]
    assert ids(c.search(q, k=1, liked_genres=["Comedy"])) == [2]
    assert ids(c.search(q, k=1, seen_before=[1]))[0] != 1  # shown in an earlier chat: a fresh equal goes first

    # taste builds up: one loved film is a fifth of a full taste, five or more count in full
    assert np.linalg.norm(c.taste({2: 1.0})) == pytest.approx(0.2, abs=1e-3)
    assert c.language_shares([1]) == {"en": pytest.approx(0.2)}


def test_recommend_uses_the_users_activity(api, monkeypatch):
    seen = {}
    original = Catalog.search

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Catalog, "search", spy)
    ask = lambda s: api.post("/recommend", json={"message": "x", "session": s})  # noqa: E731

    ask("s1")  # a new user: no taste, nothing seen before
    assert seen["liked"] is None and seen["disliked"] is None and seen["seen_before"] == []
    api.put("/library/2", json={"status": "watched", "rating": 5})
    api.put("/library/3", json={"status": "blocked", "block_reason": "theme"})
    api.put("/library/4", json={"status": "watchlist"})  # says nothing about taste
    api.put("/me/preferences", json={"genres_like": ["Drama"]})
    ask("s2")
    assert seen["liked"] is not None and seen["disliked"] is not None and seen["liked_genres"] == ["Drama"]
    assert 1 in seen["seen_before"]  # shown in chat s1


def test_api_reloads_a_newly_packed_catalog(tmp_path, monkeypatch):
    import os

    import pyarrow.parquet as pq

    from builder.embed import MODEL
    pq.write_table(fake_table(), tmp_path / "catalog-v1.parquet")
    manifest = {"version": "v1", "file": "catalog-v1.parquet", "embedding": {"model": MODEL, "dims": DIMS}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(main, "CATALOG_DIR", tmp_path)
    monkeypatch.setattr(main, "_loaded", {})
    first = main.get_catalog()
    assert main.get_catalog() is first and first.version == "v1"  # loaded once
    (tmp_path / "manifest.json").write_text(json.dumps({**manifest, "version": "v2"}))
    os.utime(tmp_path / "manifest.json", (1, 2_000_000_000))  # a new pack
    assert main.get_catalog().version == "v2"


def beyond_card(tmdb_id, **kw):
    return {"tmdb_id": tmdb_id, "imdb_id": f"tt{tmdb_id}", "title": f"Web {tmdb_id}", "original_title": None,
            "year": 2024, "runtime": 110, "language": "ml", "genres": ["Comedy"], "overview": "A film.", "tagline": None,
            "poster_path": None, "poster": None, "imdb_rating": None, "imdb_votes": None, "director": ["Dileesh Pothan"],
            "cast": ["Fahadh Faasil"], "providers_in": [], "countries": ["IN"], "companies": ["Bhavana Studios"],
            "documentary": False, "animation": False, "mood_tags": [], "effect": "", "pace": "", "intensity": None,
            "watch_when": "", "obscurity": 0.5, "beyond": True, **kw}


def test_beyond_rules_on_tmdb_cards():
    from backend.beyond import obeys
    c = beyond_card(1)
    assert obeys(c, {"directors": ["pothan"], "languages": ["ml"], "countries": ["IN"], "year_from": 2020})
    assert not obeys(c, {"languages": ["ta"]}) and not obeys(c, {"genres": ["Comedy", "Drama"]})
    assert not obeys(c, {"max_runtime": 90}) and not obeys(c, {"documentary": True})
    assert obeys(c, {"studios": ["Bhavana"]}) and not obeys(c, {"actors": ["Mohanlal"]})


def test_beyond_discover_parameters(monkeypatch):
    from backend import beyond
    calls = []

    def fake(path, **params):
        calls.append((path, params))
        if path == "/search/person":
            return {"results": [{"id": 77}] if params["query"] == "Known Person" else []}
        return {"results": [{"id": 5}, {"id": 6}]}
    monkeypatch.setattr(beyond, "tmdb", fake)
    assert beyond.discover({}) == []  # no rules: nothing to discover
    ids = beyond.discover({"languages": ["ml"], "genres": ["Comedy"], "year_from": 2010, "year_to": 2019,
                           "directors": ["Known Person"], "documentary": False})
    params = calls[-1][1]
    assert ids == [5, 6] and params["with_original_language"] == "ml" and params["with_crew"] == "77"
    assert params["with_genres"] == "35" and params["without_genres"] == "99"
    assert params["primary_release_date.gte"] == "2010-01-01" and params["primary_release_date.lte"] == "2019-12-31"
    assert beyond.discover({"directors": ["Nobody Known"]}) == []  # a person TMDB doesn't know: nothing obeys


def test_beyond_search_merges_sources(monkeypatch):
    from backend import beyond
    c = fake_catalog()
    monkeypatch.setattr(beyond, "found", {})
    monkeypatch.setattr(beyond, "web_titles", lambda m: [("Alpha", None), ("Brand New", 2024)])
    monkeypatch.setattr(beyond, "find_title", lambda t, y=None: {"Alpha": 1, "Brand New": 900}.get(t))
    monkeypatch.setattr(beyond, "discover", lambda rules: [3, 901])
    monkeypatch.setattr(beyond, "recommendations", lambda like: ([5, 902], [4]))  # film 4 is the reference itself
    monkeypatch.setattr(beyond, "card", lambda i: beyond_card(i, language="ta" if i == 902 else "ml"))
    cards = beyond.search(c, "x", {}, [{"title": "Delta"}], exclude=[5])
    # web results first (1, 900), then recommendations (902; 5 already seen, 4 is the reference), then discover
    assert [x["tmdb_id"] for x in cards] == [1, 900, 902, 3, 901] and set(beyond.found) == {900, 901, 902}
    assert [x.get("beyond", False) for x in cards] == [False, True, True, False, True]
    cards = beyond.search(c, "x", {"languages": ["ml"]}, [], exclude=[])
    assert 902 not in [x["tmdb_id"] for x in cards]  # a Tamil film breaks a Malayalam rule
    assert len(beyond.search(c, "x", {}, [], exclude=[], limit=2)) == 2


def test_beyond_route_queues_new_finds(api, monkeypatch):
    from backend import beyond
    plan = {"rules": {}, "like": []}
    monkeypatch.setattr(main, "understand", lambda message, about="": plan)
    monkeypatch.setattr(beyond, "found", {900: beyond_card(900)})
    monkeypatch.setattr(beyond, "search", lambda catalog, message, rules, like, exclude, limit=10:
                        catalog.cards([2]) + [beyond_card(900)])
    r = api.post("/beyond", json={"message": "malayalam comedies from 2024", "session": "s"}).json()
    assert [f["tmdb_id"] for f in r["films"]] == [2, 900] and "new to FlickFind" in r["notes"][0]
    assert api.put("/library/900", json={"status": "watchlist"}).status_code == 200  # a found film can be saved
    import sqlite3
    rows = sqlite3.connect(os.environ["FLICKFIND_DB"]).execute("SELECT tmdb_id, imdb_id, request FROM web_finds").fetchall()
    assert rows == [(900, "tt900", "malayalam comedies from 2024")]


def test_curation_reads_web_finds(tmp_path, monkeypatch):
    import sqlite3

    from builder import curate
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("FLICKFIND_DB", str(db_path))
    assert curate.web_finds() == set()  # no app database yet
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE web_finds (tmdb_id INTEGER PRIMARY KEY, imdb_id TEXT, title TEXT, year INTEGER, request TEXT)")
    con.execute("INSERT INTO web_finds VALUES (1, 'tt1', 'A', 2024, 'x'), (2, NULL, 'B', 2024, 'x')")
    con.commit()
    assert curate.web_finds() == {"tt1"}
