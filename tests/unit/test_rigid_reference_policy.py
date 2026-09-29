"""Safety-relevant feedback, permission and continuous-path counterexamples."""
from copy import deepcopy

import numpy as np
import pytest
import trimesh
from scipy.spatial.transform import Rotation

from topogym.planning.interlocked_claws import InterlockedClawsMediumPolicy
from topogym.planning.interlocked_claws.interlocked_claws_medium_planning import frame_hook_pose
from topogym.planning.rigid_reference.feedback import Limits, PolicyFailure, bilateral_contacts
from topogym.planning.rigid_reference.geometry import RigidPathChecker


def body(x=0., q=(1., 0., 0., 0.), links=(1,)):
    return dict(position_m=[x, 0., 0.], quaternion_wxyz=list(q), link_indices=links,
                linear_velocity_m_s=[0., 0., 0.], angular_velocity_rad_s=[0., 0., 0.])


def setup_policy(part="hold", route=None):
    oracle = dict(task_id="interlocked_claws", model_revision="opposed_pregrasp_wide2_v1", identity={"mesh": "frozen"},
                  grasps={"brown": dict(arm="left", finger_link_indices=[10, 11])})
    policy = InterlockedClawsMediumPolicy(oracle=oracle, route=route, part=part)
    context = dict(mode="unlimited", observation_spec=dict(privileged_fields=["world"]),
        timing_spec=dict(control_dt_s=.025), action_spec=dict(robot_id="aloha", mode="EE_ABS",
        coordinate_frame="world", orientation="unit wxyz", grasp_assist=dict(model="none"),
        groups={"left": dict(gripper_field="gripper_position_m", gripper_limits=[0., .05])}))
    obs = dict(state=dict(sim_time_s=0., state_id=0, episode_id="one"),
        robot={"left": dict(tcp_position_world_m=[0., 0., 0.], tcp_orientation_wxyz=[1., 0., 0., 0.])},
        privileged=dict(world=dict(bodies={"brown": body()}, assist_active=False, assist_model="none",
            contacts=dict(link_a=[1, 1], link_b=[10, 11], force=[[1., 0., 0.], [-1., 0., 0.]], penetration=[.0001, .0001]))))
    policy.initialize(context)
    return policy, context, obs


@pytest.mark.parametrize("change", ["limited", "world_missing", "assist", "delta", "quaternion", "robot"])
def test_reject_invalid_context(change):
    policy, context, _ = setup_policy()
    if change == "limited": context["mode"] = "limited"
    elif change == "world_missing": context["observation_spec"]["privileged_fields"] = []
    elif change == "assist": context["action_spec"]["grasp_assist"]["model"] = "contact_weld_v1"
    elif change == "delta": context["action_spec"]["mode"] = "EE_DELTA"
    elif change == "quaternion": context["action_spec"]["orientation"] = "xyzw"
    else: context["action_spec"]["robot_id"] = "panda_robotiq"
    with pytest.raises(ValueError): policy.initialize(context)


def test_bilateral_means_both_actual_fingers_with_nonzero_force():
    _, _, obs = setup_policy()
    world = obs["privileged"]["world"]
    assert bilateral_contacts(world, "brown", [10, 11])
    world["contacts"]["link_b"] = [10, 10]
    assert not bilateral_contacts(world, "brown", [10, 11])
    world["contacts"]["link_b"] = [10, 11]
    world["contacts"]["force"][1] = [0., 0., 0.]
    assert not bilateral_contacts(world, "brown", [10, 11])
    del world["contacts"]["force"]
    with pytest.raises(KeyError): bilateral_contacts(world, "brown", [10, 11])


def test_hold_uses_sim_time_and_quaternion_sign_invariance():
    policy, _, obs = setup_policy()
    assert policy.act(obs) == {}
    for t in (.5, 1., 1.5, 1.999):
        obs["state"]["sim_time_s"] = t
        obs["privileged"]["world"]["bodies"]["brown"]["quaternion_wxyz"] = [-1., 0., 0., 0.]
        assert policy.act(obs) == {}
    obs["state"]["sim_time_s"] = 2.
    assert policy.act(obs) is None
    assert policy.completed


def test_rotation_slip_is_latched_even_if_object_returns():
    policy, _, obs = setup_policy()
    policy.act(obs)
    obs["state"]["sim_time_s"] = .1
    q = Rotation.from_euler("z", 4., degrees=True).as_quat()[[3, 0, 1, 2]].tolist()
    obs["privileged"]["world"]["bodies"]["brown"]["quaternion_wxyz"] = q
    assert policy.act(obs) == {}  # Stationary two-second diagnostic continues.
    obs["state"]["sim_time_s"] = 2.
    obs["privileged"]["world"]["bodies"]["brown"]["quaternion_wxyz"] = [1., 0., 0., 0.]
    with pytest.raises(PolicyFailure, match="grasp_slip"): policy.act(obs)
    assert not policy.completed


def test_grasp_translation_does_not_include_long_lever_rotation():
    policy, _, obs = setup_policy()
    obs["privileged"]["world"]["bodies"]["brown"]["position_m"] = [.2, 0., 0.]
    policy.act(obs)
    rotation = Rotation.from_euler("y", 2., degrees=True)
    obs["state"]["sim_time_s"] = .025
    b = obs["privileged"]["world"]["bodies"]["brown"]
    b["position_m"] = rotation.apply([.2, 0., 0.]).tolist()
    b["quaternion_wxyz"] = rotation.as_quat()[[3, 0, 1, 2]].tolist()
    policy.act(obs)
    assert policy.max_drift["brown"][0] < 1e-12
    assert policy.max_drift["brown"][1] == pytest.approx(np.deg2rad(2.))


@pytest.mark.parametrize("task_id", ["hedgehog_in_cage", "interlocked_claws"])
@pytest.mark.parametrize("variant", ["easy", "medium", "hard"])
def test_all_variants_keep_terminal_unqualified(task_id, variant):
    from topogym.config.registry import task_definition
    task = task_definition(task_id, variant)(seed=0)
    assert task.goal_complete is False


def test_pregrasp_parameter_preserves_default_and_changes_identity(tmp_path):
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator import SimulatorConfig
    cls = task_definition("interlocked_claws", "medium")
    default, adjusted = cls(seed=0), cls(dict(initial_finger_position_m=.0218), seed=0)
    assert default.config["initial_finger_position_m"] is None
    assert default.instance_id != adjusted.instance_id
    scene = load_scene_config(SimulatorConfig(task_id="interlocked_claws", enable_rgb=False, compute_backend="cpu"))
    spec = adjusted.declare(tmp_path, .9)
    spec = adjusted.finalize_spec(spec, asset_dir=tmp_path, scene_config=scene)
    q = np.array(spec.metadata["initial_robot_qpos"])
    np.testing.assert_allclose(q[:, 6:], .0218, atol=0)
    np.testing.assert_allclose(q[:, :6], np.tile([0., -.96, 1.16, 0., -.2, 0.], (2, 1)))
    assert all(v["gripper_position_m"] == scene.robot_control.gripper.closed_qpos
               for v in spec.initial_robot_targets.values())


def test_rewind_requires_fresh_policy():
    policy, _, obs = setup_policy()
    policy.act(obs)
    with pytest.raises(PolicyFailure, match="new_policy_required_after_rewind"): policy.act(obs)


def test_tcp_reaching_target_cannot_advance_when_object_lags():
    waypoint = dict(phase="C2_first_window", timeout_s=5., tcp={"left": body()}, bodies={"brown": body(.01)}, grasps=["brown"])
    route = dict(identity={"mesh": "frozen"}, waypoints=[waypoint])
    policy, _, obs = setup_policy("solve", route)
    policy.act(obs)
    obs["state"]["sim_time_s"] = 3.1
    with pytest.raises(PolicyFailure, match="stalled"): policy.act(obs)
    assert policy.index == 0


def test_motion_starts_with_bounded_acceleration():
    route = dict(identity={"mesh": "frozen"}, waypoints=[dict(phase="C1_align", timeout_s=5., tcp={"left": body(.02)})])
    policy, _, obs = setup_policy("solve", route)
    action = policy.act(obs)
    distance = np.linalg.norm(action["left"]["position_world_m"])
    assert distance <= policy.limits.translation_acceleration_m_s2*policy.dt**2+1e-12


def test_reference_brakes_before_advancing_stage():
    route = dict(identity={"mesh": "frozen"}, waypoints=[dict(phase="C1_align", timeout_s=10., tcp={"left": body(.02)})])
    policy, _, obs = setup_policy("solve", route)
    previous, velocity = np.zeros(3), np.zeros(3)
    for i in range(300):
        obs["state"]["sim_time_s"] = i*policy.dt
        action = policy.act(obs)
        current = np.array(action.get("left", {}).get("position_world_m", previous))
        actual_velocity = (current-previous)/policy.dt
        assert np.linalg.norm(actual_velocity-velocity) <= policy.limits.translation_acceleration_m_s2*policy.dt+1e-9
        previous, velocity = current, actual_velocity
        obs["robot"]["left"]["tcp_position_world_m"] = current.tolist()
        if policy.index == 1:
            assert np.linalg.norm(velocity) < 1e-8
            break
    else:
        pytest.fail("Feedback reference did not finish a reachable free-space motion")


def test_relative_hook_pose_removes_common_frame_motion():
    q = Rotation.from_euler("z", 90., degrees=True).as_quat()[[3, 0, 1, 2]]
    frame, hook = body(q=q), body(q=q)
    frame["position_m"], hook["position_m"] = [2., 3., 4.], [2., 3.1, 4.]
    p, r = frame_hook_pose(dict(bodies={"frame": frame, "hook": hook}), "frame", "hook")
    np.testing.assert_allclose(p, [.1, 0., 0.], atol=1e-12)
    assert r.magnitude() < 1e-12


def test_free_endpoints_do_not_hide_swept_collision():
    checker = RigidPathChecker(trimesh.creation.box([.002, .2, .2]), trimesh.creation.box([.01]*3))
    a, b = (np.array([-.02, 0., 0.]), Rotation.identity()), (np.array([.02, 0., 0.]), Rotation.identity())
    assert checker.clearance(a) > 0 and checker.clearance(b) > 0
    assert not checker.edge(a, b)["passed"]


def test_containment_without_surface_intersection_is_blocked():
    checker = RigidPathChecker(trimesh.creation.box([.2]*3), trimesh.creation.box([.01]*3))
    p = np.zeros(3), Rotation.identity()
    assert checker.clearance(p) > 0
    assert not checker.initial_free(p)


def test_safe_sweep_has_positive_lower_bound():
    checker = RigidPathChecker(trimesh.creation.box([.1]*3), trimesh.creation.box([.01]*3))
    a, b = (np.array([.2, 0., 0.]), Rotation.identity()), (np.array([.2, .2, 0.]), Rotation.identity())
    result = checker.edge(a, b)
    assert result["passed"] and result["clearance_lower_bound_m"] > checker.margin


def test_unresolved_motion_is_not_certified():
    checker = RigidPathChecker(trimesh.creation.box([.1]*3), trimesh.creation.box([.01]*3), max_depth=1)
    a, b = (np.array([.06, -.1, 0.]), Rotation.identity()), (np.array([.06, .1, 0.]), Rotation.identity())
    result = checker.edge(a, b)
    assert not result["passed"] and result["reason"] == "subdivision_budget_exhausted"


def test_route_identity_and_missing_route_rejected():
    policy, _, _ = setup_policy()
    with pytest.raises(ValueError, match="explicit geometrically checked"):
        InterlockedClawsMediumPolicy(oracle=policy.oracle)
    with pytest.raises(ValueError, match="frozen instance"):
        InterlockedClawsMediumPolicy(oracle=policy.oracle, route=dict(identity={}, waypoints=[{}]))


def test_empty_grasp_set_cannot_pass_vacuously():
    policy, _, _ = setup_policy()
    oracle = deepcopy(policy.oracle)
    oracle["grasps"] = {}
    with pytest.raises(ValueError, match="ownership"):
        InterlockedClawsMediumPolicy(oracle=oracle, part="hold")


def test_nonfinite_stage_timeout_is_rejected():
    policy, _, _ = setup_policy()
    with pytest.raises(ValueError, match="waypoint"):
        InterlockedClawsMediumPolicy(oracle=policy.oracle,
            route=dict(identity={"mesh": "frozen"}, waypoints=[dict(phase="C1", timeout_s=float("nan"), tcp={"left": body()})]))
