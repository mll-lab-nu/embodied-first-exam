"""Validate simulator settings and the single honest task catalog."""

import pytest
from topogym.config import SimulatorConfig, task_catalog
from topogym.config.registry import task_definition
from topogym.config.scene import load_scene_config
from topogym.robot.description import describe_robot


@pytest.mark.parametrize(
    "options",
    [
        {"physics_dt_s": 0},
        {"physics_dt_s": float("nan")},
        {"control_decimation": True},
        {"solver_substeps": -1},
        {"compute_backend": "mujoco"},
        {"render_backend": "rasterizer"},
        {"enable_rgb": True, "compute_backend": "cpu"},
        {"enable_rgb": "yes"},
        {"robot_id": "robotiq"},
        {"variation_id": ""},
        {"max_physics_steps": 0},
        {"max_physics_steps": True},
    ],
)
def test_invalid_configuration(options):
    with pytest.raises((TypeError, ValueError)):
        SimulatorConfig(**options)


def test_config_owns_immutable_parameters():
    parameters = {"geometry": {"size": [1.0, 2.0]}}
    config = SimulatorConfig(task_parameters=parameters)
    parameters["geometry"]["size"][0] = 100.0
    assert config.task_parameters["geometry"]["size"] == (1.0, 2.0)
    with pytest.raises(TypeError):
        config.task_parameters["geometry"]["size"] = (9.0,)


def test_catalog_does_not_claim_validation():
    records = task_catalog()
    assert len({r["task_id"] for r in records}) == len(records)
    assert all(r["validation"] == "see_runs_test_results" for r in records)
    assert len(records) == 13
    assert all(r["status"] == "integrated" and r["implementation"] for r in records)
    with pytest.raises(ValueError):
        task_definition("missing-task")


@pytest.mark.parametrize("task_id", ["hedgehog_in_cage", "fiber_bundling"])
def test_single_arm_tasks_resolve_panda_robotiq_profile(task_id):
    scene = load_scene_config(SimulatorConfig(task_id=task_id))
    description = describe_robot(scene.robot_control)
    assert description.robot_id == "panda_robotiq"
    assert len(description.groups) == 1
    arm = description.groups[0]
    assert len(arm.arm_joints) == 7
    assert arm.gripper_field == "gripper_position_rad"


@pytest.mark.parametrize("robot_id", ["aloha", "panda_robotiq"])
def test_robot_profiles_share_compact_lab(robot_id):
    scene = load_scene_config(SimulatorConfig(robot_id=robot_id, enable_rgb=True))
    assert scene.env.presentation.background == "compact_lab"
    assert scene.env.renderer.type == "nyx"
    assert scene.env.genesis.backend == "cuda"
    assert scene.env.renderer.lights and scene.env.renderer.env_map
    assert scene.env.presentation.appearance and scene.env.cameras


def test_cpu_physics_does_not_require_rgb():
    scene = load_scene_config(SimulatorConfig(compute_backend="cpu", enable_rgb=False))
    assert scene.env.genesis.backend == "cpu"
    assert not scene.env.cameras
    assert scene.env.renderer.type == "nyx"


@pytest.mark.parametrize("background", ["lab", "checker", "unknown"])
def test_retired_background_is_rejected_before_scene_mutation(monkeypatch, background):
    from topogym.world import lab
    from topogym.world.visuals.presentation import prepare_presentation

    def unexpected_build(*args, **kwargs):
        pytest.fail("Invalid presentation must not add any scene entities")

    monkeypatch.setattr(lab, "add_lab", unexpected_build)
    with pytest.raises(ValueError, match="Only the compact_lab background"):
        prepare_presentation(
            object(), object(), {"presentation": {"background": background}}, {}
        )
