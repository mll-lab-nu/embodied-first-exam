"""Fresh frozen-instance replay; trajectory metadata cannot change the scene or the verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from runtime import TASK, Session
from scene import hands

# Six wrist-stage targets followed by the selected hand's native finger actuators.
WIDTHS = {"sharpa": 28, "wuji": 26}
MAX_ROWS = 6000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget (board 0136): longer episodes are filmed at a larger stride
VIDEO_LABEL = {"speed": 1}   # the overlay's playback speed, set by replay() from the filmed stride
MAX_BYTES = 64_000_000  # the archive file and its expanded members (tests/grade.py: the same 64 MB)


class BadTrajectory(ValueError):
    """An agent-caused archive problem: reported as bad_trajectory (exit 0). Anything else is an infra error."""


def load_trajectory(path, allow_empty=False):
    """Validate an agent or service archive and return ``(actions, hand, actuator_names)``.

    ``actions`` is the only numeric input. ``hand`` (default ``sharpa``) selects the frozen scene to rebuild; the width
    must equal that hand's action width exactly. Optional ``task`` / ``actuator_names`` must match. Every other member
    (claimed success, states, configs) is ignored.
    """
    actions, hand, names = hands.read_trajectory(
        path, widths=WIDTHS, max_rows=MAX_ROWS, task=TASK, allow_empty=allow_empty, max_bytes=MAX_BYTES
    )
    if (len(actions) == 0 and not allow_empty) or len(actions) > MAX_ROWS or not np.isfinite(actions).all():
        raise ValueError(f"Expected 1 to {MAX_ROWS} finite action rows")
    return np.asarray(actions, dtype=np.float64), hand, names


def overlay(frame, status, phase, hand="Sharpa Wave"):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(19 * scale))
    except OSError:
        font = ImageFont.load_default()
    label = "PASS" if status["success"] else "IN PROGRESS"
    if status["failure"]:
        label = "FAIL: " + str(status["failure"])
    draw.rectangle((0, 0, frame.shape[1], round(96 * scale)), fill=(28, 31, 33))
    phase = str(phase).replace("\n", " ")[:60]
    draw.text((round(18 * scale), round(10 * scale)), f"{hand} | stool cross brace | {label} | {phase}", font=font,
              fill="white")
    names = ["brace lifted", "brace dowel seated", "side frame lifted", "8/8 dowels seated"]
    stage = int(status["stage"])
    draw.text(
        (round(18 * scale), round(39 * scale)),
        f"Stage {stage}/4 {names[stage - 1] if stage else ''} | seated interfaces {status['seated_interfaces']}/8 | "
        f"released hold {status['released_hold_steps']}/50",
        font=font, fill=(244, 214, 157))
    draw.text((round(18 * scale), round(67 * scale)),
              f"Native actuator replay, {VIDEO_LABEL['speed']:g}x | "
              "free rigid parts, hollow dowel bores, no welds", font=font,
              fill=(185, 205, 185))
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=10, trusted_service=False, expected_hand=None, width=960,
           height=544):
    # Archive-read phase: every problem here is the submitter's (bad trajectory, exit 0).
    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service)
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise ValueError(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    except Exception as error:  # noqa: BLE001 - any unreadable archive is the submitter's, never an infra error
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    # Scene build: errors here are infrastructure errors and propagate (non-zero exit).
    session = Session(hand=hand)
    lo, hi = session.model.actuator_ctrlrange.T
    if names is not None and names != session.actuator_names:
        session.close()
        raise BadTrajectory("Trajectory actuator_names differ from the " + hand + " actuator layout")
    if len(actions) and (np.any(actions < lo - 1e-6) or np.any(actions > hi + 1e-6)):
        session.close()
        raise BadTrajectory("Actuator targets exceed native joint bounds")
    hand_label = session.hand_info["model"]
    phases = np.full(len(actions), "actuator replay")
    if video:
        try:
            with np.load(path, allow_pickle=False) as archive:
                if "phases" in archive and archive["phases"].shape == (len(actions),) and archive["phases"].dtype.kind in "US":
                    phases = archive["phases"].copy()
        except Exception:  # noqa: BLE001 - captions are cosmetic
            pass
    writer = None
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        model = session.model
        model.vis.quality.shadowsize = 2048
        for gid in range(model.ngeom):
            # Hide the Wuji vendor's translucent collision meshes; visual meshes stay. Colors never enter the physics.
            name = model.geom(gid).name or ""
            if session.owner.get(int(model.geom_bodyid[gid])) == "hand" and name.startswith("r_wuji_") and "_collision" in name:
                model.geom_rgba[gid, 3] = 0.0
        writer = imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=16)
    stride = max(1, round(1 / (session.control_dt * fps)))
    if video:
        # Board 0136: at most VIDEO_MAX_FRAMES filmed steps, so the longest archive the row limit allows is filmed
        # within the grader's time. Frames only read the scene: physics, verdict and state hash are unchanged.
        stride = max(stride, -(-len(actions) // VIDEO_MAX_FRAMES))
        VIDEO_LABEL["speed"] = round(stride * session.control_dt * fps, 3)
    timeline = []
    try:
        if writer:
            writer.append_data(overlay(session.render_frame(camera, width=width, height=height), session.status(),
                                       "initial state", hand_label))
        for i, (action, phase) in enumerate(zip(actions, phases)):
            session.step(action)
            st = session.status()
            if writer and (i + 1) % stride == 0:
                writer.append_data(overlay(session.render_frame(camera, width=width, height=height), st, str(phase),
                                           hand_label))
            if i % 100 == 0 or i == len(actions) - 1 or session.done:
                timeline.append({"action": i, "phase": str(phase), "stage": st["stage"],
                                 "seated_interfaces": st["seated_interfaces"], "reason": st["reason"]})
            if session.done:
                # The episode ends at the first success or the first broken invariant; later rows are not executed.
                if writer and (i + 1) % stride:
                    writer.append_data(overlay(session.render_frame(camera, width=width, height=height), st,
                                               str(phase), hand_label))
                break
        st = session.status()
        result = {
            "success": bool(session.success),
            "bad_trajectory": 0,
            "reason": st["reason"],
            "hand": session.hand,
            "action_dim": session.action_dim,
            "failure": session.failure,
            "failure_detail": session.failure_detail,
            "n_actions": len(actions),
            "steps": session.steps,
            "stage": st["stage"],
            "total_stages": st["total_stages"],
            "initial_sha": session.initial_sha,
            "state_sha": session.state_sha(),
            "verdict": {k: st[k] for k in ("seated_interfaces", "assembled", "hand_contact_parts",
                                           "released_hold_steps", "max_linear_speed_m_s", "max_angular_speed_rad_s",
                                           "lower_frame_shift_m", "ends")},
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        }
        if writer:
            final = overlay(session.render_frame(camera, width=width, height=height), st,
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", required=True)
    parser.add_argument("--task", default=TASK, choices=[TASK])
    parser.add_argument("--trusted-service", action="store_true")
    parser.add_argument("--out")
    parser.add_argument("--video")
    parser.add_argument("--camera", default="overview")
    parser.add_argument("--fps", type=int, choices=[5, 10, 25, 50])
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=544)
    parser.add_argument("--hand", help="hand recorded by the trusted service; must equal the archive's hand")
    args = parser.parse_args()
    try:
        fps = args.fps if args.fps is not None else (5 if args.trusted_service else 10)
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand, args.width,
                        args.height)
    except BadTrajectory as error:
        # Only archive-read and row-validation problems are the submitter's; scene/runtime errors stay infra errors.
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
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("timeline", "verdict")}, indent=2))


if __name__ == "__main__":
    main()
