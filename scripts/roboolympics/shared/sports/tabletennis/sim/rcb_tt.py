"""
rcb_tt.py — task-local tooling for the robot table tennis tasks (MuJoCo, Franka Panda with a paddle).

World frame (metres): table top is z = 0, the table's long axis is y, the net is the plane y = 0.
The robot stands behind the y < 0 end (base at (0, -1.75, 0), facing +y); the opponent half is y > 0.

Control: one action = 7 absolute joint-position targets (rad), held for CONTROL_DT = 10 ms (100 Hz). Inside a
control step the target is interpolated linearly over the 10 physics steps (1 ms each), and a joint-space
PD controller with bias (gravity + Coriolis) compensation turns it into joint torques, clipped at the Franka
torque limits (87 Nm joints 1-4, 12 Nm joints 5-7). The target velocity fed to the D term is the target's
finite difference. Target limits (checked, a violation raises ValueError / fails the verifier):
  * every target inside the joint range (JOINT_LOW..JOINT_HIGH),
  * |target_k - target_{k-1}| <= VEL_LIMIT * CONTROL_DT per joint (Franka joint speed limits);
    target_{-1} is the instance's initial joint configuration q0.
An episode lasts HORIZON_S = 2.5 s (250 control steps). A trajectory with fewer than 250 rows holds its last
target for the rest of the episode.

Python
------
  from rcb_tt import Session
  s = Session()                        # loads /app/instance.npz (or Session(instance=...))
  s.reset(); s.step(q_target); s.state(); s.status(); s.actions()
  s.predict_ball(duration=1.5)         # ball-only rollout (no robot) from the current (or a given) ball state
  s.fk(q) / s.jacobian(q) / s.ik(pos, normal, q_init)   # paddle kinematics helpers
  s.replay(actions) -> status; s.save_trajectory(actions, path)

CLI
---
  python rcb_tt.py info
  python rcb_tt.py replay --traj /app/output/trajectory.npz [--repeat 2]
  python rcb_tt.py render --traj /app/output/trajectory.npz --out replay.mp4
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

import mujoco as mj  # rendering backend: MUJOCO_GL (the image sets osmesa = CPU offscreen)

HERE = Path(__file__).resolve().parent
SCENE_XML = Path(os.environ.get("RCB_TT_SCENE", HERE / "scene" / "tt_scene.xml"))
DEFAULT_INSTANCE = os.environ.get("RCB_TT_INSTANCE", "/app/instance.npz")

CONTROL_DT = 0.01
SUBSTEPS = 10                      # physics steps per control step (timestep 1 ms)
HORIZON_S = 2.5
HORIZON = int(round(HORIZON_S / CONTROL_DT))   # 250 control steps
VEL_LIMIT = np.array([2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61])       # rad/s (Franka datasheet)
TORQUE_LIMIT = np.array([87.0, 87.0, 87.0, 87.0, 12.0, 12.0, 12.0])        # Nm
KP = np.array([2400.0, 2400.0, 2400.0, 2400.0, 1000.0, 600.0, 200.0])
KD = np.array([100.0, 100.0, 100.0, 100.0, 30.0, 20.0, 6.0])
MERGE_GAP_S = 0.005                # contacts with the same object closer than this in time count as one
NET_TOP_Z = 0.1525
TABLE_HALF_X, TABLE_HALF_Y = 0.7625, 1.37

JOINTS = [f"joint{i}" for i in range(1, 8)]


def _robot_geom_ids(m: mj.MjModel) -> set[int]:
    root = mj.mj_name2id(m, mj.mjtObj.mjOBJ_BODY, "link0")
    ids = set()
    for g in range(m.ngeom):
        b = m.geom_bodyid[g]
        while b not in (0, root):
            b = m.body_parentid[b]
        if b == root:
            ids.add(g)
    return ids


def _ball_only_xml(path: Path) -> str:
    """The same scene with the robot removed: used by predict_ball (identical ball/table/net physics)."""
    tree = ET.parse(path)
    root = tree.getroot()
    wb = root.find("worldbody")
    for b in list(wb):
        if b.tag == "body" and b.get("name") == "link0":
            wb.remove(b)
    for tag in ("actuator",):
        for el in root.findall(tag):
            root.remove(el)
    con = root.find("contact")
    for el in list(con):
        if el.tag == "exclude" or (el.tag == "pair" and el.get("geom2") == "paddle_blade"):
            con.remove(el)
    root.find("compiler").set("meshdir", str((path.parent / "assets").resolve()))
    return ET.tostring(root, encoding="unicode")


def load_instance(path: str | Path) -> dict:
    d = np.load(path, allow_pickle=False)
    return {k: d[k].copy() for k in d.files}


class Session:
    """One simulator (MuJoCo, single thread) for the frozen instance. Unlimited resets."""

    def __init__(self, instance: str | Path | None = None, scene: str | Path | None = None):
        self.instance_path = str(instance or DEFAULT_INSTANCE)
        self.inst = load_instance(self.instance_path)
        self.scene = Path(scene) if scene else SCENE_XML
        self.m = mj.MjModel.from_xml_path(str(self.scene))
        self.d = mj.MjData(self.m)
        m = self.m
        self._qadr = np.array([m.jnt_qposadr[mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j)] for j in JOINTS])
        self._vadr = np.array([m.jnt_dofadr[mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j)] for j in JOINTS])
        self.JOINT_LOW = m.jnt_range[[mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j) for j in JOINTS], 0].copy()
        self.JOINT_HIGH = m.jnt_range[[mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j) for j in JOINTS], 1].copy()
        self._ball_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "geom_ball")
        self._table_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "geom_table")
        self._net_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "geom_net")
        self._floor_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "floor")
        self._blade_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "paddle_blade")
        self._robot_geoms = _robot_geom_ids(m)
        self._paddle_site = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "paddle_center")
        tz = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "target_zone")
        m.site_pos[tz, :2] = self.inst["target_center"]
        m.site_size[tz, :2] = self.inst["target_half"]
        m.site_rgba[tz, 3] = 0.0  # target-zone visualization is not part of the match
        self._kin = mj.MjData(m)          # scratch data for fk / jacobian / ik (never stepped)
        self._ball_model = None
        self.sim_steps_total = 0
        self.resets = 0
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self) -> dict:
        """Back to the frozen initial state (ball in flight, arm at rest at q0, t = 0)."""
        m, d = self.m, self.d
        mj.mj_resetData(m, d)
        d.qpos[0:7] = self.inst["ball_qpos"]
        d.qvel[0:6] = self.inst["ball_qvel"]
        d.qpos[self._qadr] = self.inst["q0"]
        d.ctrl[:] = 0.0
        mj.mj_forward(m, d)
        self._target = self.inst["q0"].astype(np.float64).copy()
        self._actions: list[np.ndarray] = []
        self._k = 0
        self._events: list[dict] = []         # contact onsets involving the ball (merged, see MERGE_GAP_S)
        self._last_touch: dict[str, float] = {}
        self._robot_table = 0
        self._robot_contact_names: set[str] = set()
        self._v_out = None                    # ball velocity 5 ms after the first paddle contact
        self.resets += 1
        return self.state()

    def _check_target(self, q: np.ndarray) -> None:
        if q.shape != (7,) or not np.all(np.isfinite(q)):
            raise ValueError(f"action must be 7 finite joint targets, got shape {q.shape}")
        lo_bad = q < self.JOINT_LOW - 1e-9
        hi_bad = q > self.JOINT_HIGH + 1e-9
        if lo_bad.any() or hi_bad.any():
            raise ValueError(f"step {self._k}: joint target outside range {np.nonzero(lo_bad | hi_bad)[0].tolist()}: {q}")
        dq = np.abs(q - self._target)
        lim = VEL_LIMIT * CONTROL_DT * (1 + 1e-6) + 1e-12
        if (dq > lim).any():
            j = int(np.argmax(dq / lim))
            raise ValueError(f"step {self._k}: joint {j + 1} target moved {dq[j]:.5f} rad in one control step "
                             f"(limit {VEL_LIMIT[j] * CONTROL_DT:.5f} = {VEL_LIMIT[j]} rad/s x {CONTROL_DT} s)")

    def step(self, q_target) -> dict:
        """Apply one action (7 joint targets) for CONTROL_DT = 10 ms. Returns state()."""
        if self._k >= HORIZON:
            raise RuntimeError(f"episode is over ({HORIZON} control steps = {HORIZON_S} s); call reset()")
        q = np.asarray(q_target, dtype=np.float64).reshape(-1)
        self._check_target(q)
        m, d = self.m, self.d
        q_prev = self._target
        qd_des = (q - q_prev) / CONTROL_DT
        lo, hi = m.actuator_ctrlrange[:, 0], m.actuator_ctrlrange[:, 1]
        for j in range(1, SUBSTEPS + 1):
            q_des = q_prev + (q - q_prev) * (j / SUBSTEPS)
            tau = KP * (q_des - d.qpos[self._qadr]) + KD * (qd_des - d.qvel[self._vadr]) + d.qfrc_bias[self._vadr]
            d.ctrl[:] = np.clip(tau, lo, hi)
            self._v_pre = d.qvel[0:3].copy()     # the ball's velocity before this substep (pre-contact)
            mj.mj_step(m, d)
            self._scan_contacts()
            if self._v_out is None and self._events and any(e["kind"] == "paddle" for e in self._events):
                t_hit = next(e["t"] for e in self._events if e["kind"] == "paddle")
                if d.time >= t_hit + 0.005 - 1e-9:
                    self._v_out = d.qvel[0:3].copy()
        self._target = q.copy()
        self._actions.append(q.copy())
        self._k += 1
        self.sim_steps_total += SUBSTEPS
        return self.state()

    def _scan_contacts(self) -> None:
        d, t = self.d, self.d.time
        bg = self._ball_geom
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            if bg in (g1, g2):
                other = g2 if g1 == bg else g1
                if other == self._table_geom:
                    kind = "table_own" if d.qpos[1] < 0 else "table_opp"
                elif other == self._blade_geom:
                    kind = "paddle"
                elif other == self._net_geom:
                    kind = "net"
                elif other == self._floor_geom:
                    kind = "floor"
                elif other in self._robot_geoms:
                    kind = "robot"
                else:
                    kind = "other"
                last = self._last_touch.get(kind)
                if last is None or t - last > MERGE_GAP_S + 1e-9:
                    # MuJoCo's frame points geom1 -> geom2. Store a stable
                    # surface -> ball convention, independent of geom ordering.
                    normal = c.frame[:3] if g2 == bg else -c.frame[:3]
                    self._events.append(dict(t=round(float(t), 6), kind=kind, pos=d.qpos[0:3].tolist(),
                                             vel=d.qvel[0:3].tolist(), vel_pre=self._v_pre.tolist(),
                                             contact_pos=c.pos.tolist(),
                                             contact_normal=normal.tolist()))
                self._last_touch[kind] = t
            else:
                rob1, rob2 = g1 in self._robot_geoms, g2 in self._robot_geoms
                if rob1 != rob2:   # robot touches the environment (table, net, floor)
                    self._robot_table = 1
                    self._robot_contact_names.add(mj.mj_id2name(self.m, mj.mjtObj.mjOBJ_GEOM, g2 if rob1 else g1) or "?")

    def run_to_end(self) -> dict:
        """Hold the last target until the episode horizon (what the verifier does after the last action)."""
        while self._k < HORIZON:
            self.step(self._target)
        return self.status()

    # ------------------------------------------------------------------ observation
    def state(self) -> dict:
        d = self.d
        R = d.site_xmat[self._paddle_site].reshape(3, 3)
        jacp = np.zeros((3, self.m.nv)); jacr = np.zeros((3, self.m.nv))
        mj.mj_jacSite(self.m, d, jacp, jacr, self._paddle_site)
        qd = d.qvel[self._vadr]
        return dict(
            t=float(d.time), k=self._k,
            q=d.qpos[self._qadr].copy(), qd=qd.copy(), q_target=self._target.copy(),
            ball_pos=d.qpos[0:3].copy(), ball_vel=d.qvel[0:3].copy(), ball_spin=d.qvel[3:6].copy(),
            paddle_pos=d.site_xpos[self._paddle_site].copy(), paddle_R=R.copy(), paddle_normal=R[:, 0].copy(),
            paddle_vel=jacp[:, self._vadr] @ qd, paddle_angvel=jacr[:, self._vadr] @ qd,
            events=copy.deepcopy(self._events),
        )

    def actions(self) -> np.ndarray:
        """(N, 7) joint targets applied since the last reset."""
        return np.array(self._actions, dtype=np.float64).reshape(-1, 7)

    def status(self) -> dict:
        """Judge the episode so far (final only once the ball has landed or the horizon is reached)."""
        st = judge(self._events, self.inst, robot_env_contact=self._robot_table, t=float(self.d.time), k=self._k)
        if self._v_out is not None:
            st["hit_speed_out"] = float(np.linalg.norm(self._v_out))
        return st

    def state_sha(self) -> str:
        d = self.d
        h = hashlib.sha256()
        for a in (d.qpos, d.qvel, d.act, d.qacc_warmstart, d.ctrl, np.array([d.time])):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        h.update(json.dumps(self._events, sort_keys=True).encode())
        return h.hexdigest()

    # ------------------------------------------------------------------ replay / io
    def replay(self, actions) -> dict:
        """Reset, apply `actions` open-loop, hold the last target to the 2.5 s horizon, return status()."""
        a = np.asarray(actions, dtype=np.float64)
        if a.ndim != 2 or a.shape[1] != 7 or not (1 <= len(a) <= HORIZON):
            raise ValueError(f"actions must have shape (N, 7) with 1 <= N <= {HORIZON}, got {a.shape}")
        self.reset()
        for q in a:
            self.step(q)
        st = self.run_to_end()
        st["n_actions"] = int(len(a))
        st["state_sha"] = self.state_sha()
        return st

    @staticmethod
    def save_trajectory(actions, path: str = "/app/output/trajectory.npz") -> str:
        a = np.asarray(actions, dtype=np.float64)
        if a.ndim != 2 or a.shape[1] != 7:
            raise ValueError(f"actions must be (N, 7), got {a.shape}")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez(path, actions=a, control_dt=np.float64(CONTROL_DT), task=np.str_("tabletennis_return"))
        return path

    # ------------------------------------------------------------------ helpers (privileged, allowed)
    def predict_ball(self, pos=None, vel=None, spin=None, duration: float = 1.5) -> dict:
        """Roll the ball out WITHOUT the robot (same ball/table/net physics, 1 ms steps) from the current ball
        state or from (pos, vel, spin). Returns t (N,), pos (N,3), vel (N,3), spin (N,3) and the table/net
        contact onsets. Times are relative to the current sim time. Matches the full sim until the ball
        touches the robot (up to floating-point differences)."""
        if self._ball_model is None:
            self._ball_model = mj.MjModel.from_xml_string(_ball_only_xml(self.scene))
            self._ball_data = mj.MjData(self._ball_model)
        bm, bd = self._ball_model, self._ball_data
        mj.mj_resetData(bm, bd)
        bd.qpos[0:7] = self.d.qpos[0:7]
        bd.qvel[0:6] = self.d.qvel[0:6]
        if pos is not None:
            bd.qpos[0:3] = pos
        if vel is not None:
            bd.qvel[0:3] = vel
        if spin is not None:
            bd.qvel[3:6] = spin
        mj.mj_forward(bm, bd)
        n = int(round(duration / bm.opt.timestep))
        P = np.zeros((n, 3)); V = np.zeros((n, 3)); W = np.zeros((n, 3)); T = np.zeros(n)
        tg = mj.mj_name2id(bm, mj.mjtObj.mjOBJ_GEOM, "geom_table")
        ng = mj.mj_name2id(bm, mj.mjtObj.mjOBJ_GEOM, "geom_net")
        fg = mj.mj_name2id(bm, mj.mjtObj.mjOBJ_GEOM, "floor")
        events, prev = [], set()
        for i in range(n):
            mj.mj_step(bm, bd)
            T[i] = (i + 1) * bm.opt.timestep
            P[i], V[i], W[i] = bd.qpos[0:3], bd.qvel[0:3], bd.qvel[3:6]
            cur = set()
            for c in range(bd.ncon):
                g = {int(bd.contact[c].geom1), int(bd.contact[c].geom2)}
                if tg in g:
                    cur.add("table_own" if bd.qpos[1] < 0 else "table_opp")
                if ng in g:
                    cur.add("net")
                if fg in g:
                    cur.add("floor")
            for kind in cur - prev:
                events.append(dict(t=float(T[i]), kind=kind, pos=P[i].tolist()))
            prev = cur
        return dict(t=T, pos=P, vel=V, spin=W, events=events)

    def _kin_set(self, q):
        self._kin.qpos[:] = self.d.qpos
        self._kin.qpos[self._qadr] = q
        mj.mj_kinematics(self.m, self._kin)
        mj.mj_comPos(self.m, self._kin)

    def fk(self, q) -> tuple[np.ndarray, np.ndarray]:
        """Paddle blade centre position (3,) and rotation matrix (3,3) for joint config q. Column 0 of the
        rotation is the blade face normal, column 2 points along the handle (away from the wrist)."""
        self._kin_set(np.asarray(q, dtype=np.float64))
        return (self._kin.site_xpos[self._paddle_site].copy(),
                self._kin.site_xmat[self._paddle_site].reshape(3, 3).copy())

    def jacobian(self, q) -> np.ndarray:
        """(6, 7) paddle-centre Jacobian [linear; angular] (world frame) at joint config q."""
        self._kin_set(np.asarray(q, dtype=np.float64))
        jacp = np.zeros((3, self.m.nv)); jacr = np.zeros((3, self.m.nv))
        mj.mj_jacSite(self.m, self._kin, jacp, jacr, self._paddle_site)
        return np.vstack([jacp[:, self._vadr], jacr[:, self._vadr]])

    def ik(self, pos, normal, q_init=None, iters: int = 200, tol: float = 1e-4) -> tuple[np.ndarray, float]:
        """Damped-least-squares IK for the paddle: blade centre at `pos` with face normal along `normal`
        (rotation about the normal is free). Joint limits are respected by clipping. Returns (q, residual)
        where residual = position error (m) + normal error (rad); check it."""
        q = np.array(self.inst["q0"] if q_init is None else q_init, dtype=np.float64)
        pos = np.asarray(pos, dtype=np.float64)
        n_t = np.asarray(normal, dtype=np.float64); n_t = n_t / np.linalg.norm(n_t)
        err = np.inf
        for _ in range(iters):
            p, R = self.fk(q)
            n = R[:, 0]
            e = np.r_[pos - p, np.cross(n, n_t)]
            err = float(np.linalg.norm(e[:3]) + np.arcsin(min(1.0, np.linalg.norm(e[3:]))))
            if n @ n_t < 0:
                e[3:] = np.cross(n, n_t) + 0.5 * np.cross(n, R[:, 1])  # flip out of the antipodal solution
                err += np.pi / 2
            if err < tol:
                break
            J = self.jacobian(q)
            lam = 1e-3
            dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(6), e)
            q = np.clip(q + dq, self.JOINT_LOW + 1e-4, self.JOINT_HIGH - 1e-4)
        return q, err

    # ------------------------------------------------------------------ rendering
    def render_video(self, actions, out: str, fps: int = 25, every: int = 1, width: int = 640, height: int = 360,
                     slowmo_label: bool = True) -> str:
        """Replay `actions` and write an mp4 (two views side by side). One frame per `every` control steps
        (10 ms): fps=25, every=1 is 4x slow motion."""
        import imageio.v2 as imageio
        a = np.asarray(actions, dtype=np.float64)
        r = mj.Renderer(self.m, height=height, width=width)
        cams = []
        for lookat, dist, az, el in (([0.0, -0.2, 0.1], 3.6, 0.0, -18.0), ([0.0, 0.0, 0.1], 4.2, -90.0, -22.0)):
            c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
            cams.append(c)
        opt = mj.MjvOption()
        writer = imageio.get_writer(out, fps=fps, macro_block_size=8)

        def frame():
            imgs = []
            for c in cams:
                r.update_scene(self.d, camera=c, scene_option=opt)
                imgs.append(r.render())
            writer.append_data(np.concatenate(imgs, axis=1))

        self.reset(); frame()
        for k in range(HORIZON):
            self.step(a[k] if k < len(a) else self._target)
            if (k + 1) % every == 0:
                frame()
        writer.close(); r.close()
        return out


# ---------------------------------------------------------------------- judging
def judge(events: list[dict], inst: dict, robot_env_contact: int = 0, t: float = 0.0, k: int = 0) -> dict:
    """Success iff: the ball bounces exactly once on the robot's half and touches nothing else before the hit;
    exactly one paddle contact; after the hit the ball's first contact other than the net is the table on the
    opponent half inside the target zone; the robot never touches the table, net or floor.
    The net is transparent to the judgement (ITTF 2.7.1: a return is good if it touches the opponent's court
    "directly or after touching the net assembly"); `net_touch` reports it. A serve that touches the net is a let:
    the caller decides that before calling judge."""
    center = np.asarray(inst["target_center"], dtype=np.float64)
    half = np.asarray(inst["target_half"], dtype=np.float64)
    def top_contact(e):
        cp, cn = e.get("contact_pos"), e.get("contact_normal")
        # Top edges have an upward component; vertical sides and the underside
        # do not. Contact midpoints may lie well below z=0 at higher impact
        # speeds, so height cannot distinguish top contact from side contact.
        return bool(cp is not None and cn is not None and cn[2] > 1e-6 and
                    abs(cp[0]) <= .7625 + .001 and abs(cp[1]) <= 1.37 + .001)
    kinds = [e["kind"] for e in events]
    out = dict(success=False, hit=0, n_paddle_contacts=kinds.count("paddle"), own_bounces_before_hit=0,
               bad_contact_before_hit=0, landed=0, landed_opponent_half=0, in_zone=0, landing_error_m=-1.0,
               landing_x=0.0, landing_y=0.0, net_touch=int("net" in kinds), robot_env_contact=int(robot_env_contact),
               hit_time=-1.0, hit_speed_out=0.0, t=t, k=k)
    if "paddle" not in kinds:
        return out
    ip = kinds.index("paddle")
    out["hit"] = 1
    out["hit_time"] = float(events[ip]["t"])
    pre = kinds[:ip]
    edge_rules = bool(inst.get("table_edges_valid"))
    out["own_bounces_before_hit"] = sum(e["kind"] == "table_own" and (not edge_rules or top_contact(e))
                                           for e in events[:ip])
    out["bad_contact_before_hit"] = int(any(x in ("robot", "floor", "other") for x in pre) or
        (edge_rules and any(e["kind"] in ("table_own", "table_opp") and not top_contact(e)
                            for e in events[:ip])))
    post = [e for e in events[ip + 1:] if e["kind"] not in ("paddle", "net")]
    if post:
        e = post[0]
        out["landed"] = 1
        out["landing_x"], out["landing_y"] = float(e["pos"][0]), float(e["pos"][1])
        if e["kind"] == "table_opp":
            out["landed_opponent_half"] = 1
            err = np.abs(np.array(e["pos"][:2]) - center)
            if edge_rules:
                cp = e.get("contact_pos")
                out["in_zone"] = int(top_contact(e) and cp[1] >= 0)
            else:
                out["in_zone"] = int(bool(np.all(err <= half)))
            out["landing_error_m"] = float(np.linalg.norm(np.array(e["pos"][:2]) - center))
    out["success"] = bool(out["n_paddle_contacts"] == 1 and out["own_bounces_before_hit"] == 1
                          and not out["bad_contact_before_hit"] and out["landed_opponent_half"] == 1
                          and out["in_zone"] == 1 and not out["robot_env_contact"])
    return out


# ---------------------------------------------------------------------- CLI
def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("--instance", default=DEFAULT_INSTANCE)
    p = sub.add_parser("replay"); p.add_argument("--instance", default=DEFAULT_INSTANCE)
    p.add_argument("--traj", required=True); p.add_argument("--repeat", type=int, default=1)
    p = sub.add_parser("render"); p.add_argument("--instance", default=DEFAULT_INSTANCE)
    p.add_argument("--traj", required=True); p.add_argument("--out", default="replay.mp4")
    a = ap.parse_args(argv)
    s = Session(instance=a.instance)
    if a.cmd == "info":
        inst = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in s.inst.items()}
        print(json.dumps(dict(instance=inst, horizon_s=HORIZON_S, control_dt=CONTROL_DT,
                              joint_low=s.JOINT_LOW.tolist(), joint_high=s.JOINT_HIGH.tolist(),
                              vel_limit=VEL_LIMIT.tolist()), indent=1))
        return 0
    acts = np.load(a.traj, allow_pickle=False)["actions"]
    if a.cmd == "replay":
        for _ in range(a.repeat):
            st = s.replay(acts)
            print(json.dumps({k: v for k, v in st.items()}, default=float))
        return 0
    if a.cmd == "render":
        print(s.render_video(acts, a.out))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(_main())
