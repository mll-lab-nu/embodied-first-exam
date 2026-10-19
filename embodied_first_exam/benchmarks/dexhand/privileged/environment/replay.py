"""Replay a submitted trajectory in a fresh simulator process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile

import numpy as np

import essential
import hands
from runtime import SUPPORTED_HANDS, Session, actuator_targets_in_range, locked_wrist_targets_match

ACTION_DIM = 6 + 22
MAX_ROWS = 50_000
VIDEO_MAX_FRAMES = 1500   # the replay video's frame budget (60 s at 25 fps)


def load_actions(path: str | Path, max_rows: int | None = MAX_ROWS) -> np.ndarray:
    """Read only finite numeric actions; never load pickles from an agent artifact."""
    if max_rows is not None and Path(path).stat().st_size > 32_000_000:
        raise ValueError("trajectory exceeds the 32 MB artifact limit")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if max_rows is not None and (sum(item.file_size for item in entries) > 32_000_000 or len(entries) > 32):
            raise ValueError("trajectory exceeds the 32 MB uncompressed artifact limit")
        action_entries = [item for item in entries if item.filename == "actions.npy"]
        if len(action_entries) != 1:
            raise ValueError("trajectory must contain exactly one actions.npy member")
        member = action_entries[0]
        with archive.open(member) as stream:
            version = np.lib.format.read_magic(stream)
            if version == (1, 0):
                shape, _fortran, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=10_000)
            elif version == (2, 0):
                shape, _fortran, dtype = np.lib.format.read_array_header_2_0(stream, max_header_size=10_000)
            else:
                raise ValueError("actions must use NumPy array format version 1 or 2")
            if (
                len(shape) != 2
                or shape[1] != ACTION_DIM
                or dtype.kind not in "fiu"
                or (max_rows is not None and shape[0] > max_rows)
            ):
                raise ValueError(f"actions header must describe a numeric (T, {ACTION_DIM}) array")
            expected_bytes = shape[0] * shape[1] * dtype.itemsize
            if stream.tell() + expected_bytes != member.file_size:
                raise ValueError("actions header shape does not match the member payload size")
    with np.load(path, allow_pickle=False) as archive:
        actions = archive["actions"]
    if actions.ndim != 2 or actions.shape[1] != ACTION_DIM or (max_rows is not None and len(actions) > max_rows):
        raise ValueError(f"actions must have shape (T, {ACTION_DIM}), T <= {max_rows}")
    if actions.dtype.kind not in "fiu" or not np.isfinite(actions).all():
        raise ValueError("actions must contain finite numeric values")
    return np.asarray(actions, dtype=np.float64)


def _bad(args, error: str, hand: str | None = None) -> dict:
    return {"success": False, "bad_trajectory": 1, "error": error[:500], "hand": hand or "sharpa",
            "state_sha": "", "steps": 0, "stage": 0, "n_actions": 0, "reason": "bad_trajectory", "video": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--traj", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--video")
    parser.add_argument("--hand", help="Trusted service hand; must equal the archive's hand")
    parser.add_argument("--trusted-service", action="store_true")
    args = parser.parse_args()
    try:
        widths = {hand: ACTION_DIM - 22 + hands.HANDS[hand]["finger_actuators"] for hand in SUPPORTED_HANDS}
        actions, hand, names = hands.read_trajectory(
            args.traj, widths=widths, max_rows=None if args.trusted_service else MAX_ROWS, task=args.task,
            allow_empty=args.trusted_service)
        if args.hand is not None and hands.canonical(args.hand) != hand:
            raise hands.HandError(f"archive hand {hand!r} differs from the service hand {args.hand!r}")
    except Exception as error:  # noqa: BLE001 - any unreadable agent archive is a clean failure, never a crash
        Path(args.out).write_text(json.dumps(_bad(args, f"{type(error).__name__}: {error}"), sort_keys=True))
        return
    try:
        session = Session(args.task, hand=hand)
    except hands.HandError as error:  # a hand this family does not offer: the archive's fault, a clean 0
        Path(args.out).write_text(json.dumps(_bad(args, f"{type(error).__name__}: {error}", hand), sort_keys=True))
        return
    limits = session.model.actuator_ctrlrange
    bad_targets = not actuator_targets_in_range(actions, limits, session.spec)
    if essential.is_essential(session.spec):
        bad_targets |= not locked_wrist_targets_match(actions[:, :6], session.spec)
    if names is not None and names != list(session.actuator_names):
        bad_targets = True
    if bad_targets:
        result = {**_bad(args, "targets outside the declared ranges, locked wrist moved or actuator names differ", hand),
                  "state_sha": session.state_sha(), "n_actions": int(len(actions))}
        Path(args.out).write_text(json.dumps(result, sort_keys=True))
        return
    session.reset()
    for row in actions:
        session.step(row)
        if session.status()["done"]:
            break
    status = session.status()
    result = dict(status)
    result["state_sha"] = session.state_sha()
    result["n_actions"] = int(len(actions))
    result["hand"] = hand
    result["bad_trajectory"] = 0
    result["video"] = False
    Path(args.out).write_text(json.dumps(result, sort_keys=True))
    if args.video:
        import imageio.v2 as imageio

        # Every 2nd step, but at most VIDEO_MAX_FRAMES frames (board 0136): a 640x480 OSMesa frame costs ~0.3 s on
        # one core, so a 28k-step episode took over an hour to film. Rendering only reads the scene; the verdict above
        # is already written and this pass is a separate replay from the reset.
        steps = int(result.get("steps") or len(actions))   # the verdict pass's executed steps (an episode may end early)
        stride = max(2, -(-steps // VIDEO_MAX_FRAMES))
        session.reset()
        with imageio.get_writer(args.video, fps=25, codec="libx264", macro_block_size=1) as writer:
            writer.append_data(session.render_frame("overview"))
            index = last = -1
            for index, action in enumerate(actions):
                session.step(action)
                if index % stride == 0:
                    writer.append_data(session.render_frame("overview"))
                    last = index
                if session.status()["done"]:
                    break
            if last != index:
                writer.append_data(session.render_frame("overview"))   # the final state
        result["video"] = True
        result["video_stride"] = stride
        Path(args.out).write_text(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
