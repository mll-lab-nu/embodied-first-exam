"""Single-owner, recoverable projections of committed SQLite state."""
import fcntl
import json
import os
from pathlib import Path

from .store import atomic_json


class PipelineOwnership:
    def __init__(self, root):
        self.file = (Path(root) / "pipeline.lock").open("a")
        os.chmod(self.file.name, 0o600)
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("A usage pipeline already owns this trial") from None

    def close(self):
        if not self.file.closed:
            fcntl.flock(self.file, fcntl.LOCK_UN)
            self.file.close()


class UsagePublisher:
    def __init__(self, root, ledger):
        self.root, self.ledger = Path(root), ledger
        self.path = self.root / "events.jsonl"
        self.cursor = 0
        self._rebuild()

    def _rebuild(self):
        # Never trust an old projection as accounting input. This also repairs a
        # corrupt/truncated tail from a previous process without replaying usage.
        self.ledger.store.export_events(self.path)
        self.cursor = 0
        with self.path.open() as stream:
            for line in stream:
                self.cursor = json.loads(line)["audit_id"]
        info = self.path.stat()
        self.inode, self.size = info.st_ino, info.st_size

    def publish(self, snapshot):
        atomic_json(self.root / "snapshot.json", snapshot)
        try:
            info = self.path.stat()
            intact = info.st_ino == self.inode and info.st_size == self.size
        except FileNotFoundError:
            intact = False
        if not intact:
            self._rebuild()
        # Bound each periodic batch so continuous traffic cannot starve health
        # monitoring. close() rebuilds the full final projection after drain.
        rows = self.ledger.store.read_audit(self.cursor)
        if rows:
            with self.path.open("a") as stream:
                for row in rows:
                    stream.write(json.dumps(row, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self.cursor = rows[-1]["audit_id"]
            self.size = self.path.stat().st_size

    def finalize(self, snapshot):
        self._rebuild()
        atomic_json(self.root / "snapshot.json", snapshot)
