"""eai-standard/2.3 sim service for RoboOlympics: rcb_realtime.py (the sidecar's entry point, `python /srv/rcb_realtime.py`)
imports this module and calls build(). The sport and its frozen instance come from environment/docker-compose.yaml:
  RO_PLUGIN        the sport's plugin (/srv/sport/plugin.py)
  RO_FORMAT        the sport's format (match: one player against the scripted opponent)
  RO_SEED          the frozen instance's seed (serves, the opponent's returns, the execution scatter)
  RO_LEVEL         the scripted opponent's level
  RO_ACTION_LEVEL  the action level (high: strokes the service plans; low: joint or mallet targets)
  RO_TASK_TEXT, RO_EPISODE_TEXT   one sentence each for /spec
  RCB_SLOWDOWN     the slowdown S (badminton's stroke lead depends on it); RCB_DATA, RCB_RESET_BUDGET,
                   RCB_WALL_CLOCK_S: the service's own (rcb_service.main)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.sport import MatchConfig  # noqa: E402
from rcb_olympics import Olympics  # noqa: E402


def build() -> Olympics:
    env = os.environ.get
    plugin = env("RO_PLUGIN", "/srv/sport/plugin.py")
    sport = os.path.basename(os.path.dirname(os.path.abspath(plugin)))
    cfg = MatchConfig(sport=env("RO_SPORT", sport), format=env("RO_FORMAT", "match"), seats=("A",),
                      seed=int(env("RO_SEED", "101")), first="A", slowdown=float(env("RCB_SLOWDOWN") or 10),
                      level=int(env("RO_LEVEL", "1")), action_level=env("RO_ACTION_LEVEL", "high"), play="program")
    return Olympics(plugin, cfg, data=env("RCB_DATA", "/data"), task_text=env("RO_TASK_TEXT", ""),
                    episode_text=env("RO_EPISODE_TEXT", ""))
