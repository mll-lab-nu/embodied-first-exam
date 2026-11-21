"""Fresh-process replay of a sweep_dustpan trajectory (the verifier's only path to a verdict).

    python replay.py --task sweep_dustpan --traj trajectory.npz --out result.json [--trusted-service] [--hand H] [--video out.mp4]

The scene, reset and predicate come from this task directory; the archive contributes only its numeric `actions`
rows and its `hand` label (HAND_INTERFACE.md). Agent-caused problems give success false with bad_trajectory 1 and
exit status 0; any other exception is an infrastructure error (non-zero exit).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import hands
from runtime import ACTION_DIM, TASK_ID, Session, _config

MAX_BYTES = 96_000_000  # expanded members: 160,000 float64 rows of 58 targets are 74.2 MB; the archive file itself is capped at 64 MB by tests/grade.py (save it compressed)


def load(path, trusted: bool, expected_hand: str | None):
    config = _config()
    actions, hand, names = hands.read_trajectory(
        path,
        widths=ACTION_DIM,
        max_rows=None if trusted else int(config["max_rows"]),
        task=TASK_ID,
        allow_empty=trusted,
        max_bytes=MAX_BYTES,
    )
    if expected_hand is not None and hands.canonical(expected_hand) != hand:
        raise hands.HandError(f"trajectory hand {hand!r} differs from the recorded episode hand {expected_hand!r}")
    return actions, hand, names


class Recorder:
    """Evidence frames during the replay (rendering reads the state; it never changes physics or the verdict)."""

    def __init__(self, session: Session, path: Path, camera: str, fps: int, speed: float, overview: bool):
        import imageio.v2 as imageio

        self.session, self.path, self.camera, self.fps, self.speed = session, path, camera, fps, speed
        self.overview = overview
        self.every = max(1, int(round(speed / (fps * session.control_dt))))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.writer = imageio.get_writer(path, fps=fps, codec="libx264", macro_block_size=16, quality=7)
        self.frames = 0

    def frame(self) -> np.ndarray:
        from PIL import Image, ImageDraw

        s = self.session
        status = s.status()
        views = [s.render_frame(self.camera, 640, 480)]
        if self.overview:
            views.append(s.render_frame("overview", 640, 480))
        image = Image.fromarray(np.concatenate(views, axis=1))
        draw = ImageDraw.Draw(image)
        label = "PASS" if status["success"] else ("FAIL: " + status["reason"] if status["failed"] else "IN PROGRESS")
        draw.rectangle((0, 0, image.width, 28), fill=(20, 26, 34))
        draw.text((10, 7), f"sweep_dustpan | {s.hand} | t={status['time_s']:.2f}s | in pan {status['in_pan']}/6 | "
                  f"{label} | native replay {self.speed:g}x", fill=(235, 238, 242))
        return np.asarray(image)

    def tick(self, steps: int, force: bool = False) -> None:
        if force or steps % self.every == 0:
            self.writer.append_data(self.frame())
            self.frames += 1

    def close(self) -> dict:
        last = self.frame()
        for _ in range(self.fps * 2):
            self.writer.append_data(last)
            self.frames += 1
        self.writer.close()
        return {"path": str(self.path), "fps": self.fps, "playback_speed": self.speed, "frames": self.frames,
                "camera": self.camera, "final_hold_s": 2,
                "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--traj", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--trusted-service", action="store_true")
    parser.add_argument("--hand")
    parser.add_argument("--video")
    parser.add_argument("--camera", default="work")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--speed", type=float, default=4.0, help="playback speed of the evidence video")
    parser.add_argument("--overview", action="store_true", help="add the overview camera next to --camera")
    args = parser.parse_args()
    out = Path(args.out)
    result = {"success": False, "bad_trajectory": 0, "state_sha": "", "steps": 0, "stage": 0, "n_actions": 0,
              "reason": "", "hand": args.hand or "", "task": args.task}
    def reject(error) -> None:
        result.update(bad_trajectory=1, error=str(error)[:500])
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, sort_keys=True))

    try:
        if args.task != TASK_ID:
            raise hands.HandError(f"unknown task {args.task!r}")
        actions, hand, names = load(args.traj, args.trusted_service, args.hand)
    except Exception as error:  # the archive is the only input of this stage: any failure is the archive's
        return reject(f"{type(error).__name__}: {error}")
    result.update(hand=hand, n_actions=int(len(actions)))
    session = Session(TASK_ID, hand=hand)  # a broken task install is an infrastructure error, not the agent's
    try:
        if names is not None and names != session.actuator_names:
            raise hands.HandError("actuator_names differ from this hand's actuator order")
        if len(actions):
            session.validate(actions)
    except (ValueError, TypeError) as error:
        session.close()
        return reject(error)
    recorder = None
    if args.video:
        try:
            recorder = Recorder(session, Path(args.video), args.camera, args.fps, args.speed, args.overview)
            recorder.tick(0, force=True)
        except Exception as error:  # evidence only
            result["video_error"] = str(error)[:300]
            recorder = None
    session.reset()
    for row in actions:
        if session.checker.done:
            break
        session._advance(row)
        if recorder is not None:
            try:
                recorder.tick(session.steps)
            except Exception as error:  # evidence only; never stops the replay
                result["video_error"] = str(error)[:300]
                recorder = None
    status = session.status()
    result.update(
        success=bool(status["success"]),
        steps=int(status["steps"]),
        stage=int(status["stage"]),
        reason=status["reason"],
        state_sha=session.state_sha(),
        physics_sha=session.physics_sha(),
        initial_sha=session.initial_sha,
        trajectory_sha256=hashlib.sha256(Path(args.traj).read_bytes()).hexdigest(),
        scene_sha256=session.scene_sha256,
        verdict=session.features(),
    )
    if recorder is not None:
        try:
            result["video"] = recorder.close()
        except Exception as error:
            result["video_error"] = str(error)[:300]
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    session.close()
    print(json.dumps({k: v for k, v in result.items() if k != "verdict"}, sort_keys=True))


if __name__ == "__main__":
    main()
