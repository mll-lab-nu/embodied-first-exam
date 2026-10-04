"""rcb_molmospaces.py -- MolmoSpaces tooling for robot coding bench (docs/benchmarks/molmospaces.md).

One module, copied unchanged into every MolmoSpaces task: the privileged environment (`Session`), both verifiers
(`replay`) and the standard-mode sim service (`Episode`, driven by environment/sim/server.py). Everything that decides
the outcome is upstream code (molmo-spaces 0.2.9, MuJoCo 3.5.0, CPU physics):

- the frozen episode (instance.json: one upstream benchmark episode) is loaded through upstream's JSON-evaluation path
  (eval_main.create_eval_config -> JsonEvalRunner -> JsonEvalTaskSampler.sample_task -> setup_policy -> task.reset);
- one control step = one upstream `Task.step` with the joint-position targets of every controlled move group;
- the episode ends when upstream's `task.is_done()` says so (the benchmark's horizon) or when the agent ends it;
- success = upstream `task.judge_success()` on the final state (upstream's evaluation default: success at the end).

Only one thing differs from upstream's loader: its grasp-file existence filter for articulated objects is skipped
(grasp files are not shipped, and the filter only decides whether to raise; the joint comes from the episode).

Trajectory rows (both modes): the controlled move groups in upstream order, each the target upstream's joint-position
controller receives. Franka (8): 7 arm joints (rad) + the Robotiq command (0 open .. 255 closed). RB-Y1 (25): base x, y
(m, world frame) and yaw (rad), torso 6, left arm 7, right arm 7 (rad), left and right gripper (the finger motor's
force, -100 .. 100: positive closes, negative opens).

Python (privileged mode):
    from rcb_molmospaces import Session
    s = Session("/app/instance.json")      # 10-40 s: scene build
    s.layout, s.hold_row(), s.step(row)    # the row layout, the row that holds every target, one control step
    s.done, s.status()                     # upstream is_done(); success / done / steps / horizon / state hash
    s.state(); s.model, s.data             # every body pose and joint position; the MuJoCo model and data
    s.render(cam), s.render_depth(cam), s.camera_info(cam), s.proprio(), s.robot_spec()
    s.kinematics({"op": "fk", "q": q}); s.kinematics({"op": "ik", "targets": {tcp: pose7}})   # upstream's kinematic model
    s.reset()                              # rebuild the frozen episode (unlimited)
    s.replay(rows); s.save_trajectory(rows, "/app/output/trajectory.npz")
CLI (the verifiers):
    python rcb_molmospaces.py replay --instance instance.json --traj trajectory.npz [--video replay.mp4] [--out r.json]
"""

import argparse
import atexit
import hashlib
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", os.environ["MUJOCO_GL"])

# The asset sources the tasks use (the image ships only these; nothing is downloaded at run time).
ASSET_SOURCES = {
    "robots": ("franka_droid", "rby1", "rby1m"),
    "scenes": ("ithor", "refs", "procthor-10k-val", "procthor-objaverse-val", "holodeck-objaverse-val"),
    "objects": ("thor", "objaverse", "objathor_metadata"),
}
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
# The frame of upstream's kinematic model (MlSpacesKinematics.fk) each robot-mounted camera is rigidly attached to: the
# DROID wrist camera to the Robotiq gripper's base (the `gripper` frame's body), the DROID shoulder camera to the FR3's
# fixed base; the RB-Y1 head camera to link_head_2 (`head`), its wrist cameras to the arm's last link, rigid with
# EE_BODY (`left_gripper` / `right_gripper`), its third-person follower camera (MJCF mode "fixed") to its base. A
# camera's mount = this frame's pose^-1 . the camera's pose.
GRIPPER_COMMAND = {  # what the gripper entry of a row means, by upstream's gripper class
    "RobotIQGripperGroup": "the Robotiq 2F-85 command, 0 = open .. 255 = closed",
    "RBY1GripperGroup": "the finger motor's force, positive closes, negative opens, 0 exerts none",
}
CAMERA_PARENTS = {
    "wrist_camera_zed_mini": "gripper",
    "droid_shoulder_light_randomization": "base",
    "head_camera": "head",
    "wrist_camera_l": "left_gripper",
    "wrist_camera_r": "right_gripper",
    "camera_follower": "base",
}


def boot(install: bool = False):
    """The global upstream resource manager, restricted to ASSET_SOURCES. Call before any other molmo_spaces import:
    upstream modules fetch the global manager when imported. At run time nothing is installed. install=True (image
    build and instance selection only, with network): upstream's own manager with its scene post-setup, plus the grasp
    source its lazy Objaverse install fetches (utils.lazy_loading_utils.install_uid; the image build deletes it again)."""
    import molmo_spaces.molmo_spaces_constants as C

    if C._RESOURCE_MANAGER is None:
        versions = {t: {s: C.DATA_TYPE_TO_SOURCE_TO_VERSION[t][s] for s in srcs} for t, srcs in ASSET_SOURCES.items()}
        if install:
            versions["grasps"] = {"droid_objaverse": C.DATA_TYPE_TO_SOURCE_TO_VERSION["grasps"]["droid_objaverse"]}
            C._RESOURCE_MANAGER = C.get_resource_manager(data_type_to_source_to_version=versions)
        else:
            C._RESOURCE_MANAGER = C.setup_resource_manager(
                C._select_storage(),
                symlink_dir=C.ASSETS_DIR,
                versions=versions,
                cache_dir=C.DATA_CACHE_DIR,
                env_prefix="MLSPACES",
                post_setup=None,
            )
    return C._RESOURCE_MANAGER


def install(instance) -> None:
    """Build time only (network, after boot(install=True)): upstream's installer for the episode's scene and the objects
    in it (no grasps). Objects the episode adds are installed by upstream's loader itself."""
    from molmo_spaces.molmo_spaces_constants import get_scenes
    from molmo_spaces.utils.lazy_loading_utils import install_scene_with_objects_and_grasps_from_path

    ep = (load_instance(instance) if isinstance(instance, (str, Path)) else instance)["episode"]
    scene = get_scenes(ep["scene_dataset"], ep["data_split"])[ep["data_split"]][ep["house_index"]]
    install_scene_with_objects_and_grasps_from_path(scene, grasp_sources=())  # a variant dict: upstream takes "base"


def load_instance(path) -> dict:
    return json.loads(Path(path).read_text())


@contextmanager
def _no_grasp_file_filter():
    """Upstream's JsonEvalTaskSampler.set_joint_values raises unless one joint of the target articulated object has a
    grasp file; it only checks existence (the joint comes from the episode). Grasp files are not shipped, so the check
    is answered "exists" while the episode is built, and nothing else changes."""
    import molmo_spaces.utils.grasps as grasps

    orig = grasps.get_joint_grasp_path
    grasps.get_joint_grasp_path = lambda uid, joint_name, grasp_libraries=None: Path("/dev/null")
    try:
        yield
    finally:
        grasps.get_joint_grasp_path = orig


def _pose7(T) -> np.ndarray:
    """4x4 -> x y z qw qx qy qz."""
    from scipy.spatial.transform import Rotation

    q = Rotation.from_matrix(np.asarray(T)[:3, :3]).as_quat()  # x y z w
    return np.concatenate([np.asarray(T)[:3, 3], [q[3], q[0], q[1], q[2]]])


def _mat(pose7) -> np.ndarray:
    """x y z qw qx qy qz -> 4x4."""
    from scipy.spatial.transform import Rotation

    p = np.asarray(pose7, dtype=np.float64)
    T = np.eye(4)
    T[:3, :3] = Rotation.from_quat([p[4], p[5], p[6], p[3]]).as_matrix()
    T[:3, 3] = p[:3]
    return T


def _rot_err(T1, T2) -> float:
    from scipy.spatial.transform import Rotation

    return float(Rotation.from_matrix(np.asarray(T1)[:3, :3].T @ np.asarray(T2)[:3, :3]).magnitude())


def _short(name: str) -> str:
    return name.split("/")[-1]


class Episode:
    """One upstream episode built from a frozen instance. Rendering, proprioception and kinematics never step physics."""

    def __init__(self, instance):
        self.inst = load_instance(instance) if isinstance(instance, (str, Path)) else instance
        boot()
        from pydantic import create_model
        from molmo_spaces.configs import robot_configs
        from molmo_spaces.configs.policy_configs import DummyPolicyConfig
        from molmo_spaces.data_generation.pipeline import setup_policy
        from molmo_spaces.evaluation import eval_main
        from molmo_spaces.evaluation.benchmark_schema import EpisodeSpec
        from molmo_spaces.evaluation.configs.evaluation_configs import JsonBenchmarkEvalConfig
        from molmo_spaces.evaluation.json_eval_runner import JsonEvalRunner as R

        spec = EpisodeSpec.model_validate(self.inst["episode"])
        robot_cls = getattr(robot_configs, self.inst["robot_config"])
        dt = float(self.inst["policy_dt_ms"])
        cfg_cls = create_model(
            "RcbEvalConfig",
            __base__=JsonBenchmarkEvalConfig,
            robot_config=(robot_cls, robot_cls()),
            policy_config=(DummyPolicyConfig, DummyPolicyConfig()),
            policy_dt_ms=(float, dt),
        )
        self.horizon = eval_main.determine_task_horizon([spec], None, policy_dt_ms=dt)
        tmp = Path(tempfile.gettempdir()) / "rcb_molmospaces"
        exp = eval_main.create_eval_config(
            eval_config_cls=cfg_cls,
            benchmark_dir=tmp,
            output_dir=tmp / "eval",
            checkpoint_path=None,
            task_horizon=self.horizon,
            num_workers=1,
        )
        exp = R.patch_config(exp, episode_idx=0)
        R.adjust_robot(exp)
        exp.task_sampler_config.house_inds = [spec.house_index]
        exp.task_sampler_config.samples_per_house = 1
        cfg = R.prepare_episode_config(exp, spec, 0)
        self._sampler = R.get_episode_task_sampler(cfg, spec, None, None)
        with _no_grasp_file_filter():
            self.task = R.sample_task_from_spec(self._sampler, spec.house_index, spec, 0)
        if self.task is None:
            raise RuntimeError("upstream task sampling returned None")
        setup_policy(cfg, self.task, None, None)
        self.task.reset()
        self.env = self.task.env
        self.robot = self.env.current_robot
        self.dt = dt / 1000.0
        rv = self.robot.robot_view
        # controlled move groups, upstream order; a gripper group takes one command
        noop = rv.get_noop_ctrl_dict()
        self.groups = [g for g in rv.move_group_ids() if g in self.robot.controllers]
        self.grippers = [g for g in self.groups if g in rv.get_gripper_movegroup_ids()]
        self.joint_groups = [g for g in self.groups if g not in self.grippers]
        self.dims = {g: int(np.asarray(noop[g]).size) for g in self.groups}
        self.action_dim = sum(self.dims.values())
        m = self.env.current_model
        self.joint_names = [_short(m.joint(j).name) for g in self.joint_groups for j in rv.get_move_group(g).joint_ids]
        self.layout = [
            n
            for g in self.groups
            for n in (
                [_short(m.joint(j).name) for j in rv.get_move_group(g).joint_ids] if g not in self.grippers else [g]
            )
        ]
        self.q0 = self.proprio()["joint_pos"]  # the frozen start's joints: the IK's default seed (stateless, §8)

    # ---- acting
    def action(self, row) -> dict:
        a = np.asarray(row, dtype=np.float64).reshape(-1)
        if a.size != self.action_dim or not np.all(np.isfinite(a)):
            raise ValueError(f"an action row has {self.action_dim} finite numbers ({', '.join(self.layout)})")
        out, i = {}, 0
        for g in self.groups:
            out[g] = a[i : i + self.dims[g]].copy()
            i += self.dims[g]
        return out

    @property
    def done(self) -> bool:
        """Upstream's episode end: the benchmark's horizon (or upstream's own terminal condition)."""
        return bool(np.all(self.task.is_done()))

    @property
    def steps(self) -> int:
        return int(self.task.episode_step_count)

    def step(self, row) -> bool:
        """One control step: one upstream Task.step. False (nothing executed) once the episode is over."""
        if self.done:
            return False
        self.task.step(self.action(row))
        return True

    def success(self) -> bool:
        return bool(self.task.judge_success())

    def state_sha(self) -> str:
        d = self.env.current_data
        h = hashlib.sha1()
        for arr in (d.qpos, d.qvel, d.act, d.ctrl, d.mocap_pos, d.mocap_quat, [d.time]):
            h.update(np.ascontiguousarray(arr, dtype=np.float64).tobytes())
        return h.hexdigest()

    def hold_row(self) -> np.ndarray:
        """The row that keeps every controlled group at its current target."""
        return np.concatenate(
            [np.asarray(self.robot.controllers[g].target_pos, dtype=np.float64).reshape(-1) for g in self.groups]
        )

    # ---- cameras
    @property
    def cameras(self) -> list[str]:
        """Every camera of the episode (privileged mode)."""
        return list(self.env.camera_manager.registry.keys())

    @property
    def agent_cameras(self) -> list[str]:
        """The robot's own cameras (standard mode): the episode's cameras minus upstream's third-person follower."""
        return list(self.inst["agent_cameras"])

    def _camera(self, name: str):
        reg = self.env.camera_manager.registry
        reg.update_all_cameras(self.env)
        return reg[name]

    def render(self, camera: str) -> np.ndarray:
        """uint8 (H, W, 3), upstream's renderer at the episode's resolution."""
        self._camera(camera)
        return np.asarray(self.env.render_rgb_frame(camera))

    def render_depth(self, camera: str) -> np.ndarray:
        """float32 (H, W) depth in metres, upstream's depth render."""
        self._camera(camera)
        return np.asarray(self.env.render_depth_frame(camera), dtype=np.float32)

    def camera_info(self, camera: str) -> dict:
        """Calibration at the current state: OpenCV intrinsics, world -> camera extrinsics (OpenCV axes), cam2world in
        OpenGL axes, image size, and the mount (static, or the frame of the kinematic model it is rigid on and the fixed
        offset)."""
        cam = self._camera(camera)
        w, h = (int(v) for v in self.inst["episode"]["img_resolution"])
        f = 0.5 * h / np.tan(np.radians(cam.fov) / 2)
        c2w = np.asarray(cam.get_pose(), dtype=np.float64)  # OpenCV axes: x right, y down, z forward
        cam2world_gl = (c2w @ np.diag([1.0, -1.0, -1.0, 1.0])).tolist()
        mount = {"type": "static", "extrinsic_cv": np.linalg.inv(c2w)[:3].tolist(), "cam2world_gl": cam2world_gl}
        if getattr(cam, "_active_reference_body_name", None):  # robot-mounted: rigid on a frame of the kinematic model
            parent, rv = CAMERA_PARENTS[camera], self.robot.robot_view
            T_parent = self.robot.kinematics.fk(rv.get_qpos_dict(), rv.base.pose)[parent]
            mount = {"type": "link", "parent_link": parent, "link_T_cam_cv": (np.linalg.inv(T_parent) @ c2w).tolist()}
        return {
            "intrinsic_cv": [[f, 0.0, w / 2], [0.0, f, h / 2], [0.0, 0.0, 1.0]],
            "image_size": [w, h],
            "fovy_deg": float(cam.fov),
            "extrinsic_cv": np.linalg.inv(c2w)[:3].tolist(),
            "cam2world_gl": cam2world_gl,
            "mount": mount,
        }

    # ---- the robot
    def proprio(self) -> dict:
        """The robot's own sensors: joint positions / velocities / drive efforts of the controlled joints, the gripper
        openings (m between the fingertips) and the TCP poses (x y z qw qx qy qz, world frame)."""
        rv, d = self.robot.robot_view, self.env.current_data
        mgs = [rv.get_move_group(g) for g in self.joint_groups]
        return {
            "joint_pos": np.concatenate([mg.joint_pos for mg in mgs]),
            "joint_vel": np.concatenate([mg.joint_vel for mg in mgs]),
            "joint_effort": np.concatenate([d.actuator_force[mg.actuator_ids] for mg in mgs]),
            "gripper_opening": np.array([rv.get_gripper(g).inter_finger_dist for g in self.grippers]),
            "tcp_pose": np.concatenate([_pose7(rv.get_move_group(g).leaf_frame_to_world) for g in self.grippers]),
        }

    def command_limits(self) -> np.ndarray:
        """(action_dim, 2): each row entry's range: upstream's controller range, within the joint's range where the
        model limits the joint (the RB-Y1's base_theta: +-3.14 in the model, +-pi in the controller)."""
        lim = np.concatenate(
            [np.asarray(self.robot.controllers[g].ctrl_range, dtype=np.float64).reshape(-1, 2) for g in self.groups]
        )
        m, rv = self.env.current_model, self.robot.robot_view
        joints = [j for g in self.groups for j in ([None] if g in self.grippers else rv.get_move_group(g).joint_ids)]
        for i, j in enumerate(joints):
            if j is not None and m.jnt_limited[j]:
                lim[i] = np.clip(lim[i], *m.jnt_range[j])
        return lim

    def robot_spec(self) -> dict:
        """The robot's spec sheet (eai-standard/2.2 §5 robot_spec), read off the robot's MuJoCo model: every joint of
        the controlled move groups with the limits the simulator enforces, the grippers, the controller and its gains,
        the tool frames and the base. Nothing about the scene."""
        rv, m = self.robot.robot_view, self.env.current_model
        lims = dict(zip(self.layout, self.command_limits().tolist()))
        acts = {int(m.actuator_trnid[a, 0]): a for a in range(m.nu) if m.actuator_trntype[a] == 0}  # joint -> actuator
        joints, gains = [], {}
        for g in self.groups:
            mg = rv.get_move_group(g)
            for j in mg._joint_ids:  # every group's joints (`joint_ids` exists on simply actuated groups only)
                name, a = _short(m.joint(j).name), acts.get(int(j))
                limited = bool(m.jnt_limited[j])
                rng = m.jnt_range[j] if limited else lims.get(name)
                frc = float(m.jnt_actfrcrange[j][1]) if m.jnt_actfrclimited[j] else None
                if frc is None and a is not None and m.actuator_forcelimited[a]:
                    frc = float(m.actuator_forcerange[a][1])
                joints.append(
                    {
                        "name": name,
                        "type": "prismatic" if m.jnt_type[j] == 2 else "revolute",
                        "unit": "m" if m.jnt_type[j] == 2 else "rad",
                        "position_limits": None if rng is None else [round(float(v), 6) for v in rng],
                        "velocity_limit": None,
                        "effort_limit": round(frc, 6) if frc else None,
                        "group": g,
                        **(
                            {}
                            if limited
                            else {
                                "note": "the joint has no range in the model; the limits are the "
                                "controller's, which clips every target to them"
                            }
                        ),
                    }
                )
                if a is not None:
                    gains[name] = {
                        "stiffness": float(m.actuator_gainprm[a][0]),
                        "damping": float(-m.actuator_biasprm[a][2]),
                    }
        grippers, tcp = {}, {}
        for g in self.grippers:
            mg = rv.get_move_group(g)
            site = int(mg.leaf_frame_id)
            body = int(m.site_bodyid[site])
            d = self.env.current_data
            T_body, T_site = np.eye(4), np.eye(4)
            T_body[:3, :3], T_body[:3, 3] = d.xmat[body].reshape(3, 3), d.xpos[body]
            T_site[:3, :3], T_site[:3, 3] = d.site_xmat[site].reshape(3, 3), d.site_xpos[site]
            lo, hi = lims[g]
            grippers[g] = {
                "joints": [_short(m.joint(j).name) for j in mg._joint_ids],
                "opening_m": [float(v) for v in rv.get_gripper(g).inter_finger_dist_range],
                "command": f"joint_position entry {g}: {GRIPPER_COMMAND.get(type(mg).__name__, 'the gripper command')} "
                f"({lo:g} .. {hi:g})",
                "tcp_frame": g,
            }
            tcp[g] = {
                "parent_link": m.body(body).name.split("/", 1)[-1],  # the MJCF body, e.g. the Robotiq's gripper/base
                "link_T_frame": (np.linalg.inv(T_body) @ T_site).round(9).tolist(),
                "definition": f"upstream's grasp site `{_short(m.site(site).name)}`, between the fingertips: the `{g}` "
                "frame of /kinematics and of the proprio tcp_pose",
            }
        if "base" in self.groups:
            root = rv.base.root_body_id  # upstream's RB-Y1 base gives the body itself, not its id
            base = {
                "type": "mobile",
                "root_link": _short(m.body(getattr(root, "id", root)).name),
                "pose_in_proprio": [n for n in self.layout if n.startswith("base_")],
                "command": "joint_position entries base_x, base_y (m) and base_theta (rad): absolute targets in the "
                "world frame, held by position actuators",
                "limits": {n: lims[n] for n in self.layout if n.startswith("base_")},
            }
        else:
            base = {
                "type": "fixed",
                "pose": _pose7(rv.base.pose).tolist(),
                "note": "the world pose of the robot's base: x y z qw qx qy qz",
            }
        return {
            "name": self.inst["episode"]["robot"]["robot_name"],
            "description": f"MolmoSpaces' {self.inst['robot_config']} (molmo-spaces 0.2.9), move groups "
            f"{', '.join(self.groups)}",
            "base": base,
            "joints": joints,
            "grippers": grippers,
            "controller": {
                "type": "upstream's JointPosController per move group: MuJoCo position actuators on the joints, PD",
                "control_hz": 1.0 / self.dt,
                "physics_hz": 1.0 / float(m.opt.timestep),
                "gains": gains,
                "note": "one control step is one upstream Task.step: the targets are held for its physics substeps",
            },
            "tcp": tcp,
        }

    # ---- kinematics: upstream's MlSpacesKinematics on the robot's own model (never the scene)
    def _ik_arm(self, gripper: str) -> list[str]:
        """The arm group that moves a gripper (IK moves only that arm)."""
        arms = self.robot.get_arm_move_group_ids()
        return [a for a in arms if a.split("_")[0] == gripper.split("_")[0]] if len(arms) > 1 else list(arms)

    def kinematics_spec(self) -> dict:
        mounts = [CAMERA_PARENTS[c] for c in self.cameras if c in CAMERA_PARENTS]
        return {
            "endpoint": "/kinematics",
            "joint_names": self.joint_names,
            "frame": "world",
            "quaternion_order": "wxyz",
            "links": list(dict.fromkeys([*self.grippers, *mounts])),  # the TCP frames and the cameras' parent frames
            "tcp_frames": list(self.grippers),
            "ee_frames": list(self.grippers),
            "ik_targets": list(self.grippers),
            "ik": {
                "solver": "upstream MlSpacesKinematics.ik: damped least squares on the robot's MuJoCo model, no "
                "collision checking; one target after the other, each moving its arm"
                + (
                    "; where an arm alone fails, each target with the torso and its arm, then each with its arm "
                    "alone again (the torso moved them)"
                    if "torso" in self.joint_groups
                    else ""
                ),
                "moves": {g: self._ik_arm(g) for g in self.grippers},
                "seed": "the joint positions at the episode's start (or the request's `seed`)",
                "tol_pos_m": 0.005,
                "tol_rot_rad": 0.05,
                "max_iters": 1000,
            },
        }

    def _qpos(self, q) -> dict:
        """q in kinematics_spec()["joint_names"] order -> upstream's per-group qpos dict (grippers as they are now)."""
        qd = {g: np.asarray(v, dtype=np.float64).copy() for g, v in self.robot.robot_view.get_qpos_dict().items()}
        q = np.asarray(q, dtype=np.float64).reshape(-1)
        if q.size != len(self.joint_names):
            raise ValueError(f"q has {len(self.joint_names)} entries ({', '.join(self.joint_names)})")
        i = 0
        for g in self.joint_groups:
            qd[g] = q[i : i + qd[g].size]
            i += qd[g].size
        return qd

    def kinematics(self, req: dict) -> dict:
        """{"op": "fk", "q", "links"?} -> poses; {"op": "ik", "targets": {tcp: pose7}, "seed"?, "tol_pos_m"?,
        "tol_rot_rad"?, "max_iters"?} -> q (eai-standard/2.2 §8). Poses: x y z qw qx qy qz, world frame."""
        kin, base = self.robot.kinematics, self.robot.robot_view.base.pose
        spec = self.kinematics_spec()
        if req.get("op") == "fk":
            links = req.get("links") or self.grippers
            if any(k not in spec["links"] for k in links):
                raise ValueError(f"links must be among {spec['links']}")
            T = kin.fk(self._qpos(req["q"]), base)
            return {"ok": True, "op": "fk", "frame": "world", "poses": {k: _pose7(T[k]).tolist() for k in links}}
        if req.get("op") != "ik":
            raise ValueError("op must be 'fk' or 'ik'")
        seed = req.get("seed")
        qd = self._qpos(self.q0 if seed is None else seed)
        targets = {k: _mat(v) for k, v in req["targets"].items()}
        if any(k not in spec["ik_targets"] for k in targets):
            raise ValueError(f"targets must be among {spec['ik_targets']}")
        tp = float(req.get("tol_pos_m") or spec["ik"]["tol_pos_m"])
        tr = float(req.get("tol_rot_rad") or spec["ik"]["tol_rot_rad"])
        iters = int(req.get("max_iters") or spec["ik"]["max_iters"])

        def solve(q, unlocked):  # upstream's IK, one target frame after the other
            for g, T in targets.items():
                q = kin.ik(g, T, unlocked(g), q, base, eps=min(tp, tr), max_iter=iters)
                if q is None:
                    return None
            return q

        sol = solve(qd, self._ik_arm)
        if sol is None and "torso" in self.joint_groups:
            sol = solve(qd, lambda g: ["torso", *self._ik_arm(g)])
            sol = None if sol is None else solve(sol, self._ik_arm)
        if sol is None:
            return {
                "ok": False,
                "op": "ik",
                "frame": "world",
                "q": None,
                "error": {k: {"pos_m": None, "rot_rad": None} for k in targets},
            }
        qd = {k: np.asarray(v, dtype=np.float64) for k, v in sol.items()}
        reached = kin.fk(qd, base)
        err = {
            k: {"pos_m": float(np.linalg.norm(reached[k][:3, 3] - T[:3, 3])), "rot_rad": _rot_err(reached[k], T)}
            for k, T in targets.items()
        }
        return {
            "ok": all(e["pos_m"] <= tp and e["rot_rad"] <= tr for e in err.values()),
            "op": "ik",
            "frame": "world",
            "q": np.concatenate([qd[g] for g in self.joint_groups]).tolist(),
            "error": err,
        }

    def close(self) -> None:
        self._sampler.close()


def replay(instance, rows, video: str | None = None, fps: int = 15) -> dict:
    """A fresh episode from the frozen instance, the rows in order until upstream ends the episode, then the verdict
    (upstream judge_success on the final state) and the final state hash. `instance_ok`: the fresh episode starts in the
    instance's recorded t = 0 state. With `video`, the first agent camera is encoded on the way (a failing encoder only
    drops the video: `video` false)."""
    t0 = time.time()
    ep = Episode(instance)
    start_sha = ep.state_sha()
    rows = np.asarray(rows, dtype=np.float64).reshape(-1, ep.action_dim)
    writer, every = None, max(1, round(1 / (ep.dt * fps)))
    if video:
        try:
            import imageio

            writer = imageio.get_writer(video, fps=fps)
        except Exception:  # noqa: BLE001 -- the video is for humans: it never decides the verdict
            writer = None
    executed = 0
    for row in rows:
        if not ep.step(row):
            break
        executed += 1
        if writer is not None and executed % every == 0:
            try:
                writer.append_data(ep.render(ep.agent_cameras[0]))
            except Exception:  # noqa: BLE001
                writer = None
    out = {
        "success": ep.success(),
        "state_sha": ep.state_sha(),
        "instance_ok": start_sha == ep.inst["t0"]["state_sha"],
        "n_rows": int(len(rows)),
        "executed_rows": executed,
        "horizon": ep.horizon,
        "reached_horizon": ep.done,
        "replay_s": round(time.time() - t0, 1),
        "video": False,
    }
    if writer is not None:
        try:
            writer.close()
            out["video"] = executed >= every
        except Exception:  # noqa: BLE001
            pass
    ep.close()
    return out


class Session:
    """Privileged mode: the frozen episode with full state access, unlimited resets and self-replay."""

    def __init__(self, instance: str = "/app/instance.json"):
        self.instance = instance
        self.resets = 0
        self.sim_steps = 0
        self._ended = False
        self.ep = Episode(instance)
        self._log({"ev": "session_start"})
        atexit.register(self._end)  # agents rarely call close(): the cost is logged at exit too

    # the episode
    def reset(self) -> None:
        self.sim_steps += self.ep.steps
        self.ep.close()
        self.ep = Episode(self.instance)
        self.resets += 1
        self._log({"ev": "reset"})

    def step(self, row) -> bool:
        return self.ep.step(row)

    @property
    def done(self) -> bool:
        return self.ep.done

    def status(self) -> dict:
        return {
            "success": self.ep.success(),
            "done": self.ep.done,
            "steps": self.ep.steps,
            "horizon": self.ep.horizon,
            "state_sha": self.ep.state_sha(),
            "resets": self.resets,
        }

    def replay(self, rows) -> dict:
        self.reset()
        executed = sum(
            1 for row in np.asarray(rows, dtype=np.float64).reshape(-1, self.ep.action_dim) if self.step(row)
        )
        self._log({"ev": "replay"})
        return {**self.status(), "executed_rows": executed}

    def save_trajectory(self, rows, path: str = "/app/output/trajectory.npz") -> None:
        rows = np.asarray(rows, dtype=np.float64).reshape(-1, self.ep.action_dim)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=rows, layout=np.array(self.ep.layout), family=self.ep.inst["family"])

    # privileged state
    def state(self) -> dict:
        """Every body's world pose (x y z qw qx qy qz) and every joint's position, keyed by name, plus the task config."""
        import mujoco

        m, d = self.ep.env.current_model, self.ep.env.current_data
        bodies = {m.body(i).name: np.concatenate([d.xpos[i], d.xquat[i]]).tolist() for i in range(1, m.nbody)}
        joints = {
            m.joint(j).name: d.qpos[
                m.jnt_qposadr[j] : m.jnt_qposadr[j] + {0: 7, 1: 4}.get(int(m.jnt_type[j]), 1)
            ].tolist()
            for j in range(m.njnt)
        }
        return {
            "bodies": bodies,
            "joints": joints,
            "task": self.ep.inst["episode"]["task"],
            "time": float(d.time),
            "mujoco": mujoco.__version__,
        }

    @property
    def model(self):
        return self.ep.env.current_model

    @property
    def data(self):
        return self.ep.env.current_data

    def __getattr__(self, name):  # layout, hold_row, render, camera_info, proprio, kinematics, ...
        if "ep" not in self.__dict__:
            raise AttributeError(name)
        return getattr(self.__dict__["ep"], name)

    def _end(self) -> None:
        if not self._ended:
            self._ended = True
            self._log({"ev": "session_end", "sim_steps": self.sim_steps + self.ep.steps, "resets": self.resets})

    def close(self) -> None:
        self._end()
        self.ep.close()

    @staticmethod
    def _log(ev: dict) -> None:
        if not SESSION_LOG:
            return
        try:
            Path(SESSION_LOG).parent.mkdir(parents=True, exist_ok=True)
            with open(SESSION_LOG, "a") as f:
                f.write(json.dumps({"ts": time.time(), **ev}) + "\n")
        except OSError:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="replay a trajectory in this (fresh) process; prints one JSON line")
    r.add_argument("--instance", required=True)
    r.add_argument("--traj", required=True)
    r.add_argument("--video")
    r.add_argument("--out", help="also write the result there (JSON); upstream prints its own text on stdout")
    a = ap.parse_args(argv)
    rows = np.load(a.traj, allow_pickle=False)["actions"]
    result = replay(a.instance, rows, video=a.video)
    if a.out:
        Path(a.out).write_text(json.dumps(result))
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
