"""Nyx pixel projection, strict camera rig and moving wrist calibration."""
from pathlib import Path
import os
import traceback
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from topogym.simulator import Env, SimulatorConfig
from topogym.tasks.base import TaskDefinition, TaskSpec, EntitySpec
from topogym.sensors.camera_info import optical_transform
from topogym.utils.arrays import to_numpy
from runtime_evidence import RuntimeEvidence

pytestmark = [pytest.mark.genesis, pytest.mark.render]


class CalibrationTask(TaskDefinition):
    task_id = "cast_coil"
    goal_complete = False

    def declare(self, asset_dir, table_height_m):
        self.points = [(-.12, -.08, table_height_m + .10), (.03, -.08, table_height_m + .10),
                       (.18, -.08, table_height_m + .10)]
        return TaskSpec(tuple(EntitySpec(f"marker_{i}", "sphere", None, p, fixed=True,
            morph_options={"radius": .016}, surface={"color": (*np.eye(3)[i], 1.), "roughness": 1.})
            for i, p in enumerate(self.points)))

    def evaluate_state(self, state):
        return False, None, {}


@pytest.mark.parametrize("robot_id", ["aloha", "panda_robotiq"])
def test_cameras(robot_id, monkeypatch):
    import topogym.simulator.env as env_module
    monkeypatch.setattr(env_module, "task_definition", lambda task_id: CalibrationTask)
    cfg = SimulatorConfig(robot_id=robot_id, enable_privileged=True)
    root = Path(os.environ["TOPOGYM_TEST_OUTPUT"])
    evidence = RuntimeEvidence(root / f"cameras_{robot_id}", f"cameras_{robot_id}", cfg)
    error = None
    try:
        with Env(cfg) as env:
            with evidence.stage("pixel_projection") as stage:
                obs, info = env.reset(seed=31)
                evidence.sample(env, obs, info, label="initial")
                camera = "cam_high" if robot_id == "aloha" else "agentview"
                metadata = obs["cameras"][camera]
                image = np.asarray(obs["rgb"][camera]).astype(float)
                transform = np.asarray(metadata["T_camera_cv_from_world"])
                intrinsics = np.asarray(metadata["K_px"])
                measured = []
                for channel, point in enumerate(env._task.points):
                    cv = transform @ np.r_[point, 1.]
                    assert cv[2] > 0
                    projected = intrinsics @ cv[:3]; projected = projected[:2] / projected[2]
                    u, v = np.rint(projected).astype(int)
                    assert 16 <= u < 832 and 16 <= v < 464
                    crop = image[v-14:v+15, u-14:u+15]
                    other = np.delete(crop, channel, axis=2).max(axis=2)
                    mask = (crop[..., channel] > other + 25) & (crop[..., channel] > 45)
                    ys, xs = np.nonzero(mask)
                    assert len(xs) >= 12, f"Nyx marker not visible near projected pixel {projected}"
                    centre = np.array([xs.mean() + u - 14, ys.mean() + v - 14])
                    residual = float(np.linalg.norm(centre - projected))
                    assert residual <= 3., (camera, channel, projected, centre)
                    measured.append(dict(projected=projected.tolist(), observed=centre.tolist(), error_px=residual))
                stage["fiducials"] = measured
            with evidence.stage("wrist_installation_and_follow") as stage:
                from topogym.config.scene import load_scene_config
                scene = load_scene_config(cfg)
                wrist_names = [name for name in obs["rgb"] if "wrist" in name]
                first = {name: np.asarray(obs["cameras"][name]["T_world_from_camera_cv"]) for name in wrist_names}
                group = env.action_spec["arms"][0]
                q = np.array(env.privileged.get("robot")[group]["joint_position_rad"], copy=True); q[0] += .04
                for i in range(12):
                    action = {group: {"joint_position_rad": q}} if i == 0 else {}
                    obs, _, done, timeout, info = env.step(action)
                    assert not done and not timeout
                    evidence.sample(env, obs, info, action=action)
                displacements = {}
                for name in wrist_names:
                    attach = scene.env.cameras[name].attach
                    link = env._world.entities["robot"].get_link(attach.link)
                    T = np.eye(4)
                    quat = to_numpy(link.get_quat()).reshape(-1, 4)[0]
                    T[:3, :3] = Rotation.from_quat(quat[[1, 2, 3, 0]]).as_matrix()
                    T[:3, 3] = to_numpy(link.get_pos()).reshape(-1, 3)[0]
                    expected = T @ optical_transform(attach.offset_pos, attach.offset_lookat, attach.offset_up) @ np.diag([1., -1., -1., 1.])
                    actual = np.asarray(obs["cameras"][name]["T_world_from_camera_cv"])
                    np.testing.assert_allclose(actual, expected, atol=5e-6, rtol=0)
                    displacements[name] = float(np.max(abs(actual - first[name])))
                moving = "cam_left_wrist" if robot_id == "aloha" else "wrist"
                assert displacements[moving] > 1e-5
                stage["transform_displacements"] = displacements
                evidence.end_recording()
    except BaseException:
        error = traceback.format_exc()
        raise
    finally:
        evidence.close(error)
