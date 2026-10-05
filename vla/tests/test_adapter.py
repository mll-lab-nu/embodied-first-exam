"""Adapter against the real cast_coil (ALOHA) and buzz_wire_3d (Panda) action specs."""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

import topogym
from vla.gym.adapter import Adapter, rot6d, rot6d_to_wxyz
from vla.protocol import STATE_KEY, PolicySpec

TASKS = {"aloha": "cast_coil", "panda_robotiq": "buzz_wire_3d"}
MODES = {"joint_abs": "JOINT_ABS", "ee_abs": "EE_ABS"}


def action_spec(robot, action_space):
    with topogym.make(TASKS[robot], control_mode=MODES[action_space]) as env:
        return env.action_spec


def policy_spec(robot, action_space="joint_abs", cameras=()):
    return PolicySpec(name="test", embodiment=robot, cameras=cameras,
                      action_space=action_space, control_hz=50, chunk_size=10, execute_steps=5)


def measured_robot(spec, fingers):
    """Joint midpoints, a tilted TCP pose and the given native finger values per arm."""
    robot = {}
    for i, (arm, group) in enumerate(spec["groups"].items()):
        unit = group["gripper_field"].rsplit("_", 1)[1]
        robot[arm] = {"joint_position_rad": np.mean(group["joint_limits_rad"], axis=1),
                      "tcp_position_world_m": np.array([0.1 * i, 0.2, 0.3]),
                      "tcp_orientation_wxyz": Rotation.from_euler("xyz", [0.3, -0.2, i]).as_quat()[[3, 0, 1, 2]],
                      f"finger_position_{unit}": np.array([fingers[i], fingers[i]])}
    return robot


@pytest.mark.parametrize("robot, fingers, openings", [
    ("aloha", [0.037, 0.0226], [1.0, 0.5]),  # the ALOHA fingers touch at 8.2 mm: opening 0
    ("aloha", [0.002, 0.05], [0.0, 1.0]),
    ("panda_robotiq", [0.4], [0.5]),
    ("panda_robotiq", [-0.1], [1.0]),
])
def test_joint_state_is_arm_ordered_with_openings(robot, fingers, openings):
    spec = action_spec(robot, "joint_abs")
    measured = measured_robot(spec, fingers)
    state = Adapter(spec, policy_spec(robot)).observation({}, measured, "go", "e", 0).state["joint"]
    expected = np.concatenate([np.r_[measured[arm]["joint_position_rad"], opening]
                               for arm, opening in zip(spec["arms"], openings)])
    assert state.dtype == np.float32 and state.shape == ({"aloha": 14, "panda_robotiq": 8}[robot],)
    np.testing.assert_allclose(state, expected, atol=1e-6)


def test_ee_state_layout_uses_tcp_pose():
    spec = action_spec("aloha", "ee_abs")
    measured = measured_robot(spec, [0.037, 0.002])
    obs = Adapter(spec, policy_spec("aloha", "ee_abs")).observation({}, measured, "go", "e", 0)
    ee = obs.state["ee"]
    assert ee.shape == (20,) and list(obs.state) == ["ee"]
    right = measured["right"]
    np.testing.assert_allclose(ee[10:13], right["tcp_position_world_m"], atol=1e-6)
    np.testing.assert_allclose(ee[13:19], rot6d(right["tcp_orientation_wxyz"]), atol=1e-6)
    assert (ee[9], ee[19]) == (1.0, 0.0)


def test_rot6d_is_first_two_matrix_columns_and_round_trips():
    for q in Rotation.random(20, random_state=0).as_quat():
        wxyz = q[[3, 0, 1, 2]]
        matrix = Rotation.from_quat(q).as_matrix()
        np.testing.assert_allclose(rot6d(wxyz), np.r_[matrix[:, 0], matrix[:, 1]], atol=1e-12)
        back = rot6d_to_wxyz(rot6d(wxyz) * 3.0)  # Gram-Schmidt removes the scale
        assert np.isclose(np.linalg.norm(back), 1.0) and np.isclose(abs(back @ wxyz), 1.0)


def test_images_follow_spec_camera_order():
    spec = action_spec("aloha", "joint_abs")
    rgb = {name: np.full((480, 848, 3), i, np.uint8)
           for i, name in enumerate(["cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist"])}
    cameras = ("cam_right_wrist", "cam_high")
    obs = Adapter(spec, policy_spec("aloha", cameras=cameras)).observation(
        rgb, measured_robot(spec, [0.03, 0.03]), "go", "e", 7)
    assert tuple(obs.images) == cameras and obs.images["cam_high"] is rgb["cam_high"]
    assert (obs.instruction, obs.episode_id, obs.step) == ("go", "e", 7)


@pytest.mark.parametrize("robot", ["aloha", "panda_robotiq"])
@pytest.mark.parametrize("action_space", ["joint_abs", "ee_abs"])
def test_action_keys_match_action_spec_fields(robot, action_space):
    spec = action_spec(robot, action_space)
    key = STATE_KEY[action_space]
    adapter = Adapter(spec, policy_spec(robot, action_space))
    row = adapter.observation({}, measured_robot(spec, [0.01, 0.01]), "go", "e", 0).state[key]
    assert row.shape == (adapter.action_dim,)
    action, _ = adapter.action(row)
    assert list(action) == spec["arms"]
    for arm, command in action.items():
        assert set(command) == set(spec["groups"][arm]["fields"])


@pytest.mark.parametrize("robot", ["aloha", "panda_robotiq"])
def test_joint_action_inverts_joint_state_including_partly_open_grippers(robot):
    spec = action_spec(robot, "joint_abs")
    fingers = [0.01, 0.02] if robot == "aloha" else [0.3]
    measured = measured_robot(spec, fingers)
    adapter = Adapter(spec, policy_spec(robot))
    action, clipped = adapter.action(adapter.observation({}, measured, "go", "e", 0).state["joint"])
    for arm, command in action.items():
        np.testing.assert_allclose(command["joint_position_rad"], measured[arm]["joint_position_rad"], atol=1e-6)
    grippers = [command[spec["groups"][arm]["gripper_field"]] for arm, command in action.items()]
    np.testing.assert_allclose(grippers, fingers, atol=1e-6)  # a partly open gripper keeps its opening
    assert clipped is False


def test_aloha_openings_read_the_touching_fingers_as_closed_and_close_commands_squeeze():
    spec = action_spec("aloha", "joint_abs")
    adapter = Adapter(spec, policy_spec("aloha"))
    state = adapter.observation({}, measured_robot(spec, [0.0082, 0.037]), "go", "e", 0).state["joint"]
    assert (state[6], state[13]) == (0.0, 1.0)
    action, _ = adapter.action(state)
    assert (action["left"]["gripper_position_m"], action["right"]["gripper_position_m"]) == (0.002, 0.037)


def test_joint_action_clips_joints_and_opening():
    spec = action_spec("panda_robotiq", "joint_abs")
    limits = np.asarray(spec["groups"]["arm"]["joint_limits_rad"])
    adapter = Adapter(spec, policy_spec("panda_robotiq"))
    action, clipped = adapter.action(np.r_[limits[:, 1] + 1.0, 1.5].astype(np.float32))
    np.testing.assert_allclose(action["arm"]["joint_position_rad"], limits[:, 1], atol=1e-6)
    assert action["arm"]["gripper_position_rad"] == 0.0 and clipped is True
    assert adapter.action(np.r_[limits.mean(axis=1), 0.5].astype(np.float32))[1] is False


@pytest.mark.parametrize("robot", ["aloha", "panda_robotiq"])
@pytest.mark.parametrize("opening", [0.0, 1.0])
def test_gripper_extremes_stay_within_native_limits(robot, opening):
    spec = action_spec(robot, "joint_abs")
    adapter = Adapter(spec, policy_spec(robot))
    row = np.concatenate([np.r_[np.mean(spec["groups"][arm]["joint_limits_rad"], axis=1), opening]
                          for arm in spec["arms"]]).astype(np.float32)
    for arm, command in adapter.action(row)[0].items():
        low, high = spec["groups"][arm]["gripper_limits"]
        assert low <= command[spec["groups"][arm]["gripper_field"]] <= high


def test_ee_action_is_not_clipped():
    spec = action_spec("panda_robotiq", "ee_abs")
    adapter = Adapter(spec, policy_spec("panda_robotiq", "ee_abs"))
    wxyz = Rotation.from_euler("xyz", [3.0, 0.1, -0.4]).as_quat()[[3, 0, 1, 2]]
    action, clipped = adapter.action(np.r_[5.0, -5.0, 5.0, rot6d(wxyz), 0.25].astype(np.float32))
    command = action["arm"]
    assert command["position_world_m"] == [5.0, -5.0, 5.0]
    assert np.isclose(abs(np.asarray(command["orientation_wxyz"]) @ wxyz), 1.0, atol=1e-6)
    assert np.isclose(command["gripper_position_rad"], 0.6) and clipped is False


def test_embodiment_mismatch_is_rejected():
    with pytest.raises(ValueError, match="aloha"):
        Adapter(action_spec("panda_robotiq", "joint_abs"), policy_spec("aloha"))
