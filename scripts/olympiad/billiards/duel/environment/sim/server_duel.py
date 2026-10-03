"""Two-seat turn-based duel service, program play (eai-standard-turn/1.0; docs/EAI_STANDARD_REALTIME_1_0.md).

The sport (sport.py) is a turn-based match between two agents, seats A and B, each in its own container. Rules here:
  * Start: each seat sends `POST /<seat>/start`; the match begins when both have. After the first start the other
    seat has START_TIMEOUT_S to start, else it forfeits (`start_timeout`).
  * Turns: only the seat whose turn it is may act; an act out of turn gets HTTP 409. After each of its shots the
    shooter hands in a review (`POST /<seat>/ready`); the game goes on only then.
  * Chess clocks: each seat has CLOCK_BUDGET_S (60 min) that runs only on its own turn (its shots and its reviews),
    stopped while the service simulates. A seat whose clock runs out loses (`clock_expired`).
  * Program play: a seat's program may act without a new model response, with a live metered model session for
    that seat (think_clock.py, PLAYER_MODE_<seat>); one act per seat in flight (HTTP 429 `busy`).
Endpoints (seat = A or B, only from that seat's container): GET /<seat>/spec, /<seat>/status; POST /<seat>/observe,
/<seat>/start, /<seat>/act, /<seat>/ready, /<seat>/wait {"max_s": S}. Every reply carries the seat's state and
the shots played since its previous call.
Evidence (/data): episode.jsonl, final.json, trajectory.json (+ .npz), replay_check.json (fresh-process replay),
replay.mp4. The replay runs on match end or SIGUSR1 (the verifier's collect hook).
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sport as SP  # noqa: E402
from replay import source_sha  # noqa: E402
from think_clock import MeterError, ThinkClock, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402

PROTOCOL = "eai-standard-turn/1.0"
DATA = Path(os.environ.get("RCB_DATA", "/data"))
DATA.mkdir(parents=True, exist_ok=True)
SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
SEED = int(os.environ.get("DUEL_SEED", "1") or 1)
FIRST = (os.environ.get("FIRST_PLAYER") or "A").strip().upper()
if FIRST not in SIDES:
    raise ValueError("FIRST_PLAYER must be A or B")
CLOCK_BUDGET_S = float(os.environ.get("CLOCK_BUDGET_S", "3600"))
START_TIMEOUT_S = float(os.environ.get("START_TIMEOUT_S", "1800"))
WAIT_MAX_S = 60.0
REVIEW_MAX_CHARS = 2000
REVIEW_PROMPT = ("Shot played. Review it: `game ready \"WHY\" \"PLAN\"` (why it went well or badly; what you will "
                 "change). The game goes on only then; your clock runs.")


class Seat:
    def __init__(self, name: str):
        self.name = name
        self.mode = os.environ.get(f"PLAYER_MODE_{name}", os.environ.get("RCB_PLAYER_MODE", "model"))
        self.clock = ThinkClock(usage_file=str(DATA / f"think_usage_{name}.json"), mode=self.mode)
        self.act_lock = threading.Lock()
        self.joined = False
        self.clock_left_s = CLOCK_BUDGET_S
        self.clock_since = None
        self.news: list[dict] = []
        self.stats = {"n_decisions": 0, "refused_busy": 0, "refused_not_model": 0, "refused_out_of_turn": 0,
                      "n_reviews": 0, "n_observe": 0}

    def left(self) -> float:
        left = self.clock_left_s
        if self.clock_since is not None:
            left -= time.time() - self.clock_since
        return max(0.0, left)


SEATS = {s: Seat(s) for s in SIDES}
COND = threading.Condition(threading.RLock())
G = SP.new(SEED, FIRST)
E = {"t0": time.time(), "phase": "prepare", "review_due": None, "start_deadline": None, "reason": None,
     "forfeiting": None, "finalizing": False, "finalized": False, "extra": {}, "errors": [], "reviews": [],
     "meter_error": {s: False for s in SIDES}}


def log(ev: dict) -> None:
    with open(DATA / "episode.jsonl", "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), "wall": round(time.time() - E["t0"], 3), **ev}, default=float) + "\n")


# ----------------------------------------------------------------------------- turns and clocks (COND held)
def running_seat() -> str | None:
    if E["phase"] != "play":
        return None
    return E["review_due"] or G.turn


def stop_clocks() -> None:
    for s in SEATS.values():
        if s.clock_since is not None:
            s.clock_left_s = s.left()
            s.clock_since = None


def sync_clocks() -> None:
    """Only the seat whose turn it is (to shoot or to review) has its clock running."""
    stop_clocks()
    r = running_seat()
    if r is not None:
        SEATS[r].clock_since = time.time()


def state(seat: str) -> dict:
    r = running_seat()
    if E["phase"] == "over":
        turn = "over"
    elif E["phase"] == "prepare":
        turn = "not started" if not SEATS[seat].joined else "waiting for the opponent to start"
    elif r == seat:
        turn = "your review" if E["review_due"] == seat else "you"
    else:
        turn = "opponent's review" if E["review_due"] else "opponent"
    return {"seat": seat, "phase": E["phase"], "turn": turn, **SP.score_view(G, seat),
            "clock_left_s": round(SEATS[seat].left(), 1), "opponent_clock_left_s": round(SEATS[OTHER[seat]].left(), 1),
            "done": E["phase"] == "over"}


def final_obs(seat: str) -> dict:
    w = E["extra"].get("winner_live")
    return {"done": True, "reason": E["reason"], "forfeiting": None if E["forfeiting"] is None else
            ("you" if E["forfeiting"] == seat else "opponent"),
            "result": "you won" if w == seat else "you lost" if w else "no result"}


def reply(seat: str, out: dict) -> dict:
    out["state"] = state(seat)
    out["shots_since_your_last_call"], SEATS[seat].news = SEATS[seat].news, []
    return out


def winner_live() -> str | None:
    if E["forfeiting"] in SIDES:
        return OTHER[E["forfeiting"]]
    if E["reason"] == "match_over":
        return G.winner
    return None


# ----------------------------------------------------------------------------- evidence
def write_final() -> None:
    with COND:
        usage = {s: read_usage(SEATS[s].clock.usage_file) for s in SIDES}
        meter = {s: bool(E["meter_error"][s] or (SEATS[s].mode == "model" and SEATS[s].joined and
                                                   (not usage[s].get("epoch") or usage[s].get("requests", 0) < 1)))
                 for s in SIDES}
        apis = {s: seat_api_errors(SEATS[s].clock.usage_file, usage[s]) for s in SIDES}   # model-API errors: transient vs unrecovered (api_errors.py)
        api = {s: apis[s]["api_failure"] for s in SIDES}   # unrecovered, or more than MAX_TRANSIENT_API_ERRORS
        rp = E["extra"].get("replay") or {}
        replay_ok = bool(E["finalized"] and rp.get("state_sha") == G.state_sha() and rp.get("score") == SP.scores(G)
                         and rp.get("source_sha") == E["extra"].get("source_sha"))
        complete = (E["reason"] in ("match_over", "clock_expired")
                    or (E["reason"] == "start_timeout" and E["forfeiting"] in SIDES))
        valid = bool(complete and replay_ok and not E["errors"] and not any(meter.values()) and not any(api.values()))
        w = winner_live()
        out = {"protocol": PROTOCOL, "revision": SP.REVISION, "sport": SP.NAME, "seed": SEED, "first_player": FIRST,
               "score": SP.scores(G), "winner": w if valid else None, "tiebreak": E.get("tiebreak"),
               "reason": E["reason"], "forfeiting": E["forfeiting"], "clock_forfeit": E["reason"] == "clock_expired",
               "start_forfeit": E["reason"] == "start_timeout", "phase": E["phase"],
               "finalized": E["finalized"], "graded_ready": E["finalized"], "valid_trial": valid, "technical_failure": not valid,
               "errors": E["errors"], "meter_error": meter, "proxy_error": api,
               "transient_api_errors": {s: apis[s]["transient_api_errors"] for s in SIDES},
               "unrecovered_api_errors": {s: apis[s]["unrecovered_api_errors"] for s in SIDES}, "deterministic": replay_ok,
               "replay_score": rp.get("score"), "state_sha": G.state_sha(), "n_shots": len(G.decisions),
               "clock_budget_s": CLOCK_BUDGET_S,
               "seats": {s: {**SEATS[s].stats, "joined": SEATS[s].joined, "player_mode": SEATS[s].mode,
                             "clock_left_s": round(SEATS[s].left(), 1), "decision_rule": SEATS[s].clock.rule}
                         for s in SIDES},
               "reviews": E["reviews"], "video": bool(E["extra"].get("video")), "source_sha": E["extra"].get("source_sha"),
               "elapsed_s": round(time.time() - E["t0"], 1), "shots": getattr(G, "shots", None) or getattr(G, "log", [])}
        tmp = DATA / "final.json.tmp"
        tmp.write_text(json.dumps(out, default=float))
        tmp.replace(DATA / "final.json")


def finalize() -> None:
    try:
        with COND:
            decs = [dict(d) for d in G.decisions]
            tr = {"protocol": PROTOCOL, "revision": SP.REVISION, "seed": SEED, "first_player": FIRST, "decisions": decs,
                  "tiebreak": E.get("tiebreak"),
                  "source_sha": source_sha(), "live_sha": G.state_sha(), "live_score": SP.scores(G)}
            E["extra"]["source_sha"] = tr["source_sha"]
        (DATA / "trajectory.json").write_text(json.dumps(tr))
        # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads the JSON; the same actions)
        np.savez(DATA / "trajectory.npz", seed=SEED, first_player=FIRST, **SP.actions_array(decs))
        subprocess.run([sys.executable, str(HERE / "replay.py"), str(DATA)], check=True,
                       timeout=float(os.environ.get("RCB_REPLAY_TIMEOUT_S", "600")))
        E["extra"]["replay"] = json.loads((DATA / "replay_check.json").read_text())
        if os.environ.get("RCB_RENDER_VIDEO", "1") == "1":
            try:
                subprocess.run([sys.executable, str(HERE / "replay.py"), str(DATA), "--video"], check=True,
                               capture_output=True, timeout=float(os.environ.get("RCB_VIDEO_TIMEOUT_S", "600")))
                E["extra"]["video"] = True
            except Exception as exc:  # noqa: BLE001
                log({"ev": "video_error", "error": repr(exc)[:300]})
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        E["errors"].append({"where": "replay", "error": repr(exc)[:300]})
    with COND:
        E["finalized"] = True
        write_final()
        COND.notify_all()


def end(reason: str, forfeiting: str | None = None) -> None:
    """With COND held."""
    if E["finalizing"]:
        return
    stop_clocks()
    E.update(phase="over", reason=reason, forfeiting=forfeiting, finalizing=True, review_due=None)
    E["extra"]["winner_live"] = winner_live()
    log({"ev": "end", "reason": reason, "forfeiting": forfeiting, "score": SP.scores(G), "winner": E["extra"]["winner_live"]})
    write_final()
    COND.notify_all()
    threading.Thread(target=finalize, daemon=True).start()


# ----------------------------------------------------------------------------- endpoints
def start(seat: str) -> tuple[int, dict]:
    S = SEATS[seat]
    with COND:
        if E["phase"] == "over":
            return 200, reply(seat, final_obs(seat))
        if S.joined:
            return 409, reply(seat, {"error": "you have already started"})
    S.clock.check_ready()                  # program play: a live, metered model session for this seat
    with COND:
        S.joined = True
        log({"ev": "start", "seat": seat})
        if E["start_deadline"] is None:
            E["start_deadline"] = time.time() + START_TIMEOUT_S
        if all(SEATS[s].joined for s in SIDES):
            E["phase"] = "play"
            sync_clocks()
            log({"ev": "match_begins", "first_player": FIRST})
        COND.notify_all()
        write_final()
        out = {"started": True}
        if E["phase"] == "play":
            out["observation"] = SP.observation(G, seat, {})
        else:
            out["note"] = (f"the match begins when your opponent has started too (it has {START_TIMEOUT_S / 60:.0f} "
                           "minutes from the first start); `game wait` returns when it is your turn")
        return 200, reply(seat, out)


def gate(seat: str) -> tuple[int, dict] | None:
    if E["phase"] == "over":
        return 200, reply(seat, final_obs(seat))
    if E["phase"] != "play":
        return 409, reply(seat, {"error": "the match has not begun: it begins when both players have run `game start`"})
    return None


def observe(seat: str, query: dict) -> tuple[int, dict]:
    with COND:
        g = gate(seat)
        if g:
            return g
        SEATS[seat].stats["n_observe"] += 1
        out = {"observation": SP.observation(G, seat, query)}
        if E["review_due"] == seat:
            out["review_due"] = REVIEW_PROMPT
        return 200, reply(seat, out)


def act(seat: str, body: dict) -> tuple[int, dict]:
    S = SEATS[seat]
    with COND:
        g = gate(seat)
        if g:
            return g
        if E["review_due"] == seat:
            S.stats["refused_out_of_turn"] += 1
            return 409, reply(seat, {"error": "review your shot first: `game ready \"WHY\" \"PLAN\"`"})
        if running_seat() != seat:
            S.stats["refused_out_of_turn"] += 1
            return 409, reply(seat, {"error": "it is not your turn"})
        dec = SP.validate(body, G, seat)
        if isinstance(dec, str):
            return 400, reply(seat, {"error": dec})
    if not S.clock.decided_by_model():     # program play: raises MeterError without a live metered session
        with COND:
            S.stats["refused_not_model"] += 1
            return 429, reply(seat, {"refused": True, "error": "refused: no new model call since your previous act"})
    with COND:
        if E["phase"] != "play" or running_seat() != seat or E["review_due"]:
            return 409, reply(seat, {"error": "it is not your turn"})
        stop_clocks()                      # the service's own computing time is on no clock
        S.stats["n_decisions"] += 1
        log({"ev": "decision", "seat": seat, "decision": dec, "clock_left_s": round(S.left(), 1),
             "model_call": S.clock.last_call()})
        recs = SP.play(G, seat, dec)
        for r in recs:
            for s in SIDES:
                SEATS[s].news.append(SP.shot_text(r, s))
            log({"ev": "shot", **r})
        out = {"accepted": dec, "your_shot": SP.shot_text(recs[0], seat) if recs else None}
        if G.done:
            if G.winner is None:           # a tie at the cap: the player with more chess-clock time left wins
                clocks = {s: round(SEATS[s].left(), 3) for s in SIDES}
                w = ("A" if clocks["A"] > clocks["B"] else "B" if clocks["B"] > clocks["A"] else OTHER[FIRST])
                G.resolve_tie(w, clocks)
                E["tiebreak"] = {"winner": w, "clock_left_s": clocks}
                log({"ev": "tiebreak", **E["tiebreak"]})
            end("match_over")
            out.update(final_obs(seat))
        else:
            E["review_due"] = seat
            sync_clocks()
            out["review_prompt"] = REVIEW_PROMPT
        COND.notify_all()
        write_final()
        return 200, reply(seat, out)


def ready(seat: str, body: dict) -> tuple[int, dict]:
    with COND:
        g = gate(seat)
        if g:
            return g
        if E["review_due"] != seat:
            return 409, reply(seat, {"error": "no review is due from you now (a review is due after each of your shots)"})
        why, plan = body.get("why"), body.get("plan")
        if not (isinstance(why, str) and isinstance(plan, str) and why.strip() and plan.strip()):
            return 400, reply(seat, {"error": "ready needs two non-empty texts: WHY and PLAN"})
        if len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
            return 400, reply(seat, {"error": f"WHY and PLAN are limited to {REVIEW_MAX_CHARS} characters each"})
        rv = {"seat": seat, "after_shot": len(G.decisions), "score": SP.scores(G), "why": why.strip(),
              "plan": plan.strip(), "clock_left_s": round(SEATS[seat].left(), 1)}
        E["reviews"].append(rv)
        SEATS[seat].stats["n_reviews"] += 1
        log({"ev": "review", **rv})
        E["review_due"] = None
        sync_clocks()
        COND.notify_all()
        out = {"accepted": "review recorded"}
        if running_seat() == seat:
            out["next"] = SP.observation(G, seat, {})
        write_final()
        return 200, reply(seat, out)


def wait(seat: str, body: dict) -> tuple[int, dict]:
    try:
        max_s = float(body.get("max_s", 30))
        assert 0 <= max_s <= WAIT_MAX_S
    except Exception:  # noqa: BLE001
        return 400, {"error": f"max_s must be a number in [0, {WAIT_MAX_S:g}]"}
    deadline = time.time() + max_s
    with COND:
        while E["phase"] != "over" and running_seat() != seat and time.time() < deadline:
            COND.wait(min(0.5, max(0.0, deadline - time.time())))
        return 200, reply(seat, {"waited": True})


def spec(seat: str) -> dict:
    return {"protocol": PROTOCOL, "revision": SP.REVISION, "seat": seat,
            "clock": {"total_s": CLOCK_BUDGET_S, "rule": "chess clock per player: runs only on your turn (your shots "
                      "and your reviews), stopped while the service simulates; when it runs out you lose"},
            "start": {"window_s": START_TIMEOUT_S, "rule": "the match begins when both players have started; after the "
                      "first start the other player has this long to start, else it loses"},
            "decision_rule": ("program play: your own program may act without a new model response; one act per seat "
                              "in flight; acts out of turn are refused (HTTP 409)"
                              if os.environ.get("RCB_ACT_RULE") == "program" else "one new completed model response per act"),
            "first_player_rule": SP.FIRST_MEANING, **SP.spec(seat, FIRST)}


# ----------------------------------------------------------------------------- HTTP
def seat_allowed(side: str, addr: str) -> bool:
    hosts = dict(x.split("=", 1) for x in os.environ.get("SEAT_HOSTS", "").split(",") if "=" in x)
    if side not in hosts:
        return addr in ("127.0.0.1", "::1")
    try:
        return addr in {a[4][0] for a in socket.getaddrinfo(hosts[side], None)}
    except OSError:
        return False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, code: int, value: dict) -> None:
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

    def dispatch(self, post: bool) -> None:
        u = urllib.parse.urlparse(self.path)
        bits = u.path.strip("/").split("/")
        if len(bits) != 2 or bits[0] not in SIDES or not seat_allowed(bits[0], self.client_address[0]):
            return self.send(403, {"error": "seat not authorized"})
        seat, ep = bits
        try:
            body = {}
            if post:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 65536:
                    raise ValueError("request too large")
                body = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("the body must be a JSON object")
            if post and ep == "act":
                S = SEATS[seat]
                if not S.act_lock.acquire(blocking=False):          # one act per seat in flight
                    with COND:
                        S.stats["refused_busy"] += 1
                    return self.send(429, {"refused": True, "busy": True,
                                           "error": "busy: one act at a time; wait for the previous act's reply"})
                try:
                    code, out = act(seat, body)
                finally:
                    S.act_lock.release()
            elif post and ep == "start":
                code, out = start(seat)
            elif post and ep == "ready":
                code, out = ready(seat, body)
            elif post and ep == "wait":
                code, out = wait(seat, body)
            elif post and ep == "observe":
                code, out = observe(seat, SP.parse_query(body))
            elif not post and ep == "spec":
                code, out = 200, spec(seat)
            elif not post and ep == "status":
                with COND:
                    code, out = 200, reply(seat, final_obs(seat) if E["phase"] == "over" else {})
            else:
                code, out = 404, {"error": "unknown endpoint (GET spec status; POST observe start act ready wait)"}
        except (ValueError, TypeError, KeyError) as exc:
            code, out = 400, {"error": str(exc)[:200]}
        except MeterError as exc:
            with COND:
                E["meter_error"][seat] = True
                E["errors"].append({"where": f"meter {seat}", "error": str(exc)[:300]})
                end("technical_error")
            code, out = 503, {"error": "model meter error: the trial is invalid", "detail": str(exc)[:200]}
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            with COND:
                E["errors"].append({"where": ep, "error": repr(exc)[:300]})
                end("technical_error")
            code, out = 500, {"error": "technical failure", "detail": repr(exc)[:200]}
        self.send(code, out)

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)


class Server(ThreadingHTTPServer):
    daemon_threads = True


def watch() -> None:
    while True:
        time.sleep(0.25)
        with COND:
            if E["phase"] == "play":
                r = running_seat()
                if r and SEATS[r].clock_since is not None and SEATS[r].left() <= 0.0:
                    log({"ev": "clock_expired", "seat": r})
                    end("clock_expired", r)
            elif E["phase"] == "prepare" and E["start_deadline"] and time.time() > E["start_deadline"]:
                missing = [s for s in SIDES if not SEATS[s].joined]
                if len(missing) == 1:
                    end("start_timeout", missing[0])


def on_usr1(*_):
    def run():
        with COND:
            end("collected")
    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    signal.signal(signal.SIGUSR1, on_usr1)
    SP.warm()
    log({"ev": "service", "sport": SP.NAME, "revision": SP.REVISION, "seed": SEED, "first_player": FIRST,
         "clock_budget_s": CLOCK_BUDGET_S, "start_timeout_s": START_TIMEOUT_S, "source_sha": source_sha(),
         "player_modes": {s: SEATS[s].mode for s in SIDES}, "decision_rules": {s: SEATS[s].clock.rule for s in SIDES}})
    write_final()
    threading.Thread(target=watch, daemon=True).start()
    (DATA / "server.pid").write_text(str(os.getpid()))
    print("turn-based duel service ready", flush=True)
    Server(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), Handler).serve_forever()
