"""The development sandbox of the privileged setting: the full simulator of one sport, any state readable and writable,
the whole match reset to its start. Reset rebuilds the entire same-seed match, never a point.

    from tools.fullsim.session import Session
    s = Session("badminton", level=1, seed=7)
    s.state(); s.world; s.spec(); s.act({...}); s.step(5); s.ready(); s.reset()
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FROZEN = "0d7f680cc04918f419230588732aedbb9ccdc900"  # the fexam-export commit the First Exam twins were exported from
os.environ.setdefault("MUJOCO_GL", "disable")  # no renderer is used here: no display or GPU needed
sys.path.insert(0, str(ROOT))
from core.episode import Episode
from core.sport import FINISHED, UNIT_OVER, MatchConfig, Refused, parse_action
from tools.fullsim.adapter import load


def plugin(sport):
    """The sport's plugin module, loaded once (sports/<sport>/plugin.py, its directory on sys.path)."""
    name = f"fullsim_frozen_plugin_{sport}"
    if name not in sys.modules:
        here = ROOT / "sports" / sport
        sys.path.insert(0, str(here))
        spec = importlib.util.spec_from_file_location(name, here / "plugin.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def plugin_path(sport):
    return ROOT / "sports" / sport / "plugin.py"


def plain(value):
    return json.loads(json.dumps(value, default=lambda x: x.tolist() if isinstance(x, np.ndarray) else x.item()))


def match_config(ad, level, seed, slowdown=None):
    return MatchConfig(
        ad.SPORT,
        ad.FORMAT,
        tuple(ad.SEATS),
        seed,
        first="A",
        slowdown=ad.SLOWDOWN if slowdown is None else slowdown,
        level=level,
        action_level=ad.ACTION_LEVEL,
        play="program",
    )


class Session:
    """Full local world access for development; the formal runner owns a different world."""

    def __init__(self, sport, level=None, seed=None, log_dir=None):
        self.ad = load(sport)
        inst = next(iter(self.ad.INSTANCES.values()))
        level = inst["level"] if level is None else level
        seed = inst["seed"] if seed is None else seed
        if level not in self.ad.LEVELS:
            raise ValueError(f"opponent level must be one of {tuple(self.ad.LEVELS)}")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 100000:
            raise ValueError("only public development seeds below 100000 are permitted")
        self.cfg = match_config(self.ad, level, seed)
        self.sport = plugin(self.ad.SPORT).SPORT
        self.log_dir = Path(log_dir) if log_dir else None
        self.resets = 0
        self.total_steps = 0
        self.reset()

    @property
    def world(self):
        """The complete mutable Match object of the sport (its simulator, referee, scripted opponent, planners)."""
        return self.match

    def reset(self):
        """Reset the entire match to its start and the same seed. No checkpoint argument."""
        self.match = self.sport.build(self.cfg)
        self.layer = self.sport.action_layer(self.cfg.action_level)
        self.scheduled = []  # (effect step, seat, low command): an action layer's declared delay_steps
        self.resets += 1
        self.ep = None
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / "episode.jsonl"
            if path.exists():
                raise FileExistsError("use a fresh log directory for each recorded episode")
            self.ep = Episode(path)
            self._log(
                "header",
                cfg=self.cfg.to_json(),
                sport=self.sport.name,
                revision=self.sport.revision,
                protocol=self.sport.protocol,
                source_sha=FROZEN,
                versions={"fullsim": "fullsim/1"},
            )
        return self.state()

    def _log(self, ev, **fields):
        if self.ep:
            self.ep.write(ev, **fields)

    def state(self):
        m = self.match
        return plain(
            {
                "state": {"step": m.k, "world": "running", "phase": m.phase().state, **m.observe("A")},
                "truth": self.ad.truth(m),
                "scores": m.scores(),
                "finished": m.phase().state == FINISHED,
                "state_sha": m.state_digest(),
            }
        )

    def spec(self):
        return plain(
            {
                "frozen_commit": FROZEN,
                "cfg": self.cfg.to_json(),
                "action_level": self.cfg.action_level,
                "actions": self.layer.schema(self.match, "A"),
                **self.sport.spec(self.cfg, "A", self.match),
            }
        )

    def act(self, command, seat="A"):
        """One action, as the live service handles it: parse, snapshot -> prepare (in process here; the service plans
        in the seat's worker while the world runs) -> lower -> apply now or after the layer's delay_steps."""
        if self.match.phase().state != "playing":
            raise Refused("actions only allowed while playing", 409)
        parsed = parse_action(self.layer, seat, command, self.match, {})
        job = self.layer.snapshot(seat, parsed, self.match, self.match.k)
        prepared = self.layer.prepare(job) if job is not None else None
        low, info = self.layer.lower(seat, parsed, prepared, self.match)
        low = plain(low)  # JSON round trip: the trusted journal's representation
        delay = int(getattr(self.layer, "delay_steps", 0) or 0)
        if delay:
            self.scheduled.append((self.match.k + delay, seat, low))
            return plain({"planning": info, "scheduled_at": self.match.k + delay})
        self._log("cmd", k=self.match.k, seat=seat, cmd=low)
        applied = self.match.apply(seat, low) or {}
        return plain({"planning": info, "applied": applied})

    def ready(self):
        if self.match.phase().state != UNIT_OVER:
            raise Refused("ready only allowed during the between-point review", 409)
        self.scheduled.clear()
        self._log("resume", k=self.match.k)
        self.match.resume()

    def step(self, n=1):
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 100000:
            raise ValueError("step count must be 1..100000")
        tick = getattr(self.layer, "tick", None)
        for _ in range(n):
            if self.match.phase().state in (FINISHED, UNIT_OVER):
                break
            for item in [x for x in self.scheduled if x[0] <= self.match.k]:
                self.scheduled.remove(item)
                self._log("cmd", k=self.match.k, seat=item[1], cmd=item[2])
                self.match.apply(item[1], item[2])
            if tick is not None:
                for seat in self.cfg.seats:
                    low = tick(seat, self.match)
                    if low is not None:
                        self._log("cmd", k=self.match.k, seat=seat, cmd=plain(low))
                        self.match.apply(seat, low)
            self.match.step()
            self.total_steps += 1
        return self.state()

    def finish_log(self, reason):
        self._log("end", k=self.match.k, reason=reason)
