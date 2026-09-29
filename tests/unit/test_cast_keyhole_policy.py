"""Coordinate and frozen-instance checks; these do not claim physical success."""
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.cast_keyhole import generate_variant_assets
from topogym.planning.cast_keyhole.policy import (
    ASSEMBLY_ROTATIONS, FAMILIES, GRASP_POINTS, REGRASP_POINTS, PARTS, CastKeyholePolicy,
    canonical_offsets, load_reference,
)


@pytest.mark.parametrize("level", FAMILIES)
def test_real_variant_grasps_are_on_solid_and_com_frames_roundtrip(level, tmp_path):
    assembly, report = generate_variant_assets(tmp_path, f"variations/cast_keyhole/{FAMILIES[level]}/geometry.json")
    origins = {b["name"]: np.asarray(b["origin_m"]) for b in report["bodies"]}
    offsets = canonical_offsets(origins)
    canonical = {}
    bodies = {}
    expected = {}
    for side, name in PARTS.items():
        mesh = next(b.visual for b in assembly.bodies if b.name == name).copy()
        mesh.vertices = ASSEMBLY_ROTATIONS[side].inv().apply(mesh.vertices-origins[name])+offsets[side]
        assert mesh.contains([GRASP_POINTS[side]])[0]
        assert mesh.contains([REGRASP_POINTS[side]])[0]
        canonical[side] = mesh.vertices
        r = Rotation.from_euler("xyz", [33, -17, 48], degrees=True)
        p = np.array([.2, -.13, 1.04])
        expected[side] = (p, r)
        body_r = r*ASSEMBLY_ROTATIONS[side].inv()
        bodies[name] = dict(position_m=p+r.apply(offsets[side]),
            quaternion_wxyz=body_r.as_quat()[[3, 0, 1, 2]])
    policy = CastKeyholePolicy(variation=level, body_origins=origins, goal_region={},
        mount_position=[0., 0., 0.], canonical_vertices=canonical)
    policy.obs = dict(privileged=dict(world=dict(bodies=bodies)))
    for side, (p, r) in policy.bodies().items():
        np.testing.assert_allclose(p, expected[side][0], atol=1e-12)
        assert (r.inv()*expected[side][1]).magnitude() < 1e-12
    reference = load_reference(level)
    assert reference["variation_id"] == "cast_keyhole_"+level
    assert all("qpos" not in frame for frame in reference["frames"])
    assert ("return_to_offset_gate" in {f["stage"] for f in reference["frames"]}) == (level == "hard")


def test_reference_rejects_unknown_variant():
    with pytest.raises(ValueError, match="Unsupported"):
        load_reference("cast_keyhole_retired")


def test_cartesian_move_accepts_tick_just_below_its_final_time():
    policy = object.__new__(CastKeyholePolicy)
    policy.dt = .025
    policy.grip = {"left": .027}
    policy.obs = {"state": {"sim_time_s": 3.4}}
    policy.tcp = lambda: {"left": (np.zeros(3), Rotation.identity())}
    target = (np.array([.1, .1, .1]), Rotation.from_euler("z", 60, degrees=True))
    sequence = policy.move({"left": target}, 3., "test_endpoint")
    next(sequence)
    policy.obs["state"]["sim_time_s"] = 3.4+3.-.025-1e-15
    action = next(sequence)  # An unbounded quintic overshoots SLERP's [0, 1].
    np.testing.assert_allclose(action["left"]["position_world_m"], target[0], atol=1e-12)


def test_relative_path_compaction_keeps_corners_and_rotation_excursion():
    from topogym.planning.cast_keyhole.kinematics import simplify_relative_samples
    identity = Rotation.identity()
    straight = [(np.array([x, 0., 0.]), identity) for x in np.linspace(0., .1, 101)]
    assert len(simplify_relative_samples(straight)) == 2
    corner = (np.array([.05, .004, 0.]), identity)
    bent = straight[:50]+[corner]+straight[51:]
    compact = simplify_relative_samples(bent)
    assert any(np.array_equal(p, corner[0]) for p, _ in compact)
    spin = Rotation.from_euler("z", 3., degrees=True)
    excursion = [(np.zeros(3), identity), (np.zeros(3), spin), (np.zeros(3), identity)]
    assert len(simplify_relative_samples(excursion)) == 3


def test_precise_progress_caps_surface_motion_even_at_high_requested_speed():
    policy = object.__new__(CastKeyholePolicy)
    identity = Rotation.identity()
    initial = {"left": (np.zeros(3), identity), "right": (np.array([.1, 0., 0.]), identity)}
    policy.dt, policy.route_clearance = .025, .0004
    policy.obs = {"state": {"sim_time_s": 0.}, "privileged": {"world": {"bodies": {
        name: dict(linear_velocity_m_s=np.zeros(3), angular_velocity_rad_s=np.zeros(3))
        for name in PARTS.values()}}}}
    policy.origins = {s: np.zeros(3) for s in PARTS}
    policy.bodies = lambda: initial
    policy.bias = {s: np.zeros(3) for s in PARTS}
    policy.angle_bias = {s: np.zeros(3) for s in PARTS}
    policy.grasp_offsets = {s: (np.zeros(3), identity) for s in PARTS}
    policy.grip, policy.diagnostics = {s: .002 for s in PARTS}, {}
    def pose(u):
        return {"left": initial["left"], "right": (initial["right"][0]+[0., .01*u, 0.],
            Rotation.from_euler("x", u*.1))}
    sequence = policy.follow_bodies(pose, .025, "narrow_channel", precise=True)
    next(sequence)
    assert 0. < policy.diagnostics["progress"] < .03
    assert (policy.diagnostics["commanded_relative_step_bound_m"]
            + policy.diagnostics["relative_displacement_bound_m"]) <= .00048


def test_velocity_feedback_uses_canonical_origin_instead_of_moving_com():
    policy = object.__new__(CastKeyholePolicy)
    identity = Rotation.identity()
    poses = {s: (np.zeros(3), identity) for s in PARTS}
    policy.bodies = lambda: poses
    policy.dt, policy.derivative_gain = .025, .06
    policy.origins = {s: np.array([.1, 0., 0.]) for s in PARTS}
    policy.bias = {s: np.zeros(3) for s in PARTS}
    policy.angle_bias = {s: np.zeros(3) for s in PARTS}
    policy.grasp_offsets = {s: (np.zeros(3), identity) for s in PARTS}
    policy.grip, policy.diagnostics = {s: .002 for s in PARTS}, {}
    policy.obs = {"privileged": {"world": {"bodies": {
        name: dict(linear_velocity_m_s=[0., .01, 0.], angular_velocity_rad_s=[0., 0., .1])
        for name in PARTS.values()}}}}
    action = policy.attached_targets(poses)
    for side in PARTS:
        np.testing.assert_allclose(action[side]["position_world_m"], 0., atol=1e-15)
        q = np.asarray(action[side]["orientation_wxyz"])[[1, 2, 3, 0]]
        np.testing.assert_allclose(Rotation.from_quat(q).as_rotvec(), [0., 0., -.006], atol=1e-15)
