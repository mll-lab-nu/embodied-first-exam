"""Seats: metering (the unchanged think_clock.py / api_errors.py), per-seat counters, one-request-in-flight locks (per
entity for acts), the chess clock of the turn protocol, and the validity fields every final.json carries."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from .metering.api_errors import seat_api_errors
from .metering.think_clock import ThinkClock, read_usage

UNMETERED_MODES = ("oracle", "unmetered")   # player modes whose model the sim does not meter


class Seat:
    def __init__(self, name: str, data: Path, clock_s: float | None = None, side: str | None = None):
        self.name, self.side = name, side or name
        self.mode = os.environ.get(f"PLAYER_MODE_{name}", os.environ.get("RCB_PLAYER_MODE", "model"))
        if self.mode not in UNMETERED_MODES + ("model",):
            raise ValueError(f"PLAYER_MODE_{name} must be model, oracle or unmetered")
        # "unmetered" (core 0.2.27): the runner meters the seat's model itself (a single-seat task run by a plain
        # Harbor with its native agents, e.g. the export to the upstream benchmark): no metering proxy, so the meter
        # takes the gate's exemption (ThinkClock's oracle rule; think_clock.py stays unchanged) and no meter is
        # required for validity (Service.need_meter); final.json records the mode as it is.
        self.meter = ThinkClock(usage_file=str(Path(data) / f"think_usage_{name}.json"),
                                mode="oracle" if self.mode in UNMETERED_MODES else self.mode)
        self.act_locks: dict[str, threading.Lock] = {}
        self.view_lock = threading.Lock()
        self.joined = self.ready = self.retired = False
        self.stats: dict = {}
        self.clock_s, self.used, self.turn_t0, self.turn_busy = clock_s, 0.0, None, 0.0
        self.frozen, self.frozen_at = 0, None    # off-lock service in progress (images being drawn): no clock

    def act_lock(self, entity: str = "") -> threading.Lock:
        return self.act_locks.setdefault(entity, threading.Lock())

    def count(self, key: str, n: int = 1):
        self.stats[key] = self.stats.get(key, 0) + n

    def sample(self, key: str, v: float):
        self.stats.setdefault(key, []).append(v)

    # chess clock (turn protocol): runs on this seat's turn only; service time inside the turn does not count
    def clock_used(self, now=None) -> float:
        if self.turn_t0 is None:
            return self.used
        now = now or time.time()
        if self.frozen:                          # the clock stands still while the service draws this seat's images
            now = max(self.turn_t0, min(now, self.frozen_at))
        return self.used + max(0.0, now - self.turn_t0 - self.turn_busy)

    def freeze(self, now):
        """Service work for this seat continues off the lock (drawing its images, core 0.2.8): stop the clock."""
        if self.frozen == 0:
            self.frozen_at = now
        self.frozen += 1

    def thaw(self, now):
        self.frozen -= 1
        if self.frozen == 0:
            if self.turn_t0 is not None:
                self.turn_busy += max(0.0, now - max(self.frozen_at, self.turn_t0))
            self.frozen_at = None

    def clock_left(self) -> float:
        return (self.clock_s or 0.0) - self.clock_used()

    def start_turn(self, now):
        self.turn_t0, self.turn_busy = now, 0.0

    def stop_turn(self, now):
        if self.turn_t0 is not None:
            self.used = self.clock_used(now)
            self.turn_t0 = None


def validity_fields(seats: dict[str, Seat], need_meter) -> dict:
    """Metering and model-API validity of every seat (the one rule of api_errors.py)."""
    usage = {s: read_usage(st.meter.usage_file) for s, st in seats.items()}
    meter = {s: bool(need_meter(seats[s]) and (not usage[s].get("epoch") or not usage[s].get("requests")))
             for s in seats}
    apis = {s: seat_api_errors(seats[s].meter.usage_file, usage[s]) for s in seats}
    return {"meter_error": meter, "proxy_error": {s: a["api_failure"] for s, a in apis.items()},
            "transient_api_errors": {s: a["transient_api_errors"] for s, a in apis.items()},
            "unrecovered_api_errors": {s: a["unrecovered_api_errors"] for s, a in apis.items()},
            # recorded only (2026-10-17): recovered errors void a trial only above api_errors.py's sanity cap
            "api_retries": {s: a["api_retries"] for s, a in apis.items()},
            "api_wait_s": {s: a["api_wait_s"] for s, a in apis.items()},
            "api_failure_reason": {s: a["api_failure_reason"] for s, a in apis.items()},
            "player_modes": {s: st.mode for s, st in seats.items()}}
