#!/usr/bin/env python3
"""Native strand/sheath contact probes for simplified Fiber scenes.

Owner intervention translates the robot to shallow contact. This checks the
failure mechanism and rewind, and is explicitly not a solving demonstration.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("very_easy", "easier"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import numpy as np
    import torch
    from topogym.simulator import Env, SimulatorConfig
    from topogym.utils.arrays import to_numpy
    from topogym.utils.io import to_jsonable, write_json_atomic
    torch.set_num_threads(1)
    args.output.mkdir(parents=True, exist_ok=False)
    config = SimulatorConfig(task_id="fiber_bundling", variation_id=args.variant,
        compute_backend="cpu", enable_rgb=False, enable_privileged=True,
        history_storage="memory", rigid_options={"use_contact_island": False}, work_dir=args.output / "scene")
    report = dict(scope=__doc__, status="running", config=to_jsonable(config), probes=[])
    write_json_atomic(args.output / "report.json", report)
    try:
        with Env(config) as env:
            env.reset(seed=0)
            report.update(instance_id=env._task.instance_id, asset_sha256=dict(env._asset_build.sha256))
            birth = env.state_history[0].ref
            initial = to_jsonable(env._task.get_state())
            initial_events = deepcopy(env._world.read_state()["contact_events"])
            for role in ("fiber_strand", "fiber_sheath"):
                robot = env._world.entities["robot"]
                monitor = env._world._contact_collector
                finger = next(g for link in robot.links if link.name == "left_finger" for g in link.geoms)
                name = "fiber_00_08" if role == "fiber_strand" else "trunk_03"
                target = next(g for link in env._world.entities["fiber_bundle"].links if link.name == name
                              for g in link.geoms if g.type.name == ("CAPSULE" if role == "fiber_strand" else "CYLINDER"))
                assert monitor.roles[target.idx] == role
                delta = to_numpy(target.get_pos(relative=False)) - to_numpy(finger.get_pos(relative=False))
                aligned = to_numpy(robot.get_pos(relative=False)) + delta

                def contact_pose(height):
                    robot.set_pos(aligned + np.array([0., 0., height]), zero_velocity=True, relative=False)
                    monitor.birth()
                    return env._world.read_state()["contact_events"]

                def hits(summary):
                    return [event for event in summary["events"] if any(
                        event[f"role_{a}"] == role and event[f"role_{b}"] == "robot"
                        and event[f"robot_part_{b}"] == "gripper" for a, b in (("a", "b"), ("b", "a")))]

                clear = .3
                assert not hits(contact_pose(clear))
                for height in np.linspace(.29, 0., 30):
                    if hits(contact_pose(float(height))):
                        touching = float(height)
                        break
                    clear = float(height)
                else:
                    raise AssertionError("No native shallow contact found")
                for _ in range(18):
                    height = (clear + touching) / 2
                    if hits(contact_pose(height)):
                        touching = height
                    else:
                        clear = height
                summary = contact_pose(touching - .00005)
                assert hits(summary)
                maximum_depth = max((event["penetration_m"] for event in summary["events"]), default=0.)
                assert maximum_depth <= .001
                _, reason, _, _ = env._task.evaluate_transition(env._world.read_state(), env._task.task_state)
                assert reason == ("fiber_gripper_contact" if role == "fiber_strand" else None)
                _, reward, done, truncated, info = env.interaction().step({})
                sampled = env._world.read_state()["contact_events"]
                assert sampled["substeps_complete"] and sampled["sampled_substeps"] == config.solver_substeps
                assert not truncated and done == (role == "fiber_strand")
                if role == "fiber_strand":
                    assert reward == 0 and info["failure_code"] == "task_failed"
                    assert env._task.result.reason == "fiber_gripper_contact"
                probe = dict(role=role, maximum_initial_penetration_m=maximum_depth,
                    intervention_robot_translation_m=(delta + [0., 0., touching - .00005]).tolist(),
                    native_contacts=to_jsonable(summary), feedback=to_jsonable(info),
                    result=to_jsonable(env._task.result))
                env.privileged.rewind_to(birth)
                assert to_jsonable(env._task.get_state()) == initial
                assert env._world.read_state()["contact_events"] == initial_events
                probe["birth_restored"] = True
                report["probes"].append(probe)
                write_json_atomic(args.output / "report.json", report)
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        write_json_atomic(args.output / "report.json", report)


if __name__ == "__main__":
    main()
