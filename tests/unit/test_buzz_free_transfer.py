"""A planned free transfer must preserve the opening and leave the tool alone."""
import pytest

from topogym.planning.buzz_wire_3d.policy import BuzzWirePolicy


def observation(binding=None):
    return {"state": {"sim_time_s": 0.},
            "robot": {"arm": {"joint_position_rad": [0.]*7,
                              "tcp_position_world_m": [.1, .2, .3],
                              "tcp_orientation_wxyz": [1., 0., 0., 0.]}},
            "privileged": {"world": {"contact_events": {"events": []},
                "grasp": {"hands": {"arm": {"binding": binding, "last_fraction": .5625}}}}}}


def policy():
    result = BuzzWirePolicy(route=None, origin=[0., 0., 0.], part="acquire",
        stop_after_transfer=True, plan=[dict(time_s=.025, position_m=[.1, .2, .3],
            quaternion_wxyz=[1., 0., 0., 0.], qpos=[0.]*15)])
    result.initialize({"action_spec": {"robot_id": "panda_robotiq", "mode": "EE_ABS"},
                       "timing_spec": {"control_dt_s": .025}})
    return result


def test_free_transfer_finishes_without_grasping_or_reading_tool_pose():
    controller, obs = policy(), observation()
    first = controller.act(obs)
    assert first["arm"]["gripper_position_rad"] == pytest.approx(.45)
    assert first["arm"]["position_world_m"] == [.1, .2, .3]
    obs["state"]["sim_time_s"] = .025
    assert controller.act(obs) is None
    assert controller.desired_arm_seed is None
    assert controller.phase == "regrasp_free_transfer"


def test_free_transfer_rejects_a_bound_tool():
    with pytest.raises(RuntimeError, match="requires a released tool"):
        policy().act(observation(binding={"target": ["wand", "wand"]}))


def test_free_transfer_stops_before_sending_another_action_if_tool_moves():
    controller, obs = policy(), observation()
    controller.free_tool_motion_limit_m = .003
    body = {"position_m": [0., 0., 0.], "quaternion_wxyz": [1., 0., 0., 0.]}
    obs["privileged"]["world"]["bodies"] = {"wand": body}
    assert controller.act(obs) is not None
    body["position_m"] = [.004, 0., 0.]
    obs["state"]["sim_time_s"] = .025
    with pytest.raises(RuntimeError, match="moved the released tool"):
        controller.act(obs)


@pytest.mark.parametrize("phase", ["registered", "holding"])
def test_approach_stops_before_advancing_again_after_real_grasp(phase):
    controller, obs = policy(), observation()
    controller.obs = obs
    advanced = []

    def motion(*args):
        advanced.append(1)
        yield {"arm": {"position_world_m": [.1, .2, .3]}}
        advanced.append(2)
        yield {"arm": {"position_world_m": [.1, .2, .29]}}

    controller.move = motion
    approach = controller.approach_grasp(None)
    assert next(approach)["arm"]["position_world_m"] == [.1, .2, .3]
    obs["privileged"]["world"]["grasp"]["hands"]["arm"]["phase"] = phase
    assert list(approach) == []
    assert advanced == [1]
    assert controller.phase == "regrasp_contact_stop"


def test_body_lowering_stops_at_first_tool_deck_contact():
    controller, obs = policy(), observation()
    obs["privileged"]["world"]["grasp"]["hands"]["arm"]["phase"] = "holding"
    obs["privileged"]["world"]["bodies"] = {"wand": {"position_m": [0., 0., .1], "quaternion_wxyz": [1., 0., 0., 0.]}}
    controller.part, controller.instructions = "script", [
        dict(operation="body", translation_m=[0., 0., -.04], seconds=3., stop_when_supported=True)]
    assert controller.act(obs) is not None
    obs["state"]["sim_time_s"] = .025
    obs["privileged"]["world"]["contact_events"]["events"] = [
        dict(touching=True, role_a="finish_support", role_b="wand_handle")]
    assert controller.act(obs) is None
    assert controller.samples[-1]["stopped"]
