"""The second LLM call of a chat turn: check the search's candidates against the request, keep only the films that
truly fit (fewer than 5 if fewer fit) and write a one-line "why" for each.

The vector search finds films near the mood; this catches what vectors can't judge: wrong tone, a film that only
shares surface words, or one that fits "uplifting" in general but not this request. Same Gemini -> Groq fallback as
backend.understand; if both fail, the search's own top picks are shown with the film's "watch this when" line.
"""
import json

from backend.understand import ask

CANDIDATES = 12  # films the search proposes per turn
KEEP_MIN = 7     # fit (0-10) a film needs to be shown...
KEEP_GAP = 2     # ...and no more than this below the best candidate
SHOW = 5

SYSTEM = """You check film suggestions for a person using a film recommendation app.
You get their request and candidate films from the app's catalog. For every candidate give:
- fit: 0 to 10, how well it gives them what they asked for (10 = exactly it). Be strict: a film that only shares
  surface words with the request, has the wrong tone or intensity, or is merely fine scores 6 or less.
- why: one sentence, under 20 words, spoken to them, on why this film suits this request. No spoilers, and don't
  start with the title.
Every candidate already meets any hard requirement in the request (director, actor, country, language, years,
studio, genre), so judge only how well it fits what they want beyond that. Use only the details given."""

SCHEMA = {"type": "object", "properties": {"films": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "integer"}, "fit": {"type": "integer"}, "why": {"type": "string"}},
    "required": ["id", "fit", "why"]}}}, "required": ["films"]}


def describe(card):
    return {"id": card["tmdb_id"], "title": card["title"], "year": card["year"], "genres": card["genres"],
            "synopsis": (card.get("overview") or "")[:350], "effect": card["effect"], "mood": card["mood_tags"],
            "watch this when": card["watch_when"]}


def check(message, cards):
    """(the cards worth showing, best first, each with a "why"; whether the LLM check ran)."""
    order = {c["tmdb_id"]: n for n, c in enumerate(cards)}

    def valid(answer):
        rows = [r for r in answer.get("films", []) if r.get("id") in order and isinstance(r.get("fit"), int)
                and str(r.get("why", "")).strip()]
        return rows or None

    prompt = json.dumps({"request": message, "candidates": [describe(c) for c in cards]}, ensure_ascii=False)
    rows = ask(prompt, SYSTEM, SCHEMA, valid) if cards else None
    if rows is None:  # no LLM: the search's own order, with the film's generic line
        for c in cards[:SHOW]:
            c["why"] = f"Watch this when {c['watch_when']}"
        return cards[:SHOW], False
    best = max(r["fit"] for r in rows)
    keep = sorted((r for r in rows if r["fit"] >= KEEP_MIN and r["fit"] >= best - KEEP_GAP),
                  key=lambda r: (-r["fit"], order[r["id"]]))[:SHOW]
    by_id = {c["tmdb_id"]: c for c in cards}
    for r in keep:
        by_id[r["id"]]["why"], by_id[r["id"]]["fit"] = str(r["why"]).strip(), r["fit"]
    return [by_id[r["id"]] for r in keep], True
