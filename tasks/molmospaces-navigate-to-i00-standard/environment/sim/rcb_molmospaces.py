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
CLI:
    python rcb_molmospaces.py replay --instance instance.json --traj trajectory.npz [--video replay.mp4]
    python rcb_molmospaces.py info   --instance instance.json
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
        OpenGL axes, image size, and the mount (static, or the robot link it moves with and its fixed offset)."""
        cam = self._camera(camera)
        w, h = (int(v) for v in self.inst["episode"]["img_resolution"])
        f = 0.5 * h / np.tan(np.radians(cam.fov) / 2)
        c2w = np.asarray(cam.get_pose(), dtype=np.float64)  # OpenCV axes: x right, y down, z forward
        mount = {"type": "static", "extrinsic_cv": np.linalg.inv(c2w)[:3].tolist()}
        body = getattr(cam, "_active_reference_body_name", None)
        if body:
            from molmo_spaces.env.data_views import create_mlspaces_body

            T_body = np.asarray(create_mlspaces_body(self.env.current_data, body).pose, dtype=np.float64)
            mount = {
                "type": "link",
                "link": body.split("/", 1)[-1],
                "T_link_cam_cv": (np.linalg.inv(T_body) @ c2w).tolist(),
            }
        return {
            "intrinsic_cv": [[f, 0.0, w / 2], [0.0, f, h / 2], [0.0, 0.0, 1.0]],
            "image_size": [w, h],
            "fovy_deg": float(cam.fov),
            "extrinsic_cv": np.linalg.inv(c2w)[:3].tolist(),
            "cam2world_gl": (c2w @ np.diag([1.0, -1.0, -1.0, 1.0])).tolist(),
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

    def robot_spec(self) -> dict:
        rv = self.robot.robot_view
        groups = {}
        for g in self.groups:
            mg = rv.get_move_group(g)
            ctl = np.asarray(self.robot.controllers[g].ctrl_range, dtype=np.float64).reshape(-1, 2)
            groups[g] = {"command_range": ctl.tolist(), "dim": self.dims[g]}
            if g in self.grippers:
                groups[g]["opening_range_m"] = list(rv.get_gripper(g).inter_finger_dist_range)
            else:
                groups[g]["joints"] = [_short(self.env.current_model.joint(j).name) for j in mg.joint_ids]
                groups[g]["joint_limits"] = np.asarray(mg.joint_pos_limits, dtype=np.float64).tolist()
        return {
            "robot": self.inst["episode"]["robot"]["robot_name"],
            "robot_config": self.inst["robot_config"],
            "control_hz": 1.0 / self.dt,
            "physics_dt_s": float(self.env.current_model.opt.timestep),
            "action_layout": self.layout,
            "move_groups": groups,
            "tcp_frames": list(self.grippers),
        }

    # ---- kinematics: upstream's MlSpacesKinematics on the robot's own model (never the scene)
    def _ik_arm(self, gripper: str) -> list[str]:
        """The arm group that moves a gripper (IK moves only that arm)."""
        arms = self.robot.get_arm_move_group_ids()
        return [a for a in arms if a.split("_")[0] == gripper.split("_")[0]] if len(arms) > 1 else list(arms)

    def kinematics_spec(self) -> dict:
        return {
            "endpoint": "/kinematics",
            "joint_names": self.joint_names,
            "frame": "world",
            "quaternion_order": "wxyz",
            "links": list(self.grippers),
            "tcp_frames": list(self.grippers),
            "ee_frames": list(self.grippers),
            "ik_targets": list(self.grippers),
            "ik": {
                "solver": "upstream MlSpacesKinematics.ik: damped least squares on the robot's MuJoCo model, no "
                "collision checking",
                "moves": {g: self._ik_arm(g) for g in self.grippers},
                "seed": "the measured joint positions",
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
            T = kin.fk(self._qpos(req["q"]), base)
            return {
                "ok": True,
                "op": "fk",
                "frame": "world",
                "poses": {k: _pose7(T[k]).tolist() for k in (req.get("links") or self.grippers)},
            }
        if req.get("op") != "ik":
            raise ValueError("op must be 'fk' or 'ik'")
        seed = req.get("seed")
        qd = self._qpos(self.proprio()["joint_pos"] if seed is None else seed)
        targets = {k: _mat(v) for k, v in req["targets"].items()}
        for g, T in targets.items():
            sol = kin.ik(g, T, self._ik_arm(g), qd, base, max_iter=int(req.get("max_iters") or spec["ik"]["max_iters"]))
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
        tp, tr = (
            float(req.get("tol_pos_m") or spec["ik"]["tol_pos_m"]),
            float(req.get("tol_rot_rad") or spec["ik"]["tol_rot_rad"]),
        )
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
    (upstream judge_success on the final state) and the final state hash."""
    t0 = time.time()
    ep = Episode(instance)
    rows = np.asarray(rows, dtype=np.float64).reshape(-1, ep.action_dim)
    frames, every = [], max(1, round(1 / (ep.dt * fps)))
    executed = 0
    for row in rows:
        if not ep.step(row):
            break
        executed += 1
        if video and executed % every == 0:
            frames.append(ep.render(ep.agent_cameras[0]))
    out = {
        "success": ep.success(),
        "state_sha": ep.state_sha(),
        "n_rows": int(len(rows)),
        "executed_rows": executed,
        "horizon": ep.horizon,
        "reached_horizon": ep.done,
        "replay_s": round(time.time() - t0, 1),
    }
    if video and frames:
        import imageio

        imageio.mimsave(video, frames, fps=fps)
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
    a = ap.parse_args(argv)
    rows = np.load(a.traj, allow_pickle=False)["actions"]
    print(json.dumps(replay(a.instance, rows, video=a.video)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
