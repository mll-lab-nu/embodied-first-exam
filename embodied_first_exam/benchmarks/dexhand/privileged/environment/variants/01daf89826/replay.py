"""Fresh frozen-instance replay of a pancake-serving trajectory; metadata cannot change the verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

TASK = "pancake_serve"
# Six wrist-stage targets followed by the selected hand's native finger actuators.
WIDTHS = {"sharpa": 58, "wuji": 54}  # Marvin rig: 14 arm targets, then left and right hand fingers
MAX_ROWS = 3000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget: longer episodes are filmed at a larger stride
MAX_BYTES = 64_000_000  # the archive file and its expanded members (tests/grade.py: the same 64 MB)


class BadTrajectory(ValueError):
    """The submitted archive or its rows are invalid (agent-caused): reported as bad_trajectory, exit 0."""


def load_trajectory(path, allow_empty=False):
    """Validate an archive and return ``(actions float64, hand, actuator_names or None)``."""
    from scene import hands

    max_rows = None if allow_empty else MAX_ROWS
    actions, hand, names = hands.read_trajectory(path, widths=WIDTHS, max_rows=max_rows, task=TASK,
                                                 allow_empty=allow_empty, max_bytes=MAX_BYTES)
    return np.asarray(actions, dtype=np.float64), hand, names


def overlay(frame, f, hand_label):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(20 * scale))
    except OSError:
        font = ImageFont.load_default()
    label = "PASS" if f["success"] else ("FAIL: " + f["failure"] if f["failure"] else "in progress")
    draw.rectangle((0, 0, frame.shape[1], round(70 * scale)), fill=(28, 30, 34))
    draw.text((round(16 * scale), round(8 * scale)),
              f"{hand_label} | serve the pancake with the turner | {label} | t = {f['steps'] * 0.02:5.2f} s",
              font=font, fill="white")
    stages = ["on blade", "over plate", "served + 1 s hold"]
    done = ", ".join(f"[{'x' if f['stage'] > i else ' '}] {s}" for i, s in enumerate(stages))
    draw.text((round(16 * scale), round(38 * scale)),
              f"{done} | hold {f['hold_controls']}/50 | plate dist {f['pancake_plate_dist_m'] * 100:4.1f} cm",
              font=font, fill=(240, 214, 160))
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=25, trusted_service=False, expected_hand=None, width=1280,
           height=720):
    from runtime import Session
    from scene import hands

    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service)
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise ValueError(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    except Exception as error:  # noqa: BLE001 - archive-read phase only: an unreadable archive is the submitter's
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    # Scene build / simulation errors below are NOT caught: they are infrastructure errors (non-zero exit).
    session = Session(hand=hand)
    lo, hi = session.model.actuator_ctrlrange.T
    if names is not None and names != session.actuator_names:
        session.close()
        raise BadTrajectory("Trajectory actuator_names differ from the " + hand + " actuator layout")
    if len(actions) and (np.any(actions < lo - 1e-6) or np.any(actions > hi + 1e-6)):
        session.close()
        raise BadTrajectory("Actuator targets exceed native joint bounds")
    writer = None
    label = session.hand_info["model"]
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        model = session.model
        for gid in range(model.ngeom):
            # Drawing only: hide the Wuji vendor's translucent collision meshes (its visual meshes stay).
            name = model.geom(gid).name or ""
            if name.startswith("r_wuji_") and "_collision" in name:
                model.geom_rgba[gid, 3] = 0.0
        writer = imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=16)
    stride = max(1, round(1 / (session.control_dt * fps)))
    if video:
        # At most VIDEO_MAX_FRAMES filmed steps, so the longest archive the row limit allows is filmed
        # within the grader's time. Frames only read the scene: physics, verdict and state hash are unchanged.
        stride = max(stride, -(-len(actions) // VIDEO_MAX_FRAMES))
    timeline = []
    try:
        if writer:
            first = overlay(session.render_frame(camera, width, height), session.features(), label)
            for _ in range(fps // 2):
                writer.append_data(first)
        for i, action in enumerate(actions):
            f = session.step(action)
            if writer and ((i + 1) % stride == 0 or session.done):
                writer.append_data(overlay(session.render_frame(camera, width, height), f, label))
            if i % 50 == 0 or i == len(actions) - 1 or session.done:
                timeline.append({"action": i, **{k: f[k] for k in (
                    "stage", "pancake_pos", "pancake_tilt_deg", "pancake_plate_dist_m", "pancake_partners",
                    "hold_controls", "failure")}})
            if session.done:
                break
        f = session.features()
        result = {
            "success": session.success,
            "bad_trajectory": 0,
            "reason": "success" if session.success else (session.failure or ""),
            "hand": session.hand,
            "action_dim": session.action_dim,
            "failure": session.failure,
            "failure_detail": session.failure_detail,
            "n_actions": len(actions),
            "steps": session.steps,
            "success_step": session.checker.success_step,
            "stage": int(session.checker.stage),
            "initial_sha": session.initial_sha,
            "state_sha": session.state_sha(),
            "verdict": f,
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        }
        if writer:
            final = overlay(session.render_frame(camera, width, height), f, label)
            for _ in range(fps):
                writer.append_data(final)
    finally:
        if writer:
            writer.close()
        session.close()
    if video:
        result["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
        result.update(video=True, video_stride=stride)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", required=True)
    parser.add_argument("--task", default=TASK, choices=[TASK])
    parser.add_argument("--trusted-service", action="store_true")
    parser.add_argument("--out")
    parser.add_argument("--video")
    parser.add_argument("--camera", default="overview")
    parser.add_argument("--fps", type=int, choices=[5, 10, 25, 50])
    parser.add_argument("--hand", help="hand recorded by the trusted service; must equal the archive's hand")
    args = parser.parse_args()
    try:
        # The bounded service collector renders a light 640 x 480, 5 fps evidence video; authoring videos default to
        # 1280 x 720 at 25 fps. Every control is executed either way (1x playback).
        fps = args.fps if args.fps is not None else (5 if args.trusted_service else 25)
        size = (640, 480) if args.trusted_service else (1280, 720)
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand, *size)
    except BadTrajectory as error:  # archive-read problems and invalid rows only; anything else exits non-zero
        result = {
            "success": False,
            "bad_trajectory": 1,
            "reason": "bad_trajectory",
            "error": str(error)[:500],
            "hand": args.hand,
            "n_actions": 0,
            "steps": 0,
            "stage": 0,
            "state_sha": "",
        }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("timeline", "verdict")}, indent=2))
