"""Table tennis duel against the built-in RL opponent: the privileged twin of
embodied-olympics-match-tabletennis-duelrl-i01-realtime (seat B builtin_players:RLOpponentV2, seed 8, S = 10,
7200 s).

The twin's rules, referee, built-in seat B, action layer and S = 10 clock are unchanged; only the information (the full
state instead of the camera images) and the development rights (the full simulator, whole-match reset) differ. A duel
has no scripted level: the single level 0 stands for "seat B is the twin's built-in player". The task's own
tools/fullsim/duel.py starts that seat in the formal match (BUILTIN_SEATS = the twin's RO_BUILTIN_SEATS) and in
DuelSession; nothing of sports/tabletennis changes (PROTOCOL H.7).
"""
from __future__ import annotations

import numpy as np

SPORT = "tabletennis"
FORMAT = "duel"                          # the twin's RO_FORMAT
SEATS = ("A", "B")                       # the twin's RO_SEATS
BUILTIN_SEATS = {"B": "builtin_players:RLOpponentV2"}   # the twin's RO_BUILTIN_SEATS
ACTION_LEVEL = "high"
LEVELS = (0,)                            # no scripted level: seat B is the built-in player
SOURCE_TASK = "tabletennis-duel-wallclock-program-standard"
FAMILY = "tabletennis-duelrl"
METADATA_FAMILY = "tabletennis_duel"     # the twin's [metadata] family
INSTANCES = {"i01": {"level": 0, "seed": 8}}
SLOWDOWN = 10                            # the twin's RO_SLOWDOWN
CUTOFF_S = 7200                          # the twin's [agent] timeout_sec
READY_TIMEOUT_S = 300                    # the twin's READY_TIMEOUT_S
REPLAY_TIMEOUT_S = 600                   # the twin's RO_REPLAY_TIMEOUT_S
VIDEO_TIMEOUT_S = 600                    # the twin's RCB_VIDEO_TIMEOUT_S
MATCH_WALL_S = 7200                     # the twin's wall clock (RCB_WALL_CLOCK_S): unfinished there = not won
IMAGE = "ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7"
RESOURCES = {"min_cpus": 4.0, "min_memory_gb": 4.0, "verifier_min_cpus": 4.0, "verifier_min_memory_gb": 8.0}
ROBOT = "franka-panda"
DESCRIPTION = "table tennis, one game to 5 against the built-in RL opponent (seat B)"
TRUTH_DOC = '`view["truth"]` is the state of the formal match at the step of the view (`state.step`), nothing later. Your frame is\nthe world frame (you are seat A; seat B\'s own frame is the world turned by 180 degrees about z).\n\n- `ball_pos` [x, y, z] (m), `ball_vel` [vx, vy, vz] (m/s), `ball_spin` [wx, wy, wz] (rad/s): the ball now;\n- `opponent_x`: the world x of the opponent\'s paddle centre now, `opponent_paddle_pos`, `opponent_q`, `opponent_qd`\n  (its rail base and arm joints, in its own joint order);\n- `leg`: the rally state (point, server, receiver, expect, launch step, hits, ...), `score` {A, B};\n- `qpos`, `qvel`: the whole MuJoCo state; `servo`: your arm\'s servo state (targets, limits in force).'
NOTES_DOC = "Seat B is the twin's built-in player (`sports/tabletennis/builtin_players.py`, class `RLOpponentV2`: learned shot\nchoices and its own joint-level swing, `rl/`), played inside the service process exactly as in the twin; it sees the\nball's true position (`Match.builtin_truth`). For development use `DuelSession` (below): a `Session` in which seat B\nplays with that player every `b_every` control steps (default 1; in the formal match it acts about every 0.05 s of wall\ntime). One control step is 0.01 game seconds; at S = 10 that is 0.1 s of wall time. The rules (ITTF, one game to 5,\nlead by 2, cap 7) and the action schema: `Session.spec()` and `sports/tabletennis/sport.toml`."


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
    d = g.d
    pb = d.site_xpos[g.site_paddle["B"]]
    return {
        "ball_pos": d.qpos[0:3].tolist(),
        "ball_vel": d.qvel[0:3].tolist(),
        "ball_spin": d.qvel[3:6].tolist(),
        "opponent_x": float(pb[0]),
        "opponent_paddle_pos": pb.tolist(),
        "opponent_q": d.qpos[g.qadr["B"]].tolist(),
        "opponent_qd": d.qvel[g.vadr["B"]].tolist(),
        "leg": _plain(g.rs),
        "score": dict(g.score),
        "qpos": d.qpos.tolist(),
        "qvel": d.qvel.tolist(),
        "servo": _plain(g.servo["A"].state()) if hasattr(g.servo["A"], "state") else None,
    }
