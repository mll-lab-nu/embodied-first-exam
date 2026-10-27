"""Scripted lift policy: grasp the lying bottle, lift, reorient upright, place on the pad.

Phases (right arm; the left arm holds its parked pose):

``init`` -> ``pre_grasp`` -> ``grasp`` -> ``close`` -> ``retrieve`` -> ``grasp_settle``
-> ``reorient`` -> ``pre_place`` -> ``place`` -> ``open`` -> ``settle`` [-> ``retreat``]

* The grasp is the roll-corrected body grasp: from the bottle's
  measured orientation the part-frame direction pointing world-up is found and the hand
  is placed ``standoff`` along it, approach axis (hand +z) toward the bottle axis and the
  jaw axis (hand +x) along the bottle's diametral direction; the jaw sign is the one
  needing the least wrist rotation unless the configuration pins it.
* ``reorient`` rotates the measured bottle axis onto world up in hops of at most
  ``step_deg`` about the bottle's own centre (the hand orbits through the live grip
  transform), re-measuring after every hop, then dwells ``hold_ticks``.
* ``place`` seats the bottle's base (``bottom_center``) on the pad centre through the
  grip transform captured at the start of the pre-place move, releases and optionally
  retreats.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from ...core import math as m
from ...core.policy import Gripper, Hold, MoveL, PhaseBase, PhasedPolicy, ee_pose
from ...core.types import GRIPPER_CLOSE, GRIPPER_OPEN, Action
from ...rigid import geometry as G
from .task import bottom_center, place_target_position

UP = np.array([0.0, 0.0, 1.0])

__all__ = ["Policy", "ReorientPhase", "roll_corrected_grasps", "select_grasp"]


# --------------------------------------------------------------------------- grasp family
def roll_corrected_grasps(bottle_pose: np.ndarray, standoff: float, bands: Sequence[float]) -> List[Dict[str, Any]]:
    """Body-radial grasp family of a lying bottle, from its measured orientation.

    Returns ``[{pose (env frame), band, sign}]``: for every band (height along the
    bottle axis) two wrist poses whose jaw axis runs along +/- the diametral direction.
    Raises ``ValueError`` if the bottle is not lying (axis within about 60 deg of vertical).
    """
    bottle_pose = np.asarray(bottle_pose, dtype=np.float64)
    u_p = m.quat_rotate_inverse(bottle_pose[3:7], UP)  # world-up in the part frame
    rn = float(np.linalg.norm(u_p[:2]))
    if rn < 0.5:
        raise ValueError("bottle is not lying: its axis is near vertical")
    rhat = u_p[:2] / rn
    z_h = np.array([-rhat[0], -rhat[1], 0.0])  # approach: radially inward
    t = np.array([-rhat[1], rhat[0], 0.0])  # diametral direction (part z x rhat)
    out = []
    for zg in bands:
        for sgn in (1.0, -1.0):
            x_h = sgn * t
            y_h = np.cross(z_h, x_h)
            local = np.concatenate(
                [
                    [standoff * rhat[0], standoff * rhat[1], float(zg)],
                    m.matrix_to_quat(np.stack([x_h, y_h, z_h], axis=1)),
                ]
            )
            out.append({"pose": m.pose_compose(bottle_pose, local), "band": float(zg), "sign": sgn})
    return out


def select_grasp(cands: List[Dict[str, Any]], ee_quat: np.ndarray, band: float, closing_sign) -> Dict[str, Any]:
    """Family member at ``band`` whose jaw sign needs the least wrist rotation (or the pinned sign)."""
    bands = sorted({c["band"] for c in cands}, key=lambda b: abs(b - float(band)))
    pool = [c for c in cands if c["band"] == bands[0]]
    if closing_sign not in (None, "auto"):
        pool = [c for c in pool if c["sign"] == float(closing_sign)] or pool
    return min(pool, key=lambda c: m.quat_diff_angle(ee_quat, c["pose"][3:7]))


# --------------------------------------------------------------------------- reorient phase
class ReorientPhase(PhaseBase):
    """Rotate the held object's +z axis to world up in planned hops about its own centre."""

    name = "reorient"

    def __init__(
        self, obj_key: str, step_deg: float, done_deg: float, hold_ticks: int, steps: int, gripper, max_hops: int = 12
    ):
        self.obj_key = obj_key
        self.step_deg = float(step_deg)
        self.done_deg = float(done_deg)
        self.hold_ticks = int(hold_ticks)
        self.steps = int(steps)
        self.gripper = np.asarray(gripper, dtype=np.int64)
        self.max_hops = int(max_hops)
        self._hop: Optional[MoveL] = None
        self._hops = 0
        self._holding = 0
        self.tilt_deg = float("nan")
        self._done_reason = None

    def _object(self, obs) -> np.ndarray:
        return np.asarray(obs["privileged"][self.obj_key], dtype=np.float64)

    def start(self, obs, info) -> None:
        self._hop = None
        self._hops = 0
        self._holding = 0
        self._plan(obs, info)

    def _plan(self, obs, info) -> None:
        obj = self._object(obs)
        eef = ee_pose(obs, 0)
        a_w = m.quat_rotate(obj[3:7], UP)
        self.tilt_deg = G.angle_between_deg(a_w, UP)
        if self.tilt_deg <= self.done_deg or self._hops >= self.max_hops:
            self._hop = None
            return
        if 0.0 < self.step_deg < self.tilt_deg:
            q_align = m.quat_from_axis_angle(np.cross(a_w, UP), np.radians(self.step_deg))
        else:
            q_align = G.quat_align(a_w, UP)
        obj_des = np.concatenate([obj[:3], m.quat_normalize(m.quat_mul(q_align, obj[3:7]))])
        eef_des = G.eef_from_object(obj_des, G.relative_pose(eef, obj))
        self._hop = MoveL(
            eef_des, "right", steps=self.steps, converge=False, gripper=self.gripper, name=f"reorient_hop{self._hops}"
        )
        self._hop.start(obs, info)
        self._hops += 1

    def step(self, obs, info) -> Action:
        if self._hop is not None:
            return self._hop.step(obs, info)
        self._holding += 1
        return Action(np.full(14, np.nan), self.gripper)

    def done(self, obs, info) -> bool:
        if self._hop is not None:
            if self._hop.done(obs, info):
                self._plan(obs, info)
            return False
        if self._holding >= self.hold_ticks:
            self._done_reason = f"upright (tilt {self.tilt_deg:.1f} deg after {self._hops} hops)"
            return True
        return False


# --------------------------------------------------------------------------- policy
class Policy(PhasedPolicy):
    """Fixed-pose lift expert (see the module docstring).

    Args:
        cfg: the task configuration (``policy`` block).
        task: the built task (kept for parity with the assembly policies; object poses
            are read from the privileged observation).
        planner: optional :class:`tactilelab_tasks.core.planner.Planner` for the free-space
            moves (``MoveL(mode="motiongen")``); straight-line interpolation otherwise.
    """

    def __init__(self, cfg: Dict[str, Any], task=None, verbose: bool = True, planner=None):
        super().__init__(phases=None, cfg=cfg, verbose=verbose)
        self.task = task
        self.planner = planner
        self.p = dict(self.cfg.get("policy") or {})
        self.obj_key = f"object_pose/{self.cfg['lift']['bottle']}"
        self.grasp_choice: Optional[Dict[str, Any]] = None

    # -- helpers
    def _free_move(self, target, name: str, gripper, speed: Optional[float] = None) -> MoveL:
        mv = self.p.get("move", {})
        return MoveL(
            target,
            "right",
            mode="motiongen" if self.planner is not None else "interp",
            steps=int(mv.get("interp_steps", 120)),
            speed=float(mv.get("speed", 0.0) if speed is None else speed),
            gripper=gripper,
            planner=self.planner,
            name=name,
        )

    def _converge_move(self, target, name: str, gripper) -> MoveL:
        mv = self.p.get("move", {})
        return MoveL(
            target,
            "right",
            steps=int(mv.get("descend_steps", 60)),
            converge=True,
            tol=(float(mv.get("translation_tol", 0.002)), float(mv.get("rotation_tol", 0.005))),
            timeout=int(mv.get("timeout", 120)),
            gripper=gripper,
            name=name,
        )

    def _gripper(self, command: str, name: str) -> Gripper:
        g = self.p.get("gripper", {})
        return Gripper(
            command,
            "right",
            timeout=int(g.get("timeout", 30)),
            settle_threshold=float(g.get("settle_threshold", 1e-3)),
            name=name,
        )

    # -- plan
    def build_phases(self, obs, info) -> List[PhaseBase]:
        gp = self.p.get("grasp", {})
        bottle = np.asarray(obs["privileged"][self.obj_key], dtype=np.float64)
        cands = roll_corrected_grasps(bottle, float(gp.get("standoff", 0.18)), gp.get("bands", (-0.045, 0.0, 0.045)))
        self.grasp_choice = select_grasp(
            cands, ee_pose(obs, 0)[3:7], float(gp.get("band", 0.0)), gp.get("closing_sign", "auto")
        )
        grasp = self.grasp_choice["pose"]
        if self.verbose:
            print(
                f"[lift] grasp band {self.grasp_choice['band']:+.3f} sign {self.grasp_choice['sign']:+.0f} at {np.round(grasp[:3], 3).tolist()}",
                flush=True,
            )
        pre_grasp = G.pose_backward_along_z(grasp, float(gp.get("pre_grasp_offset", 0.06)))
        retrieval = G.pose_up(grasp, float(gp.get("retrieval_offset", 0.3)))
        open_, closed = (GRIPPER_OPEN, GRIPPER_OPEN), (GRIPPER_CLOSE, GRIPPER_OPEN)
        ro = self.p.get("reorient", {})
        pl = self.p.get("place", {})
        mv = self.p.get("move", {})

        target_pos = place_target_position(self.cfg)
        contact = bottom_center(self.cfg)
        clearance = float(self.cfg["lift"].get("release_clearance", 0.005))
        seat_z = target_pos[2] + float(contact[2])  # height of the contact point at release (pad top + clearance)
        state: Dict[str, np.ndarray] = {}

        def pre_place_target(obs_, info_):
            obj = np.asarray(obs_["privileged"][self.obj_key], dtype=np.float64)
            eef = ee_pose(obs_, 0)
            q_t = m.quat_normalize(m.quat_mul(G.quat_align(m.quat_rotate(obj[3:7], UP), UP), obj[3:7]))
            pos_t = np.array([target_pos[0], target_pos[1], seat_z]) - m.quat_rotate(q_t, contact)
            obj_target = np.concatenate([pos_t, q_t])
            state["eef_place"] = m.pose_compose(obj_target, m.pose_relative(obj, eef))  # grip transform captured here
            return G.pose_up(state["eef_place"], float(pl.get("pre_place_offset", 0.12)))

        phases: List[PhaseBase] = [
            Hold(int(self.p.get("init_hold", 30)), gripper=open_, name="init"),
            self._free_move(pre_grasp, "pre_grasp", open_),
            self._converge_move(grasp, "grasp", open_),
            self._gripper("close", "close"),
            self._free_move(retrieval, "retrieve", closed, speed=float(mv.get("speed", 0.1))),
            Hold(int(gp.get("settle_ticks", 30)), gripper=closed, name="grasp_settle"),
            ReorientPhase(
                self.obj_key,
                ro.get("step_deg", 30.0),
                ro.get("done_deg", 5.0),
                ro.get("hold_ticks", 20),
                int(mv.get("interp_steps", 120)),
                closed,
                int(ro.get("max_hops", 12)),
            ),
            self._free_move(pre_place_target, "pre_place", closed, speed=float(mv.get("speed", 0.1))),
            self._converge_move(lambda o, i: state["eef_place"], "place", closed),
            self._gripper("open", "open"),
            Hold(int(pl.get("settle", 15)), gripper=open_, name="settle"),
        ]
        retreat = float(pl.get("retreat_offset", 0.0))
        if retreat > 0.0:
            phases.append(self._free_move(lambda o, i: G.pose_up(ee_pose(o, 0), retreat), "retreat", open_))
        del clearance
        return phases
