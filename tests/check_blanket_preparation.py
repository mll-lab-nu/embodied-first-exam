"""Controls for material-preserving construction of a crossed/twisted initial state."""
import unittest
import numpy as np
import trimesh

from topogym.tasks.blanket_flatten.geometry import BlanketLayout, generate_flat_binding
from topogym.tasks.blanket_flatten.preparation import MaterialVelocityProjection, fold_target, arc_fold_target, twist_target
from topogym.tasks.blanket_flatten.diagnostics import footprint_area


class PreparationChecks(unittest.TestCase):
    def test_longitudinal_gather_preserves_material_order_and_flat_start(self):
        from omegaconf import OmegaConf
        from topogym.tasks.blanket_flatten.gathered_geometry import gathered_target
        cfg = OmegaConf.load('configs/blanket_flatten_gathered_twist.yaml').task.preparation.gathered
        x, y = np.meshgrid(np.linspace(-.3, .3, 61), np.linspace(-.24, .24, 481), indexing='ij')
        uv = np.column_stack((x.ravel(), y.ravel()))
        flat = gathered_target(uv, .6, .48, 0., 0., cfg)
        np.testing.assert_allclose(flat, np.column_stack((uv, np.zeros(len(uv)))), atol=1e-12)
        pleated = gathered_target(uv, .6, .48, 1., 0., cfg).reshape(61, 481, 3)
        # Ordered cross sections prevent layers from crossing while gathering.
        self.assertGreater(np.diff(pleated[:, :, 1], axis=1).min(), 0.)
        np.testing.assert_allclose(np.linalg.norm(np.diff(pleated, axis=1), axis=2).sum(axis=1), .48, atol=.002)
        target = gathered_target(uv, .6, .48, 1., 1., cfg)
        self.assertGreater(np.ptp(target[:, 0]), .55)
        self.assertLess(np.ptp(target[:, 1]), .18)
        # A complete cross section rotates; its radial distances are preserved.
        sway = np.column_stack((float(cfg.centerline_sway_m)*np.sin(2*np.pi*(x[:, 0]/.6+.5)), np.zeros(61)))
        np.testing.assert_allclose(np.linalg.norm(target.reshape(61, 481, 3)[:, :, 1:]-sway[:, None], axis=2),
                                   np.linalg.norm(pleated[:, :, 1:]-sway[:, None], axis=2), atol=1e-12)

    def test_common_tangent_keeps_nested_layers_disjoint(self):
        from shapely.geometry import LineString
        x = np.linspace(-.25, .25, 1001)
        p = np.vstack([np.column_stack((x, np.zeros_like(x), np.full_like(x, z)))
                       for z in [0., .012, .024]])
        for angle in [0., 1., 2., np.pi]:
            target = arc_fold_target(p, [1,0], .5, angle, .005, shared_tangent=True)
            curves = [LineString(layer[:, [0,2]]) for layer in np.split(target, 3)]
            for i in range(3):
                for j in range(i):
                    self.assertFalse(curves[i].intersects(curves[j]))

    def test_nested_fold_preserves_each_layer_arc_length(self):
        x = np.linspace(-.25, .25, 10001)
        lengths = []
        for z in [0., .012, .024]:
            p = np.column_stack((x, np.zeros_like(x), np.full_like(x, z)))
            # Include the upper reference layer in every evaluation.
            all_layers = np.vstack((p, [[-.25, 0., .024], [.25, 0., .024]]))
            np.testing.assert_allclose(arc_fold_target(all_layers, [1,0], .5, 0., .005), all_layers)
            target = arc_fold_target(all_layers, [1,0], .5, np.pi, .005)[:len(x)]
            lengths.append(np.linalg.norm(np.diff(target, axis=0), axis=1).sum())
        np.testing.assert_allclose(lengths, .5, atol=1e-7)

    def test_coverage_with_collapsed_and_nearly_coincident_projections(self):
        v = np.array([[0.,0,0],[.3,0,0],[.3,.48,0],[0,.48,0]])
        faces = np.array([[0,1,2],[0,2,3]])
        # Stacked layers, reverse winding, near-vertical slivers and touching
        # endpoints must still give the same projected material union.
        thin = np.array([[.15,0,.1],[.15+1e-11,0,.2],[.15,.48,.1]])
        vertices = np.vstack((v,v+[1e-12,1e-12,.01],thin))
        triangles = np.vstack((faces,faces[:,::-1]+4,[[8,9,10]]))
        self.assertAlmostEqual(footprint_area(vertices,triangles),.144,places=7)

    def test_preparation_controller_prevents_remote_layers_approaching(self):
        lower = np.array([[0.,0,0],[.1,0,0],[0,.1,0]])
        p = np.vstack((lower, lower+[0,0,.009]))
        edges = np.array([[0,1],[0,2],[1,2],[3,4],[3,5],[4,5]])
        rest = np.linalg.norm(p[edges[:,1]]-p[edges[:,0]], axis=1)
        uv = np.vstack((lower[:,:2], lower[:,:2]+[1,0]))
        projector = MaterialVelocityProjection(edges, rest, len(p), material_uv=uv, clearance=.012)
        requested = np.zeros_like(p)
        requested[:3,2], requested[3:,2] = .1, -.1
        actual = projector.project(p, requested)
        self.assertTrue(np.all(actual[3:,2]-actual[:3,2] > 0))

    def test_velocity_projection_suppresses_stretch_but_allows_rigid_motion(self):
        p = np.array([[0.,0,0],[.1,0,0],[0,.1,0]])
        edges = np.array([[0,1],[0,2],[1,2]])
        rest = np.linalg.norm(p[edges[:, 1]]-p[edges[:, 0]], axis=1)
        projector = MaterialVelocityProjection(edges, rest, len(p))
        expanding = p*2
        projected = projector.project(p, expanding)
        direction = (p[edges[:, 1]]-p[edges[:, 0]])/rest[:, None]
        before = np.sum((expanding[edges[:, 1]]-expanding[edges[:, 0]])*direction, axis=1)
        after = np.sum((projected[edges[:, 1]]-projected[edges[:, 0]])*direction, axis=1)
        self.assertLess(np.linalg.norm(after), np.linalg.norm(before)*.02)
        rigid = np.cross([0,0,1.], p)+[.1,.2,.3]
        np.testing.assert_allclose(projector.project(p, rigid), rigid, atol=1e-10)

    def test_reference_material_remains_one_flat_disk(self):
        v, f, uv, panels, report = generate_flat_binding(BlanketLayout(drop_clearance_m=.22))
        mesh = trimesh.Trimesh(v, f, process=False)
        self.assertEqual(mesh.euler_number, 1)
        self.assertEqual(len(mesh.split(only_watertight=False)), 1)
        self.assertAlmostEqual(mesh.area, .288)
        np.testing.assert_allclose(v[:, :2], uv)
        self.assertEqual(panels.shape, (1, 4))
        self.assertIsNone(report['minimum_nonadjacent_panel_gap_m'])

    def test_diagonal_corner_leaves_other_three_corners_unchanged(self):
        p = np.array([[-.3,-.24,.22],[.3,-.24,.22],[-.3,.24,.22],[.3,.24,.22]])
        np.testing.assert_allclose(fold_target(p, [1, 1], .77, 0, .035), p)
        target = fold_target(p, [1, 1], .77, np.radians(150), .035)
        np.testing.assert_allclose(target[:3], p[:3])
        self.assertGreater(target[3, 2], p[3, 2])
        self.assertLess(target[3, 0], p[3, 0])
        self.assertLess(target[3, 1], p[3, 1])

    def test_twist_rotates_both_ends_of_entire_current_bundle(self):
        p = np.array([[x,y,z] for x in [-.2,.2] for y in [-.04,.04] for z in [-.02,.02]])
        target, axis = twist_target(p, np.pi, .8, np.array([1.,0,0]))
        np.testing.assert_allclose(target[:, 0], .8*p[:, 0])
        np.testing.assert_allclose(np.linalg.norm(target[:, 1:], axis=1), np.linalg.norm(p[:, 1:], axis=1))
        # Opposite 90-degree rotations at the two ends, not a curl at one edge.
        np.testing.assert_allclose(target[:4, 1], p[:4, 2], atol=1e-12)
        np.testing.assert_allclose(target[4:, 1], -p[4:, 2], atol=1e-12)
        identity, _ = twist_target(p, 0, 1, axis)
        np.testing.assert_allclose(identity, p)


if __name__ == '__main__':
    unittest.main()
