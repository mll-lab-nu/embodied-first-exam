"""SQLite is authoritative; JSON files are replaceable exports, never inputs."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def atomic_json(path, value, *, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".usage-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS scope (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    request_id TEXT NOT NULL, event_id TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY(request_id, event_id));
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
            """)
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def read_scope(db):
        row = db.execute("SELECT data FROM scope WHERE id=1").fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def write_scope(db, state):
        db.execute("INSERT OR REPLACE INTO scope VALUES (1, ?)", (json.dumps(state, allow_nan=False),))

    def export_events(self, path):
        # Export after requests have drained; includes policy revisions and failure receipts.
        with self.transaction() as db:
            rows = db.execute("SELECT id, data FROM audit ORDER BY id").fetchall()
        path = Path(path)
        fd, temporary = tempfile.mkstemp(prefix=".events-", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                for audit_id, data in rows:
                    stream.write(json.dumps(dict(json.loads(data), audit_id=audit_id), allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def read_audit(self, after=0, limit=1000):
        with self.transaction() as db:
            rows = db.execute("SELECT id, data FROM audit WHERE id > ? ORDER BY id LIMIT ?",
                              (after, limit)).fetchall()
        return [dict(json.loads(data), audit_id=identity) for identity, data in rows]
