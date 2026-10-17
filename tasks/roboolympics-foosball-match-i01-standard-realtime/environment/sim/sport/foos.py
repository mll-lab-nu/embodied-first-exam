"""Table football (foosball) on a physical MuJoCo table: 2 x 4 motor-driven rods, the ball, and the referee.

The table is procedural (primitive geoms, no meshes). Each rod has a slide and a rotation joint driven by torque-limited
motors that follow a speed- and acceleration-limited path to the commanded target; the servo never drives a rod faster
than the machine's top speeds (KiRo, deviation D10), also when the rod catches up with its path after the ball held it
up, and the drives hold the top speeds against outside pushes too (govern). The referee follows the ITSF Standard
Matchplay Rules v2.0 (RULEBOOK in scripts/olympiad/foosball/spec.py) with the deviations listed there: one game to 5
points, the opening sequence, the possession time limits per rod, dead ball and ball off table restarts, the spinning
rule, and a safety cap on the playing time with a stated last resort (no draws).

Frames. World: x along the table (seat A's goal at x = -0.60, seat B's at x = +0.60), y across, z up, playfield at
z = 0. Each seat has a local frame turned half a turn about the table centre for B: local x points at the opponent's
goal, local y to the left of a player looking at it. Rod commands and rod states are in the seat's local frame.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from foos_policy import Policy

REVISION = 'foosball-program-v2'
DT, PHYSICS_DT = .01, .001                  # 10 ms control step (eai-standard-realtime/1.0), 1 kHz physics
SUBSTEPS = round(DT / PHYSICS_DT)
LATENCY_STEPS = 2                           # a command reaches the motors 2 control steps (20 ms) after it is taken
POINTS_TO_WIN = 5                           # one game to 5 points (the ITSF points target of a standard game)
CAP_S = 240.                                # safety cap: at most this much playing time (game seconds) ...
MAX_RALLIES = 40                            # ... and at most this many rallies; then the last resort decides
DEAD_S = 1.                                 # dead ball: stationary and unreachable this long (SMR 7.2)
STILL_V = .01                               # m/s: below this the ball is stationary
CAM_W, CAM_H, CAM_FOVY, CAM_Z = 384, 240, 32., 1.45
LENGTH, WIDTH, GOAL_W = 1.20, .68, .20      # playfield (x, y), goal mouth width
HALF_L, HALF_W = LENGTH/2, WIDTH/2
BALL_R, BALL_M = .0175, .024
LID_Z = .040                                # a transparent cover: the ball stays below it (no aerials, no ball off table)
ROD_Z = .090                                # rod axes above the playfield
FOOT_R, FOOT_HL = .012, .014               # a figure's foot: a capsule along x (radius, half length): 5.2 x 2.4 cm
FOOT_Z = -.075                              # its axis below the rod axis: bottom 3 mm above the playfield
TORSO_HALF = (.010, .011, .034)
TORSO_Z = -.040
FIGURE_REACH = FOOT_R+BALL_R                # lateral contact half-width of a figure for a ball on the playfield
FILLET_R = .02                              # rounded fillets along the side walls: a ball cannot rest against a wall
ROD_X = {'goalie': -.525, 'defence': -.375, 'midfield': -.075, 'attack': .225}      # local x of each seat's rods
MEN = {'goalie': (-.20, 0., .20), 'defence': (-.12, .12), 'midfield': (-.24, -.12, 0., .12, .24),
       'attack': (-.20, 0., .20)}           # figure offsets along each rod (local y at slide 0)
TRAVEL = {'goalie': .11, 'defence': .19, 'midfield': .06, 'attack': .11}             # slide range +- (m)
RODS = ('goalie', 'defence', 'midfield', 'attack')
GROUP = {'goalie': 'goalie_rods', 'defence': 'goalie_rods', 'midfield': 'midfield', 'attack': 'attack'}  # SMR 2: the
LIMIT_S = {'goalie_rods': 15., 'midfield': 10., 'attack': 15.}   # goalie rod = goalkeeper + 2-rod; SMR 6 time limits
AWARD = {'goalie_rods': 'midfield', 'midfield': 'midfield', 'attack': 'goalie'}      # SMR 6 penalties: 5-rod / goalie
ANGLE_MAX = 2.6                             # rad: commands within +-ANGLE_MAX (0 = figures hanging straight down)
ANGLE_STOP = 2.8                            # rad: the rotation's mechanical stops (no full turn: no spinning, SMR 10)
SLIDE_V, SLIDE_A = 2.0, 40.                 # m/s, m/s^2: top sliding speed (KiRo, D10) and path acceleration (an estimate)
SPIN_W, SPIN_A = 52., 4000.                 # rad/s, rad/s^2: top turning speed (KiRo: 3000 deg/s) and acceleration (estimate)
SLIDE_F, SPIN_T = 60., 5.                   # N, N m: motor limits (estimates)
SERVO_W, SERVO_Z = 150., .9                 # servo bandwidth (rad/s) and damping ratio; the top speeds bound the rod (servo)
ROD_MASS = .40                              # kg, the bare rod (figures add 0.025 kg each)
FOOT_RADIUS = math.hypot(FOOT_Z, FOOT_HL)+FOOT_R                # the foot's farthest point from the rod axis
X_REACH = math.sqrt((FOOT_RADIUS+BALL_R)**2-(ROD_Z-BALL_R)**2)    # how far from a rod (along x) a foot reaches the ball
LEVELS = {                                  # the scripted opponent (seat B of the single-player game): reaction delay
    1: dict(delay=14, predict=1., slide_v=.6, omega=25., shoot=True, aim=False, style='solo'),    # (control steps),
    2: dict(delay=11, predict=.5, slide_v=1.0, omega=35., shoot=True, aim=False, style='solo'),   # extrapolation over
    3: dict(delay=9, predict=1., slide_v=1.6, omega=45., shoot=True, aim=True, style='team'),     # it, slide speed m/s,
    4: dict(delay=8, predict=1., slide_v=2.0, omega=52., shoot=True, aim=True, style='team')}     # kick speed rad/s,
                                                    # shots from the 5- and 3-rod, aiming past the opponent's figures,
                                                    # style (foos_policy.py). v2: no level reacts faster than KiRo
                                                    # (about 80 ms); v1: 14/9/6/3 steps, 20/35/55/80 rad/s, L1 no shots
SCENE_COLORS = dict(field='.12 .45 .2 1', wall='.18 .18 .2 1', A='.15 .3 .95 1', B='.92 .12 .12 1',
                    ball='1 .55 0 1', rod='.75 .75 .78 1', goal='.05 .05 .05 1', mark='.9 .9 .9 1')
OWN = {'A': 1., 'B': -1.}                   # world x = OWN * local x, world y = OWN * local y
OTHER = {'A': 'B', 'B': 'A'}


def source_sha():
    h = hashlib.sha256(Path(__file__).read_bytes())
    h.update(Path(__file__).with_name('foos_policy.py').read_bytes())
    return h.hexdigest()


def rod_world_x(seat, rod): return OWN[seat]*ROD_X[rod]


def to_local(seat, xy): return [OWN[seat]*float(xy[0]), OWN[seat]*float(xy[1])]


def scene_xml():
    c = SCENE_COLORS
    root = ET.Element('mujoco', model='foosball')
    ET.SubElement(root, 'compiler', angle='radian', autolimits='true')
    ET.SubElement(root, 'option', timestep=str(PHYSICS_DT), integrator='implicitfast', cone='elliptic', iterations='30',
                  noslip_iterations='0')
    visual = ET.SubElement(root, 'visual'); ET.SubElement(visual, 'global', offwidth='768', offheight='480')
    ET.SubElement(visual, 'headlight', ambient='.55 .55 .55', diffuse='.45 .45 .45', specular='0 0 0')
    ET.SubElement(visual, 'quality', shadowsize='0')
    world = ET.SubElement(root, 'worldbody')
    ET.SubElement(world, 'light', pos='0 0 3', dir='0 0 -1', directional='true', castshadow='false', diffuse='.3 .3 .3')
    # every ball contact uses the other geom's parameters (priority 2): the playfield rolls the ball with a little
    # resistance (condim 6), walls and fillets are bouncy, figures are dead (a block stops the ball at the figure)
    static = dict(contype='2', conaffinity='0', condim='3', friction='.3 .005 .0002', priority='2')
    bounce = dict(solref='.004 .3', solimp='.95 .99 .001')
    ET.SubElement(world, 'geom', name='floor', type='plane', pos='0 0 -.30', size='3 3 .1', rgba='.3 .3 .32 1',
                  contype='0', conaffinity='0')
    ET.SubElement(world, 'geom', name='playfield', type='box', pos='0 0 -.01', size=f'{HALF_L} {HALF_W} .01',
                  rgba=c['field'], **{**static, 'condim': '6'}, solref='.004 1', solimp='.95 .99 .001')
    for name, x, y in (('mark_centre', 0., 0.),):
        ET.SubElement(world, 'geom', name=name, type='cylinder', pos=f'{x} {y} .0005', size='.012 .0005', rgba=c['mark'],
                      contype='0', conaffinity='0')
    ET.SubElement(world, 'geom', name='mark_line', type='box', pos='0 0 .0004', size=f'.002 {HALF_W} .0004', rgba=c['mark'],
                  contype='0', conaffinity='0')
    for side in (-1, 1):                  # side walls, end walls with the goal mouths, goal boxes
        ET.SubElement(world, 'geom', name=f'wall_side_{side}', type='box', pos=f'0 {side*(HALF_W+.02)} .03',
                      size=f'{HALF_L+.08} .02 .07', rgba=c['wall'], **static, **bounce)
        half = (WIDTH-GOAL_W)/4
        for end in (-1, 1):
            ET.SubElement(world, 'geom', name=f'wall_end_{end}_{side}', type='box',
                          pos=f'{end*(HALF_L+.02)} {side*(GOAL_W/2+half)} .03', size=f'.02 {half} .07', rgba=c['wall'],
                          **static, **bounce)
        ET.SubElement(world, 'geom', name=f'fillet_{side}', type='cylinder', pos=f'0 {side*HALF_W} 0',
                      quat='.7071068 0 .7071068 0', size=f'{FILLET_R} {HALF_L}', rgba=c['wall'], **static, **bounce)
    for end in (-1, 1):
        ET.SubElement(world, 'geom', name=f'goal_floor_{end}', type='box', pos=f'{end*(HALF_L+.05)} 0 -.06',
                      size=f'.05 {GOAL_W/2} .01', rgba=c['goal'], **static)
        ET.SubElement(world, 'geom', name=f'goal_back_{end}', type='box', pos=f'{end*(HALF_L+.11)} 0 -.01',
                      size=f'.01 {GOAL_W/2+.02} .06', rgba=c['goal'], **static)
        for side in (-1, 1):
            ET.SubElement(world, 'geom', name=f'goal_side_{end}_{side}', type='box',
                          pos=f'{end*(HALF_L+.06)} {side*(GOAL_W/2+.01)} -.01', size='.06 .01 .06', rgba=c['goal'], **static)
    ET.SubElement(world, 'geom', name='lid', type='box', pos=f'0 0 {LID_Z+.005}', size=f'{HALF_L+.12} {HALF_W} .005',
                  rgba='1 1 1 0', group='3', **static, solref='.004 1')
    for i, (x, y) in enumerate([(-.56, -.30), (-.56, .30), (.56, -.30), (.56, .30)]):     # calibration markers
        ET.SubElement(world, 'geom', name=f'marker_{i}', type='box', pos=f'{x} {y} .0005', size='.01 .01 .0005',
                      rgba='1 1 1 1', contype='0', conaffinity='0')
    ball = ET.SubElement(world, 'body', name='ball', pos=f'0 0 {BALL_R}')
    ET.SubElement(ball, 'freejoint', name='ball')
    ET.SubElement(ball, 'geom', name='ball', type='sphere', size=str(BALL_R), mass=str(BALL_M), rgba=c['ball'],
                  contype='1', conaffinity='2', condim='6', friction='.3 .005 .0002', solref='.004 1',
                  solimp='.95 .99 .001')
    for seat in ('A', 'B'):
        for rod in RODS:
            x = rod_world_x(seat, rod)
            body = ET.SubElement(world, 'body', name=f'{seat}_{rod}', pos=f'{x} 0 {ROD_Z}',
                                 quat='1 0 0 0' if seat == 'A' else '0 0 0 1')
            t = TRAVEL[rod]
            ET.SubElement(body, 'joint', name=f'{seat}_{rod}_slide', type='slide', axis='0 1 0', range=f'{-t-.002} {t+.002}',
                          damping='.5', armature='.0')
            ET.SubElement(body, 'joint', name=f'{seat}_{rod}_spin', type='hinge', axis='0 -1 0',
                          range=f'{-ANGLE_STOP} {ANGLE_STOP}', damping='.002', armature='.0005')
            ET.SubElement(body, 'geom', name=f'{seat}_{rod}_bar', type='cylinder', pos='0 0 0', quat='.7071068 .7071068 0 0',
                          size='.006 .62', mass=str(ROD_MASS), rgba=c['rod'], contype='0', conaffinity='0')
            for i, y in enumerate(MEN[rod]):
                kw = dict(contype='2', conaffinity='0', condim='4', friction='.4 .005 .0001', rgba=c[seat], priority='2',
                          solref='.004 1', solimp='.95 .99 .001')
                ET.SubElement(body, 'geom', name=f'{seat}_{rod}_{i}_torso', type='box', pos=f'0 {y} {TORSO_Z}',
                              size=' '.join(map(str, TORSO_HALF)), mass='.015', **kw)
                ET.SubElement(body, 'geom', name=f'{seat}_{rod}_{i}_foot', type='capsule', pos=f'0 {y} {FOOT_Z}',
                              quat='.7071068 0 .7071068 0', size=f'{FOOT_R} {FOOT_HL}', mass='.010', **kw)
                ET.SubElement(body, 'geom', name=f'{seat}_{rod}_{i}_head', type='sphere', pos=f'0 {y} .016', size='.012',
                              mass='.0001', rgba=c[seat], contype='0', conaffinity='0')
    for seat in ('A', 'B'):               # the seat's overhead camera: its own goal at the left of the image
        s = OWN[seat]
        ET.SubElement(world, 'camera', name=f'overhead_{seat}', pos=f'0 0 {CAM_Z}', xyaxes=f'{s} 0 0 0 {s} 0',
                      fovy=str(CAM_FOVY))
    ET.SubElement(world, 'camera', name='broadcast', pos='0 -1.25 1.15', xyaxes='1 0 0 0 .68 .73', fovy='45')
    act = ET.SubElement(root, 'actuator')
    for seat in ('A', 'B'):
        for rod in RODS:
            ET.SubElement(act, 'motor', name=f'{seat}_{rod}_slide_motor', joint=f'{seat}_{rod}_slide',
                          ctrlrange=f'{-SLIDE_F} {SLIDE_F}')
            ET.SubElement(act, 'motor', name=f'{seat}_{rod}_spin_motor', joint=f'{seat}_{rod}_spin',
                          ctrlrange=f'{-SPIN_T} {SPIN_T}')
    return ET.tostring(root, encoding='unicode')


def validate_action(body, seat=None):
    """{'rods': {rod: {'slide': m, 'angle': rad, ['omega': rad/s], ['speed': m/s]}}}: any subset of the four rods,
    each with a slide and/or an angle target. Returns the normalised dict; anything else -> ValueError (HTTP 400)."""
    if not isinstance(body, dict) or set(body) - {'rods', 'type'} or body.get('type', 'rods') != 'rods':
        raise ValueError('action must be {"rods": {...}}')
    rods = body.get('rods')
    if not isinstance(rods, dict) or not rods: raise ValueError('rods must be a nonempty object')
    out = {}
    for rod, cmd in rods.items():
        if rod not in RODS: raise ValueError(f'unknown rod {rod!r} (goalie, defence, midfield, attack)')
        if not isinstance(cmd, dict) or not cmd or set(cmd) - {'slide', 'angle', 'omega', 'speed'}:
            raise ValueError(f'{rod}: give slide and/or angle, optionally omega and speed')
        if 'slide' not in cmd and 'angle' not in cmd: raise ValueError(f'{rod}: give slide and/or angle')
        c = {}
        for k, v in cmd.items():
            if type(v) not in (int, float) or not math.isfinite(v): raise ValueError(f'{rod}.{k} must be a finite number')
            c[k] = float(v)
        if 'slide' in c and abs(c['slide']) > TRAVEL[rod]+1e-9:
            raise ValueError(f'{rod}.slide must be within +-{TRAVEL[rod]} m')
        if 'angle' in c and abs(c['angle']) > ANGLE_MAX+1e-9:
            raise ValueError(f'{rod}.angle must be within +-{ANGLE_MAX} rad (no spinning)')
        if 'omega' in c and not 0 < c['omega'] <= SPIN_W+1e-9: raise ValueError(f'{rod}.omega must be in (0, {SPIN_W}] rad/s')
        if 'speed' in c and not 0 < c['speed'] <= SLIDE_V+1e-9: raise ValueError(f'{rod}.speed must be in (0, {SLIDE_V}] m/s')
        out[rod] = c
    return out


def profile(q, v, target, vmax, amax, dt):
    """One step of a speed- and acceleration-limited path towards target (vectorised): returns (q, v)."""
    e = target-q
    vd = np.sign(e)*np.minimum(vmax, np.sqrt(2*amax*np.abs(e)*.95))
    dv = np.clip(vd-v, -amax*dt, amax*dt)
    v2 = v+dv
    q2 = q+(v+v2)/2*dt
    over = (np.sign(target-q2) != np.sign(e)) & (e != 0)          # never overshoot the target
    q2 = np.where(over | (np.abs(e) < 1e-7), target, q2); v2 = np.where(over | (np.abs(e) < 1e-7), 0., v2)
    return q2, v2


def servo(inertia, ref, ref_v, q, v, vmax, fmax):
    """The motor force (torque) of one physics step (vectorised): a position loop that asks for a speed, the path's speed
    plus the position error x bandwidth / (2 damping ratio), within the top speed vmax, and a speed loop that drives the
    rod to it with the force limit fmax. Below the top speed this is the PD law inertia x (bandwidth^2 x error + 2 x damping
    ratio x bandwidth x speed error) unchanged; a rod that the ball held up catches up with its path at vmax at most."""
    kd = 2*SERVO_Z*SERVO_W
    want = np.clip(ref_v+SERVO_W**2/kd*(ref-q), -vmax, vmax)
    return np.clip(inertia*kd*(want-v), -fmax, fmax)


class Foosball:
    def __init__(self, seed=101, level=1, duel=False, first='A'):
        if level not in (1, 2, 3, 4) or first not in ('A', 'B'): raise ValueError('invalid configuration')
        self.seed, self.level, self.duel, self.first = seed, level, duel, first
        self.source_sha = source_sha(); self.model = mujoco.MjModel.from_xml_string(scene_xml())
        self.data = mujoco.MjData(self.model)
        self.rng = np.random.default_rng(seed)
        m = self.model
        self.keys = [(s, r) for s in ('A', 'B') for r in RODS]          # 8 rods, A first
        self.sq = np.array([m.jnt_qposadr[m.joint(f'{s}_{r}_slide').id] for s, r in self.keys])
        self.aq = np.array([m.jnt_qposadr[m.joint(f'{s}_{r}_spin').id] for s, r in self.keys])
        self.sv = np.array([m.jnt_dofadr[m.joint(f'{s}_{r}_slide').id] for s, r in self.keys])
        self.av = np.array([m.jnt_dofadr[m.joint(f'{s}_{r}_spin').id] for s, r in self.keys])
        self.sact = np.array([m.actuator(f'{s}_{r}_slide_motor').id for s, r in self.keys])
        self.aact = np.array([m.actuator(f'{s}_{r}_spin_motor').id for s, r in self.keys])
        self.mass = np.array([ROD_MASS+.025*len(MEN[r]) for _, r in self.keys])
        self.inertia = np.array([.0005+.025*.06**2*len(MEN[r]) for _, r in self.keys])     # about the rod axis (approx.)
        bq = m.jnt_qposadr[m.joint('ball').id]; self.bq = int(bq); self.bv = int(m.jnt_dofadr[m.joint('ball').id])
        self.ball_geom = m.geom('ball').id
        self.figure_of = {}                                             # geom id -> (seat, rod, figure index)
        for s, r in self.keys:
            for i in range(len(MEN[r])):
                for part in ('torso', 'foot'):
                    self.figure_of[m.geom(f'{s}_{r}_{i}_{part}').id] = (s, r, i)
        self.k = 0                  # control steps of play (the world's clock; frozen time does not count)
        self.point_k = 0
        self.results = []           # one entry per rally: how it ended
        self.done = self.awaiting_review = False
        self.decided_by = None
        self.contact_steps = 0; self.wall_contacts = 0
        self.governed = 0           # physics steps x rods at which govern() held a pushed rod to its top speed
        self.half_steps = {'A': 0, 'B': 0}          # steps with the ball in each player's half (the last resort)
        self.kickoff_team = first                   # who kicks off between the 5-rods (initial flip, then conceder)
        mujoco.mj_resetData(m, self.data)
        self.restart(('kickoff', first), 'start')

    # ---------------------------------------------------------------- state
    def ball(self): return self.data.qpos[self.bq:self.bq+3].copy()

    def ball_velocity(self): return self.data.qvel[self.bv:self.bv+3].copy()

    def rod_index(self, seat, rod): return (0 if seat == 'A' else 4)+RODS.index(rod)

    def rod_state(self, seat):
        """The seat's own rods, in its local frame (slide in local y; angle positive = feet towards the opponent)."""
        out = {}
        for rod in RODS:
            i = self.rod_index(seat, rod)
            out[rod] = dict(slide=float(self.data.qpos[self.sq[i]]), angle=float(self.data.qpos[self.aq[i]]),
                            slide_velocity=float(self.data.qvel[self.sv[i]]), angular_velocity=float(self.data.qvel[self.av[i]]),
                            command=dict(slide=float(self.cmd_slide[i]), angle=float(self.cmd_angle[i]),
                                         omega=float(self.cmd_omega[i]), speed=float(self.cmd_speed[i])))
        return out

    def figure_y(self, seat, rod):
        """World y of the rod's figures now."""
        i = self.rod_index(seat, rod); s = float(self.data.qpos[self.sq[i]])
        return [OWN[seat]*(y+s) for y in MEN[rod]]

    def reachable_by(self, seat, rod, p=None):
        """Whether a figure of this rod can touch the ball (geometrically, at some slide and angle) where it is."""
        p = self.ball() if p is None else p
        if p[2] > LID_Z or p[2] < -.005: return False
        if abs(p[0]-rod_world_x(seat, rod)) > X_REACH: return False
        y = OWN[seat]*p[1]
        return any(abs(y-m) <= TRAVEL[rod]+FIGURE_REACH for m in MEN[rod])

    def groups_reaching(self, p=None):
        return {(s, GROUP[r]) for s in ('A', 'B') for r in RODS if self.reachable_by(s, r, p)}

    def restart(self, where, why):
        """Play stops: every rod goes back to slide 0, angle 0 (instantly) and the referee places the ball at rest
        beside the central figure of the restart rod: ('kickoff'|'midfield', team) = the team's 5-rod, ('goalie',
        team) = its goalkeeper rod. The side of the figure and a few millimetres along x come from the seed."""
        kind, team = where
        rod = 'goalie' if kind == 'goalie' else 'midfield'
        side = 1. if self.rng.random() < .5 else -1.
        dx = round(float(self.rng.uniform(-.008, .008)), 6)
        local = [ROD_X[rod]+dx, side*.034]
        self.data.qvel[:] = 0
        self.data.qpos[self.sq] = 0.; self.data.qpos[self.aq] = 0.
        self.data.qpos[self.bq:self.bq+3] = [OWN[team]*local[0], OWN[team]*local[1], BALL_R]
        self.data.qpos[self.bq+3:self.bq+7] = [1, 0, 0, 0]
        self.data.ctrl[:] = 0
        n = len(self.keys)
        self.ref_slide = np.zeros(n); self.ref_slide_v = np.zeros(n); self.ref_angle = np.zeros(n); self.ref_angle_v = np.zeros(n)
        self.cmd_slide = np.zeros(n); self.cmd_angle = np.zeros(n)
        self.cmd_omega = np.full(n, SPIN_W); self.cmd_speed = np.full(n, SLIDE_V)
        self.queue = {}                                                 # effect step -> [(seat, rods)]
        self.clock = {}                                                 # (seat, group) -> steps of active possession
        self.still_steps = 0
        self.opening = dict(team=team, group=GROUP[rod], seq=[], done=False)
        self.last_touch = None; self.last_touch_rod = None
        self.sweep = np.zeros(n); self.sweep_dir = np.zeros(n)          # rotation since the last reversal or stop
        self.spin_flag = None                                           # (seat, rod) whose contact was a contact spin
        self.contact_sweep = {}
        self.script = dict(hist=[], policy=None)
        self.restart_k, self.restart_why, self.restart_where = self.k, why, [kind, team]
        mujoco.mj_forward(self.model, self.data)

    # ---------------------------------------------------------------- commands
    def schedule(self, seat, rods):
        """A validated command reaches the motors LATENCY_STEPS control steps from now (the caller records it)."""
        self.queue.setdefault(self.k+LATENCY_STEPS, []).append((seat, rods))

    def set_command(self, seat, rods):
        for rod, c in rods.items():
            i = self.rod_index(seat, rod)
            if 'slide' in c: self.cmd_slide[i] = c['slide']
            if 'angle' in c: self.cmd_angle[i] = c['angle']
            self.cmd_omega[i] = c.get('omega', SPIN_W); self.cmd_speed[i] = c.get('speed', SLIDE_V)

    # ---------------------------------------------------------------- scripted opponent (single player, seat B)
    def scripted(self, seat='B'):
        """Trusted referee-side opponent: the shared player policy (foos_policy.py) on the true ball position `delay`
        control steps ago, extrapolated by its velocity then (levels: LEVELS). It never reads the agent's commands."""
        lv = LEVELS[self.level]; sg = OWN[seat]; sc = self.script
        if sc.get('policy') is None:
            sc['policy'] = Policy(style=lv['style'], omega=lv['omega'], speed=lv['slide_v'], shoot=lv['shoot'], aim=lv['aim'])
            mine = self.restart_where[1] == seat
            sc['policy'].reset(('goalie' if self.restart_where[0] == 'goalie' else 'midfield') if mine else None)
        sc['hist'].append(self.ball()[:2].copy()); sc['hist'] = sc['hist'][-(lv['delay']+3):]
        P = sc['hist'][0]; W = (sc['hist'][2]-sc['hist'][0])/(2*DT) if len(sc['hist']) > 2 else np.zeros(2)
        p = P+W*lv['delay']*DT*lv['predict']
        rods = {r: dict(slide=float(self.data.qpos[self.sq[self.rod_index(seat, r)]]),
                        angle=float(self.data.qpos[self.aq[self.rod_index(seat, r)]])) for r in RODS}
        opp = {r: [sg*y for y in self.figure_y(OTHER[seat], r)] for r in RODS}
        cmds = sc['policy'].update(self.point_k*DT, (sg*float(p[0]), sg*float(p[1])), (sg*float(W[0]), sg*float(W[1])), rods,
                                   {r: opp[r] for r in RODS} if lv['aim'] else None,
                                   opening_done=self.opening['done'] or self.opening['team'] != seat)
        return validate_action(dict(rods={r: dict(slide=float(np.clip(c['slide'], -TRAVEL[r], TRAVEL[r])),
                                                  angle=float(np.clip(c['angle'], -ANGLE_MAX, ANGLE_MAX)),
                                                  omega=float(np.clip(c['omega'], 1., SPIN_W)),
                                                  speed=float(np.clip(c['speed'], .05, SLIDE_V))) for r, c in cmds.items()}))

    # ---------------------------------------------------------------- one control step
    def step(self):
        if self.done or self.awaiting_review: raise RuntimeError('world frozen')
        for seat, rods in self.queue.pop(self.k, []): self.set_command(seat, rods)
        if not self.duel: self.set_command('B', self.scripted('B'))
        m, d = self.model, self.data
        contacts = []
        for _ in range(SUBSTEPS):
            self.ref_slide, self.ref_slide_v = profile(self.ref_slide, self.ref_slide_v, self.cmd_slide, self.cmd_speed,
                                                       SLIDE_A, PHYSICS_DT)
            self.ref_angle, self.ref_angle_v = profile(self.ref_angle, self.ref_angle_v, self.cmd_angle, self.cmd_omega,
                                                       SPIN_A, PHYSICS_DT)
            d.ctrl[self.sact] = servo(self.mass, self.ref_slide, self.ref_slide_v, d.qpos[self.sq], d.qvel[self.sv], SLIDE_V,
                                      SLIDE_F)
            d.ctrl[self.aact] = servo(self.inertia, self.ref_angle, self.ref_angle_v, d.qpos[self.aq], d.qvel[self.av], SPIN_W,
                                      SPIN_T)
            mujoco.mj_step(m, d)
            self.govern()
            for j in range(d.ncon):
                c = d.contact[j]; g1, g2 = int(c.geom1), int(c.geom2)
                if self.ball_geom not in (g1, g2): continue
                other = g2 if g1 == self.ball_geom else g1
                if other in self.figure_of: contacts.append(self.figure_of[other])
                elif (m.geom(other).name or '').startswith('wall'): contacts.append('wall')
            self.track_spin()
        self.k += 1; self.point_k += 1
        figs = [c for c in contacts if c != 'wall']
        if figs: self.contact_steps += 1
        if 'wall' in contacts: self.wall_contacts += 1
        seen = []
        for f in figs:
            if f not in seen: seen.append(f)
        for f in seen: self.touch(f)
        self.referee()
        return seen

    def govern(self):
        """The drives' speed limit against outside pushes: the motors never drive a rod past the top speeds (servo), but
        a ball wedged between a foot, a side wall's fillet and the cover can push one past them (measured: up to 59
        rad/s and 2.1 m/s in about one game in six). After every physics step a rod faster than SLIDE_V / SPIN_W is put
        back to the top speed, and its position to where the top speed would have taken it (semi-implicit Euler: the
        step moved it by its new speed x the time step); each such rod and step is counted (self.governed)."""
        d = self.data
        for qa, va, cap in ((self.sq, self.sv, SLIDE_V), (self.aq, self.av, SPIN_W)):
            v = d.qvel[va]
            over = np.abs(v) > cap
            if over.any():
                held = np.clip(v, -cap, cap)
                d.qpos[qa] -= (v-held)*PHYSICS_DT
                d.qvel[va] = held
                self.governed += int(over.sum())

    def track_spin(self):
        """The rotation of each rod since its last reversal or stop (for the spinning rule, SMR 10)."""
        w = self.data.qvel[self.av]
        moving = np.abs(w) > .5
        same = np.sign(w) == self.sweep_dir
        self.sweep = np.where(moving & same, self.sweep+np.abs(w)*PHYSICS_DT, np.where(moving, np.abs(w)*PHYSICS_DT, 0.))
        self.sweep_dir = np.where(moving, np.sign(w), 0.)
        for (s, r), at in list(self.contact_sweep.items()):             # rotation after the contact, same sweep
            i = self.rod_index(s, r)
            if self.sweep[i] < at-1e-9: del self.contact_sweep[(s, r)]  # a new sweep began
            elif self.sweep[i]-at > 2*math.pi and self.last_touch_rod == (s, r): self.spin_flag = (s, r)

    def touch(self, figure):
        seat, rod, i = figure
        idx = self.rod_index(seat, rod)
        if self.sweep[idx] > 2*math.pi: self.spin_flag = (seat, rod)    # more than a full turn before the contact
        elif self.last_touch_rod != (seat, rod): self.spin_flag = None
        self.contact_sweep[(seat, rod)] = float(self.sweep[idx])
        self.last_touch, self.last_touch_rod = seat, (seat, rod)
        op = self.opening
        if not op['done']:
            if seat == op['team'] and GROUP[rod] == op['group']:
                if not op['seq'] or op['seq'][-1] != (rod, i): op['seq'].append((rod, i))
                if len(op['seq']) >= 3: op['done'] = True                # SMR 5.2: restart figure, clock figure, another
            else:
                op['done'] = True                                       # the opponent played the ball: play is on

    def referee(self):
        """After each control step: goal, possession time limit, opening sequence, spinning, dead ball, ball off table
        and the safety cap (SMR 5-10; deviations in spec.py)."""
        p = self.ball(); v = self.ball_velocity()
        if abs(p[0]) > HALF_L+BALL_R and abs(p[1]) < GOAL_W/2+.02 and p[2] < LID_Z:      # wholly over the goal line
            scorer = 'A' if p[0] > 0 else 'B'
            if self.spin_flag and self.spin_flag[0] == scorer:          # a goal from an illegal spin does not count
                return self.end_rally('illegal_spin', guilty=scorer, next=('midfield', OTHER[scorer]), goal_disallowed=True)
            return self.end_rally('goal', winner=scorer, next=('kickoff', OTHER[scorer]),       # the conceder kicks off
                                  own_goal=self.last_touch == OTHER[scorer],
                                  rod=self.last_touch_rod[1] if self.last_touch_rod else None)
        if abs(p[1]) > HALF_W+.01 or p[2] > LID_Z+.02 or p[2] < -.03 or abs(p[0]) > HALF_L+.15 or not np.all(np.isfinite(p)):
            guilty = self.last_touch                                    # SMR 7.3: the other team's goalie rod
            return self.end_rally('ball_off_table', guilty=guilty,
                                  next=('goalie', OTHER[guilty] if guilty else ('A' if p[0] < 0 else 'B')))
        side = 'A' if p[0] < 0 else 'B'
        self.half_steps[side] += 1
        reach = self.groups_reaching(p)
        for key in list(self.clock):
            if key not in reach: del self.clock[key]                    # the active possession ended
        for key in reach: self.clock[key] = self.clock.get(key, 0)+1
        op = self.opening
        if not op['done'] and (op['team'], op['group']) not in reach:   # transition before the opening was complete
            return self.end_rally('incomplete_opening', guilty=op['team'], next=('midfield', OTHER[op['team']]))
        if self.spin_flag and self.last_touch_rod == self.spin_flag and (self.spin_flag[0], GROUP[self.spin_flag[1]]) not in reach:
            s = self.spin_flag[0]                                        # SMR 10: a transition from a contact spin
            return self.end_rally('illegal_spin', guilty=s, next=('midfield', OTHER[s]))
        over = [key for key, n in self.clock.items() if n*DT > LIMIT_S[key[1]]+1e-9]
        if len(over) == 1:
            s, g = over[0]
            return self.end_rally('possession_time', guilty=s, group=g, next=(AWARD[g], OTHER[s]))
        if len(over) > 1:                                               # both limits at once: neither is at fault
            return self.end_rally('dead_ball', where='both_clocks', next=('kickoff', self.kickoff_team))
        self.still_steps = self.still_steps+1 if np.linalg.norm(v[:3]) < STILL_V else 0
        if not reach and self.still_steps*DT >= DEAD_S-1e-9:            # SMR 7.2: stationary and not reachable
            if abs(p[0]) < abs(ROD_X['midfield']):
                return self.end_rally('dead_ball', where='between_5_rods', next=('kickoff', self.kickoff_team))
            return self.end_rally('dead_ball', where='behind_5_rod', next=('goalie', side))
        if self.k*DT >= CAP_S-1e-9:
            return self.end_rally('time_cap', next=('kickoff', self.kickoff_team))

    def end_rally(self, how, winner=None, guilty=None, next=None, **extra):
        self.results.append(dict(rally=len(self.results)+1, how=how, winner=winner, guilty=guilty,
                                 next=list(next), k=self.k, steps=self.point_k, **extra))
        if how == 'goal': self.kickoff_team = next[1]
        sc = self.scores()
        if max(sc['A']['points'], sc['B']['points']) >= POINTS_TO_WIN:
            self.done, self.decided_by = True, 'score'
        elif how == 'time_cap' or self.k*DT >= CAP_S-1e-9 or len(self.results) >= MAX_RALLIES:
            self.done, self.decided_by = True, self.cap_decision()
        else:
            self.awaiting_review = True

    def cap_decision(self):
        sc = self.scores(); a, b = sc['A']['points'], sc['B']['points']
        if a != b: return 'cap_points'
        if any(r['how'] == 'goal' for r in self.results): return 'cap_last_goal'
        if self.half_steps['A'] != self.half_steps['B']: return 'cap_territory'
        return 'cap_first_kickoff'

    def ready(self):
        if not self.awaiting_review: raise ValueError('not in review')
        self.awaiting_review = False; self.point_k = 0
        r = self.results[-1]
        self.restart(tuple(r['next']), r['how'])

    # ---------------------------------------------------------------- result
    def scores(self):
        return {s: dict(points=sum(r['how'] == 'goal' and r['winner'] == s for r in self.results),
                        fouls=sum(r['guilty'] == s and r['how'] != 'ball_off_table' for r in self.results))
                for s in ('A', 'B')}

    def winner(self):
        """'A' or 'B' once the game is over (never a draw), else None."""
        if not self.done: return None
        sc = self.scores(); a, b = sc['A']['points'], sc['B']['points']
        if a != b: return 'A' if a > b else 'B'
        goals = [r for r in self.results if r['how'] == 'goal']
        if goals: return goals[-1]['winner']                            # the winner of the last point
        if self.half_steps['A'] != self.half_steps['B']:                # 0:0: less time with the ball in one's own half
            return 'A' if self.half_steps['A'] < self.half_steps['B'] else 'B'
        return OTHER[self.first]                                        # identical: not the first kick-off

    def digest(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        h = hashlib.sha256(state.tobytes())
        arrays = {k: getattr(self, k).tolist() for k in ('ref_slide', 'ref_slide_v', 'ref_angle', 'ref_angle_v', 'cmd_slide',
                                                         'cmd_angle', 'cmd_omega', 'cmd_speed', 'sweep', 'sweep_dir')}
        h.update(json.dumps(dict(k=self.k, point_k=self.point_k, results=self.results, arrays=arrays,
                                 queue={str(k): v for k, v in sorted(self.queue.items())},
                                 clock={f'{s}:{g}': n for (s, g), n in sorted(self.clock.items())},
                                 still=self.still_steps, opening=self.opening, last_touch=self.last_touch,
                                 last_touch_rod=self.last_touch_rod, spin_flag=self.spin_flag,
                                 contact_sweep={f'{s}:{r}': v for (s, r), v in sorted(self.contact_sweep.items())},
                                 half_steps=self.half_steps, kickoff=self.kickoff_team, rng=self.rng.bit_generator.state,
                                 script=dict(hist=[x.tolist() for x in self.script['hist']],
                                             policy=None if self.script['policy'] is None else vars(self.script['policy'])),
                                 contacts=self.contact_steps, walls=self.wall_contacts, governed=self.governed,
                                 done=self.done, decided_by=self.decided_by, awaiting_review=self.awaiting_review),
                            sort_keys=True, default=list).encode())
        return h.hexdigest()
