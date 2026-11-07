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
uv sync                         # Python 3.12 env with all dependencies
cp .env.example .env             # then fill in the keys
ollama pull qwen3:4b-instruct    # local model for mood profiles
uv run scripts/check_setup.py    # every key and service should report ok
```

TMDB's usual API host `api.themoviedb.org` is blocked by some Indian ISPs' DNS; `.env.example` points at `api.tmdb.org`, which serves the same API.

## Run

The API needs a built catalog in `data/build/catalog/` (see `builder/`). The app needs Node.js.

```bash
uv run uvicorn backend.main:app --port 8000   # API; docs at http://localhost:8000/docs
cd app && npm install && npm run web           # app in the browser at http://localhost:8081
uv run pytest                                  # backend and builder tests
```

On a phone, run the app with `EXPO_PUBLIC_API_URL` set to the laptop's Tailscale address, e.g. `http://100.x.y.z:8000`.

## Daily catalog update

`scripts/daily.sh` adds new releases: fresh IMDb lists, TMDB details for new films, curation, mood profiles through Groq's free API (up to 300 a day), vectors and a new catalog file. The running API loads the new catalog on its next request. Run it by hand, or every morning at 06:00 with a systemd user timer:

```bash
cp scripts/flickfind-daily.service scripts/flickfind-daily.timer ~/.config/systemd/user/
systemctl --user enable --now flickfind-daily.timer
```

The log is in `data/build/daily.log`.

## Credits

This product uses the TMDB API but is not endorsed or certified by TMDB. Film ratings from IMDb's non-commercial datasets and OMDb; where-to-watch data from JustWatch via TMDB. Non-commercial project.
