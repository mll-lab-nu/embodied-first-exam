"""Core of the table-tennis rally service (interactive mode): the episode, the stroke controller and the views.

An episode = N_BALLS incoming balls (recorded DeepMind serves, `rally.json`), one after another. Per ball:
  ready   READY_STEPS control steps: the service brings the arm back to the ready pose Q0; the next ball is held
          at its launch state, out of play.
  launch  the ball is released from its recorded state (bounces on the opponent's half, crosses the net).
  pause   at the 5th camera frame after the ball's bounce on the opponent's half the world stops: DECISION POINT.
  shot    the decision (swing: contact time, contact point, aim point; or skip) arrives; first the think delay
          runs (arm holding the ready pose, ball flying), then the stroke controller plans and executes the swing.
  outcome the ball's first contact after the paddle, or the ball out of play / 2.5 s after the launch.
The whole episode is recorded as (applied joint targets, launch schedule) and replays bit-exactly (`replay()`).
"""
from __future__ import annotations

import io
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

import mujoco as mj
import rcb_tt
from rcb_tt import CONTROL_DT, VEL_LIMIT

HERE = Path(__file__).resolve().parent
SCENE = HERE / "scene" / "tt_scene.xml"
INSTANCE = HERE / "instance.npz"
BALLS = json.load(open(HERE / "rally.json"))["balls"]
N_BALLS = len(BALLS)
READY_STEPS = 60                 # 0.6 s between one outcome and the next launch
BALL_STEPS = 250                 # a ball is over at the latest 2.5 s after its launch
CAM_EVERY = 2                    # 50 Hz camera
NOISE_SIGMA = 0.003
NOISE_SEED = 314159
AIM_DEFAULT = (0.0, 0.7)
ADJUST_FRAMES = 3               # adjust point: 3rd camera frame (0.06 s) after the bounce on our half
DECISION_FRAMES = 5             # decision point: 5th camera frame (0.1 s) after the bounce on the opponent's half
AIM_BIAS = np.array([-0.1, -0.28])   # controller calibration: its forward model sends clean contacts ~(0.1, 0.28) m long/right
BALL_R, HALF_T, E_PADDLE = 0.02, 0.0075, 0.985
OPP_HALF = dict(table_edges_valid=True, target_center=np.array([0.0, 0.685]), target_half=np.array([0.7625, 0.685]))
rcb_tt.HORIZON = 10 ** 7         # no episode-level step cap in the tooling; the rally ends itself


def world_spin(d) -> np.ndarray:
    R = np.zeros(9)
    mj.mju_quat2Mat(R, d.qpos[3:7])
    return R.reshape(3, 3) @ d.qvel[3:6]


def _ball_only_xml(path: Path) -> str:
    root = ET.parse(path).getroot()
    wb = root.find("worldbody")
    for b in list(wb):
        if b.tag == "body" and b.get("name") == "link0":
            wb.remove(b)
    for el in root.findall("actuator"):
        root.remove(el)
    con = root.find("contact")
    for el in list(con):
        if el.tag == "exclude" or (el.tag == "pair" and el.get("geom2") == "paddle_blade"):
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


class Rally:
    """The episode. Live: step() / run_to_decision() / shot(). Replay: replay(actions, schedule)."""

    def __init__(self):
        self.s = rcb_tt.Session(instance=str(INSTANCE), scene=str(SCENE))
        self.bm = BallModel()
        self.schedule: list[dict] = []          # per ball: {"ball", "hold_from", "launch"}
        self.i = -1                             # current ball (index into BALLS), -1 before the first hold
        self.frames: list[dict] = []            # camera frames of the current ball
        self.results: list[dict] = []           # per-ball outcome
        self.shots: list[dict] = []             # per-ball decision record
        self.done = False
        self.phase = "swing"                    # which decision the episode waits for: swing | adjust | done
        self.plan, self.plan_j, self._rec = [], 0, {}
        self._twin = None
        self._ik_seed = None
        self._schedule_ball(0, 0)

    # ------------------------------------------------------------------ bookkeeping
    @property
    def k(self) -> int:
        return self.s._k

    def _schedule_ball(self, i, hold_from):
        self.schedule.append({"ball": i, "hold_from": hold_from, "launch": hold_from + READY_STEPS})
        self.i = i
        self.frames = []
        self._park()

    def _cur(self) -> dict:
        return self.schedule[-1]

    def _park(self):
        b = BALLS[self.i]
        d = self.s.d
        d.qpos[0:3] = b["pos"]; d.qpos[3:7] = [1, 0, 0, 0]; d.qvel[0:3] = b["vel"]; d.qvel[3:6] = b["spin"]
        s = self.s
        s._events.clear(); s._last_touch.clear(); s._robot_table = 0; s._v_out = None

    def in_play(self) -> bool:
        return self.k > self._cur()["launch"]

    def t_since_launch(self) -> float:
        return round((self.k - self._cur()["launch"]) * CONTROL_DT, 6)

    def ball_outcome_final(self) -> bool:
        if not self.in_play():
            return False
        if self.k - self._cur()["launch"] >= BALL_STEPS:
            return True
        kinds = [e["kind"] for e in self.s._events]
        if "paddle" in kinds and any(x != "paddle" for x in kinds[kinds.index("paddle") + 1:]):
            return True
        if any(x in ("floor", "robot", "other") for x in kinds):
            return True
        p = self.s.d.qpos
        return bool(p[2] < -0.3 or p[1] < -2.6)

    # ------------------------------------------------------------------ stepping (shared by live and replay)
    def step(self, q):
        self.s.step(q)
        cur = self._cur()
        if self.k <= cur["launch"]:
            self._park()                         # held out of play until the launch step
        elif (self.k - cur["launch"]) % CAM_EVERY == 0:
            p = self.s.d.qpos[0:3]
            if p[2] > -0.5 and p[1] > -2.6 and abs(p[0]) < 2.0:
                f = (self.k - cur["launch"]) // CAM_EVERY
                noise = np.random.default_rng([NOISE_SEED, cur["ball"], f]).normal(0.0, NOISE_SIGMA, 3)
                self.frames.append({"t": self.t_since_launch(), "pos": [round(float(x), 4) for x in p + noise]})

    def _close_ball(self):
        v = rcb_tt.judge(self.s._events, OPP_HALF, robot_env_contact=self.s._robot_table)
        kinds = [e["kind"] for e in self.s._events]
        ret = bool(v["success"])
        res = {"ball": self.i, "returned": ret, "hit": int(v["hit"]), "n_paddle_contacts": int(v["n_paddle_contacts"]),
               "landed_opponent_half": int(v["landed_opponent_half"]), "landing_x": round(float(v["landing_x"]), 4),
               "landing_y": round(float(v["landing_y"]), 4), "net_touch": int(v["net_touch"]),
               "robot_env_contact": int(v["robot_env_contact"]), "events": kinds, "step": self.k,
               "own_bounces_before_hit": int(v["own_bounces_before_hit"])}
        if ret:
            res["summary"] = f"returned: landed on the opponent's half at x={v['landing_x']:.2f}, y={v['landing_y']:.2f}"
        elif not v["hit"]:
            res["summary"] = "missed: no paddle contact"
        elif v["robot_env_contact"]:
            res["summary"] = "fault: the arm or paddle touched the table/net/floor"
        elif v["n_paddle_contacts"] != 1:
            res["summary"] = "fault: more than one paddle contact"
        elif v["own_bounces_before_hit"] != 1:
            res["summary"] = "fault: hit before the ball bounced on your half (volley)"
        elif v["landed"]:
            res["summary"] = (f"fault: first contact after the hit was {kinds[kinds.index('paddle') + 1:][0]} at "
                              f"x={v['landing_x']:.2f}, y={v['landing_y']:.2f}")
        else:
            res["summary"] = "fault: the ball did not land"
        self.results.append(res)
        return res

    def replay(self, actions, schedule) -> None:
        """Fresh replay of a recorded episode (same actions and launch schedule). Each ball is judged at the
        first step its outcome is final, exactly as in the live episode (results in self.results)."""
        sched = [dict(x) for x in schedule]
        self.schedule = [sched[0]]; self.i = sched[0]["ball"]; self._park()
        j, closed = 1, set()
        for q in actions:
            if j < len(sched) and self.k == sched[j]["hold_from"]:
                self.schedule.append(sched[j]); self.i = sched[j]["ball"]; self.frames = []; self._park()
                j += 1
            self.step(q)
            if self.i not in closed and self.ball_outcome_final():
                self._close_ball(); closed.add(self.i)

    # ------------------------------------------------------------------ live episode
    def _ready_target(self):
        """Service-driven return to the ready pose Q0 (speed-limited, 60 % of the joint speed limits)."""
        tgt = self.s._target
        lim = VEL_LIMIT * CONTROL_DT * 0.6
        return tgt + np.clip(self.s.inst["q0"] - tgt, -lim, lim)

    def run_to_decision(self) -> None:
        """Advance until the current ball reaches its decision point (first camera frame past the net)."""
        while not self.done:
            self.step(self._ready_target())
            if self.in_play() and self._decision_due():
                return
            if self.ball_outcome_final():          # (cannot normally happen before the decision point)
                self._next_ball()

    def _decision_due(self) -> bool:
        """Decision point: the DECISION_FRAMES-th camera frame after the ball's bounce on the opponent's half
        (or, if it never bounces there, the first frame past the net)."""
        ev = [e for e in self.s._events if e["kind"] == "table_opp"]
        if ev:
            t_b = ev[0]["t"] - self._cur()["launch"] * CONTROL_DT
            return sum(1 for f in self.frames if f["t"] > t_b) >= DECISION_FRAMES
        return bool(self.frames and self.frames[-1]["pos"][1] < 0.0)

    def _next_ball(self):
        self._close_ball()
        if self.i + 1 < N_BALLS:
            self._schedule_ball(self.i + 1, self.k)
        else:
            for _ in range(20):                    # a short tail so the last landing is in the video
                self.step(self.s._target)
            self.done = True

    def decision_observation(self) -> dict:
        st = self.s.state()
        return {"ball_index": self.i, "n_balls": N_BALLS, "t_since_launch": self.t_since_launch(),
                "frames": list(self.frames), "q": st["q"].round(4).tolist(),
                "paddle_pos": st["paddle_pos"].round(4).tolist(), "paddle_normal": st["paddle_normal"].round(4).tolist(),
                "events": [{"event": e["kind"], "t_since_launch": round(e["t"] - self._cur()["launch"] * CONTROL_DT, 3)}
                           for e in self.s._events],
                "returns_so_far": sum(r["returned"] for r in self.results), "results_so_far": list(self.results)}

    def _adjust_due(self) -> bool:
        """Second decision point: the ADJUST_FRAMES-th camera frame after the bounce on our half."""
        ev = [e for e in self.s._events if e["kind"] == "table_own"]
        if not ev or any(e["kind"] == "paddle" for e in self.s._events):
            return False
        t_b = ev[0]["t"] - self._cur()["launch"] * CONTROL_DT
        return sum(1 for f in self.frames if f["t"] > t_b) >= ADJUST_FRAMES

    def _run_plan(self, stop_at_adjust: bool) -> bool:
        """Execute the current plan (then hold) until the ball's outcome (False) or the adjust point (True)."""
        while not self.ball_outcome_final():
            self.step(self.plan[self.plan_j] if self.plan_j < len(self.plan) else self.s._target)
            self.plan_j += 1
            if stop_at_adjust and self._adjust_due():
                return True
        return False

    def _finish_ball(self, rec) -> dict:
        if self.s._v_out is not None:
            rec["v_out_actual"] = [round(float(x), 3) for x in self.s._v_out]
        self.shots.append(rec)
        self._next_ball()
        res = dict(self.results[-1]); res.update({k: rec[k] for k in rec if k not in ("decision", "adjust")})
        self.phase = "done" if self.done else "swing"
        if not self.done:
            self.run_to_decision()
        return res

    def shot(self, decision: dict, delay_steps: int) -> dict:
        """Decision 1 (swing / skip): think delay (the arm holds its ready pose, the ball flies), then the stroke
        controller plans and starts the swing; runs to the adjust point (-> {"phase": "adjust"}) or, if there is
        none, to the ball's outcome and on to the next ball's first decision point (-> the ball's result)."""
        rec = {"ball": self.i, "decision": decision, "delay_steps": int(delay_steps), "k_decision": self.k}
        self.plan, self.plan_j = [], 0
        self._ik_seed = None
        self._planned_hit = None
        for _ in range(delay_steps):
            if self.ball_outcome_final():
                break
            self.step(self.s._target)
        rec["k_exec"] = self.k
        if decision.get("type") == "swing" and not self.ball_outcome_final():
            self.plan, info = self.plan_stroke(float(decision["t"]), np.asarray(decision["pos"], float),
                                               np.asarray(decision.get("aim", AIM_DEFAULT), float))
            rec.update(info)
        self._rec = rec
        if decision.get("type") == "swing" and self._run_plan(stop_at_adjust=True):
            self.phase = "adjust"
            return {"phase": "adjust", "ball": self.i, **{k: rec[k] for k in rec if k != "decision"}}
        self._run_plan(stop_at_adjust=False)
        return self._finish_ball(rec)

    def adjust(self, decision: dict, delay_steps: int) -> dict:
        """Decision 2 (adjust / keep): during the think delay the swing already under way continues; then, for an
        adjust, the stroke controller re-plans the rest of the swing from the arm's current motion."""
        rec = self._rec
        rec["adjust"] = decision
        rec["adjust_delay_steps"] = int(delay_steps)
        rec["k_adjust_decision"] = self.k
        for _ in range(delay_steps):
            if self.ball_outcome_final():
                break
            self.step(self.plan[self.plan_j] if self.plan_j < len(self.plan) else self.s._target)
            self.plan_j += 1
        rec["k_adjust_exec"] = self.k
        self._ik_seed = getattr(self, "_planned_hit", None)
        if decision.get("type") == "adjust" and not self.ball_outcome_final():
            plan, info = self.plan_stroke(float(decision["t"]), np.asarray(decision["pos"], float),
                                          np.asarray(decision.get("aim", rec.get("aim", AIM_DEFAULT)), float))
            rec["adjust_info"] = info
            if plan:
                self.plan, self.plan_j = plan, 0
        self._run_plan(stop_at_adjust=False)
        return self._finish_ball(rec)

    # ------------------------------------------------------------------ stroke controller
    def _twin_session(self):
        if self._twin is None:
            self._twin = rcb_tt.Session(instance=str(INSTANCE), scene=str(SCENE))
        return self._twin

    def _simulate_arm(self, targets, n):
        """Robot-only rollout of `targets` from the live arm state; paddle (pos, normal, vel) after n steps."""
        tw = self._twin_session()
        m, d = tw.m, tw.d
        mj.mj_resetData(m, d)
        d.qpos[tw._qadr] = self.s.d.qpos[self.s._qadr]; d.qvel[tw._vadr] = self.s.d.qvel[self.s._vadr]
        d.qpos[0:3] = [3.0, 3.0, 5.0]; d.qpos[3:7] = [1, 0, 0, 0]
        mj.mj_forward(m, d)
        tw._target = self.s._target.copy(); tw._k = 0; tw._actions = []; tw._events = []; tw._last_touch = {}
        for j in range(n):
            d.qpos[0:3] = [3.0, 3.0, 5.0]; d.qvel[0:6] = 0
            tw.step(targets[j])
        st = tw.state()
        return st["paddle_pos"], st["paddle_normal"], st["paddle_vel"]

    def _shoot(self, p0, spin, aim):
        """Outgoing velocities whose ball-only flight lands at `aim` and clears the net by >= 5 cm (one per launch
        angle)."""
        cands = []
        for vz in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
            v = np.array([aim[0] - p0[0], 5.0, vz])
            for _ in range(10):
                P, _, _, first = self.bm.rollout(p0, v, spin, 1500, stop_at_contact=True)
                L = first[2][:2] if first else np.array([9.0, 9.0])
                err = L - aim
                if np.linalg.norm(err) < 0.01:
                    i0 = np.argmin(np.abs(P[:, 1]))
                    if first[1] == "table_opp" and P[i0, 2] > 0.2:
                        cands.append(v.copy())
                    break
                J = np.zeros((2, 2))
                for c in range(2):
                    dv = np.zeros(3); dv[c] = 1e-3
                    _, _, _, f2 = self.bm.rollout(p0, v + dv, spin, 1500, stop_at_contact=True)
                    L2 = f2[2][:2] if f2 else np.array([9.0, 9.0])
                    J[:, c] = (L2 - L) / 1e-3
                try:
                    v[:2] -= np.linalg.lstsq(J, err, rcond=None)[0]
                except np.linalg.LinAlgError:
                    break
        return cands or [np.array([aim[0] - p0[0], 5.0, 1.5])]

    def _stroke_for(self, v_in, v_out, p_hit):
        """Impulse model -> blade normal, contact point, paddle velocity; IK and joint velocity at the hit."""
        s = self.s
        dv = v_out - v_in
        nrm = dv / np.linalg.norm(dv)
        vpn = np.linalg.norm(dv) / (1 + E_PADDLE) + v_in @ nrm
        v_p = vpn * nrm + (v_in - (v_in @ nrm) * nrm)
        p_c = p_hit - nrm * (BALL_R + HALF_T)
        q_h, res = self._ik(p_c, nrm, self._ik_seed if self._ik_seed is not None else s.inst["q0"])
        Jp = s.jacobian(q_h)[:3]
        Winv = np.diag(VEL_LIMIT ** 2)
        qd_h = Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T, v_p)
        ratio = float(np.max(np.abs(qd_h) / VEL_LIMIT))
        return dict(nrm=nrm, v_p=v_p, p_c=p_c, q_h=q_h, qd_h=qd_h, ik=res, ratio=ratio, v_out=v_out)

    def plan_stroke(self, t_hit, p_hit, aim):
        """Swing so that the blade centre meets a ball centred at `p_hit` at `t_hit` (s after launch) and sends it
        towards `aim`. The blade angle and speed come from the incoming ball's velocity/spin at that time (the
        controller's own forward model) and an impulse model of the paddle (normal restitution 0.985 in the paddle frame, no slip); IK + a
        speed-weighted Jacobian inverse give the hit configuration; a cubic swing (at most 0.35 s) and follow-through,
        refined by 4 robot-only rehearsals so the lagging PD controller puts the blade where it was planned."""
        info = {"t_hit": t_hit, "p_hit": [float(x) for x in p_hit], "aim": [float(x) for x in aim]}
        cur = self._cur()
        k_hit = cur["launch"] + int(round(t_hit / CONTROL_DT))
        n_avail = k_hit - self.k
        info["n_swing_steps_available"] = int(n_avail)
        if n_avail < 1:
            info["stroke"] = "too late: the contact time has already passed"
            return [], info
        # incoming ball at the contact time, from the ball's current state (forward model)
        d = self.s.d
        n_roll = max(1, int(round((k_hit - self.k) * CONTROL_DT / 0.001)))
        P, V, W, _ = self.bm.rollout(d.qpos[0:3].copy(), d.qvel[0:3].copy(), world_spin(d), n_roll)
        v_in, w_in = V[-1], W[-1]
        cands = [self._stroke_for(v_in, v, np.asarray(p_hit, float))
                 for v in self._shoot(np.asarray(p_hit, float), -0.5 * w_in, np.asarray(aim, float) + AIM_BIAS)]
        c = self._pick_stroke(cands)
        v_out, nrm, v_p, p_c, q_h, qd_h = c["v_out"], c["nrm"], c["v_p"], c["p_c"], c["q_h"], c["qd_h"]
        s = self.s
        info["ik_residual"] = round(float(c["ik"]), 5)
        Jp = s.jacobian(q_h)[:3]
        Winv = np.diag(VEL_LIMIT ** 2)
        scale = max(1.0, c["ratio"] / 0.9)
        qd_h = qd_h / scale
        info["speed_scale"] = round(scale, 3)
        # swing duration: the shortest (>= 0.25 s) whose cubic stays under the speed limits, within the time left
        q_s = self.s._target.copy()
        v_s = self._target_vel()
        n_sw = int(n_avail)
        for n in (range(25, int(n_avail) + 1) if np.max(np.abs(v_s)) < 1e-6 else []):
            sw = hermite(q_s, np.zeros(7), q_h, qd_h, n * CONTROL_DT, n)
            if np.max(np.abs(np.diff(np.vstack([q_s, sw]), axis=0)) / (VEL_LIMIT * CONTROL_DT)) <= 0.97:
                n_sw = n
                break
        n_sw = int(min(n_sw, n_avail))
        info["n_swing_steps"] = n_sw
        q_goal, qd_goal = q_h.copy(), qd_h.copy()
        self._planned_hit = q_h.copy()
        for it in range(5):
            tg = self._swing_targets(q_goal, qd_goal, n_avail, n_sw)
            p, n_act, v_act = self._simulate_arm(tg, n_avail)
            if it == 4:
                break
            J = s.jacobian(q_goal)
            e = np.r_[p_c - p, np.cross(n_act, nrm)]
            q_goal = np.clip(q_goal + J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e),
                             s.JOINT_LOW + 1e-4, s.JOINT_HIGH - 1e-4)
            qd_goal = qd_goal + Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T, (v_p / scale) - v_act) * 0.7
            qd_goal = qd_goal / max(1.0, float(np.max(np.abs(qd_goal) / VEL_LIMIT)))
        info["blade_error_m"] = round(float(np.linalg.norm(p - p_c)), 4)
        info["n_plan"] = [round(float(x), 4) for x in nrm]; info["v_out_plan"] = [round(float(x), 3) for x in v_out]; info["v_in"] = [round(float(x), 3) for x in v_in]
        info["paddle_v_plan"] = [round(float(x), 3) for x in v_p / scale]; info["paddle_v_twin"] = [round(float(x), 3) for x in v_act]
        info["stroke"] = "ok" if n_sw >= 20 else "short swing (little time left: slow paddle)"
        return tg, info

    def _pick_stroke(self, cands):
        good = [c for c in cands if c["ik"] < 1e-3] or cands
        return min(good, key=lambda c: c["ratio"])            # the least demanding stroke

    def _target_vel(self) -> np.ndarray:
        a = self.s._actions
        return (a[-1] - a[-2]) / CONTROL_DT if len(a) >= 2 else np.zeros(7)

    def _swing_targets(self, q_h, qd_h, n_avail, n_sw):
        q_s = self.s._target.copy()
        v_s = self._target_vel()
        pre = np.tile(q_s, (n_avail - n_sw, 1))
        swing = hermite(q_s, v_s if n_sw == n_avail else np.zeros(7), q_h, qd_h, n_sw * CONTROL_DT, n_sw)
        n_f = 25
        follow = hermite(q_h, qd_h, q_h + qd_h * 0.5 * n_f * CONTROL_DT, np.zeros(7), n_f * CONTROL_DT, n_f)
        out, prev = [], q_s
        lim = VEL_LIMIT * CONTROL_DT * 0.999
        for q in np.vstack([pre, swing, follow]):
            q = np.clip(q, self.s.JOINT_LOW + 1e-4, self.s.JOINT_HIGH - 1e-4)
            q = prev + np.clip(q - prev, -lim, lim)
            out.append(q); prev = q
        return out

    def _ik(self, pos, normal, q_init, iters=200, tol=1e-4):
        s = self.s
        q = np.array(q_init, float)
        n_t = normal / np.linalg.norm(normal)
        err = np.inf
        jacp = np.zeros((3, s.m.nv)); jacr = np.zeros((3, s.m.nv))
        damping = 1e-3 * np.eye(6)
        # These vectors are always length three. Avoid numpy.cross's general
        # broadcasting machinery inside every iteration of every IK start.
        def cross(a, b):
            return np.array([a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]])
        for _ in range(iters):
            # FK and the Jacobian use the same q; refresh scratch kinematics once.
            s._kin_set(q)
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
            J = np.vstack([jacp[:, s._vadr], jacr[:, s._vadr]])
            q = np.clip(q + J.T @ np.linalg.solve(J @ J.T + damping, e), s.JOINT_LOW + 1e-4, s.JOINT_HIGH - 1e-4)
        return q, err

    # ------------------------------------------------------------------ views
    def render_views(self, width=480, height=320) -> bytes:
        """PNG: three camera views side by side (behind the robot, side, top), the camera detections of the
        current ball drawn as cyan dots (older = darker)."""
        import imageio.v2 as imageio
        if not hasattr(self, "_renderer"):
            self._renderer = mj.Renderer(self.s.m, height=height, width=width)
            cams = []
            for lookat, dist, az, el in (([0.0, -0.9, 0.15], 2.4, 60.0, -28.0), ([0.0, -0.3, 0.1], 3.4, 0.0, -10.0),
                                         ([0.0, -0.35, 0.0], 3.9, 90.0, -89.0)):
                c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
                cams.append(c)
            self._cams = cams
        r = self._renderer
        imgs = []
        n = len(self.frames)
        for c in self._cams:
            r.update_scene(self.s.d, camera=c)
            for j, fr in enumerate(self.frames):
                if r.scene.ngeom >= r.scene.maxgeom:
                    break
                a = 0.35 + 0.65 * (j + 1) / max(1, n)
                g = r.scene.geoms[r.scene.ngeom]
                mj.mjv_initGeom(g, mj.mjtGeom.mjGEOM_SPHERE, np.array([0.012, 0, 0]), np.array(fr["pos"], float),
                                np.eye(3).ravel(), np.array([0.1 * a, 0.9 * a, 1.0 * a, 1.0], np.float32))
                r.scene.ngeom += 1
            imgs.append(r.render())
        buf = io.BytesIO()
        imageio.imwrite(buf, np.concatenate(imgs, axis=1), format="png")
        return buf.getvalue()


def render_video(actions, schedule, out, fps=25):
    """Replay video, two views, 4x slow motion (frames during the ready phases are skipped every other step)."""
    import imageio.v2 as imageio
    rp = Rally()
    r = mj.Renderer(rp.s.m, height=360, width=640)
    cams = []
    for lookat, dist, az, el in (([0.0, -0.4, 0.15], 3.0, 90.0, -14.0), ([0.0, -0.3, 0.1], 3.6, 0.0, -14.0)):
        c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
        cams.append(c)
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)
    sched = [dict(x) for x in schedule]
    rp.schedule = [sched[0]]; rp.i = sched[0]["ball"]; rp._park()
    j = 1
    for k, q in enumerate(actions):
        if j < len(sched) and rp.k == sched[j]["hold_from"]:
            rp.schedule.append(sched[j]); rp.i = sched[j]["ball"]; rp.frames = []; rp._park(); j += 1
        rp.step(q)
        if not rp.in_play() and k % 3:
            continue
        imgs = []
        for c in cams:
            r.update_scene(rp.s.d, camera=c)
            imgs.append(r.render())
        w.append_data(np.concatenate(imgs, axis=1))
    w.close(); r.close()
