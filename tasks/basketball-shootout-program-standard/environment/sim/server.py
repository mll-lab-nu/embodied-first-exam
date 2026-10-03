"""Robot basketball shootout: the sim service of basketball-shootout-program-standard (eai-standard-turn/1.0, program
play).

A simulated Franka Panda shooter (a launcher on a 1 m pedestal) takes 10 shots, two from each of five spots (1 point
per make), with a static defender between it and the hoop (bball.py, MuJoCo). Turn-based: the world waits between shots; the agent
sees camera images only (no hoop, ball or spot coordinates) and sends `shoot ANGLE SPEED SPIN YAW`.
Rules enforced here (docs/EAI_STANDARD_REALTIME_1_0.md, last section):
  1. program play (RCB_ACT_RULE=program): the agent's own program may shoot without a new model response, but a live
     metered model session must exist (think_clock.py); one action in flight (HTTP 429 `busy`). Thinking is not
     turned into simulated time: the defender stands still and there is no shot clock;
  2. chess clock: CLOCK_S (60 min) of wall-clock time from `game start` (reviews included; service time excluded);
     when it runs out the shootout ends and the shots not taken are misses;
  3. after each shot except the last the game waits for the review (`POST /ready` {why, plan}; recorded, not scored).
Endpoints: GET /spec, GET /status, POST /start, POST /observe, POST /act, POST /ready.
Evidence (/data): episode.jsonl, final.json, trajectory.json (+ .npz), replay_check.json, replay.mp4. A fresh process
replays the shots and must reproduce the state hash.
"""
from __future__ import annotations

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
import bball  # noqa: E402
import server_common as C  # noqa: E402
from think_clock import ThinkClock, MeterError, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(DATA, exist_ok=True)
PROTOCOL = "eai-standard-turn/1.0"
REVISION = "basketball-shootout-program-2"
CLOCK_S = float(os.environ.get("CLOCK_S", "3600"))
MAKES_NEEDED = int(os.environ.get("MAKES_NEEDED", str(bball.MAKES_NEEDED)))
PLAYER_MODE = os.environ.get("RCB_PLAYER_MODE", "model")
REVIEW_MAX_CHARS = 2000
REVIEW_PROMPT = ("Shot over. Review it: `game ready \"WHY\" \"PLAN\"` (why it was made or missed; what you will "
                 "change). The game waits until then; your clock runs.")
USAGE_FILE = os.environ.get("THINK_USAGE_FILE", os.path.join(DATA, "think_usage.json"))

CLOCK = ThinkClock(seconds_per_ktok=0.0, usage_file=USAGE_FILE)
LOCK = threading.RLock()
ACT_FLIGHT = threading.Lock()
G = bball.Game(int(os.environ.get("BB_SEED", "7")))
N_SHOTS = len(G.plan)
E = {"t0": time.time(), "started": False, "start_wall": None, "busy_s": 0.0, "clock_final": None, "clock_out": False,
     "awaiting_review": False, "reviews": [], "final_obs": None, "finalizing": False, "finalized": False,
     "reason": None, "extra": {}, "view_cache": {}, "refused_busy": 0, "refused_not_model": 0, "n_act": 0,
     "n_observe": 0, "meter_error": False}


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), **ev}, default=float) + "\n")


def clock_used() -> float:
    if not E["started"]:
        return 0.0
    if E["clock_final"] is not None:
        return E["clock_final"]
    return max(0.0, time.time() - E["start_wall"] - E["busy_s"])


def clock_left() -> float:
    return CLOCK_S - clock_used()


view_b64, strip_b64 = C.view_b64, C.strip_b64


def results():
    return [{k: v for k, v in r.items() if k != "nearest_snap"} for r in G.results]


def write_final() -> None:
    with LOCK:
        usage = read_usage(USAGE_FILE)
        api = seat_api_errors(USAGE_FILE, usage)   # model-API errors: transient vs unrecovered (api_errors.py)
        out = {"revision": REVISION, "protocol": PROTOCOL, "seed": G.seed, "player_mode": PLAYER_MODE,
               "decision_rule": CLOCK.rule, "started": E["started"], "shots_total": N_SHOTS,
               "makes_needed": MAKES_NEEDED, "made": G.made, "shots_taken": G.shot, "complete": G.done,
               "clock_forfeit": E["clock_out"], "done": G.done or E["reason"] is not None, "reason": E["reason"],
               "finalized": E["finalized"], "n_act": E["n_act"], "n_observe": E["n_observe"],
               "refused_busy": E["refused_busy"], "refused_not_model": E["refused_not_model"], "clock_s": CLOCK_S,
               "clock_used_s": round(clock_used(), 1), "clock_left_s": round(clock_left(), 1),
               "n_reviews": len(E["reviews"]), "reviews": E["reviews"], "steps": G.k,
               "elapsed_s": round(time.time() - E["t0"], 1), "results": results(),
               "decisions": [a["decision"] for a in G.actions]}
        out["counts"] = {c: sum(1 for r in G.results if r["result"] == c)
                         for c in ("made", "rim", "backboard", "blocked", "airball")}
        out.update(E["extra"])
        out["graded_ready"] = E["finalized"]
        out["meter_error"] = bool(E["meter_error"] or (PLAYER_MODE == "model" and E["started"] and
                                                        (not usage.get("epoch") or usage.get("requests", 0) < 1)))
        out["proxy_error"] = api["api_failure"]     # unrecovered, or more than MAX_TRANSIENT_API_ERRORS transient
        out["transient_api_errors"] = api["transient_api_errors"]
        out["unrecovered_api_errors"] = api["unrecovered_api_errors"]
        out["sim_error"] = E["reason"] == "error"
        replay_ok = bool(E["finalized"] and out.get("deterministic") and out.get("replay_made") == G.made)
        out["replay_error"] = bool(out.get("finalize_error") or not replay_ok)
        out["valid_trial"] = bool(replay_ok and not any(out[k] for k in ("replay_error", "sim_error", "meter_error",
                                                                          "proxy_error")))
        out["technical_failure"] = not out["valid_trial"]
        out["success"] = bool(out["valid_trial"] and G.done and G.made >= MAKES_NEEDED)
        tmp = os.path.join(DATA, "final.json.tmp")
        with open(tmp, "w") as f:
            json.dump(out, f, default=float)
        os.replace(tmp, os.path.join(DATA, "final.json"))


def finalize() -> None:
    try:
        tr = os.path.join(DATA, "trajectory.json")
        with LOCK:
            acts = [dict(a) for a in G.actions]
            live_sha = G.state_sha()
            json.dump({"seed": G.seed, "control_dt": bball.CONTROL_DT, "actions": acts, "revision": REVISION},
                      open(tr, "w"))
            np.savez(os.path.join(DATA, "trajectory.npz"),
                     actions=np.asarray([[a["decision"][k] for k in ("angle_deg", "speed", "spin_hz", "yaw_deg")]
                                         for a in acts], dtype=np.float64).reshape(-1, 4), seed=G.seed)
        p = subprocess.run([sys.executable, "-c", REPLAY, tr], capture_output=True, text=True, timeout=600, cwd=HERE)
        rp = json.loads(p.stdout.strip().splitlines()[-1])
        json.dump(rp, open(os.path.join(DATA, "replay_check.json"), "w"))
        E["extra"] = {"n_actions": len(acts), "deterministic": rp["sha"] == live_sha, "replay_made": rp["made"],
                      "replay_results_match": rp["results"] == [r["result"] for r in G.results]}
        log({"ev": "replay", **E["extra"]})
        E["finalized"] = True
        write_final()
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1" and acts:
            try:
                import video
                video.render(acts, G.seed, os.path.join(DATA, "replay.mp4"))
                E["extra"]["video"] = True
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                E["extra"]["video"] = False
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["extra"]["finalize_error"] = repr(exc)[:300]
    E["finalized"] = True
    write_final()


# the fresh-process replay (python -c REPLAY trajectory.json)
REPLAY = """
import json, sys
sys.path.insert(0, '.')
import bball
tr = json.load(open(sys.argv[1]))
g = bball.Game(tr['seed']); g.record_snaps = False
g.replay(tr['actions'])
print(json.dumps({'sha': g.state_sha(), 'made': g.made, 'results': [r['result'] for r in g.results]}))
"""


def end(reason: str) -> None:
    if E["finalizing"]:
        return
    E["reason"] = reason
    E["clock_final"] = clock_used()
    E["final_obs"] = {"done": True, "reason": reason, "made": G.made, "shots_taken": G.shot,
                      "success_line": MAKES_NEEDED, "results": [r["result"] for r in G.results],
                      "clock_left_s": round(clock_left(), 1), "note": "the shootout is over"}
    E["finalizing"] = True
    log({"ev": "end", "reason": reason, "made": G.made})
    write_final()
    threading.Thread(target=finalize, daemon=True).start()


def clock_out() -> None:
    E["clock_out"] = True
    log({"ev": "clock_forfeit", "shots_taken": G.shot})
    end("clock_forfeit")


def state() -> dict:
    if E["final_obs"] is not None:
        return E["final_obs"]
    o = {"done": False, "turn": "review" if E["awaiting_review"] else "you", "awaiting_review": E["awaiting_review"],
         "shot": G.shot + 1, "shots_total": N_SHOTS, "shots_left": N_SHOTS - G.shot, "made": G.made,
         "success_line": MAKES_NEEDED, "spot": G.plan[min(G.shot, N_SHOTS - 1)] + 1,
         "attempt_at_this_spot": G.attempt_at_spot() if not G.done else None, "clock_left_s": round(clock_left(), 1)}
    if G.results:
        r = G.results[-1]
        o["last_shot"] = {k: r.get(k) for k in ("shot", "spot", "result", "how", "touched", "release_point")}
    return o


def observation() -> dict:
    key = G.shot
    if key not in E["view_cache"]:
        E["view_cache"] = {key: view_b64(G)}
    return {"image_png_b64": E["view_cache"][key], "image_layout": C.VIEW_NOTE}


def gate():
    if E["final_obs"] is not None:
        return 200, E["final_obs"]
    if not E["started"]:
        return 409, {"error": "the shootout has not started: run `game start` when you are ready (nothing before it "
                     "counts on your clock)"}
    return None


def validate(body: dict):
    if body.get("type") != "shoot":
        return "the action must be {'type':'shoot','angle_deg','speed','spin_hz','yaw_deg'}"
    try:
        dec = {k: float(body[k]) for k in ("angle_deg", "speed", "spin_hz", "yaw_deg")}
    except Exception:  # noqa: BLE001
        return "shoot needs numbers angle_deg, speed, spin_hz, yaw_deg"
    for k, (lo, hi) in bball.LIMITS.items():
        if not (math.isfinite(dec[k]) and lo <= dec[k] <= hi):
            return f"{k} must be in [{lo}, {hi}]"
    return {k: round(v, 4) for k, v in dec.items()}


def start(body: dict):
    if E["final_obs"] is not None:
        return 200, E["final_obs"]
    if E["started"]:
        return 409, {"error": "the shootout has already started", "state": state()}
    CLOCK.check_ready()
    if CLOCK.rule != "program":            # per-response rule only: drop pre-start act credits (program play needs none)
        CLOCK.settle()
        CLOCK.rebase()
    E["started"], E["start_wall"] = True, time.time()
    log({"ev": "shootout_start"})
    return 200, {"started": True, "note": f"your {CLOCK_S / 60:g}-minute clock runs from now",
                 "state": state(), "observation": observation()}


def observe(body: dict):
    g = gate()
    if g:
        return g
    E["n_observe"] += 1
    return 200, {"state": state(), "observation": observation()}


def act(body: dict):
    g = gate()
    if g:
        return g
    if E["awaiting_review"]:
        return 409, {"error": "review your last shot first with `game ready \"WHY\" \"PLAN\"`", "state": state()}
    dec = validate(body)
    if isinstance(dec, str):
        return 400, {"error": dec}
    if not CLOCK.decided_by_model():
        E["refused_not_model"] += 1
        return 429, {"refused": True, "error": "refused: no new model response since your previous shot"}
    E["n_act"] += 1
    if clock_left() < 0:
        clock_out()
        return 200, {"clock_forfeit": "your clock ran out: the shootout is over", **E["final_obs"]}
    res = G.shoot(dec)
    log({"ev": "shot", "decision": dec, "model_call": CLOCK.last_call(), "clock_used_s": round(clock_used(), 1),
         **{k: v for k, v in res.items() if k != "nearest_snap"}})
    out = {"accepted": dec, "result": res["result"], "how": res.get("how"), "touched": res["touched"],
           "made": G.made, "shots_left": N_SHOTS - G.shot, "result_image_b64": strip_b64(G, res),
           "result_image_note": C.STRIP_NOTE}
    if G.done:
        end("all_shots_taken")
    else:
        E["awaiting_review"] = True
        out["review_prompt"] = REVIEW_PROMPT
    out["state"] = state()
    return 200, out


def ready(body: dict):
    g = gate()
    if g:
        return g
    if not E["awaiting_review"]:
        return 409, {"error": "no review is due now (reviews are due after each shot)", "state": state()}
    why, plan = body.get("why"), body.get("plan")
    if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
        return 400, {"error": "ready needs two non-empty texts: WHY (why the shot was made or missed) and PLAN (what "
                     "you will change)"}
    if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
        return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
    rv = {"after_shot": G.shot, "made": G.made, "why": why.strip(), "plan": plan.strip(),
          "clock_used_s": round(clock_used(), 1)}
    E["reviews"].append(rv)
    log({"ev": "review", **rv})
    E["awaiting_review"] = False
    if clock_left() < 0:
        clock_out()
        return 200, {"accepted": "review recorded", "clock_forfeit": "your clock ran out: the shootout is over",
                     **E["final_obs"]}
    return 200, {"accepted": "review recorded", "state": state()}


def spec() -> dict:
    return C.spec_common(N_SHOTS) | {"protocol": PROTOCOL, "revision": REVISION, "player_mode": PLAYER_MODE,
        "shootout": {"shots": N_SHOTS, "spots": len(bball.SPOT_NOMINAL), "attempts_per_spot": 2,
                     "order": "spot 1 twice, then spot 2 twice, ... spot 5 twice", "success_line": MAKES_NEEDED},
        "clock": {"total_s": CLOCK_S, "runs": "from `game start` (reviews included); the simulation does not count; "
                  "out of time = the shootout ends, the shots not taken are misses"},
        "decision_rule": ("program play: your own program may shoot without a new model response; one action in "
                          "flight" if os.environ.get("RCB_ACT_RULE") == "program" else
                          "a new model response before every shot")}


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

    def do_GET(self):
        if self.path == "/spec":
            return self._send(200, SPEC)
        if self.path == "/status":
            with LOCK:
                return self._send(200, {"started": E["started"], "state": state(),
                                        "results": [r["result"] for r in G.results]})
        return self._send(404, {"error": "no such endpoint (GET /spec /status; POST /start /observe /act /ready)"})

    def do_POST(self):
        kind = self.path.strip("/")
        if kind not in ("start", "observe", "act", "ready"):
            return self._send(404, {"error": "no such endpoint"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:  # noqa: BLE001
            return self._send(400, {"error": "invalid JSON"})
        if not isinstance(body, dict):
            return self._send(400, {"error": "JSON body must be an object"})
        if kind == "act" and not ACT_FLIGHT.acquire(blocking=False):
            with LOCK:
                E["refused_busy"] += 1
            return self._send(429, {"refused": True, "busy": True, "error": "busy: one action at a time; wait for "
                                    "the previous action's reply"})
        try:
            with LOCK:
                t = time.time()
                try:
                    code, obj = {"start": start, "observe": observe, "act": act, "ready": ready}[kind](body)
                except Exception as exc:  # noqa: BLE001
                    traceback.print_exc()
                    if isinstance(exc, MeterError):
                        E["meter_error"] = True
                    log({"ev": "error", "error": repr(exc)})
                    end("error")
                    return self._send(500, {"error": "simulator error", "detail": repr(exc)[:200]})
                finally:
                    if E["started"] and E["clock_final"] is None:
                        E["busy_s"] += time.time() - max(t, E["start_wall"])
            write_final()
        finally:
            if kind == "act":
                ACT_FLIGHT.release()
        return self._send(code, obj)


def on_usr1(*_):
    def run():
        with LOCK:
            if E["started"] and not G.done and E["final_obs"] is None and clock_left() < 0:
                clock_out()
                return
            end("collected")
    threading.Thread(target=run, daemon=True).start()


def watchdog() -> None:
    while not E["finalizing"]:
        time.sleep(1)
        with LOCK:
            if E["started"] and not E["finalizing"] and not G.done and clock_left() < 0:
                clock_out()
                return


if __name__ == "__main__":
    signal.signal(signal.SIGUSR1, on_usr1)
    open(os.environ.get("THINK_CALLS_FILE") or os.path.join(DATA, "think_calls.jsonl"), "a").close()
    observation()                                    # warm up the renderer
    log({"ev": "start", "seed": G.seed, "clock_s": CLOCK_S, "protocol": PROTOCOL, "revision": REVISION,
         "decision_rule": CLOCK.rule, "player_mode": PLAYER_MODE})
    threading.Thread(target=watchdog, daemon=True).start()
    write_final()
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    print("shootout service ready", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()
