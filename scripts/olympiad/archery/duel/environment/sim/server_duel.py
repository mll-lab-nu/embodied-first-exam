"""Archery duel: the two-seat sim service of archery-duel-program-standard (eai-standard-turn/1.0, program play).

Two agents (seats A and B) shoot the same round on identical lanes (archery.Duel): 4 ends x 3 arrows at 50, 70, 70
and 90 m, the same wind for the n-th arrow of either player and the same scatter draws. In each end one player shoots
its 3 arrows, then the other; FIRST_PLAYER shoots first in ends 1 and 3, the other player in ends 2 and 4. Highest
total wins (cumulative, compound-style match play); a tie goes to shoot-off arrows (one each at 70 m, FIRST_PLAYER
first; higher score, then nearer the centre), repeated until the tie is broken.
Rules enforced here:
  * turns: an action or review out of turn gets HTTP 409; the camera images are served only on your own turn (the
    windsocks show the wind of your next arrow); one action in flight per seat (HTTP 429);
  * program play (RCB_ACT_RULE=program): a live metered model session per seat (think_clock.py);
  * start: the match begins when both seats have sent `start`; after the first, the second has START_TIMEOUT_S;
  * chess clock: CLOCK_S per seat, running only on its own turn (its arrows and reviews; service time excluded); a
    seat whose clock runs out, or that stops playing on its turn, loses the match;
  * after each arrow (except the one that ends the match) its archer sends the review (`ready`).
Endpoints (per seat, /A/... or /B/...): GET spec, GET status, POST start, POST observe, POST act, POST ready, POST wait.
"""
from __future__ import annotations

import base64
import io
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
os.environ["ARCHERY_SEED"] = str(SEED)                    # the wind sequence and the scatter draws
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archery as A  # noqa: E402
from think_clock import ThinkClock, MeterError, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(DATA, exist_ok=True)
PROTOCOL = "eai-standard-turn/1.0"
REVISION = "archery-duel-program-2"
SEATS, OTHER = A.SEATS, A.OTHER
FIRST = os.environ.get("FIRST_PLAYER", "A")
if FIRST not in SEATS:
    raise ValueError("FIRST_PLAYER must be A or B")
CLOCK_S = float(os.environ.get("CLOCK_S", "3600"))
START_TIMEOUT_S = float(os.environ.get("START_TIMEOUT_S", "1800"))
WAIT_MAX_S = 60.0
REVIEW_MAX_CHARS = 2000
IMAGE_LAYOUT = ("one PNG of four tiles (`game spec` image.tiles: x, y, width, height): archer (from just behind the bow, "
                "down the range; windsocks at 1/4, 1/2, 3/4 of the distance on the left and one by the target), scope "
                "(centred on the gold), side (across the range at the middle windsock; image right = towards the "
                "target) and target (close-up of the face with your arrows of this end: magenta = arrow 1, lime = 2, "
                "cyan = 3). The windsocks show the wind for the arrow you are about to shoot.")


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
M = A.Duel(FIRST)
S = {s: Seat(s) for s in SEATS}
V = A.Views()
E = {"t0": time.time(), "phase": "prepare", "start_deadline": None, "on_turn": None, "review_due": None,
     "reviews": [], "finalizing": False, "finalized": False, "reason": None, "extra": {}, "errors": [],
     "view_cache": {}, "last_seen": {s: 0 for s in SEATS}, "arrows": []}


def log(ev: dict) -> None:
    with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), **ev}, default=float) + "\n")


def png(im) -> str:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(im).save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


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
    log({"ev": "end", "reason": reason, "totals": M.totals(), "winner": M.winner, "forfeit": M.forfeit})
    write_final()
    COND.notify_all()
    threading.Thread(target=finalize, daemon=True).start()


def lose(seat: str, why: str) -> None:
    M.lose(seat, why)
    log({"ev": "lost", "seat": seat, "why": why, "clock_used_s": round(S[seat].clock_used(), 1)})
    end(why)


def scorecard(seat: str) -> list:
    r = M.rounds[seat]
    return [{"end": e + 1, "distance_m": D, "arrows": [A.label(v, x) for v, x in zip(r.scores[e], r.xs[e])],
             "end_score": sum(r.scores[e])} for e, D in enumerate(A.DISTANCES)]


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
               "reason": E["reason"], "totals": M.totals(), "scorecards": {s: scorecard(s) for s in SEATS},
               "n_x": {s: M.rounds[s].n_x() for s in SEATS}, "shootoff": M.shootoff,
               "winner": M.winner if valid else None, "match_winner": M.winner,
               "forfeit": M.forfeit,
               "clock_forfeit": M.forfeit["seat"] if M.forfeit and M.forfeit["why"] == "clock" else None,
               "abandoned": M.forfeit["seat"] if M.forfeit and M.forfeit["why"] == "abandoned" else None,
               "started": {s: S[s].started for s in SEATS}, "player_modes": {s: S[s].mode for s in SEATS},
               "clock_s": CLOCK_S, "clock_used_s": {s: round(S[s].clock_used(), 1) for s in SEATS},
               "seats": {s: S[s].stats for s in SEATS}, "reviews": E["reviews"], "decisions": M.decisions,
               "arrows": E["arrows"], "errors": E["errors"], "meter_error": meter, "proxy_error": proxy,
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
                     actions=np.asarray([[d["elev_deg"], d["azim_deg"], d["draw"]] for d in shots], dtype=np.float64).reshape(-1, 3),
                     seat=np.asarray([d["seat"] for d in shots]), seed=SEED, first_player=FIRST)
        p = subprocess.run([sys.executable, os.path.join(HERE, "archery.py"), "replay_duel", tr], capture_output=True,
                           text=True, timeout=300, env=dict(os.environ, ARCHERY_SEED=str(SEED)))
        rp = json.loads(p.stdout.strip().splitlines()[-1])
        json.dump(rp, open(os.path.join(DATA, "replay_check.json"), "w"))
        with COND:
            E["extra"] = {"n_actions": len(decs), "deterministic": rp["sha"] == live_sha and rp["totals"] == M.totals()
                          and rp["winner"] == M.winner, "replay_totals": rp["totals"], "replay_winner": rp["winner"]}
            log({"ev": "replay", **E["extra"]})
            E["finalized"] = True
            write_final()
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
            try:                                   # each seat's round (the shoot-off is not drawn)
                for s in SEATS:
                    r = M.rounds[s]
                    shots = [{"end": x["end"], "arrow": x["arrow"], "elev_deg": x["elev_deg"], "azim_deg": x["azim_deg"],
                              "draw": x["draw"]} for x in r.log]
                    if shots:
                        A.render_video(shots, os.path.join(DATA, f"replay_{s}.mp4"))
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
    """The four decision images for `seat`'s next arrow (its own lane: its arrows of this end, the wind of its arrow)."""
    D, w, e, a = M.shooting(seat)
    stuck = M.rounds[seat].stuck if M.phase == "round" else []      # shoot-off: a fresh face
    key = (seat, len(M.decisions))
    if key not in E["view_cache"]:
        E["view_cache"] = {key: base64.b64encode(A.compose(V.render(D, w, stuck))).decode()}
    return E["view_cache"][key]


def state(seat: str) -> dict:
    o = OTHER[seat]
    news = [{"by": "you" if r["seat"] == seat else "opponent", "end": r["end"], "arrow": r["arrow"],
             "score": r["call"], **({"shootoff": True} if r.get("shootoff") else {})}
            for r in E["arrows"][E["last_seen"][seat]:]]
    E["last_seen"][seat] = len(E["arrows"])
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
           "totals": {"you": M.rounds[seat].total(), "opponent": M.rounds[o].total()},
           "clock_left_s": round(S[seat].clock_left(), 1), "opponent_clock_left_s": round(S[o].clock_left(), 1),
           "shots_since_your_last_call": news}
    if not M.done and E["phase"] != "over":
        D, w, e, a = M.shooting(seat)
        r = M.rounds[seat]
        if M.phase == "round" and not r.done:
            out.update({"stage": "round", "end": e + 1, "of_ends": A.N_ENDS, "arrow": a + 1, "distance_m": D,
                        "this_end": [A.label(v, x) for v, x in zip(r.scores[e], r.xs[e])],
                        "you_shoot_first_this_end": M.end_order(e)[0] == seat})
        elif M.phase == "shootoff":
            out.update({"stage": "shoot-off", "shootoff_pair": a + 1, "distance_m": D,
                        "shootoff": [{"by": "you" if x["seat"] == seat else "opponent", "score": x["call"],
                                      "distance_from_centre_m": None if x["r_m"] is None else round(x["r_m"], 4)}
                                     for x in M.shootoff]})
        else:
            out["stage"] = "your round is complete"
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
        return 409, {"error": "the camera images are served on your turn only (before each of your arrows)",
                     "state": state(seat)}
    S[seat].stats["n_observe"] += 1
    return 200, {"state": state(seat), "observation": {"image_png_b64": views(seat), "image_layout": IMAGE_LAYOUT}}


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


def act(seat: str, body: dict):
    g = gate(seat)
    if g:
        return g
    if E["on_turn"] != seat or E["review_due"] == seat:
        S[seat].stats["refused_turn"] += 1
        why = "review your last arrow first" if E["review_due"] == seat else "it is not your turn"
        return 409, {"error": why, "state": state(seat)}
    dec = validate(body)
    if isinstance(dec, str):
        return 400, {"error": dec}
    if not S[seat].clock.decided_by_model():
        S[seat].stats["refused_not_model"] += 1
        return 429, {"refused": True, "error": "refused: no new model response since your previous arrow"}
    S[seat].stats["n_act"] += 1
    if S[seat].clock_left() < 0:
        lose(seat, "clock")
        return 200, {"clock_forfeit": "your clock ran out: you lose the match", "state": state(seat)}
    D, w, e, a = M.shooting(seat)
    stuck = list(M.rounds[seat].stuck) if M.phase == "round" else []
    rec = M.shoot(seat, dec["elev_deg"], dec["azim_deg"], dec["draw"])
    fl = rec.pop("_flight")
    E["arrows"].append({k: v for k, v in rec.items() if k != "trail"})
    log({"ev": "arrow", "decision": dec, "model_call": S[seat].clock.last_call(),
         "clock_used_s": round(S[seat].clock_used(), 1), **{k: v for k, v in rec.items() if k != "trail"}})
    V.set_state(D, w, stuck + [(fl["hit"], fl["vel"], fl["kind"])])
    out = {"accepted": dec, "last_arrow": {"end": rec["end"], "arrow": rec["arrow"], "score": rec["call"],
                                           **({"spotter": rec["miss"]} if rec.get("miss") else {}),
                                           **({"shootoff": True} if rec.get("shootoff") else {})},
           "landed_image_b64": png(V._shot(D, A.CLOSE_W, A.CLOSE_H, A.close_fovy(), (D - A.CLOSE_BACK, 0.0, A.FACE_Z),
                                           0.0, 0.0))}
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
        return 409, {"error": "no review is due from you now (reviews follow each of your arrows)", "state": state(seat)}
    why, plan = body.get("why"), body.get("plan")
    if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
        return 400, {"error": "ready needs two non-empty texts: WHY and PLAN"}
    if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
        return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
    last = [r for r in E["arrows"] if r["seat"] == seat][-1]
    rv = {"seat": seat, "end": last["end"], "arrow": last["arrow"], "score": last["call"], "why": why.strip(),
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
    return {
        "seat": seat, "protocol": PROTOCOL, "revision": REVISION, "player_mode": S[seat].mode,
        "match": {"format": "4 ends x 3 arrows each (50, 70, 70, 90 m) on identical lanes; in each end one player "
                            "shoots its 3 arrows, then the other; first_player shoots first in ends 1 and 3",
                  "first_player": FIRST, "scoring": "cumulative total, as in compound match play (WA 12.1.4.3)",
                  "winner": "the higher total",
                  "tie": f"shoot-off (WA 12.5.2.2): one arrow each at {A.SHOOTOFF_D:g} m (first_player first); the "
                         "higher score wins, then the arrow nearer the centre; tied pairs are repeated until the tie "
                         "is broken",
                  "same_conditions": "the n-th arrow of either player has the same wind and the same scatter draw"},
        "round": {"ends": A.spec_ends(), "arrows_per_end": A.ARROWS_PER_END,
                  "scoring": "ring value 10 (inner 10 = X, counts 10) down to 1; off the face or off the boss = M (0); "
                             "an arrow touching a ring line scores the higher ring"},
        "clock": {"total_s": CLOCK_S, "runs": "on your turn only (your arrows and your reviews); the time the service "
                  "is busy does not count; out of time = you lose the match", "start_window_s": START_TIMEOUT_S},
        "decision_rule": ("program play: your own program may shoot without a new model response; one action in "
                          "flight" if os.environ.get("RCB_ACT_RULE") == "program" else
                          "a new model response before every arrow"),
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
                  "windsocks": {"reading": "a windsock points downwind; its angle below horizontal = 90 deg x "
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
    print("archery duel service ready", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
