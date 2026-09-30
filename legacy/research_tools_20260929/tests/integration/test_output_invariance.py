"""The same input sequence is invariant to RGB and passive recording consumers."""
from dataclasses import replace
from contextlib import nullcontext
from pathlib import Path
import os
import traceback
import numpy as np
import pytest
from topogym.simulator import Env, SimulatorConfig
from topogym.data import EpisodeDatasetWriter
from runtime_evidence import RuntimeEvidence, state_arrays
from test_base_task_runtime import compare_states

pytestmark = [pytest.mark.genesis, pytest.mark.render]


@pytest.mark.parametrize("robot_id", ["aloha", "panda_robotiq"])
def test_outputs(robot_id):
    root = Path(os.environ["TOPOGYM_TEST_OUTPUT"])
    cfg = SimulatorConfig(task_id="cast_coil" if robot_id == "aloha" else "hedgehog_in_cage",
                          robot_id=robot_id, enable_privileged=True)
    evidence = RuntimeEvidence(root / f"outputs_{robot_id}", f"outputs_{robot_id}", cfg)
    error, expected = None, []
    try:
        for rgb in (False, True):
            with Env(replace(cfg, enable_rgb=rgb)) as env:
                with evidence.stage("rgb_on" if rgb else "rgb_off") as stage:
                    obs, info = env.reset(seed=23)
                    group = env.action_spec["arms"][0]
                    q = np.array(env.privileged.get("robot")[group]["joint_position_rad"], copy=True); q[0] += .01
                    if rgb:
                        evidence.sample(env, obs, info, label="initial")
                    # Baseline has no RGB, recording or dataset consumer.
                    with (EpisodeDatasetWriter(evidence.folder / "transitions.jsonl") if rgb else nullcontext()) as writer:
                        remove = env.add_transition_sink(writer.append) if writer else lambda: None
                        remove_events = env.add_lifecycle_sink(writer.on_lifecycle) if writer else lambda: None
                        for i in range(12):
                            action = {group: {"joint_position_rad": q}} if i == 0 else {}
                            obs, _, done, truncated, info = env.step(action)
                            assert not done and not truncated
                            if rgb:
                                for _ in range(3):
                                    assert env.observe() is obs
                                    env.render()
                                actual = evidence.sample(env, obs, info, action=action)
                                compare_states(actual, expected[i], atol=2e-6)
                            else:
                                actual = state_arrays(dict(world=env.privileged.get("world"), robot=env.privileged.get("robot")))
                                expected.append(actual)
                                np.savez_compressed(evidence.folder / f"rgb_off_{i:04d}.npz", **actual)
                        if writer:
                            writer.finish({"scope": "output invariance"})
                        remove(); remove_events()
                    stage["physical_ticks"] = info["physics_step"]
                    evidence.end_recording()
    except BaseException:
        error = traceback.format_exc()
        raise
    finally:
        evidence.close(error)
