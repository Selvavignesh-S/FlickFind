"""Paths and settings shared by the builder steps."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# One dataset for every checkout: set FLICKFIND_DATA in .env to share it (e.g. with a branch's working folder),
# instead of each checkout starting from an empty data/.
DATA = Path(os.environ.get("FLICKFIND_DATA") or ROOT / "data").expanduser()
RAW = DATA / "raw"      # downloaded source files (IMDb TSVs)
CACHE = DATA / "cache"  # raw API responses, so rebuilds don't re-call APIs
BUILD = DATA / "build"  # intermediate and final outputs
for d in (RAW, CACHE, BUILD):
    d.mkdir(parents=True, exist_ok=True)

TMDB_BASE = os.environ["TMDB_API_BASE"]
TMDB_TOKEN = os.environ["TMDB_API_TOKEN"]
