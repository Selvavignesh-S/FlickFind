"""The film catalog in memory: the parquet file from builder.pack, searched with numpy (no vector database)."""
import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from builder import embed
from builder.common import BUILD

POSTER = "https://image.tmdb.org/t/p/w342"
# Ranking: mood fit decides; quality and the user's own lean only reorder films that already fit (no language or
# popularity edge for a new user). Weights are on the scale of mood similarity; tune with builder/quality.py.
EFFECT_BONUS = 0.06  # film has the effect the message asks for
SHORTLIST = 100      # only the best mood fits are considered at all
QUALITY = 0.1        # rating vs films in the same language, weighted by votes (0.1 keeps sub-5.5 films out)
LEAN = 0.06          # the user's learned lean: at taste 0 well-known films get +LEAN, at taste 1 lesser-known ones do
NEUTRAL = 0.5        # where every new user's taste starts: no lean either way
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
        self.effect = np.array(table["effect"].to_pylist(), dtype=object)
        self.popularity = 1 - table["obscurity"].to_numpy()  # vote rank within the film's language group (builder.pack)
        self.quality = quality(table)

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
               niche=NEUTRAL):
        """Top-k films. The SHORTLIST best mood fits (similarity + effect match) are reordered by quality and the
        user's learned lean, then spread apart so the picks aren't near-copies. Excluded ids and anything matching an
        avoid list never appear."""
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
        fit = self.vecs @ query_vec
        if effects:
            fit = fit + EFFECT_BONUS * np.isin(self.effect, list(effects))
        fit = np.where(ok, fit, -np.inf)
        best = np.argsort(-fit)[:SHORTLIST]
        best = best[np.isfinite(fit[best])]
        lean = LEAN * 2 * (NEUTRAL - niche)  # > 0 favours well-known films, < 0 lesser-known, 0 for a new user
        scores = np.full(len(fit), -np.inf)
        scores[best] = fit[best] + QUALITY * self.quality[best] + lean * self.popularity[best]
        pool = list(best[np.argsort(-scores[best])][:POOL])

        picked = []  # maximal marginal relevance: each pick trades its score against similarity to earlier picks
        while pool and len(picked) < k:
            penalty = (self.vecs[pool] @ self.vecs[picked].T).max(axis=1) if picked else np.zeros(len(pool))
            best = int(np.argmax(scores[pool] - VARIETY * penalty))
            picked.append(pool.pop(best))
        return [(int(self.ids[i]), float(scores[i])) for i in picked]


def quality(table):
    """0..1 per film: its IMDb rating ranked against films in its own language group, after pulling ratings with few
    votes toward the group average (a Bayesian average; a rating counts half once it has the group's median votes).
    Ranking within the group means no language gains from rating more generously or voting more."""
    group = np.array(table["group"].to_pylist(), dtype=object)
    votes = table["imdb_votes"].to_numpy(zero_copy_only=False).astype(float)
    rating = table["imdb_rating"].to_numpy(zero_copy_only=False).astype(float)
    out = np.zeros(len(votes))
    for g in set(group):
        m = group == g
        r = np.nan_to_num(rating[m], nan=np.nanmean(rating[m]))
        k = max(np.median(votes[m]), 1)
        weighted = (votes[m] * r + k * r.mean()) / (votes[m] + k)
        below = np.searchsorted(np.sort(weighted), weighted)  # films rated strictly lower; ties share a rank
        out[m] = below / max(m.sum() - 1, 1)
    return out


def embed_query(text):
    """The chat message as a vector, with the same model, prefix and size as the films (builder.embed)."""
    return embed.embed([text], "search_query")[0].astype(np.float32)
