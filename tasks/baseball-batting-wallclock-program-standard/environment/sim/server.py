"""Wall-clock sim service for baseball-batting-wallclock-program-standard (program play, slowed world).

The world runs ON ITS OWN CLOCK: a background thread steps the pitch clock (bbrt.RT, 100 Hz over the event engine
bb.py) at DT = 10 ms of simulated time per control step and paces every step to DT x SLOWDOWN of wall time
(time.monotonic schedule from an anchor, so there is no drift accumulation). sim time = wall time / SLOWDOWN. Nothing
pauses the world while the model thinks: its thinking, tool calls, network and API latency all take real time. If
the computer cannot keep up, the thread catches up as fast as it can and the lateness is recorded (`sim_lag` in
final.json; revision wallclock-3 reports it without a disqualification threshold, timing_policy=report_only); it
never silently slows the world down.

Per pitch the pitcher winds up (seeded 0.60-1.20 s), releases, the ball flies; the rig executes the current command.
Work inside a running step is kept small (see bbrt.py): a swing start only fixes the executed swing and the bat-ball
contact (~1 ms); the batted ball's flight, the fielders and the count are judged when the pitch is over, after the
world has been frozen for the review, and the next pitch's flight is generated at `ready` (frozen time). Outcomes are
the same functions of the commands as in one bb.Game.decide call.

Frozen (free) time, as in the lock-step protocol: until `game start`, and after each pitch until `game ready WHY PLAN`.

Calls (the server runs by itself; clients pull the state and push commands):
  observe  the newest 2 cameras x 4 frames (30 ms apart) + what was heard, at the sim time of the request. The frames'
           display data are copied under the lock and drawn in a separate render process (render_worker.py; MuJoCo's
           render call holds the GIL). Reports t_sim, step, step_phase and the wall time.
  act      a new swing command (the bat's state when square, T s from when it takes effect). Queued per seat; it takes
           effect at the next control step after it arrives (the current command keeps executing until then); the
           reply comes once it has taken effect and gives the exact step. Program play (RCB_ACT_RULE=program): the
           agent's own program may act without a new model response, while a live metered model session exists; one
           act in flight per seat (think_clock.py). RCB_PLAYER_MODE=oracle (set explicitly by the runner) exempts a
           reference / negative-control run.
  wait DT  block until sim time + DT (convenience).
  ready    after each pitch: the review; the next windup starts only then.
  status / spec.

Seats: every call may name a seat ("seat" in the body or the X-Seat header); this task has one seat, "A".

Configuration (run time): MATCH_LEVEL (1-4), SLOWDOWN, MATCH_SEED (docker-compose maps RCB_LEVEL / RCB_SLOWDOWN /
RCB_SEED onto them).

Evidence (/data): episode.jsonl (every call: wall time, sim step, payload; every applied act with its pitch and
effect step), final.json, trajectory.json (+ trajectory.npz), replay_check.json, replay.mp4. On game end (or SIGUSR1 from the collect
hook) a FRESH PROCESS (replay.py) re-simulates the game from the logged (pitch, step, act) list only; the replayed
bases, decisions and state hash must equal the live ones.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bb  # noqa: E402
import bbrt  # noqa: E402
from think_clock import ThinkClock, read_usage, MeterError  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402
from render_worker import RenderProcess  # noqa: E402
try:                                            # spectator broadcast log (never read back; see broadcast_log.py)
    from broadcast_log import BroadcastLog, pitch_frame, flight  # noqa: E402
except ImportError:  # pragma: no cover
    BroadcastLog = None
BC = None                                       # the spectator broadcast log (set in __main__)


def bc_event(ev: str, **fields) -> None:
    if BC is not None:
        BC.event(ev, R.k, score=[G.bases, THRESHOLD], **fields)

DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(DATA, exist_ok=True)
SLOWDOWN = float(os.environ.get("SLOWDOWN", "20"))       # wall seconds per simulated second
os.environ.setdefault("WALLCLOCK_RULE_WAIT_S", "1.0")    # max real-time wait for the act's model call to be counted
RULE_WAIT_S = float(os.environ["WALLCLOCK_RULE_WAIT_S"])
WAIT_MAX_S = 1.0
LEVEL = int(os.environ.get("MATCH_LEVEL", "1"))
SEED = int(os.environ.get("MATCH_SEED", str(bb.LEVELS[LEVEL]["seed"])))
REVIEW = True                                             # the frozen review between pitches is part of the protocol
REVIEW_MAX_CHARS = 2000
REVIEW_PROMPT = ("Pitch over. Review it: `game ready \"WHY\" \"PLAN\"` (why it went as it did; what you will "
                 "change). The world stays frozen until then.")
REVISION = "wallclock-3"                                  # the engine / replay revision (replay.py)
PLAYER_MODE = os.environ.get("RCB_PLAYER_MODE", "model")
if PLAYER_MODE not in ("model", "oracle"):
    raise ValueError("RCB_PLAYER_MODE must be model or oracle")
if os.environ.get("THINK_DECISION_RULE", "act") != "act":
    raise ValueError("the wall-clock service implements only THINK_DECISION_RULE=act")
MAX_LAG_S = None                                          # wallclock-3: lateness is reported, never disqualifying
TIMING_POLICY = "report_only"
DT = bbrt.DT
PERIOD = DT * SLOWDOWN                                    # wall seconds per control step

COND = threading.Condition(threading.RLock())   # guards R and everything in E / SIM / seats
R = bbrt.RT(LEVEL, SEED)
G = R.G
THRESHOLD = int(G.lv["threshold"])
T0_WALL, T0_MONO = time.time(), time.monotonic()
E = {"started": False, "starting": False, "awaiting_review": False, "readying": False, "reviews": [],
     "final_obs": None, "obs_seq": 0, "act_seq": 0, "finalizing": False, "finalized": False, "reason": None,
     "extra": {}, "last": None, "calls_per_pitch": [], "cur_pitch_calls": 0, "pitches_wall": []}
SIM = {"anchor": None, "lates": [], "step_ms": [], "commit_ms": [], "judge_ms": [], "next_pitch_ms": [],
       "run_wall_s": 0.0, "run_steps": 0, "seg_start": None, "seg_last": None, "segments": 0}


class Seat:
    def __init__(self, name: str, usage_file: str):
        self.name = name
        self.clock = ThinkClock(seconds_per_ktok=0.0, usage_file=usage_file)
        self.decision_lock = threading.Lock()    # pair a consumed model response with its audit receipt
        self.queue: list[dict] = []
        self.news = {"pitches": []}
        self.calls = {"observe": 0, "act": 0, "wait": 0}
        self.refused_not_model = 0
        self.refused_busy = 0                     # acts refused because another act of this seat was in flight
        self.act_in_flight = False
        self.act_owner = None
        self.rule_wait_s: list[float] = []        # real time the call rule waited per accepted act
        self.act_delay_steps: list[int] = []      # control steps between an act's arrival and its effect
        self.act_wall_s: list[float] = []         # wall time from the act's arrival (incl. the rule wait) to its effect
        self.dropped_acts = 0                     # acts whose pitch ended before they took effect
        self.rejected_acts = 0                    # acts that took effect after the swing had started (no change)


SEATS = {"A": Seat("A", os.environ.get("THINK_USAGE_FILE", os.path.join(DATA, "think_usage.json")))}


def source_sha():
    from replay import source_sha as fingerprint
    return fingerprint()


def wall() -> float:
    return round(time.monotonic() - T0_MONO, 4)


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 4), "wall": wall(), "step": R.k, "pitch": R.idx, "t": R.t, **ev},
                           default=float) + "\n")


def passed() -> bool:
    return G.bases >= THRESHOLD


def running() -> bool:
    return E["started"] and not E["awaiting_review"] and E["final_obs"] is None and not G.done


# ---------------------------------------------------------------------------------------------- lag statistics
def _q(a, p):
    return round(float(np.percentile(a, p)), 5)


def lag_stats() -> dict:
    L = np.asarray(SIM["lates"], float)
    S = np.asarray(SIM["step_ms"], float)
    sim_s = SIM["run_steps"] * DT
    run_wall_s = SIM["run_wall_s"]
    if SIM["seg_start"] is not None and SIM.get("seg_last") is not None:
        run_wall_s += SIM["seg_last"] - SIM["seg_start"]
    out = {"slowdown": SLOWDOWN, "period_s": round(PERIOD, 4), "steps": int(SIM["run_steps"]),
           "run_wall_s": round(run_wall_s, 3), "run_sim_s": round(sim_s, 3),
           "effective_slowdown": round(run_wall_s / sim_s, 4) if sim_s > 0 else None,
           "segments": SIM["segments"]}
    if len(L):
        out.update(late_max_s=round(float(L.max()), 4), late_mean_s=round(float(L.mean()), 5),
                   late_p50_s=_q(L, 50), late_p99_s=round(float(np.percentile(L, 99)), 4),
                   late_max_steps=round(float(L.max() / PERIOD), 2),
                   frac_steps_late_over_1_period=round(float(np.mean(L > PERIOD)), 4),
                   frac_steps_late_over_10ms=round(float(np.mean(L > 0.010)), 4))
    if len(S):
        out.update(step_ms_mean=round(float(S.mean()), 3), step_ms_p99=round(float(np.percentile(S, 99)), 3),
                   step_ms_max=round(float(S.max()), 3))
    for name in ("commit_ms", "judge_ms", "next_pitch_ms"):     # judge / next pitch run while the world is frozen
        a = SIM[name]
        if a:
            out[name + "_max"] = round(max(a), 2)
            out[name + "_mean"] = round(float(np.mean(a)), 2)
            out["n_" + name[:-3]] = len(a)
    if SIM.get("slow"):
        out["slowest_steps"] = SIM["slow"]
    return out


def game_state() -> dict:
    """The count, the bases so far: always the state before the current pitch until that pitch is over."""
    return {"plate_appearance": min(G.pa + 1, G.lv["n_pa"]), "n_plate_appearances": G.lv["n_pa"],
            "count": {"balls": G.balls, "strikes": G.strikes}, "bases": G.bases, "threshold": THRESHOLD,
            "pa_results": [r["result"] for r in G.pa_results]}


def write_final() -> None:
    with COND:
        _write_final_locked()


def _write_final_locked() -> None:
    sA = SEATS["A"]
    s = G.summary()
    rw = sA.rule_wait_s
    out = {"level": LEVEL, "seed": G.seed, "bases": G.bases, "threshold": THRESHOLD, "passed": passed(),
           **{k: s[k] for k in ("pa_done", "n_pa", "hits", "walks", "strikeouts", "home_runs", "pitches")},
           "pa_results": s["pa_results"],
           "done": G.done or E["reason"] is not None, "reason": E["reason"], "finalized": E["finalized"],
           "protocol": "wallclock", "slowdown": SLOWDOWN, "control_dt": DT,
           "n_decisions": sA.calls["act"], "n_calls": sum(sA.calls.values()),
           "n_observe": sA.calls["observe"], "n_act": sA.calls["act"], "n_wait": sA.calls["wait"],
           "calls_per_pitch": E["calls_per_pitch"], "refused_not_model": sA.refused_not_model,
           "refused_busy": sA.refused_busy,
           "dropped_acts": sA.dropped_acts, "rejected_acts": sA.rejected_acts,
           "act_rule_wait_s": [round(x, 4) for x in rw],
           "act_rule_wait_max_s": round(max(rw), 4) if rw else 0.0,
           "act_rule_wait_mean_s": round(float(np.mean(rw)), 4) if rw else 0.0,
           "act_delay_steps": sA.act_delay_steps, "act_wall_s": [round(x, 4) for x in sA.act_wall_s],
           "sim_lag": lag_stats(),
           "decision_rule": sA.clock.rule, "rule_wait_cap_s": RULE_WAIT_S,
           "review": REVIEW, "n_reviews": len(E["reviews"]), "reviews": E["reviews"],
           "steps": R.k, "elapsed_s": round(time.time() - T0_WALL, 1), "pitches_wall": E["pitches_wall"],
           "pitch_log": [G.public_rec(r) | {"zone": r["zone"], "crossing": r["crossing"]} for r in G.history]}
    out.update(E["extra"])
    out["graded_ready"] = E["finalized"]
    usage = read_usage(sA.clock.usage_file)
    api = seat_api_errors(sA.clock.usage_file, usage)   # model-API errors: transient vs unrecovered (api_errors.py)
    out.update(revision=REVISION, player_mode=PLAYER_MODE, started=E["started"],
               meter_error=bool(E.get("meter_error") or (PLAYER_MODE == "model" and
                                (not usage.get("epoch") or usage.get("requests", 0) < 1))), max_lag_s=MAX_LAG_S,
               sim_error=E["reason"] == "error",
               proxy_error=api["api_failure"],
               rate_limit_retries=usage.get("rate_limit_retries", 0),
               transient_api_errors=api["transient_api_errors"], unrecovered_api_errors=api["unrecovered_api_errors"],
               timing_policy=TIMING_POLICY, timing_invalid=False)
    replay_ok = bool(out["graded_ready"] and out.get("deterministic") and out.get("replay_bases") == G.bases
                     and out.get("replay_decisions_equal"))
    out["replay_error"] = bool(out.get("finalize_error") or not replay_ok)
    out["valid_trial"] = bool(replay_ok and not any(out[k] for k in
                             ("replay_error", "sim_error", "meter_error", "proxy_error", "timing_invalid")))
    out["technical_failure"] = not out["valid_trial"]
    out["success"] = bool(passed() and out["valid_trial"])
    tmp = os.path.join(DATA, "final.json.tmp")
    with open(tmp, "w") as f:
        json.dump(out, f, default=float)
    os.replace(tmp, os.path.join(DATA, "final.json"))


# ---------------------------------------------------------------------------------------------- end of the game
def finalize() -> None:
    try:
        with COND:
            live_sha = G.state_sha()
            k_end = R.k
            live_bases = G.bases
            decisions = json.loads(json.dumps(G.decisions, default=float))
        dec_sha = hashlib.sha256(json.dumps(decisions, sort_keys=True).encode()).hexdigest()
        tp = os.path.join(DATA, "trajectory.json")
        with open(tp, "w") as f:
            json.dump({"level": LEVEL, "seed": G.seed, "decisions": decisions, "t_decision": bb.T_DECISION,
                       "protocol": "wallclock", "slowdown": SLOWDOWN, "control_dt": DT, "k_end": k_end,
                       "revision": REVISION, "source_sha": source_sha()}, f)
        # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads episode.jsonl; the same commands):
        # one row per command that took effect: pitch index, control step, kind (0 none, 1 swing), T, plane, height,
        # speed, reach
        with open(os.path.join(DATA, "episode.jsonl")) as f:
            applied = [json.loads(line) for line in f if '"act_applied"' in line]
        rows = [[e["pitch_idx"], e["k"], 0 if e["decision"]["type"] == "none" else 1]
                + [float(e["decision"].get(x, 0.0)) for x in ("t", "plane", "height", "speed", "reach")]
                for e in applied if e.get("ev") == "act_applied"]
        np.savez(os.path.join(DATA, "trajectory.npz"), actions=np.asarray(rows, dtype=np.float64).reshape(-1, 8),
                 control_dt=DT, level=LEVEL, seed=G.seed, slowdown=SLOWDOWN, k_end=k_end)
        out_p = os.path.join(DATA, "replay_check.json")
        t0 = time.time()
        subprocess.run([sys.executable, os.path.join(HERE, "replay.py"), os.path.join(DATA, "episode.jsonl"),
                        str(k_end), out_p], check=True, timeout=float(os.environ.get("RCB_REPLAY_TIMEOUT_S", "300")),
                       env=dict(os.environ), stdout=subprocess.DEVNULL,
                       stderr=open(os.path.join(DATA, "replay.log"), "w"))
        with open(out_p) as f:
            rp = json.load(f)
        E["extra"] = {"n_actions": len(decisions), "state_sha": live_sha,
                      "deterministic": rp["state_sha"] == live_sha and rp["steps"] == k_end,
                      "replay_bases": rp["bases"], "replay_steps": rp["steps"], "replay_n_acts": rp["n_acts"],
                      "replay_decisions_equal": rp["decisions_sha"] == dec_sha,
                      "replay_wall_s": round(time.time() - t0, 1), "live_bases": live_bases, "video": "pending"}
        log({"ev": "replay", **E["extra"]})
        with COND:                            # grading readiness is independent of the optional video
            E["finalized"] = True
            _write_final_locked()
        try:
            if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
                tmp = os.path.join(DATA, "replay.tmp.mp4")
                subprocess.run([sys.executable, os.path.join(HERE, "render_video.py"), tp, tmp], check=True,
                               timeout=float(os.environ.get("RCB_VIDEO_TIMEOUT_S", "300")),
                               stdout=subprocess.DEVNULL, stderr=open(os.path.join(DATA, "replay_video.log"), "w"))
                os.replace(tmp, os.path.join(DATA, "replay.mp4"))
                E["extra"]["video"] = True
            else:
                E["extra"]["video"] = False
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            E["extra"]["video"] = False
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["extra"]["finalize_error"] = repr(exc)[:300]
        E["extra"]["video"] = False
    E["finalized"] = True
    write_final()


def end(reason: str) -> None:
    """With COND held."""
    if E["finalizing"]:
        return
    E["reason"] = reason
    E["final_obs"] = {"done": True, "reason": reason, "bases": G.bases, "threshold": THRESHOLD,
                      "passed": passed(), "summary": G.summary(), "note": "the game is over"}
    E["finalizing"] = True
    _close_segment()
    for s in SEATS.values():
        for it in s.queue:
            it["dropped"] = True
        s.queue.clear()
    log({"ev": "end", "reason": reason, "bases": G.bases, "k_end": R.k})
    bc_event("end", reason=reason)
    _write_final_locked()
    COND.notify_all()
    threading.Thread(target=finalize, daemon=True).start()


# ---------------------------------------------------------------------------------------------- the sim thread
def _close_segment() -> None:
    if SIM["seg_start"] is not None and SIM.get("seg_last") is not None:   # anchor -> start of the segment's last step
        SIM["run_wall_s"] += SIM["seg_last"] - SIM["seg_start"]
    SIM["seg_start"] = SIM["seg_last"] = None
    SIM["anchor"] = None


def _apply_queued() -> None:
    """At the start of a control step: every act that arrived since the previous step takes effect, in arrival order
    (a later one replaces an earlier one, exactly as in the replay)."""
    for name, s in SEATS.items():
        for it in s.queue:
            dec = it["dec"]
            t0 = time.monotonic()
            t_eff, k_eff, n_hist = R.t, R.k, len(G.decisions)
            info = bbrt.apply(R, dec)
            if len(G.decisions) > n_hist:
                SIM["commit_ms"].append((time.monotonic() - t0) * 1000.0)
            if not info.get("accepted"):
                s.rejected_acts += 1
            it.update(k_effect=k_eff, t_effect=t_eff, info=info, wall_effect=time.monotonic())
            s.act_delay_steps.append(k_eff - it["k_arrive"])
            s.act_wall_s.append(it["wall_effect"] - it["wall_arrive"])
            log({"ev": "act_applied", "seat": name, "k": k_eff, "pitch_idx": R.idx, "decision": dec,
                 "k_arrive": it["k_arrive"], "apply_ms": round((time.monotonic() - t0) * 1000.0, 3),
                 "act_id": it["act_id"], "model_call": it["model_call"], "obs_ids": it["obs_ids"], "result": info})
            it["done"] = True
        s.queue.clear()


def _pitch_over() -> None:
    """With COND held, right after the step that ended the pitch: freeze the world, then judge the outcome."""
    _close_segment()
    for s in SEATS.values():                   # a command does not carry over to the next pitch
        for it in s.queue:
            it["dropped"] = True
            s.dropped_acts += 1
        s.queue.clear()
    t0 = time.monotonic()
    pr = R.finish()
    SIM["judge_ms"].append((time.monotonic() - t0) * 1000.0)
    pub = G.public_rec(pr)
    d = pub.pop("your_decision")
    pub["your_command"] = ("take (no swing started)" if d["type"] == "take" else
                           {"swing_start_t": round(d["t"], 4), **{k: d[k] for k in ("plane", "height", "speed", "reach")}})
    E["last"] = pub
    for s in SEATS.values():
        s.news["pitches"].append(pub)
    log({"ev": "pitch_over", "result": pub, "zone": pr["zone"], "crossing": pr["crossing"], "bases": G.bases})
    if BC is not None:
        how = f"{pub.get('pitch_type', '')} {pub.get('radar_mps', '')} m/s: {pr['outcome']}" + \
              (f" ({pr['pa_result']})" if pr.get("pa_result") else "")
        BC.event("point", R.k, score=[G.bases, THRESHOLD], winner=None, how=how, n=len(G.history),
                 note=f"PA {min(G.pa + 1, G.lv['n_pa'])}/{G.lv['n_pa']} · count {G.balls}-{G.strikes}",
                 flight=flight(pr.get("batted_samples")))
    E["pitches_wall"].append({"pitch": pr["pitch"] + 1, "wall": wall(), "k": R.k})
    E["calls_per_pitch"].append(E["cur_pitch_calls"]); E["cur_pitch_calls"] = 0
    if G.done:
        end("game_over")
    else:
        E["awaiting_review"] = True
        log({"ev": "pause_for_review", "k": R.k})
        bc_event("pause")


def sim_loop() -> None:
    while True:
        with COND:
            while not running():
                if E["finalizing"]:
                    return
                COND.wait(0.5)
            if SIM["anchor"] is None:       # (re)start of a running segment: a fresh schedule, no catch-up across pauses
                SIM["anchor"] = (time.monotonic(), R.k)
                SIM["seg_start"] = SIM["anchor"][0]
                SIM["segments"] += 1
                log({"ev": "run", "k": R.k})
                bc_event("run")
            a_wall, a_k = SIM["anchor"]
            due = a_wall + (R.k + 1 - a_k) * PERIOD       # state k+1 becomes current at this wall time
        while True:                                       # pace: sleep until the step's slot (short sleeps)
            rem = due - time.monotonic()
            if rem <= 0 or E["final_obs"] is not None:
                break
            time.sleep(min(rem, 0.02))
        with COND:
            if not running():
                continue
            t0 = time.monotonic()
            SIM["lates"].append(max(0.0, t0 - due))
            SIM["seg_last"] = t0
            nq = sum(len(s.queue) for s in SEATS.values())
            n_dec = len(G.decisions)
            _apply_queued()
            t1 = time.monotonic()
            n = R.advance(1)
            if len(G.decisions) > n_dec and nq == 0:     # a planned swing started (or a take) during the step
                SIM["commit_ms"].append((time.monotonic() - t1) * 1000.0)
            t2 = time.monotonic()
            SIM["lates"][-1] = max(SIM["lates"][-1], t2 - due)    # completion lag of this step
            SIM["step_ms"].append((t2 - t0) * 1000.0)
            if len(G.decisions) > n_dec:
                log({"ev": "resolved", "decision": G.decisions[-1], "k": R.k})
            if (t2 - due) > min(PERIOD, 0.01):          # a slow or late step: keep the worst ones for the record
                SIM.setdefault("slow", []).append({"k": R.k, "wake_late_ms": round((t0 - due) * 1000, 1),
                                                   "apply_ms": round((t1 - t0) * 1000, 1),
                                                   "step_ms": round((t2 - t1) * 1000, 1), "acts": nq,
                                                   "completion_late_ms": round((t2 - due) * 1000, 1)})
                SIM["slow"] = sorted(SIM["slow"], key=lambda e: -e["completion_late_ms"])[:8]
            SIM["run_steps"] += n
            pitch_frame(BC, R)
            if R.over:
                _pitch_over()
            if R.over or R.k % 50 == 0:
                _write_final_locked()
            COND.notify_all()


# ---------------------------------------------------------------------------------------------- observations
RENDER = RenderProcess()      # a separate process: MuJoCo rendering holds the GIL

IMAGE_LAYOUT = ("2 rows x 4 columns. Row 1: camera behind home plate (catcher's view) looking at the pitcher; "
                "row 2: camera beside the first part of the pitch path near the pitcher, looking along -x (the "
                "pitcher is on the right, home plate off-image to the left). Columns: four frames 30 ms apart, "
                "oldest left, the latest (the state at the request) right; each tile is stamped with its time since "
                "release (negative: the windup, the ball still in the pitcher's hand). The ball is the small bright "
                "white sphere (7.3 cm). Camera poses and intrinsics: `game spec`.")


def now_state(seat: Seat) -> dict:
    """With COND held. What the batter knows without looking: the game, the time, what it heard, its command."""
    o = {"pitch": R.idx + 1, **game_state()}
    o["step"] = R.k
    o["t_sim"] = round(R.k * DT, 4)
    ph = 0.0
    if running() and SIM["anchor"] is not None:
        a_wall, a_k = SIM["anchor"]
        ph = min(1.0, max(0.0, (time.monotonic() - (a_wall + (R.k - a_k) * PERIOD)) / PERIOD))
    o["step_phase"] = round(ph, 3)
    o["wall_s"] = wall()
    o["world"] = ("running" if running() else ("frozen: review due (game ready)" if E["awaiting_review"] else
                  ("frozen: not started (game start)" if not E["started"] else "over")))
    if R.released():
        o["phase"] = "ball released"
        o["t_since_release"] = R.t
    else:
        o["phase"] = "windup (the ball is still in the pitcher's hand)"
        o["t_since_release"] = None
    if R.over:
        o["phase"] = "pitch over"
    o["heard"] = R.heard()
    o["command"] = R.command()
    if E["last"] is not None:
        o["last_pitch"] = E["last"]
    return o


def observe_payload(seat: Seat) -> dict:
    """Snapshot under the lock, render outside it (the world keeps running while the image is drawn)."""
    with COND:
        o = now_state(seat)
        snaps = R.snapshots()
        E["obs_seq"] += 1
        o["obs_id"] = E["obs_seq"]
        k_snap, wall_snap = R.k, time.monotonic()
    render_start = time.monotonic()
    png = RENDER.render(snaps)
    render_end = time.monotonic()
    o["view_times"] = [s["t"] for s in snaps]
    o["view_steps"] = [s["k"] for s in snaps]
    o["view_sim_times"] = [round(s["k"] * DT, 4) for s in snaps]
    o["image_png_b64"] = base64.b64encode(png).decode()
    o["image_layout"] = IMAGE_LAYOUT
    with COND:
        o["t_sim_at_reply"] = round(R.k * DT, 4)
        o["wall_s_at_reply"] = wall()
        o["obs_age_sim_s"] = round((R.k - k_snap) * DT, 4)
        o["obs_age_wall_s"] = round(time.monotonic() - wall_snap, 6)
        o["render_wall_s"] = round(render_end - render_start, 6)
    return o


def take_news(seat: Seat) -> dict:
    """With COND held: pitches this seat has not been told about yet (repeated until the review is handed in)."""
    out = {}
    ps = seat.news["pitches"]
    if ps:
        out["pitch_over"] = ps[-1]
        if len(ps) > 1:
            out["pitches_over"] = list(ps)
        out.update(game_state())
    if not E["awaiting_review"]:
        seat.news = {"pitches": []}
    if E["awaiting_review"]:
        out["review_prompt"] = REVIEW_PROMPT
    return out


def validate_act(body: dict) -> dict | str:
    if body.get("type") == "none":
        return {"type": "none"}
    try:
        T = float(body["t"]); plane = float(body["plane"]); h = float(body["height"]); sp = float(body["speed"])
        reach = float(body.get("reach", 0.0))
    except Exception:  # noqa: BLE001
        return ("act needs T (s from when it takes effect until the bat is square), plane (deg), height (m), speed "
                "(m/s) and optionally reach (m); or `act none`")
    if not np.all(np.isfinite([T, plane, h, sp, reach])):
        return "all act fields must be finite numbers"
    if not (0.0 < T <= 2.5):
        return "T must be in (0, 2.5] s from when the act takes effect"
    if not (-15.0 <= plane <= 35.0):
        return "PLANE_DEG must be in [-15, 35]"
    if not (0.30 <= h <= 1.40):
        return "HEIGHT must be in [0.30, 1.40] m"
    if not (15.0 <= sp <= 34.0):
        return "SPEED must be in [15, 34] m/s"
    if not (-0.20 <= reach <= 0.20):
        return "REACH must be in [-0.20, 0.20] m"
    return {"type": "swing", "t": T, "plane": plane, "height": h, "speed": sp, "reach": reach}


def gate() -> tuple[int, dict] | None:
    """With COND held: the calls act / wait need a started, running game."""
    if E["final_obs"] is not None:
        return 200, E["final_obs"]
    if E["awaiting_review"]:
        return 409, {"error": "the pitch is over: review it first with `game ready \"WHY\" \"PLAN\"` (the world is "
                     "frozen until then)", "review_prompt": REVIEW_PROMPT, **take_news_peek()}
    if not E["started"]:
        return 409, {"error": "the game has not started: the world is frozen until you run `game start`. Take all the "
                     "time you need first (read, plan, write and test your code): nothing before `game start` counts."}
    return None


def take_news_peek() -> dict:
    return {"pitch_over": E["last"]} if E["last"] is not None else {}


# ---------------------------------------------------------------------------------------------- endpoints
def start(seat: Seat) -> tuple[int, dict]:
    """`game start`: the world starts running now (real time); everything before was free."""
    with COND:
        if E["final_obs"] is not None:
            return 200, E["final_obs"]
        if E["started"] or E["starting"]:
            return 409, {"error": "the game has already started"}
        seat.clock.check_ready()
        E["starting"] = True
    try:
        obs = observe_payload(seat)             # render and settle while the world is still frozen
        seat.clock.settle()
        with COND:
            if E["final_obs"] is not None:
                return 200, E["final_obs"]
            seat.clock.rebase()                 # pre-start responses cannot bank an act
            E["started"] = True
            log({"ev": "game_start", "seat": seat.name, "slowdown": SLOWDOWN})
            bc_event("start")
            obs["world"] = "running"
            COND.notify_all()
    finally:
        with COND:
            E["starting"] = False
    write_final()
    return 200, {"started": True, "note": f"the world runs from now on its own, at 1/{SLOWDOWN:g} of real speed "
                 f"({PERIOD:.3f} s of wall time per 10 ms of game time); it does not wait for you. The pitcher is "
                 f"winding up (0.60-1.20 s of game time)", "observation": obs}


def do_observe(seat: Seat, body: dict) -> tuple[int, dict]:
    with COND:
        if E["final_obs"] is not None:
            return 200, E["final_obs"]
        seat.calls["observe"] += 1; E["cur_pitch_calls"] += 1
        k_req, w_req = R.k, wall()
    o = observe_payload(seat)
    with COND:
        news = take_news(seat)
    log({"ev": "call", "kind": "observe", "seat": seat.name, "k_request": k_req, "wall_request": w_req,
         "obs_id": o["obs_id"], "view_steps": o["view_steps"], "k_reply": int(round(o["t_sim_at_reply"] / DT)),
         "render_wall_s": o["render_wall_s"]})
    return 200, {"call": "observe", "t_sim": round(k_req * DT, 4), "wall_s": w_req, "observation": o, **news}


def do_act(seat: Seat, body: dict) -> tuple[int, dict]:
    try:
        return _do_act(seat, body)
    finally:
        if threading.current_thread() is getattr(seat, 'act_owner', None):
            seat.act_in_flight = False
            seat.act_owner = None


def _do_act(seat: Seat, body: dict) -> tuple[int, dict]:
    entered = getattr(threading.current_thread(), "request_entered", time.monotonic())
    dec = validate_act(body)
    if isinstance(dec, str):
        return 400, {"error": dec}
    with COND:
        g = gate()
        if g:
            return g
        obs_ids = body.get("obs_ids", [])
        if not isinstance(obs_ids, list) or any(type(i) is not int or i < 1 or i > E["obs_seq"] for i in obs_ids):
            return 400, {"error": "obs_ids must list previously issued observation IDs"}
        if seat.queue or seat.act_in_flight:
            seat.refused_busy += 1
            return 429, {"refused": True, "busy": True,
                         "error": "busy: one act at a time; wait for the previous act's reply before sending another"}
        seat.act_in_flight = True
        seat.act_owner = threading.current_thread()
        k_arr, w_arr, pitch_arr = R.k, entered, R.idx
        lock_wait = time.monotonic() - entered
    t_rule = time.monotonic()
    with seat.decision_lock:
        ok = seat.clock.decided_by_model()
        model_call = seat.clock.last_call() if ok else None
    rule_wait = time.monotonic() - t_rule
    with COND:
        if not ok:
            seat.refused_not_model += 1
            log({"ev": "refused_not_model", "seat": seat.name, "kind": "act", "rule_wait_s": round(rule_wait, 4)})
            return 429, {"refused": True, "error": "refused: no live, metered model session (program play needs your "
                         "model session to be running through the metering proxy)"}
        seat.rule_wait_s.append(rule_wait)
        g = gate()
        if g:
            return g
        if R.idx != pitch_arr or R.over:
            seat.dropped_acts += 1
            log({"ev": "act_dropped", "seat": seat.name, "reason": "pitch over during model-call wait",
                 "k_request": k_arr})
            return 409, {"error": "act dropped: its pitch ended while waiting for the model response"}
        E["act_seq"] += 1
        it = {"act_id": E["act_seq"], "model_call": model_call, "obs_ids": obs_ids,
              "dec": dec, "k_arrive": k_arr, "wall_arrive": w_arr, "k_queued": R.k, "done": False, "dropped": False}
        seat.queue.append(it)
        seat.calls["act"] += 1; E["cur_pitch_calls"] += 1
        log({"ev": "call", "kind": "act", "seat": seat.name, "k_request": k_arr, "k_queued": R.k,
             "rule_wait_s": round(rule_wait, 4), "decision": dec, "act_id": it["act_id"],
             "http_arrive_wall": round(entered - T0_MONO, 6), "lock_wait_s": lock_wait,
             "model_call": it["model_call"], "obs_ids": obs_ids})
        COND.wait_for(lambda: it["done"] or it["dropped"] or E["final_obs"] is not None, timeout=60 + 5 * PERIOD)
        out = {"call": "act", "act_id": it["act_id"], "lock_wait_s": round(lock_wait, 6),
               "t_sim_request": round(k_arr * DT, 4), "rule_wait_s": round(rule_wait, 4)}
        if it["done"]:
            out["took_effect"] = {"step": it["k_effect"], "t_sim": round(it["k_effect"] * DT, 4),
                                  "t_since_release": it["t_effect"],
                                  "steps_after_request": it["k_effect"] - k_arr,
                                  "wall_s_after_request": round(it["wall_effect"] - w_arr, 4)}
            out["swing"] = it["info"]
        else:
            if it in seat.queue:
                seat.queue.remove(it)
            if not it["dropped"]:
                seat.dropped_acts += 1
            it["dropped"] = True
            out["note"] = "act dropped before it took effect (the pitch ended, or service timeout)"
        out["now"] = now_state(seat)
        out.update(take_news(seat))
        if E["final_obs"] is not None:
            out.update(E["final_obs"])
    return 200, out


def do_wait(seat: Seat, body: dict) -> tuple[int, dict]:
    try:
        dt = float(body.get("dt"))
    except (TypeError, ValueError):
        return 400, {"error": f"wait needs DT seconds of game time, 0 < DT <= {WAIT_MAX_S}"}
    if not (0.0 < dt <= WAIT_MAX_S):
        return 400, {"error": f"wait needs DT seconds of game time, 0 < DT <= {WAIT_MAX_S}"}
    with COND:
        g = gate()
        if g:
            return g
        seat.calls["wait"] += 1; E["cur_pitch_calls"] += 1
        k0 = R.k
        target = k0 + max(1, int(round(dt / DT)))
        log({"ev": "call", "kind": "wait", "seat": seat.name, "k_request": k0, "dt": dt})
        COND.wait_for(lambda: R.k >= target or not running(), timeout=dt * SLOWDOWN + 60)
        out = {"call": "wait", "t_sim_request": round(k0 * DT, 4), "waited_s": round((R.k - k0) * DT, 4),
               "now": now_state(seat)}
        out.update(take_news(seat))
        if E["final_obs"] is not None:
            out.update(E["final_obs"])
    return 200, out


def do_ready(seat: Seat, body: dict) -> tuple[int, dict]:
    """Between pitches: the review; the world is frozen until then and resumes on a fresh schedule."""
    with COND:
        if E["final_obs"] is not None:
            return 200, E["final_obs"]
        if not E["awaiting_review"] or E["readying"]:
            return 409, {"error": "no review is due now (a review is due after each pitch)"}
        why, plan = body.get("why"), body.get("plan")
        if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
            return 400, {"error": "ready needs two non-empty texts: WHY (why it went as it did) and PLAN (what you "
                         "will change)"}
        if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
            return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
        E["readying"] = True
    try:
        seat.clock.settle()
        with COND:
            if E["final_obs"] is not None:
                return 200, E["final_obs"]
            seat.clock.rebase()                 # review responses cannot bank the next pitch's act
            rv = {"after_pitch": len(G.history), "after_pa": len(G.pa_results), "bases": G.bases,
                  "why": why.strip(), "plan": plan.strip(), "t": round(time.time() - T0_WALL, 1)}
            E["reviews"].append(rv)
            log({"ev": "review", "seat": seat.name, **rv})
            t0 = time.monotonic()
            R.next_pitch()                      # the next pitch's flight (frozen time)
            SIM["next_pitch_ms"].append((time.monotonic() - t0) * 1000.0)
            for s in SEATS.values():
                s.news = {"pitches": []}
            E["awaiting_review"] = False
            out = {"accepted": "review recorded", "now": now_state(seat),
                   "note": "the world is running again: the pitcher is winding up for the next pitch (0.60-1.20 s "
                           f"of game time, {0.6 * SLOWDOWN:.1f}-{1.2 * SLOWDOWN:.1f} s of wall time)"}
            COND.notify_all()
    finally:
        with COND:
            E["readying"] = False
    write_final()
    return 200, out


SPEC = {
    "revision": REVISION, "player_mode": PLAYER_MODE,
    "protocol": "eai-standard-realtime/1.0",
    "simulator": "mujoco 3.3.7 (scene, rig, rendering) + published ball model",
    "robot": "4-parameter kinematic swing rig holding a 0.84 m / 0.90 kg bat",
    "match": {"plate_appearances": G.lv["n_pa"], "opponent_level": LEVEL, "success": f"bases >= {THRESHOLD}",
              "bases": "walk 1, single 1, double 2, home run 4 (no triples)",
              "count": "3 strikes = strikeout, 4 balls = walk, a foul is a strike unless there are already 2 strikes; a plate "
                       "appearance reaching 15 pitches is an out",
              "pa_max_pitches": bb.PA_MAX_PITCHES,
              "pitcher": {"release": list(bb.REL),
                          "arsenal": {n: {"speed_mps": list(G.lv["speeds"][n]), "spin_rad_s": bb.PITCH_TYPES[n]["spin"],
                                          "spin_axis": list(bb.PITCH_TYPES[n]["axis"])} for n in G.lv["speeds"]},
                          "mix": G.lv["mix"]}},
    "timing": {"slowdown": SLOWDOWN, "control_dt_s": DT, "wall_s_per_control_step": PERIOD,
               "wall_s_per_game_s": SLOWDOWN, "wait_max_s": WAIT_MAX_S,
               "windup_s": list(bbrt.WINDUP), "frame_gap_s": bbrt.FRAME_GAP,
               "rule": f"the world runs on its own clock at 1/{SLOWDOWN:g} of real speed (game time = wall time / "
                       f"{SLOWDOWN:g}); it does not wait for your calls or your thinking. An act takes effect at the "
                       "next control step after it arrives; the rig keeps its current command until then",
               "pitch_resolved": f"a planned swing starts at its time; with no swing started {bbrt.TAKE_AFTER} s after "
                                 f"the ball reached the plate, the pitch is taken; the pitch is over {bbrt.END_AFTER} s "
                                 "after the contact or the plate"},
    "decision_rule": ("program play: your own program may observe and act without a new model response; "
                      "one act in flight at a time" if os.environ.get("RCB_ACT_RULE") == "program" else
                      "each act needs a new completed model response containing a game act tool call"),
    "review": "after every pitch (except the game's last) the world stays frozen until `game ready WHY PLAN`; "
              "recorded, not scored",
    "calls": {"observe": "the newest camera frames (2 x 4, 30 ms apart), what you heard, the time, your command",
              "act": "{'type':'swing','t':T_from_effect_until_square,'plane':PLANE_DEG,'height':HEIGHT,'speed':SPEED,"
                     "'reach':REACH} or {'type':'none'}",
              "wait": "{'dt': game seconds}"},
    "seats": sorted(SEATS),
    "swing_rig": {"pivot": f"(-0.66 + REACH, {bb.PIVOT_Y}, HEIGHT) = the knob", "bat_length": bb.L_BAT,
                  "bat_axis": "u(theta) = (cos th, sin th cos a, sin th sin a), a = PLANE_DEG",
                  "profile": "theta = -180 deg at rest; from the swing start constant angular acceleration to omega = "
                             "SPEED/0.69 at -30 deg (time 2*(150 deg in rad)/omega), constant omega to +90 deg, then it "
                             "slows to rest at +150 deg",
                  "time_to_square_s": "(5*pi/3 + pi/6) / omega = 3.9741 / SPEED after the swing start",
                  "command": "act T ...: the bat square T s after the control step at which the act takes effect; the "
                             "swing starts 3.9741 / SPEED s before that (at once if that is already past); once started "
                             "it cannot be changed",
                  "bat_radius_m": "knob 0.025 (s < 0.02), handle 0.0125 (s < 0.40), taper to 0.033 at s = 0.60, barrel 0.033 to the end 0.84",
                  "sweet_spot_s": bb.S_SS, "scatter": dict(bb.SCATTER)},
    "ball": {"mass": bb.M_BALL, "radius": bb.R_BALL, "air_density": bb.RHO, "C_D": bb.CD,
             "C_L": "1.5 S (S < 0.1), 0.09 + 0.6 S; S = R|w|/|v|", "spin_decay_s": bb.SPIN_TAU,
             "bat_ball": {"cor": "max(0.10, 0.50 - 4.0 (s - 0.69)^2)", "bat_cm_s": bb.S_CM, "bat_I_cm": bb.I_CM,
                          "friction": bb.MU}},
    "zone": {"plane": "y = 0", "x": [-bb.ZONE_X, bb.ZONE_X], "z": [bb.ZONE_LO, bb.ZONE_HI],
             "rule": "strike if the ball's centre crosses y = 0 within the zone grown by the ball radius"},
    "field": {"foul_lines_deg": 45, "first_base_xy": [round(v, 2) for v in bb.B1], "fence_m": bb.FENCE_R, "fence_height_m": bb.FENCE_H,
              "fielders": {f[0]: {"xy": [round(v, 2) for v in bb.FIELDER_POS[f[0]]], "r0": f[3], "v_run": f[4],
                                  "t_react": f[5]} for f in bb.FIELDERS},
              "catch_height_m": bb.REACH_H, "runner_to_first_s": bb.RUNNER_TO_1B, "throw_mps": bb.THROW_V},
    "cameras": bb.cam_info(),
    "image": "2 rows (catcher, side) x 4 columns (the newest frames, 30 ms apart, oldest left); tile 480 x 360; "
             "pinhole, image right = forward x up",
    "world": "home plate centre = origin, +y to the pitcher / centre field, +x to first base, z up; ground z = 0",
}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, obj: dict) -> None:
        b = json.dumps(obj, default=float).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def _seat(self, body: dict):
        name = str(body.get("seat") or self.headers.get("X-Seat") or "A")
        return SEATS.get(name)

    def do_GET(self):
        if self.path == "/spec":
            return self._send(200, SPEC)
        if self.path == "/status":
            with COND:
                s = SEATS["A"]
                return self._send(200, {**game_state(), "pitch": R.idx + 1, "calls": s.calls,
                                        "t_sim": round(R.k * DT, 4), "step": R.k, "wall_s": wall(),
                                        "t_since_release": R.t if R.released() else None,
                                        "slowdown": SLOWDOWN, "running": running(),
                                        "awaiting_review": E["awaiting_review"], "started": E["started"],
                                        "done": E["final_obs"] is not None, "reason": E["reason"],
                                        "last_pitch": E["last"]})
        return self._send(404, {"error": "no such endpoint (GET /spec /status; POST /start /observe /act /wait /ready)"})

    def do_POST(self):
        threading.current_thread().request_entered = time.monotonic()
        kind = self.path.strip("/")
        if kind not in ("observe", "act", "wait", "ready", "start"):
            return self._send(404, {"error": "no such endpoint"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:  # noqa: BLE001
            return self._send(400, {"error": "invalid JSON"})
        if not isinstance(body, dict):
            return self._send(400, {"error": "JSON body must be an object"})
        seat = self._seat(body)
        if seat is None:
            return self._send(400, {"error": f"unknown seat; seats: {sorted(SEATS)}"})
        if E["final_obs"] is not None:
            return self._send(200, E["final_obs"])
        try:
            fn = {"start": lambda: start(seat), "observe": lambda: do_observe(seat, body),
                  "act": lambda: do_act(seat, body), "wait": lambda: do_wait(seat, body),
                  "ready": lambda: do_ready(seat, body)}[kind]
            code, obj = fn()
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            if isinstance(exc, MeterError):
                E["meter_error"] = True
            log({"ev": "error", "error": repr(exc)})
            with COND:
                end("error")
            return self._send(500, {"error": "simulator error", "detail": repr(exc)[:200]})
        return self._send(code, obj)


def on_usr1(*_):
    def run():
        with COND:
            end("timeout")
    threading.Thread(target=run, daemon=True).start()


def guarded_sim_loop():
    try:
        sim_loop()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        log({"ev": "error", "where": "sim thread", "error": repr(exc)})
        with COND:
            end("error")


if __name__ == "__main__":
    signal.signal(signal.SIGUSR1, on_usr1)
    open(os.path.join(DATA, "think_calls.jsonl"), "a").close()   # exists (maybe empty) for artifact collection
    log({"ev": "start", "level": LEVEL, "seed": G.seed, "protocol": "wallclock", "slowdown": SLOWDOWN,
         "control_dt": DT, "period_s": PERIOD, "decision_rule": SEATS["A"].clock.rule, "rule_wait_cap_s": RULE_WAIT_S,
         "revision": REVISION, "player_mode": PLAYER_MODE, "max_lag_s": MAX_LAG_S, "timing_policy": TIMING_POLICY, "threshold": THRESHOLD,
         "source_sha": source_sha()})
    if BroadcastLog is not None:
        BC = BroadcastLog(every=2, sport="baseball", mode="single", slowdown=SLOWDOWN, dt=DT, level=LEVEL, seed=SEED,
                          threshold=THRESHOLD, n_pa=G.lv["n_pa"], players={"A": "you"})
        with COND:
            pitch_frame(BC, R)                  # the scene before the first pitch
    write_final()
    threading.Thread(target=guarded_sim_loop, daemon=True).start()
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    print(f"baseball service ready (wall clock, slowdown x{SLOWDOWN:g})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()
