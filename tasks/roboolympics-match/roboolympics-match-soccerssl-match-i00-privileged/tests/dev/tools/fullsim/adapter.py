"""A sport's privileged-setting adapter: tools/fullsim/sports/<sport>.py (never under sports/<sport>/: that directory is
copied byte for byte into the twin task's simulator, PROTOCOL H.7).

Required: SPORT, SOURCE_TASK, FAMILY, INSTANCES, SLOWDOWN, CUTOFF_S, IMAGE, truth(match).
Optional (defaults below): FORMAT, SEATS, ACTION_LEVEL, LEVELS, EVERY, MAX_COMMANDS, READY_TIMEOUT_S, MATCH_WALL_S,
REPLAY_TIMEOUT_S, VIDEO_TIMEOUT_S, VERIFIER_TIMEOUT_S, PUBLIC_DROP_FILES, METADATA_FAMILY (the twin's [metadata] family when it is
not FAMILY with underscores), TRUTH_DOC, NOTES_DOC, RESOURCES, DESCRIPTION, ROBOT, PUBLIC_EDITS,
unavailable() (why this host cannot build the sport, e.g. a package only its image has; None).
"""

from __future__ import annotations

import importlib
from types import ModuleType

DEFAULTS = {
    "FORMAT": "match",
    "SEATS": ("A",),
    "ACTION_LEVEL": "high",
    "LEVELS": (1, 2, 3, 4),
    "EVERY": 5,  # control steps between two views of the formal match (also in calibrate.py)
    "MAX_COMMANDS": 1,  # commands a program may return for one view (a list), each one in flight on its own
    "READY_TIMEOUT_S": 300,  # the review after each point (the twin's READY_TIMEOUT_S)
    "MATCH_WALL_S": 1800,  # the formal match's wall-clock cutoff (the program's CPU limit too)
    "REPLAY_TIMEOUT_S": 600,  # one fresh-process replay of the whole match (the twin's RO_REPLAY_TIMEOUT_S)
    "VIDEO_TIMEOUT_S": 1800,  # the replay video after the verdict (tests/grade.py VIDEO_TIMEOUT_S, the same number)
    "VERIFIER_TIMEOUT_S": None,  # default: MATCH_WALL_S + REPLAY_TIMEOUT_S + 600 + VIDEO_TIMEOUT_S (one replay)
    "PUBLIC_DROP_FILES": ("builtin_players.py",),  # files of sports/<sport>/ left out of the agent's copies
    "PUBLIC_EDITS": {},  # {file of sports/<sport>/: cut from this line on} in the agent's copies (H.2)
    "TRUTH_DOC": "",
    "NOTES_DOC": "",
    "RESOURCES": {},
    "DESCRIPTION": "",
    "unavailable": lambda: None,  # the generic tests skip a sport this host cannot build
}
REQUIRED = ("SPORT", "SOURCE_TASK", "FAMILY", "INSTANCES", "SLOWDOWN", "CUTOFF_S", "IMAGE", "truth")


def load(sport: str) -> ModuleType:
    mod = importlib.import_module(f"tools.fullsim.sports.{sport}")
    missing = [k for k in REQUIRED if not hasattr(mod, k)]
    if missing:
        raise AttributeError(f"tools/fullsim/sports/{sport}.py lacks {', '.join(missing)}")
    for k, v in DEFAULTS.items():
        if not hasattr(mod, k):
            setattr(mod, k, v)
    if mod.VERIFIER_TIMEOUT_S is None:
        mod.VERIFIER_TIMEOUT_S = mod.MATCH_WALL_S + mod.REPLAY_TIMEOUT_S + 600 + mod.VIDEO_TIMEOUT_S
    return mod


def task_name(ad, inst: str) -> str:
    return f"roboolympics-match-{ad.FAMILY}-{inst}-privileged"


def twin_name(ad, inst: str) -> str:
    return f"roboolympics-match-{ad.FAMILY}-{inst}-standard-realtime"
