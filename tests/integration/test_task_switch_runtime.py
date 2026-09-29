"""Same-process rigid/FEM/PBD/Panda switching, with evidence for every scene."""

import os
from pathlib import Path
import traceback
import pytest

from runtime_evidence import RuntimeEvidence
from test_base_task_runtime import compare_states
from topogym.config import SimulatorConfig
from topogym.simulator.env import Env

pytestmark = [pytest.mark.genesis, pytest.mark.render]


def test_task_switch():
    root = Path(os.environ["TOPOGYM_TEST_OUTPUT"])
    cfg = SimulatorConfig(
        compute_backend=os.environ.get("TOPOGYM_TEST_DEVICE", "cuda"), enable_rgb=True
    )
    evidence = RuntimeEvidence(root / "task_switch", "task_switch", cfg)
    failure, env = None, None
    try:
        identities = set()
        robot_initials = {}
        for i, task in enumerate(
            (
                "cast_coil",
                "rope_threading",
                "blanket_flatten",
                "hedgehog_in_cage",
                "cast_coil",
            )
        ):
            with evidence.stage(f"{i}_{task}"):
                env = Env(
                    SimulatorConfig(
                        task_id=task,
                        compute_backend=cfg.compute_backend,
                        enable_rgb=True, enable_privileged=True,
                        work_dir=root / "task_switch" / "episodes",
                    )
                )
                obs, info = env.reset(seed=0)
                assert info["episode_id"] not in identities
                identities.add(info["episode_id"])
                values = evidence.sample(env, obs, info, label=f"{task}_initial")
                robot_id = env.action_spec["robot_id"]
                robot_state = {
                    key: value
                    for key, value in values.items()
                    if key.startswith("/robot/")
                }
                if robot_id in robot_initials:
                    compare_states(robot_state, robot_initials[robot_id], atol=1e-8)
                else:
                    robot_initials[robot_id] = robot_state
                if i == 0:
                    first = values
                if i == 4:
                    compare_states(values, first, atol=1e-8)
                obs, _, done, timeout, info = env.step({})
                evidence.sample(env, obs, info, action={}, label=f"{task}_step")
                assert not done and not timeout
                evidence.end_recording()
                env.close()
                assert not env.state_history
                env = None
    except BaseException:
        failure = traceback.format_exc()
        raise
    finally:
        try:
            evidence.close(failure)
        finally:
            if env is not None:
                env.close()
