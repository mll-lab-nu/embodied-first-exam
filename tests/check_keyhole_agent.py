"""Keyhole task boundary, private geometry verdict, shared adapter selection."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from hydra import compose, initialize_config_dir
import numpy as np
import trimesh

from topogym.agent_bridge.registry import TASKS, factory_for
from topogym.agent_bridge.robot_adapter import AlohaRigidAdapter
from topogym.tasks.cast_keyhole.agent_adapter import KeyholeAdapter
from topogym.tasks.cast_keyhole.agent_spec import describe_task
from topogym.tasks.cast_keyhole.collision import CompoundCollision
from topogym.tasks.horseshoe_ring.agent_adapter import HorseshoeAdapter
from topogym.world.aloha_cameras import configure_aloha_rig

ROOT = Path(__file__).resolve().parents[1]


class KeyholeChecks(unittest.TestCase):
    def test_task_geometry_and_solution_paths_do_not_enter_public_spec(self):
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            cfg = compose(config_name="cast_keyhole_aloha")
        configure_aloha_rig(cfg, keep=(), resolution=(640, 360), low_pitch_offset_deg=20)
        before = describe_task(cfg)
        cfg.task.scale, cfg.task.center_xy_m, cfg.task.yaw_deg = 99, [99, 99], 99
        self.assertEqual(before, describe_task(cfg))
        self.assertEqual(len(before["cameras"]), 4)
        self.assertFalse(before["perception"]["reference_images_provided"])
        self.assertNotIn("goal_reference", before)
        self.assertIn("不要求放回桌面", before["task_goal"])

    def test_both_tasks_share_runtime_and_registry_is_transport_independent(self):
        self.assertTrue(issubclass(KeyholeAdapter, AlohaRigidAdapter))
        self.assertTrue(issubclass(HorseshoeAdapter, AlohaRigidAdapter))
        self.assertIs(KeyholeAdapter.step, HorseshoeAdapter.step)
        self.assertIn("cast_keyhole", TASKS)
        self.assertEqual(factory_for("cast_keyhole", "cpu", "rasterizer").func.__module__,
                         "topogym.tasks.cast_keyhole.agent_adapter")
        self.assertEqual(factory_for("cast_coil", "cpu", "rasterizer", objective="disassemble").keywords["objective"], "disassemble")
        tree = ast.parse((ROOT/"topogym/agent_bridge/robot_adapter.py").read_text())
        self.assertFalse(any(isinstance(n, ast.ImportFrom) and n.module and "topogym.tasks" in n.module for n in ast.walk(tree)))

    def test_sat_detects_containment_and_stability_does_not_require_release(self):
        class Body:
            def __init__(self, idx, pos):
                self.base_link_idx, self.pos = idx, np.array(pos, dtype=float)
                self.vel = np.zeros(3)
            def get_pos(self): return self.pos
            def get_quat(self): return np.array([1., 0., 0., 0.])
            def get_vel(self): return self.vel
            def get_ang(self): return np.zeros(3)
        adapter = KeyholeAdapter.__new__(KeyholeAdapter)
        gold, silver = Body(10, [0, 0, .2]), Body(11, [.2, 0, .2])
        adapter.task = SimpleNamespace(bodies=dict(keyhole_gold=gold, keyhole_silver=silver),
            tabletop=SimpleNamespace(frames=SimpleNamespace(table_surface_origin=[0, 0, 0])))
        adapter.bodylinks, adapter.robotlinks, adapter.table = {10, 11}, {20, 21}, 30
        adapter.registrations = [(20, 10), (21, 11)]  # Held is a legitimate terminal state.
        adapter.collision = CompoundCollision([trimesh.creation.box(extents=[.1]*3)],
                                             [trimesh.creation.box(extents=[.02]*3)])
        contacts = dict(link_a=np.array([], dtype=int), link_b=np.array([], dtype=int), penetration=np.array([]))
        self.assertEqual(adapter._failure_and_goal(contacts), (None, True))
        silver.vel[0] = .1
        self.assertEqual(adapter._failure_and_goal(contacts), (None, False))
        silver.vel[0] = 0
        silver.pos[0] = .07  # Only 1 cm gap: separated but below the goal margin.
        self.assertEqual(adapter._failure_and_goal(contacts), (None, False))
        silver.pos[0] = 0  # Full containment must fail despite absent surface intersections.
        self.assertIn("SAT", adapter._failure_and_goal(contacts)[0])
        silver.pos[2] = -.2
        self.assertIn("fell", adapter._failure_and_goal(contacts)[0])
        silver.pos[2] = float("nan")
        self.assertIn("Non-finite", adapter._failure_and_goal(contacts)[0])


if __name__ == "__main__":
    unittest.main()
