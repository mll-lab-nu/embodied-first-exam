"""Conservative volume certificates, with independent distance/containment controls."""
from copy import deepcopy
from itertools import product
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.spatial import Delaunay
from scipy.spatial.transform import Rotation

from topogym.evaluation.terminal import SettlingSpec, evaluate_settling
from terminal_fixtures import soft


def box_volume(center, half):
    vertices = np.array(list(product((-1., 1.), repeat=3)))*half+center
    return vertices, Delaunay(vertices).simplices


def box_planes(bounds):
    normals = np.r_[np.eye(3), -np.eye(3)]
    return np.c_[normals, np.r_[-bounds[1], bounds[0]]]


def fixture(robot_center=(0, 0, 0)):
    points, elements = [], []
    for center, half in [((-.2, 0, 0), (.002, .2, .002)),
                         ((0, -.2, 0), (.2, .002, .002)),
                         ((.2, 0, 0), (.002, .2, .002))]:
        p, e = box_volume(center, half)
        elements.extend(e+len(points)); points.extend(p)
    bounds = np.array(robot_center)+np.array([[-.01]*3, [.01]*3])
    state = dict(physics_step=0, assist_active=False, fem={'rope': soft(points)},
                 release_geometry=dict(schema_version=2, physics_step=0, complete=True,
                     robot_present=True, robot_bounds_m=bounds[None], target_bounds_m={},
                     robot_convex_planes_m=[box_planes(bounds)], fem_elements={'rope':np.array(elements)}))
    return state, SettlingSpec(fem_targets=('rope',))


@pytest.mark.parametrize('center,clear', [((0, 0, 0),True), ((0,.3,0),True),
                                        ((.184,0,0),False), ((.2,0,0),False)])
def test_whole_rope_empty_space_is_refined_without_admitting_near_or_contact(center, clear):
    state, spec = fixture(center)
    reached, metrics, _ = evaluate_settling(state, spec)
    assert reached == clear and metrics['robot_clear'] == clear
    if center == (0, 0, 0):
        assert metrics['coarse_clearance_lower_bound_m'] == 0
        assert .187 < metrics['clearance_lower_bound_m'] <= .188+1e-12
        assert metrics['refined_fem_targets'] == ['rope']


def test_vertices_clear_but_robot_inside_a_tetrahedron_is_rejected():
    state, spec = fixture()
    # Every vertex is far from the robot. The filled tetrahedron contains it.
    state['fem']['rope'] = soft([[1,1,1],[-1,-1,1],[-1,1,-1],[1,-1,-1]])
    state['release_geometry']['fem_elements']['rope'] = np.array([[0,1,2,3]])
    assert not evaluate_settling(state, spec)[0]


@pytest.mark.parametrize('gap,clear', [(.0049,False),(.0051,True)])
def test_five_mm_boundary_is_preserved(gap, clear):
    state, spec = fixture()
    p, e = box_volume((.011+gap,0,0), (.001,.001,.001))
    state['fem']['rope'] = soft(p)
    state['release_geometry']['fem_elements']['rope'] = e
    assert evaluate_settling(state, spec)[0] == clear


def test_refinement_missing_topology_keeps_safe_coarse_fallback():
    state, spec = fixture()
    del state['release_geometry']['fem_elements']['rope']
    reached, metrics, _ = evaluate_settling(state, spec)
    assert not reached and not metrics['robot_clear']


@pytest.mark.parametrize('damage', ['count','normal','nan','index','coverage','float_index','stale'])
def test_bad_refinement_evidence_is_rejected(damage):
    state, spec = fixture()
    geometry = state['release_geometry']
    if damage=='count': geometry['robot_convex_planes_m'] = []
    elif damage=='normal': geometry['robot_convex_planes_m'][0][0,:3] *= 2
    elif damage=='nan': geometry['robot_convex_planes_m'][0][0,3] = np.nan
    elif damage=='index': geometry['fem_elements']['rope'][0,0] = 1000
    elif damage=='coverage': geometry['fem_elements']['rope'] = geometry['fem_elements']['rope'][:1]
    elif damage=='float_index': geometry['fem_elements']['rope'] = geometry['fem_elements']['rope'].astype(float)
    else: geometry['physics_step'] = 1
    with pytest.raises(ValueError): evaluate_settling(state, spec)


def test_world_geometry_refinement_uses_current_pose_and_immutable_topology():
    from topogym.world.physics.release_geometry import ReleaseGeometry
    vertices, _ = box_volume((0,0,0), (.1,.2,.3))
    geom = SimpleNamespace(type=SimpleNamespace(name='MESH'), data=[], init_verts=vertices, idx=7)
    entity = SimpleNamespace(links=[SimpleNamespace(geoms=[geom])])
    p, e = box_volume((.5,0,0), (.01,.01,.01))
    fem = SimpleNamespace(material_coordinates=p, elems=e, n_vertices=len(p))
    class Solver:
        angle = 45.
        def get_geoms_pos(self, indices, *, relative): return np.array([[1.,2.,3.]])
        def get_geoms_quat(self, indices, *, relative):
            return Rotation.from_euler('z', self.angle, degrees=True).as_quat()[[3,0,1,2]][None]
    solver = Solver()
    world = SimpleNamespace(entities={'robot':entity, 'rope':fem}, physics_step=4,
                            scene=SimpleNamespace(sim=SimpleNamespace(rigid_solver=solver)))
    reader = ReleaseGeometry(world, ())
    first = reader.read()
    assert first['schema_version']==2
    planes = first['robot_convex_planes_m'][0]
    posed = Rotation.from_euler('z',45,degrees=True).apply(vertices)+[1,2,3]
    assert np.max(posed@planes[:,:3].T+planes[:,3]) <= 1e-10
    np.testing.assert_array_equal(first['fem_elements']['rope'],e)
    assert not first['fem_elements']['rope'].flags.writeable
    saved = deepcopy(planes)
    solver.angle = 12.; world.physics_step=5
    second = reader.read()
    assert second['physics_step']==5
    assert not np.allclose(second['robot_convex_planes_m'][0],saved)
    np.testing.assert_array_equal(first['robot_convex_planes_m'][0],saved)


def test_random_rotated_volume_bounds_never_exceed_independent_surface_distance():
    import trimesh
    from topogym.evaluation.terminal.clearance import convex_cover_planes, fem_clearance_lower_bound
    rng = np.random.default_rng(481)
    robot = trimesh.creation.icosphere(subdivisions=1, radius=.07)
    robot.vertices = robot.vertices*[1.,.7,1.2]
    turn = Rotation.from_euler('xyz',[.2,-.4,.3])
    robot.vertices = turn.apply(robot.vertices)+[.1,-.2,.3]
    planes = convex_cover_planes(robot.vertices)
    manager = trimesh.collision.CollisionManager()
    manager.add_object('robot',robot)
    certified = 0
    for _ in range(30):
        points = rng.normal(size=(4,3))*.01+[.1,-.2,.3]+rng.uniform(-.13,.13,3)
        lower = fem_clearance_lower_bound(points,np.array([[0,1,2,3]]),robot.bounds[None],[planes],.005)
        tet = trimesh.Trimesh(vertices=points,faces=[[0,1,2],[0,3,1],[0,2,3],[1,3,2]],process=False)
        if manager.in_collision_single(tet):
            assert lower < 1e-10
        else:
            assert 0 <= lower <= manager.min_distance_single(tet)+1e-10
        certified += lower >= .005
    assert certified >= 5
