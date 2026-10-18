"""The practice-match service of the joint-level soccer tasks (task v3, SOCJV3 2026-10-14): full CPU copies of the
match world (the same soccer.World, referee and rules as the match, through the same plugin and action layer) that a
seat can play as fast as its program runs, against the scripted team (levels 1-3, a black box: the seat sees only the
observations, never the code) or against itself (both teams under the seat's joint control: sparring).

Runs in its own sidecar container (the soccer sim image; the sport code mounted read-only at /srv, this file at
/practice), one per seat, on that seat's internal network only: http://practice:8100/ (the seat's toolkit has a client,
/opt/robot/scrimmage.py). Every world lives in its own worker process (PRACTICE_WORLDS at a time, default 6).

  POST /new   {"opponent": "L1"|"L2"|"L3"|"L4"|"L5"|"self", "seed": S, "first": "A"|"B"}
              -> {"id", "k", "obs": {"A": ...[, "B": ...]}}       (obs = the match's `game status` for that seat)
  POST /step  {"id", "acts": {"A": [act, ...], "B": [...]}, "n": 1..50}
              -> the acts take effect at this control step (as in the match: an act takes effect at the next 20 ms
                 boundary), then the world advances n control steps; a stoppage (goal, half time, ...) is resumed at
                 once (no reviews here) and listed in "stoppages"; -> {"k", "t", "obs", "refused", "stoppages", "done",
                 "result"}
  POST /close {"id"}            GET /worlds            GET /  (this text)

Practice seeds never coincide with match seeds: practice seed S plays the world seed 1 000 000 + S. Worlds idle for
IDLE_S (default 1800 s) are closed.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SRV = os.environ.get("PRACTICE_SRV", "/srv")
MAX_WORLDS = int(os.environ.get("PRACTICE_WORLDS", "6"))
IDLE_S = float(os.environ.get("PRACTICE_IDLE_S", "1800"))
PORT = int(os.environ.get("PRACTICE_PORT", "8100"))
SEED_BASE = 1_000_000
N_MAX = 50
OPPONENTS = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5, "self": 0}   # L4, L5: the RL opponents (soccer.RL_LEVELS)


def _world_proc(conn, opponent, seed, first):
    """One practice world: the match's own plugin (SoccerMatch + JointLayer), driven synchronously."""
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    sys.path[:0] = [SRV, os.path.join(SRV, "sport")]
    try:
        import torch
        torch.set_num_threads(1)
    except Exception:  # noqa: BLE001
        pass
    import plugin as P  # the match's plugin
    from core.sport import MatchConfig, Refused
    level = OPPONENTS[opponent]
    seats = ("A", "B") if level == 0 else ("A",)
    cfg = MatchConfig(sport="soccer", format="duel" if level == 0 else "single", seats=seats,
                      seed=SEED_BASE + int(seed), first=first, level=level or None, action_level="low")
    sport = P.Soccer()
    m = sport.build(cfg)
    layer = sport.action_layer("low")

    def obs():
        return {s: m.observe(s) for s in seats}

    def step(acts, n):
        refused = []
        w = m.w
        for seat, lst in (acts or {}).items():
            if seat not in seats:
                refused.append({"seat": seat, "error": f"you drive seat(s) {list(seats)}"})
                continue
            for body in lst or []:
                try:
                    cmd = layer.parse(seat, body, m, {})
                    job = layer.snapshot(seat, cmd, m, 0)
                    prepared = layer.prepare(job) if job is not None else None
                    low, _info = layer.lower(seat, cmd, prepared, m)
                    r = m.apply(seat, low) or {}
                    if "rejected" in r:
                        refused.append({"seat": seat, "entity": cmd.get("entity"), "error": r["rejected"]})
                except Refused as e:
                    refused.append({"seat": seat, "entity": (body or {}).get("entity") if isinstance(body, dict)
                                    else None, "error": str(e)})
                except Exception as e:  # noqa: BLE001
                    refused.append({"seat": seat, "error": f"bad act: {e}"})
        stops = []
        for _ in range(n):
            if w.done:
                break
            m.step()
            if w.stopped and not w.done:
                st = w.stopped
                stops.append({"kind": st["kind"], "k": st["k"], "t": st["t"], "score": dict(st["score"]),
                              **({"team": st["team"]} if st.get("team") else {})})
                m.resume()
                break                      # return at once: the referee has placed the robots anew
        out = {"k": w.k, "t": round(w.t(), 3), "obs": obs(), "refused": refused, "stoppages": stops,
               "done": bool(w.done)}
        if w.done:
            out["result"] = {"score": dict(w.score), "winner": w.winner, "how": w.end_reason}
        return out

    conn.send({"k": m.w.k, "obs": obs(), "seats": list(seats)})
    while True:
        try:
            msg = conn.recv()
        except EOFError:
            return
        if msg is None:
            return
        try:
            conn.send(step(msg.get("acts"), int(msg.get("n", 1))))
        except Exception as e:  # noqa: BLE001
            conn.send({"error": f"practice world failed: {e!r}"})


class Worlds:
    def __init__(self):
        self.lock = threading.Lock()
        self.w = {}                      # id -> dict(proc, conn, lock, last, opponent, seed)

    def reap(self):
        now = time.monotonic()
        with self.lock:
            dead = [i for i, x in self.w.items() if now - x["last"] > IDLE_S or not x["proc"].is_alive()]
        for i in dead:
            self.close(i)

    def new(self, opponent, seed, first):
        self.reap()
        with self.lock:
            if len(self.w) >= MAX_WORLDS:
                return 429, {"error": f"at most {MAX_WORLDS} practice worlds at a time: close one first",
                             "open": list(self.w)}
        a, b = mp.Pipe()
        p = mp.get_context("fork").Process(target=_world_proc, args=(b, opponent, seed, first), daemon=True)
        p.start()
        if not a.poll(120):
            p.kill()
            return 500, {"error": "the practice world did not start"}
        first_msg = a.recv()
        wid = secrets.token_hex(6)
        with self.lock:
            self.w[wid] = dict(proc=p, conn=a, lock=threading.Lock(), last=time.monotonic(), opponent=opponent,
                               seed=seed, first=first)
        return 200, {"id": wid, **first_msg}

    def step(self, wid, acts, n):
        x = self.w.get(wid)
        if x is None:
            return 404, {"error": "no such practice world (closed after %g s idle, or never opened)" % IDLE_S}
        with x["lock"]:
            x["last"] = time.monotonic()
            x["conn"].send({"acts": acts, "n": n})
            r = x["conn"].recv()
        return (500 if "error" in r else 200), r

    def close(self, wid):
        with self.lock:
            x = self.w.pop(wid, None)
        if x is None:
            return 404, {"error": "no such practice world"}
        try:
            x["conn"].send(None)
        except Exception:  # noqa: BLE001
            pass
        x["proc"].join(2)
        if x["proc"].is_alive():
            x["proc"].kill()
        return 200, {"closed": wid}

    def list(self):
        self.reap()
        with self.lock:
            return {i: dict(opponent=x["opponent"], seed=x["seed"], first=x["first"],
                            idle_s=round(time.monotonic() - x["last"], 1)) for i, x in self.w.items()}


WORLDS = Worlds()


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        b = json.dumps(obj, separators=(",", ":")).encode() if not isinstance(obj, str) else obj.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json" if not isinstance(obj, str) else "text/plain")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/") == "/worlds":
            return self.reply(200, WORLDS.list())
        return self.reply(200, __doc__)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("the body must be a JSON object")
        except Exception as e:  # noqa: BLE001
            return self.reply(400, {"error": f"bad JSON: {e}"})
        p = self.path.rstrip("/")
        if p == "/new":
            opp = body.get("opponent", "L1")
            if opp not in OPPONENTS:
                return self.reply(400, {"error": f"opponent must be one of {list(OPPONENTS)}"})
            seed = body.get("seed", 0)
            if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < SEED_BASE:
                return self.reply(400, {"error": f"seed must be an integer in [0, {SEED_BASE})"})
            first = body.get("first", "A")
            if first not in ("A", "B"):
                return self.reply(400, {"error": "first must be A or B"})
            return self.reply(*WORLDS.new(opp, seed, first))
        if p == "/step":
            nn = body.get("n", 1)
            if isinstance(nn, bool) or not isinstance(nn, int) or not 1 <= nn <= N_MAX:
                return self.reply(400, {"error": f"n must be an integer in [1, {N_MAX}]"})
            acts = body.get("acts") or {}
            if not isinstance(acts, dict) or any(not isinstance(v, list) for v in acts.values()):
                return self.reply(400, {"error": 'acts must be {"A": [act, ...], "B": [...]}'})
            return self.reply(*WORLDS.step(str(body.get("id")), acts, nn))
        if p == "/close":
            return self.reply(*WORLDS.close(str(body.get("id"))))
        return self.reply(404, {"error": "unknown endpoint"})


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    srv.daemon_threads = True
    print(f"practice service on :{PORT}, at most {MAX_WORLDS} worlds", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
