"""Step 6: join details, mood profiles and vectors into one versioned catalog file + manifest.

Run:    uv run python -m builder.pack
Output: data/build/catalog/catalog-vYYYYMMDD.parquet and manifest.json
Only films with both a profile and a vector are included; the manifest says how many are still missing.
"""
import datetime
import json
import sqlite3
from collections import Counter

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from builder import curate, embed, mood
from builder.common import BUILD
from builder.tmdb import cache as tmdb_cache

OUT = BUILD / "catalog"
PROVIDER_COUNTRY = "IN"  # where-to-watch is stored for India only


def credits(d):
    crew = (d.get("credits") or {}).get("crew", [])
    jobs = lambda *names: list(dict.fromkeys(c["name"] for c in crew if c.get("job") in names))  # noqa: E731
    cast = sorted((d.get("credits") or {}).get("cast", []), key=lambda c: c.get("order", 99))[:5]
    return {"director": jobs("Director"), "cinematographer": jobs("Director of Photography"),
            "composer": jobs("Original Music Composer", "Music"), "writers": jobs("Screenplay", "Writer", "Story")[:4],
            "cast": [c["name"] for c in cast], "cast_ids": [c["id"] for c in cast]}


def providers(d):
    country = ((d.get("watch/providers") or {}).get("results") or {}).get(PROVIDER_COUNTRY, {})
    return list(dict.fromkeys(p["provider_name"] for kind in ("flatrate", "free", "ads") for p in country.get(kind, [])))


def main():
    films = {r["tmdb_id"]: r for r in duckdb.sql(f"SELECT * FROM '{BUILD / 'selected.parquet'}'").to_arrow_table().to_pylist()}
    profiles = {i: (json.loads(p), m) for i, p, m in
                sqlite3.connect(mood.DB).execute("SELECT tmdb_id, profile, model FROM profiles")}
    vectors = dict(embed.db().execute("SELECT tmdb_id, vec FROM vectors"))

    rows = []
    for tmdb_id, body in tmdb_cache().execute("SELECT tmdb_id, body FROM details"):
        f = films.get(tmdb_id)
        if f is None or tmdb_id not in profiles or tmdb_id not in vectors:
            continue
        d, (p, model) = json.loads(body), profiles[tmdb_id]
        rows.append({
            **{k: f[k] for k in ("tmdb_id", "imdb_id", "title", "year", "title_type", "runtime", "language",
                                 "group", "documentary", "animation", "imdb_rating", "imdb_votes", "released")},
            "original_title": d.get("original_title"), "tagline": d.get("tagline"), "overview": d.get("overview"),
            "poster_path": d.get("poster_path"), "genres": [g["name"] for g in d.get("genres", [])],
            "keywords": [k["name"] for k in (d.get("keywords") or {}).get("keywords", [])][:20],
            "countries": [c["iso_3166_1"] for c in d.get("production_countries", [])],
            "tmdb_rating": d.get("vote_average"), "tmdb_votes": d.get("vote_count"), "popularity": d.get("popularity"),
            **credits(d), "providers_in": providers(d),
            **{k: p[k] for k in ("mood_tags", "effect", "pace", "intensity", "watch_when")},
            "mood_confidence": p["confidence"], "profile_model": model,
            "vec": np.frombuffer(vectors[tmdb_id], dtype=np.float16),
        })
    if not rows:
        raise SystemExit("No films with both a profile and a vector yet.")

    # obscurity: 0 = most-voted film *in its language group*, 1 = least-voted. Within the group, so a famous Tamil or
    # French film counts as famous; it feeds the user's mainstream <-> niche lean and its drift.
    by_group = {}
    for n, r in enumerate(rows):
        by_group.setdefault(r["group"], []).append(n)
    for idx in by_group.values():
        votes = np.array([rows[n]["imdb_votes"] for n in idx])
        more = len(votes) - np.searchsorted(np.sort(votes), votes, side="right")  # films with more votes; ties share
        for n, rank in zip(idx, more):
            rows[n]["obscurity"] = round(float(rank) / max(len(idx) - 1, 1), 4)

    vecs = pa.FixedSizeListArray.from_arrays(pa.array(np.concatenate([r.pop("vec") for r in rows]), pa.float16()),
                                             embed.DIMS)
    table = pa.Table.from_pylist(rows).append_column("vec", vecs)
    version = datetime.date.today().strftime("v%Y%m%d")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"catalog-{version}.parquet"
    pq.write_table(table, path, compression="zstd")

    manifest = {
        "version": version, "built_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "file": path.name, "films": len(rows), "selected": len(films),
        "missing_profile_or_vector": len(films) - len(rows),
        "embedding": {"model": embed.MODEL, "dims": embed.DIMS, "document_prefix": "search_document",
                      "query_prefix": "search_query", "dtype": "float16"},
        "profile_prompt_version": mood.PROMPT_VERSION,
        "profile_models": dict(Counter(r["profile_model"] for r in rows)),
        "vote_floors": {**curate.FLOORS, "documentary": curate.DOC_FLOOR},
        "groups": dict(Counter(r["group"] for r in rows)),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    print(f"{path} {path.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
