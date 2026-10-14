"""Fresh-process replay of a pot_shelf_transfer trajectory (privileged grader and trusted service collector).

python replay.py --task pot_shelf_transfer --traj trajectory.npz --out result.json [--trusted-service] [--hand H]
                 [--video replay.mp4]

Only the `actions` rows (and the optional `hand`, `task`, `actuator_names` labels) are read; every other member of
the archive is ignored. The scene, reset and predicate come from this task directory. Agent-caused problems exit 0
with `bad_trajectory = 1`; only infrastructure problems exit non-zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

import hands
from runtime import CONFIG, TASK_ID, Session

WIDTHS = {"sharpa": 58, "wuji": 54}
MAX_ROWS = int(CONFIG["max_rows"])


def load(path, trusted: bool, hand_arg: str | None):
    actions, hand, names = hands.read_trajectory(
        path, widths=WIDTHS, max_rows=None if trusted else MAX_ROWS, task=TASK_ID, allow_empty=trusted)
    if hand_arg is not None and hands.canonical(hand_arg) != hand:
        raise hands.HandError(f"trajectory hand {hand!r} differs from the recorded episode hand {hand_arg!r}")
    return actions, hand, names


def overlay(frame, status: dict, camera: str):
    from PIL import Image, ImageDraw

    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    label = "SUCCESS" if status["success"] else ("FAIL: " + status["reason"] if status["failed"] else "running")
    draw.rectangle((0, 0, image.width, 38), fill=(24, 34, 30))
    draw.text((8, 4), f"pot_shelf_transfer | {status['hand']} | {camera} | {label}", fill=(255, 255, 255))
    draw.text((8, 20), f"t={status['steps'] * 0.002:6.2f}s  rows={status['steps']}  stage={status['stage']}/2  "
                       f"carry={status['lift_s']:.2f}s  hold={status['hold_s']:.2f}s", fill=(240, 214, 150))
    return np.asarray(image)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--traj", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--trusted-service", action="store_true")
    parser.add_argument("--hand")
    parser.add_argument("--video")
    parser.add_argument("--camera", default="overview")
    parser.add_argument("--shadows", action="store_true", help="render shadows (slower; evidence videos only)")
    parser.add_argument("--fps", type=int, choices=[5, 10, 25, 50])
    args = parser.parse_args()
    # The trusted service renders with software OpenGL inside a bounded collect hook: fewer frames, same physics.
    args.fps = args.fps or (5 if args.trusted_service else 10)
    out = Path(args.out)
    result = {"success": False, "bad_trajectory": 0, "state_sha": "", "steps": 0, "stage": 0, "n_actions": 0,
              "reason": "", "hand": args.hand or "sharpa"}

    def reject(error) -> int:
        result.update(bad_trajectory=1, error=f"{type(error).__name__}: {error}"[:500])
        out.write_text(json.dumps(result, sort_keys=True))
        print(json.dumps(result, sort_keys=True))
        return 0

    # 1. The archive is agent input: anything wrong with it (or a crafted member) is a rejected trajectory.
    try:
        if args.task != TASK_ID:
            raise hands.HandError(f"unknown task {args.task!r}")
        actions, hand, names = load(args.traj, args.trusted_service, args.hand)
    except Exception as error:  # noqa: BLE001 - every failure to parse agent input is the agent's
        return reject(error)
    result["hand"] = hand
    result["n_actions"] = int(len(actions))
    # 2. The frozen scene is the task's own: a failure here is an infrastructure error (non-zero exit).
    session = Session(TASK_ID, hand=hand)
    # 3. Labels and every row are checked against the scene before any physics runs.
    try:
        if names is not None and names != session.actuator_names:
            raise hands.HandError("actuator_names differ from this task's actuator order for that hand")
        for row in actions:
            session.validate(row)
    except ValueError as error:
        return reject(error)
    status = session.replay(actions)
    result.update(
        success=bool(status["success"]),
        state_sha=session.state_sha(),
        physics_sha=session.physics_sha(),
        initial_sha=session.initial_sha,
        steps=int(status["steps"]),
        stage=int(status["stage"]),
        reason=status["reason"],
        detail=status["detail"],
        lift_s=status["lift_s"],
        hold_s=status["hold_s"],
        features={k: v for k, v in session.features().items() if k not in status},
        trajectory_sha256=hashlib.sha256(Path(args.traj).read_bytes()).hexdigest(),
        scene_sha256=session.scene_sha256,
        video=False,
    )
    out.write_text(json.dumps(result, sort_keys=True))
    if args.video:
        import imageio.v2 as imageio

        session.reset()
        every = max(1, round(1.0 / (session.control_dt * args.fps)))

        def frame():
            return overlay(session.render_frame(args.camera, shadows=args.shadows), session.status(), args.camera)

        with imageio.get_writer(args.video, fps=args.fps, codec="libx264", macro_block_size=8) as writer:
            writer.append_data(frame())
            for index, row in enumerate(actions):
                if session.done:
                    break
                session.step(row)
                if (index + 1) % every == 0 or session.done:
                    writer.append_data(frame())
            final = frame()
            for _ in range(args.fps):
                writer.append_data(final)
        result["video"] = True
        result["video_sha256"] = hashlib.sha256(Path(args.video).read_bytes()).hexdigest()
        if session.state_sha() != result["state_sha"]:
            raise RuntimeError("video replay diverged from the verdict replay")
        out.write_text(json.dumps(result, sort_keys=True))
        session.close()
    print(json.dumps({k: v for k, v in result.items() if k != "features"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
