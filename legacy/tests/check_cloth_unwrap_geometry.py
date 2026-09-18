"""Checks the preview's actual material geometry, not physical task success."""
import unittest

from hydra import compose, initialize
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from demos.deformation._cloth_unwrap_model import WrapModel


class ClothUnwrapGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with initialize(version_base='1.3', config_path='../configs'):
            cls.cfg=compose(config_name='cloth_unwrap')
        cls.model=WrapModel(cls.cfg.unwrap)

    def test_single_connected_material_disk(self):
        m=self.model
        edges=np.sort(np.concatenate([m.faces[:,[0,1]],m.faces[:,[1,2]],m.faces[:,[2,0]]]),axis=1)
        unique,counts=np.unique(edges,axis=0,return_counts=True)
        self.assertTrue(np.all((counts==1)|(counts==2)))
        self.assertEqual(len(m.flat)-len(unique)+len(m.faces),1)
        graph=coo_matrix((np.ones(len(unique)),(unique[:,0],unique[:,1])),shape=(len(m.flat),len(m.flat)))
        self.assertEqual(connected_components(graph,directed=False,return_labels=False),1)

    def test_all_peels_clear_plate_and_preserve_material_lengths(self):
        m=self.model;opened=np.zeros(4)
        origin=np.asarray(self.cfg.unwrap.work)
        bp,bq=m.board_pose(origin,0.)
        for flap in range(4):
            for value in np.linspace(0,1,31):
                opened[flap]=value
                vertices=m.vertices(opened,origin,0.)
                a=m.audit_frame(vertices,bp,bq)
                self.assertEqual(a['cloth_board_interior_samples'],0)
                # Analytic arc length is constant; polygon chord discretization
                # changes by at most 0.15 percent with the configured grid.
                self.assertLess(a['max_edge_length_change'],.0015)
                self.assertGreaterEqual(a['min_cloth_z'],-1e-10)

    def test_flip_keeps_material_and_plate_rigidly_together(self):
        m=self.model;opened=np.zeros(4);origin=np.array([0.,0.,.19])
        reference=m.vertices(opened,origin,np.pi)
        lengths=np.linalg.norm(reference[m.edges[:,0]]-reference[m.edges[:,1]],axis=1)
        for angle in np.linspace(np.pi,2*np.pi,31):
            v=m.vertices(opened,origin,angle);bp,bq=m.board_pose(origin,angle)
            np.testing.assert_allclose(np.linalg.norm(v[m.edges[:,0]]-v[m.edges[:,1]],axis=1),lengths,atol=1e-12)
            self.assertEqual(m.audit_frame(v,bp,bq)['cloth_board_interior_samples'],0)
            self.assertGreater(v[:,2].min(),0.)


if __name__=='__main__':unittest.main()
