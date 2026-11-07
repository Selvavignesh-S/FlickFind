"""Turn a chat message into a search: an LLM imagines the ideal film for it, written like a film's mood document.

Searching with the raw message matches words, not moods ("a good cry" found films titled "Kiss and Cry"). The LLM
writes the film the user wants in the catalog's own vocabulary and layout (builder.embed.document), so the query
vector lands among films that would do that to the viewer.
The same call also pulls out the request's hard rules ("directed by Tarantino", "Indian", "from the 2010s"), which
filter the catalog before any mood ranking, and films named as references ("like Inception"), whose own vectors
steer the search.
Gemini Flash-Lite first, Groq as the fallback; if both fail, the raw message and keyword rules are used instead.
Temperature 0, so the same message gets the same reading (and results) every time.
"""
import datetime
import json
import os

import httpx
import numpy as np

from backend.catalog import embed_query
from backend.intent import effects_for
from builder.embed import document
from builder.vocab import ALL_TAGS, EFFECTS, PACES, TAGS

GEMINI_MODEL = "gemini-3.5-flash-lite"
GROQ_MODEL = "openai/gpt-oss-20b"
GENRES = ["Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary", "Drama", "Family", "Fantasy",
          "History", "Horror", "Music", "Mystery", "Romance", "Science Fiction", "TV Movie", "Thriller", "War", "Western"]

SCHEMA = {
    "type": "object",
    "properties": {
        "effects": {"type": "array", "items": {"type": "string", "enum": list(EFFECTS)}, "minItems": 1, "maxItems": 2},
        "genres": {"type": "array", "items": {"type": "string", "enum": GENRES}, "minItems": 1, "maxItems": 3},
        "mood_tags": {"type": "array", "items": {"type": "string", "enum": ALL_TAGS}, "minItems": 3, "maxItems": 6},
        "pace": {"type": "string", "enum": PACES},
        "watch_when": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
        "synopsis": {"type": "string"},
        "rules": {"type": "object", "properties": {  # each one only when the person states it
            "directors": {"type": "array", "items": {"type": "string"}},
            "actors": {"type": "array", "items": {"type": "string"}},
            "studios": {"type": "array", "items": {"type": "string"}},
            "countries": {"type": "array", "items": {"type": "string"}},  # ISO 3166-1 alpha-2, e.g. "IN"
            "languages": {"type": "array", "items": {"type": "string"}},  # ISO 639-1, e.g. "ml"
            "genres": {"type": "array", "items": {"type": "string", "enum": GENRES}},
            "year_from": {"type": "integer"},
            "year_to": {"type": "integer"},
            "max_runtime": {"type": "integer"},
            "documentary": {"type": "boolean"},
            "animation": {"type": "boolean"},
        }},
        "like": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "year": {"type": "integer"}}, "required": ["title"]}},
        "rules_summary": {"type": "string"},
    },
    "required": ["effects", "genres", "mood_tags", "pace", "watch_when", "keywords", "synopsis", "rules", "like",
                 "rules_summary"],
}
LIKE_WEIGHT = 0.6  # "films like X": how much the search follows X's own vector vs the imagined film

SYSTEM = f"""You help a film recommendation app. A person tells you how they feel and what they want from a film.
Describe the ideal film for them, in the same vocabulary the app uses to describe every film in its catalog.

Choose the effect for what they want the film to DO for them, not for how they feel now:
"I'm sad and want to laugh" is lift, "I want a good cry" is catharsis, "I'm stressed, I want to switch off" is escape.
Effects:
{chr(10).join(f"- {e}: {d}" for e, d in EFFECTS.items())}

Mood tags, 3 to 6, only from: {", ".join(f"{group}: {', '.join(tags)}" for group, tags in TAGS.items())}.
watch_when finishes the sentence "Watch this when ..." in under 15 words.
keywords: 3 to 8 short plot or theme keywords, like a film database would list.
synopsis: 2 or 3 sentences of an imagined film that would fit them perfectly. Never name a real film, and don't
repeat their wording unless it is about the story itself.
Respect what they rule out ("not gory", "nothing slow"): leave those qualities out of every field.

rules: hard requirements every result must meet. Fill a field ONLY when the person states that requirement;
otherwise leave it out (an empty rules object is normal for a mood-only request).
- directors / actors: full names as film databases write them ("tarantino" -> "Quentin Tarantino").
- studios: production companies they name, as film databases write them ("Ghibli" -> "Studio Ghibli", "A24",
  "Pixar" -> "Pixar", "Marvel" -> "Marvel Studios").
- A nationality or country ("Indian", "Korean films", "from France"): countries with its ISO code, no languages.
  A named language ("a Malayalam film", "in Japanese"): languages with its ISO 639-1 code, no countries.
- genres: only genres they ask for by name; every result must have all of them.
- year_from / year_to: "the 2010s" -> 2010 and 2019, "after 2015" -> 2016, "old" or "classic" -> year_to 1979,
  "recent" or "new" -> year_from three years before today.
- max_runtime in minutes ("under 90 minutes", "short" -> 100).
- documentary / animation: true when they ask for one, false when they rule it out.
like: films they name as a reference ("like Inception", "similar to Drishyam"), with the year if known. For these,
still fill every other field to describe what they want.
rules_summary: the rules in a few plain words for the person to see ("Indian thrillers", "directed by Quentin
Tarantino", "Malayalam, 2010s"); empty when there are no rules."""

_cache = {}  # message -> plan; only successes are kept, so a failed LLM call is retried next time
_gemini = None


def dated(message):
    return f"Today is {datetime.date.today().isoformat()}. Request: {message}"  # so "recent" means something


def ask_gemini(message):
    global _gemini
    from google import genai
    from google.genai import types
    _gemini = _gemini or genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    r = _gemini.models.generate_content(model=GEMINI_MODEL, contents=dated(message), config=types.GenerateContentConfig(
        system_instruction=SYSTEM, temperature=0, response_mime_type="application/json", response_json_schema=SCHEMA))
    return json.loads(r.text)


def ask_groq(message):
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=20,
                   headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                   json={"model": GROQ_MODEL, "temperature": 0, "reasoning_effort": "low",
                         "response_format": {"type": "json_schema", "json_schema": {"name": "film", "schema": SCHEMA}},
                         "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": dated(message)}]})
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def valid(plan):
    """The plan with anything outside the vocabulary dropped, or None if too little is left to search with."""
    plan["effects"] = [e for e in plan.get("effects", []) if e in EFFECTS][:2]
    plan["mood_tags"] = [t for t in dict.fromkeys(plan.get("mood_tags", [])) if t in ALL_TAGS][:6]
    plan["genres"] = [g for g in plan.get("genres", []) if g in GENRES][:3]
    if plan.get("pace") not in PACES:
        plan["pace"] = "medium"
    plan["rules"] = valid_rules(plan.get("rules") or {})
    plan["like"] = [x for x in plan.get("like") or [] if isinstance(x, dict) and str(x.get("title", "")).strip()][:3]
    ok = plan["effects"] and len(plan["mood_tags"]) >= 2 and str(plan.get("synopsis", "")).strip()
    return plan if ok else None


def valid_rules(r):
    """Only well-formed rules survive: a malformed one is dropped rather than filtering out everything."""
    names = lambda v: [str(x).strip() for x in v or [] if str(x).strip()][:5]  # noqa: E731
    year = lambda v: v if isinstance(v, int) and 1880 <= v <= 2100 else None  # noqa: E731
    out = {"directors": names(r.get("directors")), "actors": names(r.get("actors")), "studios": names(r.get("studios")),
           "countries": [c.upper() for c in r.get("countries") or [] if isinstance(c, str) and len(c) == 2],
           "languages": [c.lower() for c in r.get("languages") or [] if isinstance(c, str) and len(c) == 2],
           "genres": [g for g in r.get("genres") or [] if g in GENRES],
           "year_from": year(r.get("year_from")), "year_to": year(r.get("year_to"))}
    if out["year_from"] and out["year_to"] and out["year_from"] > out["year_to"]:
        out["year_from"], out["year_to"] = out["year_to"], out["year_from"]
    m = r.get("max_runtime")
    out["max_runtime"] = m if isinstance(m, int) and 30 <= m <= 600 else None
    for f in ("documentary", "animation"):
        out[f] = r[f] if isinstance(r.get(f), bool) else None
    return out


def understand(message):
    """The imagined ideal film for a message (cached), or None when no LLM could answer."""
    if message in _cache:
        return _cache[message]
    for name, ask in (("gemini", ask_gemini), ("groq", ask_groq)):
        try:
            plan = valid(ask(message))
        except Exception as e:  # rate limit, timeout, bad JSON: try the next one
            print(f"understand: {name} failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
            continue
        if plan:
            _cache[message] = plan
            return plan
    return None


def prepare(catalog, message):
    """Everything catalog.search needs for a chat message, plus what the app shows about how it was read:
    {"query_vec", "effects", "allowed", "exclude", "understood" (list of words), "notes" (list of sentences)}."""
    plan = understand(message)
    if plan is None:  # shortcut: no LLM available; search with the raw words and keyword rules, no hard rules
        return {"query_vec": embed_query(message), "effects": effects_for(message), "allowed": None, "exclude": [],
                "understood": [], "notes": ["The AI couldn't be reached, so this is a simple keyword search."],
                "asked_genres": []}
    text = document(", ".join(plan["genres"]), plan["mood_tags"], plan["effects"][0], plan["pace"],
                    str(plan["watch_when"]).removeprefix("Watch this when ").strip(),
                    ", ".join(map(str, plan["keywords"])), plan["synopsis"])
    query = embed_query(text)
    allowed, applied, notes = catalog.rules_mask(plan["rules"])
    summary = str(plan.get("rules_summary") or "").strip()
    understood = [summary] if summary and applied else applied  # plain words if the AI gave them, else the raw rules

    like, exclude = [], []
    for ref in plan["like"]:
        n = catalog.find_title(ref["title"], ref.get("year") if isinstance(ref.get("year"), int) else None)
        if n is None:
            notes.append(f"Couldn't find {ref['title']} in the catalog, so the search follows your description.")
        else:
            like.append(n)
            exclude += catalog.same_title(n)  # the reference itself (and its same-titled remakes) isn't a pick
    if like:
        ref_vec = catalog.vecs[like].mean(axis=0)
        query = LIKE_WEIGHT * ref_vec / np.linalg.norm(ref_vec) + (1 - LIKE_WEIGHT) * query
        query = (query / np.linalg.norm(query)).astype(np.float32)
        titles = catalog.table.take(like).select(["title", "year"]).to_pylist()
        understood.insert(0, "like " + " and ".join(f"{t['title']} ({t['year']})" for t in titles))
    if not allowed.any() and not notes:
        notes.append("No film in the catalog meets all of those requirements.")
    return {"query_vec": query, "effects": plan["effects"], "allowed": allowed, "exclude": exclude,
            "understood": understood, "notes": notes, "asked_genres": plan["rules"]["genres"]}
