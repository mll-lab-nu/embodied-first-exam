"""MuJoCo Playground's quadruped environments re-implemented in plain MuJoCo (CPU, numpy) for PPO training.

Each env mirrors its Playground source at 4057c14 (reset distribution, action mapping, observations, rewards,
termination); comments cite the file. Training only: the benchmark's own tool (rcb_quadruped.py) carries the frozen
instances and success checks, not these rewards.
"""
from __future__ import annotations

import glob
import os

import mujoco
import numpy as np

ROOT = os.environ.get("RCB_MJ_ROOT", "/opt/rcb_mj")    # the asset tree of eai-mujoco (images/mujoco/prepare_assets.sh)
_MODELS: dict = {}
_GO1 = [("playground/locomotion/go1/xmls", "*.xml"), ("playground/locomotion/go1/xmls/assets", "*"),
        ("menagerie/unitree_go1", "*.xml"), ("menagerie/unitree_go1/assets", "*")]
_SPOT = [("playground/locomotion/spot/xmls", "*.xml"), ("menagerie/boston_dynamics_spot", "*.xml"),
         ("menagerie/boston_dynamics_spot/assets", "*")]
_BARKOUR = [("menagerie/google_barkour_vb", "*.xml"), ("menagerie/google_barkour_vb/assets", "*")]
BARKOUR_FEET = ["foot_front_left", "foot_hind_left", "foot_front_right", "foot_hind_right"]
SCENES = {   # env -> (scene XML, the asset directories Playground's get_assets() reads)
    "Go1JoystickFlatTerrain": ("playground/locomotion/go1/xmls/scene_mjx_feetonly_flat_terrain.xml", _GO1),
    "Go1JoystickRoughTerrain": ("playground/locomotion/go1/xmls/scene_mjx_feetonly_rough_terrain.xml", _GO1),
    "Go1Getup": ("playground/locomotion/go1/xmls/scene_mjx_fullcollisions_flat_terrain.xml", _GO1),
    "Go1Handstand": ("playground/locomotion/go1/xmls/scene_mjx_flat_terrain.xml", _GO1),
    "Go1Footstand": ("playground/locomotion/go1/xmls/scene_mjx_flat_terrain.xml", _GO1),
    "SpotFlatTerrainJoystick": ("playground/locomotion/spot/xmls/scene_mjx_feetonly_flat_terrain.xml", _SPOT),
    "SpotGetup": ("playground/locomotion/spot/xmls/scene_mjx_flat_terrain.xml", _SPOT),
    "SpotJoystickGaitTracking": ("playground/locomotion/spot/xmls/scene_mjx_feetonly_flat_terrain.xml", _SPOT),
    "BarkourJoystick": ("menagerie/google_barkour_vb/scene_mjx.xml", _BARKOUR),
}


def load_model(env_name: str) -> mujoco.MjModel:
    """The scene as Playground builds it (its XML with an asset dict of bare file names), with a 1 MB arena per MjData
    (the default 14.7 MB is ~200x what these scenes use; physics unchanged)."""
    xml, dirs = SCENES[env_name]
    assets = {}
    for d, pat in dirs:
        for f in sorted(glob.glob(os.path.join(ROOT, d, pat))):
            if os.path.isfile(f):
                assets[os.path.basename(f)] = open(f, "rb").read()
    spec = mujoco.MjSpec.from_file(os.path.join(ROOT, xml), assets=assets)   # includes resolve next to the XML
    spec.memory = 1 << 20
    if env_name == "BarkourJoystick":   # barkour/joystick.py adds a foot-floor contact sensor per foot
        for g in BARKOUR_FEET:
            spec.add_sensor(name=f"{g}_floor_found", type=mujoco.mjtSensor.mjSENS_CONTACT, objtype=mujoco.mjtObj.mjOBJ_GEOM,
                            objname=g, reftype=mujoco.mjtObj.mjOBJ_GEOM, refname="floor", intprm=[1, 1, 1],
                            datatype=mujoco.mjtDataType.mjDATATYPE_REAL, needstage=mujoco.mjtStage.mjSTAGE_ACC, dim=1)
    return spec.compile()


class Env:
    """Shared plumbing: model, PD gains as Playground sets them, sensors, substeps."""

    name = ""
    episode_length = 1000
    ctrl_dt = 0.02
    kp = kd = None  # None = keep the XML's
    obs_noise = True
    imu_site = "imu"
    scene = None    # the SCENES entry, when it differs from `name`

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        key = (type(self).__name__, self.name)
        if key not in _MODELS:   # one compiled model per process, shared by its envs (each has its own MjData)
            m = load_model(self.scene or self.name)
            if self.kp is not None:
                m.dof_damping[6:] = self.kd
                m.actuator_gainprm[:, 0] = self.kp
                m.actuator_biasprm[:, 1] = -self.kp
            self.edit_model(m)
            _MODELS[key] = m
        self.m = _MODELS[key]
        self.d = mujoco.MjData(self.m)
        self.n_sub = round(self.ctrl_dt / self.m.opt.timestep)
        self.imu = self.m.site(self.imu_site).id
        self.lo, self.hi = self.m.jnt_range[1:].T.copy()
        self.ctrl_lo, self.ctrl_hi = self.m.actuator_ctrlrange.T.copy()
        self.home = self.m.keyframe("home").qpos.copy()
        self.default_pose = self.home[7:].copy()
        self._sens = {self.m.sensor(i).name: (self.m.sensor_adr[i], self.m.sensor_dim[i]) for i in range(self.m.nsensor)}

    def edit_model(self, m: mujoco.MjModel) -> None:
        """Per-env model changes Playground makes after loading (once per process)."""

    def sensor(self, name: str) -> np.ndarray:
        a, n = self._sens[name]
        return self.d.sensordata[a:a + n].copy()

    def imu_xmat(self) -> np.ndarray:
        return self.d.site_xmat[self.imu].reshape(3, 3)

    def noise(self, x: np.ndarray, scale: float) -> np.ndarray:
        if not self.obs_noise:
            return x
        return x + (2 * self.rng.random(x.shape) - 1) * scale

    def sim(self, ctrl: np.ndarray, n: int | None = None) -> None:
        self.d.ctrl[:] = ctrl
        mujoco.mj_step(self.m, self.d, nstep=n or self.n_sub)


# ---------------------------------------------------------------------------------------------------------- Go1 getup
class Go1Getup(Env):
    """go1/getup.py: recover from a random drop (p = 0.6) or the home pose and stand at z_des."""

    name = "Go1Getup"
    episode_length = 300
    kp, kd = 35.0, 0.5
    action_scale = 0.5
    scales = dict(orientation=1.0, torso_height=1.0, posture=1.0, stand_still=1.0, action_rate=-0.001,
                  dof_pos_limits=-0.1, torques=-1e-5, dof_acc=-2.5e-7, dof_vel=-0.1)
    noise_scales = dict(joint_pos=0.03, joint_vel=1.5, gyro=0.2, gravity=0.05)
    z_des = 0.275
    up = np.array([0.0, 0.0, -1.0])
    n_obs, n_priv = 42, 42 + 3 + 3 + 3 + 3 + 12 + 12 + 12 + 1

    def __init__(self, seed=0):
        super().__init__(seed)
        c = (self.lo + self.hi) / 2; r = self.hi - self.lo
        self.soft_lo, self.soft_hi = c - 0.5 * r * 0.95, c + 0.5 * r * 0.95

    def random_qpos(self) -> np.ndarray:
        q = np.zeros(self.m.nq); q[2] = 0.5
        quat = self.rng.normal(size=4); q[3:7] = quat / (np.linalg.norm(quat) + 1e-6)
        q[7:] = self.rng.uniform(self.lo, self.hi)
        return q

    def reset_to(self, qpos: np.ndarray, qvel: np.ndarray) -> None:
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[:] = qpos; self.d.qvel[:] = qvel
        mujoco.mj_forward(self.m, self.d)
        self.sim(qpos[7:], n=round(0.5 / self.m.opt.timestep))   # settle 0.5 s with ctrl = joints (getup.py:189)
        self.d.time = 0.0

    def reset(self):
        qpos = self.random_qpos() if self.rng.random() < 0.6 else self.home.copy()
        qvel = np.zeros(self.m.nv); qvel[:6] = self.rng.uniform(-0.5, 0.5, 6)
        self.reset_to(qpos, qvel)
        self.last_act = np.zeros(12); self.last_last_act = np.zeros(12)
        return self.obs()

    def gravity(self):
        return self.imu_xmat().T @ np.array([0, 0, -1.0])

    def obs(self):
        ns = self.noise_scales
        gyro, grav = self.sensor("gyro"), self.gravity()
        q, qd = self.d.qpos[7:].copy(), self.d.qvel[6:].copy()
        state = np.concatenate([self.noise(gyro, ns["gyro"]), self.noise(grav, ns["gravity"]),
                                self.noise(q, ns["joint_pos"]) - self.default_pose, self.noise(qd, ns["joint_vel"]),
                                self.last_act])
        priv = np.concatenate([state, gyro, self.sensor("accelerometer"), self.sensor("local_linvel"),
                               self.sensor("global_angvel"), q, qd, self.d.actuator_force, [self.d.site_xpos[self.imu][2]]])
        return state, priv

    def step(self, a):
        self.sim(self.d.qpos[7:] + a * self.action_scale)
        g = self.gravity(); h = self.d.site_xpos[self.imu][2]
        upright = np.sum((self.up - g) ** 2) < 0.01
        at_h = self.z_des - min(h, self.z_des) < 0.005
        q = self.d.qpos[7:]; tau = self.d.actuator_force
        r = dict(
            orientation=np.exp(-2.0 * np.sum((self.up - g) ** 2)),
            torso_height=np.exp(min(h, self.z_des)) - 1.0,
            posture=upright * np.exp(-0.5 * np.sum((q - self.default_pose) ** 2)),
            stand_still=upright * at_h * np.exp(-0.5 * np.sum(a ** 2)),
            action_rate=np.sum((a - self.last_act) ** 2) + np.sum((a - 2 * self.last_act + self.last_last_act) ** 2),
            torques=np.sqrt(np.sum(tau ** 2)) + np.sum(np.abs(tau)),
            dof_pos_limits=np.sum(-np.clip(q - self.soft_lo, None, 0) + np.clip(q - self.soft_hi, 0, None)),
            dof_acc=np.sum(self.d.qacc[6:] ** 2),
            dof_vel=np.sum(np.maximum(np.abs(self.d.qvel[6:]) - 2 * np.pi, 0) ** 2),
        )
        reward = float(np.clip(sum(self.scales[k] * v for k, v in r.items()) * self.ctrl_dt, 0, 1e4))
        self.last_last_act = self.last_act; self.last_act = a.copy()
        return (*self.obs(), reward, False)


# ------------------------------------------------------------------------------------------------- Go1 hand/footstand
class Go1Handstand(Env):
    """go1/handstand.py: from home (random xy/yaw/base velocity), balance on the front legs, nose down, at z_des."""

    name = "Go1Handstand"
    episode_length = 500
    kp, kd = 35.0, 0.5
    action_scale = 0.3
    z_des = 0.55
    desired_forward = np.array([0.0, 0.0, -1.0])
    pose_joints = np.arange(6, 12)
    scales = dict(height=1.0, orientation=1.0, contact=-0.1, dof_pos_limits=-0.5, pose=-0.1)
    noise_scales = dict(joint_pos=0.01, joint_vel=1.5, gyro=0.2, gravity=0.05, linvel=0.1)
    unwanted = ["fl_calf1", "fl_calf2", "fr_calf1", "fr_calf2", "fl_thigh1", "fl_thigh2", "fl_thigh3", "fr_thigh1",
                "fr_thigh2", "fr_thigh3", "fl_hip", "fr_hip"]   # Footstand inherits this front-leg list (handstand.py)

    def __init__(self, seed=0):
        super().__init__(seed)
        c = (self.lo + self.hi) / 2; r = self.hi - self.lo
        self.soft_lo, self.soft_hi = c - 0.5 * r * 0.9, c + 0.5 * r * 0.9
        self.unwanted_s = [self._sens[f"{g}_floor_found"][0] for g in self.unwanted]
        self.feet_s = [self._sens[f"{f}_floor_found"][0] for f in ("FR", "FL", "RR", "RL")]

    def reset(self):
        q = self.home.copy(); q[0:2] += self.rng.uniform(-0.5, 0.5, 2)
        yaw = self.rng.uniform(-3.14, 3.14); q[3:7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[:] = q; self.d.qvel[:6] = self.rng.uniform(-0.5, 0.5, 6); self.d.ctrl[:] = q[7:]
        mujoco.mj_forward(self.m, self.d)
        self.last_act = np.zeros(12)
        return self.obs()

    def gravity(self):
        return self.imu_xmat().T @ np.array([0, 0, -1.0])

    def obs(self):
        ns = self.noise_scales
        lin, gyro, grav = self.sensor("local_linvel"), self.sensor("gyro"), self.gravity()
        q, qd = self.d.qpos[7:].copy(), self.d.qvel[6:].copy()
        state = np.concatenate([self.noise(lin, ns["linvel"]), self.noise(gyro, ns["gyro"]), self.noise(grav, ns["gravity"]),
                                self.noise(q, ns["joint_pos"]) - self.default_pose, self.noise(qd, ns["joint_vel"]),
                                self.last_act])
        priv = np.concatenate([state, gyro, self.sensor("accelerometer"), lin, self.sensor("global_angvel"), q, qd,
                               self.d.actuator_force, [self.d.site_xpos[self.imu][2]]])
        return state, priv

    def step(self, a):
        self.sim(self.d.ctrl + a * self.action_scale)   # targets accumulate in ctrl space (handstand.py:203)
        sd = self.d.sensordata
        bad_contact = any(sd[i] > 0 for i in self.unwanted_s)
        done = self.d.site_xmat[self.imu].reshape(3, 3)[2, 2] < -0.25 or bad_contact
        fwd = self.imu_xmat() @ np.array([1.0, 0, 0]); h = self.d.site_xpos[self.imu][2]; q = self.d.qpos[7:]
        r = dict(
            height=np.exp(-(self.z_des - min(h, self.z_des))),
            orientation=(0.5 * fwd @ self.desired_forward + 0.5) ** 2,
            contact=float(any(sd[i] > 0 for i in self.feet_s)),
            dof_pos_limits=np.sum(-np.clip(q - self.soft_lo, None, 0) + np.clip(q - self.soft_hi, 0, None)),
            pose=np.sum((q[self.pose_joints] - self.default_pose[self.pose_joints]) ** 2),
        )
        reward = float(np.clip(sum(self.scales[k] * v for k, v in r.items()) * self.ctrl_dt, 0, 1e4))
        self.last_act = a.copy()
        return (*self.obs(), reward, bool(done))


class Go1Footstand(Go1Handstand):
    name = "Go1Footstand"
    z_des = 0.53
    desired_forward = np.array([0.0, 0.0, 1.0])
    pose_joints = np.arange(0, 6)


class Go1FootstandStrict(Go1Footstand):
    """Go1Footstand plus the termination Playground's Footstand sets up but never reads (handstand.py: _post_init
    assigns the hind-leg geoms to _unwanted_contact_geom_ids, the termination reads the inherited front-leg sensors):
    a hind leg's hip, thigh or calf touching the floor ends the episode too. Without it the policy sits on a hind hip."""

    name = "Go1FootstandStrict"
    scene = "Go1Footstand"
    hind = ["rl_calf1", "rl_calf2", "rr_calf1", "rr_calf2", "rl_thigh1", "rl_thigh2", "rl_thigh3", "rr_thigh1",
            "rr_thigh2", "rr_thigh3", "rl_hip", "rr_hip"]

    def __init__(self, seed=0):
        super().__init__(seed)
        self.floor = self.m.geom("floor").id
        self.hind_ids = {self.m.geom(g).id for g in self.hind}

    def step(self, a):
        state, priv, reward, done = super().step(a)
        return state, priv, reward, done or self.hind_contact()

    def hind_contact(self) -> bool:
        d = self.d
        for i in range(d.ncon):
            g1, g2 = d.contact[i].geom1, d.contact[i].geom2
            if (g1 == self.floor and g2 in self.hind_ids) or (g2 == self.floor and g1 in self.hind_ids):
                return True
        return False


class Go1FootstandStrict2(Go1FootstandStrict):
    """Go1FootstandStrict trained from scratch with a start curriculum (training only): half of the episodes start in
    Playground's `footstand` keyframe (small joint and base-velocity noise), so balancing is learnt before rearing up;
    the other half start as Playground's reset does."""

    name = "Go1FootstandStrict2"

    def reset(self):
        if self.rng.random() < 0.5:
            return super().reset()
        kf = self.m.keyframe("footstand")
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[:] = kf.qpos
        self.d.qpos[7:] += self.rng.uniform(-0.05, 0.05, 12)
        self.d.qvel[:6] = self.rng.uniform(-0.2, 0.2, 6)
        self.d.ctrl[:] = self.d.qpos[7:]
        mujoco.mj_forward(self.m, self.d)
        self.last_act = np.zeros(12)
        return self.obs()


# --------------------------------------------------------------------------------------------------------- Spot getup
class SpotGetup(Env):
    """spot/getup.py: recover from a drop from 1 m in a random orientation (p = 0.6) or the home pose."""

    name = "SpotGetup"
    episode_length = 300
    kp, kd = 400.0, 20.0
    action_scale = 0.6
    scales = dict(orientation=1.0, torso_height=1.0, posture=1.0, stand_still=1.0)
    noise_scales = dict(joint_pos=0.01, gyro=0.2, gravity=0.05)
    up = np.array([0.0, 0.0, 1.0])

    def __init__(self, seed=0):
        super().__init__(seed)
        self.z_des = self.home[2]

    def reset(self):
        if self.rng.random() < 0.6:
            q = np.zeros(self.m.nq); q[2] = 1.0
            quat = self.rng.normal(size=4); q[3:7] = quat / (np.linalg.norm(quat) + 1e-6)
            q[7:] = self.rng.uniform(self.ctrl_lo, self.ctrl_hi)
        else:
            q = self.home.copy()
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[:] = q
        mujoco.mj_forward(self.m, self.d)
        self.sim(q[7:], n=round(0.5 / self.m.opt.timestep)); self.d.time = 0.0
        self.last_act = np.zeros(12)
        return self.obs()

    def obs(self):
        ns = self.noise_scales
        gyro, up = self.sensor("gyro"), self.sensor("upvector")
        q = self.d.qpos[7:].copy()
        state = np.concatenate([self.noise(gyro, ns["gyro"]), self.noise(up, ns["gravity"]),
                                self.noise(q, ns["joint_pos"]) - self.default_pose, self.last_act])
        priv = np.concatenate([state, gyro, up, q, self.d.qvel.copy(), [self.d.qpos[2]], self.d.actuator_force])
        return state, priv

    def step(self, a):
        self.sim(np.clip(self.d.qpos[7:] + a * self.action_scale, self.ctrl_lo, self.ctrl_hi))
        q = self.d.qpos[7:]; up = self.sensor("upvector"); z = self.d.qpos[2]
        done = bool(np.any(q < self.ctrl_lo) or np.any(q > self.ctrl_hi))
        upright = np.sum((self.up - up) ** 2) < 0.01
        h_err = np.clip((self.z_des - z) / self.z_des, 0, 1)
        r = dict(orientation=np.exp(-2.0 * np.sum((self.up - up) ** 2)), torso_height=1.0 - h_err,
                 posture=upright * np.exp(-0.5 * np.sum((q - self.default_pose) ** 2)),
                 stand_still=upright * (h_err < 0.005) * np.exp(-0.5 * np.sum(a ** 2)))
        reward = float(np.clip(sum(self.scales[k] * v for k, v in r.items()) * self.ctrl_dt, 0, 1e4))
        self.last_act = a.copy()
        return (*self.obs(), reward, done)


# ------------------------------------------------------------------------------------------------ Spot joystick
class SpotFlatTerrainJoystick(Env):
    """spot/joystick.py (task flat_terrain): track (vx, vy, wz) commands from the home pose; perturbations off (its
    default config); a command redrawn every 201 control steps (zero with p = 0.1); termination: upvector z < 0.85."""

    name = "SpotFlatTerrainJoystick"
    episode_length = 1000
    kp, kd = 300.0, 1.0
    action_scale = 0.3
    cmd_lo = np.array([-1.0, -0.8, -1.0])
    cmd_hi = np.array([1.0, 0.8, 1.0])
    scales = dict(tracking_lin_vel=1.5, tracking_ang_vel=0.8, lin_vel_z=-2.0, ang_vel_xy=-0.05, orientation=-5.0,
                  termination=-1.0, posture=1.0, torques=-0.0002, action_rate=-0.01, energy=-0.001, feet_slip=-0.1,
                  feet_clearance=-2.0, feet_height=-0.1, feet_air_time=0.1)
    sigma, max_foot_height = 0.25, 0.12
    feet = ("FL", "FR", "HL", "HR")

    def __init__(self, seed=0):
        super().__init__(seed)
        self.foot_site = np.array([self.m.site(f).id for f in self.feet])
        self.contact_s = [self._sens[f"{f}_floor_found"][0] for f in self.feet]

    def sample_command(self):
        if self.rng.random() < 0.1:
            return np.zeros(3)
        return self.rng.uniform(self.cmd_lo, self.cmd_hi)

    def reset(self):
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[:] = self.home
        mujoco.mj_forward(self.m, self.d)
        self.cmd = self.sample_command()
        self.step_i = 0
        self.last_act = np.zeros(12); self.last_last_act = np.zeros(12)
        self.motor_targets = np.zeros(12)
        self.err_hist = np.zeros(36)
        self.air = np.zeros(4); self.last_contact = np.zeros(4, bool); self.swing_peak = np.zeros(4)
        return self.obs()

    def feet_pos(self):
        return np.concatenate([self.sensor(f"{f}_pos") for f in self.feet])

    def obs(self):
        gyro, up = self.sensor("gyro"), self.sensor("upvector")
        q = self.d.qpos[7:].copy()
        nq = self.noise(q, 0.05)
        fp = self.feet_pos().reshape(4, 3)
        if self.obs_noise:
            for ax, sc in enumerate((0.01, 0.005, 0.02)):
                fp[:, ax] += (2 * self.rng.random(4) - 1) * sc
        self.err_hist = np.roll(self.err_hist, 12)
        self.err_hist[:12] = nq - self.motor_targets
        state = np.concatenate([self.noise(gyro, 0.1), self.noise(up, 0.03), nq - self.default_pose, self.err_hist,
                                fp.ravel(), self.last_act, self.cmd])
        feet_v = np.concatenate([self.sensor(f"{f}_global_linvel") for f in self.feet])
        priv = np.concatenate([state, gyro, self.sensor("accelerometer"), up, self.sensor("local_linvel"),
                               self.sensor("global_angvel"), q - self.default_pose, self.feet_pos(), self.d.qvel[6:],
                               self.d.actuator_force, self.last_contact.astype(float), feet_v, self.air, np.zeros(3)])
        return state, priv

    def step(self, a):
        self.motor_targets = np.clip(self.default_pose + a * self.action_scale, self.ctrl_lo, self.ctrl_hi)
        self.sim(self.motor_targets)
        sd = self.d.sensordata
        contact = np.array([sd[i] > 0 for i in self.contact_s])
        contact_filt = contact | self.last_contact
        first = (self.air > 0) * contact_filt
        self.air += self.ctrl_dt
        pz = self.d.site_xpos[self.foot_site][:, 2]
        self.swing_peak = np.maximum(self.swing_peak, pz)
        up = self.sensor("upvector")
        done = bool(up[2] < 0.85)
        lin, gyro = self.sensor("local_linvel"), self.sensor("gyro")
        glin, gang = self.sensor("global_linvel"), self.sensor("global_angvel")
        feet_v = np.array([self.sensor(f"{f}_global_linvel") for f in self.feet])
        cmd_norm = np.linalg.norm(self.cmd)
        tau = self.d.actuator_force
        vxy = feet_v[:, :2]
        r = dict(
            tracking_lin_vel=np.exp(-np.sum((self.cmd[:2] - lin[:2]) ** 2) / self.sigma),
            tracking_ang_vel=np.exp(-((self.cmd[2] - gyro[2]) ** 2) / self.sigma),
            lin_vel_z=glin[2] ** 2,
            ang_vel_xy=np.sum(gang[:2] ** 2),
            orientation=np.sum(up[:2] ** 2),
            termination=float(done),
            posture=np.exp((-10.0 if cmd_norm < 0.01 else 0.0) * np.sum((self.d.qpos[7:] - self.default_pose) ** 2)),
            torques=np.sqrt(np.sum(tau ** 2)) + np.sum(np.abs(tau)),
            action_rate=np.sum((a - self.last_act) ** 2) + np.sum((a - 2 * self.last_act + self.last_last_act) ** 2),
            energy=np.sum(np.abs(self.d.qvel[6:]) * np.abs(tau)),
            feet_slip=np.sum(np.sum(vxy ** 2, axis=1) * contact),
            feet_clearance=np.sum(np.abs(pz - self.max_foot_height) * np.sqrt(np.linalg.norm(vxy, axis=1))),
            feet_height=np.sum((self.swing_peak / self.max_foot_height - 1.0) ** 2 * first) * (cmd_norm >= 0.01),
            feet_air_time=np.sum((self.air - 0.1) * first) * (cmd_norm >= 0.01),
        )
        reward = float(np.clip(sum(self.scales[k] * v for k, v in r.items()) * self.ctrl_dt, 0, 1e4))
        self.last_last_act = self.last_act; self.last_act = a.copy()
        self.step_i += 1
        if self.step_i > 200:
            self.cmd = self.sample_command(); self.step_i = 0
        self.air *= ~contact; self.last_contact = contact; self.swing_peak *= ~contact
        return (*self.obs(), reward, done)


# ------------------------------------------------------------------------------------------------ Barkour joystick
class BarkourJoystick(Env):
    """barkour/joystick.py: track (vx, vy, wz) under random pushes. Its model keeps the XML's 2 ms timestep while the
    env takes round(ctrl_dt / sim_dt) = 5 substeps, so one control step is 10 ms of simulated time (as upstream).
    Command at reset and redrawn after step 500; a push every kick_wait_steps (50-149) steps lasting 1-9 steps;
    termination: upvector z < 0, a joint outside [lowers, uppers], torso z < 0.18. Observation: 15 frames of 31."""

    name = "BarkourJoystick"
    imu_site = "imu_frame"
    episode_length = 1000
    action_scale = 0.3
    lowers = np.array([-0.7, -1.0, 0.05] * 4)
    uppers = np.array([0.52, 2.1, 2.1] * 4)
    scales = dict(tracking_lin_vel=1.5, tracking_ang_vel=0.8, lin_vel_z=-2.0, ang_vel_xy=-0.05, orientation=-5.0,
                  torques=-0.0002, action_rate=-0.1, stand_still=-0.5, termination=-1.0, feet_air_time=0.2)
    sigma = 0.25

    def edit_model(self, m):
        m.dof_damping[6:] = 0.5239
        m.actuator_gainprm[:, 0] = 35.0
        m.actuator_biasprm[:, 1] = -35.0

    def __init__(self, seed=0):
        super().__init__(seed)
        self.n_sub = 5
        self.torso = self.m.body("torso").id
        self.torso_mass = self.m.body_subtreemass[self.torso]
        self.contact_s = [self._sens[f"{g}_floor_found"][0] for g in BARKOUR_FEET]

    def sample_command(self):
        return self.rng.uniform([-0.6, -0.8, -0.7], [1.5, 0.8, 0.7])

    def reset(self):
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[:] = self.home
        mujoco.mj_forward(self.m, self.d)
        self.cmd = self.sample_command()
        self.kick_wait = int(self.rng.integers(50, 150)); self.kick_dur = int(self.rng.integers(1, 10))
        self.vel_kick = self.rng.uniform(0.1, 1.0); self.kick_dir = np.zeros(3); self.last_kick = -np.inf
        self.step_i = 0
        self.last_act = np.zeros(12); self.air = np.zeros(4); self.last_contact = np.zeros(4, bool)
        self.hist = np.zeros(15 * 31)
        return self.obs()

    def obs(self):
        o = np.concatenate([self.sensor("gyro")[2:3] * 0.25, self.sensor("upvector"), self.cmd * np.array([2.0, 2.0, 0.25]),
                            self.d.qpos[7:] - self.default_pose, self.last_act])
        o = np.clip(o, -100, 100)
        if self.obs_noise:
            o = o + 0.05 * self.rng.uniform(-1, 1, o.shape)
        self.hist = np.roll(self.hist, o.size); self.hist[:o.size] = o
        priv = np.concatenate([self.hist[:31], self.sensor("local_linvel"), self.sensor("global_angvel"), self.d.qvel[6:],
                               [self.d.xpos[self.torso][2]], self.cmd, self.d.xfrc_applied[self.torso, :3] / 100.0])
        return self.hist.copy(), priv

    def push(self):
        start = self.step_i % self.kick_wait == 0 and self.step_i != 0
        if start:
            ang = self.rng.uniform(0, 2 * np.pi); self.kick_dir = np.array([np.cos(ang), np.sin(ang), 0.0])
            self.last_kick = self.step_i
        dur = max(self.step_i - self.last_kick, 0)
        self.d.xfrc_applied[:] = 0
        if dur < self.kick_dur:
            u = 0.5 * np.sin(np.pi * dur / self.kick_dur)
            self.d.xfrc_applied[self.torso, :3] = u * self.torso_mass * self.vel_kick / (self.kick_dur * self.ctrl_dt) * self.kick_dir

    def step(self, a):
        self.push()
        self.sim(np.clip(self.default_pose + a * self.action_scale, self.lowers, self.uppers))
        q = self.d.qpos[7:]
        contact = np.array([self.d.sensordata[i] > 0 for i in self.contact_s])
        first = (self.air > 0) * (contact | self.last_contact)
        self.air += self.ctrl_dt
        up = self.sensor("upvector")
        done = bool(up[2] < 0 or np.any(q < self.lowers) or np.any(q > self.uppers) or self.d.xpos[self.torso][2] < 0.18)
        lin, gyro = self.sensor("local_linvel"), self.sensor("gyro")
        unit = self.cmd[:2] / (np.linalg.norm(self.cmd[:2]) + 1e-12)
        r = dict(
            tracking_lin_vel=np.exp(-np.sum((self.cmd[:2] - lin[:2]) ** 2) / self.sigma),
            tracking_ang_vel=np.exp(-((self.cmd[2] - gyro[2]) ** 2) / self.sigma),
            lin_vel_z=self.sensor("global_linvel")[2] ** 2,
            ang_vel_xy=np.sum(self.sensor("global_angvel")[:2] ** 2),
            orientation=np.sum(up[:2] ** 2),
            torques=np.sqrt(np.sum(self.d.qfrc_actuator ** 2)) + np.sum(np.abs(self.d.qfrc_actuator)),
            action_rate=np.sum((a - self.last_act) ** 2),
            stand_still=np.sum(np.abs(q - self.default_pose)) * (unit[1] < 0.1),
            termination=float(done and self.step_i < 500),
            feet_air_time=np.sum((self.air - 0.1) * first) * (np.linalg.norm(self.cmd[:2]) > 0.05),
        )
        reward = float(np.clip(sum(self.scales[k] * v for k, v in r.items()) * self.ctrl_dt, 0, 1e4))
        self.last_act = a.copy()
        self.step_i += 1
        if self.step_i > 500:
            self.cmd = self.sample_command(); self.step_i = 0
        self.air *= ~contact; self.last_contact = contact
        return (*self.obs(), reward, done)


# ----------------------------------------------------------------------------------------- Spot gait tracking
GAIT_PHASES = np.array([[0, np.pi, np.pi, 0], [0, 0.5 * np.pi, np.pi, 1.5 * np.pi], [0, np.pi, 0, np.pi],
                        [0, 0, np.pi, np.pi], [0, 0, 0, 0]])   # trot, walk, pace, bound, pronk; feet FL, FR, HL, HR


def gait_rz(phi, swing_height):
    """mujoco_playground/_src/gait.py get_rz: a foot's target height over its phase (cubic Bezier up, then down)."""
    x = (phi + np.pi) / (2 * np.pi)
    bez = lambda y0, y1, t: y0 + (y1 - y0) * (t ** 3 + 3 * (t ** 2 * (1 - t)))  # noqa: E731
    return np.where(x <= 0.5, bez(0, swing_height, 2 * x), bez(swing_height, 0, 2 * x - 1))


class SpotJoystickGaitTracking(SpotFlatTerrainJoystick):
    """spot/joystick_gait_tracking.py: joystick commands plus a gait (type, frequency 0.5-4 Hz, foot height 0.08-0.4 m)
    fixed per episode; reward = (sum of positive terms) * exp(0.2 * sum of negative terms) * dt, not clipped."""

    name = "SpotJoystickGaitTracking"
    kp, kd = 400.0, 10.0
    action_scale = 0.6
    cmd_lo = np.array([-1.0, -0.5, -1.0])
    cmd_hi = np.array([1.0, 0.5, 1.0])
    pos_scales = dict(feet_phase=2.0, tracking_lin_vel=0.5, tracking_ang_vel=0.5)
    neg_scales = dict(ang_vel_xy=-0.5, lin_vel_z=-0.5, hip_splay=-0.5)

    def reset(self):
        self.gait_freq = self.rng.uniform(0.5, 4.0)
        self.phase_dt = 2 * np.pi * self.ctrl_dt * self.gait_freq
        self.gait = int(self.rng.integers(0, 5))
        self.phase = GAIT_PHASES[self.gait].copy()
        self.foot_height = self.rng.uniform(0.08, 0.4)
        return super().reset()

    def obs(self):
        gyro, up = self.sensor("gyro"), self.sensor("upvector")
        q = self.d.qpos[7:].copy()
        nq = self.noise(q, 0.05)
        self.err_hist = np.roll(self.err_hist, 12)
        self.err_hist[:12] = nq - self.motor_targets
        contact = np.array([self.d.sensordata[i] > 0 for i in self.contact_s], dtype=float)
        state = np.concatenate([self.noise(gyro, 0.1), self.noise(up, 0.03), nq, self.err_hist, contact,
                                np.cos(self.phase), np.sin(self.phase), [self.gait_freq, self.gait, self.foot_height]])
        priv = np.concatenate([state, self.sensor("local_linvel"), self.sensor("global_angvel"), self.d.qvel[6:],
                               self.d.site_xpos[self.foot_site][:, 2], self.cmd])
        return state, priv

    def step(self, a):
        self.motor_targets = np.clip(self.default_pose + a * self.action_scale, self.ctrl_lo, self.ctrl_hi)
        self.sim(self.motor_targets)
        contact = np.array([self.d.sensordata[i] > 0 for i in self.contact_s])
        up = self.sensor("upvector")
        done = bool(up[2] < 0.85)
        lin, gyro = self.sensor("local_linvel"), self.sensor("gyro")
        fz = self.d.site_xpos[self.foot_site][:, 2]
        pos = dict(feet_phase=np.exp(-np.sum((fz - gait_rz(self.phase, self.foot_height)) ** 2) / 0.1),
                   tracking_lin_vel=np.exp(-np.sum((self.cmd[:2] - lin[:2]) ** 2) / self.sigma),
                   tracking_ang_vel=np.exp(-((self.cmd[2] - gyro[2]) ** 2) / self.sigma))
        neg = dict(ang_vel_xy=np.sum(self.sensor("global_angvel")[:2] ** 2),
                   lin_vel_z=self.sensor("global_linvel")[2] ** 2 * (self.gait > 2),
                   hip_splay=np.sum((self.d.qpos[7:][[0, 3, 6, 9]] - self.default_pose[[0, 3, 6, 9]]) ** 2))
        reward = float(sum(self.pos_scales[k] * v for k, v in pos.items())
                       * np.exp(0.2 * sum(self.neg_scales[k] * v for k, v in neg.items())) * self.ctrl_dt)
        self.last_last_act = self.last_act; self.last_act = a.copy()
        self.step_i += 1
        self.phase = np.fmod(self.phase + self.phase_dt + np.pi, 2 * np.pi) - np.pi
        if self.step_i > 200:
            self.cmd = self.sample_command(); self.step_i = 0
        self.last_contact = contact
        return (*self.obs(), reward, done)



class Go1FootstandStrict3(Go1FootstandStrict2):
    """Go1FootstandStrict2 fine-tuned with a steeper height reward (training only): exp(-(z_des - min(h, z_des)) / 0.1)
    at scale 3 instead of Playground's exp(-(z_des - min(h, z_des))) at scale 1, which leaves a squat on the hind feet
    (IMU at 0.2 m, trunk 30 deg from vertical) at 72% of the standing reward."""

    name = "Go1FootstandStrict3"

    def step(self, a):
        state, priv, reward, done = super().step(a)
        h = self.d.site_xpos[self.imu][2]
        old = np.exp(-(self.z_des - min(h, self.z_des)))
        new = 3.0 * np.exp(-(self.z_des - min(h, self.z_des)) / 0.1)
        return state, priv, max(0.0, reward + (new - old) * self.ctrl_dt), done


class SpotJoystickGaitTrackingCmd(SpotJoystickGaitTracking):
    """SpotJoystickGaitTracking with the command in the policy's observation (72 = Playground's 69 + vx, vy, wz).
    Playground's observation leaves the command out, so a policy trained on it cannot track the joystick, which its
    reward asks for; this is how the reference for that task is trained."""

    name = "SpotJoystickGaitTrackingCmd"
    scene = "SpotJoystickGaitTracking"

    def obs(self):
        state, priv = super().obs()
        return np.concatenate([state, self.cmd]), priv


ENVS = {c.name: c for c in (Go1Getup, Go1Handstand, Go1Footstand, Go1FootstandStrict, Go1FootstandStrict2,
                                     Go1FootstandStrict3, SpotGetup,
                                     SpotFlatTerrainJoystick, BarkourJoystick, SpotJoystickGaitTracking,
                                     SpotJoystickGaitTrackingCmd)}
