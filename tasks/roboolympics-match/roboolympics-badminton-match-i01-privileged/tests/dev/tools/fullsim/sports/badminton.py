"""Badminton singles (revision badminton-wallclock-12): the twins of roboolympics-badminton-match-i01/i02-standard-realtime
(First Exam, exported from fexam-export 0d7f680c)."""

SPORT = "badminton"
FORMAT = "match-wallclock"  # the twin's RO_FORMAT
SOURCE_TASK = "badminton-match-wallclock-program-standard"
FAMILY = "badminton-match"
INSTANCES = {"i01": {"level": 1, "seed": 7}, "i02": {"level": 2, "seed": 8}}
LEVELS = (1, 2, 3)  # badminton has three levels (BM.LEVELS)
SLOWDOWN = 20  # the twins' S (badminton stays x20: at x10 the camera-only reference loses level 1)
CUTOFF_S = 14400  # the twins' per-task cutoff
READY_TIMEOUT_S = 300
MATCH_WALL_S = 7200  # a game to 11 at S = 20: 78-93 min for the camera-only reference
IMAGE = "ghcr.io/mll-lab-nu/eai-olympiad:0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7"
RESOURCES = {"min_cpus": 4.0, "min_memory_gb": 6.0, "verifier_min_cpus": 4.0, "verifier_min_memory_gb": 8.0}
DESCRIPTION = (
    "singles badminton on a 0.4-scale court (BWF Laws, one game to 11): Franka Panda with a racket on a gantry base "
    "against the scripted opponent"
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
NOTES_DOC = """Coordinates: metres, +y toward the opponent, z up, the net at y = 0. One control step is 0.01 game seconds; at
S = 20 that is 0.2 s of wall time. You serve the first point (the rally winner serves next); `toss` places the
shuttle, `act` plans a stroke at a contact time `t` (game seconds from when the act takes effect, `lead` steps
after it arrives), `move` sends the base. The rules and the action schema: `Session.spec()` and
`sports/badminton/sport.toml`."""


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
