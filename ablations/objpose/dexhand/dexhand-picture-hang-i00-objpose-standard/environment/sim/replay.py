"""Fresh-process replay of a picture_hang trajectory; only the action rows (and the hand label) are used."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from runtime import TASK_ID, Session
from scene import hands

# Two Marvin arms (7 joint targets each) + both hands' finger actuators (22 per Sharpa Wave, 20 per Wuji Hand 2.2).
WIDTHS = {"sharpa": 58, "wuji": 54}
MAX_ROWS = 3000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget: longer episodes are filmed at a larger stride
MAX_BYTES = 64_000_000


def load_trajectory(path, allow_empty=False, max_rows=MAX_ROWS):
    """Validated ``(actions float64, hand, actuator_names)``; any other archive member is ignored."""
    actions, hand, names = hands.read_trajectory(path, widths=WIDTHS, max_rows=max_rows, task=TASK_ID,
                                                 allow_empty=allow_empty, max_bytes=MAX_BYTES)
    return np.asarray(actions, dtype=np.float64), hand, names


def overlay(frame, status, hand_label, phase=""):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(20 * scale))
    except OSError:
        font = ImageFont.load_default()
    f = status["features"]
    label = "PASS" if status["success"] else ("FAIL: " + status["reason"] if status["failed"] else "IN PROGRESS")
    draw.rectangle((0, 0, frame.shape[1], round(70 * scale)), fill=(28, 34, 38))
    draw.text((round(16 * scale), round(8 * scale)),
              f"Marvin + {hand_label} x2 | hang picture on two hooks | {label} | t={status['steps'] * 0.02:5.2f}s {phase}",
              font=font, fill="white")
    shares = f["hook_load_share"]
    draw.text((round(16 * scale), round(38 * scale)),
              f"stage {status['stage']}/3 | threaded L={int(f['threaded']['l'])} R={int(f['threaded']['r'])} | "
              f"hook load L={shares['l']:.2f} R={shares['r']:.2f} W | hand contacts {f['hand_contacts']} | "
              f"roll {f['roll_deg']:+.2f} deg | hold {status['hold_steps']}/50",
              font=font, fill=(240, 214, 150))
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=25, trusted_service=False, expected_hand=None,
           width=1280, height=720, shadows=True):
    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service,
                                               max_rows=None if trusted_service else MAX_ROWS)
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise ValueError(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    except Exception as error:  # noqa: BLE001 - an unreadable archive is the submitter's problem, never infra
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    # Building the frozen scene is the infrastructure's job: errors here propagate (non-zero exit = infra error).
    session = Session(TASK_ID, hand=hand)
    if names is not None and names != session.actuator_names:
        session.close()
        raise BadTrajectory("Trajectory actuator_names differ from the " + hand + " actuator layout")
    lo, hi = session.ctrl_lo, session.ctrl_hi
    if len(actions) and (np.any(actions < lo - 1e-6) or np.any(actions > hi + 1e-6)):
        session.close()
        raise BadTrajectory("Actuator targets exceed the actuator control ranges")
    writer = None
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        model = session.model
        if not shadows:
            # Drawing settings only (the bounded software-rendered evidence video); physics is untouched.
            model.vis.quality.shadowsize = 1024
            model.vis.quality.offsamples = 1
        for gid in range(model.ngeom):
            name = model.geom(gid).name or ""
            if "_wuji_" in name and "_collision" in name:
                model.geom_rgba[gid, 3] = 0.0  # hide Wuji collision meshes in the picture only
        writer = imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=16)
    stride = max(1, round(1 / (session.control_dt * fps)))
    if video:
        # At most VIDEO_MAX_FRAMES filmed steps, so the longest archive the row limit allows is filmed
        # within the grader's time. Frames only read the scene: physics, verdict and state hash are unchanged.
        stride = max(stride, -(-len(actions) // VIDEO_MAX_FRAMES))
    timeline = []
    label = session.hand_info["model"]
    try:
        session.reset()
        if writer:
            writer.append_data(overlay(session.render_frame(camera, width, height, shadows), session.status(), label))
        for i, row in enumerate(actions):
            status = session.step(row)
            if writer and (i + 1) % stride == 0:
                writer.append_data(overlay(session.render_frame(camera, width, height, shadows), status, label))
            if i % 50 == 0 or session.done or i == len(actions) - 1:
                f = status["features"]
                timeline.append({"control": i + 1, "stage": status["stage"], "reason": status["reason"],
                                 "origin": [round(v, 5) for v in f["origin"]], "threaded": f["threaded"],
                                 "hook_load_share": {k: round(v, 4) for k, v in f["hook_load_share"].items()},
                                 "hand_contacts": f["hand_contacts"], "hold": status["hold_steps"]})
            if session.done:
                break
        status = session.status()
        result = {
            "success": bool(status["success"]),
            "bad_trajectory": 0,
            "reason": status["reason"],
            "failure_detail": status["failure_detail"],
            "hand": session.hand,
            "action_dim": session.action_dim,
            "n_actions": int(len(actions)),
            "steps": int(session.steps),
            "stage": int(status["stage"]),
            "total_stages": 3,
            "state_sha": session.state_sha(),
            "initial_sha": session.initial_sha,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
            "final": {k: v for k, v in status["features"].items() if k not in ("ring_in_saddle_frame",)},
            "timeline": timeline,
        }
        if writer:
            final = overlay(session.render_frame(camera, width, height, shadows), status, label, "(final)")
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


class BadTrajectory(ValueError):
    """The submitted archive (not the infrastructure) is invalid."""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", required=True)
    parser.add_argument("--task", default=TASK_ID, choices=[TASK_ID])
    parser.add_argument("--out")
    parser.add_argument("--trusted-service", action="store_true")
    parser.add_argument("--hand", help="hand recorded by the trusted service; must equal the archive's hand")
    parser.add_argument("--video")
    parser.add_argument("--camera", default="overview")
    parser.add_argument("--fps", type=int, choices=[5, 10, 25, 50])
    args = parser.parse_args()
    try:
        if args.trusted_service:
            # The standard service's evidence video is software rendered inside a bounded collector: small and cheap.
            # Every control is still replayed at 1x; only the drawing settings differ.
            result = replay(args.traj, args.video, args.camera, args.fps or 5, True, args.hand, 640, 360, False)
        else:
            result = replay(args.traj, args.video, args.camera, args.fps or 25, False, args.hand)
    except BadTrajectory as error:  # every read/validation problem of the archive is a bad trajectory, exit 0
        result = {"success": False, "bad_trajectory": 1, "reason": "bad_trajectory", "error": str(error)[:500],
                  "hand": args.hand, "n_actions": 0, "steps": 0, "stage": 0, "state_sha": ""}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("timeline", "final")}, indent=2))


if __name__ == "__main__":
    main()
