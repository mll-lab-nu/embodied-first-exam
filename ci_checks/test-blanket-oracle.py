"""Blanket audit regressions; physical evidence is produced by the runner."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.evaluation.terminal import SettlingSpec, evaluate_settling
from topogym.planning.blanket_flatten.audit import release_settled
from scripts.oracle_runners import run_blanket_oracle

# The final-settling contract a Blanket episode seals in static_model.json.
SETTLING = dict(revision="release_settling_v2", rigid_targets=[], fem_targets=[], particle_targets=["blanket"],
                clearance_m=.005, maximum_speed_m_s=.03, maximum_angular_speed_rad_s=.02, maximum_drift_m=.003,
                maximum_rotation_drift_rad=.02, particle_radius_m=.008)
SPEC = SettlingSpec(particle_targets=("blanket",), clearance_m=.005, maximum_speed_m_s=.03, maximum_drift_m=.003,
                    particle_radius_m=.008)


def cloth(rng):
    x = np.column_stack((rng.uniform(-.3, .3, 400), rng.uniform(-.24, .24, 400), rng.uniform(.75, .754, 400)))
    return x, rng.normal(0., .005, x.shape)


def world(x, v, robot, assist=False):
    geometry = dict(schema_version=1, physics_step=7, complete=True, robot_present=True,
                    robot_bounds_m=np.asarray(robot, float).tolist(), target_bounds_m={})
    return dict(physics_step=7, assist_active=assist, release_geometry=geometry,
                particles=dict(blanket=dict(position_m=x, velocity_m_s=v)))


def audited(state, x, v, reference=None):
    return release_settled(state, x, v, reference, SETTLING, np.asarray)


def native(state, reference=None):
    return evaluate_settling(state, SPEC, reference)[0]


class BlanketAuditReleaseTests(unittest.TestCase):
    def test_clearance_threshold_matches_the_native_contract(self):
        x, v = cloth(np.random.default_rng(0))
        top = x[:, 2].max()+SETTLING["particle_radius_m"]
        for gap, expected in ((.0049, False), (.0051, True), (.08, True)):
            robot = [[[-.05, -.05, top+gap], [.05, .05, top+gap+.1]]]
            state = world(x, v, robot)
            self.assertEqual(audited(state, x, v), expected, gap)
            self.assertEqual(native(state), expected, gap)

    def test_active_assist_or_window_drift_restarts_confirmation(self):
        x, v = cloth(np.random.default_rng(1))
        robot = [[[-.05, -.05, 1.], [.05, .05, 1.1]]]
        self.assertFalse(audited(world(x, v, robot, assist=True), x, v))
        moved = x.copy()
        moved[0, 0] += .004
        for reference, expected in ((x, False), (moved, True)):
            state = world(moved, v, robot)
            self.assertEqual(audited(state, moved, v, reference), expected)
            self.assertEqual(native(state, dict(blanket=reference)), expected)

    def test_random_robot_bounds_agree_with_native_evaluation(self):
        rng = np.random.default_rng(2)
        for case in range(300):
            x, v = cloth(rng)
            low = rng.uniform([-.4, -.3, .74], [.4, .3, .80], (rng.integers(1, 6), 3))
            robot = np.stack((low, low+rng.uniform(.005, .08, low.shape)), axis=1)
            if case % 3 == 0:
                v = v*8   # some cases exceed the 0.03 m/s quiet gate
            state = world(x, v, robot)
            self.assertEqual(audited(state, x, v), native(state), case)


class BlanketRunnerTests(unittest.TestCase):
    def test_faulted_recording_preserves_prefix_and_original_error(self):
        env = SimpleNamespace(_faulted=False, sensor_frame=Mock(), add_frame_sink=Mock(),
            _task=SimpleNamespace(result=SimpleNamespace(task_success=False, terminated=False)))
        with tempfile.TemporaryDirectory() as folder, \
                patch("topogym.recording.RecordingSession") as recorder, \
                patch("topogym.recording.segment.save_rgb"):
            with self.assertRaisesRegex(RuntimeError, "physics interrupted"):
                with run_blanket_oracle.record_episode(env, Path(folder)):
                    env._faulted = True
                    raise RuntimeError("physics interrupted")
            env.sensor_frame.assert_called_once_with()
            env.add_frame_sink.return_value.assert_called_once_with()
            session = recorder.return_value
            session.append_final.assert_not_called()
            result = session.finish.call_args.args[0]
            self.assertTrue(result["environment_faulted"])
            self.assertFalse(result["task_success"])
            self.assertFalse(result["final_frame_available"])
            session.close.assert_called_once_with(commit=True)

    def run_worker(self, output, variation, *, success=True, extra=()):
        argv = ["run_blanket_oracle.py", "--worker", "--variation", variation,
                "--seed", "0", "--output", str(output), *extra]
        with patch.object(sys, "argv", argv), \
                patch("topogym.simulator.Env") as env_type, \
                patch("topogym.simulator.SegmentRunner") as runner_type, \
                patch("topogym.planning.blanket_flatten.assist_support.enable") as enable, \
                patch("topogym.planning.blanket_flatten.robot_oracle.run_route_oracle",
                      return_value=dict(task_success=success)) as route:
            result = run_blanket_oracle.main()
            config = env_type.call_args.args[0]
            env = env_type.return_value.__enter__.return_value
            runner = runner_type.return_value.__enter__.return_value
            self.assertTrue(env.defer_rgb)
            env.reset.assert_called_once_with(seed=0)
            enable.assert_called_once_with()
            runner_type.assert_called_once_with(env, output / "trail")
            route.assert_called_once_with(env, runner, output, variation=variation)
        return result, config

    def test_worker_preserves_frozen_scene_and_route_contracts(self):
        # The hard witness needs 33687 ticks, beyond the other tiers' budget.
        with tempfile.TemporaryDirectory() as folder:
            for tier, budget, guard in (("very_easy", 20000, 1.3), ("easier", 48000, 1.3),
                                        ("easy", 28000, 1.3), ("medium", 28000, 1.5),
                                        ("hard", 40000, 1.5)):
                with self.subTest(variation=tier):
                    code, config = self.run_worker(Path(folder), tier)
                    self.assertEqual(code, 0)
                    self.assertEqual(config.task_id, "blanket_flatten")
                    self.assertEqual(config.variation_id, tier)
                    self.assertEqual(config.max_physics_steps, budget)
                    self.assertEqual((config.compute_backend, config.precision, config.physics_dt_s,
                                      config.solver_substeps, config.control_decimation),
                                     ("cuda", "64", .0025, 4, 10))
                    self.assertTrue(config.enable_rgb)
                    self.assertTrue(config.enable_privileged)
                    self.assertEqual(config.control_mode, "JOINT_ABS")
                    self.assertEqual(config.grasp_assist.model, "pbd_local_patch_v1")
                    target, = config.grasp_assist.targets
                    self.assertEqual(target.entity, "blanket")
                    self.assertEqual((target.spatial_radius_m, target.material_radius_m), (.018, .018))
                    self.assertEqual(target.max_strain_ratio, guard)

    def test_explicit_budget_and_native_failure_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            code, config = self.run_worker(Path(folder), "hard", success=False,
                                           extra=("--max-physics-steps", "45000"))
            self.assertEqual(config.max_physics_steps, 45000)
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
