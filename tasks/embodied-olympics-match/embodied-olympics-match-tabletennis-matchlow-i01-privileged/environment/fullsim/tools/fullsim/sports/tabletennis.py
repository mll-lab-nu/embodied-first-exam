"""The privileged twin of the exported table-tennis match at the LOW level
(embodied-olympics-match-tabletennis-matchlow-i01-realtime: the agent's own skill in the loop).

Adapter of the generic full-simulator setting (tools/fullsim): the frozen sport (sports/tabletennis, its `match`
format against the scripted opponent), its frozen instance (level 1, seed 22, S = 10, cutoff 7200 s), and the declared
truth the program sees in the formal match. The robot, its limits, the low-level command set and the opponent are the
twin's; only the skill-server plumbing (RCB_SKILL_INLOOP_*: the simulator calling the agent's hit.py / step() over TCP)
is replaced: the program returns the low-level commands itself (ACTION_LEVEL "low" without an in-loop skill is the
sport's JointLayer: traj / slew / hold / toss), every 2 control steps (the twin's step() cadence). Nothing of
sports/tabletennis changes: its directory is the twin's simulator byte for byte (PROTOCOL H.7).
"""
from __future__ import annotations

SPORT = "tabletennis"
FORMAT = "match"
SEATS = ("A",)
ACTION_LEVEL = "low"                    # the twin's RCB_ACTION_LEVEL; no RCB_SKILL_INLOOP_*: JointLayer
EVERY = 2                               # the twin's step() cadence ([modes.low.inloop] step_every)
LEVELS = (1, 2, 3, 4)                   # the scripted opponent's official levels
SOURCE_TASK = "tabletennis-match-wallclock-program-lowlevel-standard"
FAMILY = "tabletennis-matchlow"
METADATA_FAMILY = "tabletennis_matchlow"  # the twin's [metadata] family
INSTANCES = {"i01": {"level": 1, "seed": 22}}
SLOWDOWN = 10                           # the twin's RO_SLOWDOWN
CUTOFF_S = 7200                         # the twin's [agent] timeout_sec
READY_TIMEOUT_S = 300                   # the twin's READY_TIMEOUT_S
REPLAY_TIMEOUT_S = 600                  # the twin's RO_REPLAY_TIMEOUT_S
VIDEO_TIMEOUT_S = 600                   # the twin's RCB_VIDEO_TIMEOUT_S
MATCH_WALL_S = 7200                     # the twin's cutoff: the match ends there unfinished (not won)
IMAGE = "ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7"
RESOURCES = {"min_cpus": 4.0, "min_memory_gb": 4.0, "verifier_min_cpus": 4.0, "verifier_min_memory_gb": 8.0}
ROBOT = "franka-panda"
DESCRIPTION = "table tennis at the low level (your own joint-level commands), one game to 5 against the scripted opponent"
TRUTH_DOC = "- the ball's state (`ball_pos`, `ball_vel`, its spin and flight phase: the simulator's own state() fields);\n- `opponent_x`: where the opponent's paddle base is now, `opponent_parameters`: its level's parameters;\n- `leg`: the current leg (point, server, state, launch step, serve window);\n- `qpos`, `qvel`: the whole MuJoCo state; `servo`: your arm's servo state (targets, limits in force)."
NOTES_DOC = 'The low level (the twin\'s skill in the loop, without its plumbing): your program returns the robot\'s LOW-LEVEL\ncommands itself, `{"type": "traj", "k0", "q": rows of 9 joint targets}`, `{"type": "slew", "q", "speed"}`,\n`{"type": "hold"}` and `{"type": "toss", ...}` (the schema: `Session.spec()["actions"]`), every view (every 2 control\nsteps, the cadence of the twin\'s `step()`). There is no `hit` skill and no skill server: what the twin\'s skill computes\n(the stroke, the swing within the real limits) your program computes, and its computation counts as the twin\'s skill\'s\ndoes (the world runs on while it computes; a command takes effect at the first control step after the answer). The\nlow-level toolkit of the twin (the robot\'s own model, the kinematics and servo libraries) is in your copy of the\nsimulator under `sports/tabletennis/seat/` (the twin\'s /opt/robot). One control step is 0.01 game seconds; at S = 10\nthat is 0.1 s of wall time.'


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
