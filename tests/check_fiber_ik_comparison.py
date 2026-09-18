"""A timestep comparison must preserve every control and acceptance parameter."""
import unittest

from topogym.tasks.fiber_bundling.assess_ik import comparable_plan


class IKComparisonChecks(unittest.TestCase):
    def setUp(self):
        self.plan = dict(dt=.002, stability_gate="first/result.json",
                         stability_gate_sha256="gate-content", press_radius_m=.0353,
                         fine_contact_penetration_limit_m=.0003,
                         policy_parameters=dict(mode="greedy_hybrid", max_presses=16))

    def test_step_and_gate_location_can_differ(self):
        other = dict(self.plan, dt=.001, stability_gate="copy/result.json")
        self.assertEqual(comparable_plan(self.plan), comparable_plan(other))

    def test_control_limits_and_gate_contents_must_match(self):
        for key, changed in (("press_radius_m", .034),
                             ("fine_contact_penetration_limit_m", .0007),
                             ("stability_gate_sha256", "different-gate"),
                             ("policy_parameters", dict(mode="greedy_hybrid", max_presses=20))):
            with self.subTest(key=key):
                self.assertNotEqual(comparable_plan(self.plan),
                                    comparable_plan(dict(self.plan, **{key: changed})))


if __name__ == "__main__":
    unittest.main()
