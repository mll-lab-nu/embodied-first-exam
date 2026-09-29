"""Real frozen Blanket reset and standard segment evidence; explicit GPU run."""
import json
import os
from pathlib import Path

import numpy as np
import pytest

pytestmark = [pytest.mark.genesis, pytest.mark.pbd, pytest.mark.render]


def test_frozen_blanket_reset_and_segments(monkeypatch):
    from topogym.simulator.env import Env
    from topogym.simulator.config import SimulatorConfig
    from topogym.simulator import SegmentRunner
    from topogym.world.genesis_world import GenesisWorld
    from topogym.utils.arrays import to_numpy
    from topogym.utils.io import write_json_atomic, sha256_file
    from PIL import Image
    candidate = Path(os.environ["TOPOGYM_BLANKET_CANDIDATE"])
    root = Path(os.environ["TOPOGYM_BLANKET_ACCEPTANCE"])
    root.mkdir(parents=True, exist_ok=False)
    report = dict(status="in_progress", position_tolerance_m=1e-8,
        velocity_tolerance_m_s=1e-7, rgb_mean_tolerance=1., rgb_p99_tolerance=5.,
        reset_advance_calls=0, kind="frozen_initialization_not_solvability",
        checks=os.environ.get("TOPOGYM_BLANKET_CHECKS", "full"))
    write_json_atomic(root/"report.json", report)
    manifest = candidate/"state/manifest.json"
    preparation_config = json.loads((candidate/"report.json").read_text())["config"]
    parameters = dict(preparation_config["task_parameters"])
    parameters.update(initialization_mode="frozen", initial_state_path=str(manifest.resolve()),
                      initial_state_sha256=sha256_file(manifest))
    config = SimulatorConfig(task_id="blanket_flatten", seed=preparation_config["seed"], enable_privileged=True,
        variation_id=(preparation_config.get("variation_id") if preparation_config.get("variation_id") not in (None, "base") else "simple_folds"),
        control_decimation=10, max_physics_steps=1000, work_dir=root/"work",
        task_parameters=parameters)
    env, runner = Env(config), None
    def state():
        cloth = env._task.entities["blanket"]
        return (to_numpy(cloth.get_particles_pos()), to_numpy(cloth.get_particles_vel()))
    def reset_without_advance():
        with monkeypatch.context() as m:
            def forbidden(*args, **kwargs):
                report["reset_advance_calls"] += 1
                raise AssertionError("Frozen reset advanced physics")
            m.setattr(GenesisWorld, "advance", forbidden)
            return env.reset(seed=config.seed)
    try:
        reset_without_advance()
        with np.load(candidate/"reference.npz", allow_pickle=False) as archive:
            reference = {name: archive[name] for name in archive.files}
        p, v = state()
        report["anchor_position_error_m"] = float(np.abs(p-reference["positions"]).max())
        report["anchor_velocity_error_m_s"] = float(np.abs(v-reference["velocities"]).max())
        assert report["anchor_position_error_m"] <= report["position_tolerance_m"]
        assert report["anchor_velocity_error_m_s"] <= report["velocity_tolerance_m_s"]
        assert env.state_history[0].physics_step == 0 and len(env.state_history) == 1
        assert not env._task.result.task_success
        first_rgb = {name: rgb.copy() for name, rgb in env.sensor_frame().rgb.items()}
        rgb_errors = {}
        for name, pixels in first_rgb.items():
            source = np.asarray(Image.open(candidate/f"rgb/segment_0/final/{name}.png"))
            error = abs(pixels.astype(float)-source.astype(float))
            rgb_errors[name] = dict(mean=float(error.mean()), p99=float(np.quantile(error, .99)), maximum=float(error.max()))
            assert error.mean() <= report["rgb_mean_tolerance"] and np.quantile(error, .99) <= report["rgb_p99_tolerance"]
        report["source_to_reset_rgb_errors"] = rgb_errors
        report["initial_state"] = env.episode_metadata["initial_state"]
        write_json_atomic(root/"report.json", report)
        if report["checks"] == "full":
            runner = SegmentRunner(env, root/"segments")
            interaction = runner.interaction(privileged=True)
            interaction.begin_segment(request_id="released-continuation")
            with np.load(candidate/"continuation.npz", allow_pickle=False) as archive:
                expected = {name: archive[name] for name in archive.files}
            continuation_error = [0., 0.]
            def compare_tick(record):
                tick = record["state"]["physics_step"]
                if 1 <= tick <= 5:
                    cloth = record["world"]["particles"]["blanket"]
                    continuation_error[0] = max(continuation_error[0], float(np.abs(cloth["position_m"]-expected["positions"][tick-1]).max()))
                    continuation_error[1] = max(continuation_error[1], float(np.abs(cloth["velocity_m_s"]-expected["velocities"][tick-1]).max()))
            unsubscribe = env.add_state_sink(compare_tick)
            interaction.step({})
            unsubscribe()
            report["continuation_maximum_errors"] = continuation_error
            assert continuation_error[0] <= report["position_tolerance_m"]
            assert continuation_error[1] <= report["velocity_tolerance_m_s"]
            for _ in range(19):
                interaction.step({})
            interaction.end_segment()
            middle = dict(episode_id=env._episode_id, state_id=env._state_id)
            interaction.begin_segment(request_id="continued-hold")
            for _ in range(20):
                interaction.step({})
            interaction.end_segment()
            report["two_segments_final_tick"] = env._world.physics_step
            drift = float(np.linalg.norm(state()[0]-p, axis=1).max())
            report["released_one_second_drift_m"] = drift
            assert drift <= .002
            # One real joint action and privileged rewind share the same Env path.
            group = env._robot.description.groups[0]
            targets = env._robot.capture_state().targets[group.name]["joint_position_rad"].copy()
            targets[0] += .01
            before = state()
            joints_before = env._robot.observe()[group.name]["joint_position_rad"].copy()
            ref = dict(episode_id=env._episode_id, state_id=env._state_id)
            interaction.run_segment(request_id="small-joint-action", actions=[{group.name: {"joint_position_rad": targets}}])
            joint_movement = np.linalg.norm(env._robot.observe()[group.name]["joint_position_rad"]-joints_before)
            report["actual_joint_movement_rad"] = float(joint_movement)
            assert joint_movement > 1e-8
            interaction.rewind_to(ref)
            for a, b in zip(before, state()):
                np.testing.assert_array_equal(a, b)
            np.testing.assert_array_equal(env._robot.observe()[group.name]["joint_position_rad"], joints_before)
            report["action_then_rewind"] = True
            runner.close(); runner = None
        old = env.interaction()
        reset_without_advance()
        for a, key in zip(state(), ("positions", "velocities")):
            np.testing.assert_array_equal(a, reference[key])
        report["repeated_reset_rgb_equal"] = {
            n: bool(np.array_equal(first_rgb[n], pix)) for n, pix in env.sensor_frame().rgb.items()}
        assert all(report["repeated_reset_rgb_equal"].values())
        with pytest.raises(RuntimeError):
            old.observe()
        report.update(status="passed", repeated_reset_state_equal=True, initial_task_success=False)
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json_atomic(root/"report.json", report)
        if runner is not None:
            runner.close()
        env.close()
