"""Step 4: write a mood profile for every selected film.

    uv run python -m builder.mood inputs              # write data/build/profile_inputs.jsonl (films still needing a profile)
    uv run python -m builder.mood local [LIMIT]       # profile pending films with the local Ollama model
    uv run python -m builder.mood import FILE.jsonl   # load profiles produced elsewhere (Kaggle)
    uv run python -m builder.mood bakeoff             # 50 films, local model vs Gemini, side by side
    uv run python -m builder.mood kaggle-upload       # inputs + prompt -> private Kaggle dataset
    uv run python -m builder.mood kaggle-push [OFFSET LIMIT]  # start a GPU run on Kaggle
    uv run python -m builder.mood kaggle-fetch [wait] # status; when ended, download + import (wait: until it ends)

Profiles live in data/cache/profiles.sqlite keyed by TMDB id, with a fingerprint of the input text:
a film is only re-profiled when its synopsis, keywords, reviews or this prompt change.
"""
import hashlib
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import time

import duckdb
import httpx

from builder.common import BUILD, CACHE, ROOT
from builder.tmdb import cache as tmdb_cache
from builder.vocab import ALL_TAGS, EFFECTS, PROFILE_SCHEMA, TAG_NOTES, TAGS

PROMPT_VERSION = 1  # bump when SYSTEM changes, so every film is re-profiled
DB = CACHE / "profiles.sqlite"
INPUTS = BUILD / "profile_inputs.jsonl"

SYSTEM = f"""You describe films by mood for a film recommendation app.
Work only from the information given. If it is too thin to judge the mood, set "confidence" to "low".

Return:
- effect: the film's main effect on a viewer, one of:
{chr(10).join(f'  {k}: {v}' for k, v in EFFECTS.items())}
- mood_tags: 3 to 6 tags, most characteristic first, only from this list:
{chr(10).join(f'  {group}: {", ".join(tags)}' for group, tags in TAGS.items())}
{chr(10).join(f'  ("{k}" means: {v})' for k, v in TAG_NOTES.items())}
- pace: slow, medium or fast
- intensity: 1 (gentle) to 5 (harrowing)
- watch_when: one sentence, at most 20 words, completing "Watch this when ...". No title, names or plot details.
- confidence: high, or low when the text is too thin"""


def film_text(d):
    """The facts the model sees about one film, from its cached TMDB details."""
    keywords = [k["name"] for k in (d.get("keywords") or {}).get("keywords", [])][:20]
    reviews = [r["content"].replace("\n", " ")[:400] for r in (d.get("reviews") or {}).get("results", [])[:2]]
    lines = [
        f"Title: {d['title']} ({(d.get('release_date') or '')[:4]})",
        f"Original language: {d.get('original_language')}",
        f"Genres: {', '.join(g['name'] for g in d.get('genres', []))}",
        f"Runtime: {d.get('runtime')} min",
        f"Tagline: {d.get('tagline') or '-'}",
        f"Synopsis: {d.get('overview')}",
        f"Keywords: {', '.join(keywords) or '-'}",
        *[f"Review excerpt: {r}" for r in reviews],
    ]
    return "\n".join(lines)


def fingerprint(text):
    return hashlib.sha1(f"{PROMPT_VERSION}\n{text}".encode()).hexdigest()


def clean(p):
    """Validate a model's answer against the vocabulary; raise if unusable."""
    tags = list(dict.fromkeys(t for t in p["mood_tags"] if t in ALL_TAGS))[:6]  # drop unknown/duplicate tags
    if len(tags) < 2 or p["effect"] not in EFFECTS or p["pace"] not in ("slow", "medium", "fast"):
        raise ValueError(f"unusable profile: {p}")
    return {"mood_tags": tags, "effect": p["effect"], "pace": p["pace"],
            "intensity": min(max(int(p["intensity"]), 1), 5),
            "watch_when": p["watch_when"].strip().removeprefix("Watch this when").strip(),  # models repeat the stem
            "confidence": "low" if p["confidence"] == "low" else "high"}


def db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS profiles (tmdb_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL, "
                "model TEXT NOT NULL, profile TEXT NOT NULL, created_at INTEGER NOT NULL)")
    return con


def pending():
    """(tmdb_id, film text, fingerprint) for selected films with details but no current profile."""
    have = dict(db().execute("SELECT tmdb_id, fingerprint FROM profiles"))
    selected = {r[0] for r in duckdb.sql(f"SELECT tmdb_id FROM '{BUILD / 'selected.parquet'}'").fetchall()}
    for tmdb_id, body in tmdb_cache().execute("SELECT tmdb_id, body FROM details"):
        if tmdb_id in selected:
            text = film_text(json.loads(body))
            fp = fingerprint(text)
            if have.get(tmdb_id) != fp:
                yield tmdb_id, text, fp


def save(rows, model):
    con = db()
    now = int(time.time())
    con.executemany("INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?)",
                    [(i, fp, model, json.dumps(p), now) for i, fp, p in rows])
    con.commit()


def ollama(text):
    r = httpx.post(f"{os.environ['OLLAMA_URL']}/api/chat", timeout=300, json={
        "model": os.environ["OLLAMA_MODEL"], "stream": False, "format": PROFILE_SCHEMA,
        "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 300},  # cap: forced-JSON can loop on whitespace
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]})
    r.raise_for_status()
    return clean(json.loads(r.json()["message"]["content"]))


def gemini(text, client, model="gemini-3.5-flash"):
    from google.genai import types
    r = client.models.generate_content(model=model, contents=text, config=types.GenerateContentConfig(
        system_instruction=SYSTEM, temperature=0.2,
        response_mime_type="application/json", response_json_schema=PROFILE_SCHEMA))
    return clean(json.loads(r.text))


def groq(text, model="openai/gpt-oss-120b"):
    """Groq's free tier (OpenAI-compatible API); waits out rate limits instead of failing."""
    for _ in range(10):
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=120,
                       headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                       json={"model": model, "temperature": 0.2, **({"reasoning_effort": "low"} if "gpt-oss" in model else {}),
                             "response_format": {"type": "json_schema",
                                                 "json_schema": {"name": "profile", "schema": PROFILE_SCHEMA}},
                             "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]})
        if r.status_code != 429:
            break
        time.sleep(float(r.headers.get("retry-after", 10)))
    r.raise_for_status()
    return clean(json.loads(r.json()["choices"][0]["message"]["content"]))


def cmd_inputs(limit=None):
    """Pending films, most-voted first, so each Kaggle slice covers the best-known films first."""
    votes = dict(duckdb.sql(f"SELECT tmdb_id, imdb_votes FROM '{BUILD / 'selected.parquet'}'").fetchall())
    films = sorted(pending(), key=lambda f: -votes.get(f[0], 0))[:None if limit is None else int(limit)]
    n = 0
    with open(INPUTS, "w") as f:
        for tmdb_id, text, fp in films:
            f.write(json.dumps({"tmdb_id": tmdb_id, "fingerprint": fp, "text": text}) + "\n")
            n += 1
    print(f"Wrote {n:,} films to {INPUTS}")


def cmd_local(limit=None):
    todo = list(pending())[:limit]
    model, start, batch, failed = os.environ["OLLAMA_MODEL"], time.time(), [], 0
    for i, (tmdb_id, text, fp) in enumerate(todo, 1):
        try:
            batch.append((tmdb_id, fp, ollama(text)))
        except (ValueError, KeyError, httpx.HTTPError) as e:
            failed += 1
            print(f"  {tmdb_id}: {e}", file=sys.stderr)
        if len(batch) >= 50 or i == len(todo):
            save(batch, model)
            batch.clear()
            print(f"{i:,}/{len(todo):,}  {i / (time.time() - start):.2f} films/s  failed {failed}", flush=True)


def cmd_import(path):
    rows, bad, model = [], 0, "kaggle"
    for line in open(path):
        r = json.loads(line)
        model = r.get("model", model)
        try:
            rows.append((r["tmdb_id"], r["fingerprint"], clean(r["profile"])))
        except (ValueError, KeyError, TypeError):
            bad += 1
    save(rows, model)
    print(f"Imported {len(rows):,} profiles, {bad} unusable (they stay pending)")


KAGGLE = BUILD / "kaggle"


def kaggle_cli(*args, check=True):
    return subprocess.run(["kaggle", *args], check=check, capture_output=True, text=True)


def cmd_kaggle_upload():
    """Upload profile_inputs.jsonl + the prompt to a private Kaggle dataset (new version if it exists)."""
    ds = KAGGLE / "dataset"
    ds.mkdir(parents=True, exist_ok=True)
    shutil.copy(INPUTS, ds / INPUTS.name)
    (ds / "prompt.json").write_text(json.dumps({"system": SYSTEM, "schema": PROFILE_SCHEMA}))
    ds_id = f"{os.environ['KAGGLE_USERNAME']}/flickfind-profile-inputs"
    (ds / "dataset-metadata.json").write_text(json.dumps(
        {"title": "flickfind-profile-inputs", "id": ds_id, "licenses": [{"name": "other"}]}))
    if kaggle_cli("datasets", "status", ds_id, check=False).returncode == 0:
        kaggle_cli("datasets", "version", "-p", str(ds), "-m", "new inputs")
    else:
        kaggle_cli("datasets", "create", "-p", str(ds))  # private unless --public is passed
    while (status := kaggle_cli("datasets", "status", ds_id, check=False).stdout.strip()) != "ready":
        print(f"dataset {ds_id}: {status}", flush=True)
        time.sleep(15)
    print(f"dataset {ds_id} ready")


def cmd_kaggle_push(offset="0", limit=None):
    """Start a GPU run on Kaggle for films [offset, offset+limit) of the uploaded inputs."""
    user = os.environ["KAGGLE_USERNAME"]
    k = KAGGLE / "kernel"
    k.mkdir(parents=True, exist_ok=True)
    script = (ROOT / "builder" / "kaggle_profile.py").read_text()
    script = script.replace("OFFSET, LIMIT = 0, None", f"OFFSET, LIMIT = {int(offset)}, {limit and int(limit)}", 1)
    (k / "kaggle_profile.py").write_text(script)
    (k / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{user}/flickfind-mood-profiles", "title": "flickfind-mood-profiles",
        "code_file": "kaggle_profile.py", "language": "python", "kernel_type": "script",
        "is_private": True, "enable_gpu": True, "enable_internet": True, "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [f"{user}/flickfind-profile-inputs"]}))
    print(kaggle_cli("kernels", "push", "-p", str(k)).stdout)


def cmd_kaggle_fetch(wait=False):
    """Show the run's status; once it has ended, download its output and log, and import the profiles.

    wait: keep checking every minute until the run ends (used to chain runs unattended).
    """
    kid = f"{os.environ['KAGGLE_USERNAME']}/flickfind-mood-profiles"
    while True:
        status = kaggle_cli("kernels", "status", kid, check=False).stdout.strip()
        ended = any(w in status.lower() for w in ("complete", "error", "cancel"))
        if ended or not wait:
            break
        time.sleep(60)
    print(status, flush=True)
    if ended:
        out = KAGGLE / "output"
        shutil.rmtree(out, ignore_errors=True)
        kaggle_cli("kernels", "output", kid, "-p", str(out), "--force", check=False)
        for log in out.glob("*.log"):  # Kaggle's run log: JSON lines of stdout/stderr
            lines = [json.loads(x).get("data", "") for x in json.loads(log.read_text() or "[]")] \
                if log.read_text().lstrip().startswith("[") else log.read_text().splitlines()
            print("".join(lines)[-3000:])
        if (out / "profiles.jsonl").exists():
            cmd_import(out / "profiles.jsonl")


def cmd_bakeoff(*models, n=50, famous=False):
    """Same films through several models side by side; writes data/build/bakeoff[_famous].md.

    models: "local", "groq:<model>" or "gemini:<model>". famous=True takes the most-voted films
    (ones you can judge yourself) instead of a random sample.
    """
    models = models or ("local", "groq:openai/gpt-oss-120b")
    client = None
    if any(m.startswith("gemini:") for m in models):
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def ask(m, text):
        if m == "local":
            return ollama(text)
        provider, name = m.split(":", 1)
        return gemini(text, client, name) if provider == "gemini" else groq(text, name)

    films = sorted(pending(), key=lambda f: f[0])
    if famous:
        votes = dict(duckdb.sql(f"SELECT tmdb_id, imdb_votes FROM '{BUILD / 'selected.parquet'}'").fetchall())
        films.sort(key=lambda f: -votes.get(f[0], 0))
    else:
        random.Random(7).shuffle(films)
    path = BUILD / ("bakeoff_famous.md" if famous else "bakeoff.md")
    out = [f"# Mood profile bake-off: {' vs '.join(models)}\n"]
    for done, (tmdb_id, text, _) in enumerate(films[:n], 1):
        out.append(f"## {text.splitlines()[0][7:]}\n\n<details><summary>input</summary>\n\n```\n{text}\n```\n</details>\n")
        for m in models:
            try:
                p = ask(m, text)
                out.append(f"- **{m}**: `{p['effect']}` · {', '.join(p['mood_tags'])} · {p['pace']} · "
                           f"intensity {p['intensity']} · {p['confidence']}  \n  *Watch this when {p['watch_when']}*")
            except Exception as e:  # show the failure in the report instead of aborting the comparison
                out.append(f"- **{m}**: ERROR {str(e)[:200]}")
        out.append("")
        path.write_text("\n".join(out))  # after every film, so a stopped run keeps its results
        print(f"{done}/{n}", flush=True)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"inputs": cmd_inputs, "import": cmd_import, "bakeoff": lambda *a: cmd_bakeoff(*a), "kaggle-upload": cmd_kaggle_upload,
     "kaggle-push": cmd_kaggle_push, "kaggle-fetch": lambda *a: cmd_kaggle_fetch(wait="wait" in a),
     "local": lambda *a: cmd_local(int(a[0]) if a else None)}[cmd](*args)
