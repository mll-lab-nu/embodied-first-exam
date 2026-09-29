"""All thirteen base settings, with mandatory reports and actual scene video."""

import os
from pathlib import Path
import traceback

import numpy as np
import pytest

from topogym.config import SimulatorConfig, task_catalog
from topogym.config.registry import task_registration
from topogym.simulator.env import Env
from runtime_evidence import BASE_TASKS, RuntimeEvidence
from rgb_repro_evidence import save_rgb_comparison

pytestmark = [pytest.mark.genesis, pytest.mark.render]


@pytest.mark.parametrize("task_id", BASE_TASKS)
def test_base_runtime(task_id):
    assert set(BASE_TASKS) == {item["task_id"] for item in task_catalog()}
    exercise_runtime(task_id)


def exercise_runtime(task_id):
    root = os.environ.get("TOPOGYM_TEST_OUTPUT")
    assert root, "Use scripts/test_base_tasks.py to preserve reports and video"
    steps = int(os.environ.get("TOPOGYM_TEST_STEPS", "20"))
    assert steps >= 3
    cfg = SimulatorConfig(
        task_id=task_id,
        variation_id=os.environ.get("TOPOGYM_TEST_VARIATION", "base"),
        compute_backend=os.environ.get("TOPOGYM_TEST_DEVICE", "cuda"),
        precision="64",
        enable_rgb=True, enable_privileged=True,
        control_decimation=10,
        work_dir=Path(root) / task_id / "episodes",
    )
    evidence = RuntimeEvidence(Path(root) / task_id, task_id, cfg)
    env = Env(cfg)
    failure = None
    try:
        with evidence.stage("reset") as stage:
            initial, initial_info = env.reset(seed=0)
            assert initial_info["physics_step"] == 0
            assert set(initial) == {"state", "robot", "task", "rgb", "cameras"}
            assert (
                env.action_spec["robot_id"] == task_registration(task_id).default_robot
            )
            stage["metadata"] = dict(env.episode_metadata)
            stage["action_spec"] = env.action_spec
            values0 = evidence.sample(env, initial, initial_info, label="initial")
            initial_assets = dict(env.episode_metadata["asset_sha256"])
            initial_rgb = {name: pixels.copy() for name, pixels in initial["rgb"].items()}
            old_operator = env.interaction(privileged=True)
            assert not hasattr(old_operator, "reset")
            for name, value in values0.items():
                if name.startswith("/world/") and name.endswith(
                    ("velocity_m_s", "velocity_rad_s", "/velocity")
                ):
                    np.testing.assert_allclose(
                        value,
                        0.0,
                        atol=1e-12,
                        rtol=0.0,
                        err_msg=f"Unexpected birth velocity: {name}",
                    )
        with evidence.stage("observe_render_no_physics"):
            before = env._world.scene.t
            assert env.observe() is initial
            env.render()
            assert env._world.scene.t == before
        with evidence.stage("invalid_action_is_atomic"):
            before = env.state_history
            with pytest.raises(ValueError):
                env.step({"invalid_arm": {}})
            assert env.state_history == before
            assert env.observe() is initial
        group = env.action_spec["arms"][0]
        target = np.array(env.privileged.get("robot")[group]["joint_position_target_rad"], copy=True)
        limits = np.array(env.action_spec["groups"][group]["joint_limits_rad"])
        target[0] += 0.025 if target[0] + 0.025 <= limits[0, 1] else -0.025
        action = {group: {"joint_position_rad": target.tolist()}}
        anchor = future = None
        with evidence.stage("real_step_and_robot_response") as stage:
            for i in range(steps):
                observed, reward, done, timeout, info = env.step(
                    action if i == 0 else {}
                )
                values = evidence.sample(
                    env, observed, info, action=action if i == 0 else {}
                )
                assert np.isfinite(reward) and not done and not timeout, info
                assert info["physics_step"] == (i + 1) * cfg.control_decimation
                assert info["sim_time_s"] == pytest.approx(
                    info["physics_step"] * cfg.physics_dt_s
                )
                if i == 0:
                    anchor, anchor_values = info["state_id"], values
                if i == 1:
                    future, future_values = info["state_id"], values
            response = float(
                np.max(
                    abs(
                        observed["robot"][group]["joint_position_rad"]
                        - initial["robot"][group]["joint_position_rad"]
                    )
                )
            )
            stage["robot_response_rad"] = response
            assert response > 1e-6
            physical = env.privileged.get("world")
            if physical["particles"] or physical["fem"]:
                soft = "particles" if physical["particles"] else "fem"
                displacement = max(
                    float(np.max(abs(values[k] - values0[k])))
                    for k in values0
                    if k.startswith(f"/world/{soft}/") and k.endswith("/position_m")
                )
                stage["deformable_displacement_m"] = displacement
                assert displacement > 1e-8
        with evidence.stage("mid_state_restore_and_continuation") as stage:
            observed, info = env.privileged.rewind_to({"episode_id": env.state_history[0].episode_id, "state_id": anchor})
            restored = evidence.sample(env, observed, info, label="rewind")
            errors = compare_states(restored, anchor_values, atol=1e-8)
            checkpoint = env._history.get(anchor).world.ipc_state
            if checkpoint is not None:
                recaptured = env._world.scene.sim.coupler.checkpoint_store.capture()
                assert dict(recaptured.files) == dict(checkpoint.files), (
                    "Native dump changed after recover"
                )
                stage["native_dump_roundtrip_identical"] = True
            stage["continuation_absolute_tolerances"] = dict(
                position_m=2e-6,
                quaternion=2e-6,
                contact_force_N=1e-4,
                linear_velocity_m_s=1e-4 if checkpoint is not None else 2e-6,
                angular_velocity_rad_s=1e-3 if checkpoint is not None else 2e-6,
            )
            observed, _, done, timeout, info = env.step({})
            continued = evidence.sample(
                env, observed, info, action={}, label="continued"
            )
            assert not done and not timeout
            continuation_errors = compare_states(
                continued,
                future_values,
                atol=2e-6,
                ipc_continuation=checkpoint is not None,
            )
            stage.update(
                restore_max_errors=errors, continuation_max_errors=continuation_errors
            )
        with evidence.stage("discarded_future_and_control_substep"):
            # The next branch has the same engine tick. Poison only the renderer
            # cache to prove reset obtains fresh images even for static cameras.
            cameras = env._world.cameras
            shared = next(iter(cameras.values())).sensor._shared_metadata
            for cached in shared.image_cache.values():
                cached.zero_()
            with pytest.raises(ValueError):
                env.privileged.rewind_to({"episode_id": env.state_history[0].episode_id, "state_id": future})
            observed, info = env.privileged.rewind_to(env.state_history[-1].ref)
            assert all(np.any(pixels) for pixels in observed["rgb"].values()), (
                "Nyx reused its stale image cache after a same-tick branch restore"
            )
            compare_states(
                evidence.sample(env, observed, info, label="same_tick_rewind"),
                continued,
                atol=1e-8,
            )
            substep = next(
                s for s in env.state_history if s.branch_id == 0 and s.physics_step == 1
            )
            observed, info = env.privileged.rewind_to({"episode_id": env.state_history[0].episode_id, "state_id": substep.state_id})
            evidence.sample(env, observed, info, label="control_substep")
            assert info["physics_step"] == 1
            observed, _, done, timeout, info = env.step({})
            evidence.sample(env, observed, info, action={}, label="substep_continued")
            assert not done and not timeout
        with evidence.stage("initial_restore"):
            observed, info = env.privileged.rewind_to({"episode_id": env.state_history[0].episode_id, "state_id": initial_info["state_id"]})
            compare_states(
                evidence.sample(env, observed, info, label="initial_restore"),
                values0,
                atol=1e-8,
            )
        # A seed reset creates a fresh episode; it does not recover the prior
        # solver. Exercise A/B/A separately from state_id restoration.
        with evidence.stage("seed_A_B_A") as stage:
            old_episode = info["episode_id"]
            evidence.end_recording()
            observed, info = env.reset(seed=1)
            evidence.sample(env, observed, info, label="seed_B")
            assert info["episode_id"] != old_episode and info["physics_step"] == 0
            episode_b = info["episode_id"]
            evidence.end_recording()
            observed, info = env.reset(seed=0)
            repeated = evidence.sample(env, observed, info, label="seed_A_again")
            # Preserve all cameras before any asset/RGB assertion can abort.
            save_rgb_comparison(evidence.folder / "rgb_repro", initial_rgb, observed["rgb"])
            stage["rgb_difference_report"] = "rgb_repro/comparison.json"
            assert dict(env.episode_metadata["asset_sha256"]) == initial_assets
            stage["initial_rgb_bitwise_equal"] = {
                name: bool(np.array_equal(pixels, observed["rgb"][name])) for name, pixels in initial_rgb.items()}
            for name, equal in stage["initial_rgb_bitwise_equal"].items():
                assert equal, f"Initial Nyx pixels not reproducible for seed 0: {name}"
            with pytest.raises(RuntimeError, match="expired"):
                old_operator.observe()
            assert info["episode_id"] not in {old_episode, episode_b}
            stage["initial_state_max_errors"] = compare_states(
                repeated, values0, atol=1e-8
            )
            assert len(env.state_history) == 1
            observed, _, done, timeout, info = env.step({})
            evidence.sample(env, observed, info, action={}, label="rebuilt_step")
            assert not done and not timeout
        with evidence.stage("close"):
            # Finish external consumers before Nyx releases native scene resources.
            evidence.end_recording()
            env.close()
            env.close()
            assert not env.state_history
    except BaseException:
        failure = traceback.format_exc()
        raise
    finally:
        try:
            evidence.close(failure)
        finally:
            env.close()


def compare_states(actual, expected, *, atol, ipc_continuation=False):
    assert actual.keys() == expected.keys()
    errors = {}
    for key in expected:
        assert actual[key].shape == expected[key].shape, key
        errors[key] = float(np.max(np.abs(actual[key] - expected[key]), initial=0))
        tolerance = atol
        # A force residual is measured in newtons, not metres. Contact forces
        # from the iterative CUDA solve are accepted within 0.1 mN on a rerun;
        # direct restoration of stored forces still uses the strict 1e-8.
        if atol > 1e-8 and key == "/world/contacts/force":
            tolerance = 1e-4
        if ipc_continuation:
            # The native Newton stop criterion is a velocity tolerance (1e-4
            # m/s). Angular rates on centimetre-scale ABD objects amplify that
            # residual. Restore itself still uses the strict 1e-8 tolerance.
            if key.endswith("velocity_m_s"):
                tolerance = 1e-4
            elif key.endswith("angular_velocity_rad_s"):
                tolerance = 1e-3
        np.testing.assert_allclose(
            actual[key],
            expected[key],
            rtol=0.0 if atol <= 1e-8 else 1e-6,
            atol=tolerance,
            err_msg=key,
        )
    return errors
