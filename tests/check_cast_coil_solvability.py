"""Guard the constructive solution against missed table collisions and stale assets."""
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from topogym.tasks.cast_coil.geometry import CoilAssembly, generate_assets
from topogym.tasks.cast_coil.solvability import minimum_height, table_audit, exported_boxes_match
from topogym.tasks.cast_coil.verification import Motion, prototype_route


class CastCoilSolvabilityChecks(unittest.TestCase):
    def test_rotation_can_hit_table_between_clear_endpoints(self):
        for sign in (-1., 1.):
            corner = np.array([[sign, 0., 0.]])
            motion = Motion('half_turn', 1., np.eye(3), np.zeros(3),
                axis=np.array([0., 1., 0.]), angle_rad=sign*np.pi, pivot=np.zeros(3))
            for u in (0, 1):
                R, t = motion.pose(u)
                self.assertAlmostEqual((corner@R.T+t)[0, 2], 0.)
            result = minimum_height(motion, corner)
            self.assertAlmostEqual(result['minimum_z_m'], -1.)
            self.assertAlmostEqual(result['u'], .5)

    def test_translation_accounts_for_rotated_start(self):
        R = np.diag([-1., 1., -1.])
        motion = Motion('translation', 1., R, np.array([0., 0., .4]), np.array([0., 0., .1]))
        result = minimum_height(motion, np.array([[0., 0., .5]]))
        self.assertAlmostEqual(result['minimum_z_m'], -.4)
        self.assertEqual(result['u'], 1.)

    def test_known_route_requires_lift_and_turn_extremum_is_not_endpoint(self):
        assembly = CoilAssembly()
        result = table_audit(assembly, prototype_route(assembly), .0005)
        self.assertLess(result['minimum_table_clearance_without_lift_m'], -.059)
        self.assertGreater(result['segments'][1]['u'], 0.)
        self.assertLess(result['segments'][1]['u'], 1.)
        self.assertEqual(result['proposed_common_lift_m'], .07)
        self.assertGreater(result['minimum_table_clearance_after_lift_m'], .010)

    def test_unchanged_template_does_not_hide_altered_urdf_collision(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            assembly, _ = generate_assets(path)
            self.assertTrue(exported_boxes_match(path, assembly))
            file = path/'coil_silver/coil_silver.urdf'
            tree = ET.parse(file)
            box = tree.find('.//collision/geometry/box')
            size = np.fromstring(box.get('size'), sep=' ')
            size[0] *= .5
            box.set('size', ' '.join(map(str, size)))
            tree.write(file)
            self.assertFalse(exported_boxes_match(path, assembly))


if __name__ == '__main__':
    unittest.main()
