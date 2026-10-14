"""Badminton's hooks for the post-match evaluator of the low level (skilleval/evaluate.py; sport.toml [modes.low]
evaluator). Headless, in-process, deterministic; the reference player sees the shuttle's true position (at the camera
frames' steps, + 3 mm seeded noise: the screening's "truth perception", docs/screening/badminton.md) instead of its
camera detections, so that the tests measure the `act` implementation, not the vision.

skill_spec()                  what every call of the skill receives as `spec`: the low-level seat's game spec fields
                              joints, limits, toolkit, skill_contract (plugin.low_spec)
platform()                    our implementation (the high level's act: plugin.RacketLayer, bm.Match.plan_racket with its
                              seeded execution scatter), in process: the reference row
api_case(case, skill)         one hidden request: the match brought to the case's start state by replaying the recorded
                              match (its 9-joint targets and tosses, bit for bit: the shuttle in flight, the robot as the
                              match left it), act(t, pos, normal, vel) once at that step (k_eff), then step() every 2
                              control steps until the leg's verdict (at most 1.5 s after the contact step); measured at
                              the contact step k_c = k_eff + round(t / 0.01) (skill_api.ACT)
competition_match(skill, s)   our fixed high-level reference player (builtin_players.Reference with truth perception:
                              its prediction, shot choice, serves and re-planning unchanged) plays a full match against
                              the scripted opponent; each of its acts {t, pos, normal, vel} goes to the skill's act at
                              the act's effect step (the request step + the act lead, as in the game), step() between
                              them; tosses pass through; s = level x 1000 + seed (COMPETITION_SEEDS: L1 and L2, 4 seeds
                              each)

A skill's commands go through the low level's validation exactly as in the game (plugin.LowLayer.parse,
Badminton._take_effect: joint ranges, joint speed limits, the base's speed and acceleration). A call that raises or
overruns its time limit gives no command (skilleval counts it); after a time-out the skill gives no more commands in
that run.

  python3 sports/badminton/lowlevel/evaluator.py record DIR [SEEDS]   (sport image, repo root) our reference player
                                                                     with our implementation: every leg's acts and
                                                                     each match's replay log -> DIR
  python3 sports/badminton/lowlevel/evaluator.py make-cases DIR [OUT] the feasible requests of DIR -> lowlevel/cases/
                                                                     (or OUT)
  python3 sports/badminton/lowlevel/evaluator.py merge-cases OUT DIR...  join per-part make-cases outputs
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
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

import bm as BM  # noqa: E402
import builtin_players as BP  # noqa: E402
import plugin as PL  # noqa: E402
import wc as WC  # noqa: E402
from core.observe import filter_fields  # noqa: E402
from core.sport import FINISHED, UNIT_OVER, MatchConfig, Refused  # noqa: E402
from core.spec import whitelist  # noqa: E402
from skill_api import ACT, CONTRACTS  # noqa: E402,F401
from skilleval import cases as C  # noqa: E402
from skilleval.sandbox import SkillError  # noqa: E402

DT = BM.CONTROL_DT
EVERY = 5               # the reference player is asked every 5 control steps (core/local.py's default, the screening's)
CALL_EVERY = 2          # the skill's step() every 2 control steps (20 ms; as in the skill in the loop)
SLOWDOWN = 20           # the act lead of x20 (plugin.lead_steps: 2 control steps)
WINDOW_S = 0.10         # the head's closest pass to pos is reported within +-0.1 s of the contact step (time_err_s)
AFTER_STEPS = 150       # an API-test case runs to the leg's verdict, at most 1.5 s after the contact step
K_MAX = 80000           # a competition match: 800 s of game time, far beyond any match (40 points at most)
NOISE = 0.003           # the truth perception's noise (m), as the screening's
SEEDS = {1: [41, 42, 43, 44, 45, 46], 2: [41, 42, 43, 44, 45, 46]}  # tools/export_fexam.py: the development seeds (the competition seeds are not exported)
COMPETITION_SEEDS = [lv * 1000 + s for lv in sorted(SEEDS) for s in SEEDS[lv]]
RECORD_SEEDS = COMPETITION_SEEDS  # tools/export_fexam.py: the development seeds only
PUBLIC_SHARE = 3        # of 10: the public practice share (make-cases)
MAX_LEGS = 50           # make-cases: legs per recorded match (long rallies on the slower base give 100-160)
_LOGS: dict = {}        # replay logs by name (carried by the hidden cases themselves: simulator side only)
_DECL: dict = {}


def decl() -> dict:
    if not _DECL:
        import tomllib
        _DECL.update(tomllib.loads((SPORT_DIR / "sport.toml").read_text()))
    return _DECL


# ------------------------------------------------------------------ the match and the reference player
def build(level: int, seed: int, level_name: str = "low"):
    """A fresh in-process match (plugin.Badminton) of `level` and seed, with the given action level's observation."""
    cfg = MatchConfig(sport="badminton", format="match-wallclock", seats=("A",), seed=int(seed), level=int(level),
                      action_level=level_name, slowdown=SLOWDOWN)
    m = PL.SPORT.build(cfg)
    m._ctx()
    return cfg, m


_TRUTH = {"obs": None}
_REAL_DECODE, _REAL_DETECT = BP.decode, BP.detect_views


def _decode(b):
    return b if _TRUTH["obs"] is not None else _REAL_DECODE(b)


def _detect_views(img, cams, times, max_res=0.12):
    if _TRUTH["obs"] is None:
        return _REAL_DETECT(img, cams, times, max_res)
    ts = {round(float(t), 4) for t in times}
    return [(t, X) for t, X in _TRUTH["obs"] if round(float(t), 4) in ts]


BP.decode, BP.detect_views = _decode, _detect_views


class TruthReference(BP.Reference):
    """builtin_players.Reference whose detections are the shuttle's true positions at the camera frames' steps
    (+ NOISE, seeded by the frame's step): the screening's perception-free reference (study.PerfectRef)."""

    def __init__(self, spec, seat, seed=0):
        super().__init__(spec, seat, seed)
        self.seed_ = int(seed)

    def view(self, m, seat, extra=None):
        job, meta = m.camera_job(seat)
        obs = []
        for sn, t in zip(job["snaps"], meta["view_sim_times"]):
            X = np.asarray(sn["sh"], float)
            if X[2] < -0.1:
                continue
            g = np.random.default_rng([self.seed_, ord(seat), int(sn["k"])])
            obs.append((float(t), X + g.normal(0.0, NOISE, 3)))
        st = {"seat": seat, "phase": "running", "world": "running", "step": m.k, "t_sim": m.k * DT, "done": False,
              **m.observe(seat), **(extra or {})}
        return {"state": st, "observation": {**meta, "image_png_b64": "eA==", "_obs": obs}}

    def act(self, view):
        _TRUTH["obs"] = (view.get("observation") or {}).get("_obs")
        try:
            return super().act(view)
        finally:
            _TRUTH["obs"] = None


def reference_player(m, seed: int) -> TruthReference:
    cfg_h = MatchConfig(sport="badminton", format="match-wallclock", seats=("A",), seed=int(seed),
                        level=m.level_, action_level="high", slowdown=SLOWDOWN)
    spec = {"seat": "A", "action_level": "high", **PL.SPORT.spec(cfg_h, "A", m)}
    return TruthReference(spec, "A", seed)


# ------------------------------------------------------------------ the skill's view, spec and commands
_SPEC: dict = {}


def skill_spec() -> dict:
    """The fields of the low level's game spec an `act` skill receives (plugin.low_spec): joints, limits, toolkit (the
    seat's /opt/robot paths: the evaluation container mounts the toolkit there), skill_contract."""
    if not _SPEC:
        _SPEC.update(PL.low_spec(BM.Phys()))
    return copy.deepcopy(_SPEC)


def skill_view(m, seat="A") -> dict:
    """What a skill call sees as `state`: the low level's whitelisted observe state + step (as skilleval/inloop.py)."""
    st, _ = filter_fields(m.observe(seat), whitelist(decl()))
    st["step"] = int(m.k)
    return st


class Platform:
    """Our implementation: the high level's act. api_case / competition_match play it through plugin.RacketLayer (the
    stroke controller, IK, rehearsals, the seeded execution scatter), planned at the act's effect step."""

    PLATFORM = True

    def act(self, t, pos, normal, vel, base=None, *, state=None, spec=None):
        out = {"type": "act", "t": t, "pos": list(pos), "normal": list(normal), "vel": list(vel)}
        if base is not None:
            out["base"] = list(base)
        return out


def platform():
    return Platform()


def _is_platform(skill) -> bool:
    return bool(getattr(getattr(skill, "impl", None), "PLATFORM", False))  # skilleval.sandbox.InProcessSkill only


REQ_KEYS = ("t", "pos", "normal", "vel", "base")


def act_args(req: dict) -> list:
    """The act call's positional arguments: t, pos, normal, vel and, only when the request gives it, base (the
    contract's optional field: where the base stands at contact)."""
    return [req[k] if k == "t" else list(req[k]) for k in REQ_KEYS if req.get(k) is not None]


def _call(skill, fn: str, *args, state: dict):
    """One call of the skill; an error or a time-out gives no command (skilleval counts it)."""
    try:
        return skill.call(fn, *args, state=state)
    except SkillError:
        return None


class _Submit:
    """A skill's command through the low level's parser and the match's checks, as in the game; refusals counted."""

    def __init__(self, m):
        self.m, self.refused, self.low = m, [], PL.LowLayer()

    def __call__(self, cmd):
        if cmd is None:
            return None
        try:
            low = self.low.parse("A", cmd, self.m, {})
        except Refused as e:
            self.refused.append(f"parse: {e}")
            return None
        r = self.m.apply("A", low) or {}
        if "rejected" in r:
            self.refused.append(r["rejected"])
        return r


def _platform_act(m, req):
    """Our implementation at the current step (= the act's effect step): wc.apply_inline = Match.rt_act, what the plan
    worker computes for the effect step and installs there (bit-identical, sim/wc.py)."""
    return WC.apply_inline(m.g, {"type": "act", **req})


# ------------------------------------------------------------------ replaying a recorded match (case start states)
def pack_log(targets, tosses) -> str:
    buf = io.BytesIO()
    np.savez_compressed(buf, targets=np.asarray(targets, np.float64), tosses=np.array(json.dumps(tosses)))
    return base64.b64encode(buf.getvalue()).decode()


def unpack_log(text: str) -> dict:
    z = np.load(io.BytesIO(base64.b64decode(text)), allow_pickle=False)
    return {"targets": z["targets"], "tosses": json.loads(str(z["tosses"]))}


def load_log(name: str) -> dict:
    """The replay log `name`: carried by the first hidden case of that match (field `replay`)."""
    if name not in _LOGS:
        for c in C.load(SPORT_DIR / decl()["modes"]["low"]["cases"]["hidden"]):
            if c.get("replay"):
                _LOGS[c["log"]] = unpack_log(c["replay"])
    return _LOGS[name]


_CURSOR: dict = {}      # log name -> (cfg, m): a replay advanced as far as the last case asked (cases come in order)


def replay_to(level: int, seed: int, log: dict, k: int, name: str | None = None, level_name: str = "low"):
    """A match at control step k of the recorded match: the targets and tosses replayed into the world (the physics,
    the referee and the opponent are deterministic: the same state bit for bit). Replays of one log are continued from
    the furthest point reached (a copy of it is returned: the original stays untouched)."""
    cur = _CURSOR.get(name) if name else None
    if cur is None or cur[1].g.k > k:
        cur = build(level, seed, level_name)
    cfg, m = cur
    T = log["targets"]
    tosses = {int(t["k"]): t for t in log["tosses"]}
    g = m.g
    while g.k < k:
        t = tosses.get(g.k)
        if t is not None:
            g.toss(t["pos"], t["height"])
        g.step(T[g.k])
    if name:
        _CURSOR[name] = (cfg, m)
    cfg2, m2 = build(level, seed, level_name)
    m2.g = WC.restore(WC.snapshot(g), g.s.m)
    return m2


# ------------------------------------------------------------------ the API test
def _racket(m):
    p, n, v = m.g.s.racket_state()
    return p.copy(), n.copy(), v.copy()


def measure(req: dict, track: dict, k_c: int) -> dict:
    """The delivered act. track: {k: (pos, normal, vel)} of the racket head after control step k (around k_c). The
    face normal is compared with either face of the string bed (the contact law reads the face the head moves
    towards)."""
    p_t = np.asarray(req["pos"], float)
    n_t = np.asarray(req["normal"], float)
    n_t = n_t / np.linalg.norm(n_t)
    v_t = np.asarray(req["vel"], float)
    if k_c not in track:
        return {"measured": False}
    p, n, v = track[k_c]
    w = int(round(WINDOW_S / DT))
    ks = [k for k in range(k_c - w, k_c + w + 1) if k in track]
    k_best = min(ks, key=lambda k: float(np.linalg.norm(track[k][0] - p_t)))
    e_v = float(np.linalg.norm(v - v_t))
    return {
        "measured": True,
        "pos_err_m": round(float(np.linalg.norm(p - p_t)), 5),
        "normal_err_deg": round(float(np.degrees(np.arccos(np.clip(abs(float(n @ n_t)), 0.0, 1.0)))), 3),
        "vel_err_mps": round(e_v, 4),
        "vel_norm": round(float(np.linalg.norm(v_t)), 4),
        "vel_err_rel": round(e_v / max(float(np.linalg.norm(v_t)), 1e-6), 4),
        "time_err_s": round((k_best - k_c) * DT, 3),
        "speed_got": round(float(np.linalg.norm(v)), 3),
    }


def api_case(case: dict, skill) -> dict:
    plat = _is_platform(skill)
    m = replay_to(case["level"], case["seed"], load_log(case["log"]), int(case["k"]), case["log"])
    g = m.g
    req = case["request"]
    k_c = g.k + int(round(float(req["t"]) / DT))
    w = int(round(WINDOW_S / DT))
    sub = _Submit(m)
    sc0, r0, p0 = g.s.selfcol["A"].steps_in_contact, len(g.results), len(g.points)
    nr0 = g.s.n_reflex                              # joint-velocity reflexes (bm.REFLEX; reported, not a tolerance)
    if plat:
        _call(skill, "act", *act_args(req), state={})
        info = _platform_act(m, req)
    else:
        info = None
        sub(_call(skill, "act", *act_args(req), state=skill_view(m)))
    has_step = not plat and skill.has("step")
    track, base_at_contact = {}, None
    while True:
        g.rt_advance(1)
        if abs(g.k - k_c) <= w:
            track[g.k] = _racket(m)
        if g.k == k_c:
            base_at_contact = g.s.d.qpos[g.s.qa[:2]].copy()
        if g.k >= k_c + w and (len(g.results) > r0 or len(g.points) > p0):
            break
        if g.done or g.k >= k_c + AFTER_STEPS or len(g.points) > p0:
            break
        if has_step and g.k % CALL_EVERY == 0:
            sub(_call(skill, "step", state=skill_view(m)))
    mm = measure(req, track, k_c)
    if req.get("base") is not None and base_at_contact is not None:   # reported, not a tolerance of the contract
        mm["base_err_m"] = round(float(np.linalg.norm(base_at_contact - np.asarray(req["base"], float))), 4)
    res = g.results[r0] if len(g.results) > r0 else None
    mm.update(
        refused=len(sub.refused),
        refused_kinds=sorted({r.split(":")[0] for r in sub.refused})[:3],
        self_collision_steps=int(g.s.selfcol["A"].steps_in_contact - sc0),
        velocity_reflexes=int(g.s.n_reflex - nr0),
        shuttle_touched=int(any(e["kind"] == "hit" for e in g.s.events)) if len(g.points) == p0 else None,
        shuttle_returned=int(bool(res and res.get("returned"))),
        summary=res["summary"] if res else "not judged",
        level=case["level"],
    )
    if info:
        mm["platform_stroke"] = str(info.get("stroke"))[:120]
    return mm


# ------------------------------------------------------------------ the competition test
def competition_match(skill, seed: int, record: dict | None = None) -> dict:
    """Our reference player against the scripted opponent (level, seed = divmod(seed, 1000)); its acts lowered by the
    skill at their effect steps (the platform: plugin.RacketLayer, as in the game)."""
    level, mseed = divmod(int(seed), 1000)
    plat = _is_platform(skill)
    cfg, m = build(level, mseed, "high" if plat else "low")
    ref = reference_player(m, mseed)
    racket = PL.RacketLayer(PL.lead_steps(SLOWDOWN))
    sub = _Submit(m)
    has_step = not plat and skill.has("step")
    due = None                                      # the skill's act waiting for its effect step: (k0, request)
    n_acts, tosses, refused_acts = 0, [], 0
    g = m.g
    sc0 = g.s.selfcol["A"].steps_in_contact
    while m.phase().state != FINISHED and m.k < K_MAX:
        if m.phase().state == UNIT_OVER:
            m.resume()
            due = None
        if due is not None and due[0] == m.k:
            req = due[1]
            due = None
            sub(_call(skill, "act", *act_args(req), state=skill_view(m)))
        elif has_step and due is None and m.k % CALL_EVERY == 0:
            sub(_call(skill, "step", state=skill_view(m)))
        if m.k % EVERY == 0:
            extra = {"pending_commands": [{"type": "act", "takes_effect_at_step": due[0]}]} if due else None
            a = ref.act(ref.view(m, "A", extra))
            if a:
                try:
                    cmd = racket.parse("A", a, m, {})
                except Refused:
                    refused_acts += 1
                    cmd = None
                if cmd is not None and (cmd["type"] != "act" or plat):
                    if cmd["type"] == "act":
                        n_acts += 1
                        _note(record, g, m.k + racket.lead, cmd, level, mseed)
                    job = racket.snapshot("A", cmd, m, m.k)
                    prepared = racket.prepare(job) if job is not None else None
                    low, _ = racket.lower("A", cmd, prepared, m)
                    r = m.apply("A", low) or {}
                    if cmd["type"] == "toss":
                        tosses.append({"k": int(low["k0"]), "pos": cmd["pos"], "height": cmd["height"]})
                    if "rejected" in r:
                        sub.refused.append(r["rejected"])
                elif cmd is not None:                 # the skill's act: called at its effect step
                    n_acts += 1
                    due = (m.k + racket.lead, {k: cmd[k] for k in REQ_KEYS if k in cmd})
        m.step()
    if record is not None:
        for b in record.values():
            b["result"] = next(({k: r.get(k) for k in ("returned", "summary", "speed_out")}
                                for r in g.results if r.get("leg") == b["leg"]), None)
        record["_log"] = {"targets": g.s.actions(), "tosses": tosses}
    pf, pa = int(g.score[0]), int(g.score[1])
    return {
        "seed": seed,
        "level": level,
        "match_seed": mseed,
        "success": int(bool(g.done and g.winner == 0)),
        "points_for": pf,
        "points_against": pa,
        "point_share": round(pf / max(1, pf + pa), 4),
        "our_legs": int(g.n_our_legs),
        "returns": int(sum(r["returned"] for r in g.results)),
        "acts_requested": n_acts,
        "refused": len(sub.refused) + refused_acts,
        "self_collision_steps": int(g.s.selfcol["A"].steps_in_contact - sc0),
        "velocity_reflexes": int(g.s.n_reflex),
        "k": int(m.k),
    }


def _note(record, g, k_eff, cmd, level, seed):
    """Record an act of our implementation for the cases (not the serve's: its start state is the static ready pose
    and its contact depends on the toss)."""
    if record is None or g.leg["kind"] == "our_serve":
        return
    b = record.setdefault(g.n_our_legs, {"leg": g.n_our_legs, "acts": []})
    if not b["acts"]:
        b.update(k_first=int(k_eff), level=level, seed=seed, kind=g.leg["kind"], launch=int(g.leg["launch"]),
                 n_points=len(g.points))
    b["acts"].append({"k": int(k_eff), "req": {k: cmd[k] for k in REQ_KEYS if k in cmd}})


def competition_summary(rows: list[dict]) -> dict:
    """Wins, point share and returns per opponent level (the report's competition_test)."""
    out = {}
    for lv in sorted({r["level"] for r in rows if "level" in r}):
        rs = [r for r in rows if r.get("level") == lv]
        pf, pa = sum(r.get("points_for", 0) for r in rs), sum(r.get("points_against", 0) for r in rs)
        out[f"L{lv}"] = {
            "won": f"{sum(int(r.get('success', 0)) for r in rs)}/{len(rs)}",
            "points_for": pf, "points_against": pa, "point_share": round(pf / max(1, pf + pa), 4),
            "returns_per_leg": round(sum(r.get("returns", 0) for r in rs) / max(1, sum(r.get("our_legs", 0) for r in rs)), 3),
        }
    pf, pa = sum(r.get("points_for", 0) for r in rows), sum(r.get("points_against", 0) for r in rows)
    out["point_share"] = round(pf / max(1, pf + pa), 4)
    out["refused_total"] = sum(r.get("refused", 0) for r in rows)
    out["self_collision_steps_total"] = sum(r.get("self_collision_steps", 0) for r in rows)
    out["velocity_reflexes_total"] = sum(r.get("velocity_reflexes", 0) for r in rows)
    return out


# ------------------------------------------------------------------ building the cases
def record(out_dir: str, seeds=None) -> None:
    """Our reference player with our implementation on each seed; every leg's acts -> DIR/L*-s*.jsonl, the match's
    replay log -> DIR/L*-s*.npz."""
    from skilleval.sandbox import InProcessSkill

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for seed in seeds or RECORD_SEEDS:
        legs: dict = {}
        r = competition_match(InProcessSkill(platform(), context={"spec": {}}), seed, record=legs)
        lv, s = divmod(seed, 1000)
        log = legs.pop("_log")
        np.savez_compressed(Path(out_dir) / f"L{lv}-s{s}.npz", targets=log["targets"],
                            tosses=np.array(json.dumps(log["tosses"])))
        with open(Path(out_dir) / f"L{lv}-s{s}.jsonl", "w") as f:
            for b in legs.values():
                f.write(json.dumps(b, default=float) + "\n")
        print(json.dumps(r), flush=True)


def _candidate(b: dict) -> list[dict]:
    """A leg's cases: the start state of its FIRST act with the contact state of its LAST act (the same contact step:
    a stroke from the robot as the previous rally left it); and, when the leg had several acts, the start state of its
    LAST act with the same request ("-replan": a new act replaces the stroke under way, from a moving arm, with less
    time)."""
    if not b.get("acts"):
        return []
    last = b["acts"][-1]
    k_c = last["k"] + int(round(float(last["req"]["t"]) / DT))
    out = []
    for k0, tag in ((b["k_first"], ""), (last["k"], "-replan")):
        if tag and (len(b["acts"]) < 2 or k0 == b["k_first"]):
            continue
        req = dict(last["req"], t=round((k_c - k0) * DT, 2))
        full = {**req, "base": req.get("base") or [0.0, -1.6]} if "base" in ACT.args else req
        if ACT.valid_request(full) or req["t"] <= 0.05:
            continue
        out.append({"id": f"L{b['level']}-s{b['seed']}-leg{b['leg']}{tag}", "level": b["level"], "seed": b["seed"],
                    "k": k0, "k_contact": k_c, "request": req, "ball": b["kind"], "n_acts": len(b["acts"]),
                    "leg_no": b["leg"], "n_points": b.get("n_points"), "log": f"L{b['level']}-s{b['seed']}",
                    "reference_result": b.get("result"), "replan": bool(tag)})
    return out


NO_SCATTER = dict(pos=0.0, ang_deg=0.0, speed=0.0)


def _plan(case, log):
    m = replay_to(case["level"], case["seed"], log, case["k"], case["log"], "high")
    g = m.g
    g.RACKET_SCATTER = NO_SCATTER                    # the rehearsal of the request itself
    st = PL.low_state(g)
    st["q_target"] = [float(x) for x in g.s.target]
    info = _platform_act(m, case["request"])
    return st, info


def _feasible(case: dict, log: dict) -> dict:
    """Feasible under the real limits: our implementation, without its execution scatter, plans it and its own
    rehearsal (the robot alone) delivers it with a margin; a request asking for more head speed than the limits
    allow gets its velocity scaled the way our skill scales it."""
    r = case["request"]
    st, info = _plan(case, log)
    if "base" in ACT.args and r.get("base") is None and info.get("base_goal") is not None:
        # every case says where the base stands at contact (the contract's optional base: the platform's stance)
        r["base"] = [round(float(x), 4) for x in info["base_goal"]]
        st, info = _plan(case, log)
    sc = float(info.get("speed_scale") or 1.0)
    if sc > 1.005:
        r["vel"] = [round(float(x) / sc, 4) for x in r["vel"]]
        case["vel_scaled_by"] = round(1.0 / sc, 4)
        st, info = _plan(case, log)
    case["feasible"] = _delivers(info, r)
    case["arm"] = {k: st[k] for k in ("q", "qd", "q_target", "qd_target", "servo")}
    case["platform_plan"] = {k: info.get(k) for k in ("stroke", "base", "ik_residual", "blade_error_m",
                                                      "normal_error_deg", "speed_scale", "n_swing_steps",
                                                      "n_swing_steps_available", "base_goal", "racket_vel_delivered")}
    return case


def _delivers(info: dict, req: dict) -> bool:
    """The platform's own rehearsal of the request (robot only, no execution scatter) meets the contract with a margin:
    IK residual < 2 mm, head within 15 mm, face within 2.5 degrees, velocity within 0.10 m/s + 8 %, the base at its
    stance in time, no self-collision in the rehearsal."""
    v_req = np.asarray(req["vel"], float)
    v_got = np.asarray(info.get("racket_vel_delivered") or [9, 9, 9], float)
    notes = str(info.get("stroke") or "")
    return bool(info.get("n_swing_steps_available", 0) >= 3 and float(info.get("ik_residual", 1)) < BM.IK_OK
                and float(info.get("blade_error_m", 1)) < 0.015 and float(info.get("normal_error_deg", 99)) < 2.5
                and np.linalg.norm(v_got - v_req) <= 0.10 + 0.08 * np.linalg.norm(v_req)
                and str(info.get("base", "ok")) == "ok" and "self-collision" not in notes)


def write_cases(keep: list[dict], out_dir=HERE / "cases", logs: dict | None = None) -> dict:
    """Drop repeated requests; split by a hash of the leg (30 % public; a leg's cases stay on one side);
    hidden.jsonl.gz (with the start states: the replay logs, simulator side only) and public.jsonl (the practice view:
    id, request, the robot's state, our implementation's plan; no world state, no seed)."""
    hidden, public, seen, dup = [], [], set(), 0
    for c in keep:
        key = json.dumps(c["request"], sort_keys=True)
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        leg = f"{c['log']}-leg{c['leg_no']}"            # a leg's cases (first act, re-plan) go to the same side
        if int(hashlib.sha256(leg.encode()).hexdigest()[:8], 16) % 10 < PUBLIC_SHARE:
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


def make_cases(record_dir: str, out_dir=None) -> None:
    """record_dir: one or more recorded matches; out_dir (default lowlevel/cases/): hidden.jsonl.gz, public.jsonl and
    candidates.json. Several out_dirs (e.g. one per match, run in parallel) are joined by merge-cases."""
    rd = Path(record_dir)
    cands = []
    for f in sorted(rd.glob("L*-s*.jsonl")):          # at most MAX_LEGS legs per match, evenly spread over it
        legs = [json.loads(line) for line in open(f)]
        stride = max(1, -(-len(legs) // MAX_LEGS))
        cands += [c for b in legs[::stride] for c in _candidate(b)]
    cands.sort(key=lambda c: (c["log"], c["k"]))
    logs, out = {}, []
    for c in cands:
        if c["log"] not in logs:
            z = np.load(rd / f"{c['log']}.npz", allow_pickle=False)
            logs[c["log"]] = {"targets": z["targets"], "tosses": json.loads(str(z["tosses"]))}
        out.append(_feasible(c, logs[c["log"]]))
        print(c["id"], out[-1]["feasible"], str(out[-1]["platform_plan"]["stroke"])[:80], flush=True)
    keep = [c for c in out if c["feasible"]]
    w = write_cases(keep, out_dir or HERE / "cases", logs=logs)
    (Path(out_dir) if out_dir else rd).mkdir(parents=True, exist_ok=True)
    ((Path(out_dir) if out_dir else rd) / "candidates.json").write_text(json.dumps([{k: c.get(k) for k in ("id", "feasible", "request", "platform_plan",
                                                                            "vel_scaled_by")} for c in out], default=float))
    print(json.dumps({"candidates": len(cands), "feasible": len(keep), **w}))


def merge_cases(out_dir, parts) -> dict:
    """Join make-cases outputs (one directory per part, e.g. per match): hidden cases as they are (each part's replay
    logs ride on its own first hidden case), public cases renumbered, duplicates of a request dropped."""
    hidden, public, seen, cands = [], [], set(), []
    for d in parts:
        d = Path(d)
        for c in C.load(d / "hidden.jsonl.gz"):
            key = json.dumps(c["request"], sort_keys=True)
            if key not in seen:
                seen.add(key)
                hidden.append(c)
        for c in C.load(d / "public.jsonl"):
            key = json.dumps(c["request"], sort_keys=True)
            if key not in seen:
                seen.add(key)
                public.append(dict(c, id=f"public-{len(public):03d}"))
        if (d / "candidates.json").is_file():
            cands += json.loads((d / "candidates.json").read_text())
    C.write(Path(out_dir) / "hidden.jsonl.gz", hidden)
    C.write(Path(out_dir) / "public.jsonl", public)
    return {"hidden": len(hidden), "public": len(public), "candidates": len(cands),
            "feasible": sum(bool(c.get("feasible")) for c in cands)}


if __name__ == "__main__":
    if sys.argv[1:2] == ["record"] and len(sys.argv) > 2:
        record(sys.argv[2], [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else None)
    elif sys.argv[1:2] == ["merge-cases"] and len(sys.argv) > 3:
        print(json.dumps(merge_cases(sys.argv[2], sys.argv[3:])))
    elif sys.argv[1:2] == ["make-cases"] and len(sys.argv) > 2:
        make_cases(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        print(__doc__)
