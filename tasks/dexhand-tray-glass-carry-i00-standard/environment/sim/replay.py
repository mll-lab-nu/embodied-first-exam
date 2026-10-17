"""Fresh-process replay of a tray_glass_carry trajectory; archive metadata cannot change the frozen instance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from runtime import Session
from scene import hands

TASK = "tray_glass_carry"
WIDTHS = {"sharpa": 56, "wuji": 52}  # 2 x 6 wrist-stage targets + both hands' finger actuators
MAX_ROWS = 3000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget (board 0136): longer episodes are filmed at a larger stride
MAX_BYTES = 64_000_000


class BadTrajectory(ValueError):
    """The submitted archive (not the infrastructure) is invalid: reported as bad_trajectory, exit 0."""


def load_trajectory(path, allow_empty=False):
    """``(actions float64 (T, D), hand, actuator_names or None)``; everything else in the archive is ignored."""
    actions, hand, names = hands.read_trajectory(
        path, widths=WIDTHS, max_rows=None if allow_empty else MAX_ROWS, task=TASK, allow_empty=allow_empty,
        max_bytes=MAX_BYTES)
    return np.asarray(actions, dtype=np.float64), hand, names


def overlay(frame, status, hand_label):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(20 * scale))
    except OSError:
        font = ImageFont.load_default()
    label = "PASS" if status["success"] else ("FAIL: " + status["reason"] if status["failed"] else "in progress")
    f = status["features"] or {}
    stages = ["start", "lifted", "placed on target", "released + held"]
    draw.rectangle((0, 0, frame.shape[1], round(70 * scale)), fill=(24, 30, 34))
    draw.text((round(16 * scale), round(8 * scale)),
              f"{hand_label} x2 | tray with two filled glasses | {label} | stage {status['stage']}/3 "
              f"({stages[status['stage']]}) | t = {status['steps'] * 0.02:5.2f} s",
              font=font, fill="white")
    glasses = f.get("glasses", {})
    tilts = ", ".join(f"{g['tilt_deg']:.1f}" for g in glasses.values())
    draw.text((round(16 * scale), round(38 * scale)),
              f"glass tilt [{tilts}] deg (spill > 15) | tray tilt {f.get('tray_tilt_deg', 0):.1f} deg | "
              f"hand contact {'yes' if f.get('hand_contact') else 'no'} | hold {status['hold_steps']}/50",
              font=font, fill=(236, 214, 160))
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=25, trusted_service=False, expected_hand=None, width=1280,
           height=720):
    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service)
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise ValueError(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    except Exception as error:  # noqa: BLE001 - any unreadable archive is the submitter's problem
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    # Building the frozen scene and the physics are the infrastructure's job: errors there propagate (non-zero exit =
    # infrastructure error), never relabelled as a bad trajectory.
    session = Session(hand=hand)
    if names is not None and names != session.actuator_names:
        session.close()
        raise BadTrajectory("Trajectory actuator_names differ from the " + hand + " actuator layout")
    lo, hi = session.model.actuator_ctrlrange.T
    if len(actions) and (np.any(actions < lo - 1e-6) or np.any(actions > hi + 1e-6)):
        session.close()
        raise BadTrajectory("Actuator targets exceed their ranges")
    writer = None
    label = session.hand_info["model"]
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        model = session.model
        for gid in range(model.ngeom):  # hide the Wuji vendor collision meshes (drawing only)
            name = model.geom(gid).name or ""
            if "_wuji_" in name and "_collision" in name:
                model.geom_rgba[gid, 3] = 0.0
        writer = imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=16)
        writer.append_data(overlay(session.render_frame(camera, width, height), session.status(), label))
    stride = max(1, round(1 / (session.control_dt * fps)))
    if video:
        # Board 0136: at most VIDEO_MAX_FRAMES filmed steps, so the longest archive the row limit allows is filmed
        # within the grader's time. Frames only read the scene: physics, verdict and state hash are unchanged.
        stride = max(stride, -(-len(actions) // VIDEO_MAX_FRAMES))
    timeline = []
    try:
        for i, action in enumerate(actions):
            st = session.step(action)
            if writer and ((i + 1) % stride == 0 or session.done):
                writer.append_data(overlay(session.render_frame(camera, width, height), st, label))
            if i % 50 == 0 or session.done or i == len(actions) - 1:
                timeline.append({"control": i, "stage": st["stage"], "reason": st["reason"],
                                 "tray_pos": st["features"]["tray_pos"]})
            if session.done:
                break
        st = session.status()
        result = {
            "success": bool(st["success"]),
            "bad_trajectory": 0,
            "reason": st["reason"],
            "failure_detail": st["failure_detail"],
            "hand": session.hand,
            "action_dim": session.action_dim,
            "n_actions": int(len(actions)),
            "steps": int(st["steps"]),
            "stage": int(st["stage"]),
            "total_stages": 3,
            "initial_sha": session.initial_sha,
            "state_sha": session.state_sha(),
            "final": st["features"],
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        }
        if writer:
            final = overlay(session.render_frame(camera, width, height), st, label)
            for _ in range(fps):
                writer.append_data(final)
    finally:
        if writer:
            writer.close()
        session.close()
    if video:
        result["video_sha256"] = hashlib.sha256(Path(video).read_bytes()).hexdigest()
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
        # The standard collector renders its evidence video in software: fewer, smaller frames. Every control is
        # still executed at 1x; drawing settings never change the physics or the verdict.
        fps = args.fps or (5 if args.trusted_service else 25)
        size = (960, 544) if args.trusted_service else (1280, 720)
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand, *size)
    except BadTrajectory as error:  # read/validation problems of the archive only; scene/physics errors propagate
        result = {"success": False, "bad_trajectory": 1, "reason": "bad_trajectory", "error": str(error)[:500],
                  "hand": args.hand, "n_actions": 0, "steps": 0, "stage": 0, "state_sha": ""}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("timeline", "final")}, indent=2))
