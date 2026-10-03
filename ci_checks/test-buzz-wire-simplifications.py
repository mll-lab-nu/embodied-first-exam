#!/usr/bin/env python3
"""Geometry/initial-pose checks; these do not qualify a robot solution."""

from dataclasses import asdict
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.assets.geometry.buzz_wire_3d import SpatialWire, endpoint_pose
from topogym.assets.geometry.buzz_wire_3d_simplified import simplified_layout
from topogym.config.registry import seeded_variation, task_definition
from topogym.assets.library import resource_path


class SimplifiedBuzzWireChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.easy = task_definition("buzz_wire_3d", "easy")(seed=0)
        cls.reference = cls.easy.build_layout()
        cls.tasks = {level: task_definition("buzz_wire_3d", level)(seed=0)
                     for level in ("very_easy", "easier")}
        cls.routes = {level: SpatialWire(task.build_layout()) for level, task in cls.tasks.items()}

    def test_dimensions_endpoints_and_initial_pose_match_current_easy(self):
        reference_route = SpatialWire(self.reference)
        changed = {"authored_controls_m", "authored_section_ends",
                   "orientation_knots_wxyz", "center_offset_knots_m"}
        for level, route in self.routes.items():
            for name, value in asdict(self.reference).items():
                if name not in changed:
                    self.assertEqual(getattr(route.layout, name), value)
            np.testing.assert_allclose(route.rail[[0, -1]], reference_route.rail[[0, -1]], atol=1e-12)
            for end in (0, 1):
                p, r = endpoint_pose(route, end)
                old_p, old_r = endpoint_pose(reference_route, end)
                np.testing.assert_allclose(p, old_p, atol=1e-12)
                np.testing.assert_allclose(r.as_matrix(), old_r.as_matrix(), atol=1e-12)
            self.assertEqual(self.tasks[level].config, self.easy.config)
            self.assertEqual(self.tasks[level].terminal_revision, self.easy.terminal_revision)

    def test_middle_spans_have_the_requested_geometry(self):
        for level, route in self.routes.items():
            controls = np.asarray(route.layout.authored_controls_m)
            ends = dict(route.layout.authored_section_ends)
            name = "straight_span" if level == "very_easy" else "sideways_then_down"
            span = controls[ends["entry_elbow"]:ends[name]+1]
            self.assertTrue(np.all(np.diff(span[:, 0]) > 0))
            lateral = span[:, 1] - controls[0, 1]
            vertical = span[:, 2] - span[0, 2]
            if level == "very_easy":
                self.assertLess(np.max(abs(vertical)), 1e-12)
                self.assertLess(np.max(abs(lateral)), 1e-12)
            else:
                self.assertAlmostEqual(float(lateral.max()), .035, places=5)
                self.assertAlmostEqual(float(vertical.min()), -.035, places=5)
                self.assertGreaterEqual(float(lateral.min()), -1e-12)
                self.assertLessEqual(float(vertical.max()), 1e-12)
                # The first lobe stays horizontal; the second lies in XZ.
                self.assertTrue(np.all(lateral[1:120] > 0))
                np.testing.assert_allclose(vertical[:120], 0., atol=1e-12)
                np.testing.assert_allclose(lateral[181:], 0., atol=1e-12)
                self.assertTrue(np.all(vertical[181:-1] < 0))
                # The interpolated join itself must not introduce a kink or
                # a tighter bend than the old easy maze (checked below).
                np.testing.assert_allclose(span[0, 1:], span[-1, 1:], atol=1e-12)
            # These simpler paths have no tighter bend than the old easy maze.
            self.assertGreater(route.minimum_curvature_radius,
                               SpatialWire(self.reference).minimum_curvature_radius)
        self.assertLess(self.routes["very_easy"].length, self.routes["easier"].length)
        self.assertLess(self.routes["easier"].length, SpatialWire(self.reference).length)

    def test_shared_generator_produces_loadable_entities_and_metal_roles(self):
        with tempfile.TemporaryDirectory() as folder:
            for level, task in self.tasks.items():
                spec = task.declare(Path(folder)/level, .9196429)
                self.assertEqual([e.name for e in spec.entities], ["wire_base", "wire", "wand"])
                for entity in spec.entities:
                    root = ET.parse(entity.asset_path)
                    self.assertTrue(root.findall(".//collision"))
                    self.assertTrue(entity.contact_roles)
                    for mesh in root.findall(".//visual/geometry/mesh"):
                        self.assertTrue((Path(entity.asset_path).parent/mesh.attrib["filename"]).is_file())
                roles = {role for e in spec.entities for role in e.contact_roles.values()}
                self.assertTrue({"wire_metal", "wand_metal", "wand_handle", "finish_support"} <= roles)
                wand = spec.entities[-1]
                p, r = endpoint_pose(task.route, 0)
                np.testing.assert_allclose(wand.position_m, p+task.origin)
                np.testing.assert_allclose(wand.quaternion_wxyz, r.as_quat()[[3, 0, 1, 2]])

    def test_reference_is_unchanged_and_old_seed_mapping_is_preserved(self):
        before = asdict(self.reference)
        for level in self.tasks:
            self.assertEqual(json.loads(json.dumps(asdict(simplified_layout(self.reference, level)))),
                             json.loads(json.dumps(asdict(self.tasks[level].build_layout()))))
            resource = self.tasks[level].layout_resource
            self.assertNotEqual(resource, self.easy.layout_resource)
            self.assertIn(resource, self.tasks[level].resource_hashes)
            self.assertTrue(resource_path(resource).is_file())
        self.assertEqual(asdict(self.reference), before)
        self.assertEqual([seeded_variation("buzz_wire_3d", i)["difficulty"] for i in range(3)],
                         ["easy", "medium", "hard"])
        with self.assertRaises(ValueError):
            simplified_layout(self.reference, "hard")

    def test_finish_requires_history_release_support_and_contact_coverage(self):
        # Synthetic evaluator inputs test the inherited contract, not dynamics.
        for level, route in self.routes.items():
            task = task_definition("buzz_wire_3d", level)()
            task.layout, task.route, task.origin = route.layout, route, np.array([-.08, -.27, .92])
            task.table_height_m = .92
            task.rail = route.rail + task.origin
            p, r = endpoint_pose(route, 1)
            state = dict(physics_step=1, assist_active=False,
                bodies=dict(wand=dict(position_m=p+task.origin, quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]],
                    linear_velocity_m_s=np.zeros(3), angular_velocity_rad_s=np.zeros(3))),
                contact_events=dict(schema_version=1, physics_step=1, substeps_complete=True,
                    geometry_roles_complete=True,
                    events=[dict(role_a="wand_handle", role_b="finish_support", touching=True)]))
            history = task.initial_task_state(state)
            self.assertFalse(task.evaluate_transition(state, history)[0])
            history["traversal_complete"] = True
            self.assertTrue(task.evaluate_transition(state, history)[0])
            for change in ("held", "moving", "unsupported", "uncovered"):
                changed = deepcopy(state)
                if change == "held":
                    changed["assist_active"] = True
                elif change == "moving":
                    changed["bodies"]["wand"]["linear_velocity_m_s"] = [0., 0., .02]
                elif change == "unsupported":
                    changed["contact_events"]["events"] = []
                else:
                    changed["contact_events"]["substeps_complete"] = False
                self.assertFalse(task.evaluate_transition(changed, history)[0], (level, change))
            touched = deepcopy(state)
            touched["contact_events"]["events"].append(
                dict(role_a="wand_metal", role_b="wire_metal", touching=True))
            self.assertEqual(task.evaluate_transition(touched, history)[1], "wire_touched")


if __name__ == "__main__":
    unittest.main()
