"""Wall-clock sim service for tennis-match-wallclock-program-standard (racket-level control, slowed world, program play).

The world runs ON ITS OWN CLOCK: a background thread steps the match at CONTROL_DT = 10 ms of simulated time per
control step and paces every step to CONTROL_DT x SLOWDOWN of wall time (time.monotonic schedule from an anchor, so
there is no drift accumulation). sim time = wall time / SLOWDOWN. Nothing pauses the world while the model thinks:
its thinking, tool calls, network and API latency all take real time. If the computer cannot keep up the thread
catches up as fast as it can and the lateness is recorded (`sim_lag` in final.json); it never silently slows the
world down. Revision wallclock-3: timing is report_only (no lateness cutoff; all lag telemetry is kept).

Frozen (free) time, as in the lock-step protocol: until `game start`, and after each point until `game ready WHY PLAN`.

Heavy computation never runs in the sim thread:
  * an `act`'s stroke plan (IK multi-start, swing search, rehearsals: ~0.15-0.26 s of CPU) is computed in a planner
    PROCESS from a snapshot of the robot taken at the step the act is accepted (k_s); the plan takes effect at the
    fixed step k_e = k_s + LEAD (LEAD = ceil(WALLCLOCK_PLAN_LEAD_S / wall time per step)), for the robot state
    the planner predicts for k_e by running the robot's current command forward (joint targets bit-exact). The
    arm keeps its current command until k_e. Both steps are logged; the replay recomputes the plan in-process from
    the same snapshot, so it is bit-identical;
  * the opponent's return search (~0.05-0.11 s) is started in a second worker process when the opponent reacts to
    our shot, for the ball position at its hit step (predicted exactly with the same integrator), and cached; the
    hit step only selects the candidate our robot can reach (cheap). A cache miss recomputes in-process (same result);
  * all serves are solved before the match starts;
  * the camera images are rendered in a render PROCESS from snapshots (render_worker.py).

Calls (the server runs by itself; clients pull the state and push commands):
  observe  the newest 2 cameras x 4 frames (40 ms apart) + what was heard, at the sim time of the request.
  act      a new racket state at contact (T s from the step the act takes effect; optionally the base position at
           contact), or `none`, or `move` (the base's rest position). Queued per seat, in order. An act takes effect
           LEAD steps after the step it is accepted at; `none` / `move` at the next step (after any act before them).
           The reply comes once the command has taken effect and gives the exact steps. Program play
           (RCB_ACT_RULE=program): the agent's own program may act without a new model response; one act (or move)
           in flight per seat (think_clock.py).
  wait DT  block until sim time + DT (convenience).
  ready    after each point: the review; the world restarts only then.
  start / status / spec.

Evidence (/data): episode.jsonl (every call; every snapshot / applied command with its step), final.json,
trajectory.json, replay_check.json, replay.mp4. On episode end (or SIGUSR1 from the collect hook) a FRESH PROCESS
(replay.py) re-simulates the match from the logged commands only; the score, the final state hash and every joint
target must equal the live ones.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tn as match  # noqa: E402
from think_clock import ThinkClock, read_usage, MeterError  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402
from render_worker import RenderProcess  # noqa: E402
from compute_worker import ComputeProcess  # noqa: E402
try:                                            # spectator broadcast log (never read back; see broadcast_log.py)
    from broadcast_log import BroadcastLog  # noqa: E402
except ImportError:  # pragma: no cover
    BroadcastLog = None
BC = None                                       # the spectator broadcast log (set in __main__)


def bc_event(ev: str, **fields) -> None:
    if BC is not None:
        BC.event(ev, R.k, score=list(R.score), **fields)

DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(DATA, exist_ok=True)
SLOWDOWN = float(os.environ.get("SLOWDOWN", "20"))       # wall seconds per simulated second
os.environ.setdefault("WALLCLOCK_RULE_WAIT_S", "1.0")    # max real-time wait for the act's model call to be counted
RULE_WAIT_S = float(os.environ["WALLCLOCK_RULE_WAIT_S"])
WAIT_MAX_S = 1.0
T_MAX_S = 5.0                                            # contact at most this long after the act takes effect
LEVEL = int(os.environ.get("MATCH_LEVEL", "1"))
REVIEW = os.environ.get("MATCH_REVIEW", "1") == "1"
REVIEW_MAX_CHARS = 2000
REVIEW_PROMPT = ("Point over. Review it: `game ready \"WHY\" \"PLAN\"` (why it was won or lost; what you will change). "
                 "The world stays frozen until then.")
REVISION = match.REVISION
PLAYER_MODE = os.environ.get("RCB_PLAYER_MODE", "model")
if PLAYER_MODE not in ("model", "oracle"):
    raise ValueError("RCB_PLAYER_MODE must be model or oracle")
MAX_LAG_S = None                                        # wallclock-3: timing is reported, not a disqualification
TIMING_POLICY = "report_only"
LAG_REPORT_S = 0.1                                      # lateness above this is flagged in the telemetry only
DT = match.CONTROL_DT
PERIOD = DT * SLOWDOWN                                    # wall seconds per control step
PLAN_LEAD_S = float(os.environ.get("WALLCLOCK_PLAN_LEAD_S", "0.5"))   # wall-time budget of an act's stroke planning
LEAD = max(1, int(math.ceil(PLAN_LEAD_S / PERIOD - 1e-9)))            # control steps from acceptance to effect
OPP_WAIT_MAX_S = 5.0

COND = threading.Condition(threading.RLock())   # guards the match R and everything in E / SIM / seats
R = match.Match(LEVEL)
R.precompute_serves()                           # every serve of the match, before the clock runs
T0_WALL, T0_MONO = time.time(), time.monotonic()
E = {"started": False, "awaiting_review": False, "readying": False, "reviews": [], "reviewed_points": 0,
     "final_obs": None, "starting": False, "obs_seq": 0, "act_seq": 0, "op_seq": 0, "finalizing": False,
     "finalized": False, "reason": None, "extra": {}, "calls_per_point": [], "cur_point_calls": 0, "points_wall": []}
SIM = {"anchor": None, "lates": [], "step_ms": [], "run_wall_s": 0.0, "run_steps": 0, "seg_start": None,
       "segments": 0, "plan_cpu_ms": [], "plan_wall_ms": [], "plan_slack_ms": [], "plan_wait_ms": [],
       "opp_cpu_ms": [], "opp_slack_ms": [], "opp_wait_ms": [], "spec_leg": None, "spec_job": None}


class Seat:
    def __init__(self, name: str, usage_file: str):
        self.name = name
        self.clock = ThinkClock(seconds_per_ktok=0.0, usage_file=usage_file)
        self.decision_lock = threading.Lock()    # pair a consumed model response with its audit receipt
        self.queue: list[dict] = []
        self.news = {"results": [], "points": []}
        self.calls = {"observe": 0, "act": 0, "wait": 0}
        self.refused_not_model = 0
        self.refused_busy = 0                     # acts refused because another was in flight
        self.act_in_flight = False
        self.act_owner = None
        self.rule_wait_s: list[float] = []        # real time the call rule waited per accepted act
        self.act_delay_steps: list[int] = []      # control steps between an act's arrival and its effect
        self.act_wall_s: list[float] = []         # wall time from the act's arrival (incl. the call-rule wait) to its effect
        self.dropped_acts = 0                     # commands whose point ended before they took effect


SEATS = {"A": Seat("A", os.environ.get("THINK_USAGE_FILE", os.path.join(DATA, "think_usage.json")))}


def source_sha():
    from replay import source_sha as fingerprint
    return fingerprint()


def wall() -> float:
    return round(time.monotonic() - T0_MONO, 4)


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 4), "wall": wall(), "step": R.k, **ev}, default=_jdef) + "\n")


def _jdef(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return str(x)


def won() -> bool:
    """The agent won the match (by the score, or at the match limit by the score / the last point won)."""
    return R.winner() == 0


def running() -> bool:
    return E["started"] and not E["awaiting_review"] and E["final_obs"] is None and not R.done


# ---------------------------------------------------------------------------------------------- lag statistics
def _st(a, name) -> dict:
    a = np.asarray(a, float)
    if not len(a):
        return {}
    return {f"{name}_min": round(float(a.min()), 2), f"{name}_mean": round(float(a.mean()), 2),
            f"{name}_p99": round(float(np.percentile(a, 99)), 2),
            f"{name}_max": round(float(a.max()), 2), f"{name}_n": int(len(a))}


def lag_stats() -> dict:
    L = np.asarray(SIM["lates"], float)
    sim_s = SIM["run_steps"] * DT
    run_wall_s = SIM["run_wall_s"]
    if SIM["seg_start"] is not None and SIM.get("seg_last") is not None:
        run_wall_s += SIM["seg_last"] - SIM["seg_start"]
    out = {"slowdown": SLOWDOWN, "period_s": round(PERIOD, 4), "steps": int(SIM["run_steps"]),
           "run_wall_s": round(run_wall_s, 3), "run_sim_s": round(sim_s, 3),
           "effective_slowdown": round(run_wall_s / sim_s, 4) if sim_s > 0 else None,
           "segments": SIM["segments"], "plan_lead_steps": LEAD, "plan_lead_wall_s": round(LEAD * PERIOD, 4)}
    if len(L):
        out.update(late_max_s=round(float(L.max()), 4), late_mean_s=round(float(L.mean()), 5),
                   late_p50_s=round(float(np.percentile(L, 50)), 5), late_p99_s=round(float(np.percentile(L, 99)), 4),
                   late_max_steps=round(float(L.max() / PERIOD), 2),
                   frac_steps_late_over_1_period=round(float(np.mean(L > PERIOD)), 4),
                   frac_steps_late_over_10ms=round(float(np.mean(L > 0.010)), 4))
    out.update(_st(SIM["step_ms"], "step_ms"))
    for k in ("plan_cpu_ms", "plan_wall_ms", "plan_slack_ms", "plan_wait_ms", "opp_cpu_ms", "opp_slack_ms",
              "opp_wait_ms", "render_ms"):
        out.update(_st(SIM.get(k, []), k))
    out["opp_cache"] = dict(R.opp_cache_stats)
    if SIM.get("slow"):
        out["slowest_steps"] = SIM["slow"]
    return out


def write_final() -> None:
    with COND:
        _write_final_locked()


def _meter_error(usage) -> bool:
    if E.get("meter_error"):
        return True
    return PLAYER_MODE == "model" and (not usage.get("epoch") or usage.get("requests", 0) < 1)


def _write_final_locked() -> None:
    sA = SEATS["A"]
    n_calls = sum(sA.calls.values())
    rw = sA.rule_wait_s
    out = {"level": LEVEL, "points_for": R.score[0], "points_against": R.score[1], "win_points": match.WIN_POINTS,
           "won": won(), "returns": int(sum(r["returned"] for r in R.results)), "our_legs": R.n_our_legs,
           "winner": {0: "you", 1: "opponent", None: None}[R.winner()], "match_limit": bool(R.limit_reached),
           "hits": R.hits, "lets": sum(1 for p in R.points if p["winner"] == "let"),
           "done": R.done or E["reason"] is not None, "reason": E["reason"], "finalized": E["finalized"],
           "protocol": "wallclock", "slowdown": SLOWDOWN, "control_dt": DT, "plan_lead_steps": LEAD,
           "n_decisions": sA.calls["act"], "n_calls": n_calls,
           "n_observe": sA.calls["observe"], "n_act": sA.calls["act"], "n_wait": sA.calls["wait"],
           "calls_per_point": E["calls_per_point"], "refused_not_model": sA.refused_not_model, "refused_busy": sA.refused_busy,
           "dropped_acts": sA.dropped_acts,
           "act_rule_wait_s": [round(x, 4) for x in rw],
           "act_rule_wait_max_s": round(max(rw), 4) if rw else 0.0,
           "act_rule_wait_mean_s": round(float(np.mean(rw)), 4) if rw else 0.0,
           "act_delay_steps": sA.act_delay_steps, "act_wall_s": [round(x, 4) for x in sA.act_wall_s],
           "sim_lag": lag_stats(),
           "decision_rule": sA.clock.rule, "rule_wait_cap_s": RULE_WAIT_S,
           "review": REVIEW, "n_reviews": len(E["reviews"]), "reviews": E["reviews"],
           "steps": R.k, "physics_steps": int(R.s.steps_total), "elapsed_s": round(time.time() - T0_WALL, 1),
           "points": R.points, "points_wall": E["points_wall"], "results": R.results, "shots": R.shots,
           "opponent": [l.get("opp") for l in R.legs if l.get("opp")],
           "serves": [l.get("serve") for l in R.legs if l.get("kind") == "serve"]}
    out.update(E["extra"])
    out["graded_ready"] = E["finalized"]
    usage = read_usage(sA.clock.usage_file)
    api = seat_api_errors(sA.clock.usage_file, usage)   # model-API errors: transient vs unrecovered (api_errors.py)
    out.update(revision=REVISION, seed=R.lv["seed"], player_mode=PLAYER_MODE, started=E["started"],
               meter_error=_meter_error(usage), max_lag_s=MAX_LAG_S,
               sim_error=E["reason"] == "error",
               proxy_error=api["api_failure"],
               rate_limit_retries=usage.get("rate_limit_retries", 0),
               transient_api_errors=api["transient_api_errors"], unrecovered_api_errors=api["unrecovered_api_errors"],
               timing_policy=TIMING_POLICY, timing_invalid=False,
               late_over_100ms=bool(SIM["lates"] and max(SIM["lates"]) > LAG_REPORT_S))
    replay_ok = bool(out["graded_ready"] and out.get("deterministic") and out.get("replay_joint_targets_equal")
                     and out.get("replay_score") == list(R.score))
    out["replay_error"] = bool(out.get("finalize_error") or not replay_ok)
    out["valid_trial"] = bool(replay_ok and not any(out[k] for k in
                              ("replay_error", "sim_error", "meter_error", "proxy_error", "timing_invalid")))
    out["technical_failure"] = not out["valid_trial"]
    out["success"] = bool(won() and out["valid_trial"])
    tmp = os.path.join(DATA, "final.json.tmp")
    with open(tmp, "w") as f:
        json.dump(out, f, default=_jdef)
    os.replace(tmp, os.path.join(DATA, "final.json"))


# ---------------------------------------------------------------------------------------------- end of the match
def finalize() -> None:
    try:
        with COND:
            acts = R.s.actions().copy()
            live_sha = R.s.state_sha()
            k_end = R.k
            live_score = list(R.score)
        with open(os.path.join(DATA, "trajectory.json"), "w") as f:
            json.dump({"actions": acts.tolist(), "level": LEVEL, "control_dt": DT, "joints": match.JOINTS,
                       "slowdown": SLOWDOWN, "seed": R.lv["seed"], "revision": REVISION, "source_sha": source_sha()}, f)
        # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads the episode log; same joint targets)
        np.savez(os.path.join(DATA, "trajectory.npz"), actions=np.asarray(acts, dtype=np.float64), control_dt=DT,
                 level=LEVEL, seed=R.lv["seed"], slowdown=SLOWDOWN)
        out_p = os.path.join(DATA, "replay_check.json")
        t0 = time.time()
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "replay.py"),
                        os.path.join(DATA, "episode.jsonl"), str(k_end), out_p], check=True,
                       timeout=float(os.environ.get("RCB_REPLAY_TIMEOUT_S", "600")), env=dict(os.environ))
        with open(out_p) as f:
            rp = json.load(f)
        act_sha = hashlib.sha256(np.ascontiguousarray(acts, dtype=np.float64).tobytes()).hexdigest()
        E["extra"] = {"n_actions": int(len(acts)),
                      "deterministic": rp["state_sha"] == live_sha and rp["actions_sha"] == act_sha and rp["steps"] == k_end,
                      "replay_score": rp["score"], "replay_steps": rp["steps"], "replay_n_commands": rp["n_commands"],
                      "replay_joint_targets_equal": rp["actions_sha"] == act_sha, "live_state_sha": live_sha,
                      "replay_wall_s": round(time.time() - t0, 1), "live_score": live_score}
        log({"ev": "replay", **E["extra"]})
        with COND:                      # grading readiness is independent of the optional video
            E["finalized"] = True
            write_final()
        try:
            if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
                subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_video.py"),
                                os.path.join(DATA, "trajectory.json"), os.path.join(DATA, "replay.mp4")],
                               check=True, timeout=float(os.environ.get("RCB_VIDEO_TIMEOUT_S", "300")))
                E["extra"]["video"] = True
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            E["extra"]["video"] = False
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["extra"]["finalize_error"] = repr(exc)[:300]
    E["finalized"] = True
    write_final()


def _drop_queues(count: bool) -> None:
    for s in SEATS.values():
        for it in s.queue:
            it["dropped"] = True
            if count:
                s.dropped_acts += 1
            log({"ev": "act_dropped", "seat": s.name, "act_id": it["act_id"], "reason": "the point ended",
                 "state": it["state"]})
        s.queue.clear()


def end(reason: str) -> None:
    """With COND held."""
    if E["finalizing"]:
        return
    E["reason"] = reason
    E["final_obs"] = {"done": True, "reason": reason, "score": {"you": R.score[0], "opponent": R.score[1]},
                      "won": won(), "points": R.points, "note": "the match is over"}
    E["finalizing"] = True
    _close_segment()
    _drop_queues(count=False)
    log({"ev": "end", "reason": reason, "score": R.score, "k_end": R.k})
    bc_event("end", reason=reason)
    write_final()
    COND.notify_all()
    threading.Thread(target=finalize, daemon=True).start()


# ---------------------------------------------------------------------------------------------- workers
RENDER = RenderProcess()                 # separate processes: rendering and planning hold the GIL
PLANNER = ComputeProcess("plan")
OPPW = ComputeProcess("opponent")


def _plan_job(it: dict, snap: dict) -> None:
    t0 = time.monotonic()
    try:
        res, cpu = PLANNER.call(("plan", snap, LEAD, it["dec"]))
        err = None
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        res, cpu, err = None, 0.0, repr(exc)[:300]
    with COND:
        it["result"], it["error"] = res, err
        it["plan_cpu_s"], it["plan_wall_s"], it["t_result"] = cpu, time.monotonic() - t0, time.monotonic()
        COND.notify_all()


def _opp_job(job: dict) -> None:
    t0 = time.monotonic()
    try:
        out, cpu = OPPW.call(("opp",) + job["args"])
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        out, cpu = None, 0.0
    with COND:
        job["cpu_s"], job["wall_s"], job["t_result"] = cpu, time.monotonic() - t0, time.monotonic()
        if out is not None and job["leg_n"] == len(R.legs) - 1 and not R.done:
            key, cands = out
            R.opp_cache[key] = cands
        job["done"] = True
        COND.notify_all()


# ---------------------------------------------------------------------------------------------- the sim thread
def _close_segment() -> None:
    if SIM["seg_start"] is not None and SIM.get("seg_last") is not None:   # anchor -> start of the segment's last step
        SIM["run_wall_s"] += SIM["seg_last"] - SIM["seg_start"]
    SIM["seg_start"] = SIM["seg_last"] = None
    SIM["anchor"] = None


def _due(k: int) -> float:
    a_wall, a_k = SIM["anchor"]
    return a_wall + (k + 1 - a_k) * PERIOD


def _op(ev: dict) -> None:
    E["op_seq"] += 1
    log({**ev, "op": E["op_seq"]})


def _process_commands() -> None:
    """At the start of a control step, per seat in order: an act whose effect step has come takes effect (its plan
    from the planner process); then commands queued behind it: `none` / `move` take effect now, an act is
    snapshotted now (k_s) and sent to the planner, to take effect at k_s + LEAD (later commands wait for it)."""
    for name, s in SEATS.items():
        while s.queue:
            it = s.queue[0]
            dec = it["dec"]
            if it["state"] == "planning":
                if R.k < it["k_effect"]:
                    break
                if it["result"] is None and it["error"] is None:
                    t0 = time.monotonic()
                    COND.wait_for(lambda: it["result"] is not None or it["error"] is not None
                                  or E["final_obs"] is not None, timeout=60)
                    SIM["plan_wait_ms"].append((time.monotonic() - t0) * 1000.0)
                    if E["final_obs"] is not None:
                        return
                if it["error"] is not None or it["result"] is None:
                    raise RuntimeError(f"stroke planner failed: {it['error']}")
                SIM["plan_cpu_ms"].append(it["plan_cpu_s"] * 1000.0)
                SIM["plan_wall_ms"].append(it["plan_wall_s"] * 1000.0)
                SIM["plan_slack_ms"].append((_due(R.k) - it["t_result"]) * 1000.0)
                info = R.rt_install(it["result"])
                it["info"] = info
                _op({"ev": "act_applied", "seat": name, "k": R.k, "k_snap": it["k_snap"], "decision": dec,
                     "act_id": it["act_id"], "k_arrive": it["k_arrive"], "plan_cpu_ms": round(it["plan_cpu_s"] * 1e3, 1),
                     "plan_wall_ms": round(it["plan_wall_s"] * 1e3, 1), "model_call": it["model_call"],
                     "obs_ids": it["obs_ids"]})
            elif dec["type"] == "act":
                it["k_snap"], it["k_effect"], it["state"] = R.k, R.k + LEAD, "planning"
                it["result"] = it["error"] = None
                _op({"ev": "act_snapshot", "seat": name, "k": R.k, "k_effect": it["k_effect"], "act_id": it["act_id"]})
                threading.Thread(target=_plan_job, args=(it, match.plan_snapshot(R)), daemon=True).start()
                break
            else:
                if dec["type"] == "none":
                    R.rt_clear()
                    it["info"] = {"command": "cleared: the arm returns to the ready pose"}
                else:
                    it["info"] = {"base_rest": R.rt_move(*dec["base"])}
                it["k_snap"] = R.k
                _op({"ev": "act_applied", "seat": name, "k": R.k, "k_snap": R.k, "decision": dec,
                     "act_id": it["act_id"], "k_arrive": it["k_arrive"], "model_call": it["model_call"],
                     "obs_ids": it["obs_ids"]})
            it["k_effect"] = R.k
            it["wall_effect"] = time.monotonic()
            s.act_delay_steps.append(R.k - it["k_arrive"])
            s.act_wall_s.append(it["wall_effect"] - it["wall_arrive"])
            it["done"] = True
            s.queue.pop(0)


def _await_opp_spec() -> None:
    """Before the opponent's hit step: its return search, started at its reaction, must be in (else wait)."""
    job = SIM["spec_job"]
    if job is None or job["done"] or R.leg.get("opp_hit_k") != R.k + 1 or job["leg_n"] != len(R.legs) - 1:
        return
    t0 = time.monotonic()
    COND.wait_for(lambda: job["done"] or E["final_obs"] is not None, timeout=OPP_WAIT_MAX_S)
    SIM["opp_wait_ms"].append((time.monotonic() - t0) * 1000.0)


def _base_hints() -> list:
    """Where our base will probably be at the opponent's hit (only bounds how much of the search is precomputed)."""
    hints = [R.s.d.qpos[R.s.qa[:2]].copy(), (match.HOME if R.base_goal is None else R.base_goal).copy()]
    if R.plan_j < len(R.plan):
        hints.append(np.asarray(R.plan[-1][:2], float).copy())
    return hints


def _launch_opp_spec() -> None:
    """After the step at which the opponent reacted to our shot (it now knows where it will hit the ball): start
    its return search for the ball position at its hit step."""
    leg, n = R.leg, len(R.legs) - 1
    if (leg.get("opp_hit_k") is None or SIM["spec_leg"] == n or leg.get("state") != "to_opp"
            or leg.get("opp_leave") or leg.get("opp_pressure", 9.0) > 1.0 or leg["opp_hit_k"] <= R.k):
        return
    SIM["spec_leg"] = n
    pr = leg["opp_pressure"]
    mode = "weak" if pr > match.PRESSURE_WEAK else ("attack" if pr < match.PRESSURE_PASSIVE else "normal")
    s = R.s
    job = {"leg_n": n, "done": False, "k_hit": leg["opp_hit_k"], "t_start": time.monotonic(),
           "args": (s.b_p, s.b_v, s.b_w, (leg["opp_hit_k"] - R.k) * match.SUBSTEPS, mode, dict(R.lv),
                    len(R.points), len(R.legs), _base_hints())}
    SIM["spec_job"] = job
    threading.Thread(target=_opp_job, args=(job,), daemon=True).start()


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
            due = _due(R.k)                                # state k+1 becomes current at this wall time
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
            _process_commands()
            _await_opp_spec()
            if not running():
                continue
            t1 = time.monotonic()
            hit_step = R.leg.get("opp_hit_k") == R.k + 1
            n, pts, res = R.rt_advance(1)
            t2 = time.monotonic()
            SIM["lates"][-1] = max(SIM["lates"][-1], t2 - due)
            if R.hist and R.hist[-1]["k"] == R.k:
                R.hist[-1]["wall_mono"] = t2
            SIM["step_ms"].append((t2 - t0) * 1000.0)
            job = SIM["spec_job"]
            if hit_step and job is not None and job["k_hit"] == R.k:
                SIM["opp_cpu_ms"].append(job.get("cpu_s", 0.0) * 1000.0)
                if job.get("t_result") is not None:
                    SIM["opp_slack_ms"].append((due - job["t_result"]) * 1000.0)
            if (t2 - t0) > PERIOD or (t0 - due) > PERIOD or (t2 - due) > 0.5 * LAG_REPORT_S:
                SIM.setdefault("slow", []).append({"k": R.k, "late_ms": round((t0 - due) * 1000, 1),
                                                   "commands_ms": round((t1 - t0) * 1000, 1),
                                                   "step_ms": round((t2 - t1) * 1000, 1), "queued": nq,
                                                   "opp_hit": hit_step})
                SIM["slow"] = sorted(SIM["slow"], key=lambda e: -(e["late_ms"] + e["commands_ms"] + e["step_ms"]))[:8]
            SIM["run_steps"] += n
            if BC is not None:
                BC.after_step(R, bool(pts))
                for p in pts:
                    BC.event("point", R.k, score=list(R.score), winner=p.get("winner"), how=p.get("how"),
                             n=len(R.points))
            _launch_opp_spec()
            for s in SEATS.values():
                s.news["results"] += list(res)
                s.news["points"] += list(pts)
            if res:
                log({"ev": "shot", "shots": [{k: r.get(k) for k in ("returned", "summary", "speed_out", "landing")}
                                             for r in res]})
            if pts:
                log({"ev": "point", "points": pts})
                E["points_wall"].append({"point": len(R.points), "wall": wall(), "k": R.k})
                _drop_queues(count=True)              # a command does not carry over to the next point
                E["calls_per_point"].append(E["cur_point_calls"]); E["cur_point_calls"] = 0
            if R.done:
                end("match_over")
            elif len(R.points) > E["reviewed_points"]:
                if REVIEW:
                    E["awaiting_review"] = True
                    _close_segment()
                    log({"ev": "pause_for_review", "k": R.k})
                    bc_event("pause")
                else:
                    E["reviewed_points"] = len(R.points)
            if pts or res or R.k % 50 == 0:
                write_final()
            COND.notify_all()


# ---------------------------------------------------------------------------------------------- rendering
def ensure_frame() -> None:
    """Before the world's first step there is no camera snapshot yet (display only; not part of the physics state)."""
    if not R.hist:
        R.hist.append({"k": R.k, "t": R.t_since_launch(), "qpos": R.s.d.qpos.copy(), "b": R.s.b_p,
                       "opp": R.opp_x(), "leg_id": len(R.legs) - 1, "wall_mono": time.monotonic()})


def snapshots() -> list[dict]:
    """With COND held: the 4 camera frames 40 ms apart ending at the newest one (copies; the match keeps one
    snapshot per camera frame, every 2 control steps). During a review: the previous point's last frames."""
    ensure_frame()
    hist = list(R.review_hist if (E["awaiting_review"] and R.review_hist) else R.hist)
    return [dict(hist[max(0, len(hist) - 1 - b)]) for b in reversed(match.Match.VIEW_BACK)]


# ---------------------------------------------------------------------------------------------- observations
def now_state(seat: Seat) -> dict:
    """With COND held. What the player knows without looking: score, time, what it heard, its robot, its command."""
    ensure_frame()
    o = R.decision_observation()
    o.pop("view_times", None)
    o["t_sim"] = round(R.k * DT, 4)
    o["step"] = R.k
    # how far into the current control step's wall slot we are (0..1; 0 while frozen): game time now is
    # (step + step_phase) x 0.01 s
    ph = 0.0
    if running() and SIM["anchor"] is not None:
        a_wall, a_k = SIM["anchor"]
        ph = min(1.0, max(0.0, (time.monotonic() - (a_wall + (R.k - a_k) * PERIOD)) / PERIOD))
    o["step_phase"] = round(ph, 3)
    o["wall_s"] = wall()
    o["world"] = ("running" if running() else ("frozen: review due (game ready)" if E["awaiting_review"] else
                  ("frozen: not started (game start)" if not E["started"] else "over")))
    o["ball_in_play"] = R.in_play() and R.leg["state"] in ("incoming", "to_opp")
    o["ball_state"] = ({"incoming": "coming to you", "to_opp": "going to the opponent", "done": "dead"}
                       .get(R.leg["state"], R.leg["state"]) if R.in_play() else "not yet served")
    if not R.in_play():
        o["serve_in_s"] = round(max(0.0, (R.leg["launch"] - R.k) * DT), 3)
        o["heard"] = []
        o["t_since_played"] = None
    la = getattr(R, "_last_act", None)
    active = R.plan_j < len(R.plan)
    k_hit = la.get("k_hit") if la else None
    o["command"] = ({"contact_in_s": round(max(0, k_hit - R.k) * DT, 3) if k_hit is not None else None,
                     "phase": "approach" if (k_hit is not None and R.k < k_hit) else "follow_through",
                     "pos": la.get("racket_pos"), "normal": la.get("racket_normal"), "vel": la.get("racket_vel"),
                     "base_at_contact": la.get("base_goal"), "stroke": la.get("stroke")}
                    if active and la else "none (the arm returns to / holds the ready pose)")
    o["base_rest"] = ("home " + str(match.HOME.tolist()) if R.base_goal is None
                      else [round(float(x), 3) for x in R.base_goal])
    pend = [it for it in seat.queue if not it.get("done")]
    if pend:
        o["pending_commands"] = [{"act_id": it["act_id"], "type": it["dec"]["type"],
                                  "takes_effect_at_step": it.get("k_effect") if it["state"] == "planning" else None}
                                 for it in pend]
    return o


IMAGE_LAYOUT = ("2 rows x 4 columns. Row 1: camera behind and above your base line looking down the court; "
                "row 2: camera at the side of the court (x < 0) looking along +x: your half (y < 0) is on the "
                "right, the opponent's on the left. Columns: four camera frames 40 ms apart, oldest left, latest "
                "right; each tile is stamped with its control step k and its time t since the ball that was current "
                "then was played (see view_steps / view_times). The ball is drawn enlarged: a yellow-green sphere of "
                "radius 9 cm (the real ball: 3.35 cm) centred on the ball's true position. Yellow marks every 2 m "
                "outside the doubles side lines (y = -10..10) and every 1 m behind the base lines (x = -4..4); the "
                "opponent is the grey figure with the red racket.")


def observe_payload(seat: Seat) -> dict:
    """Snapshot under the lock, render outside it (the world keeps running while the image is drawn)."""
    with COND:
        o = now_state(seat)
        snaps = snapshots()
        E["obs_seq"] += 1
        o["obs_id"] = E["obs_seq"]
    render_start = time.monotonic()
    png = RENDER.render(snaps)
    render_end = time.monotonic()
    o["view_times"] = [s["t"] for s in snaps]
    o["view_steps"] = [s["k"] for s in snaps]
    o["view_leg_ids"] = [s.get("leg_id") for s in snaps]
    o["view_sim_times"] = [round(s["k"] * DT, 4) for s in snaps]
    o["image_png_b64"] = base64.b64encode(png).decode()
    o["image_layout"] = IMAGE_LAYOUT
    with COND:
        o["t_sim_at_reply"] = round(R.k * DT, 4)
        o["wall_s_at_reply"] = wall()
        o["obs_age_sim_s"] = round((R.k - snaps[-1]["k"]) * DT, 4)
        o["obs_age_wall_s"] = round(time.monotonic() - snaps[-1].get("wall_mono", time.monotonic()), 6)
        o["render_wall_s"] = round(render_end - render_start, 6)
        SIM.setdefault("render_ms", []).append((render_end - render_start) * 1000.0)
    return o


def take_news(seat: Seat) -> dict:
    """With COND held: shot results and finished points this seat has not been told yet."""
    out = {}
    res, pts = seat.news["results"], seat.news["points"]
    if res:
        out["shots_since_your_last_call"] = [{k: r.get(k) for k in ("returned", "summary", "speed_out")} for r in res]
    if pts:
        out["points_finished"] = [{k: p[k] for k in ("point", "winner", "how", "score")} for p in pts]
        out["score"] = {"you": R.score[0], "opponent": R.score[1]}
    if not E["awaiting_review"]:
        seat.news = {"results": [], "points": []}
    if E["awaiting_review"]:
        out["review_prompt"] = REVIEW_PROMPT
    return out


def _base_arg(base) -> list | str:
    try:
        base = [float(x) for x in base]
    except Exception:  # noqa: BLE001
        return "base must be [bx, by]"
    if len(base) != 2 or not np.all(np.isfinite(base)):
        return "base must be [bx, by] (2 finite numbers)"
    if not (abs(base[0]) <= 5.9 and -15.4 <= base[1] <= -7.6):
        return "base out of range: |bx| <= 5.9, -15.4 <= by <= -7.6"
    return base


def validate_act(body: dict) -> dict | str:
    typ = body.get("type")
    if typ == "none":
        return {"type": "none"}
    if typ == "move":
        base = _base_arg(body.get("base"))
        return base if isinstance(base, str) else {"type": "move", "base": base}
    try:
        T = float(body["t"]); pos = [float(x) for x in body["pos"]]
        nrm = [float(x) for x in body["normal"]]; vel = [float(x) for x in body["vel"]]
    except Exception:  # noqa: BLE001
        return ("act needs T (s from when the act takes effect until contact), pos [x, y, z] (racket-head centre at "
                "contact), normal [nx, ny, nz] (string-face normal) and vel [vx, vy, vz] (head velocity at contact, "
                "m/s), optionally base [bx, by] (the base position at contact); or `act none`, or `move BX BY`")
    if len(pos) != 3 or len(nrm) != 3 or len(vel) != 3 or not np.all(np.isfinite(pos + nrm + vel + [T])):
        return "pos, normal and vel must have 3 finite numbers each"
    if np.linalg.norm(nrm) < 1e-6:
        return "normal must be a non-zero vector"
    if not (0.0 < T <= T_MAX_S):
        return f"T must be in (0, {T_MAX_S}] s from when the act takes effect"
    if not (abs(pos[0]) <= 6.5 and -16.0 <= pos[1] <= -6.0 and 0.1 <= pos[2] <= 2.4):
        return "pos out of range: |x| <= 6.5, -16 <= y <= -6, 0.1 <= z <= 2.4"
    if np.linalg.norm(vel) > 8.0:
        return "vel too large: |vel| <= 8 m/s"
    out = {"type": "act", "t": T, "pos": pos, "normal": nrm, "vel": vel}
    if body.get("base") is not None:
        base = _base_arg(body["base"])
        if isinstance(base, str):
            return base
        out["base"] = base
    return out


def gate() -> tuple[int, dict] | None:
    """With COND held: the calls observe / act / wait need a started, running match."""
    if E["final_obs"] is not None:
        return 200, E["final_obs"]
    if E["awaiting_review"]:
        return 409, {"error": "the point is over: review it first with `game ready \"WHY\" \"PLAN\"` (the world is "
                     "frozen until then)", "review_prompt": REVIEW_PROMPT}
    if not E["started"]:
        return 409, {"error": "the match has not started: the world is frozen until you run `game start`. Take all the "
                     "time you need first (read, plan, write and test your code): nothing before `game start` counts."}
    return None


# ---------------------------------------------------------------------------------------------- endpoints
def start(seat: Seat) -> tuple[int, dict]:
    """`game start`: the world starts running now (real time); everything before was free."""
    with COND:
        if E["final_obs"] is not None:
            return 200, E["final_obs"]
        if E["started"] or E["starting"]:
            return 409, {"error": "the match has already started"}
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
            log({"ev": "match_start", "seat": seat.name, "slowdown": SLOWDOWN})
            bc_event("start")
            obs["world"] = "running"
            COND.notify_all()
    finally:
        with COND:
            E["starting"] = False
    write_final()
    return 200, {"started": True, "note": f"the world runs from now on its own, at 1/{SLOWDOWN:g} of real speed "
                 f"({PERIOD:.3f} s of wall time per 10 ms of game time); it does not wait for you. The first serve "
                 f"comes in {max(0.0, (R.leg['launch'] - R.k) * DT):.2f} s of game time", "observation": obs}


def do_observe(seat: Seat, body: dict) -> tuple[int, dict]:
    with COND:
        if E["final_obs"] is not None:
            return 200, E["final_obs"]
        seat.calls["observe"] += 1; E["cur_point_calls"] += 1
        k_req, w_req = R.k, wall()
    o = observe_payload(seat)
    with COND:
        news = take_news(seat)
    log({"ev": "call", "kind": "observe", "seat": seat.name, "k_request": k_req, "wall_request": w_req,
         "obs_id": o["obs_id"], "view_steps": o["view_steps"], "k_reply": int(round(o["t_sim_at_reply"] / DT)),
         "render_wall_s": o["render_wall_s"]})
    return 200, {"call": "observe", "t_sim": round(k_req * DT, 4), "wall_s": w_req, "observation": o, **news}


STROKE_KEYS = ("stroke", "base", "base_goal", "k_hit", "n_swing_steps_available", "n_swing_steps", "ik_residual",
               "blade_error_m", "normal_error_deg", "speed_scale", "racket_vel_delivered", "T_from_now")


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
        k_arr, w_arr, point_arr = R.k, entered, len(R.points)
        lock_wait = time.monotonic() - entered
    t_rule = time.monotonic()
    with seat.decision_lock:
        ok = seat.clock.decided_by_model()
        model_call = seat.clock.last_call() if ok else None
    rule_wait = time.monotonic() - t_rule
    with COND:
        if not ok:
            seat.refused_not_model += 1
            log({"ev": "refused_not_model", "seat": seat.name, "kind": dec["type"], "rule_wait_s": round(rule_wait, 4)})
            return 429, {"refused": True, "error": "refused: no new completed model response since the previous act/move "
                         "whose tool call contains `game act` or `game move`. Every act / move must be a model turn that "
                         "itself runs the command; a script looping over the game is not allowed."}
        seat.rule_wait_s.append(rule_wait)
        g = gate()
        if g:
            return g
        if len(R.points) != point_arr:
            seat.dropped_acts += 1
            log({"ev": "act_dropped", "seat": seat.name, "reason": "point changed during model-call wait",
                 "k_request": k_arr})
            return 409, {"error": "act dropped: its point ended while waiting for the model response"}
        E["act_seq"] += 1
        it = {"act_id": E["act_seq"], "model_call": model_call, "obs_ids": obs_ids, "state": "queued",
              "dec": dec, "k_arrive": k_arr, "wall_arrive": w_arr, "k_queued": R.k, "done": False, "dropped": False}
        seat.queue.append(it)
        seat.calls["act"] += 1; E["cur_point_calls"] += 1
        log({"ev": "call", "kind": "act" if dec["type"] != "move" else "move", "seat": seat.name, "k_request": k_arr,
             "k_queued": R.k, "rule_wait_s": round(rule_wait, 4), "decision": dec, "act_id": it["act_id"],
             "http_arrive_wall": round(entered - T0_MONO, 6), "lock_wait_s": lock_wait,
             "model_call": it["model_call"], "obs_ids": obs_ids})
        COND.wait_for(lambda: it["done"] or it["dropped"] or E["final_obs"] is not None,
                      timeout=60 + (LEAD + 5) * PERIOD * (1 + len(seat.queue)))
        out = {"call": "act" if dec["type"] != "move" else "move", "act_id": it["act_id"],
               "lock_wait_s": round(lock_wait, 6), "t_sim_request": round(k_arr * DT, 4), "rule_wait_s": round(rule_wait, 4)}
        if it["done"]:
            info = it["info"]
            out["took_effect"] = {"step": it["k_effect"], "t_sim": round(it["k_effect"] * DT, 4),
                                  "accepted_step": it["k_snap"], "steps_after_request": it["k_effect"] - k_arr,
                                  "wall_s_after_request": round(it["wall_effect"] - w_arr, 4)}
            if dec["type"] == "none":
                out["command"] = "cleared: the arm returns to the ready pose"
            elif dec["type"] == "move":
                out["base_rest"] = info["base_rest"]
            else:
                out["stroke"] = {k: info.get(k) for k in STROKE_KEYS}
        else:
            if it in seat.queue:
                seat.queue.remove(it)
                seat.dropped_acts += 1
            it["dropped"] = True
            out["note"] = "command dropped before it took effect (the point ended or the service timed out)"
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
        seat.calls["wait"] += 1; E["cur_point_calls"] += 1
        k0, n0 = R.k, len(R.points)
        target = k0 + max(1, int(round(dt / DT)))
        log({"ev": "call", "kind": "wait", "seat": seat.name, "k_request": k0, "dt": dt})
        COND.wait_for(lambda: R.k >= target or len(R.points) > n0 or not running(), timeout=dt * SLOWDOWN + 60)
        out = {"call": "wait", "t_sim_request": round(k0 * DT, 4), "waited_s": round((R.k - k0) * DT, 4),
               "now": now_state(seat)}
        out.update(take_news(seat))
        if E["final_obs"] is not None:
            out.update(E["final_obs"])
    return 200, out


def do_ready(seat: Seat, body: dict) -> tuple[int, dict]:
    """Between points: the review; the world is frozen until then and resumes on a fresh schedule."""
    with COND:
        if E["final_obs"] is not None:
            return 200, E["final_obs"]
        if not E["awaiting_review"] or E["readying"]:
            return 409, {"error": "no review is due now (reviews are due after each point)"}
        why, plan = body.get("why"), body.get("plan")
        if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
            return 400, {"error": "ready needs two non-empty texts: WHY (why the point was won or lost) and PLAN (what "
                         "you will change)"}
        if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
            return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
        E["readying"] = True
    try:
        seat.clock.settle()
        with COND:
            if E["final_obs"] is not None:
                return 200, E["final_obs"]
            seat.clock.rebase()                 # review responses cannot bank the next point's act
            rv = {"after_point": len(R.points), "score": list(R.score), "why": why.strip(), "plan": plan.strip(),
                  "t": round(time.time() - T0_WALL, 1)}
            E["reviews"].append(rv)
            E["reviewed_points"] = len(R.points)
            log({"ev": "review", "seat": seat.name, **rv})
            E["awaiting_review"] = False
            out = {"accepted": "review recorded", "now": now_state(seat),
                   "note": "the world is running again: the next serve comes in "
                           f"{max(0.0, (R.leg['launch'] - R.k) * DT):.2f} s of game time "
                           f"({max(0.0, (R.leg['launch'] - R.k) * PERIOD):.1f} s of wall time)"}
            out.update(take_news(seat))
            COND.notify_all()
    finally:
        with COND:
            E["readying"] = False
    write_final()
    return 200, out


SPEC = {
    "revision": REVISION, "player_mode": PLAYER_MODE,
    "protocol": "eai-standard-realtime/1.0",
    "simulator": "mujoco 3.3.7 (robot) + point-mass tennis ball with drag, Magnus lift, court bounce and racket impact laws",
    "robot": (f"franka-panda on a 0.55 m pedestal, base on x-y rails (<= {match.BASE_VMAX} m/s, <= {match.BASE_AMAX} m/s^2) "
              "+ tennis racket (head centre 0.52 m beyond the flange, strung area an ellipse 0.26 x 0.32 m)"),
    "match": {"win_points": match.WIN_POINTS, "win_by": match.WIN_BY, "cap_points": match.CAP_POINTS,
              "max_hits": match.MAX_HITS, "max_points_played": match.MAX_POINTS, "opponent_level": LEVEL,
              "first_player": "opponent",
              "serves": "the opponent serves every point (it is the first player; you always receive)"},
    "timing": {"slowdown": SLOWDOWN, "control_dt_s": DT, "wall_s_per_control_step": PERIOD,
               "wall_s_per_game_s": SLOWDOWN, "wait_max_s": WAIT_MAX_S, "act_lead_steps": LEAD,
               "act_lead_game_s": round(LEAD * DT, 4), "act_lead_wall_s": round(LEAD * PERIOD, 4), "act_T_max_s": T_MAX_S,
               "rule": f"the world runs on its own clock at 1/{SLOWDOWN:g} of real speed (game time = wall time / "
                       f"{SLOWDOWN:g}); it does not wait for your calls or your thinking. An act is accepted at the next "
                       f"control step after it arrives and takes effect {LEAD} control steps later ({LEAD * DT:.2f} s of "
                       "game time: the stroke controller plans meanwhile); `act none` and `move` take effect at the "
                       "next step. The robot keeps its current command until then; commands take effect in order"},
    "decision_rule": ("program play: your own program may observe and act (or move) without a new model response; "
                      "one act or move in flight at a time" if os.environ.get("RCB_ACT_RULE") == "program" else
                      "each act (and each move) needs a new completed model response since the previous one whose tool "
                      "call contains the `game act` (or `game move`) command"),
    "review": ("after each point the world stays frozen until `game ready WHY PLAN`; recorded, not scored"
               if REVIEW else "off"),
    "calls": {"start": "start the match (the world runs from then on); returns the first observation",
              "observe": "the newest camera frames (2 x 4), heard bounces, time, your robot and command",
              "act": "{'type':'act','t':T_from_effect,'pos':[x,y,z],'normal':[nx,ny,nz],'vel':[vx,vy,vz],'base':[bx,by] "
                     "(optional)} (racket state at contact) or {'type':'none'}",
              "move": "{'type':'move','base':[bx,by]} (POST /act): the base's rest position when no stroke is under way",
              "wait": "{'dt': game seconds}"},
    "seats": sorted(SEATS),
    "cameras": [dict(c, fovy_deg=match.Match.FOVY, tile_px=list(match.Match.TILE), focal_px=579.4,
                     principal_point_px=[320, 240], image_right="forward x up") for c in match.Match.cam_info()],
    "image": "2 rows (behind, side) x 4 columns (camera frames 40 ms apart, oldest left); tile 640 x 480",
    "world": ("court z = 0; singles court |x| <= 4.115, |y| <= 11.885 (lines in); service line |y| = 6.40; net plane "
              "y = 0, top 0.914 m at x = 0 rising linearly to 1.07 m at |x| = 5.029; your half y < 0. Robot base home "
              f"{match.HOME.tolist()}, rails |bx| <= 5.9, -15.4 <= by <= -7.6; default stance: base = contact xy - "
              f"{match.STANCE_OFF.tolist()}"),
    "ball": {"mass_kg": match.BALL_M, "radius_m": match.BALL_R, "drag": f"a = -{match.K_DRAG:.5f} |v| v (C_D {match.C_D})",
             "magnus": f"a = {match.K_LIFT:.5f} C_L |v|^2 unit(w x v), C_L = 1/(2 + 1/S), S = r|w|/|v|",
             "court_bounce": {"restitution": match.E_COURT, "friction": match.MU_COURT, "inertia_factor": match.ALPHA},
             "racket": {"restitution_centre": match.E_RACKET, "offcentre_loss": match.OFFCENTRE_LOSS,
                        "friction": match.MU_RACKET, "racket_gain": match.RACKET_GAIN}},
}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, obj: dict) -> None:
        b = json.dumps(obj, default=_jdef).encode()
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
                ph = 0.0
                if running() and SIM["anchor"] is not None:
                    a_wall, a_k = SIM["anchor"]
                    ph = min(1.0, max(0.0, (time.monotonic() - (a_wall + (R.k - a_k) * PERIOD)) / PERIOD))
                return self._send(200, {"score": {"you": R.score[0], "opponent": R.score[1]}, "calls": s.calls,
                                        "t_sim": round(R.k * DT, 4), "step": R.k, "step_phase": round(ph, 3),
                                        "wall_s": wall(), "slowdown": SLOWDOWN, "running": running(),
                                        "awaiting_review": E["awaiting_review"], "started": E["started"],
                                        "done": E["final_obs"] is not None, "reason": E["reason"],
                                        "last_point": R.points[-1] if R.points else None,
                                        "last_shot": ({k: R.results[-1].get(k) for k in ("returned", "summary", "speed_out")}
                                                      if R.results else None)})
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
    log({"ev": "start", "level": LEVEL, "seed": R.lv["seed"], "protocol": "wallclock", "slowdown": SLOWDOWN,
         "control_dt": DT, "period_s": PERIOD, "plan_lead_steps": LEAD, "decision_rule": SEATS["A"].clock.rule,
         "rule_wait_cap_s": RULE_WAIT_S, "revision": REVISION, "player_mode": PLAYER_MODE,
         "max_lag_s": MAX_LAG_S, "timing_policy": TIMING_POLICY, "source_sha": source_sha()})
    PLANNER.warm(); OPPW.warm()
    if BroadcastLog is not None:
        BC = BroadcastLog(every=2, sport="tennis", mode="single", slowdown=SLOWDOWN, dt=DT, level=LEVEL,
                          seed=R.lv["seed"], nq=int(R.s.m.nq), players={"A": "you", "B": "opponent"})
        with COND:
            ensure_frame()
            BC.snapshot(R.hist[-1], force=True)     # the scene before the first serve
    write_final()
    threading.Thread(target=guarded_sim_loop, daemon=True).start()
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    print(f"match service ready (wall clock, slowdown x{SLOWDOWN:g}, act lead {LEAD} steps)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()
