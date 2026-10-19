"""The privileged twin of the exported humanoid soccer 2 v 2 match (roboolympics-match-soccer-match-i00-standard-realtime).

Adapter of the generic full-simulator setting (tools/fullsim): the frozen sport (sports/soccer, soccer-2v2-10, the
`match` format: one seat A commands both Booster T1 of team A against the scripted team B), its frozen instance (level
2, seed 7, S = 5, cutoff 7200 s), and the declared truth the program sees in the formal match.
Nothing of sports/soccer changes: its directory is the twin's simulator byte for byte (PROTOCOL H.7).
"""
from __future__ import annotations

import math

SPORT = "soccer"
FORMAT = "match"
SEATS = ("A",)
ACTION_LEVEL = "low"                    # soccer's one action level: walk / stand / kick per robot (entity "1", "2")
LEVELS = (1, 2, 3)                      # the scripted team's levels (2 and 3 official, 1 a warm-up; the agent's copy: 1, 2)
SOURCE_TASK = "soccer-match-wallclock-program-standard"
FAMILY = "soccer-match"
INSTANCES = {"i00": {"level": 2, "seed": 7}}
SLOWDOWN = 5                            # the twin's RO_SLOWDOWN
CUTOFF_S = 7200                         # the twin's [agent] timeout_sec
EVERY = 1                               # a fresh view every control step (20 ms of game time, 0.1 s of wall time at S = 5)
MAX_COMMANDS = 2                        # one act in flight per robot (the twin's rule): at most one command per robot per view
READY_TIMEOUT_S = 600                   # the twin's READY_TIMEOUT_S
REPLAY_TIMEOUT_S = 600                  # the twin's RO_REPLAY_TIMEOUT_S (a whole-match replay: about 150-300 s)
# Two halves of 300 s of game time at S = 5 are 3000 s of wall time; the stoppages' restarts, a shoot-out (3 kicks each
# + up to 3 sudden-death rounds, 20 s of game time per kick: up to 1200 s of wall time) and the service's lag need the
# rest. The program's review answers are immediate (ready), so reviews add almost nothing.
MATCH_WALL_S = 4800
# The agent's copies hold no reference (H.2): the screening's truth reference (reference_check.py) is left out, and so are
# the scripted coach's "reference" level and the level it equals in 2 v 2 (level 3 with the in-walk kick: the oracle's
# exact play, #282 review) with their parameter set "ref"; the agent's copy plays levels 1 and 2 (the instance: 2).
# The generator also strips these assignments from the agent's copy of this adapter (export.public_adapter).
PUBLIC_DROP_FILES = ("builtin_players.py", "reference_check.py")
PUBLIC_EDITS = {"soccer.py": [
    ('    "ref": dict(delay_s=0.0, vmax=0.8, vlat=0.4, wmax=1.0, pos_tol=0.05, yaw_tol=0.08, every=1, shoot_m=7.5,\n'
     '                feet="both"),\n', ""),
    ('# level 3 (soccer-2v2-6): the strongest scripted team found in the screening: every robot goes for the ball (the\n'
     '# "chase" plan) at the reference\'s speed and precision, no delay (docs/screening/soccer.md)\n'
     'COACH_LEVELS[3] = dict(COACH_LEVELS["ref"], style="chase")\n',
     "# (the privileged twin's public copy: level 3, the oracle's play, is left out, H.2)\n"),
    ('# a match. "reference": the strongest play found, every robot goes for the ball at the reference\'s speed with the\n'
     '# in-walk kick (the tools/check stage-5 truth reference); a coordinated plan (one strikes, one covers or presses behind)\n'
     '# lost to it head to head 4-7 / 40 (docs/screening/soccer.md)\n', "# a match.\n"),
    ("    for _k in (1, 2, 3):\n", "    for _k in (1, 2):\n"),
    ('COACH_LEVELS["reference"] = dict(COACH_LEVELS["ref"], style="chase", step=True)\n',
     "# (the privileged twin's public copy: the reference level is left out, H.2)\n"),
]}
IMAGE = "ghcr.io/mll-lab-nu/efe:olympiad-soccer-0.1.0@sha256:b6fbfae73399a7daee9c623eb34cfe18de63b458349b5a2b9d122c00e9f1602b"
RESOURCES = {"min_cpus": 6.0, "min_memory_gb": 8.0, "verifier_min_cpus": 6.0, "verifier_min_memory_gb": 8.0,
             "cpus": 6, "memory_mb": 10240}
ROBOT = "booster-t1"
DESCRIPTION = ("robot soccer 2 v 2 (RoboCup Humanoid Soccer League rules, soccer-2v2-10): two simulated Booster T1 "
               "humanoids of team A, commanded by one program, against the scripted team B on a boarded 10 x 7 m pitch, "
               "two halves of 5 minutes of game time")

TRUTH_DOC = """\
`view["truth"]` (your team's frame = the world frame for seat A: you attack the goal at x = +5; metres, m/s, radians):

| field | what |
|---|---|
| `k` | the control step (20 ms of game time each) |
| `ball` | `pos` [x, y, z] (the ball's centre), `vel` [vx, vy, vz], `spin` [wx, wy, wz] |
| `robots` | `A1`, `A2` (yours: entities "1", "2") and `B1`, `B2` (the scripted team): `xy`, `yaw`, `z` (IMU height), `vel` [vx, vy, wz] (world frame), `fallen`, `bench` (penalized and removed), `penalty_s` (time left, or null), `kicking` (a kick under way) |
| `referee` | the game controller's internal state now: `state` (kickoff / play / pso_kick), `period` (1, 2, "pso"), `clock_s`, `kickoff` {`team`, `in_play`, `touched_outside`} or null, `free_kick` {`team`, `kind`, `spot`, `in_play`} or null, `shootout` {`n`, `team`, `striker`, `keeper`} or null (the kick under way) |
| `qpos`, `qvel` | the complete MuJoCo state (`Session("soccer", ...).world.w.m` is the model: joint names and addresses) |

Nothing of the future: no scripted team's plan, no random draws, no coming events. Your robots' own state (pose,
IMU, command under way, joint positions) and the referee's messages are in `view["state"]` as in the twin."""

NOTES_DOC = """\
Robot soccer 2 v 2 (soccer-2v2-10, RoboCup Humanoid Soccer League rules with the deviations of `config["spec"]`): your
two Booster T1 (team A) against the scripted team B, two halves of 300 s of game time, a penalty shoot-out when level.
One control step is 20 ms of game time; at S = 5 it is 0.1 s of wall time, and the world runs on while your program
computes. Each robot takes one low-level command at a time: `{"type": "walk", "v": [vx, vy, wz], "entity": "1"}`,
`{"type": "stand", "entity": "2"}` or `{"type": "kick", "power": P, "style": "step"|"swing"|"push", ...}`
(`config["spec"]["act"]` and `config["spec"]["robot"]` have the schema, the strike zones and the kick timings). Return
`None`, one command, or a list of at most two commands (one per robot) per view; `{"type": "ready"}` alone during a
review (after every goal, half time, dropped ball and shoot-out kick). A command for a fallen or penalized robot is
refused. The world does not wait: a command takes effect at the next control step after it arrives."""


def _f(x):
    return float(x)                     # full precision: the truth is exact


def truth(match) -> dict:
    """The declared truth of the formal match (pure: reads the world, never changes it; nothing of the future)."""
    import soccer as S                  # the frozen simulator (sports/soccer) the Session or the service imported
    w = match.w
    d = w.d
    team = "A"
    to = lambda xy: [_f(v) for v in S.to_team(team, xy)]   # noqa: E731
    robots = {}
    for r in S.ROBOTS:
        rb = w.rob[r]
        pen = w.penalty[r]
        robots[r] = {"xy": to(rb.xy(d)), "yaw": _f(S.yaw_to_team(team, rb.yaw(d))), "z": _f(rb.height(d)),
                     "vel": to(rb.vel(d)) + [_f(d.qvel[rb.rv + 5])], "fallen": w.fallen[r] is not None,
                     "bench": w.on_bench(r), "kicking": bool(w.kicking(r)),
                     "penalty_s": None if not pen or pen.get("pso") else _f(max(0, pen["until"] - w.k) * S.CONTROL_DT)}
    bp = w.ball_pos()
    bv = d.qvel[w._bv:w._bv + 6]
    ko, fk, cur = w.ko, w.fk, (w.pso or {}).get("cur") if w.pso else None
    referee = {"state": w.state, "period": w.period, "clock_s": _f(w.clock()),
               "kickoff": None if not ko else {"team": ko["team"], "in_play": bool(ko["in_play"]),
                                               "touched_outside": bool(ko["touched_outside"])},
               "free_kick": None if not fk else {"team": fk["team"], "kind": fk["kind"], "spot": to(fk["spot"]),
                                                 "in_play": bool(fk["in_play"])},
               "shootout": None if not cur else {"n": int(cur["n"]), "team": cur["team"], "striker": cur["striker"],
                                                 "keeper": cur["keeper"]}}
    return {"k": int(w.k),
            "ball": {"pos": to(bp[:2]) + [_f(bp[2])], "vel": to(bv[:2]) + [_f(bv[2])],
                     "spin": [_f(v) for v in bv[3:6]]},
            "robots": robots, "referee": referee,
            "qpos": [float(x) for x in d.qpos], "qvel": [float(x) for x in d.qvel]}



def unavailable():
    """The soccer simulator needs its image (ghcr.io/mll-lab-nu/efe:olympiad-soccer-<version>): PyTorch for the T1 walking policy
    and the T1 model at $RCB_T1_ASSETS. Hosts without them (the repository's CI) skip it in the generic tests."""
    import importlib.util
    import os
    if importlib.util.find_spec("torch") is None:
        return "PyTorch missing (the T1 walking policy; the soccer image has it)"
    if not os.path.isdir(os.environ.get("RCB_T1_ASSETS", "/opt/sai_t1")):
        return "the Booster T1 model ($RCB_T1_ASSETS) missing (the soccer image has it)"
    return None
