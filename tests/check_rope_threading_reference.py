"""Validate public hand frames against the actual adapted robot asset."""
from pathlib import Path
import unittest

from hydra import compose, initialize_config_dir
import mujoco
import numpy as np

from topogym.robot.assets import robot_asset
from topogym.tasks.rope_threading.reference_actions import ReferenceThreadingActions
from topogym.tasks.rope_threading.qualification import summarize, compare_trajectories

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT/"runs/environment-solvability/rope_threading/reference_motion_v1"


class ReferenceChecks(unittest.TestCase):
    def test_time_comparison_uses_saved_states_without_smoothing_contact_peaks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/"a", Path(folder)/"b"
            a.mkdir()
            b.mkdir()
            ca, cb = np.zeros((4, 81, 3)), np.zeros((4, 81, 3))
            cb[0, :, 2] = .99  # Different initial timestamps must not be paired.
            cb[2, :, 2] = .008  # A saved contact peak must not be interpolated away.
            np.savez(a/"trajectory.npz", times=[.00125, .02, .04, .06], centerlines=ca)
            np.savez(b/"trajectory.npz", times=[.000625, .02, .04, .06], centerlines=cb)
            result = compare_trajectories(a, b)
        self.assertFalse(result["passed"])
        self.assertEqual(result["comparison_samples"], 3)
        self.assertAlmostEqual(result["maximum_rms_time_s"], .04)
        self.assertAlmostEqual(result["maximum_frame_rms_m"], .008)

    @unittest.skipUnless((REFERENCE/"reference_motion.npz").exists(), "Offline public reference not downloaded")
    def test_reference_frames_agree_with_adapted_robot_kinematics(self):
        actions = ReferenceThreadingActions(REFERENCE)
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            cfg = compose(config_name="rope_threading_preview")
        model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
        data = mujoco.MjData(model)
        for time in np.linspace(0, actions.cutoff, 151):
            # At exact saved samples, FK must reproduce both observed hands.
            i = int(np.argmin(abs(actions.reference["time"]-time)))
            q, hands, _, _ = actions._sample(actions.reference["time"][i])
            data.qpos[:] = q
            mujoco.mj_forward(model, data)
            for si, side in enumerate(("left", "right")):
                body = data.body(f"{side}/gripper_link")
                np.testing.assert_allclose(body.xpos, hands[si, :3]+[0, 0, .0009], atol=1e-9)
                self.assertAlmostEqual(abs(float(body.xquat@hands[si, 3:])), 1., places=9)

    @unittest.skipUnless((REFERENCE/"reference_motion.npz").exists(), "Offline public reference not downloaded")
    def test_reference_carries_all_grasps_and_releases_in_physical_order(self):
        actions = ReferenceThreadingActions(REFERENCE)
        owners = {}
        acquired = []
        for event in actions.schedule:
            side, node = event["side"], event["node"]
            if event["kind"] == "acquire":
                self.assertNotIn(side, owners)
                owners[side] = node
                acquired.append((side, node))
            else:
                self.assertEqual(owners.pop(side), node)
        self.assertEqual(owners, {})
        self.assertEqual(acquired, [("right", 80), ("left", 0), ("left", 77),
                                    ("right", 80), ("left", 75), ("right", 80)])

    def test_missing_physics_evidence_cannot_qualify(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            result = summarize(folder)
        self.assertFalse(result["passed"])
        self.assertTrue(all(not value["passed"] for value in result["cases"].values()))


if __name__ == "__main__":
    unittest.main()
