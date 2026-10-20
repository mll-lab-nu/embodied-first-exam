"""Fresh-process replay of an envelope_letter_insert trajectory (privileged grader and trusted service collector).

python replay.py --task envelope_letter_insert --traj trajectory.npz --out result.json [--trusted-service]
                 [--hand H] [--video replay.mp4]

Only the `actions` rows (and the optional `hand`, `task`, `actuator_names` labels) are read; every other member of
the archive is ignored. The scene, reset and predicate come from this task directory. Agent-caused problems exit 0
with `bad_trajectory = 1`; only infrastructure problems exit non-zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np

from runtime import TASK, Session
from scene import hands

# 14 Marvin arm joint targets (left arm, then right arm), then the left and the right hand's finger targets.
WIDTHS = {"sharpa": 58, "wuji": 54}
MAX_ROWS = 6000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget: longer episodes are filmed at a larger stride
MAX_BYTES = 64_000_000  # the archive file and its expanded members (tests/grade.py: the same 64 MB)


class BadTrajectory(ValueError):
    """An agent-caused archive problem (reported as bad_trajectory, exit 0); never raised for scene/runtime errors."""


def load_trajectory(path, allow_empty=False):
    """Validate an agent or service archive and return ``(actions, hand, actuator_names)``."""
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
                or not minimum <= shape[0] <= (MAX_ROWS if not allow_empty else 10**7)
                or dtype.kind not in "fiu"
            ):
                raise ValueError("Invalid action array header")
            if stream.tell() + shape[0] * shape[1] * dtype.itemsize != members[0].file_size:
                raise ValueError("Action array header differs from its payload")
    actions, hand, names = hands.read_trajectory(
        path, widths=WIDTHS, max_rows=None if allow_empty else MAX_ROWS, task=TASK, allow_empty=allow_empty,
        max_bytes=MAX_BYTES,
    )
    if (len(actions) == 0 and not allow_empty) or not np.isfinite(actions).all():
        raise ValueError(f"Expected 1 to {MAX_ROWS} finite action rows")
    return np.asarray(actions, dtype=np.float64), hand, names


def overlay(frame, f, phase, hand_label):
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.fromarray(frame)
    draw = ImageDraw.Draw(canvas)
    scale = frame.shape[1] / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(19 * scale))
    except OSError:
        font = ImageFont.load_default()
    label = "PASS" if f["success"] else ("FAIL: " + f["failure"] if f["failure"] else "IN PROGRESS")
    draw.rectangle((0, 0, frame.shape[1], round(70 * scale)), fill=(23, 35, 29))
    phase = str(phase).replace("\n", " ")[:60]
    draw.text((round(16 * scale), round(8 * scale)), f"{hand_label} | letter into envelope | {label} | {phase}",
              font=font, fill="white")
    draw.text(
        (round(16 * scale), round(38 * scale)),
        f"t={f['steps'] * 0.02:5.2f}s  stage {f['stage_completed']}/3  inside {100 * f['inserted_fraction']:5.1f}%"
        f"  outside {1000 * f['outside_m']:4.1f} mm  hand contacts L{f['hand_letter_contacts']}/E{f['hand_envelope_contacts']}"
        f"  released hold {f['released_hold_steps']}/50",
        font=font, fill=(244, 214, 157),
    )
    return np.asarray(canvas)


def replay(path, video=None, camera="overview", fps=25, trusted_service=False, expected_hand=None,
           width=960, height=544):
    try:
        actions, hand, names = load_trajectory(path, allow_empty=trusted_service)
        if expected_hand is not None and hands.canonical(expected_hand) != hand:
            raise ValueError(f"Trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    except Exception as error:  # noqa: BLE001 - any unreadable archive is the submitter's, never an infra error
        raise BadTrajectory(f"Invalid trajectory archive: {type(error).__name__}: {error}") from error
    # Scene build / runtime errors below are infrastructure errors: they propagate (non-zero exit).
    session = Session(hand=hand)
    lo, hi = session.model.actuator_ctrlrange.T
    if names is not None and names != session.actuator_names:
        session.close()
        raise BadTrajectory("Trajectory actuator_names differ from the " + hand + " actuator layout")
    if len(actions) and (np.any(actions < lo - 1e-6) or np.any(actions > hi + 1e-6)):
        session.close()
        raise BadTrajectory("Actuator targets exceed native joint bounds")
    hand_label = session.hand_info["model"]
    phases = np.full(len(actions), "actuator replay", dtype=object)
    if video:
        try:
            with np.load(path, allow_pickle=False) as archive:
                if "phases" in archive and archive["phases"].shape == (len(actions),) and archive["phases"].dtype.kind in "US":
                    phases = archive["phases"].astype(str)
        except Exception:  # noqa: BLE001 - phase labels are cosmetic
            pass
    writer = None
    if video:
        import imageio.v2 as imageio

        video = Path(video)
        video.parent.mkdir(parents=True, exist_ok=True)
        model = session.model
        for gid in range(model.ngeom):
            # Hide the Wuji vendor's translucent collision meshes; its visual meshes stay. Colors never enter physics.
            name = model.geom(gid).name or ""
            if session.owner.get(int(model.geom_bodyid[gid])) == "hand" and name.startswith("r_wuji_") and "_collision" in name:
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
            writer.append_data(overlay(session.render_frame(camera, width, height), session.features(),
                                       "initial state", hand_label))
        for i, (action, phase) in enumerate(zip(actions, phases)):
            f = session.step(action)
            if writer and ((i + 1) % stride == 0 or session.done):
                writer.append_data(overlay(session.render_frame(camera, width, height), f, str(phase), hand_label))
            if i % 50 == 0 or i == len(actions) - 1 or session.done:
                timeline.append({"action": i, "phase": str(phase),
                                 **{k: v for k, v in f.items() if k != "corners_envelope_frame"}})
            if session.done:
                # The episode ends at the first success or the first broken invariant (fail fast).
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
            "stage": session.stage,
            "total_stages": status["total_stages"],
            "stage_steps": status["stage_steps"],
            "initial_sha": session.initial_sha,
            "state_sha": session.state_sha(),
            "verdict": {k: v for k, v in status.items() if k not in ("stage_steps",)},
            "timeline": timeline,
            "trajectory_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        }
        if writer:
            final = overlay(session.render_frame("closeup" if session.success else camera, width, height),
                            session.features(), "final state", hand_label)
            for _ in range(fps * 2):
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
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=544)
    parser.add_argument("--hand", help="hand recorded by the trusted service; must equal the archive's hand")
    args = parser.parse_args()
    try:
        fps = args.fps if args.fps is not None else (5 if args.trusted_service else 25)
        result = replay(args.traj, args.video, args.camera, fps, args.trusted_service, args.hand, args.width,
                        args.height)
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
            "state_sha": "",
        }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("timeline", "verdict")}, indent=2))
