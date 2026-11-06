# FlickFind

A movie recommender you talk to. Describe your mood; it asks what you want from it when it needs to, then shows up to five films that fit, each with a reason. It learns from what you watch, rate and block.

**Status:** v2 rebuild in progress. The full plan (architecture, dataset, workflows, phases) is in [docs/flickfind-plan.html](docs/flickfind-plan.html).

## Layout

| Folder | What runs there |
|---|---|
| `builder/` | Offline dataset pipeline on your PC: IMDb + TMDB → curated, mood-profiled, embedded catalog |
| `backend/` | FastAPI chat engine; catalog in memory, user data in SQLite |
| `app/` | Expo app for web and phone |
| `scripts/` | Setup and maintenance helpers |

## Setup

Requires [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com) (with GPU support if you have one).

```bash
uv sync --extra builder          # Python 3.12 env with all dependencies
cp .env.example .env             # then fill in the keys
ollama pull qwen3:4b-instruct    # local model for mood profiles
uv run scripts/check_setup.py    # every key and service should report ok
```

TMDB's usual API host `api.themoviedb.org` is blocked by some Indian ISPs' DNS; `.env.example` points at `api.tmdb.org`, which serves the same API.

## Credits

This product uses the TMDB API but is not endorsed or certified by TMDB. Film ratings from IMDb's non-commercial datasets and OMDb; where-to-watch data from JustWatch via TMDB. Non-commercial project.
