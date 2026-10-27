"""Shared base of the cloth / cable tasks: a :class:`SoftTask` owns one soft world in the Newton sidecar.

Every control tick the task

1. steps the robot (Isaac Lab, through the scene's IK) with the policy's action,
2. reads the poses of the robot links that carry the soft-world colliders (gel pads, sensor cases, finger bodies, and
   the left forearm for the sleeve task) and mirrors them into the sidecar as kinematic colliders,
3. steps the soft world one control tick (``fps`` = 60) and keeps the returned state (``particle_q`` ... / ``cable_nodes``),
4. refits the deformed surface mesh of the two GelSight Mini sensors (a thick shell of one particle radius for cloth,
   the tube around a cable), updates the task metrics and the pad contact / penetration diagnostics.

Subclasses implement :meth:`build_world` (the sidecar world config), :meth:`initial_state` (particle / cable positions of
an episode), :meth:`update_metrics` (called every soft tick), :meth:`success_predicate` and :meth:`task_obs`; the scripted
policies (:mod:`tactilelab_tasks.soft.plan`) use the pinch-frame helpers (:meth:`mid_frame`, :meth:`eef_pose_for_mid`,
:meth:`gripper_gap`, :meth:`close_command_for_gap`, :meth:`set_gripper_gap`).

The task talks to its scene through the small :class:`tactilelab_tasks.core.task.SceneLike` interface plus one optional method,
``link_pose(name) -> pose7`` (env frame, wxyz).  The Isaac Lab scene has no such method: link poses are read from the robot
articulation; a kinematic stand-in (:mod:`tactilelab_tasks.soft.kinematic_hand`) provides it, so the plans and the success
metrics run against the sidecar alone.

Configuration (``tasks/<name>/cfg.yaml``)::

    name: cloth_edge_feed
    table_z: 1.102
    scene:                       # Isaac side
      left_arm_q0: [...]         # parked left arm (default PARKED_LEFT_ARM)
      gel: {stiffness, damping, friction}
      fixture_physics: true      # fixtures (shelf, clamp ...) get a PhysX collider
    soft:
      settle_ticks: 45           # soft ticks after a reset with the colliders held (the cloth comes to rest)
      solver: {substeps: 10, iterations: 5}
      pinch_overlap: 0.00025     # m; the close command squeezes the object by this much per gel (None = fixed close)
      close_gap_calib: [[0.038, 0.00655], [0.0392, 0.0041], [0.041, 0.0026]]
      penetration_fail: true     # truncate when the soft body sits behind a gel pad for penetration_ticks ticks
      pad_mu: 0.45               # gel pad friction in the soft world (colliders 0 and 1)
      colliders: [...]           # optional explicit collider list (default: the six gripper boxes)
    success: {hold: 15, ...}     # the predicate must hold for ``hold`` consecutive ticks
    world: {...}                 # task-specific scene numbers (see the task module)
    policy: {...}                # scripted-policy numbers (see the task module)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..core import math as m
from ..core.task import Task
from ..core.types import CONTROL_DT, GEL_BODIES, GRIPPER_WIDTH_OFFSET, PARKED_LEFT_ARM, TABLE_TOP_Z, Action
from ..softbody_geom import spec
from ..softbody_geom.soft_scenes import FOREARM_COLLIDER, GSMINI_COLLIDERS
from . import metrics as M

__all__ = ["SoftTask", "SoftTactileRig", "SoftMeshVisual", "DEFAULT_CLOSE_GAP_CALIB", "PAD_HALF"]

DEFAULT_CLOSE_GAP_CALIB: List[List[float]] = [[0.038, 0.00655], [0.0392, 0.0041], [0.041, 0.0026]]
"""Measured ``[|q|, gel-face gap]`` pairs of the GelSight Mini gripper: the finger joint magnitude against the gap between
the two gel pad colliders of the soft world (the geometric 2 mm per mm of command up to about 0.039, flattening toward the
0.041 joint limit)."""

PAD_HALF = tuple(GSMINI_COLLIDERS[0]["half"])
"""Half extents of a gel pad collider box (x, y, z)."""


def _deep_merge(base: Dict[str, Any], over: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# ----------------------------------------------------------------------------- tactile
class SoftTactileRig:
    """Two GelSight Mini sensors on the right gripper, raycast against the deformed soft-body surface.

    ``set_mesh(points, faces, thickness)`` (re)builds the warp mesh; ``refit(points)`` follows the deformation every tick.
    A cloth is a sheet through the particle centres, so the target is the closed shell ``thickness`` (= particle radius)
    either side of it; a cable is the tube around its nodes (thickness 0).
    """

    def __init__(self, scene, device: str = "cuda", with_rgb: bool = True):
        from ..tactile.sensor import GelSightMini

        self.scene = scene
        self.device = device
        self.with_rgb = bool(with_rgb)
        self.sensors = {g: GelSightMini(g, device=device) for g in GEL_BODIES}
        self.target = None
        self.frames = 0
        self.contact_frames = 0

    def set_mesh(self, points: np.ndarray, faces: np.ndarray, thickness: float) -> None:
        from ..tactile.raycast import MeshTarget

        pts = np.asarray(points, dtype=np.float32)
        if (
            self.target is not None
            and len(self.target.mid_points) == len(pts)
            and abs(self.target.thickness - thickness) < 1e-9
        ):
            self.target.rebuild(pts, faces)
        else:
            self.target = MeshTarget(
                pts, np.asarray(faces, dtype=np.int32), device=self.device, thickness=float(thickness)
            )

    def refit(self, points: np.ndarray) -> None:
        if self.target is not None:
            self.target.refit(np.asarray(points, dtype=np.float32))

    def read(self) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        targets = [self.target] if self.target is not None else []
        any_contact = False
        for gel, pose in self.scene.robot.gel_poses().items():
            side = "left" if gel.endswith("left") else "right"
            o = self.sensors[gel].observe(pose, targets)
            contact = o["contact"].detach().cpu().numpy().astype(bool)
            any_contact = any_contact or bool(contact.any())
            out[f"tactile_{side}_height"] = o["height_mm"].detach().cpu().numpy().astype(np.float16)
            out[f"tactile_{side}_contact"] = contact
            out[f"tactile_{side}_press_mm"] = np.asarray(float(o["press_depth_mm"]), dtype=np.float32)
            if self.with_rgb:
                out[f"tactile_{side}_rgb"] = np.ascontiguousarray(o["rgb"].detach().cpu().numpy().astype(np.uint8))
        self.frames += 1
        if any_contact:
            self.contact_frames += 1
        return out

    def reset_counters(self) -> None:
        self.frames = 0
        self.contact_frames = 0


# ----------------------------------------------------------------------------- visual mesh
class SoftMeshVisual:
    """A USD mesh on the Isaac stage that follows the soft body (so the wrist cameras see it).  Fixed topology; the
    points are rewritten every tick."""

    def __init__(self, path: str, faces: np.ndarray, color: Sequence[float], double_sided: bool = True):
        from isaaclab.sim.utils.stage import get_current_stage
        from pxr import Gf, Sdf, UsdGeom, Vt

        self.path = path
        self._Vt = Vt
        stage = get_current_stage()
        if stage.GetPrimAtPath(path).IsValid():
            stage.RemovePrim(path)
        mesh = UsdGeom.Mesh.Define(stage, Sdf.Path(path))
        f = np.asarray(faces, dtype=np.int32).reshape(-1, 3)
        mesh.CreateFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(f.reshape(-1)))
        mesh.CreateFaceVertexCountsAttr().Set(Vt.IntArray.FromNumpy(np.full(len(f), 3, dtype=np.int32)))
        mesh.CreateDoubleSidedAttr().Set(bool(double_sided))
        mesh.CreateSubdivisionSchemeAttr().Set("none")
        mesh.CreateDisplayColorAttr().Set([Gf.Vec3f(*[float(c) for c in color])])
        self.mesh = mesh

    def update(self, points: np.ndarray) -> None:
        self.mesh.GetPointsAttr().Set(self._Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(points, dtype=np.float32)))


# ----------------------------------------------------------------------------- task
class SoftTask(Task):
    """Base class of the cloth / cable tasks (see the module docstring)."""

    name = "soft"
    success_hold = 15
    latch = False
    """Success follows the hold window (the verdict is taken at the end of the plan)."""

    robot_settle_ticks = 5
    """Control ticks the robot is held after a reset before the collider poses are read."""

    def __init__(
        self,
        cfg: Dict[str, Any],
        scene=None,
        obs_mode: str = "full",
        device: str = "cuda:0",
        cameras: bool = True,
        tactile: bool = True,
        client=None,
    ):
        super().__init__(cfg, scene, obs_mode)
        self.name = str(cfg.get("name", self.name))
        self.device = device
        self.cameras = bool(cameras)
        self.tactile_enabled = bool(tactile)
        self.max_steps = int(cfg.get("max_steps", 0))
        self.table_z = float(cfg.get("table_z", TABLE_TOP_Z))
        soft = dict(cfg.get("soft", {}))
        self.settle_ticks = int(soft.get("settle_ticks", 45))
        self.solver = {
            "substeps": int(soft.get("solver", {}).get("substeps", 10)),
            "iterations": int(soft.get("solver", {}).get("iterations", 5)),
        }
        self.pinch_overlap: Optional[float] = (
            None if soft.get("pinch_overlap") is None else float(soft["pinch_overlap"])
        )
        self.close_gap_calib = sorted(
            [[float(a), float(b)] for a, b in soft.get("close_gap_calib", DEFAULT_CLOSE_GAP_CALIB)]
        )
        self.penetration_fail = bool(soft.get("penetration_fail", False))
        self.penetration_ticks = int(soft.get("penetration_ticks", 10))
        self.penetration_min_points = int(soft.get("penetration_min_points", 2))
        self.attach_radius = float(soft.get("attach_radius", 0.012))
        self.visual_enabled = bool(soft.get("visual", True))
        self.success_hold = int(cfg.get("success", {}).get("hold", self.success_hold))
        self.colliders: List[spec.ColliderSpec] = [spec.ColliderSpec.from_cfg(c) for c in self.collider_cfgs(soft)]
        self.pad_halves = [self.colliders[k].half for k in (0, 1)]
        self._client = client
        self.world = None
        self._world_key: Optional[str] = None
        self._world_cfg: Optional[Dict[str, Any]] = None
        self._tube_faces: Optional[np.ndarray] = None
        self._tube_n = 0
        self.state: Dict[str, np.ndarray] = {}
        self.pads = np.zeros((len(self.colliders), 7), dtype=np.float32)
        self.pads[:, 6] = 1.0
        self.tris: Optional[np.ndarray] = None
        self.rest: Optional[np.ndarray] = None
        self.pinned: Optional[np.ndarray] = None
        self.soft_ticks = 0
        self.truncation_reason: Optional[str] = None
        self.gripper_gap_cmd: Optional[float] = None
        self._pad_contact = np.zeros(2, dtype=np.float32)
        self._pen = np.zeros((2, 2), dtype=np.int64)
        self._pen_max = np.zeros((2, 2), dtype=np.int64)
        self._pen_ticks = 0
        self._attached = False
        self._link_ids: Dict[str, int] = {}
        self.tactile: Optional[SoftTactileRig] = None
        self.visual: Optional[SoftMeshVisual] = None
        self._visual_failed = False

    # ------------------------------------------------------------------ subclass API
    def collider_cfgs(self, soft: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The collider list of the soft world: an explicit ``soft.colliders`` list or the six gripper boxes with the gel
        pads' friction ``soft.pad_mu`` (the sleeve task inserts the forearm cylinder)."""
        if soft.get("colliders"):
            return [dict(c) for c in soft["colliders"]]
        out = []
        for i, d in enumerate(GSMINI_COLLIDERS):
            d = dict(d)
            if i < 2 and soft.get("pad_mu") is not None:
                d["mu"] = float(soft["pad_mu"])
            out.append(d)
        return out

    def build_world(self) -> Dict[str, Any]:
        """The soft world config (``cloth`` / ``cable`` block, ``statics``, ``soft_contact`` ...); solver settings, the
        table height and the collider list are appended by :meth:`world_cfg`."""
        raise NotImplementedError

    def initial_state(self) -> Dict[str, Any]:
        """``{"particle_q": (P, 3)}`` and / or ``{"cable_points": (S+1, 3)}`` of an episode (absent = the rest shape)."""
        return {}

    def rest_cable_points(self, points):
        """Cable centreline the rod is built from (its rest bend); default the initial points."""
        return points

    def fixtures(self) -> List[Dict[str, Any]]:
        """Rigid boxes of the Isaac scene: ``{name, center, half, color, [physics]}`` (env frame, axis aligned)."""
        return []

    def on_reset(self, state: Dict[str, np.ndarray]) -> None:
        """Called once per reset with the first soft state (before the settle window)."""

    def update_metrics(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> None:
        """Called after every soft tick with the new state and the ``(C, 7)`` xyzw collider poses."""

    def task_obs(self) -> Dict[str, np.ndarray]:
        """Task metrics for ``obs["privileged"]``."""
        return {}

    def task_metrics(self) -> Dict[str, float]:
        """Scalar diagnostics for ``info``."""
        return {}

    # ------------------------------------------------------------------ scene (Isaac side)
    def scene_cfg(self, cameras: Optional[bool] = None, device: Optional[str] = None):
        from ..backends.isaaclab_scene import ObjectCfg, SceneCfg
        from ..backends.robot import RobotCfg

        sc = dict(self.cfg.get("scene", {}))
        gel = dict(sc.get("gel", {}))
        robot = RobotCfg(
            gel_stiffness=float(gel.get("stiffness", 650.0)),
            gel_damping=float(gel.get("damping", 0.5)),
            gel_friction=float(gel.get("friction", 1.5)),
            close_magnitude=float(sc.get("close_magnitude", 0.038)),
            right_arm_q0=tuple(float(v) for v in sc.get("right_arm_q0", (0.0,) * 6)),
            left_arm_q0=tuple(float(v) for v in sc.get("left_arm_q0", PARKED_LEFT_ARM)),
        )
        objects = []
        physics = bool(sc.get("fixture_physics", True))
        for fx in self.fixtures():
            if not (physics and fx.get("physics", True)):
                continue
            half = [float(v) for v in fx["half"]]
            objects.append(
                ObjectCfg(
                    name=str(fx["name"]),
                    shape="cuboid",
                    dims=(2.0 * half[0], 2.0 * half[1], 2.0 * half[2]),
                    pos=tuple(float(v) for v in fx["center"]),
                    ori_deg=(0.0, 0.0, float(fx.get("yaw_deg", 0.0))),
                    kinematic=True,
                    color=tuple(float(c) for c in fx.get("color", (0.55, 0.55, 0.6))),
                    friction=float(fx.get("friction", 0.6)),
                )
            )
        return SceneCfg(
            robot=robot,
            objects=objects,
            cameras=self.cameras if cameras is None else cameras,
            device=self.device if device is None else device,
        )

    def build(self) -> "SoftTask":
        """Create and build the Isaac Lab scene and the tactile rig (the app must be launched first)."""
        from ..backends.isaaclab_scene import IsaacLabScene

        if self.scene is None:
            scene = IsaacLabScene(self.scene_cfg())
            scene.build()
            self.scene = scene
        if self.tactile_enabled and self.tactile is None:
            self.tactile = SoftTactileRig(self.scene, device=self.device, with_rgb=self.obs_mode == "full")
            self.sensors["tactile"] = self.tactile.read
        return self

    def close(self) -> None:
        if self.world is not None:
            self.world.close()
            self.world = None
        if self.scene is not None and hasattr(self.scene, "close"):
            self.scene.close()

    # ------------------------------------------------------------------ links / colliders
    def link_pose(self, name: str) -> np.ndarray:
        """Env-frame pose7 (wxyz) of a robot link (``scene.link_pose`` when the scene has one, else the articulation)."""
        sc = self.scene
        if hasattr(sc, "link_pose"):
            return np.asarray(sc.link_pose(name), dtype=np.float64).reshape(7)
        robot = sc.robot
        if name in robot._body_ids:
            return robot.body_pose(name)
        idx = self._link_ids.get(name)
        if idx is None:
            ids, _ = robot.articulation.find_bodies(name)
            if len(ids) != 1:
                raise RuntimeError(f"collider link {name!r} not found in the robot articulation")
            idx = self._link_ids[name] = int(ids[0])
        st = robot.articulation.data.body_link_pose_w[0, idx].cpu().numpy().astype(np.float64)
        return m.pose_from_pos_quat(st[:3], st[3:7])

    def collider_poses(self) -> np.ndarray:
        """``(C, 7)`` xyzw env-frame poses of the soft-world colliders from the current robot link poses."""
        links: Dict[str, np.ndarray] = {}
        for s in self.colliders:
            if s.link not in links:
                links[s.link] = spec.pose7_wxyz_to_xyzw(self.link_pose(s.link))
        return spec.collider_poses(self.colliders, links)

    def world_cfg(self) -> Dict[str, Any]:
        cfg = _deep_merge(self.build_world(), self.cfg.get("soft", {}).get("soft_world", {}))
        cfg["substeps"] = self.solver["substeps"]
        cfg["iterations"] = self.solver["iterations"]
        cfg["fps"] = int(round(1.0 / CONTROL_DT))
        cfg.setdefault("table", {})
        cfg["table"].setdefault("z", self.table_z)
        cfg["colliders"] = [s.world_cfg() for s in self.colliders]
        return cfg

    def _ensure_world(self, init: Dict[str, Any]) -> None:
        from ..backends.newton_client import SoftWorldClient

        cfg = self.world_cfg()
        key = json.dumps(cfg, sort_keys=True, default=float)
        if self.world is not None and key == self._world_key:
            return
        if self.world is not None:
            self.world.close()
        cable = self.rest_cable_points(init.get("cable_points"))
        self.world = SoftWorldClient(cfg, collider_q0=self.pads, cable_points=cable, client=self._client)
        self._world_key = key
        self._world_cfg = cfg
        if "cloth" in cfg:
            mesh = self.world.mesh()
            self.tris = np.asarray(mesh["triangles"], dtype=np.int32)
            self.rest = np.asarray(mesh["rest"], dtype=np.float32)
            self.pinned = np.asarray(mesh["pinned"], dtype=np.int32)
        else:
            self.tris = self.rest = self.pinned = None
        self._mesh_ready = False

    # ------------------------------------------------------------------ surface mesh (tactile + visual)
    def surface_mesh(self, state: Dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray, float]:
        """``(points, faces, thickness)`` of the soft body's surface for the raycast sensors."""
        if "particle_q" in state:
            return (
                np.asarray(state["particle_q"], dtype=np.float32),
                self.tris,
                float(self._world_cfg["cloth"]["radius"]),
            )
        nodes = np.asarray(state["cable_nodes"], dtype=np.float64)
        r = float(self._world_cfg["cable"]["radius"])
        faces = getattr(self, "_tube_faces", None)
        if faces is None or self._tube_n != len(nodes):
            _, faces = spec.tube_mesh(nodes, r)
            self._tube_faces, self._tube_n = faces, len(nodes)
        return spec.tube_vertices(nodes, r), faces, 0.0

    def _refresh_surface(self, state: Dict[str, np.ndarray], rebuild: bool = False) -> None:
        if self.tactile is None and (not self.visual_enabled or self._visual_failed):
            return
        points, faces, thick = self.surface_mesh(state)
        if self.tactile is not None:
            if rebuild or self.tactile.target is None:
                self.tactile.set_mesh(points, faces, thick)
            else:
                self.tactile.refit(points)
        if self.visual_enabled and not self._visual_failed and self.scene is not None and hasattr(self.scene, "sim"):
            try:
                if rebuild or self.visual is None:
                    color = (
                        self._world_cfg["cloth"]["color"]
                        if "cloth" in self._world_cfg
                        else self._world_cfg["cable"]["color"]
                    )
                    self.visual = SoftMeshVisual("/World/Soft/body", faces, color)
                self.visual.update(points)
            except Exception:  # noqa: BLE001 - a visual failure never stops the task
                self._visual_failed = True

    # ------------------------------------------------------------------ reset / step
    @property
    def settling(self) -> bool:
        return self.soft_ticks < self.settle_ticks

    def _reset_scene(self, seed: int) -> None:
        sc = self.scene
        if sc is None:
            raise RuntimeError("SoftTask needs a scene (call build() or pass one)")
        if hasattr(sc, "reset_robot"):
            sc.reset_robot()
        if hasattr(sc, "reset_objects"):
            sc.reset_objects()
        for _ in range(self.robot_settle_ticks):
            sc.step(Action.hold())
        self.pads = self.collider_poses()
        self.soft_ticks = 0
        self.truncation_reason = None
        self.gripper_gap_cmd = None
        self._pad_contact = np.zeros(2, dtype=np.float32)
        self._pen = np.zeros((2, 2), dtype=np.int64)
        self._pen_max = np.zeros((2, 2), dtype=np.int64)
        self._pen_ticks = 0
        self._attached = False
        init = self.initial_state()
        self._ensure_world(init)
        state = self.world.reset(init.get("particle_q"), init.get("cable_points"), self.pads)
        self.state = state
        self._refresh_surface(state, rebuild=True)
        if self.tactile is not None:
            self.tactile.reset_counters()
        self.on_reset(state)
        self._post_step(state, self.pads)
        # the soft body settles with the colliders held at their reset poses; the robot holds still meanwhile
        for _ in range(self.settle_ticks):
            sc.step(Action.hold())
            state = self.world.step(self.pads)
            self.soft_ticks += 1
            self.state = state
            self._post_step(state, self.pads)

    def _apply_action(self, action: Action) -> None:
        if self.scene is None or self.world is None:
            raise RuntimeError("reset() first")
        self.scene.step(action)
        pads = self.collider_poses()
        state = self.world.step(pads)
        self.soft_ticks += 1
        self.pads = pads
        self.state = state
        self._post_step(state, pads)

    def _post_step(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> None:
        self._refresh_surface(state)
        self.update_metrics(state, pads)
        self._pad_contact = self._count_pad_contacts(state, pads)
        self._track_penetration(state, pads)
        if self.truncation_reason is None:
            self.truncation_reason = self.penetration_reason()

    # ------------------------------------------------------------------ diagnostics
    def _samples(self, state: Dict[str, np.ndarray]) -> Tuple[np.ndarray, float]:
        if "particle_q" in state:
            return M.cloth_samples(state["particle_q"], self.tris), float(self._world_cfg["cloth"]["radius"])
        nodes = np.asarray(state["cable_nodes"], dtype=np.float64)
        return np.concatenate([nodes, 0.5 * (nodes[1:] + nodes[:-1])]), float(self._world_cfg["cable"]["radius"])

    def _count_pad_contacts(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> np.ndarray:
        """Surface samples touching each of the two gel pads (``pad_contact`` of the privileged observation)."""
        try:
            pts, r = self._samples(state)
            return M.contact_counts(pts, r, np.asarray(pads[:2], dtype=np.float64), self.pad_halves).astype(np.float32)
        except Exception:  # noqa: BLE001 - a diagnostic never stops the task
            return np.zeros(2, dtype=np.float32)

    def _track_penetration(self, state: Dict[str, np.ndarray], pads: np.ndarray) -> None:
        try:
            if "particle_q" in state:
                pts = np.asarray(state["particle_q"], dtype=np.float64)
            else:
                nodes = np.asarray(state["cable_nodes"], dtype=np.float64)
                pts = np.concatenate([nodes, 0.5 * (nodes[1:] + nodes[:-1])])
            pen = M.pad_penetration(pts, np.asarray(pads[:2], dtype=np.float64), self.pad_halves)
        except Exception:  # noqa: BLE001
            pen = np.zeros((2, 2), dtype=np.int64)
        self._pen = pen
        self._pen_max = np.maximum(self._pen_max, pen)
        self._pen_ticks = self._pen_ticks + 1 if int(pen[:, 1].max()) >= self.penetration_min_points else 0

    def penetration_reason(self) -> Optional[str]:
        """Truncation reason once the soft body has sat behind a gel pad for ``penetration_ticks`` consecutive ticks."""
        if not self.penetration_fail or self._pen_ticks < self.penetration_ticks:
            return None
        k = int(np.argmax(self._pen[:, 1]))
        how = "passed through" if int(self._pen_max[k, 0]) else "slipped around"
        return f"the soft body {how} pad {k} ({int(self._pen[k, 1])} points behind it for {self._pen_ticks} ticks)"

    @property
    def pad_contact(self) -> np.ndarray:
        return self._pad_contact

    @property
    def pad_penetration(self) -> np.ndarray:
        return self._pen

    # ------------------------------------------------------------------ success / info
    def is_success(self) -> bool:
        return bool(self._latched) and self.truncation_reason is None

    @property
    def truncated(self) -> bool:
        return self.truncation_reason is not None

    def metrics(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "truncated": self.truncation_reason,
            "soft_ticks": self.soft_ticks,
            "pad_contact": self._pad_contact.tolist(),
            "pad_penetration": self._pen.reshape(-1).tolist(),
            "hold": self._hold_count,
        }
        if self.tactile is not None:
            d["tactile_contact_frames"] = self.tactile.contact_frames
        d.update(self.task_metrics())
        return d

    def privileged_obs(self) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        st = self.state
        for k in ("particle_q", "particle_qd", "cable_nodes", "cable_seg_q"):
            if k in st:
                out[k] = np.asarray(st[k], dtype=np.float32)
        out["pad_poses"] = spec.pose7_xyzw_to_wxyz(np.asarray(self.pads[:2], dtype=np.float64)).astype(np.float32)
        out["pad_contact"] = self._pad_contact.astype(np.float32)
        out["pad_penetration"] = self._pen.reshape(-1).astype(np.float32)
        out["gripper_gap"] = np.array([self.gripper_gap()], dtype=np.float32)
        out.update(self.task_obs())
        return out

    # ------------------------------------------------------------------ state
    def get_state(self) -> Dict[str, Any]:
        st = super().get_state()
        st["soft"] = {k: np.asarray(v).copy() for k, v in self.state.items()}
        st["soft_ticks"] = self.soft_ticks
        return st

    def set_state(self, state: Dict[str, Any]) -> None:
        st = dict(state)
        soft = st.pop("soft", None)
        self.soft_ticks = int(st.pop("soft_ticks", self.soft_ticks))
        super().set_state(st)
        if soft is not None and self.world is not None:
            self.pads = self.collider_poses()
            cable = None
            if "cable_nodes" in soft:
                cable = soft["cable_nodes"]
            self.state = self.world.reset(soft.get("particle_q"), cable, self.pads)
            self._refresh_surface(self.state)

    # ------------------------------------------------------------------ pinch-frame helpers
    def eef_pose(self) -> np.ndarray:
        """Env-frame pose7 (wxyz) of the right hand frame ``J1_6``."""
        if hasattr(self.scene, "ee_pose"):
            return np.asarray(self.scene.ee_pose(0), dtype=np.float64).reshape(7)
        o = self.scene.robot_obs()
        return m.pose_from_pos_quat(o["ee_pos_right"], o["ee_quat_right"])

    def mid_frame(self) -> Tuple[np.ndarray, np.ndarray]:
        """Pinch frame of the two gel pads: ``(centre (3,), R (3, 3))`` with the frame's +z along the closing axis (from pad
        0 toward pad 1) and the rest of the rotation that of pad 0."""
        pads = np.asarray(self.pads, dtype=np.float64)[:2]
        c = pads[:, :3].mean(axis=0)
        R = spec.quat_to_mat(pads[0, 3:7])
        if float(R[:, 2] @ (pads[1, :3] - pads[0, :3])) < 0.0:
            R = R @ np.diag([1.0, -1.0, -1.0])
        return c, R

    def mid_in_eef(self) -> Tuple[np.ndarray, np.ndarray]:
        """The pinch frame seen from the hand frame: ``(t (3,), R (3, 3))`` (constant while the gripper only opens / closes)."""
        e = self.eef_pose()
        Re = spec.quat_to_mat(spec.quat_wxyz_to_xyzw(e[3:7]))
        c, R = self.mid_frame()
        return Re.T @ (c - e[:3]), Re.T @ R

    def eef_pose_for_mid(self, mid_pos: Sequence[float], R_mid: np.ndarray) -> np.ndarray:
        """Hand pose7 (wxyz, env frame) that puts the pinch frame at ``mid_pos`` with rotation ``R_mid``."""
        t, R_em = self.mid_in_eef()
        R_we = np.asarray(R_mid, dtype=np.float64) @ R_em.T
        p = np.asarray(mid_pos, dtype=np.float64) - R_we @ t
        q = spec.quat_xyzw_to_wxyz(spec.mat_to_quat(R_we))
        return np.concatenate([p, q])

    def approach_axis_in_mid(self) -> np.ndarray:
        """The hand's approach direction (flange -> pinch centre) in the pinch frame, unit vector."""
        t, R_em = self.mid_in_eef()
        return R_em.T @ (t / np.linalg.norm(t))

    def pad_mid(self) -> np.ndarray:
        return np.asarray(self.pads[:2, :3], dtype=np.float64).mean(axis=0)

    def gripper_gap(self) -> float:
        """Opening between the two gel faces [m]: ``0.082 + q(J1_7) - q(J1_8)``."""
        q = np.asarray(self.scene.robot_obs()["joint_pos"], dtype=np.float64)
        return float(GRIPPER_WIDTH_OFFSET + q[12] - q[13])

    def grasp_thickness(self) -> float:
        """Thickness of the soft body where the pads pinch it: the particle shell of a cloth, the diameter of a cable."""
        cfg = self._world_cfg if getattr(self, "_world_cfg", None) else self.world_cfg()
        return 2.0 * float(cfg["cloth"]["radius"] if "cloth" in cfg else cfg["cable"]["radius"])

    def close_command_for_gap(self, gap: float) -> float:
        """``|q|`` of the finger joints for a gel-face gap ``gap`` [m]: piecewise linear through ``close_gap_calib`` (gap
        decreasing with ``|q|``), extrapolated with the first segment below the smallest command, clamped to the largest."""
        qs = np.array([p[0] for p in self.close_gap_calib])
        gs = np.array([p[1] for p in self.close_gap_calib])
        if gap > gs[0]:
            q = qs[0] - (gap - gs[0]) * (qs[1] - qs[0]) / (gs[0] - gs[1])
        else:
            q = float(np.interp(-gap, -gs, qs))
        return float(np.clip(q, qs[0] - 0.002, qs[-1]))

    @staticmethod
    def joint_gap_for_close(magnitude: float) -> float:
        """The ``Action.gripper_gap`` value that commands finger joints ``J1_7 = -|q|, J1_8 = +|q|``."""
        return float(GRIPPER_WIDTH_OFFSET - 2.0 * float(magnitude))

    def set_gripper_gap(self, gap: float) -> float:
        """Partial open: the joint-space gap (``0.082 - 2 |q|``) to command for a gel-face gap ``gap`` outside the pinch
        range (the fingers are symmetric, so the two coincide).  Returned for ``Action.gripper_gap`` and remembered."""
        q = float(np.clip(0.5 * (GRIPPER_WIDTH_OFFSET - float(gap)), 0.0, 0.041))
        self.gripper_gap_cmd = self.joint_gap_for_close(q)
        return self.gripper_gap_cmd

    def pinch_close_gap(self) -> Optional[float]:
        """The joint-space gap of the calibrated close (``thickness - 2 * pinch_overlap`` between the gel faces), or None
        when the task closes with the fixed command."""
        if self.pinch_overlap is None:
            return None
        face_gap = max(self.grasp_thickness() - 2.0 * float(self.pinch_overlap), 0.0)
        self.gripper_gap_cmd = self.joint_gap_for_close(self.close_command_for_gap(face_gap))
        return self.gripper_gap_cmd

    # ------------------------------------------------------------------ anchors (fixture grasps)
    def attach(self, radius: Optional[float] = None, slot: int = 0) -> int:
        """Tie the soft body within ``radius`` of the pad midpoint to collider ``slot`` (an ideal grasp); returns the count."""
        r = self.attach_radius if radius is None else float(radius)
        mid = self.pad_mid()
        st = self.state
        if "particle_q" in st:
            ids = np.nonzero(np.linalg.norm(np.asarray(st["particle_q"], dtype=np.float64) - mid[None], axis=1) < r)[0]
            if len(ids):
                self.world.anchor_particles(ids, slot)
        else:
            nodes = np.asarray(st["cable_nodes"], dtype=np.float64)
            mids = 0.5 * (nodes[1:] + nodes[:-1])
            ids = np.nonzero(np.linalg.norm(mids - mid[None], axis=1) < r)[0]
            if len(ids):
                self.world.anchor_segments(ids, slot)
        self._attached = bool(len(ids))
        return int(len(ids))

    def detach(self) -> None:
        if "particle_q" in self.state:
            self.world.release_particles()
        else:
            self.world.release_segments()
        self._attached = False

    @property
    def attached(self) -> bool:
        return self._attached


def forearm_collider() -> Dict[str, Any]:
    """The left forearm cylinder of the sleeve task (a copy of :data:`FOREARM_COLLIDER`)."""
    return dict(FOREARM_COLLIDER)
