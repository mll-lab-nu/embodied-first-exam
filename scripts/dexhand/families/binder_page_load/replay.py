"""Fresh frozen-instance replay of a binder_page_load trajectory; archive metadata cannot change the scene."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np

from runtime import Session
from scene import hands

TASK = "binder_page_load"
# Six wrist-stage targets followed by the selected hand's native finger actuators.
WIDTHS = {"sharpa": 28, "wuji": 26}
MAX_ROWS = 6000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget (board 0136): longer episodes are filmed at a larger stride
VIDEO_LABEL = {"speed": 1}   # the overlay's playback speed, set by replay() from the filmed stride
MAX_BYTES = 64_000_000  # the archive file and its expanded members (tests/grade.py: the same 64 MB)


class BadTrajectory(ValueError):
    """The submitted archive is unusable (agent-caused): reported as bad_trajectory, exit 0."""


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


def overlay(frame, features, phase, hand="Sharpa Wave"):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(19 * scale))
    except OSError:
        font = ImageFont.load_default(size=round(19 * scale))
    label = "PASS" if features["success"] else "INCOMPLETE"
    if features["failure"]:
        label = "FAIL: " + features["failure"]
    draw.rectangle((0, 0, frame.shape[1], round(96 * scale)), fill=(23, 35, 29))
    phase = str(phase).replace("\n", " ").replace("\r", " ")[:64]
    draw.text(
        (round(18 * scale), round(10 * scale)),
        hand + " | ring binder page loading | " + label + " | " + phase,
        font=font,
        fill="white",
    )
    draw.text(
        (round(18 * scale), round(39 * scale)),
        f"Stage {features['stage']}/4 | rings {np.round(features['toggles_rad'][1], 2)} rad | holes threaded "
        f"{sum(features['open_threaded'])}/6 linked {sum(features['linked'])}/6 | hold {features['hold_steps']}/50",
        font=font,
        fill=(244, 214, 157),
    )
    draw.text(
        (round(18 * scale), round(67 * scale)),
        f"Native actuator replay, {VIDEO_LABEL['speed']:g}x | passive over-centre ring mechanism, rigid punched pages",
        font=font,
        fill=(185, 205, 185),
    )
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=10, trusted_service=False, expected_hand=None):
    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service)
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise ValueError(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    except Exception as error:  # noqa: BLE001 - any unreadable archive is the submitter's, never an infra error
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    # Scene build and simulation errors below are infrastructure errors (non-zero exit), never bad trajectories.
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
                if (
                    "phases" in archive
                    and archive["phases"].shape == (len(actions),)
                    and archive["phases"].dtype.kind in "US"
                ):
                    phases = archive["phases"].copy()
        except Exception:  # noqa: BLE001 - phase labels only caption the video: an unreadable
            pass  # member keeps the default labels, never costs the video (review 0146)
    writer = None
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        # These are drawing settings only. Every original physics step is replayed.
        session.model.vis.quality.shadowsize = 1024
        session.model.vis.quality.offsamples = 1
        model = session.model
        for gid in range(model.ngeom):
            # Hide the Wuji vendor's translucent collision meshes (group 2); its visual meshes stay. Colors never
            # enter the physics.
            if (
                session.checker.geom_owner[gid] == "hand"
                and (model.geom(gid).name or "").startswith("r_wuji_")
                and "_collision" in model.geom(gid).name
            ):
                model.geom_rgba[gid, 3] = 0.0
        writer = imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=16)
    stride = round(1 / (session.control_dt * fps))
    if video:
        # Board 0136: at most VIDEO_MAX_FRAMES filmed steps, so the longest archive the row limit allows is filmed
        # within the grader's time. Frames only read the scene: physics, verdict and state hash are unchanged.
        stride = max(stride, -(-len(actions) // VIDEO_MAX_FRAMES))
        VIDEO_LABEL["speed"] = round(stride * session.control_dt * fps, 3)
    timeline = []
    try:
        if writer:
            writer.append_data(
                overlay(
                    session.render_frame(camera, width=960, height=544, shadows=False),
                    session.status(),
                    "initial state",
                    hand_label,
                )
            )
        for i, (action, phase) in enumerate(zip(actions, phases)):
            f = session.step(action)
            if writer and (i + 1) % stride == 0:
                frame = session.render_frame(camera, width=960, height=544, shadows=False)
                writer.append_data(overlay(frame, f, str(phase), hand_label))
            if writer and i % 500 == 0:
                print(f"Recorded native action {i}/{len(actions)}", flush=True)
            if i % 50 == 0 or i == len(actions) - 1 or session.done:
                timeline.append({"action": i, "phase": str(phase), **{k: v for k, v in f.items() if k != "holes"}})
            if session.done:
                # The episode ends at the first success or the first broken invariant (fail fast);
                # later rows are not executed.
                if writer and (i + 1) % stride:
                    frame = session.render_frame(camera, width=960, height=544, shadows=False)
                    writer.append_data(overlay(frame, f, str(phase), hand_label))
                break
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
            "stage": session.stage,
            "stage_steps": list(session.stage_steps),
            "state_sha": session.state_sha(),
            "verdict": {k: v for k, v in session.status().items() if k != "holes"},
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
            "recording": {
                "fps": fps,
                "playback_speed": round(stride * session.control_dt * fps, 3),
                "width": 960,
                "height": 544,
                "shadows": False,
                "shadowsize": 1024,
                "offsamples": 1,
            }
            if video
            else None,
        }
        if writer:
            from PIL import Image

            # A released stack is shown in close-up; any other end state in the overview camera.
            final = overlay(
                session.render_frame("closeup" if session.success else camera, width=960, height=544, shadows=False),
                session.status(),
                "pages loaded, rings closed" if session.success else "final state",
                hand_label,
            )
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
        video.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
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
        # Software rendering in the bounded service collector uses fewer samples.
        # Both defaults execute every original control; the video is 1x up to VIDEO_MAX_FRAMES filmed steps.
        fps = args.fps if args.fps is not None else (5 if args.trusted_service else 10)
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand)
    except BadTrajectory as error:
        result = {
            "success": False,
            "bad_trajectory": 1,
            "reason": "bad_trajectory",
            "error": str(error)[:500],
            "hand": args.hand,
            "n_actions": 0,
            "steps": 0,
            "stage": 0,
        }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "timeline"}, indent=2))
