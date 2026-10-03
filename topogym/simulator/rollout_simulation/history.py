"""Sealed, permission-filtered segment history; never export raw owner evidence."""
import json
import os

from topogym.utils.io import to_jsonable
from .evidence import EvidenceError
from .policy_observation import project_robot


STATE_KEYS = ("episode_id", "branch_id", "state_id", "control_step", "physics_step",
              "sim_time_s", "terminated", "truncated")
ROBOT_KEYS = ("joint_position_rad", "tcp_position_world_m", "tcp_orientation_wxyz",
              "finger_position_m", "finger_position_rad")
# "inline": unlimited rows embed the privileged fields the policy received (an exportable log).
# "reference": rows name the owner evidence row (same tick record, keyed by state_id) instead of
# copying it, so an owner/oracle run writes the world once per tick; the log is then not self-contained.
PRIVILEGED_STORAGES = ("inline", "reference")
PHYSICS_EVIDENCE = "private/physics_states.jsonl"


class SegmentHistory:
    def __init__(self, root, segment_id, profile=None, privileged_storage="inline"):
        if privileged_storage not in PRIVILEGED_STORAGES:
            raise ValueError("privileged_storage must be inline or reference")
        self.root, self.segment_id, self.profile = root, segment_id, profile
        self.privileged_storage = privileged_storage
        self.directory = root / f"segments/segment_{segment_id}"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.streams = {}
        self.counts = dict(steps=0, events=0)
        try:
            for name in self.counts:
                self.streams[name] = (self.directory / f"{name}.jsonl").open("x", encoding="utf-8")
        except BaseException:
            self.close()
            raise

    def _write(self, kind, value):
        try:
            self.streams[kind].write(json.dumps(to_jsonable(value), ensure_ascii=False,
                                                allow_nan=False) + "\n")
            self.streams[kind].flush()
            self.counts[kind] += 1
        except Exception as error:
            raise EvidenceError("Segment history write failed") from error

    def tick(self, record, *, action=None, action_index=None, initial=False):
        try:
            if self.profile is None:
                robot = {arm: {key: values[key] for key in ROBOT_KEYS if key in values}
                         for arm, values in record["robot"].items()}
            else:
                robot = project_robot(record["robot"], self.profile.robot_fields)
            row = dict(schema_version=1, segment_id=self.segment_id,
                kind="initial" if initial else "tick", record_index=self.counts["steps"],
                state={key: record["state"][key] for key in STATE_KEYS}, robot=robot,
                action=action, action_index=action_index)
            if self.profile is not None and self.profile.mode == "unlimited":
                if self.privileged_storage == "inline":
                    row["privileged"] = {name: record[name] for name in self.profile.state_fields}
                elif self.profile.state_fields:
                    row["privileged_ref"] = dict(source=PHYSICS_EVIDENCE, state_id=record["state"]["state_id"],
                                                 fields=list(self.profile.state_fields))
            self._write("steps", row)
        except EvidenceError:
            raise
        except Exception as error:
            raise EvidenceError("Segment history projection failed") from error

    def event(self, kind, **values):
        self._write("events", dict(schema_version=1, segment_id=self.segment_id,
                                   kind=kind, **values))

    def close(self):
        errors = []
        for stream in self.streams.values():
            if not stream.closed:
                try:
                    stream.flush()
                    os.fsync(stream.fileno())
                except Exception as error:
                    errors.append(error)
                finally:
                    stream.close()
        if errors:
            raise EvidenceError("Segment history seal failed") from errors[0]

    def finish(self):
        self.close()
        return {kind: str((self.directory / f"{kind}.jsonl").relative_to(self.root))
                for kind in self.streams}
