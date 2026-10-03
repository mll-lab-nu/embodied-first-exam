#!/usr/bin/env python3
"""Explicit real-physics acceptance. Run from a frozen source tree; never claims oracle success."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def ordinary_worker(pipe, cancel, config, output, session_id, kind):
    """Regression peer: construct the ordinary Env without a sensor adapter."""
    import os
    import traceback
    if os.name == "posix":
        os.setsid()
    with (Path(output) / "worker.log").open("a", buffering=1) as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        try:
            import torch
            torch.set_num_threads(1)
            from topogym.simulator import Env, SimulatorConfig, SegmentRunner
            from topogym.planning.calibration_tools.contracts import json_value
            from topogym.planning.calibration_tools.evidence import Evidence
            evidence = Evidence(output, session_id)
            with Env(SimulatorConfig(**dict(config, enable_privileged=True, work_dir=str(Path(output) / "scene")))) as env:
                env.reset(seed=config["seed"])
                evidence.event("ordinary_episode_started", metadata=env.episode_metadata)
                with SegmentRunner(env, Path(output) / "ordinary_execution") as runner:
                    pipe.send(dict(kind="ready", progress=dict(stage="idle", physics_step=0)))
                    while True:
                        request = pipe.recv()
                        if request["method"] == "close":
                            break
                        if request["method"] == "inspect":
                            result = dict(state_ref=env._info()["state_ref"],
                                rgb_cameras=list(env.observe()["rgb"]), sensor_class=type(env._sensors).__name__)
                        else:
                            result = runner.interaction(privileged=True).run_segment(
                                request_id=request["operation_id"], actions=[{}, {}, {}])
                        pipe.send(dict(kind="result", operation_id=request["operation_id"], result=json_value(result)))
            evidence.report(status="ordinary_default_regression")
            evidence.close()
            pipe.send(dict(kind="result", operation_id=request["operation_id"], result=dict(closed=True)))
        except BaseException as error:
            traceback.print_exc()
            pipe.send(dict(kind="startup_error", error=dict(type=type(error).__name__, message=str(error))))
        finally:
            pipe.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variation", default="very_easy")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--rgb", action="store_true")
    parser.add_argument("--ordinary", action="store_true", help="Regress default Env sensors and shared recording, without development adapter")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import numpy as np
    from topogym.planning.calibration_tools import open_session
    from topogym.planning.calibration_tools.contracts import CalibrationError
    from topogym.utils.io import write_json_atomic
    checks, artifacts = [], {}
    config = dict(task_id="cast_keyhole", variation_id=args.variation, compute_backend=args.backend,
                  enable_rgb=args.rgb, seed=0)
    started = time.monotonic()
    if args.ordinary:
        from topogym.planning.calibration_tools.supervisor import Supervisor
        supervisor = Supervisor(config, args.output, worker_target=ordinary_worker)
        try:
            observation = supervisor.call("inspect")
            assert observation["sensor_class"] == "SensorSuite", observation
            if args.rgb:
                assert len(observation["rgb_cameras"]) == 4, observation
            result = supervisor.call("step")
            assert result["control_steps"] == 3 and result["physics_steps"] == 30, result
            assert result["evidence_complete"] and result["reason"] == "segment_complete", result
            write_json_atomic(args.output / "acceptance.json", dict(status="passed", ordinary_sensors=True,
                observation=observation, result=result, full_oracle_success=False, elapsed_s=time.monotonic()-started))
            print(json.dumps(dict(status="passed", ordinary=True, report=str(args.output / "acceptance.json"))))
        finally:
            supervisor.close()
        return
    with open_session(config, args.output, kind="physics") as dev:
        try:
            initial = dev.inspect()
            checkpoint = dev.checkpoint("initial")
            initial_ref = initial["source_state_ref"]
            dev.contacts()
            targets = {side: dict(position_m=row["tcp_position_world_m"], quaternion_wxyz=row["tcp_orientation_wxyz"])
                       for side, row in initial["robot"].items()}
            ik = dev.solve_ik(targets)
            assert any(c["accepted"] for c in ik["candidates"]), ik
            candidate = next(c for c in ik["candidates"] if c["accepted"])
            audit = dev.check_robot_path([candidate["qpos"]], include_tcp=True)
            artifacts.update(ik=ik, collision_audit=audit)
            assert audit["passed"], audit
            for side, measured in initial["robot"].items():
                np.testing.assert_allclose(audit["tcp_path"][0][side]["position_m"],
                                           measured["tcp_position_world_m"], atol=1e-4, rtol=0)
            assert dev.inspect()["source_state_ref"] == initial_ref
            checks.append("inspect/contacts/IK/FK do not advance physics")
            probe = dev.sync_probe()
            silver = probe["bodies"]["keyhole_silver"]
            p = {key: silver[key] for key in ("position_m", "quaternion_wxyz")}
            p["position_m"][0] += .1
            dev.set_object_pose("keyhole_silver", p)
            np.testing.assert_allclose(dev.inspect()["world"]["bodies"]["keyhole_silver"]["position_m"],
                                       initial["world"]["bodies"]["keyhole_silver"]["position_m"])
            checks.append("probe edits leave physical bodies unchanged")
            if args.rgb:
                artifacts["initial_frame"] = dev.capture_frame("cam_high", record_video=True)
                assert artifacts["initial_frame"]["state_ref"] == initial_ref
                dev.watch(["always"], before_steps=1, after_steps=0, camera="cam_high")
            else:
                dev.watch(["contact_changed"], before_steps=1, after_steps=1)
            receipts = []
            for i in range(3):
                row = dev.step({}, request_id=f"step-{i}")
                assert row["control_steps"] == 1 and row["physics_steps"] == 10, row
                assert row == dev.step({}, request_id=f"step-{i}")
                receipts.append(row)
            assert dev.inspect()["info"]["physics_step"] == 30
            checks.append("three real control steps / 30 physics ticks, duplicate requests do not execute")
            artifacts["receipts"] = receipts
            future = dev.checkpoint("future")
            dev.restore(checkpoint)
            try:
                dev.restore(future)
            except CalibrationError:
                pass
            else:
                raise AssertionError("Future checkpoint remained usable")
            restored = dev.inspect()
            assert restored["info"]["physics_step"] == 0
            assert restored["info"]["branch_id"] > 0
            for name, body in initial["world"]["bodies"].items():
                np.testing.assert_allclose(restored["world"]["bodies"][name]["position_m"], body["position_m"], atol=1e-7)
            if args.rgb:
                artifacts["restored_frame"] = dev.capture_frame("cam_high", near="keyhole_silver", overlays=["contacts"])
                assert artifacts["restored_frame"]["branch_id"] == restored["info"]["branch_id"]
                assert dev.inspect()["info"]["physics_step"] == 0
                checks.append("Nyx raw/diagnostic frames carry actual restored branch; no implicit step")
            checks.append("physical checkpoint restore and stale future rejection")
            policy_path = args.output / "stateful_fixture.py"
            policy_path.write_text('''class Policy:
    def __init__(self): self.count = 0
    def initialize(self, context): self.count = 0
    def act(self, observation):
        self.count += 1
        if self.count > 3: raise ValueError("policy state was not restored")
        return {}
    def save_debug_state(self): return {"count": self.count}
    def load_debug_state(self, state): self.count = state["count"]
def make_policy(): return Policy()
''')
            policy = dict(path=str(policy_path.resolve()))
            result = dev.wait(dev.run_policy(policy, max_control_steps=2))
            assert result["development_stop_reason"] == "control_step_limit", result
            assert result["result"]["control_steps"] == 2, result
            stage = dev.checkpoint("policy_stage")
            result = dev.wait(dev.run_policy(policy, max_control_steps=1))
            assert result["result"]["control_steps"] == 1, result
            dev.restore(stage)
            result = dev.wait(dev.run_policy(policy, max_control_steps=1))
            assert result["result"]["control_steps"] == 1, result
            assert result["result"]["reason"] == "cancelled", result
            checks.append("bounded SegmentRunner policy and world+policy checkpoint restore")
            report = dict(status="passed", checks=checks, artifacts=artifacts, config=config,
                          elapsed_s=time.monotonic()-started, full_oracle_success=False,
                          video_scope="initial keyframe only; numerical traces cover subsequent physics")
            write_json_atomic(args.output / "acceptance.json", report)
            print(json.dumps(dict(status="passed", checks=len(checks), report=str(args.output / "acceptance.json"))))
        except BaseException as error:
            write_json_atomic(args.output / "acceptance.json", dict(status="failed", checks=checks,
                error=f"{type(error).__name__}: {error}", artifacts=artifacts, full_oracle_success=False))
            raise


if __name__ == "__main__":
    main()
