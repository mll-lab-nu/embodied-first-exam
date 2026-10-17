"""Fresh frozen-instance replay of a fan-guard trajectory; only the numeric rows influence the verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import zlib

import numpy as np

from runtime import TASK, TOL, Session
from scene import hands

# Six wrist-stage targets followed by the selected hand's native finger actuators.
WIDTHS = {"sharpa": 28, "wuji": 26}
MAX_ROWS = 6000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget (board 0136): longer episodes are filmed at a larger stride
VIDEO_LABEL = {"speed": 1}   # the overlay's playback speed, set by replay() from the filmed stride
MAX_BYTES = 64_000_000  # the archive file and its expanded members (tests/grade.py: the same 64 MB)


class BadTrajectory(ValueError):
    """The submitted archive (not the infrastructure) is invalid: reported as bad_trajectory, exit 0."""


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


def overlay(frame, features, phase, hand="Sharpa Wave"):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(19 * scale))
    except OSError:
        font = ImageFont.load_default()
    label = "PASS" if features["success"] else "INCOMPLETE"
    if features["failure"]:
        label = "FAIL: " + features["failure"]
    draw.rectangle((0, 0, frame.shape[1], round(96 * scale)), fill=(24, 30, 36))
    phase = str(phase).replace("\n", " ").replace("\r", " ")[:64]
    draw.text((round(18 * scale), round(10 * scale)), f"{hand} | fan front guard | {label} | {phase}", font=font,
              fill="white")
    clips = sum(1 for q in features["clip_angles_rad"] if q <= 0.12)
    draw.text(
        (round(18 * scale), round(39 * scale)),
        f"Stage {features['stage']}/3 | concentric {features['concentric_m'] * 1000:.1f} mm | parallel "
        f"{np.degrees(features['parallel_rad']):.1f} deg | clips locked {clips}/4 | hands-off hold "
        f"{features['hold_steps']}/50",
        font=font,
        fill=(244, 214, 157),
    )
    draw.text((round(18 * scale), round(67 * scale)),
              f"Native actuator replay, {VIDEO_LABEL['speed']:g}x | "
              "passive hinged clips with elastic over-centre detent", font=font,
              fill=(185, 205, 185))
    return np.asarray(canvas)


def pick_camera(session, camera):
    """``auto``: the overview while the guard is away from the fan, the close-up near it (presentation only)."""
    if camera != "auto":
        return camera
    gap = np.linalg.norm(session.data.body("front_guard").xpos - session.data.body("fan").xpos)
    return "closeup" if gap < 0.12 else "overview"


def replay(path, video=None, camera="overview", fps=10, trusted_service=False, expected_hand=None, width=960,
           height=544, quality="evidence"):
    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service)
    except Exception as error:  # noqa: BLE001 - any unreadable archive is the submitter's, never an infra error
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    if expected_hand is not None and hands.canonical(expected_hand) != hand:
        raise BadTrajectory(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    session = Session(hand=hand)
    lo, hi = session.model.actuator_ctrlrange.T
    if names is not None and names != session.actuator_names:
        session.close()
        raise BadTrajectory("Trajectory actuator_names differ from the " + hand + " actuator layout")
    if len(actions) and (np.any(actions < lo - TOL) or np.any(actions > hi + TOL)):
        session.close()
        raise BadTrajectory("Actuator targets exceed native joint bounds")
    hand_label = session.hand_info["model"]
    phases = np.full(len(actions), "actuator replay")
    if video:
        try:
            with np.load(path, allow_pickle=False) as archive:
                if "phases" in archive and archive["phases"].shape == (len(actions),) and archive["phases"].dtype.kind in "US":
                    phases = archive["phases"].copy()
        except Exception:  # noqa: BLE001 - phase labels only caption the video: an unreadable
            pass  # member keeps the default labels, never costs the video (review 0146)
    writer = None
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        model = session.model
        # Drawing settings only (every original physics step is replayed): the evidence video uses a coarser wire
        # tessellation and no shadows so the software renderer of the collect hook stays fast.
        if quality == "evidence":
            model.vis.quality.numslices, model.vis.quality.numstacks = 12, 6
            model.vis.quality.offsamples = 1
        model.vis.quality.shadowsize = 2048
        for gid in range(model.ngeom):
            # Hide the Wuji vendor's translucent collision meshes (group 2); colors never enter the physics.
            name = model.geom(gid).name or ""
            if name.startswith("r_wuji_") and "_collision" in name:
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
            writer.append_data(overlay(session.render_frame(pick_camera(session, camera), width, height, quality != "evidence"), session.features(),
                                       "initial state", hand_label))
        for i, (action, phase) in enumerate(zip(actions, phases)):
            f = session.step(action)
            if writer and (i + 1) % stride == 0:
                writer.append_data(overlay(session.render_frame(pick_camera(session, camera), width, height, quality != "evidence"), f, str(phase), hand_label))
            if i % 50 == 0 or i == len(actions) - 1 or session.done:
                timeline.append({"action": i, "phase": str(phase), **{k: v for k, v in f.items() if k != "failure_detail"}})
            if session.done:
                # The episode ends at the first success or the first broken invariant (fail fast);
                # later rows are not executed.
                if writer and (i + 1) % stride:
                    writer.append_data(overlay(session.render_frame(pick_camera(session, camera), width, height, quality != "evidence"), f, str(phase), hand_label))
                break
        features = session.features()
        result = {
            "success": session.success,
            "bad_trajectory": 0,
            "reason": "success" if session.success else (session.failure or ""),
            "hand": session.hand,
            "action_dim": session.action_dim,
            "failure": session.failure,
            "failure_detail": session.failure_detail,
            "n_actions": len(actions),
            "rows_submitted": len(actions),
            "steps": session.steps,
            "initial_sha": session.initial_sha,
            "stage": features["stage"],
            "state_sha": session.state_sha(),
            "verdict": features,
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        }
        if writer:
            from PIL import Image

            final = overlay(session.render_frame("closeup" if session.success else pick_camera(session, camera), width, height, quality != "evidence"), features,
                            "final installed guard" if session.success else "final state", hand_label)
            for _ in range(fps * 2):
                writer.append_data(final)
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
    parser.add_argument("--quality", choices=["evidence", "preview"], default="evidence",
                        help="video drawing settings only; never changes the replayed physics")
    args = parser.parse_args()
    try:
        fps = args.fps if args.fps is not None else (5 if args.trusted_service else 10)
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand, args.width,
                        args.height, args.quality)
    except BadTrajectory as error:
        # The archive's problems (unreadable, wrong width/hand/task, NaN, out-of-range targets) are bad trajectories;
        # any other exception (missing assets, a broken runtime) propagates as an infrastructure error.
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
