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

from backend.catalog import NAMES, embed_query, words
from backend.intent import effects_for
from builder.embed import document
from builder.vocab import ALL_TAGS, EFFECTS, PACES, TAGS

GEMINI_MODEL = "gemini-3.5-flash-lite"
# Groq backups in order. Each model has its own free limit of 8,000 tokens a minute (about two of these requests),
# so a second model doubles the cover while Gemini is overloaded.
GROQ_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
GENRES = ["Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary", "Drama", "Family", "Fantasy",
          "History", "Horror", "Music", "Mystery", "Romance", "Science Fiction", "TV Movie", "Thriller", "War", "Western"]

RULE_FIELDS = ["directors", "actors", "studios", "countries", "languages", "genres", "not_countries", "not_languages", "not_genres", "year_from", "year_to", "max_runtime", "documentary", "animation", "well_rated"]

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
            "not_countries": {"type": "array", "items": {"type": "string"}},  # "no Indian films" -> ["IN"]
            "not_languages": {"type": "array", "items": {"type": "string"}},
            "not_genres": {"type": "array", "items": {"type": "string", "enum": GENRES}},
            "year_from": {"type": "integer"},
            "year_to": {"type": "integer"},
            "max_runtime": {"type": "integer"},
            "documentary": {"type": "boolean"},
            "animation": {"type": "boolean"},
            "well_rated": {"type": "boolean"},
        }},
        "like": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "year": {"type": "integer"}}, "required": ["title"]}},
        # the exact words of the request that state each rule: a rule without them is dropped (see valid_rules)
        "rules_quotes": {"type": "object", "properties": {f: {"type": "string"} for f in RULE_FIELDS}},
        "clarify": {"type": "object", "properties": {
            "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}}},
    },
    "required": ["effects", "genres", "mood_tags", "pace", "watch_when", "keywords", "synopsis", "rules", "like",
                 "rules_quotes", "clarify"],
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

rules: hard requirements every result must meet. Fill a field ONLY when the person states that requirement in
their message; otherwise leave it out. An empty rules object is normal: most requests are about a mood. Never add a
director, actor, studio, country, language, years or runtime they didn't ask for, even if it would suit them.
rules_quotes: for every rule you fill, the few words of their message that name it, copied exactly, e.g.
"directors": "directed by tarantino", "not_countries": "dont recommend indian movies". A rule you can't quote from
their message must stay empty.
- directors / actors: full names as film databases write them ("tarantino" -> "Quentin Tarantino").
- studios: production companies they name, as film databases write them ("Ghibli" -> "Studio Ghibli", "A24",
  "Pixar" -> "Pixar", "Marvel" -> "Marvel Studios").
- A nationality or country ("Indian", "Korean films", "from France"): countries with its ISO code, no languages.
  A named language ("a Malayalam film", "in Japanese"): languages with its ISO 639-1 code, no countries.
- genres: only genres they ask for by name; every result must have all of them.
- not_countries / not_languages / not_genres: what they rule out ("no Indian movies" -> not_countries ["IN"],
  "nothing animated" -> animation false). Something they rule out never goes in countries, languages or genres.
- year_from / year_to: "the 2010s" -> 2010 and 2019, "after 2015" -> 2016, "old" or "classic" -> year_to 1979,
  "recent" or "new" -> year_from three years before today.
- max_runtime in minutes ("under 90 minutes", "short" -> 100).
- documentary / animation: true when they ask for one, false when they rule it out.
- well_rated: true only when they ask for good ratings, acclaimed, top-rated or the best films.
like: only films they name themselves as a reference ("like Inception", "similar to Drishyam"), with the year if
known; never add reference films of your own. For these, still fill every other field to describe what they want.
clarify: ONLY when the request is too vague to tell what they want the film to do for them ("I'm sad", "something
good", "a movie for tonight", "bored"), ask one short, warm question with 2 to 4 short answer options, e.g. "I'm sad"
-> question "Do you want to lift your mood, have a good cry, or sit with the feeling?", options ["Lift my mood",
"A good cry", "Sit with it"]. Leave question empty and options empty when the request already says what they want, or
names rules or a reference film. Either way, fill every other field with your best guess."""

_cache = {}  # message -> plan; only successes are kept, so a failed LLM call is retried next time
_gemini = None


def dated(message):
    return f"Today is {datetime.date.today().isoformat()}. Request: {message}"  # so "recent" means something


def ask_gemini(message, system=SYSTEM, schema=SCHEMA):
    global _gemini
    from google import genai
    from google.genai import types
    # 10 s cap (the minimum Gemini accepts): when it is overloaded, Groq answers sooner than a long wait would
    _gemini = _gemini or genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=10_000))
    r = _gemini.models.generate_content(model=GEMINI_MODEL, contents=dated(message), config=types.GenerateContentConfig(
        system_instruction=system, temperature=0, response_mime_type="application/json", response_json_schema=schema))
    return json.loads(r.text)


def ask_groq(message, system=SYSTEM, schema=SCHEMA, model=GROQ_MODELS[0]):
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=20,
                   headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                   json={"model": model, "temperature": 0, "reasoning_effort": "low",
                         "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
                         "messages": [{"role": "system", "content": system}, {"role": "user", "content": dated(message)}]})
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def ask(message, system, schema, check):
    """Gemini, then each Groq model: the first answer that `check` accepts (check returns the cleaned answer or None)."""
    calls = [("gemini", lambda: ask_gemini(message, system, schema))] + [
        (m, lambda m=m: ask_groq(message, system, schema, model=m)) for m in GROQ_MODELS]
    for name, call in calls:
        try:
            answer = check(call())
        except Exception as e:  # rate limit, timeout, bad JSON: try the next one
            print(f"llm: {name} failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
            continue
        if answer:
            return answer
    return None


def valid(plan, message=""):
    """The plan with anything outside the vocabulary, and any rule or reference film the message doesn't state,
    dropped; None if too little is left to search with."""
    plan["effects"] = [e for e in plan.get("effects", []) if e in EFFECTS][:2]
    plan["mood_tags"] = [t for t in dict.fromkeys(plan.get("mood_tags", [])) if t in ALL_TAGS][:6]
    plan["genres"] = [g for g in plan.get("genres", []) if g in GENRES][:3]
    if plan.get("pace") not in PACES:
        plan["pace"] = "medium"
    plan["rules"] = valid_rules(plan.get("rules") or {}, plan.get("rules_quotes") or {}, message)
    plan["like"] = [x for x in plan.get("like") or [] if isinstance(x, dict) and str(x.get("title", "")).strip()
                    and named(x["title"], message)][:3]
    c = plan.get("clarify") or {}
    options = [str(o).strip() for o in c.get("options") or [] if str(o).strip()][:4]
    question = str(c.get("question") or "").strip()
    plan["clarify"] = {"question": question, "options": options} if question and len(options) >= 2 else None
    ok = plan["effects"] and len(plan["mood_tags"]) >= 2 and str(plan.get("synopsis", "")).strip()
    return plan if ok else None


STOP = {"the", "a", "an", "of", "and", "in", "on", "to"}
NAMES = {**NAMES, **{g: g for g in GENRES}}  # country codes are upper case, language codes lower: no clashes
ALIASES = {  # words for a country, language or genre that don't start like its English name
    "US": "american hollywood usa us", "GB": "british uk england english scottish welsh", "FR": "french",
    "ES": "spanish", "NL": "dutch holland", "CN": "chinese", "DK": "danish", "FI": "finnish", "PL": "polish",
    "GR": "greek", "CH": "swiss", "IE": "irish", "PH": "filipino", "TH": "thai", "SE": "swedish", "TR": "turkish",
    "PT": "portuguese", "IL": "israeli", "HK": "hk", "IN": "bollywood tollywood kollywood mollywood sandalwood desi",
    "SU": "soviet ussr", "zh": "chinese", "cn": "chinese hk", "hi": "bollywood", "te": "tollywood",
    "ta": "kollywood", "ml": "mollywood", "kn": "sandalwood", "fa": "iranian", "tl": "filipino",
    "Science Fiction": "sci scifi", "Animation": "anime cartoon cartoons", "Documentary": "docu docs doc",
    "TV Movie": "tv", "Romance": "romcom romcoms", "Comedy": "romcom romcoms"}
GENERIC = {"south", "north", "east", "west", "united", "states", "kingdom", "republic", "democratic", "islands",
           "america", "new", "saint", "movie", "federal", "central", "people", "s"}
CUES = {  # a year, runtime or yes/no rule's quote must have one of these words (or, for years and runtime, a number)
    "year_from": "old older classic classics recent new newer latest modern vintage century decade era year years "
                 "fifties sixties seventies eighties nineties",
    "max_runtime": "short shorter quick hour hours hr hrs min mins minutes runtime long",
    "documentary": "docu doc docs documentary documentaries real",
    "animation": "anime animated animation cartoon cartoons live action pixar ghibli",
    "well_rated": "rated rating ratings acclaimed best top highly masterpiece masterpieces imdb critically award awards "
                  "reviews reviewed"}
CUES["year_to"] = CUES["year_from"]
NEGATION = {"no", "not", "don", "dont", "never", "without", "avoid", "except", "nothing", "skip", "exclude", "nor"}
POSITIVE = ("directors", "actors", "studios", "countries", "languages", "genres")


def stated(quote, message):
    """Whether the quote's words appear, in order, in the message (case, accents and punctuation ignored)."""
    q = words(str(quote or ""))
    return bool(q) and f" {q} " in f" {words(message)} "


def named(name, message, person=False):
    """Whether the message mentions the name: one distinctive word is enough ("tarantino" names Quentin Tarantino),
    all of a title's main words for films ("spirited away")."""
    said = set(words(message).split())
    keys = [w for w in words(name).split() if w not in STOP and (len(w) > 2 or w.isdigit())] or words(name).split()
    return bool(keys) and (any if person else all)(w in said for w in keys)


def says(quote, value):
    """Whether the quote names a country or language code, or a genre: a word starting like its English name
    ("indian" for IN, "thrillers" for Thriller) or a usual alias ("hollywood" for US)."""
    q = words(quote).split()
    keys = [w[:5] for w in words(NAMES.get(value, value)).split() if w not in GENERIC]
    return any(w.startswith(k) for w in q for k in keys) or any(w in ALIASES.get(value, "").split() for w in q)


def valid_rules(r, quotes=None, message=None):
    """Only well-formed rules survive: a malformed one is dropped rather than filtering out everything. With a message,
    a rule also needs a quote of the message's own words (LLMs fill rule fields the person never asked for: "violent
    horror" came back as A24, Ari Aster, US/UK, 2010-2025), and each named person or studio must be in the message."""
    names = lambda v: [str(x).strip() for x in v or [] if str(x).strip()][:5]  # noqa: E731
    year = lambda v: v if isinstance(v, int) and 1880 <= v <= 2100 else None  # noqa: E731
    out = {"directors": names(r.get("directors")), "actors": names(r.get("actors")), "studios": names(r.get("studios")),
           "countries": [c.upper() for c in r.get("countries") or [] if isinstance(c, str) and len(c) == 2],
           "languages": [c.lower() for c in r.get("languages") or [] if isinstance(c, str) and len(c) == 2],
           "genres": [g for g in r.get("genres") or [] if g in GENRES],
           "not_countries": [c.upper() for c in r.get("not_countries") or [] if isinstance(c, str) and len(c) == 2],
           "not_languages": [c.lower() for c in r.get("not_languages") or [] if isinstance(c, str) and len(c) == 2],
           "not_genres": [g for g in r.get("not_genres") or [] if g in GENRES],
           "year_from": year(r.get("year_from")), "year_to": year(r.get("year_to"))}
    if out["year_from"] and out["year_to"] and out["year_from"] > out["year_to"]:
        out["year_from"], out["year_to"] = out["year_to"], out["year_from"]
    m = r.get("max_runtime")
    out["max_runtime"] = m if isinstance(m, int) and 30 <= m <= 600 else None
    for f in ("documentary", "animation"):
        out[f] = r[f] if isinstance(r.get(f), bool) else None
    out["well_rated"] = True if r.get("well_rated") is True else None
    if message is None:
        return out
    for f in RULE_FIELDS:
        q = str((quotes or {}).get(f) or "")
        q = q if stated(q, message) else ""
        if out[f] in (None, []):
            continue
        if f in POSITIVE and NEGATION & set(words(q).split()):  # "dont recommend indian movies" is not a wish for them
            out[f] = []
        elif f in ("directors", "actors", "studios"):  # names and codes: the message must name each one
            out[f] = [n for n in out[f] if named(n, message, person=True)]
        elif isinstance(out[f], list):
            out[f] = [x for x in out[f] if says(message, x)]
        else:  # years, runtime, yes/no: the quote must say it
            number = f in ("year_from", "year_to", "max_runtime") and any(ch.isdigit() for ch in q)
            out[f] = out[f] if number or set(words(q).split()) & set(CUES[f].split()) else None
    for f in ("countries", "languages", "genres"):  # both wanted and ruled out: ruled out
        out[f] = [x for x in out[f] if x not in out["not_" + f]]
    return out


def with_about(message, about):
    """The request, plus what the user wrote about themselves as background that never overrides it."""
    return f"{message}\n\nAbout them (background only; the request above comes first): {about}" if about else message


def understand(message, about=""):
    """The imagined ideal film for a message (cached), or None when no LLM could answer."""
    key = with_about(message, about)
    if key not in _cache:
        plan = ask(key, SYSTEM, SCHEMA, lambda answer: valid(answer, message))
        if plan is None:
            return None
        _cache[key] = plan
    return _cache[key]


def prepare(catalog, message, about=""):
    """Everything catalog.search needs for a chat message, plus what the app shows about how it was read:
    {"query_vec", "effects", "allowed", "exclude", "understood" (list of words), "notes" (list of sentences)}."""
    plan = understand(message, about)
    if plan is None:  # shortcut: no LLM available; search with the raw words and keyword rules, no hard rules
        return {"query_vec": embed_query(message), "effects": effects_for(message), "allowed": None, "exclude": [],
                "understood": [], "notes": ["The AI couldn't be reached, so this is a simple keyword search."],
                "asked_genres": [], "clarify": None}
    text = document(", ".join(plan["genres"]), plan["mood_tags"], plan["effects"][0], plan["pace"],
                    str(plan["watch_when"]).removeprefix("Watch this when ").strip(),
                    ", ".join(map(str, plan["keywords"])), plan["synopsis"])
    query = embed_query(text)
    allowed, applied, notes = catalog.rules_mask(plan["rules"])
    understood = applied  # only rules that survived validation (an AI-written summary could mention dropped ones)

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
            "understood": understood, "notes": notes, "asked_genres": plan["rules"]["genres"],
            "clarify": plan["clarify"]}
