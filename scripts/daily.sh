#!/bin/bash
# Daily catalog update: new IMDb/TMDB films -> curated -> mood-profiled (Groq) -> embedded -> packed.
# Each step only does what is new, so a run takes minutes. The API loads the new catalog on its next request.
# Log: data/build/daily.log. Run by hand, or by the systemd timer in scripts/ (see README).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/build
exec 9>data/build/catalog.lock  # one catalog job at a time
flock -n 9 || { echo "$(date '+%F %T') another catalog job is running; skipping" >> data/build/daily.log; exit 0; }
step() { echo "== $(date '+%F %T') $1"; shift; uv run python -W ignore -m "$@"; }
{
  step "IMDb lists" builder.imdb
  step "TMDB ids" builder.tmdb find
  step "TMDB details" builder.tmdb details
  step "curation" builder.curate
  step "mood profiles" builder.mood groq 300   # leftovers carry over to the next day
  step "vectors" builder.embed                 # CPU: a day's few hundred films take minutes
  step "catalog" builder.pack
  step "backup" builder.backup || echo "backup failed or not set up; the catalog update above still stands"
  echo "== $(date '+%F %T') done"
} >> data/build/daily.log 2>&1
