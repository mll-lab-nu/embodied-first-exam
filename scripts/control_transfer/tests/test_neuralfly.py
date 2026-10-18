"""Family regression tests; no private force asset needed for these checks."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from scripts.control_transfer.control_public.fly import Controller, DEFAULT, MASS, Vehicle, target, validate
from scripts.control_transfer.neuralfly_reference import improve, observed_error
from scripts.control_transfer.neuralfly_spec import make_spec
from scripts.control_transfer.neuralfly_video import Video
from scripts.control_transfer.trusted.fly import episode_trajectory, features, load_force_asset, parameters, rollout
from scripts.control_transfer.trusted.adapter import feedback
from scripts.control_transfer.trusted.session import Session, atomic
from scripts.control_transfer.trusted.verify import verdict


class NeuralFlyTests(unittest.TestCase):
    def test_plant_is_fixed_and_banks_disjoint(self):
        for index in [0, 1, 999]:
            spec = make_spec(index)
            self.assertEqual(spec["schema"], "control-transfer-instance/2")
            self.assertEqual(spec["transfer_track"], "same-plant")
            a, b = spec["bank"]["adaptation"], spec["bank"]["held_out"]
            self.assertEqual((len(a), len(b)), (5, 10))
            self.assertEqual({c["plant_seed"] for c in a + b}, {10000 + index * 1000 + 100})
            self.assertFalse({c["episode_seed"] for c in a} & {c["episode_seed"] for c in b})
            self.assertEqual(sorted(c["stratum"] for c in b), sorted(list(range(5)) * 2))
            self.assertEqual(parameters(a[0]["plant_seed"]), parameters(b[-1]["plant_seed"]))

    def test_randomized_start_survives_model_constant_update(self):
        start = np.array([0.82, -0.27, 2.23])
        v = Vehicle(start, mass_scale=1.02)
        np.testing.assert_array_equal(v.data.qpos[:3], start)
        self.assertAlmostEqual(v.model.body_mass[1], MASS * 1.02)

    def test_reference_derivatives_and_period(self):
        for t in [0.1, 1.7, 5.2]:
            dt = 1e-5
            p, v, a = target(t)
            np.testing.assert_allclose((target(t + dt)[0] - target(t - dt)[0]) / (2 * dt), v, atol=1e-8)
            np.testing.assert_allclose((target(t + dt)[1] - target(t - dt)[1]) / (2 * dt), a, atol=1e-8)
            np.testing.assert_allclose(target(t + 2 * np.pi)[0], p, atol=1e-12)

    def test_general_eight_derivatives_and_reverse_traversal(self):
        for tilt in (0.0, np.pi / 2, 0.61):
            for direction in (-1, 1):
                command = dict(
                    yaw=1.1, tilt=tilt, amplitude_x=1.43, amplitude_z=0.61, rate=0.87, direction=direction, phase=0.43
                )
                t, dt = 1.7, 1e-5
                p, v, a = target(t, **command)
                np.testing.assert_allclose(
                    (target(t + dt, **command)[0] - target(t - dt, **command)[0]) / (2 * dt), v, atol=1e-8
                )
                np.testing.assert_allclose(
                    (target(t + dt, **command)[1] - target(t - dt, **command)[1]) / (2 * dt), a, atol=1e-8
                )
                np.testing.assert_allclose(target(t + 2 * np.pi / command["rate"], **command)[0], p, atol=1e-12)
        forward = target(0.7, phase=0.0, direction=1)
        reverse = target(-0.7, phase=0.0, direction=-1)
        np.testing.assert_allclose(forward[0], reverse[0])
        np.testing.assert_allclose(forward[1], -reverse[1])
        points = np.array([target(t, tilt=np.pi / 2, yaw=0.8)[0] for t in np.linspace(0, 7, 100)])
        np.testing.assert_allclose(points[:, 2], 1.8, atol=1e-12)

    def test_rotation_covariance_and_legacy_default_values(self):
        yaw, tilt = 0.7, -0.48
        c, s, ct, st = np.cos(yaw), np.sin(yaw), np.cos(tilt), np.sin(tilt)
        rotation = np.array([[c, -s * ct, s * st], [s, c * ct, -c * st], [0, st, ct]])
        for time in (0.0, 0.83, 3.17):
            expected = (
                np.array([1.25 * np.sin(time), 0, 1.8 + 0.75 * np.sin(2 * time)]),
                np.array([1.25 * np.cos(time), 0, 1.5 * np.cos(2 * time)]),
                np.array([-1.25 * np.sin(time), 0, -3 * np.sin(2 * time)]),
            )
            for value, old in zip(target(time), expected):
                np.testing.assert_array_equal(value, old)
            base = target(time, center=(0, 0, 0), direction=-1, rate=0.83)
            turned = target(time, yaw=yaw, tilt=tilt, center=(0, 0, 0), direction=-1, rate=0.83)
            for value, original in zip(turned, base):
                np.testing.assert_allclose(value, rotation @ original, atol=1e-14)

    def test_slow_six_lap_rollout_telemetry_and_frames_fit_image_cap(self):
        from scripts.control_transfer import neuralfly_nominal

        times, curves = [], []

        class Recorder:
            def __init__(self, model, path, center, *, curve):
                curves.extend(curve)

            def frame(self, data):
                times.append(float(data.time))

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as d, patch.object(neuralfly_nominal, "Video", Recorder):
            result = neuralfly_nominal.rollout(
                {**DEFAULT, "kp": 10.0, "kd": 6.0, "observer_gain": 8.0},
                rate=0.8,
                direction=-1,
                yaw=0.7,
                tilt=np.pi / 2,
                out=Path(d) / "nominal",
                render=True,
            )
        steps = round(6 * 2 * np.pi / (0.8 * 0.02))
        self.assertEqual(steps, 2356)
        self.assertEqual(len(times), 472)
        self.assertEqual(len(result["telemetry"]), 472)
        np.testing.assert_allclose(times, np.arange(472) * 0.1 + 0.02, atol=1e-10)
        np.testing.assert_allclose([r["t"] for r in result["telemetry"]], np.arange(472) * 0.1, atol=1e-12)
        np.testing.assert_allclose(
            curves,
            [
                target(t, rate=0.8, direction=-1, yaw=0.7, tilt=np.pi / 2)[0]
                for t in np.linspace(0, 2 * np.pi / 0.8, 100, endpoint=False)
            ],
        )
        sampled = times[::10]
        self.assertEqual(len(sampled), 48)
        self.assertLessEqual(steps * 0.02 - sampled[-1], 1.0)
        self.assertAlmostEqual(sampled[-1], 47.02, places=8)

    def test_held_out_trajectory_diversity_and_ground_clearance(self):
        for index in (0, 1):
            spec = make_spec(index, revision="general-eight/1")
            cases = spec["bank"]["held_out"]
            commands = [episode_trajectory(c["episode_seed"]) for c in cases]
            self.assertEqual({plane for plane, _ in commands}, {"horizontal", "vertical", "inclined"})
            for wind in range(5):
                self.assertEqual(
                    {cmd["direction"] for case, (_, cmd) in zip(cases, commands) if case["stratum"] == wind}, {-1, 1}
                )
            self.assertEqual(len({round(cmd["yaw"], 8) for _, cmd in commands}), 10)
            for case, (_, cmd) in zip(cases, commands):
                self.assertEqual(episode_trajectory(case["episode_seed"])[1], cmd)
                points = np.array([target(t, **cmd)[0] for t in np.linspace(0, 2 * np.pi / cmd["rate"], 200)])
                self.assertGreater(points[:, 2].min(), 0.9)
            train = {
                json.dumps(episode_trajectory(c["episode_seed"])[1], sort_keys=True) for c in spec["bank"]["adaptation"]
            }
            held = {json.dumps(cmd, sort_keys=True) for _, cmd in commands}
            self.assertFalse(train & held)

    def test_strict_numeric_policy_and_backward_compatibility(self):
        original = copy.deepcopy(DEFAULT)
        del original["observer_gain"]
        self.assertEqual(validate(original)["observer_gain"], 0.0)
        for key, value in [
            ("kp", True),
            ("observer_gain", 16.0),
            ("kp", float("nan")),
            ("residual", [[0] * 8] * 3),
            ("path", "/private"),
        ]:
            policy = copy.deepcopy(DEFAULT)
            policy[key] = value
            with self.assertRaises(ValueError):
                validate(policy)
        with self.assertRaises(ValueError):
            validate(None)
        p = copy.deepcopy(DEFAULT)
        p["residual"][1][2] = True
        with self.assertRaises(ValueError):
            validate(p)

    def test_observer_only_uses_observations_and_stays_in_envelope(self):
        p = {**copy.deepcopy(DEFAULT), "observer_gain": 8.0}
        controller = Controller(p)
        obs = {
            "position": [1.0, 0.0, 1.0],
            "velocity": [0.0, 0.0, 0.0],
            "target_position": [0.0, 0.0, 1.0],
            "target_velocity": [0.0, 0.0, -1.5],
            "target_acceleration": [0.0, 0.0, -3.0],
            "quaternion": [1.0, 0.0, 0.0, 0.0],
        }
        for i in range(40):
            obs["velocity"] = [0.1 * np.sin(i), 0.0, 0.0]
            force = controller.action(obs)
            self.assertLessEqual(np.linalg.norm(force), MASS * 9.81 * 2.2 + 1e-10)
            self.assertLessEqual(np.linalg.norm(force[:2]), force[2] * np.tan(np.deg2rad(50)) + 1e-10)
            self.assertGreater(force[2], 0.0)
        self.assertLessEqual(np.max(np.abs(controller.disturbance)), 20.0)

    def test_quaternion_sign_invariant(self):
        a = features([1.0, 2.0, 3.0], [0.98, 0.1, 0.1, 0.1], 8.5)
        np.testing.assert_allclose(a, features([1.0, 2.0, 3.0], [-0.98, -0.1, -0.1, -0.1], 8.5))

    def test_private_asset_required_and_hash_checked(self):
        with self.assertRaises(ValueError):
            load_force_asset(None)
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "forces.npz"
            np.savez(p, weights=np.zeros((18, 3)))
            with self.assertRaises(ValueError):
                load_force_asset(p)
            with self.assertRaises(ValueError):
                rollout(DEFAULT, {"plant_seed": 1, "episode_seed": 2, "stratum": 5}, Path(root) / "run", p)
            self.assertFalse((Path(root) / "run").exists())

    def test_feedback_projects_out_every_private_record(self):
        vehicle = Vehicle([0.0, 0.0, 1.8])
        row = vehicle.observation(0.0, target(0.0), np.random.default_rng(42))
        with tempfile.TemporaryDirectory() as root:
            record = {
                "feedback": {"telemetry": [row]},
                "metrics": {"score": 100},
                "dynamics": {"mass_scale": 1.01},
                "scenario": {"stratum": 4},
                "asset_sha256": "secret",
                "state_sha256": "secret",
            }
            result = feedback("neural-fly", record, root)
            self.assertEqual(set(result), {"telemetry", "images"})
            self.assertNotIn("secret", json.dumps(result))
            row["true_state"] = [0.0]
            with self.assertRaises(ValueError):
                feedback("neural-fly", record, root)

    def test_reference_rejects_privileged_feedback(self):
        case = {
            "telemetry": [{"t": 37.6, "position": [0.2, 0.0, 1.8], "target_position": [0.0, 0.0, 1.8]}],
            "images": [],
        }
        p, diagnosis = improve(DEFAULT, [case] * 5)
        self.assertEqual(p["observer_gain"], 4.0)
        self.assertIn("Noisy", diagnosis)
        with self.assertRaises(ValueError):
            observed_error([{**case, "score": 100}] * 5)

    def test_nop_scores_zero_and_asset_not_needed(self):
        with tempfile.TemporaryDirectory() as root:
            spec = make_spec(0)
            atomic(Path(root) / "instance.json", spec)
            session = Session(Path(root) / "nop", spec, render=False)
            session.finalize()
            result = verdict(session.root, Path(root) / "instance.json")
            self.assertEqual(result["success"], 0)
            self.assertEqual(result["final_reward"], 0)
            self.assertEqual(result["infra_error"], 0)

    def test_video_rejects_non_cpu_backend(self):
        with patch.dict("os.environ", {"MUJOCO_GL": "egl"}):
            with self.assertRaises(RuntimeError):
                Video(None, "/not-created.mp4", [0.0, 0.0, 1.8])

    def test_target_marker_uses_current_world_command(self):
        import io
        from types import SimpleNamespace
        import mujoco

        vehicle = Vehicle([0.0, 0.0, 1.8])
        model, data = vehicle.model, vehicle.data
        scene = mujoco.MjvScene(model, maxgeom=1000)
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [0.0, 0.0, 1.8]
        camera.distance = 6.0

        class Renderer:
            def __init__(self):
                self.scene = scene

            def update_scene(self, current, camera):
                mujoco.mjv_updateScene(
                    model, current, mujoco.MjvOption(), None, camera, mujoco.mjtCatBit.mjCAT_ALL, scene
                )

            def render(self):
                return np.zeros((1, 1, 3), dtype=np.uint8)

        video = Video.__new__(Video)
        video.model, video.renderer, video.camera = model, Renderer(), camera
        video.center = np.array([0.0, 0.0, 1.8])
        video.curve = [
            target(t, yaw=0.83, tilt=0.91, amplitude_x=1.4, amplitude_z=0.57)[0]
            for t in np.linspace(0, 2 * np.pi, 100, endpoint=False)
        ]
        video.writer = SimpleNamespace(stdin=io.BytesIO())
        for command in ([0.8, 0.1, 2.2], [-0.7, -0.2, 1.1]):
            model.site_pos[0] = command
            mujoco.mj_forward(model, data)
            video.frame(data)
            # The added target must match the command, independent of the robot
            # and MuJoCo's cached static site location.
            marker = scene.geoms[scene.ngeom - 101]
            np.testing.assert_allclose(marker.pos, command, atol=1e-6)
            self.assertFalse(np.allclose(marker.pos, data.qpos[:3]))
            drawn = [scene.geoms[scene.ngeom - 100 + i].pos.copy() for i in range(100)]
            np.testing.assert_allclose(drawn, video.curve, atol=1e-6)

    def test_public_nominal_has_no_private_imports_or_draws(self):
        root = Path(__file__).resolve().parents[1]
        for name in ["neuralfly_nominal.py", "neuralfly_video.py", "neuralfly_constants.py", "control_public/fly.py"]:
            text = (root / name).read_text()
            for forbidden in ["trusted.", "plant_seed", "private-fly", "forces.npz", "ASSET_SHA256", "held_out"]:
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
