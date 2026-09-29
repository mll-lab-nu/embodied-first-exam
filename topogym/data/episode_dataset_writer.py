"""Write immutable transitions; never sample cameras or wrap an engine method."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING

from topogym.utils.io import to_jsonable, write_json_atomic

from topogym.data.h5_schema import SCHEMA_VERSION, TRANSITION_FIELDS

if TYPE_CHECKING:
    from topogym.simulator.history import Transition


class EpisodeDatasetWriter:
    """Stream one episode's transitions to JSONL or optional HDF5.

    ``append(transition)`` accepts the exact command/state record from Env.
    Branch changes are recorded explicitly; increasing time is required within
    each branch, not across a history restore. A caller must call ``finish``
    before clean context exit; incomplete output keeps its ``.part`` suffix.
    """

    def __init__(self, path, *, metadata=None):
        self.path = Path(path)
        if self.path.suffix not in {".jsonl", ".h5", ".hdf5"}:
            raise ValueError("Dataset path must end in .jsonl, .h5, or .hdf5")
        self.temporary = self.path.with_suffix(self.path.suffix + ".part")
        self.manifest = self.path.with_suffix(self.path.suffix + ".manifest.json")
        self.metadata = to_jsonable(metadata or {})
        self.count = 0
        self.previous = self.result = self.episode_id = None
        self.opened = self.closed = self.failed = False
        self.handle = None
        self._state_indices = []
        self._invalidated_indices = set()
        self._lifecycle_events = []
        self._manifest_status = "writing"

    def __enter__(self):
        if self.opened or self.closed:
            raise RuntimeError("A dataset writer cannot be reused")
        if self.path.exists() or self.temporary.exists() or self.manifest.exists():
            raise FileExistsError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self.path.suffix == ".jsonl":
                self.handle = self.temporary.open("x", encoding="utf-8")
            else:
                import h5py
                self.handle = h5py.File(self.temporary, "x")
                self.handle.attrs["schema_version"] = SCHEMA_VERSION
                self.handle.attrs["dataset_status"] = "writing"
                self.handle.attrs["metadata_json"] = json.dumps(self.metadata, allow_nan=False)
                self.handle.create_group("transitions")
            self.opened = True
            self._status("writing")
        except BaseException:
            if self.handle is not None:
                self.handle.close()
            self.closed = True
            raise
        return self

    def _status(self, status):
        self._manifest_status = status
        write_json_atomic(self.manifest, dict(schema_version=SCHEMA_VERSION,
            dataset_status=status, episode_id=self.episode_id, transition_count=self.count,
            metadata=self.metadata, result=self.result,
            active_transition_indices=[i for i in range(self.count) if i not in self._invalidated_indices],
            invalidated_transition_indices=sorted(self._invalidated_indices),
            lifecycle_events=self._lifecycle_events,
            path=(self.path if status == "complete" else self.temporary).name))

    def on_lifecycle(self, event):
        """Register with Env.add_lifecycle_sink to invalidate abandoned samples."""
        if self.closed and not (event["kind"] == "rewind" and event["episode_id"] == self.episode_id):
            return
        if event["kind"] == "reset" and self.episode_id and event["episode_id"] != self.episode_id:
            # A writer is episode-local; the owner must finish it before reset.
            self.failed = True
            self._lifecycle_events.append(to_jsonable(event))
            self.close(commit=False)
            return
        if event["kind"] == "rewind" and event["episode_id"] == self.episode_id:
            invalid = set(event["invalidated_state_ids"])
            self._invalidated_indices.update(i for i, state in enumerate(self._state_indices) if state in invalid)
            self.previous = None
        self._lifecycle_events.append(to_jsonable(event))
        if self.opened:
            self._status(self._manifest_status if self.closed else "writing")

    def append(self, transition: Transition):
        if not self.opened or self.closed or self.failed or self.result is not None:
            raise RuntimeError("Dataset is not accepting transitions")
        try:
            self._append(transition)
        except BaseException:
            self.failed = True
            raise

    def _append(self, transition):
        row = ({field.name: getattr(transition, field.name) for field in fields(transition)}
               if is_dataclass(transition) else dict(transition))
        if set(row) != set(TRANSITION_FIELDS):
            raise ValueError("Transition does not match the dataset schema")
        if any(not isinstance(row[key], Mapping) for key in (
                "observation", "action", "next_observation", "info")):
            raise ValueError("Transition observations, action and info must be mappings")
        plain = to_jsonable(row)
        for name in ("branch_id", "state_id", "previous_state_id", "control_step", "physics_step", "physics_steps"):
            if type(plain[name]) is not int or plain[name] < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not isinstance(plain["episode_id"], str) or not plain["episode_id"]:
            raise ValueError("An episode identity is required")
        if plain["state_id"] <= plain["previous_state_id"]:
            raise ValueError("A transition must have a new state identifier")
        if plain["physics_steps"] < 1 or plain["action_duration_s"] <= 0 or plain["sim_time_s"] < 0:
            raise ValueError("A completed transition must have positive physical duration")
        if not all(math.isfinite(plain[key]) for key in ("sim_time_s", "action_duration_s", "reward")):
            raise ValueError("Transition scalars must be finite")
        if type(plain["terminated"]) is not bool or type(plain["truncated"]) is not bool:
            raise ValueError("Termination flags must be boolean")
        branch_parent = plain["info"].get("branch_parent_state_id")
        if plain["branch_id"] > 0:
            if (type(branch_parent) is not int or branch_parent < 0 or
                    branch_parent > plain["previous_state_id"]):
                raise ValueError("A restored branch requires a valid branch_parent_state_id in info")
        elif branch_parent is not None:
            raise ValueError("The initial branch cannot have a restored parent state")
        if self.episode_id is None:
            self.episode_id = plain["episode_id"]
        elif self.episode_id != plain["episode_id"]:
            raise ValueError("A dataset contains one episode; use a new writer after reset(seed=...)")
        if self.previous is not None:
            old = self.previous
            if plain["branch_id"] > old["branch_id"]:
                self._invalidated_indices.update(i for i, state in enumerate(self._state_indices)
                                                 if state > branch_parent)
            if plain["branch_id"] < old["branch_id"] or plain["state_id"] <= old["state_id"]:
                raise ValueError("Branch and state identities cannot be reused")
            if plain["branch_id"] == old["branch_id"]:
                if branch_parent != old["branch_parent_state_id"]:
                    raise ValueError("A branch's restoration parent cannot change")
                if old["terminated"] or old["truncated"]:
                    raise ValueError("An ended branch cannot accept another transition")
                if (plain["previous_state_id"] != old["state_id"] or
                    plain["control_step"] != old["control_step"] + 1 or
                    plain["physics_step"] != old["physics_step"] + plain["physics_steps"] or
                    plain["sim_time_s"] <= old["sim_time_s"]):
                    raise ValueError("Transition sequence is discontinuous within a branch")
        if self.path.suffix == ".jsonl":
            self.handle.write(json.dumps(plain, ensure_ascii=False, allow_nan=False) + "\n")
        else:
            group = self.handle["transitions"].create_group(f"{self.count:08d}")
            self._write_group(group, row)
        self.handle.flush()
        self.previous = {key: plain[key] for key in (
            "branch_id", "state_id", "control_step", "physics_step", "sim_time_s", "terminated", "truncated")}
        self.previous["branch_parent_state_id"] = branch_parent
        self._state_indices.append(plain["state_id"])
        self.count += 1

    @staticmethod
    def _write_group(group, values):
        import h5py
        import numpy as np
        for key, value in values.items():
            if not isinstance(key, str) or not key or "/" in key:
                raise ValueError("HDF5 field names must be nonempty strings without slashes")
            if isinstance(value, Mapping):
                EpisodeDatasetWriter._write_group(group.create_group(key), value)
            elif isinstance(value, np.ndarray) and value.dtype.kind in "biuf":
                group.create_dataset(key, data=value)
            elif isinstance(value, (bool, int, float, np.number)):
                group.create_dataset(key, data=value)
            elif isinstance(value, str):
                group.create_dataset(key, data=value, dtype=h5py.string_dtype("utf-8"))
            else:
                dataset = group.create_dataset(key, data=json.dumps(to_jsonable(value), allow_nan=False),
                                               dtype=h5py.string_dtype("utf-8"))
                dataset.attrs["encoding"] = "json"

    def finish(self, result):
        if not self.opened or self.closed or self.failed or self.result is not None:
            raise RuntimeError("Cannot finish this dataset")
        if not self.count:
            raise ValueError("Cannot finish an empty dataset")
        if result is None:
            raise ValueError("A dataset result must be explicit; use an empty mapping if no task result exists")
        self.result = to_jsonable(result)

    def close(self, *, commit=False):
        if self.closed:
            return
        if not self.opened:
            self.closed = True
            return
        complete = bool(commit and not self.failed and self.result is not None and self.count)
        try:
            if self.path.suffix != ".jsonl":
                self.handle.attrs["dataset_status"] = "complete" if complete else "incomplete"
                self.handle.attrs["result_json"] = json.dumps(self.result, allow_nan=False)
            self.handle.flush()
        finally:
            self.handle.close()
            self.closed = True
        if complete:
            if self.path.exists():
                self._status("incomplete")
                raise FileExistsError(self.path)
            self.temporary.rename(self.path)
        self._status("complete" if complete else "incomplete")

    def __exit__(self, kind, value, traceback):
        try:
            self.close(commit=kind is None)
        except Exception:
            if kind is None:
                raise
        return False
