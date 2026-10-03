"""Basketball shooting contest: the simulator, the shot controller, the defender and the scoring rules (sim sidecar only).

One episode = the shots of a plan (default: two from each of five spots). At each decision point the world is paused:
the shooter (a Franka Panda on a pedestal with a ball cup) stands at the spot holding the ball, the defender stands
still between it and the hoop. A decision is a set of release parameters; the service runs the throw (wind-up,
release at THROW_RELEASE_S, follow-through), then the flight until the shot is resolved. Thinking costs no
simulated time (program play: the agent's time is its chess clock), so the defender never moves.

Determinism: everything is a function of the instance seed and the recorded decision list; the execution scatter is
drawn from a per-shot seeded generator. `Game.replay(actions)` on a fresh process reproduces the state hash
bit-exactly (MuJoCo is deterministic for the same binary, model and inputs).
"""
from __future__ import annotations

import hashlib
import math
import os

import mujoco as mj
import numpy as np

import court

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE_DIR = os.path.join(HERE, "scene")

INSTANCE_SEED = int(os.environ.get("BB_SEED", "7"))
N_SHOTS = 10
MAKES_NEEDED = 6
CONTROL_DT = 0.01
SUBSTEPS = int(round(CONTROL_DT / 0.0005))
THROW_RELEASE_S = 0.45
FLIGHT_MAX_S = 4.0

# air: drag F = -C_D |v| v, Magnus F = C_M (w x v)   (rho 1.2, Cd 0.54, A = pi r^2; C_M = 0.5 rho A r * 1.3)
C_D = 0.5 * 1.2 * 0.54 * math.pi * court.BALL_R ** 2
C_M = 0.5 * 1.2 * math.pi * court.BALL_R ** 2 * court.BALL_R * 1.3

# execution scatter of the launcher (1 sigma)
NOISE = {"speed_rel": 0.005, "angle_deg": 0.40, "yaw_deg": 0.40, "spin_hz": 0.15}

# defender
DEF_START_MAX = 3.0        # start distance (shooter axis to defender axis) = min(DEF_START_MAX, DEF_START_FRAC * r)
DEF_START_FRAC = 0.55

# arm keyframes (joint1 is replaced by the aim yaw)
Q_REST = np.array([0.0, -0.3, 0.0, -2.2, 0.0, 2.0, 0.785])
Q_WIND = np.array([0.0, -0.6, 0.0, -2.6, 0.0, 1.2, 0.785])
Q_REL = np.array([0.0, 0.0, 0.0, -0.6, 0.0, 2.4, 0.785])
Q_FOLL = np.array([0.0, 0.35, 0.0, -0.4, 0.0, 2.9, 0.785])
KEYS = [(0.0, Q_REST), (0.25, Q_WIND), (THROW_RELEASE_S, Q_REL), (0.65, Q_FOLL), (1.25, Q_REST)]

# spots: (label, r, phi_deg) around the hoop, phi = 0 straight out (-y), phi > 0 to the shooter's right? see _spots
SPOT_NOMINAL = [("free-throw area", 4.4, 0.0), ("left wing", 5.3, -40.0), ("right baseline", 5.8, 62.0),
                ("top of the key (three)", 7.45, 6.0), ("left corner (three)", 6.85, -84.0)]

LIMITS = {"angle_deg": (20.0, 80.0), "speed": (3.0, 14.0), "spin_hz": (-5.0, 5.0), "yaw_deg": (-35.0, 35.0)}


def _smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def arm_pose(t: float, yaw: float) -> np.ndarray:
    """Joint targets t s after the throw started (t < 0: resting)."""
    if t <= 0:
        q = Q_REST.copy(); q[0] = 0.0; return q
    for (t0, q0), (t1, q1) in zip(KEYS[:-1], KEYS[1:]):
        if t <= t1:
            u = _smooth((t - t0) / (t1 - t0))
            q = q0 + (q1 - q0) * u
            break
    else:
        q = Q_REST.copy()
    yaw_now = yaw * _smooth(t / 0.25) if t < 1.25 else yaw * (1 - _smooth((t - 1.25) / 0.3))
    q = q.copy(); q[0] = yaw_now
    return q


def make_spots(seed: int = INSTANCE_SEED) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for label, r0, phi0 in SPOT_NOMINAL:
        r = r0 + rng.uniform(-0.25, 0.25)
        phi = math.radians(phi0 + rng.uniform(-4.0, 4.0))
        # phi > 0: to the right of the hoop as seen from the court (towards -x)
        x, y = -r * math.sin(phi), -r * math.cos(phi)
        bearing = math.atan2(-y, -x)                       # direction shooter -> hoop
        off = math.radians(rng.uniform(4.0, 9.0)) * (1 if rng.uniform() < 0.5 else -1)
        out.append({"label": label, "pos": [x, y], "r": r, "heading": bearing + off, "heading_offset": off})
    return out


def shot_plan(n_spots: int) -> list[int]:
    return [i // 2 for i in range(2 * n_spots)]


class Game:
    CAMS = ("shooter_wide", "shooter_zoom", "broadcast", "baseline")

    def __init__(self, seed: int = INSTANCE_SEED, plan: list | None = None):
        cwd = os.getcwd(); os.chdir(SCENE_DIR)
        try:
            self.m = mj.MjModel.from_xml_string(court.build_xml())
        finally:
            os.chdir(cwd)
        self.d = mj.MjData(self.m)
        m = self.m
        self.seed = seed
        self.spots = make_spots(seed)
        self.plan = list(plan) if plan is not None else shot_plan(len(self.spots))   # spot index of every shot
        self.bq = m.joint("ball").qposadr[0]; self.bv = m.joint("ball").dofadr[0]
        self.ball_body = m.body("ball").id
        self.arm_q = [m.joint(f"joint{i + 1}").qposadr[0] for i in range(7)]
        self.arm_v = [m.joint(f"joint{i + 1}").dofadr[0] for i in range(7)]
        self.shooter = m.body("shooter").id
        self.defender_mocap = m.body("defender").mocapid[0]
        self.seat = m.site("ball_seat").id
        self.gid = {m.geom(i).name: i for i in range(m.ngeom) if m.geom(i).name}
        self.rim_ids = {self.gid[f"rim{i}"] for i in range(court.N_RIM)} | {self.gid["bracket"]}
        self.board_id = self.gid["board"]; self.floor_id = self.gid["floor"]; self.ball_gid = self.gid["ball"]
        self.def_ids = {self.gid[n] for n in self.gid if n.startswith("d_")}
        self.k = 0                      # control steps
        self.shot = 0                   # index of the next shot
        self.made = 0
        self.results: list[dict] = []
        self.actions: list[dict] = []
        self.snaps: list[tuple] = []    # (t_local, qpos, mocap_pos, mocap_quat, shooter pos, shooter quat) for rendering
        self.record_snaps = True
        self.frame_cb = None            # called after every control step (video)
        self.done = False
        self.phase_label = ""
        self._renderer = None
        self.load_spot()

    # ------------------------------------------------------------------ world state
    def spot(self) -> dict:
        return self.spots[self.plan[min(self.shot, len(self.plan) - 1)]]

    def attempt_at_spot(self) -> int:
        return 1 + sum(1 for j in range(self.shot) if self.plan[j] == self.plan[self.shot])

    def load_spot(self):
        m, d = self.m, self.d
        sp = self.spot()
        m.body_pos[self.shooter] = [sp["pos"][0], sp["pos"][1], 0.0]
        h = sp["heading"]
        m.body_quat[self.shooter] = [math.cos(h / 2), 0, 0, math.sin(h / 2)]
        self.throw_t = None
        self.yaw_cmd = 0.0
        self.def_dist = min(DEF_START_MAX, DEF_START_FRAC * sp["r"])
        self.t_spot = 0.0
        self.held = True
        d.qvel[:] = 0
        self._set_arm(arm_pose(-1, 0))
        mj.mj_kinematics(m, d)
        self._place_defender()
        self._hold_ball()
        mj.mj_forward(m, d)

    def _set_arm(self, q):
        for a, v, x in zip(self.arm_q, self.arm_v, q):
            self.d.qpos[a] = x; self.d.qvel[v] = 0.0

    def _hold_ball(self):
        d = self.d
        mj.mj_kinematics(self.m, d)
        d.qpos[self.bq:self.bq + 3] = d.site_xpos[self.seat]
        d.qpos[self.bq + 3:self.bq + 7] = [1, 0, 0, 0]
        d.qvel[self.bv:self.bv + 6] = 0

    def _to_hoop_dir(self):
        sp = self.spot()
        v = np.array([court.HOOP[0] - sp["pos"][0], court.HOOP[1] - sp["pos"][1]])
        return v / np.linalg.norm(v)

    def _place_defender(self):
        sp = self.spot(); u = self._to_hoop_dir()
        p = np.array(sp["pos"]) + u * self.def_dist
        z = 0.0
        self.d.mocap_pos[self.defender_mocap] = [p[0], p[1], z]
        a = math.atan2(-u[1], -u[0])          # local +x faces the shooter
        self.d.mocap_quat[self.defender_mocap] = [math.cos(a / 2), 0, 0, math.sin(a / 2)]

    def release_point(self, yaw_rad: float) -> np.ndarray:
        sp = self.spot(); h = sp["heading"] + yaw_rad
        return np.array([sp["pos"][0] + REL_FWD * math.cos(h), sp["pos"][1] + REL_FWD * math.sin(h), REL_H])

    # ------------------------------------------------------------------ stepping
    def control_step(self, mode: str):
        """One control step of the throw and the flight (mode is 'throw')."""
        m, d = self.m, self.d
        self.throw_t += CONTROL_DT
        t = self.throw_t if self.throw_t is not None else -1.0
        self._set_arm(arm_pose(t, self.yaw_cmd))
        self._place_defender()
        if self.held:
            self._hold_ball()
        for _ in range(SUBSTEPS):
            self._set_arm(arm_pose(t, self.yaw_cmd))
            if self.held:
                d.qvel[self.bv:self.bv + 6] = 0
                d.xfrc_applied[self.ball_body] = 0
            else:
                v = d.qvel[self.bv:self.bv + 3]
                R = d.xmat[self.ball_body].reshape(3, 3)
                w = R @ d.qvel[self.bv + 3:self.bv + 6]
                f = -C_D * np.linalg.norm(v) * v + C_M * np.cross(w, v)
                d.xfrc_applied[self.ball_body, :3] = f
                d.xfrc_applied[self.ball_body, 3:] = 0
            mj.mj_step(m, d)
            if not self.held:
                self._scan_contacts()
        self.k += 1
        self.t_spot += CONTROL_DT
        if self.record_snaps:
            self.snaps.append((round(self.t_spot, 4), d.qpos.copy(), d.mocap_pos.copy(), d.mocap_quat.copy(),
                               m.body_pos[self.shooter].copy(), m.body_quat[self.shooter].copy()))
        if self.frame_cb is not None:
            self.frame_cb(self, mode)

    def _scan_contacts(self):
        d = self.d
        for i in range(d.ncon):
            c = d.contact[i]
            g = c.geom2 if c.geom1 == self.ball_gid else c.geom1 if c.geom2 == self.ball_gid else None
            if g is None:
                continue
            if g in self.rim_ids:
                self._touch("rim")
            elif g == self.board_id:
                self._touch("backboard")
            elif g in self.def_ids:
                self._touch("defender")
            elif g == self.floor_id:
                self._touch("floor")

    def _touch(self, what):
        if what not in self.cur["touched"]:
            self.cur["touched"].append(what)
            self.cur["t_touch"][what] = round(self.throw_t - THROW_RELEASE_S, 3)

    # ------------------------------------------------------------------ one shot
    def draw_noise(self, shot_idx: int) -> dict:
        rng = np.random.default_rng([self.seed, 1000 + shot_idx])
        return {"speed_rel": rng.normal(0, NOISE["speed_rel"]), "angle_deg": rng.normal(0, NOISE["angle_deg"]),
                "yaw_deg": rng.normal(0, NOISE["yaw_deg"]), "spin_hz": rng.normal(0, NOISE["spin_hz"])}

    def shoot(self, dec: dict, noise: bool = True) -> dict:
        """dec: angle_deg, speed, spin_hz, yaw_deg. Returns the shot result."""
        assert not self.done
        d = self.d
        self.snaps = []
        self.actions.append({"shot": self.shot, "decision": dict(dec)})
        sp = self.spot()
        rel_steps = int(round(THROW_RELEASE_S / CONTROL_DT))
        self.cur = {"shot": self.shot + 1, "spot": self.plan[self.shot] + 1, "touched": [], "t_touch": {}}
        res = self.cur
        res["defender_distance_m"] = round(self.def_dist, 3)
        self.yaw_cmd = math.radians(float(dec["yaw_deg"]))
        n = self.draw_noise(self.shot) if noise else {k: 0.0 for k in NOISE}
        ang = math.radians(float(dec["angle_deg"]) + n["angle_deg"])
        spd = float(dec["speed"]) * (1 + n["speed_rel"])
        yaw = sp["heading"] + math.radians(float(dec["yaw_deg"]) + n["yaw_deg"])
        spin = float(dec["spin_hz"]) + n["spin_hz"]
        self.throw_t = 0.0
        for _ in range(rel_steps):
            self.control_step("throw")
        # release
        self.held = False
        dirh = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        v = spd * np.array([math.cos(ang) * dirh[0], math.cos(ang) * dirh[1], math.sin(ang)])
        w = 2 * math.pi * spin * np.cross(dirh, [0, 0, 1])     # backspin for spin > 0
        d.qvel[self.bv:self.bv + 3] = v
        d.qvel[self.bv + 3:self.bv + 6] = w                      # body frame = world frame (quat identity)
        res["release_point"] = [round(float(x), 4) for x in d.qpos[self.bq:self.bq + 3]]
        made = False; made_t = None; prev = d.qpos[self.bq:self.bq + 3].copy(); nearest = (1e9, 0)
        max_steps = int(FLIGHT_MAX_S / CONTROL_DT)
        after = None
        hz = court.HOOP[2]
        for i in range(max_steps):
            self.control_step("throw")
            p = d.qpos[self.bq:self.bq + 3]
            rh = math.hypot(p[0] - court.HOOP[0], p[1] - court.HOOP[1])
            dist = math.sqrt(rh ** 2 + (p[2] - hz) ** 2)
            if dist < nearest[0]:
                nearest = (dist, len(self.snaps) - 1)
            if (not made and prev[2] >= hz - 0.10 > p[2] and rh < 0.20 and "floor" not in res["touched"]
                    and "defender" not in res["touched"][:1]):
                made = True; made_t = self.throw_t
            prev = p.copy()
            if after is None and (made or "floor" in res["touched"]):
                after = i + (60 if made else 25)
            if after is not None and i >= after:
                break
        if made:
            res["result"] = "made"
            res["how"] = "swish" if not ({"rim", "backboard"} & set(res["touched"])) else "off the " + "/".join(
                t for t in res["touched"] if t in ("rim", "backboard"))
        elif res["touched"][:1] == ["defender"]:
            res["result"] = "blocked"
        elif {"rim", "backboard"} & set(res["touched"]):
            res["result"] = "rim" if "rim" in res["touched"] else "backboard"
        else:
            res["result"] = "airball"
        res["nearest_snap"] = nearest[1]
        res["nearest_hoop_dist_m"] = round(nearest[0], 3)
        return self._finish(res)

    def _finish(self, res: dict) -> dict:
        if res["result"] == "made":
            self.made += 1
        res["made_total"] = self.made
        self.results.append(res)
        self.shot += 1
        self.last_snaps = self.snaps
        if self.shot >= len(self.plan):
            self.done = True
        else:
            self.load_spot()
        return res

    def extend(self, spot_index: int):
        """One more shot (a duel's tie-break) from spot `spot_index`."""
        self.plan.append(int(spot_index))
        if self.done:
            self.done = False
            self.load_spot()

    def replay(self, actions: list[dict]):
        for a in actions:
            self.shoot(a["decision"])

    def state_sha(self) -> str:
        h = hashlib.sha256()
        h.update(self.d.qpos.tobytes()); h.update(self.d.qvel.tobytes()); h.update(np.int64(self.k).tobytes())
        h.update(repr([(r["result"], r.get("release_point")) for r in self.results]).encode())
        return h.hexdigest()

    # ------------------------------------------------------------------ rendering
    def renderer(self, w=640, h=480):
        if self._renderer is None:
            self._renderer = {}
        if (w, h) not in self._renderer:          # one renderer (GL context) per size, kept for the process
            self._renderer[(w, h)] = mj.Renderer(self.m, height=h, width=w)
        return self._renderer[(w, h)]

    def render_cam(self, cam: str, w=640, h=480) -> np.ndarray:
        r = self.renderer(w, h)
        r.update_scene(self.d, camera=cam)
        return r.render()

    def render_snap(self, snap, cam, w, h) -> np.ndarray:
        m, d = self.m, self.d
        save = (d.qpos.copy(), d.mocap_pos.copy(), d.mocap_quat.copy(), m.body_pos[self.shooter].copy(),
                m.body_quat[self.shooter].copy())
        _, q, mp, mq, bp, bq = snap
        d.qpos[:] = q; d.mocap_pos[:] = mp; d.mocap_quat[:] = mq
        m.body_pos[self.shooter] = bp; m.body_quat[self.shooter] = bq
        mj.mj_forward(m, d)
        img = self.render_cam(cam, w, h)
        d.qpos[:] = save[0]; d.mocap_pos[:] = save[1]; d.mocap_quat[:] = save[2]
        m.body_pos[self.shooter] = save[3]; m.body_quat[self.shooter] = save[4]
        mj.mj_forward(m, d)
        return img


def _release_geometry():
    g = Game.__new__(Game)
    cwd = os.getcwd(); os.chdir(SCENE_DIR)
    try:
        m = mj.MjModel.from_xml_string(court.build_xml())
    finally:
        os.chdir(cwd)
    d = mj.MjData(m)
    m.body_pos[m.body("shooter").id] = [0, 0, 0]
    for i, x in enumerate(Q_REL):
        d.qpos[m.joint(f"joint{i + 1}").qposadr[0]] = x
    mj.mj_kinematics(m, d)
    p = d.site("ball_seat").xpos.copy()
    return float(p[0]), float(p[2])


REL_FWD, REL_H = _release_geometry()
