"""Table tennis' skill API (docs/construction_zh.md step 3; skilleval/README.md): one skill, `hit`, the same in both
modes.

  high  Agent as Athlete: the act {type: hit, t, pos, normal, vel} IS the skill (also under its Season-1 name `act`,
        which may add `base`); the platform implements it (plugin.StrokeLayer: match.Match.plan_paddle: the base's
        go-to, IK, the limits-aware swing, robot-only rehearsals, the seeded execution scatter)
  low   Agent as Robotics Engineer: the player implements hit(t, pos, normal, vel, *, state, spec) itself from the
        toolkit (seat/toolkit.toml: the robot-only model, the joint-target interface with the real limits, the
        kinematics library, the servo model), at /app/output/skill/hit.py; evaluated after the match
        (lowlevel/evaluator.py, tools/skill_eval.py) and, in the skill-in-the-loop mode, called by the platform
        during the match (skilleval/inloop.py)

This file is the contract's single source (P6): the request ranges (the high level's `hit` schema is built from them,
plugin.HIGH_SCHEMA), what is measured, the tolerances (2 cm, 3 degrees, 0.15 m/s + 10 %, 10 ms), what counts as
success, who may read what and what happens when a request cannot be met (skilleval/contract.py). Standard library
only."""

from skilleval.contract import SkillContract, Tolerance

DT = 0.01  # control step (s); a command takes effect at the start of a control step
WINDOW_S = 0.10  # the blade's closest pass to pos is searched within +-0.1 s of the contact step


def _vec(doc: str, **kw) -> dict:
    return {"type": "vector", "len": 3, "doc": doc, **kw}


HIT = SkillContract(
    name="hit",
    call="hit(t, pos, normal, vel)",
    args={
        "t": {"type": "number", "min": 0.0, "max": 2.5, "unit": "s",
              "doc": "time from the hit's effect until contact, 0 < t <= 2.5"},
        "pos": _vec("blade centre at contact (m, your frame): |x| <= 2.0, -3.3 <= y <= -0.3, -0.5 <= z <= 1.5",
                    box=[[-2.0, 2.0], [-3.3, -0.3], [-0.5, 1.5]]),
        "normal": _vec("blade face normal at contact (non-zero; pointing at the opponent)", nonzero=True),
        "vel": _vec("blade velocity at contact (m/s), |vel| <= 8", max_norm=8.0),
    },
    returns="one low-level command of this level (game spec actions: {'type': 'traj', 'k0', 'q': rows of 9 targets "
    "[base_x, base_y, q1..q7]} | {'type': 'slew', 'q', 'speed'} | {'type': 'hold'}) or None, taking effect at control "
    "step state['step'] (that is k_eff); the high level's implementation lowers the act to the same traj command. "
    "The base is part of the skill: the implementation moves it (the high level: the stance rule, rcb_tt.stance)",
    measured="the blade centre (site paddle_center), its face normal (the paddle body's +x) and its linear velocity "
    "in the simulator's state at the contact step k_c = k_eff + round(t / 0.01) (as the high level's act: its "
    "reply's n_swing_steps_available); time_err_s = the step of the blade's closest pass to pos within +-0.1 s, "
    "minus k_c (x 10 ms); the case starts from the exact state of one of our reference player's matches (the robot "
    "as the match left it, the ball in flight) and runs to the leg's verdict, step() called every 2 control steps",
    tolerances=(
        Tolerance("pos_err_m", 0.02, text="blade centre within 2 cm of pos at the contact step"),
        Tolerance("normal_err_deg", 3.0, text="face normal within 3 degrees of normal"),
        Tolerance("vel_err", 0.15, rel=0.10, rel_to="speed_req", text="blade velocity within 0.15 m/s + 10 % of |vel|"),
        Tolerance("time_err_s", 0.01, two_sided=True, text="closest pass to pos within 10 ms (one control step)"),
    ),
    must_be_zero=("refused", "robot_net_contact"),
    metrics=("vel_err_rel", "ball_returned", "robot_table_contact", "self_collision_events"),
    feasible="every API-test request comes from our reference player's own matches (L1-L4) on this revision and is "
    "feasible under the real limits: from the case's start state the platform's implementation plans it and its own "
    "rehearsal (the robot alone) delivers it within 15 mm, 2.5 degrees and 0.10 m/s + 8 % (IK residual < 1 mm, no "
    "table contact, the base in time); a request that asked for more paddle speed than the limits allow carries the "
    "velocity scaled the way the platform's skill scales it",
    replaces="a new hit replaces the stroke under way (as the high level's act): plan from the robot's current state "
    "(q, qd, q_target, qd_target, the command in force)",
    notes={
        "frame": "your frame: x to your right, y towards the opponent, z up; table top z = 0",
        "inputs": "t, pos, normal, vel as above; the implementation also gets state (the low level's observe state: "
        "the robot's own joints q, qd, the target in force q_target and its velocity qd_target, the command in force, "
        "base_xy, paddle_pos / paddle_normal, step; no images, no ball coordinates) and spec (game spec's "
        "kinematics, limits, toolkit, skill_contract)",
        "timing": "the command a hit returns takes effect at control step state['step'] (k_eff); contact at "
        "k_eff + round(t / 0.01); a hit with t below the time the robot needs is answered as well as it can be "
        "(no refusal); a new hit replaces the stroke under way; between hits step() may move the robot (every 20 ms). "
        "In the match (the skill in the loop) the call's compute counts: the world runs on while hit computes and "
        "its command takes effect at the first control step after it returns (spec timing); the contact stays at "
        "state['step'] + round(t / 0.01) and the rows of a traj that have passed are skipped",
        "feedback": "high level: the act reply (stroke: ok or what limited it, blade_error_m, normal_error_deg, "
        "speed_scale, the base goal); low level: the robot's own observed state after every step",
        "authority": "the implementation reads only the robot's own state and its commands, never the ball or the "
        "opponent: it executes the paddle state it is asked for and neither predicts nor aims (P2). The high level's "
        "rehearsals roll the robot alone (no ball) on a copy of the simulator; the low level's toolkit gives the same "
        "robot-only model and servo law",
        "failure": "a request outside the ranges: refused (400, nothing changes); a contact time already passed: "
        "'too late', no stroke (high level) / no command; not enough time or speed: the best reachable contact, the "
        "reply says how much (speed_scale, blade_error_m); a low-level command beyond the limits: refused, the "
        "previous command goes on and the hit fails the API test; the skill raising or overrunning its time limit: "
        "no command (counted), after a time-out no further calls in that run",
        "refused": "a command refused by the low level's checks (joint ranges, speed and acceleration limits, "
        "continuity of the first row) fails the hit; so does the robot touching the net (robot_net_contact: a lost "
        "point by the rules). Touching the table is allowed by the rules since revision 9/7 (D4) and is reported "
        "(robot_table_contact), not a failure: the table stops the paddle, which already shows in the tolerances",
        "ball": "the measurement also reports whether the ball went back (ball_returned; not part of success)",
    },
)
CONTRACTS = {"hit": HIT}
