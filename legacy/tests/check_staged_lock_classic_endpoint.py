"""Check the original same-direction storyboard adapted to a fixed endpoint.

Run: python tests/check_staged_lock_classic_endpoint.py
"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from demos.connectivity import _staged_lock_classic_endpoint_model as m


def phase_end(index):
    p=m.Pose()
    for b in m.BEATS[:index+1]:
        p=m.transition(p,b.kind,b.value)
    return p


class ClassicEndpointChecks(unittest.TestCase):
    def test_full_original_style_route_reaches_fixed_endpoint(self):
        states=m.timeline(120)
        self.assertEqual(len(states),4920)
        self.assertTrue(all(not m.geometry_errors(p) for _,p in states))
        self.assertTrue(m.succeeded(states[-1][1]))
        self.assertEqual(tuple(a%360 for a in states[-1][1].disc_deg),(270,210,0))
        self.assertFalse(m.succeeded(replace(states[-1][1],depth=3.95)))

    def test_retreat_keeps_deeper_discs_and_allows_one_stroke(self):
        before=phase_end(8)
        with self.assertRaises(ValueError):
            m.transition(before,"depth",3)
        shallow=m.transition(before,"depth",1)
        corrected=m.transition(shallow,"turn",120)
        self.assertEqual(corrected.disc_deg[1:],before.disc_deg[1:])
        self.assertEqual(corrected.key_deg%360,60)
        deep=m.transition(corrected,"depth",3)
        self.assertEqual(deep.disc_deg,corrected.disc_deg)
        self.assertEqual(deep.key_deg,corrected.key_deg)

    def test_wrong_endpoint_and_full_turns_are_rejected(self):
        with self.assertRaises(ValueError):
            m.transition(phase_end(11),"depth",4)
        final=phase_end(14)
        for angle in (30,360,-360):
            with self.subTest(angle=angle), self.assertRaises(ValueError):
                m.transition(final,"turn",angle)

    def test_coupled_rotation_is_a_valid_alternative_to_retreat(self):
        # Prevent this presentation route being mislabelled as mandatory.
        p=m.transition(phase_end(8),"turn",-60)
        p=m.transition(p,"depth",3)
        p=m.transition(p,"turn",120)
        p=m.transition(p,"depth",4)
        self.assertTrue(m.succeeded(p))


if __name__=="__main__":
    unittest.main(verbosity=2)
