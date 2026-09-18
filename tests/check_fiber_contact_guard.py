"""Forbidden contact filtering, substep coverage and episode failure semantics."""
from types import SimpleNamespace
import unittest
import numpy as np

from topogym.tasks.fiber_bundling.contact_guard import (
    FAILURE_REASON, GripperFineContactGuard, gripper_link_names,
)


def contacts(a=(), b=(), **extra):
    return dict(link_a=np.asarray(a), link_b=np.asarray(b),
                position=np.zeros((len(a), 3)), force_a=np.zeros((len(a), 3)), **extra)


class ContactGuardChecks(unittest.TestCase):
    def guard(self):
        return GripperFineContactGuard({10: "left_finger", 11: "housing"},
                                       {50: "fiber_00_00", 51: "fiber_07_09"}, .0005)

    def test_both_pair_orders_and_zero_force_fail(self):
        for a, b in ((10, 50), (51, 11)):
            with self.subTest(a=a, b=b):
                guard = self.guard()
                guard.observe(contacts([a], [b]))
                self.assertTrue(guard.report()["failed"])
                self.assertEqual(guard.first_contact["reason"], FAILURE_REASON)

    def test_trunk_ring_self_contact_arm_and_masked_pairs_are_allowed(self):
        guard = self.guard()
        guard.observe(contacts([10, 50, 50, 2, 10], [40, 70, 51, 50, 50],
                               valid_mask=np.array([True, True, True, True, False])))
        self.assertFalse(guard.report()["failed"])

    def test_failure_and_first_evidence_survive_separation(self):
        guard = self.guard()
        guard.observe(contacts([10], [50]))
        event = guard.first_contact.copy()
        guard.observe(contacts())
        guard.observe(contacts([11], [51]))
        self.assertEqual(guard.first_contact, event)
        self.assertEqual(guard.report()["observed_substeps"], 3)

    def test_first_substep_contact_cannot_hide_in_clear_last_substep(self):
        guard = self.guard()
        frames = iter([contacts([10], [50]), contacts(), contacts(), contacts()])
        solver = SimpleNamespace(substep=lambda f: setattr(solver, "contacts", next(frames)))
        solver.collider = SimpleNamespace(get_contacts=lambda: solver.contacts)
        guard.install(solver)
        for f in range(4):
            solver.substep(f)
        self.assertEqual(len(solver.contacts["link_a"]), 0)
        self.assertTrue(guard.report()["failed"])
        self.assertEqual(guard.first_contact["substep"], 1)
        self.assertEqual(guard.first_contact["time_s"], .0005)

    def test_tool_subtree_includes_housing_and_sibling_linkage(self):
        # Deliberately non-contiguous global IDs; hand is a reference sibling.
        robot = SimpleNamespace(links=[SimpleNamespace(idx=i, name=n, parent_idx=p) for i, n, p in
            [(20, "arm", -1), (24, "tool_mount", 20), (27, "r85_base", 24),
             (30, "left_finger", 27), (33, "hand", 24), (37, "linkage", 27)]])
        self.assertEqual(set(gripper_link_names(robot)), {24, 27, 30, 33, 37})

    def test_unknown_tool_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unmonitored"):
            gripper_link_names(SimpleNamespace(links=[]))


if __name__ == "__main__":
    unittest.main()
