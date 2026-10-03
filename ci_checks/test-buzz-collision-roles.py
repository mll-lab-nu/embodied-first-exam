"""Regression for wooden connectors embedded in the Buzz wire entity."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.planning.buzz_wire_3d import kinematics


def geometry(index, center):
    mesh = trimesh.creation.box(extents=[.01, .01, .01])
    vertices = mesh.vertices + np.asarray(center)
    return NS(idx=index, init_faces=mesh.faces, get_verts=lambda: vertices)


class FK:
    def __init__(self, entity):
        pass

    def solve(self, q):
        return dict(position_world_m=np.asarray(q).reshape(1, 3),
                    orientation_wxyz=np.array([[1., 0., 0., 0.]]))


class SupportedPlacementRoles(unittest.TestCase):
    def test_support_permission_never_relaxes_robot_or_metal_contacts(self):
        robot_position = np.array([.15, .1, 0.])
        robot_entity = NS(
            get_qpos=lambda: robot_position.copy(),
            links=[NS(idx_local=0, geoms=[geometry(0, robot_position)])])
        robot = NS(entity=robot_entity, groups={"arm": NS()},
                   _indices={"arm": [0, 1, 2]}, _q_indices={"arm": [0, 1, 2]})
        metal, wood, deck = [geometry(i, [x, 0., 0.])
                             for i, x in [(1, 0.), (2, .05), (3, .1)]]
        wand_position = np.array([.15, -.1, 0.])
        wand = NS(get_pos=lambda: wand_position,
                  get_quat=lambda: np.array([1., 0., 0., 0.]),
                  links=[NS(geoms=[geometry(4, wand_position)])])
        world = NS(entities={
            "wire": NS(links=[NS(geoms=[metal, wood])]),
            "wire_base": NS(links=[NS(geoms=[deck])]), "wand": wand},
            _contact_collector=NS(roles={1: "wire_metal", 2: "wood_stop",
                                         3: "finish_support"}))
        with patch.object(kinematics, "GenesisFKSolver", FK), \
                patch.object(kinematics, "GenesisIKSolver"):
            kin = kinematics.BuzzIK(NS(_robot=robot, _world=world))
        rotation = Rotation.identity()
        for x in [.05, .1]:
            body = (np.array([x, 0., 0.]), rotation)
            with self.subTest(support_x=x):
                self.assertLessEqual(kin.clearance(robot_position, body), 0.)
                self.assertGreater(kin.clearance(
                    robot_position, body, allow_wand_support=True), .001)
                self.assertLessEqual(kin.clearance(
                    np.array([x, 0., 0.]), body, allow_wand_support=True), 0.)
        self.assertLessEqual(kin.clearance(
            robot_position, (np.zeros(3), rotation), allow_wand_support=True), 0.)


if __name__ == "__main__":
    unittest.main()
