#!/usr/bin/env python3
"""Short real-Env tool smoke; no physical grasp or task-success qualification."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--rgb", action="store_true")
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()
    from topogym.planning.calibration_tools import open_session, open_grasp_sweep, parameter_grid
    from topogym.utils.io import write_json_atomic
    config = dict(task_id="cast_keyhole", variation_id="very_easy", robot_id="aloha",
                  compute_backend=args.backend, enable_rgb=args.rgb, seed=0)
    trial = dict(hand="right", target="keyhole_silver", record_video=args.rgb,
        phases=[dict(name="approach", action={}, steps=1),
                dict(name="close", action={"right": dict(gripper_position_m=.005)}, steps=1),
                dict(name="lift", action={}, steps=1),
                dict(name="hold", action={}, steps=3),
                dict(name="release", action={"right": dict(gripper_position_m=.027)}, steps=1)])
    if args.sweep:
        candidates = parameter_grid({"phase_actions.close.right.gripper_position_m": [.005, .007]})
        with open_grasp_sweep(config, trial, candidates, args.output) as sweep:
            result = sweep.wait()
            assert result["status"] == "completed", result
            assert len({c["result"]["initial_state"]["episode_id"] for c in result["cases"]}) == 2
            assert all(c["result"]["completed_controls"] == 7 for c in result["cases"])
    else:
        with open_session(config, args.output) as dev:
            before = dev.inspect()["source_state_ref"]
            status = dev.grasp_status("right")
            assert status["source_state_ref"] == before and status["physics_steps_advanced"] == 0
            dev.watch(["grasp_acquired", "grasp_lost", "grasp_rejected"], before_steps=1, after_steps=1)
            token = dev.run_grasp_trial(trial, request_id="smoke-once")
            result = dev.wait(token)
            assert result["status"] == "completed", result
            assert result["completed_controls"] == 7, result
            assert result["last_state"]["physics_step"]-result["initial_state"]["physics_step"] == 70
            assert dev.run_grasp_trial(trial, request_id="smoke-once") == token
            assert dev.grasp_trial_report(result["trial_id"])["completed_controls"] == 7
            dev.export_report()
    write_json_atomic(args.output / "acceptance.json", dict(status="passed", backend=args.backend,
        rgb=args.rgb, sweep=args.sweep, scope="real tool execution only; no grasp qualification", result=result))
    print(json.dumps(dict(status="passed", report=str(args.output / "acceptance.json"))))


if __name__ == "__main__": main()
