"""The duel twins' layer over the generic full-simulator setting (tools/fullsim): the twin plays a `duel` in which seat B
is a built-in player inside the service process (the twin's RO_BUILTIN_SEATS, core/builtin_seat.py). This task's own
file; tools/fullsim/formal.py, session.py and the sport stay unchanged.

- `evaluate(...)`: tools.fullsim.formal.evaluate on a service that also starts the built-in seat B, exactly as the twin's
  core/serve.py does (after the service's loop; its calls go to the service's own handlers, never to the program). The
  sport's score table names the seats (A, B); the generic verdict reads the opponent's points as "opponent", so this
  layer reads "opponent" as B (the same alias in the live record and in its replay check, so their comparison is
  unchanged).
- `DuelSession`: tools.fullsim.session.Session with seat B played by the same built-in player in process, once every
  `b_every` control steps (the twin's player acts about every 0.05 s of wall time; the formal match is the reference),
  and an action layer that plans in a worker (the sport's `worker_init` / `worker_call`, as core/local.py does) planned
  in process.
"""

from __future__ import annotations

import json as _json
import os
from types import SimpleNamespace

from core import builtin_seat
from core.sport import PLAYING
from tools.fullsim import formal
from tools.fullsim.adapter import load
from core.sport import Refused, parse_action
from tools.fullsim.session import Session, plain, plugin_path

_generic = formal.evaluate  # captured at import: the verifier's entrypoint may point formal.evaluate at evaluate below
PLAYER_MODES = {"B": "oracle"}  # the twin's PLAYER_MODE_B: a built-in seat has no model and no proxy


def builtin_of(ad) -> dict:
    return dict(ad.BUILTIN_SEATS)  # {"B": "builtin_players:Factory"}: the twin's RO_BUILTIN_SEATS


def environ(ad):
    os.environ["RO_BUILTIN_SEATS"] = ",".join(f"{s}={ref}" for s, ref in builtin_of(ad).items())
    for s in builtin_of(ad):
        os.environ[f"PLAYER_MODE_{s}"] = PLAYER_MODES.get(s, "oracle")


def _alias(obj):
    sc = obj.get("scores") if isinstance(obj, dict) else None
    if isinstance(sc, dict) and "B" in sc and "opponent" not in sc:
        obj["scores"] = {**sc, "opponent": sc["B"]}
    return obj


def _loads(text, *a, **kw):
    return _alias(_json.loads(text, *a, **kw))


class DuelService(formal.FullSimService):
    builtin: dict = {}

    def loop(self):
        builtin_seat.start(self, self.plugin, self.builtin)  # core/serve.py: the loop, then the built-in seats
        return super().loop()


def evaluate(policy, out, *, sport, **kw):
    ad = load(sport)
    environ(ad)
    service_cls, json_mod = formal.FullSimService, formal.json
    DuelService.builtin = builtin_of(ad)
    formal.FullSimService = DuelService
    formal.json = SimpleNamespace(loads=_loads, dumps=_json.dumps, dump=_json.dump, load=_json.load)
    try:
        return _generic(policy, out, sport=sport, **kw)
    finally:
        formal.FullSimService, formal.json = service_cls, json_mod


class DuelSession(Session):
    """A development world in which seat B plays as in the twin (the built-in player); you play A."""

    def __init__(self, sport, level=None, seed=None, log_dir=None, b_every=1, player_seed=0):
        self.b_every, self.player_seed = int(b_every), int(player_seed)
        ad = load(sport)
        environ(ad)
        self.builtin_refs = builtin_of(ad)
        super().__init__(sport, level=level, seed=seed, log_dir=log_dir)

    def reset(self):
        out = super().reset()
        planned = getattr(self.layer, "worker", None) == "plan"
        self.planners = {s: self.sport.worker_init("plan", s, self.cfg) for s in self.cfg.seats} if planned else {}
        self.builtin = {}
        for seat, ref in self.builtin_refs.items():
            factory = builtin_seat.load(ref, str(plugin_path(self.ad.SPORT)))
            spec = plain({"frozen_commit": formal.FROZEN, "cfg": self.cfg.to_json(), "action_level": self.cfg.action_level,
                          "actions": self.layer.schema(self.match, seat), **self.sport.spec(self.cfg, seat, self.match)})
            self.builtin[seat] = factory(spec, seat, self.player_seed)
        return out

    def act(self, command, seat="A"):
        """tools.fullsim.session.Session.act, with the seat's plan worker in process (core/local.py)."""
        if not self.planners:
            return super().act(command, seat=seat)
        if self.match.phase().state != PLAYING:
            raise Refused("actions only allowed while playing", 409)
        parsed = parse_action(self.layer, seat, command, self.match, {})
        job = self.layer.snapshot(seat, parsed, self.match, self.match.k)
        prepared = self.sport.worker_call(self.planners[seat], "plan", job) if job is not None else None
        low, info = self.layer.lower(seat, parsed, prepared, self.match)
        low = plain(low)
        self._log("cmd", k=self.match.k, seat=seat, cmd=low)
        applied = self.match.apply(seat, low) or {}
        return plain({"planning": info, "applied": applied})

    def _builtin_views(self):
        m = self.match
        for seat, player in self.builtin.items():
            view = {"state": plain({"step": m.k, "world": "running", "phase": PLAYING, **m.observe(seat)}),
                    "observation": {}}
            if getattr(player, "uses_truth", False):
                view["truth"] = plain(m.builtin_truth(seat))
            body = player.act(view)
            if body is not None:
                try:
                    self.act(body, seat=seat)
                except Exception:  # noqa: BLE001 -- a refused act of the built-in player: as in the service, it plays on
                    pass

    def step(self, n=1):
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 100000:
            raise ValueError("step count must be 1..100000")
        out = None
        for _ in range(n):
            if self.match.phase().state != PLAYING:
                break
            if self.match.k % self.b_every == 0:
                self._builtin_views()
            out = super().step(1)
        return out if out is not None else self.state()


if __name__ == "__main__":  # the developer self-test: python -m tools.fullsim.duel (tools.fullsim.formal's arguments)
    formal.evaluate = evaluate
    formal.main()
