#!/usr/bin/env python3
"""Reevaluate Coil success and exact box gaps from a frozen run's tick evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def replay_current_policy(folder):
    """Check current policy outputs against an already successful execution.

    This is a read-only action equivalence check, not another physical run.
    The ordinary audit separately validates the frozen execution and success.
    """
    folder = Path(folder).resolve()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from topogym.planning.cast_coil.policy import CastCoilPolicy, variant_reference
    report = json.loads((folder/"run_report.json").read_text())
    if report.get("status") != "passed" or not report.get("task_success"):
        raise ValueError("Action equivalence requires a successful physical run")
    assembly, _ = variant_reference(report["variant"])
    policy = CastCoilPolicy(body_origins={b.name: b.visual.center_mass for b in assembly.bodies},
                           variant=report["variant"])
    config = report["config"]
    policy.initialize(dict(action_spec=dict(robot_id="aloha", mode="EE_ABS"),
                           timing_spec=dict(control_dt_s=config["physics_dt_s"]*config["control_decimation"])))
    requests = {}
    for line in (folder/"private/control_steps.jsonl").open():
        row = json.loads(line)
        if row.get("kind") == "requested":
            key = row["state_ref"]["state_id"]
            if key in requests:
                raise ValueError("Multiple actions from one state are not supported")
            requests[key] = row["action"]
    checked, mismatches = 0, []
    for line in (folder/"private/physics_states.jsonl").open():
        row = json.loads(line)
        key = row["state"]["state_id"]
        if key not in requests:
            continue
        # These fields are small numeric arrays, stored inline by the runner;
        # the policy does not consume the large geometry/contact array chunks.
        actual = policy.act(dict(state=row["state"], robot=row["robot"], privileged=dict(world=row["world"])))
        if actual != requests[key]:
            mismatches.append(key)
        checked += 1
    sources = ("topogym/planning/cast_coil/policy.py", "topogym/planning/cast_coil/baseline.py",
               "topogym/planning/cast_coil/__init__.py", "scripts/audit_cast_coil_policy.py")
    return dict(passed=checked == len(requests) and not mismatches, checked_actions=checked,
        expected_actions=len(requests), mismatch_state_ids=mismatches,
        scope="Current policy exactly reproduces recorded actions on recorded observations; not a new physics execution",
        current_source_sha256={name: digest(root/name) for name in sources},
        evidence_sha256={name: digest(folder/name) for name in ("run_report.json", "private/physics_states.jsonl", "private/control_steps.jsonl")})


def audit(folder):
    folder = Path(folder).resolve()
    source = folder/"source_snapshot"
    manifest = json.loads((folder/"run_source_manifest.json").read_text())
    mismatches = [name for name, expected in manifest.items()
                  if not (source/name).is_file() or digest(source/name) != expected]
    if mismatches:
        raise ValueError(f"Frozen source identity mismatch: {mismatches[:5]}")
    sys.path.insert(0, str(source))
    import numpy as np
    from scipy.spatial.transform import Rotation
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.planning.cast_coil.policy import variant_reference
    from topogym.simulator import SimulatorConfig
    from topogym.solvers.collision.box_compounds import BoxCompoundCollision
    from topogym.utils.io import to_jsonable

    report = json.loads((folder/"run_report.json").read_text())
    config = SimulatorConfig(**report["config"])
    if config.task_id != "cast_coil" or report["status"] == "running":
        raise ValueError("Expected a completed Coil attempt")
    scene = load_scene_config(config)
    task = task_definition("cast_coil", config.variation_id)(config.task_parameters, seed=report["seed"])
    assembly, _ = variant_reference(report["variant"])
    collision = BoxCompoundCollision(*(b.boxes for b in assembly.bodies))
    issues, acquisitions = [], {}
    previous, count, min_gap, min_gap_time = None, 0, float("inf"), None
    joint_margins = dict(actual=float("inf"), commanded=float("inf"))
    limits = np.asarray(scene.robot_control.robot.arm_joint_limits)
    evidence = folder/"private/physics_states.jsonl"
    array_hashes = {}
    with tempfile.TemporaryDirectory(prefix="coil_audit_") as temporary:
        table = scene.env.world.table
        spec = task.declare(Path(temporary), table.pos[2]+table.size[2]/2)
        task.finalize_spec(spec, asset_dir=Path(temporary), scene_config=scene)
        if task.instance_id != report["instance_id"]:
            issues.append("Regenerated task instance differs")
        for line in evidence.open():
            chunks = {}
            def decode(value):
                if isinstance(value, dict):
                    if "array_file" in value and "key" in value:
                        name = value["array_file"]
                        path = (folder/"private"/name).resolve()
                        if not path.is_relative_to(folder/"private/arrays"):
                            raise ValueError("Array reference escapes evidence directory")
                        if name not in chunks:
                            array_hashes[name] = digest(path)
                            with np.load(path, allow_pickle=False) as archive:
                                chunks[name] = {k: archive[k] for k in archive.files}
                        result = chunks[name][value["key"]]
                        if list(result.shape) != value["shape"] or str(result.dtype) != value["dtype"]:
                            raise ValueError("Array layout differs from evidence reference")
                        return result
                    return {k: decode(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [decode(v) for v in value]
                return value
            row = decode(json.loads(line))
            state, world = row["state"], row["world"]
            count += 1
            if previous is None:
                task.bind({n: SimpleNamespace(links=[SimpleNamespace(idx=i) for i in b["link_indices"]])
                           for n, b in world["bodies"].items()})
                task.initialize(world)
            else:
                if (state["episode_id"] != previous["episode_id"] or state["branch_id"] != 0 or
                        state["parent_state_id"] != previous["state_id"] or
                        state["physics_step"] != previous["physics_step"]+1):
                    issues.append(f"Nonconsecutive tick {state['state_id']}")
                task.update(world, config.physics_dt_s)
            if row["task"]["result"] != to_jsonable(task.result):
                issues.append(f"Task reevaluation differs at tick {state['state_id']}")
            for arm in row["robot"].values():
                for label, field in (("actual", "joint_position_rad"), ("commanded", "joint_position_target_rad")):
                    q = np.asarray(arm[field])
                    joint_margins[label] = min(joint_margins[label], float(np.min(q-limits[:, 0])),
                                               float(np.min(limits[:, 1]-q)))
            poses = {}
            for name in ("coil_gold", "coil_silver"):
                body = world["bodies"][name]
                turn = Rotation.from_quat(np.asarray(body["quaternion_wxyz"])[[1, 2, 3, 0]])
                poses[name] = (np.asarray(body["position_m"])-turn.apply(task.body_origins[name]), turn)
            gp, gr = poses["coil_gold"]
            sp, sr = poses["coil_silver"]
            gap = collision.gap((gr.inv()*sr).as_matrix(), gr.inv().apply(sp-gp))
            if gap < min_gap:
                min_gap, min_gap_time = gap, state["sim_time_s"]
            for side, hand in world["grasp"]["hands"].items():
                binding = hand["binding"]
                if binding:
                    event = binding["acquisition_evidence"]
                    acquisitions[f"{side}:{event['physics_step']}"] = event
            previous = state
    if count != report.get("physics_steps", -2)+1:
        issues.append("Tick count does not match run report")
    if joint_margins["actual"] < -1e-5 or joint_margins["commanded"] < -1e-8:
        issues.append("Arm joints exceeded model limits")
    if to_jsonable(task.result) != report.get("task_result"):
        issues.append("Final result differs from run report")
    if not task.result.task_success or world["assist_active"]:
        issues.append("Task success and final assist release required")
    actions, pose_actions = 0, 0
    for line in (folder/"private/control_steps.jsonl").open():
        row = json.loads(line)
        if row.get("kind") == "requested":
            actions += 1
            pose_actions += sum("position_world_m" in command for command in row["action"].values())
    sources = ("run_report.json", "run_source_manifest.json", "private/physics_states.jsonl", "private/control_steps.jsonl")
    return dict(passed=not issues, issues=issues, variant=report["variant"], instance_id=task.instance_id,
        config=report["config"], task_success=task.result.task_success, task_result=to_jsonable(task.result),
        tick_records=count, action_requests=actions, checked_ee_pose_requests=pose_actions,
        ik_scope="EE_ABS requests use frozen compile_action / Genesis solve_checked; residual thresholds 1e-4 m, 1e-3 rad",
        arm_joint_limit_margin_rad=joint_margins, grasp_acquisitions=acquisitions,
        minimum_sampled_box_gap_m=min_gap, minimum_gap_time_s=min_gap_time,
        gap_scope="Exact authored collision box unions at every saved tick; not continuous-time or solver-substep coverage",
        artifact_sha256={name: digest(folder/name) for name in sources}, array_sha256=array_hashes,
        audit_source_sha256=digest(Path(__file__)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--replay-current-policy", action="store_true")
    args = parser.parse_args()
    if args.replay_current_policy:
        result = replay_current_policy(args.run)
        (args.run/"current_policy_replay.json").write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["passed"] else 1)
    result = audit(args.run)
    (args.run/"audit.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"array_sha256", "artifact_sha256", "grasp_acquisitions"}}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
