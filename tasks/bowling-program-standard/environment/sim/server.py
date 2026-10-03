#!/usr/bin/env python3
"""Turn-based (precision) sports service, `eai-standard-turn/1.0` (docs/EAI_STANDARD_REALTIME_1_0.md, last section).

One file for every precision sport (byte-identical copies in scripts/olympiad/shared/<sport>/sim/); the sport is the
module `sport.py` next to it. The world waits between shots. Each player has a chess clock (CLOCK_S) that runs only on
its own turn, reviews included, and stops while the service simulates and renders a shot; a player whose clock runs out
loses (single player: the match ends). After each shot the player hands in a review (`ready`) before the game goes on
(not after the shot that ends the match).

  single player   TURN_SEATS=A; calls at /<call>; RCB_SEED; the agent's metering in THINK_USAGE_FILE
  duel            TURN_SEATS=A,B; calls at /<seat>/<call> (only from that seat's host, SEAT_HOSTS); DUEL_SEED,
                  FIRST_PLAYER; meters /data/think_usage_<seat>.json; the second player must start within
                  START_TIMEOUT_S of the first; turns follow the sport (`sport.Match.turn`); an action out of turn: 409

Calls: GET spec, GET status, POST observe, POST act, POST start, POST ready, POST wait (long-poll, at most 60 s:
returns when it is the caller's turn or the match is over). Every reply carries `state` (score, whose turn,
clock_left_s) and `shots_since_your_last_call`. `observe` returns one PNG (`observation.image_png_b64`), the sport's
camera views tiled as `sport.TILES` says. Program play (RCB_ACT_RULE=program):
an act needs a live metered model session (think_clock.py), not a new response; one act in flight per seat (429 busy).

At the end (or on SIGUSR1 from the verifier's collect hook) the service writes trajectory.json / .npz, replays it in a
fresh process (`server.py --replay DIR` -> replay_check.json), optionally renders the video (`server.py --video DIR SEAT`, one process per seat),
and sets `graded_ready` in final.json.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DATA = Path(os.environ.get("RCB_DATA", "/data"))
SEATS = [s for s in os.environ.get("TURN_SEATS", "A").split(",") if s]
DUEL = len(SEATS) > 1
PROTOCOL = "eai-standard-turn/1.0"
REVISION = "turn-1"
OFFLINE = next((Path(sys.argv[sys.argv.index(f) + 1]) for f in ("--replay", "--video") if f in sys.argv), None)
if OFFLINE is not None:          # the recorded configuration, not this process's environment
    os.environ["TURN_SEED"] = str(json.loads((OFFLINE / "trajectory.json").read_text())["seed"])
else:
    os.environ["TURN_SEED"] = os.environ.get("DUEL_SEED" if DUEL else "RCB_SEED", "")
import sport as S  # noqa: E402
from think_clock import MeterError, ThinkClock, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402

CLOCK_S = float(os.environ.get("CLOCK_S", "3600"))
START_S = float(os.environ.get("START_TIMEOUT_S", "1800"))
FIRST = os.environ.get("FIRST_PLAYER", "A") if DUEL else SEATS[0]
if FIRST not in SEATS:
    raise ValueError(f"FIRST_PLAYER must be one of {SEATS}")
ORDER = [FIRST] + [s for s in SEATS if s != FIRST]
REVIEW_MAX_CHARS = 2000
PROGRAM = os.environ.get("RCB_ACT_RULE") == "program"


def source_sha() -> str:
    h = hashlib.sha256()
    for p in sorted(HERE.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(str(p.relative_to(HERE)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def actions_sha(actions: dict) -> str:
    return hashlib.sha256(json.dumps(actions, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ------------------------------------------------------------------------------------------------ offline: replay, video
def decision(scores: dict, actions: dict, order: list, reason, forfeiting):
    """The duel's winner and how it was decided, from the scores and the recorded actions only: a forfeit (clock out,
    start window) goes to the other player; otherwise the sport's score with its tie-break (sport.decide); if still
    level, the player with more chess-clock time left at the last shot (both clocks are recorded with every shot, in
    ms; an exact tie goes to the second player). Used live and by the replay, so the replay reproduces the decision."""
    seats = list(scores)
    if len(seats) < 2:
        return {"winner": None, "decided_by": None}
    if forfeiting:
        return {"winner": next(s for s in seats if s != forfeiting), "decided_by": reason}
    if reason != "match_over":
        return {"winner": None, "decided_by": None}
    w = S.decide(scores)
    if w is not None:
        tb = any(scores[s].get("rolloffs") or scores[s].get("playoff") for s in seats)
        return {"winner": w, "decided_by": "tiebreak" if tb else "score"}
    last = max((a for s in seats for a in actions[s]), key=lambda a: a["shot_n"])
    left = last["clock_left_s"]
    return {"winner": order[0] if left[order[0]] > left[order[1]] else order[1], "decided_by": "clock",
            "clock_left_s": left}


def offline_replay(d: Path) -> None:
    tr = json.loads((d / "trajectory.json").read_text())
    seats = {s: S.replay(a, bool(tr["clock_out"][s]), int(tr.get("n_tiebreaks", 0))) for s, a in tr["actions"].items()}
    out = {"seed": S.SEED, "revision": REVISION, "source_sha": source_sha(), "actions_sha": actions_sha(tr["actions"]),
           "seats": seats,
           "decision": decision({s: v["score"] for s, v in seats.items()}, tr["actions"], tr["order"], tr["reason"],
                                tr["forfeiting"])}
    (d / "replay_check.json").write_text(json.dumps(out))


def offline_video(d: Path, seat: str) -> None:
    tr = json.loads((d / "trajectory.json").read_text())
    S.render_video(tr["actions"][seat], str(d / ("replay.mp4" if len(tr["actions"]) == 1 else f"replay_{seat}.mp4")))


# ------------------------------------------------------------------------------------------------ the live service
class ChessClock:
    def __init__(self, total: float):
        self.total, self.used, self.since = total, 0.0, None

    def run(self) -> None:
        if self.since is None:
            self.since = time.monotonic()

    def stop(self) -> None:
        if self.since is not None:
            self.used += time.monotonic() - self.since
            self.since = None

    def left(self) -> float:
        return self.total - self.used - (time.monotonic() - self.since if self.since is not None else 0.0)


class Seat:
    def __init__(self, name: str):
        self.name = name
        self.mode = os.environ.get(f"PLAYER_MODE_{name}", "model") if DUEL else os.environ.get("RCB_PLAYER_MODE", "model")
        usage = str(DATA / f"think_usage_{name}.json") if DUEL else os.environ.get(
            "THINK_USAGE_FILE", str(DATA / "think_usage.json"))
        self.think = ThinkClock(seconds_per_ktok=0.0, usage_file=usage, mode=self.mode)
        self.chess = ChessClock(CLOCK_S)
        self.flight = threading.Lock()          # one act in flight per seat
        self.started = False
        self.awaiting_review = False
        self.clock_out = False
        self.meter_error = False
        self.actions: list[dict] = []
        self.results: list[dict] = []
        self.reviews: list[dict] = []
        self.news: list[dict] = []
        self.views = None                       # (decision key, {name: PNG base64})
        self.calls = {k: 0 for k in ("spec", "status", "observe", "act", "start", "ready")}
        self.refused_busy = self.refused_not_model = self.refused_turn = 0


COND = threading.RLock()
TURN_CV = threading.Condition(COND)             # notified whenever the turn or the phase may have changed
WAIT_MAX_S = 60.0
M = None
SE: dict[str, Seat] = {}
E = {"phase": "prepare", "turn": None, "decided_by": None, "clock_left_at_end": None, "shot_n": 0, "simulating": False, "reason": None, "winner": None, "forfeiting": None,
     "first_start": None, "final_obs": None, "finalizing": False, "finalized": False, "extra": {}, "error": None}
T0 = time.time()


def log(ev: dict) -> None:
    with open(DATA / "episode.jsonl", "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), **ev}, default=float) + "\n")


def other(seat: str) -> str | None:
    return next((s for s in SEATS if s != seat), None)


def retime() -> None:
    """With COND held: the turn, and the chess clock of the player whose turn it is runs (not while simulating)."""
    t = None
    if E["phase"] == "running":
        t = next((s for s in SEATS if SE[s].awaiting_review), None) or M.turn(ORDER)
    E["turn"] = t
    for s, st in SE.items():
        (st.chess.run if s == t and not E["simulating"] else st.chess.stop)()
    TURN_CV.notify_all()


def state(seat: str) -> dict:
    st = SE[seat]
    out = {"phase": E["phase"], "your_turn": E["turn"] == seat, "turn": E["turn"], "awaiting_review": st.awaiting_review,
           "clock_left_s": round(max(0.0, st.chess.left()), 1), "your_game_over": M.done(seat)}
    if DUEL:
        o = other(seat)
        out.update(seat=seat, opponent_clock_left_s=round(max(0.0, SE[o].chess.left()), 1),
                   score={"you": M.summary(seat), "opponent": M.summary(o)})
    else:
        out["score"] = M.summary(seat)
    if E["phase"] == "over":
        out.update(reason=E["reason"], winner=E["winner"])
    return out


def take_news(seat: str) -> dict:
    n, SE[seat].news = SE[seat].news, []
    return {"shots_since_your_last_call": n}


def gate(seat: str, need_turn: bool):
    if E["final_obs"] is not None:
        return 200, dict(E["final_obs"], state=state(seat))
    if not SE[seat].started:
        return 409, {"error": "run `game start` first", "state": state(seat)}
    if E["phase"] != "running":
        return 409, {"error": "waiting for your opponent to start", "state": state(seat)}
    if need_turn and E["turn"] != seat:
        SE[seat].refused_turn += 1
        return 409, {"error": "not your turn", "state": state(seat)}
    return None


def render_views(seat: str) -> None:
    """With COND held: the current decision point's camera views tiled into one PNG (base64; sport.TILES), cached
    until the next shot."""
    key = json.dumps(M.decision(seat), sort_keys=True, default=float)
    if SE[seat].views is None or SE[seat].views[0] != key:
        import numpy as np
        from PIL import Image
        ims = M.views(seat)
        canvas = np.zeros((S.IMAGE_SIZE[1], S.IMAGE_SIZE[0], 3), dtype=np.uint8)
        for k, (x, y, w, h) in S.TILES.items():
            if k in ims:
                canvas[y:y + h, x:x + w] = ims[k][:h, :w, :3]
        b = io.BytesIO()
        Image.fromarray(canvas).save(b, format="PNG")
        SE[seat].views = (key, base64.b64encode(b.getvalue()).decode())


def do_spec(seat: str):
    with COND:
        SE[seat].calls["spec"] += 1
    rule = ("program play: your own program may observe and act without a new model response; one act in flight at a "
            "time" if PROGRAM else "each act needs a new completed model response")
    sp = S.spec(DUEL)
    sp["match"] = {"seed": S.SEED, **({"first_player": FIRST} if DUEL else {}), **sp.get("match", {})}
    sp.update({"protocol": PROTOCOL, "revision": REVISION, "sport": S.NAME,
               "clock": {"total_s": CLOCK_S, "runs": "only on your turn (thinking, tools, programs, reviews); not "
                         "while the service simulates a shot; when it runs out you lose"},
               "decision_rule": rule,
               "review": "after each of your shots (except one that ends the match) the game waits for `ready WHY PLAN`",
               "image": {"size_px": list(S.IMAGE_SIZE), "tiles": {k: {"x": x, "y": y, "w": w, "h": h}
                                                                    for k, (x, y, w, h) in S.TILES.items()}}})
    if DUEL:
        sp.update(seat=seat, seats=SEATS, start_timeout_s=START_S)
    return 200, sp


def do_status(seat: str):
    with COND:
        SE[seat].calls["status"] += 1
        return 200, {"call": "status", "state": state(seat), **take_news(seat)}


def do_observe(seat: str):
    with COND:
        g = gate(seat, False)
        if g:
            return g
        st = SE[seat]
        st.calls["observe"] += 1
        ob = {"decision": None if M.done(seat) else M.decision(seat)}
        if not M.done(seat):
            render_views(seat)
            ob["image_png_b64"] = st.views[1]
            ob["image_layout"] = S.IMAGE_LAYOUT
        return 200, {"call": "observe", "observation": ob, "state": state(seat), **take_news(seat)}


def do_start(seat: str):
    with COND:
        if E["final_obs"] is not None:
            return 200, dict(E["final_obs"], state=state(seat))
        st = SE[seat]
        if st.started:
            return 409, {"error": "you have already started", "state": state(seat)}
        st.think.check_ready()                      # a live, metered model session (raises MeterError otherwise)
        st.started = True
        st.calls["start"] += 1
        if E["first_start"] is None:
            E["first_start"] = time.monotonic()
        log({"ev": "start", "seat": seat})
        if all(SE[s].started for s in SEATS):
            E["phase"] = "running"
            log({"ev": "match_start", "first_player": FIRST})
            retime()
        out = {"call": "start", "started": True, "state": state(seat), **take_news(seat)}
    write_final()
    return 200, out


def do_act(seat: str, body: dict):
    st = SE[seat]
    dec = S.validate(body)
    if isinstance(dec, str):
        return 400, {"error": dec}
    if not st.flight.acquire(blocking=False):
        with COND:
            st.refused_busy += 1
        return 429, {"refused": True, "busy": True,
                     "error": "busy: one action at a time; wait for the previous action's reply"}
    try:
        with COND:
            g = gate(seat, True)
            if g:
                return g
            if st.awaiting_review:
                return 409, {"error": "review your previous shot first: `game ready \"WHY\" \"PLAN\"`", "state": state(seat)}
        ok = st.think.decided_by_model()            # program play: a live metered session (MeterError otherwise)
        with COND:
            if not ok:
                st.refused_not_model += 1
                log({"ev": "refused_not_model", "seat": seat})
                return 429, {"refused": True, "error": "refused: no new model call completed since the previous act"}
            g = gate(seat, True)
            if g:
                return g
            E["simulating"] = True
            retime()                                    # every clock stopped: record both, to the ms
            clk = {s: round(max(0.0, SE[s].chess.left()), 3) for s in SEATS}
            try:
                res = M.shoot(seat, dec)
                E["shot_n"] += 1
                st.actions.append(dict(dec, shot_n=E["shot_n"], clock_left_s=clk))
                st.results.append(res)
                st.calls["act"] += 1
                log({"ev": "shot", "seat": seat, "decision": dec, "result": res})
                if not M.done(seat):
                    render_views(seat)              # the next decision point, while the clock is stopped
            finally:
                E["simulating"] = False
            if DUEL and all(M.done(s) for s in SEATS) and M.winner() is None and M.n_tiebreaks < S.TIEBREAK_MAX:
                M.start_tiebreak()                      # level: the sport's tie-break (no draws)
                log({"ev": "tiebreak", "n": M.n_tiebreaks})
                for s in SEATS:
                    render_views(s)
            over = all(M.done(s) for s in SEATS)
            st.awaiting_review = not over               # a review after every shot except one that ends the match
            for s in SEATS:
                SE[s].news.append({"shot_by": "you" if s == seat else "opponent", **res} if DUEL else res)
            if over:
                end("match_over")
            retime()
            out = {"call": "act", "accepted": dec, "result": res, "state": state(seat), **take_news(seat)}
            if E["final_obs"] is not None:
                out.update(E["final_obs"])
            elif st.awaiting_review:
                out["review_due"] = "review this shot: `game ready \"WHY\" \"PLAN\"`; the game waits until then"
        write_final()
        return 200, out
    finally:
        st.flight.release()


def do_wait(seat: str, body: dict):
    """Long-poll: returns when it is the caller's turn or the match is over, at most WAIT_MAX_S (or max_s) seconds."""
    try:
        max_s = float(body.get("max_s", WAIT_MAX_S))
    except (TypeError, ValueError):
        return 400, {"error": f"max_s must be a number of seconds, 0 < max_s <= {WAIT_MAX_S:g}"}
    if not 0.0 < max_s <= WAIT_MAX_S:
        return 400, {"error": f"max_s must be a number of seconds, 0 < max_s <= {WAIT_MAX_S:g}"}
    with TURN_CV:
        if E["final_obs"] is None and not SE[seat].started:
            return 409, {"error": "run `game start` first", "state": state(seat)}
        t0 = time.monotonic()
        TURN_CV.wait_for(lambda: E["phase"] == "over" or E["turn"] == seat, timeout=max_s)
        out = {"call": "wait", "waited_s": round(time.monotonic() - t0, 3), "state": state(seat), **take_news(seat)}
        if E["final_obs"] is not None:
            out.update(E["final_obs"])
        return 200, out


def do_ready(seat: str, body: dict):
    with COND:
        g = gate(seat, False)
        if g:
            return g
        st = SE[seat]
        if not st.awaiting_review:
            return 409, {"error": "no review is due now (one is due after each of your shots)", "state": state(seat)}
        why, plan = body.get("why"), body.get("plan")
        if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
            return 400, {"error": "ready needs two non-empty texts: WHY (why the shot went well or badly) and PLAN "
                                  "(what you will change)"}
        if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
            return 400, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"}
        rv = {"after_shot": len(st.actions), "why": why.strip(), "plan": plan.strip(), "t": round(time.time() - T0, 1)}
        st.reviews.append(rv)
        st.calls["ready"] += 1
        st.awaiting_review = False
        log({"ev": "review", "seat": seat, **rv})
        retime()
        out = {"call": "ready", "accepted": "review recorded", "state": state(seat), **take_news(seat)}
    write_final()
    return 200, out


# ------------------------------------------------------------------------------------------------ end and grading evidence
def winner() -> str | None:
    """With COND held, at the end of a played-out duel: the score (after the sport's tie-break); if still level after
    S.TIEBREAK_MAX tie-break rounds, the player with more chess-clock time left (to the millisecond; an exact tie goes
    to the second player). Never a draw."""
    if not DUEL:
        return None
    dc = decision({s: M.score(s, SE[s].clock_out) for s in SEATS}, {s: SE[s].actions for s in SEATS}, ORDER,
                  "match_over", None)
    E["decided_by"] = dc["decided_by"]
    E["clock_left_at_end"] = dc.get("clock_left_s")
    return dc["winner"]


def end(reason: str, forfeiting: str | None = None) -> None:
    """With COND held."""
    if E["finalizing"]:
        return
    E["phase"], E["reason"], E["forfeiting"], E["finalizing"] = "over", reason, forfeiting, True
    retime()                                    # stops the clocks; also wakes every `wait`
    E["winner"] = other(forfeiting) if (DUEL and forfeiting) else (winner() if reason == "match_over" else None)
    if DUEL and forfeiting:
        E["decided_by"] = reason
    scores = {s: M.score(s, SE[s].clock_out) for s in SEATS}
    E["final_obs"] = {"done": True, "reason": reason, "note": "the match is over",
                      **({"winner": E["winner"], "scores": scores} if DUEL else {"score": scores[SEATS[0]]})}
    log({"ev": "end", "reason": reason, "winner": E["winner"], "forfeiting": forfeiting, "scores": scores})
    write_final()
    threading.Thread(target=finalize, daemon=True).start()


def write_final() -> None:
    with COND:
        out = {"protocol": PROTOCOL, "revision": REVISION, "sport": S.NAME, "duel": DUEL, "seats": SEATS,
               "seed": S.SEED, "first_player": FIRST, "phase": E["phase"], "reason": E["reason"],
               "winner": E["winner"], "forfeiting": E["forfeiting"], "decided_by": E["decided_by"],
               "n_tiebreaks": M.n_tiebreaks, "clock_left_at_end": E["clock_left_at_end"],
               "started": {s: SE[s].started for s in SEATS}, "clock_out": {s: SE[s].clock_out for s in SEATS},
               "scores": {s: M.score(s, SE[s].clock_out) for s in SEATS},
               "complete": {s: M.done(s) for s in SEATS},
               "state_sha": {s: M.state_sha(s) for s in SEATS},
               "actions": {s: SE[s].actions for s in SEATS},
               "actions_sha": actions_sha({s: SE[s].actions for s in SEATS}),
               "results": {s: SE[s].results for s in SEATS}, "reviews": {s: SE[s].reviews for s in SEATS},
               "seat_stats": {s: {"n_shots": len(SE[s].actions), "n_reviews": len(SE[s].reviews),
                                  "refused_busy": SE[s].refused_busy, "refused_not_model": SE[s].refused_not_model,
                                  "refused_turn": SE[s].refused_turn, "calls": SE[s].calls,
                                  "clock_used_s": round(SE[s].chess.total - SE[s].chess.left(), 2)} for s in SEATS},
               "player_mode": {s: SE[s].mode for s in SEATS},
               "decision_rule": {s: SE[s].think.rule for s in SEATS},
               "clock_s": CLOCK_S, "start_timeout_s": START_S, "elapsed_s": round(time.time() - T0, 1),
               "sim_error": E["reason"] == "error", "error": E["error"], "source_sha": SOURCE_SHA}
        meter, proxy, transient, unrecovered = {}, {}, {}, {}
        for s in SEATS:
            u = read_usage(SE[s].think.usage_file)
            meter[s] = bool(SE[s].meter_error or (SE[s].mode == "model" and (not u.get("epoch") or u.get("requests", 0) < 1)))
            api = seat_api_errors(SE[s].think.usage_file, u)     # model-API errors: transient vs unrecovered (api_errors.py)
            proxy[s] = api["api_failure"]                        # unrecovered, or more than MAX_TRANSIENT_API_ERRORS
            transient[s], unrecovered[s] = api["transient_api_errors"], api["unrecovered_api_errors"]
        out.update(meter_error=meter, proxy_error=proxy, transient_api_errors=transient, unrecovered_api_errors=unrecovered)
        out.update(E["extra"])
        out["finalized"] = out["graded_ready"] = E["finalized"]
        tmp = DATA / "final.json.tmp"
        tmp.write_text(json.dumps(out, default=float))
        os.replace(tmp, DATA / "final.json")


def finalize() -> None:
    try:
        with COND:
            acts = {s: list(SE[s].actions) for s in SEATS}
            live = {s: {"state_sha": M.state_sha(s), "score": M.score(s, SE[s].clock_out)} for s in SEATS}
            tr = {"sport": S.NAME, "revision": REVISION, "seed": S.SEED, "seats": SEATS, "first_player": FIRST,
                  "actions": acts, "clock_out": {s: SE[s].clock_out for s in SEATS}, "n_tiebreaks": M.n_tiebreaks,
                  "order": ORDER, "reason": E["reason"], "forfeiting": E["forfeiting"], "source_sha": SOURCE_SHA}
        (DATA / "trajectory.json").write_text(json.dumps(tr))
        import numpy as np
        np.savez(DATA / "trajectory.npz", seed=S.SEED, keys=np.array(S.ACTION_KEYS),
                 **{f"actions_{s}": np.array([[a[k] for k in S.ACTION_KEYS] for a in acts[s]], dtype=np.float64).reshape(-1, len(S.ACTION_KEYS))
                    for s in SEATS},
                 # both players' chess-clock time left (s) when each shot was played, and the shot's number in the match
                 **{f"clock_left_{s}": np.array([[a["clock_left_s"][t] for t in SEATS] for a in acts[s]], dtype=np.float64).reshape(-1, len(SEATS))
                    for s in SEATS},
                 **{f"shot_n_{s}": np.array([a["shot_n"] for a in acts[s]], dtype=np.int64) for s in SEATS}, clock_seats=np.array(SEATS))
        t0 = time.time()
        subprocess.run([sys.executable, str(HERE / "server.py"), "--replay", str(DATA)], check=True,
                       timeout=float(os.environ.get("RCB_REPLAY_TIMEOUT_S", "900")), env=dict(os.environ))
        rp = json.loads((DATA / "replay_check.json").read_text())
        det = (rp["source_sha"] == SOURCE_SHA and rp["seed"] == S.SEED and rp["actions_sha"] == actions_sha(acts)
               and all(rp["seats"][s]["state_sha"] == live[s]["state_sha"] and rp["seats"][s]["score"] == live[s]["score"]
                       for s in SEATS)
               and rp["decision"]["winner"] == E["winner"] and rp["decision"]["decided_by"] == E["decided_by"])
        E["extra"] = {"deterministic": det, "replay_scores": {s: rp["seats"][s]["score"] for s in SEATS},
                      "replay_wall_s": round(time.time() - t0, 1)}
        log({"ev": "replay", **E["extra"]})
        E["extra"]["video"] = False
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1" and any(acts.values()):
            procs = [subprocess.Popen([sys.executable, str(HERE / "server.py"), "--video", str(DATA), s], env=dict(os.environ))
                     for s in SEATS if acts[s]]          # one process per seat, in parallel
            deadline = time.monotonic() + float(os.environ.get("RCB_VIDEO_TIMEOUT_S", "300"))
            ok = True
            for p in procs:
                try:
                    ok &= p.wait(timeout=max(1.0, deadline - time.monotonic())) == 0
                except subprocess.TimeoutExpired:
                    p.kill()
                    ok = False
            E["extra"]["video"] = ok
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["extra"]["finalize_error"] = repr(exc)[:300]
    E["finalized"] = True
    write_final()


def watchdog() -> None:
    while True:
        time.sleep(0.2)
        with COND:
            if E["finalizing"]:
                return
            if E["phase"] == "prepare" and E["first_start"] is not None and time.monotonic() - E["first_start"] > START_S:
                late = next(s for s in SEATS if not SE[s].started)
                log({"ev": "start_timeout", "seat": late})
                end("start_timeout", forfeiting=late)
            elif E["phase"] == "running" and E["turn"] and SE[E["turn"]].chess.left() <= 0:
                t = E["turn"]
                SE[t].clock_out = True
                log({"ev": "clock_out", "seat": t})
                end("clock_out", forfeiting=t if DUEL else None)


def seat_allowed(seat: str, addr: str) -> bool:
    hosts = dict(x.split("=", 1) for x in os.environ.get("SEAT_HOSTS", "").split(",") if "=" in x)
    if seat not in hosts:
        return True
    try:
        return addr in {a[4][0] for a in socket.getaddrinfo(hosts[seat], None)} or addr in ("127.0.0.1", "::1")
    except OSError:
        return False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, code: int, obj: dict) -> None:
        b = json.dumps(obj, default=float).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def dispatch(self, post: bool) -> None:
        bits = [b for b in self.path.split("?")[0].strip("/").split("/") if b]
        if DUEL:
            if len(bits) != 2 or bits[0] not in SEATS or not seat_allowed(bits[0], self.client_address[0]):
                return self.send(403, {"error": f"use /<your seat>/<call>; seats {SEATS}"})
            seat, ep = bits
        else:
            if len(bits) != 1:
                return self.send(404, {"error": "no such endpoint (GET /spec /status; POST /observe /act /start /ready /wait)"})
            seat, ep = SEATS[0], bits[0]
        body = {}
        if post:
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}") if 0 <= n <= 65536 else None
            except (ValueError, OSError):
                body = None
            if not isinstance(body, dict):
                return self.send(400, {"error": "the body must be a JSON object"})
        try:
            if ep == "spec":
                code, obj = do_spec(seat)
            elif ep == "status":
                code, obj = do_status(seat)
            elif ep == "observe":
                code, obj = do_observe(seat)
            elif post and ep == "act":
                code, obj = do_act(seat, body)
            elif post and ep == "start":
                code, obj = do_start(seat)
            elif post and ep == "ready":
                code, obj = do_ready(seat, body)
            elif post and ep == "wait":
                code, obj = do_wait(seat, body)
            else:
                code, obj = 404, {"error": "no such endpoint (GET spec, status; POST observe, act, start, ready, wait)"}
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            with COND:
                if isinstance(exc, MeterError):
                    SE[seat].meter_error = True
                E["error"] = repr(exc)[:300]
                log({"ev": "error", "seat": seat, "error": repr(exc)})
                end("error")
            code, obj = 500, {"error": "technical failure", "detail": repr(exc)[:200]}
        self.send(code, obj)

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)


def on_usr1(*_):
    def run():
        with COND:
            end("timeout")
    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    if "--replay" in sys.argv:
        offline_replay(OFFLINE)
        sys.exit(0)
    if "--video" in sys.argv:
        offline_video(OFFLINE, sys.argv[sys.argv.index("--video") + 2])
        sys.exit(0)
    DATA.mkdir(parents=True, exist_ok=True)
    SOURCE_SHA = source_sha()
    M = S.Match(SEATS, ORDER)
    SE.update({s: Seat(s) for s in SEATS})
    for s in SEATS:
        (DATA / ("think_calls.jsonl" if not DUEL else f"think_calls_{s}.jsonl")).touch()   # exists even with no model
        render_views(s)                             # warm up the renderer; the first decision point is ready
    signal.signal(signal.SIGUSR1, on_usr1)
    log({"ev": "service", "protocol": PROTOCOL, "sport": S.NAME, "seed": S.SEED, "seats": SEATS, "first_player": FIRST,
         "clock_s": CLOCK_S, "act_rule": os.environ.get("RCB_ACT_RULE"), "player_mode": {s: SE[s].mode for s in SEATS},
         "source_sha": SOURCE_SHA})
    write_final()
    threading.Thread(target=watchdog, daemon=True).start()
    (DATA / "server.pid").write_text(str(os.getpid()))
    print(f"{S.NAME} service ready ({PROTOCOL}, seats {SEATS})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), Handler).serve_forever()
