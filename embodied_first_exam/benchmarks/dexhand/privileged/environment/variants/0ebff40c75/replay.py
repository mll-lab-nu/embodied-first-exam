"""Fresh-process replay of a ``boot_sole_brush`` trajectory from the frozen reset (FAMILY_PLUGIN section 5).

python replay.py --task boot_sole_brush --traj trajectory.npz --out result.json [--trusted-service] [--hand ID]
                 [--video out.mp4] [--camera overview] [--fps 10]

Only the ``actions`` rows (and the recorded ``hand``) are used; any other archive member is ignored. Agent-caused
problems exit 0 with ``bad_trajectory = 1``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from runtime import ACTION_DIM, TASK_ID, Session
from scene import hands

MAX_ROWS = 3000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget: longer episodes are filmed at a larger stride
MAX_BYTES = 64_000_000


class BadTrajectory(ValueError):
    """The submitted archive (not the infrastructure) is invalid: reported as bad_trajectory, exit 0."""


def load(path, trusted_service=False, expected_hand=None):
    try:
        actions, hand, names = hands.read_trajectory(
            path, widths=ACTION_DIM, max_rows=None if trusted_service else MAX_ROWS, task=TASK_ID,
            allow_empty=trusted_service, max_bytes=MAX_BYTES,
        )
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise ValueError(f"trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    except Exception as error:  # noqa: BLE001 - an unreadable or invalid archive is the submitter's problem
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    return actions, hand, names


def overlay(frame, status, hand_label):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(20 * scale))
    except OSError:
        font = ImageFont.load_default()
    label = "SUCCESS" if status["success"] else ("FAIL: " + status["reason"] if status["failed"] else "running")
    draw.rectangle((0, 0, frame.shape[1], round(70 * scale)), fill=(24, 32, 30))
    draw.text((round(16 * scale), round(8 * scale)),
              f"{hand_label} | brush the boot sole | {label} | control {status['steps']}", font=font, fill="white")
    draw.text((round(16 * scale), round(38 * scale)),
              f"stage {status['stage']}/3 | clods brushed {status['clods_brushed']}/6 | in tray "
              f"{status['clods_in_tray']}/6 | hold {status['hold']}/50", font=font, fill=(240, 214, 160))
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=10, trusted_service=False, expected_hand=None, width=None,
           height=None):
    actions, hand, names = load(path, trusted_service, expected_hand)
    # Building the frozen scene and the physics are the infrastructure's job: errors there propagate (non-zero exit =
    # infrastructure error), never relabelled as a bad trajectory.
    session = Session(TASK_ID, hand=hand)
    try:
        if names is not None and names != session.actuator_names:
            raise BadTrajectory("trajectory actuator_names differ from the " + hand + " actuator layout")
        if len(actions) and (np.any(actions < session.lo - 1e-6) or np.any(actions > session.hi + 1e-6)):
            raise BadTrajectory("actuator targets exceed native joint bounds")
    except Exception:
        session.close()
        raise
    writer = None
    if video:
        import imageio.v2 as imageio

        Path(video).parent.mkdir(parents=True, exist_ok=True)
        writer = imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=16)
        m = session.model
        for g in range(m.ngeom):  # hide Wuji's translucent collision meshes in the evidence video (no physics effect)
            name = m.geom(g).name or ""
            if name.startswith("r_wuji_") and "_collision" in name:
                m.geom_rgba[g, 3] = 0.0
    # Evidence video only (never the verdict): the bounded service collector renders smaller frames without shadows.
    width = width or (960 if trusted_service else 1280)
    height = height or (544 if trusted_service else 720)
    shadows = not trusted_service
    stride = max(1, round(1 / (session.control_dt * fps)))
    if video:
        # At most VIDEO_MAX_FRAMES filmed steps, so the longest archive the row limit allows is filmed
        # within the grader's time. Frames only read the scene: physics, verdict and state hash are unchanged.
        stride = max(stride, -(-len(actions) // VIDEO_MAX_FRAMES))
    label = session.hand_info["model"]
    timeline = []
    try:
        if writer:
            writer.append_data(overlay(session.render_frame(camera, width, height, shadows), session.status(), label))
        for i, row in enumerate(actions):
            st = session.step(row)
            if writer and ((i + 1) % stride == 0 or session.done):
                writer.append_data(overlay(session.render_frame(camera, width, height, shadows), st, label))
            if i % 100 == 0 or session.done or i == len(actions) - 1:
                timeline.append({"control": i + 1, "stage": st["stage"], "reason": st["reason"],
                                 "in_tray": st["clods_in_tray"], "brushed": st["clods_brushed"]})
            if session.done:
                break
        st = session.status()
        if writer:
            last = overlay(session.render_frame(camera, width, height, shadows), st, label)
            for _ in range(fps):
                writer.append_data(last)
        result = {
            "success": bool(st["success"]),
            "state_sha": session.state_sha(),
            "steps": int(session.steps),
            "stage": int(st["stage"]),
            "hand": session.hand,
            "n_actions": int(len(actions)),
            "reason": st["reason"],
            "bad_trajectory": 0,
            "failure_detail": st["failure_detail"],
            "clods_in_tray": st["clods_in_tray"],
            "clods_brushed": st["clods_brushed"],
            "initial_sha": session.initial_sha,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
            "timeline": timeline,
        }
    finally:
        if writer:
            writer.close()
        session.close()
    if video:
        result.update(video=True, video_stride=stride)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", required=True)
    parser.add_argument("--task", default=TASK_ID, choices=[TASK_ID])
    parser.add_argument("--out")
    parser.add_argument("--trusted-service", action="store_true")
    parser.add_argument("--hand")
    parser.add_argument("--video")
    parser.add_argument("--camera", default="overview")
    parser.add_argument("--fps", type=int, default=None, choices=[5, 10, 25, 50])
    args = parser.parse_args()
    try:
        fps = args.fps or (5 if args.trusted_service else 10)
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand)
    except BadTrajectory as error:  # read/validation problems of the archive only; scene/physics errors propagate
        result = {"success": False, "bad_trajectory": 1, "reason": "bad_trajectory", "error": str(error)[:500],
                  "hand": args.hand, "n_actions": 0, "steps": 0, "stage": 0, "state_sha": ""}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "timeline"}, indent=2))


if __name__ == "__main__":
    main()
