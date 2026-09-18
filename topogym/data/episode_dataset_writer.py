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
    total = int(controller.robot.n_qs)
    full = _as_numpy(controller.robot.get_qpos()).reshape(-1, total)[0]
    joints = full[: int(controller.arm_joint_count)].astype(np.float32)
    return {
        "eef_state": eef,
        "gripper_state": gripper,
        "is_gripper_close": bool(is_close),
        "joint_state": joints,
    }


def _quat_to_rot6d(quat) -> np.ndarray:
    """The first two columns of the rotation matrix a ``(w, x, y, z)`` quaternion names.

    A quaternion is a double cover -- ``q`` and ``-q`` are the same rotation --
    so regressing one dimension by dimension asks a network to choose between
    two equally correct answers, and normalizing over the four dimensions has no
    meaning. Six numbers have neither problem (Zhou et al. 2019, *On the
    Continuity of Rotation Representations in Neural Networks*); the third
    column is the cross product of these two, so nothing is lost.
    """

    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=np.float64).reshape(4) /
                  np.linalg.norm(np.asarray(quat, dtype=np.float64).reshape(4)))
    return np.array(
        [
            1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + w * z), 2.0 * (x * z - w * y),
            2.0 * (x * y - w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z + w * x),
        ],
        dtype=np.float32,
    )


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
        task_goal: str | None = None,
        camera_names: Sequence[str] = ("front", "wrist"),
        every_n_steps: int = 10,
        subgoal_label_fn: Callable[[], str] | None = None,
    ) -> None:
        self.path = Path(path)
        self.scene = scene
        self.controller = controller
        self.spec = spec
        self.plan = plan
        # The spec carries the instruction the task yaml states for this seed, so
        # a caller that has a spec needs no second copy of the sentence. Passing
        # one explicitly still wins -- the three legacy demos do.
        self.task_goal = str(task_goal if task_goal is not None else spec.variant.instruction)
        # The same goal as an integer, for training a policy that is given no
        # sentence. Constant over the episode, so it is written from here rather
        # than captured per frame.
        self.goal_id = int(getattr(spec.variant, "goal_id", 0))
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

    def start_capture(self) -> None:
        """Drop whatever has been captured so far and start the episode here.

        The symmetric partner of ``stop_capture``. Capture is on from
        ``__enter__``, but the cloth and rope tasks open with a settle --
        cloth_unroll holds still for ``success.settle_steps`` = 200 steps, which
        at 10 steps per frame is 20 frames of an arm that has not moved yet.
        Those frames teach a policy to wait for a cue it cannot see. Call this
        once the settle is over and the demonstration actually begins.
        """
        self._frames.clear()
        self._count = 0
        self._capturing = True

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
        self._frames.append(
            {
                "obs": obs,
                "subgoal": str(subgoal),
                # The gripper COMMAND at this frame, read live. Unlike the pose
                # action -- which `_write` recovers from the next frame's
                # observed pose -- a command is not in the observations at all:
                # fingers closing on an object stop short of what was asked for,
                # and "close now" is exactly what behaviour cloning must learn.
                "gripper_cmd": float(self.controller.current_gripper_qpos),
            }
        )

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
        rot6d = [_quat_to_rot6d(pose[3:7]) for pose in actions]
        # The gripper action follows the same "next step" convention as the pose,
        # so a policy trained on them issues both at the same moment.
        commands = [frame["gripper_cmd"] for frame in self._frames]
        gripper_actions = [
            commands[min(i + 1, len(commands) - 1)] for i in range(len(commands))
        ]

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
                    rot6d=rot6d[index],
                    gripper_action=gripper_actions[index],
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
        setup.attrs["goal_id"] = self.goal_id
        setup.attrs["status"] = status
        setup.attrs["success"] = success
        setup.attrs["every_n_steps"] = int(self.every_n_steps)
        setup.attrs["robot_tool_model"] = str(self.controller.cfg.robot.get("tool_model", "panda"))
        setup.attrs["robot_qpos_size"] = int(self.controller.robot.n_qs)
        setup.attrs["gripper_state_units"] = "metres_half_gap"
        setup.attrs["ee_pose_frame"] = str(self.controller.cfg.robot.ee_link)
        # Seconds between two captured frames. `every_n_steps` alone is a step
        # count, so a reader had to know dt out of band to turn an absolute pose
        # into a velocity or a delta -- and `export_h5_lerobot.py` guessed 10 Hz.
        setup.attrs["frame_dt_s"] = float(self.scene.dt) * int(self.every_n_steps)
        setup.attrs["camera_names"] = np.array(
            [name for name, _ in self.cam_items], dtype="S"
        )
        # Aligned with camera_names; old/custom camera sources remain explicit.
        setup.attrs["camera_renderers"] = np.array(
            [getattr(cam, "renderer_type", "unknown") for _, cam in self.cam_items], dtype="S"
        )
        setup.attrs["camera_backgrounds"] = np.array(
            [getattr(cam, "presentation_background", "unknown") for _, cam in self.cam_items], dtype="S"
        )
        self._write_variant(setup)
        self._write_readings(setup)
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

    def _write_variant(self, setup) -> None:
        """What this seed actually drew, one attribute per task config leaf.

        Without it a file carries the seed but not what the seed chose, so the
        only way to learn that this demonstration grasped the far-left corner is
        to re-run the randomization. That also makes it impossible to split
        train/test by an axis value rather than by seed, which is the difference
        between "unseen random numbers" and "unseen situations".
        """

        parameters = self.spec.variant.parameters_dict()
        if not parameters:
            return
        group = setup.create_group("variant")
        for path, value in parameters.items():
            if isinstance(value, (list, tuple)):
                group.create_dataset(path, data=np.asarray(value))
            else:
                group.attrs[path] = value

    def _write_readings(self, setup) -> None:
        """The verifier's end-of-episode numbers, and why the episode failed.

        These are what a later filter selects on (drop the failures before
        training) and what a reward can be recomputed from without re-running
        physics, which is the form that survives changing one's mind about the
        reward. Whatever the demo put in ``EpisodeResult.metrics``.
        """

        if self._result is None:
            return
        setup.attrs["failure_reason"] = str(self._result.failure_reason or "")
        metrics = dict(self._result.metrics or {})
        if not metrics:
            return
        readings = setup.create_group("readings")
        for name, value in metrics.items():
            readings.attrs[name] = value

    def _write_timestep(
        self,
        episode,
        index,
        frame,
        *,
        action,
        rot6d,
        gripper_action,
        status,
        success,
        is_boundary,
        last,
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
        # Repeated on every frame, not just in `setup`, so one timestep is enough
        # to build the policy's input: the goal is part of what the policy sees,
        # the same way the images are.
        obs_group.create_dataset("goal_id", data=np.asarray(self.goal_id, dtype=np.int64))
        action_group = ts.create_group("action")
        action_group.create_dataset(
            "ee_pose_action", data=np.asarray(action, dtype=np.float32)
        )
        action_group.create_dataset(
            "ee_rot6d_action", data=np.asarray(rot6d, dtype=np.float32)
        )
        action_group.create_dataset(
            "gripper_action", data=np.asarray([gripper_action], dtype=np.float32)
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
    task_goal: str | None = None,
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
