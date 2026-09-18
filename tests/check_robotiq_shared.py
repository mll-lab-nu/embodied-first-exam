"""Shared task selection, articulated asset and metric gripper API contracts."""

import unittest
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from hydra import compose, initialize_config_dir
from topogym.robot.assets import robot_asset, ROOT
from topogym.robot.gripper import robotiq_joint_targets
from topogym.robot.franka import FrankaPositionIKController
from topogym.data.episode_dataset_writer import _proprio


TASKS = (
    "presentation_preview",
    "lock_picking_baseline",
    "lock_picking_spaced_preview",
    "hedgehog_in_cage_classic_preview",
)


class SharedRobotiqTests(unittest.TestCase):
    def test_proprio_uses_arm_joints_and_measured_metric_aperture(self):
        with initialize_config_dir(
            config_dir=str(ROOT / "configs"), version_base="1.3"
        ):
            cfg = compose(config_name="lock_picking_baseline")
        model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
        data = mujoco.MjData(model)
        data.qpos[:7] = np.asarray(cfg.robot_control.home.qpos[:7])
        data.qpos[7:] = list(robotiq_joint_targets(0.025).values())
        mujoco.mj_forward(model, data)

        def joint(name):
            j = model.joint(name)
            return SimpleNamespace(dofs_idx_local=j.dofadr, qs_idx_local=j.qposadr)

        def link(name):
            body = data.body(name)
            return SimpleNamespace(
                get_pos=lambda: body.xpos, get_quat=lambda: body.xquat
            )

        robot = SimpleNamespace(
            n_qs=model.nq, get_qpos=lambda: data.qpos, get_joint=joint, get_link=link
        )
        controller = FrankaPositionIKController(
            SimpleNamespace(dt=0.005), robot, cfg.robot_control
        )
        obs = _proprio(controller)
        np.testing.assert_allclose(obs["joint_state"], data.qpos[:7], atol=1e-7)
        np.testing.assert_allclose(obs["gripper_state"], [0.025, 0.025], atol=0.0008)
        self.assertEqual(obs["eef_state"].shape, (7,))
        self.assertEqual(controller.gripper_dofs, [7, 11])

    def test_all_task_presets_select_the_same_tool(self):
        paths = set()
        with initialize_config_dir(
            config_dir=str(ROOT / "configs"), version_base="1.3"
        ):
            for name in TASKS:
                cfg = compose(config_name=name)
                self.assertEqual(
                    cfg.robot_control.robot.tool_model, "robotiq_2f85", name
                )
                paths.add(robot_asset(cfg.robot_control))
        self.assertEqual(len(paths), 1)

    def test_articulated_model_preserves_arm_and_contact_aliases(self):
        with initialize_config_dir(
            config_dir=str(ROOT / "configs"), version_base="1.3"
        ):
            cfg = compose(config_name="lock_picking_baseline")
        path = robot_asset(cfg.robot_control)
        tree = ET.parse(path)
        m = mujoco.MjModel.from_xml_path(path)
        self.assertEqual(m.nq, 15)
        self.assertEqual(m.neq, 3)
        self.assertEqual(
            [m.joint(i).name for i in range(7)],
            list(cfg.robot_control.robot.joint_names[:7]),
        )
        for name in ("hand", "tool_mount", "left_finger", "right_finger"):
            self.assertIsNotNone(tree.find(f".//body[@name='{name}']"))
        used = [geom.get("mesh", "") for geom in tree.findall(".//worldbody//geom")]
        self.assertFalse(any(name.startswith(("hand_", "finger_")) for name in used))
        self.assertTrue(any(name.startswith("r85_base") for name in used))
        self.assertEqual(len(tree.findall("equality/connect")), 2)
        self.assertEqual(len(tree.findall("contact/exclude")), 6)

    def test_width_commands_are_metric_and_monotone(self):
        values = [
            robotiq_joint_targets(w)["right_driver_joint"]
            for w in np.linspace(0, 0.04, 21)
        ]
        self.assertTrue(all(a > b for a, b in zip(values, values[1:])))
        self.assertTrue(all(0 <= a <= 0.8 for a in values))
        self.assertGreater(values[0], 0.75)
        self.assertLess(values[-1], 0.1)

    def test_explicit_panda_fallback_is_available(self):
        with initialize_config_dir(
            config_dir=str(ROOT / "configs"), version_base="1.3"
        ):
            cfg = compose(
                config_name="lock_picking_baseline",
                overrides=["common.robot_setup.gripper_model=panda"],
            )
        self.assertEqual(
            robot_asset(cfg.robot_control), "xml/franka_emika_panda/panda.xml"
        )


if __name__ == "__main__":
    unittest.main()
