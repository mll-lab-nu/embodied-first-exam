"""Candidate crossing layouts: geometry and declarations, no solve qualification."""
from dataclasses import replace
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.assets.geometry.knot_untying import (
    KnotLayout, generate_assets, inspect_geometry, template_diagram_matches,
)
from topogym.config.registry import task_definition, variation_registration, seeded_variation
from topogym.config.scene import load_scene_config
from topogym.simulator import SimulatorConfig


class SimplifiedGeometryTest(unittest.TestCase):
    def test_crossing_count_order_and_clearance(self):
        for family, count, word in (("single_overlap_loop", 1, ["O", "U"]),
                                   ("alternating_overlap_loop", 2, ["U", "O", "U", "O"])):
            layout = KnotLayout(family=family)
            for hand in ("right", "left"):
                with self.subTest(family=family, hand=hand):
                    mirrored = replace(layout, handedness=hand)
                    report = inspect_geometry(mirrored.centerline(), mirrored)
                    self.assertEqual(report["crossing_count"], count)
                    self.assertEqual(report["over_under"], word)
                    self.assertTrue(report["authored_projection_verified"])
                    self.assertFalse(report["knot_diagram_verified"])
                    self.assertGreater(report["minimum_nonlocal_surface_gap_m"], .001)
                    self.assertGreater(report["minimum_bend_radius_m"], 2*layout.rope_radius_m)
                    self.assertAlmostEqual(report["table_surface_clearance_m"], .001)

    def test_same_tail_above_is_not_alternating(self):
        layout = KnotLayout(family="two_overlap_loop")
        report = inspect_geometry(layout.centerline(), layout)
        self.assertFalse(template_diagram_matches(report["crossings"], "alternating_overlap_loop"))
        layout = KnotLayout(family="alternating_overlap_loop")
        report = inspect_geometry(layout.centerline(), layout)
        self.assertFalse(template_diagram_matches(report["crossings"], "two_overlap_loop"))

    def test_assets_have_two_free_ends_and_no_physics_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            for family in ("single_overlap_loop", "alternating_overlap_loop"):
                _, report = generate_assets(Path(folder)/family, KnotLayout(family=family))
                self.assertEqual(report["physical_components"], 1)
                self.assertEqual(report["physical_endpoints"], 2)
                self.assertTrue(report["watertight"])
                self.assertFalse(report["physics_qualified"])

    def test_existing_scene_and_terminal_defaults_inherited(self):
        from omegaconf import OmegaConf
        easy = task_definition("knot_untying", "easy")
        baseline = load_scene_config(SimulatorConfig(task_id="knot_untying", variation_id="easy"))
        for tier in ("very_easy", "easier"):
            cls = task_definition("knot_untying", tier)
            self.assertEqual(cls.defaults, {**easy.defaults, "geometry": {"family": cls.family_id}})
            self.assertIs(cls.declare, easy.declare)
            self.assertIs(cls.evaluate_state, easy.evaluate_state)
            scene = load_scene_config(SimulatorConfig(task_id="knot_untying", variation_id=tier))
            self.assertEqual(OmegaConf.to_container(scene), OmegaConf.to_container(baseline))
            self.assertEqual(variation_registration("knot_untying", tier)["pool"], "below_easy")
            self.assertEqual(cls.difficulty, tier)
        self.assertEqual(variation_registration("knot_untying", "base")["variation_id"], "knot_untying_easy")
        for seed in range(9):
            self.assertEqual(seeded_variation("knot_untying", seed)["difficulty"], ("easy", "medium", "hard")[seed % 3])

    def test_reference_actions_distinguish_one_curl_from_two_twists(self):
        import numpy as np
        from topogym.planning.knot_untying.route_rule import only_local_loops, choose
        for family, local in (("single_overlap_loop", True), ("alternating_overlap_loop", False)):
            layout = KnotLayout(family=family)
            line = layout.centerline()
            stations = np.r_[0., np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
            report = inspect_geometry(line, layout)
            self.assertEqual(only_local_loops(report["crossings"], stations), local)
            if not local:
                plan = choose(line, stations, report["crossings"], stations[-1])
                self.assertIsNotNone(plan)
                self.assertTrue(np.isfinite(plan["direction"]).all())

    def test_pickup_selection_tries_the_other_end_without_executing_actions(self):
        import numpy as np
        from types import SimpleNamespace
        from unittest.mock import Mock
        from topogym.planning.knot_untying.route_rule import choose
        from topogym.planning.knot_untying.simplified_policy import reachable_withdrawal
        layout = KnotLayout(family="alternating_overlap_loop")
        line = layout.centerline()
        stations = np.r_[0., np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
        crossing = inspect_geometry(line, layout)['crossings']
        first = choose(line, stations, crossing, stations[-1])
        def pose(side, station):
            if station == first['s_pull']:
                raise ValueError('preferred pickup is unreachable')
        runner = SimpleNamespace(line=lambda: line, crossings=lambda _: crossing, stations=stations,
            length=stations[-1], arms_for=lambda _: ('left', 'right'),
            grasp_site=lambda station: (station, .038), pose=Mock(side_effect=pose), step=Mock())
        selected = reachable_withdrawal(runner, dict(hold='far', direction='tangent'))
        self.assertNotEqual(selected['end'], first['end'])
        self.assertEqual(len(selected['pickup_selection']['rejected_candidates']), 1)
        runner.step.assert_not_called()
        runner.pose.side_effect = ValueError('all pickup poses unreachable')
        with self.assertRaisesRegex(ValueError, 'No reachable node-deletion'):
            reachable_withdrawal(runner, dict(hold='far', direction='tangent'))
        runner.step.assert_not_called()


if __name__ == "__main__":
    unittest.main()
