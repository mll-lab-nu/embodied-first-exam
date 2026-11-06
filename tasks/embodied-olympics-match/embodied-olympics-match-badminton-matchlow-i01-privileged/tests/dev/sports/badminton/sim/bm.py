"""Core of the robot badminton match service (interactive mode): first to 5 (two-point lead from 4-4, at most 7) against a scripted opponent.

World (metres, seconds): floor z = 0, court long axis y, net = the plane y = 0 with its top at 1.524 m. The robot's
half is y < 0, the opponent's y > 0. Since revision wallclock-8 / duel-10 the court is the BWF court x COURT_SCALE (0.4):
singles court |x| <= 1.036, |y| <= 2.68 (the net keeps its BWF height; see COURT_SCALE).

Robot: a Franka Panda arm on a 1.0 m pedestal whose base rides an x-y gantry (2 prismatic joints; Festo EGC-185-TB-KF:
<= 5 m/s, <= 50 m/s^2, 2500 N), holding a badminton racket (head centre 0.56 m beyond the flange). One action = 9
absolute joint targets [base_x, base_y, q1..q7] held for 10 ms; target steps are limited to the joint speed limits.
At 1 ms the base follows its targets by PD + bias compensation within the feed force; the arm follows them through
the real Panda's limits (Phys.servo: setpoint generator for velocity / acceleration / jerk, inertia and base-coupling
feed-forward, PD, bias compensation, torque size and rate limits; bodies/franka_panda, bodies/limits.py).

Shuttlecock (not a MuJoCo body; integrated here at 1 ms, semi-implicit Euler, pure Python floats, deterministic):
a point mass under gravity and quadratic drag, dv/dt = g - K |v| v with K = g / V_TERM^2, V_TERM = 6.8 m/s (the
measured terminal speed of a feather shuttle). A real shuttle flips to fly cork first within a few centimetres of a
hit; a point mass has no orientation, it is drawn cork first along its velocity. No bounce: when the shuttle reaches
the floor (z <= 0) the rally is over.

Racket-shuttle contact (a model, not MuJoCo contact): at every 1 ms step the shuttle's centre is tested against the
racket's string plane; when it crosses the plane within R_HEAD of the head centre, the shuttle leaves along the face
normal (the side facing the relative motion) at
    speed = RACKET_GAIN * (racket-head speed along the normal) * (1 - OFFCENTRE_LOSS (r / R_HEAD)^2)
            + E_SHUTTLE * (incoming speed into the face)
RACKET_GAIN = 4 (revision wallclock-8; was 20): a real racket sends the shuttle at about 1.5 x the head speed; 4 lets
the Panda's best swing stand for a real fast badminton arm's (D9). One hit per shot.

Point flow (all inside Match.step() and the player's commands, so a recorded command sequence replays the whole match
bit-exactly). You serve the first point; then the winner of the last rally serves (BWF Law 10.3). Both players stand
at their spots in their service courts (serve_spot, diagonally opposite) before every serve:
  ready    READY_STEPS; the server holds the shuttle.
  serve    the opponent's serve: high and deep, or short (a seeded choice per point, by level), hit at 1.05 m
           upwards into your diagonal service court. Your serve (leg kind "our_serve"): within SERVE_WINDOW_STEPS you
           toss the shuttle (toss(), the `toss` command) and hit it below SERVE_MAX_Z, upwards; then it flies
           to the opponent like any of your shots (it must land in the opponent's diagonal service court).
  our leg  the shuttle comes to us; the model decides the shot (live code: swing / adjust decision points); the
           robot hits it or not. Our shot is good if the shuttle crosses the net above its top and would land in the
           opponent's court. The shuttle landing in our court, the net, out = the opponent's point.
  opp leg  the opponent (below) returns it (a new "our leg" starts at its hit) or cannot reach it (our point when it
           lands in); a shot that would land out it leaves (our fault).

The opponent (LEVELS): a kinematic player on its half, at home (0, 3.8) between rallies. `reaction_s` after our hit it
predicts the flight perfectly and moves in a straight line towards the best interception point at `chase` m/s; after
its own shots it walks back home at `recover` m/s. For every point of the flight in its hitting envelope (its half,
height 0.1-2.7 m) it evaluates
    slack    = time - max(0, distance - reach) / chase - swing        (revision wallclock-10: its arm needs `swing` s)
    pressure = max(max(0, window - slack) / window, (shuttle speed there - SPEED_FREE) / (max_speed - SPEED_FREE))
takes the shuttle at the earliest point whose pressure is within 0.05 of the minimum, and there, deterministically:
pressure > 1 -> it misses (our point); > PRESSURE_WEAK -> a weak lift to the middle of our court; < PRESSURE_PASSIVE ->
it attacks (a smash from above 1.9 m, else a tight drop or a fast push to a corner, at its widest); otherwise a
normal return (a seeded clear / drop / drive within the level's width and pace). It sets the shuttle's velocity (an
impulse; its racket is drawn only) so that the shuttle lands at its target, clears the net by >= 15 cm, and our robot
can reach the flight from where it stands; an unreachable shot moves towards the centre and becomes gentler.
Our strokes scatter: the delivered racket state is perturbed (RACKET_SCATTER, a seeded draw per act).

The player's execution scatter has its own seeded stream, scatter_rng(seed, kind, stream, n) = default_rng([seed,
SCATTER_TAG, kind, stream, n]) (n = the player's act ordinal): no other draw of the match starts with SCATTER_TAG (the
opponent's serve choice [seed, 11, n] and return choice [seed, point, leg]), so it is independent of them (until
revision wallclock-6 the scatter drew [seed, 13, n], which coincided with the opponent's draws of point 13 / 11).
In the duel (bduel.Side) each robot has its own stream: 1 for the first server, 2 for the other.
"""
from __future__ import annotations

import copy as _copy
import hashlib
import io
import json
import math
import os
import sys
from collections import deque
from pathlib import Path

import numpy as np

import mujoco as mj

HERE = Path(__file__).resolve().parent
_ROOT = HERE.parent.parent               # the task's sim/ (bodies/ next to sport/); sports/ in a checkout
sys.path.insert(0, str(_ROOT if (_ROOT / "bodies").is_dir() else _ROOT.parent))
from bodies import limits as AL  # noqa: E402
from bodies import selfcollision as SC  # noqa: E402  (the arm's self-collision record, bodies/README.md §4.1)
SCENE = Path(os.environ.get("RCB_BM_SCENE", HERE / "scene" / "bm_scene.xml"))

CONTROL_DT, SUBSTEPS, PHYS_DT = 0.01, 10, 0.001
GRAV, V_TERM = 9.81, 6.8
K_DRAG = GRAV / V_TERM ** 2
# The court (revision wallclock-8 / duel-10, user decision 2026-10-08: real physics, a smaller court). With real-robot
# limits the shuttle leaves the racket at <= about 18 m/s (RACKET_GAIN below), and the real drag (V_TERM) then carries
# it at most about 7.5 m: the regulation court (13.40 m, a clear needs 40-50 m/s) cannot be played. So the court's
# horizontal lines are those of a smaller court (COURT_SCALE x every BWF length, D8); the net keeps its BWF height:
# the robot is human-sized (its racket meets shuttles 0.4-2.5 m high), only its shuttle speed is not.
COURT_SCALE = 0.4
NET_TOP = 1.524                                   # BWF Law 1.10: net top 1.524 m at the centre (unchanged)
COURT_X, COURT_Y = 2.59 * COURT_SCALE, 6.70 * COURT_SCALE      # singles side line, back line (BWF 5.18 x 13.40 m)
POST_X = 3.05 * COURT_SCALE                       # the posts on the doubles side lines (BWF 6.10 m apart)
SHORT_SERVICE_Y = 1.98 * COURT_SCALE              # the short service line (BWF 1.98 m from the net)
# The racket contact law's gain (real physics, D9): a real racket sends the shuttle at about 1.5 x the head speed
# (string bed); the Panda's head reaches about 4.4 m/s where a real fast badminton arm (ANYmal + DynaArm, 2025)
# swings 10-12 m/s, so gain 4 lets the Panda's best swing give that arm's shuttle speed (<= about 18 m/s).
R_HEAD, RACKET_GAIN, E_SHUTTLE, OFFCENTRE_LOSS = 0.14, 4.0, 0.15, 0.3
ARM_VEL = np.array([2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61])
# The base is a real gantry (D4): Festo EGC-185-TB-KF toothed-belt axes (part 556817): <= 5 m/s, <= 50 m/s^2, feed
# force 2500 N; a jerk limit of 25 x the acceleration (1250 m/s^3). The high-level controller's go-to generator holds
# the speed on the norm (combined, <= BASE_VMAX); a low-level traj is refused beyond these limits.
BASE_VMAX, BASE_AMAX, BASE_JMAX, BASE_FORCE = 5.0, 50.0, 1250.0, 2500.0
BASE_AXIS_AMAX = np.array([BASE_AMAX, BASE_AMAX])          # per axis (x: the robot's left-right, y: forward)
VEL_LIMIT = np.r_[BASE_VMAX, BASE_VMAX, ARM_VEL]
# Candidate bases (the screening's base study, docs/screening/badminton.md): real machines and their published limits
# (speed m/s; acceleration m/s^2, per axis x (left-right), y (forward) where they differ; jerk 25 x the acceleration
# where none is published, as for the EGC). set_base(name) installs one before the plugin is imported.
BASES = {
    "festo_egc": dict(vmax=5.0, amax=(50.0, 50.0), force=2500.0,
                      source="Festo EGC-185-TB-KF toothed-belt axis, part 556817: 5 m/s, 50 m/s^2, 2500 N (datasheet)"),
    "tt_gantry_2ms": dict(vmax=2.0, amax=(10.0, 10.0), force=2500.0,
                          source="the robotic table tennis gantry (Festo 2-DOF linear axes, 'up to 2 m/s in both axes', "
                                 "arXiv 2309.03315); acceleration not published: ESTIMATE 10 m/s^2"),
    "festo_egc_bs": dict(vmax=2.0, amax=(15.0, 15.0), force=3000.0, x_half=1.5,
                         source="Festo EGC-185-BS-KF-40P ball-screw axis (spindle axes EGC-BS-KF, technical data: size "
                                "185, pitch 40 mm, speed 2.0 m/s, max. acceleration 15 m/s^2, feed force 3000 N, "
                                "working stroke up to 3000 mm; speed stroke-dependent)"),
    "rby1_base": dict(vmax=1.5, amax=(2.0, 2.0), force=2500.0,
                      source="Rainbow Robotics RB-Y1 mobile base: 1.5 m/s (datasheet, bodies/wheeled_humanoid S1); "
                             "acceleration DERIVED 2.0 m/s^2 (half the tip-over limit, bodies/wheeled_humanoid)"),
    "r1pro_base": dict(vmax=1.5, amax=(1.0, 2.5), force=2500.0,
                       source="Galaxea R1 Pro chassis: vx, vy within 1.5 m/s, accelerations 2.5 (forward) / 1.0 (left) "
                              "m/s^2 (bodies/galaxea_r1pro S5)"),
    "ridgeback": dict(vmax=1.1, amax=(1.0, 1.0), force=2500.0,
                      source="Clearpath Ridgeback omnidirectional base: 1.1 m/s (Clearpath user manual, system "
                             "specifications); acceleration not published: ESTIMATE 1.0 m/s^2"),
}
BASE_NAME = "festo_egc_bs"                  # the base study's choice (installed below, set_base)
# The arm is a Franka Panda held to the manufacturer's limits (D9; bodies/franka_panda/body.toml, bodies/limits.py, as
# fencing-3): the joint targets of every 10 ms step go through the robot's 1 kHz setpoint generator (JerkLimiter:
# velocity, acceleration and jerk limits, the jerk also capped by what the torque-rate limit allows at the pose), an
# inertia feed-forward + PD + gravity/Coriolis compensation, and the torque stage (TorqueRateLimiter: 87 / 12 N m,
# 1000 N m/s). The base's targets stay within the gantry's limits (the go-to generator; a low-level traj is checked).
ARM = AL.load("franka_panda")
READY_SPEED = 0.9               # the arm returns to its ready pose at 90 % of its speed limits (wallclock-8; before 60 %)
ACC_SHARE = 0.90                # the swing's duration keeps the planned joint accelerations within 90 % of the limits
COUPLING_FF = True
RESYNC = 0.02                   # rad: a joint farther than this from its setpoint pulls the setpoint along (no wind-up)
# The joint-velocity rule (revision wallclock-12 / duel-14; the user's decision of 2026-10-13, the rule table tennis took
# on 10-12, the Embodied Olympics screening notes): the setpoints never exceed the velocity limits, but the
# physical joints overshoot a setpoint that runs at the limit (PD tracking, the torque-rate limit, the base's
# acceleration through the arm-base coupling), and a real Franka answers a joint faster than its limit with its
# velocity reflex (libfranka joint_velocity_violation). So (1) the arm's setpoint generator and the stroke controller
# run at VMARGIN of the velocity limits, and (2) a physical arm joint faster than REFLEX x its limit triggers the reflex:
# the robot stops - the targets are ignored, the arm's setpoints brake to rest at the pose of the trigger and the
# gantry brakes to rest within its own limits - for REFLEX_RECOVER_S, then it resumes from rest and catches up with its
# targets within the limits (the arm through its setpoint generator, the gantry through a setpoint generator at its
# limits) until the referee next puts the robot at its spot. Phys.n_reflex counts them (results: velocity_reflexes).
VMARGIN = 0.9
REFLEX = 1.05
REFLEX_RECOVER_S = 1.0
ARM_OP = __import__("dataclasses").replace(ARM, vel=ARM.vel * VMARGIN)   # what the setpoint generator runs at
ARM_VEL_OP = ARM_VEL * VMARGIN                                          # what the stroke controller plans with
KP = np.array([4e4, 4e4, 2400.0, 2400.0, 2400.0, 2400.0, 1000.0, 600.0, 200.0])
KD = np.array([3e3, 3e3, 100.0, 100.0, 100.0, 100.0, 30.0, 20.0, 6.0])
JOINTS = ["base_x", "base_y"] + [f"joint{i}" for i in range(1, 8)]
SPOT_X, SPOT_Y = 0.3 * COURT_SCALE, -4.0 * COURT_SCALE        # the serve spot (D4), the BWF court's x 0.3, y 4.0 scaled
HOME = np.array([0.0, SPOT_Y])               # the robot's base between shots
PED_H = 1.0                                  # link0 height on the pedestal; shoulder at PED_H + 0.333
Q0_ARM = np.array([0.0, -0.3, 0.0, -1.9, 0.0, 1.9, 0.785])   # ready pose (refined at import by IK, see _ready_pose)
# the gantry's travel: 0.95 m beyond the side lines, 0.85 m behind the back line, up to 0.5 m from the net
BASE_LO, BASE_HI = np.array([-(COURT_X + 0.95), -(COURT_Y + 0.85)]), np.array([COURT_X + 0.95, -0.5])
# the act's range of racket-head positions at contact (plugin; a little beyond the base's reach)
ACT_X, ACT_Y = round(COURT_X + 1.1, 3), round(COURT_Y + 1.0, 3)

WIN_POINTS = 11                 # both formats (revision wallclock-10 / duel-12, the screening: a first program rarely
CAP_POINTS = 15                 # scores in a game to 5; a game to 11 leaves it ten reviews): from 10-10 by 2, at most 15
SINGLE_WIN_POINTS, SINGLE_CAP_POINTS = WIN_POINTS, CAP_POINTS
MAX_HITS = 400                  # (300 before wallclock-11 / duel-13) cap on hits in the match (both sides): the match ends after that point; the leader wins,
MAX_POINTS = 40                 # if level the winner of the last point (no draws; the same in single and duel)
READY_STEPS = 100               # 1.0 s between points
LEG_STEPS = 600                 # safety: 6 s after a serve or hit without a decision -> the player to hit loses
CAM_EVERY = 2                   # 50 Hz camera snapshots
SWING_AFTER = 20                # first decision point: 0.2 s after the shuttle was played (serve or opponent's hit)
ADJUST_BEFORE = 30              # second decision point: 0.3 s before the planned contact
OPP_HOME = np.array([0.0, 3.8 * COURT_SCALE])
OPP_Z = (0.10, 2.70)            # the opponent's hitting envelope (height)
ANTICIPATE_N = 4                # the opponent's memory of your shots' landing points (LEVELS anticipate)
ANTICIPATE_BOX = (np.array([-0.8, 0.6]), np.array([0.8, 2.3]))   # where it may wait (its frame: its half y > 0)
READ_N, READ_AGREE = 6, 4       # LEVELS read: of your last 5 changes of side, 4 alike (all switches or all stays) are
READ_SIDE_X, READ_SHORT_Y = 0.25, 1.4   # a habit it reads; a side is |x| > 0.25 m; short is closer than 1.4 m to the net
READ_SPOT = 0.4                 # or your last 3 shots all landed within this of their mean (the same spot)
READ_HIT = 0.5                  # a shot landing within this of the read spot finds its stroke prepared
REACH_T, REACH_KEEP, REACH_Z = 1.05, 0.95, (0.7, 1.7)   # the opponent's shots leave you a contact this late, this
                                                        # long after your base arrives, this high (Match._reachable)
SPEED_FREE = 8.0                # the opponent takes shuttles arriving at up to this speed without pressure
PRESSURE_WEAK, PRESSURE_PASSIVE = 0.75, 0.35

LEVELS = {   # defence: reaction, recover (speed back to where it waits), follow (s its base stays put after its own
             # stroke), reach (its base gets within this of the shuttle), swing (the arm's time to strike once there),
             # block (s of arm time that still give a weak block), window (less slack than this is pressure);
             # placement: anticipate (waits this share of the way towards the mean of your last 4 landings), read
             # (reads a habit of yours and moves this share of the way to its prediction at full speed), open_side
             # (share of its shots to the side away from your base), lob (share of returns lifted over a base standing
             # within 1.2 m of the net), reach_keep (its shots leave a robot waiting mid-court this many s), kill (share
             # of its attacks played without that guarantee); attack: max_speed (faster arrivals press it), width, pace
             # (smash speed); serve: share of high serves, |x| range of the target, depth range of a short serve.
             # Revision wallclock-11 (docs/screening/badminton.md): the base study and the habit-reading opponent;
             # level 1 = reaction 0.30 s, reach 0.85 m, mild attacks, kill 0.2; 2 = as 1 with level 2's attacks,
             # kill 0.5 and a 0.25 s reach margin; 3 = reaction 0.20 s, reach 0.9 m, kill 0.9 and a fast recovery
             # (2 m/s, its base's top speed). Revision wallclock-12 (the joint-velocity rule made level 2 easier for
             # the reference, 6/20 -> 17/20): level 2's reaction 0.25 s (was 0.30 s).
    1: dict(reaction_s=0.30, chase=None, recover=0.6, follow=0.35, anticipate=0.7, read=0.9, open_side=0.7, lob=0.7,
            reach_keep=0.45, kill=0.2, reach=0.85, swing=0.55, block=0.45, window=0.3, max_speed=15.0, width=0.7,
            pace=15.0, min_t=0.0, seed=101, serve_high=0.7, serve_x=(0.2, 0.8), serve_short_y=(-1.25, -1.4)),
    2: dict(reaction_s=0.25, chase=None, recover=0.6, follow=0.35, anticipate=0.7, read=0.9, open_side=0.7, lob=0.7,
            reach_keep=0.25, kill=0.5, reach=0.85, swing=0.55, block=0.45, window=0.3, max_speed=17.0, width=0.95,
            pace=17.0, min_t=0.0, seed=202, serve_high=0.5, serve_x=(0.12, 1.1), serve_short_y=(-1.1, -1.25)),
    3: dict(reaction_s=0.20, chase=None, recover=2.0, follow=0.35, anticipate=0.7, read=0.9, open_side=0.7, lob=0.7,
            reach_keep=0.25, kill=0.9, reach=0.9, swing=0.55, block=0.45, window=0.3, max_speed=17.0, width=0.95,
            pace=17.0, min_t=0.0, seed=303, serve_high=0.5, serve_x=(0.12, 1.1), serve_short_y=(-1.1, -1.25)),
}

# The players' serve (BWF Laws 9-10; 2026-10-07). Before every serve both robots are put in their service courts at
# their spot (serve_spot: x = +SPOT_X in the right court, -SPOT_X in the left one; own frame), at rest in the ready
# pose; the spot is the robot's home (the ready target's base goal) for the whole point. READY_STEPS after play
# resumes the receiver is ready (Law 9.4) and the server may toss the shuttle (docs/conventions/racket_serve_zh.md):
# it appears at a point the server chooses, within TOSS_REACH (horizontally) of its base and TOSS_Z high, and is
# released from rest (height 0) or projected straight up to rise at most TOSS_H_MAX (the robot has no free hand: the
# toss stands for the server's hand letting go of the shuttle, Law 9.1.5: no spin), within SERVE_WINDOW_STEPS (else a
# fault: undue delay, Law 9.1.1; every one is a fault, never a disqualification). Then the server must hit it (a miss is a fault, Law 9.1.8) below SERVE_MAX_Z (Law 9.1.6) and upwards (Law
# 9.1), over the net into the receiver's diagonal service court (Laws 9.1, 10.1). Both bases stay within BASE_TOL of
# their spots until the serve is delivered (Law 9.1.4; both moving: a let, Law 14.2.2). The rally winner serves next
# (Law 10.3).
TOSS_REACH, TOSS_Z, TOSS_H_MAX = 1.0, (0.5, 1.8), 0.5
SERVE_MAX_Z = 1.15
SERVE_WINDOW_STEPS = 300                     # 3 s after the receiver is ready
BASE_TOL = 0.05


def serve_spot(right: bool) -> np.ndarray:
    """Where both robots stand before a serve (own frame): in their right service courts when the server's score is
    even (BWF 10.1), else in their left ones."""
    return np.array([SPOT_X if right else -SPOT_X, SPOT_Y])


def toss_problem(p, h, base) -> str | None:
    """Why a toss (point p in the own frame, height h) is not allowed for a robot whose base is at `base`, or None."""
    p = np.asarray(p, float)
    if p.shape != (3,) or not np.all(np.isfinite(p)):
        return "the toss point must be 3 finite numbers"
    if not (isinstance(h, (int, float)) and math.isfinite(h) and 0.0 <= h <= TOSS_H_MAX):
        return f"the toss height must be 0-{TOSS_H_MAX} m (0: released from rest)"
    if not TOSS_Z[0] <= p[2] <= TOSS_Z[1]:
        return f"the toss point must be {TOSS_Z[0]}-{TOSS_Z[1]} m high"
    d = float(np.hypot(p[0] - base[0], p[1] - base[1]))
    if d > TOSS_REACH:
        return f"the toss point must be within {TOSS_REACH} m (horizontally) of your base; it is {d:.2f} m away"
    if p[1] > -0.5:
        return "the toss point must be on your half, y <= -0.5"
    return None


def toss_vz(h) -> float:
    """The upward speed that makes a shuttle rise h metres under gravity and quadratic drag (exact for the continuous
    model: h = V_TERM^2 / (2 g) ln(1 + vz^2 / V_TERM^2))."""
    return float(V_TERM * math.sqrt(math.expm1(2.0 * GRAV * float(h) / V_TERM ** 2)))

# launch-angle families (deg) of the opponent's shots, tried in order; max launch speed (m/s)
SHOT_THETAS = {"clear": (50, 45, 55, 40, 60, 35, 65, 70, 75), "lift": (66, 62, 70, 58, 52), "drop": (5, 0, 10, 15, -5, 20, 25, 30),
               "drive": (6, 2, 10, 14, -2, 18), "smash": (-14, -10, -18, -6, -22, -2), "push": (28, 32, 24, 36, 20),
               "serve_high": (55, 50, 60, 45), "serve_short": (22, 26, 18, 30, 34)}
# the scripted opponent's shots leave its (drawn) racket at most at the speed a racket of gain 4 gives (SHUTTLE_VMAX)
SHUTTLE_VMAX = 18.0
SHOT_VMAX = {"clear": 18.0, "lift": 18.0, "drop": 12.0, "drive": 16.0, "smash": 18.0, "push": 16.0,
             "serve_high": 18.0, "serve_short": 10.0}


# ---------------------------------------------------------------------- shuttle physics
def sh_step(p, v):
    """One 1 ms step of the shuttle (python floats)."""
    vx, vy, vz = v
    c = K_DRAG * math.sqrt(vx * vx + vy * vy + vz * vz) * PHYS_DT
    vx -= c * vx
    vy -= c * vy
    vz -= GRAV * PHYS_DT + c * vz
    return (p[0] + vx * PHYS_DT, p[1] + vy * PHYS_DT, p[2] + vz * PHYS_DT), (vx, vy, vz)


def predict(p, v, n_max=6000):
    """Shuttle-only flight from (p, v): arrays P, V (N, 3) after 1..N steps of 1 ms, until the floor (inclusive) or
    the net (the step at which it crossed y = 0 below the net top, inclusive)."""
    p = tuple(float(x) for x in p); v = tuple(float(x) for x in v)
    P, V = [], []
    for _ in range(n_max):
        p1, v1 = sh_step(p, v)
        if (p[1] > 0) != (p1[1] > 0) and p[1] != p1[1]:
            f = p[1] / (p[1] - p1[1])
            z = p[2] + f * (p1[2] - p[2]); x = p[0] + f * (p1[0] - p[0])
            if z < NET_TOP and abs(x) <= POST_X:
                P.append(p1); V.append(v1)
                break
        P.append(p1); V.append(v1)
        p, v = p1, v1
        if p[2] <= 0.0:
            break
    return np.array(P), np.array(V)


def flight_table(p0, heading, thetas_deg, speeds, dt=0.002, t_max=4.0):
    """Vectorised planar flights from p0 along `heading` (unit xy) for every (theta, speed): horizontal range at the
    floor, height when crossing the net plane y = 0 (nan if it never does), flight time. Solver only (2 ms steps);
    the real flight is the 1 ms 3-D integration."""
    th = np.deg2rad(np.asarray(thetas_deg, float))[:, None]
    sp = np.asarray(speeds, float)[None, :]
    vh = (np.cos(th) * sp).ravel(); vz = (np.sin(th) * sp).ravel()
    n = vh.size
    h = np.zeros(n); z = np.full(n, float(p0[2]))
    s_net = (-p0[1] / heading[1]) if abs(heading[1]) > 1e-9 else np.inf
    rng_ = np.full(n, np.nan); znet = np.full(n, np.nan); tf = np.full(n, np.nan)
    alive = np.ones(n, bool)
    for i in range(int(t_max / dt)):
        s = np.sqrt(vh * vh + vz * vz)
        c = K_DRAG * s * dt
        vh = vh - c * vh; vz = vz - GRAV * dt - c * vz
        h1 = h + vh * dt; z1 = z + vz * dt
        cross = alive & (h < s_net) & (h1 >= s_net)
        if cross.any():
            f = (s_net - h[cross]) / (h1[cross] - h[cross])
            znet[cross] = z[cross] + f * (z1[cross] - z[cross])
        land = alive & (z1 <= 0.0)
        if land.any():
            f = z[land] / (z[land] - z1[land])
            rng_[land] = h[land] + f * (h1[land] - h[land]); tf[land] = (i + f) * dt
            alive &= ~land
        h, z = h1, z1
        if not alive.any():
            break
    shp = (len(thetas_deg), len(speeds))
    return rng_.reshape(shp), znet.reshape(shp), tf.reshape(shp)


def solve_shots(p0, target, thetas, vmax, net_margin=0.15, vmin=2.0):
    """Launch velocities from p0 that land at `target` (xy) and clear the net top by >= net_margin: one per launch
    angle that works (in the order given). Returns [(theta, speed, v (3,), flight time)]."""
    p0 = np.asarray(p0, float); target = np.asarray(target, float)
    d = target - p0[:2]; H = float(np.linalg.norm(d))
    if H < 1e-6:
        return []
    hd = d / H
    speeds = np.linspace(vmin, vmax, 90)
    R, ZN, TF = flight_table(p0, hd, thetas, speeds)
    out = []
    for i, th in enumerate(thetas):
        r = R[i]; ok = np.isfinite(r)
        if not ok.any():
            continue
        r_ok = r[ok]; s_ok = speeds[ok]
        j = np.nonzero(r_ok >= H)[0]
        if len(j) == 0:
            continue
        j = j[0]
        if j == 0:
            v = s_ok[0]; f = 0.0; j0 = 0
        else:
            f = (H - r_ok[j - 1]) / (r_ok[j] - r_ok[j - 1]); v = s_ok[j - 1] + f * (s_ok[j] - s_ok[j - 1]); j0 = j - 1
        zn = ZN[i][ok]; tf = TF[i][ok]
        crosses = (p0[1] > 0) != (target[1] > 0)
        if crosses:
            z_net = zn[j0] + f * (zn[min(j, len(zn) - 1)] - zn[j0]) if j > 0 else zn[0]
            if not np.isfinite(z_net) or z_net < NET_TOP + net_margin:
                continue
        t_f = tf[j0] + f * (tf[min(j, len(tf) - 1)] - tf[j0]) if j > 0 else tf[0]
        thr = math.radians(th)
        vel = np.array([hd[0] * v * math.cos(thr), hd[1] * v * math.cos(thr), v * math.sin(thr)])
        out.append((th, float(v), vel, float(t_f)))
    return out


def in_service_court(x, y, right):
    """The receiver's service court in the receiver's frame (receiver on y < 0, facing +y; singles: between the short
    service line and the back line; its right court is x >= 0). BWF Laws 9.1 / 10.1: the serve must land in the court
    diagonally opposite, the receiver's right court when the server's score is even (lines are in)."""
    return (0.0 <= x <= COURT_X if right else -COURT_X <= x <= 0.0) and -COURT_Y <= y <= -SHORT_SERVICE_Y


def serve_plan(seed, n, server_score, base, reachable, lv=None):
    """The scripted opponent's serve (type, hitting point p0, velocity) in the RECEIVER's frame, from the server's
    service court into the receiver's diagonal service court (BWF 10.1.1: from the right court when the server's score
    is even), hit at 1.05 m (below 1.15 m, Law 9.1.6) and upwards (Law 9.1). The server faces -y, so its right court is
    x < 0. seed: the rng seed list prefix; n: the point's serial number (lets included, for the seeded choice);
    reachable(p0, v, base): the receiver can meet the flight; lv: the level (share of high serves, target range)."""
    lv = lv or LEVELS[1]
    rng = np.random.default_rng(list(seed) + [11, n])
    u = rng.uniform(-1, 1, 4)
    right = server_score % 2 == 0
    sx = -0.45 * COURT_SCALE if right else 0.45 * COURT_SCALE                 # the server's right court is at x < 0 in the receiver's frame
    p0 = np.array([sx, 2.3 * COURT_SCALE, 1.05])
    high = (u[0] + 1.0) / 2.0 < lv["serve_high"]
    typ = "serve_high" if high else "serve_short"
    side = 1.0 if right else -1.0                  # the receiver's diagonal court: x > 0 when the server serves from its right
    x0, x1 = lv["serve_x"]
    tx = side * (x0 + (x1 - x0) * (u[1] + 1.0) / 2.0)
    y0, y1 = lv["serve_short_y"]
    ty = (-5.9 - 0.4 * abs(u[2])) * COURT_SCALE if high else y0 + (y1 - y0) * abs(u[2])
    v = None
    for frac in (1.0, 0.6, 0.3):
        c = solve_shots(p0, (side * max(0.25 * COURT_SCALE, abs(tx) * frac), ty), SHOT_THETAS[typ], SHOT_VMAX[typ])
        c = [x for x in c if reachable(p0, x[2], base)]
        if c:
            v = c[0][2]; break
    if v is None:
        v = solve_shots(p0, (side * 0.6 * COURT_SCALE, -5.5 * COURT_SCALE), SHOT_THETAS["serve_high"] + (40, 35, 30),
                        SHUTTLE_VMAX)[0][2]
    return typ, p0, np.asarray(v, float), right


def in_court(x, y, side):
    """side +1: the opponent's court, -1: ours (lines are in)."""
    return abs(x) <= COURT_X and (0.0 < side * y <= COURT_Y)


BASE_PLAN_AMAX = 0.8 * BASE_AMAX               # the acceleration the go-to generator plans with: the feed force moves the
                                               # carriage, pedestal and arm (about 58 kg) at up to 43 m/s^2
BASE_TJ = BASE_PLAN_AMAX / BASE_JMAX           # time to ramp the base's acceleration up (or down)


def set_base(name):
    """Install the base `name` of BASES (its speed, per-axis accelerations, jerk 25 x the acceleration): the module's
    limits, the go-to generator's, the traj check's and the speed limits of the joint vector."""
    global BASE_NAME, BASE_VMAX, BASE_AMAX, BASE_JMAX, BASE_FORCE, BASE_AXIS_AMAX, VEL_LIMIT, BASE_PLAN_AMAX, BASE_TJ
    b = BASES[name]
    BASE_NAME = name
    BASE_VMAX = float(b["vmax"])
    BASE_AXIS_AMAX = np.array(b["amax"], float)
    BASE_AMAX = float(BASE_AXIS_AMAX.max())
    BASE_JMAX = 25.0 * BASE_AMAX
    BASE_FORCE = float(b["force"])
    VEL_LIMIT = np.r_[BASE_VMAX, BASE_VMAX, ARM_VEL]
    BASE_PLAN_AMAX = 0.8 * float(BASE_AXIS_AMAX.min())
    BASE_TJ = BASE_PLAN_AMAX / BASE_JMAX
    global BASE_LO, BASE_HI
    xh = float(b.get("x_half", COURT_X + 0.95))      # the axis' stroke (EGC-BS: up to 3000 mm)
    BASE_LO, BASE_HI = np.array([-xh, -(COURT_Y + 0.85)]), np.array([xh, -0.5])


set_base(BASE_NAME)


def base_limits():
    """The gantry's limits as a 2-axis limits record (speed, per-axis acceleration, jerk 25 x the acceleration): the
    setpoint generator that brakes the gantry in a joint-velocity reflex and brings it back to its targets after."""
    return AL.ArmLimits("gantry", BASE_NAME, BASE_LO.copy(), BASE_HI.copy(), np.full(2, BASE_VMAX), BASE_AXIS_AMAX.copy(),
                        25.0 * BASE_AXIS_AMAX, np.full(2, BASE_FORCE), None)


def base_goto(b, v, goal, a_prev=None):
    """One control step of the base's go-to generator: new (target, velocity). The speed is limited on the norm
    (BASE_VMAX), the acceleration (BASE_AMAX) and its rate of change (BASE_JMAX: the commanded acceleration changes by
    at most BASE_JMAX x dt per step, from a_prev, the previous step's); the braking curve leaves room for the jerk ramp
    (v_des = min(sqrt(1.4 a (d - v tj / 2)), d / (2 tj + dt))) and the acceleration towards the speed limit is ramped
    down in time. The final settle (within 4 mm and 5 cm/s) snaps to the goal."""
    e = goal - b; dist = float(np.hypot(e[0], e[1]))
    sp = float(np.hypot(v[0], v[1]))
    amin = float(BASE_AXIS_AMAX.min())                  # the final settle snaps only within what the base can stop
    if dist < min(0.004, 0.4 * amin * CONTROL_DT ** 2) and sp < min(0.05, 0.4 * amin * CONTROL_DT):
        return goal.copy(), np.zeros(2)
    tj = BASE_TJ
    d_eff = max(0.0, dist - sp * tj * 0.5)
    vdes = e / max(dist, 1e-9) * min(BASE_VMAX * 0.98, math.sqrt(2 * BASE_PLAN_AMAX * 0.7 * d_eff), dist / (2 * tj + 0.02))
    a_cmd = (vdes - v) / CONTROL_DT
    na = float(np.hypot(*a_cmd))
    amax = (min(BASE_PLAN_AMAX, math.sqrt(2 * BASE_JMAX * max(0.0, BASE_VMAX * 0.98 - sp)) + BASE_JMAX * CONTROL_DT)
            if float(a_cmd @ v) > 0 else BASE_PLAN_AMAX)
    if na > amax:
        a_cmd = a_cmd * (amax / na)
    a_cmd = np.clip(a_cmd, -0.8 * BASE_AXIS_AMAX, 0.8 * BASE_AXIS_AMAX)   # a base with per-axis limits (R1 Pro)
    ap = np.zeros(2) if a_prev is None else a_prev
    da = a_cmd - ap; nda = float(np.hypot(*da)); lim = BASE_JMAX * CONTROL_DT
    if nda > lim:
        a_cmd = ap + da * (lim / nda)
    v = v + a_cmd * CONTROL_DT
    nv = float(np.hypot(v[0], v[1]))
    if nv > BASE_VMAX * 0.98:
        v = v * (BASE_VMAX * 0.98 / nv)
    return np.clip(b + v * CONTROL_DT, BASE_LO, BASE_HI), v


BASE_ARRIVE = 0.015             # the stroke counts the base as arrived within 1.5 cm of its stance (wallclock-8; before:
                                # exactly, after the generator's final settle, about 0.15 s later)


def base_time(dist):
    """Approximate time for the base to travel `dist` from rest to rest (the generator's limits and its jerk ramp)."""
    a, vm = BASE_PLAN_AMAX * 0.85, BASE_VMAX * 0.98
    t = 2 * math.sqrt(dist / a) if dist < vm * vm / a else dist / vm + vm / a
    return t + BASE_TJ


def base_rows_problem(rows, b0, v0):
    """Why base targets (n x 2, one per control step) following the target b0 (moving at v0) break the gantry's limits,
    or None: speed (norm) <= BASE_VMAX, acceleration (norm) <= BASE_AMAX, from the finite differences (0.1 %)."""
    q = np.vstack([np.asarray(b0, float)[None], np.asarray(rows, float).reshape(-1, 2)])
    v = np.vstack([np.asarray(v0, float)[None], np.diff(q, axis=0) / CONTROL_DT])
    if (np.hypot(v[1:, 0], v[1:, 1]) > BASE_VMAX * 1.001 + 1e-9).any():
        return f"the base faster than {BASE_VMAX:g} m/s"
    a = np.diff(v, axis=0) / CONTROL_DT
    if (np.hypot(a[:, 0], a[:, 1]) > BASE_AMAX * 1.001 + 1e-9).any():
        return f"the base accelerating at more than {BASE_AMAX:g} m/s^2"
    if (np.abs(a) > BASE_AXIS_AMAX * 1.001 + 1e-9).any():
        return f"the base accelerating beyond its per-axis limits {BASE_AXIS_AMAX.tolist()} m/s^2"
    return None


LOB_Z, LOB_ZONE = 2.8, (-1.2, -0.05)   # (revision wallclock-11) a clear passes above any racket in your forward zone
LOB_FWD_Y = -1.2                # LEVELS lob: your base forward of this (y) invites a clear over your head


def over_the_net_player(p0, v) -> bool:
    """The flight from p0 at v stays above LOB_Z (beyond the reach of any racket on your side) over your forward
    zone LOB_ZONE (y), as a real clear does."""
    P, _ = predict(np.asarray(p0, float), np.asarray(v, float))
    m = (P[:, 1] > LOB_ZONE[0]) & (P[:, 1] < LOB_ZONE[1])
    return bool(m.any() and P[m, 2].min() >= LOB_Z)


def read_pattern(lands):
    """The next landing point your habits predict (lands: your last READ_N shots' landing points in the opponent's
    frame, oldest first), or None. The side: of the last READ_N - 1 changes of side (x beyond READ_SIDE_X), at least
    READ_AGREE either all switches or all stays, the next shot follows suit. The depth: the mean of your last 3 shots
    (short or deep: when they all landed on one side of READ_SHORT_Y; otherwise no reading). The point: that side at
    the mean |x| and that depth."""
    L = np.asarray(lands, float).reshape(-1, 2)[-READ_N:]
    if len(L) >= 3 and np.hypot(*(L[-3:] - L[-3:].mean(axis=0)).T).max() <= READ_SPOT:
        return L[-3:].mean(axis=0)                          # the same spot three times (revision wallclock-11)
    if len(L) < 4:
        return None
    sd = np.where(L[:, 0] > READ_SIDE_X, 1, np.where(L[:, 0] < -READ_SIDE_X, -1, 0))
    tr = [int(sd[i] == sd[i - 1]) for i in range(1, len(sd)) if sd[i] and sd[i - 1]]
    if len(tr) < READ_AGREE:
        return None
    if sum(tr) >= READ_AGREE:
        nxt = sd[-1] if sd[-1] else None                   # the same side again
    elif len(tr) - sum(tr) >= READ_AGREE:
        nxt = -sd[-1] if sd[-1] else None                  # alternating sides
    else:
        return None
    last3 = L[-3:]
    short = last3[:, 1] < READ_SHORT_Y
    if nxt is None or not (short.all() or (~short).all()):
        return None
    return np.array([nxt * float(np.mean(np.abs(last3[:, 0]))), float(np.mean(last3[:, 1]))])


SHOULDER_Z = PED_H + 0.333


STANCE_DIR = np.array([0.62, 0.62])     # the forehand contact's direction from the base (x right, y forward) x reach


def stance_offset(z):
    """The forehand contact's offset (x, y) from the base for a contact z high: to the right of and in front of the
    base, closer in for high and low contacts."""
    r = max(0.30, 0.95 - 0.35 * abs(float(z) - SHOULDER_Z))
    return STANCE_DIR * r


def stance(p):
    """Where the base should stand to meet the shuttle at p with a forehand (stance_offset)."""
    return np.clip(np.asarray(p[:2], float) - stance_offset(p[2]), BASE_LO, BASE_HI)


def quat_z_to(v):
    """Quaternion rotating the local z axis onto the direction v."""
    v = np.asarray(v, float); n = np.linalg.norm(v)
    if n < 1e-9:
        return np.array([1.0, 0, 0, 0])
    v = v / n; z = np.array([0.0, 0, 1])
    c = float(z @ v)
    if c < -0.999999:
        return np.array([0.0, 1, 0, 0])
    ax = np.cross(z, v); s = math.sqrt((1 + c) * 2)
    return np.array([s / 2, ax[0] / s, ax[1] / s, ax[2] / s])


def hermite(q0, v0, q1, v1, T, n):
    t = np.arange(1, n + 1) * (T / n)
    s = t / T
    h00 = 2 * s**3 - 3 * s**2 + 1; h10 = s**3 - 2 * s**2 + s; h01 = -2 * s**3 + 3 * s**2; h11 = s**3 - s**2
    return h00[:, None] * q0 + h10[:, None] * T * v0 + h01[:, None] * q1 + h11[:, None] * T * v1


# ---------------------------------------------------------------------- the servo's arithmetic, without the overhead
# Phys.servo runs 10 times per control step, for the match and for every rehearsal of the stroke planner (about 6 500
# times per planned stroke): its Python overhead was most of the planner's wall time (2026-10-13: ~75 % of 0.5-2 s per
# stroke). _jerk_caps and _jl_step do the SAME floating-point operations in the same order as limits.jerk_caps and
# limits.JerkLimiter.step (and Phys.servo those of limits.TorqueRateLimiter), so the results are bit-identical
# (tests/test_badminton.py test_planner_fast_paths_bit_identical); only the constants of the arm's limits are computed
# once, the ufuncs are called directly (no wrappers) and common subexpressions are shared.
_uclip = (np._core if hasattr(np, "_core") else np.core).umath.clip   # what np.clip calls with both bounds
_umin, _umax, _uabs, _usign, _usqrt = np.minimum, np.maximum, np.abs, np.sign, np.sqrt
_add_reduce, _max_reduce = np.add.reduce, np.maximum.reduce


class _ArmConst:
    """The constants of the arm's setpoint generator (limits.JerkLimiter), jerk caps (limits.jerk_caps, share 0.7) and
    torque stage (limits.TorqueRateLimiter), computed as their code computes them."""

    def __init__(self, jl, lim_caps, trl):
        assert lim_caps.dtau is not None and lim_caps.jerk is not None and trl.step_max is not None
        assert np.array_equal(lim_caps.jerk, jl.J)      # so min(J, jerk_caps(..)) is jerk_caps(..) itself
        self.dt, self.V, self.A, self.Jh = jl.dt, jl.V, jl.A, jl.J
        self.negV, self.negA = -jl.V, -jl.A
        self.KP, self.KV, self.KV2 = jl.KP, jl.KV, jl.KV * jl.KV
        Ab = jl.BRAKE * jl.A                            # brake_speed's A
        self.Ab3, self.nAbAb, self.Ab4, self.Ab8 = Ab**3, -Ab * Ab, Ab**4, 8.0 * Ab
        self.twoJh = 2.0 * jl.J
        self.dt3 = jl.dt**3
        self.cap_num, self.cap_jerk = 0.7 * lim_caps.dtau, lim_caps.jerk
        self.tau_max, self.neg_tau_max, self.step_max = trl.tau_max, -trl.tau_max, trl.step_max


def _jerk_caps(c: _ArmConst, M):
    """limits.jerk_caps(M, lim) (share 0.7) for a lim with torque-rate and jerk limits."""
    return _umin(c.cap_jerk, c.cap_num / _umax(_add_reduce(_uabs(M), axis=1), 1e-9))


def _jl_step(c: _ArmConst, jl, r, rd, J):
    """limits.JerkLimiter.step(r, rd, jerk_cap) with jerk_cap = J from _jerk_caps (<= the jerk limits): the same
    operations in the same order. Updates jl.q, jl.qd, jl.qdd (new arrays) and returns them."""
    q, qd, qdd, dt = jl.q, jl.qd, jl.qdd, c.dt
    e = r - q
    t = _uabs(qdd) / J
    e = e - ((qd - rd) * t + 0.5 * qdd * t * t - _usign(qdd) * J * t**3 / 6.0)
    ae = _uabs(e)
    J2 = J**2                                       # brake_speed(|e|, BRAKE A, J) (its max(dist, 0) is |e| itself)
    bs = np.where(ae <= c.Ab3 / J2, np.cbrt(ae * ae * J), 0.5 * (c.nAbAb / J + _usqrt(c.Ab4 / J2 + c.Ab8 * ae)))
    v_cmd = _uclip(rd + _usign(e) * _umin(c.KP * ae, bs), c.negV, c.V)
    err = v_cmd - qd                                # _sqrt_ctrl(v_cmd - qd, KV, J)
    lin = J / c.KV2
    a = _uabs(err)
    twoJ = 2.0 * J
    sc = np.where(a <= lin, c.KV * err, _usign(err) * _usqrt(_umax(0.0, twoJ * (a - 0.5 * lin))))
    a_cmd = _uclip(sc, c.negA, c.A)
    room_up, room_dn = _umax(0.0, c.V - qd), _umax(0.0, c.V + qd)
    a_cmd = _uclip(a_cmd, -_usqrt(twoJ * room_dn), _usqrt(twoJ * room_up))
    h_up, h_dn = _usqrt(c.twoJh * room_up), _usqrt(c.twoJh * room_dn)
    hard = (qdd > h_up) | (qdd < -h_dn)
    if hard.any():
        a_cmd = np.where(hard, _uclip(a_cmd, -h_dn, h_up), a_cmd)
        jlim = np.where(hard, c.Jh, J)
    else:
        jlim = J
    j = _uclip((a_cmd - qdd) / dt, -jlim, jlim)
    jl.q = q + qd * dt + 0.5 * qdd * dt * dt + j * c.dt3 / 6.0
    jl.qd = qd + qdd * dt + 0.5 * j * dt * dt
    jl.qdd = qdd + j * dt
    return jl.q, jl.qd, jl.qdd


_ARMC: list = []                                # [_ArmConst] of the arm (ARM_OP setpoints, ARM caps), built once


def _arm_const() -> _ArmConst:
    if not _ARMC:
        _ARMC.append(_ArmConst(AL.JerkLimiter(ARM_OP, PHYS_DT), ARM, AL.TorqueRateLimiter(ARM, PHYS_DT)))
    return _ARMC[0]


_MON_STATE = ("t", "open", "events", "warnings", "steps_in_contact", "peak_force", "peak_force_10ms", "max_depth",
              "impulse", "first_t", "by_pair")      # selfcollision.Monitor's running state (its reset())


# ---------------------------------------------------------------------- robot + shuttle physics
class Phys:
    """MuJoCo robot (mobile base + Franka + racket), the shuttle integrator and the racket-shuttle contact model."""

    def __init__(self):
        self.m = mj.MjModel.from_xml_path(str(SCENE))
        self.d = mj.MjData(self.m)
        self.selfcol = SC.monitors(self.m, {"A": "selfcol"}, "franka_panda")   # recorded only
        m = self.m
        jid = [mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j) for j in JOINTS]
        self.qa = np.array([m.jnt_qposadr[j] for j in jid]); self.va = np.array([m.jnt_dofadr[j] for j in jid])
        self.lo = m.jnt_range[jid, 0].copy(); self.hi = m.jnt_range[jid, 1].copy()
        m.actuator_ctrlrange[:2] = [[-BASE_FORCE, BASE_FORCE]] * 2    # the axes' feed force (set_base)
        self.lo[:2] = np.maximum(self.lo[:2], BASE_LO - 0.05); self.hi[:2] = np.minimum(self.hi[:2], BASE_HI + 0.05)   # stroke
        self.site = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "racket_center")
        self.kin = mj.MjData(m)
        self.steps_total = 0
        self.n_reflex = 0                        # joint-velocity reflexes of this robot (VMARGIN, REFLEX)

    def reset(self, q9):
        m, d = self.m, self.d
        mj.mj_resetData(m, d)
        d.qpos[self.qa] = q9
        mj.mj_forward(m, d)
        self.target = np.asarray(q9, float).copy()
        self.k = 0
        self._actions: list[np.ndarray] = []
        self.sh_p, self.sh_v, self.sh_live = (0.0, 3.0, 1.0), (0.0, 0.0, 0.0), False
        self.hit_enabled = False
        self.events: list[dict] = []
        self._prev = None
        self.n_reflex = 0
        self.reset_servo()

    def reset_servo(self):
        """The setpoint generators and the torque stage at rest at the robot's current pose (after a reset or when the
        referee puts the robot at its spot)."""
        d = self.d
        self._M = np.zeros((self.m.nv, self.m.nv))
        self.jl = AL.JerkLimiter(ARM_OP, PHYS_DT, d.qpos[self.qa[2:]].copy())
        self.trl = AL.TorqueRateLimiter(ARM, PHYS_DT, d.qfrc_bias[self.va[2:]].copy())
        self.n_steady = 0                        # control steps since the robot was last put somewhere
        self.reflex_at = None                    # (time, q9 at the trigger, the gantry's stop point) of a reflex in force
        self.bl = None                           # the gantry's setpoint generator, from a reflex until the next reset

    def base_acc(self, q):
        """The base targets' acceleration over the step to q (second difference with the last two targets)."""
        a = self._actions
        if self.n_steady < 2 or len(a) < 2:          # just put at its spot (or reset): from rest
            return np.zeros(2)
        return (np.asarray(q[:2]) - 2 * self.target[:2] + a[-2][:2]) / CONTROL_DT ** 2

    def servo_state(self) -> np.ndarray:
        """The servo's internal state (setpoints and the last arm torque), for the state hashes."""
        rf = self.reflex_at
        return np.concatenate([self.jl.q, self.jl.qd, self.jl.qdd, self.trl.tau, [float(min(self.n_steady, 2))],
                               [0.0, 0.0] if rf is None else [1.0, rf[0]],
                               np.zeros(6) if self.bl is None else np.r_[self.bl.q, self.bl.qd, self.bl.qdd]])

    def _servo_extra(self):
        """The reflex state (copy_from, save / load)."""
        rf = self.reflex_at
        return (None if rf is None else (rf[0], rf[1].copy(), rf[2].copy()),
                None if self.bl is None else (self.bl.q.copy(), self.bl.qd.copy(), self.bl.qdd.copy()), self.n_reflex)

    def _set_servo_extra(self, x):
        rf, bl, self.n_reflex = x
        self.reflex_at = None if rf is None else (rf[0], rf[1].copy(), rf[2].copy())
        self.bl = None
        if bl is not None:
            self.bl = AL.JerkLimiter(base_limits(), PHYS_DT)
            self.bl.reset(*bl)

    def copy_from(self, o: "Phys"):
        d = self.d
        mj.mj_resetData(self.m, d)
        d.qpos[:] = o.d.qpos; d.qvel[:] = o.d.qvel; d.qacc_warmstart[:] = o.d.qacc_warmstart; d.time = o.d.time
        d.ctrl[:] = o.d.ctrl
        mj.mj_forward(self.m, d)
        self.target = o.target.copy(); self.k = o.k
        self._actions = [x.copy() for x in o._actions[-2:]]      # the base's acceleration feed-forward reads them
        self.sh_p, self.sh_v, self.sh_live, self.hit_enabled = o.sh_p, o.sh_v, o.sh_live, o.hit_enabled
        self.events = []
        self._prev = None if o._prev is None else (o._prev[0].copy(), o._prev[1].copy(), o._prev[2])
        self.jl.reset(o.jl.q, o.jl.qd, o.jl.qdd)
        self.trl.reset(o.trl.tau)
        self.n_steady = o.n_steady
        self._set_servo_extra(o._servo_extra())

    def save(self):
        """The robot's state as copy_from copies it (for a twin rollout to continue from later: Phys.load)."""
        d = self.d
        return (d.qpos.copy(), d.qvel.copy(), d.qacc_warmstart.copy(), d.time, d.ctrl.copy(), self.target.copy(),
                self.k, [x.copy() for x in self._actions[-2:]], self.jl.q.copy(), self.jl.qd.copy(),
                self.jl.qdd.copy(), self.trl.tau.copy(), self.n_steady, self._servo_extra())

    def load(self, st):
        """Back to a state from save(), robot only (no shuttle in play), as copy_from does."""
        d = self.d
        mj.mj_resetData(self.m, d)
        d.qpos[:] = st[0]; d.qvel[:] = st[1]; d.qacc_warmstart[:] = st[2]; d.time = st[3]; d.ctrl[:] = st[4]
        mj.mj_forward(self.m, d)
        self.target = st[5].copy(); self.k = st[6]
        self._actions = [x.copy() for x in st[7]]
        self.sh_live = False; self.hit_enabled = False
        self.events = []
        self._prev = None
        self.jl.reset(st[8], st[9], st[10])
        self.trl.reset(st[11])
        self.n_steady = st[12]
        self._set_servo_extra(st[13])

    def checkpoint(self):
        """The robot's whole state, exactly (all of MjData, the servo, the reflex, the self-collision monitor), for
        restore(): stepping on from a restored checkpoint is bit-identical to stepping on from where it was taken
        (unlike save() / load(), which keep only what copy_from copies and recompute the rest with mj_forward). The
        stroke planner's rehearsals share their common start this way (Match._simulate_arm)."""
        mon = self.selfcol["A"]
        return (_copy.copy(self.d), self.target.copy(), self.k, list(self._actions), self.jl.q.copy(),
                self.jl.qd.copy(), self.jl.qdd.copy(), self.trl.tau.copy(), self.n_steady, self._servo_extra(),
                self.sh_p, self.sh_v, self.sh_live, self.hit_enabled, list(self.events), self._prev, self.steps_total,
                _copy.deepcopy({k: getattr(mon, k) for k in _MON_STATE}))

    def restore(self, ck):
        """Back to a checkpoint() of this robot (the checkpoint stays valid: it can be restored again)."""
        self.d = _copy.copy(ck[0])
        self.target = ck[1].copy(); self.k = ck[2]; self._actions = list(ck[3])
        self.jl.reset(ck[4], ck[5], ck[6])
        self.trl.tau = ck[7].copy()
        self.n_steady = ck[8]
        self._set_servo_extra(ck[9])
        self.sh_p, self.sh_v, self.sh_live, self.hit_enabled = ck[10], ck[11], ck[12], ck[13]
        self.events = list(ck[14]); self._prev = ck[15]; self.steps_total = ck[16]
        mon = self.selfcol["A"]
        for k, v in _copy.deepcopy(ck[17]).items():
            setattr(mon, k, v)

    def check_target(self, q):
        if q.shape != (9,) or not np.all(np.isfinite(q)):
            raise ValueError(f"action must be 9 finite joint targets, got {q.shape}")
        if (q < self.lo - 1e-9).any() or (q > self.hi + 1e-9).any():
            raise ValueError(f"step {self.k}: joint target outside range: {q}")
        dq = np.abs(q - self.target)
        lim = VEL_LIMIT * CONTROL_DT * (1 + 1e-6) + 1e-12
        if (dq > lim).any():
            j = int(np.argmax(dq / lim))
            raise ValueError(f"step {self.k}: joint {JOINTS[j]} target moved {dq[j]:.5f} in one control step "
                             f"(limit {VEL_LIMIT[j] * CONTROL_DT:.5f})")

    def servo(self, q_des, qd_des, base_acc=None):
        """One 1 ms servo step towards the (interpolated) joint target: the base by PD + bias compensation within the
        gantry's feed force (its targets are within the gantry's limits: the go-to generator, the traj check); the arm
        through its setpoint generator (velocity at VMARGIN of the limits, acceleration, jerk limits), an inertia
        feed-forward + PD + bias compensation and the torque stage (size and rate limits). The joint-velocity reflex
        (REFLEX): a physical arm joint faster than REFLEX x its limit stops the robot for REFLEX_RECOVER_S (the targets
        are ignored: the arm brakes to rest at the pose of the trigger, the gantry to rest within its limits), then it
        catches up with its targets within the limits."""
        m, d, qa, va = self.m, self.d, self.qa, self.va
        mj.mj_fullM(m, self._M, d.qM)
        M = self._M
        ix = self._ix()
        if self.reflex_at is None and (_uabs(d.qvel[ix["va_a"]]) > ix["reflex_vel"]).any():
            # the joint-velocity reflex: the gantry's setpoints from its targets' state, braking to rest where its
            # limits stop it (BASE_LIM), the arm's to rest at the pose of the trigger
            if self.bl is None:
                self.bl = AL.JerkLimiter(base_limits(), PHYS_DT)
                bl0 = self.bl
                self.bl.reset(q_des[:2], np.clip(qd_des[:2], -bl0.V, bl0.V),
                              np.zeros(2) if base_acc is None else np.clip(base_acc, -bl0.A, bl0.A))
            bl = self.bl
            stop = bl.q + bl.qd * np.abs(bl.qd) / (2.0 * bl.A) + bl.qd * (bl.A / bl.J)
            self.reflex_at = (float(d.time), d.qpos[qa].copy(), np.clip(stop, BASE_LO, BASE_HI))
            self.n_reflex += 1
        if self.reflex_at is not None and d.time - self.reflex_at[0] >= REFLEX_RECOVER_S - 1e-9:
            self.reflex_at = None                  # recovered: from rest, the targets again (through the limiters)
        if self.reflex_at is not None:
            q_des = np.r_[self.reflex_at[2], self.reflex_at[1][2:]]
            qd_des = np.zeros(9)
        if self.bl is not None:                    # after a reflex: the gantry's targets through its setpoint generator
            b_sp, bd_sp, base_acc = self.bl.step(q_des[:2], qd_des[:2])
        else:
            b_sp, bd_sp = q_des[:2], qd_des[:2]
        tau_b = ix["kp_b"] * (b_sp - d.qpos[ix["qa_b"]]) + ix["kd_b"] * (bd_sp - d.qvel[ix["va_b"]]) \
            + d.qfrc_bias[ix["va_b"]]
        cr = m.actuator_ctrlrange
        d.ctrl[:2] = _uclip(tau_b, cr[:2, 0], cr[:2, 1])   # the gantry's feed force (BASE_FORCE, the scene's ctrlrange)
        Ma = M[ix["aa"]]
        c = _arm_const()                           # the arm: setpoint generator, jerk caps (limits.py, bit-identical)
        q_sp, qd_sp, qdd_sp = _jl_step(c, self.jl, q_des[2:], qd_des[2:], _jerk_caps(c, Ma))
        qa_a, va_a = ix["qa_a"], ix["va_a"]
        e = q_sp - d.qpos[qa_a]
        tau = Ma @ qdd_sp + ix["kp_a"] * e + ix["kd_a"] * (qd_sp - d.qvel[va_a]) + d.qfrc_bias[va_a]
        if COUPLING_FF and base_acc is not None:   # the base's commanded acceleration fed forward into the arm
            tau = tau + M[ix["ab"]] @ base_acc      # (the coupling M_arm,base x a_base)
        trl = self.trl                             # the torque stage (limits.TorqueRateLimiter)
        trl.tau = _uclip(_uclip(tau, trl.tau - c.step_max, trl.tau + c.step_max), c.neg_tau_max, c.tau_max)
        d.ctrl[2:] = trl.tau
        if _max_reduce(_uabs(e)) > RESYNC:         # the setpoint does not run away from the arm (no wind-up)
            jl = self.jl
            big = np.abs(e) > RESYNC
            jl.q[big] = d.qpos[qa[2:]][big] + np.sign(e[big]) * RESYNC
            jl.qd[big] = np.clip(d.qvel[va[2:]], -jl.V, jl.V)[big]
            jl.qdd[big] = 0.0

    def _ix(self) -> dict:
        """The servo's index arrays and gains (fancy indices of qpos / qvel / qM, as servo used them), built once."""
        ix = self.__dict__.get("_ixd")
        if ix is None:
            qa, va = self.qa, self.va
            # the joints' qpos / qvel addresses as slices when contiguous (views: the same numbers, no copy); the
            # inertia blocks stay fancy-indexed copies (the matrix products see the same contiguous arrays as before)
            def sl(a, i, j):
                run = np.array_equal(a[i:j], np.arange(a[i], a[i] + j - i))
                return slice(int(a[i]), int(a[i]) + j - i) if run else a[i:j].copy()
            ix = self._ixd = {"qa_b": sl(qa, 0, 2), "qa_a": sl(qa, 2, 9), "va_b": sl(va, 0, 2),
                              "va_a": sl(va, 2, 9), "aa": np.ix_(va[2:], va[2:]), "ab": np.ix_(va[2:], va[:2]),
                              "kp_b": KP[:2].copy(), "kd_b": KD[:2].copy(), "kp_a": KP[2:].copy(),
                              "kd_a": KD[2:].copy(), "reflex_vel": REFLEX * ARM_VEL}
        return ix

    def step(self, q):
        q = np.asarray(q, dtype=np.float64).reshape(-1)
        self.check_target(q)
        m, d, site = self.m, self.d, self.site
        q_prev = self.target
        dq = q - q_prev
        qd_des = dq / CONTROL_DT
        b_acc = self.base_acc(q)
        mon = self.selfcol["A"]
        pending = False                            # the racket's pose of the last substep still to be kept (_prev)
        for j in range(1, SUBSTEPS + 1):
            self.servo(q_prev + dq * (j / SUBSTEPS), qd_des, b_acc)
            mj.mj_step(m, d)
            mon.update(d)
            # site pose now = the pose at the start of this step (time t_n), the same time as self.sh_p
            if self.sh_live:
                c = d.site_xpos[site].copy(); n = d.site_xmat[site].reshape(3, 3)[:, 0].copy()
                if self.hit_enabled and self._prev is not None and self.sh_p[1] < 0:   # only on our half (BWF 13.4.2)
                    self._check_hit(c, n)
                self._prev = (c, n, self.sh_p)
                self._advance_shuttle()
                pending = False
            else:                                  # (only the last one is ever read: taken after the loop)
                pending = True
        if pending:
            self._prev = (d.site_xpos[site].copy(), d.site_xmat[site].reshape(3, 3)[:, 0].copy(), self.sh_p)
        self.target = q.copy()
        self._actions.append(q.copy())
        self.k += 1
        self.n_steady += 1
        self.steps_total += SUBSTEPS

    def actions(self) -> np.ndarray:
        """(N, 9) joint targets applied since the reset."""
        return np.array(self._actions, dtype=np.float64).reshape(-1, 9)

    def _advance_shuttle(self):
        p, v = self.sh_p, self.sh_v
        p1, v1 = sh_step(p, v)
        if (p[1] > 0) != (p1[1] > 0) and p[1] != p1[1]:
            f = p[1] / (p[1] - p1[1])
            z = p[2] + f * (p1[2] - p[2]); x = p[0] + f * (p1[0] - p[0])
            self.events.append({"kind": "cross", "k": self.k, "x": round(x, 4), "z": round(z, 4),
                                "to": "opp" if p1[1] > 0 else "own"})
            if z < NET_TOP and abs(x) <= POST_X:
                self.sh_p = (x, 0.0, z); self.sh_v = (0.0, 0.0, 0.0); self.sh_live = False
                self.events.append({"kind": "net", "k": self.k, "x": round(x, 4), "z": round(z, 4)})
                return
        if p1[2] <= 0.0:
            f = p[2] / (p[2] - p1[2]) if p[2] != p1[2] else 1.0
            x = p[0] + f * (p1[0] - p[0]); y = p[1] + f * (p1[1] - p[1])
            self.sh_p = (x, y, 0.0); self.sh_v = (0.0, 0.0, 0.0); self.sh_live = False
            self.events.append({"kind": "land", "k": self.k, "x": round(x, 4), "y": round(y, 4)})
            return
        self.sh_p, self.sh_v = p1, v1

    def _check_hit(self, c, n):
        cp, npv, sp = self._prev
        sp = np.array(sp); sh = np.array(self.sh_p)
        s0 = float((sp - cp) @ npv); s1 = float((sh - c) @ n)
        if s0 * s1 > 0 or (s0 == 0 and s1 == 0):
            return
        f = s0 / (s0 - s1) if s0 != s1 else 0.0
        pc = cp + f * (c - cp); ps = sp + f * (sh - sp)
        r = ps - pc
        off = float(np.linalg.norm(r - (r @ n) * n))
        if off > R_HEAD:
            return
        vr = (c - cp) / PHYS_DT; vs = np.array(self.sh_v)
        n_out = n if float((vr - vs) @ n) >= 0 else -n
        u = float(vr @ n_out); vin = float(vs @ n_out)
        spd = RACKET_GAIN * max(u, 0.0) * (1 - OFFCENTRE_LOSS * (off / R_HEAD) ** 2) + E_SHUTTLE * max(0.0, -vin)
        v_out = n_out * spd
        p_new = ps + n_out * 0.002
        self.sh_p = tuple(float(x) for x in p_new); self.sh_v = tuple(float(x) for x in v_out)
        self.hit_enabled = False
        self.events.append({"kind": "hit", "k": self.k, "pos": [round(float(x), 4) for x in ps],
                            "offcentre": round(off, 4), "racket_speed": round(u, 3), "speed": round(spd, 3),
                            "v_out": [round(float(x), 3) for x in v_out]})

    # kinematics (scratch data; never stepped)
    def kin_set(self, q9):
        qp = self.d.qpos.copy()
        qp[self.qa] = q9
        key = qp.tobytes()
        if self.__dict__.get("_kin_key") == key:  # the scratch data already holds this exact pose (fk then jac: IK)
            return
        self.kin.qpos[:] = qp
        mj.mj_kinematics(self.m, self.kin)
        mj.mj_comPos(self.m, self.kin)
        self._kin_key = key

    def fk(self, q9):
        self.kin_set(np.asarray(q9, float))
        return self.kin.site_xpos[self.site].copy(), self.kin.site_xmat[self.site].reshape(3, 3).copy()

    def clearance(self, q9):
        """The least distance (m) between the two geoms of any of the arm's self-collision pairs (its links, the racket,
        the stand) at the joint configuration q9, capped at CLEAR_CUT; negative = penetration. Kinematics only: MuJoCo's
        own collision detection on the clearance model (_clear_model: the pairs with a margin of CLEAR_CUT), so the
        planner measures exactly what the physics' contacts would (mj_geomDistance reads 0.0 for some mesh pairs
        centimetres apart in MuJoCo 3.3.7)."""
        mc, keys = _clear_model(self.m)
        d = self.__dict__.get("_clr_d")
        if d is None:
            d = self._clr_d = mj.MjData(mc)
        d.qpos[:] = self.d.qpos
        d.qpos[self.qa] = np.asarray(q9, float)
        mj.mj_kinematics(mc, d)
        mj.mj_collision(mc, d)
        n = d.ncon
        if not n:
            return CLEAR_CUT
        g = d.contact.geom[:n]
        k = np.minimum(g[:, 0], g[:, 1]).astype(np.int64) * mc.ngeom + np.maximum(g[:, 0], g[:, 1])
        sel = np.isin(k, keys)
        return float(min(CLEAR_CUT, d.contact.dist[:n][sel].min())) if sel.any() else CLEAR_CUT

    def __getstate__(self):
        st = self.__dict__.copy()
        for k in ("_clr_d", "_ixd", "_kin_key"):    # scratch (the clearance model's data, the servo's indices, the
            st.pop(k, None)                         # pose in kin): rebuilt on use, not pickled
        return st

    def jac(self, q9):
        """(6, 7) racket-centre Jacobian w.r.t. the arm joints."""
        self.kin_set(np.asarray(q9, float))
        jp = np.zeros((3, self.m.nv)); jr = np.zeros((3, self.m.nv))
        mj.mj_jacSite(self.m, self.kin, jp, jr, self.site)
        return np.vstack([jp[:, self.va[2:]], jr[:, self.va[2:]]])

    def racket_state(self):
        d = self.d
        jp = np.zeros((3, self.m.nv)); jr = np.zeros((3, self.m.nv))
        mj.mj_jacSite(self.m, d, jp, jr, self.site)
        return (d.site_xpos[self.site].copy(), d.site_xmat[self.site].reshape(3, 3)[:, 0].copy(), jp @ d.qvel)

    def state_sha(self):
        d = self.d
        h = hashlib.sha256()
        for a in (d.qpos, d.qvel, d.qacc_warmstart, d.ctrl, np.array([d.time]), np.array(self.sh_p + self.sh_v),
                  self.servo_state()):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        h.update(json.dumps(self.events, sort_keys=True).encode())
        return h.hexdigest()


_CLEAR = {}


def _clear_model(m):
    """The planner's clearance model (built once per process from the scene): a copy of the robot model whose
    self-collision pairs (selfcol_<i>) have a margin of CLEAR_CUT, so mj_collision reports every pair closer than that
    with its distance; and the pair keys checked (min geom id * ngeom + max). Not checked: the pairs closer than
    CLEAR_MIN in the ready pose (structurally close: the wrist's link5 x link7, 2.2 cm), which the planner cannot keep
    clear of; they still collide in the physics and are recorded."""
    c = _CLEAR.get("model")
    if c is not None:
        return c
    import copy
    mc = copy.deepcopy(m)
    ids = [i for i in range(m.npair) if SC.is_tag(mj.mj_id2name(m, mj.mjtObj.mjOBJ_PAIR, i), "selfcol")]
    mc.pair_margin[ids] = CLEAR_CUT
    key = lambda a, b: min(a, b) * mc.ngeom + max(a, b)
    keys = {key(int(mc.pair_geom1[i]), int(mc.pair_geom2[i])) for i in ids}
    d = mj.MjData(mc)
    qa = [mc.jnt_qposadr[mj.mj_name2id(mc, mj.mjtObj.mjOBJ_JOINT, j)] for j in JOINTS]
    d.qpos[qa] = np.r_[HOME, Q0_ARM]
    mj.mj_kinematics(mc, d)
    mj.mj_collision(mc, d)
    close = {key(int(c_.geom[0]), int(c_.geom[1])) for c_ in d.contact[:d.ncon] if c_.dist < CLEAR_MIN}
    c = _CLEAR["model"] = (mc, np.array(sorted(keys - close), dtype=np.int64))
    return c


_EYE6_1E3 = 1e-3 * np.eye(6)


def _cross3(a, b) -> np.ndarray:
    """np.cross of two 3-vectors (the same products and differences: a1 b2 - a2 b1, a2 b0 - a0 b2, a0 b1 - a1 b0)."""
    a0, a1, a2 = a.tolist()
    b0, b1, b2 = b.tolist()
    return np.array([a1 * b2 - a2 * b1, a2 * b0 - a0 * b2, a0 * b1 - a1 * b0])


def ik(ph: Phys, pos, normal, base_xy, q_init, iters=150, tol=1e-4):
    """Damped least squares over the 7 arm joints (base fixed at base_xy): racket centre at pos, face normal along
    `normal` (rotation about the normal free)."""
    q = np.r_[base_xy, q_init].astype(float)
    n_t = np.asarray(normal, float); n_t = n_t / np.linalg.norm(n_t)
    lo, hi = ph.lo[2:] + 1e-4, ph.hi[2:] - 1e-4
    err = np.inf
    for _ in range(iters):
        p, R = ph.fk(q)
        n = R[:, 0]
        c = _cross3(n, n_t)
        e = np.concatenate((pos - p, c))
        e3, e6 = e[:3], e[3:]                   # np.linalg.norm(x) of a float vector is sqrt(x.dot(x))
        err = float(_usqrt(e3.dot(e3)) + np.arcsin(min(1.0, _usqrt(e6.dot(e6)))))
        if n @ n_t < 0:
            e[3:] = c + 0.5 * _cross3(n, R[:, 1]); err += np.pi / 2
        if err < tol:
            break
        J = ph.jac(q)
        dq = J.T @ np.linalg.solve(J @ J.T + _EYE6_1E3, e)
        nd = float(np.max(np.abs(dq)))
        if nd > 0.25:
            dq *= 0.25 / nd
        q[2:] = np.clip(q[2:] + dq, lo, hi)
    return q[2:].copy(), err


SCATTER_TAG = 1000                             # the first key word of the execution-scatter streams (see the header)


def scatter_rng(seed, kind: int, stream: int, n: int) -> np.random.Generator:
    """The execution scatter of a player's n-th act: its own stream (1 = the match's player / the duel's first
    server, 2 = the duel's other robot), independent of every other draw of the match."""
    return np.random.default_rng([int(seed), SCATTER_TAG, int(kind), int(stream), int(n)])


# fixed extra IK start poses (offsets from the ready pose Q0_ARM): arm lowered / raised, turned left / right, wrist
# turned. Deterministic: the same list every run, so the plan is a pure function of the state (replay is bit-exact).
IK_SEED_OFFSETS = np.array([
    [0.0, 0.5, 0.0, 0.6, 0.0, -0.4, 0.0],
    [0.0, -0.4, 0.0, -0.3, 0.0, 0.4, 0.0],
    [0.6, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0],
    [-0.6, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.3, 0.0, 0.3, 1.2, 0.0, 0.0],
    [0.0, 0.3, 0.0, 0.3, -1.2, 0.0, 0.0],
])
IK_OK = 2e-3                    # an IK solution with a residual below this counts as reaching the pose
# Self-collision (sport revision wallclock-9 / duel-11, 2026-10-10): the arm cannot pass through its own pedestal
# (1.0 m, r 0.11 m), platform or links (the scene's self-collision pairs, bodies/selfcollision.py). The stroke planner
# keeps clear of them: the hit configuration at least CLEAR_MIN from them (ik_multi); of the candidate swings, one whose
# rehearsals on the robot-only twin (where the stand and links block the arm physically: the swing's correction passes,
# then the whole motion with the follow-through and the return to the ready pose, Match._rollout_contact) have no
# self-collision contact is taken first.
# For low forehands (contact below about 0.75 m) the nearest IK solution often folded the forearm into the pedestal
# (up to 15 cm deep); a clear solution almost always exists at nearly the same move time (IK_CLEAR_SEEDS reach it).
CLEAR_CUT = 0.05                # m: the clearance is measured up to this (the clearance model's pair margin)
CLEAR_MIN = 0.04                # m: a hit configuration this close to the stand or its own links is a last resort
READY_CHECK_STEPS = 200         # the return to the ready pose checked for at most this many control steps
# extra IK starts (absolute arm poses) tried when no start above gives a clear solution: forehand poses with the
# forearm held out from the pedestal (low contacts), from a sweep of random starts (2026-10-10)
IK_CLEAR_SEEDS = np.array([
    [1.10, 1.70, -0.35, -1.70, -0.70, 2.15, -0.60],
    [1.00, 1.50, -0.45, -1.85, -0.70, 2.10, -0.80],
    [1.45, 1.40, -0.70, -2.35, -0.55, 2.45, -0.70],
    [1.25, 1.00, -0.85, -2.40, -1.00, 2.25, -0.50],
    [-1.20, 1.65, -0.60, -1.70, 2.00, 1.25, 0.00],
])


def move_time(dq):
    """The least time of a rest-to-rest joint move dq under the joint speed and acceleration limits (the slowest
    joint; the acceleration limits at ACC_SHARE, as the swing plans them)."""
    d = np.abs(np.asarray(dq, float))
    a = ARM.acc * ACC_SHARE
    t = np.where(d < ARM_VEL_OP ** 2 / a, 2.0 * np.sqrt(d / a), d / ARM_VEL_OP + ARM_VEL_OP / a)
    return float(np.max(t))


def ik_multi(ph: Phys, pos, normal, base_xy, seeds, q_now):
    """Deterministic multi-start IK for both string faces: starts from `seeds` (the caller's seed, the current joint
    targets, the ready pose) and the fixed IK_SEED_OFFSETS poses. Of the solutions that reach the pose
    (residual < IK_OK) it takes the one nearest to the current joint state in joint-speed terms (the least time at the
    joint speed and acceleration limits, move_time), so the swing does not wander into a far, flipped
    configuration; if none reaches it, the lowest residual. Self-collision: the solutions closer than CLEAR_MIN to the
    robot's own stand or links (Phys.clearance) come after the clear ones (by clearance), and when no start gives a
    clear one, the IK_CLEAR_SEEDS starts are tried too. Returns (q, residual, face sign, fallbacks): up to 2 more
    distinct solutions, next-nearest first, for when the nearest one cannot be swung to in time or without
    self-collision."""
    n_t = np.asarray(normal, float); n_t = n_t / np.linalg.norm(n_t)
    q_now = np.asarray(q_now, float)
    lo, hi = ph.lo[2:] + 1e-3, ph.hi[2:] - 1e-3
    starts = []
    cands = []

    def solve_from(seed_list):
        for s in seed_list:
            s = np.clip(np.asarray(s, float), lo, hi)
            if any(np.array_equal(s, t) for t in starts):
                continue
            starts.append(s)
            i = len(starts) - 1
            for sgn in (1.0, -1.0):                   # the string bed has two faces (the commanded one first)
                q, r = ik(ph, pos, sgn * n_t, base_xy, s)
                cands.append((move_time(q - q_now), r, i, sgn, q))

    def ordered():
        """the solutions that reach the pose: the clear ones (CLEAR_MIN) nearest first, then the others by clearance"""
        good = sorted((c for c in cands if c[1] < IK_OK), key=lambda c: (round(c[0], 9), c[2], -c[3]))
        clr = [ph.clearance(np.r_[base_xy, c[4]]) for c in good]
        return ([c for c, d in zip(good, clr) if d >= CLEAR_MIN]
                + [c for d, _, c in sorted(((d, j, c) for j, (c, d) in enumerate(zip(good, clr)) if d < CLEAR_MIN),
                                           key=lambda t: (-round(t[0], 9), t[1]))]), max(clr, default=-1.0)

    solve_from(list(seeds) + [Q0_ARM + d for d in IK_SEED_OFFSETS])
    good, best_clr = ordered()
    if best_clr < CLEAR_MIN:                          # no clear solution yet: the extra starts (self-collision)
        solve_from(IK_CLEAR_SEEDS)
        good, best_clr = ordered()
    if not good:
        c = min(cands, key=lambda c: (c[1], c[2]))
        return c[4], c[1], c[3], []
    alts = []                                         # the next-nearest distinct solutions (fallbacks), at most 2
    for c in good[1:]:
        if len(alts) < 2 and all(np.max(np.abs(c[4] - o[4])) > 0.2 for o in [good[0]] + alts):
            alts.append(c)
    return good[0][4], good[0][1], good[0][3], [(c[4], c[1], c[3]) for c in alts]


def swing_score(perr, nerr_deg, verr):
    """How far a rehearsed swing is from the commanded racket state (m-equivalent: 1 cm ~ 1.7 deg ~ 0.17 m/s; legacy:
    0.5 m/s, but with the shuttle at 4 x the head speed a head 0.5 m/s off sends it 2 m/s off, a metre long or short)."""
    return float(perr) + 0.006 * float(nerr_deg) + 0.06 * float(verr)


DELIVERY_POS_WARN, DELIVERY_ANG_WARN = 0.03, 5.0   # stroke note when the rehearsed delivery is off by more


# ---------------------------------------------------------------------- the match
class Match:
    """The match. Live: run_to_decision() / shot() / adjust(). Replay: replay(actions)."""

    # decision cameras: (lookat, distance, azimuth, elevation) of MuJoCo free cameras
    # (revision wallclock-8: closer, for the smaller court; the behind camera stands 7.3 m behind the net, 2.9 m high)
    CAMS = (([0.0, -0.4, 1.7], 7.0, 90.0, -10.0),         # behind and above the robot's baseline, looking down the court
            ([0.0, -0.6, 1.9], 7.0, 0.0, -6.0))           # at the side of the court (x < 0), looking along +x
    VIEW_BACK = (0, 3, 6, 9)                              # snapshots back from the latest: 0, 60, 120, 180 ms
    TILE = (480, 360)

    def __init__(self, level: int = 1, lv_override: dict | None = None):
        self.level = int(level)
        self.lv = dict(LEVELS.get(self.level, LEVELS[1]))
        if lv_override:
            self.lv.update(lv_override)
        if os.environ.get("MATCH_SEED"):           # other instances of the same level: serves + opponent + scatter
            self.lv["seed"] = int(os.environ["MATCH_SEED"])
        self.s = Phys()
        self.s.reset(np.r_[HOME, Q0_ARM])
        self._twin = None
        self.score = [0, 0]
        self.points: list[dict] = []
        self.legs: list[dict] = []
        self.results: list[dict] = []
        self.shots: list[dict] = []
        self.hist: deque = deque(maxlen=16)
        self.done = False
        self.winner = None                         # 0 you, 1 the opponent (set when the match ends)
        self.hits = 0                              # hits in the match, both sides (the MAX_HITS cap)
        self.phase = "swing"
        self.plan, self.plan_j, self._rec = [], 0, {}
        self._adj_k = None
        self.n_our_legs = 0
        self._start_point(hold_from=0)

    @property
    def k(self) -> int:
        return self.s.k

    # ------------------------------------------------------------------ points / legs
    def next_server(self) -> int:
        """0 (you) or 1 (the opponent): you serve the first point (Law 6: the toss is fixed in this format); then the
        winner of the last rally serves (Law 10.3); after a let the same player serves again (Law 14.3)."""
        if not self.points:
            return 0
        last = self.points[-1]
        if last.get("let"):
            return last["server"]
        return 0 if last["winner"] == "you" else 1

    def _start_point(self, hold_from: int):
        self.hist.clear()          # camera history (display only): no frames of the previous point in the next views
        n = len(self.points)
        server = self.point_server = self.next_server()
        right = self.score[server] % 2 == 0          # the server's right court when its score is even (Law 10.1)
        self.home = serve_spot(right)                # both robots in their right (left) courts, diagonally (Law 9.1.3)
        self.spot = self.home.copy()                 # the serve spot (the standing-still judgement, Law 9.1.4)
        if server == 1:
            # the opponent serves from its right court when its own score is even (BWF 10.1.1), diagonally to us
            typ, p0, v, right = serve_plan([self.lv["seed"]], n, self.score[1], self.home, self._reachable, self.lv)
            sx = float(p0[0])
            self.leg = {"kind": "serve", "serve": typ, "point": n, "hold_from": hold_from, "server": 1,
                        "launch": hold_from + READY_STEPS, "state": "incoming", "p0": p0.tolist(),
                        "v0": [float(x) for x in v], "service_court_right": right}
            # the server stands at its serving spot and walks home from the moment it serves
            self.opp = {"xy0": np.array([sx, 2.7 * COURT_SCALE]), "k0": hold_from + READY_STEPS, "txy": OPP_HOME.copy(),
                        "speed": min(self.lv["recover"], BASE_VMAX)}
        else:
            # you serve: READY_STEPS after play resumes the opponent is ready and you may toss the shuttle
            ready = hold_from + READY_STEPS
            self.leg = {"kind": "our_serve", "point": n, "hold_from": hold_from, "server": 0, "launch": ready,
                        "ready": ready, "deadline": ready + SERVE_WINDOW_STEPS, "state": "held",
                        "service_court_right": right}
            # the opponent receives in its diagonal service court (its right court is x < 0 in your frame) and
            # stands still until the serve is delivered
            spot = np.array([(-0.45 if right else 0.45) * COURT_SCALE, OPP_HOME[1]])
            self.opp = {"xy0": spot, "k0": hold_from, "txy": spot.copy(), "speed": 0.0}
            p0 = np.r_[self.home + np.array([-0.25, 0.35]), 1.0]   # held in the server's (missing) free hand
            v = np.zeros(3)
        self.legs.append(self.leg)
        self._new_leg()
        self.s.sh_p = tuple(float(x) for x in p0); self.s.sh_v = tuple(float(x) for x in v); self.s.sh_live = False
        self._go_home()

    def _go_home(self):
        """Before every serve: the robot at its spot in its service court (its home for the point) in the ready pose,
        at rest, no command (as in the duel)."""
        ph = self.s
        q = np.r_[self.home, Q0_ARM]
        ph.d.qpos[ph.qa] = q; ph.d.qvel[ph.va] = 0.0
        mj.mj_forward(ph.m, ph.d)
        ph.reset_servo()
        ph.target = q.copy()
        self.plan, self.plan_j = [], 0
        self._last_act = None; self._q_hit_active = None
        self._since_reset = 0

    def toss(self, p, h=0.0):
        """Your serve: the shuttle appears at p (your frame) now and rises h straight up (0: from rest). Raises
        ValueError if not allowed."""
        leg = self.leg
        if self.done or leg["kind"] != "our_serve":
            raise ValueError("it is not your serve")
        if leg["state"] != "held":
            raise ValueError("the shuttle was already tossed")
        if self.k < leg["ready"]:
            raise ValueError(f"the opponent is not ready before step {leg['ready']}")
        why = toss_problem(p, h, self.s.d.qpos[self.s.qa[:2]])
        if why:
            raise ValueError(why)
        self.s.sh_p = tuple(float(x) for x in p); self.s.sh_v = (0.0, 0.0, toss_vz(h))
        self.s.sh_live = True; self.s.hit_enabled = True
        leg["state"] = "falling"; leg["toss_k"] = self.k; leg["launch"] = self.k
        leg["toss"] = [round(float(x), 4) for x in p]; leg["toss_height"] = float(h)

    def delivered(self) -> bool:
        """The serve of the current point was delivered (hit, missed or faulted)."""
        leg = self.leg
        if leg["kind"] == "our_serve":
            return leg["state"] not in ("held", "falling")
        if leg["kind"] == "serve":
            return self.k >= leg["launch"]
        return True

    def _new_leg(self):
        self.s.events.clear()
        self.s.hit_enabled = False
        self._opp_plan_k = None

    def in_play(self) -> bool:
        return self.k >= self.leg["launch"]

    def t_since_launch(self) -> float:
        return round((self.k - self.leg["launch"]) * CONTROL_DT, 6)

    # ------------------------------------------------------------------ the opponent
    def opp_xy(self, k=None) -> np.ndarray:
        k = self.k if k is None else k
        o = self.opp
        dt = max(0.0, (k - o["k0"]) * CONTROL_DT)
        e = o["txy"] - o["xy0"]; dist = float(np.hypot(e[0], e[1]))
        if dist < 1e-9:
            return o["xy0"].copy()
        return o["xy0"] + e / dist * min(dist, o["speed"] * dt)

    def _opp_plan(self):
        """`reaction_s` after our hit: predict the flight, choose the interception point, start moving."""
        leg = self.leg
        P, V = predict(self.s.sh_p, self.s.sh_v)
        o = self.opp_xy()
        last = P[-1]
        if leg["kind"] == "our_serve":               # a serve must land in the opponent's diagonal service court
            lands_in = bool(last[2] <= 1e-9 and in_service_court(-last[0], -last[1], leg["service_court_right"]))
        else:
            lands_in = bool(last[2] <= 1e-9 and in_court(last[0], last[1], +1))
        leg["opp_x_react"] = [round(float(x), 3) for x in o]
        if not lands_in:
            leg["opp_leave"] = True
            return
        pred = read_pattern(getattr(self, "our_lands", [])) if self.lv.get("read", 0.0) > 0.0 else None
        prepared = (leg["kind"] != "our_serve" and pred is not None
                    and float(np.hypot(last[0] - pred[0], last[1] - pred[1])) <= READ_HIT)
        leg["opp_read"] = bool(prepared)
        if leg["kind"] != "our_serve":               # it remembers where your last shots were going (anticipate)
            self.our_lands = (getattr(self, "our_lands", []) + [[float(last[0]), float(last[1])]])[-READ_N:]
        idx = np.arange(9, len(P), 10)
        j = (idx + 1) // 10
        Pc, sp = P[idx], np.linalg.norm(V[idx], axis=1)
        ok = (Pc[:, 1] > 0.3) & (Pc[:, 2] >= OPP_Z[0]) & (Pc[:, 2] <= OPP_Z[1])
        # it is a robot too (revision wallclock-8): it needs min_t after your hit to meet the shuttle (your arm, held
        # to the Panda's limits, needs about 0.9 s)
        ok &= j * CONTROL_DT + self.lv["reaction_s"] >= self.lv["min_t"]     # (this runs reaction_s after your hit)
        if not ok.any():
            leg["opp_leave"] = True
            leg["opp_miss"] = (f"too quick: the opponent needs {self.lv['min_t']:.2f} s from your hit to meet the "
                               "shuttle" if ((Pc[:, 1] > 0.3) & (Pc[:, 2] >= OPP_Z[0])).any() else
                               "the shuttle never came into the opponent's hitting range")
            return
        lv = self.lv
        dist = np.hypot(Pc[:, 0] - o[0], Pc[:, 1] - o[1])
        t = j * CONTROL_DT
        # the position pressure (revision wallclock-10): the opponent's base travels max(0, distance - reach) at `chase`
        # m/s and its arm then needs `swing` s to strike (a robot's stroke is planned ahead, as yours); the slack left
        # is t - travel / chase - swing: no slack is out of reach, less than `window` s of slack is pressure
        # (the base study) the opponent's base obeys the same limits as yours: its travel takes base_time()
        travel = np.maximum(0.0, dist - lv["reach"])
        tmove = np.array([base_time(float(d)) if d > 0 else 0.0 for d in travel])
        if lv.get("chase"):
            tmove = np.maximum(tmove, travel / lv["chase"])
        # (revision wallclock-11) a shot it read (it lands within READ_HIT of the predicted spot): its stroke is
        # prepared, the arm needs only `block` s
        sw = lv.get("block", lv["swing"]) if prepared else lv["swing"]
        slack = t - tmove - sw
        pp = np.maximum(0.0, lv["window"] - slack) / lv["window"]
        if lv.get("block"):                          # (revision wallclock-11) a block needs only `block` s of the arm:
            late = slack + sw - lv["block"]  # a shuttle it meets too late for a full stroke is blocked (a weak
            pp = np.where(slack >= 0, pp, np.where(late >= 0, np.minimum(pp, 0.95), 1.0 - late / lv["window"]))
            slack = np.where(slack >= 0, slack, np.minimum(0.0, late))     # lift); too late for a block is a miss
        ps = (sp - SPEED_FREE) / (lv["max_speed"] - SPEED_FREE)
        pr = np.where(ok, np.maximum(pp, ps), np.inf)
        pmin = float(pr.min())
        near = pr <= pmin + 0.05
        if pmin <= 1.0:                              # (revision wallclock-11) never a point it would miss when it can
            near &= pr <= 1.0                        # make another (it took a slightly-too-early point before)
        js = int(np.nonzero(near)[0][0])
        if pmin < PRESSURE_PASSIVE:                  # (revision wallclock-11) with time to attack it takes the shuttle
            att = np.nonzero(pr < PRESSURE_PASSIVE)[0]   # as high as it can (an overhead attack, not off the floor)
            js = int(att[np.argmax(Pc[att, 2])])
        leg["opp_hit_k"] = self.k + int(j[js])
        leg["opp_pressure"] = round(float(pr[js]), 3)
        leg["opp_gap"] = round(float(max(0.0, -slack[js])), 3)          # seconds short (0: in time)
        leg["opp_speed_in"] = round(float(sp[js]), 2)
        self.opp = {"xy0": o, "k0": self.k, "txy": Pc[js, :2].copy(),
                    "speed": min(lv.get("chase") or BASE_VMAX, BASE_VMAX)}

    def _opp_ready_spot(self) -> np.ndarray:
        """Where the opponent waits for your next shot: home, moved `anticipate` of the way towards the mean landing
        point of your last ANTICIPATE_N shots (within ANTICIPATE_BOX of its half)."""
        lands = getattr(self, "our_lands", [])
        a = float(self.lv.get("anticipate", 0.0))
        if not lands or a <= 0.0:
            return OPP_HOME.copy()
        tgt = OPP_HOME + a * (np.mean(np.asarray(lands, float)[-ANTICIPATE_N:], axis=0) - OPP_HOME)
        rd = read_pattern(lands)
        if rd is not None and self.lv.get("read", 0.0) > 0.0:     # a pattern it has read: it waits for the next shot
            tgt = OPP_HOME + float(self.lv["read"]) * (rd - OPP_HOME)
        return np.clip(tgt, ANTICIPATE_BOX[0], ANTICIPATE_BOX[1])

    def _opp_hit(self):
        leg = self.leg
        p = np.array(self.s.sh_p)
        pr = leg["opp_pressure"]
        rec = {"k": self.k, "pos": [round(float(x), 3) for x in p], "opp_xy": [round(float(x), 3) for x in self.opp_xy()],
               "pressure": pr, "gap": leg.get("opp_gap"), "speed_in": leg.get("opp_speed_in")}
        leg["opp"] = rec
        if pr > 1.0:
            gap = leg.get("opp_gap", 0.0)
            why = (f"out of reach: the opponent was {gap:.2f} s late to the shuttle"
                   if gap > 0 else
                   f"too fast: the shuttle arrived at {leg.get('opp_speed_in'):.1f} m/s (it handles up to "
                   f"{self.lv['max_speed']:.0f} m/s)")
            leg["opp_miss"] = why; rec["missed"] = why
            return
        mode = "weak" if pr > PRESSURE_WEAK else ("attack" if pr < PRESSURE_PASSIVE else "normal")
        rec["mode"] = mode
        shot, v, target = self._opp_return(p, mode)
        rec.update(shot=shot, target=[round(float(x), 3) for x in target], speed=round(float(np.linalg.norm(v)), 2))
        self._close_our_leg(True, f"good: the opponent played it ({mode} return, a {shot})")
        self.hits += 1
        self.s.sh_v = tuple(float(x) for x in v)
        leg["state"] = "done"
        # it recovers towards home at `recover` m/s once its stroke's follow-through is over (`follow` s: its base does
        # not move meanwhile; revision wallclock-10), so where it played from tells where it is when you hit
        # (revision wallclock-10) It recovers not to the middle but towards where your last shots went: `anticipate`
        # of the way from home to the mean of your last ANTICIPATE_N shots' landing points (it reads your habits)
        self.opp = {"xy0": self.opp_xy(), "k0": self.k + int(round(self.lv.get("follow", 0.0) / CONTROL_DT)),
                    "txy": self._opp_ready_spot(), "speed": min(self.lv["recover"], BASE_VMAX)}
        if self.lv.get("read", 0.0) > 0.0 and read_pattern(getattr(self, "our_lands", [])) is not None:
            self.opp["speed"] = BASE_VMAX            # (revision wallclock-11) a pattern it has read: it commits early
        self.leg = {"kind": "return", "shot": shot, "point": len(self.points), "launch": self.k, "state": "incoming",
                    "opp_hit_pos": rec["pos"]}
        self.legs.append(self.leg)
        self._new_leg()
        self.s.hit_enabled = True

    def _opp_return(self, p, mode):
        lv = self.lv
        rng = np.random.default_rng([lv["seed"], len(self.points), len(self.legs)])
        u = rng.uniform(-1, 1, 5)
        side = 1.0 if u[0] >= 0 else -1.0
        # (the base study) it plays to the side away from your base when it can (`open_side` of the time): where you
        # wait matters
        bx = float(self.s.d.qpos[self.s.qa[0]])
        if abs(bx) > 0.05 and 0.5 * (u[4] + 1.0) < lv.get("open_side", 0.0):
            side = -1.0 if bx > 0 else 1.0
        high = p[2] >= 1.9
        W = lv["width"]
        S = COURT_SCALE                            # the BWF-court depths of the legacy opponent, scaled
        by = float(self.s.d.qpos[self.s.qa[1]])
        if mode != "weak" and by > LOB_FWD_Y and not (mode == "attack" and high) and 0.5 * (u[3] + 1.0) < lv.get("lob", 0.0):
            mode = "lob"                           # your base stands forward: it lifts the shuttle over your head
        if mode == "lob":
            plan = [("clear", side * W * abs(u[0]) ** 0.5, (-5.9 + 0.3 * u[1]) * S, SHOT_VMAX["clear"])]
        elif mode == "weak":
            plan = [("lift", 0.35 * S * u[0], (-3.9 + 0.4 * u[1]) * S, SHOT_VMAX["lift"])]
        elif mode == "attack":
            if high:
                plan = [("smash", side * W, (-3.3 + 0.5 * u[1]) * S, lv["pace"])]
            elif u[1] > 0:
                plan = [("drop", side * W, -1.2 * S, SHOT_VMAX["drop"])]
            else:
                plan = [("push", side * W, -6.0 * S, SHOT_VMAX["push"])]
        else:
            x = side * W * abs(u[0]) ** 0.5
            if high and u[3] > 0.5:
                plan = [("smash", x, (-3.6 + 0.4 * u[1]) * S, 0.8 * lv["pace"])]
            elif u[2] < -0.1:
                plan = [("clear", x, (-5.9 + 0.3 * u[1]) * S, SHOT_VMAX["clear"])]
            elif u[2] < 0.5:
                plan = [("drop", x, (-1.7 + 0.3 * u[1]) * S, SHOT_VMAX["drop"])]
            else:
                plan = [("drive", x, (-4.6 + 0.4 * u[1]) * S, SHOT_VMAX["drive"])]
        # (the base study) its shots are within reach of a robot waiting in the middle of your court (HOME), not of
        # wherever your base is: where you wait is your decision, and a poor waiting position costs you
        base = HOME.copy()
        typ, tx, ty, vmax = plan[0]
        kp = lv.get("kill", 0.0) * (1.0 if mode == "attack" else 0.5 if mode == "normal" else 0.0)
        if kp > 0.0 and rng.uniform() < kp:          # (revision wallclock-11) a winner it goes for (in an attack with
            # probability kill, in a normal return with half that): without the reach guarantee, the shot among a few
            # (to the corners and sides away from your base, short and deep; a smash from a high contact) that leaves
            # your robot the least time from where its base stands
            ours = np.array([bx, by])
            ks = -1.0 if bx > 0 else 1.0
            cands = [("drop", (ks * 0.9 * COURT_X, -0.75)), ("push", (ks * 0.9 * COURT_X, -5.9 * S)),
                     ("drive", (ks * 0.9 * COURT_X, -3.5 * S)), ("drop", (-ks * 0.9 * COURT_X, -0.75)),
                     ("push", (-ks * 0.9 * COURT_X, -5.9 * S))]
            if high:
                cands = [("smash", (ks * 0.85 * COURT_X, -3.3 * S)), ("smash", (-ks * 0.85 * COURT_X, -3.3 * S))] + cands
            best = None
            for t2, tg in cands:
                for c in solve_shots(p, tg, SHOT_THETAS[t2], SHOT_VMAX[t2])[:2]:
                    mg = self._margin(p, c[2], ours)
                    if mg is not None and (best is None or mg < best[0]):
                        best = (mg, t2, c[2], tg)
            if best:
                return best[1], best[2], best[3]
        for frac, t2 in ((1.0, typ), (0.6, typ), (0.3, typ), (0.6, "clear"), (0.0, "clear"), (0.0, "lift")):
            vm = vmax if t2 == typ else SHOT_VMAX[t2]
            tyy = ty if t2 == typ else (-5.6 * S if t2 == "clear" else -4.0 * S)
            cs = solve_shots(p, (tx * frac, tyy), SHOT_THETAS[t2], vm)
            if t2 == "clear":                      # a clear passes over a robot at the net (above LOB_Z there) if it can
                cs = sorted(cs, key=lambda c: not over_the_net_player(p, c[2]))
            for c in cs:
                if self._reachable(p, c[2], base):
                    return t2, c[2], (tx * frac, tyy)
        c = solve_shots(p, (0.0, -4.0 * S), SHOT_THETAS["lift"] + (70, 40, 30), SHUTTLE_VMAX)
        v = c[0][2] if c else np.array([0.0, -5.0, 8.0])
        return "lift", v, (0.0, -4.0 * S)

    def _margin(self, p0, v, base):
        """How much time your robot standing at `base` has to spare for this flight (the best point REACH_Z high in
        your court: time there - its base's travel time to that point's stance), or None if it lands out."""
        P, _ = predict(p0, v)
        if len(P) == 0 or P[-1][2] > 1e-9 or not in_court(P[-1][0], P[-1][1], -1):
            return None
        best = -np.inf
        for i in range(19, len(P) - 20, 20):
            q = P[i]
            if REACH_Z[0] <= q[2] <= REACH_Z[1] and q[1] < -0.5:
                best = max(best, (i + 1) * PHYS_DT - base_time(float(np.hypot(*(stance(q) - base)))))
        return best

    def _reachable(self, p0, v, base) -> bool:
        """Our robot can meet this flight: a point REACH_Z high inside our court, >= REACH_T s after the shot, whose
        stance the base can reach in time (REACH_KEEP s kept for the decision and the swing). Revision wallclock-8:
        the arm held to the Panda's limits delivers a stroke reliably about 0.9 s ahead (legacy: 0.5-2.5 m, 0.55 s,
        0.45 s)."""
        P, _ = predict(p0, v)
        if len(P) == 0 or P[-1][2] > 1e-9 or not in_court(P[-1][0], P[-1][1], -1):
            return False
        idx = np.arange(int(REACH_T / PHYS_DT) - 1, len(P) - 20, 20)
        for i in idx:
            q = P[i]
            if not (REACH_Z[0] <= q[2] <= REACH_Z[1] and q[1] < -0.5):
                continue
            st = stance(q)
            if base_time(float(np.hypot(*(st - base)))) <= (i + 1) * PHYS_DT - self.lv.get("reach_keep", REACH_KEEP):
                return True
        return False

    # ------------------------------------------------------------------ stepping (shared by live and replay)
    def step(self, q):
        self.s.step(q)
        self._since_reset = getattr(self, "_since_reset", 0) + 1
        leg = self.leg
        if leg["kind"] == "serve" and leg["state"] == "incoming" and self.k == leg["launch"]:
            self.s.sh_live = True; self.s.hit_enabled = True
        self._referee()
        if self.k % CAM_EVERY == 0:
            self.hist.append({"k": self.k, "t": self.t_since_launch(), "qpos": self.s.d.qpos.copy(),
                              "sh": self.s.sh_p, "shv": self.s.sh_v, "opp": self.opp_xy().copy()})

    def _referee(self):
        if self.done:
            return
        leg, s = self.leg, self.s
        kinds = [e["kind"] for e in s.events]
        if not self.delivered():
            moved = float(np.hypot(*(s.d.qpos[s.qa[:2]] - getattr(self, "spot", self.home))))
            if moved > BASE_TOL:                        # Law 9.1.4: both players stand still until the serve
                who = "serve_fault:moved" if leg["kind"] == "our_serve" else "receive_fault:moved"
                self._close_our_leg(False, f"{who}: your base moved {moved:.2f} m from its spot before the serve was "
                                           "delivered (Law 9.1.4)")
                self._end_point(1, self.results[-1]["summary"])
                return
        if leg["kind"] == "our_serve" and leg["state"] in ("held", "falling"):
            if leg["state"] == "held":
                if self.k >= leg["deadline"]:
                    self._close_our_leg(False, f"serve_fault:undue_delay: you did not toss the shuttle within "
                                               f"{SERVE_WINDOW_STEPS * CONTROL_DT:.0f} s (undue delay, Law 9.1.1)")
                    self._end_point(1, self.results[-1]["summary"])
                return
            if "hit" in kinds:
                e = next(e for e in s.events if e["kind"] == "hit")
                leg["hit"] = e; self.hits += 1
                if e["pos"][2] > SERVE_MAX_Z:
                    self._close_our_leg(False, f"serve_fault:too_high: you hit the shuttle {e['pos'][2]:.2f} m high, above "
                                               f"{SERVE_MAX_Z} m (Law 9.1.6)")
                    self._end_point(1, self.results[-1]["summary"])
                elif e["v_out"][2] <= 0.0:
                    self._close_our_leg(False, "serve_fault:not_upwards: the serve did not go upwards from your racket (Law 9.1)")
                    self._end_point(1, self.results[-1]["summary"])
                else:
                    leg["state"] = "to_opp"; leg["delivered_k"] = self.k
                    self._opp_plan_k = self.k + int(round(self.lv["reaction_s"] / CONTROL_DT))
                return
            if "land" in kinds or self.k - leg["launch"] >= LEG_STEPS:
                self._close_our_leg(False, "serve_fault:missed: you missed the shuttle (Law 9.1.8)")
                self._end_point(1, self.results[-1]["summary"])
            return
        if leg["state"] == "incoming":
            if "hit" in kinds:
                e = next(e for e in s.events if e["kind"] == "hit")
                leg["hit"] = e; leg["state"] = "to_opp"; self.hits += 1
                self._opp_plan_k = self.k + int(round(self.lv["reaction_s"] / CONTROL_DT))
                return
            if "net" in kinds:                          # never seen: serves and returns are solved over the net
                e = next(x for x in s.events if x["kind"] == "net")
                what = "serve_fault:net: the opponent's serve" if leg["kind"] == "serve" else "the opponent's shot"
                self._close_our_leg(True, f"{what} hit the net (x={e['x']:.2f}, height {e['z']:.2f} m)")
                self._end_point(0, self.results[-1]["summary"])
                return
            if "land" in kinds:
                e = next(x for x in s.events if x["kind"] == "land")
                if leg["kind"] == "serve" and not in_service_court(e["x"], e["y"], leg["service_court_right"]):
                    self._close_our_leg(True, f"serve_fault:out: the opponent's serve landed outside your service court "
                                              f"(x={e['x']:.2f}, y={e['y']:.2f})")
                    self._end_point(0, self.results[-1]["summary"])
                elif in_court(e["x"], e["y"], -1):
                    self._close_our_leg(False, f"missed: the shuttle landed in your court at x={e['x']:.2f}, y={e['y']:.2f}")
                    self._end_point(1, self.results[-1]["summary"])
                else:
                    self._close_our_leg(True, f"the opponent's shot landed out (x={e['x']:.2f}, y={e['y']:.2f})")
                    self._end_point(0, self.results[-1]["summary"])
            elif self.in_play() and self.k - leg["launch"] >= LEG_STEPS:
                self._close_our_leg(False, "missed"); self._end_point(1, "missed")
            return
        if leg["state"] == "to_opp":
            serve = leg["kind"] == "our_serve"
            if "net" in kinds:
                e = next(x for x in s.events if x["kind"] == "net")
                what = "serve_fault:net: your serve" if serve else "fault: your shot"
                self._close_our_leg(False, f"{what} hit the net (x={e['x']:.2f}, height {e['z']:.2f} m)")
                self._end_point(1, self.results[-1]["summary"])
                return
            if "land" in kinds:
                e = next(x for x in s.events if x["kind"] == "land")
                if e["y"] < 0:
                    self._close_our_leg(False, f"fault: your shot came down on your own side (x={e['x']:.2f}, y={e['y']:.2f})")
                    self._end_point(1, self.results[-1]["summary"])
                elif serve and not in_service_court(-e["x"], -e["y"], leg["service_court_right"]):
                    self._close_our_leg(False, f"serve_fault:out: your serve landed outside the opponent's service court "
                                               f"at x={e['x']:.2f}, y={e['y']:.2f} (the opponent let it go)")
                    self._end_point(1, self.results[-1]["summary"])
                elif serve or in_court(e["x"], e["y"], +1):
                    why = leg.get("opp_miss") or "the opponent could not reach it"
                    self._close_our_leg(True, f"winner: landed in at x={e['x']:.2f}, y={e['y']:.2f} ({why})")
                    self._end_point(0, self.results[-1]["summary"])
                else:
                    self._close_our_leg(False, f"fault: your shot landed out at x={e['x']:.2f}, y={e['y']:.2f} "
                                               "(the opponent let it go)")
                    self._end_point(1, self.results[-1]["summary"])
                return
            if self._opp_plan_k is not None and self.k == self._opp_plan_k:
                self._opp_plan()
            if leg.get("opp_hit_k") == self.k and "opp_miss" not in leg:
                self._opp_hit()
            elif self.k - leg["launch"] >= 3 * LEG_STEPS:
                self._close_our_leg(False, "?"); self._end_point(1, "timeout")

    def _close_our_leg(self, ok, summary):
        leg = self.leg
        if leg.get("closed"):
            return
        leg["closed"] = True
        h = leg.get("hit")
        res = {"leg": self.n_our_legs, "point": len(self.points), "kind": leg["kind"], "returned": bool(ok),
               "summary": summary, "hit": int(h is not None), "speed_out": None if h is None else h["speed"],
               "offcentre": None if h is None else h["offcentre"], "step": self.k}
        self.results.append(res)
        self.n_our_legs += 1

    def match_over(self) -> bool:
        """First to SINGLE_WIN_POINTS; from 10-10 a two-point lead is needed; the first to SINGLE_CAP_POINTS wins."""
        hi, lo = max(self.score), min(self.score)
        return (hi >= SINGLE_WIN_POINTS and hi - lo >= 2) or hi >= SINGLE_CAP_POINTS

    def _end_point(self, winner, how: str):
        """winner 0 (you), 1 (the opponent) or None (a let: the point is replayed)."""
        if winner is not None:
            self.score[winner] += 1
        self.points.append({"point": len(self.points), "winner": None if winner is None else
                            ("you" if winner == 0 else "opponent"), "how": how, "score": list(self.score),
                            "step": self.k, "let": winner is None, "server": self.point_server})
        self.leg["state"] = "done"
        if self.match_over():
            self.winner = 0 if self.score[0] > self.score[1] else 1
            self.done = True
            return
        if getattr(self, "hits", 0) >= MAX_HITS or len(self.points) >= MAX_POINTS:
            # the cap: the leader wins; if level, the winner of the last point (no draws)
            last = next((p["winner"] for p in reversed(self.points) if p["winner"]), "opponent")
            self.winner = (0 if self.score[0] > self.score[1] else 1 if self.score[1] > self.score[0]
                           else 0 if last == "you" else 1)
            self.points[-1]["cap"] = True
            self.done = True
            return
        self._start_point(hold_from=self.k)

    def replay(self, actions) -> None:
        for q in actions:
            self.step(q)

    # ------------------------------------------------------------------ live control
    def _target_vel(self):
        a = self.s._actions
        return (a[-1] - a[-2]) / CONTROL_DT if len(a) >= 2 and getattr(self, "_since_reset", 2) >= 2 else np.zeros(9)

    def _target_acc(self):
        """The base targets' acceleration over the last three steps (the go-to generator's jerk limit starts from it)."""
        a = self.s._actions
        ok = len(a) >= 3 and getattr(self, "_since_reset", 3) >= 3
        return (a[-1][:2] - 2 * a[-2][:2] + a[-3][:2]) / CONTROL_DT ** 2 if ok else np.zeros(2)

    def _ready_target(self):
        """Service-driven recovery: the arm back to the ready pose (READY_SPEED of its speed limits; the setpoint
        generator keeps it within the acceleration limits), the base to its home (the point's spot, serve_spot)."""
        tgt = self.s.target
        lim = ARM_VEL * CONTROL_DT * READY_SPEED
        arm = tgt[2:] + np.clip(Q0_ARM - tgt[2:], -lim, lim)
        b, _ = base_goto(tgt[:2], self._target_vel()[:2], self.home, self._target_acc())
        return np.r_[b, arm]

    def _arm_target(self):
        if self.plan_j < len(self.plan):
            q = self.plan[self.plan_j]; self.plan_j += 1
            return q
        return self._ready_target()

    def decision_due(self) -> bool:
        leg = self.leg
        if self.done or leg["state"] != "incoming" or not self.in_play():
            return False
        if any(e["kind"] == "hit" for e in self.s.events):
            return False
        if self.phase == "swing":
            return self.k - leg["launch"] >= SWING_AFTER
        return self._adj_k is not None and self.k >= self._adj_k

    def run_to_decision(self) -> None:
        self.phase = "swing"
        while not self.done:
            if self.decision_due():
                return
            self.step(self._arm_target())

    def shot(self, decision: dict, delay_steps: int) -> dict:
        leg_i = self.n_our_legs
        rec = {"leg": leg_i, "decision": decision, "delay_steps": int(delay_steps), "k_decision": self.k}
        for _ in range(delay_steps):
            if self.leg["state"] != "incoming" or self.done:
                break
            self.step(self._arm_target())
        rec["k_exec"] = self.k
        self._adj_k = None
        if decision.get("type") == "swing" and self.leg["state"] == "incoming" and not self.done:
            self._ik_seed = None
            # the racket state at contact only (P1: the aim-based legacy stroke, plan_stroke, was removed)
            self.plan, info = self.plan_racket(float(decision["t"]), decision["pos"], decision["normal"],
                                               decision["vel"])
            self.plan_j = 0
            rec.update(info)
            if self.plan and info.get("k_hit") is not None and info["k_hit"] - ADJUST_BEFORE >= self.k + 5:
                self._adj_k = info["k_hit"] - ADJUST_BEFORE
        self._rec = rec
        if decision.get("type") == "swing" and self._adj_k is not None:
            self.phase = "adjust"
            while not self.done and self.n_our_legs == leg_i:
                if self.decision_due():
                    return {"phase": "adjust", **{k: rec[k] for k in rec if k != "decision"}}
                self.step(self._arm_target())
        return self._after_leg(rec, leg_i)

    def adjust(self, decision: dict, delay_steps: int) -> dict:
        rec, leg_i = self._rec, self.n_our_legs
        rec["adjust"] = decision
        rec["adjust_delay_steps"] = int(delay_steps)
        for _ in range(delay_steps):
            if self.n_our_legs != leg_i or self.done:
                break
            self.step(self._arm_target())
        if decision.get("type") == "adjust" and self.n_our_legs == leg_i and not self.done \
                and self.leg["state"] == "incoming":
            self._ik_seed = rec.get("_q_hit")
            plan, info = self.plan_racket(float(decision["t"]), decision["pos"], decision["normal"], decision["vel"])
            q_hit = info.pop("_q_hit", None)
            rec["adjust_info"] = info
            if plan:
                rec["_q_hit"] = q_hit
                self.plan, self.plan_j = plan, 0
        return self._after_leg(rec, leg_i)

    # ------------------------------------------------------------------ real-time protocol (no decision points)
    def rt_advance(self, n_steps: int):
        """Run up to n_steps control steps with the current command (the planned stroke, then the return to ready);
        stops early when a point ends (the command is then dropped). Returns (steps run, points, our results)."""
        n0, r0, n = len(self.points), len(self.results), 0
        while n < n_steps and not self.done and len(self.points) == n0:
            self.step(self._arm_target()); n += 1
        if len(self.points) > n0:
            self.plan, self.plan_j = [], 0
            self._last_act = None
        return n, self.points[n0:], self.results[r0:]

    def rt_act(self, T, pos, nrm, vel, base=None) -> dict:
        """A new command: the racket state at contact T s from now, planned from the robot's current motion; it
        replaces the stroke under way (the hit configuration of the replaced stroke seeds the IK)."""
        t_hit = (self.k - self.leg["launch"]) * CONTROL_DT + float(T)
        self._ik_seed = getattr(self, "_q_hit_active", None) if self.plan_j < len(self.plan) else None
        plan, info = self.plan_racket(t_hit, pos, nrm, vel, base)
        q_hit = info.pop("_q_hit", None)
        info["T_from_now"] = round(float(T), 4)
        if plan:
            self.plan, self.plan_j = plan, 0
            self._q_hit_active = q_hit
        self.shots.append({"k": self.k, "leg": self.n_our_legs, **info})
        self._last_act = info
        return info

    def rt_clear(self):
        self.plan, self.plan_j = [], 0
        self._last_act = None
        self.home = self.s.target[:2].copy()     # (the base study) the base stays where it is

    def move(self, base):
        """`move`: where the base waits (it goes there once no stroke is under way; a stroke under way finishes)."""
        self.home = np.clip(np.asarray(base, float), BASE_LO, BASE_HI)
        return [round(float(x), 3) for x in self.home]

    def _after_leg(self, rec, leg_i) -> dict:
        n0 = len(self.points)
        while not self.done and self.n_our_legs == leg_i:
            self.step(self._arm_target())
        rec.pop("_q_hit", None)
        self.shots.append(rec)
        res = dict(self.results[leg_i]) if leg_i < len(self.results) else {"summary": "match over"}
        self.run_to_decision()
        res["points_finished"] = self.points[n0:]
        return res

    # ------------------------------------------------------------------ stroke controller
    def _twin_phys(self) -> Phys:
        if self._twin is None:
            self._twin = Phys()
            self._twin.reset(self.s.target)
        return self._twin

    def _base_plan(self, goal, n):
        """n base targets of the go-to generator from the current base target/velocity towards goal; and the step
        index at which it has arrived, within BASE_ARRIVE (None if not within n; it settles exactly later)."""
        b = self.s.target[:2].copy(); v = self._target_vel()[:2].copy(); acc = self._target_acc()
        out, arrived = [], None
        for i in range(n):
            v0 = v
            b, v = base_goto(b, v, goal, acc)
            acc = (v - v0) / CONTROL_DT
            out.append(b.copy())
            if arrived is None and float(np.hypot(*(b - goal))) < BASE_ARRIVE:
                arrived = i
        return out, arrived

    def _stroke_for(self, v_in, v_out, p_hit, bxy, seed):
        ph = self.s
        sp = float(np.linalg.norm(v_out)); nrm = v_out / sp
        vin_n = float(v_in @ nrm)
        u = max(0.05, (sp - E_SHUTTLE * max(0.0, -vin_n)) / RACKET_GAIN)
        v_p = u * nrm
        best = None
        for sgn in (1.0, -1.0):
            q_h, res = ik(ph, p_hit, sgn * nrm, bxy, seed)
            if best is None or res < best[1] - 1e-6:
                best = (q_h, res)
        q_h, res = best
        Jp = ph.jac(np.r_[bxy, q_h])[:3]
        Winv = np.diag(ARM_VEL_OP ** 2)
        qd_h = Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T + 1e-9 * np.eye(3), v_p)
        ratio = float(np.max(np.abs(qd_h) / ARM_VEL_OP))
        return dict(nrm=nrm, v_p=v_p, q_h=q_h, qd_h=qd_h, ik=res, ratio=ratio, v_out=v_out, u=u,
                    p_hit=np.asarray(p_hit, float))

    RACKET_SCATTER = dict(pos=0.006, ang_deg=0.8, speed=0.03)   # execution scatter of the racket state at contact

    def plan_racket(self, t_hit, p_c, nrm, v_p, base=None):
        """_plan_racket, with the rehearsals' shared start kept for this plan only (_simulate_arm)."""
        self._sim_ck = None
        try:
            return self._plan_racket(t_hit, p_c, nrm, v_p, base)
        finally:
            self.__dict__.pop("_sim_ck", None)

    def _plan_racket(self, t_hit, p_c, nrm, v_p, base=None):
        """Racket-level decision: the player gives the racket state at contact (time t_hit s after the shuttle was
        played, head centre p_c, string-face normal nrm, head velocity v_p). The controller only makes the robot
        deliver it: the base to the forehand stance for p_c (or as far as it gets), IK, a speed-weighted Jacobian
        inverse, a joint-speed-limited cubic swing and robot-only rehearsals that correct the PD lag. It uses no
        shuttle state and does not aim. The delivered state scatters (seeded, RACKET_SCATTER)."""
        p_c = np.asarray(p_c, float); nrm = np.asarray(nrm, float); nrm = nrm / np.linalg.norm(nrm)
        v_p = np.asarray(v_p, float)
        info = {"t_hit": t_hit, "racket_pos": p_c.round(4).tolist(), "racket_normal": nrm.round(4).tolist(),
                "racket_vel": v_p.round(3).tolist()}
        k_hit = self.leg["launch"] + int(round(t_hit / CONTROL_DT))
        n_avail = k_hit - self.k
        info["n_swing_steps_available"] = int(n_avail)
        info["k_hit"] = None
        if n_avail < 3:
            info["stroke"] = "too late: the contact time has already passed"
            return [], info
        info["k_hit"] = int(k_hit)
        rng = scatter_rng(self.lv["seed"], 13, self.lv.get("stream", 1), self.n_our_legs)
        sc = self.RACKET_SCATTER
        p_c = p_c + rng.normal(0.0, sc["pos"], 3)
        axis = np.cross(nrm, rng.normal(0.0, 1.0, 3)); axis /= np.linalg.norm(axis)
        ang = np.radians(rng.normal(0.0, sc["ang_deg"]))
        nrm = nrm * np.cos(ang) + np.cross(axis, nrm) * np.sin(ang); nrm /= np.linalg.norm(nrm)
        v_p = v_p * (1.0 + rng.normal(0.0, sc["speed"]))
        st = stance(p_c) if base is None else np.clip(np.asarray(base, float), BASE_LO, BASE_HI)
        goal = st
        b0 = self.s.target[:2].copy()
        _, arr = self._base_plan(goal, n_avail)
        if arr is None or arr > n_avail - 5:
            lo_, hi_ = 0.0, 1.0
            for _ in range(10):
                mid = 0.5 * (lo_ + hi_)
                _, a2 = self._base_plan(b0 + mid * (st - b0), n_avail)
                if a2 is not None and a2 <= n_avail - 5:
                    lo_ = mid
                else:
                    hi_ = mid
            goal = b0 + lo_ * (st - b0)
            info["base"] = f"could not reach the stance in time: {float(np.linalg.norm(st - goal)):.2f} m short"
        else:
            info["base"] = "ok"
        info["base_goal"] = [round(float(x), 3) for x in goal]
        if base is not None:
            info["base_commanded"] = [round(float(x), 3) for x in st]
        # (the base study) no automatic return: after the stroke the base stays where it struck until the player moves
        # it (`move`); the follow-through and the arm's return are rehearsed with the base held there
        self.home = np.asarray(goal, float).copy()
        info["home_after"] = [float(x) for x in goal]      # installed on the live robot with the stroke (wc / bduel)
        base_tg, _ = self._base_plan(goal, n_avail + 40)
        ph = self.s
        seed = getattr(self, "_ik_seed", None)
        q_now = ph.target[2:].copy()                # the swing starts from the current joint targets
        seeds = ([] if seed is None else [seed]) + [q_now, Q0_ARM]
        q_h, res, sgn, alts = ik_multi(ph, p_c, nrm, goal, seeds, q_now)   # deterministic multi-start, nearest first
        Winv = np.diag(ARM_VEL_OP ** 2)
        tried = None
        for q_h, res, _ in [(q_h, res, sgn)] + alts:
            Jp = ph.jac(np.r_[goal, q_h])[:3]
            qd_h = Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T + 1e-9 * np.eye(3), v_p)
            ratio = float(np.max(np.abs(qd_h) / ARM_VEL_OP))
            c = dict(nrm=nrm, v_p=v_p, q_h=q_h, qd_h=qd_h, ik=res, ratio=ratio, v_out=np.zeros(3), p_hit=p_c)
            tg, sinfo = self._swing(c, goal, base_tg, n_avail)
            sc = swing_score(sinfo["blade_error_m"], sinfo["normal_error_deg"],
                             np.linalg.norm(self._swing_last[2] - v_p / sinfo["speed_scale"]))
            # self-collision: a motion clear of the stand and links first (the swing's rehearsal on the twin, where
            # they block the arm; then the rest of the motion: follow-through and the return to the ready pose)
            rc, rf = self._swing_contact, self._swing_reflex
            if rc == 0 and rf == 0:                   # the swing is clear: the whole motion (follow-through, return)
                rc = self._rollout_contact(tg)
                rf = self._roll_reflex
            # a motion that stops the robot in the joint-velocity reflex last, then self-collision
            key = (rf > 0, rc > 0, rc, sc)
            if tried is None or key < tried[0]:
                tried = (key, tg, sinfo, self._swing_last, q_h, res, rc, rf)
            if rc == 0 and rf == 0 and sinfo["blade_error_m"] <= DELIVERY_POS_WARN \
                    and sinfo["normal_error_deg"] <= DELIVERY_ANG_WARN:
                break                                 # delivered and clear: the nearest solution that works
        _, tg, sinfo, self._swing_last, q_h, res, rc, rf = tried
        for k in ("shot_speed_plan", "launch_dir", "head_speed_plan"):
            sinfo.pop(k, None)
        info.update(sinfo)
        p, n_act, v_act = self._swing_last
        info["racket_vel_delivered"] = [round(float(x), 3) for x in v_act]
        info["_q_hit"] = q_h
        notes = []
        if res > IK_OK: notes.append(f"pose not reachable exactly (IK residual {res:.3f})")
        if sinfo["blade_error_m"] > DELIVERY_POS_WARN or sinfo["normal_error_deg"] > DELIVERY_ANG_WARN:
            notes.append(f"pose not delivered: the rehearsed racket head is {100 * sinfo['blade_error_m']:.1f} cm off "
                         f"and the face {sinfo['normal_error_deg']:.1f} deg off the command at the contact time")
        if sinfo["speed_scale"] > 1.005: notes.append(f"head speed limited by the joint speed limits (x{1 / sinfo['speed_scale']:.2f})")
        if sinfo["n_swing_steps"] < 20: notes.append("short swing (little time left)")
        if info["base"] != "ok": notes.append(info["base"])
        if rc > 0:
            notes.append("self-collision: in the rehearsal the arm or racket runs into the robot's own stand or links "
                         "(they stop it)")
        if rf > 0:
            notes.append("joint-velocity reflex: in the rehearsal an arm joint exceeds 1.05 x its velocity limit and "
                         "the robot stops for 1 s")
        info["stroke"] = "; ".join(notes) or "ok"
        return tg, info

    def _rollout_contact(self, targets):
        """Self-collision contact steps (1 ms) of a robot-only twin rollout of the rest of the planned motion: from the
        swing's kept rehearsal at the contact time (_swing: the twin's `kept`), the follow-through targets, then the
        return to the ready pose (_ready_target: the arm at READY_SPEED, the base to its home) for at most
        READY_CHECK_STEPS control steps, until the arm is within 0.05 rad of the ready pose."""
        tw = self._twin_phys()
        n0, st = tw.kept                        # the swing's kept rehearsal, at the contact time (it had no contact)
        tw.load(st)
        nrf0 = tw.n_reflex
        mon = tw.selfcol["A"]
        mon.reset()
        for q in targets[n0:]:
            tw.step(q)
        lim = ARM_VEL * CONTROL_DT * READY_SPEED
        for _ in range(READY_CHECK_STEPS):      # the return to the ready pose (_ready_target on the twin's targets)
            t, a = tw.target, tw._actions
            dq = np.clip(Q0_ARM - t[2:], -lim, lim)
            if not np.any(np.abs(dq) > 1e-9) and np.max(np.abs(tw.d.qpos[tw.qa[2:]] - Q0_ARM)) < 0.05:
                break
            v = (a[-1][:2] - a[-2][:2]) / CONTROL_DT if len(a) >= 2 else np.zeros(2)
            acc = (a[-1][:2] - 2 * a[-2][:2] + a[-3][:2]) / CONTROL_DT ** 2 if len(a) >= 3 else np.zeros(2)
            b, _ = base_goto(t[:2], v, self.home, acc)
            tw.step(np.r_[b, t[2:] + dq])
        self._roll_reflex = tw.n_reflex - nrf0
        return int(mon.steps_in_contact)

    def _swing(self, c, goal, base_tg, n_avail):
        """Arm swing (cubic to the hit configuration, follow-through) + base plan; 5 robot-only twin rehearsals
        correct the hit configuration/velocity for the PD lag, and the best of them (swing_score) is kept."""
        ph = self.s
        scale = max(1.0, c["ratio"] / 0.9)
        q_h, qd_h = c["q_h"].copy(), c["qd_h"] / scale
        q_s = ph.target[2:].copy(); v_s = self._target_vel()[2:]
        rest = np.max(np.abs(v_s)) < 1e-6

        def demand(qd_end, n):
            """the swing's peak joint speed and acceleration over 97 % / ACC_SHARE of the limits (max ratio)"""
            sw = hermite(q_s, np.zeros(7) if rest else v_s, q_h, qd_end, n * CONTROL_DT, n)
            path = np.vstack([q_s - (np.zeros(7) if rest else v_s) * CONTROL_DT, q_s, sw])
            vel = np.diff(path, axis=0) / CONTROL_DT
            acc = np.diff(vel, axis=0) / CONTROL_DT
            return max(float(np.max(np.abs(vel) / (ARM_VEL_OP * 0.97))), float(np.max(np.abs(acc) / (ARM.acc * ACC_SHARE))))
        n_sw = int(n_avail)
        if rest and n_avail >= 25:
            # from rest: the shortest swing within 97 % of the speed limits and ACC_SHARE of the acceleration limits
            for n in range(25, int(n_avail) + 1):
                if demand(qd_h, n) <= 1.0:
                    n_sw = n
                    break
        n_sw = int(min(n_sw, n_avail))
        if n_sw >= 3 and demand(qd_h, n_sw) > 1.0 >= demand(np.zeros(7), n_sw):
            # not within the limits in the time left: a slower head at contact (the joint accelerations bind; when not
            # even the pose is within them, the setpoint generator does what it can and the rehearsal tells)
            lo_, hi_ = 0.0, 1.0
            for _ in range(12):
                mid = 0.5 * (lo_ + hi_)
                lo_, hi_ = (mid, hi_) if demand(qd_h * mid, n_sw) <= 1.0 else (lo_, mid)
            f = max(lo_, 0.05)
            qd_h = qd_h * f
            scale = scale / f
        v_p = c["v_p"] / scale
        qd_cap = np.abs(qd_h) * 1.2 + 0.05             # the correction passes keep the head speed near the feasible one
        Winv = np.diag(ARM_VEL_OP ** 2)
        q_goal, qd_goal = q_h.copy(), qd_h.copy()
        best = None
        for it in range(5):
            tg = self._swing_targets(q_goal, qd_goal, n_avail, n_sw, base_tg)
            p, n_act, v_act = self._simulate_arm(tg, n_avail, keep=n_avail - n_sw)
            sg = 1.0 if n_act @ c["nrm"] >= 0 else -1.0
            perr = float(np.linalg.norm(p - c["p_hit"]))
            nerr = float(np.degrees(np.arccos(np.clip(abs(float(n_act @ c["nrm"])), 0.0, 1.0))))
            sc = swing_score(perr, nerr, np.linalg.norm(v_act - v_p))
            # a rehearsal without the joint-velocity reflex first, then without self-collision, then the best one
            key = (self._sim_reflex > 0, self._sim_contact > 0, sc)
            if best is None or key < best[0]:         # keep the best of the correction passes, not the last one
                best = (key, tg, (p, n_act, v_act), perr, nerr, self._sim_contact, self._sim_reflex)
                self._twin.kept = (n_avail, self._twin.save())     # its end (the contact time): _rollout_contact
            if it == 4:
                break
            J = ph.jac(np.r_[goal, q_goal])
            e = np.r_[c["p_hit"] - p, np.cross(n_act, sg * c["nrm"])]
            q_goal = np.clip(q_goal + J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e),
                             ph.lo[2:] + 1e-4, ph.hi[2:] - 1e-4)
            Jp = J[:3]
            qd_goal = qd_goal + Winv @ Jp.T @ np.linalg.solve(Jp @ Winv @ Jp.T + 1e-9 * np.eye(3), v_p - v_act) * 0.7
            qd_goal = np.clip(qd_goal, -qd_cap, qd_cap)
            qd_goal = qd_goal / max(1.0, float(np.max(np.abs(qd_goal) / ARM_VEL_OP)))
        _, tg, self._swing_last, perr, nerr, self._swing_contact, self._swing_reflex = best
        info = {"ik_residual": round(float(c["ik"]), 5), "speed_scale": round(scale, 3), "n_swing_steps": n_sw,
                "blade_error_m": round(perr, 4), "normal_error_deg": round(nerr, 2),
                "head_speed_plan": round(float(np.linalg.norm(v_p)), 2),
                "shot_speed_plan": round(float(np.linalg.norm(c["v_out"]) / scale), 2),
                "launch_dir": [round(float(x), 3) for x in c["nrm"]]}
        info["stroke"] = "ok" if n_sw >= 20 else "short swing (little time left: slow racket)"
        return tg, info

    def _swing_targets(self, q_h, qd_h, n_avail, n_sw, base_tg):
        ph = self.s
        q_s = ph.target[2:].copy(); v_s = self._target_vel()[2:]
        pre = np.tile(q_s, (n_avail - n_sw, 1))
        swing = hermite(q_s, v_s if n_sw == n_avail else np.zeros(7), q_h, qd_h, n_sw * CONTROL_DT, n_sw)
        # follow-through: to rest within ACC_SHARE of the acceleration limits (at least 0.25 s)
        n_f = max(25, int(math.ceil(float(np.max(1.5 * np.abs(qd_h) / (ARM.acc * ACC_SHARE))) / CONTROL_DT)))
        follow = hermite(q_h, qd_h, q_h + qd_h * 0.5 * n_f * CONTROL_DT, np.zeros(7), n_f * CONTROL_DT, n_f)
        out, prev = [], ph.target.copy()
        lim = np.r_[BASE_VMAX, BASE_VMAX, ARM_VEL_OP] * CONTROL_DT * 0.999   # the arm at VMARGIN
        arm = np.vstack([pre, swing, follow])
        rows = np.concatenate((np.asarray(base_tg)[np.minimum(np.arange(len(arm)), len(base_tg) - 1)], arm), axis=1)
        rows = _uclip(rows, ph.lo + 1e-4, ph.hi - 1e-4)       # (row by row before 2026-10-13: the same numbers)
        nlim = -lim
        for q9 in rows:                                        # within the joint speed limits, step by step
            q9 = prev + _uclip(q9 - prev, nlim, lim)
            out.append(q9); prev = q9
        return out

    def _simulate_arm(self, targets, n, keep=None):
        """Robot-only twin rollout from the live robot state: racket (pos, normal, velocity) after n steps.
        Within one plan_racket the rollouts start from the same state and the correction passes of a swing share their
        first `keep` targets (the wait before the swing): the twin's exact state after them is kept (Phys.checkpoint)
        and a later rollout whose targets start with the same rows (compared) continues from it, bit-identically."""
        tw = self._twin_phys()
        mon = tw.selfcol["A"]
        ck, start = self.__dict__.get("_sim_ck"), 0
        if ck is not None and ck[0] is tw and ck[1] <= n and all(
                a.tobytes() == np.asarray(b, np.float64).tobytes() for a, b in zip(ck[2], targets)):   # bit for bit
            start, nrf0 = ck[1], ck[4]
            tw.restore(ck[3])
        else:
            tw.copy_from(self.s)
            tw.sh_live = False; tw.hit_enabled = False
            nrf0 = tw.n_reflex
            mon.reset()
        for j in range(start, n):
            if j == keep and j > start and "_sim_ck" in self.__dict__:
                self._sim_ck = (tw, j, [np.array(x, dtype=np.float64) for x in targets[:j]], tw.checkpoint(), nrf0)
            tw.step(targets[j])
        self._sim_contact = int(mon.steps_in_contact)   # the rollout's self-collision contact steps (1 ms)
        self._sim_reflex = tw.n_reflex - nrf0           # joint-velocity reflexes in the rollout
        mj.mj_forward(tw.m, tw.d)
        return tw.racket_state()

    # ------------------------------------------------------------------ views
    @staticmethod
    def cam_pose(lookat, dist, az, el):
        a, e = math.radians(az), math.radians(el)
        fwd = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        up = np.array([-math.sin(e) * math.cos(a), -math.sin(e) * math.sin(a), math.cos(e)])
        pos = np.asarray(lookat, float) - dist * fwd
        return pos, fwd, up

    @classmethod
    def cam_info(cls):
        out = []
        for name, c in zip(("behind", "side"), cls.CAMS):
            pos, fwd, up = cls.cam_pose(*c)
            out.append({"name": name, "position": [round(float(x), 4) for x in pos],
                        "forward": [round(float(x), 4) for x in fwd], "up": [round(float(x), 4) for x in up]})
        return out

    def _set_render_state(self, rd, sn):
        rd.qpos[:] = sn["qpos"]
        rd.mocap_pos[0] = sn["sh"]
        v = np.asarray(sn["shv"], float)
        if np.linalg.norm(v) < 1e-6:
            v = np.array([0.0, 0.0, -1.0])
        rd.mocap_quat[0] = quat_z_to(v)
        mj.mj_kinematics(self.s.m, rd)

    @staticmethod
    def _extra_geoms(scn, opp_xy, sh=None):
        def add(typ, size, pos, rgba, mat=np.eye(3)):
            if scn.ngeom >= scn.maxgeom:
                return
            mj.mjv_initGeom(scn.geoms[scn.ngeom], typ, np.asarray(size, float), np.asarray(pos, float),
                            np.asarray(mat, float).ravel(), np.asarray(rgba, np.float32))
            scn.ngeom += 1
        ox, oy = float(opp_xy[0]), float(opp_xy[1])
        add(mj.mjtGeom.mjGEOM_CAPSULE, [0.16, 0.55, 0], [ox, oy, 0.75], [0.35, 0.35, 0.42, 1])
        add(mj.mjtGeom.mjGEOM_SPHERE, [0.12, 0, 0], [ox, oy, 1.55], [0.85, 0.7, 0.6, 1])
        # the opponent's racket: red head, reaching towards the shuttle when it is near
        rp = np.array([ox + 0.45, oy - 0.1, 1.9])
        if sh is not None:
            d = np.array(sh) - np.array([ox, oy, 1.2])
            if np.linalg.norm(d) < 1.6:
                rp = np.array([ox, oy, 1.2]) + d / max(1e-6, np.linalg.norm(d)) * min(1.2, np.linalg.norm(d))
        add(mj.mjtGeom.mjGEOM_ELLIPSOID, [0.10, 0.02, 0.13], rp, [0.9, 0.1, 0.1, 1])

    def _renderer(self, w, h):
        key = (w, h)
        if getattr(self, "_rkey", None) != key:
            self._r = mj.Renderer(self.s.m, height=h, width=w)
            self._rd = mj.MjData(self.s.m)
            self._rkey = key
            self._cams = []
            for lookat, dist, az, el in self.CAMS:
                c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
                self._cams.append(c)
        return self._r, self._rd

    def render_views(self) -> bytes:
        """PNG: 2 rows (behind camera, side camera) x 4 columns (snapshots 60 ms apart, oldest left), each tile
        stamped with its time since the shuttle was played."""
        import imageio.v2 as imageio
        from PIL import Image, ImageDraw
        w, h = self.TILE
        r, rd = self._renderer(w, h)
        hist = list(self.hist)
        snaps = [hist[max(0, len(hist) - 1 - b)] for b in reversed(self.VIEW_BACK)]
        rows = []
        for c in self._cams:
            tiles = []
            for sn in snaps:
                self._set_render_state(rd, sn)
                r.update_scene(rd, camera=c)
                self._extra_geoms(r.scene, sn["opp"], sn["sh"])
                im = Image.fromarray(r.render())
                ImageDraw.Draw(im).text((6, 4), f"t={sn['t']:.2f}s", fill=(255, 255, 255))
                tiles.append(np.asarray(im))
            rows.append(np.concatenate(tiles, axis=1))
        buf = io.BytesIO()
        imageio.imwrite(buf, np.concatenate(rows, axis=0), format="png")
        return buf.getvalue()

    def view_times(self):
        hist = list(self.hist)
        return [hist[max(0, len(hist) - 1 - b)]["t"] for b in reversed(self.VIEW_BACK)]

    def decision_observation(self) -> dict:
        ph = self.s
        leg = self.leg
        heard = []
        if leg["kind"] == "serve":
            heard.append({"event": "the opponent served", "t": 0.0})
        else:
            heard.append({"event": "the opponent hit the shuttle", "t": 0.0})
        c, n, _ = ph.racket_state()
        return {"score": {"you": self.score[0], "opponent": self.score[1]}, "point": len(self.points) + 1,
                "ball": "serve" if leg["kind"] == "serve" else "opponent's return",
                "t_since_played": self.t_since_launch(), "heard": heard, "view_times": self.view_times(),
                "robot_base_xy": [round(float(x), 3) for x in ph.d.qpos[ph.qa[:2]]],
                "q_arm": [round(float(x), 4) for x in ph.d.qpos[ph.qa[2:]]],
                "racket_pos": [round(float(x), 3) for x in c], "racket_normal": [round(float(x), 3) for x in n]}


# The ready pose (revision wallclock-8): the racket head 1.15 m high, 0.3 m right of and 0.6 m in front of the base,
# the elbow bent: from it the usual contacts of the slow game (0.6-1.9 m high, faces towards the net) are the quickest
# to reach under the Panda's acceleration limits (searched over ready points and IK seeds: mean rest-to-rest time
# 0.57 s; the legacy ready pose, the racket 1.78 m high with the elbow nearly straight: 0.67 s for 0.9-2.1 m contacts,
# and 1.5 rad of the elbow to reach down). Legacy: the head 0.45 m above the shoulder, 0.35 m right, 0.45 m in front.
READY_XY, READY_Z = (0.3, 0.6), 1.15
READY_SEED = np.array([1.5445, 1.3195, -1.3692, -1.7297, -0.0274, 1.8111, 0.438])


def _ready_pose():
    """Ready pose: racket head in front of the robot's right shoulder, face towards the net."""
    global Q0_ARM
    ph = Phys(); ph.reset(np.r_[HOME, Q0_ARM])
    q, err = ik(ph, np.r_[HOME + np.array(READY_XY), READY_Z], np.array([0.0, 1.0, 0.25]), HOME, READY_SEED, iters=400)
    Q0_ARM = np.round(q, 4)


_ready_pose()


def render_video(actions, level, out, fps=25, every=2):
    """Replay video: the two decision cameras side by side, 2x slow motion (every `every` control steps at 25 fps),
    3x fewer frames while no shuttle is in play."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    mt = Match(level)
    r = mj.Renderer(mt.s.m, height=360, width=640)
    rd = mj.MjData(mt.s.m)
    cams = []
    for lookat, dist, az, el in Match.CAMS:
        c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
        cams.append(c)
    w = imageio.get_writer(out, fps=fps, macro_block_size=8)
    for k, q in enumerate(actions):
        mt.step(q)
        live = mt.s.sh_live
        if k % (every if live else 3 * every):
            continue
        sn = {"qpos": mt.s.d.qpos.copy(), "sh": mt.s.sh_p, "shv": mt.s.sh_v}
        mt._set_render_state(rd, sn)
        imgs = []
        for c in cams:
            r.update_scene(rd, camera=c)
            mt._extra_geoms(r.scene, mt.opp_xy(), mt.s.sh_p)
            imgs.append(r.render())
        im = Image.fromarray(np.concatenate(imgs, axis=1))
        ImageDraw.Draw(im).text((8, 6), f"robot {mt.score[0]} : {mt.score[1]} opponent   (level {level})",
                                fill=(255, 255, 255))
        w.append_data(np.asarray(im))
    w.close(); r.close()
