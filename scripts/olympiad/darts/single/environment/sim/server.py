"""Darts 501 against a scripted thrower: the sim service of darts-501-program-standard (eai-standard-turn/1.0,
program play).

Best of 3 legs of 501 double-out (3 darts per visit, bust rule) against a deterministic scripted thrower (level
MATCH_LEVEL 1-4) that aims with an optimal-aim policy for its own scatter; it throws first in legs 1 and 3, the player
in leg 2. Turn-based: the opponent's visits are
simulated as soon as it is their turn; the world then waits for the player's dart: `throw YAW PITCH SPEED`, the
release direction and speed at the fixed release point (where the dart lands is decided by the flight physics and
the seeded execution scatter). Observations are camera images (thrower's view, side view with the player's last
dart's path, board close-up) plus what a player knows: scores, the caller's calls, the clock.

Rules enforced here (docs/EAI_STANDARD_REALTIME_1_0.md, last section):
  1. program play (RCB_ACT_RULE=program): the agent's own program may throw without a new model response, but a
     live metered model session must exist (think_clock.py); one action in flight (HTTP 429 `busy`);
  2. chess clock: MATCH_CLOCK_S (60 min) of wall-clock time from `game start`, running on the player's turn (the
     opponent's visits and the time this service is busy do not count); when it runs out the match is lost;
  3. after each of the player's darts (except the one that ends the match) the game waits for the review
     (`POST /ready` {why, plan}; recorded, not scored).
Endpoints: GET /spec, GET /status, POST /start, POST /observe, POST /act, POST /ready.
Evidence (/data): episode.jsonl, final.json, trajectory.json (+ .npz), replay_check.json, replay.mp4. On match end or
SIGUSR1 (collect hook) a fresh process (`darts.py replay`) replays trajectory.json and must reproduce the state hash.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import darts as D  # noqa: E402
import render  # noqa: E402
from think_clock import ThinkClock, MeterError, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(DATA, exist_ok=True)
PROTOCOL = "eai-standard-turn/1.0"
REVISION = "darts-501-program-3"
MATCH_CLOCK_S = float(os.environ.get("MATCH_CLOCK_S", "3600"))
LEVEL = int(os.environ.get("MATCH_LEVEL", "1"))
if LEVEL not in D.LEVELS:
    raise ValueError("MATCH_LEVEL must be 1-4")
PLAYER_MODE = os.environ.get("RCB_PLAYER_MODE", "model")
REVIEW_MAX_CHARS = 2000
REVIEW_PROMPT = ("Dart over. Review it: `game ready \"WHY\" \"PLAN\"` (why it went well or badly; what you will "
                 "change). The game waits until then; your clock runs.")
USAGE_FILE = os.environ.get("THINK_USAGE_FILE", os.path.join(DATA, "think_usage.json"))

CLOCK = ThinkClock(seconds_per_ktok=0.0, usage_file=USAGE_FILE)
LOCK = threading.RLock()                   # the match, the renderer and E
ACT_FLIGHT = threading.Lock()              # one action in flight
M = D.Match(LEVEL)
RD = None
E = {"t0": time.time(), "started": False, "start_wall": None, "busy_s": 0.0, "clock_final": None,
     "awaiting_review": False, "opp_pending": False, "reviews": [], "heard": None, "final_obs": None,
     "finalizing": False, "finalized": False, "reason": None, "extra": {}, "img_cache": {}, "refused_busy": 0,
     "refused_not_model": 0, "n_act": 0, "n_observe": 0, "meter_error": False}


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), "darts": len(M.log), **ev}, default=float) + "\n")


def won() -> bool:
    return M.done and M.winner == 0


def clock_used() -> float:
    if not E["started"]:
        return 0.0
    if E["clock_final"] is not None:
        return E["clock_final"]
    return max(0.0, time.time() - E["start_wall"] - E["busy_s"])


def clock_left() -> float:
    return MATCH_CLOCK_S - clock_used()


def visit_summary(v: dict) -> dict:
    return {"by": D.WHO[v["who"]], "leg": v["leg"], "visit": v["n"], "darts": [d["call"] for d in v["darts"]],
            "scored": v.get("scored"), "bust": v["bust"], "checkout": v["checkout"], "remaining": v.get("remaining")}


def write_final() -> None:
    with LOCK:
        usage = read_usage(USAGE_FILE)
        api = seat_api_errors(USAGE_FILE, usage)   # model-API errors: transient vs unrecovered (api_errors.py)
        out = {"revision": REVISION, "protocol": PROTOCOL, "level": LEVEL, "seed": M.seed, "player_mode": PLAYER_MODE,
               "decision_rule": CLOCK.rule, "won": won(), "winner": None if M.winner is None else D.WHO[M.winner],
               "match_over": M.done, "match_reason": M.reason, "started": E["started"], "legs": M.legs,
               "leg_results": M.leg_results,
               "you_remaining": M.rem[0], "opponent_remaining": M.rem[1],
               "stats_you": M.stats(0), "stats_opponent": M.stats(1),
               "done": M.done or E["reason"] is not None, "reason": E["reason"], "finalized": E["finalized"],
               "n_act": E["n_act"], "n_observe": E["n_observe"], "refused_busy": E["refused_busy"],
               "refused_not_model": E["refused_not_model"],
               "match_clock_s": MATCH_CLOCK_S, "clock_used_s": round(clock_used(), 1),
               "clock_left_s": round(clock_left(), 1), "clock_forfeit": bool(M.forfeit),
               "n_reviews": len(E["reviews"]), "reviews": E["reviews"],
               "visits": [visit_summary(v) for v in M.visits], "decisions": M.decisions, "log": M.log,
               "elapsed_s": round(time.time() - E["t0"], 1)}
        out.update(E["extra"])
        out["graded_ready"] = E["finalized"]
        out["meter_error"] = bool(E["meter_error"] or (PLAYER_MODE == "model" and E["started"] and
                                                        (not usage.get("epoch") or usage.get("requests", 0) < 1)))
        out["proxy_error"] = api["api_failure"]     # unrecovered, or more than MAX_TRANSIENT_API_ERRORS transient
        out["transient_api_errors"] = api["transient_api_errors"]
        out["unrecovered_api_errors"] = api["unrecovered_api_errors"]
        out["sim_error"] = E["reason"] == "error"
        replay_ok = bool(E["finalized"] and out.get("deterministic") and out.get("replay_winner") == M.winner
                         and out.get("replay_legs") == list(M.legs) and out.get("replay_remaining") == list(M.rem))
        out["replay_error"] = bool(out.get("finalize_error") or not replay_ok)
        out["valid_trial"] = bool(replay_ok and not any(out[k] for k in ("replay_error", "sim_error", "meter_error",
                                                                          "proxy_error")))
        out["technical_failure"] = not out["valid_trial"]
        out["success"] = bool(won() and out["valid_trial"])
        tmp = os.path.join(DATA, "final.json.tmp")
        with open(tmp, "w") as f:
            json.dump(out, f, default=float)
        os.replace(tmp, os.path.join(DATA, "final.json"))


def finalize() -> None:
    try:
        tr = os.path.join(DATA, "trajectory.json")
        with LOCK:
            decs = [dict(d) for d in M.decisions]
            live_sha = M.state_sha()
            json.dump({"level": LEVEL, "seed": M.seed, "decisions": decs, "forfeit": M.forfeit, "winner": M.winner,
                       "remaining": M.rem, "revision": REVISION}, open(tr, "w"))
            # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads the JSON; same commands)
            np.savez(os.path.join(DATA, "trajectory.npz"),
                     actions=np.asarray([[d["yaw"], d["pitch"], d["speed"]] for d in decs], dtype=np.float64).reshape(-1, 3),
                     level=LEVEL, seed=M.seed, forfeit=bool(M.forfeit))
        p = subprocess.run([sys.executable, os.path.join(HERE, "darts.py"), "replay", tr], capture_output=True,
                           text=True, timeout=300, env=dict(os.environ, MATCH_SEED=str(M.seed)))
        rp = json.loads(p.stdout.strip().splitlines()[-1])
        json.dump(rp, open(os.path.join(DATA, "replay_check.json"), "w"))
        E["extra"] = {"n_actions": len(decs), "deterministic": rp["sha"] == live_sha, "replay_winner": rp["winner"],
                      "replay_legs": rp["legs"], "replay_remaining": rp["rem"], "replay_n_darts": rp["n_darts"]}
        log({"ev": "replay", **E["extra"]})
        E["finalized"] = True
        write_final()
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
            try:
                render.render_match_video(LEVEL, M.seed, decs, os.path.join(DATA, "replay.mp4"), forfeit=M.forfeit)
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
    E["final_obs"] = {"done": True, "reason": reason, "won": won(),
                      "winner": None if M.winner is None else D.WHO[M.winner],
                      "legs": {"you": M.legs[0], "opponent": M.legs[1]}, "leg_results": M.leg_results,
                      "remaining": {"you": M.rem[0], "opponent": M.rem[1]}, "clock_left_s": round(clock_left(), 1),
                      "your_stats": M.stats(0), "note": "the match is over"}
    E["finalizing"] = True
    log({"ev": "end", "reason": reason, "rem": M.rem, "winner": M.winner})
    write_final()
    threading.Thread(target=finalize, daemon=True).start()


def heard_visit(recs: list[dict]) -> dict | None:
    """What a player hears of the opponent's visit: the caller's call for each dart, the visit's score."""
    if not recs:
        return None
    v = [x for x in M.visits if x["who"] == 1][-1]
    return {"opponent_visit": v["n"], "calls": [r["call"] + (f" ({r['event']})" if r.get("event") else "") for r in recs],
            "scored": v["scored"], "bust": v["bust"], "checkout": v["checkout"], "opponent_remaining": M.rem[1]}


def _renderer():
    global RD
    if RD is None:
        RD = render.Renderer()
    return RD


def _trail() -> list:
    mine = [r for r in M.log if r["who"] == 0]
    if not mine:
        return []
    ex = mine[-1]["executed"]
    return [(p[1], p[2], p[3]) for p in D.fly(ex[0], ex[1], ex[2], M.k, trail=True)["trail"]]


def _stuck(recs: list[dict]) -> list:
    return [s for s in (render.stuck(r, r["dart"] - 1) for r in recs) if s]


def view_png() -> str:
    """The observation image (render.TILES): the board shows the darts of the latest visit (whoever threw them; as in
    the duel)."""
    recs = []
    if M.log:
        last = M.log[-1]
        recs = [r for r in M.log if (r["who"], r["leg"], r["visit"]) == (last["who"], last["leg"], last["visit"])]
    key = ("view", len(M.log))
    if key not in E["img_cache"]:
        E["img_cache"] = {key: base64.b64encode(render.compose(_renderer(), _stuck(recs), _trail())).decode()}
    return E["img_cache"][key]


def landed_png(recs: list[dict]) -> str:
    """The board close-up right after a dart landed (this visit's darts)."""
    R = _renderer()
    R.set_darts(_stuck(recs))
    return base64.b64encode(R.png("board")).decode()


def state() -> dict:
    """The state every reply carries."""
    if E["final_obs"] is not None:
        return E["final_obs"]
    v = M.visit
    mine = [r for r in M.log if r["who"] == 0]
    return {"done": False, "turn": "review" if E["awaiting_review"] else "you",
            "awaiting_review": E["awaiting_review"], "legs": {"you": M.legs[0], "opponent": M.legs[1]}, "leg": M.leg,
            "leg_first_thrower": D.WHO[M.starter], "remaining": {"you": M.rem[0], "opponent": M.rem[1]},
            "visit": v["n"], "dart_in_visit": len(v["darts"]) + 1, "darts_left_in_visit": M.darts_left(),
            "visit_start_score": v["start"], "this_visit_so_far": [r["call"] for r in v["darts"]],
            "clock_left_s": round(clock_left(), 1), "last_opponent_visit": E["heard"],
            "your_last_dart": None if not mine else {
                "you_sent": {"yaw_deg": mine[-1]["cmd"][0], "pitch_deg": mine[-1]["cmd"][1], "speed": mine[-1]["cmd"][2]},
                "call": mine[-1]["call"], "event": mine[-1].get("event")}}


def observation() -> dict:
    return {"image_png_b64": view_png(),
            "image_layout": "one PNG of three tiles (`game spec` image.tiles: x, y, width, height): oche (your view "
                            "from the throw line), board (straight at the board from 0.9 m; image right = your right) "
                            "and side (from your right, image right = towards the board; yellow balls = the path of "
                            "your last dart, every 10 ms). The board shows the darts of the latest visit, yours or the "
                            "opponent's: flights yellow (dart 1), cyan (2), magenta (3)."}


def gate() -> tuple[int, dict] | None:
    if E["final_obs"] is not None:
        return 200, E["final_obs"]
    if not E["started"]:
        return 409, {"error": "the match has not started: run `game start` when you are ready (nothing before it "
                     "counts on your clock)"}
    return None


def validate(body: dict) -> dict | str:
    if body.get("type") != "throw":
        return "the action must be a throw: {'type':'throw','yaw':deg,'pitch':deg,'speed':m/s}"
    try:
        y, p, s = float(body["yaw"]), float(body["pitch"]), float(body["speed"])
    except Exception:  # noqa: BLE001
        return "throw needs yaw (deg), pitch (deg) and speed (m/s)"
    if not all(math.isfinite(x) for x in (y, p, s)):
        return "yaw, pitch and speed must be finite"
    if not abs(y) <= D.YAW_MAX:
        return f"yaw must be in [-{D.YAW_MAX}, {D.YAW_MAX}] deg"
    if not D.PITCH_MIN <= p <= D.PITCH_MAX:
        return f"pitch must be in [{D.PITCH_MIN}, {D.PITCH_MAX}] deg"
    if not D.V_MIN <= s <= D.V_MAX:
        return f"speed must be in [{D.V_MIN}, {D.V_MAX}] m/s"
    return {"type": "throw", "yaw": round(y, 4), "pitch": round(p, 4), "speed": round(s, 4)}


def forfeit() -> None:
    """With LOCK held: the clock ran out."""
    M.player_forfeit()
    log({"ev": "clock_forfeit", "clock_used_s": round(clock_used(), 1)})
    end("clock_forfeit")


def start(body: dict) -> tuple[int, dict]:
    if E["final_obs"] is not None:
        return 200, E["final_obs"]
    if E["started"]:
        return 409, {"error": "the match has already started", "state": state()}
    CLOCK.check_ready()                     # a live metered model session (program play)
    if CLOCK.rule != "program":            # per-response rule only: drop pre-start act credits (program play needs none)
        CLOCK.settle()
        CLOCK.rebase()
    E["started"], E["start_wall"] = True, time.time()
    log({"ev": "match_start", "level": LEVEL})
    return 200, {"started": True, "note": f"your {MATCH_CLOCK_S / 60:g}-minute clock runs from now on your turn",
                 "state": state(), "observation": observation()}


def observe(body: dict) -> tuple[int, dict]:
    g = gate()
    if g:
        return g
    E["n_observe"] += 1
    return 200, {"state": state(), "observation": observation()}


def act(body: dict) -> tuple[int, dict]:
    g = gate()
    if g:
        return g
    if E["awaiting_review"]:
        return 409, {"error": "review your last dart first with `game ready \"WHY\" \"PLAN\"`", "state": state()}
    dec = validate(body)
    if isinstance(dec, str):
        return 400, {"error": dec}
    if not CLOCK.decided_by_model():
        E["refused_not_model"] += 1
        log({"ev": "refused_not_model"})
        return 429, {"refused": True, "error": "refused: no new model response since your previous dart"}
    E["n_act"] += 1
    log({"ev": "decision", "decision": dec, "clock_used_s": round(clock_used(), 1), "model_call": CLOCK.last_call()})
    if clock_left() < 0:
        forfeit()
        return 200, {"clock_forfeit": "your clock ran out: the dart is not thrown and the match is lost",
                     **E["final_obs"]}
    rec = M.player_throw(dec["yaw"], dec["pitch"], dec["speed"])
    log({"ev": "dart", **{k: rec[k] for k in ("visit", "dart", "executed", "u", "v", "call", "value", "after")},
         "event": rec.get("event")})
    vis = [r for r in M.log if r["who"] == 0 and (r["leg"], r["visit"]) == (rec["leg"], rec["visit"])]
    out = {"accepted": {"yaw_deg": dec["yaw"], "pitch_deg": dec["pitch"], "speed": dec["speed"]},
           "caller": rec["call"] + (f" - {rec['event']}" if rec.get("event") else ""),
           "landed_image_b64": landed_png(vis), "leg": rec["leg"], "visit": rec["visit"], "dart": rec["dart"]}
    if rec.get("visit_over"):
        out["visit_over"] = visit_summary([x for x in M.visits if x["who"] == 0][-1])
    if rec.get("leg_over"):
        out["leg_over"] = M.leg_results[-1]
    if M.done:
        end("match_over")
    else:
        E["opp_pending"] = bool(rec.get("visit_over"))
        E["awaiting_review"] = True
        out["review_prompt"] = REVIEW_PROMPT
    out["state"] = state()
    return 200, out


def ready(body: dict) -> tuple[int, dict]:
    g = gate()
    if g:
        return g
    if not E["awaiting_review"]:
        return 409, {"error": "no review is due now (reviews are due after each of your darts)", "state": state()}
    why, plan = body.get("why"), body.get("plan")
    if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
        return 400, {"error": "ready needs two non-empty texts: WHY (why the dart went well or badly) and PLAN (what "
                     "you will change)"}
    if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
        return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
    last = [r for r in M.log if r["who"] == 0][-1]
    rv = {"after_visit": last["visit"], "after_dart": last["dart"], "call": last["call"], "remaining": list(M.rem),
          "why": why.strip(), "plan": plan.strip(), "clock_used_s": round(clock_used(), 1)}
    E["reviews"].append(rv)
    log({"ev": "review", **rv})
    E["awaiting_review"] = False
    if clock_left() < 0:
        forfeit()
        return 200, {"accepted": "review recorded", "clock_forfeit": "your clock ran out: the match is lost",
                     **E["final_obs"]}
    if E["opp_pending"]:
        E["opp_pending"] = False
        E["heard"] = heard_visit(M.run_to_decision())
    if M.done:
        end("match_over")
    return 200, {"accepted": "review recorded", "state": state()}


SPEC = {
    "protocol": PROTOCOL, "revision": REVISION, "player_mode": PLAYER_MODE,
    "simulator": "deterministic dart flight (RK4, gravity + quadratic drag) + regulation board scoring; MuJoCo 3.3.7 "
                 "scene for the cameras",
    "match": {"game": "best of 3 legs of 501, double-out", "darts_per_visit": 3, "first_player": "opponent",
              "first_thrower": "the opponent in legs 1 and 3, you in leg 2",
              "visit_cap": f"{D.MAX_VISITS} visits each per leg; then the lower remaining score wins the leg; if level, "
                           "the player with more chess-clock time left (the last-resort rule): the opponent, which "
                           "uses no clock time",
              "opponent_level": LEVEL, "opponent": D.LEVELS[LEVEL]["name"],
              "opponent_scatter_1sigma": D.LEVELS[LEVEL]["scatter"],
              "opponent_release_speed_m_s": D.LEVELS[LEVEL]["speed"]},
    "clock": {"total_s": MATCH_CLOCK_S, "runs": "from `game start`, on your turn only (reviews included); "
              "the opponent's visits and the simulation do not count; out of time = the match is lost"},
    "decision_rule": ("program play: your own program may throw without a new model response; one action in flight"
                      if os.environ.get("RCB_ACT_RULE") == "program" else "a new model response before every dart"),
    "review": "after each of your darts (except the one that ends the match): `game ready WHY PLAN`",
    "action": "{'type':'throw','yaw':deg,'pitch':deg,'speed':m/s}",
    "throw": {"release_point_m": list(D.RELEASE),
              "yaw_deg": "horizontal release direction: 0 = along +x (perpendicular to the board), + = to your left",
              "pitch_deg": "elevation above horizontal, + = up", "speed_m_s": "release speed",
              "limits": {"yaw_deg": [-D.YAW_MAX, D.YAW_MAX], "pitch_deg": [D.PITCH_MIN, D.PITCH_MAX],
                         "speed_m_s": [D.V_MIN, D.V_MAX]},
              "execution_scatter_1sigma": D.PLAYER_SCATTER},
    "flight": {"gravity_m_s2": D.G, "drag": f"a = -k |v| v, k fixed for the match in [{D.K_MIN}, {D.K_MAX}] 1/m (not given)",
               "sticks": "where the dart's tip reaches the board plane; darts do not deflect off wires or other darts"},
    "board": {"face_plane_x_m": D.X_BOARD, "bull_centre_m": [D.X_BOARD, 0.0, D.Z_BULL],
              "radii_mm": {"bull (50, counts as a double)": 6.35, "outer bull (25)": 15.9, "treble ring": [99, 107],
                           "double ring": [162, 170], "board edge (beyond: missed the board)": 225},
              "segments_clockwise_from_top": D.SEGMENTS, "segment_width_deg": 18},
    "world": {"origin": "floor, centre of the throw line", "+x": "towards the board", "+y": "to your left", "+z": "up"},
    "cameras": [{k: v for k, v in c.items() if not k.startswith("_")} for c in render.CAMERAS],
    "image": {"size_px": list(render.CANVAS), "tiles": render.TILES,
              "note": "the observation is one PNG; each camera is a tile at (x, y) with its own width and height"},
    "camera_model": "pinhole; pixel (u, v) from the image's top-left; u right, v down; a world point p maps to "
                    "u = cx + f * (p - pos).image_right / depth, v = cy - f * (p - pos).image_up / depth, "
                    "depth = (p - pos).optical_axis_forward",
    "dart_model": "a stuck dart's tip is 6 mm inside the board; the dart lies along its arrival velocity; the flight "
                  "(3 cm cross, 3.8 cm long) is centred 13.5 cm behind the tip",
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

    def do_GET(self):
        if self.path == "/spec":
            return self._send(200, SPEC)
        if self.path == "/status":
            with LOCK:
                return self._send(200, {"started": E["started"], "state": state(), "n_act": E["n_act"],
                                        "visits": [visit_summary(v) for v in M.visits]})
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
            if E["started"] and not M.done and E["final_obs"] is None and clock_left() < 0:
                forfeit()
                return
            end("collected")
    threading.Thread(target=run, daemon=True).start()


def watchdog() -> None:
    while not E["finalizing"]:
        time.sleep(1)
        with LOCK:
            if E["started"] and not E["finalizing"] and not M.done and clock_left() < 0:
                forfeit()
                return


if __name__ == "__main__":
    signal.signal(signal.SIGUSR1, on_usr1)
    open(os.environ.get("THINK_CALLS_FILE") or os.path.join(DATA, "think_calls.jsonl"), "a").close()  # always an artifact
    E["heard"] = heard_visit(M.run_to_decision())   # the opponent throws first
    view_png()                                      # warm up the renderer
    log({"ev": "start", "level": LEVEL, "seed": M.seed, "k_drag": M.k, "match_clock_s": MATCH_CLOCK_S,
         "protocol": PROTOCOL, "revision": REVISION, "decision_rule": CLOCK.rule, "player_mode": PLAYER_MODE})
    threading.Thread(target=watchdog, daemon=True).start()
    write_final()
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    print("darts match service ready", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()
