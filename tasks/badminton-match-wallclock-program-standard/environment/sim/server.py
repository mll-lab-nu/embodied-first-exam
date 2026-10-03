"""Wall-clock sim service for badminton-match-wallclock-program-standard (racket-level, slowed world, program play).

The world runs ON ITS OWN CLOCK: a background thread steps the match (bm.py, the same engine as the lock-step
badminton tasks) at CONTROL_DT = 10 ms of simulated time per control step and paces every step to CONTROL_DT x
SLOWDOWN of wall time (time.monotonic schedule from an anchor, so there is no drift accumulation). sim time = wall
time / SLOWDOWN. Nothing pauses the world while the model thinks: its thinking, tool calls, network and API latency
all take real time. If the computer cannot keep up (a step takes longer than its wall slot, or a stroke plan is not
back by the step it is due) the thread catches up as fast as it can and the lateness is recorded (`sim_lag` in
final.json); it never silently slows the world down. Revision wallclock-3: lateness is reported only
(timing_policy=report_only, max_lag_s=null); there is no timing_invalid cutoff.

Frozen (free) time: until `game start`, and after each point until `game ready WHY PLAN`.

Calls (the server runs by itself; clients pull the state and push commands):
  observe  the newest 2 cameras x 4 frames (60 ms apart) + what was heard, at the sim time of the request. Rendered
           from snapshots (the match keeps one per camera frame) in a separate render process (render_worker.py).
  act      a new racket state at contact (same validation as the lock-step task). Queued per seat at step k_q; it
           takes effect at step k_e = k_q + LEAD_STEPS, the first control step at least PLAN_LEAD_S (0.4 s) of wall
           time later (the replaced command keeps executing until then); T counts from k_e. The stroke is planned in
           a separate planner process from an exact copy of the match advanced to k_e (wc.py), so planning never
           stalls the world; the result is bit-identical to planning at k_e in the sim thread (the replay does that).
           The reply comes once it has taken effect and gives the exact step. Program play (RCB_ACT_RULE=program):
           the agent's own program may act without a new model response; one act in flight per seat (think_clock.py).
  wait DT  block until sim time + DT (convenience).
  ready    after each point: the review; the world restarts only then.
  status / spec.
  oracle   RCB_PLAYER_MODE=oracle only: the true state and the privileged reference decision (oracle_ref.py,
           computed in its own advisor process from an exact copy of the match). 403 in model mode.

Evidence (/data): episode.jsonl (every call: wall time, sim step, payload; every applied act with its effect step),
final.json, trajectory.json, replay_check.json, replay.mp4. On episode end (or SIGUSR1 from the collect hook) a FRESH
PROCESS (replay.py) re-simulates the match from the logged (step, act) list only; the replayed score, final state hash
and joint targets must equal the live ones.
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
import bm as match  # noqa: E402
import wc  # noqa: E402
from think_clock import ThinkClock, read_usage, MeterError  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402
from render_worker import RenderProcess  # noqa: E402
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
LEVEL = int(os.environ.get("MATCH_LEVEL", "1"))
REVIEW = os.environ.get("MATCH_REVIEW", "1") == "1"
REVIEW_MAX_CHARS = 2000
REVIEW_PROMPT = ("Point over. Review it: `game ready \"WHY\" \"PLAN\"` (why it was won or lost; what you will change). "
                 "The world stays frozen until then.")
REVISION = wc.REVISION
PLAYER_MODE = os.environ.get("RCB_PLAYER_MODE", "model")
if PLAYER_MODE not in ("model", "oracle"):
    raise ValueError("RCB_PLAYER_MODE must be model or oracle")
# Revision 3 reports scheduling delays without a lateness disqualification threshold.
MAX_LAG_S = None
TIMING_POLICY = "report_only"
DT = match.CONTROL_DT
PERIOD = DT * SLOWDOWN                                    # wall seconds per control step
PLAN_LEAD_S = float(os.environ.get("WALLCLOCK_PLAN_LEAD_S", "0.4"))
LEAD_STEPS = max(1, int(math.ceil(PLAN_LEAD_S / PERIOD - 1e-9)))   # act effect step = queue step + LEAD_STEPS
PLAN_TIMEOUT_S = float(os.environ.get("RCB_PLAN_TIMEOUT_S", "30"))
ADVICE_TIMEOUT_S = 60.0

COND = threading.Condition(threading.RLock())   # guards the match R and everything in E / SIM / seats
R = match.Match(LEVEL)
T0_WALL, T0_MONO = time.time(), time.monotonic()
E = {"started": False, "awaiting_review": False, "readying": False, "reviews": [], "reviewed_points": 0,
     "final_obs": None, "starting": False, "obs_seq": 0, "act_seq": 0, "finalizing": False, "finalized": False,
     "reason": None, "extra": {}, "calls_per_point": [], "cur_point_calls": 0, "points_wall": [],
     "review_hist": None, "n_oracle_advice": 0, "advice_ms": []}
SIM = {"anchor": None, "lates": [], "step_ms": [], "plan_ms": [], "fork_ms": [], "plan_wait_ms": [],
       "snap_ms": [], "plan_mismatch": 0, "plan_inline": 0, "run_wall_s": 0.0, "run_steps": 0,
       "seg_start": None, "segments": 0}
PLAN_RESULTS: dict = {}                         # act_id -> planner reply


class Seat:
    def __init__(self, name: str, usage_file: str):
        self.name = name
        self.clock = ThinkClock(seconds_per_ktok=0.0, usage_file=usage_file)
        self.decision_lock = threading.Lock()    # pair a consumed model response with its audit receipt
        self.queue: list[dict] = []
        self.news = {"results": [], "points": []}
        self.calls = {"observe": 0, "act": 0, "wait": 0}
        self.refused_not_model = 0
        self.refused_busy = 0
        self.act_in_flight = False
        self.act_owner = None
        self.rule_wait_s: list[float] = []        # real time the call rule waited per accepted act
        self.act_delay_steps: list[int] = []      # control steps between an act's arrival and its effect
        self.act_wall_s: list[float] = []         # wall time from the act's arrival (incl. the call-rule wait) to its effect
        self.dropped_acts = 0                     # acts whose point ended before they took effect
        self.last_act_info = None


SEATS = {"A": Seat("A", os.environ.get("THINK_USAGE_FILE", os.path.join(DATA, "think_usage.json")))}


def wall() -> float:
    return round(time.monotonic() - T0_MONO, 4)


def _jsonable(o):
    return o.tolist() if hasattr(o, "tolist") else float(o)


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 4), "wall": wall(), "step": R.k, **ev}, default=_jsonable) + "\n")


def won() -> bool:
    return R.winner == 0


def running() -> bool:
    return E["started"] and not E["awaiting_review"] and E["final_obs"] is None and not R.done


# ---------------------------------------------------------------------------------------------- planner process
def _on_plan_result(msg) -> None:
    st, out = msg
    with COND:
        if st == "ok":
            PLAN_RESULTS[out["act_id"]] = out
        elif st == "error" and out.get("act_id") is not None:
            PLAN_RESULTS[out["act_id"]] = {"act_id": out["act_id"], "status": "error", "error": out.get("error")}
        else:
            E["planner_dead"] = out.get("error", "planner died")
        COND.notify_all()


PLANNER = wc.Worker("planner", on_result=_on_plan_result)
ADVISOR = wc.Worker("advisor") if PLAYER_MODE == "oracle" else None


# ---------------------------------------------------------------------------------------------- lag statistics
def _pct(a, q):
    return round(float(np.percentile(np.asarray(a, float), q)), 3) if len(a) else None


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
           "segments": SIM["segments"], "plan_lead_steps": LEAD_STEPS, "plan_lead_s": PLAN_LEAD_S}
    if len(L):
        out.update(late_max_s=round(float(L.max()), 4), late_mean_s=round(float(L.mean()), 5),
                   late_p50_s=round(float(np.percentile(L, 50)), 5), late_p99_s=round(float(np.percentile(L, 99)), 4),
                   late_max_steps=round(float(L.max() / PERIOD), 2),
                   frac_steps_late_over_1_period=round(float(np.mean(L > PERIOD)), 4),
                   frac_steps_late_over_10ms=round(float(np.mean(L > 0.010)), 4))
    if len(S):
        out.update(step_ms_mean=round(float(S.mean()), 3), step_ms_p99=round(float(np.percentile(S, 99)), 3),
                   step_ms_max=round(float(S.max()), 3))
    if SIM.get("slow"):
        out["slowest_steps"] = SIM["slow"]
    P = SIM["plan_ms"]
    if P:
        out.update(n_plans=len(P), plan_ms_mean=round(float(np.mean(P)), 2), plan_ms_max=round(float(max(P)), 2),
                   fork_ms_max=round(float(max(SIM["fork_ms"] or [0])), 2),
                   plan_wait_ms_max=round(float(max(SIM["plan_wait_ms"] or [0])), 2),
                   n_plan_waits=int(sum(1 for w in SIM["plan_wait_ms"] if w > 0)),
                   snapshot_ms_max=round(float(max(SIM["snap_ms"] or [0])), 2))
    out.update(plan_mismatch=SIM["plan_mismatch"], plan_inline=SIM["plan_inline"])
    return out


def write_final() -> None:
    with COND:
        _write_final_locked()


def _write_final_locked() -> None:
    sA = SEATS["A"]
    n_calls = sum(sA.calls.values())
    rw = sA.rule_wait_s
    out = {"level": LEVEL, "points_for": R.score[0], "points_against": R.score[1], "win_points": match.WIN_POINTS,
           "won": won(), "returns": int(sum(r["returned"] for r in R.results)), "our_legs": R.n_our_legs,
           "done": R.done or E["reason"] is not None, "reason": E["reason"], "finalized": E["finalized"],
           "protocol": "wallclock", "slowdown": SLOWDOWN, "control_dt": DT,
           "plan_lead_s": PLAN_LEAD_S, "plan_lead_steps": LEAD_STEPS,
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
           "serves": [l.get("serve") for l in R.legs if l.get("kind") == "serve"],
           "n_oracle_advice": E["n_oracle_advice"],
           "oracle_advice_ms_max": round(max(E["advice_ms"]), 1) if E["advice_ms"] else None}
    out.update(E["extra"])
    out["graded_ready"] = E["finalized"]
    usage = read_usage(sA.clock.usage_file)
    api = seat_api_errors(sA.clock.usage_file, usage)   # model-API errors: transient vs unrecovered (api_errors.py)
    out.update(revision=REVISION, seed=R.lv["seed"], player_mode=PLAYER_MODE, started=E["started"],
               meter_error=bool(E.get("meter_error") or (PLAYER_MODE == "model" and
                                (not usage.get("epoch") or usage.get("requests", 0) < 1))), max_lag_s=MAX_LAG_S,
               sim_error=E["reason"] == "error",
               proxy_error=api["api_failure"],
               rate_limit_retries=usage.get("rate_limit_retries", 0),
               transient_api_errors=api["transient_api_errors"], unrecovered_api_errors=api["unrecovered_api_errors"],
               timing_policy=TIMING_POLICY, timing_invalid=False)
    replay_ok = (out["graded_ready"] and out.get("deterministic") and out.get("replay_joint_targets_equal")
                 and out.get("replay_score") == list(R.score))
    out["replay_error"] = bool(out.get("finalize_error") or not replay_ok)
    out["valid_trial"] = bool(replay_ok and not any(out[k] for k in
                             ("replay_error", "sim_error", "meter_error", "proxy_error", "timing_invalid")))
    out["technical_failure"] = not out["valid_trial"]
    out["success"] = bool(won() and out["valid_trial"])
    tmp = os.path.join(DATA, "final.json.tmp")
    with open(tmp, "w") as f:
        json.dump(out, f, default=_jsonable)
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
                       "slowdown": SLOWDOWN, "seed": R.lv["seed"], "revision": REVISION,
                       "source_sha": wc.source_sha()}, f)
        # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads the episode log; same joint targets)
        np.savez(os.path.join(DATA, "trajectory.npz"), actions=np.asarray(acts, dtype=np.float64), control_dt=DT,
                 level=LEVEL, seed=R.lv["seed"], slowdown=SLOWDOWN)
        out_p = os.path.join(DATA, "replay_check.json")
        t0 = time.time()
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "replay.py"),
                        os.path.join(DATA, "episode.jsonl"), str(k_end), out_p], check=True,
                       timeout=float(os.environ.get("RCB_REPLAY_TIMEOUT_S", "300")), env=dict(os.environ))
        with open(out_p) as f:
            rp = json.load(f)
        act_sha = hashlib.sha256(np.ascontiguousarray(acts, dtype=np.float64).tobytes()).hexdigest()
        E["extra"] = {"n_actions": int(len(acts)),
                      "deterministic": (rp["state_sha"] == live_sha and rp["actions_sha"] == act_sha and rp["steps"] == k_end
                                        and rp.get("winner") == R.winner),
                      "replay_score": rp["score"], "replay_steps": rp["steps"], "replay_n_acts": rp["n_acts"],
                      "replay_joint_targets_equal": rp["actions_sha"] == act_sha,
                      "replay_wall_s": round(time.time() - t0, 1), "live_score": live_score}
        log({"ev": "replay", **E["extra"]})
        with COND:                              # grading readiness is independent of the optional video
            E["finalized"] = True
            write_final()
        try:
            if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
                subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_video.py"),
                                os.path.join(DATA, "trajectory.json"), os.path.join(DATA, "replay.mp4")],
                               check=True, timeout=float(os.environ.get("RCB_VIDEO_TIMEOUT_S", "120")))
                E["extra"]["video"] = True
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            E["extra"]["video"] = False
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["extra"]["finalize_error"] = repr(exc)[:300]
    E["finalized"] = True
    write_final()


def end(reason: str) -> None:
    """With COND held."""
    if E["finalizing"]:
        return
    E["reason"] = reason
    E["final_obs"] = {"done": True, "reason": reason, "score": {"you": R.score[0], "opponent": R.score[1]},
                      "won": won(), "points": R.points, "note": "the match is over"}
    E["finalizing"] = True
    _close_segment()
    for s in SEATS.values():
        for it in s.queue:
            it["dropped"] = True
        s.queue.clear()
    log({"ev": "end", "reason": reason, "score": R.score, "k_end": R.k})
    bc_event("end", reason=reason)
    write_final()
    COND.notify_all()
    threading.Thread(target=finalize, daemon=True).start()


# ---------------------------------------------------------------------------------------------- the sim thread
def _close_segment() -> None:
    if SIM["seg_start"] is not None and SIM.get("seg_last") is not None:   # anchor -> start of the segment's last step
        SIM["run_wall_s"] += SIM["seg_last"] - SIM["seg_start"]
    SIM["seg_start"] = SIM["seg_last"] = None
    SIM["anchor"] = None


def _apply_due() -> float:
    """At the start of a control step (COND held): every act due at this step takes effect, in arrival order (a later
    one replaces an earlier one, exactly as in the replay). Waits (releasing COND) for a plan not yet back from the
    planner process. Returns the wall seconds spent waiting."""
    waited = 0.0
    for name, s in SEATS.items():
        due = [it for it in s.queue if it["k_e"] == R.k]
        for it in due:
            t0 = time.monotonic()
            got = COND.wait_for(lambda: it["act_id"] in PLAN_RESULTS or E.get("planner_dead")
                                or E["final_obs"] is not None, timeout=PLAN_TIMEOUT_S)
            w = time.monotonic() - t0
            waited += w
            if E["final_obs"] is not None:
                return waited
            if not got or E.get("planner_dead") and it["act_id"] not in PLAN_RESULTS:
                raise RuntimeError(f"stroke planner did not answer act {it['act_id']} ({E.get('planner_dead')})")
            pr = PLAN_RESULTS.pop(it["act_id"])
            dec = it["dec"]
            t1 = time.monotonic()
            src = "planner"
            if pr.get("status") == "ok" and pr["key"] == wc.state_key(R):
                info = wc.install(R, pr["res"])
            else:                                   # never expected: the copy diverged; plan here (exact, but slow)
                SIM["plan_mismatch"] += 1; SIM["plan_inline"] += 1
                src = f"inline ({pr.get('status')}{': ' + pr['error'] if pr.get('error') else ''})"
                info = wc.apply_inline(R, dec)
            if dec["type"] != "none":
                SIM["plan_ms"].append(float(pr.get("plan_ms") or 0.0))
                SIM["fork_ms"].append(float(pr.get("fork_ms") or 0.0))
                SIM["plan_wait_ms"].append(round(w * 1e3, 2))
            s.last_act_info = info
            it["k_effect"] = R.k
            it["info"] = info if info is not None else {"stroke": "cleared: the arm returns to the ready pose"}
            it["wall_effect"] = time.monotonic()
            s.act_delay_steps.append(R.k - it["k_arrive"])
            s.act_wall_s.append(it["wall_effect"] - it["wall_arrive"])
            log({"ev": "act_applied", "seat": name, "k": R.k, "decision": dec, "k_arrive": it["k_arrive"],
                 "k_queued": it["k_queued"], "act_id": it["act_id"], "plan_source": src,
                 "plan_ms": pr.get("plan_ms"), "fork_ms": pr.get("fork_ms"), "plan_wait_ms": round(w * 1e3, 2),
                 "install_ms": round((time.monotonic() - t1) * 1e3, 2),
                 "model_call": it["model_call"], "obs_ids": it["obs_ids"]})
            it["done"] = True
            s.queue.remove(it)
    return waited


def _frame_extras() -> None:
    if R.hist and R.hist[-1]["k"] == R.k and "wall_mono" not in R.hist[-1]:
        R.hist[-1]["wall_mono"] = time.monotonic()
        R.hist[-1]["leg_id"] = len(R.legs) - 1


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
            waited = _apply_due()
            if not running():
                SIM["lates"][-1] = max(SIM["lates"][-1], time.monotonic() - due)
                continue
            t1 = time.monotonic()
            pre_hist = list(R.hist)
            n, pts, res = R.rt_advance(1)
            t2 = time.monotonic()
            _frame_extras()
            SIM["lates"][-1] = max(SIM["lates"][-1], t2 - due)
            SIM["step_ms"].append((t2 - t1) * 1000.0)
            if (t2 - t0) > PERIOD or (t0 - due) > PERIOD:      # a slow or late step: keep the worst ones for the record
                SIM.setdefault("slow", []).append({"k": R.k, "late_ms": round((t0 - due) * 1000, 1),
                                                   "apply_ms": round((t1 - t0) * 1000, 1),
                                                   "plan_wait_ms": round(waited * 1000, 1),
                                                   "step_ms": round((t2 - t1) * 1000, 1), "acts": nq,
                                                   "leg": R.leg.get("state")})
                SIM["slow"] = sorted(SIM["slow"], key=lambda e: -(e["late_ms"] + e["apply_ms"] + e["step_ms"]))[:8]
            SIM["run_steps"] += n
            if BC is not None:                     # (a point's last frame is the newest snapshot before its end)
                if not pts:
                    BC.after_step(R)
                for p in pts:
                    BC.event("point", R.k, score=list(R.score), winner=p.get("winner"), how=p.get("how"),
                             n=len(R.points))
            for s in SEATS.values():
                s.news["results"] += list(res)
                s.news["points"] += list(pts)
            if res:
                log({"ev": "shot", "shots": [{k: r.get(k) for k in ("returned", "summary", "speed_out", "offcentre")}
                                             for r in res]})
            if pts:
                log({"ev": "point", "points": pts})
                E["points_wall"].append({"point": len(R.points), "wall": wall(), "k": R.k})
                E["review_hist"] = pre_hist or None       # the finished point's last frames, for review observations
                for s in SEATS.values():               # a command does not carry over to the next point
                    for it in s.queue:
                        it["dropped"] = True
                        s.dropped_acts += 1
                    s.queue.clear()
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
RENDER = RenderProcess()      # a separate process: MuJoCo rendering holds the GIL


def ensure_frame() -> None:
    """Before the world's first step there is no camera snapshot yet (display only; not part of the physics state)."""
    if not R.hist:
        R.hist.append({"k": R.k, "t": R.t_since_launch(), "qpos": R.s.d.qpos.copy(), "sh": R.s.sh_p, "shv": R.s.sh_v,
                       "opp": R.opp_xy().copy(), "leg_id": len(R.legs) - 1, "wall_mono": time.monotonic()})


def snapshots() -> list[dict]:
    """With COND held: the 4 camera frames 60 ms apart ending at the newest one (copies; the match keeps one snapshot
    per camera frame, every 2 control steps). During a review: the finished point's last frames."""
    ensure_frame()
    hist = list(E["review_hist"] if E["awaiting_review"] and E["review_hist"] else R.hist)
    out = [dict(hist[max(0, len(hist) - 1 - b)]) for b in reversed(match.Match.VIEW_BACK)]
    for sn in out:
        sn.setdefault("leg_id", None); sn.setdefault("wall_mono", time.monotonic())
    return out


# ---------------------------------------------------------------------------------------------- observations
def now_state(seat: Seat) -> dict:
    """With COND held. What the player knows without looking: score, time, what it heard, its robot, its command."""
    ensure_frame()
    o = R.decision_observation()
    o.pop("view_times", None)
    o["t_sim"] = round(R.k * DT, 4)
    o["step"] = R.k
    ph = 0.0                            # how far into the current control step's wall slot we are (0..1; 0 while frozen)
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
    elif R.leg["state"] == "to_opp":
        o["heard"] = o["heard"] + [{"event": "you hit the shuttle",
                                    "t": round((R.leg["hit"]["k"] - R.leg["launch"]) * DT, 3)
                                    if "k" in R.leg.get("hit", {}) else None}]
    la = getattr(R, "_last_act", None)
    active = R.plan_j < len(R.plan)
    k_hit = la.get("k_hit") if la else None
    o["command"] = ({"contact_in_s": round((k_hit - R.k) * DT, 3) if k_hit is not None and k_hit >= R.k else "passed",
                     "phase": "approach" if k_hit is not None and R.k < k_hit else "follow_through",
                     "pos": la.get("racket_pos"), "normal": la.get("racket_normal"), "vel": la.get("racket_vel"),
                     "stroke": la.get("stroke")}
                    if active and la else "none (the robot returns to / holds the ready pose, the base to its home)")
    pend = [it for it in seat.queue if not it.get("done")]
    if pend:
        o["pending_act"] = {"act_id": pend[-1]["act_id"], "takes_effect_at_step": pend[-1]["k_e"]}
    return o


IMAGE_LAYOUT = ("2 rows x 4 columns. Row 1: camera behind and above your baseline looking down the court; row 2: camera "
                "at the side of the court (x < 0) looking along +x: your half (y < 0) is on the right, the opponent's on "
                "the left. Columns: four camera frames 60 ms apart, oldest left, latest right; each tile is stamped with "
                "its control step k and its time t since the shuttle was played (see view_steps / view_times). The "
                "shuttle is drawn enlarged: an orange cork (12 cm ball, its centre is the shuttle's position) with a "
                "white skirt behind it, cork first along its flight. Yellow marks every 1 m along the outside of the "
                "singles side lines (y = -6..6) and behind the base lines (x = -2, -1, 1, 2; none at x = 0); the "
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
        o["obs_age_sim_s"] = round((R.k - snaps[-1]["k"]) * DT, 4) if not E["awaiting_review"] else None
        o["obs_age_wall_s"] = round(time.monotonic() - snaps[-1]["wall_mono"], 6)
        o["render_wall_s"] = round(render_end - render_start, 6)
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


def validate_act(body: dict) -> dict | str:
    if body.get("type") == "none":
        return {"type": "none"}
    try:
        T = float(body["t"]); pos = [float(x) for x in body["pos"]]
        nrm = [float(x) for x in body["normal"]]; vel = [float(x) for x in body["vel"]]
    except Exception:  # noqa: BLE001
        return ("act needs T (s from when the act takes effect until contact), pos [x, y, z] (racket-head centre at "
                "contact), normal [nx, ny, nz] (string-face normal) and vel [vx, vy, vz] (head velocity at contact, "
                "m/s); or `act none`")
    if len(pos) != 3 or len(nrm) != 3 or len(vel) != 3 or not np.all(np.isfinite(pos + nrm + vel + [T])):
        return "pos, normal and vel must have 3 finite numbers each"
    if np.linalg.norm(nrm) < 1e-6:
        return "normal must be a non-zero vector"
    if not (0.0 < T <= 5.0):
        return "T must be in (0, 5.0] s from when the act takes effect"
    if not (abs(pos[0]) <= 3.4 and -7.5 <= pos[1] <= -0.3 and 0.2 <= pos[2] <= 3.0):
        return "pos out of range: |x| <= 3.4, -7.5 <= y <= -0.3, 0.2 <= z <= 3.0"
    if np.linalg.norm(vel) > 8.0:
        return "vel too large: |vel| <= 8 m/s"
    return {"type": "act", "t": T, "pos": pos, "normal": nrm, "vel": vel}


def gate() -> tuple[int, dict] | None:
    """With COND held: the calls act / wait need a started, running match."""
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
                 f"({PERIOD:.3f} s of wall time per 10 ms of game time); it does not wait for you. An act takes "
                 f"effect {LEAD_STEPS} control steps ({LEAD_STEPS * DT:.2f} s of game time) after it arrives",
                 "observation": obs}


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
         "render_ms": round(o["render_wall_s"] * 1e3, 2)})
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
            log({"ev": "refused_not_model", "seat": seat.name, "kind": "act", "rule_wait_s": round(rule_wait, 4)})
            return 429, {"refused": True, "error": "refused: no new completed model response since the previous act "
                         "whose tool call contains `game act`. Every act must be a model turn that itself runs "
                         "`game act ...`; a script looping over the game is not allowed."}
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
        k_q = R.k
        it = {"act_id": E["act_seq"], "model_call": model_call, "obs_ids": obs_ids, "dec": dec, "k_arrive": k_arr,
              "wall_arrive": w_arr, "k_queued": k_q, "k_e": k_q + LEAD_STEPS, "done": False, "dropped": False}
        pending = [p["act_id"] for s in SEATS.values() for p in s.queue if not p["done"] and not p["dropped"]]
        t_s = time.monotonic()
        snap = wc.snapshot(R)
        SIM["snap_ms"].append((time.monotonic() - t_s) * 1e3)
        seat.queue.append(it)
        seat.calls["act"] += 1; E["cur_point_calls"] += 1
        log({"ev": "call", "kind": "act", "seat": seat.name, "k_request": k_arr, "k_queued": k_q, "k_effect": it["k_e"],
             "rule_wait_s": round(rule_wait, 4), "decision": dec, "act_id": it["act_id"],
             "http_arrive_wall": round(entered - T0_MONO, 6), "lock_wait_s": lock_wait,
             "snapshot_ms": round(SIM["snap_ms"][-1], 2), "pending": pending,
             "model_call": it["model_call"], "obs_ids": obs_ids})
    PLANNER.submit({"op": "plan", "act_id": it["act_id"], "k_q": k_q, "k_e": it["k_e"], "snap": snap,
                    "pending": pending, "dec": dec})
    with COND:
        COND.wait_for(lambda: it["done"] or it["dropped"] or E["final_obs"] is not None,
                      timeout=PLAN_TIMEOUT_S + 60 + (LEAD_STEPS + 5) * PERIOD)
        out = {"call": "act", "act_id": it["act_id"], "lock_wait_s": round(lock_wait, 6),
               "t_sim_request": round(k_arr * DT, 4), "rule_wait_s": round(rule_wait, 4)}
        if it["done"]:
            info = it["info"]
            out["took_effect"] = {"step": it["k_effect"], "t_sim": round(it["k_effect"] * DT, 4),
                                  "steps_after_request": it["k_effect"] - k_arr,
                                  "wall_s_after_request": round(it["wall_effect"] - w_arr, 4)}
            if dec["type"] == "none":
                out["command"] = "cleared: the arm returns to the ready pose"
            else:
                out["stroke"] = {k: info.get(k) for k in ("stroke", "base", "n_swing_steps_available", "n_swing_steps",
                                                          "ik_residual", "blade_error_m", "normal_error_deg",
                                                          "speed_scale", "racket_vel_delivered", "T_from_now")}
        else:
            if it in seat.queue:
                seat.queue.remove(it)
                seat.dropped_acts += 1
            it["dropped"] = True
            PLAN_RESULTS.pop(it["act_id"], None)
            out["note"] = "act dropped before it took effect (the point ended first, or a service timeout)"
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
            E["review_hist"] = None
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


def do_oracle(seat: Seat, body: dict) -> tuple[int, dict]:
    """RCB_PLAYER_MODE=oracle only: the true state, and with {"advise": true} the privileged reference decision
    computed in the advisor process from an exact copy of the match."""
    if PLAYER_MODE != "oracle" or ADVISOR is None:
        return 403, {"error": "not available"}
    with COND:
        if E["final_obs"] is not None:
            return 200, E["final_obs"]
        st = {"k": R.k, "leg_id": len(R.legs) - 1, "leg_state": R.leg["state"], "leg_kind": R.leg["kind"],
              "launch": R.leg["launch"], "in_play": R.in_play(), "t_since_launch": R.t_since_launch(),
              "running": running(), "started": E["started"], "awaiting_review": E["awaiting_review"],
              "done": E["final_obs"] is not None, "lead_steps": LEAD_STEPS, "score": list(R.score),
              "sh_p": list(R.s.sh_p), "sh_v": list(R.s.sh_v)}
        snap = wc.snapshot(R) if body.get("advise") else None
    if snap is None:
        return 200, st
    t0 = time.monotonic()
    adv = ADVISOR.call({"op": "advise", "snap": snap}, ADVICE_TIMEOUT_S)
    with COND:
        E["n_oracle_advice"] += 1
        E["advice_ms"].append((time.monotonic() - t0) * 1e3)
        adv["k_reply"] = R.k
    log({"ev": "oracle_advice", **{k: adv.get(k) for k in ("k_snap", "k_reply", "leg_id", "t_hit", "pos", "normal",
                                                          "vel", "none", "advice_ms")}})
    return 200, {**st, "advice": adv}


SPEC = {
    "revision": REVISION, "player_mode": PLAYER_MODE,
    "protocol": "eai-standard-realtime/1.0",
    "simulator": "mujoco 3.3.7 (robot) + point-mass shuttle with quadratic drag",
    "robot": "franka-panda on an x-y sliding base + badminton racket",
    "base": {"max_speed_mps": match.BASE_VMAX, "max_accel_mps2": match.BASE_AMAX, "home_xy": [0.0, -4.0]},
    "match": {"win_points": match.WIN_POINTS, "two_point_lead_from": match.WIN_POINTS - 1, "cap_points": match.CAP_POINTS,
              "max_hits": match.MAX_HITS, "opponent_level": LEVEL, "first_player": "opponent",
              "serves": "the opponent serves every point, into your diagonal service court", "scoring": "rally point"},
    "timing": {"slowdown": SLOWDOWN, "control_dt_s": DT, "wall_s_per_control_step": PERIOD,
               "wall_s_per_game_s": SLOWDOWN, "wait_max_s": WAIT_MAX_S,
               "act_lead_steps": LEAD_STEPS, "act_lead_game_s": round(LEAD_STEPS * DT, 4),
               "act_lead_wall_s": round(LEAD_STEPS * PERIOD, 4),
               "rule": f"the world runs on its own clock at 1/{SLOWDOWN:g} of real speed (game time = wall time / "
                       f"{SLOWDOWN:g}); it does not wait for your calls or your thinking. An act queued at control "
                       f"step k takes effect at step k + {LEAD_STEPS} (the stroke controller's planning time: at least "
                       f"{PLAN_LEAD_S:g} s of wall time); the robot keeps its current command until then"},
    "decision_rule": ("program play: your own program may observe and act without a new model response; "
                      "one act in flight at a time" if os.environ.get("RCB_ACT_RULE") == "program" else
                      "each act needs a new completed model response containing a game act tool call"),
    "review": ("after each point the world stays frozen until `game ready WHY PLAN`; recorded, not scored"
               if REVIEW else "off"),
    "calls": {"start": "start the match (the world is frozen until then); returns the first observation",
              "observe": "the newest camera frames (2 x 4), what was heard, time, your robot and command",
              "act": "{'type':'act','t':T_from_effect,'pos':[x,y,z],'normal':[nx,ny,nz],'vel':[vx,vy,vz]} (racket "
                     "state at contact) or {'type':'none'}",
              "wait": "{'dt': game seconds}"},
    "seats": sorted(SEATS),
    "cameras": [dict(c, fovy_deg=45.0, tile_px=[480, 360], focal_px=434.6, principal_point_px=[240, 180],
                     image_right="forward x up") for c in match.Match.cam_info()],
    "image": "2 rows (behind, side) x 4 columns (camera frames 60 ms apart, oldest left); tile 480 x 360",
    "world": "floor z = 0; singles court |x| <= 2.59, |y| <= 6.70 (lines in); net plane y = 0, top z = 1.524 m, posts "
             "at x = +-3.05; your half y < 0. Robot base home (0, -4.0), base speed <= 6 m/s",
    "shuttle": {"model": "point mass, gravity 9.81 + quadratic drag: dv/dt = g - K |v| v", "K_per_m": round(match.K_DRAG, 4),
                "terminal_speed_mps": match.V_TERM, "bounce": "none: the rally ends when it reaches the floor"},
}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, obj: dict) -> None:
        b = json.dumps(obj, default=_jsonable).encode()
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
                return self._send(200, {"score": {"you": R.score[0], "opponent": R.score[1]}, "calls": s.calls,
                                        "t_sim": round(R.k * DT, 4), "step": R.k, "wall_s": wall(),
                                        "slowdown": SLOWDOWN, "running": running(),
                                        "awaiting_review": E["awaiting_review"], "started": E["started"],
                                        "done": E["final_obs"] is not None, "reason": E["reason"],
                                        "last_point": R.points[-1] if R.points else None,
                                        "last_shot": ({k: R.results[-1].get(k) for k in ("returned", "summary", "speed_out")}
                                                      if R.results else None)})
        return self._send(404, {"error": "no such endpoint (GET /spec /status; POST /start /observe /act /wait /ready)"})

    def do_POST(self):
        threading.current_thread().request_entered = time.monotonic()
        kind = self.path.strip("/")
        if kind not in ("observe", "act", "wait", "ready", "start", "oracle"):
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
                  "ready": lambda: do_ready(seat, body), "oracle": lambda: do_oracle(seat, body)}[kind]
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
    log({"ev": "start", "level": LEVEL, "seed": R.lv["seed"], "protocol": "wallclock",
         "slowdown": SLOWDOWN, "control_dt": DT, "period_s": PERIOD, "plan_lead_s": PLAN_LEAD_S,
         "plan_lead_steps": LEAD_STEPS, "decision_rule": SEATS["A"].clock.rule,
         "rule_wait_cap_s": RULE_WAIT_S, "revision": REVISION, "player_mode": PLAYER_MODE,
         "max_lag_s": MAX_LAG_S, "timing_policy": TIMING_POLICY, "source_sha": wc.source_sha()})
    if BroadcastLog is not None:
        BC = BroadcastLog(every=2, sport="badminton", mode="single", slowdown=SLOWDOWN, dt=DT, level=LEVEL,
                          seed=R.lv["seed"], nq=int(R.s.m.nq), players={"A": "you", "B": "opponent"})
        with COND:
            ensure_frame()
            BC.snapshot(R.hist[-1], force=True)     # the scene before the first serve
    write_final()
    threading.Thread(target=guarded_sim_loop, daemon=True).start()
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    print(f"match service ready (wall clock, slowdown x{SLOWDOWN:g}, act lead {LEAD_STEPS} steps)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()
