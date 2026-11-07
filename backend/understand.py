"""Turn a chat message into a search: an LLM imagines the ideal film for it, written like a film's mood document.

Searching with the raw message matches words, not moods ("a good cry" found films titled "Kiss and Cry"). The LLM
writes the film the user wants in the catalog's own vocabulary and layout (builder.embed.document), so the query
vector lands among films that would do that to the viewer.
Gemini Flash-Lite first, Groq as the fallback; if both fail, the raw message and keyword rules are used instead.
"""
import json
import os

import httpx

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
    },
    "required": ["effects", "genres", "mood_tags", "pace", "watch_when", "keywords", "synopsis"],
}

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
Respect what they rule out ("not gory", "nothing slow"): leave those qualities out of every field."""

_cache = {}  # message -> plan; only successes are kept, so a failed LLM call is retried next time
_gemini = None


def ask_gemini(message):
    global _gemini
    from google import genai
    from google.genai import types
    _gemini = _gemini or genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    r = _gemini.models.generate_content(model=GEMINI_MODEL, contents=message, config=types.GenerateContentConfig(
        system_instruction=SYSTEM, temperature=0.3, response_mime_type="application/json", response_json_schema=SCHEMA))
    return json.loads(r.text)


def ask_groq(message):
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=20,
                   headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                   json={"model": GROQ_MODEL, "temperature": 0.3, "reasoning_effort": "low",
                         "response_format": {"type": "json_schema", "json_schema": {"name": "film", "schema": SCHEMA}},
                         "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": message}]})
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def valid(plan):
    """The plan with anything outside the vocabulary dropped, or None if too little is left to search with."""
    plan["effects"] = [e for e in plan.get("effects", []) if e in EFFECTS][:2]
    plan["mood_tags"] = [t for t in dict.fromkeys(plan.get("mood_tags", [])) if t in ALL_TAGS][:6]
    plan["genres"] = [g for g in plan.get("genres", []) if g in GENRES][:3]
    if plan.get("pace") not in PACES:
        plan["pace"] = "medium"
    ok = plan["effects"] and len(plan["mood_tags"]) >= 2 and str(plan.get("synopsis", "")).strip()
    return plan if ok else None


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


def query_for(message):
    """(query vector, effects asked for) for a chat message."""
    plan = understand(message)
    if plan is None:  # shortcut: no LLM available; search with the raw words and keyword rules
        return embed_query(message), effects_for(message)
    text = document(", ".join(plan["genres"]), plan["mood_tags"], plan["effects"][0], plan["pace"],
                    str(plan["watch_when"]).removeprefix("Watch this when ").strip(),
                    ", ".join(map(str, plan["keywords"])), plan["synopsis"])
    return embed_query(text), plan["effects"]
