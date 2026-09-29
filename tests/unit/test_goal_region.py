from dataclasses import replace
import numpy as np
import pytest
import trimesh
from topogym.assets.geometry.goal_region import write_goal_region
from topogym.utils.geometry.regions import placement_measurements
from terminal_fixtures import region


def test_whole_shape_height_and_remainder_not_centers():
    r = region()
    assert r.contains([[1,0,.8],[1.19,0,.8]])
    assert not r.contains([[1,0,.8],[1.2,0,.8]])
    assert not r.contains([[1,0,1.5]])
    result = placement_measurements(r,{"ring":[[1,0,.8]]},{"system":[[0,0,.8],[.51,0,.8]]})
    assert result["all_target_inside"] and not result["remainder_on_system_side"]
    with pytest.raises(ValueError):
        placement_measurements(r,{"ring":[]},{"system":[[0,0,.8]]})


def test_rotated_volume_and_separator_validation():
    r = replace(region(), yaw_deg=45.)
    point = r.rotation@np.array([.19,.19])+r.center_xy_m
    assert r.contains([[*point,.8]])
    assert not r.contains([[1.19,.19,.8]])
    with pytest.raises(ValueError, match="overlaps"):
        replace(r, center_xy_m=(.5,0.))


def test_marker_is_visual_only_and_inner_edges_match_region(tmp_path):
    r = region()
    spec = write_goal_region(tmp_path,r)
    assert spec.morph_options["collision"] is False
    assert spec.morph_options["file_meshes_are_zup"] is True and spec.morph_options["align"] is False
    mesh = trimesh.load(spec.asset_path,force="mesh",process=False)
    extent = np.max(mesh.vertices[:,0])-r.center_xy_m[0]
    assert extent == pytest.approx(r.half_size_m[0]-r.boundary_margin_m+.002)
    assert np.min(mesh.vertices[:,2]) > r.table_height_m
    observation = r.observation(("cord","handle"),("fixture",))
    assert observation["target_entities"] == ["cord","handle"]
    assert observation["goal_region"]["separator_offset_m"] == r.separator_offset_m
