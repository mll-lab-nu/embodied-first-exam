"""A development sandbox. Reset rebuilds the entire same-seed match, never a point."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FROZEN = "0d7f680cc04918f419230588732aedbb9ccdc900"
# No renderer is instantiated in this track; do not require a display/GPU.
os.environ.setdefault("MUJOCO_GL", "disable")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sports/tabletennis"))
from core.episode import Episode
from core.sport import (
    FINISHED,
    UNIT_OVER,
    MatchConfig,
    Refused,
    parse_action,
)


def plugin():
    name = "tt_fullsim_frozen_plugin"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "sports/tabletennis/plugin.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def plain(value):
    return json.loads(json.dumps(value, default=lambda x: x.tolist() if isinstance(x, np.ndarray) else x.item()))


class Session:
    """Full local world access for development; the formal runner owns a different world.

    The First Exam privileged twins run L2/seed22 (i01) and L3/seed12 (i02), the same frozen instances as their
    standard-realtime versions. Any opponent level 1-4 and any public seed may be explored. Physics is unchanged.
    """

    def __init__(self, level=2, seed=22, log_dir=None):
        if level not in (1, 2, 3, 4):
            raise ValueError("opponent level must be 1-4")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 100000:
            raise ValueError("only public development seeds below 100000 are permitted")
        self.cfg = MatchConfig("tabletennis", "match", ("A",), seed, level=level, slowdown=10, action_level="high")
        self.sport = plugin().SPORT
        self.log_dir = Path(log_dir) if log_dir else None
        self.resets = 0
        self.total_steps = 0
        self.reset()

    @property
    def world(self):
        """The complete mutable Match: world.R.s.m/d, referee, opponent, planner."""
        return self.match

    def reset(self):
        """Reset the entire match to 0:0 and the same seed. No checkpoint argument."""
        self.match = self.sport.build(self.cfg)
        self.layer = self.sport.action_layer("high")
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
                versions={"pilot": "tt-fullsim/0.1"},
            )
        return self.state()

    def _log(self, ev, **fields):
        if self.ep:
            self.ep.write(ev, **fields)

    def state(self):
        m, r = self.match, self.match.R
        return plain(
            {
                "state": {"step": m.k, "world": "running", "phase": m.phase().state, **m.observe("A")},
                "truth": {
                    **r.s.state(),
                    "opponent_x": r.opp_x(),
                    "opponent_parameters": r.lv,
                    "leg": r.leg,
                    "qpos": r.s.d.qpos,
                    "qvel": r.s.d.qvel,
                    "servo": r.s.servo.state(),
                },
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
                "action_level": "high",
                "actions": self.layer.schema(self.match, "A"),
                **self.sport.spec(self.cfg, "A", self.match),
            }
        )

    def act(self, command):
        if self.match.phase().state != "playing":
            raise Refused("actions only allowed while playing", 409)
        parsed = parse_action(self.layer, "A", command, self.match, {})
        # For the frozen single-player TT high layer, snapshot is None and delay is zero.
        job = self.layer.snapshot("A", parsed, self.match, 0)
        if job is not None or self.layer.delay_steps:
            raise RuntimeError("unexpected frozen action-layer contract")
        low, info = self.layer.lower("A", parsed, None, self.match)
        # JSON round-trip matches the trusted journal's replay representation.
        low = plain(low)
        self._log("cmd", k=self.match.k, seat="A", cmd=low)
        applied = self.match.apply("A", low) or {}
        return plain({"planning": info, "applied": applied})

    def ready(self):
        if self.match.phase().state != UNIT_OVER:
            raise Refused("ready only allowed during the between-point review", 409)
        self._log("resume", k=self.match.k)
        self.match.resume()

    def step(self, n=1):
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 10000:
            raise ValueError("step count must be 1..10000")
        for _ in range(n):
            if self.match.phase().state in (FINISHED, UNIT_OVER):
                break
            self.match.step()
            self.total_steps += 1
        return self.state()

    def finish_log(self, reason):
        self._log("end", k=self.match.k, reason=reason)
