"""Real joint/EE controls, observation rigs and episode-bound operator APIs."""
from dataclasses import replace
from pathlib import Path
import os
import traceback
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from topogym.simulator import Env, SimulatorConfig
from runtime_evidence import RuntimeEvidence

pytestmark = [pytest.mark.genesis, pytest.mark.render]


@pytest.mark.parametrize("robot_id", ["aloha", "panda_robotiq"])
def test_interfaces(robot_id):
    root = Path(os.environ["TOPOGYM_TEST_OUTPUT"])
    cfg = SimulatorConfig(task_id="cast_coil" if robot_id == "aloha" else "hedgehog_in_cage",
                          robot_id=robot_id, enable_privileged=True)
    evidence = RuntimeEvidence(root / f"interfaces_{robot_id}", f"interfaces_{robot_id}", cfg)
    error = None
    try:
        for observation_mode in ("JOINT", "EE"):
            for control_mode in ("JOINT_ABS", "JOINT_DELTA", "EE_ABS", "EE_DELTA"):
                with Env(replace(cfg, observation_mode=observation_mode, control_mode=control_mode)) as env:
                    with evidence.stage(f"{observation_mode}_{control_mode}") as stage:
                        obs, info = env.reset(seed=17)
                        operator = env.interaction(privileged=True)
                        assert not hasattr(operator, "reset")
                        evidence.sample(env, obs, info, label="initial")
                        group = env.action_spec["arms"][0]
                        measured = env.privileged.get("robot")[group]
                        # Pose from FK of a nearby valid configuration is a reachable target.
                        if control_mode.startswith("EE"):
                            from topogym.solvers.genesis_kinematics import GenesisFKSolver
                            from topogym.utils.arrays import to_numpy
                            description = env._robot.groups[group]
                            q = to_numpy(env._robot.entity.get_qpos()).reshape(-1).copy()
                            q[env._robot._q_indices[group][0]] += .01
                            pose = GenesisFKSolver(env._robot.entity).solve(q)
                            link = env._robot.entity.get_link(description.hand_link).idx_local
                            hand_rotation = Rotation.from_quat(pose["orientation_wxyz"][link][[1, 2, 3, 0]])
                            goal_position = pose["position_world_m"][link] + hand_rotation.apply(description.tcp_position_in_hand_m)
                            goal_rotation = hand_rotation * Rotation.from_quat(np.asarray(description.tcp_orientation_in_hand_wxyz)[[1, 2, 3, 0]])
                        if control_mode == "JOINT_ABS":
                            q = np.array(measured["joint_position_rad"], copy=True); q[0] += .01
                            action = {group: {"joint_position_rad": q}}
                        elif control_mode == "JOINT_DELTA":
                            q = np.zeros_like(measured["joint_position_rad"]); q[0] = .01
                            action = {group: {"joint_delta_rad": q}}
                        elif control_mode == "EE_ABS":
                            action = {group: {"position_world_m": goal_position,
                                              "orientation_wxyz": goal_rotation.as_quat()[[3, 0, 1, 2]]}}
                        else:
                            current_rotation = Rotation.from_quat(np.asarray(measured["tcp_orientation_wxyz"])[[1, 2, 3, 0]])
                            action = {group: {"translation_world_m": goal_position - measured["tcp_position_world_m"],
                                              "rotation_world_rad": (goal_rotation * current_rotation.inv()).as_rotvec()}}
                        group_spec = env.action_spec["groups"][group]
                        action[group][group_spec["gripper_field"]] = float(np.mean(group_spec["gripper_limits"]))
                        initial = env.state_history[0].ref
                        for i in range(4):
                            obs, _, done, truncated, info = operator.step(action if i == 0 else {})
                            assert not done and not truncated
                            evidence.sample(env, obs, info, action=action if i == 0 else {})
                        before = env.privileged.get("robot")
                        assert np.linalg.norm(before[group]["tcp_position_world_m"] - measured["tcp_position_world_m"]) > 1e-6
                        history = env.state_history
                        invalid = ({group: {"position_world_m": [100., 100., 100.], "orientation_wxyz": [1., 0., 0., 0.]}}
                                   if control_mode == "EE_ABS" else {"invalid_arm": {}})
                        with pytest.raises(ValueError):
                            operator.step(invalid)
                        assert env.state_history == history
                        for side in before:
                            np.testing.assert_allclose(env.privileged.get("robot")[side]["joint_position_rad"],
                                                       before[side]["joint_position_rad"], atol=1e-12, rtol=0)
                        obs, info = operator.rewind_to(initial)
                        evidence.sample(env, obs, info, label="rewind")
                        stage["action_spec"] = env.action_spec
                        stage["observation_spec"] = env.observation_spec
                        evidence.end_recording()
    except BaseException:
        error = traceback.format_exc()
        raise
    finally:
        evidence.close(error)
