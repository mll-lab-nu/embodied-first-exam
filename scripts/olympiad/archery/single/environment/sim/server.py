"""Target archery in the wind: the sim service of archery-program-standard (eai-standard-turn/1.0, program play).

A round of 4 ends x 3 arrows at a World Archery 122 cm face (50, 70, 70, 90 m) in a seeded, gusty wind (archery.py).
Turn-based: nothing moves between arrows; at each arrow the agent sees camera images only (the archer's view with the
windsocks, a scope view, a side view of the middle windsock, a spotting-scope close-up of the face; no coordinates,
no wind numbers) and sends `shoot ELEV AZIM DRAW`.
Rules enforced here (docs/EAI_STANDARD_REALTIME_1_0.md, last section):
  1. program play (RCB_ACT_RULE=program): the agent's own program may shoot without a new model response, but a live
     metered model session must exist (think_clock.py); one action in flight (HTTP 429 `busy`);
  2. chess clock: ROUND_CLOCK_S (60 min) of wall-clock time from `game start`, running while the agent is on turn
     (always, in this solo event) except while the service is busy; when it runs out the round ends and the arrows
     not shot score M (0);
  3. after each arrow except the last the game waits for the review (`POST /ready` {why, plan}; recorded, not scored).
Endpoints: GET /spec, GET /status, POST /start, POST /observe, POST /act, POST /ready.
Evidence (/data): episode.jsonl, final.json, trajectory.json (+ .npz), replay_check.json, replay.mp4. A fresh process
(`archery.py replay`) replays the shots and must reproduce the state hash.
"""
from __future__ import annotations

import base64
import io
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
import archery as A  # noqa: E402
from think_clock import ThinkClock, MeterError, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(DATA, exist_ok=True)
PROTOCOL = "eai-standard-turn/1.0"
REVISION = "archery-program-2"
ROUND_CLOCK_S = float(os.environ.get("ROUND_CLOCK_S", "3600"))
SUCCESS_MIN_TOTAL = int(os.environ.get("SUCCESS_MIN_TOTAL", "110"))
PLAYER_MODE = os.environ.get("RCB_PLAYER_MODE", "model")
N_ARROWS = A.N_ENDS * A.ARROWS_PER_END
MAX_TOTAL = 10 * N_ARROWS
REVIEW_MAX_CHARS = 2000
REVIEW_PROMPT = ("Arrow over. Review it: `game ready \"WHY\" \"PLAN\"` (why it went well or badly; what you will "
                 "change). The game waits until then; your clock runs.")
IMAGE_LAYOUT = ("one PNG of four tiles (`game spec` image.tiles: x, y, width, height): archer (from just behind the bow, "
                "down the range; windsocks at 1/4, 1/2, 3/4 of the distance on the left and one by the target), scope "
                "(centred on the gold), side (across the range at the middle windsock; image right = towards the "
                "target) and target (close-up of the face with your arrows of this end: magenta = arrow 1, lime = 2, "
                "cyan = 3). The windsocks show the wind for the arrow you are about to shoot.")
USAGE_FILE = os.environ.get("THINK_USAGE_FILE", os.path.join(DATA, "think_usage.json"))

CLOCK = ThinkClock(seconds_per_ktok=0.0, usage_file=USAGE_FILE)
LOCK = threading.RLock()
ACT_FLIGHT = threading.Lock()
R = A.Round()
V = A.Views()
E = {"t0": time.time(), "started": False, "start_wall": None, "busy_s": 0.0, "clock_final": None, "clock_out": False,
     "awaiting_review": False, "reviews": [], "shots": [], "final_obs": None, "finalizing": False, "finalized": False,
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
    return ROUND_CLOCK_S - clock_used()


def calls(e: int) -> list:
    return [A.label(v, x) for v, x in zip(R.scores[e], R.xs[e])]


def n_shot() -> int:
    return sum(len(s) for s in R.scores)


def scorecard() -> list:
    return [{"end": e + 1, "distance_m": D, "arrows": calls(e), "end_score": sum(R.scores[e])}
            for e, D in enumerate(A.DISTANCES)]


def png(im) -> str:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(im).save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


def write_final() -> None:
    with LOCK:
        usage = read_usage(USAGE_FILE)
        api = seat_api_errors(USAGE_FILE, usage)   # model-API errors: transient vs unrecovered (api_errors.py)
        out = {"revision": REVISION, "protocol": PROTOCOL, "seed": A.SEED, "player_mode": PLAYER_MODE,
               "decision_rule": CLOCK.rule, "started": E["started"], "ends": A.N_ENDS,
               "arrows_per_end": A.ARROWS_PER_END, "distances_m": A.DISTANCES, "max_total": MAX_TOTAL,
               "success_min_total": SUCCESS_MIN_TOTAL, "total": R.total(), "n_x": R.n_x(),
               "end_scores": [sum(s) for s in R.scores], "arrow_scores": R.scores, "arrows_shot": n_shot(),
               "round_complete": R.done, "clock_forfeit": E["clock_out"], "done": R.done or E["reason"] is not None,
               "reason": E["reason"], "finalized": E["finalized"], "n_act": E["n_act"], "n_observe": E["n_observe"],
               "refused_busy": E["refused_busy"], "refused_not_model": E["refused_not_model"],
               "clock_s": ROUND_CLOCK_S, "clock_used_s": round(clock_used(), 1), "clock_left_s": round(clock_left(), 1),
               "n_reviews": len(E["reviews"]), "reviews": E["reviews"], "elapsed_s": round(time.time() - E["t0"], 1),
               "shots": R.log}
        out.update(E["extra"])
        out["graded_ready"] = E["finalized"]
        out["meter_error"] = bool(E["meter_error"] or (PLAYER_MODE == "model" and E["started"] and
                                                        (not usage.get("epoch") or usage.get("requests", 0) < 1)))
        out["proxy_error"] = api["api_failure"]     # unrecovered, or more than MAX_TRANSIENT_API_ERRORS transient
        out["transient_api_errors"] = api["transient_api_errors"]
        out["unrecovered_api_errors"] = api["unrecovered_api_errors"]
        out["sim_error"] = E["reason"] == "error"
        replay_ok = bool(E["finalized"] and out.get("deterministic") and out.get("replay_total") == R.total())
        out["replay_error"] = bool(out.get("finalize_error") or not replay_ok)
        out["valid_trial"] = bool(replay_ok and not any(out[k] for k in ("replay_error", "sim_error", "meter_error",
                                                                          "proxy_error")))
        out["technical_failure"] = not out["valid_trial"]
        out["success"] = bool(out["valid_trial"] and R.done and R.total() >= SUCCESS_MIN_TOTAL)
        tmp = os.path.join(DATA, "final.json.tmp")
        with open(tmp, "w") as f:
            json.dump(out, f, default=float)
        os.replace(tmp, os.path.join(DATA, "final.json"))


def finalize() -> None:
    try:
        tr = os.path.join(DATA, "trajectory.json")
        with LOCK:
            shots = [dict(s) for s in E["shots"]]
            live_sha = R.state_sha()
            json.dump({"seed": A.SEED, "shots": shots, "clock_forfeit": E["clock_out"], "revision": REVISION},
                      open(tr, "w"))
            np.savez(os.path.join(DATA, "trajectory.npz"),
                     actions=np.asarray([[s["elev_deg"], s["azim_deg"], s["draw"]] for s in shots], dtype=np.float64).reshape(-1, 3),
                     seed=A.SEED)
        p = subprocess.run([sys.executable, os.path.join(HERE, "archery.py"), "replay", tr], capture_output=True,
                           text=True, timeout=300, env=dict(os.environ, ARCHERY_SEED=str(A.SEED)))
        rp = json.loads(p.stdout.strip().splitlines()[-1])
        json.dump(rp, open(os.path.join(DATA, "replay_check.json"), "w"))
        E["extra"] = {"n_shots": len(shots), "deterministic": rp["sha"] == live_sha, "replay_total": rp["total"],
                      "replay_end_scores": [sum(s) for s in rp["scores"]]}
        log({"ev": "replay", **E["extra"]})
        E["finalized"] = True
        write_final()
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1" and shots:
            try:
                A.render_video(shots, os.path.join(DATA, "replay.mp4"))
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
    """With LOCK held."""
    if E["finalizing"]:
        return
    E["reason"] = reason
    E["clock_final"] = clock_used()
    E["final_obs"] = {"done": True, "reason": reason, "round_complete": R.done, "total": R.total(), "n_x": R.n_x(),
                      "success_line": SUCCESS_MIN_TOTAL, "scorecard": scorecard(),
                      "clock_left_s": round(clock_left(), 1), "note": "the round is over"}
    E["finalizing"] = True
    log({"ev": "end", "reason": reason, "total": R.total(), "scores": R.scores})
    write_final()
    threading.Thread(target=finalize, daemon=True).start()


def clock_out() -> None:
    E["clock_out"] = True
    log({"ev": "clock_forfeit", "arrows_shot": n_shot()})
    end("clock_forfeit")


def last_arrow(L: dict) -> dict:
    o = {"end": L["end"], "arrow": L["arrow"],
         "you_sent": {"elev_deg": L["elev_deg"], "azim_deg": L["azim_deg"], "draw": L["draw"]},
         "score": L["call"], "flight_time_s": round(L["flight_s"], 2)}
    if L["miss"]:
        o["spotter"] = L["miss"]
    return o


def state() -> dict:
    if E["final_obs"] is not None:
        return E["final_obs"]
    e = R.end
    o = {"done": False, "turn": "review" if E["awaiting_review"] else "you", "awaiting_review": E["awaiting_review"],
         "end": e + 1, "of_ends": A.N_ENDS, "arrow": R.arrow + 1, "arrows_per_end": A.ARROWS_PER_END,
         "distance_m": A.DISTANCES[e], "this_end": calls(e), "total_so_far": R.total(),
         "arrows_left_in_round": N_ARROWS - n_shot(), "clock_left_s": round(clock_left(), 1)}
    if R.log:
        o["last_arrow"] = last_arrow(R.log[-1])
    return o


def view_png() -> str:
    key = (R.end, R.arrow, R.done)
    if key not in E["view_cache"]:
        ims = V.render(A.DISTANCES[R.end], A.WINDS[R.end][min(R.arrow, A.ARROWS_PER_END - 1)], R.stuck)
        E["view_cache"] = {key: base64.b64encode(A.compose(ims)).decode()}
    return E["view_cache"][key]


def observation() -> dict:
    return {"image_png_b64": view_png(), "image_layout": IMAGE_LAYOUT}


def gate():
    if E["final_obs"] is not None:
        return 200, E["final_obs"]
    if not E["started"]:
        return 409, {"error": "the round has not started: run `game start` when you are ready (nothing before it "
                     "counts on your clock)"}
    return None


def validate(body: dict):
    if body.get("type") != "shoot":
        return "the action must be {'type':'shoot','elev_deg':e,'azim_deg':a,'draw':d}"
    try:
        el, az, dr = float(body["elev_deg"]), float(body["azim_deg"]), float(body["draw"])
    except Exception:  # noqa: BLE001
        return "shoot needs elev_deg, azim_deg and draw (numbers)"
    if not all(math.isfinite(v) for v in (el, az, dr)):
        return "elev_deg, azim_deg and draw must be finite"
    if not -10.0 <= el <= 30.0:
        return "elev_deg must be in [-10, 30]"
    if not -20.0 <= az <= 20.0:
        return "azim_deg must be in [-20, 20]"
    if not A.DRAW_MIN <= dr <= A.DRAW_MAX:
        return f"draw must be in [{A.DRAW_MIN}, {A.DRAW_MAX}]"
    return {"elev_deg": round(el, 4), "azim_deg": round(az, 4), "draw": round(dr, 4)}


def start(body: dict):
    if E["final_obs"] is not None:
        return 200, E["final_obs"]
    if E["started"]:
        return 409, {"error": "the round has already started", "state": state()}
    CLOCK.check_ready()
    if CLOCK.rule != "program":            # per-response rule only: drop pre-start act credits (program play needs none)
        CLOCK.settle()
        CLOCK.rebase()
    E["started"], E["start_wall"] = True, time.time()
    log({"ev": "round_start"})
    return 200, {"started": True, "note": f"your {ROUND_CLOCK_S / 60:g}-minute clock runs from now",
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
        return 409, {"error": "review your last arrow first with `game ready \"WHY\" \"PLAN\"`", "state": state()}
    dec = validate(body)
    if isinstance(dec, str):
        return 400, {"error": dec}
    if not CLOCK.decided_by_model():
        E["refused_not_model"] += 1
        return 429, {"refused": True, "error": "refused: no new model response since your previous arrow"}
    E["n_act"] += 1
    if clock_left() < 0:
        clock_out()
        return 200, {"clock_forfeit": "your clock ran out: the round is over", **E["final_obs"]}
    e, D, w = R.end, A.DISTANCES[R.end], A.WINDS[R.end][R.arrow]
    stuck = list(R.stuck)
    E["shots"].append({"end": e + 1, "arrow": R.arrow + 1, **dec})
    rec, fl = R.shoot(dec["elev_deg"], dec["azim_deg"], dec["draw"])
    log({"ev": "shot", "decision": dec, "model_call": CLOCK.last_call(), "clock_used_s": round(clock_used(), 1),
         **{k: v for k, v in rec.items() if k != "trail"}})
    V.set_state(D, w, stuck + [(fl["hit"], fl["vel"], fl["kind"])])
    out = {"accepted": dec, "last_arrow": last_arrow(rec),
           "landed_image_b64": png(V._shot(D, A.CLOSE_W, A.CLOSE_H, A.close_fovy(), (D - A.CLOSE_BACK, 0.0, A.FACE_Z),
                                           0.0, 0.0))}
    if rec["end_finished"]:
        out["end_finished"] = {"end": e + 1, "distance_m": D, "arrows": calls(e), "end_score": sum(R.scores[e])}
    if R.done:
        end("round_over")
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
        return 409, {"error": "no review is due now (reviews are due after each arrow)", "state": state()}
    why, plan = body.get("why"), body.get("plan")
    if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
        return 400, {"error": "ready needs two non-empty texts: WHY (why the arrow went well or badly) and PLAN (what "
                     "you will change)"}
    if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
        return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
    L = R.log[-1]
    rv = {"after_end": L["end"], "after_arrow": L["arrow"], "arrow_score": L["call"], "total_so_far": R.total(),
          "why": why.strip(), "plan": plan.strip(), "clock_used_s": round(clock_used(), 1)}
    E["reviews"].append(rv)
    log({"ev": "review", **rv})
    E["awaiting_review"] = False
    if clock_left() < 0:
        clock_out()
        return 200, {"accepted": "review recorded", "clock_forfeit": "your clock ran out: the round is over",
                     **E["final_obs"]}
    return 200, {"accepted": "review recorded", "state": state()}


def spec() -> dict:
    return {
        "protocol": PROTOCOL, "revision": REVISION, "player_mode": PLAYER_MODE,
        "simulator": "mujoco 3.3.7 scene/rendering + deterministic point-mass arrow ballistics (RK4, 1 ms)",
        "round": {"ends": A.spec_ends(), "arrows_per_end": A.ARROWS_PER_END, "max_total": MAX_TOTAL,
                  "scoring": "ring value 10 (inner 10 = X, counts 10) down to 1; off the face or off the boss = M (0); "
                             "an arrow touching a ring line scores the higher ring",
                  "success_line": SUCCESS_MIN_TOTAL},
        "clock": {"total_s": ROUND_CLOCK_S, "runs": "from `game start`, while you are on turn (reviews included); the "
                  "simulation does not count; out of time = the round ends and the arrows not shot score M (0)"},
        "decision_rule": ("program play: your own program may shoot without a new model response; one action in "
                          "flight" if os.environ.get("RCB_ACT_RULE") == "program" else
                          "a new model response before every arrow"),
        "review": "after every arrow but the last: `game ready WHY PLAN`",
        "action": "{'type':'shoot','elev_deg':e,'azim_deg':a,'draw':d}",
        "shot": {"elev_deg": "the arrow's launch direction above horizontal at release, in [-10, 30]",
                 "azim_deg": "the launch direction's heading, 0 = +x (straight down the range), + = to the archer's "
                             "left (+y), in [-20, 20]",
                 "draw": f"draw fraction in [{A.DRAW_MIN}, {A.DRAW_MAX}]: launch speed = {A.V_FULL:g} m/s x draw",
                 "full_draw_speed_m_s": A.V_FULL,
                 "scatter_1sigma": {"elev_deg": A.SIG_ELEV_DEG, "azim_deg": A.SIG_AZIM_DEG, "speed_rel": A.SIG_DRAW}},
        "range": {"frame": "x down the range (shooting line x = 0, target face = the plane x = D), y to the archer's "
                           "left, z up (ground z = 0)",
                  "launch_point_m": list(A.LAUNCH), "target_centre_z_m": A.FACE_Z,
                  "face": "World Archery 122 cm 10-ring face: rings 6.1 cm wide; 1-2 white, 3-4 black, 5-6 blue, "
                          "7-8 red, 9-10 gold; on a 1.30 m square straw boss",
                  "distance_lines": "white lines across the range every 10 m",
                  "windsocks": {"mouths_m": "windsocks_by_distance (three on 4 m poles at y = +3.5, x = D/4, D/2, "
                                            "3D/4; a 0.6-size one on a 3.1 m pole at (D, 1.1))",
                                "reading": "a windsock points downwind; its angle below horizontal = 90 deg x "
                                           f"(1 - speed / {A.SOCK_FULL:g} m/s), horizontal at >= {A.SOCK_FULL:g} m/s; "
                                           f"{A.SOCK_LEN:g} m long, 5 stripes, orange at the mouth",
                                "full_speed_m_s": A.SOCK_FULL}},
        "arrow": {"model": "point mass; gravity + quadratic drag on the velocity relative to the air: "
                           "a = -g z - K |v - w| (v - w)", "mass_kg": A.MASS, "shaft_diameter_m": A.D_SHAFT,
                  "drag_coefficient": A.CD, "air_density_kg_m3": A.RHO, "K_per_m": round(A.K_DRAG, 7), "g": A.G},
        "wind": "uniform over the range, horizontal, constant during a flight; it changes from end to end and gusts "
                "from arrow to arrow; the windsocks show the wind for the arrow you are about to shoot",
        "cameras": A.spec_cameras(),
        "image": {"size_px": list(A.CANVAS), "tiles": A.TILES,
                  "note": "the observation is one PNG; each camera is a tile at (x, y) with its own width and height"},
        "cameras_by_distance": {str(int(D)): A.cameras_numeric(D) for D in sorted(set(A.DISTANCES))},
        "windsocks_by_distance": {str(int(D)): A.sock_tops(D) for D in sorted(set(A.DISTANCES))},
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

    def do_GET(self):
        if self.path == "/spec":
            return self._send(200, SPEC)
        if self.path == "/status":
            with LOCK:
                return self._send(200, {"started": E["started"], "state": state(), "scorecard": scorecard()})
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
            if E["started"] and not R.done and E["final_obs"] is None and clock_left() < 0:
                clock_out()
                return
            end("collected")
    threading.Thread(target=run, daemon=True).start()


def watchdog() -> None:
    while not E["finalizing"]:
        time.sleep(1)
        with LOCK:
            if E["started"] and not E["finalizing"] and not R.done and clock_left() < 0:
                clock_out()
                return


if __name__ == "__main__":
    signal.signal(signal.SIGUSR1, on_usr1)
    open(os.environ.get("THINK_CALLS_FILE") or os.path.join(DATA, "think_calls.jsonl"), "a").close()
    view_png()                                       # warm up the renderer
    log({"ev": "start", "seed": A.SEED, "clock_s": ROUND_CLOCK_S, "protocol": PROTOCOL, "revision": REVISION,
         "decision_rule": CLOCK.rule, "player_mode": PLAYER_MODE})
    threading.Thread(target=watchdog, daemon=True).start()
    write_final()
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    print("archery service ready", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()
