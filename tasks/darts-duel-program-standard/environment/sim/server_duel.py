"""Darts duel: the two-seat sim service of darts-duel-program-standard (eai-standard-turn/1.0, program play).

Two agents (seats A and B) play best of 3 legs of 501 double-out at one board, alternate visits of 3 darts
(darts.Duel: FIRST_PLAYER throws first in legs 1 and 3; identical release mechanisms, drag and scatter draws).
Rules enforced here:
  * turns: an action or review out of turn gets HTTP 409; one action in flight per seat (HTTP 429);
  * program play (RCB_ACT_RULE=program): a seat's program may throw without a new model response, but that seat
    needs a live metered model session (think_clock.py, one meter per seat);
  * start: the match begins when both seats have sent `start`; after the first, the second has START_TIMEOUT_S
    (else the trial is incomplete);
  * chess clock: each seat has CLOCK_S of wall-clock time, running only on its own turn (its darts and its reviews;
    the time this service is busy does not count). A seat whose clock runs out loses the match. A seat that stops
    playing on its turn (its session ended: collect hook) loses too;
  * after each dart (except the one that ends the match) its thrower sends the review (`ready`).
Endpoints (per seat, /A/... or /B/...; the caller's address must be that seat's container): GET spec, GET status,
POST start, POST observe, POST act, POST ready, POST wait. Evidence (/data): episode.jsonl, final.json, trajectory.json
(+ .npz), replay_check.json, replay.mp4; a fresh process (`darts.py replay_duel`) must reproduce the state hash.
"""
from __future__ import annotations

import base64
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
REVISION = "darts-duel-program-2"
SEATS = D.SEATS
OTHER = D.OTHER
SEED = int(os.environ.get("DUEL_SEED", "1"))
FIRST = os.environ.get("FIRST_PLAYER", "A")
if FIRST not in SEATS:
    raise ValueError("FIRST_PLAYER must be A or B")
CLOCK_S = float(os.environ.get("CLOCK_S", "3600"))
START_TIMEOUT_S = float(os.environ.get("START_TIMEOUT_S", "1800"))
WAIT_MAX_S = 60.0
REVIEW_MAX_CHARS = 2000
IMAGE_LAYOUT = ("one PNG of three tiles (`game spec` image.tiles: x, y, width, height): oche (your view from the throw "
                "line), board (straight at the board from 0.9 m; image right = your right) and side (from your right, "
                "image right = towards the board; yellow balls = the path of your last dart, every 10 ms). The board "
                "shows the darts of the latest visit: flights yellow (dart 1), cyan (2), magenta (3).")


class Seat:
    def __init__(self, name):
        self.name = name
        self.mode = os.environ.get(f"PLAYER_MODE_{name}", os.environ.get("RCB_PLAYER_MODE", "model"))
        self.clock = ThinkClock(usage_file=os.path.join(DATA, f"think_usage_{name}.json"), mode=self.mode)
        self.started = False
        self.used = 0.0                 # clock used on finished turns
        self.turn_t0 = None             # when the current turn began (wall)
        self.turn_busy = 0.0            # service time inside the current turn (not counted)
        self.flight = threading.Lock()
        self.stats = {"n_act": 0, "n_observe": 0, "n_wait": 0, "refused_busy": 0, "refused_turn": 0,
                      "refused_not_model": 0, "n_reviews": 0}

    def clock_used(self, now=None):
        if self.turn_t0 is None:
            return self.used
        return self.used + max(0.0, (now or time.time()) - self.turn_t0 - self.turn_busy)

    def clock_left(self):
        return CLOCK_S - self.clock_used()


COND = threading.Condition(threading.RLock())
M = D.Duel(SEED, FIRST)
S = {s: Seat(s) for s in SEATS}
RD = None
E = {"t0": time.time(), "phase": "prepare", "start_deadline": None, "on_turn": None, "review_due": None,
     "reviews": [], "final_obs": None, "finalizing": False, "finalized": False, "reason": None, "extra": {},
     "errors": [], "img_cache": {}, "last_seen": {s: 0 for s in SEATS}}


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), "darts": len(M.log), **ev}, default=float) + "\n")


def set_turn(seat) -> None:
    """With COND held: the clock of the seat on turn stops, `seat`'s starts (None: nobody's)."""
    now = time.time()
    old = E["on_turn"]
    if old is not None and S[old].turn_t0 is not None:
        S[old].used = S[old].clock_used(now)
        S[old].turn_t0 = None
    E["on_turn"] = seat
    if seat is not None:
        S[seat].turn_t0, S[seat].turn_busy = now, 0.0
        log({"ev": "turn", "seat": seat, "clock_left_s": round(S[seat].clock_left(), 1)})
    COND.notify_all()


def end(reason: str) -> None:
    """With COND held."""
    if E["finalizing"]:
        return
    set_turn(None)
    E["phase"], E["reason"], E["finalizing"] = "over", reason, True
    log({"ev": "end", "reason": reason, "legs": M.legs, "winner": M.winner, "forfeit": M.forfeit})
    write_final()
    COND.notify_all()
    threading.Thread(target=finalize, daemon=True).start()


def lose(seat: str, why: str) -> None:
    M.lose(seat, why)
    log({"ev": "lost", "seat": seat, "why": why, "clock_used_s": round(S[seat].clock_used(), 1)})
    end(why)


def write_final() -> None:
    with COND:
        usage = {s: read_usage(S[s].clock.usage_file) for s in SEATS}
        meter = {s: S[s].mode == "model" and S[s].started and (not usage[s].get("epoch") or usage[s].get("requests", 0) < 1)
                 for s in SEATS}
        apis = {s: seat_api_errors(S[s].clock.usage_file, usage[s]) for s in SEATS}   # model-API errors: transient vs unrecovered (api_errors.py)
        proxy = {s: apis[s]["api_failure"] for s in SEATS}   # unrecovered, or more than MAX_TRANSIENT_API_ERRORS
        complete = M.done and E["reason"] in ("match_over", "clock", "abandoned")
        replay_ok = bool(E["finalized"] and E["extra"].get("deterministic"))
        valid = bool(complete and replay_ok and not E["errors"] and not any(meter.values()) and not any(proxy.values()))
        out = {"revision": REVISION, "protocol": PROTOCOL, "seed": SEED, "first_player": FIRST, "phase": E["phase"],
               "reason": E["reason"], "legs": M.legs, "leg_results": M.leg_results, "remaining": M.rem,
               "winner": M.winner if valid else None, "match_winner": M.winner, "forfeit": M.forfeit,
               "clock_forfeit": M.forfeit["seat"] if M.forfeit and M.forfeit["why"] == "clock" else None,
               "abandoned": M.forfeit["seat"] if M.forfeit and M.forfeit["why"] == "abandoned" else None,
               "started": {s: S[s].started for s in SEATS}, "player_modes": {s: S[s].mode for s in SEATS},
               "clock_s": CLOCK_S, "clock_used_s": {s: round(S[s].clock_used(), 1) for s in SEATS},
               "seats": {s: dict(S[s].stats, **M.stats(s)) for s in SEATS}, "reviews": E["reviews"],
               "decisions": M.decisions, "log": M.log, "errors": E["errors"], "meter_error": meter,
               "proxy_error": proxy,
               "transient_api_errors": {s: apis[s]["transient_api_errors"] for s in SEATS},
               "unrecovered_api_errors": {s: apis[s]["unrecovered_api_errors"] for s in SEATS}, "finalized": E["finalized"], "graded_ready": E["finalized"],
               "valid_trial": valid, "technical_failure": not valid, "elapsed_s": round(time.time() - E["t0"], 1)}
        out.update(E["extra"])
        tmp = os.path.join(DATA, "final.json.tmp")
        with open(tmp, "w") as f:
            json.dump(out, f, default=float)
        os.replace(tmp, os.path.join(DATA, "final.json"))


def finalize() -> None:
    try:
        tr = os.path.join(DATA, "trajectory.json")
        with COND:
            decs = [dict(d) for d in M.decisions]
            live_sha = M.state_sha()
            json.dump({"seed": SEED, "first_player": FIRST, "decisions": decs, "revision": REVISION}, open(tr, "w"))
            throws = [d for d in decs if "forfeit" not in d]
            np.savez(os.path.join(DATA, "trajectory.npz"),
                     actions=np.asarray([[d["yaw"], d["pitch"], d["speed"]] for d in throws], dtype=np.float64).reshape(-1, 3),
                     seat=np.asarray([d["seat"] for d in throws]), seed=SEED, first_player=FIRST)
        p = subprocess.run([sys.executable, os.path.join(HERE, "darts.py"), "replay_duel", tr], capture_output=True,
                           text=True, timeout=300)
        rp = json.loads(p.stdout.strip().splitlines()[-1])
        json.dump(rp, open(os.path.join(DATA, "replay_check.json"), "w"))
        with COND:
            E["extra"] = {"n_actions": len(decs), "deterministic": rp["sha"] == live_sha and rp["legs"] == M.legs
                          and rp["winner"] == M.winner, "replay_legs": rp["legs"], "replay_winner": rp["winner"]}
            log({"ev": "replay", **E["extra"]})
            E["finalized"] = True
            write_final()
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
            try:
                render.render_duel_video(SEED, FIRST, decs, os.path.join(DATA, "replay.mp4"))
                E["extra"]["video"] = True
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                E["extra"]["video"] = False
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["errors"].append({"where": "replay", "error": repr(exc)[:300]})
    E["finalized"] = True
    write_final()


def _renderer():
    global RD
    if RD is None:
        RD = render.Renderer()
    return RD


def _board_darts() -> list:
    """The darts of the latest visit (whoever threw them; pulled when the next visit's first dart is thrown)."""
    if not M.log:
        return []
    last = M.log[-1]
    vis = [r for r in M.log if (r["seat"], r["leg"], r["visit"]) == (last["seat"], last["leg"], last["visit"])]
    return [s for s in (render.stuck(r, r["dart"] - 1) for r in vis) if s]


def view_png(seat: str) -> str:
    """The observation image (render.TILES); the side view shows the path of `seat`'s own last dart."""
    key = (len(M.log), seat)
    if key not in E["img_cache"]:
        mine = [r for r in M.log if r["seat"] == seat]
        tr = []
        if mine:
            ex = mine[-1]["executed"]
            tr = [(p[1], p[2], p[3]) for p in D.fly(ex[0], ex[1], ex[2], M.k, trail=True)["trail"]]
        if len(E["img_cache"]) > 4:
            E["img_cache"] = {}
        E["img_cache"][key] = base64.b64encode(render.compose(_renderer(), _board_darts(), tr)).decode()
    return E["img_cache"][key]


def landed_png() -> str:
    R = _renderer()
    R.set_darts(_board_darts())
    return base64.b64encode(R.png("board")).decode()


def state(seat: str) -> dict:
    o = OTHER[seat]
    news = [{"by": "you" if r["seat"] == seat else "opponent", "leg": r["leg"], "visit": r["visit"], "dart": r["dart"],
             "call": r["call"] + (f" - {r['event']}" if r.get("event") else ""), "remaining_after": r["after"]}
            for r in M.log[E["last_seen"][seat]:]]
    E["last_seen"][seat] = len(M.log)
    if E["phase"] == "prepare":
        turn = "start" if not S[seat].started else "waiting for the opponent to start"
    elif E["phase"] == "over":
        turn = "over"
    elif E["on_turn"] == seat:
        turn = "review" if E["review_due"] == seat else "you"
    else:
        turn = "opponent"
    out = {"seat": seat, "phase": E["phase"], "turn": turn, "your_turn": turn in ("you", "review"),
           "awaiting_review": E["review_due"] == seat, "done": E["phase"] == "over",
           "legs": {"you": M.legs[seat], "opponent": M.legs[o]}, "leg": M.leg,
           "leg_first_thrower": "you" if M.starter == seat else "opponent",
           "remaining": {"you": M.rem[seat], "opponent": M.rem[o]},
           "clock_left_s": round(S[seat].clock_left(), 1), "opponent_clock_left_s": round(S[o].clock_left(), 1),
           "shots_since_your_last_call": news}
    if not M.done and E["phase"] != "over":
        v = M.visit
        out.update({"visit_by": "you" if v["seat"] == seat else "opponent", "visit": v["n"],
                    "dart_in_visit": len(v["darts"]) + 1, "darts_left_in_visit": M.darts_left(),
                    "visit_start_score": v["start"], "this_visit_so_far": [r["call"] for r in v["darts"]]})
    if E["phase"] == "over":
        out.update({"reason": E["reason"], "won": M.winner == seat, "winner": None if M.winner is None else
                    ("you" if M.winner == seat else "opponent")})
    return out


def busy(seat: str, t: float) -> None:
    """With COND held: service time of `seat`'s request since t is not counted on its clock."""
    if E["on_turn"] == seat and S[seat].turn_t0 is not None:
        S[seat].turn_busy += time.time() - max(t, S[seat].turn_t0)


def start(seat: str, body: dict) -> tuple[int, dict]:
    if E["phase"] != "prepare" or S[seat].started:
        return 409, {"error": "already started", "state": state(seat)}
    S[seat].clock.check_ready()                 # a live metered model session (program play)
    S[seat].started = True
    log({"ev": "start", "seat": seat})
    if all(S[s].started for s in SEATS):
        E["phase"], E["start_deadline"] = "play", None
        log({"ev": "match_start", "first_player": FIRST})
        set_turn(M.turn)
    else:
        E["start_deadline"] = time.time() + START_TIMEOUT_S
    COND.notify_all()
    return 200, {"started": True, "state": state(seat)}


def gate(seat: str):
    if E["phase"] == "over":
        return 200, {"state": state(seat)}
    if E["phase"] == "prepare":
        return 409, {"error": "the match has not started (both players must send start)", "state": state(seat)}
    return None


def observe(seat: str, body: dict) -> tuple[int, dict]:
    g = gate(seat)
    if g:
        return g
    S[seat].stats["n_observe"] += 1
    return 200, {"state": state(seat), "observation": {"image_png_b64": view_png(seat), "image_layout": IMAGE_LAYOUT}}


def validate(body: dict):
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
    return {"yaw": round(y, 4), "pitch": round(p, 4), "speed": round(s, 4)}


def act(seat: str, body: dict) -> tuple[int, dict]:
    g = gate(seat)
    if g:
        return g
    if E["on_turn"] != seat or E["review_due"] == seat:
        S[seat].stats["refused_turn"] += 1
        why = "review your last dart first" if E["review_due"] == seat else "it is not your turn"
        return 409, {"error": why, "state": state(seat)}
    dec = validate(body)
    if isinstance(dec, str):
        return 400, {"error": dec}
    if not S[seat].clock.decided_by_model():
        S[seat].stats["refused_not_model"] += 1
        return 429, {"refused": True, "error": "refused: no new model response since your previous dart"}
    S[seat].stats["n_act"] += 1
    if S[seat].clock_left() < 0:
        lose(seat, "clock")
        return 200, {"clock_forfeit": "your clock ran out: you lose the match", "state": state(seat)}
    rec = M.throw(seat, dec["yaw"], dec["pitch"], dec["speed"], {s: S[s].clock_left() for s in SEATS})
    log({"ev": "dart", "seat": seat, "decision": dec, "model_call": S[seat].clock.last_call(),
         **{k: rec[k] for k in ("leg", "visit", "dart", "executed", "u", "v", "call", "value", "after")},
         "event": rec.get("event"), "clock_used_s": round(S[seat].clock_used(), 1)})
    out = {"accepted": dec, "caller": rec["call"] + (f" - {rec['event']}" if rec.get("event") else ""),
           "leg": rec["leg"], "visit": rec["visit"], "dart": rec["dart"]}
    if M.done:
        end("match_over")
    else:
        E["review_due"] = seat
    out["landed_image_b64"] = landed_png()
    out["state"] = state(seat)
    return 200, out


def ready(seat: str, body: dict) -> tuple[int, dict]:
    g = gate(seat)
    if g:
        return g
    if E["review_due"] != seat:
        S[seat].stats["refused_turn"] += 1
        return 409, {"error": "no review is due from you now (reviews follow each of your darts)", "state": state(seat)}
    why, plan = body.get("why"), body.get("plan")
    if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
        return 400, {"error": "ready needs two non-empty texts: WHY and PLAN"}
    if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
        return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
    last = [r for r in M.log if r["seat"] == seat][-1]
    rv = {"seat": seat, "leg": last["leg"], "visit": last["visit"], "dart": last["dart"], "call": last["call"],
          "why": why.strip(), "plan": plan.strip(), "clock_used_s": round(S[seat].clock_used(), 1)}
    E["reviews"].append(rv)
    S[seat].stats["n_reviews"] += 1
    log({"ev": "review", **rv})
    E["review_due"] = None
    if S[seat].clock_left() < 0:
        lose(seat, "clock")
        return 200, {"accepted": "review recorded", "clock_forfeit": "your clock ran out: you lose the match",
                     "state": state(seat)}
    if M.turn != seat:
        set_turn(M.turn)
    return 200, {"accepted": "review recorded", "state": state(seat)}


def wait(seat: str, body: dict) -> tuple[int, dict]:
    """Block until it is this seat's turn, the match is over or `timeout_s` (<= 60) passed."""
    try:
        timeout = min(WAIT_MAX_S, max(0.0, float(body.get("timeout_s", WAIT_MAX_S))))
    except (TypeError, ValueError):
        return 400, {"error": "timeout_s must be a number"}
    S[seat].stats["n_wait"] += 1
    deadline = time.time() + timeout
    while E["phase"] != "over" and E["on_turn"] != seat and time.time() < deadline:
        COND.wait(min(1.0, max(0.01, deadline - time.time())))
    return 200, {"state": state(seat)}


def spec(seat: str) -> dict:
    return {
        "seat": seat, "protocol": PROTOCOL, "revision": REVISION, "player_mode": S[seat].mode,
        "match": {"game": "best of 3 legs of 501, double-out", "darts_per_visit": 3, "first_player": FIRST,
                  "first_thrower": "first_player in legs 1 and 3, the other player in leg 2",
                  "visit_cap": f"{D.MAX_VISITS} visits each per leg; then the lower remaining score wins the leg; if "
                               "level, the player with more chess-clock time left (the last-resort rule)"},
        "clock": {"total_s": CLOCK_S, "runs": "on your turn only (your darts and your reviews); the time the service "
                  "is busy does not count; out of time = you lose the match",
                  "start_window_s": START_TIMEOUT_S},
        "decision_rule": ("program play: your own program may throw without a new model response; one action in "
                          "flight" if os.environ.get("RCB_ACT_RULE") == "program" else
                          "a new model response before every dart"),
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
        "dart_model": "a stuck dart's tip is 6 mm inside the board; the dart lies along its arrival velocity; the "
                      "flight (3 cm cross, 3.8 cm long) is centred 13.5 cm behind the tip",
    }


def watchdog() -> None:
    while True:
        time.sleep(0.5)
        with COND:
            if E["finalizing"]:
                return
            if E["phase"] == "prepare" and E["start_deadline"] and time.time() > E["start_deadline"]:
                log({"ev": "start_timeout", "started": {s: S[s].started for s in SEATS}})
                end("incomplete")
            elif E["phase"] == "play" and E["on_turn"] and S[E["on_turn"]].clock_left() < 0:
                lose(E["on_turn"], "clock")


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

    def send(self, code, value):
        raw = json.dumps(value, default=float).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def dispatch(self, post=False):
        bits = self.path.strip("/").split("/")
        if len(bits) != 2 or bits[0] not in SEATS or not seat_allowed(bits[0], self.client_address[0]):
            return self.send(403, {"error": "seat not authorized"})
        seat, ep = bits
        body = {}
        if post:
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 <= n <= 32768:
                    raise ValueError("request too large")
                body = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("JSON object required")
            except (ValueError, TypeError) as exc:
                return self.send(400, {"error": str(exc)})
        if not post:
            if ep == "spec":
                return self.send(200, spec(seat))
            if ep == "status":
                with COND:
                    return self.send(200, {"state": state(seat)})
            return self.send(404, {"error": "unknown endpoint"})
        fn = {"start": start, "observe": observe, "act": act, "ready": ready, "wait": wait}.get(ep)
        if fn is None:
            return self.send(404, {"error": "unknown endpoint"})
        if ep == "act" and not S[seat].flight.acquire(blocking=False):
            with COND:
                S[seat].stats["refused_busy"] += 1
            return self.send(429, {"refused": True, "busy": True, "error": "busy: one action at a time"})
        try:
            with COND:
                t = time.time()
                try:
                    code, out = fn(seat, body)
                except Exception as exc:  # noqa: BLE001
                    traceback.print_exc()
                    E["errors"].append({"where": ep, "seat": seat, "error": repr(exc)[:300],
                                        "meter": isinstance(exc, MeterError)})
                    log({"ev": "error", "seat": seat, "error": repr(exc)})
                    end("error")
                    return self.send(500, {"error": "technical failure", "detail": repr(exc)[:200]})
                finally:
                    if ep != "wait":
                        busy(seat, t)
            if ep != "wait":
                write_final()
        finally:
            if ep == "act":
                S[seat].flight.release()
        return self.send(code, out)

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch(True)


def on_usr1(*_):
    def run():
        with COND:
            if E["phase"] == "play" and E["on_turn"]:
                seat = E["on_turn"]
                lose(seat, "clock" if S[seat].clock_left() < 0 else "abandoned")
            else:
                end("incomplete" if E["phase"] == "prepare" else "collected")
    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    signal.signal(signal.SIGUSR1, on_usr1)
    view_png("A")                                    # warm up the renderer
    log({"ev": "service", "seed": SEED, "first_player": FIRST, "k_drag": M.k, "clock_s": CLOCK_S, "revision": REVISION,
         "protocol": PROTOCOL, "player_modes": {s: S[s].mode for s in SEATS}})
    write_final()
    threading.Thread(target=watchdog, daemon=True).start()
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    print("darts duel service ready", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
