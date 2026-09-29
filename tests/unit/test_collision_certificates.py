"""共享盒/凸体查询及连续几何证书；只编写，未执行，不证明物理可行性。"""
import numpy as np
import pytest
import trimesh
from scipy.spatial.transform import Rotation

from topogym.evaluation.motion_certificate import certify_motion
from topogym.utils.geometry.rigid_motion import RigidMotionSegment
from topogym.solvers.collision.box_compounds import BoxCompoundCollision
from topogym.solvers.collision.convex_compounds import ConvexCompoundCollision


@pytest.fixture(params=["boxes", "convex_meshes"])
def collision_factory(request):
    def make(fixed_extent=(1., 1., 1.), moving_extent=(1., 1., 1.)):
        if request.param == "boxes":
            fixed, moving = np.asarray(fixed_extent) / 2, np.asarray(moving_extent) / 2
            return BoxCompoundCollision([[-fixed, fixed]], [[-moving, moving]])
        return ConvexCompoundCollision([trimesh.creation.box(extents=fixed_extent)],
                                       [trimesh.creation.box(extents=moving_extent)])
    return make


def test_signed_gap_distinguishes_separation_contact_and_containment(collision_factory):
    collision = collision_factory()
    assert collision.gap(np.eye(3), [2., 0., 0.]) == pytest.approx(1.)
    assert collision.gap(np.eye(3), [1., 0., 0.]) == pytest.approx(0., abs=1e-12)
    assert collision.gap(np.eye(3), [0., 0., 0.]) < 0
    contained = collision_factory(fixed_extent=(4., 4., 4.))
    assert contained.gap(np.eye(3), [0., 0., 0.]) < 0


def test_rotation_changes_clearance_and_material_displacement_bound(collision_factory):
    collision = collision_factory(moving_extent=(1.6, .2, .2))
    motion = RigidMotionSegment("turn", 4., np.eye(3), np.array([1.2, 0., 0.]),
        axis=np.array([0., 0., 1.]), angle_rad=np.pi/2, pivot=np.array([1.2, 0., 0.]))
    assert collision.gap(*motion.pose(0.)) < 0
    assert collision.gap(*motion.pose(1.)) == pytest.approx(.6)
    np.testing.assert_allclose(motion.pose(1.)[0], Rotation.from_euler("z", 90, degrees=True).as_matrix())
    assert motion.point_speed_bound(collision.moving_corners) == pytest.approx(np.pi/2*np.hypot(.8, .1))
    assert motion.to_dict()["duration_s"] == 4.


def test_clear_translation_is_certified_using_adaptive_intervals(collision_factory):
    motion = RigidMotionSegment("slide", 3., np.eye(3), np.array([2., 0., 0.]), np.array([2., 2., 0.]))
    result = certify_motion(collision_factory(), motion, margin_m=.2)
    assert result["passed"] and result["witness"] is None
    assert result["certified_intervals"] > 1
    assert result["certified_separation_lower_bound_m"] >= .2


def test_clear_orbit_is_certified_for_both_collision_solvers(collision_factory):
    motion = RigidMotionSegment("orbit", 2., np.eye(3), np.array([3., 0., 0.]),
        axis=np.array([0., 0., 1.]), angle_rad=np.pi/2, pivot=np.zeros(3))
    np.testing.assert_allclose(motion.pose(1.)[1], [0., 3., 0.], atol=1e-12)
    result = certify_motion(collision_factory(), motion, margin_m=.2)
    assert result["passed"] and result["certified_separation_lower_bound_m"] >= .2


def test_clear_endpoints_cannot_hide_a_mid_motion_collision(collision_factory):
    collision = collision_factory()
    motion = RigidMotionSegment("cross_obstacle", 1., np.eye(3),
                               np.array([-2., 0., 0.]), np.array([2., 0., 0.]))
    assert all(collision.gap(*motion.pose(u)) > .2 for u in (0., 1.))
    result = certify_motion(collision, motion, margin_m=.2)
    assert not result["passed"]
    assert result["witness"]["u"] == .5
    assert result["witness"]["gap_m"] < 0
    assert result["certified_separation_lower_bound_m"] is None


def test_unresolved_interval_is_not_reported_as_safe(collision_factory):
    motion = RigidMotionSegment("needs_subdivision", 1., np.eye(3),
                               np.array([2., 0., 0.]), np.array([2., 2., 0.]))
    result = certify_motion(collision_factory(), motion, margin_m=.2, max_depth=0)
    assert not result["passed"]
    assert result["witness"]["reason"] == "continuous interval unresolved"
    assert result["witness"]["gap_m"] >= .2


def test_motion_requires_unit_rotation_axis_for_a_valid_speed_bound():
    with pytest.raises(ValueError, match="unit axis"):
        RigidMotionSegment("invalid_axis", 1., np.eye(3), np.zeros(3),
                           axis=np.array([0., 0., 2.]), angle_rad=1., pivot=np.zeros(3))


def test_inverse_design_screw_motion_extends_the_shared_segment():
    from topogym.planning.motions.cast_coil import ScrewMotion

    motion = ScrewMotion("screw", 2., np.eye(3), np.zeros(3),
        axis=np.array([0., 0., 1.]), angle_rad=np.pi/2, pivot=np.zeros(3), advance=np.array([0., 0., .2]))
    assert isinstance(motion, RigidMotionSegment)
    np.testing.assert_allclose(motion.pose(1.)[1], [0., 0., .2])
    assert motion.point_speed_bound(np.array([[1., 0., 0.]])) == pytest.approx(np.pi/2 + .2)
    assert motion.to_dict()["advance"] == [0., 0., .2]
