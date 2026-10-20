"""Wheeled robot soccer 5 v 5 (RoboCup SSL Division B, sports/soccer_ssl): the privileged twin of the exported
standard-realtime match roboolympics-match-soccerssl-match-i00-standard-realtime (level 2, seed 7, S = 10, 14400 s).

The twin's rules, referee, scripted yellow team, skill layer and S = 10 clock are unchanged; only the information (the
full state instead of the four overhead camera images) and the development rights (the full simulator, whole-match
reset) differ. The formal match runs in the verifier after the agent's time: at S = 10 a match of up to about 1070 s
of game time (two halves of 300 s of playing time plus every stoppage, and a shoot-out when level) takes up to about
3 hours of wall clock there, so MATCH_WALL_S and VERIFIER_TIMEOUT_S are long; the cutoff (the agent's time) stays the
twin's 14400 s (PROTOCOL H.7).
"""

from __future__ import annotations

SPORT = "soccer_ssl"
FORMAT = "match"
SEATS = ("A",)
ACTION_LEVEL = "high"
LEVELS = (1, 2, 3)  # sport.toml [formats.match] levels: 1 warm-up, 2 and 3 official
SOURCE_TASK = "soccer_ssl-match-wallclock-program-standard"  # our generated task; its environment/sim is the twin's
FAMILY = "soccerssl-match"
ROBOT = "ssl-robot"  # the twin's [metadata] robot
METADATA_FAMILY = "soccer_ssl_match"  # the twin's [metadata] family
INSTANCES = {"i00": {"level": 2, "seed": 7}}  # the twin's RO_LEVEL / RO_SEED (its docker-compose.yaml)
SLOWDOWN = 10  # the twin's RO_SLOWDOWN: the formal match runs on the clock the program was developed for (user, 10-17)
CUTOFF_S = 14400  # the twin's [agent] timeout_sec
EVERY = 5  # control steps between two views of the formal match (as table tennis)
MAX_COMMANDS = 1  # one act per view; a `batch` act commands up to five robots at one boundary (the sport's own)
READY_TIMEOUT_S = 600  # the twin's READY_TIMEOUT_S (sport.toml [timing] ready_timeout_s)
# The formal match's wall-clock cutoff: the longest match of the screening's 76 camera-reference matches and the
# calibration's full-state matches ran 107 200 control steps (1072 s of game time) = 10 720 s at S = 10; 13 500 s
# leaves 26 % for the service's lag on a loaded machine (12 600 s until 2026-10-16, user decision PRIVALL). The
# program's CPU limit is the same number. A typical match is far shorter: the 2026-10-17 Harbor oracle's verifier
# phase took 87 min in all (47 446 steps).
MATCH_WALL_S = 13500
REPLAY_TIMEOUT_S = 1800  # the twin's RO_REPLAY_TIMEOUT_S: a fresh-process replay of a whole match
# VERIFIER_TIMEOUT_S: the default, MATCH_WALL_S + REPLAY_TIMEOUT_S + 600 + VIDEO_TIMEOUT_S (one replay).
PUBLIC_DROP_FILES = ()  # opponents/ is built on builtin_players.Reference: the development copy needs it
# ... but not the camera-only reference player (its overhead-camera tracker and TeamPlayer, the wrapper the solution
# drives with the true state): the agent's copies stop before them (H.2); plugin.players() then offers the team only
PUBLIC_EDITS = {"builtin_players.py": [(("<cut>", "# the overhead camera: a colour detector"),
                                        "# (the privileged twin's public copy ends here: the camera-only reference player is left out, H.2)\n")]}
IMAGE = "ghcr.io/mll-lab-nu/efe:olympiad-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7"
RESOURCES = {
    "min_cpus": 4.0,
    "min_memory_gb": 6.0,
    "verifier_min_cpus": 4.0,
    "verifier_min_memory_gb": 8.0,
    "measured": "author estimate (RoboOlympics, an RTX 4090 workstation, 2026-10-15): CPU-only MuJoCo 3.3.7, no cameras; one "
    "world about 0.4 GB, a whole match 4-8 CPU minutes in process; the verifier holds the service, the policy (2 GiB "
    "address space) and two fresh replays",
}
DESCRIPTION = (
    "wheeled robot soccer 5 v 5 (RoboCup SSL Division B): you command the blue team (five omnidirectional SSL robots, "
    "the skills move / kick / dribble / substitute) against the scripted yellow team"
)

TRUTH_DOC = """\
`view["truth"]` is the state of the formal match at the step of the view (`state.step`), nothing later:

- `t`, `step`: game time (s) and control step (0.01 s).
- `team`: `blue` (yours). Like every command and the observation, it is in **your team's frame** (you attack +x;
  `referee.attack_sign` maps it to the world frame, which flips at half time).
- `ball`: `pos` [x, y, z] (m), `vel` [vx, vy, vz] (m/s); `ball_spin` [wx, wy, wz] (rad/s, world frame).
- `us`, `them`: robot number -> `on_field`, `pose` [x, y, theta], `vel` [vx, vy, omega] (the yellow team's robots
  are `them`; true poses, no vision delay).
- `referee`: the game controller's information (as `state.referee`).
- `world`: `ball_pos`, `ball_vel` in the world frame; `attack_sign`.
- `qpos`, `qvel`: the complete MuJoCo state vectors (`Session.world.w.model` names the joints).
- `opponent_level` and `opponent_parameters` (the scripted team's level table: reaction delay, speed, scheme, ...).

No future information: no seed, no random stream, no plan of the scripted team. `state.robots` keeps your robots'
own sensors (kicker charge, break beam, dribbler, the skill's target and eta).
"""

NOTES_DOC = """\
- One formal view every 5 control steps (and during every review). Return one act (a single command or a `batch` of
  up to five, one per robot), `{"type": "ready"}` during a review (after every goal, at half time, before the
  shoot-out and after every shoot-out kick: the world is frozen; at most 600 s), or `None`.
- The S = 10 clock: one control step every 0.1 s of wall time, whether your program has answered or not; the sport's
  declared reaction delay applies (an act takes effect 2 steps after the state it answers, or later if you answer
  later). A whole match is two halves of 300 s of playing time plus the stoppages: about 800-1070 s of game time,
  2.3-3 hours of wall clock in the verifier.
- `Session("soccer_ssl", level, seed)` in development: `s.act` applies a command at once (no reaction delay); use
  `s.step(2)` before `s.act` to reproduce the formal timing.
- The scripted team (`sports/soccer_ssl/opponents/`) is built on the sport's reference team
  (`sports/soccer_ssl/builtin_players.py`); both are readable in the development copy.
"""


def truth(match) -> dict:
    """The full state of the formal match for seat A (blue), now: read-only (World.truth_view is what the scripted
    team itself reads every step), JSON-able, nothing from the future."""
    import importlib

    w = match.w
    out = dict(w.truth_view("blue"))
    ball = w.ball
    out["ball_spin"] = [float(x) for x in w.data.qvel[ball_qvel_adr(w) + 3 : ball_qvel_adr(w) + 6]]
    out["world"] = {
        "ball_pos": [float(x) for x in ball.pos],
        "ball_vel": [float(x) for x in ball.vel],
        "attack_sign": int(w.sign("blue")),
    }
    out["qpos"] = [float(x) for x in w.data.qpos]
    out["qvel"] = [float(x) for x in w.data.qvel]
    out["opponent_level"] = int(match.level)
    try:
        table = importlib.import_module("opponents").LEVELS[int(match.level)]
        out["opponent_parameters"] = {k: v for k, v in table.items() if isinstance(v, (bool, int, float, str))}
    except (ModuleNotFoundError, KeyError):
        out["opponent_parameters"] = {}
    return out


def ball_qvel_adr(w) -> int:
    """The ball's free joint's first qvel address (its linear velocity; the angular one follows)."""
    import mujoco

    body = w.ball.body
    jnt = int(w.model.body_jntadr[body])
    if jnt < 0 or int(w.model.jnt_type[jnt]) != int(mujoco.mjtJoint.mjJNT_FREE):
        raise RuntimeError("the ball has no free joint")
    return int(w.model.jnt_dofadr[jnt])
