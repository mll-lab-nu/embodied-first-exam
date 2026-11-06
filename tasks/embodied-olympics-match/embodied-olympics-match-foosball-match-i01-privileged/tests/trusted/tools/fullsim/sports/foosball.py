"""Foosball (sports/foosball): the privileged twin of embodied-olympics-match-foosball-match-i01-realtime
(level 3, seed 7, S = 20, 14400 s).

The twin's rules, referee, scripted red team, rod motors and S = 20 clock are unchanged; only the information (the
full state instead of the overhead camera image) and the development rights (the full simulator, whole-match reset)
differ. A game runs to 5 goals or the 240 s cap (game time): at S = 20 at most 4800 s of wall clock in the verifier
(MATCH_WALL_S leaves room for a loaded machine); the cutoff (the agent's time) stays the twin's 14400 s (PROTOCOL H.7).
"""

from __future__ import annotations

import sys

SPORT = "foosball"
FORMAT = "match"
SEATS = ("A",)
ACTION_LEVEL = "low"  # the twin's RCB_ACTION_LEVEL: rod slide / angle targets (the sport's only level)
LEVELS = (1, 2, 3, 4)  # foos.LEVELS
SOURCE_TASK = "foosball-match-wallclock-program-standard"
FAMILY = "foosball-match"
ROBOT = "foosball-rods"  # the twin's [metadata] robot
METADATA_FAMILY = "foosball_match"  # the twin's [metadata] family
INSTANCES = {"i01": {"level": 3, "seed": 7}}  # the twin's RO_LEVEL / RO_SEED (its docker-compose.yaml)
SLOWDOWN = 20  # the twin's RO_SLOWDOWN
CUTOFF_S = 14400  # the twin's [agent] timeout_sec
EVERY = 1  # a view every control step (the camera player acts on every observation)
MAX_COMMANDS = 1
READY_TIMEOUT_S = 300  # the twin's review limit
MATCH_WALL_S = 6000  # the 240 s cap x S = 20 = 4800 s, plus 25 % for the service's lag on a loaded machine
REPLAY_TIMEOUT_S = 600  # the twin's RO_REPLAY_TIMEOUT_S
VIDEO_TIMEOUT_S = 600  # the twin's RCB_VIDEO_TIMEOUT_S
IMAGE = "ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7"
RESOURCES = {"min_cpus": 4.0, "min_memory_gb": 6.0, "verifier_min_cpus": 4.0, "verifier_min_memory_gb": 8.0}
DESCRIPTION = (
    "table football on a physical table: you drive the four motorised rods of one team by slide and angle targets "
    "against the scripted computer team; one game to 5 goals under the ITSF rules"
)
TRUTH_DOC = '`view["truth"]` is the state of the formal match at the step of the view (`state.t_play`), nothing later. World\nframe: x along the table towards the opponent\'s goal (your local u, as you are seat A), y to your left (local v), z up,\nthe playfield at z = 0, the centre (0, 0); metres, radians, seconds of game time.\n\n- `k` (control step of play, 0.01 s), `t_rally` (game seconds since this rally\'s restart);\n- `ball_pos` [x, y, z] (m), `ball_vel` [vx, vy, vz] (m/s): the ball now;\n- `rods`: `you` and `opponent` -> rod (`goalie`, `defence`, `midfield`, `attack`) -> `slide`, `angle`,\n  `slide_velocity`, `angular_velocity` and the current `command` (each team in its own local frame, as\n  `state.rods` gives yours);\n- `figures`: `you` and `opponent` -> rod -> the world y of each figure now;\n- `opponent_parameters`: the scripted team\'s level parameters (reaction `delay` in control steps, `predict`,\n  `slide_v`, `omega`, `shoot`, `aim`, `style`);\n- `restart` (`where`: the rod group and the team of the restart), `opening` (the opening sequence\'s state), `score`\n  (goals and fouls per team);\n- `qpos`, `qvel`: the whole simulator state vector (MuJoCo order: the eight rods\' slide and spin joints, then the ball).'
NOTES_DOC = 'Units and timing: one control step is 0.01 game seconds; at S = 20 that is 0.2 s of wall time, and the program gets a\nview every control step (it should answer in well under 0.2 s to keep up). A command (`{"type": "rods", "rods":\n{rod: {"slide", "angle", "omega", "speed"}}}`; rods not named keep their command) reaches the motors 2 control steps\nafter the step that takes it. The rules (ITSF: one game to 5 goals, the opening sequence, possession limits per rod,\nno spinning, the 240 s cap) and the action ranges: `Session.spec()` and `sports/foosball/sport.toml`. The scripted\nteam\'s policy is `sports/foosball/foos_policy.py`; it sees the ball `delay` steps late.'
TEAM = {"you": "A", "opponent": "B"}


def _plain(v):
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def truth(match):
    r = match.r
    foos = sys.modules[type(r).__module__]
    return {
        "k": int(r.k),
        "t_rally": round(r.point_k * foos.DT, 3),
        "ball_pos": [float(x) for x in r.ball()],
        "ball_vel": [float(x) for x in r.ball_velocity()],
        "rods": {name: r.rod_state(seat) for name, seat in TEAM.items()},
        "figures": {name: {rod: r.figure_y(seat, rod) for rod in foos.RODS} for name, seat in TEAM.items()},
        "opponent_parameters": dict(foos.LEVELS[r.level]),
        "restart": {"where": _plain(r.restart_where)},
        "opening": _plain(r.opening),
        "score": _plain(r.scores()),
        "qpos": r.data.qpos.tolist(),
        "qvel": r.data.qvel.tolist(),
    }
