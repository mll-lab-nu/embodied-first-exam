"""Passive control-step tracking from committed Env records (never advances physics)."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
from scipy.spatial.transform import Rotation

from .contracts import json_value
from topogym.utils.io import write_json_atomic


def pose(value):
    p = np.asarray(value["position_m"], dtype=float)
    q = np.asarray(value["quaternion_wxyz"], dtype=float)
    if p.shape != (3,) or q.shape != (4,) or not np.isfinite(np.r_[p, q]).all():
        raise ValueError("Pose requires finite position_m[3] and quaternion_wxyz[4]")
    if not np.isclose(np.linalg.norm(q), 1., atol=1e-6, rtol=0):
        raise ValueError("Pose quaternion must be unit wxyz")
    return p, Rotation.from_quat(q[[1, 2, 3, 0]])


def pose_dict(p, r):
    return dict(position_m=np.asarray(p).tolist(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist())


def relative(a, b):
    """Pose of a in b's frame."""
    ap, ar = pose(a)
    bp, br = pose(b)
    return pose_dict(br.inv().apply(ap-bp), br.inv()*ar)


def pose_error(actual, target):
    ap, ar = pose(actual)
    tp, tr = pose(target)
    return dict(translation_m=float(np.linalg.norm(ap-tp)), rotation_rad=float((ar*tr.inv()).magnitude()))


def tcp_pose(row):
    return dict(position_m=row["tcp_position_world_m"], quaternion_wxyz=row["tcp_orientation_wxyz"])


def requested_tcp(action, robot, mode):
    result = {}
    for side, command in action.items():
        if mode == "EE_ABS" and "position_world_m" in command:
            target = dict(position_m=command["position_world_m"], quaternion_wxyz=command["orientation_wxyz"])
            pose(target)
            result[side] = target
        elif mode == "EE_DELTA" and set(command) & {"translation_world_m", "rotation_world_rad"}:
            p, r = pose(tcp_pose(robot[side]))
            result[side] = pose_dict(p+np.asarray(command.get("translation_world_m", [0, 0, 0])),
                Rotation.from_rotvec(command.get("rotation_world_rad", [0, 0, 0]))*r)
    return result


def reference(value):
    if value is None:
        return None
    value = json_value(value)
    if not isinstance(value, dict) or not all(value.get(k) for k in ("plan_id", "version", "phase")):
        raise ValueError("debug_reference needs plan_id, version and phase")
    if value.get("frame") != "world" or value.get("units") != "m_wxyz":
        raise ValueError("debug_reference must declare frame='world', units='m_wxyz'")
    for target in value.get("objects", {}).values():
        pose(target)
    for row in value.get("relative_targets", []):
        if row["entity"] == row["reference"]:
            raise ValueError("Relative target needs distinct entities")
        pose(row["pose"])
    for name, budget in value.get("clearances", {}).items():
        if name not in value.get("objects", {}) or not budget.get("geometry_id"):
            raise ValueError("Clearance needs corresponding object target and geometry_id")
        for key in ("clearance_m", "radius_m"):
            if not np.isfinite(budget[key]) or budget[key] < 0:
                raise ValueError("Clearance and object radius must be finite and nonnegative")
    return value


class Tracking:
    def __init__(self, output, send):
        self.output, self.send = Path(output), send
        self.records = {}
        self.pending = None
        self.sequence = 0

    def start(self, initial, *, entities=(), relative_pairs=(), thresholds=None, reference_provider=None):
        if reference_provider not in (None, "policy", "keyhole"):
            raise ValueError("reference_provider is None, 'policy', or 'keyhole' (use debug_reference for other adapters)")
        entities = list(dict.fromkeys(entities))
        pairs = [list(p) for p in relative_pairs]
        if any(len(p) != 2 or p[0] == p[1] for p in pairs):
            raise ValueError("relative_pairs contains [entity, reference] pairs")
        names = set(entities) | {n for p in pairs for n in p}
        if not names <= initial["world"]["bodies"].keys():
            raise ValueError("Unknown tracked rigid body")
        thresholds = dict(thresholds or {})
        if set(thresholds)-{"joint_rad", "tcp_m", "tcp_rad", "object_m", "object_rad", "relative_m", "relative_rad"}:
            raise ValueError("Unknown tracking threshold")
        if any(isinstance(v, bool) or not np.isfinite(v) or v < 0 for v in thresholds.values()):
            raise ValueError("Thresholds must be finite and nonnegative")
        key = uuid4().hex
        folder = self.output / "tracking" / key
        folder.mkdir(parents=True)
        row = dict(tracking_id=key, active=True, entities=entities, relative_pairs=pairs,
                   thresholds=thresholds, reference_provider=reference_provider,
                   completed_samples=0, incomplete_attempts=0, rejected_attempts=0,
                   invalidated_samples=0, maxima={}, first_violation=None, rewind_events=[],
                   samples=str(folder / "samples.jsonl"), summary=str(folder / "summary.json"),
                   coverage=dict(sampling="committed World ticks; step-end samples and within-step maxima",
                       solver_substeps=False, object_reference="optional per-action; constant over this action",
                       physics_evidence="execution/private/physics_states.jsonl", physical_success=False))
        self.records[key] = row
        self._write(row, dict(kind="initial", state=initial["state"], measured=self._measured(initial, row)))
        self._publish(row)
        return self.report(key)

    def _measured(self, record, row):
        bodies = record["world"]["bodies"]
        names = set(row["entities"]) | {n for pair in row["relative_pairs"] for n in pair}
        return json_value(dict(robot=record["robot"],
            objects={n: {k: bodies[n][k] for k in ("position_m", "quaternion_wxyz")} for n in names if n in bodies},
            relative=[dict(entity=a, reference=b, pose=relative(bodies[a], bodies[b]))
                      for a, b in row["relative_pairs"] if a in bodies and b in bodies]))

    def begin(self, action, before, mode, *, segment_id, action_index, policy=None):
        if not any(row["active"] for row in self.records.values()):
            return
        if self.pending is not None:
            raise RuntimeError("Previous tracking attempt was not finalized")
        self.sequence += 1
        # An invalid command remains the Env's responsibility, not a tracker failure.
        try:
            tcp = requested_tcp(action, before["robot"], mode)
        except (ValueError, TypeError, KeyError, AttributeError):
            tcp = {}
        self.pending = dict(attempt_id=self.sequence, before=json_value(before["state"]),
            action=json_value(action), mode=mode, segment_id=segment_id, action_index=action_index,
            requested_tcp=tcp, rows={})
        for key, row in self.records.items():
            if not row["active"]:
                continue
            ref, error = None, None
            try:
                getter = getattr(policy, "debug_reference", None)
                if getter is not None:
                    ref = reference(getter())
                elif row["reference_provider"] == "keyhole":
                    raise ValueError("Use adapters.keyhole_reference.make_policy to capture pre-increment progress")
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            attempt = dict(reference=ref, reference_error=error, ticks=0, maxima={}, first_violation=None, last=None)
            self.pending["rows"][key] = attempt
            self._write(row, dict(kind="attempt", **{k: v for k, v in self.pending.items() if k != "rows"},
                                 reference=ref, reference_error=error))

    def _metrics(self, record, row, attempt):
        robot, targets, bodies = record["robot"], record["targets"], record["world"]["bodies"]
        metrics = {}
        for side, target in targets.items():
            if "joint_position_rad" in target:
                metrics[f"joint_rad/{side}"] = float(np.max(np.abs(
                    np.asarray(robot[side]["joint_position_rad"])-target["joint_position_rad"])))
        for side, target in self.pending["requested_tcp"].items():
            error = pose_error(tcp_pose(robot[side]), target)
            metrics.update({f"tcp_m/{side}": error["translation_m"], f"tcp_rad/{side}": error["rotation_rad"]})
        ref = attempt["reference"] or {}
        for name, target in ref.get("objects", {}).items():
            if name not in bodies:
                continue
            error = pose_error(bodies[name], target)
            metrics.update({f"object_m/{name}": error["translation_m"], f"object_rad/{name}": error["rotation_rad"]})
            budget = ref.get("clearances", {}).get(name)
            # The adapter declares geometry identity; this is a conservative displacement warning, not a certificate.
            if budget:
                bound = error["translation_m"] + 2*budget["radius_m"]*np.sin(error["rotation_rad"]/2)
                metrics[f"clearance_excess_m/{name}"] = float(bound-budget["clearance_m"])
        for target in ref.get("relative_targets", []):
            a, b = target["entity"], target["reference"]
            if a in bodies and b in bodies:
                error = pose_error(relative(bodies[a], bodies[b]), target["pose"])
                metrics.update({f"relative_m/{a}@{b}": error["translation_m"],
                                f"relative_rad/{a}@{b}": error["rotation_rad"]})
        return metrics

    def tick(self, record):
        if self.pending is None:
            return  # Initial/rewind saves are not action execution.
        for key, attempt in self.pending["rows"].items():
            row = self.records[key]
            metrics = self._metrics(record, row, attempt)
            for name, value in metrics.items():
                attempt["maxima"][name] = max(value, attempt["maxima"].get(name, value))
                threshold = row["thresholds"].get(name.split("/")[0])
                if name.startswith("clearance_excess_m/"):
                    threshold = 0.
                if threshold is not None and value > threshold and attempt["first_violation"] is None:
                    attempt["first_violation"] = dict(metric=name, value=value, threshold=threshold,
                                                       state=json_value(record["state"]))
            attempt["ticks"] += 1
            attempt["last"] = dict(state=json_value(record["state"]), targets=json_value(record["targets"]),
                                   measured=self._measured(record, row), errors=metrics)
            # Durable tick metrics let a killed worker's partial attempt be reconstructed.
            self._write(row, dict(kind="tick", attempt_id=self.pending["attempt_id"],
                                 state=record["state"], errors=metrics))

    def finish(self, transition=None):
        if self.pending is None:
            return
        pending, self.pending = self.pending, None
        for key, attempt in pending["rows"].items():
            row = self.records[key]
            complete = transition is not None
            if complete and attempt["ticks"] != transition.physics_steps:
                raise RuntimeError("Tracking tick count differs from committed transition")
            status = "complete" if complete else "partial" if attempt["ticks"] else "rejected_or_unexecuted"
            row["completed_samples" if complete else "incomplete_attempts" if attempt["ticks"] else "rejected_attempts"] += 1
            sample = dict(kind="sample", **{k: v for k, v in pending.items() if k != "rows"},
                          **attempt, status=status, reference_status="available" if attempt["reference"] else "reference_unavailable")
            if transition is not None:
                sample.update(action_duration_s=transition.action_duration_s,
                              executed_joint_targets=json_value(transition.info.get("executed_joint_targets", {})))
            self._write(row, sample)
            for name, value in attempt["maxima"].items():
                row["maxima"][name] = max(value, row["maxima"].get(name, value))
            if row["first_violation"] is None and attempt["first_violation"] is not None:
                row["first_violation"] = dict(attempt_id=pending["attempt_id"], **attempt["first_violation"])
            self._publish(row)

    def rewind(self, valid_states, new_state):
        valid = set(valid_states)
        for row in self.records.values():
            invalid = []
            # Rewind is rare: scan compact samples instead of retaining an unbounded in-memory trace.
            with open(row["samples"]) as stream:
                for line in stream:
                    sample = json.loads(line)
                    if sample["kind"] == "sample" and sample["last"] is not None:
                        if sample["last"]["state"]["state_id"] not in valid:
                            invalid.append(sample["attempt_id"])
            event = dict(kind="rewind", invalidated_attempts=invalid, new_state=new_state)
            row["invalidated_samples"] = len(invalid)
            row["rewind_events"].append(event)
            row["statistics_scope"] = "lifetime including invalidated futures; use rewind events for valid-path analysis"
            self._write(row, event)
            self._publish(row)

    @staticmethod
    def _write(row, sample):
        with open(row["samples"], "a") as stream:
            stream.write(json.dumps(json_value(sample), separators=(",", ":"), allow_nan=False)+"\n")

    def _publish(self, row):
        write_json_atomic(row["summary"], row, mode=0o600)
        self.send(dict(kind="tracking_summary", summary=deepcopy(row)))

    def report(self, tracking_id):
        return deepcopy(self.records[tracking_id])

    def stop(self, tracking_id):
        row = self.records[tracking_id]
        row["active"] = False
        self._publish(row)
        return self.report(tracking_id)

    def close(self):
        self.finish()
        for key in self.records:
            self.stop(key)


def read_tracking_report(directory, *, valid_only=False):
    """Reconstruct metrics after close/worker loss without loading Genesis or FEM arrays."""
    directory = Path(directory)
    summary = json.loads((directory / "summary.json").read_text())
    attempts, invalidated, torn_tail = {}, set(), False
    with (directory / "samples.jsonl").open() as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                torn_tail = True
                break
            if row["kind"] == "attempt":
                attempts[row["attempt_id"]] = dict(status="uncommitted", ticks=0, maxima={})
            elif row["kind"] == "tick":
                attempt = attempts[row["attempt_id"]]
                attempt["ticks"] += 1
                for name, value in row["errors"].items():
                    attempt["maxima"][name] = max(value, attempt["maxima"].get(name, value))
            elif row["kind"] == "sample":
                attempts[row["attempt_id"]].update(status=row["status"], ticks=row["ticks"], maxima=row["maxima"])
            elif row["kind"] == "rewind":
                invalidated.update(row["invalidated_attempts"])
    rows = [v for k, v in attempts.items() if not valid_only or k not in invalidated]
    maxima = {}
    for row in rows:
        for name, value in row["maxima"].items():
            maxima[name] = max(value, maxima.get(name, value))
    return dict(summary, reconstructed=True, valid_only=valid_only, torn_tail_ignored=torn_tail,
        completed_samples=sum(r["status"] == "complete" for r in rows),
        incomplete_attempts=sum(r["ticks"] > 0 and r["status"] != "complete" for r in rows),
        rejected_attempts=sum(r["status"] == "rejected_or_unexecuted" for r in rows),
        uncommitted_attempts=sum(r["status"] == "uncommitted" for r in rows),
        invalidated_samples=len(invalidated), maxima=maxima,
        first_violation_scope="stored lifetime summary; inspect sample/tick records for valid-path first violation")
