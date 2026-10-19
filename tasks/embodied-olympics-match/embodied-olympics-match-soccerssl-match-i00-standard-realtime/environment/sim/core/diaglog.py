"""Diagnostic records (core 0.2.25): environment-side rows of episode.jsonl for the post-match diagnosis
(core/diagnose.py). They are information only: no replay reads them, they are not in commands_sha or any state hash,
they never change what a seat is sent, and a failure to write one never ends a match.

Rows (every row also has the episode's "ev", "ts", "wall"):
  {"ev": "observe", "seat", "obs_id", "k", "view_steps", "query", ...}  an observation returned to the seat: k = the
        step of the world state it reports; view_steps = the step of each image frame (the sport's camera job may
        report older frames, e.g. a short history; [k] for the core's cameras; [] without images); obs_id counts the
        seat's observations (1, 2, ...)
  {"ev": "act_received", "seat", "k", "act_id", "obs_id_last", "seen", "entity", "decision", ...}  an act accepted
        for its effect: act_id = 1, 2, ... per seat (the order the service accepted them); obs_id_last = the seat's
        latest observation returned before the act arrived (None: none yet); seen = the step of the latest world state
        sent to the seat in any reply (the reaction report's s, core 0.2.23)
  {"ev": "effect", "seat", "act_id", "k", "entity", ["rejected"], ["info"]}  that act's command took effect before
        step k (it follows its `cmd` row; the cmd row itself is unchanged); turn protocol: info = Match.apply's answer
  {"ev": "act_dropped", "seat", "act_id", "k", "why"}  that act never took effect; why: unit_over (the unit ended
        before its effect step), unit_over_planning (it ended while the act was planned), unit_changed, match_over
  {"ev": "event", "k", "events"}  what Match.step() returned for the step that ended at k (non-empty lists only)
  {"ev": "team_delivered", "seat", "from", "seq", "sent_k", "k"}  a teammate's message first returned to `seat` at
        step k (sent at sent_k), once per recipient and message
"""
from __future__ import annotations

import math

DIAG_ROWS = ("observe", "act_received", "effect", "act_dropped", "event", "team_delivered")


def jsonable(x, depth: int = 0):
    """A JSON-safe copy of what a sport returned (numpy scalars and arrays, tuples, sets; anything else as its repr)."""
    if depth > 12:
        return repr(x)[:200]
    if x is None or isinstance(x, (bool, str, int)):
        return x
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): jsonable(v, depth + 1) for k, v in x.items()}
    if isinstance(x, (list, tuple, set, frozenset)):
        return [jsonable(v, depth + 1) for v in x]
    tolist = getattr(x, "tolist", None)                   # numpy arrays and scalars
    if callable(tolist):
        try:
            return jsonable(tolist(), depth + 1)
        except Exception:  # noqa: BLE001
            pass
    return repr(x)[:200]


def view_steps(meta: dict | None, job, k: int) -> list[int]:
    """The step of each image frame of an observation: the sport's own (camera job meta `view_steps`), else [k] when
    images were made from the state now, else []."""
    vs = (meta or {}).get("view_steps")
    if isinstance(vs, (list, tuple)):
        try:
            return [int(v) for v in vs]
        except (TypeError, ValueError):
            pass
    return [] if job is None else [int(k)]


class Acts:
    """Per-seat act ids and the latest observation returned to each seat (what act_received links to)."""

    def __init__(self, seats):
        self.next = {s: 0 for s in seats}
        self.last_obs: dict = {s: None for s in seats}

    def new(self, seat) -> int:
        self.next[seat] = self.next.get(seat, 0) + 1
        return self.next[seat]

    def observed(self, seat, obs_id):
        self.last_obs[seat] = obs_id

    def new_obs(self, seat) -> int:
        """In-process play (core/local.py): the next observation id, returned at once."""
        n = (self.last_obs.get(seat) or 0) + 1
        self.last_obs[seat] = n
        return n


def safe(write):
    """A row writer that never raises (a diagnostic row must not end a match)."""
    def w(ev, **row):
        try:
            write(ev, **row)
        except Exception:  # noqa: BLE001
            try:
                write(ev, **{k: jsonable(v) for k, v in row.items()})
            except Exception:  # noqa: BLE001
                pass
    return w
