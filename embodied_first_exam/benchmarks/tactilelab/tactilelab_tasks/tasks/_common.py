"""Shared helpers of the lift and handover tasks.

The assembly tasks derive from :class:`tactilelab_tasks.rigid.task.RigidAssemblyTask`;
lift and handover are not assemblies (a pad, a cradle made of boxes, a procedural
rod, a bimanual judge), so they share the small base below instead:

* :func:`make_scene_cfg` - ``scene`` block of a task yaml -> :class:`SceneCfg`
  (:func:`tactilelab_tasks.rigid.scene.build_scene_cfg`; procedural ``shape: cuboid`` boxes
  are accepted next to USD objects);
* :class:`TactileProvider` - GelSight-Mini sensors on the right gripper's pads (and,
  on request, the left gripper's) raycast against USD or box meshes;
* :class:`RigidTask` - nominal reset, object-pose privileged observations,
  truncation bookkeeping, ``build()``.

Isaac Lab, torch and warp are imported lazily inside the methods that need them.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

import numpy as np

from ..core import math as m
from ..core.task import Task
from ..core.types import GRIPPER_OPEN, Action

TCP_OFFSET = 0.1777
"""Wrist link (``J*_6``) to gel-pad centre along the wrist +z axis (metres)."""
JAW_OPEN_WIDTH = 0.09
"""Gripper width above which the jaws count as released (holding a part gives about the part width)."""

__all__ = ["make_scene_cfg", "TactileProvider", "RigidTask", "tcp_of_wrist", "TCP_OFFSET", "JAW_OPEN_WIDTH"]


# ----------------------------------------------------------------------------- scene from cfg
def make_scene_cfg(cfg: Dict[str, Any], cameras: bool = True, device: str = "cuda:0"):
    """:class:`SceneCfg` of a task configuration: :func:`tactilelab_tasks.rigid.scene.build_scene_cfg` (USD objects and
    procedural ``shape: cuboid`` boxes)."""
    from ..rigid.scene import build_scene_cfg

    return build_scene_cfg(cfg, cameras=cameras, device=device)


# ----------------------------------------------------------------------------- geometry
def tcp_of_wrist(wrist_pose7: np.ndarray, offset: float = TCP_OFFSET) -> np.ndarray:
    """Gel-pad centre of a wrist pose (``offset`` along the wrist +z axis)."""
    p = np.asarray(wrist_pose7, dtype=np.float64)
    return p[:3] + offset * m.quat_rotate(p[3:7], np.array([0.0, 0.0, 1.0]))


# ----------------------------------------------------------------------------- tactile
class TactileProvider:
    """``Task.sensors`` entry: GelSight-Mini images of gel pads against rigid object meshes.

    Keys (``<prefix>`` = ``tactile_left`` / ``tactile_right`` for the right gripper's
    pads, ``tactile_j2_left`` / ``tactile_j2_right`` for the left gripper's):
    ``<prefix>_rgb`` (240, 320, 3) uint8, ``<prefix>_height`` (60, 80) float16 mm,
    ``<prefix>_contact`` (60, 80) bool, ``<prefix>_press_mm`` float32.
    """

    def __init__(
        self, scene, pads: Dict[str, str], target_names: Sequence[str], device: str = "cuda", with_rgb: bool = True
    ):
        from ..tactile.sensor import GelSightMini

        self.scene = scene
        self.pads = dict(pads)  # obs prefix -> robot body name
        self.device = device
        self.with_rgb = bool(with_rgb)
        self.sensors = {prefix: GelSightMini(prefix, device=device) for prefix in self.pads}
        self.targets = {str(n): self._build_target(str(n)) for n in target_names}
        self._body_ids: Dict[str, int] = {}
        self.frames = 0
        self.contact_frames = 0

    def _build_target(self, name: str):
        from ..tactile.mesh_sources import box_mesh, usd_mesh_in_frame
        from ..tactile.raycast import MeshTarget

        ocfg = next(o for o in self.scene.cfg.objects if o.name == name)
        if ocfg.shape == "cuboid" or ocfg.usd_path is None:
            verts, faces = box_mesh(tuple(ocfg.dims))
        else:
            from isaaclab.sim.utils.stage import get_current_stage

            body = self.scene.rigid_body_prim_path(name)
            verts, faces = usd_mesh_in_frame(get_current_stage(), f"/World/Objects/{name}", frame_path=body)
        return MeshTarget(verts, faces, device=self.device, pose7=self.scene.object_pose(name))

    def _gel_pose(self, body: str) -> np.ndarray:
        robot = self.scene.robot
        if body in robot._body_ids:
            return robot.body_pose(body)
        if body not in self._body_ids:
            idx, _ = robot.articulation.find_bodies(body)
            if len(idx) != 1:
                raise KeyError(f"gel body {body} not found")
            self._body_ids[body] = int(idx[0])
        st = robot.articulation.data.body_link_pose_w[0, self._body_ids[body]].cpu().numpy().astype(np.float64)
        return m.pose_from_pos_quat(st[:3], st[3:7])

    @staticmethod
    def has_body(scene, body: str) -> bool:
        try:
            idx, _ = scene.robot.articulation.find_bodies(body)
            return len(idx) == 1
        except Exception:
            return False

    def reset_counters(self) -> None:
        self.frames = 0
        self.contact_frames = 0

    def read(self) -> Dict[str, np.ndarray]:
        for name, tgt in self.targets.items():
            tgt.set_pose(self.scene.object_pose(name))
        targets = list(self.targets.values())
        out: Dict[str, np.ndarray] = {}
        any_contact = False
        for prefix, body in self.pads.items():
            res = self.sensors[prefix].observe(self._gel_pose(body), targets)
            contact = res["contact"].detach().cpu().numpy().astype(bool)
            any_contact = any_contact or bool(contact.any())
            out[f"{prefix}_height"] = res["height_mm"].detach().cpu().numpy().astype(np.float16)
            out[f"{prefix}_contact"] = contact
            out[f"{prefix}_press_mm"] = np.asarray(float(res["press_depth_mm"]), dtype=np.float32)
            if self.with_rgb:
                out[f"{prefix}_rgb"] = np.ascontiguousarray(res["rgb"].detach().cpu().numpy().astype(np.uint8))
        self.frames += 1
        self.contact_frames += int(any_contact)
        return out

    __call__ = read


# ----------------------------------------------------------------------------- base task
class RigidTask(Task):
    """Base of the lift and handover tasks: cfg-driven scene, nominal reset, object poses.

    ``cfg`` keys: ``scene`` (robot, gel, objects, ``settle_ticks``), ``max_steps``,
    ``success_hold``, ``tactile`` (``enabled``, ``targets``, ``left_gripper``).
    ``scene.robot`` may add ``right_finger_q0`` / ``left_finger_q0`` (finger joints at
    reset) and ``initial_gripper`` (``[right, left]`` binary command at reset).
    """

    name = "rigid"
    success_hold = 1

    def __init__(
        self,
        cfg: Dict[str, Any],
        scene=None,
        obs_mode: str = "full",
        device: str = "cuda:0",
        cameras: bool = True,
        tactile: bool = True,
    ):
        super().__init__(cfg, scene, obs_mode)
        self.name = str(cfg.get("name", self.name))
        self.success_hold = int(cfg.get("success_hold", self.success_hold))
        self.max_steps = int(cfg.get("max_steps", 0))
        self.device = device
        self.cameras = bool(cameras)
        tcfg = cfg.get("tactile", {}) or {}
        self.tactile_enabled = bool(tactile) and bool(tcfg.get("enabled", True))
        self.settle_ticks = int(cfg.get("scene", {}).get("settle_ticks", 60))
        rc = cfg.get("scene", {}).get("robot", {})
        self._initial_gripper = np.asarray(rc.get("initial_gripper", (GRIPPER_OPEN, GRIPPER_OPEN)), dtype=np.int64)
        self._gripper_cmd = self._initial_gripper.copy()
        self._truncation: Optional[str] = None
        self.tactile: Optional[TactileProvider] = None

    # ------------------------------------------------------------------ construction
    def build(self) -> "RigidTask":
        """Create and build the Isaac Lab scene and the tactile sensors (the app must be launched)."""
        from ..rigid.scene import RigidTaskScene

        if self.scene is None:
            scene = RigidTaskScene(make_scene_cfg(self.cfg, cameras=self.cameras, device=self.device))
            scene.build()
            self.scene = scene
        if self.tactile_enabled and self.tactile is None:
            tcfg = self.cfg.get("tactile", {}) or {}
            pads = {"tactile_left": "gsmini_left", "tactile_right": "gsmini_right"}
            if tcfg.get("left_gripper", False):
                for prefix, body in (
                    ("tactile_j2_left", "tactilelab_J2_left"),
                    ("tactile_j2_right", "tactilelab_J2_right"),
                ):
                    if TactileProvider.has_body(self.scene, body):
                        pads[prefix] = body
            from ..tactile import sensor_device

            self.tactile = TactileProvider(
                self.scene,
                pads,
                [str(n) for n in tcfg.get("targets", [])],
                device=sensor_device(self.device),
                with_rgb=self.obs_mode == "full",
            )
            self.sensors["tactile"] = self.tactile.read
        return self

    def close(self) -> None:
        if self.scene is not None:
            self.scene.close()

    def robot_q0(self) -> np.ndarray:
        """Start joints: the scene's robot defaults plus the optional finger overrides."""
        q = self.scene.robot.cfg.q0().copy()
        rc = self.cfg.get("scene", {}).get("robot", {})
        if "right_finger_q0" in rc:
            q[12:14] = [float(v) for v in rc["right_finger_q0"]]
        if "left_finger_q0" in rc:
            q[14:16] = [float(v) for v in rc["left_finger_q0"]]
        return q

    # ------------------------------------------------------------------ reset
    def _reset_scene(self, seed: int) -> None:
        self._truncation = None
        self._gripper_cmd = self._initial_gripper.copy()
        self.scene.reset_robot(self.robot_q0())
        self.scene.robot.set_gripper(self._gripper_cmd)
        self.scene.reset_objects()
        self._after_objects_placed()
        for _ in range(self.settle_ticks):
            self.scene.step(Action.hold(self._gripper_cmd))
        if self.tactile is not None:
            self.tactile.reset_counters()
        self._after_settle()

    def _after_objects_placed(self) -> None:
        """Hook: after the nominal poses are written, before the settle ticks."""

    def _after_settle(self) -> None:
        """Hook: after the settle ticks (baselines)."""

    def _apply_action(self, action: Action) -> None:
        self._gripper_cmd = action.gripper.copy()
        super()._apply_action(action)

    # ------------------------------------------------------------------ queries
    def object_pose(self, name: str) -> np.ndarray:
        return self.scene.object_pose(name)

    def object_velocity(self, name: str) -> np.ndarray:
        return self.scene.object_velocity(name)

    def eef_pose(self, arm: int = 0) -> np.ndarray:
        return self.scene.ee_pose(arm)

    def gripper_width(self, arm: int = 0) -> float:
        return float(self.scene.robot.gripper_width(arm))

    def jaw_open(self, arm: int = 0, width: float = JAW_OPEN_WIDTH) -> bool:
        return self.gripper_width(arm) > width

    @property
    def truncated(self) -> bool:
        return self._truncation is not None or self.timed_out

    @property
    def truncation_reason(self) -> Optional[str]:
        if self._truncation is not None:
            return self._truncation
        return "timeout" if self.timed_out else None

    def _truncate(self, reason: str) -> None:
        if self._truncation is None:
            self._truncation = reason

    # ------------------------------------------------------------------ observation
    def privileged_obs(self) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        for ocfg in self.scene.cfg.objects:
            out[f"object_pose/{ocfg.name}"] = self.object_pose(ocfg.name).astype(np.float32)
        out.update(self.task_privileged())
        return out

    def task_privileged(self) -> Dict[str, np.ndarray]:
        """Task metrics for ``obs["privileged"]`` (override)."""
        return {}

    def metrics(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"truncated": self.truncated}
        if self.truncation_reason:
            d["truncation_reason"] = self.truncation_reason
        if self.tactile is not None:
            d["tactile_contact_frames"] = self.tactile.contact_frames
        return d
