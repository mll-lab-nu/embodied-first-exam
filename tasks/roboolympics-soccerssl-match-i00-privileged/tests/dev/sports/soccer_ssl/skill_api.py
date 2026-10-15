"""soccer_ssl's skill API (docs/framework_zh.md §6.3; docs/construction_zh.md step 3, P1-P6; skilleval/contract.py):
the high level's three skills `move`, `kick` and `dribble` as SkillContracts, the robot handler's `substitute`
command and the `batch` envelope. Proposal: olympiad_review/screening/soccer_ssl_proposal_zh.md §5.

  high  Agent as Athlete: each command IS the skill; the platform executes it on the robot (sim/world.py
        World.execute -> bodies/ssl_robot Rig: set_base_target / kick / dribble, the shared servo path
        bodies/servo.py PlanarBase). The engineer mode (Agent as Robotics Engineer) is not set this round (proposal
        §5.4): no [modes.low]; the action level `low` is the robot's servo interface only (plugin.LOW_SCHEMA), it has
        no tasks.

This file is the contract's single source (P6): the request ranges (plugin.SCHEMA is built from them; the tests check
them against bodies/ssl_robot/body.toml and sim/field.py), the timing, the feedback, what each controller reads and
may correct, the failure handling. Standard library only: the simulator, the plugin, the checks, the generator and the
built-in players all read it.

Who is commanded (one command = one robot; the `entity` field is the robot's number as a string, "0" .. "4"; robot 0
is the keeper). A team seat (formats `match`, `duel`) commands its five robots, a robot seat (format `team`) its one.

Frames (sim/frames.py): every command and every coordinate of the observation is in YOUR TEAM'S FRAME: metres,
seconds, radians; origin at the field centre; you attack +x (the goal at x = +4.5) in both halves; y to the left when
facing +x; theta counter-clockwise from +x. The camera images are in the WORLD frame (image right = world +x, image up
= world +y); the observation's `frame.attack_sign` s (+1 / -1) maps them: team (x, y) = s (x, y) world, team theta =
world theta (+ pi when s = -1). The teams change ends at half time, so s flips then.

Time: the world runs in control steps of 10 ms (1 ms physics steps). A command takes effect at the first control step
boundary after it arrives (the core applies every ready act at the boundary, then the step runs: "the next 10 ms
control step") and replaces the same robot's earlier command of the same skill (move replaces the robot's move, kick
its armed or pending kick, dribble its bar speed); the three skills are independent channels. One act per (seat,
robot) may be in flight (HTTP 429 otherwise); `batch` sends several robots' commands as one act, all taking effect at
the same boundary (the SSL team AI's per-frame packet; ssl-simulation-protocol RobotControl). `t` (move) is GAME TIME:
the world's clock in seconds (`t_sim` of the state; it runs during stops and freezes only during reviews), not
playing time.

Control authority (P2), in one place:
  * move: the base's controller (bodies/ssl_robot Rig: a bang-bang reference for a timed or moving arrival, the
    library's PlanarBase setpoint generator at the robot's real speed / acceleration / jerk limits, a 1 kHz PD) reads
    its OWN robot only: pose and velocity (odometry), its own previous target. It never reads the ball, another robot,
    a wall or the referee; it does not avoid obstacles (contact is physical; crashing and pushing are the referee's);
    it re-plans every control step from the measured state (it corrects tracking errors, wheel slip and a push);
    it never chooses where, when or how fast to arrive: those are the player's.
  * kick: the kicker reads its OWN break beam (the infrared beam across the dribbler opening, as on the real robot:
    TIGERs 2020 ETDP 2.3) and its capacitor; it fires along the robot's current heading (no direction argument: aim
    by turning the robot), at the commanded speed with the real speed and direction scatter (seeded), only when the
    ball blocks the beam. It never aims, never predicts the ball and never chooses the speed.
  * dribble: the bar's motor runs a speed loop on its own bar speed, saturated at the motor's torque. The grip on the
    ball (contact plus a capped hold force, bodies/ssl_robot README "Dribbler") is part of the robot's physics model,
    not a controller: it acts only on a ball in the robot's own dribbler opening, below the measured release limits.
  * substitute: the robot handler's command (rulebook §5.5.1, §9.2). Not a skill.
  * The stop state's 1.5 m/s limit (rulebook §5.1.1) and the 6.5 m/s ball speed limit (§8.4.2) are the player's
    business: the platform does not limit the robots or the kicks in a stop; the referee judges (proposal §10.6).

Feedback (P6): the act's reply (`took_effect`) carries the robot's number, the skill and its immediate status (below);
later results arrive as the robot's own events in the observation (`events`: kicked, kick_expired, kicker_not_ready,
kick_clipped, base_resync, substituted ...), and its state (`robots`) shows the current target, the planned arrival
(eta), the capacitor, the armed kick, the break beam and the bar speed.

Not provided (and why, proposal §5.1): pass(teammate) / shoot(): results, not actions (P1); receive(ball) /
intercept(): the controller would read and predict the ball (P2); move with obstacle avoidance or move_to_ball: the
controller would read the world (P2).

The scripted opponents and the built-in players use the SAME commands (olympiad_review/screening/
soccer_ssl_interfaces_zh.md §9): a scripted team is an object with act(truth) -> [command, ...] (the act bodies below,
with `entity`), called by the plugin every control step while the world runs, its commands checked against the same
schema (plugin.check_act) and executed through the same World.execute at the same boundary as a player's; it reads
the truth of World.truth_view(team) (team frame, no images) and draws random numbers only from the generator it is
given (core.rng stream "opponent:<team>").
"""

from __future__ import annotations

import math

from skilleval.contract import SkillContract, Tolerance

# ------------------------------------------------------------------------------------- ranges (single source)
# bodies/ssl_robot/body.toml [limits.*] (tests/test_plugin.py checks they are equal)
BASE_SPEED, BASE_ACCEL, YAW_RATE = 3.0, 3.0, 20.0
FLAT_MAX, CHIP_MAX, CHIP_ANGLE_DEG = 8.5, 5.5, 45.0
RPM_MAX = 17000.0
# sim/field.py: the walls' inner faces at |x| = 4.8, |y| = 3.3; a robot's centre stays 0.09 m inside them
WALL_X, WALL_Y, ROBOT_R = 4.8, 3.3, 0.09
REACH_X, REACH_Y = WALL_X - ROBOT_R, WALL_Y - ROBOT_R  # 4.71, 3.21: where a move target is clipped to
X_MAX, Y_MAX = 5.0, 3.5  # the request ranges (beyond them: refused; between REACH and them: clipped)
THETA_MAX = round(2 * math.pi, 6)
T_MAX = 10000.0  # game seconds (a match lasts about 1500 s of game time)
ARMED_MAX = 10.0
ROBOTS_PER_TEAM = 5
BATCH_MAX = ROBOTS_PER_TEAM

MOVE_FAILURES = {
    "out of range, non-finite, malformed, a robot you do not command": "refused (HTTP 400); nothing changes",
    "the robot is off the field (a card, a substitution)": "refused (HTTP 409); `substitute` with to = on brings it "
    "back",
    "the target is beyond the walls (|x| > 4.71 or |y| > 3.21)": "clipped to them; status 'clipped'",
    "t is earlier than the limits allow (or already past)": "executed as fast as the limits allow; status 'late' and "
    "eta = the planned arrival",
    "|v_end| > 3 m/s": "scaled to 3 m/s; status 'clipped'",
    "the robot is pushed or blocked": "it re-plans from where it is every control step (event base_resync when the "
    "setpoint restarts from the measured state); nothing is retried beyond the target",
}
KICK_FAILURES = {
    "out of range, non-finite, malformed": "refused (HTTP 400)",
    "the capacitor holds too little for the speed": "not armed; status 'kicker_not_ready' with wait_s (also an event)",
    "speed above the machine's maximum (chip 5.5 m/s)": "clipped to it; status 'clipped' (event kick_clipped)",
    "armed_for = 0 and no ball in the beam": "the kicker discharges at the next physics step anyway (the energy is "
    "used, as on the real robot); the event kicked says ball = false",
    "armed_for > 0 and no ball arrives in time": "disarmed; event kick_expired",
    "speed = 0": "cancels an armed kick; status 'disarmed'",
    "the kick sends the ball faster than 6.5 m/s (3-D)": "executed: the referee calls the foul (rulebook §8.4.2)",
}

MOVE = SkillContract(
    name="move",
    call="move(x, y, theta, t=None, v_end=None)",
    args={
        "x": {
            "type": "number",
            "min": -X_MAX,
            "max": X_MAX,
            "unit": "m",
            "doc": f"target x of the robot's centre (your frame; clipped to |x| <= {REACH_X:g})",
        },
        "y": {
            "type": "number",
            "min": -Y_MAX,
            "max": Y_MAX,
            "unit": "m",
            "doc": f"target y of the robot's centre (your frame; clipped to |y| <= {REACH_Y:g})",
        },
        "theta": {
            "type": "number",
            "min": -THETA_MAX,
            "max": THETA_MAX,
            "unit": "rad",
            "doc": "target heading (your frame, counter-clockwise from +x; the kicker points along it)",
        },
        "t": {
            "type": "number",
            "min": 0.0,
            "max": T_MAX,
            "unit": "s",
            "default": None,
            "optional": True,
            "doc": "arrival time in GAME time (state.t_sim); omit it: as fast as the limits allow",
        },
        "v_end": {
            "type": "vector",
            "len": 2,
            "min": -BASE_SPEED,
            "max": BASE_SPEED,
            "max_norm": BASE_SPEED,
            "unit": "m/s",
            "default": None,
            "optional": True,
            "doc": "velocity at arrival (your frame; omit it: [0, 0], at rest); after arriving the robot moves "
            "on at it until the next move",
        },
    },
    returns="the robot's base target in the world frame (Rig.set_base_target(x, y, theta, t, v_end)): a time-optimal "
    "bang-bang reference (timed or moving arrival) or the PlanarBase setpoint generator straight to the pose (at "
    "rest, untimed), at the real limits",
    measured="the robot's centre and heading at the planned arrival (the reply's eta) and its velocity there, robot "
    "alone on the field (bodies/tests/test_ssl_robot.py test_base_reaches_goals_within_limits)",
    tolerances=(
        Tolerance("pos_err_m", 0.01, text="the centre within 1 cm of (x, y) once arrived at rest"),
        Tolerance("yaw_err_rad", 0.01, text="the heading within 0.01 rad of theta"),
        Tolerance("arrival_late_s", 0.05, text="a feasible t is met within 50 ms"),
        Tolerance("v_end_err_mps", 0.15, text="the velocity at arrival within 0.15 m/s of v_end"),
    ),
    must_be_zero=("refused",),
    feasible="every target inside the walls is reached; a t at or after the eta of an untimed move to the same "
    "target is met; a v_end is met when the distance allows the speed change at 0.8 x the acceleration limit",
    replaces="a new move replaces the robot's move under way at the boundary: the new plan starts from the setpoint "
    "generator's current state (no jump in velocity)",
    notes={
        "limits": {
            "speed_m_s": BASE_SPEED,
            "accel_m_s2": BASE_ACCEL,
            "braking_m_s2": BASE_ACCEL,
            "jerk_m_s3": 150.0,
            "yaw_rate_rad_s": YAW_RATE,
            "yaw_accel_rad_s2": 50.0,
            "source": "bodies/ssl_robot/body.toml [limits.base] (TIGERs 2026 ETDP 3.2; Sumatra [config])",
        },
        "control_authority": "reads its own robot's pose and velocity only; no ball, no other robot, no walls, no "
        "obstacle avoidance; re-plans every control step from the measured state",
        "feedback": "reply: status ok | late | clipped, eta (game time of the planned arrival), target (your frame, "
        "after clipping); state.robots[N].target / eta; events base_resync",
        "failures": MOVE_FAILURES,
        "stop_state": "the platform does not slow the robots in a stop: keep them below 1.5 m/s yourself (the "
        "referee counts a foul after a 2 s grace, rulebook §8.4.3)",
    },
)

KICK = SkillContract(
    name="kick",
    call="kick(speed, mode='flat', armed_for=0)",
    args={
        "speed": {
            "type": "number",
            "min": 0.0,
            "max": FLAT_MAX,
            "unit": "m/s",
            "doc": f"ball speed relative to the robot: flat = horizontal (<= {FLAT_MAX:g}), chip = 3-D at "
            f"{CHIP_ANGLE_DEG:g} deg (<= {CHIP_MAX:g}); 0 cancels an armed kick",
        },
        "mode": {"type": "enum", "values": ["flat", "chip"], "default": "flat", "doc": "flat or chip kick"},
        "armed_for": {
            "type": "number",
            "min": 0.0,
            "max": ARMED_MAX,
            "unit": "s",
            "default": 0.0,
            "doc": "0: discharge now (effective only with the ball in the beam); > 0: armed, fires the "
            "moment the ball blocks the break beam within this many seconds",
        },
    },
    returns="the kicker's command (Rig.kick(speed, mode, armed_for)): an impulse on the ball when the break beam is "
    "blocked, along the robot's heading",
    measured="the ball's velocity right after the discharge relative to the robot",
    tolerances=(
        Tolerance(
            "speed_err_rel",
            0.09,
            text="within 3 sigma of the speed scatter (sigma = 3.0 % of the speed, " "ZJUNlict 2024)",
        ),
        Tolerance("dir_err_deg", 3.0, text="within 3 sigma of the direction scatter (sigma = 1 deg, ESTIMATE)"),
    ),
    must_be_zero=("refused",),
    feasible="every kick with the ball in the beam and a charged capacitor (a kick at v needs (v / v_max)^2 of the "
    "full charge and uses 25 % x (v / v_max)^2; full in 2 s, refilled 0.5 s after a maximum kick)",
    replaces="a new kick replaces an armed or pending one",
    notes={
        "limits": {
            "flat_speed_max_m_s": FLAT_MAX,
            "chip_speed_max_m_s": CHIP_MAX,
            "chip_angle_deg": CHIP_ANGLE_DEG,
            "speed_sigma_rel": 0.03,
            "direction_sigma_deg": 1.0,
            "charge_full_s": 2.0,
            "recharge_after_max_s": 0.5,
            "source": "bodies/ssl_robot/body.toml [limits.kicker] (TIGERs 2020 ETDP; ZJUNlict 2024 TDP)",
        },
        "control_authority": "reads its own break beam and capacitor only; fires along the robot's heading; no "
        "aiming, no ball prediction",
        "feedback": "reply: status ok | clipped | kicker_not_ready (wait_s) | disarmed; events kicked (t, mode, "
        "speed_cmd, ball: whether the ball was in the beam), kick_expired, kicker_not_ready, kick_clipped; "
        "state.robots[N]: kicker_charge, kicker_wait_max_s, kicker_armed, ball_in_beam",
        "failures": KICK_FAILURES,
        "rules": "the ball must not leave a robot faster than 6.5 m/s (3-D): a non-stopping foul, and a goal within "
        "2 s after it does not count; a chipped ball that was higher than 0.15 m after your last touch does not "
        "score (rulebook §7, §8.4.2)",
    },
)

DRIBBLE = SkillContract(
    name="dribble",
    call="dribble(rpm)",
    args={
        "rpm": {
            "type": "number",
            "min": 0.0,
            "max": RPM_MAX,
            "unit": "rpm",
            "doc": "the dribbling bar's speed setpoint (backspin on the ball); 0 = off",
        }
    },
    returns="the bar motor's speed setpoint (Rig.dribble(rpm))",
    measured="the bar's speed (state.robots[N].dribbler_rpm) after the motor's spin-up (about 0.04 s to 17000 rpm "
    "unloaded; a held ball slows it: the loop is saturated at the motor's torque)",
    tolerances=(Tolerance("rpm_err_rel", 0.05, text="unloaded, within 5 % of rpm after the spin-up"),),
    must_be_zero=("refused",),
    feasible="every setpoint in range (17000 rpm is the motor's rated speed, gear 1:1)",
    replaces="a new speed replaces the previous one",
    notes={
        "limits": {
            "speed_max_rpm": RPM_MAX,
            "torque_max_nm": 0.031,
            "spinup_s": 0.04,
            "with_ball": "accelerating at 3 m/s^2 with the ball, a robot loses it at about 2.3 m/s backwards (up "
            "to about 2.8 m/s with the bar above 8000 rpm), 2.6 m/s sideways and 9.3 rad/s turning (ZJUNlict's "
            "v2023 robot, 2024 TDP table 1; deviation S16: contact + adhesion capped at 0.5 N); receives balls up "
            "to about 4-5 m/s; a push of about 0.75 N takes the held ball",
            "source": "bodies/ssl_robot/body.toml [limits.dribbler], [dribbler_assist] and README",
        },
        "control_authority": "the bar's speed loop reads its own bar speed only; receiving, dribbling and turning "
        "with the ball are move + dribble, composed by the player",
        "feedback": "reply: status ok | clipped; state.robots[N]: dribbler_rpm, dribbler_target_rpm, ball_in_beam",
        "rules": "dribbling: the ball may not be carried more than 1 m from where the contact began (rulebook "
        "§8.4.1.8); two robots of a team within 0.15 m of the ball for 1 s is ball holding (S1)",
    },
)

CONTRACTS = {"move": MOVE, "kick": KICK, "dribble": DRIBBLE}

# ------------------------------------------------------------------------------------- the robot handler (no skill)
SUBSTITUTE = {
    "call": "substitute(to)",
    "args": {
        "to": {
            "type": "enum",
            "values": ["off", "on"],
            "doc": "off: take the robot off the field; on: put an off-field robot back on",
        }
    },
    "rules": "rulebook §5.5.1, §9.2, deviation S11. OFF: while your team has more robots on the field than it is "
    "allowed (within 10 s after a yellow or red card) any of your robots may be named and is taken off at the next "
    "control step; otherwise only a robot in your substitution area (at least partly in the field margin within 1 m "
    "of the halfway line) with the ball at least 0.5 m away. If you name none within 10 s of a card, the referee "
    "takes one off (the card's last offender, else your highest-numbered field robot) and play goes on with a force "
    "start. ON: when your team has fewer robots on the field than allowed (a card expired) and it is not the "
    "shoot-out, the robot enters at rest in the field margin of its own half next to the halfway line.",
    "feedback": "reply: status ok | not_in_substitution_area | too_many_robots | already_on_field | "
    "already_off_field | shootout; event ROBOT_SUBSTITUTED_OUT / ROBOT_SUBSTITUTED_IN",
}

BATCH = {
    "call": "batch(commands)",
    "args": {
        "commands": {
            "type": "list",
            "max_items": BATCH_MAX,
            "doc": "up to 5 commands (move / kick / dribble / substitute), each with its own entity; "
            "every robot at most once per skill",
        }
    },
    "rules": "every command is checked as if sent alone; one bad command refuses the whole batch (HTTP 400 / 409); "
    "all take effect at the same boundary; the reply lists each command's status in order",
}


def describe() -> dict:
    """The skill API as data (/spec skill_contract)."""
    out = {name: c.describe() for name, c in CONTRACTS.items()}
    out["substitute"] = dict(SUBSTITUTE)
    out["batch"] = dict(BATCH)
    out["entity"] = "the robot's number as a string, '0'-'4' (0 = keeper); one act per robot in flight"
    out["frame"] = (
        "your team's frame (you attack +x); the images are world-frame: team (x, y) = attack_sign (x, y) " "world"
    )
    out["time"] = "a command takes effect at the next 10 ms control step boundary; t is game time (state.t_sim)"
    return out
