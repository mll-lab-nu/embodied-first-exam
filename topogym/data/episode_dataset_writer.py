from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from topogym.generation import EpisodeStatus
from topogym.utils.recording import update_dynamic_camera

from . import h5_schema


def _as_numpy(value) -> np.ndarray:
    """Convert a Genesis/torch value to numpy, handling CUDA tensors."""
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def _grab_rgb(cam) -> np.ndarray:
    """Render one camera to an HxWx3 uint8 RGB array (Genesis render())."""
    out = cam.render()
    rgb = out[0] if isinstance(out, tuple) else out
    arr = np.asarray(rgb)
    if arr.ndim == 3 and arr.shape[-1] >= 3:
        arr = arr[..., :3]
    return np.ascontiguousarray(arr.astype(np.uint8))


def _proprio(controller) -> dict[str, Any]:
    """Read the robot's proprioceptive state through the controller's public API."""
    pos = np.asarray(controller.hand_pos(), dtype=np.float32).reshape(3)
    quat = np.asarray(controller.hand_quat(), dtype=np.float32).reshape(4)
    eef = np.concatenate([pos, quat]).astype(np.float32)
    gripper = np.asarray(controller.gripper_qpos(), dtype=np.float32).reshape(-1)
    open_q = float(controller.cfg.gripper.open_qpos)
    closed_q = float(controller.cfg.gripper.closed_qpos)
    is_close = abs(float(controller.current_gripper_qpos) - closed_q) < 0.5 * abs(
        open_q - closed_q
    )
    total = int(controller.arm_joint_count) + int(controller.gripper_joint_count)
    full = _as_numpy(controller.robot.get_qpos()).reshape(-1, total)[0]
    joints = full[: int(controller.arm_joint_count)].astype(np.float32)
    return {
        "eef_state": eef,
        "gripper_state": gripper,
        "is_gripper_close": bool(is_close),
        "joint_state": joints,
    }


class EpisodeDatasetWriter:
    """Capture per-timestep obs/action/info to a RoboMME-structural HDF5 file.

    Reuses the ``scene.step`` wrapping trick from ``utils.recording`` so any
    caller (controllers, primitives, the demo loop) drives capture without
    knowing about it. Use as a context manager wrapping the run; call
    ``finalize(result)`` before the ``with`` block exits so the episode's
    status/success land in the file. The file is written on clean exit only.

    ``every_n_steps`` strides over physics substeps -- one dataset frame per N
    ``scene.step()`` calls -- to keep files at action granularity (dense
    per-substep rgb would be enormous). See ``h5_schema`` for the layout.
    """

    def __init__(
        self,
        path,
        scene,
        cameras: dict,
        controller,
        *,
        spec,
        plan=None,
        task_goal: str,
        camera_names: Sequence[str] = ("front", "wrist"),
        every_n_steps: int = 10,
        subgoal_label_fn: Callable[[], str] | None = None,
    ) -> None:
        self.path = Path(path)
        self.scene = scene
        self.controller = controller
        self.spec = spec
        self.plan = plan
        self.task_goal = str(task_goal)
        self.every_n_steps = max(1, int(every_n_steps))
        self.subgoal_label_fn = subgoal_label_fn
        self.cam_items = [(name, cameras[name]) for name in camera_names if name in cameras]
        if not self.cam_items:
            raise KeyError(
                f"None of the dataset cameras {tuple(camera_names)} exist in scene "
                f"cameras {sorted(cameras)}."
            )
        self._frames: list[dict] = []
        self._orig_step = None
        self._count = 0
        self._result = None
        self._capturing = True

    def __enter__(self) -> "EpisodeDatasetWriter":
        self._orig_step = self.scene.step

        def wrapped_step(*args, **kwargs):
            self._orig_step(*args, **kwargs)
            if not self._capturing:
                return
            self._count += 1
            if self._count % self.every_n_steps == 0:
                self._capture()

        self.scene.step = wrapped_step
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.scene.step = self._orig_step
        if exc_type is None:
            self._write()
        return False

    def finalize(self, result) -> None:
        """Record the episode's final result so status/success reach the file."""
        self._result = result

    def stop_capture(self) -> None:
        """Stop appending frames while leaving ``scene.step`` wrapped.

        Call before post-task cleanup (e.g. ``reset_home``, which teleports the
        arm via ``set_dofs_position``) so those non-demonstration frames -- and
        the un-replayable teleport action they imply -- do not land in the
        dataset. ``scene.step`` is still restored normally on exit.
        """
        self._capturing = False

    def _default_subgoal(self) -> str:
        if self.plan is not None and self.plan.subgoals:
            return self.plan.subgoals[0].label()
        return ""

    def _capture(self) -> None:
        obs: dict[str, Any] = {}
        for name, cam in self.cam_items:
            update_dynamic_camera(cam)  # wrist cam follows the arm; move it first
            obs[f"{name}_rgb"] = _grab_rgb(cam)
        obs.update(_proprio(self.controller))
        subgoal = (
            self.subgoal_label_fn() if self.subgoal_label_fn else self._default_subgoal()
        )
        self._frames.append({"obs": obs, "subgoal": str(subgoal)})

    def _write(self) -> None:
        import h5py

        if not self._frames:
            raise RuntimeError(
                "EpisodeDatasetWriter captured no frames; lower every_n_steps or "
                "check that the run actually stepped the scene."
            )
        eefs = [frame["obs"]["eef_state"] for frame in self._frames]
        # action = absolute next-step eef pose (behavior-cloning target); the
        # last frame repeats its own pose since there is no next one.
        actions = [eefs[min(i + 1, len(eefs) - 1)] for i in range(len(eefs))]

        status = (
            self._result.status.value
            if self._result is not None
            else EpisodeStatus.ONGOING.value
        )
        success = bool(self._result.success) if self._result is not None else False

        # Subgoal boundary = first frame, last frame, or whenever the subgoal
        # label changes (so multi-subgoal tasks get real boundaries, not just
        # start/end).
        subgoals = [frame["subgoal"] for frame in self._frames]
        last_i = len(subgoals) - 1
        boundaries = [
            i == 0 or i == last_i or subgoals[i] != subgoals[i - 1]
            for i in range(len(subgoals))
        ]

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(self.path, "w") as handle:
            handle.attrs["schema_version"] = h5_schema.SCHEMA_VERSION
            episode = handle.create_group("episode_0")
            self._write_setup(episode, status=status, success=success)
            for index, frame in enumerate(self._frames):
                self._write_timestep(
                    episode,
                    index,
                    frame,
                    action=actions[index],
                    status=status,
                    success=success,
                    is_boundary=boundaries[index],
                    last=index == last_i,
                )

    def _write_setup(self, episode, *, status: str, success: bool) -> None:
        setup = episode.create_group("setup")
        setup.attrs["stable_id"] = self.spec.stable_id()
        setup.attrs["task_id"] = self.spec.task_id
        setup.attrs["seed"] = int(self.spec.seed)
        setup.attrs["preset_id"] = self.spec.key.preset_id
        setup.attrs["variant_id"] = self.spec.key.variant_id
        setup.attrs["difficulty"] = str(self.spec.variant.difficulty)
        setup.attrs["task_goal"] = self.task_goal
        setup.attrs["status"] = status
        setup.attrs["success"] = success
        setup.attrs["every_n_steps"] = int(self.every_n_steps)
        setup.attrs["camera_names"] = np.array(
            [name for name, _ in self.cam_items], dtype="S"
        )
        if self.plan is not None:
            setup.attrs["plan_id"] = self.plan.plan_id
            setup.create_dataset(
                "subgoals",
                data=np.array([s.label() for s in self.plan.subgoals], dtype="S"),
            )
            waypoints = self.plan.waypoints
            if waypoints:
                setup.create_dataset(
                    "waypoints",
                    data=np.array([w.position for w in waypoints], dtype=np.float32),
                )
                setup.create_dataset(
                    "waypoint_labels",
                    data=np.array([w.label for w in waypoints], dtype="S"),
                )

    def _write_timestep(
        self, episode, index, frame, *, action, status, success, is_boundary, last
    ) -> None:
        ts = episode.create_group(f"timestep_{index}")
        obs_group = ts.create_group("obs")
        for key, value in frame["obs"].items():
            if key.endswith("_rgb"):
                obs_group.create_dataset(
                    key, data=value, compression="gzip", compression_opts=4
                )
            else:
                obs_group.create_dataset(key, data=np.asarray(value))
        action_group = ts.create_group("action")
        action_group.create_dataset(
            "ee_pose_action", data=np.asarray(action, dtype=np.float32)
        )
        info_group = ts.create_group("info")
        info_group.attrs["task_goal"] = self.task_goal
        info_group.attrs["simple_subgoal"] = frame["subgoal"]
        info_group.attrs["is_subgoal_boundary"] = bool(is_boundary)
        info_group.attrs["is_completed"] = bool(success and last)
        info_group.attrs["status"] = status


def dataset_writer_or_null(
    record_path,
    *,
    scene,
    cameras: dict,
    controller,
    spec,
    task_goal: str,
    plan=None,
    every_n_steps: int = 10,
    subgoal_label_fn: Callable[[], str] | None = None,
):
    """Return an ``EpisodeDatasetWriter`` context, or a no-op when disabled.

    Lets a demo wire dataset recording in one call: pass ``--record-dataset``'s
    path (or ``None`` to disable). The returned object is a context manager; when
    it is a real writer, call ``.finalize(result)`` before the ``with`` exits.
    """
    if record_path is None:
        return contextlib.nullcontext()
    return EpisodeDatasetWriter(
        record_path,
        scene,
        cameras,
        controller,
        spec=spec,
        plan=plan,
        task_goal=task_goal,
        every_n_steps=every_n_steps,
        subgoal_label_fn=subgoal_label_fn,
    )
