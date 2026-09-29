"""Reproducible terminal audit controls, not physical success qualifications."""
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path

import numpy as np
import pytest

from terminal_fixtures import body
from topogym.config import SimulatorConfig
from topogym.config.registry import task_definition, task_registration
from topogym.config.scene import load_scene_config
from topogym.evaluation.task_metrics import body_points
from topogym.evaluation.terminal import evaluate_settling
from topogym.simulator.interaction import public_info
from topogym.utils.io import to_jsonable


def record(name, data):
    root = os.environ.get("TOPOGYM_AUDIT_OUTPUT")
    if root:
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{name}.json").write_text(json.dumps(to_jsonable(data), indent=2)+"\n")


@pytest.mark.parametrize("level", ("easy", "medium", "hard"))
def test_claws_original_and_finalized_frames_with_real_fall_control(level, tmp_path):
    cfg = load_scene_config(SimulatorConfig(task_id="interlocked_claws", variation_id=level, enable_rgb=False))
    table = cfg.env.world.table
    height = table.pos[2]+table.size[2]/2
    task = task_definition("interlocked_claws", level)()
    original = task.declare(tmp_path, height)
    spec = task.finalize_spec(original, asset_dir=tmp_path, scene_config=cfg)

    def state(entities):
        return dict(physics_step=0, bodies={e.name: body(e.position_m, e.quaternion_wxyz)
                    for e in entities if e.name != "goal_region"})

    stale, finalized = state(original.entities), state(spec.entities)
    stale_result, initial_result = task.evaluate_state(stale), task.evaluate_state(finalized)
    assert stale_result[1] == "A task body fell below the table"
    assert initial_result[:2] == (False, None)
    placed = deepcopy(finalized)
    for name in task.placement_targets:
        points = body_points(placed["bodies"][name], task.placement_vertices[name])
        target = np.r_[task.goal_region.center_xy_m, height+.01+np.ptp(points[:, 2])/2]
        placed["bodies"][name]["position_m"] += target-(points.max(0)+points.min(0))/2
    placed_result = task.evaluate_state(placed)
    assert placed_result[:2] == (True, None)
    fallen = deepcopy(placed)
    fallen["bodies"][task.placement_targets[0]]["position_m"][2] -= 1.
    fall_result = task.evaluate_state(fallen)
    assert fall_result[:2] == (False, "A task body fell below the table")
    record("claws_"+level, dict(scope="authored assets, synthetic poses", stale=stale_result,
           finalized=initial_result, placed=placed_result, actual_fall=fall_result))


def test_rope_three_plane_blind_spot_is_only_a_synthetic_counterexample():
    from test_terminal_rope_threading import fixture
    points = np.array([[-1,0,.8],[-.02,0,.8],[-.005,.15,.8],[-.004,0,.8],[3,0,.8]])
    task, state = fixture(points)
    reached, failure, metrics = task.evaluate_state(state)
    # Independent torus solid distance, not aperture_crossings.
    relative = points-np.array([0,0,.8])
    axis_distance = np.hypot(relative[:,0], np.linalg.norm(relative[:,1:], axis=1)-.15)
    assert reached and failure is None and axis_distance.min() < .01
    assert not task.goal_complete
    record("rope_synthetic", dict(scope="synthetic positions AND IPC validity; not a reachable state",
           predicate=reached, metrics=metrics, torus_axis_distance_m=axis_distance,
           centerline_penetration_m=.01-axis_distance.min()))


def test_knot_empty_interior_bounds_false_negative_with_controls():
    from test_terminal_knot_untying import fixture
    task, state = fixture()
    state["fem"]["rope"]["position_m"] = np.array([[.2,.2,.752],[.2,-.2,.752],[-.2,-.2,.752],[-.2,.2,.752]])
    state.update(physics_step=0, assist_active=False)
    rows = {}
    for name, center, expect_clear in (("outside", [0,.3,.752],True),
            ("empty_interior", [0,0,.752],False), ("near_rope", [.19,0,.752],False)):
        box = np.array(center)+np.array([[-.01,-.01,-.001],[.01,.01,.001]])
        state["release_geometry"] = dict(schema_version=1, physics_step=0, complete=True,
            robot_present=True, robot_bounds_m=box[None], target_bounds_m={})
        raw = task.evaluate_state(state)
        settled, metrics, _ = evaluate_settling(state, task.final_settling_spec())
        assert raw[0] and metrics["robot_clear"] == expect_clear
        rows[name] = dict(raw=raw, settled=settled, metrics=metrics)
    record("knot_synthetic", dict(scope="synthetic U and robot boxes; runtime clearance not established",
           interior_ideal_surface_clearance_m=.188, controls=rows))


@pytest.mark.parametrize("name", ("rope_threading", "knot_untying", "orbits", "slotted_post_ring"))
@pytest.mark.parametrize("enabled", (False, True))
def test_goal_flag_layers(name, enabled, tmp_path, local_env):
    # load_scene_config is patched by local_env; only the declaration and public
    # orchestration are relevant here, not table placement/reachability.
    from importlib import import_module
    from terminal_fixtures import region
    task, state = import_module("test_terminal_"+name).fixture()
    # Record real declaration metadata on an independent instance; do not
    # replace the synthetic evaluator fixture's material map with this mesh.
    declared = type(task)()
    declared.goal_complete = enabled
    spec = declared.declare(tmp_path/name, .9196429)
    task.goal_complete = enabled
    if name in {"orbits", "slotted_post_ring"}:
        task.goal_region = region()
        task.goal_region_identity = "audit_synthetic_region"
    state.update(physics_step=0, assist_active=False)
    state["release_geometry"] = dict(schema_version=1, physics_step=0, complete=True,
        robot_present=True, robot_bounds_m=np.array([[[10,10,10],[11,11,11]]]), target_bounds_m={})
    raw = task.evaluate_state(state)
    task.initialize(state)
    for tick in range(1, 8):
        state["physics_step"] = tick
        state["release_geometry"]["physics_step"] = tick
        task.update(state, .1)
    local_env._task = task
    info = public_info(local_env._info())
    episode = local_env.episode_metadata["terminal"]
    row = dict(enabled=enabled, declaration=spec.metadata, raw=raw,
        task_result=task.result.__dict__, episode=episode, public=info,
        registry=asdict(task_registration(name)))
    record(f"metadata_{name}_{enabled}", row)
    assert spec.metadata["goal_evaluation_complete"] == enabled
    assert task.result.metrics["goal_evaluation_complete"] == enabled
    assert episode["goal_complete"] == info["goal_evaluation_complete"] == enabled
    assert task.result.metrics["thresholds_calibrated"] is False
    if name in {"rope_threading", "knot_untying"}:
        assert raw[2]["goal_evaluation_complete"] == enabled
        assert task.result.task_success == enabled
    if not enabled:
        assert info["task_outcome"] == "unknown" and info["task_success"] is None
    # A flag flip cannot qualify the registered task or prove thresholds.
    assert not task_definition(name)().goal_complete
