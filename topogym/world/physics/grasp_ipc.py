"""Scene-owned FEM grasp bands using libuipc SoftPositionConstraint.

Constraint activation/animation extracted from cb60f01b's FollowHandle logic;
no historical module, global patch or task runner is imported.
"""
from itertools import combinations
import numpy as np
from topogym.utils.arrays import to_numpy
from .grasp_soft import SoftGraspBackend


class IPCGraspBackend(SoftGraspBackend):
    evidence_source = 'ipc_bilateral_finger_surface_proximity'

    def __init__(self, world, robot, config):
        super().__init__(world, robot, config)
        self.coupler = world.scene.sim.coupler
        if not hasattr(self.coupler, 'fem_grasp_specs'):
            raise ValueError('IPC grasp requires prepared native constraints')
        self.forbidden = {}
        self.surface_masks = {}
        for name, entity in self.entities.items():
            if entity not in self.coupler.fem_grasp_specs:
                raise ValueError('IPC grasp capacity must be declared before build')
            edges = np.unique(np.concatenate([entity.elems[:, [a, b]] for a, b in combinations(range(4), 2)]), axis=0)
            self.initialize_material(name, entity.material_coordinates[:, :1], entity.material_coordinates, edges)
            self.forbidden[name] = np.zeros(entity.n_vertices, dtype=bool)
            self.surface_masks[name] = np.zeros(entity.n_vertices, dtype=bool)
            self.surface_masks[name][np.unique(entity.surface_triangles)] = True
            for _, soft, indices, _, _ in self.coupler.attachment_pairs:
                if soft is entity:
                    self.forbidden[name][indices] = True
        self.coupler.grasp_backend = self

    def positions(self, name):
        from .fem import read_vertices
        return read_vertices(self.entities[name])['position_m']

    def allowed(self, name):
        return super().allowed(name) & ~self.forbidden[name]

    def candidate_mask(self, name):
        return self.allowed(name) & self.surface_masks[name]

    def geometry(self, name):
        return self.coupler.fem_slots[self.entities[name]].geometry()

    def flags(self, name):
        return np.asarray(self.geometry(name).vertices().find('is_constrained').view()).reshape(-1)

    def attach_native(self, binding):
        import uipc
        geometry = self.geometry(binding['target'][0])
        indices = binding['indices']
        if np.any(self.flags(binding['target'][0])[indices]):
            raise ValueError('IPC vertices already constrained')
        uipc.view(geometry.vertices().find('aim_position')).reshape(-1, 3)[indices] = self.positions(binding['target'][0])[indices]
        uipc.view(geometry.vertices().find('is_constrained')).reshape(-1)[indices] = 1

    def detach_native(self, binding):
        import uipc
        geometry = self.geometry(binding['target'][0])
        uipc.view(geometry.vertices().find('is_constrained')).reshape(-1)[binding['indices']] = 0

    def exists(self, binding):
        return bool(np.all(self.flags(binding['target'][0])[binding['indices']] == 1))

    def update_entity_targets(self, entity, geometry):
        import uipc
        name = next(n for n, e in self.entities.items() if e is entity)
        flags = uipc.view(geometry.vertices().find('is_constrained')).reshape(-1)
        targets = uipc.view(geometry.vertices().find('aim_position')).reshape(-1, 3)
        flags[:] = 0  # Only the scene's temporary SPC field, never permanent stitch.
        for binding in self.active.values():
            if binding['target'][0] == name:
                indices = binding['indices']
                targets[indices] = self.targets(binding)
                flags[indices] = 1

    def verify_native_ownership(self, bindings):
        for name in self.entities:
            expected = sorted(i for b in bindings if b['target'][0] == name for i in b['indices'])
            if np.flatnonzero(self.flags(name)).tolist() != expected:
                raise ValueError('IPC checkpoint temporary constraints differ from ownership')

    def check_health(self, binding):
        reason = super().check_health(binding)
        entity = self.entities[binding['target'][0]]
        x = self.positions(binding['target'][0])[entity.elems]
        if np.any(np.linalg.det(x[:, 1:]-x[:, :1]) <= 0):
            return 'inverted_material'
        return reason
