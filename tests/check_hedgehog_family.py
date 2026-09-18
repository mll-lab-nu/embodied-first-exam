"""Checks for family carving primitives; no GPU is required."""
import unittest
import numpy as np
import trimesh
from topogym.tasks.hedgehog_in_cage.family_geometry import boxes_from_mask, union64


class FamilyGeometryChecks(unittest.TestCase):
    def test_merged_cells_preserve_holes_without_overlap(self):
        rng=np.random.default_rng(12)
        mask=rng.random((7,9,11))>.30
        mask[1:6,3:7,2:9]=True
        mask[3,5,4]=False
        result=np.zeros(mask.shape,dtype=int)
        for a,b,c,d,e,f in boxes_from_mask(mask,max_second=3):
            self.assertLessEqual(d-c,3)
            result[a:b,c:d,e:f]+=1
        np.testing.assert_array_equal(result,mask.astype(int))

    def test_union_preserves_internal_void_boundary(self):
        cells=[]
        for axis in range(3):
            for sign in (-1,1):
                extent=np.full(3,2.);extent[axis]=.2
                center=np.zeros(3);center[axis]=sign*.9
                cells.append(trimesh.creation.box(extents=extent,transform=trimesh.transformations.translation_matrix(center)))
        mesh=union64(cells)
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.volume,8-1.6**3,places=10)
        shells=mesh.split()
        self.assertEqual(sum(s.volume>0 for s in shells),1)
        self.assertEqual(sum(s.volume<0 for s in shells),1)


if __name__=='__main__':unittest.main()
