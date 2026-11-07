"""The film catalog in memory: the parquet file from builder.pack, searched with numpy (no vector database)."""
import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from builder import embed
from builder.common import BUILD

POSTER = "https://image.tmdb.org/t/p/w342"
# Ranking weights, on the scale of mood similarity (top matches differ by ~0.05). Tune with builder/quality.py.
EFFECT_BONUS = 0.06  # film has the effect the message asks for
POPULARITY = 0.08    # well-known, well-rated films; scaled by (1 - niche), so it fades as a user drifts to niche
VARIETY = 0.25       # how hard the 5 picks are pushed apart (0 = pure ranking)
POOL = 60            # candidates considered for the variety step
CARD = ["tmdb_id", "imdb_id", "title", "original_title", "year", "runtime", "language", "genres", "overview",
        "tagline", "poster_path", "imdb_rating", "imdb_votes", "director", "cast", "providers_in", "mood_tags",
        "effect", "pace", "intensity", "watch_when", "obscurity"]


class Catalog:
    def __init__(self, table: pa.Table, version: str):
        self.version = version
        self.table = table.drop_columns(["vec"])
        flat = table["vec"].combine_chunks().values.to_numpy(zero_copy_only=False)
        self.vecs = flat.astype(np.float32).reshape(-1, embed.DIMS)  # float32 once: ~150 MB for 143k films
        self.ids = table["tmdb_id"].to_numpy()
        self.index = {int(i): n for n, i in enumerate(self.ids)}
        self.language = np.array(table["language"].to_pylist(), dtype=object)
        self.cast = table["cast"].to_pylist()
        self.genres = table["genres"].to_pylist()
        self.obscurity = table["obscurity"].to_numpy()
        self.effect = np.array(table["effect"].to_pylist(), dtype=object)
        rating = np.nan_to_num(table["imdb_rating"].to_numpy(zero_copy_only=False).astype(float), nan=5.0)
        # 0..1: half how many people voted (vote rank), half how well they rated it (5 -> 0, 9+ -> 1)
        self.prior = 0.5 * (1 - self.obscurity) + 0.5 * np.clip((rating - 5) / 4, 0, 1)

    @classmethod
    def load(cls, folder=BUILD / "catalog"):
        manifest = json.loads((folder / "manifest.json").read_text())
        e = manifest["embedding"]
        if (e["model"], e["dims"]) != (embed.MODEL, embed.DIMS):  # query and film vectors must come from one model
            raise RuntimeError(f"catalog vectors are {e['model']}/{e['dims']}, the backend embeds with "
                               f"{embed.MODEL}/{embed.DIMS}: rebuild one of them")
        return cls(pq.read_table(folder / manifest["file"]), manifest["version"])

    def __contains__(self, tmdb_id):
        return tmdb_id in self.index

    def all_genres(self):
        return sorted({g for gs in self.genres for g in gs})

    def cards(self, tmdb_ids):
        rows = self.table.take(pa.array([self.index[i] for i in tmdb_ids], pa.int64())).select(CARD).to_pylist()
        for r in rows:
            r["poster"] = POSTER + r["poster_path"] if r["poster_path"] else None
        return rows

    def search(self, query_vec, k=5, exclude=(), avoid_languages=(), avoid_actors=(), avoid_genres=(), effects=(),
               niche=0.25):
        """Top-k films: mood similarity + effect match + a popularity prior that fades with niche, then spread apart
        so the picks aren't near-copies. Excluded ids and anything matching an avoid list never appear."""
        ok = np.ones(len(self.ids), dtype=bool)
        ok[[self.index[i] for i in exclude if i in self.index]] = False
        if avoid_languages:
            ok &= ~np.isin(self.language, list(avoid_languages))
        # shortcut: Python loops over 143k lists (~30 ms each); precompute per-actor/genre masks if search gets slow
        if avoid_actors:
            actors = set(avoid_actors)
            ok &= np.array([actors.isdisjoint(c) for c in self.cast])
        if avoid_genres:
            genres = set(avoid_genres)
            ok &= np.array([genres.isdisjoint(g) for g in self.genres])
        scores = self.vecs @ query_vec + POPULARITY * (1 - niche) * self.prior
        if effects:
            scores = scores + EFFECT_BONUS * np.isin(self.effect, list(effects))
        scores = np.where(ok, scores, -np.inf)
        pool = np.argsort(-scores)[:POOL]
        pool = list(pool[np.isfinite(scores[pool])])

        picked = []  # maximal marginal relevance: each pick trades its score against similarity to earlier picks
        while pool and len(picked) < k:
            penalty = (self.vecs[pool] @ self.vecs[picked].T).max(axis=1) if picked else np.zeros(len(pool))
            best = int(np.argmax(scores[pool] - VARIETY * penalty))
            picked.append(pool.pop(best))
        return [(int(self.ids[i]), float(scores[i])) for i in picked]


def embed_query(text):
    """The chat message as a vector, with the same model, prefix and size as the films (builder.embed)."""
    return embed.embed([text], "search_query")[0].astype(np.float32)
