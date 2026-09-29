"""Independent material fixtures, registered only by the test owner."""
from contextlib import contextmanager
from pathlib import Path
import numpy as np
from topogym.tasks.base import TaskDefinition, TaskSpec, EntitySpec


def cloth_asset(folder, center, *, length=.16, width=.12, spacing=.008):
    from topogym.utils.geometry.rope import write_obj
    x = np.linspace(-length/2, length/2, int(round(length/spacing))+1)
    y = np.linspace(-width/2, width/2, int(round(width/spacing))+1)
    uv = np.array([(a, b) for a in x for b in y])
    vertices = np.column_stack((uv, np.zeros(len(uv)))) + center
    faces = []
    for i in range(len(x)-1):
        for j in range(len(y)-1):
            a = i*len(y)+j
            faces.extend(((a, a+len(y), a+len(y)+1), (a, a+len(y)+1, a+1)))
    faces = np.asarray(faces, dtype=int)
    path, mapping = folder/'cloth.obj', folder/'material.npz'
    write_obj(path, vertices, faces)
    np.savez_compressed(mapping, vertices=vertices, faces=faces, uv=uv)
    return path, mapping


class SoftGraspTask(TaskDefinition):
    task_id = 'pbd_grasp_fixture'
    physics_model = 'pbd_cloth'
    model_revision = 'soft_grasp_fixture_v1'
    goal_complete = False
    defaults = dict(stable_duration_s=.2, center_xy=[-.1, -.1],
                    length_m=.16, width_m=.12, spacing_m=.008)

    def declare(self, asset_dir, table_height_m):
        from topogym.assets.geometry.rope_volume import write_rope_volume
        from topogym.assets.materials import rope_fem_parameters, rope_ipc_parameters
        from topogym.utils.geometry.rope import make_elastic_tube_mesh, write_obj
        folder = Path(asset_dir)
        folder.mkdir(parents=True, exist_ok=True)
        self.table_z = table_height_m
        self.center = np.array([*self.config['center_xy'], table_height_m+.006])
        if self.physics_model == 'pbd_cloth':
            path, mapping = cloth_asset(folder, self.center, length=self.config['length_m'],
                                        width=self.config['width_m'], spacing=self.config['spacing_m'])
            entity = EntitySpec('soft', 'mesh', path, physics_model='pbd_cloth',
                material={}, material_map_path=mapping,
                morph_options=dict(decimate=False, convexify=False, file_meshes_are_zup=True),
                surface=dict(color=(.85, .3, .2), vis_mode='visual'))
            options = dict(pbd=dict(particle_size=.006, max_stretch_solver_iterations=12))
        else:
            profile = self.config['rope_profile']
            material = rope_fem_parameters()
            options = dict(fem={}, ipc={})
            if profile == 'v13_material_mesh':
                from fixtures.fem_rope_profiles import historical_rope_asset
                path, volume = historical_rope_asset(folder, self.center, self.config['length_m'])
                options['ipc'] = rope_ipc_parameters()
            elif profile == 'baseline':
                material = dict(model='stable_neohookean', E=1e6, nu=.45, rho=1100., friction_mu=.3)
                line = np.column_stack((np.linspace(-self.config['length_m']/2, self.config['length_m']/2, 17), np.zeros(17), np.zeros(17)))+self.center
                volume = write_rope_volume(folder/'volume.npz', line, .004, spacing=self.config['spacing_m'], profile='structured_baseline')
                vertices, faces = make_elastic_tube_mesh(line, radius=.004, radial_segments=8)
                path = folder/'rope.obj'
                write_obj(path, vertices, faces)
            else:
                raise ValueError(f'Unknown FEM rope fixture profile: {profile}')
            entity = EntitySpec('soft', 'mesh', path, physics_model='fem_elastic',
                volume_path=volume, material=material,
                morph_options=dict(decimate=False, convexify=False), surface=dict(color=(.85, .3, .2)))
        return TaskSpec((entity,), options, dict(scope='independent material grasp fixture'))

    def evaluate_state(self, state):
        points = state['particles' if self.physics_model == 'pbd_cloth' else 'fem']['soft']['position_m']
        return False, None, dict(min_height_m=float(points[:, 2].min()-self.table_z),
                                max_height_m=float(points[:, 2].max()-self.table_z))


class FEMGraspTask(SoftGraspTask):
    task_id = 'fem_grasp_fixture'
    physics_model = 'fem_ipc'
    model_revision = 'fem_grasp_fixture_v2_shared_rope'
    defaults = dict(SoftGraspTask.defaults, rope_profile='v13_material_mesh')


@contextmanager
def register_soft_grasp():
    from topogym.config import registry, variation_records
    old = variation_records.RECORDS
    classes = (SoftGraspTask, FEMGraspTask)
    for cls in classes:
        if cls.task_id in registry._TASKS:
            raise RuntimeError('Test material fixture already registered')
    try:
        for cls in classes:
            implementation = f'fixtures.soft_grasp:{cls.__name__}'
            registry._TASKS[cls.task_id] = registry.TaskRegistration(cls.task_id, implementation, cls.physics_model, 'panda_robotiq')
            variation_records.RECORDS = (*variation_records.RECORDS, dict(task_id=cls.task_id,
                variation_id='base', aliases=[], status='integrated', implementation=implementation,
                family_id='test', difficulty=None, model_revision=cls.model_revision,
                reason=None, validation='test_only', pool='test'))
        yield
    finally:
        for cls in classes:
            registry._TASKS.pop(cls.task_id, None)
        variation_records.RECORDS = old
