"""Step 2: look films up on TMDB and cache every raw response.

    uv run python -m builder.tmdb find [LIMIT]     # IMDb id -> TMDB match, for every IMDb candidate
    uv run python -m builder.tmdb details [LIMIT]  # full details, for films selected by curate.py

Responses go to data/cache/tmdb.sqlite, so both commands resume where they stopped
and a rebuild never calls TMDB twice for the same film.
"""
import asyncio
import json
import sqlite3
import sys
import time

import duckdb
import httpx

from builder.common import BUILD, CACHE, TMDB_BASE, TMDB_TOKEN

DB = CACHE / "tmdb.sqlite"
CONCURRENCY = 32
APPEND = "credits,keywords,release_dates,watch/providers,reviews,external_ids"


def cache():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS find (imdb_id TEXT PRIMARY KEY, body TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS details "
                "(tmdb_id INTEGER PRIMARY KEY, body TEXT NOT NULL, fetched_at INTEGER NOT NULL)")
    return con


async def get(client, path, params=None):
    """GET with retries on rate limits, server errors and dropped connections. None on 404."""
    for attempt in range(6):
        try:
            r = await client.get(path, params=params)
        except httpx.TransportError:
            await asyncio.sleep(2 ** attempt)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            await asyncio.sleep(float(r.headers.get("retry-after", 2 ** attempt)))
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"gave up on {path}")


async def fetch_all(keys, fetch, save):
    """Fetch every key with bounded concurrency, saving in batches; failures are retried next run."""
    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"Authorization": f"Bearer {TMDB_TOKEN}"}
    start, done, failed, batch = time.time(), 0, 0, []

    async with httpx.AsyncClient(base_url=TMDB_BASE, headers=headers, timeout=30) as client:
        async def one(key):
            async with sem:
                try:
                    return key, await fetch(client, key)
                except (RuntimeError, httpx.HTTPStatusError) as e:
                    return key, e

        for task in asyncio.as_completed([one(k) for k in keys]):
            key, result = await task
            done += 1
            if isinstance(result, Exception):
                failed += 1
            else:
                batch.append((key, result))
            if len(batch) >= 500 or done == len(keys):
                save(batch)
                batch.clear()
                rate = done / (time.time() - start)
                print(f"{done:,}/{len(keys):,}  {rate:.0f}/s  failed {failed}  "
                      f"eta {(len(keys) - done) / rate / 60:.0f} min", flush=True)


def find(limit=None):
    con = cache()
    have = {r[0] for r in con.execute("SELECT imdb_id FROM find")}
    ids = [r[0] for r in duckdb.sql(
        f"SELECT imdb_id FROM '{BUILD / 'imdb_candidates.parquet'}' ORDER BY imdb_votes DESC").fetchall()]
    todo = [i for i in ids if i not in have][:limit]
    print(f"find: {len(have):,} cached, {len(todo):,} to fetch")

    async def fetch(client, imdb_id):
        return await get(client, f"/find/{imdb_id}", {"external_source": "imdb_id"})

    def save(rows):
        con.executemany("INSERT OR REPLACE INTO find VALUES (?, ?)",
                        [(k, json.dumps(v)) for k, v in rows])
        con.commit()

    asyncio.run(fetch_all(todo, fetch, save))


def details(limit=None):
    con = cache()
    have = {r[0] for r in con.execute("SELECT tmdb_id FROM details")}
    ids = [r[0] for r in duckdb.sql(f"SELECT tmdb_id FROM '{BUILD / 'selected.parquet'}'").fetchall()]
    todo = [i for i in ids if i not in have][:limit]
    print(f"details: {len(have):,} cached, {len(todo):,} to fetch")

    async def fetch(client, tmdb_id):
        return await get(client, f"/movie/{tmdb_id}", {"append_to_response": APPEND})

    def save(rows):
        now = int(time.time())
        con.executemany("INSERT OR REPLACE INTO details VALUES (?, ?, ?)",
                        [(k, json.dumps(v), now) for k, v in rows if v is not None])
        con.commit()

    asyncio.run(fetch_all(todo, fetch, save))


if __name__ == "__main__":
    cmd, limit = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None
    {"find": find, "details": details}[cmd](limit)
