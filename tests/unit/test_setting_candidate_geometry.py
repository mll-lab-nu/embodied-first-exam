from dataclasses import replace

import numpy as np
import pytest

from topogym.assets.geometry.rope_threading import ThreadingLayout, inspect_geometry, generate_assets
from topogym.assets.geometry.orbits import OrbitsLayout, make_meshes, winding_numbers, cord_centerline
from topogym.assets.geometry.orbits_initial import natural_working_state, working_cord


@pytest.mark.parametrize("ids", [(), ("R1", "R1"), ("R4",), ("R2", "R1")])
def test_rope_selection_rejects_invalid_material_order(ids):
    with pytest.raises(ValueError, match="ordered subset"):
        ThreadingLayout(ring_ids=ids)


def test_rope_selection_preserves_source_identity_and_removes_fixture(tmp_path):
    baseline = ThreadingLayout()
    candidate = ThreadingLayout(ring_ids=("R1", "R2"))
    np.testing.assert_array_equal(candidate.centerline(), baseline.centerline())
    assert candidate.rings() == baseline.rings()[:2]
    assert candidate.required_crossings() == [("R1", -1), ("R2", 1)]
    report = generate_assets(tmp_path, candidate)
    assert report["target_material_order"] == ["R1-", "R2+"]
    assert (tmp_path/"R2_stand.obj").exists()
    assert not any(p.name.startswith("R3") for p in tmp_path.iterdir())


def test_rope_aperture_moves_mount_but_keeps_ring_plane_and_rope():
    baseline = ThreadingLayout()
    candidate = replace(baseline, ring_inner_radius_m=.050)
    np.testing.assert_array_equal(candidate.centerline(), baseline.centerline())
    for old, new in zip(baseline.rings(), candidate.rings()):
        assert new["center_m"] == old["center_m"]
        assert new["normal"] == old["normal"]
        assert new["radius_m"]-new["tube_radius_m"] == pytest.approx(.050)
        stand_top = candidate.transform(new["stand"]["position"])
        stand_top[2] += new["stand"]["size"][1]
        rim = np.asarray(new["center_m"])+new["radius_m"]*np.asarray(new["basis_u"])
        np.testing.assert_allclose(stand_top, rim, atol=1e-9)
    assert inspect_geometry(candidate)["ring_aperture_diameter_m"] == pytest.approx(.1)
    rotated = replace(candidate, yaw_deg=63.)
    assert inspect_geometry(rotated)["minimum_fixture_gap_lower_bound_m"] == pytest.approx(
        inspect_geometry(candidate)["minimum_fixture_gap_lower_bound_m"])


def test_rope_selection_does_not_silently_publish_stale_removed_assets(tmp_path):
    (tmp_path/"R3.obj").write_text("old generated ring")
    with pytest.raises(ValueError, match="fresh asset directory"):
        generate_assets(tmp_path, ThreadingLayout(ring_ids=("R1", "R2")))
    assert (tmp_path/"R3.obj").read_text() == "old generated ring"


@pytest.mark.parametrize("radius", [0, .003, float("nan"), True])
def test_rope_invalid_aperture(radius):
    with pytest.raises(ValueError, match="inner radius"):
        ThreadingLayout(ring_inner_radius_m=radius)


@pytest.mark.parametrize("count", [2, 3, 4])
def test_orbits_keeps_ring_post_connections_and_last_post_bight(count):
    layout = OrbitsLayout(ring_count=count).scaled(.75)
    parts, cord = make_meshes(layout)
    assert len([name for name in parts if name.startswith("ring_")]) == count
    assert len([name for name in parts if name.startswith("post_")]) == count+1
    for i in range(count):
        ring = parts[f"ring_{i+1}"]
        assert ring.is_watertight and ring.euler_number == 0
        center = ring.bounds.mean(axis=0)
        np.testing.assert_allclose(center, [layout.post_x[i+1]-layout.ring_radius_m, 0, layout.ring_z[i]], atol=1e-9)
    np.testing.assert_allclose(abs(np.array(winding_numbers(cord, layout.post_x))), [0]*count+[1], atol=1e-8)
    np.testing.assert_allclose(cord[[0, -1], :2], layout.eyes)


@pytest.mark.parametrize("count", [1, 5, 2., True])
def test_orbits_unsupported_counts_fail(count):
    with pytest.raises(ValueError, match="two, three or four"):
        OrbitsLayout(ring_count=count).validate()


@pytest.mark.parametrize("count", [2, 3])
def test_reduced_orbits_requires_explicit_slack_and_preserves_chosen_length(count):
    layout = OrbitsLayout(ring_count=count).scaled(.75)
    with pytest.raises(ValueError, match="explicit cord_length_m"):
        natural_working_state(layout)
    with pytest.raises(ValueError, match="only for four rings"):
        working_cord(layout)
    handle_x = .45
    placed = replace(layout, handle_x_m=handle_x)
    cord_length = np.linalg.norm(np.diff(cord_centerline(placed), axis=0), axis=1).sum()+.1
    points, handle = natural_working_state(layout, handle_x_m=handle_x, cord_length_m=cord_length)
    assert np.linalg.norm(np.diff(points, axis=0), axis=1).sum() == pytest.approx(cord_length, abs=1e-9)
    assert handle[0] == handle_x
    np.testing.assert_allclose(abs(np.array(winding_numbers(points, layout.post_x))), [0]*count+[1], atol=1e-8)
