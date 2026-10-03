"""8-ball service, program play (eai-standard-turn/1.0; docs/EAI_STANDARD_REALTIME_1_0.md, last section).

The player plays one rack of American 8-ball (eightball.py: rules, pooltool physics) against a scripted opponent. The
table is static between shots, so the world waits for the player: there is no real-time clock. Service rules:
  * `POST /start` starts the game and the player's chess clock (CLOCK_BUDGET_S, 60 min). The clock runs only on the
    player's turn (thinking, tools, the model API, programs, reviews); it is stopped while this service simulates a
    shot or the opponent's turn. When it runs out the game ends as a loss (`reason = clock_expired`).
  * After each of the player's shots the game waits for its review (`POST /ready` {why, plan}); only then does it go
    on (the opponent's turn when the turn passed, or the player's next shot).
  * Program play (RCB_ACT_RULE=program): the player's own program may act without a new model response, but a live,
    metered model session is required (think_clock.py). One act in flight: a second act while one is pending gets
    HTTP 429 `busy` (counted as `refused_busy`).
Endpoints: GET /spec, GET /status, POST /observe {"aim": DEG}, POST /start, POST /act, POST /ready. Every reply carries the
current state and the shots played since the previous call.
Evidence (/data): episode.jsonl, final.json, trajectory.json (+ .npz), replay_check.json, replay.mp4. The fresh-process
replay (replay.py) runs on game end or SIGUSR1 (the verifier's collect hook).
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
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eightball as E8  # noqa: E402
import render  # noqa: E402
from replay import follow, shot, source_sha  # noqa: E402
from think_clock import MeterError, ThinkClock, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402

DATA = os.environ.get("RCB_DATA", "/data")
os.makedirs(DATA, exist_ok=True)
PROTOCOL = "eai-standard-turn/1.0"
REVISION = "eightball-turn-2"
CLOCK_BUDGET_S = float(os.environ.get("CLOCK_BUDGET_S", "3600"))
DEFAULT_SEEDS = {1: 1, 2: 2}                       # the levels' first official seeds (spec.py OFFICIAL_SEEDS)
LEVEL = int(os.environ.get("MATCH_LEVEL", "1"))
if LEVEL not in E8.LEVELS:
    raise ValueError(f"MATCH_LEVEL must be one of {sorted(E8.LEVELS)}")
SEED = int(os.environ.get("MATCH_SEED") or DEFAULT_SEEDS[LEVEL])
PLAYER_MODE = os.environ.get("RCB_PLAYER_MODE", "model")
if PLAYER_MODE not in ("model", "oracle"):
    raise ValueError("RCB_PLAYER_MODE must be model or oracle")
REVIEW_MAX_CHARS = 2000
REVIEW_PROMPT = ("Shot played. Review it: `game ready \"WHY\" \"PLAN\"` (why the shot went well or badly; what you will "
                 "change). The game goes on only then; your clock runs.")
WHO = {0: "you", 1: "opponent"}

CLOCK = ThinkClock(usage_file=os.environ.get("THINK_USAGE_FILE", os.path.join(DATA, "think_usage.json")))
LOCK = threading.RLock()
ACT_BUSY = threading.Lock()
E8.simulate({"cue": (0.3, 0.3), "1": (0.3, 0.8)}, 90.0, 1.0, 0.0, 0.0)     # warm the JIT before the opening break
M = E8.Match(LEVEL, SEED)
G = M.g
E = {"t0": time.time(), "started": False, "awaiting_review": False, "followed": True, "reviews": [], "decisions": [],
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
        f.write(json.dumps({"ts": round(time.time(), 3), "shot_k": G.k, **ev}, default=float) + "\n")


def won() -> bool:
    return G.done and G.winner == 0 and E["reason"] == "match_over"


def settle_tie() -> None:
    """With LOCK held: a tie at the shot limit goes to the player with more chess-clock time left. The scripted
    opponent's clock never runs (it keeps CLOCK_BUDGET_S), so a tie is decided against the player."""
    if G.done and G.winner is None:
        clocks = [round(clock_left(), 3), CLOCK_BUDGET_S]
        G.resolve_tiebreak(0 if clocks[0] > clocks[1] else 1, clocks)
        E["tiebreak"] = dict(G.tiebreak)
        log({"ev": "tiebreak", **E["tiebreak"]})


def balls_left(p: int) -> int:
    return len(G.left_in_group(p)) if G.group[p] else 7


# ----------------------------------------------------------------------------- evidence
def write_final() -> None:
    with LOCK:
        usage = read_usage(CLOCK.usage_file)
        api = seat_api_errors(CLOCK.usage_file, usage)   # model-API errors: transient vs unrecovered (api_errors.py)
        out = {"protocol": PROTOCOL, "revision": REVISION, "level": LEVEL, "seed": SEED, "won": won(),
               "winner": None if G.winner is None else WHO[G.winner], "result": G.result, "game_over": G.done,
               "tiebreak": E.get("tiebreak"),
               "your_group": G.group[0], "opponent_group": G.group[1],
               "your_balls_left": balls_left(0), "opponent_balls_left": balls_left(1), "eight_on_table": "8" in G.pos,
               "our_shots": G.n_shots[0], "opponent_shots": G.n_shots[1], "n_shots_total": G.k,
               "done": G.done or E["reason"] is not None, "reason": E["reason"], "started": E["started"],
               "clock_forfeit": E["reason"] == "clock_expired", "clock_budget_s": CLOCK_BUDGET_S,
               "clock_left_s": round(clock_left(), 1), "n_decisions": E["n_decisions"],
               "refused_busy": E["refused_busy"], "refused_not_model": E["refused_not_model"], "n_calls": E["n_calls"],
               "decision_rule": CLOCK.rule, "player_mode": PLAYER_MODE, "n_reviews": len(E["reviews"]),
               "reviews": E["reviews"], "elapsed_s": round(time.time() - E["t0"], 1), "live_sha": G.state_sha(),
               "shots": G.shots, "finalized": E["finalized"], "graded_ready": E["finalized"]}
        out.update(E["extra"])
        out["meter_error"] = bool(E["meter_error"] or (PLAYER_MODE == "model" and E["started"] and
                                                       (not usage.get("epoch") or usage.get("requests", 0) < 1)))
        out["proxy_error"] = api["api_failure"]     # unrecovered, or more than MAX_TRANSIENT_API_ERRORS transient
        out["transient_api_errors"] = api["transient_api_errors"]
        out["unrecovered_api_errors"] = api["unrecovered_api_errors"]
        out["sim_error"] = E["reason"] == "error"
        replay_ok = bool(E["finalized"] and out.get("deterministic"))
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
            decs = [dict(d) for d in E["decisions"]]
            tr = {"protocol": PROTOCOL, "revision": REVISION, "level": LEVEL, "seed": SEED, "decisions": decs,
                  "tiebreak": E.get("tiebreak"),
                  "followed": E["followed"], "live_sha": G.state_sha(), "live_winner": G.winner,
                  "source_sha": source_sha()}
        tp = os.path.join(DATA, "trajectory.json")
        with open(tp, "w") as f:
            json.dump(tr, f)
        # PROTOCOL §4.8: the trajectory also as trajectory.npz: aim_deg, speed, spin_x, spin_y, cue_x, cue_y (NaN: no
        # placement), the call: ball (-1: none, 0: safety) and pocket (index into POCKET_IDS, -1: none) per shot
        # of the player
        np.savez(os.path.join(DATA, "trajectory.npz"),
                 actions=np.array([[d["aim_deg"], d["speed"], d["spin_x"], d["spin_y"],
                                    *(d["cue_xy"] if d.get("cue_xy") is not None else (np.nan, np.nan)),
                                    *_call_cols(d.get("call"))] for d in decs],
                                  dtype=np.float64).reshape(-1, 8), level=LEVEL, seed=SEED, followed=E["followed"])
        p = subprocess.run([sys.executable, os.path.join(HERE, "replay.py"), tp], capture_output=True, text=True,
                           timeout=float(os.environ.get("RCB_REPLAY_TIMEOUT_S", "600")))
        lines = [json.loads(x) for x in p.stdout.splitlines() if x.startswith("{")]
        rp = lines[0] if lines else {}
        with open(os.path.join(DATA, "replay_check.json"), "w") as f:
            json.dump(rp, f)
        E["extra"] = {"n_replayed_decisions": len(decs), "replay_winner": rp.get("replay_winner"),
                      "replay_sha": rp.get("replay_sha"), "source_sha": tr["source_sha"],
                      "deterministic": (rp.get("replay_sha") == tr["live_sha"] and rp.get("source_sha") == tr["source_sha"]
                                        and rp.get("replay_winner") == tr["live_winner"]),
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
    E["final_obs"] = {"done": True, "reason": reason, "won": won(), "result": G.result,
                      "winner": None if G.winner is None else WHO[G.winner],
                      "note": ("your clock ran out: the game is lost" if reason == "clock_expired" else "the game is over")}
    E["finalizing"] = True
    log({"ev": "end", "reason": reason, "winner": G.winner, "result": G.result})
    write_final()
    threading.Thread(target=finalize, daemon=True).start()


# ----------------------------------------------------------------------------- observation
def state() -> dict:
    turn = ("over" if E["final_obs"] is not None else "not started" if not E["started"]
            else "review" if E["awaiting_review"] else "you")
    o = {"turn": turn, "your_group": G.group_name(0), "opponent_group": G.group_name(1),
         "your_balls_left": balls_left(0), "opponent_balls_left": balls_left(1),
         "your_shots": G.n_shots[0], "max_shots": E8.MAX_SHOTS, "clock_left_s": round(clock_left(), 1),
         "done": E["final_obs"] is not None}
    if turn == "you":
        o.update(break_shot=not G.break_done,
                 ball_in_hand={None: None, "kitchen": "above the head string (y < L/4)",
                               "anywhere": "anywhere"}[G.ball_in_hand],
                 on_the_8=G.on_the_8(0), call_required=G.must_call(0))
    return o


def shot_text(s: dict) -> dict:
    o = {"player": WHO[s["player"]], "break": s["break"], "first_hit": s["first_hit"], "potted": s["potted"],
         "pockets": s["pockets"], "foul": s["foul"], "cue_ball_pocketed": s["cue_ball_pocketed"],
         "keeps_turn": s["keeps_turn"]}
    if s["call"]:
        o["call"], o["call_made"] = s["call"], s["call_made"]
    if s["cue_placed_at"]:
        o["cue_placed_at"] = s["cue_placed_at"]
    if s["eight_respotted"]:
        o["eight_respotted"] = "the 8 was potted on the break and spotted again on the foot spot"
    if s["group_assigned"]:
        g = s["group_assigned"]
        o["groups_assigned"] = {WHO[s["player"]]: g, WHO[1 - s["player"]]: E8.OTHER_GROUP[g]}
    if s["game_over"]:
        o["game_over"] = s["result"]
    if s["player"] == 0:
        o["your_shot"] = s["requested"]
    return o


def reply(out: dict) -> dict:
    """Every reply: the current state and the shots played since the previous call."""
    out["state"] = state()
    out["shots_since_your_last_call"], E["news"] = E["news"], []
    return out


def views(aim: float | None) -> dict:
    phi = render.default_sight_phi(G.pos) if aim is None else float(aim) % 360.0
    key = (G.k, round(phi, 3))
    if key not in E["view_cache"]:
        if len(E["view_cache"]) > 16:
            E["view_cache"] = {}
        v = render.views(G.pos, phi)
        E["view_cache"][key] = {"images_png_b64": {"top": base64.b64encode(v["top"]).decode(),
                                                   "sight": base64.b64encode(v["sight"]).decode()},
                                "sight_aim_deg": round(phi, 3), "cameras": v["cameras"]}
    return E["view_cache"][key]


def observation(aim: float | None = None) -> dict:
    o = {"shot_number": G.k + 1, "balls_on_table": G.objects_left(), "cue_ball_on_table": "cue" in G.pos}
    if E["awaiting_review"]:
        o["review_due"] = REVIEW_PROMPT
    o.update(views(aim))
    return o


# ----------------------------------------------------------------------------- endpoints
def gate() -> tuple[int, dict] | None:
    if E["final_obs"] is not None:
        return 200, reply(dict(E["final_obs"]))
    if not E["started"]:
        return 409, reply({"error": "the game has not started: `game start` starts it (and your clock)"})
    return None


def start() -> tuple[int, dict]:
    if E["final_obs"] is not None:
        return 200, reply(dict(E["final_obs"]))
    if E["started"]:
        return 409, reply({"error": "the game has already started"})
    CLOCK.check_ready()                    # program play: a live, metered model session (model mode)
    E["started"] = True
    log({"ev": "match_start", "level": LEVEL, "seed": SEED})
    if G.done:                             # the opponent's break-and-run (level 2)
        end("match_over")
        return 200, reply(dict(E["final_obs"]))
    clock_run()
    write_final()
    return 200, reply({"started": True, "observation": observation()})


def observe(aim: float | None) -> tuple[int, dict]:
    g = gate()
    if g:
        return g
    E["n_calls"]["observe"] += 1
    return 200, reply({"observation": observation(aim)})


def validate(body: dict) -> dict | str:
    if body.get("type", "shoot") != "shoot":
        return "the action is: shoot AIM_DEG SPEED [SPIN_X SPIN_Y] [cue=X,Y] [call=BALL:POCKET|safety]"
    try:
        phi = float(body["aim_deg"]); V = float(body["speed"])
        a = float(body.get("spin_x", 0.0)); b = float(body.get("spin_y", 0.0))
        cue = None
        if body.get("cue_x") is not None or body.get("cue_y") is not None:
            cue = [float(body["cue_x"]), float(body["cue_y"])]
        call = body.get("call")
        call = None if call in (None, "") else str(call)
    except Exception:  # noqa: BLE001
        return "shoot needs aim_deg, speed and optionally spin_x, spin_y, cue_x and cue_y (numbers), call (BALL:POCKET or safety)"
    if not all(math.isfinite(x) for x in (phi, V, a, b)):
        return "numbers must be finite"
    if not (E8.V_RANGE[0] <= V <= E8.V_RANGE[1]):
        return f"speed must be in [{E8.V_RANGE[0]}, {E8.V_RANGE[1]}] m/s"
    if math.hypot(a, b) > E8.SPIN_MAX:
        return f"tip offset too far from centre: sqrt(spin_x^2 + spin_y^2) must be <= {E8.SPIN_MAX} (a miscue)"
    dec = {"type": "shoot", "aim_deg": phi % 360.0, "speed": V, "spin_x": a, "spin_y": b}
    if cue is not None:
        dec["cue_xy"] = cue
    if call is not None:
        dec["call"] = call
    return G.check(0, dec) or dec


def act(body: dict) -> tuple[int, dict]:
    with LOCK:
        g = gate()
        if g:
            return g
        E["n_calls"]["act"] += 1
        if E["awaiting_review"]:
            return 409, reply({"error": "review your shot first: `game ready \"WHY\" \"PLAN\"`",
                               "review_prompt": REVIEW_PROMPT})
        dec = validate(body)
        if isinstance(dec, str):
            return 400, reply({"error": dec})
    if not CLOCK.decided_by_model():       # program play: raises MeterError without a live metered session
        with LOCK:
            E["refused_not_model"] += 1
            return 429, reply({"refused": True, "error": "refused: no new model call completed since your previous shot"})
    with LOCK:
        if E["final_obs"] is not None:
            return 200, reply(dict(E["final_obs"]))
        clock_stop()                       # the service's own computing time is not on your clock
        E["n_decisions"] += 1
        E["decisions"].append(dec)
        log({"ev": "decision", "decision": dec, "clock_left_s": round(clock_left(), 1), "model_call": CLOCK.last_call()})
        rec = shot(M, dec)
        settle_tie()
        E["followed"] = False
        E["news"].append(shot_text(rec))
        log({"ev": "shot", **rec})
        out = {"accepted": dec, "your_shot": shot_text(rec)}
        if G.done:
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
            return 409, reply({"error": "no review is due now (a review is due after each of your shots)"})
        why, plan = body.get("why"), body.get("plan")
        if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
            return 400, reply({"error": "ready needs two non-empty texts: WHY and PLAN"})
        if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
            return 400, reply({"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"})
        clock_stop()
        rv = {"after_shot": G.k, "your_shots": G.n_shots[0], "why": why.strip(), "plan": plan.strip(),
              "clock_left_s": round(clock_left(), 1), "t": round(time.time() - E["t0"], 1)}
        E["reviews"].append(rv)
        log({"ev": "review", **rv})
        E["awaiting_review"] = False
        recs = follow(M)
        settle_tie()
        E["followed"] = True
        for r in recs:
            E["news"].append(shot_text(r))
            log({"ev": "shot", **r})
        out = {"accepted": "review recorded", "opponent_shots": [shot_text(r) for r in recs]}
        if G.done:
            end("match_over")
            out.update(E["final_obs"])
        else:
            clock_run()
            out["next"] = observation()
        write_final()
        return 200, reply(out)


def spec() -> dict:
    return {
        "protocol": PROTOCOL, "revision": REVISION, "simulator": "pooltool 0.6.0 (event-based billiards physics)",
        "clock": {"total_s": CLOCK_BUDGET_S, "rule": "chess clock: runs only on your turn (reviews included), "
                  "stopped while the service plays shots; when it runs out the game is lost"},
        "decision_rule": ("program play: your own program may act without a new model response; one act in flight"
                          if os.environ.get("RCB_ACT_RULE") == "program" else
                          "one new completed model response per act"),
        "rules": "WPA Rules of Play, effective 2025-09-15, 8-Ball (with the deviations listed in the instructions)",
        "match": {"type": "8-ball, one rack", "opponent_level": LEVEL,
                 "first_player": "you" if G.breaker == 0 else "opponent", "first_player_rule": "the first player breaks",
                 "solids": list(E8.SOLIDS), "stripes": list(E8.STRIPES), "max_shots_each": E8.MAX_SHOTS},
        "action": {"shoot": {"aim_deg": "cue direction in the table plane, degrees counter-clockwise from +x",
                             "speed": f"cue stick speed at impact, m/s, in [{E8.V_RANGE[0]}, {E8.V_RANGE[1]}]",
                             "spin_x, spin_y": f"tip offset in ball radii, sqrt(x^2+y^2) <= {E8.SPIN_MAX}",
                             "cue_x, cue_y": "ball in hand only: where to place the cue ball first (optional)",
                             "call": (f"every shot after the break (not the break): BALL:POCKET with a ball you may hit first and a pocket "
                                      f"of {list(E8.POCKET_IDS)}, e.g. 3:rc or 8:lt; or safety")},
                   "execution_scatter_sigma": E8.EXEC_SIGMA},
        "table": {"playing_surface": {"x": [0.0, round(E8.W, 4)], "y": [0.0, round(E8.L, 4)]}, "ball_radius": E8.R,
                  "cloth_z": 0.0, "ball_centre_z": E8.R,
                  "pockets": {k: {"centre_xy": [round(float(c[0]), 4), round(float(c[1]), 4)],
                                  "radius": float(E8.TABLE.pockets[k].radius), "where": E8.POCKET_NAMES[k]}
                              for k, c in E8.POCKETS.items()},
                  "head_spot": [round(E8.HEAD_SPOT[0], 4), round(E8.HEAD_SPOT[1], 4)],
                  "foot_spot": [round(E8.FOOT_SPOT[0], 4), round(E8.FOOT_SPOT[1], 4)],
                  "head_string_y": round(E8.HEAD_STRING_Y, 4)},
        "cameras": {"top": render.camera_info(render.top_camera(), "top"),
                    "sight": {"eye": "0.75 m behind the cue ball centre along -aim, 0.32 m above the cloth",
                              "looks_at": "the cloth 1.0 m ahead of the cue ball along the aim",
                              "image_px": list(render.SIGHT["size"]), "fx": render.SIGHT["f"], "fy": render.SIGHT["f"],
                              "note": "its exact pose for each image is in the observation's `cameras`"}},
    }


def _call_cols(call):
    c = None if call is None else E8.parse_call(call)
    if c is None:
        return (-1.0, -1.0)
    if c == "safety":
        return (0.0, -1.0)
    return (float(c[0]), float(E8.POCKET_IDS.index(c[1])))


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
        u = urllib.parse.urlparse(self.path)
        if u.path == "/spec":
            return self._send(200, SPEC)
        if u.path == "/status":
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
            aim = body.get("aim")
            if aim is not None:
                try:
                    aim = float(aim)
                    assert math.isfinite(aim)
                except Exception:  # noqa: BLE001
                    return self._send(400, {"error": "aim must be a number (degrees)"})

            def run_observe():
                with LOCK:
                    return observe(aim)
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
    for s in M.opening:                    # level 2: the opponent broke (and played on while it potted)
        E["news"].append(shot_text(s))
    log({"ev": "start", "level": LEVEL, "seed": SEED, "clock_budget_s": CLOCK_BUDGET_S, "decision_rule": CLOCK.rule,
         "player_mode": PLAYER_MODE, "protocol": PROTOCOL, "source_sha": source_sha()})
    threading.Thread(target=clock_watch, daemon=True).start()
    write_final()
    with open(os.path.join(DATA, "server.pid"), "w") as f:
        f.write(str(os.getpid()))
    print("8-ball service ready", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), H).serve_forever()

