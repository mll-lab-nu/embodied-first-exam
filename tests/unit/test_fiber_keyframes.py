"""Fiber key poses: strand measures, roll rule, sheath poses and strand margin."""
from types import SimpleNamespace

import fcl
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.fiber_bundling.keyframes import (FRONT_M, comb_keyframes, front_point, reference_rotation,
                                                       roll_choices, sheath_pose, strand_measures)
from topogym.planning.fiber_bundling.kinematics import STRAND_MARGIN_M, FiberIK

LAYOUT = SimpleNamespace(fiber_count=2, fiber_segments=3, fiber_length_m=.03, trunk_segments=6, trunk_length_m=.24,
                         ring_inner_radius_m=.0135, ring_tube_radius_m=.004, fiber_radius_m=.0012)
CENTER = np.array([.25, -.25, 1.1596])


def link(position, direction=(1., 0., 0.)):
    r, _ = Rotation.align_vectors([direction], [[1., 0., 0.]])
    return dict(position_m=list(position), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist())


def state():
    front = np.array([.14, -.25, 1.1596])
    links = {"trunk_04": link(front-[.08, 0, 0]), "trunk_05": link(front-[.04, 0, 0])}
    # Strand 0 leaves axially from the top of the face, then bends 30 degrees up.
    a = front+[0, 0, .008]
    b = a+[.01, 0, 0]
    up = np.array([np.cos(np.radians(30)), 0, np.sin(np.radians(30))])
    for j, (p, d) in enumerate([(a, (1, 0, 0)), (b, up), (b+.01*up, up)]):
        links[f"fiber_00_{j:02d}"] = link(p, d)
    # Strand 1 is straight, 8 mm off the axis on +y.
    for j in range(3):
        links[f"fiber_01_{j:02d}"] = link(front+[.01*j, .008, 0])
    ring_q = Rotation.from_euler("y", 90, degrees=True).as_quat()[[3, 0, 1, 2]].tolist()
    return dict(bodies=dict(bundling_ring=dict(position_m=CENTER.tolist(), quaternion_wxyz=ring_q)),
                articulations=dict(fiber_bundle=dict(links=links)))


def test_strand_measures_report_radius_bend_fan_and_tip_position():
    bent, straight = strand_measures(state(), LAYOUT)
    np.testing.assert_allclose(straight["max_radius_m"], .008, atol=1e-9)
    np.testing.assert_allclose(straight["max_bend_deg"], 0., atol=1e-6)
    np.testing.assert_allclose(straight["fan_deg"], 90., atol=1e-6)
    np.testing.assert_allclose(straight["tip_ahead_of_front_m"], .03, atol=1e-9)
    np.testing.assert_allclose(bent["max_radius_m"], .008+.02*np.sin(np.radians(30)), atol=1e-9)
    np.testing.assert_allclose(bent["max_bend_deg"], 30., atol=1e-6)
    np.testing.assert_allclose(bent["fan_deg"], 0., atol=1e-6)


def test_roll_rule_turns_upward_strands_to_the_side_and_matches_sheath_roll():
    assert roll_choices(0.) == [-70., 70.]
    assert roll_choices(90.) == [0., -70.]
    assert roll_choices(-150.) == [0., -70., 70.]
    # A strand fanning to reference +y points straight up after a +90 degree roll:
    # world fan angle = fan - roll, the convention roll_choices uses.
    _, r = sheath_pose(CENTER, np.array([1., 0, 0]), np.zeros(3), 90., 0.)
    np.testing.assert_allclose(r.apply([0., 1., 0.]), [0., 0., 1.], atol=1e-12)


def test_sheath_pose_places_the_front_point_and_keeps_z_up_without_roll():
    axis = np.array([1., 0, 0])
    offset = np.array([0., -.03, .01])
    p, r = sheath_pose(CENTER, axis, offset, 0., -.11)
    np.testing.assert_allclose(front_point(p, r), CENTER+offset-.11*axis, atol=1e-12)
    np.testing.assert_allclose(p, CENTER+offset-(.11+FRONT_M)*axis, atol=1e-12)
    np.testing.assert_allclose(reference_rotation(axis).as_matrix(), np.eye(3), atol=1e-12)


def test_comb_offsets_the_sheath_opposite_the_strand_and_presses_to_d_press():
    a, b, geometry = comb_keyframes(state(), LAYOUT, 1, .034, 0.)
    assert [row["label"] for row in a] == ["measured_start", "select", "approach", "press", "slide"]
    assert [row["label"] for row in b] == ["slide", "release", "center"]
    np.testing.assert_allclose(geometry["press_direction"], [0., 1., 0.], atol=1e-12)
    np.testing.assert_allclose(geometry["d0_m"], .0215+.0012+.008+.008, atol=1e-9)
    np.testing.assert_allclose(geometry["approach_front_s_m"], .004-.03, atol=1e-9)

    def front(row):
        return front_point(np.asarray(row["position_m"]), Rotation.from_quat(np.r_[row["quaternion_wxyz"][1:],
                                                                                   row["quaternion_wxyz"][0]]))
    np.testing.assert_allclose(front(a[1]), CENTER+[-.046, -geometry["d0_m"], 0.], atol=1e-9)
    np.testing.assert_allclose(front(a[3]), CENTER+[-.026, -.034, 0.], atol=1e-9)
    np.testing.assert_allclose(front(a[4]), CENTER+[-.046, -.034, 0.], atol=1e-9)
    np.testing.assert_allclose(front(b[2]), CENTER+[-.11, 0., 0.], atol=1e-9)


def test_gripper_to_strand_gap_is_reduced_by_the_strand_margin():
    def box(x):
        obj = fcl.CollisionObject(fcl.Box(.01, .01, .01))
        obj.setTransform(fcl.Transform(np.eye(3), [x, 0., 0.]))
        return obj

    def managed(*objects):
        result = fcl.DynamicAABBTreeCollisionManager()
        result.registerObjects(list(objects))
        result.setup()
        return result
    kin = FiberIK.__new__(FiberIK)
    kin.held_objects, kin.strand_objects = [box(0.)], [box(0.)]
    kin.held_manager, kin.strand_manager = managed(*kin.held_objects), managed(*kin.strand_objects)
    kin.obstacles, kin.gripper_manager = managed(box(1.5)), managed(box(-.015))
    held, strand = kin.held_gaps((np.array([0., 0., 0.]), Rotation.identity()))
    np.testing.assert_allclose(held, 1.49, atol=1e-6)
    np.testing.assert_allclose(strand, .005-STRAND_MARGIN_M, atol=1e-6)
