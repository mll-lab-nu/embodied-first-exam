"""Fresh frozen-instance replay of agent rows (FAMILY_PLUGIN.md section 5); trajectory metadata cannot change the task."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from runtime import TASK, Session
from scene import hands

# 14 Marvin arm targets (left J1-J7, right J1-J7), then the left and the right hand's native finger actuators.
WIDTHS = {"sharpa": 58, "wuji": 54}
MAX_ROWS = 3000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget: longer episodes are filmed at a larger stride
VIDEO_LABEL = {"speed": 1}   # the overlay's playback speed, set by replay() from the filmed stride
MAX_BYTES = 64_000_000  # the archive file and its expanded members (tests/grade.py: the same 64 MB)


class BadTrajectory(ValueError):
    """The submitted archive (not the infrastructure) is invalid: reported as bad_trajectory, exit 0."""


def load_trajectory(path, allow_empty=False):
    """Validate an agent or service archive and return ``(actions, hand, actuator_names)`` (hands.read_trajectory)."""
    actions, hand, names = hands.read_trajectory(
        path, widths=WIDTHS, max_rows=None if allow_empty else MAX_ROWS, task=TASK, allow_empty=allow_empty,
        max_bytes=MAX_BYTES,
    )
    if not allow_empty and not 1 <= len(actions) <= MAX_ROWS:
        raise ValueError(f"Expected 1 to {MAX_ROWS} action rows")
    if not np.isfinite(actions).all():
        raise ValueError("Actions must be finite")
    return np.asarray(actions, dtype=np.float64), hand, names


def overlay(frame, status, phase, hand_label):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(19 * scale))
    except OSError:
        font = ImageFont.load_default()
    label = "PASS" if status["success"] else ("FAIL: " + status["failure"] if status["failure"] else "IN PROGRESS")
    draw.rectangle((0, 0, frame.shape[1], round(96 * scale)), fill=(23, 29, 35))
    phase = str(phase).replace("\n", " ")[:60]
    draw.text((round(18 * scale), round(10 * scale)), f"{hand_label} | USB plug insertion | {label} | {phase}",
              font=font, fill="white")
    draw.text(
        (round(18 * scale), round(39 * scale)),
        f"Stage {status['stage']}/3 | port-4 depth {status['target_depth_m'] * 1000:5.2f}/12.00 mm | axis error "
        f"{status['axis_error_deg']:4.1f} deg | released hold {status['released_hold_controls']}/50",
        font=font, fill=(244, 214, 157),
    )
    draw.text((round(18 * scale), round(67 * scale)),
              f"Native actuator replay, {VIDEO_LABEL['speed']:g}x | "
              "free rigid plug + passive cable; hub rests free on the counter",
              font=font, fill=(185, 205, 185))
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=10, trusted_service=False, expected_hand=None, phases_path=None):
    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service)
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise ValueError(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    except Exception as error:  # noqa: BLE001 - any unreadable archive is the submitter's, never an infra error
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    # Building the frozen scene and the physics are the infrastructure's job: errors there propagate (non-zero exit =
    # infrastructure error), never relabelled as a bad trajectory.
    session = Session(TASK, hand=hand)
    lo, hi = session.model.actuator_ctrlrange.T
    if names is not None and names != session.actuator_names:
        session.close()
        raise BadTrajectory("Trajectory actuator_names differ from the " + hand + " actuator layout")
    if len(actions) and (np.any(actions < lo - 1e-6) or np.any(actions > hi + 1e-6)):
        session.close()
        raise BadTrajectory("Actuator targets exceed native joint bounds")
    hand_label = session.hand_info["model"]
    phases = np.full(len(actions), "actuator replay", dtype=object)
    if video and phases_path and Path(phases_path).is_file():
        with np.load(phases_path, allow_pickle=False) as archive:
            if "phases" in archive and archive["phases"].shape == (len(actions),):
                phases = archive["phases"].astype(str)
    writer = None
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        model = session.model
        for gid in range(model.ngeom):
            # Hide the Wuji vendor's translucent collision meshes (drawing only; colours never enter the physics).
            if (model.geom(gid).name or "").startswith("r_wuji_") and "_collision" in model.geom(gid).name:
                model.geom_rgba[gid, 3] = 0.0
        writer = imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=16)
    stride = max(1, round(1 / (session.control_dt * fps)))
    if video:
        # At most VIDEO_MAX_FRAMES filmed steps, so the longest archive the row limit allows is filmed
        # within the grader's time. Frames only read the scene: physics, verdict and state hash are unchanged.
        stride = max(stride, -(-len(actions) // VIDEO_MAX_FRAMES))
        VIDEO_LABEL["speed"] = round(stride * session.control_dt * fps, 3)
    timeline = []
    size = (1280, 720)
    try:
        if writer:
            writer.append_data(overlay(session.render_frame(camera, *size), session.status(), "initial state", hand_label))
        for i, (action, phase) in enumerate(zip(actions, phases)):
            session.step(action)
            if writer and (i + 1) % stride == 0:
                writer.append_data(overlay(session.render_frame(camera, *size), session.status(), phase, hand_label))
            if i % 50 == 0 or i == len(actions) - 1 or session.done:
                st = session.status()
                timeline.append({k: st[k] for k in ("steps", "stage", "reason", "target_depth_m", "axis_error_deg",
                                                    "fingers_on_plug", "plug_touch", "hub_displacement_m")})
            if session.done:
                # The episode ends at the first success or the first broken invariant; later rows are not executed.
                break
        status = session.status()
        result = {
            "success": bool(session.success),
            "bad_trajectory": 0,
            "reason": status["reason"],
            "hand": session.hand,
            "action_dim": session.action_dim,
            "failure": session.failure,
            "failure_detail": session.failure_detail,
            "n_actions": len(actions),
            "steps": session.steps,
            "stage": status["stage"],
            "initial_sha": session.initial_sha,
            "state_sha": session.state_sha(),
            "verdict": {k: status[k] for k in ("seated_port", "target_depth_m", "target_lateral_m", "target_vertical_m",
                                                "axis_error_deg", "polarity_cos", "fingers_on_plug", "plug_touch",
                                                "hub_displacement_m", "released_hold_controls", "lift_step",
                                                "seat_step")},
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        }
        if writer:
            final = overlay(session.render_frame("closeup" if session.success else camera, *size), status,
                            "final state", hand_label)
            for _ in range(fps * 2):
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
    parser.add_argument("--fps", type=int, choices=[5, 10, 25, 50])
    parser.add_argument("--phases", help="authoring only: phase labels for the video overlay")
    parser.add_argument("--hand", help="hand recorded by the trusted service; must equal the archive's hand")
    args = parser.parse_args()
    try:
        fps = args.fps if args.fps is not None else (5 if args.trusted_service else 10)
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand, args.phases)
    except BadTrajectory as error:  # read/validation problems of the archive only; scene/physics errors propagate
        result = {
            "success": False,
            "bad_trajectory": 1,
            "reason": "bad_trajectory",
            "error": f"{type(error).__name__}: {error}"[:500],
            "hand": args.hand,
            "n_actions": 0,
            "steps": 0,
            "stage": 0,
            "state_sha": "",
        }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("timeline", "verdict")}, indent=2, default=str))
