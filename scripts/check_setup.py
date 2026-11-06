"""Check that every configured key and local service answers.

Run: uv run scripts/check_setup.py
Required checks must pass; optional ones are skipped while their key is empty.
"""
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
env = os.environ.get
PROMPT = "Reply with the single word: ready"


def tmdb():
    r = httpx.get(f"{env('TMDB_API_BASE')}/movie/18148",
                  headers={"Authorization": f"Bearer {env('TMDB_API_TOKEN')}"}, timeout=20)
    r.raise_for_status()
    return f"via {env('TMDB_API_BASE')}: {r.json()['title']}"


def gemini():
    from google import genai
    client = genai.Client(api_key=env("GEMINI_API_KEY"))  # keep a reference: a freed client closes its connection
    r = client.models.generate_content(model="gemini-3.5-flash-lite", contents=PROMPT)
    return r.text.strip()


def ollama():
    base, model = env("OLLAMA_URL"), env("OLLAMA_MODEL")
    r = httpx.post(f"{base}/api/generate", timeout=300,
                   json={"model": model, "prompt": PROMPT, "stream": False, "think": False})
    r.raise_for_status()
    loaded = httpx.get(f"{base}/api/ps", timeout=10).json()["models"]
    m = next(m for m in loaded if m["name"] == model or m["name"].startswith(model + ":"))
    return f"{model}: {r.json()['response'].strip()} ({m['size_vram'] / m['size']:.0%} on GPU)"


def groq():
    r = httpx.get("https://api.groq.com/openai/v1/models",
                  headers={"Authorization": f"Bearer {env('GROQ_API_KEY')}"}, timeout=20)
    r.raise_for_status()
    return f"{len(r.json()['data'])} models available"


def omdb():
    r = httpx.get("https://www.omdbapi.com/", params={"i": "tt0046438", "apikey": env("OMDB_API_KEY")},
                  timeout=20)
    d = r.json()
    if d.get("Response") != "True":
        raise RuntimeError(d.get("Error"))
    rt = next((x["Value"] for x in d.get("Ratings", []) if x["Source"] == "Rotten Tomatoes"), "no RT score")
    return f"{d['Title']}: RT {rt}"


def b2():
    import boto3
    s3 = boto3.client("s3", endpoint_url=env("B2_ENDPOINT"),
                      aws_access_key_id=env("B2_KEY_ID"), aws_secret_access_key=env("B2_APPLICATION_KEY"))
    s3.head_bucket(Bucket=env("B2_BUCKET"))
    return f"bucket {env('B2_BUCKET')} reachable"


def kaggle():
    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()  # reads KAGGLE_API_TOKEN from the environment
    n = len(api.dataset_list(user=env("KAGGLE_USERNAME")) or [])
    return f"signed in as {env('KAGGLE_USERNAME')} ({n} datasets)"


def tavily():
    return "key set (not called: each call spends free credits)"


# (name, env var that must be set, check, required)
CHECKS = [
    ("TMDB", "TMDB_API_TOKEN", tmdb, True),
    ("Gemini", "GEMINI_API_KEY", gemini, True),
    ("Ollama", "OLLAMA_MODEL", ollama, True),
    ("Groq", "GROQ_API_KEY", groq, False),
    ("OMDb", "OMDB_API_KEY", omdb, False),
    ("B2", "B2_KEY_ID", b2, False),
    ("Kaggle", "KAGGLE_API_TOKEN", kaggle, False),
    ("Tavily", "TAVILY_API_KEY", tavily, False),
]

failed = False
for name, var, check, required in CHECKS:
    if not env(var):
        print(f"{'FAIL' if required else 'skip'}  {name:7} {var} is empty")
        failed |= required
        continue
    try:
        print(f"ok    {name:7} {check()}")
    except Exception as e:  # report every failure, keep checking the rest
        print(f"FAIL  {name:7} {type(e).__name__}: {e}")
        failed |= required
sys.exit(1 if failed else 0)
