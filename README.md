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

## Always on

`scripts/flickfind-api.service` runs the API, which also serves the web app (build it once with `scripts/build_web.sh`), on port 8000. Open it from any device on your Tailscale network at `http://<laptop's tailscale ip>:8000` and add it to the home screen. It starts with your login and restarts if it crashes:

```bash
scripts/build_web.sh
cp scripts/flickfind-api.service ~/.config/systemd/user/
systemctl --user enable --now flickfind-api.service
```

To keep it running after a reboot without logging in, run `loginctl enable-linger $USER` once.

## Daily catalog update

`scripts/daily.sh` adds new releases: fresh IMDb lists, TMDB details for new films, curation, mood profiles through Groq's free API (up to 300 a day), vectors and a new catalog file. The running API loads the new catalog on its next request. Run it by hand, or every morning at 06:00 with a systemd user timer:

```bash
cp scripts/flickfind-daily.service scripts/flickfind-daily.timer ~/.config/systemd/user/
systemctl --user enable --now flickfind-daily.timer
```

The log is in `data/build/daily.log`. Each day it also refreshes the TMDB details of the 5,000 films fetched longest ago (every film about once a month) and upgrades the most-voted 4B mood profiles to 27B with whatever Groq budget new releases leave.

## Weekly 27B upgrade

`scripts/weekly_upgrade.sh` re-profiles the most-voted films still on a 4B profile with Qwen 27B on Kaggle's free GPUs: one or two runs of 10,500 films, sized to the GPU hours left that week, then vectors, a new catalog and a backup. Every Saturday at 06:30, after Kaggle's weekly reset:

```bash
cp scripts/flickfind-weekly.service scripts/flickfind-weekly.timer ~/.config/systemd/user/
systemctl --user enable --now flickfind-weekly.timer
```

The log is in `data/build/weekly.log`.

## Credits

This product uses the TMDB API but is not endorsed or certified by TMDB. Film ratings from IMDb's non-commercial datasets and OMDb; where-to-watch data from JustWatch via TMDB. Non-commercial project.
