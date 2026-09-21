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
    def test_smooth_initialization_preserves_all_source_material_points(self):
        from topogym.tasks.rope_threading.geometry import ThreadingLayout
        reference = ThreadingLayout(rope_subdivisions=1).centerline()
        for subdivisions in (4, 6, 8):
            curve = ThreadingLayout(rope_subdivisions=subdivisions,
                centerline_interpolation='circular_arc').centerline()
            np.testing.assert_array_equal(curve[::subdivisions], reference)

    def test_smooth_initialization_has_mesh_independent_curvature(self):
        from topogym.tasks.rope_threading.geometry import ThreadingLayout
        curvature, lengths = [], []
        for subdivisions in (4, 6, 8):
            curve = ThreadingLayout(rope_subdivisions=subdivisions,
                centerline_interpolation='circular_arc').centerline()
            edges = np.diff(curve, axis=0)
            length = np.linalg.norm(edges, axis=1)
            tangents = edges/length[:, None]
            angle = np.arccos(np.clip(np.sum(tangents[:-1]*tangents[1:], axis=1), -1, 1))
            values = angle/((length[:-1]+length[1:])/2)
            self.assertLess(np.ptp(values), 1.e-5)
            curvature.append(values.max())
            lengths.append(length.sum())
        self.assertLess(np.ptp(curvature), 1.e-4)
        self.assertLess(np.ptp(lengths), 5.e-6)
        self.assertLess(max(lengths)-1.1, .0001)

    def test_promoted_mesh_matches_previous_refinement_and_still_refines(self):
        from types import SimpleNamespace
        from topogym.tasks.rope_threading.physics_probe import make_config
        from topogym.tasks.rope_threading.qualification import physical_profile
        options = dict(dt=.005, robot_coupling='external_articulation', friction_eps=None,
                       young_modulus=None, contact_distance=None, initial_rope_lift=0., tighter=False)
        old = make_config(SimpleNamespace(config_name='rope_threading_deformation_damping20_preview',
                                          refined=True, **options))
        fine = make_config(SimpleNamespace(config_name='rope_threading_damped20_fine_preview',
                                           refined=False, **options))
        finer = make_config(SimpleNamespace(config_name='rope_threading_damped20_fine_preview',
                                            refined=True, **options))
        self.assertEqual(physical_profile(old), physical_profile(fine))
        self.assertEqual(finer.task.geometry.rope_subdivisions, 8)
        self.assertEqual(finer.task.geometry.radial_segments, 20)
        self.assertEqual(finer.task.rope.mesh.maxvolume, 5.e-9)

    def test_completion_waits_for_the_declared_settling_window(self):
        actions = ReferenceThreadingActions.__new__(ReferenceThreadingActions)
        actions.completion_time, actions.settle_s = None, 20.
        self.assertFalse(actions.finished(100.))
        actions.completion_time = 100.
        self.assertFalse(actions.finished(105.))
        self.assertFalse(actions.finished(119.99))
        self.assertTrue(actions.finished(120.))

    def test_release_requires_low_height_or_nearby_support(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from topogym.tasks.knot_untying.robot_probe import RobotGraspActions
        actions = ReferenceThreadingActions.__new__(ReferenceThreadingActions)
        actions.release_limits = dict(max_unsupported_height_m=.09, max_supported_material_span_m=.08)
        actions.release_checks, actions.material_nodes, actions.ring_indices = [], [0, 75, 77, 80], [0, 1, 2, 3]
        actions.material_arc = np.linspace(0., 1.1, 81)
        actions.monitor = SimpleNamespace(last_centers=np.array([[0., 0., .08]]*4), floor=0.)
        actions.task = SimpleNamespace(layout=SimpleNamespace(radius=.004))
        actions.owners = {3: "right"}
        with patch.object(RobotGraspActions, "release") as release:
            actions.release("right", 1.)
            self.assertTrue(actions.release_checks[-1]["passed"])
            release.assert_called_once()
            actions.monitor.last_centers[3, 2] = .33
            with self.assertRaisesRegex(RuntimeError, "qualified height"):
                actions.release("right", 2.)
            actions.owners[0] = "left"  # Opposite endpoint is too far to support this free tail.
            with self.assertRaisesRegex(RuntimeError, "qualified height"):
                actions.release("right", 3.)
            actions.owners = {1: "left", 3: "right"}  # Material node 75 is 68.75 mm from tip 80.
            actions.release("right", 4.)
            self.assertTrue(actions.release_checks[-1]["nearby_support"])

    def test_acquisition_holds_measured_aperture_on_the_contact_frame(self):
        from types import SimpleNamespace
        commands, captured = [.014], []
        arm = SimpleNamespace(gripper_qpos=lambda: [.012, .012],
            hand_pos=lambda: np.zeros(3), hand_quat=lambda: np.array([1., 0., 0., 0.]),
            set_gripper=commands.append)
        actions = ReferenceThreadingActions.__new__(ReferenceThreadingActions)
        actions.node_to_band = {80: 0}
        actions.controller = SimpleNamespace(arms={"right": arm})
        actions.gaps = lambda *args: [.0007, .00075]
        actions.contact_distance, actions.source_time, actions.wait_start = .0008, 16.82, 1.
        actions.bands = [SimpleNamespace(indices=np.array([0, 1]),
            _handle=SimpleNamespace(engage=captured.append), active=False)]
        actions.monitor = SimpleNamespace(last_positions=np.array([[.01, 0., 0.], [.02, 0., 0.]]))
        actions.finger_gaps, actions.offsets, actions.owners, actions.closed = {}, {}, {}, {}
        actions.adaptation_after_grasp, actions.pending_correction, actions.events = {}, {}, []
        actions.closure_targets = {"right": .0108}
        self.assertTrue(actions._acquire({"side": "right", "node": 80}, 2.))
        self.assertEqual(commands[-1], .012)
        self.assertEqual(actions.owners, {0: "right"})
        self.assertNotIn("right", actions.closure_targets)
        np.testing.assert_array_equal(captured[0], actions.monitor.last_positions)

    def test_contact_wait_integrates_closure_despite_servo_lag(self):
        from types import SimpleNamespace
        commands = []
        actions = ReferenceThreadingActions.__new__(ReferenceThreadingActions)
        actions.node_to_band = {80: 0}
        actions.controller = SimpleNamespace(arms={"right": SimpleNamespace(
            gripper_qpos=lambda: [.02], set_gripper=commands.append)})
        # A 0.3 mm gap is outside the new 0.2 mm contact range, even though
        # the historical 0.8 mm gate would already have accepted it.
        actions.gaps = lambda *args: [.0003, .0003]
        actions.finger_gaps, actions.closure_targets = {}, {}
        actions.contact_distance, actions.control_dt, actions.wait_start = .0002, .01, None
        for step in range(10):
            self.assertFalse(actions._acquire({"side": "right", "node": 80}, step*.01))
        self.assertAlmostEqual(commands[-1], .0196)
        self.assertTrue(all(a > b for a, b in zip(commands, commands[1:])))

    def test_grasp_audit_uses_measured_hand_frame_and_rejects_band_slip(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from topogym.tasks.knot_untying.robot_probe import RobotGraspActions, rotation
        quat = np.array([np.sqrt(.5), 0., 0., np.sqrt(.5)])
        hand = np.array([.1, .2, .3])
        offsets = np.array([[.01, 0., 0.], [.02, 0., 0.]])
        actions = ReferenceThreadingActions.__new__(ReferenceThreadingActions)
        actions.owners, actions.offsets = {0: "right"}, {0: offsets}
        actions.controller = SimpleNamespace(arms={"right": SimpleNamespace(
            hand_pos=lambda: hand, hand_quat=lambda: quat)})
        actions.bands = [SimpleNamespace(indices=np.array([0, 1]))]
        actions.task = SimpleNamespace(layout=SimpleNamespace(rings=lambda: [], radius=.004))
        actions.samples, actions.source_time, actions.max_follow_error = [], 0., 0.
        expected = hand+rotation(quat).apply(offsets)
        monitor = SimpleNamespace(last_positions=expected+[.001, 0, 0], last_centers=expected)
        with patch.object(RobotGraspActions, "observe", lambda self, *args: self.samples.append({})):
            actions.observe(.01, monitor)
            self.assertAlmostEqual(actions.max_follow_error, .001)
            monitor.last_positions = expected+[.003, 0, 0]
            with self.assertRaisesRegex(RuntimeError, "departed"):
                actions.observe(.02, monitor)

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
