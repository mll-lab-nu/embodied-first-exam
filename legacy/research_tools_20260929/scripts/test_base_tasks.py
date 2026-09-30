#!/usr/bin/env python3
"""Run base-task physics tests in isolated processes and preserve every outcome."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import tarfile
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from runtime_evidence import BASE_TASKS
from topogym.recording.encoding import probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--visual-asset-root", type=Path,
                        default=os.environ.get("TOPOGYM_VISUAL_ASSET_ROOT", ROOT / ".external/nyx-assets"),
                        help="Prepared Nyx HDRI/material directory; recorded in the environment")
    parser.add_argument("--robots", nargs="+", choices=("aloha", "panda_robotiq"),
                        default=["aloha", "panda_robotiq"], help="Robot profiles for interface/mechanism groups")
    parser.add_argument("--device", choices=("cuda",), default="cuda",
                        help="Runtime evidence uses Nyx RGB, which requires CUDA")
    parser.add_argument(
        "--tasks", nargs="+", choices=BASE_TASKS, default=list(BASE_TASKS)
    )
    parser.add_argument("--variation", default="base",
                        help="Canonical variation ID or difficulty alias, applied to the selected tasks")
    parser.add_argument(
        "--steps",
        type=int,
        default=200,
        help="10 physics ticks per control step; minimum 3",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1800,
        help="Seconds per task, including compilation",
    )
    parser.add_argument(
        "--mechanisms-only",
        action="store_true",
        help="Run small FEM and same-process switching checks only",
    )
    parser.add_argument("--checks", nargs="+", choices=("base", "interfaces", "stability", "outputs", "cameras", "installation", "terminal"),
                        default=["base"], help="Evidence-producing simulator acceptance groups")
    parser.add_argument(
        "--mechanisms",
        nargs="+",
        choices=("fem", "task-switch"),
        default=["fem", "task-switch"],
    )
    args = parser.parse_args()
    if args.steps < 3:
        parser.error("--steps must be at least 3")
    output = (
        args.output
        or ROOT
        / "runs/test_results"
        / datetime.now(timezone.utc).strftime("base_%Y%m%dT%H%M%SZ")
    ).resolve()
    output.mkdir(parents=True, exist_ok=False)
    active_task = None

    def interrupted(signum, frame):
        (output / "driver_interruption.json").write_text(json.dumps(dict(
            signal=signum, pid=os.getpid(), task_id=active_task,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            stack=traceback.format_stack(frame),
        ), indent=2))
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    env = dict(
        os.environ,
        PYTHONPATH=str(ROOT) + os.pathsep + str(ROOT / "tests"),
        PYOPENGL_PLATFORM="egl",
        TOPOGYM_TEST_OUTPUT=str(output),
        TOPOGYM_TEST_DEVICE=args.device,
        TOPOGYM_TEST_STEPS=str(args.steps),
        TOPOGYM_TEST_VARIATION=args.variation,
        TOPOGYM_VISUAL_ASSET_ROOT=str(Path(args.visual_asset_root).expanduser().resolve()),
    )
    source_files = sorted({
        p
        for folder in ("topogym", "tests", "scripts")
        for p in (ROOT / folder).rglob("*")
        if p.is_file() and "deferred" not in p.parts
        and "__pycache__" not in p.parts
        and (p.suffix == ".py" or
             (folder == "topogym" and p.suffix in {".yaml", ".yml", ".json"})
             or ROOT / "topogym/assets/resources" in p.parents)
    } | {ROOT / "pyproject.toml"})
    (output / "source_hashes.json").write_text(
        json.dumps(
            {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in source_files
            },
            indent=2,
        )
    )
    with tarfile.open(output / "source_snapshot.tar.gz", "w:gz") as archive:
        for path in source_files:
            archive.add(path, arcname=str(path.relative_to(ROOT)))
        archive.add(
            ROOT / "configs",
            arcname="configs",
            filter=lambda info: None if "__pycache__" in info.name else info,
        )
    results = []
    print(f"Results: {output}", flush=True)
    jobs = (
        []
        if args.mechanisms_only or "base" not in args.checks
        else [
            (
                task,
                f"tests/integration/test_base_task_runtime.py::test_base_runtime[{task}]",
            )
            for task in args.tasks
        ]
    )
    for check, script in (("interfaces", "test_interface_modes"), ("stability", "test_lifecycle_stability"),
                          ("outputs", "test_output_invariance"), ("cameras", "test_observation_rig")):
        if check in args.checks:
            for robot in args.robots:
                jobs.append((f"{check}_{robot}", f"tests/integration/{script}.py::test_{check}[{robot}]"))
    if "terminal" in args.checks:
        from integration.test_terminal_runtime import TASKS as TERMINAL_TASKS
        for task in args.tasks:
            if task in TERMINAL_TASKS:
                jobs.append((f"terminal_{task}", f"tests/integration/test_terminal_runtime.py::test_terminal_birth_and_rewind[{task}]"))
        if "lock_picking" in args.tasks:
            for case in ("pin_slot", "negative_control"):
                jobs.append((f"terminal_lock_{case}", f"tests/integration/test_terminal_runtime.py::test_lock_physical_stops_without_joint_limits[{case}]"))
        if "fiber_bundling" in args.tasks:
            for role in ("fiber_strand", "fiber_sheath"):
                jobs.append((f"terminal_fiber_{role}", f"tests/integration/test_terminal_runtime.py::test_fiber_native_gripper_contact_probe[{role}]"))
    if "installation" in args.checks:
        jobs.append(("installation", "tests/integration/test_installed_simulator.py::test_installed_runtime"))
    if args.mechanisms_only or ("base" in args.checks and set(args.tasks) == set(BASE_TASKS)):
        if "fem" in args.mechanisms:
            jobs.append(
                (
                    "fem_checkpoint_probe",
                    "tests/integration/test_genesis_fem_ipc.py::test_fem_native_checkpoint_and_end_constraints",
                )
            )
        if "task-switch" in args.mechanisms:
            jobs.append(
                (
                    "task_switch",
                    "tests/integration/test_task_switch_runtime.py::test_task_switch",
                )
            )
    for task, node in jobs:
        active_task = task
        task_sources = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source_files
        }
        (output / f"{task}_source_hashes.json").write_text(
            json.dumps(task_sources, indent=2)
        )
        with tarfile.open(output / f"{task}_source_snapshot.tar.gz", "w:gz") as archive:
            for path in source_files:
                archive.add(path, arcname=str(path.relative_to(ROOT)))
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-o",
            "faulthandler_timeout=120",
            "-vv",
            "-s",
            node,
            f"--junitxml={output / task}_junit.xml",
        ]
        start = time.monotonic()
        status = "failed"
        with (output / f"{task}.log").open("w") as log:
            process = subprocess.Popen(
                cmd,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                code = process.wait(timeout=args.timeout)
                status = "passed" if code == 0 else "failed"
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                code, status = None, "timeout"
            except KeyboardInterrupt:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                code, status = process.returncode, "interrupted"
        report_path = output / task / "report.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        partial = {}
        for video_path in sorted((output / task).rglob("*.part.mp4")):
            relative = str(video_path.relative_to(output / task))
            try:
                partial[relative] = dict(
                    status="interrupted_partial", decode=probe(video_path, decode=True)
                )
            except Exception as error:
                partial[relative] = dict(status="undecodable", error=str(error))
        if partial:
            report["partial_recordings"] = partial
        if report.get("status") == "running" or not report:
            report.update(
                task_id=task,
                status=status,
                exit_code=code,
                interruption="Test process ended before closing evidence; see outer pytest log",
                video_available=bool(report.get("recordings")),
            )
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2))
        elif partial:
            report_path.write_text(json.dumps(report, indent=2))
        if status == "passed" and (
            report.get("status") != "passed" or not report.get("recordings")
        ):
            status = "missing_evidence"
        changed = [
            str(p.relative_to(ROOT))
            for p in source_files
            if not p.exists()
            or hashlib.sha256(p.read_bytes()).hexdigest()
            != task_sources[str(p.relative_to(ROOT))]
        ]
        if changed and status == "passed":
            status = "source_changed"
        videos = {
            path: metadata
            for recording in report.get("recordings", [])
            for path, metadata in recording.get("videos", {}).items()
        }
        video = next(
            (path for path in videos if path.endswith(("/cam_high.mp4", "/agentview.mp4"))),
            next(iter(videos), None),
        )
        initial_frames = report.get("initial_frames", {})
        initial_frame = next((initial_frames[k]["path"] for k in ("cam_high", "agentview") if k in initial_frames), None)
        results.append(
            dict(
                task_id=task,
                status=status,
                exit_code=code,
                wall_time_s=time.monotonic() - start,
                report=f"{task}/report.json",
                command=cmd,
                source_changed_during_test=changed,
                source_snapshot=f"{task}_source_snapshot.tar.gz",
                video=None if video is None else f"{task}/{video}",
                video_info=videos.get(video),
                initial_frame=None if initial_frame is None else f"{task}/{initial_frame}",
            )
        )
        summary = dict(
            scope="selected settings and shared lifecycle mechanisms; no task solution claim",
            variation_id=args.variation,
            requested=[name for name, _ in jobs],
            expected=list(BASE_TASKS),
            full_coverage="base" in args.checks and not args.mechanisms_only
            and set(args.tasks) == set(BASE_TASKS) and args.variation == "base",
            device=args.device,
            renderer="nyx",
            background="compact_lab",
            steps=args.steps,
            base_passed_count=sum(
                r["task_id"] in BASE_TASKS and r["status"] == "passed" for r in results
            ),
            all_base_tasks_passed=args.variation == "base" and all(
                any(r["task_id"] == task and r["status"] == "passed" for r in results)
                for task in BASE_TASKS
            ),
            results=results,
        )
        (output / "summary.json").write_text(json.dumps(summary, indent=2))
        lines = [
            "# Task setting runtime results — Nyx + compact_lab",
            "",
            f"Requested {len(jobs)} checks; completed {len(results)}. "
            "These are actual lifecycle tests, not solved-task demonstrations.",
            "",
            f"Variation `{args.variation}`: {args.steps} control steps × 10 physics ticks × 0.0025 s; "
            "30 fps video. Rewinds and new episodes produce separate segments. "
            "Clips shorter than one second may display as 0 seconds in players; "
            "the exact encoded duration is listed below. Wall time in reports includes compilation and rendering.",
            "",
            "PNG links show the unscaled RGB SensorFrame before video encoding. "
            "Reports include actual camera settings and every camera/branch recording.",
            "",
            "| Task | Result | Evidence | Actual scene video | Seconds | Frames | Resolution | Raw initial frame |",
            "|---|---|---|---|---:|---:|---|---|",
        ]
        for r in results:
            info = r["video_info"]
            lines.append(
                f"| {r['task_id']} | {r['status']} | [report]({r['report']}) · [log]({r['task_id']}.log) | "
                + (f"[MP4]({r['video']})" if r["video"] else "unavailable")
                + (f" | {info['duration_s']:.3f} | {info['frames']} | {info['width']}×{info['height']} | "
                   if info else " | — | — | — | ")
                + (f"[PNG]({r['initial_frame']})" if r["initial_frame"] else "unavailable")
                + " |"
            )
        (output / "README.md").write_text("\n".join(lines) + "\n")
        print(f"{task}: {status} ({time.monotonic() - start:.1f}s)", flush=True)
        if status == "interrupted":
            break
    return 0 if all(r["status"] == "passed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
