#!/usr/bin/env python3
"""Run the imported Slotted Post Ring candidate under the local v15 Session rules.

The local flat-disc pickup is not implemented by the imported upright-disc
route. Full execution refuses that mismatch; --stop-after bead_to_slot exposes
the unverified prefix. No physics or geometry is changed to fit the strategy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from topogym.planning.slotted_post_ring.runtime import build_config, run_session, tooling
from topogym.tasks.release_profile import PROFILE, environment_inputs


def worker(output, variant, seed, *, max_control_steps, stop_after):
    from topogym.planning.harbor_bridge.evidence import SessionEvidence
    from topogym.planning.slotted_post_ring.audit import export_robot_geometry
    from topogym.simulator.rollout_simulation.evidence import SegmentEvidence
    from topogym.utils.io import to_jsonable, write_json_atomic

    report = dict(format="slotted_session_v1", status="running", started=time.time(),
                  profile=PROFILE, variant=variant, seed=seed, stop_after=stop_after,
                  task_success=False, qualification="unqualified", harbor_qualified=False,
                  scope="Local v15 Session candidate; per-tick measurements and executed actions")
    write_json_atomic(output / "run_report.json", report)
    session = evidence = ticks = None
    unsubscribe = None
    try:
        parameters, overrides, _ = environment_inputs("slotted_post_ring", variant, seed=seed)
        session = tooling().Session("slotted_post_ring", variation_id="slotted_post_ring_" + variant,
            seed=seed, task_parameters=parameters, simulator_overrides=overrides,
            gripper_space="native", strict=True, max_steps=max_control_steps)
        env = session.env
        report.update(config=to_jsonable(env.config), rules=session.rules,
                      tooling_sha256=hashlib.sha256(Path(tooling().__file__).read_bytes()).hexdigest(),
                      instance_id=env._task.instance_id, initial_state=dict(env.tick_record()["state"]))
        ticks = SegmentEvidence(output, env)
        export_robot_geometry(env, output)
        ticks.tick(env.tick_record(), segment_id=0)
        unsubscribe = env.add_state_sink(lambda row: ticks.tick(row, segment_id=1))
        session.record_start()
        evidence = SessionEvidence(session)
        recording = session._recording
        episode, branch = env._episode_id, env._branch_id
        result = run_session(session, output, stop_after=stop_after)
        evidence.check()
        if (env._episode_id != episode or env._branch_id != branch or session._resets
                or session._recording is not recording):
            raise RuntimeError("The policy replaced or rewound the caller-owned episode")
        if not result["evidence_complete"] or not result["physics_tick_complete"]:
            raise RuntimeError("Incomplete Session trajectory")
        report.update(result=result, task_success=bool(session.success()))
        report["status"] = ("native_success_pending_verifier" if session.success() and stop_after is None
                            else "development_prefix" if stop_after and result["reason"] == "policy_done"
                            else "not_passed")
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        try:
            if session is not None:
                report.update(final_state=dict(session.env.tick_record()["state"]),
                              task_result=to_jsonable(session.env._task.result), session=session.status())
            if evidence is not None:
                report["evaluation"] = evidence.report()
                evidence.close()
            if session is not None and session._recording is not None:
                actions = session.record_stop()
                if len(actions):
                    session.save_trajectory(actions, output / "trajectory.npz", meta=dict(
                        source="slotted_session_v1", profile=PROFILE, status=report["status"]))
        except BaseException:
            report.update(status="failed", evidence_error=traceback.format_exc())
            raise
        finally:
            if unsubscribe is not None:
                unsubscribe()
            if ticks is not None:
                report["evidence"] = ticks.statistics()
                ticks.close()
            try:
                if session is not None:
                    session.close()
            finally:
                report["wall_time_s"] = time.time() - report["started"]
                write_json_atomic(output / "run_report.json", report)
    return 0 if report["status"] == "native_success_pending_verifier" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--variant", choices=("easy", "medium", "hard"), required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-control-steps", type=int, default=28000)
    parser.add_argument("--stop-after", help="Unqualified development prefix; currently bead_to_slot only")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.max_control_steps < 1:
        parser.error("max control steps must be positive")
    build_config(args.variant, args.seed)
    output = args.output.resolve()
    if args.worker:
        return worker(output, args.variant, args.seed, max_control_steps=args.max_control_steps,
                      stop_after=args.stop_after)
    output.mkdir(parents=True, exist_ok=False)
    from scripts.test_policy_cube_transfer import snapshot
    source = snapshot(output)
    manifest_path = output / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    # The shared snapshot helper predates Session runners. Freeze the actual local tooling too.
    relative = Path("harbor_templates/topogym/common/rcb_topogym.py")
    target = source / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / relative, target)
    manifest[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_path.rename(output / "run_source_manifest.json")
    command = [sys.executable, str(source / "scripts/oracle_runners/run_slotted_post_ring_oracle.py"),
               "--worker", "--output", str(output), "--variant", args.variant, "--seed", str(args.seed),
               "--max-control-steps", str(args.max_control_steps)]
    if args.stop_after:
        command += ["--stop-after", args.stop_after]
    (output / "invocation.json").write_text(json.dumps(dict(command=command), indent=2) + "\n")
    from topogym.utils.process_limits import run_guarded
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", PYOPENGL_PLATFORM="egl")
    environment.setdefault("TOPOGYM_VISUAL_ASSET_ROOT", str(ROOT / ".external/nyx-assets"))
    return run_guarded(command, output, cwd=source, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
