"""Task information/calibration checks without starting or stepping Genesis."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf

from topogym.agent_bridge.adapters import GenesisAdapter
from topogym.agent_bridge.camera_info import camera_contract, optical_transform
from topogym.tasks.cast_coil.agent_spec import describe_task
from topogym.world.aloha_cameras import configure_aloha_rig


class TaskInformationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        with initialize_config_dir(config_dir=str(root/"configs"), version_base=None):
            cls.cfg = compose(config_name="cast_coil_aloha")
        cls.cfg.task.objective = "assemble"
        configure_aloha_rig(cls.cfg, keep=(), resolution=(320, 180), low_pitch_offset_deg=20)

    def test_fixed_projection_and_wrist_mounts_are_distinct(self):
        config = OmegaConf.to_container(self.cfg.env.cameras, resolve=True)
        cameras = camera_contract(config)
        self.assertEqual(len(cameras), 4)
        for name in ("cam_high", "cam_low"):
            info = cameras[name]
            forward_point = np.r_[config[name]["lookat"], 1]
            point_cv = (np.asarray(info["T_camera_cv_from_world"]) @ forward_point)[:3]
            pixel = np.asarray(info["K_px"]) @ point_cv
            np.testing.assert_allclose(pixel[:2]/pixel[2], [160, 90], atol=1e-9)
            self.assertGreater(point_cv[2], 0)
        for side in ("left", "right"):
            info = cameras[f"cam_{side}_wrist"]
            self.assertEqual(info["parent_link"], side+"/gripper_base")
            self.assertNotIn("T_world_from_camera_cv", info)
            np.testing.assert_allclose(np.asarray(info["T_parent_link_from_camera_cv"])[:3, 3],
                                       [0, -.0824748, -.0095955])

    def test_adapter_observation_tracks_current_camera_pose(self):
        camera = SimpleNamespace(transform=optical_transform([1, 2, 3], [1, 2, 2], [0, 1, 0]))
        adapter = GenesisAdapter(scene=SimpleNamespace(dt=.01), cameras={"wrist": camera}, description={},
            validate_action=lambda a: None, apply_action=lambda a: None, observe=lambda: {"robot": {}},
            evaluate=lambda: {"status": "running"})
        self.assertEqual(adapter.observe()["camera_poses"]["wrist"]["position_world_m"], [1, 2, 3])
        camera.transform[0, 3] += .5
        self.assertEqual(adapter.observe()["camera_poses"]["wrist"]["position_world_m"], [1.5, 2, 3])

    def test_goal_robot_units_and_objective_are_explicit_without_source_assets(self):
        spec = describe_task(self.cfg)
        self.assertIn("ALOHA 2", spec["robot"]["model"])
        self.assertEqual(spec["robot"]["arm_joint_order"],
                         ["waist", "shoulder", "elbow", "forearm_roll", "wrist_angle", "wrist_rotate"])
        self.assertEqual(spec["action_schema"]["gripper_limits_m"], [.002, .037])
        self.assertEqual(spec["control_dt_s"], .0025)
        self.assertNotIn("source_asset", spec["robot"])
        self.assertNotIn("goal_reference", spec)
        self.assertFalse(spec["perception"]["reference_images_provided"])
        self.assertFalse(spec["perception"]["object_geometry_provided"])
        self.assertNotIn("AABB", spec["success_rule"])
        cfg = OmegaConf.create(OmegaConf.to_container(self.cfg))
        cfg.task.objective = "disassemble"
        self.assertIn("AABB", describe_task(cfg)["success_rule"])
        json.dumps(spec, allow_nan=False)

    def test_hidden_object_size_and_initial_pose_do_not_change_public_brief(self):
        cfg = OmegaConf.create(OmegaConf.to_container(self.cfg))
        cfg.task.scale = 7
        cfg.task.center_xy_m = [.1, -.2]
        cfg.task.yaw_deg = 45
        self.assertEqual(describe_task(cfg), describe_task(self.cfg))


if __name__ == "__main__":
    unittest.main()
