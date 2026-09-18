"""Check ALOHA camera frame conversion against the pinned source model."""
from pathlib import Path
import unittest

from hydra import compose, initialize_config_dir
import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.world import nyx

ROOT = Path(__file__).resolve().parents[1]


def camera_transform(cfg, *, attached=False):
    source = cfg.attach if attached else cfg
    prefix = "offset_" if attached else ""
    return nyx.pos_lookat_up_to_T(*[
        np.asarray(source[prefix + key], dtype=float) for key in ("pos", "lookat", "up")])


class CameraPresetChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
            cls.demo = compose(config_name="aloha_lab_preview")
            cls.observation = compose(config_name="aloha_lab_preview", overrides=[
                "camera_configs@env=aloha_observation"])
            cls.single = compose(config_name="presentation_preview")
        cls.model = mujoco.MjModel.from_xml_path(str(ROOT / "assets/robots/aloha/aloha.xml"))
        cls.translation = np.asarray(cls.demo.env.robot_mount.pos) - [0, 0, 0.02]

    def test_demo_and_wrist_poses_match_source_mjcf(self):
        for ours, source, attached in (
            ("teleoperator", "teleoperator_pov", False),
            ("collaborator", "collaborator_pov", False),
            ("wrist", "wrist_cam_left", True),
            ("wrist_right", "wrist_cam_right", True),
        ):
            with self.subTest(camera=ours):
                camera = self.model.camera(source)
                transform = camera_transform(self.demo.env.cameras[ours], attached=attached)
                pos = camera.pos if attached else camera.pos + self.translation
                np.testing.assert_allclose(transform[:3, 3], pos, atol=1e-7)
                rotation = Rotation.from_quat(camera.quat[[1, 2, 3, 0]]).as_matrix()
                np.testing.assert_allclose(transform[:3, :3], rotation, atol=1e-7)
                if attached:
                    link = self.model.body(int(camera.bodyid[0])).name
                    self.assertEqual(self.demo.env.cameras[ours].attach.link, link)
                else:
                    self.assertEqual(self.demo.env.cameras[ours].fov, camera.fovy[0])

    def test_scene_camera_conversion_preserves_source_optical_axes(self):
        # Independent source poses from pinned aloha/scene.xml. MuJoCo camera
        # looks along local -Z; checking this catches a common inverted view.
        for name, pos, quat in (
            ("overhead", [0, -0.303794, 1.02524], [0.976332, 0.216277, 0, 0]),
            ("worms_eye", [0, -0.377167, 0.0316055], [0.672659, 0.739953, 0, 0]),
        ):
            with self.subTest(camera=name):
                transform = camera_transform(self.demo.env.cameras[name])
                np.testing.assert_allclose(transform[:3, 3] - self.translation, pos, atol=1e-7)
                rotation = Rotation.from_quat(np.asarray(quat)[[1, 2, 3, 0]]).as_matrix()
                np.testing.assert_allclose(transform[:3, :3], rotation, atol=1e-7)
                forward = -transform[:3, 2]
                self.assertGreater(forward[1], 0)  # both look into the table
                self.assertEqual(forward[2] < 0, name == "overhead")

    def test_selection_resolves_and_keeps_observation_framing(self):
        for config in (self.demo, self.observation):
            with self.subTest(preset=config.env.camera_rig.id):
                # Same filtering as the demo; also catches dangling viewer
                # interpolations after non-selected cameras are removed.
                selected = OmegaConf.create(OmegaConf.to_container(config, resolve=True))
                selected.env.cameras = {name: selected.env.cameras[name]
                                        for name in selected.env.camera_rig.preview_cameras}
                OmegaConf.to_container(selected, resolve=True, throw_on_missing=True)
                for name in selected.env.camera_rig.observation_cameras:
                    camera = selected.env.cameras[name]
                    self.assertAlmostEqual(camera.res[0] / camera.res[1], 1280 / 720)
                    self.assertAlmostEqual(camera.fov, np.degrees(2 * np.arctan(2.140 / (2 * 1.930))), places=5)
        self.assertNotIn("teleoperator", self.observation.env.cameras)
        self.assertNotIn("camera_rig", self.single.env)
        self.assertEqual(self.single.env.cameras.wrist.attach.link, "hand")
        self.assertEqual(list(self.single.env.cameras.wrist.res), [256, 256])


if __name__ == "__main__":
    unittest.main()
