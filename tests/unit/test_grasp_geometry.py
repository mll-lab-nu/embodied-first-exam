"""Actual triangle proximity and descriptor-based read-only finger geometry."""
from types import SimpleNamespace
import numpy as np
import pytest
from topogym.robot.grasp_geometry import read_grasp_geometry
from topogym.utils.grasp import surface_distances


def test_surface_distance_uses_triangle_interior_and_world_coordinates():
    vertices = np.array([[1., 2., 3.], [2., 2., 3.], [1., 3., 3.]])
    distance = surface_distances([[1.25, 2.25, 3.004], [1.25, 2.25, 3.02]], vertices, [[0, 1, 2]])
    np.testing.assert_allclose(distance, [.004, .02])


def test_geometry_reads_declared_fingers_and_preserves_mesh_face_offsets():
    class Geometry:
        init_faces = np.array([[0, 1, 2]])
        def __init__(self, shift): self.shift = shift
        def get_verts(self): return np.eye(3) + self.shift
    links = dict(hand=SimpleNamespace(get_pos=lambda: np.array([1., 2., 3.]),
                                     get_quat=lambda: np.array([1., 0., 0., 0.])),
                 a=SimpleNamespace(geoms=[Geometry(1), Geometry(2)]),
                 b=SimpleNamespace(geoms=[Geometry(3)]))
    robot = SimpleNamespace(groups={'arm': SimpleNamespace(hand_link='hand',
                grasp=SimpleNamespace(finger_links=('a', 'b')))},
                            entity=SimpleNamespace(get_link=links.__getitem__))
    result = read_grasp_geometry(robot, 'arm')
    np.testing.assert_array_equal(result['position'], [1., 2., 3.])
    np.testing.assert_array_equal(result['surfaces'][0][1], [[0, 1, 2], [3, 4, 5]])
    np.testing.assert_array_equal(result['surfaces'][1][0], np.eye(3)+3)
    links['b'].geoms = []
    with pytest.raises(ValueError, match='No collision surface'):
        read_grasp_geometry(robot, 'arm')
