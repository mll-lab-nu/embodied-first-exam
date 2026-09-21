"""Audit a complete gravity execution and optional half-timestep replication."""
import argparse
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from .gravity_demo import sha
from .independent_motion import IndependentWitness


def verify_run(folder):
    folder = Path(folder).resolve()
    result = json.loads((folder/"result.json").read_text())
    cfg = OmegaConf.load(folder/"config.yaml")
    trace = folder/"physical_states.jsonl"
    checks = dict(complete=result["complete"] and result["task_success"] and result["failure"] is None,
        original_start=result.get("checkpoint_start") is False,
        gravity=result["gravity_m_s2"] == [0, 0, -9.81] and list(cfg.env.sim.gravity) == [0, 0, -9.81],
        no_pose_replay=result["pose_writes_after_reset"] is False,
        free_initial_ring=result["ring_initial_assistance"] is False,
        free_chains=result["chain_assistance"] is False,
        states_hash=sha(trace) == result["physical_states_sha256"],
        seed_hash=sha(folder/"source_motion.json") == result["source_motion_sha256"],
        template_hash=sha(folder/"input_template.json") == result["template_sha256"],
        penetration=result["maximum_puzzle_penetration_m"] <= .001,
        robot_self_penetration=result["maximum_robot_self_penetration_m"] <= .001,
        robot_table_penetration=result.get("maximum_robot_table_penetration_m", float("inf")) <= .001)
    frames = [json.loads(line) for line in trace.read_text().splitlines()]
    checks["complete_observations"] = len(frames) == result["physical_frame_count"] and [f["frame"] for f in frames] == list(range(len(frames)))
    checks["physical_clock"] = all(np.isclose(f["time_s"], f["step"]*result["dt"]) for f in frames)
    checks["observation_cadence"] = bool(np.allclose(np.diff([f["time_s"] for f in frames]), 1/result["physical_frame_fps"]))
    checks["chain_connections"] = all(all(abs(v) == 1 for v in f["chain_link_numbers"]) for f in frames)
    chain_ids = {index for name, index in result["body_link_indices"].items() if name.startswith("chain_")}
    checks["no_chain_welds"] = all(not any(chain_ids.intersection(pair) for pair in f["active_welds"]) for f in frames)
    seed = json.loads((folder/"source_motion.json").read_text())["frames"][0]
    checks["initial_joints"] = bool(np.allclose(frames[0]["qpos"], seed["qpos"], atol=1e-9, rtol=0))
    checks["initial_puzzle"] = all(np.allclose(frames[0]["bodies"][name]["pos"],
        np.asarray(cfg.env.robot_mount.pos)+pose["pos"], atol=1e-9, rtol=0) and np.allclose(
        frames[0]["bodies"][name]["quat_wxyz"], np.asarray(pose["quat"])[[3, 0, 1, 2]], atol=1e-9, rtol=0)
        for name, pose in seed["bodies"].items())
    initial = frames[0]["bodies"]["target_ring"]["pos"][2]
    drop = initial-min(f["bodies"]["target_ring"]["pos"][2] for f in frames if f["time_s"] <= .8)
    checks["initial_gravity_drop"] = drop > .03

    previous, contact_gates = set(), 0
    checks["contact_gated_new_grasps"] = True
    for event in result["events"]:
        if "pairs" not in event:
            continue
        pairs = {tuple(pair) for pair in event["pairs"]}
        added = pairs-previous
        if event["time_s"] > 0:
            for side in {side for side, _ in added}:
                proof = event.get("contact_evidence", {}).get(side, {})
                bodies = {body for arm, body in pairs if arm == side}
                first, last = (f"robot/{side}/{finger}_finger_link" for finger in ("left", "right"))
                nodes = bodies | {first, last}
                graph = {node: set() for node in nodes}
                for edge in proof.get("edges", []):
                    if edge["force_N"] > .01 and edge["a"] in nodes and edge["b"] in nodes:
                        graph[edge["a"]].add(edge["b"])
                        graph[edge["b"]].add(edge["a"])
                supported = set()
                stack = [(first, [first])]
                while stack:
                    node, path = stack.pop()
                    if node == last:
                        supported.update(path)
                    else:
                        stack.extend((peer, path+[peer]) for peer in graph[node]-set(path))
                checks["contact_gated_new_grasps"] &= supported == nodes and set(proof.get("bodies", [])) == bodies
                contact_gates += 1
        previous = pairs
    checks["both_handover_gates"] = contact_gates >= 2
    ring_id = result["body_link_indices"]["target_ring"]
    final = frames[-1]
    checks["ring_released"] = not any(ring_id in pair for pair in final["active_welds"])
    checks["ring_table_contact"] = final["ring_contact_bodies"] == ["table"]
    tail = [f for f in frames if f["time_s"] >= final["time_s"]-1.]
    checks["free_settled_last_second"] = all(not any(ring_id in pair for pair in f["active_welds"])
        and np.linalg.norm(f["bodies"]["target_ring"]["velocity"]) < .01
        and np.linalg.norm(f["bodies"]["target_ring"]["angular_velocity"]) < .2 for f in tail)
    frame = {name: dict(pos=(np.asarray(pose["pos"])-cfg.env.robot_mount.pos).tolist(),
        quat=np.asarray(pose["quat_wxyz"])[[1, 2, 3, 0]].tolist()) for name, pose in final["bodies"].items()}
    goal = IndependentWitness(json.loads((folder/"input_template.json").read_text()), float(cfg.task.scale)).goal(frame)
    checks["independent_final_separation"] = goal["separation_m"] > .02
    return dict(passed=bool(all(checks.values())), checks={key: bool(value) for key, value in checks.items()},
        classification="gravity_and_contact_execution_with_declared_grasp_assistance",
        initial_pickup_verified=False, pure_friction_grasp_verified=False,
        source=str(folder), source_result_sha256=sha(folder/"result.json"), source_states_sha256=sha(trace),
        dt=result["dt"], physics_steps=result["physics_steps"], simulated_seconds=result["simulated_seconds"],
        maximum_puzzle_penetration_m=result["maximum_puzzle_penetration_m"],
        initial_ring_drop_m=drop, contact_gates=contact_gates, final_goal=goal,
        final_ring_height_m=final["bodies"]["target_ring"]["pos"][2])


def compare_runs(baseline, half_step):
    """Compare complete executions with identical inputs/code and half the dt.

    The controller replans from measured states at each timestep. This checks
    successful task execution, not convergence of one fixed joint trajectory.
    """
    baseline, half_step = Path(baseline).resolve(), Path(half_step).resolve()
    first, second = verify_run(baseline), verify_run(half_step)

    def parameters(folder):
        cfg = OmegaConf.to_container(OmegaConf.load(folder/"config.yaml"), resolve=True)
        cfg["env"]["sim"].pop("dt")
        cfg["task"].pop("template_path")
        cfg["run"].pop("output", None)
        return cfg

    sources = ("execution_source.py", "physical_demo.py", "physical_plan.py",
               "physical_extraction.py", "physical_place.py", "scene.py",
               "robot_motion.py", "robot_clearance.py")
    source_hashes = {label: {name: sha(folder/name) for name in sources}
                     for label, folder in (("baseline", baseline), ("half_step", half_step))}

    def geometry_hashes(folder):
        assets = folder/"assets"
        return {str(p.relative_to(assets)): sha(p) for p in assets.rglob("*")
                if p.suffix in (".urdf", ".obj", ".stl", ".ply", ".dae", ".glb")}

    first_geometry, second_geometry = geometry_hashes(baseline), geometry_hashes(half_step)
    height_delta = abs(first["final_ring_height_m"]-second["final_ring_height_m"])
    checks = dict(baseline_complete=first["passed"], half_step_complete=second["passed"],
        timestep_halved=bool(np.isclose(second["dt"]*2, first["dt"], atol=1e-12, rtol=0)),
        same_configuration_except_dt_and_paths=parameters(baseline) == parameters(half_step),
        same_template=sha(baseline/"input_template.json") == sha(half_step/"input_template.json"),
        same_initial_seed=sha(baseline/"source_motion.json") == sha(half_step/"source_motion.json"),
        same_built_geometry=bool(first_geometry) and first_geometry == second_geometry,
        same_execution_sources=source_hashes["baseline"] == source_hashes["half_step"],
        final_ring_height_agreement=height_delta < .0005)
    return dict(passed=bool(all(checks.values())), checks=checks, baseline=first, half_step=second,
        final_ring_height_difference_m=height_delta, execution_source_hashes=source_hashes,
        comparison="Independent complete replanning at each timestep with matching code, geometry and control parameters",
        fixed_trajectory_convergence_verified=False, pure_friction_grasp_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--half-step", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare_runs(args.source, args.half_step) if args.half_step else verify_run(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2), flush=True)
    if not result["passed"]:
        raise SystemExit("Physical execution evidence failed qualification")


if __name__ == "__main__":
    main()
