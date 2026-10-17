"""Robot soccer world: N v N Booster T1 lower bodies (N = SOCCER_TEAM_SIZE: 2 or 5), one ball, a referee (RoboCup HSL
rules with the deviations of the README), and the scripted coach used by the single-player opponent team.

Everything that changes the world happens in World.advance() (one 20 ms control step = 10 physics steps of 2 ms) and
in World.command() (a robot's new command, applied at a control-step boundary). The referee's decisions (fouls, falls,
goals, restarts, the penalty shoot-out) and the scripted team are deterministic functions of the simulator state, so
the logged (step, robot, command) list replays the match bit-exactly in a fresh process (replay.py).

Coordinates: world frame of soccer_scene.py (team A attacks +x). A team's own frame is the world for A and the world
turned by 180 degrees about z for B; every team attacks +x in its own frame. Functions with `tf` take/return team
frame values.

Walking: the released Booster T1 lower-body walking policy (SaiResearch/booster_soccer_models, MIT; models/), the
earlier soccer tasks' controller: body-frame velocity command (vx, vy, wz) in [-1, 1] m/s, m/s, rad/s; 50 Hz policy,
PD torques at 500 Hz. The four robots' policies are evaluated together in one batch (same order every step).

Real limits (soccer-2v2-4; bodies/booster_t1/body.toml through bodies/servo.py Actuators and WalkCommand, the robot
library's one limit path; sport.toml [legs] body): the leg motors' torques are the
Booster URDF's (45 / 30 / 30 / 60 / 24 / 15 N m; the sai-mujoco model's ctrlrange is higher and not used), a torque
that drives a joint in its direction of motion is limited by a linear torque-speed envelope (full torque up to 64 % of
the URDF joint speed, none at it), each motor's torque limit folds back to its rated (continuous) torque, 60 % of the
URDF torque, when its I^2 t thermal state is used up (the peak from a cold motor lasts about 5 s), and a robot's 12 leg
motors share a 1 kW bus (soccer-2v2-10; all ESTIMATES of bodies/booster_t1 [motors]), and the walking command a policy sees moves toward the requested one by at
most 2 m/s^2, 2 m/s^2, 4 rad/s^2 (ESTIMATE, the G1 joystick's). The feet meet the turf with a near-rigid contact
(soccer-2v2-11, soccer_scene.FLOOR_SOLREF: no creep inside the friction cone).

Kick (style "swing", the default): the right leg's model-based swing kick (swing_kick.py): once the walking controller
has stopped the robot and the ball is (nearly) still (else the kick is called off after 1 s), the legs leave the
policy (stance, weight onto the left foot, wind-up, a minimum-jerk swing through the ball as it lies when the kick
starts, along the heading turned by `aim` with the foot turned to it, retract, lower, a joint-space return to the
policy's standing targets, a stability check), then the policy takes the legs again and steps in place for 0.6 s;
`power` in [0, 1] sets the swing's nominal peak foot speed 0.8 + 3.2 power m/s. Style "push": the earlier tasks'
toe-poke (stand 0.5 s, restart the gait clock, run straight at
v = 0.6 + 0.4 power holding the heading until a foot is past the ball's centre, at most twice the nominal 1.32 m run,
stand 0.5 s).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from collections import deque

import numpy as np

import mujoco
import soccer_scene as SC
import step_kick as STK
import swing_kick as SK
from soccer_scene import BALL_R, CENTER_R, GOAL_H, GOAL_W, HALF_L, HALF_W, PEN_MARK, ROBOTS
from soccer_scene import (BOARDS, GOAL_AREA, GOAL_D, PEN_AREA, PLAY_X, PLAY_Y, TEAM_SIZE)

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(HERE)               # sim/ in a task (bodies/ next to sport/); sports/ in a checkout
sys.path.insert(0, _ROOT if os.path.isdir(os.path.join(_ROOT, "bodies")) else os.path.dirname(_ROOT))
from bodies import servo as SV  # noqa: E402
import tomllib  # noqa: E402

T1 = tomllib.loads(open(os.path.join(os.path.dirname(SV.__file__), "booster_t1", "body.toml"), "rb").read().decode())
LEG_KEYS = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"] * 2   # JOINT_NAMES' motors
MODELS_DIR = os.environ.get("RCB_SOCCER_MODELS", os.path.join(HERE, "models"))
PHYS_DT, SUB = 0.002, 10
CONTROL_DT = PHYS_DT * SUB                  # 20 ms: one control step = one walking-policy tick
TEAMS = ("A", "B")
OTHER = {"A": "B", "B": "A"}
TEAM_ROBOTS = {t: tuple(r for r in ROBOTS if r[0] == t) for t in "AB"}
N = TEAM_SIZE
REVISION = "soccer-2v2-11" if N == 2 else "soccer-5v5-3"   # 5 v 5 (not a task yet): the legacy soccer-4 rules on the real T1
GOALKEEPER = 1 if N >= 3 else None           # HSL Law 3: at most one designated goalkeeper (robot 1; 5 v 5)
JOINT_NAMES = ["Left_Hip_Pitch", "Left_Hip_Roll", "Left_Hip_Yaw", "Left_Knee_Pitch", "Left_Ankle_Pitch",
               "Left_Ankle_Roll", "Right_Hip_Pitch", "Right_Hip_Roll", "Right_Hip_Yaw", "Right_Knee_Pitch",
               "Right_Ankle_Pitch", "Right_Ankle_Roll"]

# ---- match format (README "Rules") ---------------------------------------------------------------------------------
HALF_S = float(os.environ.get("SOCCER_HALF_S", "300"))   # two halves of 5 minutes of game time (soccer-2v2-5; 2.5 up to -4)
MERCY_DIFF = 10                             # HSL Law 7 mercy rule
KICKOFF_FREE_S = 10.0                       # HSL Law 8.1: the ball is in play after 10 s at the latest
BALL_STOP_EXT_S = 3.0                       # HSL Law 7 ball stop rule: a period runs on at most 3 s while the ball moves
FALL_Z = 0.40                               # imu height below which a robot has fallen
GETUP_S = 3.0                               # a fallen robot is stood up where it lies after 3 s
PENALTY_S, PENALTY_INC_S = 15.0, 5.0        # standard removal penalty (HSL 45 s + 10 s per team offense), scaled
HOLD_R, HOLD_S = 0.16, 5.0                  # ball holding: ball centre within 0.16 m of a standing robot's trunk, 5 s
HOLD_KEEPER_S = 10.0                        # HSL Law 12: the goalkeeper in its own penalty area may hold 10 s
PUSH_WINDOW_S, PUSH_MIN_V, PUSH_LONG_S = 0.5, 0.15, 5.0
PUSH_GAP_S, PUSH_DISPLACE_M = 0.5, 0.6     # one contact survives gaps <= 0.5 s; pushing an opponent 0.6 m back is pushing
LOCAL_STUCK_S, LOCAL_STUCK_M, GLOBAL_STUCK_S, STUCK_NEAR_M = 15.0, 0.3, 30.0, 1.0   # local: 10 s up to soccer-2v2-3
                                            # (a swing kick takes ~5 s, the push 2.6 s)
PEN_AREA_X, PEN_AREA_Y = HALF_L - PEN_AREA[0], PEN_AREA[1] / 2   # the penalty area (team frame: x < -PEN_AREA_X,
                                            # |y| < PEN_AREA_Y; the goal included)
GOAL_AREA_X, GOAL_AREA_Y = HALF_L - GOAL_AREA[0], GOAL_AREA[1] / 2
MAX_IN_AREA = 1 if N == 2 else 3            # illegal defence: 2 v 2 at most one robot in the own penalty area; 5 v 5
                                            # (HSL Law 12 illegal positioning) at most three in the own goal area
FREE_KICK_S = 15.0                          # a free kick's ball is in play after 15 s at the latest (HSL: 45 s)
FK_GRACE_M = 0.2                            # an opponent is penalized only when clearly inside the avoidance radius
GOAL_STUCK_S = 5.0                          # HSL Law 12 leaving the field: in the goal (net, posts) more than 5 s
BOARD_ZONE_M, BOARD_STUCK_S, BOARD_MOVE_M = 0.3, 3.0, 1.0   # a ball resting at a board is moved 1 m inwards
CROWD_S = 5.0                               # illegal defence: both robots of a team in their own penalty area > 5 s
PSO_KICKS, PSO_SD_ROUNDS, PSO_TIME_S = 3, 3, 20.0
PSO_CATEGORIES = ["goal", "saved", "post", "wide", "other", "no_kick"]    # HSL Law 14 sudden death ranking
PSO_AIM_Y = 0.9                             # the scripted shoot-out striker aims at a corner (y = +-0.9 on the line)
STAGE_M = 0.30                              # the scripted kicker lines up this far behind its kick spot first
CONTEST_M = 1.5                             # an opponent this near the ball: the scripted striker pushes (style push)
SHOT_AIM_Y = 0.8                            # the scripted striker's shots: at y = +-0.8 on the goal line
# the kick skill (README "Kick"): style "swing" (default, swing_kick.py) or "push" (the earlier toe-poke)
SWING = dict(speed_min=0.8, speed_max=4.0,  # nominal peak foot speed of the swing: speed_min + (max - min) power (m/s)
             aim_max=0.6,                   # aim: the kick's direction relative to the heading (soccer-2v2-7; 0.2 before):
             aim_in_max=0.3,                # up to 0.6 rad away from the support foot's side (right foot: to the right),
                                            # up to 0.3 rad across it (the step-2 drill: wider inward kicks fall on landing)
             at_t_max=6.0,                  # the timed kick (`at`): the strike at most 6 s after the command
             z_off=0.0, gap=0.03,           # strike point: the ball's centre height, 3 cm behind its surface
             ready_v=0.06, ready_w=9.0, ready_max_s=1.0,   # the kick starts when the robot has stopped and the
             ball_still_v=0.15, cancel_late=True,          # ball rolls slower than 0.15 m/s; else called off at 1 s
             recover_s=0.6)                 # after the hand-back the policy steps in place this long
# the in-walk kick (style "step", step_kick.py; soccer-2v2-8): aim limits as the swing kick's; the walking command
# while it waits for the kicking foot's swing when the robot was not walking
STEP = dict(aim_max=0.6, aim_in_max=0.3, v_default=(0.3, 0.0, 0.0),
            line_m=0.16, stage_m=0.7, lat_tol=0.05, yaw_tol=0.15, approach_v=0.5,   # the scripted players' use of it
            strike_s=1.0,                   # (the reference's pass timing: about this long from command to contact)
            recover_s=0.6)                  # after the kick the policy steps to a stop (zero command) this long
STEP_DOC = ("approach: the walking policy walks on with the command's v until the kicking foot lifts off with the ball "
            "in reach (at most 2 s, else kick_cancelled); wind-up (0.08 s, the walking policy keeps the support leg "
            "and balance); swing through the ball (about 0.1-0.2 s); the foot back to a short step (0.08 s); the policy "
            "puts it down and steps to a stop (0.6 s); contact typically 0.5-1.5 s after the command")
SWING_ZONE = dict(ahead=(0.26, 0.38), right=(0.02, 0.10))   # where the ball should lie for a swing (robot frame)
SWING_NOMINAL_S = 0.01 * sum(v for k, v in SK.PARAMS.items() if k.startswith("n_")) + 0.2   # + the swing
# where the ball's centre should lie (robot frame: ahead, left) for a swing at a given aim (step-2 drill, right foot;
# the left foot mirrored): the swing's line moves outward with the aim (soccer-2v2-7)
SWING_ZONE_AIM = ((-0.6, 0.294, -0.258), (-0.5, 0.306, -0.233), (-0.4, 0.314, -0.207), (-0.3, 0.320, -0.181),
                  (-0.2, 0.324, -0.153), (-0.1, 0.324, -0.126), (0.0, 0.322, -0.099), (0.1, 0.317, -0.072),
                  (0.2, 0.310, -0.046), (0.3, 0.300, -0.020))


def swing_zone(aim, foot="right"):
    """the ball's ideal place (ahead, left of the trunk, m) for a swing kick at `aim` with `foot`"""
    a = float(aim) if foot == "right" else -float(aim)
    xs = [r[0] for r in SWING_ZONE_AIM]
    x = float(np.interp(a, xs, [r[1] for r in SWING_ZONE_AIM]))
    y = float(np.interp(a, xs, [r[2] for r in SWING_ZONE_AIM]))
    return x, (y if foot == "right" else -y)


KICKOFF_SPOT = (0.32, 0.06)                 # the kick-off robot: the ball this far ahead and to its right
SWING_DOC = ("ready: the walking controller stops the robot (at most 0.6 s); stance on both feet (0.4 s, longer until the "
             "feet are still, at most +0.6 s); weight onto the left foot (1.1 s) and balance (0.3 s); lift the right foot "
             "and wind back (0.3 s); swing through the ball (0.1-0.4 s: the ball is hit 2.4-2.9 s after the command); "
             "follow through, retract and lower the foot (0.8 s); back to the walking controller's standing pose on both "
             "feet (0.4 s) and a stability check (0.1-0.4 s); 0.6 s of recovery steps in place; about 4.7-5.6 s in all")
KICK = dict(stand_s=0.5, run_m=1.32, after_s=0.5, run_max_factor=2.0, through_m=0.0)       # the push
STRIKE_ZONE = dict(ahead=(0.90, 1.05), right=(0.10, 0.20))   # where the ball should lie for a push (robot frame)
CMD_LIMITS = dict(vx=1.0, vy=1.0, wz=1.0)
# The joint level (pilot, soccer-joint): a robot under joint control takes rows of 12 leg joint targets (JOINT_NAMES'
# order) instead of the walking policy's; each row is limited (at most the URDF speed x 20 ms from the row before,
# inside the joint ranges, a non-finite value keeps the previous one), then the same PD (Booster's deployment gains,
# the walking policy's) and the same motors (bodies/servo.py Actuators). After every placement (kick-off, restart,
# get-up, back from a penalty) the referee holds the trunk where it put it for PLACE_HOLD_S while the rows already act
# (an assistant referee steadying the robot; the user's decision 3 of 2026-10-13); on the bench a robot stays held.
PLACE_HOLD_S = 1.0                          # (not HOLD_S: that is the ball-holding rule's 5 s)
TRAJ_MAX = 50                               # rows in one plan (1 s)
ROW_STEP = np.tile(np.asarray(T1["limits"]["leg"]["speed_rad_s"], float), 2) * CONTROL_DT
ROLL_DECEL = 0.52                           # the ball's rolling deceleration on the turf (m/s^2; soccer-2v2-8, 0.15
                                            # before): the FIFA turf roll test (a ball rolling off a 1 m ramp at about
                                            # 3.2 m/s) must roll 4-10 m (Quality) / 4-8 m (Quality Pro), i.e. 0.51-1.28
                                            # m/s^2; 0.52 (9.8 m) is the low end, nearest RoboCup practice (B-Human's
                                            # ball model: 0.30) and natural grass's 0.45-1.5

SEED = int(os.environ.get("SOCCER_SEED", os.environ.get("MATCH_SEED", "1")))
FIRST_KICKOFF = os.environ.get("FIRST_KICKOFF", "A")
LEVEL = int(os.environ.get("MATCH_LEVEL", "0") or 0)       # 0: no scripted team (duel / team formats)


def in_own_area(p, margin=0.0):
    """A team-frame point inside that team's own penalty area (or its goal)."""
    return p[0] < -(PEN_AREA_X - margin) and abs(p[1]) < PEN_AREA_Y + margin


def in_own_goal_area(p, margin=0.0):
    """A team-frame point inside that team's own goal area (or its goal)."""
    return p[0] < -(GOAL_AREA_X - margin) and abs(p[1]) < GOAL_AREA_Y + margin


def in_goal(p):
    """A world point behind a goal line between the posts (inside a goal)."""
    return abs(p[0]) > HALF_L and abs(p[1]) < GOAL_W / 2 + 0.05


def off_carpet(p):
    """A robot's trunk (world xy) off the area robots may stand on: beyond the border strip (5 v 5) or over a board
    (2 v 2), not counting the goals."""
    if in_goal(p):
        return abs(p[0]) > HALF_L + GOAL_D + 0.3
    return abs(p[0]) > PLAY_X + 0.1 or abs(p[1]) > PLAY_Y + 0.1


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def _yaw_quat(yaw):
    return np.array([np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)])


def _quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def yaw_of(q) -> float:
    w, x, y, z = q
    return float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def to_team(team, xy):
    """World -> team frame (positions; for velocities use the same, it is a rotation)."""
    xy = np.asarray(xy, float)
    return xy if team == "A" else -xy


from_team = to_team                                  # the 180 degree turn is its own inverse


def yaw_to_team(team, yaw):
    return float(yaw) if team == "A" else float(_wrap(yaw + np.pi))


def jdefault(o):
    if hasattr(o, "tolist"):
        return o.tolist()
    return str(o)


# ---------------------------------------------------------------------------------------------- walking policy
class Policy:
    """The released Booster T1 lower-body walking policy, for all robots in one batch."""

    def __init__(self, n=len(ROBOTS), models_dir=MODELS_DIR):
        import torch
        import yaml
        torch.set_num_threads(1)
        self.torch = torch
        c = self.cfg = yaml.safe_load(open(os.path.join(models_dir, "config", "lower_t1.yaml")))
        self.model = torch.jit.load(os.path.join(models_dir, "robot", "lower_t1_control.pt"))
        self.model.eval()
        dja = c["init_state"]["default_joint_angles"]
        self.default = np.array([next((v for k, v in dja.items() if k in nm), dja["default"]) for nm in JOINT_NAMES],
                                dtype=np.float32)
        st, dp = c["control"]["stiffness"], c["control"]["damping"]
        self.kp = np.array([next(v for k, v in st.items() if k in nm) for nm in JOINT_NAMES], dtype=np.float32)
        self.kd = np.array([next(v for k, v in dp.items() if k in nm) for nm in JOINT_NAMES], dtype=np.float32)
        self.nrm = c["normalization"]
        self.gait_f = float(np.average(c["commands"]["gait_frequency"]))
        self.n = n
        self.actions = np.zeros((n, 12), np.float32)
        self.gait = np.zeros(n)                      # gait phase in [0, 1)
        self.freq = np.zeros(n)

    def get(self, i):
        return (self.actions[i].copy(), float(self.gait[i]), float(self.freq[i]))

    def set(self, i, s):
        self.actions[i] = s[0]; self.gait[i] = s[1]; self.freq[i] = s[2]

    @staticmethod
    def _rot_inv(q_xyzw, v):
        qw, qv = q_xyzw[-1], q_xyzw[:3]
        return v * (2.0 * qw ** 2 - 1.0) - np.cross(qv, v) * (qw * 2.0) + qv * (np.dot(qv, v) * 2.0)

    def infer(self, cmds, dof_pos, dof_vel, quats_xyzw, gyros, gait_on=None):
        """One policy tick for all robots: cmds (n, 3); gait_on (n,): step in place even at a zero command (the
        recovery steps after a kick); returns nothing (actions updated)."""
        nrm = self.nrm
        obs = np.zeros((self.n, 47), np.float32)
        for i in range(self.n):
            vx, vy, wz = (float(x) for x in cmds[i])
            on = gait_on is not None and gait_on[i]
            self.freq[i] = 0.0 if (vx == 0 and vy == 0 and wz == 0 and not on) else self.gait_f
            obs[i, 0:3] = self._rot_inv(quats_xyzw[i], np.array([0.0, 0.0, -1.0])) * nrm["gravity"]
            obs[i, 3:6] = gyros[i] * nrm["ang_vel"]
            obs[i, 6], obs[i, 7], obs[i, 8] = vx * nrm["lin_vel"], vy * nrm["lin_vel"], wz * nrm["ang_vel"]
            on = self.freq[i] > 1e-8
            obs[i, 9] = np.cos(2 * np.pi * self.gait[i]) * on
            obs[i, 10] = np.sin(2 * np.pi * self.gait[i]) * on
            obs[i, 11:23] = (dof_pos[i] - self.default) * nrm["dof_pos"]
            obs[i, 23:35] = dof_vel[i] * nrm["dof_vel"]
            obs[i, 35:47] = self.actions[i]
        with self.torch.no_grad():
            a = self.model(self.torch.from_numpy(obs)).numpy()
        self.actions[:] = np.clip(a, -nrm["clip_actions"], nrm["clip_actions"])

    def targets(self):
        return self.default[None, :] + self.cfg["control"]["action_scale"] * self.actions

    def advance_gait(self):
        self.gait = np.fmod(self.gait + PHYS_DT * self.freq, 1.0)


class Robot:
    """Index helpers of one T1 in the scene."""

    def __init__(self, m, name, idx):
        self.name, self.idx, self.team = name, idx, name[0]
        self.num = int(name[1:])
        p = name + ":"
        self.jq = np.array([m.jnt_qposadr[m.joint(p + n).id] for n in JOINT_NAMES])
        self.jv = np.array([m.jnt_dofadr[m.joint(p + n).id] for n in JOINT_NAMES])
        self.act = np.array([m.actuator(p + n).id for n in JOINT_NAMES])
        self.tau = np.tile(np.asarray(T1["limits"]["leg"]["torque_nm"], float), 2)   # the real motors' torques
        root = m.joint(p + "root")
        self.rq, self.rv = int(m.jnt_qposadr[root.id]), int(m.jnt_dofadr[root.id])
        s = lambda n: int(m.sensor_adr[m.sensor(p + n).id])  # noqa: E731
        self.s_quat, self.s_gyro, self.s_acc = s("torso_quat"), s("torso_gyro"), s("accelerometer")
        self.imu = m.site(p + "imu").id
        bodies = {i for i in range(m.nbody) if m.body(i).name.startswith(p)}
        self.gset = {g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in bodies and m.geom_contype[g]}
        self.cam = m.camera(p + "egocentric").id
        self.feet = (m.site(p + "left_foot").id, m.site(p + "right_foot").id)

    def xy(self, d):
        return d.qpos[self.rq:self.rq + 2].copy()

    def yaw(self, d):
        return yaw_of(d.sensordata[self.s_quat:self.s_quat + 4])

    def vel(self, d):
        return d.qvel[self.rv:self.rv + 2].copy()

    def height(self, d):
        return float(d.site_xpos[self.imu][2])


# ---------------------------------------------------------------------------------------------- the world
class World:
    def __init__(self, level=LEVEL, seed=SEED, first_kickoff=FIRST_KICKOFF, scripted=None, joint=()):
        """scripted: {team: Coach level} for teams the world itself plays (the single-player opponent); joint: the
        robots under joint control (the joint level; the others are on the walking policy)."""
        self.m = SC.build_model()
        self.d = mujoco.MjData(self.m)
        m, d = self.m, self.d
        self.seed, self.first_kickoff = int(seed), first_kickoff
        self.rob = {r: Robot(m, r, i) for i, r in enumerate(ROBOTS)}
        self.joint = tuple(r for r in ROBOTS if r in set(joint) or r[0] in set(joint))
        self.pol = Policy(len(ROBOTS))
        bj = m.joint("ball")
        self._bq, self._bv = int(m.jnt_qposadr[bj.id]), int(m.jnt_dofadr[bj.id])
        self._bg = m.geom("ball").id
        self._bb = int(m.geom_bodyid[self._bg])
        bm = float(m.body_mass[self._bb])
        self._rr_force = bm * ROLL_DECEL * (1.0 + float(m.body_inertia[self._bb][0]) / (bm * BALL_R ** 2))
        self._post = {m.geom(n).id: n for n in (f"post_{t}_{s}" for t in "AB" for s in "LR")}
        self._post.update({m.geom(f"bar_{t}").id: f"bar_{t}" for t in "AB"})
        self._geom_robot = {}
        for r in self.rob.values():
            for g in r.gset:
                self._geom_robot[g] = r.name
        self.scripted = dict(scripted or {})
        # {team: level} or {team: (level, style)} (style: the 5 v 5 team plan of the feasibility study)
        self.coaches = {t: (Coach(t, *lv) if isinstance(lv, (tuple, list)) else make_coach(t, lv))
                        for t, lv in self.scripted.items()}
        for t, c in self.coaches.items():               # a joint-level opponent: its team under joint control
            if getattr(c, "joint", False):
                self.joint = tuple(r for r in ROBOTS if r in self.joint or r[0] == t)
        rs = list(self.rob.values())                       # the legs of all robots as (4, 12) index arrays
        self._jq = np.array([r.jq for r in rs])
        self._jv = np.array([r.jv for r in rs])
        self._act = np.array([r.act for r in rs])
        # the legs' output stage, all four robots (bodies/servo.py: the motors' torque-speed curves of booster_t1
        # [motors] and the torque limit; the only writer of the legs' actuators) and each robot's walking command
        self.motors = SV.Actuators(m, self._act.reshape(-1), self._jv.reshape(-1),
                                   np.concatenate([r.tau for r in rs]), PHYS_DT,
                                   **SV.motor_model(T1, LEG_KEYS * len(rs),
                                                    groups=[np.arange(12) + 12 * i for i in range(len(rs))]))
        self.cmd_lim = {r: SV.WalkCommand(T1["limits"]["walk"], CONTROL_DT) for r in ROBOTS}
        self._kin = mujoco.MjData(m)                       # the swing kick's kinematics (never the world's data)
        self._jlo = {r: m.jnt_range[[m.joint(r + ":" + n).id for n in JOINT_NAMES], 0].copy() for r in ROBOTS}
        self._jhi = {r: m.jnt_range[[m.joint(r + ":" + n).id for n in JOINT_NAMES], 1].copy() for r in ROBOTS}
        self.jrow, self.jplan, self.held, self.held_pose = {}, {}, {}, {}
        self._jstance = self._joint_stance()
        self.prog = {r: dict(type="stand") for r in ROBOTS}
        self._settled = self._settle()
        self._stand_targets = (self.pol.default + self.pol.cfg["control"]["action_scale"] *
                               self._settled["pol"][0]).astype(np.float64)   # the policy's standing joint targets
        self.kick_geom = self._kick_geometry()
        self.reset()

    # ------------------------------------------------------------------ placement
    def _settle(self):
        """One standing robot's settled state (1.5 s of the zero command), placed anywhere by place()."""
        m, d = self.m, self.d
        mujoco.mj_resetData(m, d)
        for i, r in enumerate(self.rob.values()):          # far apart, all at yaw 0
            d.qpos[r.rq:r.rq + 7] = [-3.0 + 2.0 * i, 0.0, 0.70, 1, 0, 0, 0]
        d.qpos[self._bq:self._bq + 7] = [0, 3.0, BALL_R, 1, 0, 0, 0]
        mujoco.mj_forward(m, d)
        zero = np.zeros((len(ROBOTS), 3))
        for _ in range(75):
            self._physics_tick(zero)
        r = self.rob["A1"]
        q = d.qpos[r.rq:r.rq + 7].copy()
        tilt = _quat_mul(_yaw_quat(-yaw_of(q[3:])), q[3:])
        com_z = float(d.subtree_com[m.body("A1:Trunk").id][2])
        return dict(z=float(q[2]), tilt=tilt, joints=d.qpos[r.jq].copy(), pol=self.pol.get(r.idx), com_z=com_z)

    def _joint_stance(self):
        """The joint level's placed stance: Booster's default joint angles (the deployment's standing pose, knees
        bent; the walking policy's settled stance is nearly straight-legged), the trunk upright at the height where
        the lowest sole corner touches the floor."""
        m = self.m
        kd = mujoco.MjData(m)                          # its own data: self._kin's state is the kicks' (golden replays)
        r = self.rob["A1"]
        kd.qpos[:] = m.qpos0
        kd.qpos[r.rq:r.rq + 7] = [0, 0, 0, 1, 0, 0, 0]
        kd.qpos[r.jq] = self.pol.default
        mujoco.mj_kinematics(m, kd)
        low = 0.0
        for g in r.gset:
            if not m.body(int(m.geom_bodyid[g])).name.endswith("foot_link"):
                continue
            if int(m.geom_type[g]) == int(mujoco.mjtGeom.mjGEOM_BOX):
                R, c, h = kd.geom_xmat[g].reshape(3, 3), kd.geom_xpos[g], m.geom_size[g]
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        for sz in (-1, 1):
                            low = min(low, float((c + R @ (h * np.array([sx, sy, sz])))[2]))
            else:
                low = min(low, float(kd.geom_xpos[g][2] - m.geom_rbound[g]))
        return dict(z=-low + 0.0005, joints=self.pol.default.astype(float).copy())

    def _kick_geometry(self):
        """The T1's constants of the swing kick, from the model (swing_kick.SwingKick geom): the linear inverted
        pendulum's frequency at the settled standing CoM height, and the right foot's collision box relative to the
        foot site (its centre ahead of the site; the strike point 3 cm behind the toe edge, at the box centre's
        height). Rigid geometry: the same for every robot and every kick."""
        m, d = self.m, self._kin
        d.qpos[:] = self.d.qpos
        mujoco.mj_kinematics(m, d)
        sid = m.site("A1:right_foot").id
        fb = m.body("A1:right_foot_link").id
        box = next(g for g in range(m.ngeom) if m.geom_bodyid[g] == fb and m.geom_contype[g])
        Rs = d.site_xmat[sid].reshape(3, 3)
        rel = Rs.T @ (d.geom_xpos[box] - d.site_xpos[sid])
        front = rel[0] + m.geom_size[box][0]
        return dict(omega=math.sqrt(9.81 / max(self._settled["com_z"], 0.3)), foot_strike_forward=float(rel[0]),
                    strike_in_site=[float(front - 0.03), 0.0, float(rel[2])])

    def place(self, name, x, y, yaw, world=True):
        """Put a robot upright in the settled standing state at (x, y, yaw) (world frame)."""
        r, s, d = self.rob[name], self._settled, self.d
        js = name in self.joint                        # the joint level: Booster's default stance, upright
        d.qpos[r.rq:r.rq + 3] = [x, y, self._jstance["z"] if js else s["z"]]
        d.qpos[r.rq + 3:r.rq + 7] = _yaw_quat(yaw) if js else _quat_mul(_yaw_quat(yaw), s["tilt"])
        d.qpos[r.jq] = self._jstance["joints"] if js else s["joints"]
        d.qvel[r.rv:r.rv + 6] = 0.0
        d.qvel[r.jv] = 0.0
        self.pol.set(r.idx, (s["pol"][0], 0.0, 0.0))
        self.cmd_lim[name].reset()
        self.prog[name] = dict(type="stand")
        if name in self.joint:                         # the joint level: rows from the stance, held PLACE_HOLD_S
            self.jrow[name] = self._jstance["joints"].copy()
            self.jplan[name] = None
            self.held[name] = self.k + int(round(PLACE_HOLD_S / CONTROL_DT))
            self.held_pose[name] = d.qpos[r.rq:r.rq + 7].copy()

    def place_ball(self, x, y):
        d = self.d
        d.qpos[self._bq:self._bq + 7] = [x, y, BALL_R, 1, 0, 0, 0]
        d.qvel[self._bv:self._bv + 6] = 0.0

    def free_spot(self, name, x, y, ignore=(), r_robot=0.65, r_ball=0.45, inside=True):
        """The first spot at or near (x, y) clear of the other robots and the ball (a deterministic spiral)."""
        d = self.d
        others = [self.rob[o].xy(d) for o in ROBOTS if o != name and o not in ignore and not self.on_bench(o)]
        ball = self.ball_xy()
        sgn = 1.0 if name[0] == "A" else -1.0              # the spiral in the robot's team frame (mirror symmetry)
        for ring in range(0, 12):
            n = 1 if ring == 0 else 8 * ring
            for j in range(n):
                a = 2 * np.pi * j / n
                p = np.array([x, y]) + sgn * 0.25 * ring * np.array([np.cos(a), np.sin(a)])
                if inside and (abs(p[0]) > HALF_L - 0.3 or abs(p[1]) > HALF_W - 0.3):
                    continue
                if all(np.hypot(*(p - o)) >= r_robot for o in others) and np.hypot(*(p - ball)) >= r_ball:
                    return p
        return np.array([x, y])

    # ------------------------------------------------------------------ reset / restarts
    def reset(self):
        self.k = 0
        self.prog = {r: dict(type="stand") for r in ROBOTS}
        self.acts = []                                   # (k, robot, command): the replay's input
        self.score = {"A": 0, "B": 0}
        self.period = 1                                  # 1, 2, "pso"
        self.period_k = 0
        self.state = "kickoff"                           # kickoff | play | pso_kick
        self.stopped = None                              # a stoppage awaiting the reviews: dict(kind=...)
        self.done = False
        self.winner = None
        self.end_reason = None
        self.events = []                                 # referee events (goal, penalty, fall, stoppage, ...)
        self.stops = []                                  # the stoppages (each followed by a review)
        self.goals = []
        self.kickoff_team = self.first_kickoff
        self.kickoff_index = 0
        self.ko = None                                   # kick-off conditions until the ball is in play / touched
        self.fallen = {r: None for r in ROBOTS}          # step it fell
        self.penalty = {r: None for r in ROBOTS}         # dict(until=k, why=...)
        self.team_offenses = {"A": 0, "B": 0}
        self.hold = {r: 0 for r in ROBOTS}
        self.crowd = {t: 0 for t in TEAMS}               # steps a team had too many robots in its own area
        self.area_entry = {r: None for r in ROBOTS}      # step a robot entered its own (goal) area (5 v 5)
        self.in_goal_k = {r: 0 for r in ROBOTS}          # steps a robot has stood inside a goal
        self.fk = None                                   # a free kick under way (5 v 5: kick-in, goal kick, corner)
        self.restarts = {t: dict(kick_in=0, goal_kick=0, corner_kick=0) for t in TEAMS}
        self.contact_opp = {}                            # (r, o) -> dict(k_first, k_last, approach sums)
        self.ball_contact = {r: -10 ** 9 for r in ROBOTS}
        self.last_touch = None
        self.stuck_anchor = None
        self.stuck_k = 0
        self.global_k = 0
        self.extension_k = 0
        self.stats = {r: dict(goals=0, own_goals=0, shootout_goals=0, touches=0, passes_completed=0, kicks=0, kick_falls=0, kicks_cancelled=0, kicks_timed=0, kicks_retimed=0, kicks_late=0, falls=0, pushed_over=0,
                              penalties=0, offenses=[], distance_m=0.0) for r in ROBOTS}
        self.pso = None
        self.hist = deque(maxlen=40)
        self.review_hist = None
        mujoco.mj_resetData(self.m, self.d)
        self.motors.cool_down()                          # a new match: cold motors (heat stays across placements)
        self.place_ball(0, 0)
        self._kickoff_positions()
        # the first kick-off has the same conditions as every other one (HSL Law 8.1)
        self.ko = dict(team=self.kickoff_team, k0=self.k, in_play=False, touched_outside=False)
        mujoco.mj_forward(self.m, self.d)
        for c in self.coaches.values():
            c.reset()
        self._prev_xy = {r: self.rob[r].xy(self.d) for r in ROBOTS}
        self.snap()

    def _jitter(self, salt, scale):
        rng = np.random.default_rng([self.seed, self.kickoff_index, salt])
        return rng.uniform(-scale, scale, 2)

    # kick-off formations (team frame; robot 1 first): the kicking team's and the other's
    KICKOFF_SPOTS = {
        2: ([(-KICKOFF_SPOT[0], KICKOFF_SPOT[1]), (-2.5, -1.5)], [(-1.6, 0.4), (-3.6, -0.8)]),
        5: ([(-HALF_L + 0.6, 0.0), (-KICKOFF_SPOT[0], KICKOFF_SPOT[1]), (-2.4, 2.5), (-2.4, -2.3), (-4.3, -0.9)],
            [(-HALF_L + 0.6, 0.0), (-2.1, 0.5), (-3.0, 2.6), (-3.0, -2.4), (-4.6, 0.9)]),
    }
    KICKER = 0 if N == 2 else 1                          # index of the kick-off taker in the kicking formation

    def _kickoff_positions(self, dropped=False):
        """Kick-off (HSL Law 8.1) or dropped ball (Law 8.2) formation, in each team's frame; seeded jitter."""
        self.place_ball(0, 0)
        for t in TEAMS:
            kicking = (t == self.kickoff_team) and not dropped
            spots = [(x, y, 0.0) for x, y in self.KICKOFF_SPOTS[N][0 if kicking else 1]]
            for j, (name, (x, y, yaw)) in enumerate(zip(TEAM_ROBOTS[t], spots)):
                if kicking and j == self.KICKER:
                    dx, dy = self._jitter(1, 0.05)
                elif GOALKEEPER and j == GOALKEEPER - 1:
                    dx, dy = 0.0, float(self._jitter(10 + 2 * j + (t == "B"), 0.1)[1])
                else:
                    dx, dy = self._jitter(10 + 2 * j + (t == "B"), 0.3)
                p = from_team(t, (x + dx, y + dy))
                self.place(name, p[0], p[1], float(_wrap(yaw + (0 if t == "A" else np.pi))))
        self.fallen = {r: None for r in ROBOTS}
        self.hold = {r: 0 for r in ROBOTS}
        self.contact_opp = {}
        self.fk = None

    def _restart(self, kind):
        """Place everything for the next phase (immediately at the stoppage; play resumes after the reviews)."""
        self.kickoff_index += 1
        self.stuck_anchor, self.stuck_k, self.global_k = None, 0, 0
        if kind in ("kickoff", "dropped"):
            for r in ROBOTS:
                if self.penalty[r] and not self.penalty[r].get("pso"):
                    continue                                   # a removal penalty is served off the pitch
                self.penalty[r] = None
            self._kickoff_positions(dropped=kind == "dropped")
            for r in ROBOTS:                                   # penalized robots stay on the bench
                if self.penalty[r]:
                    self._to_bench(r)
            self.state = "play" if kind == "dropped" else "kickoff"
            self.ko = None if kind == "dropped" else dict(team=self.kickoff_team, k0=self.k, in_play=False,
                                                          touched_outside=False)
        mujoco.mj_forward(self.m, self.d)
        for c in self.coaches.values():
            c.reset()

    # ------------------------------------------------------------------ penalties
    def bench_xy(self, name):
        t = name[0]
        if N == 2:
            side = 1 if name[1] == "1" else -1
            return from_team(t, (-(HALF_L - PEN_MARK), side * (HALF_W + 0.8)))
        # 5 v 5: beyond the carpet on the team's own (tactical camera) side, in its own half, one spot per robot
        return from_team(t, (-(HALF_L - PEN_MARK) + 0.9 * (int(name[1:]) - 1), -(PLAY_Y + 0.8)))

    def on_bench(self, name):
        return self.penalty[name] is not None

    def _to_bench(self, name):
        x, y = self.bench_xy(name)
        self.place(name, x, y, float(np.arctan2(-y, 0.0)))
        self.fallen[name] = None
        self.hold[name] = 0

    def _penalize(self, name, why, counts=True, pso=False):
        if self.penalty[name] is not None:
            return
        t = name[0]
        dur = PENALTY_S + PENALTY_INC_S * self.team_offenses[t]
        if counts:
            self.team_offenses[t] += 1
        self.penalty[name] = dict(until=self.k + int(round(dur / CONTROL_DT)), why=why, pso=pso)
        self.stats[name]["penalties"] += 1
        self.stats[name]["offenses"].append(why)
        self._to_bench(name)
        self.event("penalty", robot=name, why=why, seconds=dur)

    def _release(self, name):
        x, y = self.bench_xy(name)
        y_in = np.sign(y) * (HALF_W - 0.45)          # back on the pitch beside the touchline, at the same x
        p = self.free_spot(name, x, y_in)
        self.penalty[name] = None
        self.place(name, p[0], p[1], float(np.arctan2(-np.sign(y), 0.0)))
        self.event("penalty_over", robot=name)

    # ------------------------------------------------------------------ commands
    def command(self, name, cmd):
        """A robot's new command, taking effect at this control step (replaces the one under way)."""
        if self.stopped or self.done:
            raise RuntimeError("the world is stopped")
        self.acts.append((self.k, name, cmd))
        self._set_prog(name, cmd)

    def _set_prog(self, name, cmd):
        t = cmd["type"]
        if t in ("joints", "traj"):                    # the joint level: a row for the next step, or a plan
            if name not in self.joint:
                raise ValueError(f"{name} is not under joint control")
            if t == "joints":
                rows, k0 = np.asarray(cmd["q"], float).reshape(1, 12), self.k
            else:
                rows = np.asarray(cmd["q"], float).reshape(-1, 12)[:TRAJ_MAX]
                k0 = max(int(cmd.get("k0", self.k)), self.k)
            self.jplan[name] = (k0, rows)
            return
        if name in self.joint:
            raise ValueError(f"{name} is under joint control: joints or traj only")
        if t == "walk":
            self.prog[name] = dict(type="walk", v=[float(x) for x in cmd["v"]])
        elif t == "stand":
            self.prog[name] = dict(type="stand")
        elif t == "kick" and cmd.get("style", "swing") == "push":
            p = float(np.clip(cmd.get("power", 1.0), 0.0, 1.0))
            v = 0.6 + 0.4 * p
            n0 = int(round(KICK["stand_s"] / CONTROL_DT))
            n1 = int(round(KICK["run_m"] / v / CONTROL_DT))
            n2 = int(round(KICK["after_s"] / CONTROL_DT))
            self.prog[name] = dict(type="kick", style="push", power=p, v=v, k0=self.k, n0=n0, n1=n1, n2=n2,
                                   yaw0=None, k_end=None)
            self.stats[name]["kicks"] += 1
        elif t == "kick" and cmd.get("style") == "step":
            # the in-walk kick (step_kick.py): walk on with v (the command's, else the current walk's, else STEP
            # v_default) until the kicking foot's swing can reach the ball, then that swing kicks it
            p = float(np.clip(cmd.get("power", 1.0), 0.0, 1.0))
            foot = "left" if cmd.get("foot") == "left" else "right"
            lo, hi = (-STEP["aim_max"], STEP["aim_in_max"]) if foot == "right" else (-STEP["aim_in_max"], STEP["aim_max"])
            aim = float(np.clip(cmd.get("aim", 0.0), lo, hi))
            cur = self.prog[name]
            if cmd.get("v") is not None:
                v = [float(np.clip(x, -CMD_LIMITS[c], CMD_LIMITS[c])) for x, c in zip(cmd["v"], ("vx", "vy", "wz"))]
            elif cur.get("type") == "walk":
                v = list(cur["v"])
            else:
                v = list(STEP["v_default"])
            kk = STK.StepKick(self.m, self._kin, self.rob[name], self.kick_geom, p, aim_rel=aim, foot=foot)
            self.prog[name] = dict(type="kick", style="step", power=p, aim=aim, foot=foot, k0=self.k, kicker=kk, v=v)
            self.stats[name]["kicks"] += 1
        elif t == "kick":
            p = float(np.clip(cmd.get("power", 1.0), 0.0, 1.0))
            foot = "left" if cmd.get("foot") == "left" else "right"
            lo, hi = (-SWING["aim_max"], SWING["aim_in_max"]) if foot == "right" else \
                (-SWING["aim_in_max"], SWING["aim_max"])
            aim = float(np.clip(cmd.get("aim", 0.0), lo, hi))
            at = cmd.get("at")
            if at is not None:                  # the timed kick: the ball's centre at (x, y) (team frame) t s from now
                tt = float(np.clip(at[0], 0.0, SWING["at_t_max"]))
                xy = from_team(name[0], (float(at[1]), float(at[2])))
                cur = self.prog[name]
                kk = cur.get("kicker") if cur.get("type") == "kick" and cur.get("style") == "swing" else None
                if cur.get("at") is not None and cur.get("foot") == foot and abs(cur.get("aim", 0.0) - aim) < 1e-9 \
                        and cur.get("recover_k") is None:
                    # the same timed kick, refined before its swing: new time and point, no new preparation
                    tgt = self._timed_target(name, xy, aim) if kk is not None else None
                    if kk is None or kk.retime(tt, tgt):
                        cur.update(at=[tt, float(xy[0]), float(xy[1])], k_at=self.k, power=p)
                        if kk is not None:
                            kk.speed = SWING["speed_min"] + (SWING["speed_max"] - SWING["speed_min"]) * p
                        self.stats[name]["kicks_retimed"] += 1
                        return
                self.prog[name] = dict(type="kick", style="swing", power=p, aim=aim, foot=foot, k0=self.k,
                                       kicker=None, ready=0, at=[tt, float(xy[0]), float(xy[1])], k_at=self.k)
                self.stats[name]["kicks"] += 1
                self.stats[name]["kicks_timed"] += 1
                return
            self.prog[name] = dict(type="kick", style="swing", power=p, aim=aim, foot=foot, k0=self.k, kicker=None,
                                   ready=0)
            self.stats[name]["kicks"] += 1
        else:
            raise ValueError(t)

    def _swing_ready(self, name):
        """A swing kick starts once the walking controller has stopped the robot (the rate-limited walking command is
        zero and the trunk moves slower than SWING ready_v) and the ball rolls slower than SWING ball_still_v. If that
        does not happen within SWING ready_max_s, the kick starts anyway (cancel_late False) or is called off: the
        robot stands (cancel_late True; stats kicks_cancelled)."""
        p, r = self.prog[name], self.rob[name]
        wz = float(self.d.qvel[r.rv + 5])
        still = not np.any(self.cmd_lim[name].cmd) and float(np.hypot(*r.vel(self.d))) < SWING["ready_v"] \
            and abs(wz) < SWING["ready_w"] and (p.get("at") is not None or            # timed: no wait for the ball
                                                float(np.hypot(*self.ball_v())) < SWING["ball_still_v"])
        if still:
            self._start_swing(name)
        elif p["ready"] * CONTROL_DT >= SWING["ready_max_s"]:
            if SWING["cancel_late"]:
                self.stats[name]["kicks_cancelled"] += 1
                moving = float(np.hypot(*self.ball_v())) >= SWING["ball_still_v"]
                self.event("kick_cancelled", robot=name, why="the ball was still rolling" if moving else
                           "the robot did not stop in time")
                self.prog[name] = dict(type="stand")
            else:
                self._start_swing(name)
        else:
            p["ready"] += 1

    def _start_swing(self, name):
        """The swing at the ball as it lies now (the robot's own close-range view of the ball: a kick's motion is
        planned from where the ball is when it starts; the player never sees these coordinates)."""
        p, r, d = self.prog[name], self.rob[name], self.d
        yaw = SK.yaw_of_mat(d.xmat[self.m.body(name + ":Trunk").id].reshape(3, 3)) + p["aim"]
        u = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        speed = SWING["speed_min"] + (SWING["speed_max"] - SWING["speed_min"]) * p["power"]
        if p.get("at") is not None:            # timed: the player's point and time; the ball is not read
            tgt = self._timed_target(name, p["at"][1:], p["aim"])
            t_strike = p["at"][0] - (self.k - p["k_at"]) * CONTROL_DT
            p["kicker"] = SK.SwingKick(self.m, d, self._kin, r, self.kick_geom, self.pol.default, speed, target=tgt,
                                       direction=u[:2], end_q=self._stand_targets, foot=p.get("foot", "right"),
                                       t_strike=t_strike)
            return
        tgt = self.ball_pos() + np.array([0.0, 0.0, SWING["z_off"]]) - u * (BALL_R + SWING["gap"])
        p["kicker"] = SK.SwingKick(self.m, d, self._kin, r, self.kick_geom, self.pol.default, speed, target=tgt,
                                   direction=u[:2], end_q=self._stand_targets, foot=p.get("foot", "right"))

    def _timed_target(self, name, xy, aim):
        """The timed kick's strike point (world): the given ball centre (world xy, the ball's centre height), BALL_R +
        SWING gap back along the kick's direction (the robot's heading now turned by aim)."""
        yaw = self.rob[name].yaw(self.d) + aim
        u = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        return np.array([float(xy[0]), float(xy[1]), BALL_R + SWING["z_off"]]) - u * (BALL_R + SWING["gap"])

    def _cmd_now(self, name):
        """The walking command of this control step from the robot's program (before the command rate limit)."""
        if self.fallen[name] is not None or self.penalty[name] is not None or name in self.joint:
            return (0.0, 0.0, 0.0)
        p = self.prog[name]
        if p["type"] == "walk":
            return p["v"]
        if p["type"] == "kick" and p["style"] == "step":     # the in-walk kick: the policy walks on (and balances the
            return p["v"] if p.get("recover_k") is None else (0.0, 0.0, 0.0)   # kick), then steps to a stop
        if p["type"] == "stand" or p["style"] == "swing":
            return (0.0, 0.0, 0.0)              # a swing kick: the legs are the kick's (the policy stands by)
        # the push: stand, run straight holding the heading until a foot is through the ball (at most run_max_factor x
        # the nominal run), stand
        i = self.k - p["k0"]
        r, d = self.rob[name], self.d
        if i < p["n0"]:
            return (0.0, 0.0, 0.0)
        if i == p["n0"]:
            self.pol.gait[r.idx] = 0.0
            p["yaw0"] = r.yaw(d)
            p["u"] = np.array([math.cos(p["yaw0"]), math.sin(p["yaw0"])])
            p["p0"] = r.xy(d)
            p["reach"] = float((self.ball_xy() - p["p0"]) @ p["u"]) + KICK["through_m"]
        if p["k_end"] is None:
            fwd = max(float((d.site_xpos[sid][:2] - p["p0"]) @ p["u"]) for sid in r.feet)
            if fwd < p["reach"] and i < p["n0"] + math.ceil(KICK["run_max_factor"] * p["n1"]):
                e = _wrap(p["yaw0"] - r.yaw(d))
                return (p["v"], 0.0, float(np.clip(2.0 * e, -0.5, 0.5)))
            p["k_end"] = i
        if i >= p["k_end"] + p["n2"]:
            self.prog[name] = dict(type="stand")
        return (0.0, 0.0, 0.0)

    def kicking(self, name):
        p = self.prog[name]
        return p["type"] == "kick"

    def _handback(self, name):
        """The swing kick is over (and the robot stands still: SwingKick's stability check): the walking policy takes
        the legs again, its memory reset to the standing state."""
        r = self.rob[name]
        self.pol.set(r.idx, (self._settled["pol"][0], 0.0, 0.0))
        self.cmd_lim[name].reset()
        n = int(round(SWING["recover_s"] / CONTROL_DT))
        if n > 0:                                      # the kick's last part: the policy steps in place a moment
            self.prog[name]["recover_k"] = self.k + n
        else:
            self.prog[name] = dict(type="stand")

    def _step_over(self, name):
        """the in-walk kick is over: the policy takes the kicking leg again in its late swing (it puts the foot down)
        and stops; or the ball never came in reach (called off)"""
        p = self.prog[name]
        kk = p["kicker"]
        if kk.cancelled:
            self.stats[name]["kicks_cancelled"] += 1
            self.event("kick_cancelled", robot=name, why=kk.why)
            self.prog[name] = dict(type="stand")
            return
        self.pol.gait[self.rob[name].idx] = kk.gait_release()
        p["recover_k"] = self.k + int(round(STEP["recover_s"] / CONTROL_DT))

    def _abort_kick(self, name):
        """A robot that falls during a kick: the kick ends (the robot lies still until it is stood up)."""
        p = self.prog[name]
        if p["type"] == "kick":
            if p["style"] == "swing":
                self.stats[name]["kick_falls"] += 1
            self.prog[name] = dict(type="stand")

    # ------------------------------------------------------------------ physics
    def _rolling_resistance(self):
        d, b = self.d, self._bb
        d.xfrc_applied[b, :] = 0.0
        if d.xipos[b][2] > BALL_R + 0.02:
            return
        v = d.cvel[b][3:5]
        sp = float(np.hypot(v[0], v[1]))
        if sp > 1e-6:
            d.xfrc_applied[b, :2] = -self._rr_force * min(1.0, sp / 0.05) * v / sp

    def _physics_tick(self, cmds):
        """One control step: the walking commands through the command rate limit, the policy for all robots, then
        SUB physics steps; each robot's legs run PD toward the policy's targets (a kicking robot: the swing kick's
        targets, gains and feed-forward, every 5 physics steps), the torques within the real motors' torque-speed
        envelope and torque limits (bodies/servo.py Actuators)."""
        m, d, pol = self.m, self.d, self.pol
        rs = list(self.rob.values())
        for r in rs:                                   # swing kicks: start when ready; when over, the policy takes
            p = self.prog[r.name]                      # the legs again
            if p["type"] == "kick" and p["style"] == "swing" and self.fallen[r.name] is None:
                if p["kicker"] is None:
                    self._swing_ready(r.name)
                elif p.get("recover_k") is not None:
                    if self.k >= p["recover_k"]:
                        self.prog[r.name] = dict(type="stand")
                elif p["kicker"].done:
                    self._handback(r.name)
            elif p["type"] == "kick" and p["style"] == "step" and self.fallen[r.name] is None and p["kicker"].done:
                if p.get("recover_k") is None:
                    self._step_over(r.name)
                elif self.k >= p["recover_k"]:
                    self.prog[r.name] = dict(type="stand")
        cmds = np.array([self.cmd_lim[r.name](c).copy() for r, c in zip(rs, np.asarray(cmds, float))])
        dq = [d.qpos[r.jq].astype(np.float32) for r in rs]
        dv = [d.qvel[r.jv].astype(np.float32) for r in rs]
        qs = [d.sensordata[r.s_quat:r.s_quat + 4][[1, 2, 3, 0]].astype(np.float32) for r in rs]
        gs = [d.sensordata[r.s_gyro:r.s_gyro + 3].astype(np.float32) for r in rs]
        gait_on = [self.prog[r.name].get("recover_k") is not None or self.prog[r.name].get("style") == "step"
                   for r in rs]                  # recovery steps after a kick; the in-walk kick steps
        pol.infer(cmds, dq, dv, qs, gs, gait_on)
        tg = pol.targets().astype(np.float64)
        kp = np.tile(pol.kp.astype(np.float64), (len(rs), 1))
        kd = np.tile(pol.kd.astype(np.float64), (len(rs), 1))
        ff = np.zeros_like(tg)
        kick = {}
        for i, r in enumerate(rs):
            p = self.prog[r.name]
            if p["type"] == "kick" and p["style"] == "swing" and p["kicker"] is not None \
                    and p.get("recover_k") is None and self.fallen[r.name] is None and self.penalty[r.name] is None:
                kick[i] = p["kicker"]
        step = {}
        for i, r in enumerate(rs):
            p = self.prog[r.name]
            if p["type"] == "kick" and p["style"] == "step" and not p["kicker"].done \
                    and self.fallen[r.name] is None and self.penalty[r.name] is None:
                step[i] = p["kicker"]
        held = []
        for i, r in enumerate(rs):                     # the joint level: this step's limited row
            if r.name not in self.jrow:                 # not under joint control (or before the first placement)
                continue
            n = r.name
            if self.on_bench(n):
                tg[i] = self._jstance["joints"]          # benched: held standing
                held.append(r)
                continue
            if self.fallen[n] is not None:               # fallen: the motors go limp (damping only) until stood up
                tg[i] = d.qpos[r.jq]
                continue
            plan, row = self.jplan.get(n), self.jrow[n]
            if plan is not None:
                k0, rows = plan
                j = min(self.k - k0, len(rows) - 1)
                if j >= 0:
                    t = np.where(np.isfinite(rows[j]), rows[j], row)
                    t = np.clip(t, row - ROW_STEP, row + ROW_STEP)
                    row = np.clip(t, self._jlo[n], self._jhi[n])
                if self.k - k0 >= len(rows) - 1:
                    self.jplan[n] = None                 # used up: the last row stays
            self.jrow[n] = row
            tg[i] = row
            if self.held.get(n) is not None and self.k < self.held[n]:
                held.append(r)
        tg_pol = tg.copy()
        touched = set()
        for s in range(SUB):
            self._rolling_resistance()
            for i, kk in kick.items():
                if s % 5 == 0 and not kk.done:        # the kick's 10 ms tick
                    tg[i] = kk.step(d)
                    kp[i], kd[i], ff[i] = kk.kp, kk.kd, kk.ff
            for i, kk in step.items():                 # the in-walk kick: the kicking leg's targets while it swings
                if s % 5 == 0 and not kk.done:
                    out = kk.step(d, float(pol.gait[i]), self.ball_pos(), tg_pol[i])
                    if out is not None:
                        tg[i] = out
                        c = kk.legcols[kk.foot]
                        kp[i, c], kd[i, c] = kk.kp[c], kk.kd[c]
                    else:
                        tg[i] = tg_pol[i]
                        kp[i], kd[i] = pol.kp, pol.kd
            q, v = d.qpos[self._jq], d.qvel[self._jv]
            tau = kp * (tg - q) - kd * v + ff
            self.motors.write(d, tau.reshape(-1))      # every actuator of the scene is a leg motor (4 x 12)
            mujoco.mj_step(m, d)
            for r in held:                             # the referee's hand on a held trunk
                d.qpos[r.rq:r.rq + 7] = self.held_pose[r.name]
                d.qvel[r.rv:r.rv + 6] = 0.0
            pol.advance_gait()
            for i, kk in step.items():                 # the policy's gait clock waits while the kicking foot swings
                h = kk.gait_hold()
                if h is not None:
                    pol.gait[i] = h
            for c in range(d.ncon):
                con = d.contact[c]
                g1, g2 = int(con.geom1), int(con.geom2)
                touched.add((g1, g2))
        return touched

    # ------------------------------------------------------------------ queries
    def ball_xy(self):
        return self.d.geom_xpos[self._bg][:2].copy()

    def ball_pos(self):
        return self.d.geom_xpos[self._bg].copy()

    def ball_v(self):
        return self.d.qvel[self._bv:self._bv + 2].copy()

    def t(self):
        return self.k * CONTROL_DT

    def clock(self):
        return self.period_k * CONTROL_DT

    def event(self, ev, **kw):
        self.events.append({**dict(ev=ev, k=self.k, t=round(self.t(), 3), period=self.period), **kw})

    # ------------------------------------------------------------------ one control step
    def advance(self):
        if self.stopped or self.done:
            raise RuntimeError("the world is stopped")
        for t, c in self.coaches.items():
            for name, cmd in c.decide(self).items():
                if cmd is not None:
                    self._set_prog(name, cmd)
        cmds = np.array([self._cmd_now(r) for r in ROBOTS], float)
        pairs = self._physics_tick(cmds)
        for r in ROBOTS:                        # timed kicks: the swing has begun; tell the team when it is late
            p = self.prog[r]
            kk = p.get("kicker") if p["type"] == "kick" else None
            if kk is not None and p.get("at") is not None and kk.late is not None and not p.get("late_told"):
                p["late_told"] = True
                if kk.late > 0.02:
                    self.stats[r]["kicks_late"] += 1
                    self.event("kick_late", robot=r, late_s=round(kk.late, 2))
        self.k += 1
        self.period_k += 1
        for n in self.joint:                    # the joint level: the referee lets go of a held robot
            if self.held.get(n) == self.k and not self.on_bench(n):
                self.event("released", robot=n)
        self._referee(pairs)
        self.snap()

    def snap(self):
        self.hist.append(dict(k=self.k, qpos=self.d.qpos.copy(), t=round(self.t(), 3), clock=round(self.clock(), 2),
                              period=self.period, score=dict(self.score)))

    # ------------------------------------------------------------------ the referee
    def _referee(self, pairs):
        d = self.d
        k = self.k
        # contacts of this step
        ball_by = set()
        opp = set()
        keeper_touch = post_touch = False
        for g1, g2 in pairs:
            r1, r2 = self._geom_robot.get(g1), self._geom_robot.get(g2)
            if self._bg in (g1, g2):
                o = g2 if g1 == self._bg else g1
                if o in self._geom_robot:
                    ball_by.add(self._geom_robot[o])
                elif o in self._post:
                    post_touch = True
            elif r1 and r2 and r1[0] != r2[0]:
                opp.add(tuple(sorted((r1, r2))))
        for r in self.rob:                                  # distance walked
            xy = self.rob[r].xy(d)
            if not self.on_bench(r):
                self.stats[r]["distance_m"] += float(np.hypot(*(xy - self._prev_xy[r])))
            self._prev_xy[r] = xy
        bxy = self.ball_xy()
        # touches, passes
        for r in sorted(ball_by):
            if k - self.ball_contact[r] > 10:
                self.stats[r]["touches"] += 1
                lt = self.last_touch
                if lt is not None and lt != r and lt[0] == r[0]:
                    self.stats[lt]["passes_completed"] += 1
                    self.event("pass", robot=lt, to=r)
                self.last_touch = r
                if self.fk:
                    if self.fk["kicker"] is None:
                        self.fk["kicker"] = r
                    elif r != self.fk["kicker"]:
                        self.fk["other"] = True
                if self.ko and r[0] == self.ko["team"] and np.hypot(*bxy) > CENTER_R:
                    self.ko["touched_outside"] = True
                if self.pso and r == self.pso["cur"]["keeper"] and self.pso["cur"].get("touched"):
                    self.pso["cur"]["saved"] = True
                if self.pso and r == self.pso["cur"]["striker"]:
                    cur = self.pso["cur"]
                    if not cur.get("touched"):
                        cur["touched"] = k
                    elif np.hypot(*(bxy - cur["spot"])) > 0.3 and k - self.ball_contact[r] > 10:
                        cur["second_touch"] = True
            self.ball_contact[r] = k
        if post_touch and self.pso and self.pso["cur"].get("touched"):
            self.pso["cur"]["post"] = True
        # robot-robot contact between opponents (pushing)
        gap = int(round(PUSH_GAP_S / CONTROL_DT))
        for (a, b) in sorted(opp):                                   # sorted: str hashing varies per process
            xa, xb = self.rob[a].xy(d), self.rob[b].xy(d)
            c = self.contact_opp.setdefault((a, b), dict(k0=k, k=k, va=0.0, vb=0.0, n=0, pa=xa, pb=xb))
            if k - c["k"] > gap:                                      # a new contact
                c.update(k0=k, va=0.0, vb=0.0, n=0, pa=xa, pb=xb)
            u = xb - xa
            u /= max(np.hypot(*u), 1e-6)
            c["k"] = k
            c["va"] += float(np.dot(self.rob[a].vel(d), u))          # a moving towards b
            c["vb"] += float(np.dot(self.rob[b].vel(d), -u))         # b moving towards a
            c["n"] += 1
            if self.state == "pso_kick":
                continue
            va, vb = c["va"] / c["n"], c["vb"] / c["n"]
            moved_b, moved_a = float(np.dot(xb - c["pb"], u)), float(np.dot(xa - c["pa"], -u))
            if moved_b > PUSH_DISPLACE_M and va > vb + PUSH_MIN_V and not self._kick_exempt(a):
                self._penalize(a, f"pushing ({b} pushed back)")
                c.update(k0=k, va=0.0, vb=0.0, n=0, pa=xa, pb=xb)
            elif moved_a > PUSH_DISPLACE_M and vb > va + PUSH_MIN_V and not self._kick_exempt(b):
                self._penalize(b, f"pushing ({a} pushed back)")
                c.update(k0=k, va=0.0, vb=0.0, n=0, pa=xa, pb=xb)
            elif (k - c["k0"]) * CONTROL_DT > PUSH_LONG_S:
                if max(va, vb) > 0.05:
                    self._penalize(a if va >= vb else b, "pushing (contact over 5 s)")
                c.update(k0=k, va=0.0, vb=0.0, n=0, pa=xa, pb=xb)
        # penalties served
        for r in ROBOTS:
            p = self.penalty[r]
            if p and not p.get("pso") and k >= p["until"]:
                self._release(r)
        # falls and get-ups
        for r in ROBOTS:
            if self.on_bench(r):
                continue
            rb = self.rob[r]
            if self.fallen[r] is None and rb.height(d) < FALL_Z:
                self.fallen[r] = k
                self._abort_kick(r)
                self.stats[r]["falls"] += 1
                self.event("fall", robot=r)
                self._judge_push(r)
            elif self.fallen[r] is not None and (k - self.fallen[r]) * CONTROL_DT >= GETUP_S and not self.on_bench(r):
                x, y = rb.xy(d)
                p = self.free_spot(r, x, y, r_ball=0.4)
                self.place(r, p[0], p[1], rb.yaw(d))
                self.fallen[r] = None
                self.event("get_up", robot=r)
        # leaving the field (HSL Law 12): off the carpet, or inside a goal for more than 5 s
        if self.state != "pso_kick":
            for r in ROBOTS:
                if self.on_bench(r):
                    self.in_goal_k[r] = 0
                    continue
                xy = self.rob[r].xy(d)
                if off_carpet(xy):
                    self._penalize(r, "leaving the field")
                elif in_goal(xy):
                    self.in_goal_k[r] += 1
                    if self.in_goal_k[r] * CONTROL_DT > GOAL_STUCK_S:
                        self._penalize(r, "leaving the field (in a goal more than 5 s)")
                        self.in_goal_k[r] = 0
                else:
                    self.in_goal_k[r] = 0
        mujoco.mj_forward(self.m, d)
        bxy = self.ball_xy()
        if self.state == "pso_kick":
            self._pso_step(bxy)
            return
        # kick-off: ball in play, illegal positions
        if self.ko and not self.ko["in_play"]:
            if np.hypot(*bxy) > 0.15 or (k - self.ko["k0"]) * CONTROL_DT >= KICKOFF_FREE_S:
                self.ko["in_play"] = True
                self.state = "play"
                self.event("ball_free")
            else:
                kt = self.ko["team"]
                for r in ROBOTS:
                    if self.on_bench(r):
                        continue
                    p = to_team(r[0], self.rob[r].xy(d))
                    in_circle = np.hypot(*p) < CENTER_R
                    kicker_ok = r[0] == kt and in_circle
                    if (p[0] > 0.05 and not kicker_ok) or (r[0] != kt and in_circle):
                        self._penalize(r, "illegal position at kick-off", counts=False)
        # ball holding
        for r in ROBOTS:
            if self.on_bench(r) or self.fallen[r] is not None:
                self.hold[r] = max(0, self.hold[r] - 1)
                continue
            if np.hypot(*(bxy - self.rob[r].xy(d))) < HOLD_R:
                self.hold[r] += 1
                lim = HOLD_KEEPER_S if (GOALKEEPER and int(r[1:]) == GOALKEEPER
                                        and in_own_area(to_team(r[0], self.rob[r].xy(d)))) else HOLD_S
                if self.hold[r] * CONTROL_DT > lim:
                    self._penalize(r, "ball holding")
                    self.hold[r] = 0
            else:
                self.hold[r] = max(0, self.hold[r] - 1)
        # illegal defence: 2 v 2 at most one robot of a team in its own penalty area (a team cannot park both in its
        # goal); 5 v 5 at most three in its own goal area (HSL Law 12 illegal positioning)
        for t in TEAMS:
            area = in_own_area if N == 2 else in_own_goal_area
            inside = []
            for r in TEAM_ROBOTS[t]:
                if not self.on_bench(r) and area(to_team(t, self.rob[r].xy(d))):
                    inside.append(r)
                    if self.area_entry[r] is None:
                        self.area_entry[r] = k
                else:
                    self.area_entry[r] = None
            self.crowd[t] = self.crowd[t] + 1 if len(inside) > MAX_IN_AREA else 0
            if self.crowd[t] * CONTROL_DT > CROWD_S:
                if N == 2:
                    off = max(inside, key=lambda r: (np.hypot(*(self.rob[r].xy(d) - bxy)), r))
                    why = "illegal defence (two robots in the own penalty area)"
                else:                                   # the robot that entered last
                    off = max(inside, key=lambda r: (self.area_entry[r], r))
                    why = "illegal defence (more than three robots in the own goal area)"
                self._penalize(off, why, counts=False)
                self.crowd[t] = 0
        if self.fk is not None:
            self._free_kick_step(bxy)
        # goals
        bp = self.ball_pos()
        for s, scorer in ((1, "A"), (-1, "B")):
            if s * bp[0] > HALF_L + BALL_R and abs(bp[1]) < GOAL_W / 2 and bp[2] < GOAL_H:
                return self._goal(scorer)
        if BOARDS:
            if abs(bp[0]) > HALF_L + 0.4 or abs(bp[1]) > HALF_W + 0.4 or bp[2] < -0.5:
                return self._stop("ball_out", "dropped")
        elif abs(bp[1]) > HALF_W + BALL_R or abs(bp[0]) > HALF_L + BALL_R:
            self._ball_out(bp)
            bxy = self.ball_xy()
        # game stuck
        near = [r for r in ROBOTS if not self.on_bench(r) and np.hypot(*(self.rob[r].xy(d) - bxy)) < STUCK_NEAR_M]
        if self.stuck_anchor is None or np.hypot(*(bxy - self.stuck_anchor)) > LOCAL_STUCK_M or \
                (self.fk is not None and not self.fk["in_play"]):         # no game stuck before a free kick is taken
            self.stuck_anchor, self.stuck_k = bxy, 0
        else:
            self.stuck_k += 1
        if BOARDS and self.state == "play" and self.stuck_k * CONTROL_DT > BOARD_STUCK_S and self._at_board(bxy):
            self._replace_ball(bxy)                       # instead of kick-ins, goal kicks and corners
            bxy = self.ball_xy()
            self.stuck_anchor, self.stuck_k = bxy, 0
        if self.stuck_k * CONTROL_DT > LOCAL_STUCK_S and near and self.state == "play":
            nearest = min(near, key=lambda r: (np.hypot(*(self.rob[r].xy(d) - bxy)), r))
            self._penalize(nearest, "local game stuck", counts=False)
            self.stuck_anchor, self.stuck_k = bxy, 0
        self.global_k = 0 if near else self.global_k + 1
        if self.global_k * CONTROL_DT > GLOBAL_STUCK_S:
            return self._stop("global_game_stuck", "dropped")
        # the period's end (ball stop rule: up to BALL_STOP_EXT_S while the ball rolls)
        if self.clock() >= HALF_S:
            if float(np.hypot(*self.ball_v())) > 0.2 and self.extension_k * CONTROL_DT < BALL_STOP_EXT_S:
                self.extension_k += 1
                return
            self.extension_k = 0
            for r in ROBOTS:
                self.penalty[r] = None                      # removal penalties end with the half (HSL Law 12)
            if self.period == 1:
                self.kickoff_team = OTHER[self.first_kickoff]
                self._stop("half_time", "kickoff")
                self.period, self.period_k = 2, 0
                return
            if self.score["A"] != self.score["B"]:
                return self._finish("full_time", "regulation")
            self._stop("full_time", "pso")
            self.period, self.period_k = "pso", 0

    # ------------------------------------------------------------------ out of play and free kicks (5 v 5; HSL Laws 9, 13, 15-17)
    def _ball_out(self, bp):
        """The whole ball left the field (not a goal): kick-in, goal kick or corner kick, by the last touch."""
        lt = self.last_touch[0] if self.last_touch else None
        if abs(bp[1]) > HALF_W + BALL_R:                         # over a touchline: kick-in (indirect)
            team = OTHER[lt] if lt else ("A" if bp[0] < 0 else "B")
            spot = (float(np.clip(bp[0], -HALF_L + 0.3, HALF_L - 0.3)), float(np.sign(bp[1]) * HALF_W))
            return self._free_kick(team, "kick_in", spot)
        s = 1.0 if bp[0] > 0 else -1.0
        defending = "B" if s > 0 else "A"
        sy = 1.0 if bp[1] >= 0 else -1.0
        if lt == defending:                                     # corner kick for the attackers
            return self._free_kick(OTHER[defending], "corner_kick", (s * HALF_L, sy * HALF_W))
        return self._free_kick(defending, "goal_kick", (s * (HALF_L - GOAL_AREA[0]), sy * GOAL_AREA[1] / 2))

    def _clear_spot(self, name, xy, spot, radius, avoid_area=None):
        """Where the referee moves an opponent at a free kick: the nearest point on a ring around the ball outside the
        avoidance radius (and outside the kicking team's penalty area at a goal kick), on the field, clear of robots."""
        d = self.d
        others = [self.rob[o].xy(d) for o in ROBOTS if o != name and not self.on_bench(o)]
        best = None
        sgn = 1.0 if name[0] == "A" else -1.0              # candidates in the robot's team frame (mirror symmetry)
        for rr in (radius + 0.45, radius + 0.9, radius + 1.4, radius + 2.0):
            for j in range(36):
                a = 2 * np.pi * j / 36
                p = np.asarray(spot) + sgn * rr * np.array([np.cos(a), np.sin(a)])
                if abs(p[0]) > HALF_L - 0.3 or abs(p[1]) > HALF_W - 0.3:
                    continue
                if avoid_area and in_own_area(to_team(avoid_area, p), 0.45):
                    continue
                if any(np.hypot(*(p - o)) < 0.65 for o in others):
                    continue
                c = (float(np.hypot(*(p - xy))), j)
                if best is None or c < best[0]:
                    best = (c, p)
            if best is not None:
                return best[1]
        return np.asarray(xy)

    def _fk_violator(self, r, team, kind, spot, margin):
        """An opponent of the free kick's team inside its avoidance region (the centre circle radius around the ball;
        at a goal kick also the kicking team's penalty area); its goalkeeper on its own goal line between the posts is
        exempt."""
        xy = self.rob[r].xy(self.d)
        p = to_team(r[0], xy)
        if GOALKEEPER and int(r[1:]) == GOALKEEPER and p[0] < -(HALF_L - 0.5) and abs(p[1]) < GOAL_W / 2:
            return False
        if np.hypot(*(xy - np.asarray(spot))) < CENTER_R - margin:
            return True
        return kind == "goal_kick" and in_own_area(to_team(team, xy), -margin)

    def _free_kick(self, team, kind, spot):
        """Award a free kick: the referee places the ball, moves the opponents out of the avoidance region, and play
        goes on at once (no stoppage, no review)."""
        self.place_ball(*spot)
        self.last_touch = None
        self.stuck_anchor, self.stuck_k, self.global_k = np.asarray(spot, float), 0, 0
        for r in TEAM_ROBOTS[OTHER[team]]:
            if self.on_bench(r) or not self._fk_violator(r, team, kind, spot, -0.3):
                continue
            xy = self.rob[r].xy(self.d)
            p = self._clear_spot(r, xy, spot, CENTER_R, avoid_area=team if kind == "goal_kick" else None)
            self.place(r, float(p[0]), float(p[1]), self.rob[r].yaw(self.d))
            self.fallen[r] = None
        self.fk = dict(team=team, kind=kind, k0=self.k, spot=np.asarray(spot, float), in_play=False, kicker=None,
                       other=False, indirect=kind == "kick_in")
        self.restarts[team][kind] += 1
        mujoco.mj_forward(self.m, self.d)
        self.event("free_kick", team=team, kind=kind)

    def _free_kick_step(self, bxy):
        fk = self.fk
        if not fk["in_play"]:
            if np.hypot(*(bxy - fk["spot"])) > 0.15 or (self.k - fk["k0"]) * CONTROL_DT >= FREE_KICK_S:
                fk["in_play"] = True
                self.event("ball_free", kind=fk["kind"])
            else:
                for r in TEAM_ROBOTS[OTHER[fk["team"]]]:
                    if not self.on_bench(r) and self._fk_violator(r, fk["team"], fk["kind"], fk["spot"], FK_GRACE_M):
                        self._penalize(r, "illegal position at a free kick", counts=False)
        elif fk["other"] or (fk["kicker"] is None and (self.k - fk["k0"]) * CONTROL_DT >= FREE_KICK_S + 2.0):
            self.fk = None                                       # the free kick is over (indirect rule satisfied)

    @staticmethod
    def _at_board(b):
        return abs(b[1]) > HALF_W - BOARD_ZONE_M or (abs(b[0]) > HALF_L - BOARD_ZONE_M and abs(b[1]) > GOAL_W / 2)

    def _replace_ball(self, b):
        """The ball rests against a board (no robot moved it 0.3 m in 3 s): the referee moves it 1 m straight inwards
        (at a corner diagonally), further in if a robot stands there; play goes on."""
        inward = np.array([-np.sign(b[0]) if abs(b[0]) > HALF_L - BOARD_ZONE_M else 0.0,
                           -np.sign(b[1]) if abs(b[1]) > HALF_W - BOARD_ZONE_M else 0.0])
        inward /= max(np.hypot(*inward), 1e-9)
        robots = [self.rob[r].xy(self.d) for r in ROBOTS if not self.on_bench(r)]
        p = b + BOARD_MOVE_M * inward
        for dist in (1.0, 1.3, 1.6, 2.0, 2.5):
            q = b + dist * inward
            if all(np.hypot(*(q - o)) >= 0.45 for o in robots):
                p = q
                break
        self.place_ball(float(p[0]), float(p[1]))
        self.last_touch = None
        mujoco.mj_forward(self.m, self.d)
        self.event("ball_replaced", why="the ball rested against a board")

    def _kick_exempt(self, o):
        """HSL Law 12: a robot kicking the ball close to it is not pushing."""
        return self.kicking(o) and np.hypot(*(self.ball_xy() - self.rob[o].xy(self.d))) < 1.3

    def _judge_push(self, r):
        """HSL Law 12 pushing: an opponent that pushed the fallen robot over (contact in the last 0.5 s, moving
        towards it faster than it moved towards the opponent) gets a removal penalty."""
        d, k = self.d, self.k
        best = None
        for (a, b), c in self.contact_opp.items():
            if r not in (a, b) or (k - c["k"]) * CONTROL_DT > PUSH_WINDOW_S or c["n"] == 0:
                continue
            o = b if a == r else a
            v_o = (c["vb"] if a == r else c["va"]) / c["n"]
            v_r = (c["va"] if a == r else c["vb"]) / c["n"]
            if v_o > PUSH_MIN_V and v_o - v_r > PUSH_MIN_V and (best is None or v_o - v_r > best[1]):
                best = (o, v_o - v_r)
        if best and self.state != "pso_kick" and self.fallen[best[0]] is None:
            o = best[0]
            if self._kick_exempt(o):
                return                                     # a kicking robot near the ball is not pushing
            self.stats[r]["pushed_over"] += 1
            self._penalize(o, f"pushing ({r} fell)")

    def _goal(self, scorer):
        lt = self.last_touch
        fk = self.fk
        if fk and fk["kicker"] is not None and not fk["other"] and fk["kicker"][0] == fk["team"]:
            s = 1.0 if scorer == "A" else -1.0                 # the goal at x = s * HALF_L
            sy = 1.0 if self.ball_xy()[1] >= 0 else -1.0
            if scorer != fk["team"]:                             # straight into its own goal: corner kick (HSL Law 13)
                self.event("no_goal", team=scorer, why="a free kick went straight into the kicking team's own goal")
                return self._free_kick(scorer, "corner_kick", (s * HALF_L, sy * HALF_W))
            if fk["indirect"]:                                   # a kick-in scores only after another touch
                self.event("no_goal", team=scorer, why="a kick-in went into the goal without another touch")
                return self._free_kick(OTHER[scorer], "goal_kick", (s * (HALF_L - GOAL_AREA[0]), sy * GOAL_AREA[1] / 2))
        if self.ko and scorer == self.ko["team"] and not self.ko["touched_outside"]:
            self.event("no_goal", team=scorer, why="kick-off team scored without touching the ball outside the centre circle")
            self.kickoff_team = OTHER[scorer]
            return self._stop("no_goal", "kickoff", team=scorer)
        self.score[scorer] += 1
        who = None
        if lt is not None:
            who = lt
            if lt[0] == scorer:
                self.stats[lt]["goals"] += 1
            else:
                self.stats[lt]["own_goals"] += 1
        g = dict(team=scorer, robot=who, own_goal=bool(who and who[0] != scorer), k=self.k, period=self.period,
                 clock=round(self.clock(), 2), score=dict(self.score))
        self.goals.append(g)
        self.event("goal", **g)
        if abs(self.score["A"] - self.score["B"]) >= MERCY_DIFF:
            return self._finish("goal", "mercy")
        self.kickoff_team = OTHER[scorer]
        return self._stop("goal", "kickoff", team=scorer, robot=who)

    def _stop(self, kind, restart, **info):
        self.review_hist = list(self.hist)
        st = dict(kind=kind, k=self.k, t=round(self.t(), 3), period=self.period, score=dict(self.score), **info)
        self.stops.append(st)
        self.event("stoppage", **st)
        self.last_touch = None
        if restart == "pso":
            self._pso_setup()
        else:
            self._restart(restart)
        self.stopped = st

    def _finish(self, kind, how, winner=None):
        self.review_hist = list(self.hist)
        if winner is None:
            winner = "A" if self.score["A"] > self.score["B"] else "B"
        self.done, self.winner, self.end_reason = True, winner, how
        st = dict(kind=kind, k=self.k, t=round(self.t(), 3), period=self.period, score=dict(self.score), final=True)
        self.stops.append(st)
        self.event("end", winner=winner, how=how, score=dict(self.score))

    def resume(self):
        self.stopped = None

    # ------------------------------------------------------------------ penalty shoot-out (HSL Law 14)
    def _pso_setup(self):
        if self.pso is None:
            self.pso = dict(kicks=[], first=self.first_kickoff)
        n = len(self.pso["kicks"])
        team = self.pso["first"] if n % 2 == 0 else OTHER[self.pso["first"]]
        j = n // 2
        if N == 2:                                       # strikers 1, 2, 1, ...; keeper the robot with that number
            striker = TEAM_ROBOTS[team][j % 2]
            keeper = TEAM_ROBOTS[OTHER[team]][j % 2]
        else:                                            # strikers the field players 2, 3, 4, 5, 2, ...; the goalkeeper
            field = [r for r in TEAM_ROBOTS[team] if int(r[1:]) != GOALKEEPER]
            striker = field[j % len(field)]
            keeper = TEAM_ROBOTS[OTHER[team]][GOALKEEPER - 1]
        spot = from_team(team, (HALF_L - PEN_MARK, 0.0))
        self.place_ball(*spot)
        for r in ROBOTS:
            self.penalty[r] = None
            self.fallen[r] = None
        dy = self._jitter(30, 0.1)[0]
        p = from_team(team, (HALF_L - PEN_MARK - 1.6, 0.15 + dy))
        self.place(striker, p[0], p[1], 0.0 if team == "A" else np.pi)
        kp = from_team(team, (HALF_L - 0.25, 0.0))
        self.place(keeper, kp[0], kp[1], np.pi if team == "A" else 0.0)
        for r in ROBOTS:
            if r not in (striker, keeper):
                self.penalty[r] = dict(until=10 ** 12, why="not in this penalty kick", pso=True)
                self._to_bench(r)
        self.pso["cur"] = dict(n=n, team=team, striker=striker, keeper=keeper, k0=self.k, spot=np.array(spot),
                               touched=None, saved=False, post=False, second_touch=False, still=0)
        self.state = "pso_kick"
        self.ko = None
        self.fk = None
        mujoco.mj_forward(self.m, self.d)
        self.event("pso_kick_setup", n=n + 1, team=team, striker=striker, keeper=keeper)

    def _pso_step(self, bxy):
        cur, d = self.pso["cur"], self.d
        bp = self.ball_pos()
        team = cur["team"]
        s = 1 if team == "A" else -1
        res = None
        if s * bp[0] > HALF_L + BALL_R and abs(bp[1]) < GOAL_W / 2 and bp[2] < GOAL_H:
            res = "goal"
        elif not cur["touched"]:
            kx = to_team(OTHER[team], self.rob[cur["keeper"]].xy(d))[0]
            if kx > -(HALF_L - 0.6):
                res = "goal"                              # the keeper left its goal line before the kick
                cur["keeper_off_line"] = True
            elif (self.k - cur["k0"]) * CONTROL_DT >= PSO_TIME_S:
                res = "no_kick"
        else:
            if float(np.hypot(*self.ball_v())) < 0.05:
                cur["still"] += 1
            else:
                cur["still"] = 0
            end = cur["second_touch"] or cur["still"] * CONTROL_DT >= 0.5 or \
                (self.k - cur["k0"]) * CONTROL_DT >= PSO_TIME_S + 10.0
            if end:
                if cur["saved"]:
                    res = "saved"
                elif cur["post"]:
                    res = "post"
                elif s * bp[0] > HALF_L - 0.3:
                    res = "wide"
                else:
                    res = "other"
        if res is None:
            return
        kick = dict(n=cur["n"] + 1, team=team, striker=cur["striker"], keeper=cur["keeper"], result=res,
                    category=PSO_CATEGORIES.index(res), k=self.k)
        if res == "goal":
            self.stats[cur["striker"]]["shootout_goals"] += 1
        self.pso["kicks"].append(kick)
        self.event("pso_kick", **kick)
        w = self._pso_winner()
        if w:
            self.review_hist = list(self.hist)
            return self._finish("pso_kick", w[1], winner=w[0])
        self.review_hist = list(self.hist)
        st = dict(kind="pso_kick", k=self.k, t=round(self.t(), 3), period="pso", score=dict(self.score), kick=kick)
        self.stops.append(st)
        self.event("stoppage", **st)
        self._pso_setup()
        self.stopped = st

    def pso_score(self):
        if not self.pso:
            return None
        return {t: sum(1 for x in self.pso["kicks"] if x["team"] == t and x["result"] == "goal") for t in TEAMS}

    def _pso_winner(self):
        kicks = self.pso["kicks"]
        first, second = self.pso["first"], OTHER[self.pso["first"]]
        reg = kicks[:2 * PSO_KICKS]
        g = {t: sum(1 for x in reg if x["team"] == t and x["result"] == "goal") for t in TEAMS}
        taken = {t: sum(1 for x in reg if x["team"] == t) for t in TEAMS}
        if len(kicks) <= 2 * PSO_KICKS:
            for t in TEAMS:
                o = OTHER[t]
                if g[t] > g[o] + (PSO_KICKS - taken[o]):
                    return (t, "pso")
            return None
        sd = kicks[2 * PSO_KICKS:]
        if len(sd) % 2:
            return None
        a, b = sd[-2], sd[-1]
        if a["category"] != b["category"]:
            return (a["team"] if a["category"] < b["category"] else b["team"], "pso_sudden_death")
        if len(sd) // 2 >= PSO_SD_ROUNDS:
            coin = first if np.random.default_rng([self.seed, 777]).random() < 0.5 else second
            return (coin, "pso_coin_toss")
        return None

    # ------------------------------------------------------------------ evidence
    def state_sha(self):
        h = hashlib.sha256()
        for a in (self.d.qpos, self.d.qvel, np.array([self.d.time, self.k, self.score["A"], self.score["B"]])):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        return h.hexdigest()

    def acts_sha(self):
        return hashlib.sha256(json.dumps(self.acts, sort_keys=True, default=jdefault).encode()).hexdigest()

    def summary(self):
        return dict(score=dict(self.score), winner=self.winner, end_reason=self.end_reason, steps=self.k,
                    goals=self.goals, stops=self.stops, pso=None if not self.pso else dict(
                        kicks=self.pso["kicks"], first=self.pso["first"], score=self.pso_score()),
                    stats=self.stats, team_offenses=self.team_offenses, team_size=N, restarts=self.restarts)

    # ------------------------------------------------------------------ what a robot knows about itself
    def self_state(self, name, team_frame=True):
        d, r = self.d, self.rob[name]
        t = name[0]
        xy, v = r.xy(d), r.vel(d)
        yaw = r.yaw(d)
        q = d.sensordata[r.s_quat:r.s_quat + 4]
        w, x, y, z = q
        roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
        pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
        p = self.prog[name]
        if p["type"] == "kick" and p["style"] == "swing":
            kk = p["kicker"]
            rec = p.get("recover_k")
            cmd = dict(type="kick", style="swing", power=p["power"], aim=p["aim"], foot=p.get("foot", "right"),
                       phase="ready" if kk is None else "recover" if rec is not None else kk.phase(),
                       ends_in_s=round(SWING_NOMINAL_S if kk is None else max(0, rec - self.k) * CONTROL_DT
                                       if rec is not None else kk.remaining_s() + SWING["recover_s"], 2))
            if p.get("at") is not None:          # the timed kick: its point (team frame) and time
                xy = to_team(t, np.array(p["at"][1:]))
                left = p["at"][0] - (self.k - p["k_at"]) * CONTROL_DT
                cmd["at"] = [round(max(left, 0.0), 2), round(float(xy[0]), 3), round(float(xy[1]), 3)]
                cmd["late_s"] = None if kk is None else kk.late
        elif p["type"] == "kick" and p.get("style") == "step":   # the in-walk kick (soccer-2v2-8)
            kk = p.get("kicker")
            cmd = dict(type="kick", style="step", power=p["power"], aim=p.get("aim", 0.0), foot=p.get("foot", "right"),
                       v=[round(float(x), 3) for x in (p.get("v") or STEP["v_default"])],
                       phase="recover" if p.get("recover_k") is not None else ("ready" if kk is None else kk.phase()))
        elif p["type"] == "kick":
            i = self.k - p["k0"]
            if i < p["n0"]:
                ph, left = "stand", p["n0"] - i + p["n1"] + p["n2"]
            elif p["k_end"] is None:
                ph, left = "run", max(0, p["n0"] + p["n1"] - i) + p["n2"]
            else:
                ph, left = "after", p["k_end"] + p["n2"] - i
            cmd = dict(type="kick", style="push", power=p["power"], phase=ph, ends_in_s=round(left * CONTROL_DT, 2))
        else:
            cmd = dict(p) if p["type"] == "walk" else dict(type="stand")
        cmd["walk_now"] = [round(float(x), 3) for x in self.cmd_lim[name].cmd]    # after the command rate limit
        pen = self.penalty[name]
        return dict(robot=name, pose=dict(x=round(float(to_team(t, xy)[0]), 3), y=round(float(to_team(t, xy)[1]), 3),
                                          yaw=round(yaw_to_team(t, yaw), 4)),
                    velocity=dict(vx=round(float(to_team(t, v)[0]), 3), vy=round(float(to_team(t, v)[1]), 3)),
                    imu=dict(roll=round(roll, 4), pitch=round(pitch, 4), yaw=round(yaw_to_team(t, yaw), 4)),
                    trunk_height=round(r.height(d), 3), fallen=self.fallen[name] is not None,
                    penalized=None if not pen else dict(why=pen["why"], remaining_s=None if pen.get("pso") else
                                                        round(max(0, pen["until"] - self.k) * CONTROL_DT, 2)),
                    command=cmd, joint_pos=[round(float(x), 4) for x in d.qpos[r.jq]])

    def referee(self, team):
        """What the game controller tells a team (its own frame)."""
        o = OTHER[team]
        out = dict(score=dict(us=self.score[team], them=self.score[o]), period=self.period,
                   clock_s=round(self.clock(), 2), half_s=HALF_S, state=self.state,
                   kickoff=None if not self.ko else dict(ours=self.ko["team"] == team, ball_in_play=self.ko["in_play"]),
                   free_kick=None if not self.fk else dict(ours=self.fk["team"] == team, kind=self.fk["kind"],
                                                           ball_in_play=self.fk["in_play"]),
                   penalties={("us" if r[0] == team else "them") + r[1:]: (None if not self.penalty[r] else dict(
                       why=self.penalty[r]["why"], remaining_s=None if self.penalty[r].get("pso") else
                       round(max(0, self.penalty[r]["until"] - self.k) * CONTROL_DT, 2))) for r in ROBOTS},
                   done=self.done)
        if self.pso:
            cur = self.pso.get("cur") or {}
            out["shootout"] = dict(score=dict(us=self.pso_score()[team], them=self.pso_score()[o]),
                                   kicks=[dict(n=k["n"], by="us" if k["team"] == team else "them",
                                               striker=("us" if k["striker"][0] == team else "them") + k["striker"][1:],
                                               result=k["result"]) for k in self.pso["kicks"]],
                                   current=None if self.done or not cur else dict(
                                       n=cur["n"] + 1, we_shoot=cur["team"] == team,
                                       striker=("us" if cur["striker"][0] == team else "them") + cur["striker"][1:],
                                       keeper=("us" if cur["keeper"][0] == team else "them") + cur["keeper"][1:]))
        return out

    def joint_state(self, name, team_frame=True):
        """The joint level's proprioception of one robot (what the real T1's encoders and IMU give, plus D14's exact
        pose): joint velocities, the trunk's attitude (team frame), gyro and accelerometer (trunk frame), the trunk's
        3-D velocity (team frame), the row in effect, the referee's hold."""
        d, r = self.d, self.rob[name]
        t = name[0]
        q = d.qpos[r.rq + 3:r.rq + 7].copy()
        if t == "B" and team_frame:                     # turn the attitude by 180 degrees about z
            q = _quat_mul(np.array([0.0, 0.0, 0.0, 1.0]), q)
        v = d.qvel[r.rv:r.rv + 3].copy()
        vxy = to_team(t, v[:2]) if team_frame else v[:2]
        plan = self.jplan.get(name)
        return dict(joint_vel=[round(float(x), 4) for x in d.qvel[r.jv]],
                    trunk_quat=[round(float(x), 6) for x in q],
                    gyro=[round(float(x), 5) for x in d.sensordata[r.s_gyro:r.s_gyro + 3]],
                    accelerometer=[round(float(x), 4) for x in d.sensordata[r.s_acc:r.s_acc + 3]],
                    trunk_pos_z=round(float(d.qpos[r.rq + 2]), 4),
                    trunk_vel=[round(float(vxy[0]), 4), round(float(vxy[1]), 4), round(float(v[2]), 4)],
                    row=[round(float(x), 5) for x in self.jrow.get(name, np.zeros(12))],
                    plan_rows_left=0 if plan is None else max(0, len(plan[1]) - (self.k - plan[0])),
                    held_s=round(max(0, (self.held.get(name) or 0) - self.k) * CONTROL_DT, 2), step=self.k,
                    motor_heat=[round(float(x), 3) for x in self.motors.h[12 * r.idx:12 * r.idx + 12]])

    def truth_full(self, team):
        """Pilot only (RCB_SOCCER_FULLSTATE): the ball and every robot in the team's frame."""
        tr = self.truth(team)
        bz = float(self.ball_pos()[2])
        return dict(ball=[round(float(tr["ball"][0]), 4), round(float(tr["ball"][1]), 4), round(bz, 4)],
                    ball_v=[round(float(x), 4) for x in tr["ball_v"]],
                    robots={("us" if n[0] == team else "them") + n[1:]: dict(x=round(float(o["xy"][0]), 4),
                                                                           y=round(float(o["xy"][1]), 4),
                                                                           yaw=round(float(o["yaw"]), 4),
                                                                           fallen=o["fallen"], bench=o["bench"])
                            for n, o in tr["robots"].items()})

    # ------------------------------------------------------------------ privileged state (scripted team, oracle)
    def truth(self, team):
        d = self.d
        out = dict(ball=to_team(team, self.ball_xy()), ball_v=to_team(team, self.ball_v()), k=self.k, robots={})
        for r in ROBOTS:
            rb = self.rob[r]
            out["robots"][r] = dict(xy=to_team(team, rb.xy(d)), yaw=yaw_to_team(team, rb.yaw(d)),
                                    fallen=self.fallen[r] is not None, bench=self.on_bench(r),
                                    kicking=self.kicking(r))
        return out


# ---------------------------------------------------------------------------------------------- scripted coach
COACH_LEVELS = {                            # pos_tol / yaw_tol: how close to the swing kick's spot it kicks
    1: dict(delay_s=0.6, vmax=0.45, vlat=0.25, wmax=0.6, pos_tol=0.10, yaw_tol=0.15, every=5, shoot_m=6.0, feet="both"),
    2: dict(delay_s=0.3, vmax=0.65, vlat=0.35, wmax=0.8, pos_tol=0.07, yaw_tol=0.10, every=3, shoot_m=7.0, feet="both"),
    "ref": dict(delay_s=0.0, vmax=0.8, vlat=0.4, wmax=1.0, pos_tol=0.05, yaw_tol=0.08, every=1, shoot_m=7.5,
                feet="both"),
}
# level 3 (soccer-2v2-6): the strongest scripted team found in the screening: every robot goes for the ball (the
# "chase" plan) at the reference's speed and precision, no delay (docs/screening/soccer.md)
COACH_LEVELS[3] = dict(COACH_LEVELS["ref"], style="chase")
# soccer-2v2-9 (screening on the soccer-2v2-8 physics, 2026-10-12): the 2 v 2 levels kick with the in-walk kick (style
# step), the platform's fastest kick; with the swing kick only, every level lost to the in-walk kick's teams by 6-9 goals
# a match. "reference": the strongest play found, every robot goes for the ball at the reference's speed with the
# in-walk kick (the tools/check stage-5 truth reference); a coordinated plan (one strikes, one covers or presses behind)
# lost to it head to head 4-7 / 40 (docs/screening/soccer.md)
if N == 2:
    for _k in (1, 2, 3):
        COACH_LEVELS[_k] = dict(COACH_LEVELS[_k], step=True)
COACH_LEVELS["reference"] = dict(COACH_LEVELS["ref"], style="chase", step=True)
# level 4 (L-RL, not official; RCB_LEVEL=4): the RL-trained opponent of rl_opponent.py (a fixed-weight policy that
# chooses skills per robot); levels 1-3 unchanged
# level 5 (not official; RCB_LEVEL=5): the joint-level RL opponent of rl_joint.py (our own walking policy trained with
# PPO on the joint level's GPU world, under a team plan): its team is under joint control like the agent's
RL_LEVELS = {4: ("skills", "v2"), 5: ("joint", "v2")} if N == 2 else {}
for _k, (_kind, _ver) in RL_LEVELS.items():
    COACH_LEVELS[_k] = dict(COACH_LEVELS["reference"], rl=_ver, rl_kind=_kind)


def make_coach(team, level):
    """The scripted team of a level: soccer.Coach, or an RL opponent (rl_opponent.RLCoach, rl_joint.JointTeam)."""
    if level in RL_LEVELS:
        kind, ver = RL_LEVELS[level]
        if kind == "joint":
            import rl_joint
            return rl_joint.JointTeam(team, version=ver)
        import rl_opponent
        return rl_opponent.RLCoach(team, version=ver)
    return Coach(team, level)
COACH_STYLES = ("positional", "chase", "defensive")   # 5 v 5 team plans (the single-player opponent: positional)
STAND_X = HALF_L - 0.3 if BOARDS else PLAY_X - 0.4  # where the scripted players may walk (5 v 5: the border strip too)
STAND_Y = HALF_W - 0.3 if BOARDS else PLAY_Y - 0.4


def shoot_m(lv):
    """the scripted players shoot from at most this far: the level's range, within the reach of its kick (soccer-2v2-8)"""
    return min(lv["shoot_m"], shot_range("step" if lv.get("step") else "swing"))


def plan_robot(lv, me, mine, ball, ball_v, robots, role, ref, team):
    """The scripted player's command for robot `me` (team frame values). role: striker | support | keeper | wing_L |
    wing_R | anchor_<i> | pso_striker | pso_keeper | idle. Returns a command dict or None (keep the current one)."""
    st = robots[me]
    if st["bench"] or st["fallen"]:
        return None
    if st["kicking"]:
        return None
    p, yaw = np.asarray(st["xy"], float), float(st["yaw"])
    goal = np.array([HALF_L, 0.0])
    own = np.array([-HALF_L, 0.0])
    others = [np.asarray(robots[o]["xy"], float) for o in robots if o != me and not robots[o]["bench"]]
    avoid = ref.get("avoid")                             # the opponents' free kick: (ball, radius, goal kick?)

    def go(tgt, face=None, press=False, vmax=None):
        vmax = vmax or lv["vmax"]
        tgt = np.array([np.clip(tgt[0], -STAND_X, STAND_X), np.clip(tgt[1], -STAND_Y, STAND_Y)])
        if avoid is not None:                            # stay out of the avoidance region (HSL Law 13)
            c, rad, gk = avoid
            u = tgt - c
            dd = float(np.hypot(*u))
            if dd < rad + 0.35:
                u = u / dd if dd > 1e-6 else (own - c) / max(np.hypot(*(own - c)), 1e-6)
                tgt = c + (rad + 0.5) * u
            if gk and tgt[0] > PEN_AREA_X - 0.5 and abs(tgt[1]) < PEN_AREA_Y + 0.5:
                tgt[0] = PEN_AREA_X - 0.6
        e = tgt - p
        dist = float(np.hypot(*e))
        if face is None:
            face = math.atan2(e[1], e[0]) if dist > 0.25 else yaw
        elif dist > 0.8:
            face = math.atan2(e[1], e[0])
        v = 1.6 * e
        if not press:
            for o in others:
                rel = p - o
                dd = float(np.hypot(*rel))
                if 1e-6 < dd < 0.75:
                    v += 0.8 * (0.75 - dd) / 0.75 * rel / dd * 1.5
        if avoid is not None:                            # walk round the avoidance region, not through it
            rel = p - avoid[0]
            dd = float(np.hypot(*rel))
            if 1e-6 < dd < avoid[1] + 0.6:
                v += 2.5 * (avoid[1] + 0.6 - dd) * rel / dd
            if avoid[2] and p[0] > PEN_AREA_X - 0.5 and abs(p[1]) < PEN_AREA_Y + 0.5:
                v[0] -= 1.5                              # a goal kick: out of their penalty area
        sp = float(np.hypot(*v))
        if sp > vmax:
            v *= vmax / sp
        c, s = math.cos(yaw), math.sin(yaw)
        vx, vy = c * v[0] + s * v[1], -s * v[0] + c * v[1]
        err = float(_wrap(face - yaw))
        if abs(err) > 0.9:
            vx *= 0.3; vy *= 0.3
        vx = float(np.clip(vx, -0.5 * vmax, vmax))
        vy = float(np.clip(vy, -lv["vlat"], lv["vlat"]))
        wz = float(np.clip(1.8 * err, -lv["wmax"], lv["wmax"]))
        if abs(vx) < 0.04 and abs(vy) < 0.04 and abs(wz) < 0.06:
            return dict(type="stand")
        return dict(type="walk", v=[round(vx, 3), round(vy, 3), round(wz, 3)])

    face_ball = math.atan2(ball[1] - p[1], ball[0] - p[0])
    if role == "idle":
        return dict(type="stand")
    if role == "pso_keeper":
        y = float(np.clip(ball[1] + 0.6 * ball_v[1] if np.hypot(*ball_v) > 0.2 else 0.0, -GOAL_W / 2 + 0.3, GOAL_W / 2 - 0.3))
        return go(np.array([-HALF_L + 0.25, y]), face=0.0)
    if role == "keeper":                                 # 5 v 5 goalkeeper: on its line, between the ball and the goal
        y = float(np.clip(0.45 * ball[1], -GOAL_W / 2 + 0.3, GOAL_W / 2 - 0.3))
        return go(np.array([-HALF_L + 0.45, y]), face=face_ball)
    if role in ("wing_L", "wing_R"):
        side = 1.0 if role == "wing_L" else -1.0
        tgt = np.array([np.clip(ball[0] - 0.8, -HALF_L + 2.5, HALF_L - 1.5), side * 0.55 * HALF_W])
        return go(tgt, face=face_ball)
    if role.startswith("anchor_"):                       # defensive line at the penalty area's edge
        j = int(role[7:]) - 1
        tgt = np.array([-PEN_AREA_X + 0.5, float(np.clip(0.5 * ball[1] + 1.3 * j, -PEN_AREA_Y, PEN_AREA_Y))])
        return go(tgt, face=face_ball)
    if role == "receive":                                # a pass is on its way to this robot: the planned spot
        return go(np.asarray(ref["spot"], float), face=float(ref["face"]), vmax=ref.get("vmax"))
    if role == "support":
        b = ball
        tgt = own + 0.42 * (b - own)
        tgt[0] = min(tgt[0], -0.6) if ref.get("defend_half", True) else tgt[0]
        mate = [np.asarray(robots[o]["xy"], float) for o in mine if o != me and not robots[o]["bench"]]
        if N == 2 and mate and in_own_area(mate[0], 0.3) and in_own_area(tgt, 0.3):
            tgt[0] = -(PEN_AREA_X - 0.45)                # the teammate defends inside the area: wait at its edge
        return go(tgt, face=face_ball)
    aim = goal.copy() if ref.get("aim_point") is None else np.asarray(ref["aim_point"], float)
    if role == "pso_striker":
        side = PSO_AIM_Y if N == 2 else GOAL_W / 2 - 0.3  # 5 v 5: closer to the post (the keeper has more time)
        aim = np.array([HALF_L, side if ref.get("aim_left", True) else -side])
    elif role == "striker" and float(np.hypot(*(goal - ball))) < shoot_m(lv) and ref.get("aim_point") is None:
        # a shot: at the corner farther from the opponents between the ball and the goal (they block the middle)
        opps = [np.asarray(robots[o]["xy"], float) for o in robots if o[0] != me[0] and not robots[o]["bench"]]
        best, gap = goal.copy(), -1.0
        for y in (SHOT_AIM_Y, -SHOT_AIM_Y):
            c = np.array([HALF_L, y])
            v = c - ball
            n = float(np.hypot(*v))
            d = min([abs(float(np.cross(v / n, o - ball))) for o in opps if 0 < float(np.dot(o - ball, v)) < n * n]
                    or [9.0])
            if d > gap:
                best, gap = c, d
        aim = best
    u = aim - ball
    u /= max(np.hypot(*u), 1e-6)
    kick_aim = 0.0
    if lv.get("wide") and role == "striker" and ref.get("aim_point") is not None and float(np.hypot(*(ball - p))) > 0.2:
        # passes with the wider aim (soccer-2v2-7): of the feet and aims (0.1 rad steps), the kick spot nearest to reach (walk
        # plus turn, small aims preferred): a fixed choice while the robot walks in
        d = math.atan2(u[1], u[0])
        best = None
        for ft in ("right", "left"):
            lo, hi = (-SWING["aim_max"], SWING["aim_in_max"]) if ft == "right" else (-SWING["aim_in_max"], SWING["aim_max"])
            for a in np.arange(round(lo, 1), hi + 1e-9, 0.1):
                a = float(round(a, 1))
                f = d - a
                fu = np.array([math.cos(f), math.sin(f)])
                zx, zy = swing_zone(a, ft)
                Pc = ball - zx * fu - zy * np.array([-fu[1], fu[0]])
                cost = float(np.hypot(*(Pc - p))) + 0.25 * abs(_wrap(f - yaw)) + 0.6 * abs(a)
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, ft, a)
        _, foot, kick_aim = best
        f = d - kick_aim
        u = np.array([math.cos(f), math.sin(f)])
        zx, zy = swing_zone(kick_aim, foot)
        left = np.array([-u[1], u[0]])
        a_x, r_y = zx, -zy
        rel = p - ball
        behind = float(np.dot(rel, u))
        lat = float(np.dot(rel, left))
    else:
        left = np.array([-u[1], u[0]])
        a_x, r_y = np.mean(SWING_ZONE["ahead"]), np.mean(SWING_ZONE["right"])
        rel = p - ball
        behind = float(np.dot(rel, u))
        lat = float(np.dot(rel, left))
        foot = "right"
        if lv.get("feet") == "both" and lat < -0.03:    # the robot on the ball's right: the left foot
            foot, r_y = "left", -r_y
    P = ball - a_x * u + r_y * left                     # the swing kick's spot: the ball ahead and to the kicking foot's side
    face = math.atan2(u[1], u[0])
    if avoid is not None and role == "striker":          # the opponents' free kick: wait outside the region
        return go(ball + (avoid[1] + 0.5) * (own - ball) / max(np.hypot(*(own - ball)), 1e-6), face=face_ball)
    # an opponent at the ball: press it (only in open play)
    opp_d = min([float(np.hypot(*(np.asarray(robots[o]["xy"]) - ball))) for o in robots
                 if o[0] != me[0] and not robots[o]["bench"]] or [9.0])
    if role == "striker":
        my_d = float(np.hypot(*rel))
        if opp_d < 0.7 and my_d < 1.4 and behind < -0.2:
            return go(ball - 0.2 * u, face=face, press=True)
    if lv.get("step") and role in ("striker", "pso_striker") and kick_aim == 0.0:
        # the in-walk kick (soccer-2v2-8): line up on the kicking foot's line about 0.7 m behind the ball, then kick
        # walking in (the kick waits for the step that reaches the ball)
        foot_s, ry = ("right", STEP["line_m"]) if lat >= 0 or lv.get("feet") != "both" else ("left", -STEP["line_m"])
        Ps = ball - STEP["stage_m"] * u + ry * left
        err_y = float(_wrap(face - yaw))
        if -STEP["stage_m"] - 0.25 < behind < -0.35 and abs(lat - ry) < STEP["lat_tol"] and abs(err_y) < STEP["yaw_tol"]:
            if ref.get("no_kick"):
                return dict(type="stand")
            dist_goal = float(np.hypot(*(goal - ball)))
            power = 1.0 if dist_goal < shoot_m(lv) or role == "pso_striker" else 0.6
            if ref.get("kickoff_touch"):
                power = 0.0
            if ref.get("pass_power") is not None:
                power = float(ref["pass_power"])
            c, s_ = math.cos(yaw), math.sin(yaw)
            e_lat = ry - lat                             # move along `left` by e_lat: robot frame lateral velocity
            vy = float(np.clip(1.5 * e_lat * float(-s_ * left[0] + c * left[1]), -lv["vlat"], lv["vlat"]))
            cmd = dict(type="kick", style="step", power=power,
                       v=[round(min(lv["vmax"], STEP["approach_v"]), 3), round(vy, 3),
                          round(float(np.clip(1.8 * err_y, -lv["wmax"], lv["wmax"])), 3)])
            if foot_s != "right":
                cmd["foot"] = foot_s
            return cmd
        if behind > -0.2:                                # not behind the ball: go round it
            side = 1.0 if lat >= 0 else -1.0
            tgt = ball - 0.75 * u + side * 0.75 * left
            return go(tgt, face=face if np.hypot(*(p - tgt)) < 0.8 else None)
        return go(Ps, face=face, vmax=min(lv["vmax"], 0.3) if np.hypot(*(Ps - p)) < 0.3 else None)
    if behind > -0.2:                                    # not behind the ball: go round it
        side = 1.0 if lat >= 0 else -1.0
        tgt = ball - 0.75 * u + side * 0.75 * left
        return go(tgt, face=face if np.hypot(*(p - tgt)) < 0.8 else None)
    if role == "striker" and opp_d < CONTEST_M and behind < -0.6 and not ref.get("kickoff_touch") and \
            ref.get("aim_point") is None:
        # an opponent near the ball and room behind it: the quick push (no 2.5 s on one leg beside an opponent)
        Pp = ball - np.mean(STRIKE_ZONE["ahead"]) * u + np.mean(STRIKE_ZONE["right"]) * left
        ep = Pp - p
        if np.hypot(*ep) < 1.5 * lv["pos_tol"] and abs(_wrap(face - yaw)) < lv["yaw_tol"]:
            return dict(type="kick", power=1.0, style="push")
        if np.hypot(*ep) < 0.5:
            return go(Pp, face=face, vmax=min(lv["vmax"], 0.25))
    e = P - p
    if np.hypot(*e) < lv["pos_tol"] and abs(_wrap(face - yaw)) < lv["yaw_tol"]:
        dist_goal = float(np.hypot(*(goal - ball)))
        power = 1.0 if dist_goal < shoot_m(lv) or role == "pso_striker" else 0.6
        if ref.get("kickoff_touch"):
            power = 0.0                                  # kick-off: a short first touch (a goal needs a touch outside the circle)
        if ref.get("pass_power") is not None:
            power = float(ref["pass_power"])
        if ref.get("no_kick"):
            return dict(type="stand")                    # a set play: the receiver is not in place yet
        cmd = dict(type="kick", power=power)
        if foot != "right":
            cmd["foot"] = foot
        if kick_aim:
            cmd["aim"] = round(kick_aim, 4)
        if ref.get("pass_t") is not None:                # a pass: the timed kick of the still ball (a known strike time)
            cmd["at"] = [float(ref["pass_t"]), float(ball[0]), float(ball[1])]
        return cmd
    if abs(lat - r_y) > 0.10 or behind > -(a_x - 0.05):  # off the line or too close: to the staging spot behind it
        return go(ball - (a_x + STAGE_M) * u + r_y * left, face=face)
    return go(P, face=face, vmax=min(lv["vmax"], 0.15) if np.hypot(*e) < 0.4 else None)   # then straight in, slowly


# ------------------------------------------------------------------ passing (the reference's team play, soccer-2v2-7)
PASS = dict(min_m=1.6, max_m=6.5,      # pass length
            arrive_v=1.0,                  # the pass arrives at about this speed (m/s): its power from KICK_V
            lane_m=0.45, opp_react_s=0.4, opp_v=0.65,   # lane clear: no opponent can reach the ball's path first
            open_m=1.1, gain_m=0.5,        # block pass: receiver open, at least this much nearer the goal
            aim_now=0.3,                   # open play: the pass direction within this of the striker's facing
            onetouch_m=4.5, onetouch_cone=1.6, onetouch_open_m=1.0, better_rad=0.12,   # one-touch shot pass
            third_m=4.0,                   # near their goal: a teammate takes a one-touch spot
            arm_s=2.9, strike_s=2.6,       # the receiver arms when the ball arrives >= arm_s later; passer's strike
            setplay_x=1.0,                 # set plays from x > -setplay_x
            onetouch_free_m=1.0, cut_t=3.0,  # cut-back: no opponent this near the ball; the passer's timed kick
            struck_v=0.4, max_s=7.0, plan_s=10.0,
            through_lead=(0.6, 1.0, 1.4), through_gain_m=1.0, through_arrive_v=0.3,   # pass into space ("through")
            through_setup_s=1.0, through_spare_s=0.0)
# power -> the ball's rolling speed once its skid is over (m/s; what roll_time() needs): the swing kick at a still ball
# (soccer-2v2-8 physics; before: the ball's speed off the foot, 0.7-3.5) and the in-walk kick (median of the drill)
KICK_V = ((0.0, 0.8), (0.25, 1.0), (0.5, 1.8), (0.75, 2.45), (1.0, 2.8))
KICK_V_STEP = ((0.0, 1.63), (0.25, 1.78), (0.5, 2.14), (0.75, 2.46), (1.0, 2.61))


def shot_range(style="swing", arrive_v=0.8):
    """how far (m) a full-power kick of this style rolls before it slows to arrive_v"""
    v = (KICK_V_STEP if style == "step" else KICK_V)[-1][1]
    return (v * v - arrive_v * arrive_v) / (2 * ROLL_DECEL)


def power_for_speed(v, style="swing"):
    """the kick's power for a ball speed (the drills' tables, linear between their points)"""
    tab = KICK_V_STEP if style == "step" else KICK_V
    xs = [p for p, _ in tab]
    vs = [x for _, x in tab]
    return float(np.interp(v, vs, xs))


def roll_time(dist, v0):
    """seconds for a ball rolling at v0 to cover dist (None if it stops first)"""
    disc = v0 * v0 - 2 * ROLL_DECEL * dist
    if disc < 0:
        return None
    return (v0 - math.sqrt(disc)) / ROLL_DECEL


def goal_angle(p):
    """the angle (rad) the goal mouth subtends from p (team frame): how open a shot from there is"""
    a1 = math.atan2(GOAL_W / 2 - p[1], HALF_L - p[0])
    a2 = math.atan2(-GOAL_W / 2 - p[1], HALF_L - p[0])
    return abs(_wrap(a1 - a2))


def one_touch_deflection(v_left):
    """the timed swing's direction error from the ball's velocity across the kick (m/s, + = moving to the kicker's
    left); the step-2 strike drill (right foot, power 1): about 0.3 rad per m/s from the right, 0.6 from the left"""
    return 0.3 * v_left if v_left > 0 else 0.6 * v_left


class Coach:
    """The scripted team (single-player opponent; the feasibility study's team plans): reacts to the true ball and
    robot positions of `delay_s` ago (its own robots: now); a new decision every `every` control steps. 5 v 5 plans
    (`style`): positional (goalkeeper, striker, a defender, two wings), chase (every field player goes for the ball),
    defensive (goalkeeper, striker, three on the edge of the own penalty area)."""

    def __init__(self, team, level, style="positional"):
        self.team, self.lv = team, COACH_LEVELS[level]
        self.style = self.lv.get("style", style)          # a level may fix its team plan (level 3: chase)
        self.hist = deque(maxlen=max(1, int(round(self.lv["delay_s"] / CONTROL_DT))) + 1)
        self.reset()

    def reset(self):
        self.hist.clear()
        self.striker = None
        self.last = {}
        self.plan = None                                 # a pass under way (lv "pass"): passer, receiver, spot, mode
        self._ot_keep = None                             # the one-touch spot kept while valid (receiver, X)
        self.log = getattr(self, "log", [])              # the passes' outcomes (screening diagnostics)

    def roles(self, w, tr):
        team = self.team
        mine = TEAM_ROBOTS[team]
        if w.state == "pso_kick" and w.pso:
            cur = w.pso["cur"]
            return {r: ("pso_striker" if r == cur["striker"] else "pso_keeper" if r == cur["keeper"] else "idle")
                    for r in mine}
        avail = [r for r in mine if not tr["robots"][r]["bench"] and not tr["robots"][r]["fallen"]]
        if not avail:
            return {r: "idle" for r in mine}
        ball = tr["ball"]
        dist = {r: float(np.hypot(*(tr["robots"][r]["xy"] - ball))) for r in avail}
        out = {r: "idle" for r in mine}
        gk = TEAM_ROBOTS[team][GOALKEEPER - 1] if GOALKEEPER else None
        field = [r for r in avail if r != gk]
        their_ko = bool(w.ko and not w.ko["in_play"] and w.ko["team"] != team)
        if gk in avail:
            out[gk] = "keeper"
            # the goalkeeper clears a ball in its penalty area when it is the nearest
            if in_own_area(ball) and all(dist[gk] <= dist[r] for r in field) and not their_ko:
                out[gk] = "striker"
        if not field:
            return out
        s = self.striker if self.striker in field else None
        best = min(field, key=lambda r: (dist[r], r))
        if s is None or dist[best] + 0.4 < dist[s]:
            s = best
        if their_ko:
            s = None                                     # their kick-off: wait outside the circle
        self.striker = s
        rest = [r for r in field if r != s]
        if self.style == "positional" or (N == 2 and self.style not in ("chase",)):
            if N == 2:
                for r in rest:
                    out[r] = "support"
            elif rest:
                own = np.array([-HALF_L, 0.0])
                dtgt = own + 0.42 * (ball - own)
                dfd = min(rest, key=lambda r: (float(np.hypot(*(tr["robots"][r]["xy"] - dtgt))), r))
                out[dfd] = "support"
                wings = sorted([r for r in rest if r != dfd], key=lambda r: (-float(tr["robots"][r]["xy"][1]), r))
                for r, role in zip(wings, ("wing_L", "wing_R")):
                    out[r] = role
                for r in wings[2:]:
                    out[r] = "support"
        elif self.style == "chase":
            for r in rest:
                out[r] = "striker" if not their_ko else "support"
        else:                                            # defensive
            line = sorted(rest, key=lambda r: (float(tr["robots"][r]["xy"][1]), r))
            for j, r in enumerate(line):
                out[r] = f"anchor_{j}"
        if s is not None:
            out[s] = "striker"
        return out

    def decide(self, w, robots=None):
        tr = w.truth(self.team)
        self.hist.append(tr)
        if w.k % self.lv["every"]:
            return {}
        old = self.hist[0]
        roles = self.roles(w, tr)
        rob = {r: (tr["robots"][r] if r[0] == self.team else old["robots"][r]) for r in ROBOTS}
        avoid = None
        if w.fk and not w.fk["in_play"] and w.fk["team"] != self.team:
            avoid = (to_team(self.team, w.fk["spot"]), CENTER_R, w.fk["kind"] == "goal_kick")
        # shoot-out aim: the same side for both teams in a round (by round and seed), so neither team gets the weaker side
        ref = dict(defend_half=True, aim_left=(w.pso["cur"]["n"] // 2 + w.seed) % 2 == 0 if w.pso else True,
                   kickoff_touch=bool(w.ko and w.ko["team"] == self.team and not w.ko["touched_outside"]
                                      and float(np.hypot(*tr["ball"])) < CENTER_R), avoid=avoid)
        out = {}
        per = {}
        if self.lv.get("pass"):
            per = self._passing(w, tr, old, roles, rob, ref)
        for r in (robots or TEAM_ROBOTS[self.team]):
            role = roles[r]
            if w.ko and not w.ko["in_play"]:
                if w.ko["team"] != self.team or role != "striker":
                    role = "idle"
            if r in per:                                 # the pass: the passer's aim / the receiver's spot or kick
                role, rref = per[r]
                if role == "keep":
                    continue
                if role == "cmd":
                    if rref != w.prog[r] and not (rref.get("type") == "kick" and w.kicking(r) and
                                                  rref.get("at") is None):
                        out[r] = rref
                    continue
                cmd = plan_robot(self.lv, r, TEAM_ROBOTS[self.team], old["ball"], old["ball_v"], rob, role,
                                 {**ref, **rref}, self.team)
                if cmd is not None and (cmd["type"] == "kick" or cmd != w.prog[r]):
                    out[r] = cmd
                continue
            cmd = plan_robot(self.lv, r, TEAM_ROBOTS[self.team], old["ball"], old["ball_v"], rob, role, ref, self.team)
            if self.lv.get("pass") and not self.lv.get("pass_never") and role == "striker" and cmd is not None and \
                    cmd["type"] == "kick" and \
                    self.plan is None and w.state == "play" and not (w.ko and not w.ko["in_play"]):
                cmd = self._kick_or_pass(w, tr, r, cmd)
            if cmd is not None and (cmd["type"] == "kick" or cmd != w.prog[r]):
                out[r] = cmd
        return out


    # ------------------------------------------------------------------ passing (lv "pass": "block" | "onetouch")
    def _opps(self, tr):
        return [np.asarray(tr["robots"][o]["xy"], float) for o in ROBOTS if o[0] != self.team and
                not tr["robots"][o]["bench"] and not tr["robots"][o]["fallen"]]

    def _mates(self, tr, s):
        return [r for r in TEAM_ROBOTS[self.team] if r != s and not tr["robots"][r]["bench"] and
                not tr["robots"][r]["fallen"] and (GOALKEEPER is None or r != TEAM_ROBOTS[self.team][GOALKEEPER - 1])]

    @staticmethod
    def _lane_clear(a, b, v0, opps, lane_m=None, keeper_x=None):
        """no opponent can reach the straight path a -> b before a ball rolling at v0 gets there"""
        L = float(np.hypot(*(b - a)))
        u = (b - a) / max(L, 1e-6)
        for o in opps:
            if keeper_x is not None and o[0] > keeper_x:
                continue
            sp = float(np.dot(o - a, u))
            if sp < 0.2 or sp > L + 0.3:
                continue
            dperp = abs(float(np.cross(u, o - a)))
            tb = (roll_time(min(sp, L), v0) if v0 else None) or 9.0
            if dperp < (lane_m or PASS["lane_m"]) + PASS["opp_v"] * max(0.0, tb - PASS["opp_react_s"]):
                return False
        return True

    def _get_open(self, tr, roles, s, ball):
        """In possession (our striker within 0.8 m of the ball, every opponent at least 0.6 m farther from it): the
        off-ball field players (2 v 2 support, 5 v 5 wings) move to open spots ahead of the ball (the most advanced
        of a few candidates with no opponent within 1.2 m and a clear line from the ball); otherwise no change."""
        me = np.asarray(tr["robots"][s]["xy"], float)
        d_me = float(np.hypot(*(me - ball)))
        opps = self._opps(tr)
        d_op = min([float(np.hypot(*(o - ball))) for o in opps] or [9.0])
        out = {}
        taken = []
        self._ot_spot = None
        if self.lv.get("pass") == "onetouch" and ball[0] > HALF_L - PASS["third_m"] and d_me < d_op:
            # near their goal: one teammate stands where a pass from the ball runs into its strike zone for a shot
            # (the cut-back: the ball from the side or the front, the robot facing the far corner)
            spot = self._onetouch_spot(tr, s, ball, opps)
            self._ot_spot = spot
            if spot is not None:
                r, S_, face = spot
                out[r] = ("receive", dict(spot=S_, face=face, vmax=0.15 if float(np.hypot(*(
                    S_ - np.asarray(tr["robots"][r]["xy"], float)))) < 0.4 else None))
                taken.append(S_)
        if d_me > 1.0 or d_op < d_me + 0.2:
            return out
        for r, ro in sorted(roles.items()):
            if r in out:
                continue
            if ro not in ("support", "wing_L", "wing_R") or tr["robots"][r]["bench"] or tr["robots"][r]["fallen"]:
                continue
            p = np.asarray(tr["robots"][r]["xy"], float)
            ys = (0.55 * HALF_W,) if ro == "wing_L" else (-0.55 * HALF_W,) if ro == "wing_R" else \
                (0.45 * HALF_W, -0.45 * HALF_W, 0.15 * HALF_W, -0.15 * HALF_W)
            best, bv = None, -1e9
            for dx in (1.2, 2.0, 2.8):
                for y in ys:
                    q = np.array([min(ball[0] + dx, HALF_L - 0.8), y])
                    if min([float(np.hypot(*(o - q))) for o in opps] or [9.0]) < 1.2:
                        continue
                    if any(float(np.hypot(*(t - q))) < 1.5 for t in taken):
                        continue
                    L = float(np.hypot(*(q - ball)))
                    u = (q - ball) / max(L, 1e-6)
                    lane = min([abs(float(np.cross(u, o - ball))) for o in opps
                                if 0.2 < float(np.dot(o - ball, u)) < L] or [9.0])
                    if lane < 0.6:
                        continue
                    val = q[0] - 0.3 * float(np.hypot(*(q - p))) - 0.2 * abs(q[1])
                    if val > bv:
                        best, bv = q, val
            if best is not None:
                taken.append(best)
                out[r] = ("receive", dict(spot=best, face=math.atan2(ball[1] - best[1], ball[0] - best[0])))
        return out

    def _kick_or_pass(self, w, tr, s, cmd):
        """At the moment the striker kicks (lined up, the ball in its strike zone): shoot, or pass to a teammate when
        that is better, with an aim the striker can reach from where it stands (no new line-up: |aim| <= 0.3 rad, the
        kick's own 8 cm correction covers the zone's shift). One-touch: a teammate standing so that the pass runs into
        its right foot's strike zone, facing the goal, with a wider view of the goal than the striker's; block: a
        teammate at least gain_m nearer the goal, open, when the striker is far from the goal. Returns the command."""
        if cmd.get("style", "swing") not in ("swing", "step") or cmd.get("at") is not None:
            return cmd
        ball = np.asarray(tr["ball"], float)
        me = tr["robots"][s]
        yaw = float(me["yaw"])
        foot = cmd.get("foot", "right")
        lo, hi = (-PASS["aim_now"], min(PASS["aim_now"], SWING["aim_in_max"])) if foot == "right" else \
            (-min(PASS["aim_now"], SWING["aim_in_max"]), PASS["aim_now"])
        opps = self._opps(tr)
        goal = np.array([HALF_L, 0.0])
        zx, zy = np.mean(SWING_ZONE["ahead"]), -np.mean(SWING_ZONE["right"])
        mine_ang = goal_angle(ball)
        far = float(np.hypot(*(goal - ball))) > self.lv["shoot_m"] * 0.6
        best, bval = None, -1e9
        for r in self._mates(tr, s):
            st = tr["robots"][r]
            q, yr = np.asarray(st["xy"], float), float(st["yaw"])
            fr = np.array([math.cos(yr), math.sin(yr)])
            for mode in (("onetouch", "block") if self.lv["pass"] == "onetouch" else ("block",)):
                if mode == "onetouch":
                    X = q + zx * fr + zy * np.array([-fr[1], fr[0]])     # its right foot's strike zone
                    yg = X[1] + (HALF_L - X[0]) * math.tan(yr) if abs(_wrap(yr)) < 1.3 else 9.0
                    if abs(yg) > GOAL_W / 2 - 0.15 or float(np.hypot(*(goal - X))) > PASS["onetouch_m"]:
                        continue                         # its shot would miss the goal or be too long
                    frm = math.atan2(ball[1] - X[1], ball[0] - X[0])
                    if abs(_wrap(frm - yr)) > PASS["onetouch_cone"]:
                        continue                         # the pass would come from behind it
                    if goal_angle(X) < mine_ang + PASS["better_rad"]:
                        continue
                else:
                    if not far:
                        continue
                    X = q.copy()
                    if float(np.hypot(*(goal - ball)) - np.hypot(*(goal - X))) < PASS["gain_m"]:
                        continue
                    if min([float(np.hypot(*(o - X))) for o in opps] or [9.0]) < PASS["open_m"]:
                        continue
                L = float(np.hypot(*(X - ball)))
                if not PASS["min_m"] <= L <= PASS["max_m"]:
                    continue
                d = X - ball
                aim = _wrap(math.atan2(d[1], d[0]) - yaw)
                if not lo <= aim <= hi:
                    continue
                v0 = math.sqrt(PASS["arrive_v"] ** 2 + 2 * ROLL_DECEL * L)
                if not self._lane_clear(ball, X, v0, opps):
                    continue
                val = (10.0 if mode == "onetouch" else 0.0) + goal_angle(X)
                if val > bval:
                    best, bval = dict(recv=r, X=X, L=L, v0=v0, mode=mode, aim=aim, S=q.copy(), face=yr), val
        if best is None:
            return cmd
        step = cmd.get("style") == "step"
        out = dict(cmd, aim=round(float(best["aim"]), 4), power=round(power_for_speed(best["v0"], cmd.get("style", "swing")), 4))
        self.plan = dict(passer=s, k0=w.k, struck_k=None, kicked=True, k_kick=w.k, armed=False,
                         t_p=STEP["strike_s"] if step else PASS["strike_s"], **{k: v for k, v in best.items() if k != "aim"})
        return out

    def _through(self, w, tr, s, ball, bv):
        """A pass into space (lv pass "through", soccer-2v2-8): the striker at a still ball outside its shooting range;
        a teammate nearer their goal; the spot X a little ahead of it toward the goal where the ball arrives slowly
        (PASS through_arrive_v); the teammate waits behind X on its kicking foot's line, facing the goal, and kicks
        when the ball is there. Only if every opponent needs clearly longer to reach X than the ball (the passer's
        line-up and kick included) and the path is clear."""
        if float(np.hypot(*bv)) > 0.3 or w.kicking(s):
            return None
        me = np.asarray(tr["robots"][s]["xy"], float)
        if float(np.hypot(*(me - ball))) > 1.2:
            return None
        goal = np.array([HALF_L, 0.0])
        if float(np.hypot(*(goal - ball))) < 0.6 * shoot_m(self.lv):
            return None                                  # near enough: shoot
        opps = self._opps(tr)
        step = bool(self.lv.get("step"))
        t_kick = PASS["through_setup_s"] + (STEP["strike_s"] if step else PASS["strike_s"])
        best, bval = None, -1e9
        for r in self._mates(tr, s):
            q = np.asarray(tr["robots"][r]["xy"], float)
            if GOALKEEPER is not None and int(r[1:]) == GOALKEEPER:
                continue
            ug = (goal - q) / max(float(np.hypot(*(goal - q))), 1e-6)
            for lead in PASS["through_lead"]:
                X = q + lead * ug
                if abs(X[0]) > HALF_L - 0.6 or abs(X[1]) > HALF_W - 0.5:
                    continue
                if float(np.hypot(*(goal - X))) > float(np.hypot(*(goal - ball))) - PASS["through_gain_m"]:
                    continue
                L = float(np.hypot(*(X - ball)))
                if not PASS["min_m"] <= L <= PASS["max_m"]:
                    continue
                v0 = math.sqrt(PASS["through_arrive_v"] ** 2 + 2 * ROLL_DECEL * L)
                if v0 > (KICK_V_STEP if step else KICK_V)[-1][1]:
                    continue
                t_ball = t_kick + (roll_time(L, v0) or 9.0)
                u2 = (goal - X) / max(float(np.hypot(*(goal - X))), 1e-6)
                S_ = X - STEP["stage_m"] * u2 + STEP["line_m"] * np.array([-u2[1], u2[0]])
                if float(np.hypot(*(S_ - q))) / max(self.lv["vmax"] * 0.75, 0.2) > t_ball:
                    continue                             # the receiver would not be there in time
                spare = self.lv.get("through_spare", PASS["through_spare_s"])   # screening variants: riskier passes
                if min([float(np.hypot(*(o - X))) / PASS["opp_v"] for o in opps] or [99.0]) < t_ball + spare:
                    continue                             # an opponent gets to the spot first
                if spare > -5.0 and not self._lane_clear(ball, X, v0, opps):
                    continue
                d = X - ball                              # the receiver itself off the ball's path
                sp = float(np.dot(S_ - ball, d / L))
                if 0.0 < sp < L and abs(float(np.cross(d / L, S_ - ball))) < 0.35:
                    continue
                val = -float(np.hypot(*(goal - X))) + goal_angle(X)
                if val > bval:
                    best, bval = dict(recv=r, X=X, L=L, v0=v0, mode="through", S=S_,
                                      face=math.atan2(u2[1], u2[0])), val
        return best

    def _cutback(self, w, tr, s, ball, bv):
        """Open play near their goal: the striker at a still ball, no opponent within onetouch_free_m, and the teammate
        on the one-touch spot (_get_open put it there; within 0.3 m) with a wider view of the goal: pass to it (the
        striker lines up for the pass; the receiver arms its timed kick when the pass is kicked)"""
        sp = getattr(self, "_ot_spot", None)
        if sp is None or float(np.hypot(*bv)) > 0.3 or w.kicking(s):
            return None
        r, S_, face = sp
        me = np.asarray(tr["robots"][s]["xy"], float)
        if float(np.hypot(*(me - ball))) > 1.2:
            return None
        if float(np.hypot(*(np.asarray(tr["robots"][r]["xy"], float) - S_))) > 0.6:
            return None                                  # it settles while the passer lines up (>= 3 s)
        opps = self._opps(tr)
        if min([float(np.hypot(*(o - ball))) for o in opps] or [9.0]) < PASS["onetouch_free_m"]:
            return None
        fu = np.array([math.cos(face), math.sin(face)])
        X = S_ + np.mean(SWING_ZONE["ahead"]) * fu - np.mean(SWING_ZONE["right"]) * np.array([-fu[1], fu[0]])
        if goal_angle(X) < goal_angle(ball) + PASS["better_rad"]:
            return None
        L = float(np.hypot(*(X - ball)))
        if not PASS["min_m"] <= L <= PASS["max_m"]:
            return None
        v0 = math.sqrt(PASS["arrive_v"] ** 2 + 2 * ROLL_DECEL * L)
        if not self._lane_clear(ball, X, v0, opps, lane_m=0.35):
            return None
        return dict(recv=r, X=X, L=L, v0=v0, mode="onetouch", S=S_, face=face)

    def _setplay_choice(self, tr, s, ball):
        """Our free kick (5 v 5 kick-in, corner, goal kick; the opponents keep their distance until the ball is in
        play): near their goal a one-touch pass (the receiver's spot and facing from _onetouch_spot's geometry, the
        nearest teammate), elsewhere a pass to the most advanced open teammate (block)"""
        opps = self._opps(tr)
        if ball[0] > HALF_L - PASS["third_m"] - 1.0 and self.lv.get("pass") == "onetouch":
            sp = self._onetouch_spot(tr, s, ball, opps)
            if sp is not None:
                r, S_, face = sp
                fu = np.array([math.cos(face), math.sin(face)])
                X = S_ + np.mean(SWING_ZONE["ahead"]) * fu - np.mean(SWING_ZONE["right"]) * np.array([-fu[1], fu[0]])
                L = float(np.hypot(*(X - ball)))
                v0 = math.sqrt(PASS["arrive_v"] ** 2 + 2 * ROLL_DECEL * L)
                if self._lane_clear(ball, X, v0, opps, lane_m=0.35):
                    return dict(recv=r, X=X, L=L, v0=v0, mode="onetouch", S=S_, face=face)
        goal = np.array([HALF_L, 0.0])
        best, bval = None, -1e9
        for r in self._mates(tr, s):
            X = np.asarray(tr["robots"][r]["xy"], float)
            L = float(np.hypot(*(X - ball)))
            if not PASS["min_m"] <= L <= PASS["max_m"]:
                continue
            if min([float(np.hypot(*(o - X))) for o in opps] or [9.0]) < PASS["open_m"]:
                continue
            v0 = math.sqrt(PASS["arrive_v"] ** 2 + 2 * ROLL_DECEL * L)
            if not self._lane_clear(ball, X, v0, opps):
                continue
            val = -float(np.hypot(*(goal - X)))
            if val > bval:
                best, bval = dict(recv=r, X=X, L=L, v0=v0, mode="block", S=X.copy(), face=0.0), val
        return best

    def _onetouch_spot(self, tr, s, ball, opps):
        """(robot, spot, facing) of a teammate for a one-touch shot from a pass from the ball now: X in front of the
        goal, the ball arriving from the robot's front half, no opponent within onetouch_open_m of the spot; the
        teammate nearest the spot. Sticky: the previous X is kept while it stays valid (the receiver settles)."""
        a_x, r_y = np.mean(SWING_ZONE["ahead"]), np.mean(SWING_ZONE["right"])
        mates = self._mates(tr, s)

        def at(X):
            L = float(np.hypot(*(X - ball)))
            if not PASS["min_m"] <= L <= PASS["max_m"]:
                return None
            u = (X - ball) / L
            G = np.array([HALF_L, (GOAL_W / 2 - 0.5) * (-1.0 if X[1] > 0 else 1.0)])
            d = G - X
            shot = math.atan2(d[1], d[0])
            vm = PASS["arrive_v"] * u
            face = shot - one_touch_deflection(float(-math.sin(shot) * vm[0] + math.cos(shot) * vm[1]))
            if abs(_wrap(math.atan2(-u[1], -u[0]) - face)) > PASS["onetouch_cone"] - 0.2:
                return None
            fu = np.array([math.cos(face), math.sin(face)])
            S_ = X - a_x * fu + r_y * np.array([-fu[1], fu[0]])
            if min([float(np.hypot(*(o - S_))) for o in opps] or [9.0]) < PASS["onetouch_open_m"]:
                return None
            return S_, face

        prev = getattr(self, "_ot_keep", None)
        if prev is not None and prev[0] in mates:
            got = at(prev[1])
            if got is not None:
                return prev[0], got[0], got[1]
        best, bc = None, 1e9
        for dx in (1.8, 2.4, 3.0):
            for y in (-0.9, -0.3, 0.3, 0.9):
                X = np.array([HALF_L - dx, y])
                got = at(X)
                if got is None:
                    continue
                for r in mates:
                    c = float(np.hypot(*(got[0] - np.asarray(tr["robots"][r]["xy"], float))))
                    if c < bc:
                        best, bc = (r, X, got[0], got[1]), c
        if best is None:
            self._ot_keep = None
            return None
        self._ot_keep = (best[0], best[1])
        return best[0], best[2], best[3]

    def _passing(self, w, tr, old, roles, rob, ref):
        """The reference's passes: {robot: (role, ref overrides)} for the passer and the receiver of a pass under way
        ({robot: ("cmd", command)}: a direct command; ("keep", None): no new command). Passes start in _kick_or_pass
        (open play: at the moment the striker kicks) or here (lv "setplay": our free kick, the passer waits until the
        receiver is in place). The receiver either stands in the ball's path (block: the ball stops at its legs) or,
        for a one-touch shot, stands so that the ball runs into its strike zone, arms a timed kick at the goal once
        the passer has kicked, and refines it when the pass has left. Without a pass: _get_open."""
        ours_fk = bool(w.fk and not w.fk["in_play"] and w.fk["team"] == self.team)
        if w.state != "play" or (w.ko and not w.ko["in_play"]) or (w.fk and not w.fk["in_play"] and not ours_fk):
            self.plan = None
            return {}
        ball, bv = np.asarray(tr["ball"], float), np.asarray(tr["ball_v"], float)
        dt = CONTROL_DT
        self._plan_end(w, tr, ball, bv)
        pl = self.plan
        if pl is None:
            s = next((r for r, ro in roles.items() if ro == "striker"), None)
            if s is None:
                return {}
            never = self.lv.get("pass_never")            # screening control: the off-ball moves, never a pass
            if ours_fk and self.lv.get("setplay") and ball[0] > -PASS["setplay_x"] and not never:
                c = self._setplay_choice(tr, s, ball)    # our free kick: a pass to a teammate set up for it
                if c is not None:
                    self.plan = dict(passer=s, k0=w.k, struck_k=None, kicked=False, k_kick=None, armed=False,
                                     t_p=PASS["strike_s"], setplay=True, **c)
            if self.plan is None:
                out = self._get_open(tr, roles, s, ball)  # the others move to where a pass can reach them
                c = None if never else self._through(w, tr, s, ball, bv) if self.lv.get("pass") == "through" else \
                    self._cutback(w, tr, s, ball, bv)
                if c is None:
                    return out
                self.plan = dict(passer=s, k0=w.k, struck_k=None, kicked=False, k_kick=None, armed=False,
                                 t_p=PASS["cut_t"], **c)
            pl = self.plan
        out = {}
        passer, recv, X = pl["passer"], pl["recv"], pl["X"]
        if pl["struck_k"] is None:
            if w.kicking(passer):
                if not pl["kicked"]:
                    pl["k_kick"] = w.k
                pl["kicked"] = True
                out[passer] = ("keep", None)
            else:
                ready = True
                if pl.get("setplay"):
                    rs = tr["robots"][recv]
                    dpos = float(np.hypot(*(np.asarray(rs["xy"], float) - pl["S"])))
                    ready = dpos < 0.08 and abs(_wrap(float(rs["yaw"]) - pl["face"])) < 0.08 if pl["mode"] == "onetouch" \
                        else dpos < 0.3
                out[passer] = ("striker", dict(aim_point=X, pass_power=power_for_speed(pl["v0"], "step" if self.lv.get("step") else "swing"),
                                               pass_t=None if pl.get("setplay") else pl["t_p"], no_kick=not ready))
        else:
            out[passer] = ("support", {})
        if self.lv.get("pass_deaf"):                     # B3 weakened: the receiver does not know the pass is coming
            return out
        if pl["mode"] == "through":                      # into space: wait behind the spot, facing their goal
            out[recv] = ("receive", dict(spot=pl["S"], face=pl["face"]))
            return out
        me = tr["robots"][recv]
        p, yaw = np.asarray(me["xy"], float), float(me["yaw"])
        moving = pl["struck_k"] is not None and float(np.hypot(*bv)) > 0.1
        u = bv / float(np.hypot(*bv)) if moving else (X - ball) / max(float(np.hypot(*(X - ball))), 1e-6)
        v = float(np.hypot(*bv)) if moving else pl["v0"]
        if pl["mode"] == "onetouch":
            sproj = float(np.dot(X - ball, u))
            P = ball + u * max(sproj, 0.0)               # where the ball passes nearest the planned point
            t_arr = None
            if pl["struck_k"] is not None:
                t_arr = roll_time(max(sproj, 0.0), v)
            elif pl["k_kick"] is not None:
                t_arr = (pl["k_kick"] - w.k) * dt + pl["t_p"] + (roll_time(pl["L"], pl["v0"]) or 3.0)
            if w.kicking(recv) and w.prog[recv].get("at") is not None:
                if t_arr is not None and pl["struck_k"] is not None:     # refine: the pass has left
                    out[recv] = ("cmd", dict(type="kick", power=1.0, aim=0.0,
                                             at=[round(t_arr, 3), float(P[0]), float(P[1])]))
                else:
                    out[recv] = ("keep", None)
                return out
            if pl["armed"]:                              # the armed kick is over (struck or missed)
                out[recv] = ("keep", None)
                return out
            S, face = pl["S"], pl["face"]
            there = float(np.hypot(*(S - p))) < 0.06 and abs(_wrap(face - yaw)) < 0.06
            if there and t_arr is not None and t_arr > PASS["arm_s"]:
                out[recv] = ("cmd", dict(type="kick", power=1.0, aim=0.0, at=[round(t_arr, 3), float(X[0]), float(X[1])]))
                pl["armed"] = True
                return out
            if pl["struck_k"] is None or (t_arr is not None and t_arr > PASS["arm_s"]):
                out[recv] = ("receive", dict(spot=S, face=face, vmax=0.15 if float(np.hypot(*(S - p))) < 0.4 else None))
                return out
            pl["mode"] = "block"                         # too late to arm: stop the ball instead
        # block: the trunk on the ball's path, facing the ball; after the pass, the earliest reachable point
        face = math.atan2(-u[1], -u[0])
        if pl["struck_k"] is None:
            spot = X
        else:
            spot = None
            for i in range(1, 60):
                t = 0.1 * i
                dist = v * t - 0.5 * ROLL_DECEL * t * t if v > ROLL_DECEL * t else v * v / (2 * ROLL_DECEL)
                q = ball + u * dist
                if float(np.hypot(*(q - p))) / 0.55 + 0.3 <= t:
                    spot = q
                    break
            if spot is None:
                spot = ball + u * max(float(np.dot(p - ball, u)), 0.0)
        out[recv] = ("receive", dict(spot=spot, face=face))
        return out

    def _plan_end(self, w, tr, ball, bv):
        """end a pass plan (and log its outcome): not struck in time, the passer far from the ball or its kick over
        without a strike; after the strike, any touch, 7 s, or the ball stopped"""
        pl, dt = self.plan, CONTROL_DT
        if pl is None:
            return
        passer, recv = pl["passer"], pl["recv"]
        gone = any(tr["robots"][x]["bench"] or tr["robots"][x]["fallen"] for x in (passer, recv))
        t_kick = None if pl["k_kick"] is None else round((pl["k_kick"] - pl["k0"]) * dt, 2)
        if pl["struck_k"] is None:
            pp = w.prog[passer]
            swung = pp["type"] == "kick" and pp.get("kicker") is not None and \
                pp["kicker"].phase() in ("swing", "follow", "retract", "lower")
            if swung and w.k - w.ball_contact[passer] <= 1 and float(np.hypot(*bv)) > PASS["struck_v"]:
                pl["struck_k"] = w.k
                return
            late = (w.k - pl["k0"]) * dt > (FREE_KICK_S - 1.0 if pl.get("setplay") else PASS["plan_s"])
            far = float(np.hypot(*(np.asarray(tr["robots"][passer]["xy"]) - ball))) > 2.0 and not pl.get("setplay")
            if gone or late or far or (pl["kicked"] and not w.kicking(passer)):
                self.log.append(dict(k0=pl["k0"], mode=pl["mode"], end="not_struck", t_kick=t_kick,
                                     why="gone" if gone else "timeout" if late else "far" if far else "kick_over",
                                     passer=passer, recv=recv, setplay=bool(pl.get("setplay"))))
                self.plan = None
            return
        touched = [x for x in ROBOTS if x != passer and w.ball_contact[x] > pl["struck_k"]]
        if gone or touched or (w.k - pl["struck_k"]) * dt > PASS["max_s"] or \
                (float(np.hypot(*bv)) < 0.05 and (w.k - pl["struck_k"]) * dt > 1.0):
            first = min(touched, key=lambda x: w.ball_contact[x]) if touched else None
            self.log.append(dict(k0=pl["k0"], mode=pl["mode"], armed=pl["armed"], end="struck", t_kick=t_kick,
                                 t_prep=round((pl["struck_k"] - pl["k0"]) * dt, 2),
                                 t_flight=round((w.k - pl["struck_k"]) * dt, 2),
                                 by=None if first is None else "recv" if first == recv else
                                 "mate" if first[0] == self.team else "opp", k_end=w.k,
                                 passer=passer, recv=recv, first=first, struck_k=pl["struck_k"],
                                 X=[round(float(x), 3) for x in pl["X"]], v0=round(float(pl["v0"]), 3),
                                 setplay=bool(pl.get("setplay"))))
            self.plan = None
