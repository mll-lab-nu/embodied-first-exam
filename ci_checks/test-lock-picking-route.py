#!/usr/bin/env python3
"""Adversarial checks of the continuous lock certificate; no physics claim."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.assets.geometry.lock_picking import LockGeometry
from topogym.config.registry import task_definition
from topogym.planning.lock_picking.object_route import construct_route, audit_route, sample_route


def problem(variant):
    task = task_definition("lock_picking", variant)(seed=0)
    return LockGeometry(**task.config["geometry"]), task.config["rotor_stops"]


class LockRouteChecks(unittest.TestCase):
    def test_current_variants_continuous_and_independent_dense_geometry(self):
        for variant, count, total in (("easy", 1, 30.), ("medium", 2, 60.), ("hard", 3, 72.)):
            with self.subTest(variant=variant):
                g, stops = problem(variant)
                route = construct_route(g, stops)
                report = audit_route(g, stops, route)
                self.assertEqual(report["retreats"], count)
                self.assertEqual(report["lower_bound"]["minimum_required_retreats"], count)
                self.assertEqual(route[-1]["disc_deg"], [0., total, 0.])
                self.assertAlmostEqual(report["minimum_rotor_stop_margin_deg"], 1.)
                self.assertGreater(report["final_leading_tab_clearance_m"], .001)
                for state in sample_route(g, route, translation_step_m=.0005, angle_step_deg=.25):
                    self.assertFalse(g.clearance(state["depth"], state["key_deg"], state["disc_deg"], tolerance=1e-9))

    def test_free_endpoints_do_not_hide_a_blocked_insertion(self):
        g, stops = problem("medium")
        route = [dict(phase="start", depth=0., key_deg=0., disc_deg=[0.,0.,0.]),
                 dict(phase="end", depth=4.08, key_deg=0., disc_deg=[0.,0.,0.])]
        self.assertFalse(g.clearance(0., 0., [0.,0.,0.]))
        self.assertFalse(g.clearance(4.08, 0., [0.,0.,0.]))
        with self.assertRaisesRegex(ValueError, "Blocked continuous segment"):
            audit_route(g, stops, route)

    def test_disengaged_rotor_cannot_be_actuated(self):
        g, stops = problem("easy")
        route = construct_route(g, stops)
        for state in route[1:]:
            state["disc_deg"][2] = .1
        with self.assertRaisesRegex(ValueError, "Disengaged rotor moved"):
            audit_route(g, stops, route)

    def test_centered_slot_motion_is_not_sidewall_driving(self):
        g, stops = problem("medium")
        route = construct_route(g, stops)
        # Removing take-up keeps waypoints collision-free, but leaves part of
        # a moving-rotor interval without sidewall contact.
        del route[4]
        with self.assertRaisesRegex(ValueError, "without a driving key sidewall"):
            audit_route(g, stops, route)

    def test_stop_violation_and_incomplete_insertion(self):
        g, stops = problem("hard")
        route = construct_route(g, stops)
        damaged = deepcopy(route)
        damaged[5]["disc_deg"][0] = 13.
        with self.assertRaisesRegex(ValueError, "Rotor stop exceeded"):
            audit_route(g, stops, damaged)
        with self.assertRaisesRegex(ValueError, "has not cleared END"):
            audit_route(g, stops, route[:-1])

    def test_nonfinite_route_is_rejected(self):
        g, stops = problem("easy")
        route = construct_route(g, stops)
        route[2]["key_deg"] = float("nan")
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            audit_route(g, stops, route)


if __name__ == "__main__":
    unittest.main()
