"""Real seed A/B/A rebuilds and initial-state rewind, without claiming byte-identical asset reports."""

import os
import numpy as np
import pytest
from topogym.config import SimulatorConfig
from topogym.simulator.env import Env

pytestmark = [pytest.mark.genesis, pytest.mark.rigid]


@pytest.mark.parametrize("robot_id", ["aloha", "panda_robotiq"])
def test_same_seed_rebuilds_initial_physical_state_after_another_seed(robot_id):
    config = SimulatorConfig(
        task_id="cast_coil",
        robot_id=robot_id,
        compute_backend=os.getenv("TOPOGYM_TEST_DEVICE", "cpu"),
        control_decimation=2, enable_rgb=False, enable_privileged=True,
    )
    with Env(config) as env:
        initial, info = env.reset(seed=11)
        episode_id = info["episode_id"]
        instance_id = env.episode_metadata["instance_id"]
        first_robot = initial["robot"]
        first_bodies = env.privileged.get("world")["bodies"]
        env.step({})
        rewound, restored = env.privileged.rewind_to({"episode_id": env.state_history[0].episode_id, "state_id": 0})
        assert restored["physics_step"] == 0 and restored["episode_id"] == episode_id
        rewound = dict(rewound, world=env.privileged.get("world"))
        env.reset(seed=12)
        repeated, info = env.reset(seed=11)
        repeated = dict(repeated, world=env.privileged.get("world"))
        assert (
            info["episode_id"] != episode_id
            and env.episode_metadata["instance_id"] == instance_id
        )
        tolerance = 1e-9 if config.compute_backend == "cpu" else 2e-5
        for observation in (rewound, repeated):
            for group in first_robot:
                np.testing.assert_allclose(
                    observation["robot"][group]["joint_position_rad"],
                    first_robot[group]["joint_position_rad"],
                    atol=tolerance,
                    rtol=0.0,
                )
            for name in first_bodies:
                for field in (
                    "position_m",
                    "quaternion_wxyz",
                    "linear_velocity_m_s",
                    "angular_velocity_rad_s",
                ):
                    np.testing.assert_allclose(
                        observation["world"]["bodies"][name][field],
                        first_bodies[name][field],
                        atol=tolerance,
                        rtol=0.0,
                    )
