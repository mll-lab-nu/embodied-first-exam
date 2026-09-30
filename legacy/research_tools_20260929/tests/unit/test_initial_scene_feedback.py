"""Geometry invariants for the September feedback, independent of render success."""
import numpy as np
import pytest
import trimesh
from scipy.spatial.transform import Rotation
from topogym.config.registry import task_definition, variation_catalog


def test_formal_inventory_and_knot_migration():
    from topogym.config.registry import task_catalog
    rows = [row for task in task_catalog() for row in variation_catalog(task['task_id'])]
    assert sum(row['pool'] == 'tier' for row in rows) == 39
    families = [task_definition('knot_untying', tier).family_id for tier in ('easy','medium','hard')]
    assert families == ['two_overlap_loop','overhand_trefoil','figure_eight']
    assert task_definition('knot_untying','double_overhand').difficulty is None


def test_easy_loop_two_clear_crossings():
    from topogym.assets.geometry.knot_untying import KnotLayout, inspect_geometry
    layout = KnotLayout(family='two_overlap_loop')
    report = inspect_geometry(layout.centerline(), layout)
    assert report['crossing_count'] == 2
    assert report['minimum_nonlocal_surface_gap_m'] > .002
    assert report['minimum_bend_radius_m'] > 2*layout.rope_radius_m
    assert report['gauss_unsigned'] == [1,2,2,1]


def test_waisted_window_lift_and_closed_end_geometry(tmp_path):
    task = task_definition('hedgehog_in_cage','medium')(seed=0)
    cage, ball, bottom, report = task.build_assets(tmp_path)
    collider = trimesh.collision.CollisionManager(); collider.add_object('cage',cage)
    initial = report['initial_pose']
    band = report['window_band_center_m']
    rotation = Rotation.from_quat(np.asarray(initial['quaternion_wxyz'])[[1,2,3,0]])
    ball.vertices = rotation.apply(ball.vertices)
    for z in np.linspace(initial['position_m'][2],band,31):
        candidate=ball.copy();candidate.apply_translation([0,0,z])
        assert not collider.in_collision_single(candidate)
    # A core-sized sphere fits the window at its wide band, but cannot cross at
    # its initial height, nor through the closed top or bottom.
    for xyz, expected in [([0,-.086,band],False),([0,-.086,-.055],True),([0,0,.12],True),([0,0,-.12],True)]:
        sphere=trimesh.creation.icosphere(subdivisions=3,radius=.027)
        sphere.apply_translation(xyz)
        assert collider.in_collision_single(sphere) == expected
    assert cage.is_watertight and len(cage.split()) == 1


def test_opposed_claws_initial_clear_and_straight_pull_blocked(tmp_path):
    from topogym.assets.geometry.claws_opposed import build_opposed_windows
    assembly, report, _ = build_opposed_windows(tmp_path)
    cage, hook = [b.mesh for b in assembly.bodies]
    collider=trimesh.collision.CollisionManager();collider.add_object('cage',cage)
    assert not collider.in_collision_single(hook)
    hits=[]
    for x in np.linspace(.005,.080,31):
        candidate=hook.copy();candidate.apply_translation([x,0,0])
        hits.append(collider.in_collision_single(candidate))
    assert any(hits)


@pytest.mark.parametrize('tier',['easy','medium','hard'])
def test_buzz_frozen_route_lift_keeps_its_shape(tier):
    from topogym.assets.variation_resources import read_json
    from topogym.assets.geometry.buzz_wire_3d import BuzzWireLayout
    task=task_definition('buzz_wire_3d',tier)(seed=0)
    old=BuzzWireLayout(**read_json(task.layout_resource));new=task.build_layout()
    lift = new.base_elevation_m-old.base_elevation_m
    assert lift > .04
    np.testing.assert_allclose(new.control_points(),old.control_points()+[0,0,lift],atol=1e-12)


def test_goal_region_can_move_past_mount_for_pregrasp():
    from topogym.tasks.placement import choose_region
    clouds={'held':np.array([[-.12,-.07,1.1],[.12,.07,1.2]]),
            'other':np.array([[-.12,-.07,1.1],[.12,.07,1.2]])}
    region=choose_region(clouds,('held',),('other',),([-.75,-.7],[.75,.7]),.9,
        excluded_bounds=[(np.array([-.667,-.122]),np.array([.667,.084]))])
    assert region.center_xy_m[1]-region.half_size_m[1] > .104
    assert region.system_side(clouds['other'])
