"""Material ownership/configuration tests; no fake physics success claims."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
import pytest
from types import SimpleNamespace
from topogym.utils.grasp import SoftGraspTarget, GraspAssistConfig, material_components, exposed_patch
from topogym.simulator.config import SimulatorConfig
from topogym.world.physics.grasp_manager import GraspManager
from topogym.world.physics.grasp_soft import SoftGraspBackend
from topogym.world.physics.pbd import bind_material_map


@pytest.mark.parametrize('case, expected', [('bilateral', True), ('single_finger', False),
                                          ('too_far', False), ('wrong_material', False),
                                          ('inside_finger', False), ('overstrain', False)])
def test_candidate_geometry_rejects_non_grasps(monkeypatch, case, expected):
    import trimesh
    import topogym.world.physics.grasp_soft as module
    surfaces = []
    for x in (-.006, .006 if case != 'single_finger' else .05):
        mesh = trimesh.creation.box(extents=(.004, .04, .04))
        mesh.vertices += [x, 0., 0.]
        surfaces.append((mesh.vertices, mesh.faces))
    x = np.array([[.5 if case == 'too_far' else -.006 if case == 'inside_finger' else 0., 0., 0.]])
    if case == 'overstrain':
        x = np.array([[0.,0.,0.], [0.,.03,0.]])
    # Deep inside a finger: reject even with a permissive distance gate.
    config = GraspAssistConfig('pbd_local_patch_v1', (SoftGraspTarget('cloth',
        material_min_m=(1., 1.) if case == 'wrong_material' else (),
        material_max_m=(2., 2.) if case == 'wrong_material' else (),
        contact_distance_m=.02, max_strain_ratio=1.3),), max_penetration_m=.001)
    world = SimpleNamespace(entities={'cloth': object()}, physics_step=1)
    robot = SimpleNamespace(groups={'arm': SimpleNamespace(hand_link='hand', tcp_position_in_hand_m=(0.,0.,0.))},
                            entity=SimpleNamespace(get_link=lambda n: object()))
    class Backend(SoftGraspBackend):
        evidence_source = 'unit_geometry_only'
        def positions(self, name): return x
    backend = Backend(world, robot, config)
    if case == 'overstrain':
        backend.initialize_material('cloth', [[0.,0.], [0.,.01]], [[0.,0.,0.], [0.,.01,0.]], edges=[[0,1]])
    else:
        backend.initialize_material('cloth', [[0.,0.]], x, edges=[])
    monkeypatch.setattr(module, 'read_grasp_geometry', lambda *args: dict(
        position=np.zeros(3), quaternion=np.array([1.,0.,0.,0.]), surfaces=surfaces))
    assert bool(backend.candidates('arm')) is expected


@pytest.mark.parametrize('same_material', [True, False])
def test_two_fingers_can_touch_different_points_of_one_patch(monkeypatch, same_material):
    import trimesh
    import topogym.world.physics.grasp_soft as module
    surfaces = []
    for center in (-.011, .011):
        mesh = trimesh.creation.box(extents=(.004,.04,.04))
        mesh.vertices += [center,0.,0.]
        surfaces.append((mesh.vertices,mesh.faces))
    x = np.array([[-.009,0.,0.], [0.,0.,0.], [.009,0.,0.]])
    uv = x[:,:2].copy()
    if not same_material: uv[2,0] += .1
    world = SimpleNamespace(entities={'cloth':object()}, physics_step=1)
    robot = SimpleNamespace(groups={'arm':SimpleNamespace(hand_link='hand',tcp_position_in_hand_m=(0.,0.,0.))},
                            entity=SimpleNamespace(get_link=lambda n:object()))
    class Backend(SoftGraspBackend):
        evidence_source = 'unit_geometry_only'
        def positions(self, name): return x
    backend = Backend(world,robot,GraspAssistConfig('pbd_local_patch_v1',(SoftGraspTarget('cloth'),)))
    backend.initialize_material('cloth',uv,x,edges=[])
    monkeypatch.setattr(module,'read_grasp_geometry',lambda *args:dict(
        position=np.zeros(3),quaternion=np.array([1.,0.,0.,0.]),surfaces=surfaces))
    assert bool(backend.candidates('arm')) is same_material


def test_soft_config_roundtrip_and_model_type_rejection():
    config = SimulatorConfig(grasp_assist=GraspAssistConfig('ipc_soft_band_v1', (SoftGraspTarget('rope', (0.,), (.2,)),)))
    assert SimulatorConfig(grasp_assist=asdict(config.grasp_assist)).grasp_assist == config.grasp_assist
    with pytest.raises(ValueError):
        GraspAssistConfig('contact_weld_v1', (SoftGraspTarget('rope'),))
    with pytest.raises(ValueError):
        SoftGraspTarget('rope', (1.,), (0.,))
    with pytest.raises(ValueError, match='dimension'):
        GraspAssistConfig('pbd_local_patch_v1', (SoftGraspTarget('cloth', (0.,), (.2,)),))


def test_spatially_coincident_material_layers_remain_separate():
    uv = np.array([[0., 0.], [.005, 0.], [.10, 0.], [.105, 0.]])
    groups = material_components(np.arange(4), uv, .01)
    assert [g.tolist() for g in groups] == [[0, 1], [2, 3]]
    x = np.array([[0., 0., 0.], [.005, 0., 0.], [0., 0., .01], [.005, 0., .01]])
    assert not exposed_patch(x, uv, [0, 1], radius=.01, clearance=.002)
    assert exposed_patch(x, uv, [2, 3], radius=.01, clearance=.002)


class MaterialBackend:
    hands = ('left', 'right')
    def __init__(self):
        self.fractions = dict(left=0., right=0.)
        self.choices = dict(left=[('rope', 1)], right=[('rope', 2)])
        self.regions = {('rope', 1): {1, 2}, ('rope', 2): {8, 9}}
        self.active = {}
    def fraction(self, hand): return self.fractions[hand]
    def candidates(self, hand): return self.choices[hand]
    def conflicts(self, a, b): return bool(self.regions[a] & self.regions[b])
    def acquire(self, hand, key):
        b = dict(hand=hand, target=key, indices=sorted(self.regions[key]))
        self.active[hand] = b
        return deepcopy(b)
    def release(self, binding): self.active.pop(binding['hand'])
    def exists(self, binding): return binding == self.active.get(binding['hand'])
    def check_health(self, binding): return None
    def verify_bindings(self, bindings): assert all(self.exists(b) for b in bindings)
    def capture(self): return deepcopy(self.active)
    def restore(self, state): self.active = deepcopy(state)


def test_same_entity_disjoint_regions_and_restore_without_rigid_pose():
    backend = MaterialBackend()
    manager = GraspManager(backend, GraspAssistConfig('ipc_soft_band_v1', (SoftGraspTarget('rope'),)))
    backend.fractions = dict(left=.5, right=.5)
    manager.before_tick(1); manager.after_tick(.02)
    assert len(backend.active) == 2
    manager.before_tick(2); manager.after_tick(.02)
    held = manager.capture()
    backend.fractions['left'] = 0.
    manager.before_tick(3); manager.after_tick(.02)
    assert list(backend.active) == ['right']
    manager.restore(held)
    assert manager.capture() == held


def test_overlapping_distinct_keys_are_rejected_for_both_hands():
    backend = MaterialBackend()
    backend.regions[('rope', 2)] = {2, 3}
    manager = GraspManager(backend, GraspAssistConfig('ipc_soft_band_v1', (SoftGraspTarget('rope'),)))
    backend.fractions = dict(left=.5, right=.5)
    manager.before_tick(1); manager.after_tick(.02)
    assert not backend.active
    assert all(s['rejection'] == 'ownership_conflict' for s in manager.hands.values())


def test_material_map_uses_barycentric_uv_and_rejects_coincident_layers(tmp_path):
    class Entity:
        def get_particles_pos(self): return np.array([[.25, .25, 0.]])
    entity = Entity()
    v = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
    f = np.array([[0, 1, 2]])
    path = tmp_path/'map.npz'
    np.savez(path, vertices=v, faces=f, uv=v[:, :2]*2)
    bind_material_map(entity, path)
    np.testing.assert_allclose(entity.grasp_material_coordinates, [[.5, .5]])
    np.savez(path, vertices=np.vstack((v, v)), faces=np.vstack((f, f+3)), uv=np.vstack((v[:, :2], v[:, :2]+3)))
    with pytest.raises(ValueError, match='Ambiguous'):
        bind_material_map(entity, path)
    np.savez(path, vertices=v, faces=[[0,1,7]], uv=v[:, :2])
    with pytest.raises(ValueError, match='indices'):
        bind_material_map(entity, path)
    np.savez(path, vertices=v, faces=[[0,0,1]], uv=v[:, :2])
    with pytest.raises(ValueError, match='Degenerate'):
        bind_material_map(entity, path)
