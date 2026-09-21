"""Conservation, dissipation, and material-mass scaling of the damping model."""
import unittest
import numpy as np
from scipy.spatial.transform import Rotation
from topogym.tasks.rope_threading.deformation_damping import DeformationDamping, dissipative_forces


class DampingChecks(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.x = rng.normal(size=(30, 3))*.1+[.2, -.1, 1.]
        self.v = rng.normal(size=(30, 3))*.2
        self.m = rng.uniform(.001, .003, 30)

    def test_rigid_motion_receives_no_force(self):
        v = np.array([.3, -.2, .7])+np.cross([1., -2., .5], self.x)
        f, _ = dissipative_forces(self.x, v, self.m, 2., .00125)
        np.testing.assert_allclose(f, 0., atol=1.e-14)

    def test_deformation_loses_energy_without_changing_momenta(self):
        f, audit = dissipative_forces(self.x, self.v, self.m, 2., .00125)
        np.testing.assert_allclose(f.sum(axis=0), 0., atol=1.e-14)
        np.testing.assert_allclose(np.cross(self.x, f).sum(axis=0), 0., atol=1.e-14)
        after = self.v+.00125*f/self.m[:, None]
        delta = .5*np.sum(self.m[:, None]*(after*after-self.v*self.v))
        self.assertLess(delta, 0.)
        self.assertAlmostEqual(delta, audit["force_only_kinetic_change_j"], places=14)

    def test_force_is_independent_of_world_frame(self):
        q = Rotation.from_euler("xyz", [.4, .7, -.2]).as_matrix()
        a, _ = dissipative_forces(self.x, self.v, self.m, 2., .00125)
        b, _ = dissipative_forces(self.x@q.T+[5., -7., 2.], self.v@q.T+[.8, -.2, 1.], self.m, 2., .00125)
        np.testing.assert_allclose(b, a@q.T, atol=1.e-14)

    def test_splitting_material_mass_preserves_its_total_force(self):
        a, _ = dissipative_forces(self.x, self.v, self.m, 2., .00125)
        b, _ = dissipative_forces(np.repeat(self.x, 2, axis=0), np.repeat(self.v, 2, axis=0),
                                  np.repeat(self.m/2, 2), 2., .00125)
        np.testing.assert_allclose(b.reshape(-1, 2, 3).sum(axis=1), a, atol=1.e-14)

    def test_shared_native_flag_does_not_leave_position_springs_after_release(self):
        import uipc
        from types import SimpleNamespace
        from uipc.constitution import SoftPositionConstraint, FiniteElementExternalForce
        from topogym.world.genesis_ipc_vertex_constraints import _SPECS
        mesh = uipc.geometry.tetmesh(np.array([[0., 0, 0], [1., 0, 0], [0., 1, 0], [0., 0, 1]]),
                                    np.array([[0, 1, 2, 3]], dtype=np.int32))
        SoftPositionConstraint().apply_to(mesh, 100.)
        FiniteElementExternalForce().apply_to(mesh, np.zeros(3))
        uid = "damping_flag_test"
        spec = SimpleNamespace(follow_verts=[np.array([0, 1])], engaged=[True],
            targets=[np.array([[.1, 0, 0], [1.1, 0, 0]])], follow_selectors=[(None, None, 100.)])
        damping = DeformationDamping.__new__(DeformationDamping)
        damping.rope, damping.force = SimpleNamespace(uid=uid), np.arange(12).reshape(4, 3)*.001
        damping.prepared_steps = 7
        info = SimpleNamespace(geo_slots=lambda: [SimpleNamespace(geometry=lambda: mesh)])
        _SPECS[uid] = spec
        try:
            damping._animate_force_and_grasps(info)
            np.testing.assert_array_equal(mesh.vertices().find("strength_ratio").view().reshape(-1), [100., 100., 0., 0.])
            spec.engaged[0] = False
            damping._animate_force_and_grasps(info)
            np.testing.assert_array_equal(mesh.vertices().find("strength_ratio").view().reshape(-1), 0.)
            np.testing.assert_array_equal(mesh.vertices().find("external_force").view().reshape(-1, 3), damping.force)
            np.testing.assert_array_equal(mesh.vertices().find("is_constrained").view().reshape(-1), 1)
        finally:
            _SPECS.pop(uid)


if __name__ == "__main__":
    unittest.main()
