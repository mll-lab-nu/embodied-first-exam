"""Publish only sealed core results and their authorized artifact descriptors."""
import hashlib
import os
from pathlib import Path

from topogym.utils.io import to_jsonable, relative_file
from .protocol import atomic_json


class PublicArtifacts:
    def __init__(self, runner, root, camera_ids, *, state_fields=()):
        self.runner = runner
        self.root = Path(root)
        self.root.mkdir(mode=0o755, parents=True, exist_ok=True)
        self.camera_ids = tuple(camera_ids)
        self.state_fields = frozenset(state_fields)
        self.entries = {}
        self.history = {}

    def json(self, relative, value):
        atomic_json(self.root / relative, to_jsonable(value))

    def _export(self, value):
        if isinstance(value, dict):
            if "artifact_id" in value:
                identity = value["artifact_id"]
                entry = self.runner._artifacts.entries[identity]
                required = frozenset(entry.get("required_state_fields", ()))
                if entry["private"] and (not required or not required <= self.state_fields):
                    raise PermissionError("Cannot publish private artifact")
                if any(value[key] != entry[key] for key in ("size_bytes", "sha256")):
                    raise ValueError("Artifact descriptor mismatch")
                source = relative_file(self.runner.root, entry["relative"])
                suffix = Path(entry["relative"]).suffix
                relative = (entry["relative"] if entry["relative"].startswith("segments/") else
                            f"artifacts/{identity}{suffix}")
                target = self.root / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                temp = target.with_name(target.name + ".partial")
                digest, size = hashlib.sha256(), 0
                try:
                    with source.open("rb") as origin, temp.open("xb") as stream:
                        for block in iter(lambda: origin.read(1024 * 1024), b""):
                            digest.update(block)
                            size += len(block)
                            stream.write(block)
                        stream.flush()
                        os.fsync(stream.fileno())
                        os.fchmod(stream.fileno(), 0o644)
                    if size != value["size_bytes"] or digest.hexdigest() != value["sha256"]:
                        raise ValueError("Artifact has changed")
                    temp.replace(target)
                finally:
                    temp.unlink(missing_ok=True)
                self.entries[identity] = {**value, "path": str(target),
                                          "archive_relative": entry["relative"]}
                value["path"] = str(target)
            else:
                for item in value.values():
                    self._export(item)
        elif isinstance(value, list):
            for item in value:
                self._export(item)

    def publish(self, result, *, initial=False):
        value = to_jsonable(result)
        if initial:
            if value["segment_id"] != 0:
                raise ValueError("Initial segment must be zero")
        if "token" in value or value.get("status") not in {"complete", "incomplete"}:
            raise ValueError("Only sealed results may be published")
        if not set(value.get("media", {}).get("camera_order", [])) <= set(self.camera_ids):
            raise PermissionError("Cannot publish unauthorized cameras")
        self._export(value)
        self.json("public_artifacts.json", {"schema_version": 1, "artifacts": self.entries})
        # Keep a manager copy for host archive verification; public paths are ephemeral.
        atomic_json(self.runner.root / "publication.json", {"artifacts": self.entries})
        relative = f"segments/segment_{value['segment_id']}/result.json"
        self.json(relative, value)  # completion marker comes last
        self.history[value["segment_id"]] = dict(segment_id=value["segment_id"],
            status=value["status"], reason=value.get("reason"),
            result_path=str(self.root / relative), result_relative=relative,
            start_state_ref=value.get("start_state_ref"), end_state_ref=value.get("end_state_ref"))
        history = dict(schema_version=2, episode_id=self.runner.episode_id,
                       segments=[self.history[key] for key in sorted(self.history)])
        self.json("history.json", history)
        atomic_json(self.runner.root / "history.json", history)
        return str(self.root / relative)
