"""run_eval pieces that need no GPU: outcome classes, make arguments and tracking error."""
import pytest
from omegaconf import OmegaConf

from vla.gym.run_eval import classify, make_args, tracking_error
from vla.protocol import PolicySpec


def spec(action_space="joint_abs", state_keys=("joint",), control_hz=15):
    return PolicySpec(name="m", embodiment="panda_robotiq", cameras=["agentview"], state_keys=state_keys,
                      action_space=action_space, control_hz=control_hz, chunk_size=15, execute_steps=8)


@pytest.mark.parametrize("outcome, reason, status, expected", [
    ("success", "task_terminal", "available", "success"),
    ("failure", "task_terminal", "available", "task_failure"),
    ("ongoing", "time_limit", "available", "time_limit"),
    ("unknown", "time_limit", "unavailable", "unevaluated"),
    ("ongoing", None, "available", "unfinished"),
])
def test_classify_follows_the_public_info(outcome, reason, status, expected):
    info = dict(task_outcome=outcome, termination_reason=reason, evaluation_status=status)
    assert classify(info) == expected


def test_make_args_follow_the_policy_spec():
    cfg = OmegaConf.create(dict(task=dict(id="buzz_wire_3d", variation="base", sim_seconds=60), env={}))
    assert make_args(cfg, spec(state_keys=("joint", "ee"))) == dict(
        variation_id="base", control_mode="JOINT_ABS", observation_mode="JOINT", control_decimation=27,
        max_physics_steps=24000)
    ee = make_args(cfg, spec("ee_abs", ("ee",), control_hz=30))
    assert (ee["control_mode"], ee["observation_mode"], ee["control_decimation"]) == ("EE_ABS", "EE", 13)


def test_make_args_pass_env_overrides_through():
    cfg = OmegaConf.create(dict(task=dict(id="cast_coil", variation="easy", sim_seconds=2),
                                env=dict(physics_dt_s=0.005, enable_depth=True)))
    args = make_args(cfg, spec(control_hz=50))
    assert (args["control_decimation"], args["max_physics_steps"], args["enable_depth"]) == (4, 400, True)


def test_tracking_error_is_the_worst_arm_distance_without_gripper():
    action = {"left": {"joint_position_rad": [0.0, 0.3, 0.0], "gripper_position_m": 0.037},
              "right": {"joint_position_rad": [0.0, 0.0, 0.1], "gripper_position_m": 0.002}}
    robot = {"left": {"joint_position_rad": [0.0, 0.0, 0.4]}, "right": {"joint_position_rad": [0.0, 0.0, 0.0]}}
    assert tracking_error(action, robot, "joint_abs") == pytest.approx(0.5)
    action = {"arm": {"position_world_m": [1.0, 2.0, 3.0], "orientation_wxyz": [1, 0, 0, 0]}}
    robot = {"arm": {"tcp_position_world_m": [1.0, 2.0, 2.9]}}
    assert tracking_error(action, robot, "ee_abs") == pytest.approx(0.1)
