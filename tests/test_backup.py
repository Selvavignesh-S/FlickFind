import datetime
import sqlite3
from pathlib import Path

import pyarrow as pa
from botocore.exceptions import ClientError

from builder import backup

NOW = datetime.datetime(2026, 11, 8, tzinfo=datetime.timezone.utc)


class FakeS3:
    def __init__(self, heads):
        self.heads = heads

    def head_object(self, Bucket, Key):
        if Key not in self.heads:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return self.heads[Key]


def test_only_changed_files_are_uploaded(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "DATA", tmp_path)
    f = tmp_path / "cache" / "tmdb.sqlite"
    f.parent.mkdir()
    f.write_bytes(b"x" * 10)
    k = backup.key(f)
    assert backup.due(FakeS3({}), "b", f, None, NOW)  # never uploaded
    same = {k: {"Metadata": {"source": backup.stamp(f)}, "LastModified": NOW - datetime.timedelta(days=30)}}
    assert not backup.due(FakeS3(same), "b", f, 7 * backup.DAY, NOW)  # unchanged: never again, however old
    old = {k: {"Metadata": {"source": "1:1"}, "LastModified": NOW - datetime.timedelta(days=2)}}
    assert backup.due(FakeS3(old), "b", f, None, NOW)  # changed: upload
    assert not backup.due(FakeS3(old), "b", f, 7 * backup.DAY, NOW)  # changed, but the weekly file waits
    old[k]["LastModified"] = NOW - datetime.timedelta(days=8)
    assert backup.due(FakeS3(old), "b", f, 7 * backup.DAY, NOW)


def test_database_snapshot_survives_compression(tmp_path):
    db = tmp_path / "flickfind.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE t (x TEXT)")
        con.executemany("INSERT INTO t VALUES (?)", [(f"row {i}",) for i in range(1000)])
    work = tmp_path / "work"
    work.mkdir()
    z = backup.compressed(db, work)
    restored = tmp_path / "restored.db"
    with pa.CompressedInputStream(str(z), "zstd") as src:
        restored.write_bytes(src.read())
    assert sqlite3.connect(restored).execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1000
    assert z.stat().st_size < db.stat().st_size
