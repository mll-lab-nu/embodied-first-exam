"""Checks for geometric proof transfer and fail-closed sampling."""
from copy import deepcopy
import json
import unittest

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from topogym.tasks.horseshoe_ring.geometry import HorseshoeAssembly
from topogym.tasks.horseshoe_ring.shape_variants import make_template, OUTPUT
from topogym.tasks.horseshoe_ring.shape_neighborhood import ShapeNeighborhood, body_change_bound


class PerturbationChecks(unittest.TestCase):
    def test_body_bound_covers_support_changes_in_all_sampled_directions(self):
        a=HorseshoeAssembly(make_template(-.5,1.15,18.,bore_margin_mm=.8))
        b=HorseshoeAssembly(make_template(-.49,1.1502,18.01,bore_margin_mm=.8))
        rng=np.random.default_rng(13);directions=rng.normal(size=(256,3));directions/=np.linalg.norm(directions,axis=1)[:,None]
        for old,new in zip(a.bodies,b.bodies):
            bound=body_change_bound(old,new)
            def supports(body):
                parts=[(mesh.vertices@directions.T).max(0) for mesh in body.convex]
                parts.extend((loop.points()@directions.T).max(0)+loop.wire_radius for loop in body.loops)
                return np.max(parts,axis=0)
            self.assertLessEqual(np.max(np.abs(supports(old)-supports(new))),bound+1e-12)
            self.assertEqual(body_change_bound(old,old),0.)

    def test_com_chord_bound_covers_intermediate_retargeting_error(self):
        rotations=Rotation.from_rotvec([[.3,.5,.2],[-.7,1.1,2.]])
        theta=(rotations[0].inv()*rotations[1]).magnitude();dc=np.array([.02,-.01,.03])
        ts=np.linspace(0,1,101)
        linear=(1-ts[:,None])*rotations[0].apply(dc)+ts[:,None]*rotations[1].apply(dc)
        exact=Slerp([0,1],rotations)(ts).apply(dc)
        self.assertLessEqual(np.linalg.norm(linear-exact,axis=1).max(),.5*theta*np.linalg.norm(dc))


@unittest.skipUnless((OUTPUT/'references/waist_ellipse/certificate.json').exists(),'Requires generated reference evidence')
class EvidenceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=OUTPUT/'references/waist_ellipse'
        cls.path=json.loads((folder/'body_poses.json').read_text())
        cls.cert=json.loads((folder/'certificate.json').read_text())

    def test_tampered_frames_coms_scale_and_incomplete_proofs_are_rejected(self):
        for mutation in ('frames','centers','scale','pairs','implementation'):
            p,c=deepcopy(self.path),deepcopy(self.cert)
            if mutation=='frames':p['frames'][10]['target_ring']['pos'][0]+=.1
            elif mutation=='centers':p['centers'][0][0]+=.1
            elif mutation=='scale':p['scale']=3.
            elif mutation=='pairs':c['minimum_pair_clearance_lower_bounds_m'].pop(next(iter(c['minimum_pair_clearance_lower_bounds_m'])))
            else:c.pop('implementation_sha256')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):ShapeNeighborhood(p,c)

    def test_large_shape_change_cannot_be_emitted_with_a_small_change_proof(self):
        n=ShapeNeighborhood(self.path,self.cert)
        template=make_template(1.,1.3,20.,bore_margin_mm=.8)
        assessment=n.assess(template)
        self.assertFalse(assessment['passed'])
        with self.assertRaises(ValueError):n.materialize(template,assessment)

    def test_identity_transfer_preserves_full_witness_and_goal(self):
        n=ShapeNeighborhood(self.path,self.cert)
        result,cert=n.materialize(self.path['template'],n.assess(self.path['template']))
        self.assertEqual(result['frames'],self.path['frames'])
        self.assertTrue(cert['passed']);self.assertTrue(cert['goal']['separated'])
        self.assertEqual(cert['frames_sha256'],self.cert['frames_sha256'])


if __name__=='__main__':unittest.main()
