"""Synchronous owner evidence for committed ticks and action attempts."""
from collections.abc import Mapping
from pathlib import Path
import json
import os
import time
import resource

import numpy as np

from topogym.utils.io import to_jsonable, write_json_atomic, sha256_file


class EvidenceError(RuntimeError):
    pass


class SegmentEvidence:
    def __init__(self, root, env, *, deduplicate_arrays=False):
        self.root = Path(root)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        (self.private / "arrays").mkdir()
        self.streams = {}
        self.ticks = self.array_chunks = self.bytes = 0
        self.deduplicate_arrays = bool(deduplicate_arrays)
        # One previous value per field path bounds memory independently of run
        # length. Compare exact C-order bytes; no hash collision or float rounding
        # can merge different physical measurements.
        self._previous_arrays = {}
        self.array_references_reused = self.array_bytes_reused = 0
        self.started = time.monotonic()
        self.closed = False
        try:
            for name in ("control_steps", "physics_states", "history_events"):
                self.streams[name] = (self.private / f"{name}.jsonl").open("x")
            write_json_atomic(self.root / "config.json", env.config)
            write_json_atomic(self.root / "asset_manifest.json", env._asset_build.sha256)
            package = Path(__file__).resolve().parents[2]
            sources = sorted(package.rglob("*.py"))
            write_json_atomic(self.root / "source_manifest.json", {
                "source_hashes": {str(p.relative_to(package)): sha256_file(p) for p in sources},
            })
            write_json_atomic(self.private / "static_model.json", {
                "episode": env.episode_metadata, "timing": env.timing_spec,
                "measurement_format": "readable measurements; not engine checkpoints",
            })
        except BaseException:
            self.close()
            raise

    def write(self, kind, value):
        try:
            line = json.dumps(to_jsonable(value), ensure_ascii=False, allow_nan=False) + "\n"
            stream = self.streams[kind]
            stream.write(line)
            stream.flush()
            self.bytes += len(line.encode())
        except Exception as error:
            raise EvidenceError("Evidence write failed") from error

    def tick(self, record, *, segment_id):
        """Commit numerical chunks before any JSONL reference becomes visible."""
        arrays = {}
        previous = self._previous_arrays
        pending = {}
        reused = reused_bytes = 0
        chunk = f"arrays/chunk_{self.array_chunks:08d}.npz"
        def encode(value, path=()):
            nonlocal reused, reused_bytes
            if isinstance(value, np.ndarray) and value.nbytes >= 512:
                if value.dtype.hasobject:
                    raise ValueError("Object arrays are not evidence")
                identity = None
                if self.deduplicate_arrays:
                    identity = (value.dtype, value.shape, value.tobytes(order='C'))
                    cached = previous.get(path)
                    if cached is not None and identity == cached[0]:
                        pending[path] = cached
                        reused += 1
                        reused_bytes += value.nbytes
                        return dict(cached[1])
                key = f"a{len(arrays)}"
                arrays[key] = value
                reference = {"chunk_id": self.array_chunks, "array_file": chunk, "key": key, "dtype": str(value.dtype),
                             "shape": list(value.shape)}
                if identity is not None:
                    pending[path] = (identity, reference)
                return reference
            if isinstance(value, Mapping):
                return {key: encode(child, (*path, ('key', key))) for key, child in value.items()}
            if isinstance(value, (tuple, list)):
                return [encode(child, (*path, ('index', index))) for index, child in enumerate(value)]
            return to_jsonable(value)
        try:
            row = encode(record)
            row["segment_id"] = segment_id
            if arrays:
                path = self.private / chunk
                temporary = path.with_suffix(".tmp")
                with temporary.open("xb") as output:
                    np.savez_compressed(output, **arrays)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.rename(path)
                self.array_chunks += 1
                self.bytes += path.stat().st_size
            self.write("physics_states", row)
            self.ticks += 1
            if self.deduplicate_arrays:
                # Only publish references after both chunk and JSONL succeeded.
                self._previous_arrays = pending
                self.array_references_reused += reused
                self.array_bytes_reused += reused_bytes
        except Exception as error:
            raise EvidenceError("Tick evidence failed") from error

    def policy_event(self, kind, *, segment_id, state_ref, action_index, **data):
        self.write("control_steps", dict(kind=kind, segment_id=segment_id,
            state_ref=state_ref, action_index=action_index, **data))

    def write_policy_report(self, segment_id, report):
        if type(segment_id) is not int or segment_id < 1:
            raise ValueError("Invalid segment ID")
        try:
            write_json_atomic(self.private / f"policies/segment_{segment_id}.json", report)
        except Exception as error:
            raise EvidenceError("Policy report write failed") from error

    def statistics(self):
        return dict(tick_records=self.ticks, array_chunks=self.array_chunks,
                    evidence_bytes=self.bytes, wall_time_s=time.monotonic() - self.started,
                    array_references_reused=self.array_references_reused,
                    array_bytes_reused=self.array_bytes_reused,
                    peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                    checkpoint_exported=False, ipc_contact_coverage=False,
                    actuator_force_coverage=False)

    def close(self):
        for stream in self.streams.values():
            if not stream.closed:
                stream.close()
        self.closed = True
