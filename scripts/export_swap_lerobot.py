"""Convert a TopoGym episode H5 into a LeRobot dataset OpenPI (pi0.5) can train on.

This is the swap-first smoke path for the RoboMME pipeline: prove a recorded H5
(see ``topogym/data/h5_schema.py`` / ``EpisodeDatasetWriter``) can enter the
pi0.5 training loop without shape/format errors -- NOT to train a real baseline.

It deliberately mirrors OpenPI's own converter,
``examples/libero/convert_libero_data_to_lerobot.py``, so the emitted feature
names (``image`` / ``wrist_image`` / ``state`` / ``actions`` + per-frame
``task``) match what ``LeRobotLiberoDataConfig`` + ``libero_policy`` already
expect. That lets the OpenPI side reuse the Libero data config verbatim, only
swapping ``repo_id``.

Field mapping (H5 -> LeRobot, matching Libero's shapes: state 8, actions 7):
    obs/front_rgb            -> image        (uint8 HxWx3)
    obs/wrist_rgb            -> wrist_image  (uint8 HxWx3; zero-filled if absent)
    obs/joint_state (7) +    -> state        (float32, 8): 7 arm joints + 1 gripper
      mean(obs/gripper_state)
    action/ee_pose_action(7) -> actions      (float32, 7): xyz + quaternion
    setup.attrs.task_goal    -> task         (prompt, via prompt_from_task=True)

Runs inside OpenPI's uv env (it needs ``lerobot``); it does NOT import topogym,
so the tiny H5 read is inlined rather than reusing ``topogym.data.replay``.

Usage (from the openpi checkout, so lerobot is importable):
    uv run --project ../../ python ../../scripts/export_swap_lerobot.py \
        <path/to/swap_seed0.h5> --repo-id topogym/swap_smoke

The dataset is written to ``$HF_LEROBOT_HOME/<repo-id>`` (LeRobot's convention);
the OpenPI train config's ``repo_id`` must equal ``--repo-id``.

KNOWN SCHEMA GAP (expected, not fixed here): ``actions`` is a 7-dim ABSOLUTE
pose whose last 4 dims are a quaternion. pi0.5 conventionally uses joint/ee
deltas, and min-max/mean-std normalization over a quaternion is not meaningful.
Fine for "runs a few steps"; revisit (waypoint/joint or 6D rotation) later.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import h5py
import numpy as np
from lerobot.common.datasets.lerobot_dataset import HF_LEROBOT_HOME, LeRobotDataset


def _decode(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _read_episode(h5_path: Path) -> tuple[list[dict], str]:
    """Read one episode's per-frame frames + its task prompt from a TopoGym H5."""
    with h5py.File(h5_path, "r") as f:
        ep = f["episode_0"]
        task_goal = _decode(ep["setup"].attrs["task_goal"])
        ts_keys = sorted(
            (k for k in ep if k.startswith("timestep_")),
            key=lambda x: int(x.split("_")[1]),
        )
        if not ts_keys:
            raise ValueError(f"{h5_path}: episode_0 has no timestep_* groups.")

        frames: list[dict] = []
        for k in ts_keys:
            obs = ep[k]["obs"]
            front = np.ascontiguousarray(obs["front_rgb"][:], dtype=np.uint8)
            if "wrist_rgb" in obs:
                wrist = np.ascontiguousarray(obs["wrist_rgb"][:], dtype=np.uint8)
            else:
                wrist = np.zeros_like(front)
            joint = np.asarray(obs["joint_state"][:], dtype=np.float32).reshape(-1)
            gripper = np.asarray(obs["gripper_state"][:], dtype=np.float32).reshape(-1)
            state = np.concatenate(
                [joint, np.array([gripper.mean()], dtype=np.float32)]
            ).astype(np.float32)
            action = np.asarray(
                ep[k]["action"]["ee_pose_action"][:], dtype=np.float32
            ).reshape(-1)
            frames.append(
                {"image": front, "wrist_image": wrist, "state": state, "actions": action}
            )
    return frames, task_goal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("h5_path", type=Path, help="Path to a recorded swap episode .h5")
    parser.add_argument(
        "--repo-id",
        default="topogym/swap_smoke",
        help="Output LeRobot dataset id; must match the OpenPI config's repo_id.",
    )
    parser.add_argument("--fps", type=int, default=10, help="Metadata fps (matches Libero).")
    args = parser.parse_args()

    frames, task_goal = _read_episode(args.h5_path)
    img_shape = tuple(int(x) for x in frames[0]["image"].shape)
    wrist_shape = tuple(int(x) for x in frames[0]["wrist_image"].shape)
    state_dim = int(frames[0]["state"].shape[0])
    action_dim = int(frames[0]["actions"].shape[0])
    print(
        f"read {len(frames)} frames from {args.h5_path} | image={img_shape} "
        f"wrist={wrist_shape} state={state_dim} actions={action_dim} | task={task_goal!r}"
    )

    output_path = HF_LEROBOT_HOME / args.repo_id
    if output_path.exists():
        shutil.rmtree(output_path)

    dataset = LeRobotDataset.create(
        repo_id=args.repo_id,
        robot_type="panda",
        fps=args.fps,
        features={
            "image": {"dtype": "image", "shape": img_shape, "names": ["height", "width", "channel"]},
            "wrist_image": {"dtype": "image", "shape": wrist_shape, "names": ["height", "width", "channel"]},
            "state": {"dtype": "float32", "shape": (state_dim,), "names": ["state"]},
            "actions": {"dtype": "float32", "shape": (action_dim,), "names": ["actions"]},
        },
        image_writer_threads=10,
        image_writer_processes=5,
    )

    for frame in frames:
        dataset.add_frame({**frame, "task": task_goal})
    dataset.save_episode()

    print(f"wrote LeRobot dataset -> {output_path}")


if __name__ == "__main__":
    main()
