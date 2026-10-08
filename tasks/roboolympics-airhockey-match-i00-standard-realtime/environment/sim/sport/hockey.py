"""Two physical 7-axis iiwa arms on an air hockey table: fixed-step Cartesian execution and the referee.

Robot dynamics are derived from AirHockeyChallenge (MIT, see scene/). The table is new and mesh-free. The referee
follows the USAA Official Rules of Air Hockey (sport.toml [rulebook]) with the deviations listed there
([[deviations]]): one game to 7 points, the seven-second rule (a foul: the puck goes to the opponent), dead-puck
face-offs, a safety cap on the playing time with a stated last resort (no draws) and a 0.35 m goal mouth (D10).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

REVISION = 'airhockey-program-v4'      # v4 (2026-10-08, review item B13): goal mouth 0.35 m (v3: 0.40 m, v2: 0.25 m)
DT, PHYSICS_DT = .01, .001                  # 10 ms control step (eai-standard-realtime/1.0), 1 kHz physics
SUBSTEPS = round(DT / PHYSICS_DT)
POINTS_TO_WIN = 7                           # USAA I.1
SEVEN_S = 7.                                # USAA I.10: seven seconds to shoot the puck across the centre line
DEAD_S = 2.                                 # dead puck: out of both robots' reach this long -> face-off
LINE_S = 7.                                 # dead puck: resting on the centre line this long -> face-off
CAP_S = 120.                                # safety cap: at most this much playing time (game seconds) ...
MAX_RALLIES = 40                            # ... and at most this many rallies; then the last resort decides
CAM_W, CAM_H = 320, 240
LENGTH, WIDTH = 1.948, 1.038
GOAL_DEFAULT = .35                          # sport.toml deviation D10 (the AirHockeyChallenge table: .25)


def goal_width():
    """The goal mouth (m): GOAL_DEFAULT, or the experiment-only override RO_AIRHOCKEY_GOAL_M (0.2-0.6; the official
    tasks never set it; plugin.REVISION and final.json record a non-default width)."""
    v = os.environ.get('RO_AIRHOCKEY_GOAL_M', '').strip()
    if not v: return GOAL_DEFAULT
    g = float(v)
    if not (math.isfinite(g) and .2 <= g <= .6): raise ValueError('RO_AIRHOCKEY_GOAL_M must be within 0.2-0.6 m')
    return g


GOAL = goal_width()
PUCK_R, MALLET_R = .03165, .04815
CONTACT = PUCK_R + MALLET_R
PUCK_DAMPING = '.001'                       # N s/m on the 10 g puck: the air cushion's drag (about 10 % speed per second)
BASE_X = 1.51                               # robot bases at x = -1.51 (A) and +1.51 (B), y = 0
REACH = 1.45                                # mallet centre at most this far from its robot's base
X_NEAR, X_FAR, Y_MAX = .05, .92, .47        # mallet centre workspace in its own half: X_NEAR <= |x| <= X_FAR, |y| <= Y_MAX
HOME_X, SPOT_X = .82, .58                   # mallet home and the puck's placement spot (|x|), in the own half
MAX_SPEED, MAX_ACCEL = 2., 10.             # the mallet's Cartesian trajectory limits (m/s, m/s^2)
LEVELS = {                                  # the scripted opponent (seat B of the single-player game): mallet
    1: dict(speed=.4, delay=15, guard=None, gain=0., tol=.25, aim=0., lead=False),   # speed cap m/s, reaction delay
    2: dict(speed=.6, delay=10, guard=.80, gain=1., tol=.15, aim=0., lead=False),   # steps, guard line |x| m, gain
    3: dict(speed=1., delay=6, guard=.80, gain=1., tol=.08, aim=.07, lead=False),   # on the puck's y, line-up
    4: dict(speed=2., delay=3, guard=.80, gain=1., tol=.05, aim=.08, lead=True)}    # tolerance rad, aim (y at the
                                                                                    # goal), crossing prediction
SCENE = Path(__file__).with_name('scene')
OWN = {'A': -1., 'B': 1.}                   # the sign of x in each seat's own half
OTHER = {'A': 'B', 'B': 'A'}


def source_sha():
    h = hashlib.sha256(Path(__file__).read_bytes())
    for f in sorted(SCENE.glob('*.xml')):
        h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()


def scene_xml(seed=101):
    root = ET.Element('mujoco', model='visual_iiwa_airhockey')
    ET.SubElement(root, 'compiler', angle='radian', autolimits='true')
    ET.SubElement(root, 'option', timestep=str(PHYSICS_DT), integrator='implicitfast', cone='elliptic', iterations='40')
    visual = ET.SubElement(root, 'visual'); ET.SubElement(visual, 'global', offwidth='640', offheight='480')
    ET.SubElement(visual, 'headlight', ambient='.5 .5 .5', diffuse='.5 .5 .5')
    world = ET.SubElement(root, 'worldbody')
    ET.SubElement(world, 'light', pos='0 0 3', dir='0 0 -1', directional='true', castshadow='false')
    ET.SubElement(world, 'geom', name='table_surface', type='box', pos='0 0 -.045', size='1.07 .61 .045', rgba='.9 .92 .94 1', contype='0', conaffinity='0')
    ET.SubElement(world, 'geom', name='floor', type='plane', pos='0 0 -.15', size='4 4 .1', rgba='.16 .2 .24 1', contype='0', conaffinity='0')
    for side in (-1, 1):
        ET.SubElement(world, 'geom', name=f'wall_side_{side}', type='box', pos=f'0 {side*(WIDTH/2+.025)} .035', size='1.07 .025 .035', rgba='.2 .25 .3 1', friction='0 0 0', solref='.0075 .1', solimp='.99 .999 .001')
        for end in (-1, 1):
            half = (WIDTH-GOAL)/4
            ET.SubElement(world, 'geom', name=f'wall_end_{side}_{end}', type='box', pos=f'{end*(LENGTH/2+.025)} {side*(GOAL/2+half)} .035', size=f'.025 {half} .035', rgba='.2 .25 .3 1', friction='0 0 0', solref='.0075 .1', solimp='.99 .999 .001')
    # Four public calibration markers outside the puck lane, plus a center line.
    for i, (x, y) in enumerate([(-.9, -.46), (-.9, .46), (.9, -.46), (.9, .46)]):
        ET.SubElement(world, 'geom', type='cylinder', pos=f'{x} {y} .001', size='.015 .001', rgba='1 .75 .03 1', contype='0', conaffinity='0')
    ET.SubElement(world, 'geom', type='box', pos='0 0 .001', size='.002 .5 .001', rgba='.7 .72 .75 1', contype='0', conaffinity='0')
    base = ET.SubElement(world, 'body', name='puck_base')
    for name, kind, axis, damping in [('puck_x', 'slide', '1 0 0', PUCK_DAMPING), ('puck_y', 'slide', '0 1 0', PUCK_DAMPING), ('puck_yaw', 'hinge', '0 0 1', '0.000002')]:
        ET.SubElement(base, 'joint', name=name, type=kind, axis=axis, damping=damping, limited='false')
    ET.SubElement(base, 'inertial', pos='0 0 0', mass='.01', diaginertia='0.0000025 0.0000025 0.000005')
    ET.SubElement(base, 'geom', name='puck', type='cylinder', pos='0 0 .012', size=f'{PUCK_R} .01', rgba='.95 .03 .04 1', friction='0 0 0', condim='4', solref='.0075 .1')
    for seat, pos, axes in [('A', '0 -1.3 2.2', '1 0 0 0 .861 .509'), ('B', '0 1.3 2.2', '-1 0 0 0 -.861 .509')]:
        ET.SubElement(world, 'camera', name=f'front_{seat}', pos=pos, xyaxes=axes, fovy='48')
    ET.SubElement(world, 'camera', name='overview', pos='0 -2.3 2.5', xyaxes='1 0 0 0 .736 .677', fovy='55')
    # Merge upstream robot defaults/world/actuators without any external assets.
    for i in (1, 2):
        robot = ET.parse(SCENE/f'iiwa{i}.xml').getroot()
        for child in robot:
            if child.tag == 'compiler': continue
            if child.tag == 'worldbody':
                for body in child: world.append(body)
            elif child.tag == 'default':
                if i == 1: root.append(child)          # iiwa1.xml declares the shared classes (vis, robot)
            elif child.tag == 'actuator':
                acts = root.find('actuator')
                if acts is None: acts = ET.SubElement(root, 'actuator')
                for act in child: acts.append(act)
    return ET.tostring(root, encoding='unicode')


def workspace(seat, xy):
    """The nearest point of the seat's mallet workspace (own half, X_NEAR <= |x| <= X_FAR, |y| <= Y_MAX, at most
    REACH from its robot's base) to a point (approximately: box clip, then radial clip towards the base)."""
    u, v = OWN[seat]*float(xy[0]), float(xy[1])
    u, v = min(max(u, X_NEAR), X_FAR), min(max(v, -Y_MAX), Y_MAX)
    d = math.hypot(BASE_X-u, v)
    if d > REACH:
        u, v = BASE_X-(BASE_X-u)*REACH/d, v*REACH/d
    return [OWN[seat]*u, v]


def reachable(seat, p):
    """Whether the seat's mallet can touch a puck centred at p (a mallet centre in the workspace within CONTACT)."""
    q = workspace(seat, p)
    return math.hypot(float(p[0])-q[0], float(p[1])-q[1]) <= CONTACT-.005


def in_workspace(seat, xy, eps=1e-4):
    u, v = OWN[seat]*float(xy[0]), float(xy[1])
    return X_NEAR-eps <= u <= X_FAR+eps and abs(v) <= Y_MAX+eps and math.hypot(BASE_X-u, v) <= REACH+eps


def validate_action(body, seat):
    """None for `none`; else the target [x, y]. Non-finite, wrong half or outside the workspace -> ValueError (400)."""
    if body.get('type') == 'none': return None
    if body.get('type', 'target') != 'target': raise ValueError('action type must be target or none')
    values = [body.get('x'), body.get('y')]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values): raise ValueError('x,y must be finite numbers')
    if seat not in ('A', 'B'): raise ValueError('unknown seat')
    if OWN[seat]*values[0] <= 0: raise ValueError('mallet must stay in own half')
    if not in_workspace(seat, values):
        raise ValueError(f'target outside the mallet workspace ({X_NEAR} <= |x| <= {X_FAR}, |y| <= {Y_MAX}, '
                         f'at most {REACH} m from the robot base at ({OWN[seat]*BASE_X:+.2f}, 0))')
    return [float(v) for v in values]


class Hockey:
    def __init__(self, seed=101, level=1, duel=False, first='A'):
        if level not in (1, 2, 3, 4) or first not in ('A', 'B'): raise ValueError('invalid configuration')
        self.seed, self.level, self.duel, self.first = seed, level, duel, first
        self.source_sha = source_sha(); self.model = mujoco.MjModel.from_xml_string(scene_xml())
        self.data = mujoco.MjData(self.model); self.ik = mujoco.MjData(self.model)
        self.rng = np.random.default_rng(seed)
        self.k = 0                  # control steps of play (the world's clock; frozen time does not count)
        self.point_k = 0            # control steps since the current point started
        self.results = []           # one entry per rally: how it ended (goal, foul, dead puck, time cap)
        self.done = self.awaiting_review = False
        self.decided_by = None      # 'score' | 'cap_points' | 'cap_last_goal' | 'cap_territory' | 'cap_first_possession'
        self.rail_contact_steps = self.contact_steps = 0
        self.half_steps = {'A': 0, 'B': 0}      # steps the puck spent wholly in each half (the cap's territory measure)
        self.ids = {}; self.qadr = {}; self.dadr = {}; self.acts = {}; self.targets = {}
        for s, n in [('A', 1), ('B', 2)]:
            names = [f'iiwa_{n}/joint_{j}' for j in range(1, 8)]+[f'iiwa_{n}/striker_joint_{j}' for j in (1, 2)]
            self.ids[s] = [self.model.joint(name).id for name in names]
            self.qadr[s] = self.model.jnt_qposadr[self.ids[s]]; self.dadr[s] = self.model.jnt_dofadr[self.ids[s]]
            self.acts[s] = [self.model.actuator(name).id for name in names]
        self.ee = {'A': self.model.geom('iiwa_1/ee').id, 'B': self.model.geom('iiwa_2/ee').id}
        self.mallet_body = {'A': self.model.body('iiwa_1/striker_mallet').id, 'B': self.model.body('iiwa_2/striker_mallet').id}
        self.puck_geom = self.model.geom('puck').id
        self.wall_geoms = {i for i in range(self.model.ngeom) if (self.model.geom(i).name or '').startswith('wall_')}
        self.px = int(self.model.jnt_qposadr[self.model.joint('puck_x').id]); self.py = self.px+1
        self.pvx = int(self.model.jnt_dofadr[self.model.joint('puck_x').id])
        mujoco.mj_resetData(self.model, self.data)
        self.restart(self.first, 'start')

    # ---------------------------------------------------------------- state
    def position(self, seat): return self.data.geom_xpos[self.ee[seat]].copy()

    def puck(self): return np.array([self.data.qpos[self.px], self.data.qpos[self.py]])

    def puck_velocity(self): return np.array([self.data.qvel[self.pvx], self.data.qvel[self.pvx+1]])

    def restart(self, holder, why):
        """Play stops: both mallets go back to their home positions (instantly) and the referee places the puck at
        rest, at the holder's spot in its own half (seeded y), or at the table centre for a face-off (holder None)."""
        puck = [0., 0.] if holder is None else [OWN[holder]*SPOT_X, round(float(self.rng.uniform(-.18, .18)), 6)]
        self.data.qvel[:] = 0
        for s in ('A', 'B'):
            self.data.qpos[self.qadr[s]] = np.array([0, -.1961, 0, -1.8436, 0, .9704, 0, 0, 0.])
        self.data.qpos[self.px], self.data.qpos[self.py], self.data.qpos[self.py+1] = puck[0], puck[1], 0.
        mujoco.mj_forward(self.model, self.data)
        for s in ('A', 'B'):
            self.targets[s] = np.array([OWN[s]*HOME_X, 0.])
            self.data.qpos[self.qadr[s]] = self.solve(s, self.data.qpos[self.qadr[s]].copy(), self.targets[s], 80)
        self.data.ctrl[:] = 0
        self.commands = {s: list(self.targets[s]) for s in ('A', 'B')}
        self.qtarget = {s: self.data.qpos[self.qadr[s]].copy() for s in ('A', 'B')}
        self.cart_velocity = {s: np.zeros(2) for s in ('A', 'B')}
        self.side, self.side_steps = holder, 0            # possession: the half the puck is wholly in
        self.line_steps = self.dead_steps = 0
        self.last_touch = None
        self.script = dict(until=-1, target=None, hist=[])
        self.restart_k, self.restart_why = self.k, why
        mujoco.mj_forward(self.model, self.data)

    def solve(self, seat, q, target, iterations):
        adr = self.qadr[seat]; dof = self.dadr[seat]
        desired = np.diag([-1., 1., -1.]) if seat == 'A' else np.diag([1., -1., -1.])
        body = self.mallet_body[seat]
        jp = np.zeros((3, self.model.nv)); jr = np.zeros_like(jp)
        self.ik.qpos[:] = self.data.qpos
        ranges = self.model.jnt_range[self.ids[seat]]
        for _ in range(iterations):
            self.ik.qpos[adr] = q; mujoco.mj_kinematics(self.model, self.ik); mujoco.mj_comPos(self.model, self.ik)
            current = self.ik.xmat[body].reshape(3, 3)
            err = np.r_[np.array([target[0], target[1], .0645])-self.ik.xpos[body],
                        sum(np.cross(current[:, i], desired[:, i]) for i in range(3))*.5]
            mujoco.mj_jacBody(self.model, self.ik, jp, jr, body)
            jac = np.vstack([jp[:, dof], jr[:, dof]])
            delta = jac.T@np.linalg.solve(jac@jac.T+.001*np.eye(6), err)
            q = q+np.clip(delta, -.08, .08)
            q = np.clip(q, ranges[:, 0]+.01, ranges[:, 1]-.01)
        return q

    def set_command(self, seat, command):
        if command is None: self.commands[seat] = workspace(seat, self.position(seat)[:2]); return
        if OWN[seat]*command[0] <= 0: raise ValueError('mallet must stay in own half')
        self.commands[seat] = list(command)

    # ---------------------------------------------------------------- scripted opponent (single player, seat B)
    def scripted(self, seat='B'):
        """Trusted referee-side opponent, from the true puck position `delay` steps ago: guards its goal while the
        puck is in the other half or coming at it fast, else lines up behind the puck and strikes it at the other
        goal. Levels differ in mallet speed, reaction delay, how far the guard follows the puck, how precisely it lines
        up and where it aims (LEVELS)."""
        lv = LEVELS[self.level]; sg = OWN[seat]; sc = self.script
        sc['hist'].append(self.puck()); sc['hist'] = sc['hist'][-(lv['delay']+2):]
        P = sc['hist'][0]; W = (sc['hist'][1]-sc['hist'][0])/DT if len(sc['hist']) > 1 else np.zeros(2)
        p = np.array([sg*P[0], P[1]]); w = np.array([sg*W[0], W[1]])          # local: u > 0 is the own half
        m = self.position(seat)[:2]; m = np.array([sg*m[0], m[1]])
        p = p+w*lv['delay']*DT                                                  # now, by its own extrapolation
        world = lambda u, v: workspace(seat, [sg*u, v])
        if p[0] < -.02 or w[0] > .15:           # guard: at its guard line, following the puck's y (or its crossing)
            sc['until'] = -1
            if lv['guard'] is None:             # level 1 does not guard: it stays where it is
                return world(*m)
            y = p[1]
            if lv['lead'] and w[0] > .1:
                y = p[1]+w[1]*(lv['guard']-p[0])/w[0]
                r = WIDTH/2-PUCK_R; y = (y+r) % (4*r); y = (y if y < 2*r else 4*r-y)-r   # rail bounces folded in
            return world(lv['guard'], float(np.clip(y*lv['gain'], -.42, .42)))
        if self.k < sc['until']: return sc['target']
        aim = 0. if not lv['aim'] else (lv['aim'] if p[1] < 0 else -lv['aim'])  # the far corner of the goal
        d = np.array([-1.05, aim])-p; d /= np.linalg.norm(d)
        rel = p-m; dist = np.linalg.norm(rel)
        if .12 < dist < .3 and float(rel@d)/dist > math.cos(lv['tol']):         # lined up: strike through the puck
            sc['target'] = world(*(m+rel/dist*(dist+.25))); sc['until'] = self.k+40
            return sc['target']
        return world(*(p-d*.18))

    # ---------------------------------------------------------------- one control step
    def step(self):
        if self.done or self.awaiting_review: raise RuntimeError('world frozen')
        if not self.duel: self.set_command('B', self.scripted('B'))
        qvelocity = {}; qprevious = {}
        for s in ('A', 'B'):
            previous_q = self.qtarget[s].copy(); qprevious[s] = previous_q
            target = np.array(self.commands[s]); delta = target-self.targets[s]
            vmax = MAX_SPEED if s == 'A' or self.duel else LEVELS[self.level]['speed']
            accel = 80*delta-18*self.cart_velocity[s]
            accel *= min(1., MAX_ACCEL/max(1e-9, np.linalg.norm(accel)))
            self.cart_velocity[s] += accel*DT
            self.cart_velocity[s] *= min(1., vmax/max(1e-9, np.linalg.norm(self.cart_velocity[s])))
            self.targets[s] += self.cart_velocity[s]*DT
            self.qtarget[s] = self.solve(s, self.qtarget[s], self.targets[s], 4)
            qvelocity[s] = np.clip((self.qtarget[s]-previous_q)/DT, -3., 3.)
        contact = set()
        mass = np.zeros((self.model.nv, self.model.nv))
        for substep in range(SUBSTEPS):
            mujoco.mj_forward(self.model, self.data)
            mujoco.mj_fullM(self.model, mass, self.data.qM)
            for s in ('A', 'B'):
                q = self.data.qpos[self.qadr[s]]; v = self.data.qvel[self.dadr[s]]
                reference = qprevious[s]+(self.qtarget[s]-qprevious[s])*(substep+1)/SUBSTEPS
                acceleration = np.clip(100*(reference-q)+20*(qvelocity[s]-v), -50, 50)
                torque = mass[np.ix_(self.dadr[s], self.dadr[s])]@acceleration+self.data.qfrc_bias[self.dadr[s]]
                bounds = self.model.actuator_ctrlrange[self.acts[s]]
                self.data.ctrl[self.acts[s]] = np.clip(torque, bounds[:, 0], bounds[:, 1])
            mujoco.mj_step(self.model, self.data)
            for i in range(self.data.ncon):
                c = self.data.contact[i]; g = (int(c.geom1), int(c.geom2))
                if self.puck_geom in g:
                    for s in ('A', 'B'):
                        if self.ee[s] in g: contact.add(s)
                    if g[0] in self.wall_geoms or g[1] in self.wall_geoms: contact.add('wall')
        self.k += 1; self.point_k += 1
        for s in ('A', 'B'):
            if s in contact: self.last_touch = s
        if contact & {'A', 'B'}: self.contact_steps += 1
        if 'wall' in contact: self.rail_contact_steps += 1
        self.referee()
        return contact

    def referee(self):
        """After each control step: a goal, a seven-second foul or a dead puck ends the rally; the world then freezes
        for the review and the next rally starts from the placement the rules give (ready())."""
        p = self.puck()
        if abs(p[0]) > LENGTH/2+PUCK_R and abs(p[1]) <= GOAL/2-PUCK_R:          # wholly in a goal (USAA I.2, V.1)
            scorer = 'A' if p[0] > 0 else 'B'
            return self.end_rally('goal', winner=scorer, next=OTHER[scorer],    # the scored-upon serves (I.4)
                                  own_goal=self.last_touch == OTHER[scorer])
        side = 'A' if p[0] < -PUCK_R else ('B' if p[0] > PUCK_R else None)   # on the centre line: nobody's (I.11)
        if side:
            self.half_steps[side] += 1
            self.line_steps = 0
            if side != self.side: self.side, self.side_steps = side, 0
            self.side_steps += 1
        else:
            self.line_steps += 1
        self.dead_steps = 0 if (reachable('A', p) or reachable('B', p)) else self.dead_steps+1
        if self.dead_steps*DT >= DEAD_S-1e-9:
            return self.end_rally('dead_puck', where='out_of_reach', next=None)
        if self.line_steps*DT >= LINE_S-1e-9:
            return self.end_rally('dead_puck', where='centre_line', next=None)
        if side and self.side_steps*DT >= SEVEN_S-1e-9:                  # a foul: forfeiture of the puck (VI.1)
            return self.end_rally('seven_second_foul', guilty=side, next=OTHER[side])
        if self.k*DT >= CAP_S-1e-9:
            return self.end_rally('time_cap', next=None)

    def end_rally(self, how, winner=None, guilty=None, next=None, **extra):
        self.results.append(dict(rally=len(self.results)+1, how=how, winner=winner, guilty=guilty,
                                 next='faceoff' if next is None else next, k=self.k, steps=self.point_k, **extra))
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
        return 'cap_first_possession'

    def ready(self):
        if not self.awaiting_review: raise ValueError('not in review')
        self.awaiting_review = False; self.point_k = 0
        nxt = self.results[-1]['next']
        self.restart(None if nxt == 'faceoff' else nxt, self.results[-1]['how'])

    # ---------------------------------------------------------------- result
    def scores(self):
        return {s: dict(points=sum(r['how'] == 'goal' and r['winner'] == s for r in self.results),
                        fouls=sum(r['guilty'] == s for r in self.results)) for s in ('A', 'B')}

    def winner(self):
        """'A' or 'B' once the game is over (never a draw), else None."""
        if not self.done: return None
        sc = self.scores(); a, b = sc['A']['points'], sc['B']['points']
        if a != b: return 'A' if a > b else 'B'
        goals = [r for r in self.results if r['how'] == 'goal']
        if goals: return goals[-1]['winner']                                    # the winner of the last point
        if self.half_steps['A'] != self.half_steps['B']:                        # 0:0: less time with the puck in
            return 'A' if self.half_steps['A'] < self.half_steps['B'] else 'B'  # one's own half (more pressure)
        return OTHER[self.first]                    # identical: the player who did not have the first possession

    def digest(self):
        state = np.empty(mujoco.mj_stateSize(self.model, mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(self.model, self.data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
        h = hashlib.sha256(state.tobytes())
        h.update(json.dumps(dict(k=self.k, point_k=self.point_k, results=self.results,
                                 commands=self.commands, targets={s: t.tolist() for s, t in self.targets.items()},
                                 cart_velocity={s: t.tolist() for s, t in self.cart_velocity.items()},
                                 qtarget={s: q.tolist() for s, q in self.qtarget.items()}, side=self.side,
                                 side_steps=self.side_steps, line_steps=self.line_steps, dead_steps=self.dead_steps,
                                 half_steps=self.half_steps, last_touch=self.last_touch, rng=self.rng.bit_generator.state,
                                 script=dict(until=self.script['until'], target=self.script['target'],
                                             hist=[x.tolist() for x in self.script['hist']]),
                                 contacts=self.contact_steps, rails=self.rail_contact_steps, done=self.done,
                                 decided_by=self.decided_by, awaiting_review=self.awaiting_review), sort_keys=True).encode())
        return h.hexdigest()
