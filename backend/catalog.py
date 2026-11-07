"""The film catalog in memory: the parquet file from builder.pack, searched with numpy (no vector database)."""
import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from builder import embed
from builder.common import BUILD

POSTER = "https://image.tmdb.org/t/p/w342"
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

    def search(self, query_vec, k=5, exclude=(), avoid_languages=(), avoid_actors=(), avoid_genres=()):
        """Top-k films by mood similarity, skipping excluded ids and anything matching an avoid list."""
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
        scores = np.where(ok, self.vecs @ query_vec, -np.inf)
        top = np.argsort(-scores)[:k]
        top = top[np.isfinite(scores[top])]
        return [(int(self.ids[i]), float(scores[i])) for i in top]


def embed_query(text):
    """The chat message as a vector, with the same model, prefix and size as the films (builder.embed)."""
    return embed.embed([text], "search_query")[0].astype(np.float32)
