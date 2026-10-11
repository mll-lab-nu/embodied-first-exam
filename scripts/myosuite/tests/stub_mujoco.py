"""A stand-in for the part of the mujoco API that scripts/myosuite/shared/standard/server.py uses (copied next to the
server as mujoco.py by test_standard_server.py): a 5-joint "hand" (bodies 1..5), a ball on a slide joint `OBJTx`
(body 6). Cameras: hand_top fixed on a hand body, front on the world, ball_cam on the ball."""
import numpy as np


class mjtObj:
    mjOBJ_BODY, mjOBJ_JOINT, mjOBJ_SITE, mjOBJ_CAMERA = 1, 3, 6, 7


class _Named:
    def __init__(self, i, name):
        self.id, self.name = i, name


class Model:
    bodies = ["world", "forearm", "palm", "mid", "ff", "th", "Object"]
    joints = ["wrist", "mcp", "pip", "ffj", "thj", "OBJTx"]
    sites = ["THtip", "IFtip"]
    cams = ["hand_top", "front", "ball_cam"]

    def __init__(self, nu: int):
        self.nu, self.nv, self.nq, self.njnt, self.ncam = nu, 6, 6, 6, 3
        self.jnt_type, self.jnt_bodyid = np.array([3, 3, 3, 3, 3, 2]), np.array([1, 2, 3, 4, 5, 6])
        self.jnt_qposadr, self.jnt_dofadr = np.arange(6), np.arange(6)
        self.jnt_range, self.jnt_limited = np.tile(np.array([-1.5, 1.5]), (6, 1)), np.ones(6, int)
        self.body_parentid, self.body_mocapid = np.array([0, 0, 1, 2, 3, 3, 0]), np.full(7, -1)
        self.body_jntadr, self.body_jntnum = np.array([-1, 0, 1, 2, 3, 4, 5]), np.array([0, 1, 1, 1, 1, 1, 1])
        self.cam_bodyid, self.cam_mode, self.cam_targetbodyid = np.array([3, 0, 6]), np.zeros(3, int), np.full(3, -1)
        self.cam_fovy = np.full(3, 45.0)
        self.actuator_actadr = np.arange(nu)

    def _get(self, names, k, what):
        if isinstance(k, (int, np.integer)):
            return _Named(int(k), names[int(k)])
        if k not in names:
            raise KeyError(f"Invalid name {k!r} for {what}")
        return _Named(names.index(k), k)

    def joint(self, k):
        return self._get(self.joints, k, "joint")

    def body(self, k):
        return self._get(self.bodies, k, "body")

    def site(self, k):
        return self._get(self.sites, k, "site")

    def camera(self, k):
        return self._get(self.cams, k, "camera")


class Data:
    def __init__(self, m: Model):
        self.qpos, self.qvel, self.qfrc_actuator = np.zeros(6), np.zeros(6), np.zeros(6)
        self.act, self.actuator_length = np.zeros(m.nu), np.full(m.nu, 0.1)
        self.xpos, self.xquat = np.zeros((7, 3)), np.tile(np.array([1.0, 0, 0, 0]), (7, 1))
        self.xmat = np.tile(np.eye(3).reshape(9), (7, 1))
        self.site_xpos, self.site_xmat = np.zeros((2, 3)), np.tile(np.eye(3).reshape(9), (2, 1))
        self.cam_xpos, self.cam_xmat = np.zeros((3, 3)), np.tile(np.eye(3).reshape(9), (3, 1))
        mj_kinematics(m, self)


def MjData(m):
    return Data(m)


def mj_name2id(m, typ, name):
    names = {mjtObj.mjOBJ_BODY: m.bodies, mjtObj.mjOBJ_CAMERA: m.cams, mjtObj.mjOBJ_JOINT: m.joints, mjtObj.mjOBJ_SITE: m.sites}[typ]
    return names.index(name) if name in names else -1


def mj_kinematics(m, d):
    for b in range(1, 6):
        d.xpos[b] = [0.1 * b + 0.01 * d.qpos[b - 1], 0.0, 0.5]
    d.xpos[6] = [0.3 + d.qpos[5], 0.2, 0.5]            # the ball slides along x
    d.site_xpos[0], d.site_xpos[1] = d.xpos[5] + [0, 0, 0.05], d.xpos[4] + [0, 0, 0.05]
    d.cam_xpos[0], d.cam_xpos[1], d.cam_xpos[2] = d.xpos[3] + [0, 0, 0.3], [1.5, 0.0, 1.0], d.xpos[6] + [0, 0, 0.1]


def mj_comPos(m, d):
    pass


def mj_jacSite(m, d, jp, jr, s):
    jp[:] = 0
    jp[0, 4 if s == 0 else 3] = 0.01


def mju_mat2Quat(q, mat):
    q[:] = [1, 0, 0, 0]
