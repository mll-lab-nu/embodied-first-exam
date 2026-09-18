"""Pinned ALOHA optical poses and the explicit Genesis calibration difference."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from hydra import compose, initialize_config_dir
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.world.aloha_cameras import CAMERA_NAMES, configure_aloha_rig, make_aloha_rig

ROOT = Path(__file__).resolve().parents[1]


class AlohaCameraChecks(unittest.TestCase):
    def test_fixed_optical_axes_follow_table_transform(self):
        origin = np.array([.2, -.1, .9])
        turn = Rotation.from_euler("z", 30, degrees=True)
        cameras, metadata = make_aloha_rig(origin, table_rotation=turn)
        np.testing.assert_allclose(cameras["cam_high"]["pos"], origin+turn.apply([0, -.303794, 1.02524]))
        for name in CAMERA_NAMES[:2]:
            camera = cameras[name]
            forward = np.array(camera["lookat"])-camera["pos"]
            self.assertAlmostEqual(np.linalg.norm(forward), 1)
            self.assertAlmostEqual(np.dot(forward, camera["up"]), 0)
        self.assertFalse(metadata["hardware_calibration_equivalent"])

    def test_wrist_optics_match_vendored_menagerie_xml(self):
        cameras, _ = make_aloha_rig([0, 0, .9])
        root = ET.parse(ROOT/"assets/robots/aloha/aloha.xml").getroot()
        for side in ("left", "right"):
            parent = root.find(f".//body[@name='{side}/gripper_base']")
            source = parent.find("camera")
            self.assertIsNotNone(source)
            attach = cameras[f"cam_{side}_wrist"]["attach"]
            np.testing.assert_allclose(attach["offset_pos"], np.fromstring(source.get("pos"), sep=" "))
            rotation = Rotation.from_euler("xyz", np.fromstring(source.get("euler"), sep=" "))
            np.testing.assert_allclose(np.array(attach["offset_lookat"])-attach["offset_pos"], rotation.apply([0, 0, -1]))
            np.testing.assert_allclose(attach["offset_up"], rotation.apply([0, 1, 0]))

    def test_intrinsics_report_actual_scalar_fov_limitation(self):
        cameras, report = make_aloha_rig([0, 0, 0])
        source, actual = np.array(report["source_intrinsics"]), np.array(report["configured_genesis_intrinsics"])
        focal = 720/(2*np.tan(np.radians(cameras["cam_high"]["fov"])/2))
        self.assertAlmostEqual(actual[0, 0], focal)
        self.assertAlmostEqual(actual[1, 1], source[1, 1])
        self.assertAlmostEqual(report["focal_x_relative_error"], .0240654205607476)

    def test_low_view_task_adjustment_preserves_mount_and_intrinsics(self):
        original, _ = make_aloha_rig([0, 0, .9])
        adjusted, report = make_aloha_rig([0, 0, .9], low_pitch_offset_deg=20)
        np.testing.assert_allclose(original["cam_low"]["pos"], adjusted["cam_low"]["pos"])
        a = np.array(original["cam_low"]["lookat"])-original["cam_low"]["pos"]
        b = np.array(adjusted["cam_low"]["lookat"])-adjusted["cam_low"]["pos"]
        self.assertAlmostEqual(np.degrees(np.arccos(np.dot(a, b))), 20)
        self.assertGreater(b[2], a[2])
        self.assertEqual(report["cam_low_pitch_offset_deg"], 20)
        self.assertEqual(adjusted["cam_low"]["fov"], original["cam_low"]["fov"])

    def test_shared_configuration_uses_robot_pair_centre(self):
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            cfg = compose(config_name="horseshoe_ring_aloha")
        report = configure_aloha_rig(cfg)
        self.assertEqual(set(cfg.env.cameras), set(CAMERA_NAMES)|{"room", "oblique"})
        np.testing.assert_allclose(report["source_frame_origin_m"], [-.1356786, 0, .8996429])
        self.assertEqual(report["robot_adapter_z_translation_m"], -.02)
        np.testing.assert_allclose(cfg.env.cameras.cam_low.pos, [-.1356786, -.377167, .9312484])


if __name__ == "__main__":
    unittest.main()
