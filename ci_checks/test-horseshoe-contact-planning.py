#!/usr/bin/env python3
"""Contact-planning bounds with real convex queries; no physics qualification."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from topogym.planning.buzz_wire_3d.kinematics import manager, mesh_object
from topogym.planning.horseshoe_ring.ring_route import HeldRingPath


class ContactPlanningTests(unittest.TestCase):
    def path(self, limit):
        mesh=trimesh.creation.box(extents=[.01,.01,.01])
        shapes={}
        for name in ('target_ring','obstacle'):
            obj=mesh_object(mesh.vertices,mesh.faces)
            shapes[name]=([obj],manager([obj]))
        poses={'target_ring':(np.array([0.,0.,1.]),Rotation.identity()),
               'obstacle':(np.array([.0097,0.,1.]),Rotation.identity())}
        checker=SimpleNamespace(bodies=shapes,table_height=0.,
            solve=lambda side,pose,seed:seed,
            check=lambda *args,**kwargs:dict(passed=True,issues=[]))
        task=SimpleNamespace(placement_remainder=('obstacle',),
            placement_vertices={'target_ring':mesh.vertices},
            terminal_metadata=lambda:dict(contact_penetration={'other_contacts_m':.001}))
        planner=SimpleNamespace(checker=checker,task=task,
            withdrawal_parameters={'puzzle_contact_limit_m':limit},
            observed=lambda obs:(poses,np.zeros(8)))
        obs={'robot':{'left':{'tcp_position_world_m':[0.,0.,1.],
                            'tcp_orientation_wxyz':[1.,0.,0.,0.]}}}
        return HeldRingPath(planner,obs)

    def test_light_sliding_contact_can_continue_beyond_initial_escape(self):
        pose=(np.array([.0002,.004,1.]),Rotation.identity())
        self.assertFalse(self.path(None).check(pose)['passed'])
        checked=self.path(.001).check(pose)
        self.assertTrue(checked['passed'])
        self.assertFalse(checked['contact_release_neighbourhood'])

    def test_deeper_contact_still_fails_and_free_endpoint_passes(self):
        path=self.path(.001)
        deep=path.check((np.array([.0011,0.,1.]),Rotation.identity()))
        self.assertFalse(deep['passed'])
        self.assertGreater(deep['penetration_m'],.001)
        free=path.check((np.array([-.02,0.,1.]),Rotation.identity()))
        self.assertTrue(free['passed'])
        self.assertGreater(free['ring_clearance_m'],.019)

    def test_planning_cannot_exceed_native_contact_contract(self):
        with self.assertRaisesRegex(ValueError,'native contact limit'):
            self.path(.0015)


if __name__=='__main__':unittest.main()
