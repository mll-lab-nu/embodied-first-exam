"""Basketball duel: the two-seat sim service of basketball-duel-program-standard (eai-standard-turn/1.0, program play).

Two agents (seats A and B) each shoot on their own identical court (bb_duel.Duel: the same five spots and headings,
the same release scatter for the n-th shot of either player). Five rounds, one per spot: one player takes its 2
shots from the spot, then the other; FIRST_PLAYER shoots first in rounds 1, 3 and 5. Most makes wins; a tie goes to
extra shots (pairs of one shot each, FIRST_PLAYER first, from spot 1, 2, ... 5, 1, ..., until one pair differs; after
30 tied pairs, a safety cap, the player with more chess-clock time left wins; never a draw).
Rules enforced here:
  * turns: an action or review out of turn gets HTTP 409; the camera images are served only on your own turn; one
    action in flight per seat (HTTP 429);
  * program play (RCB_ACT_RULE=program): a live metered model session per seat (think_clock.py);
  * start: the match begins when both seats have sent `start`; after the first, the second has START_TIMEOUT_S;
  * chess clock: CLOCK_S per seat, running only on its own turn (its shots and reviews; service time excluded); a
    seat whose clock runs out, or that stops playing on its turn, loses the match;
  * after each shot (except the one that ends the match) its shooter sends the review (`ready`).
Endpoints (per seat, /A/... or /B/...): GET spec, GET status, POST start, POST observe, POST act, POST ready, POST wait.
"""
from __future__ import annotations

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

SEED = int(os.environ.get("DUEL_SEED", "1"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bb_duel  # noqa: E402
import bball  # noqa: E402
import server_common as C  # noqa: E402
from think_clock import ThinkClock, MeterError, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(DATA, exist_ok=True)
PROTOCOL = "eai-standard-turn/1.0"
REVISION = "basketball-duel-program-4"
SEATS, OTHER = bb_duel.SEATS, bb_duel.OTHER
FIRST = os.environ.get("FIRST_PLAYER", "A")
if FIRST not in SEATS:
    raise ValueError("FIRST_PLAYER must be A or B")
CLOCK_S = float(os.environ.get("CLOCK_S", "3600"))
START_TIMEOUT_S = float(os.environ.get("START_TIMEOUT_S", "1800"))
WAIT_MAX_S = 60.0
REVIEW_MAX_CHARS = 2000


class Seat:
    def __init__(self, name):
        self.name = name
        self.mode = os.environ.get(f"PLAYER_MODE_{name}", os.environ.get("RCB_PLAYER_MODE", "model"))
        self.clock = ThinkClock(usage_file=os.path.join(DATA, f"think_usage_{name}.json"), mode=self.mode)
        self.started = False
        self.used = 0.0
        self.turn_t0 = None
        self.turn_busy = 0.0
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
M = bb_duel.Duel(SEED, FIRST)
S = {s: Seat(s) for s in SEATS}
E = {"t0": time.time(), "phase": "prepare", "start_deadline": None, "on_turn": None, "review_due": None,
     "reviews": [], "finalizing": False, "finalized": False, "reason": None, "extra": {}, "errors": [],
     "view_cache": {}, "last_seen": {s: 0 for s in SEATS}, "shots": []}


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), **ev}, default=float) + "\n")


def set_turn(seat) -> None:
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
    if E["finalizing"]:
        return
    set_turn(None)
    E["phase"], E["reason"], E["finalizing"] = "over", reason, True
    log({"ev": "end", "reason": reason, "made": M.made(), "winner": M.winner, "forfeit": M.forfeit})
    write_final()
    COND.notify_all()
    threading.Thread(target=finalize, daemon=True).start()


def lose(seat: str, why: str) -> None:
    M.lose(seat, why)
    log({"ev": "lost", "seat": seat, "why": why, "clock_used_s": round(S[seat].clock_used(), 1)})
    end(why)


def scorecard(seat: str) -> list:
    g = M.games[seat]
    return [{"shot": r["shot"], "spot": r["spot"], "result": r["result"]} for r in g.results]


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
               "reason": E["reason"], "made": M.made(), "scorecards": {s: scorecard(s) for s in SEATS},
               "extra_pairs": M.extra, "shots_taken": M.n,
               "winner": M.winner if valid else None, "match_winner": M.winner, "tiebreak": M.tiebreak,
               "forfeit": M.forfeit,
               "clock_forfeit": M.forfeit["seat"] if M.forfeit and M.forfeit["why"] == "clock" else None,
               "abandoned": M.forfeit["seat"] if M.forfeit and M.forfeit["why"] == "abandoned" else None,
               "started": {s: S[s].started for s in SEATS}, "player_modes": {s: S[s].mode for s in SEATS},
               "clock_s": CLOCK_S, "clock_used_s": {s: round(S[s].clock_used(), 1) for s in SEATS},
               "seats": {s: S[s].stats for s in SEATS}, "reviews": E["reviews"], "decisions": M.decisions,
               "shots": E["shots"], "errors": E["errors"], "meter_error": meter, "proxy_error": proxy,
               "transient_api_errors": {s: apis[s]["transient_api_errors"] for s in SEATS},
               "unrecovered_api_errors": {s: apis[s]["unrecovered_api_errors"] for s in SEATS},
               "finalized": E["finalized"], "graded_ready": E["finalized"], "valid_trial": valid,
               "technical_failure": not valid, "elapsed_s": round(time.time() - E["t0"], 1)}
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
            shots = [d for d in decs if "forfeit" not in d]
            np.savez(os.path.join(DATA, "trajectory.npz"),
                     actions=np.asarray([[d[k] for k in ("angle_deg", "speed", "spin_hz", "yaw_deg")] for d in shots],
                                        dtype=np.float64).reshape(-1, 4),
                     seat=np.asarray([d["seat"] for d in shots]), seed=SEED, first_player=FIRST)
        p = subprocess.run([sys.executable, os.path.join(HERE, "bb_duel.py"), "replay", tr], capture_output=True,
                           text=True, timeout=900, cwd=HERE)
        rp = json.loads(p.stdout.strip().splitlines()[-1])
        json.dump(rp, open(os.path.join(DATA, "replay_check.json"), "w"))
        with COND:
            E["extra"] = {"n_actions": len(decs), "deterministic": rp["sha"] == live_sha and rp["made"] == M.made()
                          and rp["winner"] == M.winner, "replay_made": rp["made"], "replay_winner": rp["winner"]}
            log({"ev": "replay", **E["extra"]})
            E["finalized"] = True
            write_final()
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
            try:
                import video
                for s in SEATS:
                    g = M.games[s]
                    if g.actions:
                        video.render([dict(a) for a in g.actions], SEED, os.path.join(DATA, f"replay_{s}.mp4"),
                                     plan=list(g.plan), label=f"seat {s}  ")
                E["extra"]["video"] = True
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                E["extra"]["video"] = False
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["errors"].append({"where": "replay", "error": repr(exc)[:300]})
    E["finalized"] = True
    write_final()


def views(seat: str) -> dict:
    """The 2 x 2 camera grid of `seat`'s court at its next shot."""
    key = (seat, M.games[seat].shot)
    if key not in E["view_cache"]:
        E["view_cache"] = {key: C.view_b64(M.games[seat])}
    return E["view_cache"][key]


def state(seat: str) -> dict:
    o = OTHER[seat]
    news = [{"by": "you" if r["seat"] == seat else "opponent", "shot": r["shot"], "spot": r["spot"],
             "result": r["result"]} for r in E["shots"][E["last_seen"][seat]:]]
    E["last_seen"][seat] = len(E["shots"])
    if E["phase"] == "prepare":
        turn = "start" if not S[seat].started else "waiting for the opponent to start"
    elif E["phase"] == "over":
        turn = "over"
    elif E["on_turn"] == seat:
        turn = "review" if E["review_due"] == seat else "you"
    else:
        turn = "opponent"
    m = M.made()
    out = {"seat": seat, "phase": E["phase"], "turn": turn, "your_turn": turn in ("you", "review"),
           "awaiting_review": E["review_due"] == seat, "done": E["phase"] == "over",
           "made": {"you": m[seat], "opponent": m[o]}, "stage": M.stage(),
           "clock_left_s": round(S[seat].clock_left(), 1), "opponent_clock_left_s": round(S[o].clock_left(), 1),
           "shots_since_your_last_call": news}
    g = M.games[seat]
    if not M.done and E["phase"] != "over" and not g.done:
        out.update({"your_shot": g.shot + 1, "spot": g.plan[g.shot] + 1,
                    "attempt_at_this_spot": g.attempt_at_spot()})
    if g.results:
        r = g.results[-1]
        out["your_last_shot"] = {k: r.get(k) for k in ("shot", "spot", "result", "how", "touched")}
    if E["phase"] == "over":
        out.update({"reason": E["reason"], "won": M.winner == seat,
                    "winner": None if M.winner is None else ("you" if M.winner == seat else "opponent")})
    return out


def busy(seat: str, t: float) -> None:
    if E["on_turn"] == seat and S[seat].turn_t0 is not None:
        S[seat].turn_busy += time.time() - max(t, S[seat].turn_t0)


def start(seat: str, body: dict):
    if E["phase"] != "prepare" or S[seat].started:
        return 409, {"error": "already started", "state": state(seat)}
    S[seat].clock.check_ready()
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


def observe(seat: str, body: dict):
    g = gate(seat)
    if g:
        return g
    if E["on_turn"] != seat or E["review_due"] == seat:
        return 409, {"error": "the camera images are served on your turn only (before each of your shots)",
                     "state": state(seat)}
    S[seat].stats["n_observe"] += 1
    return 200, {"state": state(seat), "observation": {"image_png_b64": views(seat), "image_layout": C.VIEW_NOTE}}


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


def act(seat: str, body: dict):
    g = gate(seat)
    if g:
        return g
    if E["on_turn"] != seat or E["review_due"] == seat:
        S[seat].stats["refused_turn"] += 1
        why = "review your last shot first" if E["review_due"] == seat else "it is not your turn"
        return 409, {"error": why, "state": state(seat)}
    dec = validate(body)
    if isinstance(dec, str):
        return 400, {"error": dec}
    if not S[seat].clock.decided_by_model():
        S[seat].stats["refused_not_model"] += 1
        return 429, {"refused": True, "error": "refused: no new model response since your previous shot"}
    S[seat].stats["n_act"] += 1
    if S[seat].clock_left() < 0:
        lose(seat, "clock")
        return 200, {"clock_forfeit": "your clock ran out: you lose the match", "state": state(seat)}
    game = M.games[seat]
    res = M.shoot(seat, dec, {s: S[s].clock_left() for s in SEATS})
    rec = {"seat": seat, **{k: v for k, v in res.items() if k != "nearest_snap"}}
    E["shots"].append(rec)
    log({"ev": "shot", "decision": dec, "model_call": S[seat].clock.last_call(),
         "clock_used_s": round(S[seat].clock_used(), 1), **rec})
    out = {"accepted": dec, "result": res["result"], "how": res.get("how"), "touched": res["touched"],
           "result_image_b64": C.strip_b64(game, res), "result_image_note": C.STRIP_NOTE}
    E["view_cache"] = {}
    if M.done:
        end("match_over")
    else:
        E["review_due"] = seat
    out["state"] = state(seat)
    return 200, out


def ready(seat: str, body: dict):
    g = gate(seat)
    if g:
        return g
    if E["review_due"] != seat:
        S[seat].stats["refused_turn"] += 1
        return 409, {"error": "no review is due from you now (reviews follow each of your shots)", "state": state(seat)}
    why, plan = body.get("why"), body.get("plan")
    if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
        return 400, {"error": "ready needs two non-empty texts: WHY and PLAN"}
    if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
        return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
    last = [r for r in E["shots"] if r["seat"] == seat][-1]
    rv = {"seat": seat, "shot": last["shot"], "result": last["result"], "why": why.strip(),
          "plan": plan.strip(), "clock_used_s": round(S[seat].clock_used(), 1)}
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


def wait(seat: str, body: dict):
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
    sp = C.spec_common(len(M.games[seat].plan))
    sp.update({
        "seat": seat, "protocol": PROTOCOL, "revision": REVISION, "player_mode": S[seat].mode,
        "match": {"format": "five rounds, one per spot (spot 1 .. 5): one player takes its 2 shots from the spot, "
                            "then the other; first_player shoots first in rounds 1, 3 and 5",
                  "first_player": FIRST, "winner": "the most makes",
                  "tie": f"extra shots: pairs of one shot each (first_player first) from spot 1, 2, ...; the first "
                         f"pair that differs decides (the spots rotate 1-5 and the pairs continue until one differs); "
                         f"after {bb_duel.EXTRA_PAIRS} tied pairs (a safety cap) the player with more chess-clock time left wins (the last-resort rule)",
                  "same_conditions": "identical courts: the same spots and headings, and the same release scatter "
                                     "for the n-th shot of either player"},
        "clock": {"total_s": CLOCK_S, "runs": "on your turn only (your shots and your reviews); the time the service "
                  "is busy does not count; out of time = you lose the match", "start_window_s": START_TIMEOUT_S},
        "decision_rule": ("program play: your own program may shoot without a new model response; one action in "
                          "flight" if os.environ.get("RCB_ACT_RULE") == "program" else
                          "a new model response before every shot")})
    return sp


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
                return self.send(200, SPECS[seat])
            if ep == "status":
                with COND:
                    return self.send(200, {"state": state(seat), "scorecard": scorecard(seat)})
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


SPECS = {s: spec(s) for s in SEATS}

if __name__ == "__main__":
    signal.signal(signal.SIGUSR1, on_usr1)
    views(M.turn)                                   # warm up the renderer
    E["view_cache"] = {}
    log({"ev": "service", "seed": SEED, "first_player": FIRST, "clock_s": CLOCK_S, "revision": REVISION,
         "protocol": PROTOCOL, "player_modes": {s: S[s].mode for s in SEATS}})
    write_final()
    threading.Thread(target=watchdog, daemon=True).start()
    open(os.path.join(DATA, "server.pid"), "w").write(str(os.getpid()))
    print("basketball duel service ready", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
