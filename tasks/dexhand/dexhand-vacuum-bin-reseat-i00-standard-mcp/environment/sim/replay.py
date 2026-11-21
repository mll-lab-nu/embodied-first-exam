"""Fresh frozen-instance replay of a vacuum dust-bin trajectory; archive metadata cannot change the scene."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np

from runtime import Session
from scene import hands

TASK = "vacuum_bin_reseat"
# Six wrist-stage targets followed by the selected hand's native finger actuators.
WIDTHS = {"sharpa": 56, "wuji": 52}  # two floating hands: (6 stage + 22 fingers) x 2 (Sharpa) or (6 + 20) x 2 (Wuji)
MAX_ROWS = 3000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget: longer episodes are filmed at a larger stride
MAX_BYTES = 64_000_000


class BadTrajectory(ValueError):
    """An agent-caused archive problem (unreadable, wrong hand/width/names, out of range): reward 0, exit 0.
    Scene-build and simulator errors are not caught: they are infrastructure errors (non-zero exit)."""


def load_trajectory(path, allow_empty=False):
    """Validate an agent or service archive and return ``(actions, hand, actuator_names)``.

    ``actions`` is the only numeric input. ``hand`` (default ``sharpa``) selects the frozen scene to rebuild; the
    width must equal that hand's action width exactly. Optional ``task`` / ``actuator_names`` must match. Every other
    member (claimed success, states, configs) is ignored.
    """
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Trajectory archive exceeds 64 MB")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 32 or sum(item.file_size for item in entries) > MAX_BYTES:
            raise ValueError("Expanded archive exceeds 64 MB")
    actions, hand, names = hands.read_trajectory(
        path, widths=WIDTHS, max_rows=None if allow_empty else MAX_ROWS, task=TASK, allow_empty=allow_empty,
        max_bytes=MAX_BYTES,
    )
    if (len(actions) == 0 and not allow_empty) or not np.isfinite(actions).all():
        raise ValueError(f"Expected 1 to {MAX_ROWS} finite action rows")
    if not allow_empty and len(actions) > MAX_ROWS:
        raise ValueError(f"More than {MAX_ROWS} action rows")
    return np.asarray(actions, dtype=np.float64), hand, names


def overlay(frame, status, hand_label):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(19 * scale))
    except OSError:
        font = ImageFont.load_default()
    label = "PASS" if status["success"] else ("FAIL: " + status["failure"] if status["failure"] else "IN PROGRESS")
    stages = ["latched", "bin removed", "bin reseated", "released + held"]
    draw.rectangle((0, 0, frame.shape[1], round(70 * scale)), fill=(22, 30, 36))
    draw.text((round(16 * scale), round(8 * scale)),
              f"{hand_label} | vacuum dust-bin reseat | {label} | control {status['steps']}", font=font, fill="white")
    draw.text((round(16 * scale), round(38 * scale)),
              f"stage: {stages[min(3, status['stage'])]} | button {status['button_travel_m'] * 1000:.1f} mm | "
              f"seat error {status['seat_distance_m'] * 1000:.1f} mm / {status['seat_angle_rad']:.3f} rad | "
              f"hold {status['hold_steps']}/50", font=font, fill=(236, 214, 160))
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=25, trusted_service=False, expected_hand=None, width=1280,
           height=720):
    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service)
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise ValueError(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    except Exception as error:  # noqa: BLE001 - any unreadable archive is the submitter's, never an infra error
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    session = Session(TASK, hand=hand)  # build errors propagate: infrastructure, never the agent's
    lo, hi = session.model.actuator_ctrlrange.T
    if names is not None and list(names) != session.actuator_names:
        session.close()
        raise BadTrajectory("Trajectory actuator_names differ from the " + hand + " actuator layout")
    if len(actions) and (np.any(actions < lo - 1e-6) or np.any(actions > hi + 1e-6)):
        session.close()
        raise BadTrajectory("Actuator targets exceed native joint bounds")
    hand_label = session.hand_info["model"]
    writer = None
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        model = session.model
        for gid in range(model.ngeom):
            # Hide the Wuji vendor's translucent collision meshes; visuals only, never physics.
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
            writer.append_data(overlay(session.render_frame(camera, width, height), session.status(), hand_label))
        for i, action in enumerate(actions):
            st = session.step(action)
            if writer and (i + 1) % stride == 0:
                writer.append_data(overlay(session.render_frame(camera, width, height), st, hand_label))
            if i % 50 == 0 or i == len(actions) - 1 or session.done:
                timeline.append({k: st[k] for k in ("steps", "stage", "seat_distance_m", "seat_angle_rad",
                                                   "button_travel_m", "catch_behind_tooth_m", "hand_contacts",
                                                   "body_displacement_m", "success", "failure")})
            if session.done:
                # The episode ends at the first success or the first broken invariant; later rows are not executed.
                break
        st = session.status()
        result = {
            "success": bool(session.success),
            "bad_trajectory": 0,
            "reason": "success" if session.success else (session.failure or ""),
            "hand": session.hand,
            "action_dim": session.action_dim,
            "failure": session.failure,
            "failure_detail": session.failure_detail,
            "n_actions": len(actions),
            "steps": session.steps,
            "stage": int(st["stage"]),
            "total_stages": 3,
            "initial_sha": session.initial_sha,
            "state_sha": session.state_sha(),
            "verdict": {k: v for k, v in st.items() if k not in ("bin_pos",)},
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        }
        if writer:
            final = overlay(session.render_frame(camera, width, height), st, hand_label)
            for _ in range(fps):
                writer.append_data(final)
            from PIL import Image

            Image.fromarray(final).save(video.with_suffix(".png"))
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
    parser.add_argument("--fps", type=int, default=None, choices=[5, 10, 25, 50])
    parser.add_argument("--hand", help="hand recorded by the trusted service; must equal the archive's hand")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    args = parser.parse_args()
    try:
        # The service's evidence video is rendered on the CPU: smaller frames and fps, same physics.
        fps = args.fps if args.fps is not None else (10 if args.trusted_service else 25)
        width = args.width or (640 if args.trusted_service else 1280)
        height = args.height or (360 if args.trusted_service else 720)
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand, width, height)
    except BadTrajectory as error:
        result = {"success": False, "bad_trajectory": 1, "reason": "bad_trajectory", "error": str(error)[:500],
                  "hand": args.hand, "n_actions": 0, "steps": 0, "stage": 0, "state_sha": ""}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("timeline", "verdict")}, indent=2))
