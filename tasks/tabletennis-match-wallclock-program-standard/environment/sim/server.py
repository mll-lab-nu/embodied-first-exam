"""Wall-clock interactive sim service for tabletennis-match-l1-wallclock-x*-interactive (scheme B, slowed world).

The world runs ON ITS OWN CLOCK: a background thread steps the match at CONTROL_DT = 10 ms of simulated time per
control step and paces every step to CONTROL_DT x SLOWDOWN of wall time (time.monotonic schedule from an anchor, so
there is no drift accumulation). sim time = wall time / SLOWDOWN. Nothing pauses the world while the model thinks:
its thinking, tool calls, network and API latency all take real time. If the computer cannot keep up (a step, or the
stroke planning of an `act`, takes longer than its wall slot) the thread catches up as fast as it can and the lateness
is recorded (`sim_lag` in final.json); it never silently slows the world down.

Frozen (free) time, as in the lock-step protocol: until `game start`, and after each point until `game ready WHY PLAN`.

Calls (the server runs by itself; clients pull the state and push commands):
  observe  the newest 2 cameras x 4 frames (40 ms apart) + what was heard, at the sim time of the request. Rendered
           from snapshots (the match keeps one per camera frame) in a separate render process with its own model copy,
           renderer and MjData (render_worker.py; MuJoCo's render call holds the GIL, so a thread would stall the
           physics thread). Reports t_sim, step_phase and the wall time.
  act      a new paddle state at contact (scheme B, same validation). Queued per seat; it takes effect at the next
           control step after it arrives (the replaced command keeps executing until then); the reply comes once it
           has taken effect and gives the exact step. Program play (RCB_ACT_RULE=program): the agent's own
           program may act without a new model response; one act in flight per seat (think_clock.py).
  wait DT  block until sim time + DT (convenience).
  ready    after each point: the review; the world restarts only then.
  status / spec.

Seats: every call may name a seat ("seat" in the body or the X-Seat header); this task has one seat, "A". Each seat
has its own command queue, model-call rule (think proxy usage file) and news (shot results, finished points). A duel
adds a second seat here.

Evidence (/data): episode.jsonl (every call: wall time, sim step, payload; every applied act with its effect step),
final.json, trajectory.json, replay.mp4. On episode end (or SIGUSR1 from the collect hook) a FRESH PROCESS
(replay.py) re-simulates the match from the logged (sim step, act) list only; the replayed score and final state hash
must equal the live ones.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import match  # noqa: E402
import rally  # noqa: E402
from think_clock import ThinkClock, read_usage, MeterError  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402
from render_worker import RenderProcess  # noqa: E402
try:                                            # spectator broadcast log (never read back; see broadcast_log.py)
    from broadcast_log import BroadcastLog  # noqa: E402
except ImportError:  # pragma: no cover
    BroadcastLog = None

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
REVISION = match.REVISION
PLAYER_MODE = os.environ.get("RCB_PLAYER_MODE", "model")
if PLAYER_MODE not in ("model", "oracle"):
    raise ValueError("RCB_PLAYER_MODE must be model or oracle")
# Revision 3 reports scheduling delays without a lateness disqualification threshold.
MAX_LAG_S = None
TIMING_POLICY = "report_only"
DT = rally.CONTROL_DT
PERIOD = DT * SLOWDOWN                                    # wall seconds per control step

COND = threading.Condition(threading.RLock())   # guards the match R and everything in E / SIM / seats
R = match.Match(LEVEL)
T0_WALL, T0_MONO = time.time(), time.monotonic()
E = {"started": False, "awaiting_review": False, "readying": False, "reviews": [], "reviewed_points": 0,
     "final_obs": None, "starting": False, "obs_seq": 0, "act_seq": 0, "finalizing": False, "finalized": False, "reason": None, "extra": {},
     "calls_per_point": [], "cur_point_calls": 0, "points_wall": []}
SIM = {"anchor": None, "lates": [], "step_ms": [], "plan_ms": [], "run_wall_s": 0.0, "run_steps": 0,
       "seg_start": None, "segments": 0, "k_start": None}


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
        self.act_delay_steps: list[int] = []      # control steps between an act's arrival (before the call rule) and its effect
        self.act_wall_s: list[float] = []         # wall time from the act's arrival (incl. the call-rule wait) to its effect
        self.dropped_acts = 0                     # acts whose point ended before they took effect
        self.last_act_info = None


SEATS = {"A": Seat("A", os.environ.get("THINK_USAGE_FILE", os.path.join(DATA, "think_usage.json")))}


def source_sha():
    from replay import source_sha as fingerprint
    return fingerprint()


def wall() -> float:
    return round(time.monotonic() - T0_MONO, 4)


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 4), "wall": wall(), "step": R.k, **ev}, default=float) + "\n")


BC = None          # the spectator broadcast log (set in __main__)


def bc_frame(pts=()) -> None:
    """With COND held, after a control step: the broadcast frame (the point's last state if a point just ended)."""
    if BC is None:
        return
    last = R.review_hist[-1] if pts and getattr(R, "review_hist", None) else None
    BC.frame(R.k, last["qpos"] if last else R.s.d.qpos, force=bool(pts),
             o=round(last["opp_x"] if last else R.opp_x(), 4))
    for p in pts:
        BC.event("point", R.k, score=list(R.score), winner=p.get("winner"), how=p.get("how"), n=len(R.points))


def bc_event(ev: str, **fields) -> None:
    if BC is not None:
        BC.event(ev, R.k, score=list(R.score), **fields)


def won() -> bool:
    return R.winner == 0


def running() -> bool:
    return E["started"] and not E["awaiting_review"] and E["final_obs"] is None and not R.done


# ---------------------------------------------------------------------------------------------- lag statistics
def lag_stats() -> dict:
    L = np.asarray(SIM["lates"], float)
    S = np.asarray(SIM["step_ms"], float)
    P = np.asarray(SIM["plan_ms"], float)
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
                   late_p50_s=round(float(np.percentile(L, 50)), 5), late_p99_s=round(float(np.percentile(L, 99)), 4),
                   late_max_steps=round(float(L.max() / PERIOD), 2),
                   frac_steps_late_over_1_period=round(float(np.mean(L > PERIOD)), 4),
                   frac_steps_late_over_10ms=round(float(np.mean(L > 0.010)), 4))
    if len(S):
        out.update(step_ms_mean=round(float(S.mean()), 3), step_ms_p99=round(float(np.percentile(S, 99)), 3),
                   step_ms_max=round(float(S.max()), 3))
    if SIM.get("slow"):
        out["slowest_steps"] = SIM["slow"]
    if len(P):
        out.update(plan_ms_mean=round(float(P.mean()), 2), plan_ms_max=round(float(P.max()), 2), n_plans=int(len(P)))
    return out


def write_final() -> None:
    with COND:
        _write_final_locked()


def _write_final_locked() -> None:
    sA = SEATS["A"]
    n_calls = sum(sA.calls.values())
    rw = sA.rule_wait_s
    out = {"level": LEVEL, "points_for": R.score[0], "points_against": R.score[1], "win_points": match.WIN_POINTS,
           "won": won(), "returns": int(sum(r["returned"] for r in R.results)), "our_legs": R.n_our_legs, "our_shots": R.n_our_shots,
           "winner": {0: "you", 1: "opponent"}.get(R.winner),
           "done": R.done or E["reason"] is not None, "reason": E["reason"], "finalized": E["finalized"],
           "protocol": "wallclock", "slowdown": SLOWDOWN, "control_dt": DT,
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
           "steps": R.k, "physics_steps": int(R.s.sim_steps_total), "elapsed_s": round(time.time() - T0_WALL, 1),
           "points": R.points, "points_wall": E["points_wall"], "results": R.results, "shots": R.shots,
           "opponent": [l.get("opp") for l in R.legs if l.get("opp")]}
    out.update(E["extra"])
    out["graded_ready"] = E["finalized"]
    usage = read_usage(sA.clock.usage_file)
    api = seat_api_errors(sA.clock.usage_file, usage)   # model-API errors: transient vs unrecovered (api_errors.py)
    out.update(revision=REVISION, seed=R.lv["seed"], player_mode=PLAYER_MODE, started=E["started"],
               meter_error=bool(E.get("meter_error") or (PLAYER_MODE == "model" and
                                (not usage.get("epoch") or usage.get("requests", 0) < 1))), max_lag_s=MAX_LAG_S,
               sim_error=E["reason"] == "error", proxy_error=api["api_failure"],
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
        json.dump(out, f, default=float)
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
            json.dump({"actions": acts.tolist(), "level": LEVEL, "control_dt": DT, "serves": R.serve_ids,
                       "slowdown": SLOWDOWN, "seed": R.lv["seed"], "revision": REVISION, "source_sha": source_sha()}, f)
        # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads the JSON; both hold the same actions)
        np.savez(os.path.join(DATA, "trajectory.npz"), actions=np.asarray(acts, dtype=np.float64), control_dt=DT,
                 level=LEVEL, seed=R.lv["seed"], slowdown=SLOWDOWN)
        out_p = os.path.join(DATA, "replay_check.json")
        t0 = time.time()
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "replay.py"),
                        os.path.join(DATA, "episode.jsonl"), str(k_end), out_p], check=True,
                       timeout=float(os.environ.get("RCB_REPLAY_TIMEOUT_S", "300")),
                       env=dict(os.environ))
        with open(out_p) as f:
            rp = json.load(f)
        act_sha = hashlib.sha256(np.ascontiguousarray(acts, dtype=np.float64).tobytes()).hexdigest()
        E["extra"] = {"n_actions": int(len(acts)), "deterministic": rp["state_sha"] == live_sha and rp["actions_sha"] == act_sha and rp["steps"] == k_end,
                      "replay_score": rp["score"], "replay_steps": rp["steps"], "replay_n_acts": rp["n_acts"],
                      "replay_joint_targets_equal": rp["actions_sha"] == act_sha,
                      "replay_wall_s": round(time.time() - t0, 1), "live_score": live_score}
        log({"ev": "replay", **E["extra"]})
        # Grading readiness is independent of optional video rendering.
        with COND:
            E["finalized"] = True
            write_final()
        try:
            if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
                subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "render_video.py"),
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
    bc_event("end", reason=reason, winner={0: "you", 1: "opponent"}.get(R.winner))
    write_final()
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
            if dec["type"] == "none":
                R.rt_clear()
                info = {"stroke": "cleared: the arm returns to the ready pose"}
            else:
                info = R.rt_act(dec["t"], dec["pos"], dec["normal"], dec["vel"])
                SIM["plan_ms"].append((time.monotonic() - t0) * 1000.0)
            s.last_act_info = info
            it["k_effect"] = R.k
            it["info"] = info
            it["wall_effect"] = time.monotonic()
            s.act_delay_steps.append(R.k - it["k_arrive"])
            s.act_wall_s.append(it["wall_effect"] - it["wall_arrive"])
            log({"ev": "act_applied", "seat": name, "k": R.k, "decision": dec, "k_arrive": it["k_arrive"],
                 "plan_ms": round((time.monotonic() - t0) * 1000.0, 2), "act_id": it["act_id"],
                 "model_call": it["model_call"], "obs_ids": it["obs_ids"]})
            it["done"] = True
        s.queue.clear()


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
            _apply_queued()
            t1 = time.monotonic()
            n, pts, res = R.rt_advance(1)
            t2 = time.monotonic()
            SIM["lates"][-1] = max(SIM["lates"][-1], t2 - due)
            if R.hist and R.hist[-1]["k"] == R.k:
                R.hist[-1]["wall_mono"] = t2
            SIM["step_ms"].append((t2 - t0) * 1000.0)
            if (t2 - t0) > PERIOD or (t0 - due) > PERIOD:      # a slow or late step: keep the worst ones for the record
                SIM.setdefault("slow", []).append({"k": R.k, "late_ms": round((t0 - due) * 1000, 1),
                                                   "apply_ms": round((t1 - t0) * 1000, 1),
                                                   "step_ms": round((t2 - t1) * 1000, 1), "acts": nq})
                SIM["slow"] = sorted(SIM["slow"], key=lambda e: -(e["late_ms"] + e["apply_ms"] + e["step_ms"]))[:8]
            SIM["run_steps"] += n
            bc_frame(pts)
            for s in SEATS.values():
                s.news["results"] += list(res)
                s.news["points"] += list(pts)
            if res:
                log({"ev": "shot", "shots": [{k: r.get(k) for k in ("returned", "summary", "landing_x", "landing_y")}
                                             for r in res]})
            if pts:
                log({"ev": "point", "points": pts})
                E["points_wall"].append({"point": len(R.points), "wall": wall(), "k": R.k})
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
        R.hist.append({"k": R.k, "t": R.t_since_launch(), "qpos": R.s.d.qpos.copy(), "opp_x": R.opp_x(),
                       "leg_id": len(R.legs)-1, "wall_mono": time.monotonic()})


def snapshots() -> list[dict]:
    """With COND held: the 4 camera frames 40 ms apart ending at the newest one (copies; the match keeps one snapshot
    per camera frame, every 2 control steps)."""
    ensure_frame()
    hist = list(R.review_hist if E["awaiting_review"] and hasattr(R, "review_hist") else R.hist)
    return [dict(hist[max(0, len(hist) - 1 - b)]) for b in reversed(match.Match.VIEW_BACK)]


# ---------------------------------------------------------------------------------------------- observations
def now_state(seat: Seat) -> dict:
    """With COND held. What the player knows without looking: score, time, what it heard, its arm, its command."""
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
    o["ball_in_play"] = R.in_play() and R.leg["state"] in ("incoming", "to_opp", "opp_missed")
    o["ball_state"] = {"incoming": "coming to you", "to_opp": "going to the opponent",
                       "opp_missed": "going to the opponent", "done": "dead"}.get(R.leg["state"], R.leg["state"])
    if not R.in_play():
        o["serve_in_s"] = round(max(0.0, (R.leg["launch"] - R.k) * DT), 3)
    la = getattr(R, "_last_act", None)
    active = R.plan_j < len(R.plan)
    o["command"] = ({"contact_in_s": round(max(0, R.contact_k - R.k) * DT, 3),
                     "phase": "approach" if R.k < R.contact_k else "follow_through", "pos": la.get("paddle_pos"),
                     "normal": la.get("paddle_normal"), "vel": la.get("paddle_vel"), "stroke": la.get("stroke")}
                    if active and la else "none (the arm returns to / holds the ready pose)")
    return o


IMAGE_LAYOUT = ("2 rows x 4 columns. Row 1: camera behind your robot looking down the table; row 2: camera at the side. "
                "Columns: four camera frames 40 ms apart, oldest left, latest right; each tile is stamped with its time t "
                "since the current ball was played (see view_times). Yellow marks every 0.25 m along the table edges; "
                "the opponent is the red paddle on the far side. The side camera looks along +x: your robot is on the "
                "right.")


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
        o["obs_age_wall_s"] = round(time.monotonic() - snaps[-1]["wall_mono"], 6)
        o["render_wall_s"] = round(render_end - render_start, 6)
    return o


def take_news(seat: Seat) -> dict:
    """With COND held: shot results and finished points this seat has not been told yet."""
    out = {}
    res, pts = seat.news["results"], seat.news["points"]
    if res:
        out["your_shots"] = [{k: r.get(k) for k in ("returned", "summary", "speed_out")} for r in res]
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
        return ("act needs T (s from now until contact), pos [x, y, z] (blade centre at contact), normal [nx, ny, nz] "
                "(blade face normal) and vel [vx, vy, vz] (blade velocity at contact, m/s); or `act none`")
    if len(pos) != 3 or len(nrm) != 3 or len(vel) != 3 or not np.all(np.isfinite(pos + nrm + vel + [T])):
        return "pos, normal and vel must have 3 finite numbers each"
    if np.linalg.norm(nrm) < 1e-6:
        return "normal must be a non-zero vector"
    if not (0.0 < T <= 2.5):
        return "T must be in (0, 2.5] s from now"
    if not (abs(pos[0]) <= 1.2 and -2.5 <= pos[1] <= -0.5 and 0.0 <= pos[2] <= 1.2):
        return "pos out of range: |x| <= 1.2, -2.5 <= y <= -0.5, 0 <= z <= 1.2"
    if np.linalg.norm(vel) > 8.0:
        return "vel too large: |vel| <= 8 m/s"
    return {"type": "act", "t": T, "pos": pos, "normal": nrm, "vel": vel}


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
                 f"({PERIOD:.3f} s of wall time per 10 ms of game time); it does not wait for you",
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
         "obs_id": o["obs_id"], "view_steps": o["view_steps"], "k_reply": int(round(o["t_sim_at_reply"] / DT))})
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
            return 429, {"refused": True, "error": "refused: no new model call completed since the previous act. Every "
                         "act must be a model turn; a script looping over the game is not allowed."}
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
        it = {"act_id": E["act_seq"], "model_call": model_call, "obs_ids": obs_ids,
              "dec": dec, "k_arrive": k_arr, "wall_arrive": w_arr, "k_queued": R.k, "done": False, "dropped": False}
        seat.queue.append(it)
        seat.calls["act"] += 1; E["cur_point_calls"] += 1
        log({"ev": "call", "kind": "act", "seat": seat.name, "k_request": k_arr, "k_queued": R.k,
             "rule_wait_s": round(rule_wait, 4), "decision": dec, "act_id": it["act_id"],
             "http_arrive_wall": round(entered - T0_MONO, 6), "lock_wait_s": lock_wait,
             "model_call": it["model_call"], "obs_ids": obs_ids})
        COND.wait_for(lambda: it["done"] or it["dropped"] or E["final_obs"] is not None, timeout=60 + 5 * PERIOD)
        out = {"call": "act", "act_id": it["act_id"], "lock_wait_s": round(lock_wait, 6), "t_sim_request": round(k_arr * DT, 4), "rule_wait_s": round(rule_wait, 4)}
        if it["done"]:
            info = it["info"]
            out["took_effect"] = {"step": it["k_effect"], "t_sim": round(it["k_effect"] * DT, 4),
                                  "steps_after_request": it["k_effect"] - k_arr,
                                  "wall_s_after_request": round(it["wall_effect"] - w_arr, 4)}
            if dec["type"] == "none":
                out["command"] = "cleared: the arm returns to the ready pose"
            else:
                out["stroke"] = {k: info.get(k) for k in ("stroke", "n_swing_steps_available", "n_swing_steps",
                                                          "ik_residual", "blade_error_m", "normal_error_deg", "speed_scale", "paddle_vel_delivered",
                                                          "T_from_now")}
        else:
            if it in seat.queue:
                seat.queue.remove(it)
            it["dropped"] = True
            seat.dropped_acts += 1
            out["note"] = "act dropped before application (point ended or service timeout)"
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
    "protocol": "eai-standard-realtime/1.0", "simulator": "mujoco 3.3.7", "robot": "franka-panda + paddle",
    "match": {"win_points": match.WIN_POINTS, "win_by": match.WIN_BY, "cap_points": match.CAP_POINTS,
              "expedite_returns": match.EXPEDITE_RETURNS, "opponent_level": LEVEL,
              "serves": "the opponent serves every point; you always receive",
              "format": f"first to {match.WIN_POINTS}; from {match.WIN_POINTS-1}:{match.WIN_POINTS-1} lead by "
                        f"{match.WIN_BY}, up to {match.CAP_POINTS} (at {match.CAP_POINTS-1}:{match.CAP_POINTS-1} the "
                        "next point wins)"},
    "timing": {"slowdown": SLOWDOWN, "control_dt_s": DT, "wall_s_per_control_step": PERIOD,
               "wall_s_per_game_s": SLOWDOWN, "wait_max_s": WAIT_MAX_S,
               "rule": f"the world runs on its own clock at 1/{SLOWDOWN:g} of real speed (game time = wall time / "
                       f"{SLOWDOWN:g}); it does not wait for your calls or your thinking. An act takes effect at the "
                       "next control step after it arrives; the arm keeps its current command until then"},
    "decision_rule": ("program play: your own program may observe and act without a new model response; "
                      "one act in flight at a time" if os.environ.get("RCB_ACT_RULE") == "program" else
                      "each act needs a new completed model response containing a game act tool call"),
    "review": ("after each point the world stays frozen until `game ready WHY PLAN`; recorded, not scored"
               if REVIEW else "off"),
    "calls": {"observe": "the newest camera frames (2 x 4), heard bounces, time, your arm and command",
              "act": "{'type':'act','t':T_from_now,'pos':[x,y,z],'normal':[nx,ny,nz],'vel':[vx,vy,vz]} or {'type':'none'}",
              "wait": "{'dt': game seconds}"},
    "seats": sorted(SEATS),
    "cameras": [dict(c, fovy_deg=45.0, tile_px=[480, 360], focal_px=434.6, principal_point_px=[240, 180],
                     image_right="forward x up") for c in match.Match.CAM_INFO],
    "image": "2 rows (behind, side) x 4 columns (camera frames 40 ms apart, oldest left); tile 480 x 360",
    "world": "table top z = 0, |x| <= 0.7625, |y| <= 1.37, net y = 0 (top z = 0.1525); robot base (0, -1.75, 0) facing +y",
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
    log({"ev": "start", "level": LEVEL, "seed": R.lv["seed"], "serves": R.serve_ids, "protocol": "wallclock",
         "slowdown": SLOWDOWN, "control_dt": DT, "period_s": PERIOD, "decision_rule": SEATS["A"].clock.rule,
         "rule_wait_cap_s": RULE_WAIT_S, "revision": REVISION, "player_mode": PLAYER_MODE,
         "max_lag_s": MAX_LAG_S, "timing_policy": TIMING_POLICY, "source_sha": source_sha()})
    if BroadcastLog is not None:
        BC = BroadcastLog(every=2, sport="tabletennis", mode="single", slowdown=SLOWDOWN, dt=DT, level=LEVEL,
                          seed=R.lv["seed"], nq=int(R.s.m.nq), players={"A": "you", "B": "opponent"})
        bc_frame()                          # the scene before the first serve
    write_final()
    threading.Thread(target=guarded_sim_loop, daemon=True).start()
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    print(f"match service ready (wall clock, slowdown x{SLOWDOWN:g})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()
