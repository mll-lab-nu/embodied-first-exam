"""Occluded corners must be opened from the visible material boundary."""
import numpy as np
import pytest
from topogym.tasks.blanket_flatten.grasp_sites import exposed_boundary_site, reachable_target_xy, carry_waypoints_xy


def test_occluded_corner_selects_visible_boundary_not_nearby_other_layer_or_interior():
    uv=np.array([[.3,-.24],[.3,-.20],[.295,-.239],[-.3,.24]])
    positions=np.array([[0,0,0],[.03,0,0],[.02,.03,0],[0,0,.03]])
    site=exposed_boundary_site(positions,uv,0,[.3,.24],material_radius=.16)
    assert site['particle']==1
    assert site['method']=='exposed_boundary_near_occluded_corner'
    assert np.isclose(site['material_distance_from_corner_m'],.04)


def test_occluded_boundary_is_rejected_and_visible_corner_is_preferred():
    uv=np.array([[.3,-.24],[.3,-.20],[-.3,.24],[-.3,.20]])
    positions=np.array([[0,0,0],[.03,0,0],[0,0,.03],[.03,0,.03]])
    assert exposed_boundary_site(positions,uv,0,[.3,.24],material_radius=.16) is None
    positions[0,2]=.04
    assert exposed_boundary_site(positions,uv,0,[.3,.24],material_radius=.16)['particle']==0


def test_visible_but_unreachable_corner_uses_reachable_boundary():
    uv=np.array([[.3,-.24],[.3,-.20]])
    positions=np.array([[.812,0,0],[.79,0,0]])
    site=exposed_boundary_site(positions,uv,0,[.3,.24],material_radius=.16,
                               base_xy=[0,0],radial_limits=[.285,.8],corner_reason='unreachable')
    assert site['particle']==1
    assert site['method']=='exposed_boundary_near_unreachable_corner'


def test_boundary_placement_preserves_reachable_goals_and_projects_near_base_waypoint():
    base=np.array([-.57,0.])
    corner=np.array([-.392,.232])
    np.testing.assert_array_equal(reachable_target_xy(corner,base,[.285,.8]),corner)
    projected=reachable_target_xy([-.392,.20],base,[.285,.8])
    assert np.isclose(np.linalg.norm(projected-base),.30)
    assert projected[0]>-.392 and projected[1]>.20
    assert np.isclose(np.linalg.norm(reachable_target_xy([.30,0],base,[.285,.8])-base),.785)


def test_carry_across_sides_keeps_every_segment_outside_base_zone():
    base=np.array([-.57,0.]);start=np.array([-.345,.2]);target=np.array([-.382,-.292])
    path=carry_waypoints_xy(start,target,base,[.285,.8],lane_x=-.1)
    np.testing.assert_array_equal(path[-1],target)
    assert len(path)>1
    for a,b in zip([start,*path],path):
        points=a+np.linspace(0,1,201)[:,None]*(b-a)
        radius=np.linalg.norm(points-base,axis=1)
        assert radius.min()>=.285 and radius.max()<=.8
    # A lane too close to the base is rejected instead of commanding the robot.
    with pytest.raises(ValueError):
        carry_waypoints_xy(start,target,base,[.285,.8],lane_x=-.5)
    straight=carry_waypoints_xy([-.1,-.2],[.08,.292],base,[.285,.8],lane_x=-.1)
    assert len(straight)==1
