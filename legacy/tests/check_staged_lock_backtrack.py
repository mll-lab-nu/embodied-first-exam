"""Behavior and counterfactual checks for the conditional backtracking variant.

Run: python tests/check_staged_lock_backtrack.py
No Genesis or GPU required. This is not a contact-dynamics certification.
"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from demos.connectivity import _staged_lock_backtrack_model as m


def phase_end(index):
    p=m.Pose()
    for b in m.BEATS[:index+1]:
        p=m.transition(p,b.kind,b.value)
    return p


class BacktrackingChecks(unittest.TestCase):
    def test_full_path_and_actual_insertion(self):
        states=m.timeline(120)
        self.assertEqual(len(states),4200)
        self.assertTrue(all(not m.geometry_errors(p) for _,p in states))
        final=states[-1][1]
        self.assertTrue(m.succeeded(final))
        self.assertEqual(final.disc_deg,(0,-90,0))
        self.assertFalse(m.succeeded(replace(final,depth=3.95)))

    def test_coupled_rotation_cannot_repair_the_trap(self):
        trap=phase_end(3)
        for angle in range(-360,361):
            p=m.transition(trap,"turn",angle)
            self.assertFalse(m.can_insert(p,3))
            proof=m.third_level_windows(p)
            self.assertEqual(proof["min_center_separation_deg"],30)
            self.assertEqual(proof["combined_half_width_deg"],12)
            self.assertFalse(proof["overlap_possible"])

    def test_clearance_within_current_slots_does_not_remove_the_trap(self):
        trap=phase_end(3)
        # The two discs may differ by nearly 12 degrees due to their separate
        # 6-degree fit clearances. Even those boundary poses cannot pass D3.
        for offset in (-5.99,0,5.99):
            p=replace(trap,disc_deg=(30+offset,30-offset,120))
            self.assertFalse(m.geometry_errors(p))
            proof=m.third_level_windows(p)
            self.assertFalse(proof["overlap_possible"])
            self.assertGreater(proof["min_center_separation_deg"],12)

    def test_free_rotation_between_discs_is_allowed_but_cannot_bypass(self):
        trap=phase_end(3)
        gap=m.transition(trap,"depth",2.5)
        self.assertEqual(m.active_discs(gap),())
        turned=m.transition(gap,"turn",123)
        self.assertEqual(turned.disc_deg,trap.disc_deg)
        # Independently sweep every quarter degree at the third-level entry.
        # D1/D2 themselves must reject it, regardless of the third disc.
        for n in range(1440):
            p=replace(trap,depth=3,key_deg=n*.25)
            errors=m.geometry_errors(p)
            self.assertTrue("tab_2_vs_disc_1" in errors or "tab_1_vs_disc_2" in errors)

    def test_shallow_correction_enables_one_continuous_stroke(self):
        trap=phase_end(3)
        with self.assertRaises(ValueError):
            m.transition(trap,"depth",3)
        shallow=m.transition(trap,"depth",1)
        corrected=m.transition(shallow,"turn",90)
        self.assertEqual(corrected.disc_deg,(120,30,120))
        self.assertEqual(corrected.disc_deg[1:],trap.disc_deg[1:])
        self.assertTrue(m.third_level_windows(corrected)["overlap_possible"])
        deep=m.transition(corrected,"depth",3)
        self.assertEqual(deep.key_deg,120)
        self.assertEqual(m.active_discs(deep),(0,1,2))

    def test_preselecting_the_other_entry_can_avoid_the_trap(self):
        # This makes the scope of "necessary" explicit: it applies to the
        # illustrated depth-two state, not every path from the initial pose.
        p=m.Pose()
        for kind,value in (("depth",1),("turn",90),("depth",2),("turn",30),
                           ("depth",3),("turn",-120),("depth",4)):
            p=m.transition(p,kind,value)
        self.assertTrue(m.succeeded(p))

    def test_wrong_endpoint_orientation_and_full_turns_rejected(self):
        deep=phase_end(7)
        with self.assertRaises(ValueError):
            m.transition(deep,"depth",4)
        final=phase_end(10)
        for angle in (30,360,-360):
            with self.subTest(angle=angle), self.assertRaises(ValueError):
                m.transition(final,"turn",angle)


if __name__=="__main__":
    unittest.main(verbosity=2)
