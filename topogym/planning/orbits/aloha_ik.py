"""ALOHA IK and collision audit for the Orbits rope oracle (MuJoCo kinematics, no dynamics).

The MJCF is the same tabletop ALOHA asset Genesis loads (topogym.assets.robot.build_tabletop_aloha).
Its frame origin is the robot mount centre (world (-0.1357, 0, table)); the Task places the base centre
SHIFT further along world +y. Task-local points map to MJCF coordinates by a +90 deg yaw plus that
shift: (x, y, z) -> (-y, x + SHIFT, z); directions map without the shift. The TCP is the source MJCF
'<side>/gripper' site (0.13, 0, -0.003 in gripper_link), identical to Genesis tcp_position_in_hand_m.
Fixture primitives are added as collision geoms; the grasped cord itself is not modelled.
"""
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from topogym.utils.grasp import TASK_CONTACT_PENETRATION_M


ARM = ['waist', 'shoulder', 'elbow', 'forearm_roll', 'wrist_angle', 'wrist_rotate']
LIMITS = np.array([[-3.14158, 3.14158], [-1.85005, 1.25664], [-1.76278, 1.6057],
                   [-3.14158, 3.14158], [-1.8675, 2.23402], [-3.14158, 3.14158]])
HOME = [0, -0.96, 1.16, 0, -0.3, 0]


SHIFT = 0.   # set by AlohaIK from the Task's base placement


def to_mj(p):
    p = np.asarray(p, float)
    return np.stack([-p[..., 1], p[..., 0]+SHIFT, p[..., 2]], -1)


def dir_to_mj(d):
    d = np.asarray(d, float)
    return np.stack([-d[..., 1], d[..., 0], d[..., 2]], -1)


def from_mj(p):
    p = np.asarray(p, float)
    return np.stack([p[..., 1]-SHIFT, -p[..., 0], p[..., 2]], -1)


def v(x):
    return ' '.join(f'{a:.9g}' for a in np.asarray(x, float).ravel())


TOUCH = TASK_CONTACT_PENETRATION_M
FINGER_SURFACE = TASK_CONTACT_PENETRATION_M


class AlohaIK:
    def __init__(self, lay, ring_segments=48, shift=None):
        global SHIFT
        from topogym.assets.robot import build_tabletop_aloha
        if shift is None:
            from .rope_sim import placement_shift, RING_COUNT
            shift = placement_shift({n: v_ for v_, n in RING_COUNT.items()}[lay.ring_count])
        SHIFT = float(shift)
        path = build_tabletop_aloha()
        root = ET.parse(path).getroot()
        world = root.find('worldbody')
        fx = dict(contype='2', conaffinity='2', group='3', rgba='.5 .3 .1 1')
        l = lay
        base = ET.SubElement(world, 'geom', name='fx_base', type='box', pos=v(to_mj([0, 0, l.base_height_m/2])),
                             size=v([l.base_width_m/2, l.base_length_m/2, l.base_height_m/2]), **fx)
        tops = [l.ball_z, *l.ring_z]
        for i, (x, z) in enumerate(zip(l.post_x, tops)):
            ET.SubElement(world, 'geom', name=f'fx_post{i}', type='cylinder',
                          fromto=v([*to_mj([x, 0, l.base_height_m]), *to_mj([x, 0, z])]), size=str(l.post_radius_m), **fx)
        ET.SubElement(world, 'geom', name='fx_ball', type='sphere', pos=v(to_mj([l.post_x[0], 0, l.ball_z])),
                      size=str(l.ball_radius_m), **fx)
        for k, (x, z) in enumerate(zip(l.ring_x, l.ring_z)):
            th = np.arange(ring_segments+1)*2*np.pi/ring_segments
            c = np.column_stack([x+l.ring_radius_m*np.cos(th), l.ring_radius_m*np.sin(th), np.full(len(th), z)])
            c = to_mj(c)
            for j in range(ring_segments):
                ET.SubElement(world, 'geom', name=f'fx_ring{k+1}_{j}', type='capsule', fromto=v([c[j], c[j+1]]),
                              size=str(l.ring_tube_radius_m), **fx)
        ET.SubElement(world, 'geom', name='fx_table', type='plane', pos='0 0 -0.0005', size='2 2 .01', **fx)
        # make every robot collision geom collide with the fixture bit
        for g in root.iter('geom'):
            if g.get('name', '').startswith('fx_'):
                continue
            ct = int(g.get('contype', '1')); ca = int(g.get('conaffinity', '1'))
        self.xml = ET.tostring(root, encoding='unicode')
        self.model = m = mujoco.MjModel.from_xml_string(self.xml)
        self.data = mujoco.MjData(m)
        self.fixture_geoms = set(i for i in range(m.ngeom) if (m.geom(i).name or '').startswith('fx_'))
        self.table_geom = m.geom('fx_table').id
        # robot collision geoms: anything with nonzero contype or conaffinity, excluding fixture
        self.robot_geoms = [i for i in range(m.ngeom) if i not in self.fixture_geoms and
                            (m.geom_contype[i] or m.geom_conaffinity[i])]
        for i in self.robot_geoms:        # ensure robot geoms see fixture geoms (bit 2)
            m.geom_conaffinity[i] |= 2
            m.geom_contype[i] |= 2 if m.geom_contype[i] else 0
            b = m.geom_bodyid[i]          # body-level bits drive the broad phase
            m.body_conaffinity[b] |= 2
            m.body_contype[b] |= 2
        self.qadr = {s: [int(m.joint(f'{s}/{n}').qposadr[0]) for n in ARM] for s in ('left', 'right')}
        self.site = {s: m.site(f'{s}/gripper').id for s in ('left', 'right')}
        self.dofadr = {s: [int(m.joint(f'{s}/{n}').dofadr[0]) for n in ARM] for s in ('left', 'right')}
        self.q = np.zeros(m.nq)
        for s in ('left', 'right'):
            self.q[self.qadr[s]] = HOME
            for f, val in (('left_finger', .0084), ('right_finger', .0084)):
                self.q[int(m.joint(f'{s}/{f}').qposadr[0])] = val
        self.home = self.q.copy()

    def fk(self, q):
        self.data.qpos[:] = q
        mujoco.mj_kinematics(self.model, self.data)

    def tcp(self, side):
        i = self.site[side]
        return self.data.site_xpos[i].copy(), self.data.site_xmat[i].reshape(3, 3).copy()

    PAD = .012   # the finger pads that pinch the cord sit this far beyond the TCP site along the approach

    def solve(self, side, p_local, R_mj, seed):
        """Grasp point (cord) in task-local coordinates, orientation as MJCF rotation matrix.

        The TCP site target is placed PAD before the cord along the approach axis (gripper_link x),
        so the fingertip pads, not the site, close on the cord. Damped least squares on MuJoCo's
        analytic site Jacobian; when it ends close but not converged (joint limits), the bounded
        least-squares solve finishes from there."""
        q, e_p, e_r = self._dls(side, p_local, R_mj, seed)
        if (e_p > 2e-3 or e_r > 3e-2) and e_p < .03 and e_r < .3:
            q2, e2_p, e2_r = self._lsq(side, p_local, R_mj, q)
            if e2_p+e2_r < e_p+e_r:
                return q2, e2_p, e2_r
        return q, e_p, e_r

    def _dls(self, side, p_local, R_mj, seed, iters=80):
        m, d = self.model, self.data
        target = to_mj(p_local)-self.PAD*R_mj[:, 0]
        q = seed.copy()
        idx, dof, site = self.qadr[side], self.dofadr[side], self.site[side]
        lo, hi = LIMITS[:, 0]+1e-6, LIMITS[:, 1]-1e-6
        a = np.clip(q[idx], lo, hi)
        tq, cq, nq, dq4, rv = np.zeros(4), np.zeros(4), np.zeros(4), np.zeros(4), np.zeros(3)
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        mujoco.mju_mat2Quat(tq, np.ascontiguousarray(R_mj).ravel())
        for it in range(iters+1):
            q[idx] = a
            d.qpos[:] = q
            mujoco.mj_kinematics(m, d)
            mujoco.mj_comPos(m, d)
            ep = target-d.site_xpos[site]
            mujoco.mju_mat2Quat(cq, d.site_xmat[site])
            mujoco.mju_negQuat(nq, cq)
            mujoco.mju_mulQuat(dq4, tq, nq)
            if dq4[0] < 0:
                dq4 *= -1
            mujoco.mju_quat2Vel(rv, dq4, 1.)
            n_p, n_r = float(np.linalg.norm(ep)), float(np.linalg.norm(rv))
            if (n_p < 2e-5 and n_r < 2e-4) or it == iters:
                break
            mujoco.mj_jacSite(m, d, jp, jr, site)
            J = np.vstack([20*jp[:, dof], jr[:, dof]])
            e = np.concatenate([20*ep, rv])
            step = J.T@np.linalg.solve(J@J.T+.01*np.eye(6), e)
            sn = np.abs(step).max()
            if sn > .3:
                step *= .3/sn
            a = np.clip(a+step, lo, hi)
        return q, n_p, n_r

    def _lsq(self, side, p_local, R_mj, seed):
        target = to_mj(p_local)-self.PAD*R_mj[:, 0]
        q = seed.copy()
        idx = self.qadr[side]

        def res(a):
            q[idx] = a
            self.fk(q)
            p, R = self.tcp(side)
            e = [20*(p-target)]
            if R_mj is not None:
                e.append(Rotation.from_matrix(R_mj@R.T).as_rotvec())
            return np.concatenate(e)
        r = least_squares(res, q[idx], bounds=(LIMITS[:, 0]+1e-6, LIMITS[:, 1]-1e-6), max_nfev=200,
                          ftol=1e-12, xtol=1e-12, gtol=1e-12)
        e = res(r.x)
        q[idx] = r.x
        return q, float(np.linalg.norm(e[:3])/20), float(np.linalg.norm(e[3:])) if R_mj is not None else 0.

    def collisions(self, q, sides=('left', 'right'), margin=.0):
        self.data.qpos[:] = q
        mujoco.mj_forward(self.model, self.data)
        m, d = self.model, self.data
        bad = []
        for c in d.contact[:d.ncon]:
            g1, g2 = int(c.geom1), int(c.geom2)
            f1, f2 = g1 in self.fixture_geoms, g2 in self.fixture_geoms
            if f1 and f2:
                continue
            if c.dist > -margin:
                continue
            b1 = m.body(m.geom_bodyid[g1]).name; b2 = m.body(m.geom_bodyid[g2]).name
            if (f1 or f2):
                rb = b2 if f1 else b1
                fg = m.geom(g1 if f1 else g2).name
                if fg == 'fx_table' and ('base_link' in rb or 'shoulder' in rb):
                    continue
                # grasping a cord lying on the base/table: fingertips may press on those surfaces
                if fg in ('fx_base', 'fx_table') and 'finger' in rb and -c.dist <= FINGER_SURFACE:
                    continue
                # the collision shapes are conservative: a light touch on the fixture is contact, not a clash
                if -c.dist <= TOUCH:
                    continue
                if not any(rb.startswith(s) for s in sides):
                    continue
                bad.append(dict(kind='robot_fixture', robot=rb, fixture=fg, depth=round(float(-c.dist), 5)))
            else:
                if b1.split('/')[0] != b2.split('/')[0]:
                    bad.append(dict(kind='arm_arm', a=b1, b=b2, depth=round(float(-c.dist), 5)))
        return bad

    def clearance(self, q):
        """Minimum signed distance robot<->fixture (MuJoCo narrow phase, 5 cm search)."""
        self.data.qpos[:] = q
        mujoco.mj_forward(self.model, self.data)
        m, d = self.model, self.data
        best = np.inf
        fromto = np.zeros(6)
        for g in self.robot_geoms:
            for f in self.fixture_geoms:
                if f == self.table_geom:
                    continue
                dist = mujoco.mj_geomDistance(m, d, g, f, .05, fromto)
                best = min(best, dist)
        return best


def approach_rotation(side, approach_local, roll_deg=0.):
    """MJCF rotation whose gripper_link x-axis (approach) points along approach_local (task-local)."""
    ax = dir_to_mj(np.asarray(approach_local, float)); ax /= np.linalg.norm(ax)
    up = np.array([0, 0, 1.]) if abs(ax[2]) < .95 else np.array([0, 1., 0])
    y = np.cross(up, ax); y /= np.linalg.norm(y)
    z = np.cross(ax, y)
    R = np.column_stack([ax, y, z])
    return R@Rotation.from_euler('x', roll_deg, degrees=True).as_matrix()
