"""Short, non-solving policies verify action semantics against real physics.

Candidate poses are prepared by the test owner using read-only FK. The policy
only receives ordinary Interaction and submits dictionaries. RuntimeEvidence
retains actual Nyx views and control-boundary state arrays, not per-tick exports.
"""
from copy import deepcopy
import os
from pathlib import Path
import traceback

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from topogym.simulator import Env, SimulatorConfig
from topogym.robot.control import MODES
from topogym.solvers.genesis_kinematics import GenesisFKSolver
from topogym.utils.arrays import to_numpy
from topogym.utils.io import to_jsonable
from runtime_evidence import RuntimeEvidence

pytestmark = [pytest.mark.genesis, pytest.mark.render]


def rotation(quaternion):
    return Rotation.from_quat(np.asarray(quaternion)[[1, 2, 3, 0]])


def targets_and_action(env, mode):
    measured = env.privileged.get("robot")
    q = to_numpy(env._robot.entity.get_qpos()).reshape(-1).copy()
    goals = {}
    for index, name in enumerate(env.action_spec["arms"]):
        group = env._robot.groups[name]
        target = np.array(measured[name]["joint_position_rad"], copy=True)
        target[0] += .02 if index == 0 else -.02
        q[env._robot._q_indices[name][:len(group.arm_joints)]] = target
        low, high = group.gripper_limits
        goals[name] = {"joint_position_rad": target,
                       group.gripper_field: low + .35 * (high - low)}
    pose = GenesisFKSolver(env._robot.entity).solve(q)
    action = {}
    for name, goal in goals.items():
        group = env._robot.groups[name]
        link = env._robot.entity.get_link(group.hand_link).idx_local
        hand_r = rotation(pose["orientation_wxyz"][link])
        tcp_r = hand_r * rotation(group.tcp_orientation_in_hand_wxyz)
        goal["position_world_m"] = (pose["position_world_m"][link]
                                    + hand_r.apply(group.tcp_position_in_hand_m))
        goal["orientation_wxyz"] = tcp_r.as_quat()[[3, 0, 1, 2]]
        command = {group.gripper_field: goal[group.gripper_field]}
        if mode == "JOINT_ABS":
            command["joint_position_rad"] = goal["joint_position_rad"]
        elif mode == "JOINT_DELTA":
            command["joint_delta_rad"] = (goal["joint_position_rad"]
                                            - measured[name]["joint_position_rad"])
        elif mode == "EE_ABS":
            command.update({key: goal[key] for key in
                            ("position_world_m", "orientation_wxyz")})
        else:
            command["translation_world_m"] = (goal["position_world_m"]
                                                - measured[name]["tcp_position_world_m"])
            command["rotation_world_rad"] = (
                tcp_r * rotation(measured[name]["tcp_orientation_wxyz"]).inv()
            ).as_rotvec()
        action[name] = command
    return goals, to_jsonable(action)


def short_policy(interaction, first_action, count=10):
    """One target submission, then hold; no engine or privileged access."""
    for index in range(count):
        action = first_action if index == 0 else {}
        result = interaction.step(action)
        yield action, result
        if result[2] or result[3]:
            return


@pytest.mark.parametrize("robot_id", ["aloha", "panda_robotiq"])
@pytest.mark.parametrize("control_mode", MODES)
def test_receiver(robot_id, control_mode):
    root = Path(os.environ["TOPOGYM_TEST_OUTPUT"])
    name = f"receiver_{robot_id}_{control_mode}"
    cfg = SimulatorConfig(
        task_id="cast_coil" if robot_id == "aloha" else "hedgehog_in_cage",
        robot_id=robot_id, observation_mode="EE", control_mode=control_mode,
        enable_privileged=True,
    )
    evidence = RuntimeEvidence(root / name, name, cfg)
    evidence.report["scope"] = "short policy action receiver; no grasp or solve claim"
    evidence.report["tolerances"] = dict(
        tcp_position_m=.003, tcp_orientation_rad=.01,
        joint_tracking_rad=.005, gripper_m=.003, gripper_rad=.03,
    )
    error = None
    try:
        with Env(cfg) as env:
            obs, info = env.reset(seed=17)
            operator = env.interaction()
            with pytest.raises(PermissionError):
                operator.get("world")
            initial = env.state_history[0].ref
            evidence.sample(env, obs, info, label="initial")
            goals, action = targets_and_action(env, control_mode)
            evidence.report.update(action=action, goals=to_jsonable(goals),
                                   action_spec=to_jsonable(operator.action_spec))
            compiled = None
            for segment in range(2):
                with evidence.stage(f"segment_{segment}") as row:
                    start = dict(operator.observe()["state"])
                    row["initial_state"] = start
                    # Starting/ending a Python policy does not reset or step.
                    if segment:
                        assert start == previous_final
                    for index, (submitted, result) in enumerate(short_policy(
                        operator, action if segment == 0 else {}
                    )):
                        obs, _, done, truncated, info = result
                        evidence.sample(env, obs, info, action=submitted,
                                        label=f"segment_{segment}_step_{index}")
                        assert not done and not truncated
                        assert info["physics_steps"] == cfg.control_decimation
                        assert info["action_duration_s"] == pytest.approx(.025)
                        assert info["physics_step"] == (segment * 10 + index + 1) * 10
                        executed = to_jsonable(env.last_transition.info["executed_joint_targets"])
                        if compiled is None:
                            compiled = executed
                            for arm, goal in goals.items():
                                field = operator.action_spec["groups"][arm]["gripper_field"]
                                assert executed[arm][field] == goal[field]
                                if control_mode.startswith("JOINT"):
                                    np.testing.assert_allclose(executed[arm]["joint_position_rad"],
                                                               goal["joint_position_rad"], atol=1e-12, rtol=0)
                        assert executed == compiled, "Hold changed the submitted targets"
                    previous_final = dict(obs["state"])
                    row["final_state"] = previous_final
                    evidence.end_recording()
            assert len(env.state_history) == 201
            measured = env.privileged.get("robot")
            errors = {}
            for arm, goal in goals.items():
                field = operator.action_spec["groups"][arm]["gripper_field"]
                finger_field = "finger_position_" + ("m" if field.endswith("_m") else "rad")
                errors[arm] = dict(
                    tcp_position_m=float(np.linalg.norm(measured[arm]["tcp_position_world_m"] - goal["position_world_m"])),
                    tcp_orientation_rad=float((rotation(measured[arm]["tcp_orientation_wxyz"]).inv()
                                               * rotation(goal["orientation_wxyz"])).magnitude()),
                    joint_tracking_rad=float(np.max(np.abs(measured[arm]["joint_position_rad"]
                                                          - compiled[arm]["joint_position_rad"]))),
                    gripper_native=float(np.max(np.abs(measured[arm][finger_field] - goal[field]))),
                )
            evidence.report["tracking_errors_at_0_5_s"] = errors
            evidence.save()
            for arm, values in errors.items():
                assert values["tcp_position_m"] <= .003, values
                assert values["tcp_orientation_rad"] <= .01, values
                assert values["joint_tracking_rad"] <= .005, values
                field = operator.action_spec["groups"][arm]["gripper_field"]
                assert values["gripper_native"] <= (.003 if field.endswith("_m") else .03), values
            before = operator.observe()
            history = env.state_history
            invalid = deepcopy(action)
            last = operator.action_spec["arms"][-1]
            field = operator.action_spec["groups"][last]["gripper_field"]
            invalid[last][field] = float("nan")
            with pytest.raises(ValueError):
                operator.step(invalid)
            assert operator.observe() is before and env.state_history == history
            for arm in goals:
                np.testing.assert_array_equal(env.privileged.get("robot")[arm]["joint_position_target_rad"],
                                              compiled[arm]["joint_position_rad"])
            with pytest.raises(PermissionError):
                operator.rewind_to(initial)
            obs, info = env.interaction(privileged=True).rewind_to(initial)
            evidence.sample(env, obs, info, label="rewind")
            evidence.report["checks"] = dict(
                ordinary_policy=True, simultaneous_groups=len(goals),
                clock_and_history=True, segment_continuity=True,
                target_hold=True, invalid_action_atomic=True, permission_boundary=True,
            )
            # Finish the restored-branch recording while the Env still owns
            # its renderer resources; do not leave writers open across close.
            evidence.end_recording()
    except BaseException:
        error = traceback.format_exc()
        raise
    finally:
        evidence.close(error)
