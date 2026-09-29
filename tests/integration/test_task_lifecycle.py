"""Real registered Tasks share the same local Env and historical reset path."""

import os
import numpy as np
import pytest

from topogym.config import SimulatorConfig
from topogym.simulator.env import Env


def config(task_id, **kwargs):
    kwargs.setdefault("enable_rgb", False)
    kwargs.setdefault("enable_privileged", True)
    return SimulatorConfig(
        task_id=task_id,
        compute_backend=os.getenv("TOPOGYM_TEST_DEVICE", "cuda" if kwargs.get("enable_rgb") else "cpu"),
        precision="64",
        control_decimation=2,
        **kwargs,
    )


@pytest.mark.genesis
@pytest.mark.rigid
@pytest.mark.parametrize(
    "task_id",
    [
        "cast_coil",
        "cast_keyhole",
        "horseshoe_ring",
        "hedgehog_in_cage",
        "interlocked_claws",
        "buzz_wire_3d",
        "lock_picking",
        "fiber_bundling",
    ],
)
def test_rigid_tasks_share_lifecycle_and_restore(task_id):
    with Env(config(task_id)) as env:
        initial, info = env.reset(seed=0)
        assert info["physics_step"] == 0
        assert env.privileged.get("world")["bodies"] and env.privileged.get("world")["physics_step"] == 0
        anchor = info["state_id"]
        observed, reward, terminated, truncated, info = env.step({})
        assert info["physics_step"] > 0 and np.isfinite(reward)
        _, restored = env.privileged.rewind_to({"episode_id": env.state_history[0].episode_id, "state_id": anchor})
        assert (
            restored["physics_step"] == 0
            and restored["branch_parent_state_id"] == anchor
        )
        for side in initial["robot"]:
            np.testing.assert_allclose(
                env.observe()["robot"][side]["joint_position_rad"],
                initial["robot"][side]["joint_position_rad"],
                atol=1e-10,
            )


@pytest.mark.genesis
@pytest.mark.pbd
def test_blanket_real_particles_deform_and_rewind():
    with Env(config("blanket_flatten", physics_dt_s=0.0025)) as env:
        env.reset(seed=0)
        before = env.privileged.get("world")["particles"]
        name = next(iter(before))
        positions = before[name]["position_m"].copy()
        for _ in range(3):
            _, _, done, timeout, _ = env.step({})
            assert not done and not timeout
        after = env.privileged.get("world")["particles"][name]["position_m"]
        assert np.isfinite(after).all() and np.max(np.abs(after - positions)) > 1e-8
        env.privileged.rewind_to({"episode_id": env.state_history[0].episode_id, "state_id": 0})
        restored = env.privileged.get("world")["particles"][name]["position_m"]
        np.testing.assert_allclose(restored, positions, rtol=0, atol=1e-9)


@pytest.mark.genesis
@pytest.mark.render
@pytest.mark.parametrize(
    "task_id",
    [
        pytest.param("cast_coil", marks=pytest.mark.rigid),
        pytest.param("blanket_flatten", marks=pytest.mark.pbd),
    ],
)
def test_render_does_not_change_world_and_restore_invalidates_frames(task_id):
    with Env(config(task_id, enable_rgb=True)) as env:
        env.reset(seed=0)
        if task_id == "blanket_flatten":
            import genesis as gs

            texture = env._world.entities["blanket"].surface.get_rgba()
            assert isinstance(texture, gs.textures.ImageTexture)
            assert np.any(texture.image_array != texture.image_array[0, 0])
            assert "blanket_diffuse.png" in env.episode_metadata["asset_sha256"]
        frame = env.sensor_frame()
        assert frame.rgb and frame.physics_step == 0
        for _ in range(2):
            env.render()
        assert env.state_history[-1].physics_step == 0
        env.step({})
        env.privileged.rewind_to({"episode_id": env.state_history[0].episode_id, "state_id": 0})
        restored = env.sensor_frame()
        assert restored.branch_id != frame.branch_id
        assert restored.physics_step == 0 and set(restored.rgb) == set(frame.rgb)
