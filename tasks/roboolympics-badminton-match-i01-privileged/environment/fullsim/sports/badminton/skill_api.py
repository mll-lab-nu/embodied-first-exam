"""badminton's skill API (docs/framework_zh.md §6.3; docs/construction_zh.md step 3, P1-P6; skilleval/README.md): the
high level's two skills, `act` (the racket's state at contact) and `toss` (the serve's toss), as SkillContracts.

  high  Agent as Athlete: the act IS the skill; the platform implements it (plugin.RacketLayer: the stroke controller
        sim/bm.py Match.plan_racket, planned on an exact copy of the robot at the act's effect step and lowered to joint
        targets).
  low   Agent as Robotics Engineer: the player implements act(t, pos, normal, vel, *, state, spec) itself from the
        toolkit (seat/toolkit.toml: the robot-only model, the joint-target interface with the real limits, the
        kinematics library, the servo model), at /app/output/skill/act.py; evaluated after the match
        (lowlevel/evaluator.py, tools/skill_eval.py: the API test on hidden requests, the competition test with our
        fixed reference strategy) and, in the skill-in-the-loop mode, called by the platform during the match
        (skilleval/inloop.py, plugin.inloop_layer). `toss` is the same command at both levels (nothing to implement).

This file is the contract's single source: the request ranges (plugin.HIGH_SCHEMA is built from them; tests check them
against the simulator's constants), what the controller reads and may correct, its timing, its feedback and its failure
handling (P6). Standard library only.

Control authority (P2), in one place:
  * the controller reads the robot only (joint and base state, its own previous targets); never the shuttle, the
    opponent or the score (plan_racket: "it uses no shuttle state and does not aim"); its rehearsals run on a
    robot-only twin without the shuttle;
  * it chooses: the base's stance for a forehand at `pos` (a fixed offset to the right of and in front of the base,
    closer in for high and low contacts), an IK solution clear of the robot's own stand and links, a joint-space swing
    within the Panda's limits, the follow-through; it corrects its own tracking lag (rehearsals) and slows the head when
    the time left does not allow the commanded speed;
  * after the follow-through it returns the arm to the ready pose; the base stays where it struck (since the base
    study, revision wallclock-11: no automatic return); where the base waits is the player's (`move`), and an act may
    say where the base stands at contact (`base`, else the forehand stance);
  * it never chooses the contact time, the contact point, the face or the head velocity: those are the player's.
"""

from skilleval.contract import SkillContract, Tolerance

# the act's ranges (= sim/bm.py ACT_X, ACT_Y; plugin.T_MAX_S; tests/test_badminton.py checks them)
ACT_X, ACT_Y, T_MAX_S, VEL_MAX = 2.136, 3.68, 5.0, 8.0
# the toss (= sim/bm.py TOSS_Z, TOSS_REACH, TOSS_H_MAX)
TOSS_Z, TOSS_REACH, TOSS_H_MAX = (0.5, 1.8), 1.0, 0.5

FAILURES = {
    "out of range, non-finite, malformed": "refused (HTTP 400); nothing changes (E1)",
    "sent before the previous act took effect": "refused (HTTP 409) (E3)",
    "the contact time has passed when the act takes effect": "not executed; the stroke under way continues; the reply's "
    "stroke notes say 'too late'",
    "the base cannot reach the stance in time": "the base goes as far as it gets; notes 'could not reach the stance in "
    "time: X m short'",
    "the head speed is beyond the joints in the time left": "the swing is slowed; notes 'head speed limited by the joint "
    "speed limits (xF)'; state.command.vel_rehearsed gives the rehearsed head velocity",
    "the pose is out of reach or not delivered in time": "the nearest IK solution / the rehearsed pose; notes 'pose not "
    "delivered: the rehearsed racket head is X cm off'; state.command.pos_error_rehearsed_m",
    "every candidate swing touches the robot's own stand or links": "the swing with the fewest contact steps; notes "
    "'self-collision: ...'; the contact is physical (the arm is stopped) and recorded (final fields self_collision)",
    "the point ends before the act takes effect": "dropped (notes 'dropped: ...')",
}

ACT = SkillContract(
    name="act",
    call="act(t, pos, normal, vel)",
    args={
        "t": {"type": "number", "min": 0.0, "max": T_MAX_S, "unit": "s",
              "doc": "contact T s after the act takes effect (0 < T <= 5)"},
        "pos": {"type": "vector", "len": 3, "unit": "m",
                "box": [[-ACT_X, ACT_X], [-ACT_Y, -0.3], [0.2, 3.0]],
                "doc": f"racket-head centre at contact: |x| <= {ACT_X:g}, -{ACT_Y:g} <= y <= -0.3, 0.2 <= z <= 3.0"},
        "normal": {"type": "vector", "len": 3, "nonzero": True, "doc": "string-face normal at contact (non-zero)"},
        "vel": {"type": "vector", "len": 3, "unit": "m/s", "max_norm": VEL_MAX,
                "doc": "racket-head velocity at contact, |vel| <= 8"},
        "base": {"type": "vector", "len": 2, "unit": "m", "optional": True,
                 "doc": "optional: where the base stands at contact (your frame; within the base's range); default the "
                        "forehand stance for pos (the stance formula); the base stays there after the stroke"},
    },
    returns="one low-level command of this level, taking effect at control step state['step'] (that is k_eff): "
    "{'type': 'traj', 'q': rows of 9 joint targets [base_x, base_y, q1..q7]} (row i = the target of control step "
    "k_eff + i; after the last row the arm returns by itself to its ready pose and the base stays where it is) | "
    "{'type': 'none'} | None (no command); the high level's implementation lowers the act to the same traj, planned "
    "by the stroke controller on an exact copy of the robot advanced to the effect step",
    measured="the racket head centre (site racket_center), its string-face normal (either face: the contact law reads "
    "the face the head moves towards) and its linear velocity in the match simulator's state at the contact step "
    "k_c = k_eff + round(t / 0.01) (as the high level's act: its reply's k_hit); the API-test case starts from the "
    "exact state of one of our reference player's matches (the robot as the match left it, the shuttle in flight) and "
    "runs to the leg's verdict, step() called every 2 control steps; time_err_s (reported, not a tolerance) = the step "
    "of the head's closest pass to pos within +-0.1 s, minus k_c. The high level's reply reports the same quantities "
    "from its rehearsal (blade_error_m, normal_error_deg, racket_vel_delivered); in play the platform's delivered state "
    "scatters by about 6 mm, 0.8 deg and 3 % (seeded, one stream per robot)",
    tolerances=(
        Tolerance("pos_err_m", 0.02, text="the head centre within 2 cm of pos at the contact step"),
        Tolerance("normal_err_deg", 3.0, text="the face normal within 3 degrees of normal"),
        Tolerance("vel_err_mps", 0.15, rel=0.10, rel_to="vel_norm", text="the head velocity within 0.15 m/s + 10 %"),
    ),
    must_be_zero=("refused",),
    metrics=("vel_err_rel", "time_err_s", "self_collision_steps", "shuttle_returned"),
    feasible="the platform delivers a request within the tolerances when the contact is at least about 0.9 s ahead "
    "from the ready pose, 0.65-1.75 m high, within the base's reach in time and the head speed within about "
    "2.2 t - 0.2 m/s along a forward face; otherwise it does its best and says so (FAILURES). Every API-test request "
    "comes from our reference player's own matches (L1-L3) on this revision and is feasible under the real limits: from "
    "the case's start state the platform's implementation, without its execution scatter, plans it and its own "
    "rehearsal (the robot alone) delivers it within 15 mm, 2.5 degrees and 0.10 m/s + 8 % (IK residual < 2 mm, the "
    "base at its stance in time, no self-collision); a request that asked for more head speed than the limits allow "
    "carries the velocity scaled the way the platform scales it",
    replaces="a new act (or none) replaces the stroke under way from its effect step; the swing restarts from the "
    "moving arm",
    notes={"control_authority": "the controller reads the robot only (joints, base, its own targets), never the "
           "shuttle, the opponent or the score; it chooses the base's forehand stance for pos, an IK solution clear "
           "of the robot's own stand and links, a joint-space swing within the Panda's limits and the follow-through, "
           "corrects its own tracking lag by robot-only rehearsals and slows the head when time is short; after the "
           "follow-through the arm returns to the ready pose and the base stays where it struck (no automatic "
           "return: where to wait is the player's, `move`); contact time, point, face, head velocity and, optionally, "
           "where the base stands (`base`) are the player's",
           "stance": "the base's goal for a contact at pos = (x, y, z) is (x, y) - 0.62 r (1, 1) with r = max(0.30, "
           "0.95 - 0.35 |z - 1.333|) m (a forehand: right of and in front of the base), clipped to the gantry's range; "
           "the reply's stroke.base_goal gives it. So a serve whose contact is at that offset from the base's spot "
           "keeps the base still (it must stay within 5 cm until the serve is hit)",
           "timing": "an act takes effect act.lead_steps control steps after the step at which it arrives (2 at x20); "
           "the plan is made meanwhile from the exact state at that step",
           "feedback": "the reply: effect_step and the stroke notes (stroke, base, speed_scale, blade_error_m, "
           "normal_error_deg, racket_vel_delivered); state.command: contact_in_s, vel_rehearsed, "
           "pos_error_rehearsed_m; last_shots",
           "failures": FAILURES,
           "contact_law": "the shuttle leaves along the face normal at 4 max(0, v_head.n)(1 - 0.3 (r/0.14)^2) + "
           "0.15 max(0, -v_in.n) (spec racket_contact): the player turns the shot it wants into (normal, vel)"},
)

TOSS = SkillContract(
    name="toss",
    call="toss(pos, height)",
    args={
        "pos": {"type": "vector", "len": 3, "unit": "m",
                "doc": f"your serve's toss (docs/conventions/racket_serve_zh.md): the shuttle appears at this point "
                       f"(your frame) when the command takes effect; {TOSS_Z[0]} <= z <= {TOSS_Z[1]}, within "
                       f"{TOSS_REACH} m (horizontally) of your base, y <= -0.5; only the server, once per serve, from "
                       "the step the receiver is ready (state.serve)"},
        "height": {"type": "number", "min": 0.0, "max": TOSS_H_MAX, "unit": "m", "optional": True,
                   "doc": f"how far it rises straight up from pos (0 <= height <= {TOSS_H_MAX}; default 0: released "
                          "from rest)"},
    },
    returns="the low-level toss at the effect step (the same command at both levels)",
    measured="the shuttle appears at pos at the effect step, at rest or rising height (exact; no scatter)",
    tolerances=(),
    must_be_zero=("refused",),
    feasible="every toss within the ranges and the serve's window is executed exactly",
    replaces="once per serve",
    notes={"failures": {"not the server, out of the window, a second toss, out of range": "refused (400 / 409); "
                        "a serve not tossed within 3 s of the receiver being ready is a service fault (undue delay)"}},
)

MOVE = SkillContract(
    name="move",
    call="move(base)",
    args={"base": {"type": "vector", "len": 2, "unit": "m",
                   "doc": "where your base waits (your frame, within the base's range): it goes there once no stroke "
                          "is under way (a stroke under way finishes first; none cancels it); there is no automatic "
                          "return: after a stroke the base stays where it struck until you move it"}},
    returns="the base's waiting point (the same command at both levels; the go-to generator within the base's limits)",
    measured="the base's target reaches the point (exact) within the base's speed and acceleration limits",
    tolerances=(),
    must_be_zero=("refused",),
    feasible="every point within the base's range",
    replaces="a later move or an act's stance replaces the waiting point",
    notes={"serve": "until a serve is delivered both bases must stay within 5 cm of their spots (a move then is a fault)"},
)

CONTRACTS = {"act": ACT, "toss": TOSS, "move": MOVE}
