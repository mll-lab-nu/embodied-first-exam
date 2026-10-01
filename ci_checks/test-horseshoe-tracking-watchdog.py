#!/usr/bin/env python3
"""Controller clock regressions with synthetic observations; no physics proof."""
from pathlib import Path
import sys
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from topogym.planning.horseshoe_ring.policy import HorseshoePolicy


def exercise(window, *, intermittent):
    policy=HorseshoePolicy({'left':{}})
    policy.dt=.025
    policy.held_entities={'left':'target_ring'}
    policy.grip={'left':.0162}
    policy.bias={'left':np.zeros(3)}
    policy.angle_bias={'left':np.zeros(3)}
    policy.offsets={'left':(np.zeros(3),Rotation.identity())}
    program=policy.follow_bodies({'left':(np.array([.02,0.,0.]),Rotation.identity())},
        1.,'synthetic_tracking',tracking_m=.00001,tracking_stall_timeout_s=window)
    # A measured 0.5 mm advance once per second: total duration 40 s,
    # while no interval without progress exceeds one second.
    for tick in range(2001):
        now=tick*policy.dt
        position=[min(tick//40,40)*.0005 if intermittent else 0.,0.,0.]
        policy.obs={'state':{'sim_time_s':now},'privileged':{'world':{'bodies':{
            'target_ring':{'position_m':position,'quaternion_wxyz':[1.,0.,0.,0.]}}}}}
        try:
            next(program)
        except StopIteration:
            return 'complete',now
        except RuntimeError as error:
            if 'Object tracking stalled' not in str(error):raise
            return 'stalled',now
    raise AssertionError('Synthetic controller exceeded the test bound')


class TrackingWatchdogTests(unittest.TestCase):
    def test_intermittent_progress_gets_the_remaining_stage_time(self):
        self.assertEqual(exercise(10.,intermittent=True),('complete',40.))

    def test_true_stall_is_still_bounded(self):
        result,seconds=exercise(10.,intermittent=False)
        self.assertEqual(result,'stalled')
        self.assertGreater(seconds,10.)
        self.assertLess(seconds,10.1)

    def test_legacy_default_retains_its_elapsed_time_bound(self):
        result,seconds=exercise(None,intermittent=True)
        self.assertEqual(result,'stalled')
        self.assertGreater(seconds,14.)
        self.assertLess(seconds,14.1)


if __name__=='__main__':unittest.main()
