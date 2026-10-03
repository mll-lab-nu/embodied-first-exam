#!/usr/bin/env python3
"""Two-rotor scene and clearance checks; these do not qualify robot dynamics."""
from pathlib import Path
from copy import deepcopy
import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.assets.geometry.lock_picking import LockGeometry
from topogym.config.registry import task_definition, seeded_variation
from topogym.tasks.goal_description import describe_goal
from topogym.tasks.lock_picking.common import recommended_grasp_assist


class SimplifiedLockChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.tasks, cls.specs = {}, {}
        for variant in ("very_easy", "easier"):
            task = task_definition("lock_picking", variant)(seed=0)
            cls.tasks[variant] = task
            cls.specs[variant] = task.declare(Path(cls.directory.name)/variant, .9196429)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_exactly_two_rotors_and_two_tabs(self):
        for variant, task in self.tasks.items():
            names = [e.name for e in self.specs[variant].entities]
            self.assertEqual([n for n in names if n.startswith("lock_disc_")],
                             ["lock_disc_0", "lock_disc_1"])
            key = next(e for e in self.specs[variant].entities if e.name == "lock_key")
            # One shaft, two tabs, one handle; each has its own collision piece.
            self.assertEqual(len(ET.parse(key.asset_path).findall(".//collision")), 4)
            self.assertEqual(task.layout.disc_count, 2)

    def test_straight_route_requires_only_first_rotor_alignment(self):
        for variant, task in self.tasks.items():
            g = task.layout
            initial = g.initial_disc_deg
            blocked = g.clearance(1., 0., initial)
            self.assertEqual(bool(blocked), variant == "easier")
            if blocked:
                self.assertEqual(blocked, ["tab0/disc0"])
            # Scan the insertion route after alignment, including all face crossings.
            for depth in np.linspace(0., 3.08, 1541):
                self.assertEqual(g.clearance(depth, 0., [0., 0.]), [])
            self.assertLess(g.slot_margin(0., 20., 0), 0)

    def test_initial_scene_unsolved_and_terminal_uses_three_plates(self):
        for variant, task in self.tasks.items():
            g = task.layout
            key = next(e for e in self.specs[variant].entities if e.name == "lock_key")
            state = {"bodies": {"lock_key": {"position_m": list(key.position_m),
                     "quaternion_wxyz": [1., 0., 0., 0.]}}, "articulations": {
                     f"lock_disc_{i}": {"joints": {"disc_hinge": {"position": [np.radians(a)]}}}
                     for i, a in enumerate(g.initial_disc_deg)}}
            self.assertFalse(task.evaluate_state(state)[0])
            state["bodies"]["lock_key"]["position_m"] = [g.disc_x(2)+.012, g.center_y, g.axis_z]
            for disc in state["articulations"].values():
                disc["joints"]["disc_hinge"]["position"] = [0.]
            reached, failure, metrics = task.evaluate_state(state)
            self.assertTrue(reached, metrics)
            self.assertIsNone(failure)
            # Placing only the tip at END still fails the full-shaft requirement.
            state["bodies"]["lock_key"]["position_m"][0] = g.grip_offset+.03
            self.assertFalse(task.evaluate_state(state)[0])
            public = describe_goal(task)
            self.assertIn("two rotor plates", public["summary"])
            self.assertIn("all three plates", " ".join(public["success_conditions"]))

    def test_old_geometry_and_seeded_pool_keep_three_rotors(self):
        self.assertEqual(LockGeometry.disc_count, 3)
        self.assertEqual(LockGeometry.tab_count, 3)
        for seed, tier in enumerate(("easy", "medium", "hard")):
            self.assertEqual(seeded_variation("lock_picking", seed)["difficulty"], tier)

    def test_handle_grasp_tracks_shorter_key_and_preserves_old_tiers(self):
        for variant in ("very_easy", "easier", "easy", "medium", "hard"):
            task = task_definition("lock_picking", variant)(seed=0)
            grasp = recommended_grasp_assist(variant)
            self.assertEqual(grasp.model, "contact_weld_v1")
            self.assertEqual(grasp.stable_time_s, .05)
            self.assertEqual(len(grasp.targets), 1)
            target = grasp.targets[0]
            self.assertEqual((target.entity, target.link), ("lock_key", "key"))
            self.assertEqual(target.center_m, (-task.config["geometry"]["grip_offset"], 0., 0.))
            self.assertEqual(target.radius_m, .032)

    def test_package_configuration_and_plate_count(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("lock_packaging_tool",
            root/"harbor_templates/topogym/common/rcb_topogym.py")
        tool = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = tool
        spec.loader.exec_module(tool)
        sys.path.insert(0, str(root/"scripts"))
        from topogym_rules import details_section
        for variant in ("very_easy", "easier"):
            cfg = tool.simulator_config("lock_picking", variation_id=variant, seed=0)
            self.assertEqual(cfg["grasp_assist"]["targets"][0]["center_m"], [-.345, 0., 0.])
            task = self.tasks[variant]
            text = details_section("lock_picking", {"simulator": cfg,
                "effective_task_parameters": task.config}, limited=True)
            self.assertIn("6 plate faces (two", text)
            self.assertNotIn("all 8 plate faces", text)
            self.assertIn("365 mm behind", text)
            if variant == "easier":
                self.assertIn("23 degrees toward the second rotor's slot (20 degrees aligns the slots), or 3 degrees away", text)

    def test_terminal_requires_full_confirmation_and_rejects_wrong_pose(self):
        for variant, original in self.tasks.items():
            task = task_definition("lock_picking", variant)(seed=0)
            g = original.layout
            task.layout, task.table_height_m = g, original.table_height_m
            state = {"physics_step": 0, "bodies": {"lock_key": {
                "position_m": [g.disc_x(2)+.012, g.center_y, g.axis_z],
                "quaternion_wxyz": [1., 0., 0., 0.]}}, "articulations": {
                f"lock_disc_{i}": {"joints": {"disc_hinge": {"position": [0.]}}} for i in range(2)}}
            task.initialize(state)
            self.assertFalse(task.result.task_success)
            for step in range(1, 21):
                state["physics_step"] = step
                self.assertFalse(task.update(state, .025).task_success)
            state["physics_step"] = 21
            self.assertTrue(task.update(state, .025).task_success)
            blocked = deepcopy(state)
            blocked["bodies"]["lock_key"]["position_m"][0] = g.first_x
            blocked["articulations"]["lock_disc_0"]["joints"]["disc_hinge"]["position"] = [np.radians(20.)]
            self.assertFalse(task.evaluate_state(blocked)[0])
            beyond = deepcopy(state)
            beyond["articulations"]["lock_disc_1"]["joints"]["disc_hinge"]["position"] = [np.radians(4.)]
            self.assertEqual(task.evaluate_state(beyond)[1], "rotor_limit_exceeded")


if __name__ == "__main__":
    unittest.main()
