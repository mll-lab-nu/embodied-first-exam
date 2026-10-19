"""GR00T-WBC, the walking controller of the G1 (`g1_wbc`): two ONNX policies (Balance, Walk) on onnxruntime, CPU.

What it is: NVIDIA's GR00T Whole-Body Control decoupled G1 policy (https://github.com/NVlabs/GR00T-WholeBodyControl,
`decoupled_wbc/control/policy/g1_gear_wbc_policy.py` at 021df739; code Apache-2.0, weights under the NVIDIA Open
Model License), as BiGym 2.0 vendors and wraps it (`bigym/loco/adapters/_groot/` and `groot_wbc.py`, `bigym` 1.0.0
at 93ad4b3; Apache-2.0). The computation below is that runtime's, line for line where it computes (the observation,
its history, the Balance / Walk switch, the action scale), with BiGym's adapter around it (commands clipped on set,
targets clipped to the joint ranges, a non-finite output replaced by the default angles, the fall check). The
numbers of `g1_gear_wbc.yaml` are written out here (the file is vendored next to the weights; its sha256 is checked by
`tests/sim/test_g1_wbc.py`). The weights: `assets/third_party/bigym2/wbc/`, byte for byte BiGym's (and NVIDIA's).

Every control step (50 Hz): `set_command(vx, vy, wz, height, pitch)`, then `step(data)` returns the 15 position
targets of the legs and the waist; the world applies them with the arm and finger targets and runs 20 physics steps
of 1 ms. `get_state()` / `set_state()` hold everything that carries from one step to the next (the observation
history, the last action, the gait clock, the commands): the state hash includes it.
"""
from __future__ import annotations

import collections
import os
from pathlib import Path

import numpy as np

from .bodies import g1_wbc as _body

WEIGHTS = ("GR00T-WholeBodyControl-Balance.onnx", "GR00T-WholeBodyControl-Walk.onnx")
WEIGHTS_SHA256 = {"GR00T-WholeBodyControl-Balance.onnx": "f645da599d4ca3d29ed273c8f4712620bb680d34977469ca3aeabe5bb9631c18",
                  "GR00T-WholeBodyControl-Walk.onnx": "7c82255b6905ffcc4468fa7f8ddcf7b70db168cf1042107ccab887cb6a8e5407"}
CONFIG_SHA256 = "31226a224ca8450e89d9ce17d5cb31c052192a9cbfedc8d145f1cb95627ac7a2"      # g1_gear_wbc.yaml

# g1_gear_wbc.yaml
DEFAULT_ANGLES = np.array([-0.1, 0.0, 0.0, 0.3, -0.2, 0.0, -0.1, 0.0, 0.0, 0.3, -0.2, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
ANG_VEL_SCALE = 0.5
DOF_POS_SCALE = 1.0
DOF_VEL_SCALE = 0.05
ACTION_SCALE = 0.25
CMD_SCALE = np.array([2.0, 2.0, 0.5], dtype=np.float32)
NUM_ACTIONS = 15
NUM_OBS = 516
OBS_HISTORY_LEN = 6
CMD_INIT = np.array([0.0, 0.0, 0.0], dtype=np.float32)
HEIGHT_CMD = 0.74
FREQ_CMD = 0.75
SINGLE_OBS = 86

# BiGym's adapter and loco config (`GrootWbcG1Config`, `ControllerConfig`)
CONTROL_DT = 0.02
VEL_CLIP = 1.0                  # m/s, |vx| and |vy|
WZ_CLIP = 1.0                   # rad/s
HEIGHT_RANGE = (0.4, 1.0)       # m, pelvis height command
PITCH_RANGE = (-0.2, 0.8)       # rad, torso pitch command (+ leans forward)
WARMUP_STEPS = 200              # control steps of standing still after a reset (BiGym's `reset_warmup_steps`)
INIT_PELVIS_Z = 0.74
# The fall check (`LowerBodyBase.is_failed`): projected gravity's z above -0.6 (tilt past ~53 degrees) or the pelvis
# lower than the bottom of the height range less 0.10 m.
FALL_PROJ_G_Z = -0.6
FALL_HEIGHT = HEIGHT_RANGE[0] - 0.10


def weights_dir() -> Path:
    return _body.third_party_dir() / "bigym2" / "wbc"


def _session(path: Path):
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    model = ort.InferenceSession(str(path), sess_options=opts)
    name = model.get_inputs()[0].name
    return lambda x: model.run(None, {name: x})[0]


_POLICIES: dict = {}


def policies():
    """The Balance and Walk networks (loaded once per process; they hold no state of their own)."""
    if not _POLICIES:
        d = weights_dir()
        _POLICIES["balance"] = _session(d / WEIGHTS[0])
        _POLICIES["walk"] = _session(d / WEIGHTS[1])
    return _POLICIES["balance"], _POLICIES["walk"]


def quat_rotate_inverse(q, v):
    """GR00T's `gear_wbc_utils.quat_rotate_inverse` (wxyz)."""
    w, x, y, z = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    q_conj = np.array([w, -x, -y, -z])
    return np.array([
        v[0] * (q_conj[0] ** 2 + q_conj[1] ** 2 - q_conj[2] ** 2 - q_conj[3] ** 2)
        + v[1] * 2 * (q_conj[1] * q_conj[2] - q_conj[0] * q_conj[3])
        + v[2] * 2 * (q_conj[1] * q_conj[3] + q_conj[0] * q_conj[2]),
        v[0] * 2 * (q_conj[1] * q_conj[2] + q_conj[0] * q_conj[3])
        + v[1] * (q_conj[0] ** 2 - q_conj[1] ** 2 + q_conj[2] ** 2 - q_conj[3] ** 2)
        + v[2] * 2 * (q_conj[2] * q_conj[3] - q_conj[0] * q_conj[1]),
        v[0] * 2 * (q_conj[1] * q_conj[3] - q_conj[0] * q_conj[2])
        + v[1] * 2 * (q_conj[2] * q_conj[3] + q_conj[0] * q_conj[1])
        + v[2] * (q_conj[0] ** 2 - q_conj[1] ** 2 - q_conj[2] ** 2 + q_conj[3] ** 2),
    ])


def gravity_orientation(quat):
    return quat_rotate_inverse(quat, np.array([0.0, 0.0, -1.0]))


def projected_gravity(quat) -> np.ndarray:
    """BiGym's `quat_rotate_inverse_wxyz(quat, [0, 0, -1])` in float32 (what the fall check reads)."""
    w, x, y, z = (float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3]))
    v = np.asarray([0.0, 0.0, -1.0], dtype=np.float32)
    rx, ry, rz = -x, -y, -z
    tx = 2.0 * (ry * v[2] - rz * v[1])
    ty = 2.0 * (rz * v[0] - rx * v[2])
    tz = 2.0 * (rx * v[1] - ry * v[0])
    return np.array([v[0] + w * tx + (ry * tz - rz * ty), v[1] + w * ty + (rz * tx - rx * tz), v[2] + w * tz + (rx * ty - ry * tx)],
                    dtype=np.float32)


class Controller:
    """GR00T-WBC on one G1 of a compiled model whose names carry `prefix`."""

    def __init__(self, m, prefix: str = ""):
        import mujoco
        self.balance, self.walk = policies()
        jid = lambda n: m.joint(prefix + n).id      # noqa: E731
        self.body_qadr = np.array([m.jnt_qposadr[jid(n)] for n in _body.BODY_JOINTS], dtype=np.int64)
        self.body_dadr = np.array([m.jnt_dofadr[jid(n)] for n in _body.BODY_JOINTS], dtype=np.int64)
        self.lower_qadr = self.body_qadr[:NUM_ACTIONS]
        self.base_qadr = np.array([m.jnt_qposadr[jid(n)] for n in ("pelvis_x", "pelvis_y", "pelvis_z")], dtype=np.int64)
        self.base_dadr = np.array([m.jnt_dofadr[jid(n)] for n in ("pelvis_x", "pelvis_y", "pelvis_z")], dtype=np.int64)
        self.lower_range = np.array([m.jnt_range[jid(n)] for n in _body.LOWER_JOINTS], dtype=np.float32)
        self.lower_act = np.array([m.actuator(prefix + n).id for n in _body.LOWER_JOINTS], dtype=np.int64)
        s_or = m.sensor(prefix + "orientation").id
        s_gy = m.sensor(prefix + "angular-velocity").id
        self.orientation_adr, self.gyro_adr = int(m.sensor_adr[s_or]), int(m.sensor_adr[s_gy])
        self.pelvis = m.body(prefix + "pelvis").id
        self._mujoco = mujoco
        self.reset()

    # ---- state -----------------------------------------------------------------------------------------------------
    def reset(self) -> None:
        """BiGym's `GrootWbcG1Controller.reset` with a fresh policy: commands zero, height 0.74, nothing in the history."""
        self.command = np.zeros(3, dtype=np.float32)        # vx, vy, wz as set
        self.height_command = float(HEIGHT_CMD)
        self.pitch_command = 0.0
        self.last_action = np.zeros(NUM_ACTIONS, dtype=np.float32)
        self.last_targets = DEFAULT_ANGLES.copy()
        # the policy's own
        self.action = np.zeros(NUM_ACTIONS, dtype=np.float32)
        self.cmd = CMD_INIT.copy()
        self.p_height = float(HEIGHT_CMD)
        self.rpy = [0.0, 0.0, 0.0]
        self.gait = np.zeros((1,), dtype=np.float32)
        self.history: collections.deque = collections.deque(maxlen=OBS_HISTORY_LEN)
        self.obs_buffer = np.zeros(NUM_OBS, dtype=np.float32)

    def get_state(self) -> dict:
        hist = np.stack(list(self.history)).astype(np.float32) if self.history else np.zeros((0, SINGLE_OBS), dtype=np.float32)
        return {"cmd": self.command.copy(), "height_cmd": np.float32(self.height_command), "pitch_cmd": np.float32(self.pitch_command),
                "last_action": self.last_action.copy(), "last_targets": self.last_targets.copy(), "policy_action": self.action.copy(),
                "policy_cmd": np.asarray(self.cmd, dtype=np.float32).copy(), "policy_height_cmd": np.float32(self.p_height),
                "policy_rpy_cmd": np.asarray(self.rpy, dtype=np.float32), "policy_gait_indices": self.gait.copy(),
                "policy_obs_history": hist}

    def set_state(self, st: dict) -> None:
        self.command = np.asarray(st["cmd"], dtype=np.float32).reshape(3).copy()
        self.height_command = float(np.asarray(st["height_cmd"]).reshape(-1)[0])
        self.pitch_command = float(np.asarray(st["pitch_cmd"]).reshape(-1)[0])
        self.last_action = np.asarray(st["last_action"], dtype=np.float32).reshape(15).copy()
        self.last_targets = np.asarray(st["last_targets"], dtype=np.float32).reshape(15).copy()
        self.action = np.asarray(st["policy_action"], dtype=np.float32).reshape(15).copy()
        self.cmd = np.asarray(st["policy_cmd"], dtype=np.float32).reshape(3).copy()
        self.p_height = float(np.asarray(st["policy_height_cmd"]).reshape(-1)[0])
        self.rpy = [float(v) for v in np.asarray(st["policy_rpy_cmd"], dtype=np.float32).reshape(3)]
        self.gait = np.asarray(st["policy_gait_indices"], dtype=np.float32).reshape(1).copy()
        h = np.asarray(st["policy_obs_history"], dtype=np.float32).reshape(-1, SINGLE_OBS)
        self.history = collections.deque((r.copy() for r in h), maxlen=OBS_HISTORY_LEN)

    def state_arrays(self) -> list:
        """Everything of the controller the next step depends on, for the state hash (sorted by key, as RCB's)."""
        st = self.get_state()
        return [np.asarray(st[k]) for k in sorted(st)]

    # ---- commands ----------------------------------------------------------------------------------------------------
    def set_command(self, vx: float, vy: float, wz: float, height: float, pitch: float) -> None:
        """Clip-on-set, as BiGym: the twist to +-1, the height to 0.4..1.0 m, the torso pitch to -0.2..0.8 rad."""
        vx = float(np.clip(vx, -VEL_CLIP, VEL_CLIP))
        vy = float(np.clip(vy, -VEL_CLIP, VEL_CLIP))
        wz = float(np.clip(wz, -WZ_CLIP, WZ_CLIP))
        self.command = np.asarray([vx, vy, wz], dtype=np.float32)
        self.height_command = float(np.clip(height, *HEIGHT_RANGE))
        self.pitch_command = float(np.clip(pitch, *PITCH_RANGE))

    # ---- one step ----------------------------------------------------------------------------------------------------
    def _floating_base(self, d):
        pos = d.qpos[self.base_qadr].astype(np.float32, copy=True)
        lin = d.qvel[self.base_dadr].astype(np.float32, copy=True)
        quat = d.sensordata[self.orientation_adr:self.orientation_adr + 4].astype(np.float32, copy=True)
        ang = d.sensordata[self.gyro_adr:self.gyro_adr + 3].astype(np.float32, copy=True)
        return np.concatenate([pos, quat]), np.concatenate([lin, ang])

    def _observe(self, d) -> None:
        # G1GearWbcPolicy.compute_observation / set_observation
        self.gait = np.remainder(self.gait + 0.02 * FREQ_CMD, 1.0).astype(np.float32, copy=False)
        pose, vel = self._floating_base(d)
        qj = d.qpos[self.body_qadr].astype(np.float32, copy=True)
        dqj = d.qvel[self.body_dadr].astype(np.float32, copy=True)
        quat = pose[3:7].copy()
        omega = vel[3:6].copy()
        n = len(qj)
        padded = np.zeros(n, dtype=np.float32)
        padded[:len(DEFAULT_ANGLES)] = DEFAULT_ANGLES
        qj_scaled = (qj - padded) * DOF_POS_SCALE
        dqj_scaled = dqj * DOF_VEL_SCALE
        grav = gravity_orientation(quat)
        omega_scaled = omega * ANG_VEL_SCALE
        obs = np.zeros(SINGLE_OBS, dtype=np.float32)
        obs[0:3] = self.cmd[:3] * CMD_SCALE
        obs[3:4] = np.array([self.p_height])
        obs[4:7] = np.array(self.rpy)
        obs[7:10] = omega_scaled
        obs[10:13] = grav
        obs[13:13 + n] = qj_scaled
        obs[13 + n:13 + 2 * n] = dqj_scaled
        obs[13 + 2 * n:13 + 2 * n + 15] = self.action
        self.history.append(obs)
        while len(self.history) < OBS_HISTORY_LEN:
            self.history.appendleft(np.zeros_like(obs))
        for i, h in enumerate(self.history):
            self.obs_buffer[i * SINGLE_OBS:(i + 1) * SINGLE_OBS] = h

    def step(self, d) -> np.ndarray:
        """The 15 position targets of the legs and the waist for the state in `d` (kinematics and sensors current)."""
        self._observe(d)
        # G1GearWbcPolicy.get_action with the teleop command channel on
        self.p_height = float(np.asarray([self.height_command], dtype=np.float32)[0])
        self.cmd = self.command.copy()
        rpy = np.asarray([0.0, self.pitch_command, 0.0], dtype=np.float32)
        self.rpy = [rpy[0], rpy[1], rpy[2]]
        policy = self.balance if np.linalg.norm(self.cmd) < 0.05 else self.walk
        self.action = policy(self.obs_buffer[None, :]).squeeze()
        targets = (self.action * ACTION_SCALE + DEFAULT_ANGLES).astype(np.float32).reshape(15)
        if not np.all(np.isfinite(targets)):
            targets = DEFAULT_ANGLES.copy()
        self.last_action = np.asarray(self.action, dtype=np.float32).reshape(15)
        self.last_targets = np.clip(targets, self.lower_range[:, 0], self.lower_range[:, 1])
        return self.last_targets.astype(np.float32, copy=True)

    # ---- the fall check ------------------------------------------------------------------------------------------------
    def projected_gravity(self, d) -> np.ndarray:
        return projected_gravity(d.sensordata[self.orientation_adr:self.orientation_adr + 4].astype(np.float32))

    def fallen(self, d) -> bool:
        """BiGym's `is_failed`: tilted past ~53 degrees, or the pelvis below 0.30 m."""
        if float(self.projected_gravity(d)[2]) > FALL_PROJ_G_Z:
            return True
        return float(d.xpos[self.pelvis][2]) < FALL_HEIGHT

    def tilt_deg(self, d) -> float:
        g = self.projected_gravity(d)
        return float(np.degrees(np.arccos(np.clip(-float(g[2]) / max(float(np.linalg.norm(g)), 1e-9), -1.0, 1.0))))


def onnxruntime_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


os.environ.setdefault("OMP_NUM_THREADS", os.environ.get("OMP_NUM_THREADS", "1"))
