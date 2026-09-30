"""The policy view admits proprioception and fixed calibration, not scene truth."""
import numpy as np
import pytest

from topogym.sensors.camera_info import camera_contract
from topogym.simulator.rollout_simulation.policy_observation import validate_profile, project_observation, build_context


@pytest.fixture
def inputs():
    cameras = dict(fixed=dict(res=[4, 3], fov=60., near=.1, far=10.,
                             pos=[0., 0., 1.], lookat=[0., 0., 0.], up=[0., 1., 0.]))
    specs = camera_contract(cameras)
    specs["wrist"] = dict(specs["fixed"], motion="wrist_attached")
    state = dict(episode_id="e", branch_id=0, state_id=2, physics_step=2, sim_time_s=.05)
    raw = dict(state=state, rgb={name: np.zeros((3, 4, 3), dtype=np.uint8) for name in specs},
        cameras={name: dict(specs["fixed"], secret_camera_field=[999.]) for name in specs},
        task=dict(object_position=[999.]), secret_world={"contact": 999.})
    robot = dict(arm=dict(joint_position_rad=np.zeros(2), tcp_position_world_m=np.zeros(3),
        tcp_orientation_wxyz=np.array([1., 0., 0., 0.]), finger_position_rad=np.zeros(2),
        joint_velocity_rad_s=np.ones(2), target_rad=[999.], hand_position_world_m=[999.]*3))
    proprioception = dict(state=state.copy(), robot=robot)
    action = dict(groups=dict(arm=dict(arm_joint_names=["j1", "j2"], gripper_field="gripper_position_rad")))
    return raw, proprioception, specs, action


def profile(inputs, **settings):
    raw, proprioception, specs, action = inputs
    return validate_profile(mode="limited", settings=settings, camera_specs=specs,
        action_spec=action, state_fields=(), privileged_enabled=False,
        raw_observation=raw, proprioception=proprioception)


def test_fixed_calibration_is_opt_in_and_wrist_rgb_remains(inputs):
    raw, prop, _, _ = inputs
    view = project_observation(raw, prop, profile=profile(inputs), execution_state={}, privileged_values={})
    assert "camera_calibration" not in view
    selected = profile(inputs, calibration_camera_ids=["fixed"])
    view = project_observation(raw, prop, profile=selected, execution_state={}, privileged_values={})
    assert set(view["rgb"]) == {"fixed", "wrist"}
    assert set(view["camera_calibration"]) == {"fixed"}
    assert "task" not in view
    context = build_context(selected, inputs[3], {})
    assert context["schema_version"] == 2
    assert context["observation_profile"]["schema_version"] == 2
    assert "task_instruction" not in context["observation_profile"]
    assert "task" not in context["observation_spec"]
    assert "999" not in str(view)
    assert "joint_velocity_rad_s" not in view["robot"]["arm"]
    assert "hand_position_world_m" not in view["robot"]["arm"]


@pytest.mark.parametrize("settings", [dict(calibration_camera_ids=["wrist"]),
    dict(calibration_camera_ids=["missing"]), dict(rgb_camera_ids=["fixed"], calibration_camera_ids=["wrist"]),
    dict(rgb_camera_ids=["fixed", "fixed"]), dict(privileged=True),
    dict(task_instruction="Task text belongs in instruction.md")])
def test_invalid_profiles_fail_before_execution(inputs, settings):
    with pytest.raises((ValueError, PermissionError)):
        profile(inputs, **settings)


def test_state_mismatch_and_changed_fixed_camera_rejected(inputs):
    raw, prop, _, _ = inputs
    selected = profile(inputs, calibration_camera_ids=["fixed"])
    prop["state"]["state_id"] += 1
    with pytest.raises(ValueError, match="share a state"):
        project_observation(raw, prop, profile=selected, execution_state={}, privileged_values={})
    prop["state"]["state_id"] -= 1
    raw["cameras"]["fixed"]["T_world_from_camera_cv"] = np.eye(4)*2
    with pytest.raises(ValueError, match="calibration changed"):
        project_observation(raw, prop, profile=selected, execution_state={}, privileged_values={})


def test_missing_measurements_are_not_filled_with_zero(inputs):
    raw, prop, _, _ = inputs
    del prop["robot"]["arm"]["tcp_position_world_m"]
    with pytest.raises(KeyError):
        profile(inputs)
