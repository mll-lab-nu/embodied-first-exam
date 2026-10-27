"""``DoughTask``: a dough (implicit MPM) or FEM plug task co-simulated with the Isaac robot.

The robot, the fixtures and (for ``dough_fill_tray``) the scraper live in PhysX; the deformable lives in a Newton sidecar
world (``mpm.dough`` / ``fem.plugpad``).  Every ``mpm_every``-th control tick the task sends the
poses of the world's kinematic colliders - the two gel pads (direct-sensor tasks) or the tool - and gets the particles back
(asynchronously when ``async_mpm``: the sidecar works on step k while Isaac runs the next ticks, one sidecar step of lag).  The dough's reaction wrench on the tool is fed back to the PhysX tool (``reaction_gain``, clipped to
50 N); the gel pads get no reaction (the dough does not exist in PhysX).

Frames: env frame for everything Isaac; the sidecar world runs in the *anchored* frame (origin ``task.anchor`` = the
plate / tray-floor / hole-plate top).  Success: the task's report (``pinch_report`` / ``fill_report`` / ``plug_pad_report``) is
evaluated every ``check_every`` sidecar steps; ``success_predicate`` = the last report is ok AND the working frame (pad-pair
centre or tool origin) is ``clear_z`` above the anchor; held ``success_hold`` ticks (latched).

Observations (``obs["privileged"]``): ``pad_poses`` (2, 7) xyzw env frame, ``tool_pose`` (7) wxyz (the pad-pair frame in
direct mode), ``dough_top`` (nx, ny) float32 column-top height map over the task's grid [m], ``dough_zmax`` / ``dough_n``,
``particle_q`` (P, 3) for the plug (810 nodes), and the report's numbers (``thickness`` ...; NaN before the first check).
"""

from __future__ import annotations

import math

import time
from typing import Any, Dict, List, Optional

import numpy as np

from ..core import math as m
from ..core.task import Task
from ..core.types import CONTROL_DT, GRIPPER_CLOSE, GRIPPER_OPEN, Action
from ..softbody_geom import dough_metrics as dm
from ..softbody_geom import spec
from ..softbody_geom.dough_task import DoughScene
from . import pads as pd
from .scene import build_dough_scene, build_scene, make_scene, tool_start_pose

REACTION_CLIP_N = 50.0
"""The dough force fed back to the PhysX tool is clipped to this per axis."""


def grip_to_tool(tool_kind: str, eef_to_grip, tool_yaw_deg: float = 0.0):
    """Tool frame in the end-effector frame ``(pos, quat wxyz)``: the tool points opposite to the gripper's approach axis
    (180 degrees about x), yawed about its own z, held ``GRIP_Z`` above its working face at the pads' grip point."""
    from ..softbody_geom import tools as tl

    flip = np.array([0.0, 1.0, 0.0, 0.0])
    yaw = float(np.deg2rad(tool_yaw_deg))
    q = m.quat_normalize(m.quat_mul(flip, np.array([math.cos(0.5 * yaw), 0.0, 0.0, math.sin(0.5 * yaw)])))
    pos = np.asarray(eef_to_grip, dtype=np.float64) + np.array([0.0, 0.0, tl.GRIP_Z[str(tool_kind)]])
    return pos, q


class DoughTask(Task):
    """Base of the four dough / plug tasks.  Subclasses set :attr:`kind` and implement :meth:`judge` /
    :meth:`report_metrics` (and :attr:`metric_names`).

    ``cfg["task"]`` (the task block ``p``): ``kind``, ``anchor``, ``direct_pads``, ``colliders`` (the two pads), the scene
    numbers of the sidecar builder, ``mpm_every``, ``check_every``, ``clear_z``, ``async_mpm``, ``reaction_gain``,
    ``success_hold``, ``max_steps``, ``settle_ticks``; tool tasks add ``tool_name`` / ``tool_kind`` / ``eef_to_grip`` /
    ``tool_yaw_deg`` / ``tool_pickup`` / ``rack``.  ``cfg["sidecar"]``: ``min_free_mib``, ``gpu_wait_s``, ``call_timeout``.
    """

    name = "dough"
    kind = "pinch"
    metric_names: tuple = ()
    success_hold = 20
    latch = True

    def __init__(
        self,
        cfg: Optional[dict] = None,
        scene=None,
        obs_mode: str = "full",
        device: str = "cuda:0",
        cameras: bool = True,
        tactile: bool = True,
    ):
        super().__init__(cfg, scene, obs_mode)
        self.name = str(self.cfg.get("name", self.name))
        self.device = str(device)
        self.cameras = bool(cameras) and obs_mode == "full"
        self.tactile_enabled = bool(tactile) and obs_mode == "full"
        p = self.p = dict(self.cfg.get("task") or {})
        self.kind = str(p.get("kind", self.kind))
        self.anchor = np.asarray(p["anchor"], dtype=np.float64)
        self.direct = bool(p.get("direct_pads", False))
        self.mpm_every = max(1, int(p.get("mpm_every", 2)))
        self.check_every = max(1, int(p.get("check_every", 10)))
        self.clear_z = float(p.get("clear_z", 0.035))
        self.async_mpm = bool(p.get("async_mpm", True))
        self.reaction_gain = 0.0 if self.direct else float(p.get("reaction_gain", 1.0))
        self.success_hold = int(p.get("success_hold", 20))
        self.max_steps = int(p.get("max_steps", 3600))
        self.settle_ticks = int(p.get("settle_ticks", 30))
        self.hold_release_ticks = int(p.get("hold_release_ticks", 45))
        self.tool_name = str(p.get("tool_name", "scraper_tool"))
        self.tool_pickup = bool(p.get("tool_pickup", True))
        self.pad_specs = pd.pad_specs(p.get("colliders"))
        self.sidecar_cfg = dict(self.cfg.get("sidecar") or {})
        self.tactile_cfg = dict(self.cfg.get("tactile") or {})
        self.dough: Optional[DoughScene] = None
        self.client = None
        self.visual = None
        self.tactile = None
        self._q: Optional[np.ndarray] = None  # anchored particles
        self._fut = None
        self._tick = 0
        self._mpm_steps = 0
        self._last_check = 0
        self._report = None
        self._done = False
        self._cleared = False
        self._wrench = np.zeros(6)
        self._hold_tool = False
        self._close_ticks = 0
        self._gripper_cmd = np.array([GRIPPER_OPEN, GRIPPER_OPEN], dtype=np.int64)
        self._error: Optional[str] = None
        self.mpm_ms = 0.0
        self._tgt_prev = None
        self._tgt_vel = None
        self._tgt_tick = 0
        self._plug_tris = None

    # ------------------------------------------------------------------ construction
    @staticmethod
    def make_scene(cfg: dict, cameras: bool = True, device: str = "cuda:0"):
        """The task's (unbuilt) Isaac Lab scene (see :func:`tactilelab_tasks.dough.scene.make_scene`)."""
        return make_scene(cfg, cameras=cameras, device=device)

    def build(self) -> "DoughTask":
        """Build the scene when the task was created without one and attach the tactile sensors (the app must be running)."""
        if self.scene is None:
            self.scene = build_scene(self.cfg, cameras=self.cameras, device=self.device)
        if self.tactile_enabled:
            self.attach_tactile(device=self.device)
        return self

    @classmethod
    def from_cfg(cls, cfg: dict, obs_mode: str = "full", device: str = "cuda:0") -> "DoughTask":
        """Build the Isaac scene (the app must be running) and the task; attaches the tactile sensors in ``full`` mode."""
        return cls(cfg, None, obs_mode, device=device).build()

    @property
    def truncated(self) -> bool:
        """True when the sidecar or the judge failed (the episode cannot be completed)."""
        return self._error is not None

    @property
    def truncation_reason(self) -> Optional[str]:
        return self._error

    def attach_tactile(self, device: str = "cuda"):
        """GelSight-Mini sensors on the two gel pads (``cfg.tactile.enable``); returns the provider (``.pads``)."""
        if self.tactile_cfg.get("enable", True) is False or self.tactile is not None or self.scene is None:
            return self.tactile
        from .tactile import DoughTactile

        self.tactile = DoughTactile(self.scene, device=device)
        if not self.direct:
            self.tactile.add_rigid(self.tool_name)  # the held scraper is what the gels touch
        self.sensors["tactile"] = self.tactile
        return self.tactile

    # ------------------------------------------------------------------ hooks for the subclasses
    def make_dough_scene(self, seed: int) -> DoughScene:
        return build_dough_scene(self.p, seed=0)  # nominal layout: the seed does not change the scene

    def judge(self, scene: DoughScene, q: np.ndarray):
        """The task's report (``.ok``, ``.why`` + numbers) of the anchored particles ``q``."""
        raise NotImplementedError

    def report_metrics(self, report) -> Dict[str, float]:
        return {}

    # ------------------------------------------------------------------ reset
    def _reset_scene(self, seed: int) -> None:
        sc = self.scene
        self._error = None
        self._gripper_cmd = np.array([GRIPPER_OPEN, GRIPPER_OPEN], dtype=np.int64)
        sc.reset_robot()
        sc.robot.set_gripper(self._gripper_cmd)
        sc.reset_objects()
        if not self.direct:
            sc.apply_external_force(self.tool_name, np.zeros(3))
        for _ in range(self.settle_ticks):
            sc.step(Action.hold(self._gripper_cmd))
        self.dough = self.make_dough_scene(seed)
        self._tick = 0
        self._mpm_steps = 0
        self._last_check = 0
        self._report = None
        self._done = False
        self._cleared = False
        self._wrench = np.zeros(6)
        self._fut = None
        self._close_ticks = 0
        self._tgt_prev = self._tgt_vel = None
        self._hold_tool = False
        if (
            not self.direct and not self.tool_pickup
        ):  # the pre-grasped tool: teleported into the open gripper until the fingers hold it
            self.place_tool_in_gripper()
            self._hold_tool = True
        self._q = self._reset_world()
        self._draw()

    # ------------------------------------------------------------------ sidecar world
    def _newton(self):
        from ..backends.newton_client import shared_client

        sc = self.sidecar_cfg
        return shared_client(
            min_free_mib=int(sc.get("min_free_mib", 3000)),
            gpu_wait=float(sc.get("gpu_wait_s", 600.0)),
            call_timeout=float(sc.get("call_timeout", 900.0)),
        )

    def _reset_world(self) -> np.ndarray:
        """(Re)create the sidecar world of this episode; returns the initial anchored particles."""
        from ..backends.newton_client import DoughClient, PlugPadClient

        d = self.dough
        poses = self.world_poses()
        fresh = self.client is None or getattr(self.client, "n", -1) != len(d.points)
        if self.kind == "plug_pads":
            if fresh:
                cfg = dict(d.world_cfg)
                cfg["fps"] = int(round(1.0 / (self.mpm_every * CONTROL_DT)))
                self.client = PlugPadClient(cfg, poses, client=self._newton())
                self.client.n = len(d.points)
                q = self.client.q if self.client.q is not None else self.client.reset(poses)
            else:
                q = self.client.reset(poses)
            self._plug_tris = None
            return np.asarray(q, dtype=np.float32)
        if fresh:
            cfg = dict(d.world_cfg)
            cfg["dt"] = self.mpm_every * CONTROL_DT
            self.client = DoughClient(cfg, d.points, d.pvol, poses=poses, client=self._newton())
            return np.asarray(self.client.read(), dtype=np.float32)
        return np.asarray(self.client.reset(d.points, poses), dtype=np.float32)

    def world_poses(self) -> np.ndarray:
        """Poses of the world's kinematic colliders in the anchored frame (xyzw): the two pads, or the tool ``(1, 7)``."""
        if self.direct or self.kind == "plug_pads":
            p = self.pad_poses().copy()
            p[:, :3] -= self.anchor
            return p
        t = self.tool_pose()
        return np.concatenate([t[:3] - self.anchor, spec.quat_wxyz_to_xyzw(t[3:7])])[None, :]

    # ------------------------------------------------------------------ frames
    def pad_poses(self) -> np.ndarray:
        """``(2, 7)`` env-frame xyzw poses of the two gel-pad colliders."""
        return pd.pad_poses_from_gels(self.pad_specs, self.scene.robot.gel_poses())

    def tool_pose(self) -> np.ndarray:
        """Env-frame pose7 (wxyz) of the working frame: the tool body, or the pad-pair frame in direct mode."""
        if self.direct:
            return pd.mid_pose_wxyz(self.pad_poses())
        return self.scene.object_pose(self.tool_name)

    def tool_cleared(self, tool_pose: Optional[np.ndarray] = None) -> bool:
        t = self.tool_pose() if tool_pose is None else tool_pose
        return float(t[2] - self.anchor[2]) >= self.clear_z

    def tool_pose_in_gripper(self) -> np.ndarray:
        """Where the (open) gripper holds the tool: the nominal grip transform applied to the current end-effector pose."""
        pos, q = grip_to_tool(
            str(self.p.get("tool_kind", "scraper_tool")),
            self.p.get("eef_to_grip", (0.0, 0.0, 0.177)),
            float(self.p.get("tool_yaw_deg", 0.0)),
        )
        return m.pose_compose(self.scene.ee_pose(0), np.concatenate([pos, q]))

    def place_tool_in_gripper(self) -> np.ndarray:
        """Teleport the tool into the open gripper (the pre-grasped start of the non-pickup scripts)."""
        pose = self.tool_pose_in_gripper()
        self.scene.set_object_pose(self.tool_name, pose)
        return pose

    def hold_tool(self, on: bool) -> None:
        """While on, the tool is re-teleported into the gripper every tick (a fixture for the closing fingers)."""
        self._hold_tool = bool(on)

    # ------------------------------------------------------------------ stepping
    def _apply_action(self, action: Action) -> None:
        self._gripper_cmd = action.gripper.copy()
        self.scene.step(action)
        self._advance()

    def _advance(self) -> None:
        """One control tick of the deformable (after the physics step)."""
        self._tick += 1
        if self._hold_tool:
            self.place_tool_in_gripper()
            self._close_ticks = self._close_ticks + 1 if int(self._gripper_cmd[0]) == GRIPPER_CLOSE else 0
            if self._close_ticks >= self.hold_release_ticks:  # the fingers have closed on it: hand it over
                self._hold_tool = False
        self._apply_reaction()
        if self._tick % self.mpm_every:
            self._between_updates()
            return
        if self._error:
            return
        t0 = time.perf_counter()
        try:
            poses = self.world_poses()
            if self.async_mpm:
                q = self.client.finish(self._fut) if self._fut is not None else self._q
                self._fut = self.client.submit_step(poses)
            else:
                q = self.client.step(poses)
        except Exception as exc:  # noqa: BLE001 - keep the episode alive, report the error
            self._error = f"sidecar: {exc!r}"
            return
        self.mpm_ms = 0.9 * self.mpm_ms + 0.1 * 1e3 * (time.perf_counter() - t0)
        self._q = np.asarray(q, dtype=np.float32)
        self._mpm_steps += 1
        if hasattr(self.client, "wrench"):
            self._wrench = np.asarray(self.client.wrench, dtype=np.float64)
        self._draw()
        if self._mpm_steps - self._last_check >= self.check_every:
            self._last_check = self._mpm_steps
            try:
                self._report = self.judge(self.dough, self._q)
                self._cleared = self.tool_cleared()
                self._done = bool(self._report.ok) and self._cleared
            except Exception as exc:  # noqa: BLE001
                self._error = f"judge: {exc!r}"

    def _apply_reaction(self) -> None:
        """Two-way coupling of the tool: the dough's last force on it becomes a constant external force on the PhysX tool
        (written at every physics substep by the scene; zero while the tool is held by the fixture)."""
        if self.reaction_gain <= 0.0 or self.direct:
            return
        f = (
            np.zeros(3)
            if self._hold_tool
            else np.clip(self._wrench[:3], -REACTION_CLIP_N, REACTION_CLIP_N) * self.reaction_gain
        )
        self.scene.apply_external_force(self.tool_name, f)

    def _between_updates(self) -> None:
        """Ticks without a sidecar step: the plug's tactile target is carried on with its bulk velocity (the pads move every tick)."""
        if (
            self.kind != "plug_pads"
            or self.tactile is None
            or self._tgt_vel is None
            or not bool(self.p.get("tactile_extrapolate", True))
        ):
            return
        lead = self._tick - self._tgt_tick
        self.tactile.set_soft(pd.extrapolate_points(self._tgt_prev, self._tgt_vel, lead, CONTROL_DT))

    # ------------------------------------------------------------------ visuals and tactile targets
    def _draw(self) -> None:
        if self._q is None or self.scene is None or self.obs_mode != "full":
            return
        if self.kind == "plug_pads":
            self._draw_plug()
        else:
            self._draw_dough()

    def _draw_dough(self) -> None:
        """Marching-cubes surface of the particles: the camera mesh and (direct mode) the tactile target, inset by ``tactile_inset``."""
        from ..softbody_geom.surface import cloud_to_mesh
        from .visual import SoftMeshVisual

        p, d = self.p, self.dough
        pts = self._q + self.anchor
        cell = float(p.get("mesh_voxel") or d.world_cfg["voxel"])
        lo, hi = self.anchor + np.asarray(d.world_cfg["bounds"][0]), self.anchor + np.asarray(d.world_cfg["bounds"][1])
        mesh = cloud_to_mesh(
            pts,
            cell,
            lo,
            hi,
            sigma=float(p.get("visual_sigma", 1.0)),
            level=float(p.get("visual_level", 0.5)),
            tight=p.get("mesh_voxel") is not None,
            ref=cell**3 / d.pvol,
        )
        if self.visual is None:
            self.visual = SoftMeshVisual("/World/Dough", color=tuple(p.get("dough_color", (0.74, 0.52, 0.26))))
        if mesh is None:
            self.visual.hide()
            return
        v, f, nrm = mesh
        self.visual.update(v, f, -nrm)
        if self.direct and self.tactile is not None:
            inset = float(p.get("tactile_inset", 0.0))
            self.tactile.set_soft(v - inset * nrm if inset > 0.0 else v, f)

    def _draw_plug(self) -> None:
        """The plug's boundary (fixed topology): camera mesh + tactile target pushed out by ``tactile_inflate``."""
        from ..softbody_geom import plug_scene as ps
        from .tactile import surface_normals
        from .visual import SoftMeshVisual

        pts = (self._q + self.anchor).astype(np.float32)
        if self._plug_tris is None:
            n_cells, _ = ps.grid_dims(self.dough.extra["spec"])
            self._plug_tris = ps.grid_surface_tris(n_cells)
            if self.visual is None:
                self.visual = SoftMeshVisual("/World/Plug", color=tuple(self.p.get("plug_color", (0.85, 0.25, 0.20))))
            self.visual.update(pts, self._plug_tris)
            first = True
        else:
            self.visual.update(pts)
            first = False
        if self.tactile is None:
            return
        infl = float(self.p.get("tactile_inflate", 0.0))
        tgt = (pts + infl * surface_normals(pts, self._plug_tris)).astype(np.float32) if infl > 0.0 else pts
        if (
            self._tgt_prev is not None
            and self._tgt_prev.shape == tgt.shape
            and bool(self.p.get("tactile_velocity", True))
        ):
            self._tgt_vel = ((tgt - self._tgt_prev) / (self.mpm_every * CONTROL_DT)).astype(np.float32)
        self._tgt_prev, self._tgt_tick = tgt, self._tick
        self.tactile.set_soft(tgt, self._plug_tris if first or self.tactile.soft is None else None)

    # ------------------------------------------------------------------ success / observation
    def success_predicate(self) -> bool:
        return bool(self._done)

    def report(self) -> Dict[str, Any]:
        """A fresh judgement of the particles now (``ok`` / ``why`` / ``cleared`` + the task numbers)."""
        rep = self.judge(self.dough, self._q)
        out = {"ok": bool(rep.ok), "why": rep.why, "cleared": self.tool_cleared()}
        out.update(self.report_metrics(rep))
        return out

    def particles(self) -> np.ndarray:
        """Env-frame particles ``(n, 3)``."""
        return self._q + self.anchor

    def privileged_obs(self) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        pads = self.pad_poses()
        out["pad_poses"] = pads.astype(np.float32)
        out["tool_pose"] = self.tool_pose().astype(np.float32)
        if self._q is not None and self.dough is not None:
            q = self._q
            out["dough_top"] = dm.column_top(q, self.dough.grid).astype(np.float32)
            out["dough_zmax"] = np.float32(q[:, 2].max() if len(q) else 0.0)
            out["dough_n"] = np.int32(len(q))
            if self.kind == "plug_pads":
                out["particle_q"] = (q + self.anchor).astype(np.float32)
        mets = self.report_metrics(self._report) if self._report is not None else {}
        for k in self.metric_names:
            out[k] = np.float32(mets.get(k, float("nan")))
        return out

    def metrics(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "report_ok": bool(self._report.ok) if self._report is not None else False,
            "cleared": bool(self._cleared),
            "mpm_ms": float(self.mpm_ms),
        }
        if self._report is not None:
            d["why"] = str(self._report.why)
            d.update({k: float(v) for k, v in self.report_metrics(self._report).items()})
        if self._error:
            d["error"] = self._error
        return d

    # ------------------------------------------------------------------ state
    def get_state(self) -> Dict[str, Any]:
        st = super().get_state()
        st["dough"] = {
            "q": None if self._q is None else self._q.copy(),
            "mpm_steps": self._mpm_steps,
            "tick": self._tick,
        }
        return st

    def set_state(self, state: Dict[str, Any]) -> None:
        st = dict(state)
        dough = st.pop("dough", None)
        super().set_state(st)
        if dough is not None and dough.get("q") is not None and self.client is not None:
            # the particles are restored stress-free (the solver's strain history is not part of the state blob)
            self._fut = None
            q = np.asarray(dough["q"], dtype=np.float32)
            self._q = np.asarray(
                self.client.reset(q, self.world_poses())
                if self.kind != "plug_pads"
                else self.client.reset(self.world_poses()),
                dtype=np.float32,
            )
            self._mpm_steps = int(dough.get("mpm_steps", 0))
            self._tick = int(dough.get("tick", 0))
            self._draw()

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except Exception:  # noqa: BLE001
                pass
            self.client = None


__all__ = ["DoughTask", "REACTION_CLIP_N", "tool_start_pose"]
