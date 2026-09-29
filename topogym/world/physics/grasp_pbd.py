"""Local PBD cloth attachment through native link offsets, with explicit limits."""
import numpy as np
import weakref
from importlib.metadata import version
from topogym.utils.arrays import to_numpy
from .grasp_soft import SoftGraspBackend


class PBDGraspBackend(SoftGraspBackend):
    evidence_source = 'pbd_bilateral_finger_surface_proximity'

    def __init__(self, world, robot, config):
        super().__init__(world, robot, config)
        self.coupler = world.scene.sim.coupler
        if not hasattr(self.coupler, 'particle_attach_info'):
            raise ValueError('PBD grasp requires native PBD-rigid coupling')
        for name, entity in self.entities.items():
            uv = getattr(entity, 'grasp_material_coordinates', None)
            if uv is None:
                raise ValueError('PBD grasp requires a verified birth material map')
            self.initialize_material(name, uv, uv)
        self._birth_free = {n: self._free(n).copy() for n in self.entities}
        self._birth_links = {n: self._links(n).copy() for n in self.entities}
        self._install_velocity_correction()

    def _install_velocity_correction(self):
        # Genesis 1.2.1 stores cd_vel at root_COM (see get_links_vel), but
        # LegacyCoupler subtracts link_COM when animating attached particles.
        # Add the missing omega x (link_COM-root_COM) term for OUR particles.
        # Keep native position integration, collision, offsets and release.
        if version('genesis-world').split('+')[0] != '1.2.1':
            raise RuntimeError('PBD grasp velocity adapter requires Genesis 1.2.1')
        import quadrants as qd

        @qd.kernel
        def correct(indices: qd.types.ndarray(), attachment: qd.template(), particles: qd.template(),
                    reordered: qd.template(), links: qd.template()):
            for j in range(indices.shape[0]):
                i = indices[j]
                link = attachment[i, 0].link_idx
                if link >= 0:
                    rp = particles[i, 0].reordered_idx
                    reordered[rp, 0].vel += links.cd_ang[link, 0].cross(links.i_pos[link, 0])

        self._correct_velocity = correct
        original = weakref.WeakMethod(self.coupler.couple)
        backend_ref = weakref.ref(self)
        def couple(f):
            original()(f)
            backend = backend_ref()
            if backend is not None and backend.active:
                indices = np.asarray([backend.entities[b['target'][0]]._particle_start+i
                    for b in backend.active.values() for i in b['indices']], dtype=np.int32)
                backend._correct_velocity(indices, backend.coupler.particle_attach_info,
                    backend.coupler.pbd_solver.particles_ng, backend.coupler.pbd_solver.particles_reordered,
                    backend.coupler.rigid_solver.links_state)
        self.coupler.couple = couple

    def positions(self, name):
        return to_numpy(self.entities[name].get_particles_pos()).reshape(-1, 3)

    def read_model(self):
        return dict(super().read_model(), native_velocity_adapter='genesis_1.2.1_root_COM_reference',
                    attachment_scope='native kinematic patch; native rigid collisions still act on attached particles')

    def _range(self, name):
        entity = self.entities[name]
        return slice(entity._particle_start, entity._particle_start + entity.n_particles)

    def _free(self, name):
        return self.entities[name].solver.particles.free.to_numpy()[self._range(name), 0]

    def _links(self, name):
        return self.coupler.particle_attach_info.link_idx.to_numpy()[self._range(name), 0]

    def allowed(self, name):
        # Existing hand bindings remain candidates for explicit conflict checks;
        # permanently fixed birth particles never become temporary grasp points.
        return super().allowed(name) & self._birth_free[name].astype(bool)

    def attach_native(self, binding):
        name, indices = binding['target'][0], binding['indices']
        if not np.all(self._free(name)[indices]) or np.any(self._links(name)[indices] != -1):
            raise ValueError('PBD particles already constrained')
        entity = self.entities[name]
        entity.fix_particles_to_link(self.hands[binding['hand']].idx, particles_idx_local=binding['indices'])

    def detach_native(self, binding):
        name = binding['target'][0]
        self.entities[name].release_particle(particles_idx_local=binding['indices'])
        if np.any(self._links(name)[binding['indices']] != -1) or not np.all(self._free(name)[binding['indices']]):
            raise RuntimeError('PBD native release failed')

    def exists(self, binding):
        name, indices = binding['target'][0], binding['indices']
        actual = self.coupler.particle_attach_info.local_pos.to_numpy()[self._range(name), 0][indices]
        return bool(np.all(self._links(name)[indices] == self.hands[binding['hand']].idx)
                    and not np.any(self._free(name)[indices])
                    and np.allclose(actual, binding['local_offsets'], atol=1e-9, rtol=0))

    def verify_native_ownership(self, bindings):
        hand_ids = [h.idx for h in self.hands.values()]
        for name in self.entities:
            expected = sorted(i for b in bindings if b['target'][0] == name for i in b['indices'])
            fixed = ~self._birth_free[name].astype(bool)
            if (np.any(self._free(name)[fixed] != self._birth_free[name][fixed]) or
                    np.any(self._links(name)[fixed] != self._birth_links[name][fixed])):
                raise ValueError('Permanent PBD constraints changed during grasp')
            actual = np.flatnonzero(~fixed & np.isin(self._links(name), hand_ids)).tolist()
            if actual != expected:
                raise ValueError('Unexpected PBD hand-attached particles')
