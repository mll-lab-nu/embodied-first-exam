"""Two-seat wall-clock service of the tennis duel (program play); the single-player service (tennis match) for two.

The world (duel.Duel) runs ON ITS OWN CLOCK: a background thread steps it at 10 ms of game time per control step, each
paced to 10 ms x SLOWDOWN of wall time (monotonic schedule from an anchor; lateness is recorded, report only). It is
frozen before both players have started and after every point until both have handed in their review.

Per seat (http://sim:8000/A/... and /B/..., each reachable only from its own seat service):
  spec, status, observe   the seat's view in its own frame (observe: its 2 cameras x 4 frames, rendered in its own
                          render process);
  act                     a racket state at contact (T s after the act takes effect; optional base position), `none`
                          or `move` (the base's rest position), exactly as in the single-player task: an act is
                          accepted at the next control step (k_s) and takes effect LEAD steps later, its stroke planned
                          meanwhile in the seat's planner process from a snapshot of the seat's robot at k_s; `none` /
                          `move` take effect at the next step. One act in flight per seat (HTTP 429 busy). Program play
                          (RCB_ACT_RULE=program): the seat's own program may act without a new model response; a live,
                          metered model session is required (think_clock.py, one proxy per seat);
  wait DT                 block until game time + DT;
  start / ready           start: ready to play (the world runs when both have started; START_TIMEOUT_S after the first);
                          ready WHY PLAN: the review after each point (READY_TIMEOUT_S, else the missing seat forfeits).

Evidence (/data): episode.jsonl, final.json, trajectory.json/.npz (both robots' joint targets), replay_check.json (a
fresh process re-runs the match from the joint targets and must reproduce the score, the points and the final state
hash), replay.mp4 (optional), think_usage_{A,B}.json, think_calls_{A,B}.jsonl.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import duel  # noqa: E402
import tn  # noqa: E402
from think_clock import ThinkClock, read_usage, MeterError  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402
from render_worker import RenderProcess  # noqa: E402
from compute_worker import ComputeProcess  # noqa: E402
from server_fingerprint import fingerprint  # noqa: E402
try:                                            # spectator broadcast log (never read back; see broadcast_log.py)
    from broadcast_log import BroadcastLog  # noqa: E402
except ImportError:  # pragma: no cover
    BroadcastLog = None
BC = None                                       # the spectator broadcast log (set in __main__)


def bc_event(ev, **fields):
    if BC is not None:
        BC.event(ev, R.k, score=dict(R.score), **fields)

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("RCB_DATA", "/data"))
DATA.mkdir(parents=True, exist_ok=True)
SLOWDOWN = float(os.environ.get("SLOWDOWN", "20"))
if not np.isfinite(SLOWDOWN) or SLOWDOWN <= 0:
    raise ValueError("invalid SLOWDOWN")
DT = tn.CONTROL_DT
PERIOD = DT * SLOWDOWN
PLAN_LEAD_S = float(os.environ.get("WALLCLOCK_PLAN_LEAD_S", "0.5"))
LEAD = max(1, int(math.ceil(PLAN_LEAD_S / PERIOD - 1e-9)))
WAIT_MAX_S = 1.0
T_MAX_S = 5.0
REVIEW_MAX_CHARS = 2000
READY_TIMEOUT_S = float(os.environ.get("READY_TIMEOUT_S", "300"))
START_TIMEOUT_S = float(os.environ.get("START_TIMEOUT_S", "1800"))
SIDES = duel.SIDES
OTHER = duel.OTHER
REVIEW_PROMPT = ("Point over. Review it: `game ready \"WHY\" \"PLAN\"` (why it was won or lost; what you will change) "
                 f"within {READY_TIMEOUT_S:g} s of real time, or you forfeit the match. The world stays frozen until both "
                 "players have.")


SOURCE_SHA = fingerprint()
COND = threading.Condition(threading.RLock())
R = duel.Duel()
T0_WALL, T0_MONO = time.time(), time.monotonic()
E = {"phase": "prepare", "joined": {s: False for s in SIDES}, "ready": {s: False for s in SIDES},
     "deadline": None, "resume_at": None, "reason": None, "forfeit": None, "finalizing": False, "finalized": False,
     "errors": [], "reviews": [], "act_seq": 0, "op_seq": 0, "obs_seq": 0, "extra": {}, "video": False}
SIM = {"anchor": None, "lates": [], "run_steps": 0, "run_wall_s": 0.0, "seg_start": None, "segments": 0,
       "plan_wait_ms": [], "plan_cpu_ms": []}


class Seat:
    def __init__(self, name):
        self.name = name
        self.clock = ThinkClock(usage_file=str(DATA / f"think_usage_{name}.json"),
                                mode=os.environ.get(f"PLAYER_MODE_{name}", os.environ.get("RCB_PLAYER_MODE", "model")))
        self.decision_lock = threading.Lock()
        self.queue: list[dict] = []
        self.news = {"points": []}
        self.calls = {"observe": 0, "act": 0, "wait": 0}
        self.refused_not_model = 0
        self.refused_busy = 0
        self.dropped_acts = 0
        self.act_in_flight = False
        self.act_owner = None
        self.act_delay_steps: list[int] = []
        self.render = None
        self.planner = None


SEATS = {s: Seat(s) for s in SIDES}


def wall():
    return round(time.monotonic() - T0_MONO, 4)


def _jdef(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return str(x)


LOG_LOCK = threading.Lock()


def log(ev):
    with LOG_LOCK, open(DATA / "episode.jsonl", "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 4), "wall": wall(), "step": R.k, **ev}, default=_jdef) + "\n")


def running():
    return E["phase"] == "running" and not R.done


# ---------------------------------------------------------------------------------------------- final record
def _usage(s):
    return read_usage(SEATS[s].clock.usage_file)


def targets_sha():
    return hashlib.sha256(json.dumps({s: [q.tolist() for q in R.actions[s]] for s in SIDES}, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def write_final():
    with COND:
        score = dict(R.score)
        usage = {s: _usage(s) for s in SIDES}
        meter = {s: SEATS[s].clock.mode == "model" and (not usage[s].get("epoch") or not usage[s].get("requests"))
                 for s in SIDES}
        apis = {s: seat_api_errors(SEATS[s].clock.usage_file, usage[s]) for s in SIDES}   # model-API errors: transient vs unrecovered (api_errors.py)
        api = {s: apis[s]["api_failure"] for s in SIDES}   # unrecovered, or more than MAX_TRANSIENT_API_ERRORS
        if E.get("meter_error"):
            meter = {s: meter[s] or E["meter_error"] == s for s in SIDES}
        rp = E["extra"]
        tsha = targets_sha()
        replay_ok = bool(rp.get("state_sha") == R.state_sha() and rp.get("score") == score
                         and rp.get("targets_sha") == tsha and rp.get("steps") == R.k
                         and rp.get("source_sha") == SOURCE_SHA)
        # a match ends by its score, by the stated match limit (the player ahead wins; equal is a draw) or by a review
        # forfeit; all three are results, not technical failures
        complete = E["reason"] in ("match_over", "match_limit") or (E["reason"] == "ready_timeout" and E["forfeit"] in SIDES)
        valid = bool(E["finalized"] and complete and replay_ok and not E["errors"] and not any(meter.values())
                     and not any(api.values()))
        win = OTHER[E["forfeit"]] if E["forfeit"] else R.winner()     # no draws (duel.Duel.winner)
        L = np.asarray(SIM["lates"], float)
        out = dict(revision=duel.REVISION, source_sha=SOURCE_SHA, seed=duel.SEED, first_receiver=duel.FIRST_RECEIVER,
                   state_sha=R.state_sha(), targets_sha=tsha, forfeiting=E["forfeit"], slowdown=SLOWDOWN,
                   act_lead_steps=LEAD, score=score, winner=win if valid else None, reason=E["reason"],
                   match_limit=bool(R.limit_reached),
                   phase=E["phase"], finalized=E["finalized"], graded_ready=E["finalized"], valid_trial=valid,
                   technical_failure=not valid, timing_policy="report_only", timing_invalid=False, errors=E["errors"],
                   meter_error=meter, proxy_error=api,
                   transient_api_errors={s: apis[s]["transient_api_errors"] for s in SIDES},
                   unrecovered_api_errors={s: apis[s]["unrecovered_api_errors"] for s in SIDES}, deterministic=replay_ok, replay_score=rp.get("score"),
                   steps=R.k, points=R.points, hits=R.hits, reviews=E["reviews"], joined=E["joined"],
                   player_modes={s: SEATS[s].clock.mode for s in SIDES}, video=E["video"],
                   elapsed_s=round(time.time() - T0_WALL, 1),
                   seats={s: dict(attempts=SEATS[s].calls["act"] + SEATS[s].refused_busy + SEATS[s].refused_not_model,
                                  applied=SEATS[s].calls["act"] - SEATS[s].dropped_acts,
                                  refused=SEATS[s].refused_not_model, refused_busy=SEATS[s].refused_busy,
                                  dropped=SEATS[s].dropped_acts, observations=SEATS[s].calls["observe"],
                                  waits=SEATS[s].calls["wait"], act_delay_steps_max=max(SEATS[s].act_delay_steps, default=0))
                          for s in SIDES},
                   sim_lag=dict(late_max_s=float(L.max()) if len(L) else 0.0,
                                late_p99_s=float(np.percentile(L, 99)) if len(L) else 0.0,
                                run_steps=SIM["run_steps"], run_wall_s=round(SIM["run_wall_s"], 3), period_s=PERIOD,
                                plan_wait_ms_max=max(SIM["plan_wait_ms"], default=0.0),
                                plan_cpu_ms_max=max(SIM["plan_cpu_ms"], default=0.0)))
        tmp = DATA / "final.json.tmp"
        tmp.write_text(json.dumps(out, default=_jdef))
        tmp.replace(DATA / "final.json")


def finalize():
    try:
        with COND:
            payload = dict(A=[q.tolist() for q in R.actions["A"]], B=[q.tolist() for q in R.actions["B"]],
                           seed=duel.SEED, first_receiver=duel.FIRST_RECEIVER, source_sha=SOURCE_SHA,
                           revision=duel.REVISION, slowdown=SLOWDOWN)
        (DATA / "trajectory.json").write_text(json.dumps(payload))
        # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads the JSON; same joint targets)
        np.savez(DATA / "trajectory.npz", A=np.asarray(payload["A"], dtype=np.float64).reshape(-1, 9),
                 B=np.asarray(payload["B"], dtype=np.float64).reshape(-1, 9), seed=duel.SEED,
                 first_receiver=duel.FIRST_RECEIVER, slowdown=SLOWDOWN, control_dt=DT)
        subprocess.run([sys.executable, str(HERE / "replay.py"), str(DATA)], check=True,
                       timeout=float(os.environ.get("RCB_REPLAY_TIMEOUT_S", "600")))
        E["extra"] = json.loads((DATA / "replay_check.json").read_text())
        log({"ev": "replay", **{k: E["extra"].get(k) for k in ("score", "steps", "state_sha")}})
        # the optional video before grading readiness (as in the table-tennis duel), bounded by its timeout
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
            try:
                subprocess.run([sys.executable, str(HERE / "replay.py"), str(DATA), "--video"], check=True,
                               timeout=float(os.environ.get("RCB_VIDEO_TIMEOUT_S", "300")))
                E["video"] = True
            except Exception as exc:  # noqa: BLE001
                log({"ev": "video_error", "error": repr(exc)[:200]})
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["errors"].append({"where": "replay", "error": repr(exc)[:300]})
    with COND:
        E["finalized"] = True
        write_final()
        COND.notify_all()


def end(reason, forfeiting=None):
    """With COND held."""
    if E["finalizing"]:
        return
    E["reason"], E["forfeit"], E["finalizing"] = reason, forfeiting, True
    _close_segment()
    E["phase"] = "over"
    _drop_queues(count=False)
    log({"ev": "end", "reason": reason, "forfeiting": forfeiting, "score": R.score, "k_end": R.k})
    bc_event("end", reason=reason, forfeiting=forfeiting)
    write_final()
    COND.notify_all()
    threading.Thread(target=finalize, daemon=True).start()


def failure(where, exc, seat=None):
    with COND:
        E["errors"].append({"where": where, "error": repr(exc)[:300]})
        if isinstance(exc, MeterError) and seat:
            E["meter_error"] = seat
        log({"ev": "error", "where": where, "error": repr(exc)[:300]})
        end("technical_error")


# ---------------------------------------------------------------------------------------------- the world thread
def _close_segment():
    if SIM["seg_start"] is not None and SIM.get("seg_last") is not None:
        SIM["run_wall_s"] += SIM["seg_last"] - SIM["seg_start"]
    SIM["seg_start"] = SIM["seg_last"] = None
    SIM["anchor"] = None


def _due(k):
    a_wall, a_k = SIM["anchor"]
    return a_wall + (k + 1 - a_k) * PERIOD


def _op(ev):
    E["op_seq"] += 1
    log({**ev, "op": E["op_seq"]})


def _drop_queues(count):
    for s in SEATS.values():
        for it in s.queue:
            it["dropped"] = True
            if count:
                s.dropped_acts += 1
            log({"ev": "act_dropped", "seat": s.name, "act_id": it["act_id"], "reason": "the point ended"})
        s.queue.clear()


def _plan_job(seat, it, snap):
    t0 = time.monotonic()
    try:
        res, cpu = seat.planner.call(("plan", snap, LEAD, it["dec"]))
        err = None
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        res, cpu, err = None, 0.0, repr(exc)[:300]
    with COND:
        it["result"], it["error"], it["plan_cpu_s"] = res, err, cpu
        it["plan_wall_s"] = time.monotonic() - t0
        COND.notify_all()


def _process_commands():
    """At the start of a control step, per seat in order (as in the single-player service)."""
    for name in SIDES:
        s = SEATS[name]
        while s.queue:
            it = s.queue[0]
            dec = it["dec"]
            if it["state"] == "planning":
                if R.k < it["k_effect"]:
                    break
                if it["result"] is None and it["error"] is None:
                    t0 = time.monotonic()
                    COND.wait_for(lambda: it["result"] is not None or it["error"] is not None or E["finalizing"],
                                  timeout=60)
                    SIM["plan_wait_ms"].append((time.monotonic() - t0) * 1000.0)
                    if E["finalizing"]:
                        return
                if it["error"] is not None or it["result"] is None:
                    raise RuntimeError(f"stroke planner failed: {it['error']}")
                SIM["plan_cpu_ms"].append(it["plan_cpu_s"] * 1000.0)
                it["info"] = R.rt_install(name, it["result"])
                _op({"ev": "act_applied", "seat": name, "k": R.k, "k_snap": it["k_snap"], "decision": dec,
                     "act_id": it["act_id"], "k_arrive": it["k_arrive"], "model_call": it["model_call"]})
            elif dec["type"] == "act":
                it["k_snap"], it["k_effect"], it["state"] = R.k, R.k + LEAD, "planning"
                it["result"] = it["error"] = None
                _op({"ev": "act_snapshot", "seat": name, "k": R.k, "k_effect": it["k_effect"], "act_id": it["act_id"]})
                threading.Thread(target=_plan_job, args=(s, it, R.plan_snapshot(name)), daemon=True).start()
                break
            else:
                if dec["type"] == "none":
                    R.rt_clear(name)
                    it["info"] = {"command": "cleared: the arm returns to the ready pose"}
                else:
                    it["info"] = {"base_rest": R.rt_move(name, *dec["base"])}
                it["k_snap"] = R.k
                _op({"ev": "act_applied", "seat": name, "k": R.k, "k_snap": R.k, "decision": dec,
                     "act_id": it["act_id"], "k_arrive": it["k_arrive"], "model_call": it["model_call"]})
            it["k_effect"] = R.k
            s.act_delay_steps.append(R.k - it["k_arrive"])
            it["done"] = True
            s.queue.pop(0)


def _resume():
    """With COND held: both seats are ready; the world runs again."""
    epoch = time.time()
    for s in SIDES:
        SEATS[s].clock.begin_segment(epoch)
    E["phase"] = "running"; E["resume_at"] = None; E["deadline"] = None
    E["ready"] = {s: False for s in SIDES}
    log({"ev": "run", "point": len(R.points) + 1, "started_epoch": epoch})
    bc_event("run")
    COND.notify_all()


def sim_loop():
    while True:
        with COND:
            while True:
                if E["finalizing"]:
                    return
                if E["phase"] in ("prepare", "review"):
                    now = time.monotonic()
                    if E["resume_at"] is not None and now >= E["resume_at"]:
                        _resume()
                        break
                    if E["deadline"] is not None and now > E["deadline"]:
                        missing = [s for s in SIDES if not E["ready"][s]]
                        if E["phase"] == "review" and len(missing) == 1 and all(E["joined"].values()):
                            end("ready_timeout", missing[0])
                        else:
                            end("start_timeout" if E["phase"] == "prepare" else "incomplete",
                                missing[0] if len(missing) == 1 else None)
                        return
                    COND.wait(0.01)
                    continue
                if running():
                    break
                COND.wait(0.05)
            if SIM["anchor"] is None:
                SIM["anchor"] = (time.monotonic(), R.k)
                SIM["seg_start"] = SIM["anchor"][0]
                SIM["segments"] += 1
            due = _due(R.k)
        while True:
            rem = due - time.monotonic()
            if rem <= 0 or E["finalizing"]:
                break
            time.sleep(min(rem, 0.02))
        with COND:
            if not running():
                continue
            t0 = time.monotonic()
            SIM["seg_last"] = t0
            _process_commands()
            if not running():
                continue
            n_pts = len(R.points)
            R.rt_advance(1)
            SIM["lates"].append(max(0.0, time.monotonic() - due))
            SIM["run_steps"] += 1
            if BC is not None:
                BC.after_step(R, len(R.points) > n_pts)
                for p in R.points[n_pts:]:
                    BC.event("point", R.k, score=dict(R.score), winner=p.get("winner"), how=p.get("how"),
                             n=len(R.points))
            if len(R.points) > n_pts:
                pts = R.points[n_pts:]
                log({"ev": "point", "points": pts})
                for s in SEATS.values():
                    s.news["points"] += pts
                _drop_queues(count=True)
                if R.done:
                    end("match_limit" if R.limit_reached else "match_over")
                    continue
                E["phase"] = "review"
                _close_segment()
                E["deadline"] = time.monotonic() + READY_TIMEOUT_S
                log({"ev": "pause_for_review", "point": len(R.points) + 1})
                bc_event("pause")
            if R.k % 50 == 0 or E["phase"] != "running":
                write_final()
            COND.notify_all()


# ---------------------------------------------------------------------------------------------- observations
def step_phase():
    if running() and SIM["anchor"] is not None:
        a_wall, a_k = SIM["anchor"]
        return min(1.0, max(0.0, (time.monotonic() - (a_wall + (R.k - a_k) * PERIOD)) / PERIOD))
    return 0.0


def now_state(seat):
    """With COND held."""
    R.ensure_frame()
    o = R.side_state(seat.name)
    o.update(t_sim=round(R.k * DT, 4), step=R.k, step_phase=round(step_phase(), 3), wall_s=wall(),
             world=("running" if running() else ("frozen: review due (game ready)" if E["phase"] == "review" else
                    ("frozen: not started (game start)" if E["phase"] == "prepare" else "over"))),
             ready=dict(E["ready"]))
    if not R.in_play():
        o["serve_in_s"] = round(max(0.0, (R.rs["launch"] - R.k) * DT), 3)
    sd = R.sides[seat.name]
    la = sd.last_act
    active = sd.plan_j < len(sd.plan)
    k_hit = la.get("k_hit") if la else None
    o["command"] = ({"contact_in_s": round(max(0, k_hit - R.k) * DT, 3) if k_hit is not None else None,
                     "phase": "approach" if (k_hit is not None and R.k < k_hit) else "follow_through",
                     "pos": la.get("racket_pos"), "normal": la.get("racket_normal"), "vel": la.get("racket_vel"),
                     "base_at_contact": la.get("base_goal"), "stroke": la.get("stroke")}
                    if active and la else "none (the arm returns to / holds the ready pose)")
    o["base_rest"] = ("home " + str(tn.HOME.tolist()) if sd.base_goal is None else [round(float(x), 3) for x in sd.base_goal])
    pend = [it for it in seat.queue if not it.get("done")]
    if pend:
        o["pending_commands"] = [{"act_id": it["act_id"], "type": it["dec"]["type"]} for it in pend]
    return o


def take_news(seat):
    out = {}
    pts = seat.news["points"]
    if pts:
        out["points_finished"] = [{"point": p["point"], "how": p["how"],
                                   "winner": "let" if p["winner"] is None else ("you" if p["winner"] == seat.name else "opponent"),
                                   "score": {"you": p["score"][seat.name], "opponent": p["score"][OTHER[seat.name]]}}
                                  for p in pts]
    if E["phase"] != "review":
        seat.news = {"points": []}
    elif not E["ready"][seat.name]:
        out["review_prompt"] = REVIEW_PROMPT
    return out


IMAGE_LAYOUT = ("2 rows x 4 columns. Row 1: camera behind and above your base line looking down the court; row 2: camera "
                "at the side of the court (x < 0 in your frame) looking along +x: your half (y < 0) is on the right. "
                "Columns: four camera frames 40 ms apart, oldest left; each tile is stamped with its control step k and "
                "its time t since the ball shown was played. The ball is drawn enlarged: a yellow-green sphere of radius "
                "9 cm centred on its true position.")


def observe_payload(seat):
    with COND:
        o = now_state(seat)
        hist = list(R.review_hist if (E["phase"] == "review" and R.review_hist) else R.hist)
        snaps = [dict(hist[max(0, len(hist) - 1 - b)]) for b in reversed(duel.Duel.VIEW_BACK)]
        E["obs_seq"] += 1
        o["obs_id"] = E["obs_seq"]
    t0 = time.monotonic()
    png = seat.render.render(snaps)
    o["render_wall_s"] = round(time.monotonic() - t0, 4)
    o["view_times"] = [s["t"] for s in snaps]
    o["view_steps"] = [s["k"] for s in snaps]
    o["view_leg_ids"] = [s["leg_id"] for s in snaps]
    o["view_sim_times"] = [round(s["k"] * DT, 4) for s in snaps]
    o["image_png_b64"] = base64.b64encode(png).decode()
    o["image_layout"] = IMAGE_LAYOUT
    with COND:
        o["t_sim_at_reply"] = round(R.k * DT, 4)
    return o


# ---------------------------------------------------------------------------------------------- endpoints
def gate():
    if E["phase"] == "over":
        return 200, final_obs()
    if E["phase"] == "review":
        return 409, {"error": "the point is over: review it first with `game ready \"WHY\" \"PLAN\"`",
                     "review_prompt": REVIEW_PROMPT}
    if E["phase"] == "prepare":
        return 409, {"error": "the match has not started: both players must run `game start`"}
    return None


def final_obs():
    return {"done": True, "reason": E["reason"], "score": dict(R.score), "forfeiting": E["forfeit"],
            "note": "the match is over"}


def ready(seat, body, starting):
    """start (prepare phase) or ready WHY PLAN (review): blocks until the world runs again (or the match is over)."""
    if not starting:
        why, plan = body.get("why"), body.get("plan")
        if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
            return 400, {"error": "ready needs two non-empty texts: WHY and PLAN"}
        if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
            return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
    seat.clock.settle()
    with COND:
        if E["phase"] == "over":
            return 200, final_obs()
        want = "prepare" if starting else "review"
        if E["phase"] != want:
            return 409, {"error": ("the match has already started" if starting else "no review is due now")}
        if E["ready"][seat.name]:
            return 409, {"error": "already submitted; waiting for the other player"}
        if starting:
            seat.clock.check_ready()
        E["joined"][seat.name] = True
        E["ready"][seat.name] = True
        if E["deadline"] is None and starting:
            E["deadline"] = time.monotonic() + START_TIMEOUT_S
        if not starting:
            rv = {"seat": seat.name, "after_point": len(R.points), "why": body["why"].strip(), "plan": body["plan"].strip()}
            E["reviews"].append(rv)
        log({"ev": "start" if starting else "review", "seat": seat.name, **({} if starting else {"why": body["why"], "plan": body["plan"]})})
        if all(E["ready"].values()):
            E["resume_at"] = time.monotonic() + 0.2
        COND.notify_all()
        n0 = len(R.points)
        while E["phase"] == want and len(R.points) == n0:
            COND.wait(0.5)
        if E["phase"] == "over":
            return 200, final_obs()
        out = {"accepted": "start" if starting else "review recorded", "now": now_state(seat),
               "note": f"the world runs at 1/{SLOWDOWN:g} of real speed; the next serve comes in "
                       f"{max(0.0, (R.rs['launch'] - R.k) * DT):.2f} s of game time"}
    write_final()
    return 200, out


def _base_arg(base):
    try:
        base = [float(x) for x in base]
    except Exception:  # noqa: BLE001
        return "base must be [bx, by]"
    if len(base) != 2 or not np.all(np.isfinite(base)):
        return "base must be [bx, by] (2 finite numbers)"
    if not (abs(base[0]) <= 5.9 and -15.4 <= base[1] <= -7.6):
        return "base out of range: |bx| <= 5.9, -15.4 <= by <= -7.6"
    return base


def validate_act(body):
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
        return ("act needs t, pos [x, y, z], normal [nx, ny, nz] and vel [vx, vy, vz], optionally base [bx, by]; "
                "or type none, or type move with base")
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


STROKE_KEYS = ("stroke", "base", "base_goal", "k_hit", "n_swing_steps_available", "n_swing_steps", "ik_residual",
               "blade_error_m", "normal_error_deg", "speed_scale", "racket_vel_delivered", "T_from_now")


def do_act(seat, body):
    try:
        return _do_act(seat, body)
    finally:
        if threading.current_thread() is seat.act_owner:
            seat.act_in_flight = False
            seat.act_owner = None


def _do_act(seat, body):
    dec = validate_act(body)
    if isinstance(dec, str):
        return 400, {"error": dec}
    with COND:
        g = gate()
        if g:
            return g
        if seat.queue or seat.act_in_flight:
            seat.refused_busy += 1
            return 429, {"refused": True, "busy": True,
                         "error": "busy: one act at a time; wait for the previous act's reply before sending another"}
        seat.act_in_flight = True
        seat.act_owner = threading.current_thread()
        k_arr, point_arr = R.k, len(R.points)
    with seat.decision_lock:
        ok = seat.clock.decided_by_model()
        model_call = seat.clock.last_call() if ok else None
    with COND:
        if not ok:
            seat.refused_not_model += 1
            log({"ev": "refused_not_model", "seat": seat.name})
            return 429, {"refused": True, "error": "refused: no live model session (program play needs a metered model)"}
        g = gate()
        if g:
            return g
        if len(R.points) != point_arr:
            seat.dropped_acts += 1
            return 409, {"error": "act dropped: its point ended"}
        E["act_seq"] += 1
        it = {"act_id": E["act_seq"], "model_call": model_call, "state": "queued", "dec": dec, "k_arrive": k_arr,
              "done": False, "dropped": False}
        seat.queue.append(it)
        seat.calls["act"] += 1
        log({"ev": "call", "kind": dec["type"], "seat": seat.name, "k_request": k_arr, "decision": dec,
             "act_id": it["act_id"], "model_call": model_call})
        COND.wait_for(lambda: it["done"] or it["dropped"] or E["phase"] == "over", timeout=60 + (LEAD + 5) * PERIOD * 2)
        out = {"call": dec["type"], "act_id": it["act_id"], "t_sim_request": round(k_arr * DT, 4)}
        if it["done"]:
            info = it["info"]
            out["took_effect"] = {"step": it["k_effect"], "t_sim": round(it["k_effect"] * DT, 4),
                                  "accepted_step": it["k_snap"], "steps_after_request": it["k_effect"] - k_arr}
            if dec["type"] == "none":
                out["command"] = info["command"]
            elif dec["type"] == "move":
                out["base_rest"] = info["base_rest"]
            else:
                out["stroke"] = {k: info.get(k) for k in STROKE_KEYS}
        else:
            if it in seat.queue:
                seat.queue.remove(it)
                seat.dropped_acts += 1
            it["dropped"] = True
            out["note"] = "command dropped before it took effect (the point ended)"
        out["now"] = now_state(seat)
        out.update(take_news(seat))
        if E["phase"] == "over":
            out.update(final_obs())
    return 200, out


def do_observe(seat):
    with COND:
        if E["phase"] == "over":
            return 200, final_obs()
        seat.calls["observe"] += 1
        k_req = R.k
    o = observe_payload(seat)
    with COND:
        news = take_news(seat)
        log({"ev": "observe", "seat": seat.name, "k_request": k_req, "obs_id": o["obs_id"], "view_steps": o["view_steps"]})
    return 200, {"call": "observe", "observation": o, **news}


def do_wait(seat, body):
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
        seat.calls["wait"] += 1
        k0, n0 = R.k, len(R.points)
        target = k0 + max(1, int(round(dt / DT)))
        COND.wait_for(lambda: R.k >= target or len(R.points) > n0 or not running(), timeout=dt * SLOWDOWN + 60)
        out = {"call": "wait", "waited_s": round((R.k - k0) * DT, 4), "now": now_state(seat)}
        out.update(take_news(seat))
        if E["phase"] == "over":
            out.update(final_obs())
    return 200, out


def spec(seat):
    return {
        "seat": seat.name, "revision": duel.REVISION, "protocol": "eai-standard-realtime/1.0",
        "player_mode": seat.clock.mode,
        "simulator": "mujoco 3.3.7 (robots) + point-mass tennis ball with drag, Magnus lift, court bounce and racket impact laws",
        "robot": (f"franka-panda on a 0.55 m pedestal, base on x-y rails (<= {tn.BASE_VMAX} m/s, <= {tn.BASE_AMAX} m/s^2) "
                  "+ tennis racket (head centre 0.52 m beyond the flange, strung area an ellipse 0.26 x 0.32 m)"),
        "frame": "your own: your half y < 0, your base's home (0, -11.4); the opponent's robot plays from y > 0",
        "match": {"win_points": duel.WIN_POINTS, "win_by": duel.WIN_BY, "cap_points": duel.CAP_POINTS,
                  "max_hits": duel.MAX_HITS, "max_points_played": duel.MAX_POINTS, "first_player": duel.FIRST_RECEIVER,
                  "serves": "a neutral machine serves every point; the receiver changes every point, starting with "
                            "match.first_player", "first_receiver_is_you": duel.FIRST_RECEIVER == seat.name},
        "timing": {"slowdown": SLOWDOWN, "control_dt_s": DT, "wall_s_per_control_step": PERIOD,
                   "wall_s_per_game_s": SLOWDOWN, "wait_max_s": WAIT_MAX_S, "act_lead_steps": LEAD,
                   "act_lead_game_s": round(LEAD * DT, 4), "act_T_max_s": T_MAX_S,
                   "review_timeout_wall_s": READY_TIMEOUT_S, "start_timeout_wall_s": START_TIMEOUT_S},
        "decision_rule": ("program play: your own program may observe and act (or move) without a new model response; "
                          "one act or move in flight at a time" if os.environ.get("RCB_ACT_RULE") == "program" else
                          "each act needs a new completed model response"),
        "cameras": [dict(c, fovy_deg=tn.Match.FOVY, tile_px=list(tn.Match.TILE), focal_px=579.4,
                         principal_point_px=[320, 240], image_right="forward x up") for c in tn.Match.cam_info()],
        "image": "2 rows (behind, side) x 4 columns (camera frames 40 ms apart, oldest left); tile 640 x 480",
        "world": ("court z = 0; singles court |x| <= 4.115, |y| <= 11.885 (lines in); service line |y| = 6.40; net plane "
                  "y = 0, top 0.914 m at x = 0 rising linearly to 1.07 m at |x| = 5.029; your half y < 0. Robot base home "
                  f"{tn.HOME.tolist()}, rails |bx| <= 5.9, -15.4 <= by <= -7.6; default stance: base = contact xy - "
                  f"{tn.STANCE_OFF.tolist()}"),
    }


def seat_allowed(side, addr):
    hosts = dict(x.split("=", 1) for x in os.environ.get("SEAT_HOSTS", "").split(",") if "=" in x)
    if side not in hosts:
        return addr in ("127.0.0.1", "::1")
    try:
        return addr in {a[4][0] for a in socket.getaddrinfo(hosts[side], None)}
    except OSError:
        return False


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj, default=_jdef).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def dispatch(self, post):
        bits = self.path.strip("/").split("/")
        if len(bits) != 2 or bits[0] not in SIDES or not seat_allowed(bits[0], self.client_address[0]):
            return self._send(403, {"error": "seat not authorized (use http://sim:8000/<your seat>/<call>)"})
        name, ep = bits
        seat = SEATS[name]
        body = {}
        if post:
            n = int(self.headers.get("Content-Length", 0) or 0)
            if not 0 <= n <= 32768:
                return self._send(400, {"error": "request too large"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:  # noqa: BLE001
                return self._send(400, {"error": "invalid JSON"})
            if not isinstance(body, dict):
                return self._send(400, {"error": "JSON body must be an object"})
        try:
            if ep == "spec":
                code, out = 200, spec(seat)
            elif ep == "status":
                with COND:
                    code, out = 200, {"now": now_state(seat), **({"done": True} if E["phase"] == "over" else {}),
                                      "phase": E["phase"], "score": {"you": R.score[name], "opponent": R.score[OTHER[name]]}}
            elif ep == "observe":
                code, out = do_observe(seat)
            elif post and ep == "start":
                code, out = ready(seat, body, True)
            elif post and ep == "ready":
                code, out = ready(seat, body, False)
            elif post and ep == "act":
                code, out = do_act(seat, body)
            elif post and ep == "wait":
                code, out = do_wait(seat, body)
            else:
                code, out = 404, {"error": "no such endpoint (GET spec status observe; POST start act wait ready)"}
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            failure(ep, exc, name)
            code, out = 500, {"error": "simulator error", "detail": repr(exc)[:200]}
        self._send(code, out)

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)


def guarded_sim_loop():
    try:
        sim_loop()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        failure("world", exc)


def on_usr1(*_):
    def run():
        with COND:
            if not E["finalizing"]:
                end("collected")
    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    signal.signal(signal.SIGUSR1, on_usr1)
    for s in SIDES:
        SEATS[s].render = RenderProcess(s)
        SEATS[s].planner = ComputeProcess(f"plan_{s}")
        SEATS[s].planner.warm()
    log({"ev": "start", "revision": duel.REVISION, "seed": duel.SEED, "first_receiver": duel.FIRST_RECEIVER,
         "slowdown": SLOWDOWN, "plan_lead_steps": LEAD, "source_sha": SOURCE_SHA,
         "player_modes": {s: SEATS[s].clock.mode for s in SIDES}})
    if BroadcastLog is not None:
        BC = BroadcastLog(every=2, sport="tennis", mode="duel", slowdown=SLOWDOWN, dt=DT, seed=duel.SEED,
                          first_receiver=duel.FIRST_RECEIVER, nq=int(R.m.nq), players={"A": "A", "B": "B"})
        with COND:
            R.ensure_frame()
            BC.snapshot(R.hist[-1], force=True)     # the scene before the first serve
    write_final()
    threading.Thread(target=guarded_sim_loop, daemon=True).start()
    (DATA / "server.pid").write_text(str(os.getpid()))
    print(f"tennis duel service ready (slowdown x{SLOWDOWN:g}, act lead {LEAD} steps)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()
