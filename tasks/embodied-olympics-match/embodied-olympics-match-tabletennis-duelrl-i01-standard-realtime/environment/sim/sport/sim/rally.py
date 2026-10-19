"""Shared pieces of the table-tennis simulator: the ball-only forward model, the swing helpers and the planning base
class of the stroke controller (match.Match, duel.Planner).

Until revision wallclock-6 this module also held the Season-1 rally episode (recorded serves, decision points); the
match and the duel never used it and it was removed with the mobile base (revision wallclock-7). What is left:
  BallModel        a ball-only copy of the scene (same ball / table / net physics), MuJoCo's native rollout
  hermite          cubic Hermite interpolation (joint-space swings)
  world_spin       the ball's angular velocity in the world frame
  Rally            the stroke controller's helpers on a single-robot simulator (rcb_tt.Session): robot-only twin
                   rehearsals of 9-joint target sequences (the base moving with the arm), the swing builder (an arm
                   swing over a base trajectory), the arm IK at a given base position, the rest motion
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

import mujoco as mj
import rcb_tt
from rcb_tt import ARM_VEL, BASE_VMAX, CONTROL_DT, HOME, VEL_LIMIT

HERE = Path(__file__).resolve().parent
for _root in (HERE.parent.parent, HERE.parent.parent.parent):   # sim/ in a task (bodies/ next to sport/); the repo
    if (_root / "bodies" / "trajopt.py").is_file():
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        break
from bodies import limits as AL  # noqa: E402
from bodies import trajopt  # noqa: E402

ARM_LIM = AL.load("franka_panda")       # the real Panda's limits: what the stroke planner plans within
ARM_LIM = __import__("dataclasses").replace(ARM_LIM, vel=ARM_LIM.vel * rcb_tt.VMARGIN)   # at the setpoint generator's
                                        # share of the velocity limits (rcb_tt.VMARGIN, revision 15/12)
PLANNER = os.environ.get("RCB_TT_PLANNER", "limits")   # "hermite": the velocity-limited cubic swing (until tt-planner)
SCENE = HERE / "scene" / "tt_scene.xml"
INSTANCE = HERE / "instance.npz"
CAM_EVERY = 2                    # 50 Hz camera
BALL_R, HALF_T, E_PADDLE = 0.02, 0.0075, 0.80   # E_PADDLE: the ball-blade pair's normal restitution (revision 14)
OPP_HALF = dict(table_edges_valid=True, target_center=np.array([0.0, 0.685]), target_half=np.array([0.7625, 0.685]))
REST_ARM = 0.6                   # the service's return to the ready pose: 60 % of the arm's joint speed limits
rcb_tt.HORIZON = 10 ** 7         # no episode-level step cap in the tooling; the match ends itself


def world_spin(d) -> np.ndarray:
    R = np.zeros(9)
    mj.mju_quat2Mat(R, d.qpos[3:7])
    return R.reshape(3, 3) @ d.qvel[3:6]


def _ball_only_xml(path: Path) -> str:
    root = ET.parse(path).getroot()
    wb = root.find("worldbody")
    for b in list(wb):
        if b.tag == "body" and b.get("name") in (rcb_tt.ROBOT_ROOT, rcb_tt.ROBOT_ROOT + "_b"):
            wb.remove(b)
    for el in root.findall("actuator"):
        root.remove(el)
    con = root.find("contact")
    for el in list(con):
        if el.tag == "exclude" or (el.tag == "pair" and (el.get("geom2", "").startswith("paddle_blade") or
                                                        (el.get("name") or "").startswith("selfcol"))):
            con.remove(el)
    root.find("compiler").set("meshdir", str((path.parent / "assets").resolve()))
    return ET.tostring(root, encoding="unicode")


class BallModel:
    """Ball-only copy of the scene (same ball / table / net physics): the stroke controller's own forward model."""

    def __init__(self):
        from mujoco import rollout
        root = ET.fromstring(_ball_only_xml(SCENE))
        sensors = ET.SubElement(root, "sensor")
        for geom in ("geom_table", "geom_net", "floor"):
            ET.SubElement(sensors, "distance", geom1="geom_ball", geom2=geom, cutoff="10")
        self.m = mj.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
        self.d = mj.MjData(self.m)
        self.native = rollout.Rollout()

    def rollout(self, p, v, w_world, n, stop_at_contact=False):
        # MuJoCo's native loop releases the GIL and avoids thousands of Python transitions.
        state0 = np.r_[0.0, p, 1.0, 0.0, 0.0, 0.0, v, w_world]
        states, distances = self.native.rollout(self.m, self.d, state0, nstep=n)
        st = states[0]
        P, V = st[:, 1:4].copy(), st[:, 8:11].copy()
        q, w = st[:, 4:8], st[:, 11:14]
        # Quaternion rotation of local angular velocity into world coordinates.
        qw, qv = q[:, :1], q[:, 1:]
        W = w + 2*np.cross(qv, np.cross(qv, w) + qw*w)
        hits = np.flatnonzero(np.any(distances[0] <= 0, axis=1))
        first = None
        if len(hits):
            i = int(hits[0]); geom = int(np.argmin(distances[0, i]))
            kind = "net" if geom == 1 else ("floor" if geom == 2 else
                    ("table_opp" if P[i, 1] > 0 else "table_own"))
            first = (i, kind, P[i].copy())
            if stop_at_contact:
                return P[:i+1], V[:i+1], W[:i+1], first
        return P, V, W, first


def hermite(q0, v0, q1, v1, T, n):
    t = np.arange(1, n + 1) * (T / n)
    s = t / T
    h00 = 2 * s**3 - 3 * s**2 + 1; h10 = s**3 - 2 * s**2 + s; h01 = -2 * s**3 + 3 * s**2; h11 = s**3 - s**2
    return h00[:, None] * q0 + h10[:, None] * T * v0 + h01[:, None] * q1 + h11[:, None] * T * v1


def touches_table(s: rcb_tt.Session, rows, every: int = 2) -> bool:
    """Whether the robot, posed at the joint targets `rows` (9 each; kinematics only, the ball parked away), would
    penetrate the table, the net or the floor: the planners' check of a swing path (sampled every `every` rows)."""
    m = s.m
    if not hasattr(s, "_chk"):
        s._chk = mj.MjData(m)
        env = {mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, n) for n in ("geom_table", "geom_net", "floor")}
        s._chk_env = env
    d = s._chk
    rows = list(rows)
    for i in list(range(0, len(rows), every)) + [len(rows) - 1]:
        if i < 0:
            continue
        d.qpos[:] = 0.0
        d.qpos[0:3] = [3.0, 3.0, 5.0]; d.qpos[3] = 1.0
        d.qpos[s._qadr] = rows[i]
        mj.mj_kinematics(m, d)
        mj.mj_collision(m, d)
        for c in d.contact[:d.ncon]:
            g1, g2 = int(c.geom1), int(c.geom2)
            if ((g1 in s._robot_geoms and g2 in s._chk_env) or (g2 in s._robot_geoms and g1 in s._chk_env)) \
                    and c.dist < 0.0:
                return True
    return False


def via_pose(p_c, v_p, nrm, dz):
    """A pre-contact blade position for a swing that comes onto a low contact over the table: where the blade would be
    VIA_STEPS_LIMITS control steps before the contact moving straight at the contact velocity v_p, raised by dz. The
    swing then passes the via already at stroke speed (revision 14/11; until then the via was 0.10 m back along the
    horizontal motion and dz above, and turning that descent into the upward contact velocity cost the via strokes
    about 40 % of their blade speed)."""
    return (np.asarray(p_c, float) - np.asarray(v_p, float) * (VIA_STEPS_LIMITS * CONTROL_DT)
            + np.array([0.0, 0.0, dz]))


def contact_prescale(ratio: float) -> float:
    """The factor the contact joint velocity is divided by before the swing is planned (match.plan_paddle and the
    duel's workers.prepare share it, so both formats hit alike). ratio = the busiest joint's |qd| / its speed limit.
    Only the hermite swing needs the contact velocity within 0.9 x the limits; the limits-aware planner (stroke_rows,
    bodies/trajopt) keeps every joint within its velocity, acceleration and jerk limits itself and delivers the best
    reachable contact velocity, so a uniform pre-scale there only threw blade speed away (re-screen 2026-10-12,
    revision 14/11: the full-sim contact blade speed 0.60 -> 0.84 of the command, B9 with D13 210 -> 262 of 282)."""
    return max(1.0, float(ratio) / 0.9) if PLANNER == "hermite" else 1.0


VIA_DZ = (0.05, 0.10, 0.18)       # the pre-contact heights tried when the direct swing would touch the table
VIA_STEPS = 12                    # the final approach from the pre-contact pose: 0.12 s
VIA_STEPS_LIMITS = int(os.environ.get("RCB_TT_VIA_STEPS", "12"))   # the limits-aware planner: the arm needs longer to
                                  # turn the descent onto the contact into the stroke's upward velocity


class Rally:
    """The stroke controller's helpers on a single-robot simulator `self.s` (rcb_tt.Session); subclasses: match.Match,
    duel.Planner. Joint vectors are 9 long [base_x, base_y, q1..q7] unless named `arm`."""

    s: rcb_tt.Session
    _twin = None

    @property
    def k(self) -> int:
        return self.s._k

    def _twin_session(self):
        if self._twin is None:
            self._twin = rcb_tt.Session(instance=str(INSTANCE), scene=str(SCENE))
        return self._twin

    def _target_vel(self) -> np.ndarray:
        a = self.s._actions
        return (a[-1] - a[-2]) / CONTROL_DT if len(a) >= 2 else np.zeros(rcb_tt.NQ)

    def _rest_target(self, base_goal=None, arm_speed=REST_ARM, base_speed=1.0) -> np.ndarray:
        """One step of the service's rest motion: the arm towards the ready pose at arm_speed x its speed limits (within
        its acceleration limits, rcb_tt.seek), the base towards base_goal (default: home) with the go-to generator (base_speed x BASE_VMAX, BASE_AMAX)."""
        tgt = self.s._target
        vel = self._target_vel()
        arm, _ = rcb_tt.seek(tgt[2:], vel[2:], self.s.inst["q0"], ARM_VEL * arm_speed, rcb_tt.ARM_ACC,
                             self.s.JOINT_LOW[2:], self.s.JOINT_HIGH[2:])
        b, _, _ = rcb_tt.base_goto(tgt[:2], vel[:2], HOME if base_goal is None else base_goal,
                                   vmax=BASE_VMAX * base_speed, a=self._target_acc()[:2])
        return np.r_[b, arm]

    def _simulate_arm(self, targets, n):
        """Robot-only rollout of `targets` (9-joint rows) from the live robot state (base and arm, positions and
        velocities); the paddle's (pos, normal, vel) after n steps. The ball is parked far away."""
        tw = self._twin_session()
        m, d = tw.m, tw.d
        mj.mj_resetData(m, d)
        d.qpos[tw._qadr] = self.s.d.qpos[self.s._qadr]; d.qvel[tw._vadr] = self.s.d.qvel[self.s._vadr]
        d.qpos[0:3] = [3.0, 3.0, 5.0]; d.qpos[3:7] = [1, 0, 0, 0]
        mj.mj_forward(m, d)
        tw._target = self.s._target.copy(); tw._k = 0; tw._actions = []; tw._events = []; tw._last_touch = {}
        tw.servo.copy_from(self.s.servo)             # the live robot's servo state (setpoints, torques)
        tw.substep_hook = None
        tw._robot_table = 0; tw._robot_net = 0
        for j in range(n):
            d.qpos[0:3] = [3.0, 3.0, 5.0]; d.qvel[0:6] = 0
            tw.step(targets[j])
        st = tw.state()
        self._rehearsal_table = bool(tw._robot_table or tw._robot_net)   # the rehearsed robot touched the table/net
        return st["paddle_pos"], st["paddle_normal"], st["paddle_vel"]

    def _swing_targets(self, q_h, qd_h, n_avail, n_sw, base_rows, via=None):
        """9-joint rows: the arm holds, then a cubic swing to (q_h, qd_h) at step n_avail and a 25-step
        follow-through; the base follows base_rows (its go-to trajectory, >= n_avail + 25 rows). With via = q_pre
        (an arm pose above and behind the contact) the swing goes there first and the last VIA_STEPS come down onto
        the contact (table avoidance). Every row within the joint ranges and speed limits from the target in force."""
        if PLANNER != "hermite":
            return self._stroke_targets(q_h, qd_h, n_avail, base_rows, via)
        q_s = self.s._target[2:].copy()
        v_s = self._target_vel()[2:]
        pre = np.tile(q_s, (n_avail - n_sw, 1))
        n_f = VIA_STEPS
        if via is not None and n_sw - n_f >= 8:
            qd_pre = (q_h - via) / (n_f * CONTROL_DT)
            qd_pre = qd_pre / max(1.0, float(np.max(np.abs(qd_pre) / ARM_VEL)) / 0.95)
            first = hermite(q_s, v_s if n_sw == n_avail else np.zeros(7), via, qd_pre, (n_sw - n_f) * CONTROL_DT,
                            n_sw - n_f)
            swing = np.vstack([first, hermite(via, qd_pre, q_h, qd_h, n_f * CONTROL_DT, n_f)])
        else:
            swing = hermite(q_s, v_s if n_sw == n_avail else np.zeros(7), q_h, qd_h, n_sw * CONTROL_DT, n_sw)
        n_f = 25
        follow = hermite(q_h, qd_h, q_h + qd_h * 0.5 * n_f * CONTROL_DT, np.zeros(7), n_f * CONTROL_DT, n_f)
        arm = np.vstack([pre, swing, follow])
        base = np.asarray(base_rows, float)
        out, prev = [], self.s._target.copy()
        lim = VEL_LIMIT * CONTROL_DT * 0.999
        lo, hi = self.s.JOINT_LOW + 1e-4, self.s.JOINT_HIGH - 1e-4
        for i, qa in enumerate(arm):
            q = np.clip(np.r_[base[min(i, len(base) - 1)], qa], lo, hi)
            q = prev + np.clip(q - prev, -lim, lim)
            out.append(q); prev = q
        return out

    def _target_acc(self) -> np.ndarray:
        a = self.s._actions
        return (a[-1] - 2 * a[-2] + a[-3]) / CONTROL_DT ** 2 if len(a) >= 3 else np.zeros(rcb_tt.NQ)

    def _stroke_targets(self, q_h, qd_h, n_avail, base_rows, via=None, n_follow=25):
        """9-joint rows from the limits-aware planner (bodies/trajopt.stroke): from the arm's current target state an
        anticipation move to a wind-up pose at rest, the stroke started as late as the slowest joint allows, the
        contact (q_h, qd_h) at step n_avail (through the pre-contact pose `via` if given), a follow-through to rest;
        every motion within the Panda's velocity, acceleration and jerk limits (95 %); the base follows base_rows.
        self._stroke_info: the plan's n_stroke, the share of qd_h delivered (scale) and the contact error."""
        s = self.s
        lo, hi = s.JOINT_LOW + 1e-4, s.JOINT_HIGH - 1e-4
        out = stroke_rows(s._target, self._target_vel(), self._target_acc(), q_h, qd_h, n_avail, base_rows, lo, hi,
                          via=via, n_follow=n_follow,
                          M=[self._arm_inertia(q_h), self._arm_inertia(s._target[2:]),
                             self._arm_inertia(0.5 * (q_h + s._target[2:]))],
                          serve=(getattr(self, "leg", None) or {}).get("kind") == "our_serve")
        self._stroke_info = out[1]
        return out[0]

    def _arm_inertia(self, q_arm, base=None):
        """the arm's joint-space inertia at q_arm (kinematic scratch data; for the torque-rate jerk caps)"""
        return arm_inertia(self.s, np.r_[self.s._target[:2] if base is None else base, q_arm])

    def _ik(self, pos, normal, q_init, base, iters=200, tol=1e-4, w=None):
        """Arm IK (7 joints) with the base at `base`: blade centre at pos, face normal along normal. w: joint weights
        of the steps (a weighted damped least-squares IK: joints with a small weight move little)."""
        s = self.s
        q = np.array(q_init, float)
        b = np.asarray(base, float)
        n_t = normal / np.linalg.norm(normal)
        err = np.inf
        jacp = np.zeros((3, s.m.nv)); jacr = np.zeros((3, s.m.nv))
        damping = 1e-3 * np.eye(6)
        lo, hi = s.JOINT_LOW[2:] + 1e-4, s.JOINT_HIGH[2:] - 1e-4
        va = s._vadr[2:]

        def cross(a, c):
            return np.array([a[1]*c[2]-a[2]*c[1], a[2]*c[0]-a[0]*c[2], a[0]*c[1]-a[1]*c[0]])
        for _ in range(iters):
            s._kin_set(np.r_[b, q])
            p = s._kin.site_xpos[s._paddle_site]
            R = s._kin.site_xmat[s._paddle_site].reshape(3, 3)
            n = R[:, 0]
            e = np.concatenate((pos - p, cross(n, n_t)))
            err = float(np.linalg.norm(e[:3]) + np.arcsin(min(1.0, np.linalg.norm(e[3:]))))
            if n @ n_t < 0:
                e[3:] = cross(n, n_t) + 0.5 * cross(n, R[:, 1]); err += np.pi / 2
            if err < tol:
                break
            mj.mj_jacSite(s.m, s._kin, jacp, jacr, s._paddle_site)
            J = np.vstack([jacp[:, va], jacr[:, va]])
            if w is None:
                q = np.clip(q + J.T @ np.linalg.solve(J @ J.T + damping, e), lo, hi)
            else:
                Jw = J * w
                q = np.clip(q + w * (Jw.T @ np.linalg.solve(Jw @ J.T + damping, e)), lo, hi)
        return q, err


def arm_inertia(s: rcb_tt.Session, q9) -> np.ndarray:
    """The arm's joint-space inertia (7 x 7) at the joint vector q9 (the session's kinematic scratch data)."""
    s._kin_set(np.asarray(q9, float))
    mj.mj_makeM(s.m, s._kin)                     # MuJoCo >= 3.3: qM comes from mj_makeM, not mj_crb
    M = np.zeros((s.m.nv, s.m.nv))
    mj.mj_fullM(s.m, M, s._kin.qM)
    va = s._vadr[2:]
    return M[np.ix_(va, va)]


def reach_weights(n, M=None):
    """Per arm joint, how far (position) and how much (velocity) it can still change in n control steps under the
    real limits (rest to rest: min(V t, A t^2 / 4, J t^3 / 32); a velocity change: min(A t, J t^2 / 4)), J capped by
    the torque rate at the inertia M; normalised to the largest. The re-plan weights: with little time left the
    shoulder and elbow (low torque-rate jerk) keep their course and the wrist makes the correction."""
    t = max(1, int(n)) * CONTROL_DT
    J = ARM_LIM.jerk if M is None else np.minimum(ARM_LIM.jerk, AL.jerk_caps(M, ARM_LIM))
    A, V = ARM_LIM.acc, ARM_LIM.vel
    dq = np.minimum(np.minimum(V * t, A * t * t / 4), J * t ** 3 / 32)
    dv = np.minimum(A * t, J * t * t / 4)
    return dq / float(np.max(dq)), dv / float(np.max(dv))


def vel_weights(M=None) -> np.ndarray:
    """The joint weights of the paddle-velocity distribution at a contact (qd = W J' (J W J')^-1 v): the velocity
    limits squared; with the limits-aware planner also in proportion to the jerk each joint can use at the contact
    pose (the torque-rate caps: the shoulder and elbow start slowly, the wrist fast), so the wrist takes more of it."""
    W = ARM_VEL ** 2
    if PLANNER == "hermite" or M is None or os.environ.get("RCB_TT_WRIST_WEIGHT") != "1":
        return np.diag(W)
    cap = AL.jerk_caps(M, ARM_LIM)
    return np.diag(W * cap / float(np.max(cap)))


SERVE_TOL = (1e-3, 5e-3)          # (rad, rad/s): a service, planned once with its exact timing: velocity first
RETURN_TOL = (2e-4, 2e-2)         # a return, re-planned as the prediction improves: position first


def stroke_rows(target, vel, acc, q_h, qd_h, n_avail, base_rows, lo, hi, via=None, n_follow=25, M=None, serve=False):
    """The limits-aware stroke as 9-joint rows (shared by the match and the duel): the arm from bodies/trajopt.stroke
    (jerk limits also capped by the torque rate at the contact pose when M, the arm's inertia there, is given), the
    base from base_rows; every row within the ranges and the per-step speed limits. Returns (rows, info)."""
    Ms = [] if M is None else ([M] if np.ndim(M) == 2 else list(M))   # one inertia or several poses' (min caps)
    lim = ARM_LIM if not Ms else ARM_LIM.with_jerk(np.min([AL.jerk_caps(m_, ARM_LIM) for m_ in Ms], axis=0))
    n = int(max(1, n_avail))
    pl = trajopt.stroke(np.asarray(target, float)[2:], np.asarray(vel, float)[2:], np.asarray(acc, float)[2:], n,
                        CONTROL_DT, lim, q_h, qd_h, n_follow=n_follow, via=via, via_steps=VIA_STEPS_LIMITS,
                        lo=np.asarray(lo)[2:], hi=np.asarray(hi)[2:],
                        tol_q=(SERVE_TOL if serve else RETURN_TOL)[0], tol_v=(SERVE_TOL if serve else RETURN_TOL)[1])
    if os.environ.get("RCB_TT_PLAN_DEBUG"):
        print("PLAN", n, "q0", np.round(np.asarray(target)[2:], 2).tolist(), "q1", np.round(q_h, 2).tolist(), "v1",
              np.round(qd_h, 2).tolist(), "J", np.round(lim.jerk).tolist(), "err", round(pl["contact_err_q"], 3),
              file=sys.stderr, flush=True)
    base = np.asarray(base_rows, float)
    out, prev = [], np.asarray(target, float).copy()
    step = VEL_LIMIT * CONTROL_DT * 0.999
    for i, qa in enumerate(pl["q"]):
        q = np.clip(np.r_[base[min(i, len(base) - 1)], qa], lo, hi)
        q = prev + np.clip(q - prev, -step, step)
        out.append(q); prev = q
    out = rcb_tt.limit_rows(out, target, vel, lo=lo, hi=hi)   # last guard: the low level checks speed + acceleration
    info = dict(n_stroke=int(pl["n_stroke"]), plan_scale=round(float(min(1.0, max(0.0, pl["scale"]))), 3),
                plan_contact_err=round(float(pl["contact_err_q"]), 4), plan_viol=round(float(pl["viol"]), 3))
    return out, info
