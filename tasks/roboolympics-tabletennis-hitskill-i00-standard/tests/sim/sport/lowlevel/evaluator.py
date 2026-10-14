"""Table tennis' hooks for the post-match evaluator of the low level (skilleval/evaluate.py; sport.toml [modes.low]
evaluator). Headless, in-process, deterministic; the reference player sees the ball's true state (every 20 ms) instead
of the camera detections, so that the tests measure the `hit` implementation, not the vision.

skill_spec()                  what every call of the skill receives as `spec`: the low-level seat's game spec fields
                              kinematics, limits, toolkit, skill_contract
platform()                    our implementation (the high level's act: action_high, match.Match.plan_paddle), in
                              process: the platform row, without the high level's execution scatter (the low level
                              has none; the user's decision of 2026-10-13)
api_case(case, skill)         one hidden request: the match core brought to the case's start state by replaying the
                              recorded match (its 9-joint targets and tosses, bit for bit: the ball in flight, the
                              robot as the match left it), hit(t, pos, normal, vel) once, then step() every 2 control
                              steps until the leg's verdict (at most 1.5 s after the contact step); measured at the
                              contact step k_c = k_eff + round(t / 0.01) (skill_api.HIT)
competition_match(skill, s)   our fixed high-level reference player (builtin_players.Reference: its prediction, shot
                              choice, serves and re-planning unchanged) plays a full match against the scripted
                              opponent; each of its acts {t, pos, normal, vel} goes to the skill's hit, step() between
                              them; tosses pass through; s = level x 1000 + seed (COMPETITION_SEEDS: L1-L4, 4 seeds each)

A skill's commands go through the low level's validation and arm command layer exactly as in the game (in-process: a
command takes effect at the step it is given). A call that raises or overruns its time limit gives no command
(skilleval counts it); after a time-out the skill gives no more commands in that run.

  python3 sports/tabletennis/lowlevel/evaluator.py record DIR       (sport image, repo root) our reference player with
                                                                     our implementation: every ball's acts and each
                                                                     match's replay log -> DIR
  python3 sports/tabletennis/lowlevel/evaluator.py make-cases DIR   the feasible requests of DIR -> lowlevel/cases/
                                                                     (feasible: our implementation's rehearsal meets
                                                                     the contract under the real limits, and in the
                                                                     full simulation without its execution scatter it
                                                                     fulfils the request: _feasible, _platform_exact)
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SPORT_DIR = HERE.parent
for p in (SPORT_DIR, SPORT_DIR / "sim", *(q for q in (SPORT_DIR.parent, SPORT_DIR.parents[1]) if (q / "core").is_dir())):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import action_high  # noqa: E402
import action_low  # noqa: E402
import arm_commands  # noqa: E402
import builtin_players as bp  # noqa: E402
import plugin as tt  # noqa: E402
from skill_api import CONTRACTS, DT, HIT, WINDOW_S  # noqa: E402
from skilleval import cases as C  # noqa: E402
from skilleval.sandbox import SkillError  # noqa: E402

CALL_EVERY = 2  # the reference player and the skill are called every 2 control steps (50 Hz)
AFTER_STEPS = 150  # an API-test case runs to the leg's verdict, at most 1.5 s after the contact step
K_MAX = 60000  # a competition match: 10 minutes of game time, far beyond any match (40 points at most)
SEEDS = {1: [41, 42, 49, 50, 57, 58], 2: [43, 44, 51, 52, 59, 60], 3: [45, 46, 53, 54, 61, 62], 4: [47, 48, 55, 56, 63, 64]}  # tools/export_fexam.py: the development seeds (the competition seeds are not exported)
COMPETITION_SEEDS = [lv * 1000 + s for lv in sorted(SEEDS) for s in SEEDS[lv]]
PUBLIC_SHARE = 3  # of 10: the public practice share (make-cases)
EXACT = dict(pos=0.0, ang_deg=0.0, speed=0.0)  # the platform row's execution scatter (the user's decision of 10-13)
_LOGS: dict = {}  # replay logs by name (carried by the hidden cases themselves: simulator side only)


# ------------------------------------------------------------------ the match core and the views
def core(level: int, seed: int, high: bool):
    """A fresh match core (arm_commands.Core) of `level`, MATCH_SEED = seed, with the high or the low action level."""
    os.environ["MATCH_SEED"] = str(int(seed))
    return arm_commands.Core(level, action_high if high else action_low)


class TruePlayer(bp.Player):
    """builtin_players.Player whose frames are the ball's true positions (state.ball_true) instead of detections."""

    def __init__(self, **kw):
        super().__init__([], **kw)

    def update(self, obs: dict, img, k_req: int):
        L = super().update(obs, None, k_req)
        bt = obs.get("ball_true")
        if bt and not L["done"] and bt["t"] > 0.005:
            L["frames"][round(float(bt["t"]), 3)] = np.asarray(bt["pos"], float)
        return L


class _Reference(bp.Reference):
    """Our fixed high-level reference player (with a skill its `move` of the base - the serve and receive stances,
    before the ball is in play - becomes a low-level slew of the base, the arm holding its target)."""

    skill_mode = False


def reference_player(skill_mode: bool):
    ref = _Reference({"action_level": "high", "cameras": []}, "A")
    ref.P = TruePlayer(vp_max=bp.VP_MAX)
    ref.skill_mode = skill_mode
    return ref


class _Shim:
    def __init__(self, R):
        self.R = R


def observe(R) -> dict:
    """The game's own observation of the match core R (plugin.TTMatch.observe) + step + ball_true."""
    st = tt.TTMatch.observe(_Shim(R), "A")
    if "qd" not in st:  # the high-level core: the low level's robot fields as well
        st.update(action_low.state(R))
    st.update(world="running", step=R.k)
    if R.in_play():
        d = R.s.d
        st["ball_true"] = {"t": R.t_since_launch(), "pos": d.qpos[0:3].tolist(), "vel": d.qvel[0:3].tolist()}
    return st


def skill_view(st: dict) -> dict:
    """What a skill call sees as `state`: the observe state without the reference player's true-state ball."""
    return {k: v for k, v in st.items() if k != "ball_true"}


def paddle(R):
    s = R.s.state()
    return s["paddle_pos"].tolist(), s["paddle_normal"].tolist(), s["paddle_vel"].tolist()


_SPEC: dict = {}


def skill_spec() -> dict:
    """The fields of the low level's game spec a `hit` skill receives: kinematics, limits, toolkit (the seat's
    /opt/robot paths: the evaluation container mounts the toolkit there), skill_contract (with the deliverable)."""
    if not _SPEC:
        import tomllib

        R = core(1, 1, False)
        lo = tomllib.loads((SPORT_DIR / "sport.toml").read_text())["modes"]["low"]
        _SPEC.update(
            kinematics=action_low.kinematics(R.s.m),
            limits=action_low.limits(R.s),
            toolkit=tt.toolkit_spec(),
            skill_contract=HIT.describe(lo["deliverable"]),
        )
    return copy.deepcopy(_SPEC)


class Platform:
    """Our implementation: the high level's act. hit() returns the act; api_case / competition_match apply it with the
    high action level (the stroke planner, IK, rehearsals; without the execution scatter: EXACT)."""

    PLATFORM = True

    def hit(self, t, pos, normal, vel, *, state=None, spec=None):
        return {"type": "act", "t": t, "pos": list(pos), "normal": list(normal), "vel": list(vel)}


def platform():
    return Platform()


def _is_platform(skill) -> bool:
    return bool(getattr(getattr(skill, "impl", None), "PLATFORM", False))  # skilleval.sandbox.InProcessSkill only


def _call(skill, fn: str, *args, state: dict):
    """One call of the skill; an error or a time-out gives no command (skilleval counts it)."""
    try:
        return skill.call(fn, *args, state=state)
    except SkillError:
        return None


class _Submit:
    """A skill's command through the low level's validation and the arm command layer, as in the game; refusals are
    counted. A toss passes to the match (the reference player's service)."""

    def __init__(self, R):
        self.R, self.refused = R, []

    def __call__(self, cmd):
        if not cmd:
            return
        dec = action_low.validate(cmd, self.R) if isinstance(cmd, dict) else "a command is a JSON object"
        if isinstance(dec, str):
            self.refused.append(dec)
            return
        info = self.R.toss(dec["pos"], dec["height"]) if dec["type"] == "toss" else self.R.submit(dec)
        if isinstance(info, dict) and "rejected" in info:
            self.refused.append(info["rejected"])


# ------------------------------------------------------------------ replaying a recorded match (case start states)
def pack_log(targets, tosses) -> str:
    """A match's replay log as text (the 9-joint targets as float64, bit for bit; the tosses)."""
    import base64
    import io
    buf = io.BytesIO()
    np.savez_compressed(buf, targets=np.asarray(targets, np.float64), tosses=np.array(json.dumps(tosses)))
    return base64.b64encode(buf.getvalue()).decode()


def unpack_log(text: str) -> dict:
    import base64
    import io
    z = np.load(io.BytesIO(base64.b64decode(text)), allow_pickle=False)
    return {"targets": z["targets"], "tosses": json.loads(str(z["tosses"]))}


def load_log(name: str) -> dict:
    """The replay log `name`: carried by the first hidden case of that match (field `replay`)."""
    if name not in _LOGS:
        import tomllib
        cs = tomllib.loads((SPORT_DIR / "sport.toml").read_text())["modes"]["low"]["cases"]
        for c in C.load(SPORT_DIR / cs["hidden"]):
            if c.get("replay"):
                _LOGS[c["log"]] = unpack_log(c["replay"])
    return _LOGS[name]


# The scripted opponent's parameters when the API-test cases were recorded (revision wallclock-15, re-screen
# 2026-10-12): a case is a start state, reached by replaying its match against the opponent of that revision, whatever
# the opponent of a later revision is (the competition test plays the current one). The full level, so that a later
# change of any field leaves the cases' start states as recorded.
CASE_LEVELS = {
    1: dict(reaction_s=0.34, chase=0.36, recover=0.30, reach=0.20, max_speed=5.2,
            width=0.06, pace=3.6, spin=4.0, side=0.0, chase_serve=0.65, short_y1=0.62),
    2: dict(reaction_s=0.31, chase=0.40, recover=0.32, reach=0.23, max_speed=5.3,
            width=0.10, pace=3.75, spin=6.0, side=0.0, chase_serve=0.72, short_y1=0.57),
    3: dict(reaction_s=0.27, chase=0.46, recover=0.33, reach=0.27, max_speed=5.4,
            width=0.18, pace=4.1, spin=12.0, side=0.1, chase_serve=0.78, short_y1=0.49),
    4: dict(reaction_s=0.24, chase=0.52, recover=0.36, reach=0.31, max_speed=5.6,
            width=0.26, pace=4.6, spin=25.0, side=0.5, chase_serve=1.00, short_y1=0.45),
}


def replay_to(R, log: dict, k: int) -> None:
    """Advance the fresh core R to control step k with the recorded match's targets and tosses (the physics, the
    referee and the opponent are deterministic: the same state bit for bit), against the opponent the cases were
    recorded with (CASE_LEVELS)."""
    R.lv.update(CASE_LEVELS[int(R.level)])
    T = log["targets"]
    tosses = {int(t["k"]): t for t in log["tosses"]}
    while R.k < k:
        t = tosses.get(R.k)
        if t is not None:
            r = R.toss(t["pos"], t["height"])
            assert "rejected" not in r, r
        R.step(T[R.k])
    R.cmd = None if R.plugin is action_low else R.rest_command()


# ------------------------------------------------------------------ the API test
def measure(req: dict, track: dict, k_c: int) -> dict:
    """The delivered hit. track: {k: (pos, normal, vel)} of the blade after control step k (around k_c)."""
    p_t = np.asarray(req["pos"], float)
    n_t = np.asarray(req["normal"], float)
    n_t = n_t / np.linalg.norm(n_t)
    v_t = np.asarray(req["vel"], float)
    if k_c not in track:
        return {"measured": False}
    p, n, v = (np.asarray(x, float) for x in track[k_c])
    w = int(round(WINDOW_S / DT))
    ks = [k for k in range(k_c - w, k_c + w + 1) if k in track]
    k_best = min(ks, key=lambda k: float(np.linalg.norm(np.asarray(track[k][0]) - p_t)))
    e_v = float(np.linalg.norm(v - v_t))
    return {
        "measured": True,
        "pos_err_m": round(float(np.linalg.norm(p - p_t)), 5),
        "normal_err_deg": round(float(np.degrees(np.arccos(np.clip(n @ n_t, -1.0, 1.0)))), 3),
        "vel_err": round(e_v, 4),
        "vel_err_rel": round(e_v / max(float(np.linalg.norm(v_t)), 1e-6), 4),
        "time_err_s": round((k_best - k_c) * DT, 3),
        "speed_req": round(float(np.linalg.norm(v_t)), 3),
        "speed_got": round(float(np.linalg.norm(v)), 3),
    }


def api_case(case: dict, skill) -> dict:
    plat = _is_platform(skill)
    R = core(case["level"], case["seed"], plat)
    if plat:
        R.PADDLE_SCATTER = EXACT                     # the low level has no execution scatter: neither has its row
    replay_to(R, load_log(case["log"]), int(case["k"]))
    req = case["request"]
    k_c = R.k + int(round(float(req["t"]) / DT))
    w = int(round(WINDOW_S / DT))
    sub = _Submit(R)
    sc0, r0, p0 = R.s.selfcol["A"].events, len(R.results), len(R.points)
    cmd = _call(skill, "hit", req["t"], list(req["pos"]), list(req["normal"]), list(req["vel"]),
                state={} if plat else skill_view(observe(R)))
    if plat:
        R.apply(action_high.validate(cmd, R))
    else:
        sub(cmd)
    has_step = not plat and skill.has("step")
    track, touched, net, table = {}, None, 0, 0
    while True:
        R.rt_advance(1)
        net, table = max(net, int(R.s._robot_net)), max(table, int(R.s._robot_table))
        if abs(R.k - k_c) <= w:
            track[R.k] = paddle(R)
        if touched is None and any(e["kind"] == "paddle" for e in R.s._events):
            touched = R.k
        if R.k >= k_c + w and (len(R.results) > r0 or len(R.points) > p0):
            break
        if R.done or R.k >= k_c + AFTER_STEPS:
            break
        if has_step and R.k % CALL_EVERY == 0:
            sub(_call(skill, "step", state=skill_view(observe(R))))
    m = measure(req, track, k_c)
    res = R.results[r0] if len(R.results) > r0 else None
    m.update(
        refused=len(sub.refused),
        refused_kinds=sorted({r.split(":")[0] for r in sub.refused})[:3],
        robot_net_contact=net,
        robot_table_contact=table,
        self_collision_events=int(R.s.selfcol["A"].events - sc0),
        ball_touched=int(touched is not None),
        ball_returned=int(bool(res and res.get("returned"))),
        ball_speed_out=res.get("speed_out") if res else None,
        summary=res["summary"] if res else "not judged",
        level=case["level"],
    )
    return m


# ------------------------------------------------------------------ the competition test
def competition_match(skill, seed: int, record: dict | None = None) -> dict:
    level, mseed = divmod(int(seed), 1000)
    plat = _is_platform(skill)
    R = core(level, mseed, plat)
    if plat:
        R.PADDLE_SCATTER = EXACT
    ref = reference_player(skill_mode=not plat)
    sub = _Submit(R)
    has_step = not plat and skill.has("step")
    n_hits, tosses = 0, []
    sc0 = R.s.selfcol["A"].events
    while not R.done and R.k < K_MAX:
        if R.k % CALL_EVERY == 0:
            st = observe(R)
            a = ref.act({"state": st, "observation": {}})
            if a and a.get("type") == "toss":
                r = R.toss(a["pos"], a["height"])
                if "rejected" not in r:
                    tosses.append({"k": int(R.k), "pos": a["pos"], "height": a["height"]})
                else:
                    sub.refused.append(r["rejected"])
            elif a and a.get("type") == "move":
                if plat:
                    R.set_base_rest(a["base"])
                else:                                 # the program places the base itself (no ball in play)
                    sub({"type": "slew", "q": [float(x) for x in a["base"]] + [float(x) for x in R.s._target[2:]],
                         "speed": 1.0})
            elif a and a.get("type") == "act":
                n_hits += 1
                req = {k: a[k] for k in ("t", "pos", "normal", "vel")}
                if record is not None and R.leg["kind"] != "our_serve":
                    b = record.setdefault(R.n_our_legs, {"leg": R.n_our_legs, "acts": []})
                    if not b["acts"]:
                        b.update(k_first=R.k, level=level, seed=mseed, kind=R.leg["kind"], launch=R.leg["launch"],
                                 n_points=len(R.points))
                    b["acts"].append({"k": R.k, "req": req})
                if plat:
                    dec = action_high.validate(dict(a), R)
                    if isinstance(dec, str):
                        sub.refused.append(dec)
                    else:
                        _call(skill, "hit", req["t"], req["pos"], req["normal"], req["vel"], state={})
                        R.apply(dec)
                else:
                    sub(_call(skill, "hit", req["t"], req["pos"], req["normal"], req["vel"], state=skill_view(st)))
            elif has_step:
                sub(_call(skill, "step", state=skill_view(st)))
        R.rt_advance(1)
    if record is not None:
        for b in record.values():
            b["result"] = next(({k: r.get(k) for k in ("returned", "summary", "speed_out")}
                                for r in R.results if r.get("leg") == b["leg"]), None)
        record["_log"] = {"targets": R.s.actions(), "tosses": tosses}
    return {
        "seed": seed,
        "level": level,
        "match_seed": mseed,
        "success": int(R.winner == 0),
        "points_for": int(R.score[0]),
        "points_against": int(R.score[1]),
        "our_legs": int(R.n_our_legs),
        "returns": int(sum(r["returned"] for r in R.results)),
        "hits_requested": n_hits,
        "refused": len(sub.refused),
        "net_faults": sum(1 for p in R.points if "net" in (p.get("how") or "") and p.get("winner") != "you"),
        "self_collision_events": int(R.s.selfcol["A"].events - sc0),
        "k": int(R.k),
    }


def competition_summary(rows: list[dict]) -> dict:
    """Wins and returns per opponent level (the report's competition_test)."""
    out = {}
    for lv in sorted({r["level"] for r in rows if "level" in r}):
        rs = [r for r in rows if r.get("level") == lv]
        out[f"L{lv}"] = {
            "won": f"{sum(int(r.get('success', 0)) for r in rs)}/{len(rs)}",
            "points_for": sum(r.get("points_for", 0) for r in rs),
            "points_against": sum(r.get("points_against", 0) for r in rs),
            "returns_per_leg": round(sum(r.get("returns", 0) for r in rs) / max(1, sum(r.get("our_legs", 0) for r in rs)), 3),
        }
    out["refused_total"] = sum(r.get("refused", 0) for r in rows)
    out["self_collision_events_total"] = sum(r.get("self_collision_events", 0) for r in rows)
    return out


# ------------------------------------------------------------------ building the cases
def record(out_dir: str, seeds=None) -> None:
    """Our reference player with our implementation on every competition seed; every ball's acts -> DIR/L*-s*.jsonl,
    the match's replay log -> DIR/L*-s*.npz."""
    from skilleval.sandbox import InProcessSkill

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for seed in seeds or COMPETITION_SEEDS:
        balls: dict = {}
        r = competition_match(InProcessSkill(platform(), context={"spec": {}}), seed, record=balls)
        lv, s = divmod(seed, 1000)
        log = balls.pop("_log")
        np.savez_compressed(Path(out_dir) / f"L{lv}-s{s}.npz", targets=log["targets"],
                            tosses=np.array(json.dumps(log["tosses"])))
        with open(Path(out_dir) / f"L{lv}-s{s}.jsonl", "w") as f:
            for b in balls.values():
                f.write(json.dumps(b) + "\n")
        print(json.dumps({k: r[k] for k in ("seed", "success", "points_for", "points_against")}), flush=True)


def _candidate(b: dict) -> dict | None:
    """A ball's case: the start state of its FIRST act, the contact state of its LAST act (the same contact step)."""
    if not b.get("acts"):
        return None
    k_first, last = b["k_first"], b["acts"][-1]
    k_c = last["k"] + int(round(float(last["req"]["t"]) / DT))
    req = dict(last["req"], t=round((k_c - k_first) * DT, 2))
    if HIT.valid_request(req):
        return None
    return {"id": f"L{b['level']}-s{b['seed']}-leg{b['leg']}", "level": b["level"], "seed": b["seed"], "k": k_first,
            "k_contact": k_c, "request": req, "ball": b["kind"], "n_acts": len(b["acts"]), "leg_no": b["leg"],
            "n_points": b.get("n_points"), "log": f"L{b['level']}-s{b['seed']}",
            "reference_result": b.get("result")}


def _feasible(case: dict, log: dict) -> dict:
    """Feasible under the real limits: our implementation plans it with stroke 'ok'; a request asking for more paddle
    speed than the limits allow gets its velocity scaled the way our skill scales it."""
    R = core(case["level"], case["seed"], True)
    replay_to(R, log, case["k"])
    r = case["request"]
    t_hit = (R.k - R.leg["launch"]) * DT + float(r["t"])
    st = R.s.state()
    R._ik_seed = None
    _, info = R.plan_paddle(t_hit, r["pos"], r["normal"], r["vel"])
    sc = float(info.get("speed_scale") or 1.0)
    if info.get("stroke") != "ok" and sc > 1.0:
        r["vel"] = [round(float(x) / sc, 3) for x in r["vel"]]
        case["vel_scaled_by"] = round(1.0 / sc, 3)
        R = core(case["level"], case["seed"], True)
        replay_to(R, log, case["k"])
        R._ik_seed = None
        _, info = R.plan_paddle(t_hit, r["pos"], r["normal"], r["vel"])
    case["feasible"] = _delivers(info, r)
    case["arm"] = {"q": st["q"].round(6).tolist(), "qd": st["qd"].round(6).tolist(),
                   "q_target": st["q_target"].round(6).tolist(), "qd_target": R._target_vel().round(6).tolist()}
    case["platform_plan"] = {k: info.get(k) for k in ("stroke", "ik_residual", "blade_error_m", "normal_error_deg",
                                                      "speed_scale", "n_swing_steps", "base_goal")}
    return case


def _delivers(info: dict, req: dict) -> bool:
    """The platform's own rehearsal of the request (robot only, no execution scatter) meets the contract with a margin:
    IK residual < 1 mm, blade within 15 mm, face within 2.5 degrees, velocity within 0.10 m/s + 8 %, no table or net
    contact in the rehearsal, the base in time. (The planner's notes "short swing" and a speed limit already met by
    the scaled request are not infeasibility.)"""
    v_req = np.asarray(req["vel"], float)
    v_got = np.asarray(info.get("paddle_vel_delivered") or [9, 9, 9], float)
    return bool(info.get("n_swing_steps_available", 0) >= 1 and float(info.get("ik_residual", 1)) < 1e-3
                and float(info.get("blade_error_m", 1)) < 0.015 and float(info.get("normal_error_deg", 99)) < 2.5
                and np.linalg.norm(v_got - v_req) <= 0.10 + 0.08 * np.linalg.norm(v_req)
                and not info.get("table_contact_in_rehearsal") and str(info.get("base", "ok")) == "ok")


def write_cases(keep: list[dict], out_dir=HERE / "cases", logs: dict | None = None) -> dict:
    """Drop repeated requests; split by a hash of the request (30 % public, so a repeated request can never be both);
    hidden.jsonl.gz (with the start states: the replay logs, simulator side only) and public.jsonl (the practice view:
    id, request, the robot's state, our implementation's plan; no world state, no seed)."""
    hidden, public, seen, dup = [], [], set(), 0
    for c in keep:
        key = json.dumps(c["request"], sort_keys=True)
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        if int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 10 < PUBLIC_SHARE:
            public.append({"id": f"public-{len(public):03d}", "request": c["request"], "state": c["arm"],
                           "reference": c["platform_plan"]})
        else:
            hidden.append(c)
    for name in sorted({c["log"] for c in hidden}) if logs else []:   # each match's replay log rides on its first
        mine = [c for c in hidden if c["log"] == name]                  # hidden case, cut after the last start step
        kmax = max(c["k"] for c in mine)
        lg = logs[name]
        mine[0]["replay"] = pack_log(lg["targets"][:kmax], [t for t in lg["tosses"] if t["k"] < kmax])
    C.write(Path(out_dir) / "hidden.jsonl.gz", hidden)
    C.write(Path(out_dir) / "public.jsonl", public)
    return {"hidden": len(hidden), "public": len(public), "duplicates": dup}


def make_cases(record_dir: str) -> None:
    import shutil

    rd = Path(record_dir)
    cands = [c for f in sorted(rd.glob("L*-s*.jsonl")) for line in open(f) if (c := _candidate(json.loads(line)))]
    logs = {}
    out = []
    for c in cands:
        if c["log"] not in logs:
            z = np.load(rd / f"{c['log']}.npz", allow_pickle=False)
            logs[c["log"]] = {"targets": z["targets"], "tosses": json.loads(str(z["tosses"]))}
        out.append(_feasible(c, logs[c["log"]]))
        print(c["id"], out[-1]["feasible"], out[-1]["platform_plan"]["stroke"], flush=True)
    feas = [c for c in out if c["feasible"]]
    _LOGS.update(logs)
    keep = [c for c in feas if _platform_exact(c)]
    w = write_cases(keep, logs=logs)
    print(json.dumps({"candidates": len(cands), "feasible": len(feas), "platform_exact": len(keep), **w}))


def _platform_exact(case: dict) -> bool:
    """The rev-15 feasibility test in the full simulation: our implementation (the platform's hit, under the joint-
    velocity and collision reflexes; without execution scatter, as in its API-test row) fulfils the request within the
    contract (the API test's own measurement and judgement). A request it cannot deliver exactly under the real limits
    is no case."""
    from skilleval.sandbox import InProcessSkill

    m = api_case(case, InProcessSkill(platform(), context={"spec": skill_spec()}))
    m.update(HIT.judge(m))
    case["platform_exact"] = {k: m.get(k) for k in ("pos_err_m", "normal_err_deg", "vel_err", "time_err_s",
                                                    "robot_table_contact", "success")}
    print(case["id"], "platform_exact", bool(m["success"]), flush=True)
    return bool(m["success"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["record"] and len(sys.argv) > 2:
        record(sys.argv[2], [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else None)
    elif sys.argv[1:2] == ["make-cases"] and len(sys.argv) > 2:
        make_cases(sys.argv[2])
    else:
        print(__doc__)
