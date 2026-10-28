"""Lossless array bundles with unchanged content-addressed trace references.

Images stay ordinary files. Numeric NPY bytes share one SQLite file per run,
using rollback journals (not WAL, which requires shared-memory coordination).
Callers serialize writers and commit before publishing referencing events.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any


ARRAY_DATABASE = "arrays.sqlite3"
STORAGE_VERSION = 1


def artifact_path(directory: Path, relative: str) -> Path:
    """Reject traversal and symlinks escaping the run, for both storage forms."""
    path = (directory / relative).resolve()
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.is_relative_to(directory.resolve()):
        raise ValueError(f"Artifact reference escapes run directory: {relative}")
    return path


class ArrayWriter:
    """Lazy single-writer bundle; the recorder's lock protects each operation."""

    def __init__(self, directory: Path) -> None:
        """Prepare a lazy array writer rooted in one experiment run."""
        self.directory = directory
        self.connection: sqlite3.Connection | None = None
        self.closed = False

    def put(self, relative: str, data: bytes, digest: str) -> None:
        """Stage verified NPY bytes once per content-addressed path."""
        if self.closed:
            raise RuntimeError("Array bundle is closed")
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Array checksum mismatch: {relative}")
        if relative != f"artifacts/{digest}.npy":
            raise ValueError(f"Invalid content-addressed array path: {relative}")
        if self.connection is None:
            path = artifact_path(self.directory, ARRAY_DATABASE)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, STORAGE_VERSION):
                    raise ValueError(f"Unsupported array storage version: {version}")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("CREATE TABLE IF NOT EXISTS artifacts (path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, content BLOB NOT NULL) WITHOUT ROWID")
                connection.execute(f"PRAGMA user_version={STORAGE_VERSION}")
                connection.commit()
            except BaseException:
                connection.close()
                raise
            self.connection = connection
        previous = self.connection.execute("SELECT sha256, content FROM artifacts WHERE path=?", (relative,)).fetchone()
        if previous is not None:
            if previous != (digest, data):
                raise ValueError(f"Conflicting stored array: {relative}")
            return
        self.connection.execute("INSERT INTO artifacts VALUES (?, ?, ?)", (relative, digest, data))

    def flush(self) -> None:
        """Make bytes durable before their referencing JSON is made visible."""
        if self.connection is not None:
            self.connection.commit()

    def close(self) -> None:
        """Roll back only unreferenced writes; published references were flushed."""
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        self.closed = True


class ArtifactReader:
    """Read loose or bundled artifacts without creating files or changing data."""

    def __init__(self, directory: str | Path) -> None:
        """Initialize read-only access to one run's artifact storage."""
        self.directory = Path(directory).resolve()
        self.connection: sqlite3.Connection | None = None
        self._array_directory: Path | None = None
        self._database_present: bool | None = None
        self._recovery: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> ArtifactReader:
        """Keep bundle connections available throughout a read session."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Close database handles and remove any private recovery copy."""
        if self.connection is not None:
            self.connection.close()
        if self._recovery is not None:
            self._recovery.cleanup()

    def _recover_readonly_copy(self) -> None:
        """Roll back a crashed writer's hot journal in a private temporary copy.

        SQLite needs write permission to recover even for SELECT. Never give
        the reader write access to the recorded database or its original log.
        """
        database = artifact_path(self.directory, ARRAY_DATABASE)
        journal = artifact_path(self.directory, ARRAY_DATABASE + "-journal")
        def signature(path):
            """Detect database or journal changes during recovery copying."""
            stat = path.stat()
            return stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
        before = {path: signature(path) for path in (database, journal)}
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        # Klone's TMPDIR can share the exhausted quota. System /tmp is local
        # storage; TemporaryDirectory creates a private, automatically removed directory.
        self._recovery = tempfile.TemporaryDirectory(prefix="humanclaw-array-read-", dir="/tmp" if Path("/tmp").is_dir() else None)
        copied = Path(self._recovery.name) / ARRAY_DATABASE
        shutil.copyfile(database, copied)
        shutil.copyfile(journal, copied.with_name(ARRAY_DATABASE + "-journal"))
        if {path: signature(path) for path in before} != before:
            raise OSError("Array writer changed during recovery; retry after it stops")
        try:
            recovery = sqlite3.connect(copied)
            try:
                if recovery.execute("PRAGMA user_version").fetchone()[0] != STORAGE_VERSION:
                    raise ValueError("Unsupported recovered array storage version")
            finally:
                recovery.close()
        except sqlite3.Error as exc:
            raise OSError(f"Cannot recover array bundle copy: {exc}") from exc
        self.connection = sqlite3.connect(copied.as_uri() + "?mode=ro", uri=True)

    def bundled(self, relative: str) -> bytes:
        """Read a hash-checked array without modifying its recorded bundle."""
        # These are database keys, not filesystem paths. Avoid repeated path
        # resolution/stat calls for tens of thousands of tiny arrays on GPFS.
        if not re.fullmatch(r"artifacts/[0-9a-f]{64}\.npy", relative):
            raise FileNotFoundError(relative)
        try:
            if self.connection is None:
                database = artifact_path(self.directory, ARRAY_DATABASE)
                if not database.is_file():
                    raise FileNotFoundError(relative)
                self.connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
                if self.connection.execute("PRAGMA user_version").fetchone()[0] != STORAGE_VERSION:
                    raise ValueError("Unsupported array storage version")
            row = self.connection.execute("SELECT sha256, content FROM artifacts WHERE path=?", (relative,)).fetchone()
        except sqlite3.Error as exc:
            if "readonly" in str(exc).lower() and self._recovery is None and (self.directory / (ARRAY_DATABASE + "-journal")).is_file():
                self._recover_readonly_copy()
                return self.bundled(relative)
            raise OSError(f"Unreadable array bundle: {exc}") from exc
        if row is None:
            raise FileNotFoundError(relative)
        digest, content = row
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Bundled artifact checksum mismatch: {relative}")
        return content

    def read(self, reference: dict[str, Any] | str) -> bytes:
        """Resolve artifact bytes and verify any supplied content digest."""
        relative = reference if isinstance(reference, str) else reference["artifact"]
        if re.fullmatch(r"artifacts/[0-9a-f]{64}\.npy", relative):
            if self._database_present is None:
                self._database_present = artifact_path(self.directory, ARRAY_DATABASE).is_file()
            if self._database_present:
                try:
                    content = self.bundled(relative)
                except FileNotFoundError:
                    content = self._loose_array(relative)
            else:
                content = self._loose_array(relative)
        else:
            path = artifact_path(self.directory, relative)
            try:
                content = path.read_bytes()
            except FileNotFoundError:
                content = self.bundled(relative)
        if isinstance(reference, dict) and reference.get("sha256"):
            if hashlib.sha256(content).hexdigest() != reference["sha256"]:
                raise ValueError(f"Artifact checksum mismatch: {relative}")
        return content

    def _loose_array(self, relative: str) -> bytes:
        """Read a loose array or a bundle published by offline compaction."""
        if self._array_directory is None:
            self._array_directory = artifact_path(self.directory, "artifacts")
        path = self._array_directory / Path(relative).name
        if path.is_symlink():
            path = artifact_path(self.directory, relative)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            # An offline migration may have published the bundle since this
            # reader was opened. Its committed copy precedes any loose unlink.
            return self.bundled(relative)


def read_artifact(directory: str | Path, reference: dict[str, Any] | str) -> bytes:
    """Resolve a logical trace reference; feed array bytes to np.load(BytesIO())."""
    with ArtifactReader(directory) as reader:
        return reader.read(reference)


def _atomic_json(path: Path, value: dict) -> None:
    """Flush a compaction receipt before atomically replacing its destination."""
    fd, temporary = tempfile.mkstemp(prefix=".compact-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def compact_arrays(directory: str | Path, *, inactive: bool = False, remove_loose: bool = False) -> dict:
    """Copy, commit, reopen and verify every NPY before removing redundant files.

    The caller must first stop/verify the absence of writers (including legacy
    recorders). Interrupted migration can be repeated; existing copies must
    match. Event streams, manifests, images and replay NPZ files are untouched.
    """
    if not inactive:
        raise ValueError("Confirm this run has no active writer before compaction")
    directory = Path(directory).resolve()
    if not (directory / "run.json").is_file() or not (directory / "events.jsonl").is_file():
        raise ValueError("Expected a recorded run directory")
    originals = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                 for name in ("run.json", "events.jsonl")}
    files = sorted((directory / "artifacts").glob("*.npy"))
    writer = ArrayWriter(directory)
    entries = []
    try:
        for index, path in enumerate(files):
            if path.is_symlink():
                raise ValueError(f"Refusing to compact a symlink: {path}")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if path.name != digest + ".npy":
                raise ValueError(f"Array filename checksum mismatch: {path}")
            relative = str(path.relative_to(directory))
            writer.put(relative, data, digest)
            entries.append((relative, digest, len(data)))
            if (index + 1) % 500 == 0:
                writer.flush()
        writer.flush()
    finally:
        writer.close()
    with ArtifactReader(directory) as reader:
        for relative, digest, size in entries:
            content = reader.bundled(relative)
            if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f"Copied array verification failed: {relative}")
        if reader.connection is not None:
            if reader.connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("Array database integrity check failed")
    for name, digest in originals.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Run changed during compaction; loose files retained")
    receipt = {
        "schema": "humanclaw_array_compaction_v1", "database": ARRAY_DATABASE,
        "run_directory": str(directory), "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "state": "verified_copy", "verified_arrays": len(entries),
        "array_bytes": sum(row[2] for row in entries),
        "entries_sha256": hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest(),
        "original_files_sha256": originals, "removed_loose_files": 0,
    }
    receipt_path = directory / "array_compaction.json"
    # A verified durable destination and receipt always precede any unlink.
    _atomic_json(receipt_path, receipt)
    if remove_loose:
        for relative, digest, size in entries:
            path = directory / relative
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Source changed after verification: {relative}")
            path.unlink()
            receipt["removed_loose_files"] += 1
    receipt["state"] = "completed"
    _atomic_json(receipt_path, receipt)
    return receipt
