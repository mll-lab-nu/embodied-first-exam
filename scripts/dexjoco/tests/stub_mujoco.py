"""A stand-in for the part of the mujoco API that scripts/dexjoco/shared/standard/server.py uses (copied next to the
server as mujoco.py by test_standard_server.py): two Panda + Allegro arms as a kinematic toy, and the objects a camera
can sit on. Bodies: world; per arm link0..link7 (joint i on link i), attachment, 16 finger bodies (one joint each);
`link_19`, an object on a free joint; `drawer`, an object on a slide joint; `target`, a mocap body.
Cameras: front (world), handcam_rgb_right / _left (the hand mounts), cam_pos_z (on link_19), drawer_cam (on drawer),
target_cam (on the mocap body), aim_cam (on the world, MuJoCo mode targetbody: aimed at link_19)."""
import types

import numpy as np

ARMS = ("right", "left")
OBJECT_START = np.array([0.123, 0.456, 1.03])   # where link_19 is: must never leave the service


class mjtObj:
    mjOBJ_BODY, mjOBJ_JOINT, mjOBJ_SITE, mjOBJ_CAMERA = 1, 3, 6, 7


class _Named:
    def __init__(self, i, name):
        self.id, self.name = i, name


class Model:
    def __init__(self):
        self.bodies, self.parent, self.joints, self.jnt_body, self.acts, self.sites = ["world"], [0], [], [], [], []
        self.hand_act = {}
        for a in ARMS:
            for i in range(8):
                self._body(f"link{i}_{a}", 0 if i == 0 else len(self.bodies) - 1)
                if i:
                    self._joint(f"joint{i}_{a}")
                    self.acts.append(f"actuator{i}_{a}")
            mount = self._body(f"attachment_{a}", len(self.bodies) - 1)
            self.sites.append(f"attachment_site_{a}")
            self.hand_act[a] = []
            for k in range(16):
                self._body(f"finger{k}_{a}", mount)
                self._joint(f"finger{k}_{a}_joint")
                self.hand_act[a].append(len(self.acts))
                self.acts.append(f"finger{k}_{a}_act")
        self.n_robot = len(self.joints)
        self.obj = self._body("link_19", 0)
        self._joint("link_19_free")
        self.drawer = self._body("drawer", 0)
        self._joint("drawer_slide")
        self.target = self._body("target", 0)
        nb, nj, na = len(self.bodies), len(self.joints), len(self.acts)
        self.body_parentid = np.array(self.parent)
        self.body_jntnum = np.array([self.jnt_body.count(b) for b in range(nb)])
        self.body_jntadr = np.array([self.jnt_body.index(b) if b in self.jnt_body else -1 for b in range(nb)])
        self.body_mocapid = np.array([0 if b == self.target else -1 for b in range(nb)])
        self.jnt_qposadr, self.jnt_dofadr = np.arange(nj), np.arange(nj)
        self.jnt_range = np.tile(np.array([-2.5, 2.5]), (nj, 1))
        self.nq = self.nv = nj + 7
        self.actuator_trnid = np.stack([np.array([self.joints.index(n[:-4] + "_joint") if n.startswith("finger") else
                                                  self.joints.index("joint" + n[len("actuator"):]) for n in self.acts]),
                                        -np.ones(na, int)], axis=1)
        self.actuator_ctrlrange = np.tile(np.array([-0.4, 1.6]), (na, 1))
        self.actuator_forcelimited, self.actuator_forcerange = np.zeros(na, int), np.zeros((na, 2))
        self.actuator_gainprm, self.dof_damping = np.ones((na, 10)), np.full(self.nv, 0.1)
        mounts = [self.bodies.index(f"attachment_{a}") for a in ARMS]
        self.cams = ["front", "handcam_rgb_right", "handcam_rgb_left", "cam_pos_z", "drawer_cam", "target_cam", "aim_cam"]
        self.cam_bodyid = np.array([0, *mounts, self.obj, self.drawer, self.target, 0])
        self.cam_mode = np.array([0, 0, 0, 0, 0, 0, 3])
        self.cam_targetbodyid = np.array([-1, -1, -1, -1, -1, -1, self.obj])
        self.ncam = len(self.cams)
        self.cam_fovy = np.full(self.ncam, 45.0)
        self.cam_quat, self.cam_pos = np.tile(np.array([1.0, 0, 0, 0]), (self.ncam, 1)), np.zeros((self.ncam, 3))
        self.cam_pos[3] = [0.03, 0.0, 0.06]
        self.site_quat, self.site_pos = np.tile(np.array([1.0, 0, 0, 0]), (2, 1)), np.zeros((2, 3))
        self.site_bodyid = np.array(mounts)

    def _body(self, name, parent):
        self.bodies.append(name)
        self.parent.append(parent)
        return len(self.bodies) - 1

    def _joint(self, name):
        self.joints.append(name)
        self.jnt_body.append(len(self.bodies) - 1)

    def _get(self, names, k, what):
        if isinstance(k, (int, np.integer)):
            return _Named(int(k), names[int(k)])
        if k not in names:
            raise KeyError(f"Invalid name '{k}' for {what}")
        return _Named(names.index(k), k)

    def joint(self, k):
        return self._get(self.joints, k, "joint")

    def actuator(self, k):
        return self._get(self.acts, k, "actuator")

    def site(self, k):
        return self._get(self.sites, k, "site")

    def camera(self, k):
        return self._get(self.cams, k, "camera")

    def body(self, k):
        return self._get(self.bodies, k, "body")


class Data:
    def __init__(self, m: Model):
        self.m = m
        self.qpos, self.qvel = np.zeros(m.nq), np.zeros(m.nv)
        self.qpos[-7:] = [*OBJECT_START, 1, 0, 0, 0]              # link_19's free joint (the toy keeps it at the end)
        self.ctrl, self.actuator_force = np.zeros(len(m.acts)), np.zeros(len(m.acts))
        self.mocap_pos, self.mocap_quat = np.zeros((2, 3)), np.tile(np.array([1.0, 0, 0, 0]), (2, 1))
        self.site_xpos, self.site_xmat = np.zeros((2, 3)), np.tile(np.eye(3).reshape(9), (2, 1))
        self.cam_xpos, self.cam_xmat = np.zeros((m.ncam, 3)), np.tile(np.eye(3).reshape(9), (m.ncam, 1))
        self.xpos, self.xquat = np.zeros((len(m.bodies), 3)), np.tile(np.array([1.0, 0, 0, 0]), (len(m.bodies), 1))
        mj_kinematics(m, self)
        self.mocap_pos[:] = self.site_xpos

    def body(self, name):
        i = self.m.body(name).id
        return types.SimpleNamespace(xpos=self.xpos[i], xquat=self.xquat[i])


def MjData(m):
    return Data(m)


def mj_name2id(m, typ, name):
    names = {mjtObj.mjOBJ_BODY: m.bodies, mjtObj.mjOBJ_CAMERA: m.cams, mjtObj.mjOBJ_JOINT: m.joints, mjtObj.mjOBJ_SITE: m.sites}[typ]
    return names.index(name) if name in names else -1


def mj_id2name(m, typ, i):
    return {mjtObj.mjOBJ_BODY: m.bodies, mjtObj.mjOBJ_CAMERA: m.cams}[typ][i]


BASE = {"right": np.array([-0.75, -0.4, 0.924]), "left": np.array([-0.75, 0.4, 0.924])}


def mj_kinematics(m, d):
    """tcp = base + offset + 0.1 * (the arm's first three joints); the object's cameras follow the object."""
    for k, a in enumerate(ARMS):
        tcp = BASE[a] + np.array([0.3, 0.0, 0.6]) + 0.1 * d.qpos[23 * k: 23 * k + 3]
        d.site_xpos[k] = tcp
        for i in range(8):
            d.xpos[m.body(f"link{i}_{a}").id] = BASE[a] + (tcp - BASE[a]) * i / 8
        d.xpos[m.body(f"attachment_{a}").id] = tcp
        d.cam_xpos[1 + k] = tcp
    d.xpos[m.obj], d.xquat[m.obj] = d.qpos[-7:-4], d.qpos[-4:]
    d.cam_xpos[0] = [1.5, 0.0, 1.6]
    d.cam_xpos[3] = d.qpos[-7:-4] + m.cam_pos[3]
    d.cam_xpos[4] = [0.5, 0.2, 1.0]
    d.cam_xpos[5] = d.mocap_pos[0]
    d.cam_xpos[6] = [0.0, 0.0, 2.0]


def mj_comPos(m, d):
    pass


def mj_jacSite(m, d, jp, jr, s):
    jp[:] = 0
    jr[:] = 0
    for c in range(3):
        jp[c, 23 * s + c] = 0.1
        jr[c, 23 * s + 3 + c] = 1.0


def mju_mat2Quat(q, mat):
    q[:] = [1, 0, 0, 0]


def mju_quat2Mat(R, q):
    R[:] = np.eye(3).reshape(9)


def mju_negQuat(out, q):
    out[:] = [q[0], -q[1], -q[2], -q[3]]


def mju_mulQuat(out, a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    out[:] = [w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
              w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2]


def mju_quat2Vel(out, q, dt):
    n = np.linalg.norm(q[1:])
    out[:] = 0 if n < 1e-12 else q[1:] / n * 2 * np.arctan2(n, q[0]) / dt
