"""Back up the dataset to the private Backblaze B2 bucket in .env, and restore it.

Run:    uv run python -m builder.backup            (also the last step of scripts/daily.sh)
        uv run python -m builder.backup restore    (into an empty data folder: FLICKFIND_DATA or data/)
Each file is zstd-compressed on the way up. SQLite databases are copied with SQLite's online backup first, so the
copy is consistent even while the app or a build is writing. A file is only uploaded again when it changed, and the
large TMDB cache at most once a week (it is a cache: losing a week of it only costs a few re-fetches). The bucket keeps
only the latest version of each file (bucket lifecycle setting).
"""
import datetime
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import boto3
import pyarrow as pa
from botocore.config import Config
from botocore.exceptions import ClientError

from builder.common import BUILD, CACHE, DATA

PREFIX = "backup/"
DAY = datetime.timedelta(days=1)


def files():
    """(path, every): what to back up, and how often at most (None: whenever it changed)."""
    catalog = BUILD / "catalog"
    out = [(p, None) for p in sorted(catalog.glob("catalog-*.parquet"))[-1:]] + [(catalog / "manifest.json", None)]
    out += [(BUILD / "selected.parquet", None), (DATA / "flickfind.db", None), (CACHE / "profiles.sqlite", None),
            (CACHE / "vectors.sqlite", None), (CACHE / "tmdb.sqlite", 7 * DAY)]
    return [(p, every) for p, every in out if p.exists()]


def client():
    # B2's S3 API rejects the newer default checksum headers; only send them when an operation requires them
    return boto3.client("s3", endpoint_url=os.environ["B2_ENDPOINT"], aws_access_key_id=os.environ["B2_KEY_ID"],
                        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
                        config=Config(request_checksum_calculation="when_required",
                                      response_checksum_validation="when_required"))


def key(path):
    return PREFIX + path.relative_to(DATA).as_posix() + ".zst"


def stamp(path):
    s = path.stat()
    return f"{s.st_size}:{int(s.st_mtime)}"


def due(s3, bucket, path, every, now):
    """Whether the file needs uploading: missing, changed since the last upload, and (for `every`) old enough."""
    try:
        head = s3.head_object(Bucket=bucket, Key=key(path))
    except ClientError:
        return True
    if head["Metadata"].get("source") == stamp(path):
        return False
    return every is None or now - head["LastModified"] >= every


def compressed(path, workdir):
    """A zstd-compressed copy of the file in workdir; SQLite databases are snapshotted first."""
    src = path
    if path.suffix in (".db", ".sqlite"):
        src = Path(workdir) / path.name
        with sqlite3.connect(path) as live, sqlite3.connect(src) as copy:
            live.backup(copy)
    out = Path(workdir) / (path.name + ".zst")
    with open(src, "rb") as f, pa.CompressedOutputStream(str(out), "zstd") as z:
        while chunk := f.read(16 << 20):
            z.write(chunk)
    return out


def backup():
    s3, bucket = client(), os.environ["B2_BUCKET"]
    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0
    for path, every in files():
        if not due(s3, bucket, path, every, now):
            print(f"  unchanged  {path.relative_to(DATA)}")
            continue
        with tempfile.TemporaryDirectory(dir=DATA) as tmp:  # same disk as the data: no /tmp size limits
            z = compressed(path, tmp)
            s3.upload_file(str(z), bucket, key(path), ExtraArgs={"Metadata": {"source": stamp(path)}})
            print(f"  uploaded   {path.relative_to(DATA)}  {path.stat().st_size / 1e6:,.0f} MB -> {z.stat().st_size / 1e6:,.0f} MB")
            sent += 1
    print(f"backup: {sent} file(s) uploaded to b2://{bucket}/{PREFIX}")


def restore():
    """Download and decompress every backed-up file into DATA. Refuses to overwrite files that already exist."""
    s3, bucket = client(), os.environ["B2_BUCKET"]
    keys = [o["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX)
            for o in page.get("Contents", [])]
    for k in keys:
        target = DATA / k[len(PREFIX):].removesuffix(".zst")
        if target.exists():
            print(f"  skipped (exists) {target.relative_to(DATA)}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=DATA) as tmp:
            z = Path(tmp) / "download.zst"
            s3.download_file(bucket, k, str(z))
            with pa.CompressedInputStream(str(z), "zstd") as src, open(target, "wb") as out:
                while chunk := src.read(16 << 20):
                    out.write(chunk)
        print(f"  restored {target.relative_to(DATA)}")


if __name__ == "__main__":
    if not all(os.environ.get(k) for k in ("B2_ENDPOINT", "B2_KEY_ID", "B2_APPLICATION_KEY", "B2_BUCKET")):
        sys.exit("backup: B2 is not set up in .env; skipping")  # exits 1 so a manual run notices
    restore() if sys.argv[1:] == ["restore"] else backup()
