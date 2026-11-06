"""Step 3: apply the language scope, vote floors and quality rules; print the count report.

Output: data/build/selected.parquet (the films whose full details step 2 fetches)
Run:    uv run python -m builder.curate
Works on a partly filled TMDB cache too; the report says how much is covered.
"""
import datetime
import json
import sqlite3
from collections import Counter

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from builder.common import BUILD
from builder.imdb import MIN_VOTES
from builder.tmdb import DB

# Original-language groups (ISO 639-1). Every other language falls into "world".
GROUPS = {
    "english": {"en"},
    "japanese": {"ja"},
    "european": {"fr", "de", "it", "es", "pt", "nl", "sv", "da", "no", "nb", "nn", "fi", "is", "pl",
                 "cs", "sk", "hu", "ro", "el", "uk", "sr", "hr", "bs", "sl", "bg", "mk", "sq", "ca",
                 "eu", "gl", "et", "lv", "lt", "ga", "cy", "lb", "mt"},
    # shortcut: Indian = Indian original language, so English-language Indian films fall under "english";
    # switch to production country once step 2 details are cached, if that group matters.
    "indian": {"hi", "ta", "te", "ml", "kn", "bn", "mr", "pa", "gu", "or", "as"},
}
LANG_GROUP = {lang: g for g, langs in GROUPS.items() for lang in langs}


def group_of(lang):
    """Language group of a TMDB original_language; None only when TMDB has no language at all."""
    return LANG_GROUP.get(lang, "world") if lang else None  # "xx" (silent films) counts as world

# Minimum IMDb votes. Fixed numbers, so a film never drops out as other films gain votes;
# the report prints where a "top 60%" rule would put each floor, to spot drift.
FLOORS = {"english": 200, "japanese": 100, "european": 50, "indian": 5000, "world": 100}
DOC_FLOOR = 50  # documentaries get their own floor in every group
NEW_FILM_DAYS = 365  # films younger than this need only floor × age / 365 votes (at least MIN_VOTES)
CHECK_SHARE = 0.6
MIN_OVERVIEW_WORDS = 15
TMDB_DOCUMENTARY, TMDB_ANIMATION = 99, 16
REPORT_FLOORS = (20, 50, 100, 200, 500, 1000, 5000)


def drop_reason(m, group, is_doc, votes, today):
    """Why a TMDB match is left out of the catalog, or None to keep it. Checked in this order."""
    if not m:
        return "not on TMDB"
    if m.get("adult") or m.get("softcore"):
        return "adult"
    if m.get("video"):
        return "video release"
    released = m.get("release_date")
    if not released or released > today.isoformat():
        return "not released"
    if len((m.get("overview") or "").split()) < MIN_OVERVIEW_WORDS:
        return "synopsis too short"
    if group is None:
        return "language out of scope"
    floor = DOC_FLOOR if is_doc else FLOORS[group]
    age = (today - datetime.date.fromisoformat(released)).days
    if age < NEW_FILM_DAYS:  # new films haven't had time to collect votes
        floor = max(MIN_VOTES, floor * age / NEW_FILM_DAYS)
    if votes < floor:
        return "below vote floor"
    return None


def load():
    """Join IMDb candidates with cached TMDB matches; tag each film with why it is dropped, if it is."""
    found = {k: json.loads(v) for k, v in sqlite3.connect(DB).execute("SELECT imdb_id, body FROM find")}
    today = datetime.date.today()
    rows = []
    for c in duckdb.sql(f"SELECT * FROM '{BUILD / 'imdb_candidates.parquet'}'").fetchall():
        imdb_id, title_type, title, _, year, runtime, imdb_genres, rating, votes = c
        if imdb_id not in found:
            continue  # lookup not done yet
        matches = (found[imdb_id] or {}).get("movie_results") or []
        m = matches[0] if matches else {}
        genres = set(m.get("genre_ids") or [])
        is_doc = TMDB_DOCUMENTARY in genres or "Documentary" in (imdb_genres or "")
        group = group_of(m.get("original_language"))
        drop = drop_reason(m, group, is_doc, votes, today)
        rows.append(dict(imdb_id=imdb_id, tmdb_id=m.get("id"), title=title, year=year,
                         title_type=title_type, runtime=runtime, language=m.get("original_language"),
                         released=m.get("release_date"),
                         group=group, documentary=is_doc, animation=TMDB_ANIMATION in genres,
                         imdb_rating=rating, imdb_votes=votes, drop=drop))
    return rows, len(found)


def main():
    rows, cached = load()
    total = duckdb.execute(f"SELECT count(*) FROM '{BUILD / 'imdb_candidates.parquet'}'").fetchone()[0]
    print(f"TMDB lookups cached: {cached:,} of {total:,} IMDb candidates ({cached / total:.0%})\n")

    print("Why films were dropped:")
    for reason, n in Counter(r["drop"] or "KEPT" for r in rows).most_common():
        print(f"  {reason:24} {n:>8,}")

    # Films that pass every rule except the vote floor: what each floor would keep.
    eligible = [r for r in rows if r["drop"] in (None, "below vote floor")]
    print("\nIn scope, by IMDb vote floor (documentaries counted separately):")
    print(f"  {'group':13}" + "".join(f"{'>=' + str(f):>9}" for f in REPORT_FLOORS) +
          f"   floor  top-{CHECK_SHARE:.0%} floor")
    for g in [*FLOORS, "documentary"]:
        sub = [r for r in eligible if (r["documentary"] if g == "documentary" else
                                         r["group"] == g and not r["documentary"])]
        counts = "".join(f"{sum(r['imdb_votes'] >= f for r in sub):>9,}" for f in REPORT_FLOORS)
        votes = sorted((r["imdb_votes"] for r in sub), reverse=True)
        share_floor = votes[max(int(len(votes) * CHECK_SHARE) - 1, 0)] if votes else 0
        print(f"  {g:13}{counts}   {DOC_FLOOR if g == 'documentary' else FLOORS[g]:>5,}  {share_floor:>13,}")

    kept = [r for r in rows if r["drop"] is None]
    by_group = Counter(r["group"] for r in kept)
    print(f"\nSelected with current floors: {len(kept):,} films  " +
          "  ".join(f"{g} {by_group[g]:,}" for g in FLOORS) +
          f"  | documentaries {sum(r['documentary'] for r in kept):,}"
          f"  animation {sum(r['animation'] for r in kept):,}"
          f"  TV movies {sum(r['title_type'] == 'tvMovie' for r in kept):,}")
    year_ago = (datetime.date.today() - datetime.timedelta(days=NEW_FILM_DAYS)).isoformat()
    print(f"Released in the last year: {sum(r['released'] > year_ago for r in kept):,} kept "
          f"(new films need floor × age / {NEW_FILM_DAYS} votes)")

    pq.write_table(pa.Table.from_pylist([{k: v for k, v in r.items() if k != "drop"} for r in kept]),
                   BUILD / "selected.parquet")
    print(f"Wrote {BUILD / 'selected.parquet'}")


if __name__ == "__main__":
    main()
