"""Weld a threaded fastener to its host once it has physically seated, and remove all its contacts (user decisions 2026-10-15).

One shared implementation for all IKEA scenes. Purpose: speed. Once seated, a fastener is part of its host, so it
needs no contacts at all ("after weld, there shouldn't be any contact on that screw").

A scene declares, per threaded fastener (wherever geom names are asked for, a body name means all geoms of that body):
  - `body`: the fastener; `host`: the body its thread is in;
  - `thread_holes`: the host's internal-thread geoms of that hole (they stop colliding too);
  - `head_geoms`: the head/flange/collar geoms, used only to detect seating;
  - `thread_geoms` (optional): for a load-bearing threaded part (a leg, a screw-in foot) whose other geoms must keep
    colliding, list only its thread geoms (may sit on child bodies); those go off. Omitted (small screws, bolts):
    every geom of the fastener body goes off, head included;
  - `clamped`: the bodies the head clamps against the host (e.g. a leg plate). Since the head stops colliding, each
    clamped body is welded to the host at the same moment, at its current pose, so the joint stays closed.
and authors the inactive welds that `weld_xml()` writes (MuJoCo cannot add an equality at run time).

Arming: a fastener lying head-down on the table looks "seated", so create it with `armed=False` and call
`welder.arm(name)` when its drive starts (it is in its hole); only armed fasteners are checked. Default: armed.

Seated = a head geom touches something, the fastener's velocity relative to its host is below `v_eps` (m/s) and
`w_eps` (rad/s), and this has held for `hold_s` of simulated time. Then each weld is set to the current relative pose
(no snap) and activated, and every geom of the fastener plus its hole's thread geoms lose contype/conaffinity.

Welds and contact changes live in model fields, not in mjSTATE_INTEGRATION, so each event is recorded in
`welder.events`; save them with the trajectory and call `SeatWelder.apply_event` at the same sim time on replay.
Every weld of a fastener (its own and its clamped parts') pins the same point, the fastener's origin, i.e. the joint
(anchor = that point in the host frame, relpose position = that point in body1's frame), with the current relative
orientation. Body origins far from the joint cannot then turn small rotational give into drift (fixed 09:27 for the
host after UPPSTÅ's 2.9 mm off-axis, 10:05 for clamped parts after SKÅDIS's 0.25 mm spring-back).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import mujoco
import numpy as np

# RoboARC's weld class (profiles.py _RIGID["weld"])
WELD_SOLREF = ".00125 1"
WELD_SOLIMP = ".9 .95 .001 .5 2"


def _weld(name, b1, b2):
    return (f'<weld name="{name}" body1="{b1}" body2="{b2}" active="false" '
            f'solref="{WELD_SOLREF}" solimp="{WELD_SOLIMP}"/>')


def weld_xml(name: str, fastener_body: str, host_body: str, clamped: list[str] = ()) -> str:
    """The inactive welds a scene must author for one fastener (put inside <equality>)."""
    return "".join([_weld(f"seat__{name}", fastener_body, host_body)] +
                   [_weld(f"seat__{name}__{c}", c, host_body) for c in clamped])


@dataclass
class Fastener:
    name: str
    body: str
    host: str
    thread_holes: list[str]
    head_geoms: list[str]
    clamped: list[str] = field(default_factory=list)
    thread_geoms: list[str] | None = None
    armed: bool = True
    bid: int = -1
    hid: int = -1
    welds: list[tuple[int, int]] = field(default_factory=list)   # (equality id, body1 id)
    off_geoms: list[int] = field(default_factory=list)
    head_ids: list[int] = field(default_factory=list)
    quiet_since: float | None = None
    welded: bool = False


def _rel_pose(d, b1, b2):
    """Pose of body2 in body1's frame (MuJoCo weld relpose), position and wxyz quaternion."""
    q1inv = np.zeros(4); mujoco.mju_negQuat(q1inv, d.xquat[b1])
    pos = np.zeros(3); mujoco.mju_rotVecQuat(pos, d.xpos[b2] - d.xpos[b1], q1inv)
    quat = np.zeros(4); mujoco.mju_mulQuat(quat, q1inv, d.xquat[b2])
    return pos, quat


def _rel_vel(m, d, b1, b2):
    """Linear (at body1's origin) and angular speed of body1 relative to body2."""
    v1 = np.zeros(6); v2 = np.zeros(6)
    mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b1, v1, 0)
    mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b2, v2, 0)
    v2_at_b1 = v2[3:] + np.cross(v2[:3], d.xpos[b1] - d.xpos[b2])
    return float(np.linalg.norm(v1[3:] - v2_at_b1)), float(np.linalg.norm(v1[:3] - v2[:3]))


def _geoms(m, names):
    """Geom ids for a list of names; a body name stands for all geoms of that body. Unknown names -> ValueError."""
    out, bad = [], []
    for n in names:
        g = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, n)
        if g >= 0:
            out.append(g); continue
        b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n)
        if b >= 0:
            out += [i for i in range(m.ngeom) if m.geom_bodyid[i] == b]; continue
        bad.append(n)
    if bad:
        raise ValueError(f"seat_weld: no geom or body named {bad}")
    return out


class SeatWelder:
    def __init__(self, m, d, fasteners, hold_s=0.05, v_eps=1e-4, w_eps=0.05):
        self.m, self.d, self.f = m, d, list(fasteners)
        self.hold_s, self.v_eps, self.w_eps = hold_s, v_eps, w_eps
        self.events: list[dict] = []
        name2id = lambda kind, n: mujoco.mj_name2id(m, kind, n)
        G, B, E = mujoco.mjtObj.mjOBJ_GEOM, mujoco.mjtObj.mjOBJ_BODY, mujoco.mjtObj.mjOBJ_EQUALITY
        for f in self.f:
            f.bid, f.hid = name2id(B, f.body), name2id(B, f.host)
            weld_names = [(f"seat__{f.name}", f.body)] + [(f"seat__{f.name}__{c}", c) for c in f.clamped]
            f.welds = [(name2id(E, w), name2id(B, b1)) for w, b1 in weld_names]
            own = (_geoms(m, f.thread_geoms) if f.thread_geoms is not None
                   else [g for g in range(m.ngeom) if m.geom_bodyid[g] == f.bid])
            f.off_geoms = own + _geoms(m, f.thread_holes)
            f.head_ids = _geoms(m, f.head_geoms)
            bad = ([w for (e, _), (w, _) in zip(f.welds, weld_names) if e < 0] +
                   [n for n in [f.body, f.host] + f.clamped if name2id(B, n) < 0])
            if bad:
                raise ValueError(f"seat_weld: fastener {f.name}: not in the model: {bad}")

    def arm(self, name):
        """Start checking this fastener for seating (call when its drive starts)."""
        next(x for x in self.f if x.name == name).armed = True

    def _head_in_contact(self, f):
        c = self.d.contact[: self.d.ncon]
        return bool(np.isin(c.geom1, f.head_ids).any() or np.isin(c.geom2, f.head_ids).any())

    def step(self):
        """Call after every mj_step. Returns the weld events made this step."""
        new, t = [], float(self.d.time)
        for f in self.f:
            if f.welded or not f.armed:
                continue
            v, w = _rel_vel(self.m, self.d, f.bid, f.hid)
            if v < self.v_eps and w < self.w_eps and self._head_in_contact(f):
                f.quiet_since = t if f.quiet_since is None else f.quiet_since
                if t - f.quiet_since >= self.hold_s:
                    ev = {"time": t, "fastener": f.name, "host": f.host, "clamped": list(f.clamped)}
                    self.apply_event(self.m, self.d, ev, self.f)
                    self.events.append(ev); new.append(ev)
            else:
                f.quiet_since = None
        return new

    @staticmethod
    def apply_event(m, d, ev, fasteners):
        """Weld the fastener (and its clamped parts) to the host at the current pose and drop all the fastener's
        contacts and its hole's thread contacts. Used live and on replay."""
        f = next(x for x in fasteners if x.name == ev["fastener"])
        for eq, b1 in f.welds:
            pos, quat = _rel_pose(d, b1, f.hid)
            # The weld pins one point: anchor (in body2 = host frame) to relpose pos (in body1 frame). Every weld of a
            # fastener (its own and its clamped parts') pins the fastener's origin, i.e. the joint itself; a body
            # origin far from the joint (a board centre 120-240 mm off) would let small rotational give show as drift.
            anchor, _ = _rel_pose(d, f.hid, f.bid)
            relpos, _ = _rel_pose(d, b1, f.bid)
            m.eq_data[eq, :3] = anchor
            m.eq_data[eq, 3:6] = relpos
            m.eq_data[eq, 6:10] = quat
            m.eq_data[eq, 10] = 1.0
            d.eq_active[eq] = 1
        for g in f.off_geoms:
            m.geom_contype[g] = 0
            m.geom_conaffinity[g] = 0
        f.welded = True
