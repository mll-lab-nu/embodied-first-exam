"""tabletennis_g1's built-in players (core/client.py plays them over HTTP, core/local.py in-process; the same action
interface as a model's program): camera images, the replies and /spec only; no simulator import, no ball state.

  OpenReference  the Engineer track's oracle (sport.toml [modes.low] oracle_class): our reference program. It perceives
                 the ball from the camera images (the table-tennis family's camera-only reference: detection,
                 triangulation, flight fit; the G1 preview's contact choice, HITTER's blade velocity, the G1 serve
                 repertoire) and drives every joint of its G1 itself with our learned whole-body striker
                 (solution/skill/striker.py + g1tt_striker.npz, the task's reference library = lowlevel/reference):
                 the striker maps the robot's own state (joints, pelvis IMU, the pelvis's pose) and a racket command
                 to 29 joint targets at 50 Hz. Live (a wall clock) it runs its control loop in a thread of its own
                 (wait / act calls, one joints act every 20 ms of game time) and its planning in another, so that
                 its main loop observes every control step (the every-step camera: one frame per observation, the
                 frames gathered by their steps); in-process (core/local.py: no wall clock) every call of act() is
                 one control cycle and plans at once (deterministic).
  Stand          stands still: holds the ready pose with one joints command (no walking service), never serves (three
                 undue-delay faults lose it the match)
  Idle           never acts
numpy + Pillow only (+ the reference library): this file is also the task's oracle (solution/)."""
from __future__ import annotations

import base64
import collections
import importlib.util
import io
import json
import math
import os
import sys
import threading
import time

import numpy as np
from PIL import Image

# ------------------------------------------------------------------------------------------------ the reference library
def _libdir() -> str:
    """Our reference library: a task's solution/skill/, or lowlevel/reference/ in the sport (the simulator, the repo)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, "skill"), os.path.join(here, "lowlevel", "reference")):
        if os.path.isfile(os.path.join(d, "ttplan.py")):
            return d
    raise FileNotFoundError("ttplan.py: neither solution/skill nor lowlevel/reference")


LIB = _libdir()


def _load(name):
    """A module of the reference library, loaded from its file (a fresh module)."""
    spec = importlib.util.spec_from_file_location(f"g1tt_ref_{name}", os.path.join(LIB, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TP = _load("ttplan")
SK = _load("striker")
CL = _load("control_loop")
CAP = _load("capability")
RP = _load("rallyplan")
BALL_R, E_PADDLE, G, KD, OFFSET, SERVE_LATE = TP.BALL_R, TP.E_PADDLE, TP.G, TP.KD, TP.OFFSET, TP.SERVE_LATE
fit_flight, paddle_for, predict_contact, rollout, solve_out = (TP.fit_flight, TP.paddle_for, TP.predict_contact,
                                                               TP.rollout, TP.solve_out)
TILE_W, TILE_H = 480, 360

TABLE_X, TABLE_Y = 0.7625, 1.37
NET_Z = 0.1525


# ------------------------------------------------------------------------------------------------ cameras
class Cam:
    def __init__(self, c: dict):
        self.pos = np.array(c["position"], float)
        self.fw = np.array(c["forward"], float); self.fw /= np.linalg.norm(self.fw)
        self.up = np.array(c["up"], float); self.up /= np.linalg.norm(self.up)
        self.rt = np.cross(self.fw, self.up)
        self.f = float(c.get("focal_px", 434.6))
        pp = c.get("principal_point_px", [240, 180])
        self.cx, self.cy = float(pp[0]), float(pp[1])

    def project(self, X):
        d = np.asarray(X, float) - self.pos
        z = d @ self.fw
        return self.cx + self.f * (d @ self.rt) / z, self.cy - self.f * (d @ self.up) / z

    def ray(self, u, v):
        d = self.fw + ((u - self.cx) / self.f) * self.rt - ((v - self.cy) / self.f) * self.up
        return self.pos, d / np.linalg.norm(d)


def triangulate(rays):
    """Least-squares point closest to all rays; (point, rms distance to the rays)."""
    A = np.zeros((3, 3)); b = np.zeros(3)
    for o, d in rays:
        P = np.eye(3) - np.outer(d, d)
        A += P; b += P @ o
    X = np.linalg.solve(A, b)
    res = [np.linalg.norm((np.eye(3) - np.outer(d, d)) @ (X - o)) for o, d in rays]
    return X, float(np.sqrt(np.mean(np.square(res))))


# ------------------------------------------------------------------------------------------------ detection
def decode(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


def ball_mask(t: np.ndarray) -> np.ndarray:
    r = t[..., 0].astype(np.int16); g = t[..., 1].astype(np.int16); b = t[..., 2].astype(np.int16)
    return (r > 70) & (b * 8 < r) & (g * 100 > 58 * r) & (g * 100 < 82 * r)


def detect_tile(t: np.ndarray):
    """(u, v) of the ball's centroid in a tile, or None."""
    m = ball_mask(t)
    m[:16, :70] = False                      # the time stamp
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return None
    if len(xs) > 400:                        # far too many: not a ball
        return None
    mx, my = np.median(xs), np.median(ys)
    sel = (np.abs(xs - mx) <= 8) & (np.abs(ys - my) <= 8)
    if sel.sum() == 0:
        return None
    w = t[ys[sel], xs[sel], 0].astype(float)
    # +0.5: pixel i covers [i, i + 1) in the pinhole model
    return float(np.average(xs[sel], weights=w)) + 0.5, float(np.average(ys[sel], weights=w)) + 0.5


def tile_at(img: np.ndarray, n_cams: int, i: int, j: int) -> np.ndarray:
    """Camera i's tile of frame j: the request grid (a row per camera, a column per frame) or the every-step camera's
    row (each frame's cameras side by side)."""
    if img.shape[0] >= n_cams * TILE_H:
        r, c = i, j
    else:
        r, c = 0, j * n_cams + i
    return img[r * TILE_H:(r + 1) * TILE_H, c * TILE_W:(c + 1) * TILE_W]


def detect_views(img: np.ndarray, cams: list[Cam], times: list[float], max_res: float = 0.03):
    """Per frame time: the triangulated ball centre (or nothing). img: any number of frames (times), each with every
    camera (tile_at: 2 rows x the frames, or 1 row of frames x cameras)."""
    out = []
    for j, tt in enumerate(times):
        rays = []
        for i, c in enumerate(cams):
            tile = tile_at(img, len(cams), i, j)
            uv = detect_tile(tile)
            if uv is not None:
                rays.append(c.ray(*uv))
        if len(rays) == 2:
            X, res = triangulate(rays)
            if res < max_res and -0.2 < X[2] < 2.0 and abs(X[1]) < 3.0:
                out.append((float(tt), X))
    return out


# ------------------------------------------------------------------------------------------------ the player
DT = 0.01


class Player:
    """Keeps the frames of the current incoming ball, predicts the contact, decides when to (re-)act.

    update(obs, img, k_req): one observation (its `view_times`, `heard`, `t_since_played`, `step`, `point`, `ball`).
    decide(k_now): an act dict {"t", "pos", "normal", "vel"} (T from the step k_now) or None.
    """

    def __init__(self, cams, aim_y=0.85, aim_x=0.45, vys=(5.0, 4.6, 4.2, 3.8, 3.4, 3.0), vp_max=1.4, tangential=True,
                 verbose=False):
        self.cams = cams
        self.aim_y, self.aim_x, self.vys, self.vp_max, self.tangential = aim_y, aim_x, tuple(vys), vp_max, tangential
        self.verbose = verbose
        self.leg = None
        self.log = []
        self.lock = threading.Lock()           # a leg's frames: gathered by update, read by a planning thread (live)

    def _new_leg(self, key, obs):
        self.leg = {"key": key, "frames": {}, "heard": [], "acts": [], "launch": key[2], "kind": obs.get("ball"),
                    "opp_x": None, "done": False, "pred": None}

    def update(self, obs: dict, img, k_req: int):
        launch = int(round(k_req - float(obs["t_since_played"]) / DT))
        key = (obs.get("point"), obs.get("ball"), launch)
        if self.leg is None or self.leg["key"] != key:
            self._new_leg(key, obs)
        L = self.leg
        L["heard"] = obs.get("heard") or []
        if any(h["event"] in ("paddle", "robot") for h in L["heard"]):
            L["done"] = True
        if obs.get("ball_state") != "coming to you":
            L["done"] = True
        if img is not None and not L["done"]:
            # frame times on this ball's clock from the absolute frame steps (a tile's own stamp is relative to the
            # ball that was current when the frame was taken: right after the opponent's hit, older tiles show our
            # outgoing ball with that ball's clock)
            if obs.get("view_steps") is not None:
                times = [round((k - L["launch"]) * DT, 3) for k in obs["view_steps"]]
            else:
                times = obs["view_times"]
            found = detect_views(img, self.cams, times)
            with self.lock:
                for t, X in found:
                    if t > 0.005:
                        L["frames"][round(t, 3)] = X
        return L

    def _bounce_t(self, which):
        ev = {"opp": "bounce on the opponent's half", "own": "bounce on your half"}[which]
        ts = [h["t"] for h in self.leg["heard"] if h["event"] == ev]
        return ts[0] if ts else None

    def predict(self):
        L = self.leg
        F = sorted(L["frames"].items())
        t_own = self._bounce_t("own")
        if L["kind"] == "serve":
            t_opp = self._bounce_t("opp")
            if t_opp is None:                    # anticipation: the service's flight before its first bounce, rolled
                A = [(t, X) for t, X in F if t > 0.005]        # out over both bounces (a rough contact estimate)
                fa = fit_flight(A) if len(A) >= 3 else None
                if fa is None:
                    return None
                pc = predict_contact(fa[0], fa[1], fa[2], fa[3], need_bounce=True, late=SERVE_LATE)
                return None if pc is None else pc + ("early", len(A))
            start = t_opp + 0.005
        else:
            start = 0.0
        A = [(t, X) for t, X in F if start < t and (t_own is None or t < t_own - 0.003)]
        fa = fit_flight(A, fit_accel=True) if len(A) >= 3 else None
        if t_own is not None:
            B = [(t, X) for t, X in F if t > t_own + 0.003]
            if len(B) >= 3:
                fb = fit_flight(B, a_fixed=None if fa is None else fa[3])
                pc = predict_contact(fb[0], fb[1], fb[2], fb[3], need_bounce=False, late=L["kind"] == "serve" and SERVE_LATE)
                if pc is not None:
                    return pc + ("post", len(B))
        if fa is None:
            return None
        pc = predict_contact(fa[0], fa[1], fa[2], fa[3], need_bounce=t_own is None, late=L["kind"] == "serve" and SERVE_LATE)
        if pc is None:
            return None
        return pc + ("pre", len(A))

    def opp_x(self):
        """Where the opponent is: for a return, where it hit the ball (the first frames of this ball); at a serve it
        stands at the centre."""
        L = self.leg
        if L["kind"] == "serve" or not L["frames"]:
            return 0.0
        t, X = min(L["frames"].items())
        return float(X[0]) if t < 0.2 else 0.0

    def stroke(self, p_hit, v_in, vp_max=None):
        """Aim away from the opponent; among outgoing speeds (vy = 5.0 ... 3.8 m/s) take the fastest whose paddle
        speed the arm can deliver (about VP_MAX m/s at the usual contact poses, from the `act` replies)."""
        ox = self.opp_x()
        side = -1.0 if ox > 0.05 else (1.0 if ox < -0.05 else (-1.0 if p_hit[0] > 0 else 1.0))
        aim = np.array([side * self.aim_x, self.aim_y])
        best = None
        cap = self.vp_max if vp_max is None else vp_max
        L = self.leg
        last = L["acts"][-1] if (L and L["acts"]) else None
        vys = self.vys
        if last is not None and last.get("vy") is not None and last.get("side") == side:
            vys = (last["vy"],) + tuple(v for v in self.vys if v != last["vy"])   # keep this ball's stroke (no flips)
            cap = cap * 1.1
        for vy in vys:
            v_out, ok = solve_out(p_hit, aim, vy)
            if not ok:
                continue
            p_c, n, v_p = paddle_for(p_hit, v_in, v_out, self.tangential)
            sp = float(np.linalg.norm(v_p))
            if sp <= cap:
                self._chosen = (vy, side)
                return p_c, n, v_p, aim
            if best is None or sp < best[0]:
                best = (sp, p_c, n, v_p)
        if best is None:
            v_out, _ = solve_out(p_hit, aim, self.vys[-1])
            p_c, n, v_p = paddle_for(p_hit, v_in, v_out, self.tangential)
            return p_c, n, v_p, aim
        return best[1], best[2], best[3], aim

    def decide(self, k_now_fn):
        """k_now_fn(): the current game time in (fractional) control steps, as well as the client can tell; called
        again after the stroke is computed, so T counts from when the act will reach the service."""
        L = self.leg
        if L is None or L["done"]:
            return None
        pr = self.predict()
        if pr is None:
            return None
        tc, p, v, phase, nfr = pr
        L["pred"] = pr
        t_now = (k_now_fn() - L["launch"]) * DT
        lead = tc - t_now
        if lead < 0.04:
            return None
        last = L["acts"][-1] if L["acts"] else None
        cap_changed = last is not None and last.get("vp_cap") != L.get("vp_cap")
        if last is not None and not cap_changed:
            dp = float(np.linalg.norm(p - last["p_hit"]))
            dtc = abs(tc - last["tc"])
            new_phase = (phase == "post" and last["phase"] == "pre") or (phase != "early" and last["phase"] == "early")
            if not new_phase and dp < 0.012 and dtc < 0.006:
                return None
            if lead < 0.07 and dp < 0.03 and not new_phase:
                return None
        self._chosen = (None, None)
        p_c, n, v_p, aim = self.stroke(p, v, L.get("vp_cap", self.vp_max))
        k_eff = math.floor(k_now_fn())           # the act applies at the start of the step after the current state
        T = tc - (k_eff - L["launch"]) * DT
        if T <= 0.02:
            return None
        act = {"t": round(float(T), 4), "pos": [round(float(x), 4) for x in p_c],
               "normal": [round(float(x), 4) for x in n], "vel": [round(float(x), 3) for x in v_p]}
        L["acts"].append({"tc": tc, "p_hit": p.copy(), "phase": phase, "k_eff": k_eff, "act": act, "nfr": nfr,
                          "aim": aim.tolist(), "vp": float(np.linalg.norm(v_p)), "vp_cap": L.get("vp_cap"),
                          "vy": self._chosen[0], "side": self._chosen[1]})
        return act

    def decide_cap(self, k_now_fn, planner, replan_s=0.04, pick=None, leg=None):
        """The capability-aware decision (lowlevel/reference/rallyplan.py): the arc after the bounce on our half
        from the camera frames (a service: the frames after its bounce on the server's half), corrected by the frames
        after our bounce once it is heard; the option this striker executes best among contacts every 40 ms x the
        aims x outgoing speeds, the aim preferring the side away from the opponent (pick: rallyplan's mixed choice (u, tol),
        None the best). Re-plans at most every
        replan_s s and not within 0.10 s of the contact; within LOCK_S of it a re-plan keeps the contact time. Returns an act dict (T from the step after k_now) or None.
        leg: the ball to plan for (default the current one; a planning thread passes the one it was started for)."""
        L = self.leg if leg is None else leg
        if L is None or L["done"]:
            return None
        serve = L["kind"] == "serve"
        t_opp, t_own = self._bounce_t("opp"), self._bounce_t("own")
        if serve and t_opp is None:
            return None
        t_now = (k_now_fn() - L["launch"]) * DT
        last = L["acts"][-1] if L["acts"] else None
        if last is not None and (t_now - last["t_now"] < replan_s or last["tc"] - t_now < 0.10):
            return None
        with self.lock:
            F = sorted(L["frames"].items())
        arc = RP.predict_arc(F, t_opp if serve else 0.0, t_own, sig_meas=0.012)
        if arc is None:
            return None
        k_eff = math.floor(k_now_fn())
        t_cmd = (k_eff + 1 - L["launch"]) * DT
        if last is not None and last["tc"] - t_now < LOCK_S:
            cands = RP.contact_at(arc, last["tc"])    # the swing is under way: refine the stroke, keep its time
        else:
            cands = RP.arc_contacts(arc, t_min=t_cmd + 0.12, step_s=0.04)
        if not cands:
            return None
        ox = self.opp_x()
        p_mid = cands[len(cands) // 2][1]
        side = -1.0 if ox > 0.05 else (1.0 if ox < -0.05 else (-1.0 if p_mid[0] > 0 else 1.0))
        ch = planner.choose(cands, L.get("t_first", t_cmd), aim_pref=(side * self.aim_x, self.aim_y), pick=pick)
        if ch is None:
            return None
        L.setdefault("t_first", t_cmd)
        T = ch["t"] - t_cmd
        if T <= 0.02:
            return None
        act = {"t": round(float(T), 4), "pos": [round(float(x), 4) for x in ch["p"]],
               "normal": [round(float(x), 4) for x in ch["n"]],
               "vel": [round(float(x) * RP.V_GAIN, 3) for x in ch["v"]]}
        L["acts"].append({"tc": ch["t"], "t_now": t_now, "p_hit": ch["ball"], "phase": "cap", "k_eff": k_eff,
                          "act": act, "nfr": len(F), "aim": ch["aim"], "vp": float(np.linalg.norm(ch["v"])),
                          "est": ch["est"], "vy": ch["vy"], "side": side, "post": arc[3]["n_post"]})
        return act

    def on_act_reply(self, stroke: dict | None):
        """The service says how much of the paddle speed the arm can deliver (speed_scale): cap the next strokes of this
        ball below that, and re-plan."""
        L = self.leg
        if not stroke or L is None or not L["acts"]:
            return
        sc = stroke.get("speed_scale") or 1.0
        if sc > 1.02:
            cap = 0.95 * L["acts"][-1]["vp"] / sc
            L["vp_cap"] = round(min(cap, L.get("vp_cap", self.vp_max)), 3)




# ================================================================================================ the oracle
VP_MAX = 1.4                       # the blade speed the reference asks for at most (returns)
SETTLE_S = 1.8                     # serve: s at the serve stance before the toss
LOCK_S = 0.25                      # re-plans within 0.25 s of the planned contact keep its time (moving a late contact
                                   # 40-80 ms later made the striker meet the service with a still blade: a duel of
                                   # two references lost 11 of 13 service returns that way, 2026-10-26)
REST_LEAD = 0.5                    # the ready command's strike time stays 0.5 s ahead (as the platform opponent's: with
                                   # 0.6 the G1 striker holds the blade 7 cm higher and further forward, where the
                                   # forehand service's ball rests on the toss device: struck before its projection)
POLICY_EVERY = 2                   # the striker at 50 Hz (control steps)
STRIKER = os.path.join(LIB, "g1tt_striker.npz")
CAPNET = os.path.join(LIB, "g1tt_capnet.npz")    # the striker's capability (network form of its table)
MIX = 0.03                         # g1tt-6: a seeded mixed choice among the options scoring within 0.03 of the best,
                                   # and each serve drawn from the seed (as the platform opponent's levels: mix,
                                   # serve_mix). Without them the reference was a deterministic function of the world,
                                   # the duel ignored the seed and the fairness check's 40 duels were 2 matches
SEED_TAG = 41                      # the reference's stream: default_rng([seed, SEED_TAG, seat]) (one per seat)
AIM = (0.40, 0.80)                 # the reference's preferred aim: 0.40 m off the centre line away from the opponent,
                                   # 0.80 m from the net (the capability decides contact and speed)


def _own_state(st: dict) -> dict:
    """The striker's input from the observation (the seat's own frame)."""
    imu, pel = st["imu"], st["pelvis"]
    return {"q": st["q"], "qd": st["qd"], "quat": imu["quat"], "gyro": imu["gyro"], "gravity": imu["gravity"],
            "pelvis": pel["pos"]}


class OpenReference:
    """The oracle (module docstring). Its decisions are the camera-only reference's (a racket command: contact time,
    blade centre, face normal, blade velocity; the stance; the service's toss) and its control is the striker's."""
    every_s = 0.02

    def __init__(self, spec: dict, seat: str, seed: int = 0):
        self.spec, self.seat = spec, seat
        self.period = (spec.get("timing") or {}).get("period_s")      # None in-process (core/local.py)
        if str(spec.get("image_layout") or "").startswith("1 row"):    # the every-step camera: a frame per step, so
            self.every_s = 0.01                                        # observe every step (plugin.IMAGE_LAYOUT)
        self.rng = np.random.default_rng([abs(int(seed)), SEED_TAG, sum(map(ord, str(seat)))])   # serves, mixed choice
        self.P = Player([Cam(c) for c in spec["cameras"]], aim_y=AIM[1], aim_x=AIM[0], vp_max=VP_MAX,
                        tangential=False)
        self.S = SK.Striker(STRIKER)
        self.planner = RP.Planner(CAP.Capability(CAPNET), vp_max=1.8)
        self.home = np.array(spec.get("home", [-0.30, -1.52]), float)
        self.base_rest = self.home.copy()
        self.cmd = None                    # the racket command in force (striker form, game-time t_strike)
        self.strike_k = None
        self.srv = None
        self.n_serves = 0
        self._point = None
        self._move_k = None
        self.loop = None                   # the live control loop (lowlevel/reference/control_loop.py)
        self.plan = None                   # live: the planning thread under way (one at a time)
        self.lock = threading.Lock()       # the racket command (set by the planning, read by the control loop)
        self.now = None
        self.sent = {"joints": 0, "toss": 0, "refused": 0}
        self._joints_k = None              # in-process: the step of the last joints act (the striker at 50 Hz)

    # ---------------------------------------------------------------- the racket command
    def _rest(self, k):
        return self.S.rest_command(self.base_rest, k * DT, lead=REST_LEAD)

    def _command(self, k):
        with self.lock:
            c = self.cmd
            if c is None or (self.strike_k is not None and k > self.strike_k + 2):
                self.cmd, self.strike_k = None, None
                c = self._rest(k)
            return c

    def _joints(self, st) -> dict | None:
        """One control cycle: the striker's 29 targets for the robot's state `st` (an observation)."""
        rob = st.get("robot") or {}
        if rob.get("fallen") or rob.get("reflex"):
            return None
        k = int(st["step"])
        cmd = self._command(k)
        out = self.S(_own_state(st), cmd, k * DT)
        return {"type": "joints", "q": [round(float(x), 5) for x in out["q"]],
                "kp": [round(float(x), 4) for x in out["kp"]], "kd": [round(float(x), 4) for x in out["kd"]]}

    # ---------------------------------------------------------------- decisions (camera-only)
    def _clock(self, st, ob):
        step, t0 = float(st["step"]), time.monotonic()
        if self.period is None:
            return lambda: step
        lag = float(ob.get("render_wall_s") or 0.0) + 0.03
        return lambda: step + (lag + time.monotonic() - t0) / self.period

    def _strike(self, a, k_now):
        """A racket command {t (from the next step), pos, normal, vel} -> the striker's strike command."""
        k_hit = int(math.floor(k_now)) + 1 + int(round(float(a["t"]) / DT))
        p = np.asarray(a["pos"], float)
        pel = np.asarray((self.now or {}).get("pelvis", {}).get("pos", list(self.base_rest) + [0.0])[:2], float)
        cmd = {"base": self.S.base_for(p, pel), "p": p, "v": np.asarray(a["vel"], float),
               "n": np.asarray(a["normal"], float), "t_strike": k_hit * DT, "rest": 0}
        with self.lock:
            self.cmd, self.strike_k = cmd, k_hit
            self.base_rest = np.array([float(np.clip(cmd["base"][0], -0.6, 0.6)), self.home[1]])

    def _plan_live(self, leg, k_now, pick):
        """Live: one decision in the planning thread; applied only if its ball is still the one coming."""
        a = self.P.decide_cap(k_now, self.planner, pick=pick, leg=leg)
        if a and self.P.leg is leg and not leg["done"]:
            self._strike(a, k_now())

    def _serve(self, st, k_now):
        sv = st.get("serve") or {}
        pt = st.get("point")
        if self.srv is None or self.srv["point"] != pt:
            name = TP.SERVE_ORDER[int(self.rng.integers(len(TP.SERVE_ORDER)))]   # the seed's draw (g1tt-6)
            self.srv = {"point": pt, "name": name, "plan": TP.serve_plan(TP.G1_SERVES[name]), "tossed": False,
                        "acted": False}
        S = self.srv
        if S["plan"] is None:
            return None
        toss, a = S["plan"]
        phase = sv.get("phase")
        if phase in ("waiting", "open") and not S["tossed"]:
            if np.max(np.abs(self.base_rest - a["stance"])) > 1e-6:
                self.base_rest = np.asarray(a["stance"], float).copy()
                self._move_k = int(st["step"])
                return None
            pel = np.asarray(st["pelvis"]["pos"][:2], float)
            waited = self._move_k is None or int(st["step"]) - self._move_k >= int(round(SETTLE_S / DT))
            late = sv.get("deadline_in_s") is not None and float(sv["deadline_in_s"]) < 1.5
            if phase == "open" and ((np.max(np.abs(pel - a["stance"])) < 0.06 and waited) or late):
                S["tossed"] = True
                self.n_serves += 1
                return {"type": "toss", **toss}
            return None
        if sv.get("toss") and not S["acted"]:
            S["acted"] = True
            k_hit = int(sv["toss"]["projected_at_step"]) + int(round(a["t_from_projection"] / DT))
            cmd = {"base": np.asarray(a["stance"], float), "p": np.asarray(a["pos"], float),
                   "v": np.asarray(a["vel"], float), "n": np.asarray(a["normal"], float), "t_strike": k_hit * DT,
                   "rest": 0}
            with self.lock:
                self.cmd, self.strike_k = cmd, k_hit
                self.base_rest = self.home.copy()
        return None

    def _decide(self, view):
        """The camera-only decisions of one observation: perhaps a toss to send (the rest is the command in force)."""
        st, ob = view["state"], view.get("observation") or {}
        k_now = self._clock(st, ob)
        if st.get("point") != self._point:                   # each point: home, a fresh striker memory
            self._point = st.get("point")
            with self.lock:
                self.base_rest, self.cmd, self.strike_k = self.home.copy(), None, None
                self.S.reset()
        incoming = st.get("ball_state") == "coming to you" and bool(st.get("ball_in_play"))
        if st.get("you_serve") and (st.get("serve") or {}).get("server") == "you" and not incoming:
            return self._serve(st, k_now)
        img = None
        if incoming and ob.get("image_png_b64"):
            img = decode(base64.b64decode(ob["image_png_b64"]))
        obs = dict(st, view_steps=ob.get("view_steps"), view_times=ob.get("view_times"))
        self.P.update(obs, img, int(st["step"]))
        if incoming:
            if self.period is None:                          # in-process: at once (deterministic)
                a = self.P.decide_cap(k_now, self.planner, pick=(float(self.rng.random()), MIX))
                if a:
                    self._strike(a, k_now())
            elif self.plan is None or not self.plan.is_alive():      # live: in its own thread, so that this loop
                pick = (float(self.rng.random()), MIX)                # keeps observing every step
                self.plan = threading.Thread(target=self._plan_live, args=(self.P.leg, k_now, pick), daemon=True)
                self.plan.start()
        return None

    def act(self, view):
        st = view.get("state") or {}
        if st.get("world") not in (None, "running") or st.get("step") is None:
            return None
        if self.period is not None:                          # live: the control loop runs in its own thread
            if self.loop is None:
                self.loop = CL.ControlLoop(self, POLICY_EVERY)
                self.now = st
                self.loop.start()
            toss = self._decide(view)
            if toss is not None:
                self.loop.send(toss)
            return None
        self.now = st                                        # in-process: one control cycle per call
        toss = self._decide(view)
        if toss is not None:
            return toss
        k = int(st["step"])
        if self._joints_k is not None and 0 <= k - self._joints_k < POLICY_EVERY:
            return None                                      # the striker runs at 50 Hz of game time, as live (a
        self._joints_k = k                                   # loop that observes every step does not run it at 100)
        return self._joints(st)

    def review(self, reply):
        return "reference player: scripted", "reference player: same policy"

    def play(self, c):
        """The live x1 loop (core/client.py main calls it after start; g1tt-10). The control loop: one `observe` every
        2 control steps (20 ms) gives the robot's state (latency 0) and the camera frame (L = 2 steps old); the
        striker's joints act goes out at once from that state. Perception and decisions (image decoding, detection,
        the flight fit, the stroke planning: up to ~130 ms) run in a process of their own (_Perception: a fork of
        this player; the seat's CPUs, never the control loop's interpreter lock), which gets every view and sends
        back the racket command in force whenever it changes and the service's toss. Two calls per 20 ms, within the
        seat's request rate (rate_per_s = 1.25 / 10 ms + 10 = 135). Before: an observe + wait loop every 10 ms and a
        wait + act loop every 20 ms (350 calls a second, paced down to ~5 joints acts a second), then decisions in a
        thread (the striker's acts 2 steps apart only 90 % of the time, the robot falling 2-3 times a match)."""
        period = float(self.period or 0.01)
        gaps, skipped = collections.Counter(), collections.Counter()
        cam = _Perception(self)
        last_k, t_next = None, time.monotonic()

        def apply(msgs):
            toss = None
            for m in msgs:
                if m["point"] != self._point:            # a new point: home, a fresh striker memory (as _decide)
                    self._point = m["point"]
                    self.S.reset()
                self.cmd, self.strike_k, self.base_rest = _cmd_in(m["cmd"]), m["strike_k"], np.asarray(m["base_rest"], float)
                toss = m["toss"] or toss
            return toss
        try:
            while True:
                dt = t_next - time.monotonic()
                if dt > 0:
                    time.sleep(dt)
                view = c.call("observe", {})
                t_obs = time.monotonic()
                now = view.get("now") or {}
                if now.get("done"):
                    stats = cam.close()
                    print(json.dumps({"reference_loop": {"joints_gap_steps": dict(sorted(gaps.items())),
                                                          "no_joints": dict(skipped), "sent": self.sent,
                                                          "camera_process": stats}}), flush=True)
                    return now
                if view.get("http_status") or now.get("world") is None:
                    t_next = t_obs + 0.05
                    continue
                if now.get("world") == "frozen":
                    if now.get("phase") == "review" and not (now.get("ready") or {}).get(c.seat):
                        rv = getattr(self, "review", None)
                        why, plan = rv(now) if rv else ("played as planned", "go on with the same plan")
                        c.call("ready", {"why": why, "plan": plan})
                    t_next = t_obs + 0.1
                    continue
                if now.get("world") != "running" or now.get("step") is None:
                    t_next = t_obs + 0.02
                    continue
                k = int(now["step"])
                self.now = now
                v = {"state": now, "observation": view.get("observation") or {}}
                toss = apply(cam.exchange(v)) if cam.alive else self._decide(v)   # (no process: decide here)
                early = last_k is not None and 0 <= k - last_k < POLICY_EVERY
                if not early:
                    body = self._joints(now)
                    if body is not None:
                        r = c.call("act", body)
                        self.sent["joints"] += 1
                        if r.get("error") or r.get("http_status"):
                            self.sent["refused"] += 1
                        if last_k is not None:
                            gaps[min(k - last_k, 50)] += 1
                        last_k = k
                    else:
                        rob = now.get("robot") or {}
                        skipped["fallen" if rob.get("fallen") else "reflex" if rob.get("reflex") else "other"] += 1
                if toss is not None:
                    c.call("act", toss)
                    self.sent["toss"] += 1
                t_next = t_obs + (0.004 if early else POLICY_EVERY * period - 0.003)   # too early: look again soon
        finally:
            cam.kill()


_CMD_ARRAYS = ("base", "p", "v", "n")


def _cmd_out(cmd):
    return None if cmd is None else {k: (np.asarray(x, float).tolist() if k in _CMD_ARRAYS else x) for k, x in cmd.items()}


def _cmd_in(cmd):
    return None if cmd is None else {k: (np.asarray(x, float) if k in _CMD_ARRAYS else x) for k, x in cmd.items()}


class _Perception:
    """OpenReference.play's perception process: a fork of the player (os.fork, two pipes, one JSON line per message).
    It takes every view in order (_decide: the images, the flight, the planning thread's strokes, the service) and
    sends {point, cmd, strike_k, base_rest, toss} whenever the racket command in force changes (a planning thread's
    stroke as soon as it is planned) or a toss is due; at the end its timing stats."""

    def __init__(self, player):
        r1, w1 = os.pipe()                       # views -> the process
        r2, w2 = os.pipe()                       # commands -> the control loop
        self.pid = os.fork()
        if self.pid == 0:                        # the perception process
            os.close(w1)
            os.close(r2)
            code = 0
            try:
                self._child(player, os.fdopen(r1, "rb"), os.fdopen(w2, "wb"))
            except BaseException as e:           # noqa: BLE001  (its own process: report, end)
                print(f"reference perception process: {e!r}", file=sys.stderr, flush=True)
                code = 1
            os._exit(code)
        os.close(r1)
        os.close(w2)
        self.out = os.fdopen(w1, "wb")
        self.inp = r2
        os.set_blocking(r2, False)
        self.buf, self.alive, self.stats = b"", True, {}
        # the views go out from a thread of their own: a view (its PNG) is larger than the pipe's 64 kB buffer, and a
        # write waits for the process to read it, which must never hold up the control loop (x1g: the robot fell)
        self.outq, self.outcv = collections.deque(), threading.Condition()
        threading.Thread(target=self._writer, daemon=True, name="reference-views").start()

    def _writer(self):
        while True:
            with self.outcv:
                while not self.outq:
                    self.outcv.wait()
                v = self.outq.popleft()
            try:
                self.out.write(json.dumps(v).encode() + b"\n")
                self.out.flush()
            except (OSError, ValueError):
                self.alive = False
                return
            if v is None:
                return

    def _send(self, v):
        with self.outcv:
            self.outq.append(v)
            self.outcv.notify()

    def _child(self, player, inp, out):
        box, cv = collections.deque(), threading.Condition()

        def reader():
            for line in inp:
                v = json.loads(line)
                with cv:
                    box.append(v)
                    cv.notify()
                if v is None:
                    return
            with cv:
                box.append(None)
                cv.notify()
        threading.Thread(target=reader, daemon=True).start()
        last, n, ms = None, 0, []
        while True:
            with cv:
                if not box:
                    cv.wait(0.004)
                v = box.popleft() if box else False
            if v is None:
                break
            toss = None
            if v:
                player.now = v["state"]
                t1 = time.monotonic()
                try:
                    toss = player._decide(v)
                except Exception as e:           # noqa: BLE001  (one bad view: report it, keep perceiving)
                    print(f"reference perception: {e!r}", file=sys.stderr, flush=True)
                ms.append(1000 * (time.monotonic() - t1))
                n += 1
            with player.lock:
                snap = (player._point, id(player.cmd), player.strike_k, id(player.base_rest))
                msg = {"point": player._point, "cmd": _cmd_out(player.cmd), "strike_k": player.strike_k,
                       "base_rest": np.asarray(player.base_rest, float).tolist(), "toss": toss}
            if toss is not None or snap != last:
                out.write(json.dumps(msg).encode() + b"\n")
                out.flush()
                last = snap
        q = (lambda f: round(float(np.percentile(ms, f)), 1)) if ms else (lambda f: None)
        out.write(json.dumps({"stats": {"views": n, "decide_ms_p50": q(50), "decide_ms_p99": q(99),
                                        "decide_ms_max": q(100)}}).encode() + b"\n")
        out.flush()

    def _read(self):
        msgs = []
        while True:
            try:
                b = os.read(self.inp, 1 << 16)
            except BlockingIOError:
                break
            if not b:                            # the process has ended
                self.alive = False
                break
            self.buf += b
        *lines, self.buf = self.buf.split(b"\n")
        for line in lines:
            m = json.loads(line)
            if "stats" in m:
                self.stats.update(m["stats"])
            else:
                msgs.append(m)
        return msgs

    def exchange(self, view):
        """Send a view; the messages that arrived since the last call."""
        self._send(view)
        return self._read()

    def close(self):
        self._send(None)
        t_end = time.monotonic() + 2.0
        while time.monotonic() < t_end and not self.stats and self.alive:
            self._read()
            time.sleep(0.01)
        self.kill()
        return self.stats

    def kill(self):
        if self.pid:
            try:
                if os.waitpid(self.pid, os.WNOHANG) == (0, 0):
                    os.kill(self.pid, 9)
                    os.waitpid(self.pid, 0)
            except OSError:
                pass
            self.pid = 0


class Stand:
    """Stands: holds the ready pose with one joints command (then nothing), never serves."""
    def __init__(self, spec: dict, seat: str, seed: int = 0):
        self.done = False
        self.q = list(spec.get("ready_pose") or [])

    def act(self, view):
        if self.done or len(self.q) != 29:
            return None
        self.done = True
        return {"type": "joints", "q": self.q}

    def review(self, reply):
        return "stand: never strikes", "stand"


class Idle:
    def __init__(self, spec: dict, seat: str, seed: int = 0):
        pass

    def act(self, view):
        return None

    def review(self, reply):
        return "idle: never acts", "idle"
