"""Badminton duel against the built-in RL opponent: the privileged twin of
embodied-olympics-match-badminton-duelrl-i01-realtime (seat B builtin_players:RLOpponent, seed 1001, S = 20,
14400 s).

The twin's rules, referee, built-in seat B, action layer and S = 20 clock are unchanged; only the information (the full
state instead of the camera images) and the development rights (the full simulator, whole-match reset) differ. A duel
has no scripted level: the single level 0 stands for "seat B is the twin's built-in player". The task's own
tools/fullsim/duel.py starts that seat in the formal match (BUILTIN_SEATS = the twin's RO_BUILTIN_SEATS) and in
DuelSession; nothing of sports/badminton changes (PROTOCOL H.7).
"""
from __future__ import annotations

import sys

import numpy as np

SPORT = "badminton"
FORMAT = "duel-wallclock"                # the twin's RO_FORMAT
SEATS = ("A", "B")                       # the twin's RO_SEATS
BUILTIN_SEATS = {"B": "builtin_players:RLOpponent"}   # the twin's RO_BUILTIN_SEATS
ACTION_LEVEL = "high"
LEVELS = (0,)                            # no scripted level: seat B is the built-in player
SOURCE_TASK = "badminton-duel-wallclock-program-standard"
FAMILY = "badminton-duelrl"
METADATA_FAMILY = "badminton_duel"       # the twin's [metadata] family
INSTANCES = {"i01": {"level": 0, "seed": 1001}}
SLOWDOWN = 20                            # the twin's RO_SLOWDOWN
CUTOFF_S = 14400                         # the twin's [agent] timeout_sec
READY_TIMEOUT_S = 300                    # the twin's READY_TIMEOUT_S
REPLAY_TIMEOUT_S = 600                   # the twin's RO_REPLAY_TIMEOUT_S
VIDEO_TIMEOUT_S = 600                    # the twin's RCB_VIDEO_TIMEOUT_S
MATCH_WALL_S = 7200                     # a game to 11 at S = 20 (as the badminton match twins)
IMAGE = "ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7"
RESOURCES = {"min_cpus": 4.0, "min_memory_gb": 6.0, "verifier_min_cpus": 4.0, "verifier_min_memory_gb": 8.0}
ROBOT = "franka-panda"
DESCRIPTION = "singles badminton (one game to 11) against the built-in RL opponent (seat B)"
TRUTH_DOC = '`view["truth"]` is the state of the formal match at the step of the view (`state.step`), nothing later. Your frame is\nthe world frame (you are seat A, +y toward the opponent, the net at y = 0; seat B\'s own frame is the world mirrored).\n\n- `k` (control step), `shuttle_pos` [x, y, z] (m), `shuttle_vel` [vx, vy, vz] (m/s), `shuttle_live` (in flight);\n- `opponent_xy`: where the opponent\'s base is now, `opponent_q`, `opponent_qd`: its base and arm joints;\n- `rally`: the rally state (point, server, receiver, service court, ...), `score` {A, B};\n- `qpos`, `qvel`: your robot\'s joints (base x, y and the arm) in the simulator\'s order; `target`: the joint targets.'
NOTES_DOC = "Seat B is the twin's built-in player (`sports/badminton/builtin_players.py`, class `RLOpponent`: the reference\nplayer's play loop and the platform's stroke controller, with its contact, shot, waiting position and serve length\nlearned by policy search, `rl/`), played inside the service process exactly as in the twin; it sees the shuttle's true\nstate (`Match.builtin_truth`). For development use `DuelSession` (below): a `Session` in which seat B plays with that\nplayer every `b_every` control steps (default 1; in the formal match it acts about every 0.05 s of wall time). One\ncontrol step is 0.01 game seconds; at S = 20 that is 0.2 s of wall time. The rules (BWF Laws, one game to 11) and the\naction schema: `Session.spec()` and `sports/badminton/sport.toml`."


def _plain(v):
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, np.ndarray):
        return v.tolist()
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def truth(match):
    g = match.g
    BD = sys.modules[type(g).__module__]
    a, b = g.sides["A"].s, g.sides["B"].s
    opp = BD.to_side("B", np.r_[b.d.qpos[b.qa[:2]], 0.0])[:2]    # B's base in the world (= A's) frame
    return {
        "k": int(g.k),
        "shuttle_pos": [float(x) for x in g.sh_p],
        "shuttle_vel": [float(x) for x in g.sh_v],
        "shuttle_live": bool(g.sh_live),
        "opponent_xy": [float(x) for x in opp],
        "opponent_q": b.d.qpos[b.qa].tolist(),
        "opponent_qd": b.d.qvel[b.va].tolist(),
        "rally": _plain(getattr(g, "rs", {})),
        "score": dict(g.score),
        "qpos": a.d.qpos[a.qa].tolist(),
        "qvel": a.d.qvel[a.va].tolist(),
        "target": [float(x) for x in a.target],
    }
