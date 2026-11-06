"""The privileged twin of the exported table-tennis match (embodied-olympics-match-tabletennis-match-i04-realtime).

Adapter of the generic full-simulator setting (tools/fullsim): the frozen sport (sports/tabletennis, its `match`
format against the scripted opponent), its frozen instance (level 4, seed 34, S = 10, cutoff 7200 s), and the declared
truth the program sees in the formal match (the fields of the earlier table-tennis twins' tools/tt_fullsim).
Nothing of sports/tabletennis changes: its directory is the twin's simulator byte for byte (PROTOCOL H.7).
"""
from __future__ import annotations

SPORT = "tabletennis"
FORMAT = "match"
SEATS = ("A",)
ACTION_LEVEL = "high"
LEVELS = (1, 2, 3, 4)                   # the scripted opponent's official levels
SOURCE_TASK = "tabletennis-match-wallclock-program-standard"
FAMILY = "tabletennis-match"
INSTANCES = {"i04": {"level": 4, "seed": 34}}
SLOWDOWN = 10                           # the twin's RO_SLOWDOWN
CUTOFF_S = 7200                         # the twin's [agent] timeout_sec
READY_TIMEOUT_S = 300                   # the twin's READY_TIMEOUT_S
REPLAY_TIMEOUT_S = 600                  # the twin's RO_REPLAY_TIMEOUT_S
VIDEO_TIMEOUT_S = 600                   # the twin's RCB_VIDEO_TIMEOUT_S
MATCH_WALL_S = 7200                     # the twin's cutoff: the match ends there unfinished (not won)
IMAGE = "ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7"
RESOURCES = {"min_cpus": 4.0, "min_memory_gb": 4.0, "verifier_min_cpus": 4.0, "verifier_min_memory_gb": 8.0}
ROBOT = "franka-panda"
DESCRIPTION = "table tennis, one game to 5 against the scripted opponent"
TRUTH_DOC = """- the ball's state (`ball_pos`, `ball_vel`, its spin and flight phase: the simulator's own state() fields);
- `opponent_x`: where the opponent's paddle base is now, `opponent_parameters`: its level's parameters;
- `leg`: the current leg (point, server, state, launch step, serve window);
- `qpos`, `qvel`: the whole MuJoCo state; `servo`: your arm's servo state (targets, limits in force)."""


def truth(match):
    r = match.R
    return {
        **r.s.state(),
        "opponent_x": r.opp_x(),
        "opponent_parameters": r.lv,
        "leg": r.leg,
        "qpos": r.s.d.qpos,
        "qvel": r.s.d.qvel,
        "servo": r.s.servo.state(),
    }
