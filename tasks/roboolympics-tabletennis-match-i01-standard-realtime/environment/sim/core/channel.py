"""The team channel (docs/framework_zh.md §6.1, one player per robot): short text messages between the seats of one
side, a core service so that no sport writes it. Declared in sport.toml:

    [team_channel]
    max_bytes = 120          # per message (UTF-8)
    min_interval_s = 1.0     # game time between two messages of one seat
    max_messages = 200       # per seat and match
    recent_s = 2.0           # optional: the default window of observe / status without a read mark (game seconds)
    recent_max = 20          # optional: at most this many messages in that window

A message is stamped with the sender's game time (step k) and a sequence number `seq` (1, 2, ... per side, core
0.2.20) and shown to the other seats of the SAME side only, from that step on; the other side never sees it. Every
message is a row of the episode (`team`, information only: it does not change the world, so the replay does not need
it).

Reading never consumes (core 0.2.20; before 0.2.20 every message was handed out once per seat, so an agent's own
`status` call or monitor script took messages away from its program): `observe` and `status` show the teammates'
messages with seq > `team_since` when the request gives that read mark, else the RECENT ones (the last `recent_s` game
seconds, at most `recent_max` messages: a bounded default that repeats across calls), always with `team_seq`, the
newest seq of the side. `POST /<seat>/team {"since": n}` reads the log after n (at most `page_max` per reply, `more`
when there are more). Every client of a seat (the agent, its program, a monitor) reads the same log with its own
read mark.

The task parameter RO_TEAM_CHANNEL=off switches a declared channel off (the no-communication setting of the
multi-agent taxonomy: same teams, same rules, the teammates cannot talk); the default is on."""
from __future__ import annotations

import os

from .sport import Refused


class TeamChannel:
    def __init__(self, cfg, conf: dict | None):
        self.cfg, self.conf = cfg, dict(conf or {})
        self.declared = bool(conf) and any(len(cfg.seats_of(s)) > 1 for s in cfg.side_list())
        self.switched_off = os.environ.get("RO_TEAM_CHANNEL", "on").strip().lower() == "off"
        self.enabled = self.declared and not self.switched_off
        self.max_bytes = int(self.conf.get("max_bytes", 120))
        self.min_interval_s = float(self.conf.get("min_interval_s", 1.0))
        self.max_messages = int(self.conf.get("max_messages", 200))
        self.recent_s = float(self.conf.get("recent_s", 2.0))
        self.recent_max = int(self.conf.get("recent_max", 20))
        self.page_max = 500
        self.log: list[dict] = []
        self.last_k: dict[str, int] = {}
        self.seq: dict[str, int] = {}             # side -> the newest seq
        self.delivered: dict[str, set] = {}       # seat -> seqs already returned to it (core 0.2.25, diagnostics)

    def deliver(self, seat: str, rows: list[dict], k: int) -> list[dict]:
        """The messages of `rows` (as messages() / page() return them) returned to `seat` for the first time, as
        team_delivered rows (core 0.2.25, diagnostics only: when each recipient first got each message)."""
        got = self.delivered.setdefault(seat, set())
        out = []
        for r in rows:
            if r["seq"] not in got:
                got.add(r["seq"])
                out.append({"seat": seat, "from": r["from"], "seq": r["seq"], "sent_k": r["k"], "k": int(k)})
        return out

    def say(self, seat: str, text, k: int, dt: float) -> tuple[int, dict]:
        if not self.enabled:
            if self.declared:
                return 403, {"error": "the team channel is off in this task (no-communication setting)"}
            return 404, {"error": "this task has no team channel"}
        if not isinstance(text, str) or not text.strip():
            return 400, {"error": "text must be a non-empty string"}
        if len(text.encode()) > self.max_bytes:
            return 400, {"error": f"at most {self.max_bytes} bytes per message"}
        sent = sum(1 for m in self.log if m["seat"] == seat)
        if sent >= self.max_messages:
            return 429, {"error": f"at most {self.max_messages} messages per match"}
        gap = self.min_interval_s / dt if dt else 0
        if seat in self.last_k and k - self.last_k[seat] < gap:
            return 429, {"error": f"at most one message every {self.min_interval_s} game seconds"}
        self.last_k[seat] = k
        side = self.cfg.side_of(seat)
        self.seq[side] = self.seq.get(side, 0) + 1
        msg = {"seat": seat, "side": side, "k": k, "seq": self.seq[side], "text": text}
        self.log.append(msg)
        return 200, {"sent": {"k": k, "t_sim": k * dt, "seq": msg["seq"]}}

    @staticmethod
    def since_arg(value, name: str = "team_since"):
        """A client's read mark: None (absent) or a non-negative integer seq; anything else is the caller's error."""
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise Refused(f"{name} must be a non-negative integer (a seq)")
        try:
            n = int(value)
        except (TypeError, ValueError, OverflowError):
            raise Refused(f"{name} must be a non-negative integer (a seq)") from None
        if n < 0 or n != float(value):
            raise Refused(f"{name} must be a non-negative integer (a seq)")
        return n

    def _side_log(self, seat: str, k: int) -> list[dict]:
        side = self.cfg.side_of(seat)
        return [m for m in self.log if m["side"] == side and m["k"] <= k]

    @staticmethod
    def _row(m) -> dict:
        return {"from": m["seat"], "seq": m["seq"], "k": m["k"], "text": m["text"]}

    def messages(self, seat: str, k: int, dt: float, since: int | None = None) -> tuple[list[dict], int]:
        """(the teammates' messages for `seat` at step k, the side's newest seq). With a read mark: every message with
        seq > since (at most page_max, the oldest first); without: the recent ones (the last recent_s game seconds,
        at most recent_max). Never consumes."""
        if not self.enabled:
            return [], 0
        log = self._side_log(seat, k)
        top = log[-1]["seq"] if log else 0
        mates = [m for m in log if m["seat"] != seat]
        if since is None:
            lo = k - (self.recent_s / dt if dt else 0)
            out = [m for m in mates if m["k"] >= lo][-self.recent_max:]
        else:
            out = [m for m in mates if m["seq"] > since][:self.page_max]
        return [self._row(m) for m in out], top

    def page(self, seat: str, k: int, since) -> tuple[int, dict]:
        """POST /<seat>/team {"since": n}: the teammates' messages after seq n (default 0), at most page_max."""
        if not self.enabled:
            if self.declared:
                return 403, {"error": "the team channel is off in this task (no-communication setting)"}
            return 404, {"error": "this task has no team channel"}
        n = self.since_arg(since if since is not None else 0, "since")
        log = self._side_log(seat, k)
        mates = [m for m in log if m["seat"] != seat and m["seq"] > n]
        return 200, {"messages": [self._row(m) for m in mates[:self.page_max]],
                     "team_seq": log[-1]["seq"] if log else 0, "more": len(mates) > self.page_max}
