from topogym.tasks.cast_keyhole.common import CastKeyholeTask
from topogym.tasks.cast_keyhole.qualification import PLACEMENT_QUALIFICATIONS
from terminal_fixtures import placement, region

import numpy as np
import pytest


def test_fixed_target_identity_whole_geometry_and_other_part():
    task = CastKeyholeTask()
    state = placement(task,("keyhole_silver",),("keyhole_gold",))
    assert task.evaluate_goal_region(state,region())[0]
    state["bodies"]["keyhole_gold"]["position_m"][0] = 1
    assert not task.evaluate_goal_region(state,region())[0]
    assert task.goal_region_observation(region())["target_entities"] == ["keyhole_silver"]
    state["bodies"]["keyhole_gold"]["position_m"][0] = 0
    task.placement_vertices["keyhole_silver"][1,0] = .3
    assert not task.evaluate_goal_region(state,region())[0]


@pytest.mark.parametrize("level", sorted(PLACEMENT_QUALIFICATIONS))
def test_qualification_does_not_extend_to_unverified_layout_or_geometry(level, tmp_path):
    from topogym.config.registry import task_definition

    qualified = task_definition("cast_keyhole", level)()
    assert qualified.goal_complete
    assert qualified.terminal_revision == "cast_keyhole_placement_v2"
    qualified.declare(tmp_path/"qualified", .9196429)
    assert qualified.terminal_metadata()["reachability_qualified"]
    assert not CastKeyholeTask().goal_complete
    # The seeded envelope (topogym.tasks.scene_variation: +-2 cm, +-5 deg) is qualified; beyond it is not.
    moved = task_definition("cast_keyhole", level)({"yaw_deg": 5., "center_xy_m": [-.1156786, .03]})
    assert moved.goal_complete
    relocated = task_definition("cast_keyhole", level)({"yaw_deg": 20.})
    assert not relocated.goal_complete
    relocated.declare(tmp_path/"relocated", .9196429)
    assert not relocated.terminal_metadata()["reachability_qualified"]
    qualified.goal_region_identity = "changed table or placement region"
    assert not qualified.goal_complete
    del qualified.goal_region_identity
    qualified.resource_hashes[qualified.geometry_resource] = "0"*64
    assert not qualified.goal_complete


@pytest.mark.parametrize("level", ["easy", "medium", "hard"])
def test_real_variant_placement_negatives_and_full_stability_window(level, tmp_path):
    """Actual frozen solids, synthetic motion; runtime qualification is separate."""
    from copy import deepcopy
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator import SimulatorConfig
    from topogym.evaluation.task_metrics import body_points
    from terminal_fixtures import body

    config = load_scene_config(SimulatorConfig(task_id="cast_keyhole", variation_id=level, enable_rgb=False))
    table = config.env.world.table
    height = table.pos[2]+table.size[2]/2
    task = task_definition("cast_keyhole", level)()
    original = task.declare(tmp_path, height)
    task.finalize_spec(original, asset_dir=tmp_path, scene_config=config)
    state = dict(physics_step=0, bodies={e.name: body(e.position_m, e.quaternion_wxyz) for e in original.entities})
    assert not task.evaluate_state(state)[0]
    silver = state["bodies"]["keyhole_silver"]
    points = body_points(silver, task.placement_vertices["keyhole_silver"])
    center = np.r_[task.goal_region.center_xy_m, height+task.goal_region.placement_height_m/2]
    silver["position_m"] += center-(points.max(0)+points.min(0))/2
    positive = deepcopy(state)
    assert task.evaluate_state(positive)[0]

    # A valid placement cannot override the existing physical failure guards.
    task._task_link_indices = {31, 32}
    penetrated = deepcopy(positive)
    penetrated["contacts"] = dict(link_a=np.array([31]), link_b=np.array([32]),
                                  penetration=np.array([.00101]))
    assert task.evaluate_state(penetrated)[:2] == (False, "Task contact penetration exceeded 1 mm")
    fallen = deepcopy(positive)
    fallen["bodies"]["keyhole_gold"]["position_m"][2] -= 1.
    assert task.evaluate_state(fallen)[:2] == (False, "A task body fell below the table")
    invalid = deepcopy(positive)
    invalid["bodies"]["keyhole_silver"]["linear_velocity_m_s"][0] = np.nan
    assert task.evaluate_state(invalid)[:2] == (False, "Non-finite physical state")

    moving = deepcopy(positive)
    moving["bodies"]["keyhole_silver"]["linear_velocity_m_s"][0] = .002
    assert not task.evaluate_state(moving)[0]
    spinning = deepcopy(positive)
    spinning["bodies"]["keyhole_silver"]["angular_velocity_rad_s"][2] = .03
    assert not task.evaluate_state(spinning)[0]
    crossed = deepcopy(positive)
    crossed["bodies"]["keyhole_gold"]["position_m"][:2] = task.goal_region.center_xy_m
    assert not task.evaluate_state(crossed)[0]
    over_boundary = deepcopy(positive)
    over_boundary["bodies"]["keyhole_silver"]["position_m"][0] += task.goal_region.half_size_m[0]
    assert not task.evaluate_state(over_boundary)[0]

    task.initialize(positive)
    for tick in range(1, 21):
        positive["physics_step"] = tick
        assert not task.update(positive, .025).task_success
    # One moving tick resets the window; a later quiet tail must start over.
    moving["physics_step"] = 21
    assert task.update(moving, .025).metrics["stable_time_s"] == 0.
    for tick in range(22, 42):
        positive["physics_step"] = tick
        assert not task.update(positive, .025).task_success
    positive["physics_step"] = 42
    result = task.update(positive, .025)
    assert result.metrics["stable_time_s"] == pytest.approx(.5)
    assert result.task_success == task.goal_complete
