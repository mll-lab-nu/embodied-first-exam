"""Curling match service, program play (eai-standard-turn/1.0; docs/EAI_STANDARD_REALTIME_1_0.md, last section).

The player skips the yellow team and throws every yellow stone against a scripted red team: 4 ends of 5 stones per
team (extra ends while tied, at most 3; then the chess clocks decide), the curling ice model (curling.py). The stones are static between
throws, so the world waits for the player. Rules:
  * `POST /start` starts the match and the player's chess clock (CLOCK_BUDGET_S, 60 min). The clock runs only on the
    player's turn (thinking, tools, the model API, programs, reviews); it is stopped while this service simulates a
    throw or the opponent's throws. When it runs out the match ends as a loss (`reason = clock_expired`).
  * After each of the player's throws the game waits for its review (`POST /ready` {why, plan}); only then does it go
    on (the opponent's throws, across an end if one finished, up to the player's next throw).
  * Program play (RCB_ACT_RULE=program): the player's own program may act without a new model response, but a live,
    metered model session is required (think_clock.py). One act in flight: a second act while one is pending gets
    HTTP 429 `busy` (counted as `refused_busy`).
Endpoints: GET /spec, GET /status, POST /observe, POST /start, POST /act, POST /ready. Every reply carries the current
state and the throws made since the previous call.
Evidence (/data): episode.jsonl, final.json, trajectory.json (+ .npz), replay_check.json, replay.mp4. The fresh-process
replay (replay.py) runs on match end or SIGUSR1 (the verifier's collect hook).
"""
from __future__ import annotations

import base64
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import curling as C  # noqa: E402
import render  # noqa: E402
from replay import follow, source_sha, throw  # noqa: E402
from think_clock import MeterError, ThinkClock, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402

DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(DATA, exist_ok=True)
PROTOCOL = "eai-standard-turn/1.0"
REVISION = "turn-2"
CLOCK_BUDGET_S = float(os.environ.get("CLOCK_BUDGET_S", "3600"))
LEVEL = int(os.environ.get("MATCH_LEVEL", "1"))
if LEVEL not in C.LEVELS:
    raise ValueError(f"MATCH_LEVEL must be one of {sorted(C.LEVELS)}")
if not os.environ.get("MATCH_SEED"):
    os.environ.pop("MATCH_SEED", None)             # empty = the level's first official seed (curling.LEVELS)
PLAYER_MODE = os.environ.get("RCB_PLAYER_MODE", "model")
if PLAYER_MODE not in ("model", "oracle"):
    raise ValueError("RCB_PLAYER_MODE must be model or oracle")
REVIEW_MAX_CHARS = 2000
REVIEW_PROMPT = ("Throw made. Review it: `game ready \"WHY\" \"PLAN\"` (why the throw went well or badly; what you will "
                 "change). The game goes on only then; your clock runs.")
WHO = {0: "you", 1: "opponent"}

CLOCK = ThinkClock(usage_file=os.environ.get("THINK_USAGE_FILE", os.path.join(DATA, "think_usage.json")))
LOCK = threading.RLock()
ACT_BUSY = threading.Lock()
M = C.Match(LEVEL)
SEED = int(M.L["seed"])
RD = None
E = {"t0": time.time(), "started": False, "awaiting_review": False, "followed": True, "reviews": [],
     "clock_left_s": CLOCK_BUDGET_S, "clock_since": None, "n_decisions": 0, "refused_busy": 0, "refused_not_model": 0,
     "news": [], "view_cache": {}, "final_obs": None, "finalizing": False, "finalized": False, "reason": None,
     "extra": {}, "meter_error": False, "n_calls": {"observe": 0, "act": 0, "ready": 0, "status": 0}}


# ----------------------------------------------------------------------------- the chess clock
def clock_left() -> float:
    left = E["clock_left_s"]
    if E["clock_since"] is not None:
        left -= time.time() - E["clock_since"]
    return max(0.0, left)


def clock_run() -> None:
    if E["final_obs"] is None and E["clock_since"] is None:
        E["clock_since"] = time.time()


def clock_stop() -> None:
    if E["clock_since"] is not None:
        E["clock_left_s"] = clock_left()
        E["clock_since"] = None


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), "throws": M.n_throws, **ev}, default=float) + "\n")


def won() -> bool:
    return M.done and M.winner_team == 0 and E["reason"] != "clock_expired"


def settle_tie() -> None:
    """With LOCK held: a tie after the last extra end goes to the player with more chess-clock time left. The scripted
    opponent's clock never runs (it keeps CLOCK_BUDGET_S), so a tie is decided against the player."""
    if M.done and M.score[0] == M.score[1] and getattr(M, "tiebreak", None) is None:
        clocks = [round(clock_left(), 3), CLOCK_BUDGET_S]
        M.resolve_tiebreak(0 if clocks[0] > clocks[1] else 1, clocks)
        E["tiebreak"] = dict(M.tiebreak)
        log({"ev": "tiebreak", **E["tiebreak"]})


# ----------------------------------------------------------------------------- evidence
def write_final() -> None:
    with LOCK:
        usage = read_usage(CLOCK.usage_file)
        api = seat_api_errors(CLOCK.usage_file, usage)   # model-API errors: transient vs unrecovered (api_errors.py)
        out = {"protocol": PROTOCOL, "revision": REVISION, "level": LEVEL, "seed": SEED,
               "points_for": M.score[0], "points_against": M.score[1], "won": won(), "ends": M.ends,
               "tiebreak": E.get("tiebreak"),
               "n_ends_played": len(M.ends), "match_over": M.done, "throws": M.n_throws,
               "done": M.done or E["reason"] is not None, "reason": E["reason"], "started": E["started"],
               "clock_forfeit": E["reason"] == "clock_expired", "clock_budget_s": CLOCK_BUDGET_S,
               "clock_left_s": round(clock_left(), 1), "n_decisions": E["n_decisions"],
               "refused_busy": E["refused_busy"], "refused_not_model": E["refused_not_model"], "n_calls": E["n_calls"],
               "decision_rule": CLOCK.rule, "player_mode": PLAYER_MODE, "n_reviews": len(E["reviews"]),
               "reviews": E["reviews"], "elapsed_s": round(time.time() - E["t0"], 1), "live_sha": M.state_sha(),
               "decisions": M.decisions, "log": M.log, "finalized": E["finalized"], "graded_ready": E["finalized"]}
        out.update(E["extra"])
        out["meter_error"] = bool(E["meter_error"] or (PLAYER_MODE == "model" and E["started"] and
                                                       (not usage.get("epoch") or usage.get("requests", 0) < 1)))
        out["proxy_error"] = api["api_failure"]     # unrecovered, or more than MAX_TRANSIENT_API_ERRORS transient
        out["transient_api_errors"] = api["transient_api_errors"]
        out["unrecovered_api_errors"] = api["unrecovered_api_errors"]
        out["sim_error"] = E["reason"] == "error"
        replay_ok = bool(E["finalized"] and out.get("deterministic") and out.get("replay_score") == list(M.score))
        out["replay_error"] = bool(out.get("finalize_error") or not replay_ok)
        out["valid_trial"] = bool(replay_ok and not (out["meter_error"] or out["proxy_error"] or out["sim_error"]))
        out["technical_failure"] = not out["valid_trial"]
        out["success"] = bool(won() and out["valid_trial"])
        tmp = os.path.join(DATA, "final.json.tmp")
        with open(tmp, "w") as f:
            json.dump(out, f, default=float)
        os.replace(tmp, os.path.join(DATA, "final.json"))


def finalize() -> None:
    try:
        with LOCK:
            decs = [dict(d) for d in M.decisions]
            tr = {"protocol": PROTOCOL, "revision": REVISION, "level": LEVEL, "seed": SEED, "decisions": decs,
                  "tiebreak": E.get("tiebreak"),
                  "followed": E["followed"], "live_sha": M.state_sha(), "live_score": list(M.score),
                  "source_sha": source_sha()}
        tp = os.path.join(DATA, "trajectory.json")
        with open(tp, "w") as f:
            json.dump(tr, f)
        # PROTOCOL §4.8: the trajectory also as trajectory.npz (speed, angle_deg, spin: +1 ccw / -1 cw per throw)
        np.savez(os.path.join(DATA, "trajectory.npz"),
                 actions=np.array([[d["v"], d["angle"], 1.0 if d["spin"] == "ccw" else -1.0] for d in decs],
                                  dtype=np.float64).reshape(-1, 3), level=LEVEL, seed=SEED, followed=E["followed"])
        p = subprocess.run([sys.executable, os.path.join(HERE, "replay.py"), tp], capture_output=True, text=True,
                           timeout=float(os.environ.get("RCB_REPLAY_TIMEOUT_S", "600")))
        lines = [json.loads(x) for x in p.stdout.splitlines() if x.startswith("{")]
        rp = lines[0] if lines else {}
        with open(os.path.join(DATA, "replay_check.json"), "w") as f:
            json.dump(rp, f)
        E["extra"] = {"n_replayed_decisions": len(decs), "replay_score": rp.get("replay_score"),
                      "replay_sha": rp.get("replay_sha"), "source_sha": tr["source_sha"],
                      "deterministic": rp.get("replay_sha") == tr["live_sha"] and rp.get("source_sha") == tr["source_sha"],
                      "video": False}
        if p.returncode != 0:
            E["extra"]["replay_stderr"] = p.stderr[-600:]
        log({"ev": "replay", **E["extra"]})
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
            try:
                subprocess.run([sys.executable, os.path.join(HERE, "replay.py"), tp, os.path.join(DATA, "replay.mp4")],
                               capture_output=True, text=True, check=True,
                               timeout=float(os.environ.get("RCB_VIDEO_TIMEOUT_S", "600")))
                E["extra"]["video"] = True
            except Exception as exc:  # noqa: BLE001
                log({"ev": "video_error", "error": repr(exc)[:300]})
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["extra"]["finalize_error"] = repr(exc)[:300]
    E["finalized"] = True
    write_final()


def end(reason: str) -> None:
    """With LOCK held."""
    if E["finalizing"]:
        return
    clock_stop()
    E["reason"] = reason
    E["final_obs"] = {"done": True, "reason": reason, "score": {"you": M.score[0], "opponent": M.score[1]},
                      "won": won(), "ends": [end_summary(e) for e in M.ends],
                      "note": ("your clock ran out: the match is lost" if reason == "clock_expired"
                               else "the match is over")}
    E["finalizing"] = True
    log({"ev": "end", "reason": reason, "score": M.score})
    write_final()
    threading.Thread(target=finalize, daemon=True).start()


# ----------------------------------------------------------------------------- observation
def end_summary(e: dict) -> dict:
    return {"end": e["end"] + 1, "scored_by": "blank" if e["team"] < 0 else WHO[e["team"]], "points": e["points"],
            "score_after": {"you": e["score"][0], "opponent": e["score"][1]}}


def heard(r: dict) -> dict:
    """What a player on the ice knows about a throw: who threw, the spin, collisions heard, stones removed."""
    rem = {"you": 0, "opponent": 0}
    why = []
    for sid, reason in r["removed"]:
        t = 0 if sid < C.N_STONES else 1
        rem[WHO[t]] += 1
        why.append(f"{'your' if t == 0 else 'an opponent'} stone{' (the thrown one)' if sid == r.get('sid') else ''}: {reason}")
    h = {"end": r["end"] + 1, "throw": r["k"] + 1, "by": WHO[r["team"]], "spin": r["spin"],
         "collisions_heard": r["collisions"], "stones_removed": rem, "removed_why": why}
    if r.get("fgz_violation"):
        h["free_guard_zone_violation"] = "the thrown stone moved an opposition guard out of play: it was removed and the stones were put back"
    if r["team"] == 0:
        h["your_release"] = {"speed": r["v"], "angle_deg": r["angle"], "spin": r["spin"]}
    return h


def news(recs: list[dict], n_ends_before: int) -> None:
    for r in recs:
        E["news"].append(heard(r))
    for e in M.ends[n_ends_before:]:
        E["news"].append({"end_finished": end_summary(e)})


def state() -> dict:
    turn = ("over" if E["final_obs"] is not None else "not started" if not E["started"]
            else "review" if E["awaiting_review"] else "you")
    o = {"turn": turn, "score": {"you": M.score[0], "opponent": M.score[1]}, "clock_left_s": round(clock_left(), 1),
         "done": E["final_obs"] is not None}
    if not M.done:
        o.update(end=M.end + 1, throw_in_end=M.k + 1, hammer=WHO[M.hammer],
                 stones_left_to_throw={"you": M.stones_left(0), "opponent": M.stones_left(1)})
    return o


def reply(out: dict) -> dict:
    """Every reply: the current state and the throws made since the previous call."""
    out["state"] = state()
    out["shots_since_your_last_call"], E["news"] = E["news"], []
    return out


def views() -> dict:
    global RD
    key = M.n_throws
    if key not in E["view_cache"]:
        if RD is None:
            RD = render.Renderer()
        RD.set_stones([(s["id"], s["team"], s["x"], s["y"], s["a"]) for s in M.sheet.stones])
        E["view_cache"] = {key: {c: base64.b64encode(RD.png(c)).decode() for c in ("house", "hack")}}
    return E["view_cache"][key]


def observation() -> dict:
    o = {"end": M.end + 1, "regulation_ends": C.N_ENDS, "extra_end": M.end >= C.N_ENDS,
         "throw_in_end": M.k + 1, "your_stone": C.N_STONES - M.stones_left(0) + 1, "hammer": WHO[M.hammer],
         "stones_left_to_throw": {"you": M.stones_left(0), "opponent": M.stones_left(1)},
         "stones_in_play": {"you": sum(1 for s in M.sheet.stones if s["team"] == 0),
                            "opponent": sum(1 for s in M.sheet.stones if s["team"] == 1)},
         "ends_so_far": [end_summary(e) for e in M.ends], "images_png_b64": views()}
    if E["awaiting_review"]:
        o["review_due"] = REVIEW_PROMPT
    return o


# ----------------------------------------------------------------------------- endpoints
def gate() -> tuple[int, dict] | None:
    if E["final_obs"] is not None:
        return 200, reply(dict(E["final_obs"]))
    if not E["started"]:
        return 409, reply({"error": "the match has not started: `game start` starts it (and your clock)"})
    return None


def start() -> tuple[int, dict]:
    if E["final_obs"] is not None:
        return 200, reply(dict(E["final_obs"]))
    if E["started"]:
        return 409, reply({"error": "the match has already started"})
    CLOCK.check_ready()                    # program play: a live, metered model session (model mode)
    E["started"] = True
    log({"ev": "match_start", "level": LEVEL, "seed": SEED})
    clock_run()
    write_final()
    return 200, reply({"started": True, "observation": observation()})


def observe() -> tuple[int, dict]:
    g = gate()
    if g:
        return g
    E["n_calls"]["observe"] += 1
    return 200, reply({"observation": observation()})


def validate(body: dict) -> dict | str:
    if body.get("type", "throw") != "throw":
        return "the action is: throw SPEED ANGLE SPIN"
    try:
        v = float(body["speed"]); a = float(body["angle"]); sp = str(body["spin"]).lower()
    except Exception:  # noqa: BLE001
        return "throw needs speed (m/s), angle (deg) and spin (cw | ccw)"
    if sp not in ("cw", "ccw"):
        return "spin must be cw or ccw"
    if not (math.isfinite(v) and math.isfinite(a)):
        return "numbers must be finite"
    if not (C.V_MIN <= v <= C.V_MAX):
        return f"speed must be in [{C.V_MIN}, {C.V_MAX}] m/s"
    if not abs(a) <= C.ANGLE_MAX_DEG:
        return f"angle must be in [-{C.ANGLE_MAX_DEG}, {C.ANGLE_MAX_DEG}] deg"
    return {"type": "throw", "v": v, "angle": a, "spin": sp}


def act(body: dict) -> tuple[int, dict]:
    with LOCK:
        g = gate()
        if g:
            return g
        E["n_calls"]["act"] += 1
        if E["awaiting_review"]:
            return 409, reply({"error": "review your throw first: `game ready \"WHY\" \"PLAN\"`",
                               "review_prompt": REVIEW_PROMPT})
        dec = validate(body)
        if isinstance(dec, str):
            return 400, reply({"error": dec})
    if not CLOCK.decided_by_model():       # program play: raises MeterError without a live metered session
        with LOCK:
            E["refused_not_model"] += 1
            return 429, reply({"refused": True, "error": "refused: no new model call completed since your previous throw"})
    with LOCK:
        if E["final_obs"] is not None:
            return 200, reply(dict(E["final_obs"]))
        clock_stop()                       # the service's own computing time is not on your clock
        E["n_decisions"] += 1
        log({"ev": "decision", "decision": dec, "clock_left_s": round(clock_left(), 1), "score": list(M.score),
             "end": M.end, "k": M.k, "model_call": CLOCK.last_call()})
        n_ends = len(M.ends)
        rec = throw(M, dec)
        settle_tie()
        E["followed"] = False
        news([rec], n_ends)
        log({"ev": "throw", **heard(rec)})
        out = {"accepted": {"speed": dec["v"], "angle_deg": dec["angle"], "spin": dec["spin"]}, "your_throw": heard(rec)}
        if M.done:
            end("match_over")
            out.update(E["final_obs"])
        else:
            E["awaiting_review"] = True
            clock_run()
            out["review_prompt"] = REVIEW_PROMPT
        write_final()
        return 200, reply(out)


def ready(body: dict) -> tuple[int, dict]:
    with LOCK:
        g = gate()
        if g:
            return g
        E["n_calls"]["ready"] += 1
        if not E["awaiting_review"]:
            return 409, reply({"error": "no review is due now (a review is due after each of your throws)"})
        why, plan = body.get("why"), body.get("plan")
        if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
            return 400, reply({"error": "ready needs two non-empty texts: WHY and PLAN"})
        if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
            return 400, reply({"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"})
        clock_stop()
        rv = {"after_throw": M.n_throws, "your_throws": len(M.decisions), "score": list(M.score), "why": why.strip(),
              "plan": plan.strip(), "clock_left_s": round(clock_left(), 1), "t": round(time.time() - E["t0"], 1)}
        E["reviews"].append(rv)
        log({"ev": "review", **rv})
        E["awaiting_review"] = False
        n_ends = len(M.ends)
        recs = follow(M)
        settle_tie()
        E["followed"] = True
        news(recs, n_ends)
        for r in recs:
            log({"ev": "throw", **heard(r)})
        out = {"accepted": "review recorded", "opponent_throws": [heard(r) for r in recs]}
        if M.done:
            end("match_over")
            out.update(E["final_obs"])
        else:
            clock_run()
            out["next"] = observation()
        write_final()
        return 200, reply(out)


def spec() -> dict:
    return {
        "protocol": PROTOCOL, "revision": REVISION,
        "simulator": "curling ice model with impulse collisions; MuJoCo renders the cameras",
        "clock": {"total_s": CLOCK_BUDGET_S, "rule": "chess clock: runs only on your turn (reviews included), "
                  "stopped while the service throws stones; when it runs out the match is lost"},
        "decision_rule": ("program play: your own program may act without a new model response; one act in flight"
                          if os.environ.get("RCB_ACT_RULE") == "program" else
                          "one new completed model response per act"),
        "rules": "World Curling, The Rules of Curling, July 2025 (with the deviations listed in the instructions)",
        "match": {"opponent_level": LEVEL, "ends": C.N_ENDS, "max_extra_ends": C.MAX_EXTRA_ENDS,
                  "tie_after_extra_ends": "the player with more chess-clock time left wins", "stones_per_team_per_end": C.N_STONES,
                  "first_player": "you", "hammer_end_1": "opponent", "free_guard_zone_stones": C.FGZ_STONES,
                  "your_colour": "yellow"},
        "action": {"throw": "{'type':'throw','speed':m/s,'angle':deg,'spin':'cw'|'ccw'}",
                   "limits": {"speed_m_s": [C.V_MIN, C.V_MAX], "angle_deg": [-C.ANGLE_MAX_DEG, C.ANGLE_MAX_DEG]},
                   "execution_noise_sigma": {"speed_m_s": C.PLAYER_NOISE["speed"], "angle_deg": C.PLAYER_NOISE["angle_deg"]}},
        "cameras": [{k: v for k, v in c.items() if not k.startswith("_")} for c in render.CAMERAS],
        "camera_model": "pinhole; pixel (u, v) from the image's top-left; u right, v down; a world point p maps to "
                        "u = cx + f * (p - pos).image_right / depth, v = cy - f * (p - pos).image_up / depth, "
                        "depth = (p - pos).optical_axis_forward",
        "world": {"origin": "release point at the hack", "+y": "down the sheet towards the far house", "+x": "right",
                  "tee": [0.0, C.TEE_Y], "far_hog_line_y": C.HOG_Y, "back_line_y": C.BACK_Y, "house_radius": C.HOUSE_R,
                  "sheet_half_width": C.HALF_W, "stone_radius": C.R, "stone_top_z": 0.112, "handle_top_z": 0.146},
    }


SPEC = spec()


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

    def _run(self, fn) -> None:
        try:
            code, obj = fn()
        except MeterError as exc:
            log({"ev": "meter_error", "error": repr(exc)[:300]})
            with LOCK:
                E["meter_error"] = True
                end("error")
            return self._send(503, {"error": "model meter error: the trial is invalid", "detail": str(exc)[:200]})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            log({"ev": "error", "error": repr(exc)[:300]})
            with LOCK:
                end("error")
            return self._send(500, {"error": "simulator error", "detail": repr(exc)[:200]})
        self._send(code, obj)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/spec":
            return self._send(200, SPEC)
        if path == "/status":
            with LOCK:
                E["n_calls"]["status"] += 1
                return self._send(200, reply({"started": E["started"], "reason": E["reason"]}))
        return self._send(404, {"error": "no such endpoint (GET /spec /status, POST /observe /start /act /ready)"})

    def do_POST(self):
        if self.path not in ("/observe", "/start", "/act", "/ready"):
            return self._send(404, {"error": "no such endpoint (GET /spec /status, POST /observe /start /act /ready)"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            assert isinstance(body, dict)
        except Exception:  # noqa: BLE001
            return self._send(400, {"error": "the body must be a JSON object"})
        if self.path == "/observe":
            def run_observe():
                with LOCK:
                    return observe()
            return self._run(run_observe)
        if self.path == "/act":
            if not ACT_BUSY.acquire(blocking=False):      # one act in flight
                with LOCK:
                    E["refused_busy"] += 1
                return self._send(429, {"refused": True, "busy": True,
                                        "error": "busy: one act at a time; wait for the previous act's reply"})
            try:
                return self._run(lambda: act(body))
            finally:
                ACT_BUSY.release()

        def run():
            with LOCK:
                return start() if self.path == "/start" else ready(body)
        return self._run(run)


def clock_watch() -> None:
    while True:
        time.sleep(0.5)
        with LOCK:
            if E["final_obs"] is None and E["clock_since"] is not None and clock_left() <= 0.0:
                log({"ev": "clock_expired"})
                end("clock_expired")


def on_usr1(*_):
    def run():
        with LOCK:
            end("collected")
    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    signal.signal(signal.SIGUSR1, on_usr1)
    news(follow(M), 0)                     # the opponent's throws before the player's first (none: it has the hammer)
    log({"ev": "start", "level": LEVEL, "seed": SEED, "clock_budget_s": CLOCK_BUDGET_S, "decision_rule": CLOCK.rule,
         "player_mode": PLAYER_MODE, "protocol": PROTOCOL, "source_sha": source_sha()})
    threading.Thread(target=clock_watch, daemon=True).start()
    write_final()
    with open(os.path.join(DATA, "server.pid"), "w") as f:
        f.write(str(os.getpid()))
    print("curling match service ready", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()
