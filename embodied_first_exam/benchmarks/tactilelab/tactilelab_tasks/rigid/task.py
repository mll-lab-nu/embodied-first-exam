"""Task base class of the rigid assembly tasks (grasp -> insert -> optional screw).

A :class:`RigidAssemblyTask` is driven by ``tasks/<name>/cfg.yaml``:

* ``scene`` - objects, gel material, robot start posture (see :mod:`.scene`);
* ``parts`` - the assembly plan, one entry per held part in working order
  (``held``, ``target``, ``slot``, ``screw`` and per-part skill overrides);
* ``success`` - the latch logic shared by the assembly tasks: a part is
  *deep* the moment its tip is in the bore at ``depth >= bore - assembled_margin``
  (latched, so the release pop cannot undo it); the episode succeeds when every
  part is latched deep, the active part was lifted at least once (unless
  ``require_grasp_latch`` is off), and the gripper has released for good
  (``end_on_release``: the policy announced the finish release and the fingers
  opened by ``release_open_mm``; otherwise the end-effector moved
  ``assembled_clear`` away);
* ``tactile`` - which object meshes the two gel pads are raycast against.

The task exposes privileged accessors (object poses, insertion geometry, grasp
libraries, finger limit control, the finish-release announcement) that the scripted
skills in :mod:`.skills` use. Learned policies only see ``obs``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from ..assets.resolve import annotation_file
from ..core import math as m
from ..core.task import Task
from ..core.types import GEL_BODIES, Action, ObsDict
from . import geometry as G
from .scene import RigidTaskScene, build_scene_cfg

__all__ = ["PartSpec", "RigidAssemblyTask", "TactileRig"]


@dataclass
class PartSpec:
    """One entry of the assembly plan."""

    held: str
    target: str
    slot: str
    screw: bool = False
    held_usd: str = ""
    target_usd: str = ""
    grasp: Dict[str, Any] = field(default_factory=dict)
    insert: Dict[str, Any] = field(default_factory=dict)
    screw_params: Dict[str, Any] = field(default_factory=dict)
    skip_lift: bool = False
    """Grasp the part where it stands and do not retrieve it (nut already on the bolt)."""


class TactileRig:
    """Two GelSight Mini sensors on the right gripper, raycast against rigid object meshes."""

    def __init__(self, scene: RigidTaskScene, object_names: Sequence[str], device: str = "cuda", with_rgb: bool = True):
        import torch

        from ..tactile.mesh_sources import usd_mesh_in_frame
        from ..tactile.raycast import MeshTarget
        from ..tactile.sensor import GelSightMini

        self.scene = scene
        self.device = device
        self.with_rgb = bool(with_rgb)
        self.targets: Dict[str, MeshTarget] = {}
        from isaaclab.sim.utils.stage import get_current_stage

        stage = get_current_stage()
        for name in object_names:
            root = f"/World/Objects/{name}"
            frame = scene.rigid_body_prim_path(name)
            verts, faces = self._mesh(stage, root, frame, usd_mesh_in_frame)
            self.targets[name] = MeshTarget(verts, faces, device=device)
        self.sensors = {g: GelSightMini(g, device=device) for g in GEL_BODIES}
        self.pads = {("tactile_left" if g.endswith("left") else "tactile_right"): g for g in GEL_BODIES}
        self.contact_frames = 0
        self.frames = 0
        self._torch = torch

    @staticmethod
    def _mesh(stage, root: str, frame: str, usd_mesh_in_frame):
        from ..tactile.mesh_sources import iter_usd_meshes, transform_vertices, usd_mesh_triangles

        prim = stage.GetPrimAtPath(root)
        meshes = list(iter_usd_meshes(prim))
        coll = [p for p in meshes if "collision" in str(p.GetPath()).lower()]
        chosen = coll if coll else meshes
        if not chosen:
            raise ValueError(f"no mesh under {root}")
        from pxr import UsdGeom

        inv = UsdGeom.Xformable(stage.GetPrimAtPath(frame)).ComputeLocalToWorldTransform(0).GetInverse()
        verts, faces, n = [], [], 0
        for mp in chosen:
            v, f = usd_mesh_triangles(mp)
            mat = UsdGeom.Xformable(mp).ComputeLocalToWorldTransform(0) * inv
            verts.append(transform_vertices(v, np.array(mat)))
            faces.append(f + n)
            n += len(v)
        return np.concatenate(verts).astype(np.float32), np.concatenate(faces).astype(np.int32)

    def read(self) -> Dict[str, np.ndarray]:
        for name, tgt in self.targets.items():
            tgt.set_pose(self.scene.object_pose(name))
        targets = list(self.targets.values())
        out: Dict[str, np.ndarray] = {}
        any_contact = False
        for gel, pose in self.scene.robot.gel_poses().items():
            side = "left" if gel.endswith("left") else "right"
            if self.with_rgb:
                o = self.sensors[gel].observe(pose, targets)
            else:  # geometry only: skip the Taxim render
                height, press, contact_t = self.sensors[gel].grid.penetration(pose, targets)
                o = {"height_mm": height, "press_depth_mm": press, "contact": contact_t}
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
        self.contact_frames = 0
        self.frames = 0


class RigidAssemblyTask(Task):
    """Grasp / insert / screw task over a list of parts (see the module docstring)."""

    name = "rigid_assembly"
    success_hold = 1
    latch = True

    def __init__(
        self,
        cfg: Dict[str, Any],
        scene: Optional[RigidTaskScene] = None,
        obs_mode: str = "full",
        device: str = "cuda:0",
        cameras: bool = True,
        tactile: bool = True,
    ):
        super().__init__(cfg, scene, obs_mode)
        self.name = str(cfg.get("name", self.name))
        self.success_hold = int(cfg.get("success_hold", 1))
        self.max_steps = int(cfg.get("max_steps", 0))
        self.device = device
        self.cameras = bool(cameras)
        self.tactile_enabled = bool(tactile) and bool(cfg.get("tactile", {}).get("enabled", True))
        self.parts: List[PartSpec] = self._parse_parts(cfg)
        self.active = 0
        s = cfg.get("success", {})
        self.assembled_margin = float(s.get("assembled_margin", 0.005))
        self.assembled_lateral = float(s.get("assembled_lateral", 0.008))
        self.assembled_axis_deg = float(s.get("assembled_axis_deg", 15.0))
        self.final_margin = s.get("final_margin")
        self.require_grasp_latch = bool(s.get("require_grasp_latch", True))
        self.end_on_release = bool(s.get("end_on_release", True))
        self.release_open_mm = float(s.get("release_open_mm", 10.0))
        self.release_settle_steps = int(s.get("release_settle_steps", 0))
        self.assembled_clear = float(s.get("assembled_clear", 0.35))
        self.grasp_lift_thresh = float(s.get("grasp_lift_thresh", 0.04))
        self.grasp_hold_thresh = float(s.get("grasp_hold_thresh", 0.3))
        self.settle_ticks = int(cfg.get("scene", {}).get("settle_ticks", 60))
        self._usd_of = {str(o["name"]): str(o["usd"]) for o in cfg.get("scene", {}).get("objects", [])}
        # annotations
        self._axis: Dict[str, G.HeldAxis] = {}
        self._slots: Dict[tuple, G.Slot] = {}
        self._grasp_lib: Dict[str, np.ndarray] = {}
        for p in self.parts:
            self._axis[p.held] = G.load_held_axis(annotation_file(self._usd_of[p.held], "insertion_pose"))
            self._slots[(p.target, p.slot)] = G.load_slot(
                annotation_file(self._usd_of[p.target], "insertion_pose"), p.slot
            )
            try:
                self._grasp_lib[p.held] = G.load_grasp_candidates(
                    annotation_file(self._usd_of[p.held], "grasp_pose"), part=p.grasp.get("part", "body")
                )
            except (FileNotFoundError, KeyError):
                self._grasp_lib[p.held] = np.zeros((0, 7))
        # episode state
        n = len(self.parts)
        self._parts_deep = np.zeros(n, dtype=bool)
        self._ever_grasped = False
        self._held_reset_z = np.full(n, np.nan)
        self._finish_pending = False
        self._finish_close_q: Optional[np.ndarray] = None
        self._release_ticks = 0
        self._home_eef: Optional[np.ndarray] = None
        self._home_ref_xy: Optional[np.ndarray] = None
        self._home_ref_az = s.get("home_ref_azimuth_deg", cfg.get("home_ref_azimuth_deg"))
        self._stock_finger_limits = None
        self._stock_finger_gains = None
        self._last_metrics: Dict[str, float] = {}
        self.tactile: Optional[TactileRig] = None

    # ------------------------------------------------------------------ construction
    @staticmethod
    def _parse_parts(cfg: Dict[str, Any]) -> List[PartSpec]:
        out = []
        for p in cfg.get("parts", []):
            out.append(
                PartSpec(
                    held=str(p["held"]),
                    target=str(p["target"]),
                    slot=str(p["slot"]),
                    screw=bool(p.get("screw", False)),
                    grasp=dict(p.get("grasp", {})),
                    insert=dict(p.get("insert", {})),
                    screw_params=dict(p.get("screw_params", {})),
                    skip_lift=bool(p.get("skip_lift", False)),
                )
            )
        if not out:
            raise KeyError("cfg.parts is empty")
        return out

    @classmethod
    def scene_cfg(cls, cfg: Dict[str, Any], cameras: bool = True, device: str = "cuda:0"):
        """The :class:`SceneCfg` of a task configuration."""
        return build_scene_cfg(cfg, cameras=cameras, device=device)

    @classmethod
    def make_scene(cls, cfg: Dict[str, Any], cameras: bool = True, device: str = "cuda:0") -> RigidTaskScene:
        """An unbuilt :class:`RigidTaskScene` (the object USDs need its rigid-body schema pass)."""
        return RigidTaskScene(cls.scene_cfg(cfg, cameras=cameras, device=device))

    def build(self) -> "RigidAssemblyTask":
        """Create and build the Isaac Lab scene (the app must be launched first)."""
        if self.scene is None:
            scene = self.make_scene(self.cfg, cameras=self.cameras, device=self.device)
            scene.build()
            self.scene = scene
        if self.tactile_enabled and self.tactile is None:
            self.attach_tactile(self.device)
        return self

    def attach_tactile(self, device: Optional[str] = None) -> Optional[TactileRig]:
        """Create the two GelSight Mini sensors (``cfg.tactile.targets`` meshes) and register them."""
        if self.tactile is not None:
            return self.tactile
        if not bool(self.cfg.get("tactile", {}).get("enabled", True)):
            return None
        names = self.cfg.get("tactile", {}).get("targets") or [p.held for p in self.parts]
        from ..tactile import sensor_device

        self.tactile = TactileRig(
            self.scene,
            [str(n) for n in names],
            device=sensor_device(device or self.device),
            with_rgb=self.obs_mode == "full",
        )
        self.sensors["tactile"] = self.tactile.read
        return self.tactile

    @property
    def truncated(self) -> bool:
        return self.timed_out

    @property
    def truncation_reason(self) -> Optional[str]:
        return "timeout" if self.timed_out else None

    def close(self) -> None:
        if self.scene is not None:
            self.scene.close()

    # ------------------------------------------------------------------ reset
    def _reset_scene(self, seed: int) -> None:
        sc = self.scene
        sc.reset_robot()
        sc.reset_objects()
        self.restore_finger_limits()
        for _ in range(self.settle_ticks):
            sc.step(Action.hold())
        self.active = 0
        self._parts_deep[:] = False
        self._ever_grasped = False
        self._finish_pending = False
        self._finish_close_q = None
        self._release_ticks = 0
        for k, p in enumerate(self.parts):
            self._held_reset_z[k] = float(sc.object_pose(p.held)[2])
        self._home_eef = sc.ee_pose(0).copy()
        self._home_ref_xy = sc.object_pose(self.parts[0].held)[:2].copy()
        if self.tactile is not None:
            self.tactile.reset_counters()

    # ------------------------------------------------------------------ privileged accessors (used by the skills)
    @property
    def part(self) -> PartSpec:
        return self.parts[self.active]

    def set_active_part(self, index: int) -> None:
        self.active = int(index)
        self._held_reset_z[self.active] = float(self.scene.object_pose(self.part.held)[2])

    def eef_pose(self) -> np.ndarray:
        return self.scene.ee_pose(0)

    def object_pose(self, name: str) -> np.ndarray:
        return self.scene.object_pose(name)

    def held_pose(self, index: Optional[int] = None) -> np.ndarray:
        return self.scene.object_pose(self.parts[self.active if index is None else index].held)

    def target_pose(self, index: Optional[int] = None) -> np.ndarray:
        return self.scene.object_pose(self.parts[self.active if index is None else index].target)

    def held_axis(self, index: Optional[int] = None) -> G.HeldAxis:
        return self._axis[self.parts[self.active if index is None else index].held]

    def slot(self, index: Optional[int] = None) -> G.Slot:
        p = self.parts[self.active if index is None else index]
        return self._slots[(p.target, p.slot)]

    def grasp_candidates(self, index: Optional[int] = None) -> np.ndarray:
        return self._grasp_lib[self.parts[self.active if index is None else index].held]

    def geometry(self, index: Optional[int] = None) -> Dict[str, Any]:
        k = self.active if index is None else index
        return G.insertion_world(self.held_pose(k), self.held_axis(k), self.target_pose(k), self.slot(k))

    def depth_latched(self, index: Optional[int] = None) -> bool:
        return bool(self._parts_deep[self.active if index is None else index])

    def wrist_override(self, joint_name: str, target: Optional[float]) -> bool:
        """Joint-space wrist drive is not available on this backend (returns False)."""
        return False

    def home_eef_pose(self, index: Optional[int] = None) -> np.ndarray:
        """Episode-start end-effector pose, rotated about the robot base toward part ``index``."""
        home = self._home_eef.copy()
        if index is None or self._home_ref_xy is None:
            return home
        base = self.scene.base_pose
        bx, by = float(base[0]), float(base[1])
        cur = self.scene.object_pose(self.parts[index].held)
        if self._home_ref_az is not None:
            ref_az = math.radians(float(self._home_ref_az))
        else:
            ref_az = math.atan2(float(self._home_ref_xy[1]) - by, float(self._home_ref_xy[0]) - bx)
        dth = math.atan2(float(cur[1]) - by, float(cur[0]) - bx) - ref_az
        dth = (dth + math.pi) % (2.0 * math.pi) - math.pi
        if abs(dth) < math.radians(1.0):
            return home
        c, s = math.cos(dth), math.sin(dth)
        x, y = home[0] - bx, home[1] - by
        home[0] = c * x - s * y + bx
        home[1] = s * x + c * y + by
        home[3:7] = m.quat_mul(m.quat_from_axis_angle([0.0, 0.0, 1.0], dth), home[3:7])
        return home

    # ------------------------------------------------------------------ finger limits
    def _finger_ids(self):
        return self.scene.robot._finger_ids_t[0:2]

    def set_finger_limits(self, vel_limit: float = 0.0, effort_limit: float = 0.0) -> None:
        """Cap the right finger joint velocity / drive effort in PhysX (0 = leave unchanged)."""
        import torch

        art = self.scene.robot.articulation
        ids = self._finger_ids()
        if self._stock_finger_limits is None:
            view = art.root_physx_view
            self._stock_finger_limits = (
                view.get_dof_max_velocities()[:, ids.cpu()].clone(),
                view.get_dof_max_forces()[:, ids.cpu()].clone(),
            )
        if vel_limit > 0.0:
            art.write_joint_velocity_limit_to_sim(
                torch.full((1, 2), float(vel_limit), device=art.device), joint_ids=ids
            )
        if effort_limit > 0.0:
            art.write_joint_effort_limit_to_sim(
                torch.full((1, 2), float(effort_limit), device=art.device), joint_ids=ids
            )

    def restore_finger_limits(self) -> None:
        art = self.scene.robot.articulation
        ids = self._finger_ids()
        if self._stock_finger_limits is not None:
            vel, eff = self._stock_finger_limits
            art.write_joint_velocity_limit_to_sim(vel.to(art.device), joint_ids=ids)
            art.write_joint_effort_limit_to_sim(eff.to(art.device), joint_ids=ids)
        if self._stock_finger_gains is not None:
            k, d = self._stock_finger_gains
            art.write_joint_stiffness_to_sim(k.to(art.device), joint_ids=ids)
            art.write_joint_damping_to_sim(d.to(art.device), joint_ids=ids)

    def set_finger_gains(self, stiffness: float = 0.0, damping: float = 0.0) -> None:
        """Override the right finger PD gains for this episode (0 = leave unchanged).

        A very stiff proportional gain saturates the finger drive at its effort limit, which
        emulates a constant-force jaw (the thin-walled parts are held by the drive's full
        force instead of the small spring force of the stock gains). Restored at reset.
        """
        import torch

        art = self.scene.robot.articulation
        ids = self._finger_ids()
        if self._stock_finger_gains is None:
            self._stock_finger_gains = (
                art.data.joint_stiffness[:, ids].clone(),
                art.data.joint_damping[:, ids].clone(),
            )
        if stiffness > 0.0:
            art.write_joint_stiffness_to_sim(torch.full((1, 2), float(stiffness), device=art.device), joint_ids=ids)
        if damping > 0.0:
            art.write_joint_damping_to_sim(torch.full((1, 2), float(damping), device=art.device), joint_ids=ids)

    # ------------------------------------------------------------------ finish-release gate
    def note_finish_release(self) -> None:
        """The policy is about to open the jaws for good (snapshot the finger joints)."""
        q = self.scene.robot.joint_pos()[12:14]
        self._finish_close_q = q.copy()
        self._finish_pending = True
        self._release_ticks = 0

    def clear_finish_release(self) -> None:
        self._finish_pending = False
        self._release_ticks = 0

    def _finish_released(self) -> bool:
        if not self._finish_pending or self._finish_close_q is None:
            self._release_ticks = 0
            return False
        q = self.scene.robot.joint_pos()[12:14]
        opened = bool(np.all(np.abs(q - self._finish_close_q) >= self.release_open_mm * 1e-3))
        self._release_ticks = self._release_ticks + 1 if opened else 0
        return opened and self._release_ticks >= self.release_settle_steps

    def finish_release_done(self) -> bool:
        """True once the announced release has opened and settled (always True when the gate is off)."""
        if not self.end_on_release:
            return True
        return self._finish_pending and self._release_ticks >= self.release_settle_steps

    # ------------------------------------------------------------------ success
    def _part_state(self, k: int) -> Dict[str, float]:
        geo = self.geometry(k)
        d, lat, _ = G.signed_depth_lateral(geo["tip_w"], geo["top_w"], geo["n_w"])
        ax = G.angle_between_deg(geo["axis_w"], geo["n_w"])
        return {"depth": d, "lateral": lat, "axis_err_deg": ax, "bore": geo["depth"]}

    def success_predicate(self) -> bool:
        if self.scene is None:
            return False
        eef = self.eef_pose()
        live_all = True
        for k in range(len(self.parts)):
            st = self._part_state(k)
            in_bore = st["lateral"] <= self.assembled_lateral and st["axis_err_deg"] <= self.assembled_axis_deg
            if in_bore and st["depth"] >= st["bore"] - self.assembled_margin:
                self._parts_deep[k] = True
            if self.final_margin is not None:
                live_all = live_all and in_bore and st["depth"] >= st["bore"] - float(self.final_margin)
            if k == self.active:
                self._last_metrics = st
        held = self.held_pose()
        lifted = float(held[2]) - float(self._held_reset_z[self.active]) > self.grasp_lift_thresh
        near = float(np.linalg.norm(eef[:3] - held[:3])) < self.grasp_hold_thresh
        if lifted and near:
            self._ever_grasped = True
        released = self._finish_released()  # advances the settle counter every tick
        assembled = bool(self._parts_deep.all()) and (self._ever_grasped or not self.require_grasp_latch) and live_all
        if self.end_on_release:
            return assembled and released
        clear = float(np.linalg.norm(eef[:3] - held[:3])) >= self.assembled_clear
        return assembled and clear

    # ------------------------------------------------------------------ observation
    def privileged_obs(self) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        for o in self.scene.cfg.objects:
            out[f"object_pose/{o.name}"] = self.scene.object_pose(o.name).astype(np.float32)
        st = self._last_metrics or self._part_state(self.active)
        out["insert_depth"] = np.asarray(st["depth"], dtype=np.float32)
        out["insert_lateral"] = np.asarray(st["lateral"], dtype=np.float32)
        out["insert_axis_err_deg"] = np.asarray(st["axis_err_deg"], dtype=np.float32)
        out["active_part"] = np.asarray(self.active, dtype=np.int32)
        out["parts_deep"] = self._parts_deep.copy()
        return out

    def metrics(self) -> Dict[str, float]:
        st = self._last_metrics
        d = {
            "depth_mm": 1e3 * st.get("depth", float("nan")),
            "lateral_mm": 1e3 * st.get("lateral", float("nan")),
            "axis_err_deg": st.get("axis_err_deg", float("nan")),
            "active_part": self.active,
            "parts_deep": int(self._parts_deep.sum()),
            "ever_grasped": int(self._ever_grasped),
        }
        if self.tactile is not None:
            d["tactile_contact_frames"] = self.tactile.contact_frames
        return d
