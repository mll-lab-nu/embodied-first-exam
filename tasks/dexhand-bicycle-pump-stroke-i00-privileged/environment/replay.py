"""Fresh-process replay of a bicycle_pump_stroke trajectory (privileged grader and trusted service collector).

python replay.py --task bicycle_pump_stroke --traj trajectory.npz --out result.json [--trusted-service] [--hand H]
                 [--video replay.mp4]

Only the `actions` rows (and the optional `hand`, `task`, `actuator_names` labels) are read; every other member of
the archive is ignored. The scene, reset and predicate come from this task directory. Agent-caused problems exit 0
with `bad_trajectory = 1`; only infrastructure problems exit non-zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from runtime import TASK, Session
from scene import hands

WIDTHS = {"sharpa": 58, "wuji": 54}  # 14 Marvin arm targets + the left and the right hand's finger actuators
MAX_ROWS = 5000
VIDEO_MAX_FRAMES = 300   # the replay video's frame budget (board 0136): longer episodes are filmed at a larger stride


def load(path, trusted: bool, hand_arg: str | None):
    actions, hand, names = hands.read_trajectory(
        path, widths=WIDTHS, max_rows=None if trusted else MAX_ROWS, task=TASK, allow_empty=trusted)
    if hand_arg is not None and hands.canonical(hand_arg) != hand:
        raise hands.HandError(f"trajectory hand {hand!r} differs from the recorded episode hand {hand_arg!r}")
    return actions, hand, names


def overlay(frame, status: dict, hand_label: str, camera: str):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    scale = image.width / 1280
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", round(19 * scale))
    except OSError:
        font = ImageFont.load_default()
    label = "SUCCESS" if status["success"] else ("FAIL: " + status["reason"] if status["failed"] else "running")
    draw.rectangle((0, 0, image.width, round(70 * scale)), fill=(24, 34, 30))
    draw.text((round(14 * scale), round(8 * scale)),
              f"{hand_label} | portable bicycle pump | {camera} | {label}", font=font, fill=(255, 255, 255))
    draw.text((round(14 * scale), round(38 * scale)),
              f"t={status['steps'] * 0.02:5.2f}s  strokes {status['strokes']}/{status['required_strokes']}  "
              f"tire {status['tire_gauge_pa'] / 1000:.2f} kPa gauge (target {status['target_gauge_pa'] / 1000:.1f})  "
              f"handle depth {status['piston_depth_m'] * 1000:5.1f} mm  pump tilt {np.degrees(status['pump_tilt_rad']):4.1f} deg  "
              f"released hold {status['released_hold_steps']}/50",
              font=font, fill=(240, 214, 150))
    return np.asarray(image)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default=TASK)
    parser.add_argument("--traj", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--trusted-service", action="store_true")
    parser.add_argument("--hand")
    parser.add_argument("--video")
    parser.add_argument("--camera", default="overview")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=544)
    parser.add_argument("--shadows", action="store_true", help="render shadows (slower; evidence videos only)")
    parser.add_argument("--fps", type=int, choices=[5, 10, 25, 50])
    args = parser.parse_args()
    # The trusted service renders with software OpenGL inside a bounded collect hook: fewer frames, same physics.
    args.fps = args.fps or (5 if args.trusted_service else 10)
    out = Path(args.out)
    result = {"success": False, "bad_trajectory": 0, "state_sha": "", "steps": 0, "stage": 0, "n_actions": 0,
              "reason": "", "hand": args.hand or "sharpa"}

    def reject(error) -> int:
        result.update(bad_trajectory=1, reason="bad_trajectory", error=f"{type(error).__name__}: {error}"[:500])
        out.write_text(json.dumps(result, sort_keys=True))
        print(json.dumps(result, sort_keys=True))
        return 0

    # 1. The archive is agent input: anything wrong with it (or a crafted member) is a rejected trajectory.
    try:
        if args.task != TASK:
            raise hands.HandError(f"unknown task {args.task!r}")
        actions, hand, names = load(args.traj, args.trusted_service, args.hand)
    except Exception as error:  # noqa: BLE001 - every failure to parse agent input is the agent's
        return reject(error)
    result["hand"] = hand
    result["n_actions"] = int(len(actions))
    # 2. The frozen scene is the task's own: a failure here is an infrastructure error (non-zero exit).
    session = Session(TASK, hand=hand)
    # 3. Labels and every row are checked against the scene before any physics runs.
    try:
        if names is not None and names != session.actuator_names:
            raise hands.HandError("actuator_names differ from this task's actuator order for that hand")
        for row in actions:
            session.validate(row)
    except ValueError as error:
        return reject(error)
    status = session.replay(actions)
    result.update(
        success=bool(status["success"]),
        state_sha=session.state_sha(),
        initial_sha=session.initial_sha,
        steps=int(status["steps"]),
        stage=int(status["stage"]),
        reason=status["reason"],
        failure_detail=status["failure_detail"],
        strokes=int(status["strokes"]),
        stroke_controls=status["stroke_controls"],
        tire_gauge_pa=float(status["tire_gauge_pa"]),
        features={k: v for k, v in status.items() if k not in ("success", "steps", "stage", "reason", "hand")},
        trajectory_sha256=hashlib.sha256(Path(args.traj).read_bytes()).hexdigest(),
        scene_sha256=hashlib.sha256(session.xml.encode()).hexdigest(),
        video=False,
    )
    out.write_text(json.dumps(result, sort_keys=True, default=float))
    if args.video:
        import imageio.v2 as imageio

        model = session.model
        for gid in range(model.ngeom):
            # Hide the Wuji vendor's translucent collision meshes; its visual meshes stay. Colours never enter physics.
            if session.owner.get(int(model.geom_bodyid[gid])) == "hand" and "_collision" in (model.geom(gid).name or "") \
                    and (model.geom(gid).name or "").startswith("r_wuji_"):
                model.geom_rgba[gid, 3] = 0.0
        session.reset()
        every = max(1, round(1.0 / (session.control_dt * args.fps)))
        if args.video:
            # Board 0136: at most VIDEO_MAX_FRAMES filmed steps, so the longest archive the row limit allows is filmed
            # within the grader's time. Frames only read the scene: physics, verdict and state hash are unchanged.
            every = max(every, -(-len(actions) // VIDEO_MAX_FRAMES))
        label = session.hand_info["model"]

        def frame():
            return overlay(session.render_frame(args.camera, width=args.width, height=args.height,
                                                shadows=args.shadows), session.status(), label, args.camera)

        with imageio.get_writer(args.video, fps=args.fps, codec="libx264", macro_block_size=8, quality=8) as writer:
            writer.append_data(frame())
            for index, row in enumerate(actions):
                if session.done:
                    break
                session.step(row)
                if (index + 1) % every == 0 or session.done:
                    writer.append_data(frame())
            final = frame()
            for _ in range(args.fps):
                writer.append_data(final)
        result["video"] = True
        result["video_sha256"] = hashlib.sha256(Path(args.video).read_bytes()).hexdigest()
        result["video_stride"] = every
        if session.state_sha() != result["state_sha"]:
            raise RuntimeError("video replay diverged from the verdict replay")
        out.write_text(json.dumps(result, sort_keys=True, default=float))
        session.close()
    print(json.dumps({k: v for k, v in result.items() if k not in ("features", "stroke_controls")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
