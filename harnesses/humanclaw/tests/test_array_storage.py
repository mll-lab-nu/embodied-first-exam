import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import numpy as np
import pytest

from humanclaw_bench.experiments.artifacts import (
    ARRAY_DATABASE, ArtifactReader, ArrayWriter, compact_arrays, read_artifact,
)
from humanclaw_bench.experiments.recorder import TraceRecorder, event
from humanclaw_bench.experiments.report import validate_trace


def loose_run(tmp_path, count=12):
    directory = tmp_path / "run_legacy"
    directory.mkdir()
    (directory / "artifacts").mkdir()
    (directory / "run.json").write_text('{"status":"completed"}')
    (directory / "events.jsonl").write_text('original event bytes\n')
    (directory / "trajectory_after.npz").write_bytes(b"original replay")
    refs = []
    for i in range(count):
        buffer = io.BytesIO()
        np.save(buffer, np.arange(30, dtype=np.float32) + i, allow_pickle=False)
        content = buffer.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        ref = {"artifact": f"artifacts/{digest}.npy", "sha256": digest}
        (directory / ref["artifact"]).write_bytes(content)
        refs.append((ref, content))
    return directory, refs


def test_compaction_is_lossless_readonly_and_preserves_raw_logs(tmp_path):
    directory, refs = loose_run(tmp_path)
    originals = {name: (directory / name).read_bytes() for name in ("events.jsonl", "run.json", "trajectory_after.npz")}
    receipt = compact_arrays(directory, inactive=True, remove_loose=True)
    assert receipt["removed_loose_files"] == len(refs)
    assert not list((directory / "artifacts").iterdir())
    before = {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}
    with ArtifactReader(directory) as reader:
        for ref, content in refs:
            assert reader.read(ref) == content
    assert before == {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}
    for name, content in originals.items():
        assert (directory / name).read_bytes() == content


def test_refuses_active_or_corrupt_source_without_removing_any_files(tmp_path):
    directory, refs = loose_run(tmp_path)
    with pytest.raises(ValueError, match="no active writer"):
        compact_arrays(directory, remove_loose=True)
    (directory / refs[-1][0]["artifact"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum mismatch"):
        compact_arrays(directory, inactive=True, remove_loose=True)
    assert len(list((directory / "artifacts").iterdir())) == len(refs)


def test_interrupted_removal_can_resume_from_verified_bundle(tmp_path, monkeypatch):
    directory, refs = loose_run(tmp_path)
    original = Path.unlink
    removed = []
    def interrupt(path, *args, **kwargs):
        if path.suffix == ".npy":
            if len(removed) == 3:
                raise OSError("simulated interrupted migration")
            removed.append(path)
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", interrupt)
        with pytest.raises(OSError, match="interrupted migration"):
            compact_arrays(directory, inactive=True, remove_loose=True)
    assert len(removed) == 3
    for ref, content in refs:
        assert read_artifact(directory, ref) == content
    compact_arrays(directory, inactive=True, remove_loose=True)
    assert not list((directory / "artifacts").iterdir())
    for ref, content in refs:
        assert read_artifact(directory, ref) == content


def test_corrupt_bundle_does_not_remove_loose_originals(tmp_path):
    directory, refs = loose_run(tmp_path)
    compact_arrays(directory, inactive=True)
    with sqlite3.connect(directory / ARRAY_DATABASE) as connection:
        connection.execute("UPDATE artifacts SET content=? WHERE path=?", (b"broken", refs[0][0]["artifact"]))
    with pytest.raises(ValueError, match="Conflicting stored array"):
        compact_arrays(directory, inactive=True, remove_loose=True)
    assert len(list((directory / "artifacts").iterdir())) == len(refs)


def test_both_storage_forms_reject_escape_and_corrupt_reference(tmp_path):
    directory, refs = loose_run(tmp_path)
    (directory / "outside").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        read_artifact(directory, "outside/secret")
    with pytest.raises(ValueError, match="escapes"):
        read_artifact(directory, "../secret")
    with pytest.raises(ValueError, match="checksum mismatch"):
        read_artifact(directory, {**refs[0][0], "sha256": "wrong"})


def test_many_arrays_use_constant_file_count_and_survive_process_exit(tmp_path):
    script = '''
import os, numpy as np
from humanclaw_bench.experiments.recorder import TraceRecorder, event
r = TraceRecorder(os.environ["TEST_TRACE_OUTPUT"], {})
with r:
    event("physics.state", data={"states": [np.array([i], dtype=np.float32) for i in range(2500)]})
    print(str(r.directory), flush=True)
    os._exit(0)
'''
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "TEST_TRACE_OUTPUT": str(tmp_path)}, capture_output=True, text=True, check=True)
    directory = Path(result.stdout.strip())
    assert len([p for p in directory.rglob("*") if p.is_file()]) <= 4
    rows = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    with ArtifactReader(directory) as reader:
        for i, ref in enumerate(rows[-1]["data"]["states"]):
            assert np.load(io.BytesIO(reader.read(ref)), allow_pickle=False).item() == i
    diagnostics = validate_trace(directory)
    assert diagnostics["ok"]
    assert any("Missing run.end" in warning for warning in diagnostics["warnings"])


def test_failed_manifest_finalization_does_not_duplicate_run_end(tmp_path, monkeypatch):
    recorder = TraceRecorder(tmp_path, {})
    original = recorder.write_json
    def fail(name, data):
        if name == "run.json":
            raise OSError("simulated quota failure")
        return original(name, data)
    monkeypatch.setattr(recorder, "write_json", fail)
    with pytest.raises(OSError, match="quota failure"):
        with recorder:
            event("state", data={"array": np.arange(8)})
            recorder.finish()
    rows = [json.loads(line) for line in (recorder.directory / "events.jsonl").read_text().splitlines()]
    assert sum(row["event"] == "run.end" for row in rows) == 1
    assert recorder._events.closed and recorder._arrays.closed
    assert "Manifest status differs" in " ".join(validate_trace(recorder.directory)["errors"])


def test_bundled_reads_do_not_probe_thousands_of_missing_loose_files(tmp_path, monkeypatch):
    directory, refs = loose_run(tmp_path)
    compact_arrays(directory, inactive=True, remove_loose=True)
    original_read = Path.read_bytes
    original_symlink = Path.is_symlink
    def read(path):
        assert path.suffix != ".npy", "Bundled arrays must not incur per-array filesystem opens"
        return original_read(path)
    def symlink(path):
        assert path.suffix != ".npy", "Bundled arrays must not incur per-array filesystem stats"
        return original_symlink(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(Path, "is_symlink", symlink)
    with ArtifactReader(directory) as reader:
        for ref, content in refs:
            assert reader.read(ref) == content


def test_invalid_checksum_field_is_reported_instead_of_crashing(tmp_path):
    with TraceRecorder(tmp_path, {}) as recorder:
        event("broken.ref", data={"artifact":"artifacts/missing.npy", "sha256":{"bad":"type"}})
    diagnostics = validate_trace(recorder.directory)
    assert not diagnostics["ok"]
    assert any("Invalid artifact checksum" in error for error in diagnostics["errors"])


def test_crash_during_uncommitted_array_write_recovers_without_mutating_original(tmp_path):
    script = '''
import os, numpy as np
from humanclaw_bench.experiments.recorder import TraceRecorder, event
r=TraceRecorder(os.environ["TEST_TRACE_OUTPUT"], {})
with r:
    event("committed",data={"array":np.arange(8)})
    r._arrays.connection.execute("PRAGMA cache_size=5")
    r.artifact(np.arange(100000,dtype=np.float64))
    print(str(r.directory),flush=True)
    os._exit(0)
'''
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "TEST_TRACE_OUTPUT": str(tmp_path)}, capture_output=True, text=True, check=True)
    directory = Path(result.stdout.strip())
    assert (directory / (ARRAY_DATABASE + "-journal")).is_file()
    before = {path: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    row = json.loads((directory / "events.jsonl").read_text().splitlines()[-1])
    with ArtifactReader(directory) as reader:
        content = reader.read(row["data"]["array"])
        np.testing.assert_array_equal(np.load(io.BytesIO(content),allow_pickle=False),np.arange(8))
        assert reader._recovery is not None
        temporary = Path(reader._recovery.name)
    assert not temporary.exists()
    assert validate_trace(directory)["ok"]
    assert before == {path: path.read_bytes() for path in directory.iterdir() if path.is_file()}
