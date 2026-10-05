"""Rope-only Orbits oracle in MuJoCo using the local task layout and cord profile.

Local (unrotated) task frame: x along the fixture (ball post at -x, handle at +x), z up,
table top z=0. The oracle is a planning witness, not the Genesis FEM/IPC task physics.
"""
import os
import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, replace
from functools import cached_property
from pathlib import Path

import mujoco
import numpy as np

from topogym.assets.geometry.orbits import OrbitsLayout  # noqa: E402
from topogym.assets.geometry.orbits_initial import natural_working_state, resample  # noqa: E402
from .local_contract import (MAX_PENETRATION_M, MAX_GRIP_ERROR_M, MAX_SEGMENT_STRETCH,
                             MAX_TOTAL_STRETCH, planning_goal, task_for)

RING_COUNT = dict(easy=2, medium=3, hard=4)
# Keep the source route scale names, but never let inherited environment variables
# silently replace the local v15 geometry with the source's experiments.
SCALE = float(task_for('easy').config['linear_scale'])
KS = SCALE/.85


FROM_TASK = True
if ('ORBITS_SCALE' in os.environ and float(os.environ['ORBITS_SCALE']) != SCALE) or \
        os.environ.get('ORBITS_FROM_TASK', '1') != '1':
    raise ValueError('The local Orbits oracle uses the installed task geometry; scale overrides are disabled')


def _task_params(variant):
    from topogym.tasks.orbits.common import CORD_PROFILES
    d = task_for(variant).config
    return OrbitsLayout(**d['geometry']).scaled(d['linear_scale']), CORD_PROFILES[d['cord_profile']]


def placement_shift(variant):
    """World +y offset of the Task's base centre from the robot mount centre (= task-local +x in the
    robot frame); the Task shifts longer fixtures so its placement goal fits on the table."""
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    scene = load_scene_config(SimulatorConfig(task_id='orbits', variation_id=variant, enable_rgb=False,
                                             compute_backend='cpu'))
    return float(task_for(variant).config['base_center_xy_m'][1] - scene.env.robot_mount.pos[1])


def _layout(variant):
    return _task_params(variant)[0]


def _handle_x(variant):
    from topogym.tasks.orbits.common import profile_value
    return profile_value(_task_params(variant)[1], 'handle_x_m', RING_COUNT[variant])


def layout_for(variant):
    return replace(_layout(variant), handle_x_m=_handle_x(variant))


def initial_cord(variant, spacing=.005, length=None):
    from topogym.tasks.orbits.common import profile_cord_length
    task_length = profile_cord_length(_task_params(variant)[1], RING_COUNT[variant])
    if length is not None and not np.isclose(length, task_length, rtol=0, atol=1e-12):
        raise ValueError('Cord length must match the local task profile')
    length = task_length
    lay = _layout(variant)
    cord, _ = natural_working_state(lay, handle_x_m=_handle_x(variant), cord_length_m=length, spacing=.002)
    cord = resample(resample(cord, spacing=.001), spacing=spacing)
    return cord


def v(x):
    return " ".join(f"{a:.9g}" for a in np.asarray(x, float).ravel())


def build(variant, *, spacing=.005, length=None, dt=.0005, ring_segments=64, friction=.3):
    lay = layout_for(variant)
    pts = initial_cord(variant, spacing, length)
    n = len(pts)
    root = ET.Element('mujoco', model=f'orbits_rope_oracle_{variant}')
    ET.SubElement(root, 'compiler', angle='radian', autolimits='true')
    ET.SubElement(root, 'option', timestep=str(dt), gravity='0 0 -9.81', integrator='implicitfast',
                  solver='Newton', iterations='60', tolerance='1e-9', jacobian='sparse')
    ET.SubElement(root, 'size', memory='200M')
    d = ET.SubElement(root, 'default')
    ET.SubElement(d, 'geom', friction=f'{friction} .001 .00001', solref='.001 1', solimp='.95 .99 .0005',
                  condim='3', contype='3', conaffinity='3')
    world = ET.SubElement(root, 'worldbody')
    ET.SubElement(world, 'geom', name='table', type='plane', size='1.5 1.5 .01', rgba='.8 .8 .8 1')
    wood = dict(rgba='.5 .3 .15 1')
    ET.SubElement(world, 'geom', name='base', type='box', pos=v([0, 0, lay.base_height_m/2]),
                  size=v([lay.base_length_m/2, lay.base_width_m/2, lay.base_height_m/2]), **wood)
    tops = [lay.ball_z, *lay.ring_z]
    for i, (x, z) in enumerate(zip(lay.post_x, tops)):
        ET.SubElement(world, 'geom', name=f'post_{i}', type='cylinder',
                      fromto=v([x, 0, lay.base_height_m, x, 0, z]), size=str(lay.post_radius_m), **wood)
    ET.SubElement(world, 'geom', name='ball', type='sphere', pos=v([lay.post_x[0], 0, lay.ball_z]),
                  size=str(lay.ball_radius_m), **wood)
    for k, (x, z) in enumerate(zip(lay.ring_x, lay.ring_z)):
        th = np.arange(ring_segments+1)*2*np.pi/ring_segments
        c = np.column_stack([x+lay.ring_radius_m*np.cos(th), lay.ring_radius_m*np.sin(th), np.full(len(th), z)])
        for j in range(ring_segments):
            ET.SubElement(world, 'geom', name=f'ring_{k+1}_{j}', type='capsule', fromto=v([c[j], c[j+1]]),
                          size=str(lay.ring_tube_radius_m), **wood)
    # Free wooden handle: box approximation of the elliptic prism, eyes at the authored holes.
    hc = np.array([lay.handle_x_m, 0., lay.clearance_m+lay.handle_height_m/2])
    handle = ET.SubElement(world, 'body', name='handle', pos=v(hc))
    ET.SubElement(handle, 'freejoint', name='handle_free')
    ET.SubElement(handle, 'geom', name='handle_geom', type='ellipsoid',
                  size=v([lay.handle_length_m/2, lay.handle_width_m/2, lay.handle_height_m/2]),
                  mass='.012', rgba='.6 .4 .2 1', contype='2', conaffinity='2')
    for e, idx in enumerate([0, n-1]):
        ET.SubElement(handle, 'site', name=f'eye_{e}', pos=v(pts[idx]-hc), size='.001')
    ET.SubElement(handle, 'site', name='handle_center', pos='0 0 0', size='.001')
    lin_mass = 650*np.pi*lay.cord_radius_m**2
    for i, p in enumerate(pts):
        b = ET.SubElement(world, 'body', name=f'n{i}', pos=v(p))
        ET.SubElement(b, 'inertial', pos='0 0 0', mass=str(lin_mass*spacing*3), diaginertia='1e-10 1e-10 1e-10')
        for ax in np.eye(3):
            ET.SubElement(b, 'joint', type='slide', axis=v(ax), damping='.0005')
        ET.SubElement(b, 'site', name=f's{i}', size='.001')
    dfm = ET.SubElement(root, 'deformable')
    flex = ET.SubElement(dfm, 'flex', name='cord', dim='1', radius=str(lay.cord_radius_m),
                         body=' '.join(f'n{i}' for i in range(n)),
                         element=' '.join(f'{i} {i+1}' for i in range(n-1)), rgba='.95 .78 .03 1')
    ET.SubElement(flex, 'contact', selfcollide='auto', internal='false', friction=f'{friction} .001 .00001',
                  contype='1', conaffinity='1',
                  solref='.001 1', solimp='.95 .99 .0005', condim='3')
    eq = ET.SubElement(root, 'equality')
    ET.SubElement(eq, 'flex', flex='cord', solref='.002 1', solimp='.95 .99 .0005')
    for e, idx in enumerate([0, n-1]):
        ET.SubElement(eq, 'connect', name=f'terminal_{e}', site1=f'eye_{e}', site2=f's{idx}', solref='.002 1')
    for g in 'ABCD':
        m = ET.SubElement(world, 'body', name=f'grip_{g}', mocap='true', pos='0 0 -1')
        ET.SubElement(m, 'site', name=f'grip_{g}_site', size='.003', rgba='0 .4 1 1')
        ET.SubElement(eq, 'connect', name=f'hold_{g}', site1=f'grip_{g}_site', site2='s0', active='false',
                      solref='.004 1')
        ET.SubElement(m, 'site', name=f'grip_{g}_site2', size='.002')
        ET.SubElement(eq, 'connect', name=f'hold2_{g}', site1=f'grip_{g}_site2', site2='s0', active='false',
                      solref='.004 1')
        ET.SubElement(eq, 'weld', name=f'holdh_{g}', site1=f'grip_{g}_site', site2='handle_center',
                      active='false', solref='.004 1')
    # The handle collides with the table/fixture (bit 2) but not with the cord (bit 1): the cord
    # ends are attached inside its eyes. Cord-handle interpenetration is an explicit simplification.
    ET.indent(root)
    xml = ET.tostring(root, encoding='unicode')
    model = mujoco.MjModel.from_xml_string(xml)
    return model, xml, lay, pts


class Oracle:
    def __init__(self, variant, **kw):
        self.variant = variant
        self.model, self.xml, self.lay, self.initial = build(variant, **kw)
        self.data = mujoco.MjData(self.model)
        self.n = len(self.initial)
        self.sites = np.array([self.model.site(f's{i}').id for i in range(self.n)])
        self.mocap = {g: self.model.body(f'grip_{g}').mocapid[0] for g in 'ABCD'}
        self.eq = {g: self.model.equality(f'hold_{g}').id for g in 'ABCD'}
        self.eqh = {g: self.model.equality(f'holdh_{g}').id for g in 'ABCD'}
        self.eq2 = {g: self.model.equality(f'hold2_{g}').id for g in 'ABCD'}
        self.site2 = {g: self.model.site(f'grip_{g}_site2').id for g in 'ABCD'}
        self.held = dict(A=None, B=None, C=None, D=None)
        self.log = []
        self.frames = []
        self._rest = np.linalg.norm(np.diff(self.initial, axis=0), axis=1)
        mujoco.mj_forward(self.model, self.data)

    @cached_property
    def goal(self):
        return planning_goal(self.variant, self.lay, self.initial)

    def identity(self):
        task = task_for(self.variant)
        return dict(variant=self.variant, layout=asdict(self.lay),
                    model_revision=task.model_revision, task_parameters=task.identity_config(),
                    model_sha256=hashlib.sha256(self.xml.encode()).hexdigest(),
                    limits=dict(penetration_m=MAX_PENETRATION_M, grip_error_m=MAX_GRIP_ERROR_M,
                                segment_stretch=MAX_SEGMENT_STRETCH, total_stretch=MAX_TOTAL_STRETCH),
                    scope='detached MuJoCo planning model; not Genesis FEM/IPC execution',
                    formal_qualification=False)

    # -- state
    def points(self):
        return self.data.site_xpos[self.sites].copy()

    def handle_pose(self):
        b = self.model.body('handle').id
        return self.data.xpos[b].copy(), self.data.xquat[b].copy()

    def grip_pos(self, g):
        return self.data.mocap_pos[self.mocap[g]].copy()

    # -- grasping
    def grasp(self, g, node):
        """node: int material index, or 'handle'."""
        self.release(g)
        if node == 'handle':
            p, q = self.handle_pose()
            self.data.mocap_pos[self.mocap[g]] = p
            self.data.mocap_quat[self.mocap[g]] = q
            self.model.eq_data[self.eqh[g]][:] = 0.
            self.model.eq_data[self.eqh[g]][6:10] = [1, 0, 0, 0]
            self.data.eq_active[self.eqh[g]] = 1
        elif isinstance(node, (tuple, list)):
            n1, n2 = int(node[0]), int(node[1])
            p1, p2 = self.points()[n1], self.points()[n2]
            c = (p1+p2)/2
            self.data.mocap_pos[self.mocap[g]] = c
            self.data.mocap_quat[self.mocap[g]] = [1, 0, 0, 0]
            # second site offset so both nodes are held side by side (pinch of two strands)
            self.model.site_pos[self.model.site(f'grip_{g}_site').id] = p1-c
            self.model.site_pos[self.site2[g]] = p2-c
            self.model.eq_obj2id[self.eq[g]] = self.sites[n1]
            self.model.eq_obj2id[self.eq2[g]] = self.sites[n2]
            self.data.eq_active[self.eq[g]] = 1
            self.data.eq_active[self.eq2[g]] = 1
            node = (n1, n2)
        else:
            node = int(node)
            self.model.site_pos[self.model.site(f'grip_{g}_site').id] = 0
            self.model.eq_obj2id[self.eq[g]] = self.sites[node]
            self.data.mocap_pos[self.mocap[g]] = self.points()[node]
            self.data.eq_active[self.eq[g]] = 1
        self.held[g] = node
        self.log.append(dict(t=float(self.data.time), event='grasp', gripper=g, node=node))

    def release(self, g):
        if self.held[g] is not None:
            self.log.append(dict(t=float(self.data.time), event='release', gripper=g, node=self.held[g]))
        self.data.eq_active[self.eq[g]] = 0
        self.data.eq_active[self.eqh[g]] = 0
        self.data.eq_active[self.eq2[g]] = 0
        self.model.site_pos[self.model.site(f'grip_{g}_site').id] = 0
        self.held[g] = None

    # -- motion
    def move(self, name, targets, seconds, *, record_every=20, guard_pen=MAX_PENETRATION_M,
             guard_err=MAX_GRIP_ERROR_M, guard_stretch=MAX_SEGMENT_STRETCH, guard_total=MAX_TOTAL_STRETCH):
        """targets: {gripper: xyz or list of waypoints}; smooth-step along the polyline."""
        for label, value, limit in (('penetration', guard_pen, MAX_PENETRATION_M),
                                    ('grip error', guard_err, MAX_GRIP_ERROR_M),
                                    ('segment stretch', guard_stretch, MAX_SEGMENT_STRETCH),
                                    ('total stretch', guard_total, MAX_TOTAL_STRETCH)):
            if not np.isfinite(value) or not 0 < value <= limit:
                raise ValueError(f'{label} guard may not exceed the local bound {limit}')
        paths = {}
        for g, t in targets.items():
            t = np.atleast_2d(np.asarray(t, float))
            paths[g] = np.vstack([self.grip_pos(g), t])
        steps = max(1, int(round(seconds/self.model.opt.timestep)))
        maxpen = 0.; maxerr = 0.
        for i in range(steps):
            u = (i+1)/steps
            s = u*u*(3-2*u)
            for g, P in paths.items():
                seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
                L = seg.sum()
                if L < 1e-12:
                    continue
                a = s*L
                k = min(np.searchsorted(np.cumsum(seg), a), len(seg)-1)
                a0 = np.r_[0, np.cumsum(seg)][k]
                f = 0 if seg[k] < 1e-12 else (a-a0)/seg[k]
                self.data.mocap_pos[self.mocap[g]] = P[k]+f*(P[k+1]-P[k])
            mujoco.mj_step(self.model, self.data)
            if i % 10 == 0:
                pen = max([-c.dist for c in self.data.contact[:self.data.ncon]], default=0.)
                maxpen = max(maxpen, pen)
                for g in 'ABCD':
                    if self.held[g] is None or self.held[g] == 'handle':
                        continue
                    hn = self.held[g] if isinstance(self.held[g], tuple) else (self.held[g],)
                    for j, node in enumerate(hn):
                        sid = self.model.site(f'grip_{g}_site').id if j == 0 else self.site2[g]
                        err = np.linalg.norm(self.data.site_xpos[sid]-self.points()[node])
                        maxerr = max(maxerr, err)
                seg = np.linalg.norm(np.diff(self.points(), axis=0), axis=1)
                sratio = float((seg/self._rest).max())
                tratio = float(seg.sum()/self._rest.sum())
                self.max_total = max(getattr(self, 'max_total', 1.), tratio)
                self.max_stretch = max(getattr(self, 'max_stretch', 1.), sratio)
                self.max_pen = max(getattr(self, 'max_pen', 0.), pen)
                if pen > guard_pen or maxerr > guard_err or sratio > guard_stretch or tratio > guard_total:
                    self.log.append(dict(t=float(self.data.time), event='guard', phase=name, pen=pen, err=maxerr,
                                         stretch=sratio))
                    deep = ''
                    if pen > guard_pen:
                        c = min(self.data.contact[:self.data.ncon], key=lambda c_: c_.dist)
                        def nm(g_, k_):
                            if g_ < 0:                       # a flex (cord) element
                                return f'cord[{int(c.elem[k_])}]'
                            return self.model.geom(g_).name or self.model.body(self.model.geom_bodyid[g_]).name or str(g_)
                        deep = f' deepest {nm(c.geom1, 0)}/{nm(c.geom2, 1)} at {np.round(c.pos, 3).tolist()}'
                    raise RuntimeError(f'{name}: guard pen={pen:.4f} err={maxerr:.4f} stretch={sratio:.3f} total={tratio:.4f} '
                                       f't={self.data.time:.2f}{deep}')
            if i % record_every == 0:
                self.record(name)
        self.record(name)
        self.log.append(dict(t=float(self.data.time), event='move', phase=name, maxpen=maxpen, maxerr=maxerr))
        return maxpen, maxerr

    def settle(self, seconds, name='settle', **guards):
        return self.move(name, {}, seconds, **guards)

    def record(self, name):
        p, q = self.handle_pose()
        self.frames.append((float(self.data.time), name, self.points().astype(np.float32),
                            np.r_[p, q].astype(np.float32),
                            np.array([self.grip_pos(g) for g in 'ABCD'], np.float32),
                         np.array([self.held[g] is not None for g in 'ABCD'])))

    def stretch(self):
        p = self.points()
        seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
        rest = np.linalg.norm(np.diff(self.initial, axis=0), axis=1)
        return float(seg.sum()), float((seg/rest).max())

    def save(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        (path/'model.json').write_text(json.dumps(self.identity(), indent=2)+'\n')
        np.savez_compressed(path/'checkpoint.npz', qpos=self.data.qpos, qvel=self.data.qvel,
                            time=self.data.time, mocap_pos=self.data.mocap_pos, mocap_quat=self.data.mocap_quat,
                            eq_active=self.data.eq_active, eq_obj2id=self.model.eq_obj2id,
                            eq_data=self.model.eq_data, site_pos=self.model.site_pos,
                            held=np.array([str(self.held[g]) for g in 'ABCD']))

    def restore(self, path):
        identity = Path(path)/'model.json'
        if not identity.is_file() or json.loads(identity.read_text()) != self.identity():
            raise ValueError('Checkpoint model/limits do not match the local Orbits oracle; start a new run')
        s = np.load(Path(path)/'checkpoint.npz')
        self.data.qpos[:] = s['qpos']; self.data.qvel[:] = s['qvel']; self.data.time = float(s['time'])
        self.data.mocap_pos[:] = s['mocap_pos']; self.data.mocap_quat[:] = s['mocap_quat']
        self.data.eq_active[:] = s['eq_active']; self.model.eq_obj2id[:] = s['eq_obj2id']
        self.model.eq_data[:] = s['eq_data']
        if 'site_pos' in s:
            self.model.site_pos[:] = s['site_pos']
        for g, h in zip('ABCD', s['held']):
            h = str(h)
            if h == 'None':
                self.held[g] = None
            elif h == 'handle':
                self.held[g] = 'handle'
            elif h.startswith('('):
                self.held[g] = tuple(int(x) for x in h.strip('()').split(','))
            else:
                self.held[g] = int(h)
        mujoco.mj_forward(self.model, self.data)
