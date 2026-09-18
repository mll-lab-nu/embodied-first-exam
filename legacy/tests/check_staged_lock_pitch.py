"""CPU checks for the fixed-endpoint pitch mechanism, not contact dynamics.

Run: python tests/check_staged_lock_pitch.py
"""
from dataclasses import replace
from itertools import product
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demos.connectivity import _staged_lock_model as m


class StagedLockPitchChecks(unittest.TestCase):
    def test_complete_path_to_fixed_endpoint(self):
        states=m.timeline(120)
        self.assertEqual(len(states),3720)
        self.assertTrue(all(not m.geometry_errors(p) for _,p in states))
        final=states[-1][1]
        self.assertTrue(m.succeeded(final))
        self.assertEqual(final.disc_deg,(0,90,-60))
        self.assertEqual(m.active_discs(final),(1,2))
        self.assertFalse(m.succeeded(replace(final,depth=3.95)))

    def test_all_three_blocked_requests_rejected(self):
        pose=m.Pose()
        rejected=0
        for beat in m.BEATS:
            if beat.kind=="blocked":
                with self.assertRaises(ValueError):
                    m.transition(pose,"depth",beat.value)
                rejected+=1
            pose=m.transition(pose,beat.kind,beat.value)
        self.assertEqual(rejected,3)

    def test_shallow_turn_preserves_deeper_angles(self):
        p=m.transition(m.Pose(),"depth",1)
        q=m.transition(p,"turn",45)
        self.assertEqual(q.disc_deg[1:],p.disc_deg[1:])
        self.assertFalse(m.can_insert(p,2))
        self.assertTrue(m.can_insert(q,2))

    def test_fixed_endpoint_rejects_wrong_orientation(self):
        final=m.timeline()[-1][1]
        # Keep drive slots aligned with the key, but change its orientation
        # relative to the fixed socket: only the socket should reject this.
        bad=m.Pose(4,30,tuple(a+30 for a in final.disc_deg))
        self.assertEqual(m.geometry_errors(bad),["tab_vs_fixed_endpoint"])
        self.assertFalse(m.succeeded(bad))
        for degrees in (30,360,-360):
            with self.subTest(degrees=degrees), self.assertRaises(ValueError):
                m.transition(final,"turn",degrees)

    def test_withdrawal_checks_intermediate_plate_crossings(self):
        # Neither endpoint overlaps a disc, but the rear fin would cross D1
        # through solid material between them. Final-pose-only checks miss it.
        p=m.Pose(3.5,0,(100,0,0))
        self.assertFalse(m.geometry_errors(p))
        self.assertFalse(m.geometry_errors(replace(p,depth=2.5)))
        self.assertFalse(m.can_insert(p,2.5))
        with self.assertRaises(ValueError):
            m.transition(p,"depth",2.5)

    def test_free_rotation_has_monotone_depth_solutions(self):
        # Counterexample to any claim that a fixed endpoint alone forces
        # backtracking. The same constructive policy solves 64 initial states.
        for angles in product((0.,37.,121.,253.),repeat=3):
            p=m.Pose(0,angles[0]+m.SLOTS[0][0],angles)
            p=m.transition(p,"depth",1)
            for i in (1,2):
                target=p.disc_deg[i]+m.SLOTS[i][0]
                p=m.transition(p,"turn",(target-p.key_deg+180)%360-180)
                p=m.transition(p,"depth",i+1)
            p=m.transition(p,"turn",(m.END_DEG-p.key_deg+180)%360-180)
            p=m.transition(p,"depth",m.END_DEPTH)
            self.assertTrue(m.succeeded(p),angles)


if __name__=="__main__":
    unittest.main(verbosity=2)
