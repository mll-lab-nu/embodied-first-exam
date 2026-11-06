"""Badminton singles at the LOW level: the privileged twin of
embodied-olympics-match-badminton-matchlow-i01-realtime (the agent's own act skill in the loop; level 2, seed 8,
S = 20, 14400 s). The task's own adapter of the generic full-simulator setting (tools/fullsim). The robot, its limits,
the low-level command set and the opponent are the twin's; only the skill-server plumbing (RCB_SKILL_INLOOP_*: the
simulator calling the agent's act.py over TCP) is replaced: the program returns the low-level commands itself
(ACTION_LEVEL "low" without an in-loop skill is the sport's LowLayer: traj / move / toss / none), every 2 control
steps (the twin's in-loop cadence). Nothing of sports/badminton changes (PROTOCOL H.7)."""

SPORT = "badminton"
FORMAT = "match-wallclock"  # the twin's RO_FORMAT
SOURCE_TASK = "badminton-match-wallclock-program-lowlevel-standard"
ACTION_LEVEL = "low"  # the twin's RCB_ACTION_LEVEL; no RCB_SKILL_INLOOP_*: LowLayer
EVERY = 2  # the twin's in-loop cadence ([modes.low.inloop] step_every)
FAMILY = "badminton-matchlow"
METADATA_FAMILY = "badminton_matchlow"  # the twin's [metadata] family
INSTANCES = {"i01": {"level": 2, "seed": 8}}
LEVELS = (1, 2, 3, 4, 5)  # the levels of the twin's revision (5: the top tier, the twin's opponent)
SLOWDOWN = 20  # the twins' S (badminton stays x20: at x10 the camera-only reference loses level 1)
CUTOFF_S = 14400  # the twins' per-task cutoff
READY_TIMEOUT_S = 300
REPLAY_TIMEOUT_S = 600  # the twin's RO_REPLAY_TIMEOUT_S
VIDEO_TIMEOUT_S = 1200  # the twin's RCB_VIDEO_TIMEOUT_S
MATCH_WALL_S = 7200  # a game to 11 at S = 20: 78-93 min for the camera-only reference
IMAGE = "ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7"
RESOURCES = {"min_cpus": 4.0, "min_memory_gb": 6.0, "verifier_min_cpus": 4.0, "verifier_min_memory_gb": 8.0}
DESCRIPTION = (
    "singles badminton on a 0.4-scale court (BWF Laws, one game to 11): Franka Panda with a racket on a gantry base "
    "against the scripted opponent, at the low level (your own joint-level commands)"
)
LEG_KEYS = (
    "kind",
    "point",
    "state",
    "server",
    "hold_from",
    "launch",
    "ready",
    "deadline",
    "service_court_right",
    "serve",
)
TRUTH_DOC = """- `shuttle_pos`, `shuttle_vel`: the shuttle's position (m) and velocity (m/s) now, `shuttle_live` (in flight);
- `opponent_xy`: where the opponent's base is now, `opponent_parameters`: its level's parameters;
- `leg`: the current leg (kind, point, state, server, launch step, serve window), `score`, `k` (control step);
- `qpos`, `qvel`: your robot's joints (base x, y and the arm) in the simulator's order; `target`: the joint targets."""
NOTES_DOC = 'The low level (the twin\'s skill in the loop, without its plumbing): your program returns the robot\'s LOW-LEVEL\ncommands itself, `{"type": "traj", "q": rows of 9 joint targets}` (one row per control step from the next step on;\nthen the robot returns to its ready pose and the base holds), `{"type": "move", "base"}`, `{"type": "toss", ...}`\nand `{"type": "none"}` (the schema: `Session.spec()["actions"]`), every view (every 2 control steps, the twin\'s\nin-loop cadence). There is no `act` skill and no skill server: what the twin\'s skill computes (the stroke within the\nreal limits) your program computes, and its computation counts as the twin\'s skill\'s does (the world runs on while\nit computes; a command takes effect at the first control step after the answer). The low-level toolkit of the twin\n(the robot\'s own model, the kinematics and servo libraries) is in your copy of the simulator under\n`sports/badminton/seat/` (the twin\'s /opt/robot). Coordinates: metres, +y toward the opponent, the net at y = 0.\nOne control step is 0.01 game seconds; at S = 20 that is 0.2 s of wall time.'


def truth(match):
    g = match.g
    s = g.s
    return {
        "k": int(g.k),
        "shuttle_pos": [float(x) for x in s.sh_p],
        "shuttle_vel": [float(x) for x in s.sh_v],
        "shuttle_live": bool(s.sh_live),
        "opponent_xy": [float(x) for x in g.opp_xy()],
        "opponent_parameters": {k: v for k, v in g.lv.items() if k != "seed"},
        "leg": {k: g.leg[k] for k in LEG_KEYS if k in g.leg},
        "score": list(g.score),
        "qpos": s.d.qpos[s.qa].tolist(),
        "qvel": s.d.qvel[s.va].tolist(),
        "target": [float(x) for x in s.target],
    }
