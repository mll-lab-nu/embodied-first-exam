"""Built-in seats (core 0.2.31): a seat played by a built-in player inside the service process.

    RO_BUILTIN_SEATS="B=builtin_players:RLTop[,C=module:Factory]"   (module path relative to the sport's directory)

The player is a core/client.py player (factory(spec, seat, seed), act(view) -> body | None, optional review(reply)) and
plays through core/client.py's own loops (play_realtime / play_turn), but every call goes to the service's handlers in
this process (LocalSeat), not over HTTP: the same start / observe / act / ready / wait, so the clocks, the reviews, the
rules and the record (episode.jsonl, the fresh-process replay) are exactly those of a seat played over HTTP. The HTTP
layer serves no built-in seat (core/serve.py leaves them out of make_server's seats: 403), so a seat played over
HTTP cannot read a built-in seat's view or act for it.

A player whose class sets `uses_truth = True` also gets view["truth"] = Match.builtin_truth(seat) (the sport's own,
JSON-able), taken under the service lock; it is never served over HTTP. The player runs in a daemon thread of its own;
an exception in it is logged and the seat stops playing (the match goes on: the seat loses by the sport's rules, e.g.
it does not review in time), which the trial records as a technical failure of the service.
"""
from __future__ import annotations

import importlib
import os
import sys
import threading
import time
import traceback

from . import client
from .sport import Refused


def parse(value: str | None) -> dict[str, str]:
    """RO_BUILTIN_SEATS -> {seat: "module:Factory"}."""
    out = {}
    for item in (value or "").split(","):
        if "=" in item:
            seat, _, ref = item.partition("=")
            if seat.strip() and ref.strip():
                out[seat.strip()] = ref.strip()
    return out


class LocalSeat:
    """core/client.py's Seat, in process: the same calls, answered by the service's handlers."""
    MIN_GAP_S = client.Seat.MIN_GAP_S

    def __init__(self, service, seat: str):
        self.service, self.seat, self.last = service, seat, 0.0

    def call(self, ep: str, body: dict | None = None, tries: int = 20) -> dict:
        time.sleep(max(0.0, self.last + self.MIN_GAP_S - time.monotonic()))
        self.last = time.monotonic()
        post = ep not in ("spec", "status")
        fn = self.service.routes(post).get(ep)
        if fn is None:
            return {"error": "unknown endpoint", "http_status": 404}
        try:
            code, out = fn(self.seat, dict(body or {}))
        except Refused as exc:
            code, out = exc.code, {"error": str(exc)}
        except BlockingIOError as exc:
            code, out = 429, {"error": str(exc)}
        out = self.service.public(out) if hasattr(self.service, "public") else out
        if code >= 400:
            out = {**out, "http_status": code}
        return out


class TruthPlayer:
    """Wraps a player that sets uses_truth: view["truth"] = Match.builtin_truth(seat), under the service lock."""

    def __init__(self, player, service, seat):
        self.player, self.service, self.seat = player, service, seat

    def act(self, view):
        with self.service.cond:
            view = {**view, "truth": self.service.m.builtin_truth(self.seat)}
        return self.player.act(view)

    def __getattr__(self, name):
        return getattr(self.player, name)


def load(ref: str, plugin: str):
    mod, _, name = ref.partition(":")
    sport_dir = os.path.dirname(os.path.abspath(plugin))
    if sport_dir not in sys.path:
        sys.path.insert(0, sport_dir)
    return getattr(importlib.import_module(mod), name)


def start(service, plugin: str, seats: dict[str, str]) -> list[threading.Thread]:
    """Start one daemon thread per built-in seat; returns them."""
    threads = []
    for seat, ref in seats.items():
        factory = load(ref, plugin)

        def run(seat=seat, factory=factory, ref=ref):
            try:
                c = LocalSeat(service, seat)
                spec = c.call("spec")
                player = factory(spec, seat, int(os.environ.get("RO_PLAYER_SEED", "0")))
                if getattr(player, "uses_truth", False):
                    if not hasattr(service.m, "builtin_truth"):
                        raise RuntimeError(f"{ref} uses truth but the sport's Match has no builtin_truth(seat)")
                    player = TruthPlayer(player, service, seat)
                proto = spec.get("protocol", "")
                end = (client.play_turn(c, player) if proto.startswith("eai-standard-turn")
                       else client.play_realtime(c, player))
                print(f"built-in seat {seat} ({ref}) done: {end.get('reason')}", flush=True)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                service.failure(f"builtin_{seat}", exc)
        t = threading.Thread(target=run, name=f"builtin-{seat}", daemon=True)
        t.start()
        threads.append(t)
    return threads
