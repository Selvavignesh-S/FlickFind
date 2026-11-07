"""Step 5: turn every profiled film into a 256-number mood vector.

Run: uv run python -m builder.embed            (CPU: ~2 films/s, fine for the daily few dozen)
GPU: uv run --isolated --python 3.12 --with fastembed-gpu --with "onnxruntime-gpu[cuda,cudnn]" \
         --with python-dotenv --with httpx --with duckdb python -m builder.embed   (~90 films/s on an RTX 3050)
     shortcut: GPU deps live in a throwaway env so the project stays CPU-only like the backend; move them to an
     extra if GPU embedding becomes routine.
Vectors are cached in data/cache/vectors.sqlite keyed by TMDB id + a fingerprint of the mood document,
so only new or changed films are embedded again.
"""
import hashlib
import json
import sqlite3
import time

import numpy as np

from builder.common import CACHE

MODEL = "nomic-ai/nomic-embed-text-v1.5"
DIMS = 256  # Matryoshka truncation: ~1 benchmark point below the full 768, a third of the size
DB = CACHE / "vectors.sqlite"
_model = None


def embed(texts, prefix):
    """nomic vectors for texts, cut to DIMS. prefix is "search_document" (films) or "search_query" (chat).
    The backend must embed queries with this same function, or search silently breaks."""
    global _model
    if _model is None:
        import onnxruntime as ort
        from fastembed import TextEmbedding
        gpu = "CUDAExecutionProvider" in ort.get_available_providers()
        if gpu:
            ort.preload_dlls()  # the CUDA/cuDNN libraries come from pip wheels; load them explicitly
        # kSameAsRequested: the default memory pool keeps every padded batch size it has seen and overflowed a 6 GB
        # RTX 3050 after ~30k films; this grows it only by what is asked for
        cuda = [("CUDAExecutionProvider", {"arena_extend_strategy": "kSameAsRequested"})]
        _model = TextEmbedding(MODEL, providers=cuda if gpu else None)
    full = np.array(list(_model.embed([f"{prefix}: {t}" for t in texts], batch_size=32)), dtype=np.float32)
    # nomic's recipe for shorter vectors: layer-norm the full vector, truncate, re-normalise
    full = (full - full.mean(axis=1, keepdims=True)) / (full.std(axis=1, keepdims=True) + 1e-5)
    cut = full[:, :DIMS]
    return (cut / np.linalg.norm(cut, axis=1, keepdims=True)).astype(np.float16)


def mood_document(d, p):
    """What gets embedded for a film: its mood profile first, then the facts."""
    keywords = [k["name"] for k in (d.get("keywords") or {}).get("keywords", [])][:15]
    return (f"{d['title']} ({(d.get('release_date') or '')[:4]}). "
            f"{', '.join(g['name'] for g in d.get('genres', []))}. "
            f"Mood: {', '.join(p['mood_tags'])}. Effect: {p['effect']}. Pace: {p['pace']}. "
            f"Watch this when {p['watch_when']} "
            f"Keywords: {', '.join(keywords)}. Synopsis: {d.get('overview') or ''}")


def db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS vectors "
                "(tmdb_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL, vec BLOB NOT NULL)")
    return con


def main():
    from builder.mood import DB as PROFILES  # here, not at the top: the backend imports embed() without builder deps
    from builder.tmdb import cache as tmdb_cache
    con = db()
    have = dict(con.execute("SELECT tmdb_id, fingerprint FROM vectors"))
    profiles = {i: json.loads(p) for i, p in sqlite3.connect(PROFILES).execute("SELECT tmdb_id, profile FROM profiles")}
    todo = []
    for tmdb_id, body in tmdb_cache().execute("SELECT tmdb_id, body FROM details"):
        if tmdb_id in profiles:
            doc = mood_document(json.loads(body), profiles[tmdb_id])
            fp = hashlib.sha1(f"{MODEL}:{DIMS}\n{doc}".encode()).hexdigest()
            if have.get(tmdb_id) != fp:
                todo.append((tmdb_id, fp, doc))
    print(f"{len(profiles):,} profiled films, {len(todo):,} to embed", flush=True)
    start = time.time()
    for i in range(0, len(todo), 2048):
        batch = todo[i:i + 2048]
        vecs = embed([doc for _, _, doc in batch], "search_document")
        con.executemany("INSERT OR REPLACE INTO vectors VALUES (?, ?, ?)",
                        [(tid, fp, v.tobytes()) for (tid, fp, _), v in zip(batch, vecs)])
        con.commit()
        done = i + len(batch)
        print(f"{done:,}/{len(todo):,}  {done / (time.time() - start):.0f} films/s", flush=True)


if __name__ == "__main__":
    main()
