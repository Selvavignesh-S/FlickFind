"""The film catalog in memory: the parquet file from builder.pack, searched with numpy (no vector database)."""
import json
import re
import unicodedata
from collections import defaultdict

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
        # for the hard rules in a request ("directed by Tarantino", "Indian", "from the 2010s") and "films like X"
        self.directors = People(table["director"].to_pylist())
        self.actors = People(self.cast)
        self.countries = table["countries"].to_pylist()
        self.year = np.array([y or 0 for y in table["year"].to_pylist()])
        self.runtime = np.array([r or 0 for r in table["runtime"].to_pylist()])
        self.documentary = np.array(table["documentary"].to_pylist(), dtype=bool)
        self.animation = np.array(table["animation"].to_pylist(), dtype=bool)
        self.votes = table["imdb_votes"].to_numpy()
        self.titles = defaultdict(list)  # "spirited away" -> film indices, from the title and the original title
        self.title_key = [words(t) for t in table["title"].to_pylist()]
        for n, (t, o) in enumerate(zip(table["title"].to_pylist(), table["original_title"].to_pylist())):
            for name in {words(t), words(o or "")} - {""}:
                self.titles[name].append(n)

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

    def rules_mask(self, rules):
        """(films that obey every rule, what was applied in words, notes on rules nothing matched).

        Each rule field narrows the films (AND); names within one field are alternatives (OR). Country and language
        are separate requirements: "Malayalam" read as made in India + in Malayalam must not return Hindi films."""
        n = len(self.ids)
        ok, applied, notes = np.ones(n, dtype=bool), [], []
        for field, people, label in (("directors", self.directors, "directed by"), ("actors", self.actors, "starring")):
            if not rules.get(field):
                continue
            hit, found = np.zeros(n, dtype=bool), []
            for name in rules[field]:
                names, films = people.match(name)
                hit[films] = True
                found += names
                if not films:
                    notes.append(f"No films {label} {name} are in the catalog yet.")
            ok &= hit
            if found:
                applied.append(f"{label} {' or '.join(sorted(set(found)))}")
        if countries := set(rules.get("countries") or []):
            ok &= np.array([not countries.isdisjoint(c) for c in self.countries])
            applied.append("made in " + ", ".join(sorted(countries)))
        if languages := set(rules.get("languages") or []):
            ok &= np.isin(self.language, list(languages))
            applied.append("in " + ", ".join(sorted(languages)))
        if genres := set(rules.get("genres") or []):
            ok &= np.array([genres <= set(g) for g in self.genres])
            applied.append("genre " + " + ".join(sorted(genres)))
        if y := rules.get("year_from"):
            ok &= self.year >= y
        if y := rules.get("year_to"):
            ok &= (self.year <= y) & (self.year > 0)
        if rules.get("year_from") or rules.get("year_to"):
            applied.append(f"released {rules.get('year_from') or ''}–{rules.get('year_to') or 'now'}")
        if m := rules.get("max_runtime"):
            ok &= (self.runtime > 0) & (self.runtime <= m)
            applied.append(f"under {m} min")
        for field, column in (("documentary", self.documentary), ("animation", self.animation)):
            if rules.get(field) is not None:
                ok &= column == bool(rules[field])
                applied.append(("" if rules[field] else "not ") + field)
        return ok, applied, notes

    def same_title(self, n):
        """Every film with the same title as film n: originals and remakes that share it ("Drishyam" 2013 and 2015)."""
        return [int(self.ids[m]) for m in self.titles.get(words(self.table["title"][n].as_py()), [n])]

    def find_title(self, title, year=None):
        """Index of the film called `title`: the one from `year` if given, else the most-voted. None if not found."""
        found = self.titles.get(words(title), [])
        if year:
            found = [n for n in found if abs(self.year[n] - year) <= 1] or found
        return max(found, key=lambda n: self.votes[n]) if found else None

    def search(self, query_vec, k=5, exclude=(), avoid_languages=(), avoid_actors=(), avoid_genres=(), effects=(),
               niche=NEUTRAL, allowed=None):
        """Top-k films. The SHORTLIST best mood fits (similarity + effect match) are reordered by quality and the
        user's learned lean, then spread apart so the picks aren't near-copies. Only `allowed` films (the request's
        hard rules) are considered; excluded ids and anything matching an avoid list never appear."""
        ok = np.ones(len(self.ids), dtype=bool) if allowed is None else allowed.copy()
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
            # an original and its same-titled remake ("Drishyam 2", 2021 and 2022) count as one pick
            pool = [i for i in pool if self.title_key[i] != self.title_key[picked[-1]]]
        return [(int(self.ids[i]), float(scores[i])) for i in picked]


def words(text):
    """Lowercase ASCII words, so 'Bong Joon-ho', 'bong joon ho' and 'Amélie'/'amelie' compare equal."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return " ".join(re.findall(r"[a-z0-9]+", plain))


class People:
    """Names -> films, matched on words: 'Tarantino' or 'quentin tarantino' finds 'Quentin Tarantino'."""

    def __init__(self, names_per_film):
        self.films = defaultdict(list)
        for n, names in enumerate(names_per_film):
            for name in names:
                self.films[name].append(n)
        self.by_word = defaultdict(set)
        for name in self.films:
            for w in words(name).split():
                self.by_word[w].add(name)

    def match(self, query):
        """(the names that contain every word of the query, their films)."""
        ws = words(query).split()
        names = set.intersection(*(self.by_word.get(w, set()) for w in ws)) if ws else set()
        return sorted(names), sorted({n for name in names for n in self.films[name]})


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
