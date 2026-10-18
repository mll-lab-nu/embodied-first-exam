"""Fresh-process replay of motor targets on the frozen paper scene; the verdict comes from simulator state only.

The trajectory supplies motor targets and the hand they belong to. Everything else (scene, material, thresholds,
initial state) comes from this task's frozen files; success flags, poses or configuration in an archive are never read.
Agent-caused problems exit 0 with `bad_trajectory = 1`; a non-zero exit means an infrastructure error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

import hands

TASK_ID = "paper_half_fold"
ACTION_DIMS = {"sharpa": 28, "wuji": 26}
MAX_ROWS = 1500


def read(path, trusted_service=False):
    """(actions float64 (T, D), hand, actuator_names or None); D must equal the hand's width exactly."""
    return hands.read_trajectory(
        path,
        widths=ACTION_DIMS,
        max_rows=None if trusted_service else MAX_ROWS,
        task=TASK_ID,
        allow_empty=trusted_service,
    )


class BadTrajectory(Exception):
    """The agent's archive cannot be replayed (unreadable, mismatched, out of range)."""


def read_checked(path, trusted_service=False, expected_hand=None):
    """Read phase: any failure to read or match the archive is the agent's (never an infrastructure error)."""
    try:
        actions, hand, names = read(path, trusted_service)
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise hands.HandError(f"trajectory hand {hand!r} differs from the episode hand {expected_hand!r}")
        return actions, hand, names
    except Exception as error:  # noqa: BLE001 - crafted archives may raise anything while being parsed
        raise BadTrajectory(f"{type(error).__name__}: {error}") from error


def replay(path, video=None, camera="overview", fps=10, trusted_service=False, expected_hand=None):
    from runtime import Session

    actions, hand, names = read_checked(path, trusted_service, expected_hand)
    try:
        session = Session(TASK_ID, hand=hand)
    except ValueError as error:
        # The hand id is already validated: a scene that cannot be built is an infrastructure problem.
        raise RuntimeError(f"cannot build the {hand} scene: {error}") from error
    try:
        if names is not None and list(names) != session.actuator_names:
            raise BadTrajectory("actuator_names differ from the selected hand's actuator order")
        lo, hi = session.model.actuator_ctrlrange.T
        if len(actions) and (np.any(actions < lo - 1e-7) or np.any(actions > hi + 1e-7)):
            raise BadTrajectory("actuator targets outside the declared limits")
        writer = None
        if video:
            import imageio.v2 as imageio

            video = Path(video)
            video.parent.mkdir(parents=True, exist_ok=True)
            writer = imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=16)
            writer.append_data(session.render_frame(camera, width=960, height=544, shadows=False))
        stride = max(1, round(1 / (session.control_dt * fps)))
        timeline = []
        try:
            for i, action in enumerate(actions):
                f = session.step(action)
                if writer and (i + 1) % stride == 0:
                    writer.append_data(session.render_frame(camera, width=960, height=544, shadows=False))
                if i % 50 == 0 or session.done:
                    timeline.append({"row": i, **{k: f[k] for k in (
                        "fold_angle_rad", "crease_angle_rad", "crease_coverage", "edge_alignment_m", "hand_contacts",
                        "paper_min_z_m", "on_table", "stage", "released_hold_steps", "failure")}})
                if session.done:
                    break
            if writer:
                final = session.render_frame(camera, width=960, height=544, shadows=False)
                for _ in range(fps):
                    writer.append_data(final)
        finally:
            if writer:
                writer.close()
        status = session.status()
        result = {
            "success": bool(session.success),
            "state_sha": status["state_sha"],
            "steps": session.steps,
            "stage": int(session.peak_stage),
            "final_stage": int(status["stage"]),
            "hand": hand,
            "n_actions": int(len(actions)),
            "reason": session.reason,
            "bad_trajectory": 0,
            "initial_sha": session.initial_sha,
            "model_sha256": session.model_sha256,
            "verdict": session.features(),
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        }
    finally:
        session.close()
    if video:
        result["video_sha256"] = hashlib.sha256(Path(video).read_bytes()).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", required=True)
    parser.add_argument("--task", default=TASK_ID, choices=[TASK_ID])
    parser.add_argument("--hand", help="the episode hand recorded by the trusted service")
    parser.add_argument("--trusted-service", action="store_true")
    parser.add_argument("--out")
    parser.add_argument("--video")
    parser.add_argument("--camera", default="overview")
    parser.add_argument("--fps", type=int, choices=[5, 10, 25, 50])
    args = parser.parse_args()
    fps = args.fps if args.fps is not None else (5 if args.trusted_service else 10)
    try:
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand)
    except BadTrajectory as error:
        missing = not Path(args.traj).is_file()
        result = {"success": False, "bad_trajectory": 1, "error": str(error)[:500], "state_sha": "", "steps": 0,
                  "stage": 0, "n_actions": 0, "reason": "missing_trajectory" if missing else "bad_trajectory",
                  "hand": args.hand or ""}
        if missing:
            result["missing_trajectory"] = 1
    # Anything else (the frozen scene cannot be built, a simulator crash) propagates: non-zero exit = infra error.
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("timeline", "verdict")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
