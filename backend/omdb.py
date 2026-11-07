"""Rotten Tomatoes scores from OMDb, fetched only when a card is shown and cached for 30 days.

A free OMDb key allows 1,000 requests a day: this stays under DAILY_BUDGET and fetches at most PER_REQUEST films per
API call, so a long Watched list fills in over a few visits instead of using the day's budget at once.
"""
import datetime
import os
from concurrent.futures import ThreadPoolExecutor

import httpx

DAILY_BUDGET = 900
PER_REQUEST = 10
MAX_AGE = datetime.timedelta(days=30)
_paused_on = None  # the date OMDb said "limit reached"; no more calls until the next day


def fetch(imdb_id, key):
    """The film's Rotten Tomatoes % (None if it has none). Raises on a failed request, so nothing gets cached."""
    r = httpx.get("https://www.omdbapi.com/", params={"i": imdb_id, "apikey": key}, timeout=4)
    try:
        d = r.json()
    except ValueError:
        d = {}
    if d.get("Response") == "False" and "not found" not in d.get("Error", "").lower():
        # e.g. "Request limit reached!" or "Invalid API key!"; OMDb sends these with HTTP 401
        raise RuntimeError(f"{r.status_code} {d.get('Error', 'OMDb error')}")
    if r.is_error:
        raise RuntimeError(f"HTTP {r.status_code}")  # never the URL: it carries the API key
    value = next((x["Value"] for x in d.get("Ratings", []) if x.get("Source") == "Rotten Tomatoes"), "")
    return int(value[:-1]) if value.endswith("%") and value[:-1].isdigit() else None


def _try(imdb_id, key):
    global _paused_on
    try:
        return True, fetch(imdb_id, key)
    except Exception as e:  # a missing score is cosmetic: never fail the page over it
        if "limit" in str(e).lower():
            _paused_on = datetime.date.today()
        print(f"OMDb {imdb_id}: {e}", flush=True)
        return False, None


def scores(imdb_ids, con):
    """imdb_id -> Rotten Tomatoes % (or None) for the cached ones, fetching up to PER_REQUEST missing or stale ids."""
    ids = [i for i in dict.fromkeys(imdb_ids) if i]
    if not ids:
        return {}
    now = datetime.datetime.now()
    cached = {r[0]: (r[1], r[2]) for r in con.execute(
        f"SELECT imdb_id, rotten_tomatoes, fetched_at FROM omdb WHERE imdb_id IN ({','.join('?' * len(ids))})", ids)}
    out = {i: v[0] for i, v in cached.items()}

    key, today = os.environ.get("OMDB_API_KEY"), datetime.date.today()
    if not key or _paused_on == today:
        return out
    stale = [i for i in ids if i not in cached or now - datetime.datetime.fromisoformat(cached[i][1]) > MAX_AGE]
    used = con.execute("SELECT COUNT(*) FROM omdb WHERE fetched_at >= ?", (today.isoformat(),)).fetchone()[0]
    todo = stale[:max(0, min(PER_REQUEST, DAILY_BUDGET - used))]
    if todo:
        with ThreadPoolExecutor(5) as pool:
            results = list(pool.map(lambda i: _try(i, key), todo))
        stamp = now.isoformat(timespec="seconds")
        for i, (ok, score) in zip(todo, results):
            if ok:
                out[i] = score
                con.execute("INSERT OR REPLACE INTO omdb VALUES (?, ?, ?)", (i, score, stamp))
    return out
