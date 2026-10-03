#!/usr/bin/env python3
"""Oracle route/acceptance contract checks; no claim of physical execution."""
from dataclasses import asdict
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.config.registry import task_definition
from topogym.planning.lock_picking.simplified_policy import SimplifiedLockPickingPolicy
from topogym.planning.lock_picking.robot_audit import completion_errors, simplified_acquisition_rows


def policy(variation, **kwargs):
    task = task_definition("lock_picking", variation)(seed=0)
    return SimplifiedLockPickingPolicy(geometry=asdict(task.geometry_type(**task.config["geometry"])),
        rotor_stops=task.config["rotor_stops"], part="solve", **kwargs)


class OracleChecks(unittest.TestCase):
    def test_old_three_rotor_scenes_and_unsafe_depth_rejected(self):
        for variant in ("easy", "medium", "hard"):
            with self.assertRaises(ValueError):
                policy(variant)
        for depth in (3., 4.08, float("nan")):
            with self.assertRaises(ValueError):
                policy("very_easy", endpoint_depth=depth)

    def test_first_turn_precedes_two_rotor_insertion(self):
        for variation in ("very_easy", "easier"):
            p = policy(variation)
            angles = [20., 0.] if variation == "easier" else [0., 0.]
            p._disc_angle = lambda i: angles[i]
            route = []
            def move(**kwargs):
                route.append(kwargs)
                if kwargs["phase"] == "turn_first_rotor":
                    self.assertEqual(kwargs["angle"], -4.)
                    angles[0] = 0.  # Route-only double, not a physical outcome.
                yield {}
            def hold(*args, **kwargs):
                yield {}
            p._move_key, p._hold = move, hold
            list(p._actions())
            phases = [r["phase"] for r in route]
            self.assertEqual("turn_first_rotor" in phases, variation == "easier")
            if variation == "easier":
                self.assertLess(phases.index("engage_first_rotor"), phases.index("turn_first_rotor"))
                self.assertLess(phases.index("turn_first_rotor"), phases.index("pass_second_rotor"))
            depths = [r["depth"] for r in route if "depth" in r]
            self.assertEqual(depths, sorted(depths))
            self.assertEqual(depths[-1], 3.08)

    def test_native_success_and_first_turn_evidence_are_required(self):
        report = dict(route_mode="simplified", variation="easier", completion_contract="task_success",
                      status="task_success", task_result=dict(task_success=True))
        phases = {"close_and_wait_for_automatic_assist", "lift_to_lock_axis", "pass_first_rotor",
                  "pass_second_rotor", "insert_END", "engage_first_rotor", "turn_first_rotor", "center_first_slot"}
        def check(names, success=True):
            return completion_errors(report, names, ["acquired"], retreats=0, expected=0,
                                     released_completion=False, native_success=success)
        self.assertEqual(check(phases), [])
        self.assertTrue(check(phases-{"turn_first_rotor"}))
        self.assertTrue(check(phases, success=False))

    def test_contact_audit_matches_geometric_bilateral_contract(self):
        rows = [dict(link_a=i, link_b=50, position_m=[0., 0., 0.],
                     penetration_m=.00002, force_n=[0., 0., 0.]) for i in (25, 31)]
        def check():
            return simplified_acquisition_rows(rows, [25, 31], 50, center_m=[0., 0., 0.],
                                               radius_m=.032, max_penetration_m=.002)
        self.assertEqual(check(), (0, 1))
        rows[1]["penetration_m"] = -.00001
        self.assertEqual(check(), ())
        rows[1]["penetration_m"] = .00002
        rows[1]["position_m"] = [.04, 0., 0.]
        self.assertEqual(check(), ())


if __name__ == "__main__":
    unittest.main()
