#!/usr/bin/env python3
"""Independently replay the frozen Buzz Task on every recorded physics tick."""
import argparse
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def restore_release_geometry_shapes(world):
    """Recover the schema-defined shape of inline empty plane arrays.

    The numeric evidence writer serializes small arrays with ``tolist()``.
    Consequently a valid (0, 4) convex cover becomes [], losing its second
    dimension. An empty cover retains the collider's conservative box; it
    does not remove that collider. Leave every nonempty value untouched so
    the frozen Task still validates its shape, finiteness, and unit normals.
    """
    import numpy as np

    geometry = world.get("release_geometry", {})
    if geometry is None or geometry.get("schema_version") != 2:
        return 0
    planes = geometry.get("robot_convex_planes_m")
    if not isinstance(planes, list):
        return 0
    restored = 0
    for index, value in enumerate(planes):
        if isinstance(value, list) and not value:
            planes[index] = np.empty((0, 4), dtype=float)
            restored += 1
    return restored


def audit(folder):
    folder = folder.resolve()
    source = folder/"source_snapshot"
    manifest = json.loads((folder/"run_source_manifest.json").read_text())
    for name, expected in manifest.items():
        if digest(source/name) != expected:
            raise ValueError(f"Frozen source changed: {name}")
    sys.path.insert(0, str(source))
    import numpy as np
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator import SimulatorConfig
    from topogym.utils.io import to_jsonable
    report = json.loads((folder/"run_report.json").read_text())
    segmented = report.get("policy_kind") == "segmented_feedback_with_compiled_prefix"
    if segmented:
        for name, expected in report["submission_artifact_sha256"].items():
            path = (folder/name).resolve()
            if not path.is_relative_to(folder) or digest(path) != expected:
                raise ValueError(f"Changed live submission artifact: {name}")
        for command, files in report["submitted_policies"].items():
            for name, expected in files.items():
                if digest(folder/"policy_submissions"/command/name) != expected:
                    raise ValueError(f"Changed live policy: {command}/{name}")
    feedback_finish = report.get("policy_kind") == "compiled_prefix_then_observation_feedback"
    compiled = report.get("policy_kind") == "compiled_joint_actions_from_checked_ik_development" or feedback_finish
    if compiled and digest(folder/"policy_actions.json") != report["compiled_actions_sha256"]:
        raise ValueError("Compiled action input changed")
    config = SimulatorConfig(**report["config"])
    task = task_definition(config.task_id, config.variation_id)(config.task_parameters, seed=report["seed"])
    scene = load_scene_config(config)
    issues, array_hashes = [], {}
    limits = np.asarray(scene.robot_control.robot.arm_joint_limits)
    margins = dict(actual=float("inf"), commanded=float("inf"))
    counts = dict(ticks=0, metal_touch_events=0, robot_wire_touch_events=0, coverage_incomplete_ticks=0)
    acquisitions, previous, world = {}, None, None
    empty_plane_arrays_restored = 0
    # Consecutive ticks share array chunks. Decode each compressed archive once
    # instead of reopening all of its arrays for every tick that references it.
    chunks = OrderedDict()
    with tempfile.TemporaryDirectory(prefix="buzz_audit_") as temporary:
        spec = task.declare(Path(temporary), float(scene.env.frames.table_surface.origin[2]))
        task.finalize_spec(spec, asset_dir=Path(temporary), scene_config=scene)
        if task.instance_id != report["instance_id"]:
            issues.append("Instance identity differs from report")
        for line in (folder/"private/physics_states.jsonl").open():
            def decode(value):
                if isinstance(value, dict):
                    if "array_file" in value and "key" in value:
                        name = value["array_file"]
                        path = (folder/"private"/name).resolve()
                        if not path.is_relative_to(folder/"private/arrays"):
                            raise ValueError("Array reference escapes evidence directory")
                        if name not in chunks:
                            array_hashes.setdefault(name, digest(path))
                            with np.load(path, allow_pickle=False) as archive:
                                chunks[name] = {k: archive[k] for k in archive.files}
                            while len(chunks) > 2:
                                chunks.popitem(last=False)
                        chunks.move_to_end(name)
                        result = chunks[name][value["key"]]
                        if list(result.shape) != value["shape"] or str(result.dtype) != value["dtype"]:
                            raise ValueError("Array reference layout mismatch")
                        return result
                    return {k: decode(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [decode(v) for v in value]
                return value
            row = decode(json.loads(line))
            state, world = row["state"], row["world"]
            empty_plane_arrays_restored += restore_release_geometry_shapes(world)
            counts["ticks"] += 1
            if previous is None:
                if state["physics_step"] != 0 or state["branch_id"] != 0:
                    issues.append("Execution did not begin at unrewound birth")
                task.bind({n: SimpleNamespace(links=[SimpleNamespace(idx=i) for i in b["link_indices"]])
                           for n, b in world["bodies"].items()})
                task.initialize(world)
                expected_home = np.asarray(scene.robot_control.home.arm[:7])
                if not np.allclose(row["robot"]["arm"]["joint_position_rad"], expected_home, atol=1e-10, rtol=0):
                    issues.append("Execution did not start at configured home")
            else:
                if (state["episode_id"] != previous["episode_id"] or state["branch_id"] != 0 or
                        state["parent_state_id"] != previous["state_id"] or
                        state["physics_step"] != previous["physics_step"]+1):
                    issues.append(f"Nonconsecutive tick {state['state_id']}")
                task.update(world, config.physics_dt_s)
            if row["task"]["result"] != to_jsonable(task.result):
                issues.append(f"Task reevaluation differs at tick {state['state_id']}")
            summary = world["contact_events"]
            if not (summary["geometry_roles_complete"] and summary["substeps_complete"]):
                counts["coverage_incomplete_ticks"] += 1
            for event in summary["events"]:
                roles = {event["role_a"], event["role_b"]}
                if event["touching"]:
                    counts["metal_touch_events"] += roles == {"wand_metal", "wire_metal"}
                    counts["robot_wire_touch_events"] += roles == {"robot", "wire_metal"}
            arm = row["robot"]["arm"]
            for name, field in (("actual", "joint_position_rad"), ("commanded", "joint_position_target_rad")):
                q = np.asarray(arm[field])
                margins[name] = min(margins[name], float(np.minimum(q-limits[:,0], limits[:,1]-q).min()))
            for hand, values in world["grasp"]["hands"].items():
                if values["binding"]:
                    event = values["binding"]["acquisition_evidence"]
                    acquisitions[f"{hand}:{event['physics_step']}"] = event
            previous = state
    if counts["ticks"] != report["physics_steps"]+1:
        issues.append("Tick count differs from report")
    if any(counts[name] for name in counts if name != "ticks"):
        issues.append("Forbidden contact or incomplete contact coverage")
    if margins["actual"] < -1e-5 or margins["commanded"] < -1e-8:
        issues.append("Joint limits exceeded")
    if to_jsonable(task.result) != report["task_result"]:
        issues.append("Final task result differs from report")
    if not task.result.task_success or world["assist_active"]:
        issues.append("Released Task success required")
    actions, completed = 0, 0
    expected_actions = (json.loads((folder/"prefix_actions.json").read_text()) if segmented else
                        json.loads((folder/"policy_actions.json").read_text())["actions"] if compiled else None)
    expected_prefix = report.get("compiled_prefix_steps",len(expected_actions) if compiled else 0)
    for line in (folder/"private/control_steps.jsonl").open():
        row = json.loads(line)
        actions += row.get("kind") == "requested"
        if row.get("kind") == "completed":
            if segmented and completed < expected_prefix and (
                    completed >= len(expected_actions) or row["info"]["executed_joint_targets"] != expected_actions[completed]):
                issues.append(f"Executed command differs from submitted prefix at action {completed}")
            if compiled and (not feedback_finish or completed < expected_prefix) and (
                    completed >= len(expected_actions) or row["info"]["executed_joint_targets"] != expected_actions[completed]):
                issues.append(f"Executed joint command differs from compiled input at action {completed}")
            completed += 1
    if (compiled or segmented) and completed != report["physics_steps"]:
        issues.append("Compiled execution does not have one completed ordinary action per tick")
    return dict(passed=not issues, issues=issues, variant=report["variant"], instance_id=task.instance_id,
        evidence_shape_restoration=dict(empty_convex_plane_arrays=empty_plane_arrays_restored,
            rule="Schema-v2 inline [] convex covers decode as float64 arrays of shape (0, 4); original evidence unchanged"),
        task_success=task.result.task_success, task_result=to_jsonable(task.result), counts=counts,
        action_requests=actions, arm_joint_limit_margin_rad=margins, grasp_acquisitions=acquisitions,
        ik_scope=(("Continuous physical execution of a compiled prefix and individually frozen observation-policy submissions"
                   if segmented else
                   "Fresh physical execution of a compiled prefix, followed by observation policies with checked online IK"
                   if feedback_finish else
                   "Fresh physical execution of compiled JOINT_ABS commands; IK was queried during development, not this replay"
                   if compiled else
                   "Frozen owner CheckedJointPolicy queries checked Genesis IK/FK, then sends JOINT_ABS actions"
                   if report["config"]["control_mode"] == "JOINT_ABS" else
                   "Frozen EE_ABS compile_action uses checked Genesis IK/FK")
                  + "; 1e-4 m / 1e-3 rad rejection thresholds; no independent IK residual replay"),
        artifact_sha256={name:digest(folder/name) for name in
            (("run_report.json", "run_source_manifest.json", "private/physics_states.jsonl", "private/control_steps.jsonl")
             + (("policy_actions.json",) if compiled else ("prefix_actions.json",) if segmented else ()))},
        array_sha256=array_hashes, audit_source_sha256=digest(Path(__file__)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    result = audit(args.run)
    (args.run/"independent_audit.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in {"array_sha256", "grasp_acquisitions", "task_result"}}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
