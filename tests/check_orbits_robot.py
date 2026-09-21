"""Physical contact gates and coordinate parity for the Orbits robot runtime."""
from pathlib import Path
import tempfile
import unittest

from hydra import compose, initialize_config_dir
import mujoco
import numpy as np

from topogym.tasks.orbits.robot_dynamics import build_robot_model
from topogym.tasks.orbits.dynamics import natural_working_state, working_cord
from topogym.tasks.orbits.geometry import OrbitsLayout, winding_numbers
from topogym.tasks.orbits.robot_runtime import RobotRuntime
from topogym.tasks.orbits.workspace import WorkspaceAudit
from topogym.tasks.orbits.continuous_motion import cartesian_path


ROOT = Path(__file__).resolve().parents[1]


class RobotChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        with initialize_config_dir(config_dir=str(ROOT/'configs'), version_base='1.3'):
            cls.cfg = compose(config_name='orbits_preview')
        cls.model, _, cls.points, _ = build_robot_model(Path(cls.folder.name)/'model.xml', cls.cfg)
        cls.fixture = np.load(ROOT/'tests/fixtures/orbits/bilateral_contact_state.npz')

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()
        cls.folder.cleanup()

    def setUp(self):
        self.runtime = r = object.__new__(RobotRuntime)
        r.model = mujoco.MjModel.from_xml_path(str(Path(self.folder.name)/'model.xml'))
        r.data = mujoco.MjData(r.model)
        r.nodes = [r.model.site(f'node_{i}').id for i in range(len(self.points))]
        r.events = []
        r.frames = []
        r.folder = Path(self.folder.name)
        r.step_count = 0
        r.data.qpos[:] = self.fixture['qpos']
        r.data.time = float(self.fixture['time_s'])
        mujoco.mj_forward(r.model, r.data)

    def test_contact_gate_rejects_another_part_of_the_same_cord(self):
        r = self.runtime
        self.assertEqual(len(r.grasp_contacts('left', 'cord', node=114)), 2)
        active = r.data.eq_active.copy()
        with self.assertRaisesRegex(ValueError, 'bilateral contact missing'):
            r.engage_grasp('left', node=40)
        np.testing.assert_array_equal(active, r.data.eq_active)
        r.engage_grasp('left', node=114)
        r.engage_grasp('right')
        self.assertEqual(len([e for e in r.events if e['event']=='contact_gated_grasp_assist']), 2)

    def test_acquisition_does_not_jump_the_grasp_or_drive_rope_positions(self):
        r = self.runtime
        q = r.data.qpos.copy()
        r.engage_grasp('left', node=114)
        e = r.model.equality('grasp_bight').id
        np.testing.assert_allclose(r.data.site_xpos[r.model.eq_obj1id[e]],
                                   r.data.site_xpos[r.model.eq_obj2id[e]], atol=1e-12)
        np.testing.assert_array_equal(q, r.data.qpos)
        self.assertEqual(r.model.nmocap, 0)

    def test_each_arm_has_its_own_fold_binding_and_release(self):
        r = self.runtime
        for name, side in [('grasp_fold_0', 'left'), ('grasp_fold_1', 'right')]:
            e = r.model.equality(name).id
            body = r.model.site_bodyid[r.model.eq_obj1id[e]]
            self.assertEqual(r.model.body(body).name, side+'/gripper_link')
        for name in ('grasp_bight', 'grasp_fold_0', 'grasp_handle', 'grasp_fold_1'):
            r.data.eq_active[r.model.equality(name).id] = True
        r.release_grasp('left')
        self.assertFalse(r.data.eq_active[r.model.equality('grasp_bight').id])
        self.assertFalse(r.data.eq_active[r.model.equality('grasp_fold_0').id])
        self.assertTrue(r.data.eq_active[r.model.equality('grasp_handle').id])
        r.release_grasp('right')
        self.assertFalse(r.data.eq_active[r.model.equality('grasp_fold_1').id])

    def test_native_robot_and_workspace_ik_use_the_same_frame(self):
        r = self.runtime
        checker = WorkspaceAudit(self.cfg)
        checker.forward(r.data.qpos[:16])
        for side in ('left', 'right'):
            expected, _ = checker.pose(side)
            actual = checker.yaw.apply(r.data.site_xpos[r.model.site(side+'_tcp').id])+checker.origin
            np.testing.assert_allclose(actual, expected, atol=1e-10)
        np.testing.assert_allclose(r.points(), self.fixture['points'], atol=1e-12)

    def test_cartesian_preflight_never_actuates_a_rejected_path(self):
        r = self.runtime
        r.checker = WorkspaceAudit(self.cfg)
        r.checker.fixture = [part for part in r.checker.fixture
                             if part[0] not in ('cord', 'handle')]
        actuated = r.model.jnt_qposadr[r.model.actuator_trnid[:, 0]]
        r.data.ctrl[:] = r.data.qpos[actuated]
        before = (r.data.time, r.data.qpos.copy(), r.data.qvel.copy(), r.data.ctrl.copy())
        # An unreachable target must fail during planning, before native motion.
        with self.assertRaisesRegex(ValueError, 'IK|collision|branch'):
            cartesian_path(r, 'left', [2., 0., .2])
        self.assertEqual(r.data.time, before[0])
        for actual, expected in zip((r.data.qpos, r.data.qvel, r.data.ctrl), before[1:]):
            np.testing.assert_array_equal(actual, expected)

    def test_checkpoint_preserves_continued_dynamics_and_acquired_grasps(self):
        r = self.runtime
        r.engage_grasp('left', node=114)
        r.engage_grasp('right')
        actuated = r.model.jnt_qposadr[r.model.actuator_trnid[:, 0]]
        r.data.ctrl[:] = r.data.qpos[actuated]
        for _ in range(10):
            mujoco.mj_step(r.model, r.data)
        checkpoint = r.folder/'resume_test.npz'
        r.save_checkpoint(checkpoint)
        for _ in range(20):
            mujoco.mj_step(r.model, r.data)
        expected_q = r.data.qpos.copy()
        expected_v = r.data.qvel.copy()
        expected_active = r.data.eq_active.copy()
        r.release_grasp('left')
        r.model.site_pos[:] += .001
        r.restore_checkpoint(checkpoint)
        for _ in range(20):
            mujoco.mj_step(r.model, r.data)
        np.testing.assert_allclose(r.data.qpos, expected_q, atol=1e-12, rtol=0)
        np.testing.assert_allclose(r.data.qvel, expected_v, atol=1e-12, rtol=0)
        np.testing.assert_array_equal(r.data.eq_active, expected_active)

    def test_natural_slack_keeps_length_and_trapping_without_terminal_backtracking(self):
        layout = OrbitsLayout().scaled(.75)
        points, handle = natural_working_state(layout)
        old = working_cord(layout, spacing=.0075)
        self.assertAlmostEqual(np.linalg.norm(np.diff(points, axis=0), axis=1).sum(),
                               np.linalg.norm(np.diff(old, axis=0), axis=1).sum(), places=10)
        self.assertEqual(len(points) % 2, 1)
        midpoint = len(points)//2
        self.assertTrue(np.all(np.diff(points[:midpoint+1, 0]) <= 1e-12))
        self.assertTrue(np.all(np.diff(points[midpoint:, 0]) >= -1e-12))
        self.assertLess(points[:, 0].max(), handle[0])
        np.testing.assert_allclose(winding_numbers(points, layout.post_x),
                                   [0, 0, 0, 0, -1], atol=1e-12)

    def test_moving_initial_handle_preserves_both_physical_terminal_attachments(self):
        points, handle = natural_working_state(OrbitsLayout().scaled(.75))
        model, data, _, _ = build_robot_model(Path(self.folder.name)/'natural.xml', self.cfg,
                                               initial_points=points, handle_position=handle)
        self.assertEqual(model.joint('handle_free').type[0], mujoco.mjtJoint.mjJNT_FREE)
        self.assertFalse(data.eq_active[model.equality('grasp_handle').id])
        for name in ('terminal_0', 'terminal_1'):
            e = model.equality(name).id
            np.testing.assert_allclose(data.site_xpos[model.eq_obj1id[e]],
                                       data.site_xpos[model.eq_obj2id[e]], atol=1e-12)
        np.testing.assert_allclose(data.xpos[model.body('handle').id], handle, atol=1e-12)


if __name__ == '__main__':
    unittest.main()
