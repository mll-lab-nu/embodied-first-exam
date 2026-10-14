"""The team channel (docs/framework_zh.md §6.1, one player per robot): short text messages between the seats of one
side, a core service so that no sport writes it. Declared in sport.toml:

    [team_channel]
    max_bytes = 120          # per message (UTF-8)
    min_interval_s = 1.0     # game time between two messages of one seat
    max_messages = 200       # per seat and match

A message is stamped with the sender's game time (step k) and delivered to the other seats of the SAME side only,
from that step on; the other side never sees it. Every message is a row of the episode (`team`, information only: it
does not change the world, so the replay does not need it).

The task parameter RO_TEAM_CHANNEL=off switches a declared channel off (the no-communication setting of the
multi-agent taxonomy: same teams, same rules, the teammates cannot talk); the default is on."""
from __future__ import annotations

import os


class TeamChannel:
    def __init__(self, cfg, conf: dict | None):
        self.cfg, self.conf = cfg, dict(conf or {})
        self.declared = bool(conf) and any(len(cfg.seats_of(s)) > 1 for s in cfg.side_list())
        self.switched_off = os.environ.get("RO_TEAM_CHANNEL", "on").strip().lower() == "off"
        self.enabled = self.declared and not self.switched_off
        self.max_bytes = int(self.conf.get("max_bytes", 120))
        self.min_interval_s = float(self.conf.get("min_interval_s", 1.0))
        self.max_messages = int(self.conf.get("max_messages", 200))
        self.log: list[dict] = []
        self.last_k: dict[str, int] = {}
        self.read: dict[str, int] = {s: 0 for s in cfg.seats}

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
        msg = {"seat": seat, "side": self.cfg.side_of(seat), "k": k, "text": text}
        self.log.append(msg)
        return 200, {"sent": {"k": k, "t_sim": k * dt}}

    def inbox(self, seat: str, k: int) -> list[dict]:
        """The new messages of `seat`'s teammates up to step k (each delivered once)."""
        if not self.enabled:
            return []
        side = self.cfg.side_of(seat)
        mine = [m for m in self.log if m["side"] == side and m["seat"] != seat and m["k"] <= k]
        new = mine[self.read[seat]:]
        self.read[seat] = len(mine)
        return [{"from": m["seat"], "k": m["k"], "text": m["text"]} for m in new]
