from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskSpec:
    module: str
    output_name: str
    every_n_steps: int
    extra_args: tuple[str, ...] = ()


TASK_SPECS: dict[str, TaskSpec] = {
    "swap": TaskSpec(
        module="prototypes.swap_physical_grasp_demo",
        output_name="demo_swap_physical_full.mp4",
        every_n_steps=2,
    ),
    "onestroke": TaskSpec(
        module="prototypes.onestroke_physical_wall_demo",
        output_name="demo_onestroke_physical_full.mp4",
        every_n_steps=2,
    ),
    "maze": TaskSpec(
        module="prototypes.maze_wall_removal_physical_demo",
        output_name="demo_maze_wall_removal_physical_full.mp4",
        every_n_steps=4,
        extra_args=("--seed", "11"),
    ),
}

TASK_ALIASES = {
    "one-stroke": "onestroke",
    "one_stroke": "onestroke",
    "maze_removal": "maze",
    "maze-wall-removal": "maze",
    "maze_wall_removal": "maze",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record full physical-demo videos for a selected task set. "
            "The script delegates to each task's existing prototype module."
        )
    )
    parser.add_argument(
        "--tasks",
        default="swap,onestroke,maze",
        help=(
            "Comma-separated task names, or 'all'. "
            f"Available: {', '.join(sorted(TASK_SPECS))}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs"),
        help="Directory for generated mp4 files.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to launch task modules. Defaults to the current interpreter.",
    )
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default=None)
    parser.add_argument("--record-fps", type=int, default=30)
    parser.add_argument("--record-camera", default="oblique")
    parser.add_argument(
        "--record-every-n-steps",
        type=int,
        default=None,
        help="Override each task's default video frame stride.",
    )
    parser.add_argument("--record-res", type=int, nargs=2, default=(640, 640), metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--record-aa", action="store_true", help="Enable antialiasing in child demos.")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them.",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Run later tasks even if an earlier recording command fails.",
    )
    return parser.parse_args()


def _normalize_tasks(raw_tasks: str) -> list[str]:
    requested = [name.strip().lower() for name in raw_tasks.split(",") if name.strip()]
    if not requested:
        raise SystemExit("No tasks requested.")
    if requested == ["all"]:
        return list(TASK_SPECS)

    tasks: list[str] = []
    for raw_name in requested:
        name = TASK_ALIASES.get(raw_name, raw_name)
        if name not in TASK_SPECS:
            available = ", ".join(sorted(TASK_SPECS))
            raise SystemExit(f"Unknown task {raw_name!r}. Available tasks: {available}.")
        if name not in tasks:
            tasks.append(name)
    return tasks


def _command_for_task(args: argparse.Namespace, task: str) -> list[str]:
    spec = TASK_SPECS[task]
    output_path = args.output_dir / spec.output_name
    every_n_steps = args.record_every_n_steps or spec.every_n_steps

    cmd = [
        str(args.python),
        "-m",
        spec.module,
        *spec.extra_args,
        "--record-video",
        str(output_path),
        "--record-fps",
        str(args.record_fps),
        "--record-every-n-steps",
        str(every_n_steps),
        "--record-camera",
        str(args.record_camera),
        "--record-res",
        str(int(args.record_res[0])),
        str(int(args.record_res[1])),
    ]
    if args.backend is not None:
        cmd.extend(["--backend", args.backend])
    if args.record_aa:
        cmd.append("--record-aa")
    if args.verbose:
        cmd.append("--verbose")
    return cmd


def main() -> None:
    args = parse_args()
    tasks = _normalize_tasks(args.tasks)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    failures: list[tuple[str, int]] = []
    for index, task in enumerate(tasks, start=1):
        cmd = _command_for_task(args, task)
        print(f"[{index}/{len(tasks)}] record {task}: {shlex.join(cmd)}", flush=True)
        if args.dry_run:
            continue
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            failures.append((task, result.returncode))
            if not args.continue_on_failure:
                raise SystemExit(result.returncode)

    if failures:
        summary = ", ".join(f"{task}={code}" for task, code in failures)
        raise SystemExit(f"Recording finished with failures: {summary}")


if __name__ == "__main__":
    main()
