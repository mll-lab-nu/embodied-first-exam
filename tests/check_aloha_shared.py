"""ALOHA assets, paired presets and independent control without a GPU."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hydra import compose, initialize_config_dir
import mujoco
import numpy as np

from topogym.robot import AlohaDualArmController, initialize_robot_controller
from topogym.robot.assets import robot_asset
from topogym.world.tabletop import StandardTabletopSceneBuilder

ROOT = Path(__file__).resolve().parents[1]


class AlohaChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
            cls.cfg = compose(config_name="aloha_lab_preview")
            cls.single = compose(config_name="presentation_preview")
        cls.model = mujoco.MjModel.from_xml_path(robot_asset(cls.cfg.robot_control))

    def test_vendored_files_match_pinned_source(self):
        folder = ROOT / "assets/robots/aloha"
        for name, digest in json.loads((folder / "source.json").read_text())["sha256"].items():
            path = folder / ("UPSTREAM_README.md" if name == "README.md" else name)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, name)

    def test_adapter_preserves_articulation_and_physical_properties(self):
        source = mujoco.MjModel.from_xml_path(str(ROOT / "assets/robots/aloha/aloha.xml"))
        model = self.model
        self.assertEqual((model.nq, model.nu, model.neq), (16, 14, 2))
        for field in ("jnt_range", "dof_damping", "dof_armature", "body_mass", "body_inertia",
                      "actuator_gainprm", "actuator_ctrlrange", "eq_data", "mesh_vert"):
            np.testing.assert_allclose(getattr(model, field), getattr(source, field), atol=1e-7)
        for side in ("left", "right"):
            np.testing.assert_allclose(model.body(f"{side}/base_link").pos,
                                       source.body(f"{side}/base_link").pos - [0, 0, 0.02])
            for name in self.cfg.robot_control.robot.arm_joint_names:
                self.assertEqual(model.joint(f"{side}/{name}").name, f"{side}/{name}")

    def test_both_base_meshes_fit_the_checked_footprint(self):
        builder = StandardTabletopSceneBuilder(self.cfg.env, self.cfg.robot_control)
        builder._validate_locked_preset()
        footprint = builder._validate_geometry(builder._frames())
        self.assertGreater(min(footprint.clearance_xy), 0.08)
        model, data = self.model, mujoco.MjData(self.model)
        mujoco.mj_forward(model, data)
        mount = np.asarray(self.cfg.env.robot_mount.pos)
        for side in ("left", "right"):
            body = model.body(f"{side}/base_link")
            geom_id = int(body.geomadr[0])
            mesh = model.mesh(model.geom_dataid[geom_id])
            vertices = model.mesh_vert[mesh.vertadr[0]:mesh.vertadr[0] + mesh.vertnum[0]]
            world = vertices @ data.geom_xmat[geom_id].reshape(3, 3).T + data.geom_xpos[geom_id] + mount
            self.assertTrue(np.all(world[:, :2].min(0) >= footprint.footprint_min_xy))
            self.assertTrue(np.all(world[:, :2].max(0) <= footprint.footprint_max_xy))
            self.assertAlmostEqual(world[:, 2].min(), mount[2], places=6)

    def test_mismatched_single_and_dual_presets_fail_early(self):
        for env, robot in ((self.single.env, self.cfg.robot_control),
                           (self.cfg.env, self.single.robot_control)):
            with self.assertRaisesRegex(ValueError, "paired"):
                StandardTabletopSceneBuilder(env, robot)._validate_locked_preset()
        StandardTabletopSceneBuilder(self.single.env, self.single.robot_control)._validate_locked_preset()

    def controller(self):
        model, data = self.model, mujoco.MjData(self.model)
        mujoco.mj_resetDataKeyframe(model, data, 0)
        mujoco.mj_forward(model, data)

        def joint(name):
            joint = model.joint(name)
            return SimpleNamespace(dofs_idx_local=joint.dofadr, qs_idx_local=joint.qposadr)

        def link(name):
            return SimpleNamespace(get_pos=lambda: data.body(name).xpos,
                                   get_quat=lambda: data.body(name).xquat)

        robot = Mock(n_qs=model.nq, get_joint=joint, get_link=link, get_qpos=lambda: data.qpos)
        return AlohaDualArmController(Mock(), robot, self.cfg.robot_control), data

    def test_right_joint_and_gripper_commands_do_not_control_left(self):
        controller, data = self.controller()
        data.qpos[8:14] += 0.01
        np.testing.assert_allclose(controller.right.arm_qpos(), data.qpos[8:14])
        np.testing.assert_allclose(controller.left.arm_qpos(), data.qpos[:6])
        controller.right.set_arm_qpos(data.qpos[8:14])
        self.assertEqual(controller.robot.control_dofs_position.call_args.args[1], list(range(8, 14)))
        controller.right.open_gripper()
        args = controller.robot.control_dofs_position.call_args.args
        self.assertEqual(args, ([0.037], [14]))  # passive finger 15 is not driven
        controller.scene.step.assert_not_called()
        controller.right.close_gripper(steps=3)
        self.assertEqual(controller.scene.step.call_count, 3)
        with self.assertRaises(ValueError):
            controller.left.set_arm_qpos([0, 8, 0, 0, 0, 0])
        with self.assertRaises(ValueError):
            controller.right.set_gripper(float("nan"))

    def test_dual_home_resets_both_before_one_settle_loop(self):
        controller, _ = self.controller()
        events = []
        controller.robot.set_dofs_position.side_effect = lambda *a, **kw: events.append("reset")
        controller.scene.step.side_effect = lambda: events.append("step")
        controller.reset_home(settle_steps=2)
        self.assertEqual(events, ["reset", "reset", "step", "step"])

    def test_ik_slices_right_arm_solution_by_named_joint_indices(self):
        controller, data = self.controller()
        controller.robot.inverse_kinematics.return_value = data.qpos.copy()
        result = controller.right.move_ee_to([0, 0, 1.2])
        np.testing.assert_allclose(result, data.qpos[8:14])
        self.assertEqual(controller.robot.inverse_kinematics.call_args.kwargs["dofs_idx_local"],
                         list(range(8, 14)))
        self.assertEqual(controller.robot.control_dofs_position.call_args.args[1], list(range(8, 14)))

    def test_factory_retains_single_arm_controller(self):
        with patch("topogym.robot.factory.FrankaPositionIKController") as single:
            manifest, scene = Mock(), Mock()
            result = initialize_robot_controller(scene=scene, manifest=manifest,
                                                robot_cfg=self.single.robot_control, settle_steps=0)
            self.assertIs(result, single.return_value)
            single.return_value.reset_home.assert_called_once_with(settle_steps=0)


if __name__ == "__main__":
    unittest.main()
