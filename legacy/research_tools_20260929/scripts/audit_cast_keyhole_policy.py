#!/usr/bin/env python3
"""Independently reevaluate one frozen Cast Keyhole run's numerical evidence.

No simulator is created and no physical state is changed. Raw placement
evidence and qualified Task success remain separate report fields.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            value.update(chunk)
    return value.hexdigest()


def audit(folder):
    folder = Path(folder).resolve()
    source = folder/"source_snapshot"
    manifest = json.loads((folder/"run_source_manifest.json").read_text())
    mismatches = [name for name, expected in manifest.items()
                  if not (source/name).is_file() or digest(source/name) != expected]
    if mismatches:
        raise ValueError("Frozen source identity mismatch: "+str(mismatches[:5]))
    sys.path.insert(0, str(source))
    import numpy as np
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator import SimulatorConfig
    from topogym.utils.io import to_jsonable

    report = json.loads((folder/"run_report.json").read_text())
    config = SimulatorConfig(**report["config"])
    if config.task_id != "cast_keyhole":
        raise ValueError("This audit only covers Cast Keyhole")
    scene = load_scene_config(config)
    table = scene.env.world.table
    height = table.pos[2]+table.size[2]/2
    task = task_definition(config.task_id, config.variation_id)(config.task_parameters, seed=report["seed"])
    evidence = folder/"private/physics_states.jsonl"
    issues, gaps, events, episodes = [], [], {}, set()
    maximum_penetration, max_stable, first_raw_goal, first_success = 0., 0., None, None
    joint_limits = np.asarray(scene.robot_control.robot.arm_joint_limits)
    joint_margins = dict(actual=float("inf"), commanded=float("inf"))
    previous, rows = None, 0
    with tempfile.TemporaryDirectory(prefix="keyhole_evidence_audit_") as temporary:
        spec = task.declare(Path(temporary), height)
        task.finalize_spec(spec, asset_dir=Path(temporary), scene_config=scene)
        if task.instance_id != report["instance_id"]:
            issues.append("Regenerated task instance differs from the recorded instance")
        if task.terminal_metadata() != report["terminal"]:
            # JSON converts tuple metadata to lists.
            if to_jsonable(task.terminal_metadata()) != report["terminal"]:
                issues.append("Regenerated terminal metadata differs from the recorded rule")
        with evidence.open() as stream:
            for line in stream:
                row = json.loads(line)
                state, world = row["state"], row["world"]
                episodes.add(state["episode_id"])
                rows += 1
                for arm in row["robot"].values():
                    for label, field in (("actual", "joint_position_rad"),
                                         ("commanded", "joint_position_target_rad")):
                        joints = np.asarray(arm[field])
                        joint_margins[label] = min(joint_margins[label], float(min(
                            np.min(joints-joint_limits[:, 0]), np.min(joint_limits[:, 1]-joints))))
                if state["branch_id"] != 0:
                    issues.append("Run includes a rewind branch")
                if previous is None:
                    task._task_link_indices = {i for name in task.local_vertices
                                               for i in world["bodies"][name]["link_indices"]}
                    task.initialize(world)
                else:
                    if (state["parent_state_id"] != previous["state_id"] or
                            state["physics_step"] != previous["physics_step"]+1):
                        issues.append("Numerical evidence is not one consecutive physical path")
                    task.update(world, config.physics_dt_s)
                saved, recomputed = row["task"]["result"], to_jsonable(task.result)
                if saved != recomputed:
                    issues.append(f"Task reevaluation mismatch at state {state['state_id']}")
                if task.result.reason and not task.result.task_success:
                    issues.append(f"Physical failure at state {state['state_id']}: {task.result.reason}")
                contacts = world.get("contacts", {})
                for a, b, depth in zip(contacts.get("link_a", ()), contacts.get("link_b", ()),
                                       contacts.get("penetration", ()), strict=True):
                    if a in task._task_link_indices or b in task._task_link_indices:
                        maximum_penetration = max(maximum_penetration, depth)
                stable = task.result.metrics.get("stable_time_s", 0.)
                max_stable = max(max_stable, stable)
                if stable+1e-12 >= float(task.config["stable_duration_s"]) and first_raw_goal is None:
                    first_raw_goal = state
                if task.result.task_success and first_success is None:
                    first_success = state
                for side, hand in world.get("grasp", {}).get("hands", {}).items():
                    binding = hand.get("binding")
                    if binding:
                        acquisition = binding["acquisition_evidence"]
                        events[(side, acquisition["physics_step"])] = acquisition
                previous = state
    if len(episodes) != 1 or not rows:
        issues.append("Expected one nonempty episode")
    if joint_margins["actual"] < -1e-5 or joint_margins["commanded"] < -1e-8:
        issues.append("Observed or commanded arm joints exceeded model limits")
    if previous and previous["physics_step"] != report.get("physics_steps"):
        issues.append("Final report and numerical evidence end at different ticks")
    if not report.get("from_default_home"):
        issues.append("Run does not declare the required default-home start")
    home_errors = {}
    for side, initial in report["initial_robot"].items():
        home = np.asarray(scene.robot_control.home[side])
        actual = np.r_[initial["joint_position_rad"], initial["finger_position_m"]]
        home_errors[side] = float(np.max(np.abs(actual-home)))
        if home_errors[side] > 1e-8:
            issues.append(f"Initial {side} joints differ from configured home")
    acquisitions = [dict(hand=side, **event) for (side, _), event in sorted(events.items())]
    bilateral = all(len({r["link_a"] for r in event["rows"]}) >= 2 for event in acquisitions)
    if not bilateral:
        issues.append("Acquisition is missing bilateral contact evidence")
    if len(acquisitions) < 4:
        gaps.append("Pickup and both regrasps were not all completed")
    if first_raw_goal is None:
        gaps.append("No complete stable placement window")
    if first_success is None:
        gaps.append("No actual Task success")
    issues = list(dict.fromkeys(issues))
    return dict(schema_version=1, scope="independent frozen-source numerical reevaluation; no new physics",
                run=str(folder), run_status=report["status"], source_manifest_sha256=digest(folder/"run_source_manifest.json"),
                evidence_sha256=digest(evidence), source_files_verified=len(manifest), states=rows,
                instance_id=task.instance_id, terminal=to_jsonable(task.terminal_metadata()),
                assistance=report["assistance"], timing_scope=report["timing_scope"],
                initial_home_max_error=home_errors, maximum_task_contact_penetration_m=maximum_penetration,
                minimum_joint_margin_rad={k: v if np.isfinite(v) else None for k, v in joint_margins.items()},
                acquisitions=acquisitions, max_raw_goal_stable_time_s=max_stable,
                first_raw_goal_window=first_raw_goal, first_task_success=first_success,
                evidence_consistent=not issues, issues=issues, qualification_gaps=gaps,
                passed=not issues and not gaps and report["status"] == "passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(destination)
    result = audit(args.run)
    result["auditor_sha256"] = digest(Path(__file__))
    destination.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k: result[k] for k in ("passed", "evidence_consistent", "states",
        "max_raw_goal_stable_time_s", "maximum_task_contact_penetration_m", "issues")}, indent=2))


if __name__ == "__main__":
    main()
