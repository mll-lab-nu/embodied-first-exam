"""Frozen tier scene acceptance with motion qualification explicitly deferred."""
import json
import os
from pathlib import Path

import numpy as np
import pytest

pytestmark = [pytest.mark.genesis, pytest.mark.pbd, pytest.mark.render]


def test_frozen_tier_scene_reset_action_and_rewind(monkeypatch):
    from topogym.simulator import make, SegmentRunner
    from topogym.utils.arrays import to_numpy
    from topogym.utils.io import sha256_file, write_json_atomic
    from topogym.world.genesis_world import GenesisWorld
    from topogym.world.physics.pbd_binding import read_birth_visual_binding
    from topogym.recording.segment import save_rgb
    candidate = Path(os.environ["TOPOGYM_BLANKET_CANDIDATE"])
    root = Path(os.environ["TOPOGYM_BLANKET_ACCEPTANCE"])
    root.mkdir(parents=True, exist_ok=False)
    source = json.loads((candidate/"report.json").read_text())
    config = source["config"]
    config.update(enable_privileged=True, max_physics_steps=100, work_dir=str(root/"work"))
    config["task_parameters"].update(initialization_mode="frozen",
        initial_state_path=str((candidate/"state/manifest.json").resolve()),
        initial_state_sha256=sha256_file(candidate/"state/manifest.json"))
    report = dict(status="in_progress", scope="scene_layout", motion_qualification="deferred",
        robot_solved=False, tier=config["variation_id"], seed=config["seed"],
        reset_advance_calls=0, config=config)
    write_json_atomic(root/"report.json", report)
    with np.load(candidate/"reference.npz", allow_pickle=False) as archive:
        reference = {k: archive[k].copy() for k in archive.files}
    env = make(**config)
    def state():
        cloth = env._task.entities["blanket"]
        return to_numpy(cloth.get_particles_pos()), to_numpy(cloth.get_particles_vel())
    def reset():
        def forbidden(*args, **kwargs):
            report["reset_advance_calls"] += 1
            raise AssertionError("Frozen scene reset advanced physics")
        with monkeypatch.context() as m:
            m.setattr(GenesisWorld, "advance", forbidden)
            env.reset(seed=config["seed"])
        assert len(env.state_history) == 1 and env.state_history[0].physics_step == 0
        for value, key in zip(state(), ("positions", "velocities")):
            np.testing.assert_array_equal(value, reference[key])
        assert not env._task.result.task_success
        assert env._task.binding_report["passed"]
    try:
        reset()
        report["initial_frames"] = save_rgb(root, "initial_frames", env.sensor_frame())
        initial_rgb = {k: v.copy() for k, v in env.sensor_frame().rgb.items()}
        report["initial_state"] = env.episode_metadata["initial_state"]
        report["initial_metrics"] = env._task.evaluate_state({"particles": {"blanket": {
            "position_m": state()[0], "velocity_m_s": state()[1]}}})[2]
        with SegmentRunner(env, root/"segments") as runner:
            interaction = runner.interaction(privileged=True)
            interaction.run_segment(request_id="released-scene-preview", actions=[{}]*8)
            report["free_preview_ticks"] = env._world.physics_step
            report["free_preview_maximum_drift_m"] = float(np.linalg.norm(state()[0]-reference["positions"], axis=1).max())
            before = state()
            ref = dict(episode_id=env._episode_id, state_id=env._state_id)
            group = env._robot.description.groups[0].name
            joints = env._robot.observe()[group]["joint_position_rad"].copy()
            target = env._robot.capture_state().targets[group]["joint_position_rad"].copy()
            target[0] += .01
            interaction.run_segment(request_id="small-joint-action", actions=[{group: {"joint_position_rad": target}}])
            movement = float(np.linalg.norm(env._robot.observe()[group]["joint_position_rad"]-joints))
            assert movement > 1e-8
            interaction.rewind_to(ref)
            for a, b in zip(before, state()):
                np.testing.assert_array_equal(a, b)
            np.testing.assert_array_equal(env._robot.observe()[group]["joint_position_rad"], joints)
            report.update(actual_joint_movement_rad=movement, rewind_exact=True)
            assert read_birth_visual_binding(env._task.entities["blanket"]).sha256 == env._task.binding.sha256
        reset()
        report["repeated_reset_particles_exact"] = True
        report["repeated_reset_rgb"] = {name: dict(
            equal=bool(np.array_equal(pixels, env.sensor_frame().rgb[name])),
            maximum_channel_error=int(np.abs(pixels.astype(int)-env.sensor_frame().rgb[name].astype(int)).max()))
            for name, pixels in initial_rgb.items()}
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        write_json_atomic(root/"report.json", report)
        env.close()
