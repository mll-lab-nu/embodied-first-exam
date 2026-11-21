"""Contract ①, the player's side: a stdlib client of the match service and the loop that lets a built-in player (the
sport's reference player, scripted opponents, check policies) play over HTTP exactly as a model's program would.

A built-in player is an object made by factory(spec, seat, seed) with
    act(view) -> body | None     view = {"state": <the seat's state>, "observation": <the /observe observation>}
                                 (body = the /act request; None = nothing now, realtime only)
    review(reply) -> (why, plan) optional; called after each own action (turn) or at each review (realtime)
    message(view) -> text | None optional (realtime, core 0.2.21): a team-channel message to the seat's teammates
                                 (POST /say; refused messages, e.g. faster than the channel allows, are dropped)

    python3 -m core.client MODULE:FACTORY        (SIM_URL, SEAT; e.g. the task's solution/oracle_play.py)
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
import urllib.error
import urllib.request


class Seat:
    """One seat's calls. The service allows 20 requests per second and 4 open requests per seat: the client keeps
    under that (MIN_GAP_S between calls) and retries a request the HTTP layer refused before reading it (a bare 429
    or a reset connection), which never reached the match."""
    MIN_GAP_S = 0.06

    def __init__(self, base: str, seat: str, timeout: float = 600):
        self.base, self.seat, self.timeout, self.last = base.rstrip("/"), seat, timeout, 0.0

    def call(self, ep: str, body: dict | None = None, tries: int = 20) -> dict:
        for i in range(tries):
            time.sleep(max(0.0, self.last + self.MIN_GAP_S - time.monotonic()))
            self.last = time.monotonic()
            req = urllib.request.Request(f"{self.base}/{self.seat}/{ep}",
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                raw = e.read()
                if e.code == 429 and not raw and i + 1 < tries:          # the HTTP layer's limit, not the match's
                    time.sleep(0.25 * (i + 1))
                    continue
                try:
                    out = json.loads(raw)
                except ValueError:
                    out = {"error": str(e)}
                out["http_status"] = e.code
                return out
            except urllib.error.URLError as e:
                if isinstance(e.reason, (BrokenPipeError, ConnectionResetError, ConnectionRefusedError)) and \
                        i + 1 < tries:
                    time.sleep(0.25 * (i + 1))
                    continue
                raise
        raise RuntimeError("the match service kept refusing")


def wait_for(base: str, seat: str, deadline_s: float = 300) -> dict:
    t = time.time()
    while time.time() - t < deadline_s:
        try:
            out = Seat(base, seat, 10).call("spec")
            if "error" not in out:
                return out
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError("the match service did not answer")


def review_of(player, reply) -> tuple[str, str]:
    f = getattr(player, "review", None)
    return f(reply) if f else ("played as planned", "go on with the same plan")


REPLY_IMAGES = [0]                      # acts whose reply carried images of their result (core 0.2.8)


def play_turn(c: Seat, player) -> dict:
    c.call("start", {})
    while True:
        st = c.call("wait", {"timeout_s": 60}).get("state") or {}
        if st.get("done"):
            return st
        if not st.get("your_turn"):
            continue
        if st.get("awaiting_review"):
            why, plan = review_of(player, st)
            c.call("ready", {"why": why, "plan": plan})
            continue
        view = c.call("observe", {})
        body = player.act({"state": view.get("state") or {}, "observation": view.get("observation") or {}})
        reply = c.call("act", body)
        REPLY_IMAGES[0] += bool((reply.get("observation") or {}).get("image_png_b64"))
        if (reply.get("state") or {}).get("done"):
            return reply["state"]
        if reply.get("http_status"):
            print("refused:", json.dumps(reply)[:300], file=sys.stderr)
            continue
        why, plan = review_of(player, reply)
        c.call("ready", {"why": why, "plan": plan})


def play_realtime(c: Seat, player, every_s: float = 0.05) -> dict:
    c.call("start", {})
    while True:
        view = c.call("observe", {})
        now = view.get("now") or {}
        if now.get("done"):
            return now
        if now.get("world") == "frozen" and now.get("phase") == "review" and not now.get("ready", {}).get(c.seat):
            why, plan = review_of(player, now)
            c.call("ready", {"why": why, "plan": plan})
            continue
        if now.get("world") == "running":
            v = {"state": now, "observation": view.get("observation") or {}}
            body = player.act(v)
            if body is not None:
                c.call("act", body)
            say = getattr(player, "message", None)
            text = say(v) if say is not None else None
            if text:
                c.call("say", {"text": text})
        c.call("wait", {"dt": every_s})


def main(argv):
    mod, _, name = argv[0].partition(":")
    sys.path.insert(0, os.getcwd())
    factory = getattr(importlib.import_module(mod), name or "Reference")
    base, seat = os.environ.get("SIM_URL", "http://sim:8000"), os.environ.get("SEAT", "A")
    spec = wait_for(base, seat)
    player = factory(spec, seat, int(os.environ.get("RO_PLAYER_SEED", "0")))
    c = Seat(base, seat)
    proto = spec.get("protocol", "")
    end = play_turn(c, player) if proto.startswith("eai-standard-turn") else play_realtime(c, player)
    print(json.dumps({"final_state": {k: end.get(k) for k in ("reason", "won", "winner", "scores") if k in end},
                      "replies_with_images": REPLY_IMAGES[0]}))


if __name__ == "__main__":
    main(sys.argv[1:])
