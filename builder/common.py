"""Paths and settings shared by the builder steps."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
RAW = DATA / "raw"      # downloaded source files (IMDb TSVs)
CACHE = DATA / "cache"  # raw API responses, so rebuilds don't re-call APIs
BUILD = DATA / "build"  # intermediate and final outputs
for d in (RAW, CACHE, BUILD):
    d.mkdir(parents=True, exist_ok=True)

TMDB_BASE = os.environ["TMDB_API_BASE"]
TMDB_TOKEN = os.environ["TMDB_API_TOKEN"]
