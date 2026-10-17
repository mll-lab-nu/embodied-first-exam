"""Fresh frozen-instance replay of a batter-whisk trajectory; archive metadata cannot change the scene."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np

from runtime import Session
from scene import hands

TASK = "batter_whisk"
# Marvin rig: 14 arm joint targets (left J1-J7, right J1-J7), then the left and the right hand's finger targets.
WIDTHS = {"sharpa": 58, "wuji": 54}
MAX_ROWS = 4000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget (board 0136): longer episodes are filmed at a larger stride
VIDEO_LABEL = {"speed": 1}   # the overlay's playback speed, set by replay() from the filmed stride
MAX_BYTES = 64_000_000  # the archive file and its expanded members (tests/grade.py: the same 64 MB)


class BadTrajectory(ValueError):
    """An agent-caused problem with the archive or its rows (reported as bad_trajectory, exit 0)."""


def load_trajectory(path, allow_empty=False):
    """Validate an agent or service archive and return ``(actions, hand, actuator_names)``.

    ``actions`` is the only numeric input. ``hand`` (default ``sharpa``) selects the frozen scene to rebuild;
    the width must equal that hand's action width exactly. Optional ``task`` / ``actuator_names`` must match.
    Every other member (claimed success, states, configs) is ignored.
    """
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Trajectory archive exceeds 64 MB")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 32 or sum(item.file_size for item in entries) > MAX_BYTES:
            raise ValueError("Expanded archive exceeds 64 MB")
        members = [item for item in entries if item.filename == "actions.npy"]
        if len(members) != 1:
            raise ValueError("Expected exactly one actions.npy member")
        with archive.open(members[0]) as stream:
            version = np.lib.format.read_magic(stream)
            if version == (1, 0):
                shape, _fortran, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=10000)
            elif version == (2, 0):
                shape, _fortran, dtype = np.lib.format.read_array_header_2_0(stream, max_header_size=10000)
            else:
                raise ValueError("Unsupported NumPy array format")
            minimum = 0 if allow_empty else 1
            if (
                len(shape) != 2
                or shape[1] not in WIDTHS.values()
                or not minimum <= shape[0] <= MAX_ROWS
                or dtype.kind not in "fiu"
            ):
                raise ValueError("Invalid action array header")
            if stream.tell() + shape[0] * shape[1] * dtype.itemsize != members[0].file_size:
                raise ValueError("Action array header differs from its payload")
    actions, hand, names = hands.read_trajectory(
        path, widths=WIDTHS, max_rows=MAX_ROWS, task=TASK, allow_empty=allow_empty, max_bytes=MAX_BYTES
    )
    if (len(actions) == 0 and not allow_empty) or len(actions) > MAX_ROWS or not np.isfinite(actions).all():
        raise ValueError(f"Expected 1 to {MAX_ROWS} finite action rows")
    return np.asarray(actions, dtype=np.float64), hand, names


def load_actions(path, allow_empty=False):
    """Validated actions only (any supported hand); see ``load_trajectory``."""
    return load_trajectory(path, allow_empty)[0]


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
        label = "FAIL: " + status["failure"]
    draw.rectangle((0, 0, frame.shape[1], round(96 * scale)), fill=(28, 30, 34))
    phase = str(phase).replace("\n", " ").replace("\r", " ")[:64]
    draw.text((round(18 * scale), round(10 * scale)), f"{hand} | whisk batter | {label} | {phase}", font=font,
              fill="white")
    draw.text(
        (round(18 * scale), round(39 * scale)),
        f"Stage {status['stage']}/5 | revolutions {status['revolutions']:.2f}/5 | drain {status['drain_steps']}/25 | "
        f"set-down hold {status['hold_steps']}/50 | bowl tilt {status['bowl_tilt_deg']:.1f} deg",
        font=font,
        fill=(244, 214, 157),
    )
    draw.text(
        (round(18 * scale), round(67 * scale)),
        f"Native actuator replay, {VIDEO_LABEL['speed']:g}x | "
        "batter not simulated: whisking = whisk-head revolutions in the batter volume",
        font=font,
        fill=(185, 205, 185),
    )
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=10, trusted_service=False, expected_hand=None, size=(960, 544)):
    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service)
    except Exception as error:  # noqa: BLE001 - any unreadable archive is the submitter's, never an infra error
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    if expected_hand is not None and hands.canonical(expected_hand) != hand:
        raise BadTrajectory(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    # Scene-build or runtime errors past this point are infrastructure errors: they are not caught (non-zero exit).
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
                labels = archive["phases"] if "phases" in archive else None
                if labels is not None and labels.shape == (len(actions),) and labels.dtype.kind in "US":
                    phases = labels.copy()
        except Exception:  # noqa: BLE001 - phase labels only caption the video: an unreadable
            pass  # member keeps the default labels, never costs the video (review 0146)
    writer = None
    width, height = size
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        # Drawing settings only; every physics step is replayed.
        # The bounded service collector renders cheaply (software GL); authoring previews keep antialiasing/shadows.
        session.model.vis.quality.offsamples = 1 if trusted_service else 4
        session.model.vis.quality.shadowsize = 1024 if trusted_service else 4096
        model = session.model
        for gid in range(model.ngeom):
            # Hide the Wuji vendor's translucent collision meshes; its visual meshes stay. Colors never enter physics.
            if (model.geom(gid).name or "").startswith("r_wuji_") and "_collision" in model.geom(gid).name:
                model.geom_rgba[gid, 3] = 0.0
        writer = imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=16)
    stride = max(1, round(1 / (session.control_dt * fps)))
    if video:
        # Board 0136: at most VIDEO_MAX_FRAMES filmed steps, so the longest archive the row limit allows is filmed
        # within the grader's time. Frames only read the scene: physics, verdict and state hash are unchanged.
        stride = max(stride, -(-len(actions) // VIDEO_MAX_FRAMES))
        VIDEO_LABEL["speed"] = round(stride * session.control_dt * fps, 3)

    def frame():
        return session.render_frame(camera, width, height, shadows=not trusted_service)

    timeline = []
    try:
        if writer:
            writer.append_data(overlay(frame(), session.status(), "initial state",
                                       hand_label))
        for i, (action, phase) in enumerate(zip(actions, phases)):
            session.step(action)
            st = None
            if writer and (i + 1) % stride == 0:
                st = session.status()
                writer.append_data(overlay(frame(), st, str(phase), hand_label))
            if i % 50 == 0 or i == len(actions) - 1 or session.done:
                st = st or session.status()
                timeline.append({"action": i, "phase": str(phase), "stage": st["stage"],
                                 "revolutions": round(st["revolutions"], 4), "reason": st["reason"]})
            if session.done:
                # The episode ends at the first success or failure; later rows are not executed.
                if writer and (i + 1) % stride:
                    writer.append_data(overlay(frame(), session.status(),
                                               str(phase), hand_label))
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
            "rows_submitted": len(actions),
            "steps": session.steps,
            "initial_sha": session.initial_sha,
            "stage": status["stage"],
            "total_stages": status["total_stages"],
            "state_sha": session.state_sha(),
            "verdict": status,
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        }
        if writer:
            from PIL import Image

            final = overlay(frame(), status,
                            "final: whisk set down" if session.success else "final state", hand_label)
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


if __name__ == "__main__":
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
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand,
                        (args.width, args.height))
    except BadTrajectory as error:  # only the archive-read / validation phase; everything else is an infra error
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
