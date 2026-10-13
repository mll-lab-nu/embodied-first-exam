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
from scripts.control_transfer.trusted.fly import features, load_force_asset, parameters, rollout
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

    def test_public_nominal_has_no_private_imports_or_draws(self):
        root = Path(__file__).resolve().parents[1]
        for name in ["neuralfly_nominal.py", "neuralfly_video.py", "neuralfly_constants.py", "control_public/fly.py"]:
            text = (root / name).read_text()
            for forbidden in ["trusted.", "plant_seed", "private-fly", "forces.npz", "ASSET_SHA256", "held_out"]:
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
