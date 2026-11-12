#!/bin/bash
# Weekly 27B upgrade on Kaggle's free GPUs: films with no profile, then the most-voted films still on a 4B profile,
# re-profiled by Qwen 27B in one or two parallel Kaggle runs (each ~10.5 h, inside Kaggle's 12-hour limit), then
# imported, embedded, packed and backed up. Kaggle's free GPU hours (30 a week, 2 runs at once) reset every Saturday
# 00:00 UTC; the timer in scripts/ runs after that. Log: <data>/build/weekly.log
set -uo pipefail  # not -e: if one Kaggle run fails, the other is still imported
cd "$(dirname "$0")/.."
BUILD=$(uv run python -c "from builder.common import BUILD; print(BUILD)")
PER_RUN=10500  # films per Kaggle run: ~0.29 films/s on 2x T4 = ~10 h
exec >> "$BUILD/weekly.log" 2>&1
echo "== $(date '+%F %T') weekly 27B upgrade"

left=$(uv run --env-file .env kaggle quota 2>/dev/null | awk '/^GPU/{gsub("h","",$3); print int($3)}')
runs=$(( ${left:-0} >= 22 ? 2 : ${left:-0} >= 11 ? 1 : 0 ))
if [ "$runs" -eq 0 ]; then echo "only ${left:-?} GPU hours left this week; skipping"; exit 0; fi
echo "GPU hours left: $left -> $runs run(s) of $PER_RUN films"

mood() { uv run python -W ignore -m builder.mood "$@"; }
# the input list reads the profile database: wait for any daily update to finish first
flock "$BUILD/catalog.lock" uv run python -W ignore -m builder.mood upgrade-inputs $((runs * PER_RUN)) || exit 1
mood kaggle-upload || exit 1
mood kaggle-push 0 $PER_RUN
[ "$runs" -eq 2 ] && mood kaggle-push $PER_RUN $PER_RUN

echo "== $(date '+%F %T') waiting for Kaggle"
mood kaggle-fetch wait 27b                                 # each imports its profiles when its run ends
[ "$runs" -eq 2 ] && mood kaggle-fetch wait 27b-$PER_RUN

echo "== $(date '+%F %T') vectors, catalog, backup"
gpu_embed() {
  PYTHONPATH=. uv run --isolated --python 3.12 --with fastembed-gpu --with "onnxruntime-gpu[cuda,cudnn]" \
    --with python-dotenv --with httpx --with duckdb python -W ignore -m builder.embed
}
flock "$BUILD/catalog.lock" bash -c "$(declare -f gpu_embed)
  gpu_embed || uv run python -W ignore -m builder.embed   # the GPU takes minutes; the CPU fallback takes hours
  uv run python -W ignore -m builder.pack
  uv run python -W ignore -m builder.backup || echo 'backup failed or not set up'"
echo "== $(date '+%F %T') done"
