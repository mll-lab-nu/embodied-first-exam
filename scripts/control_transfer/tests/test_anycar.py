"""Real CPU physics, numeric ABI, privacy projection, and anti-shortcut scoring checks."""

import json
from pathlib import Path
import shutil
import unittest
import tempfile
import subprocess
import sys
import numpy as np
from scripts.control_transfer.control_public.anycar import DEFAULT, HORIZON, reference, validate
from scripts.control_transfer.components.anycarbench.model import Vehicle, NOMINAL
from scripts.control_transfer.trusted.anycar import make_spec, plant_parameters, episode_parameters, score_trajectory
from scripts.control_transfer.trusted.anycar_reference import fit, public_feedback


class ContractTests(unittest.TestCase):
    def test_numeric_artifact_rejects_invalid_payloads(self):
        bad = [
            {},
            dict(DEFAULT, extra="execute"),
            dict(DEFAULT, drive_scale=float("nan")),
            dict(DEFAULT, heading_gain=True),
            dict(DEFAULT, drive_scale=10**1000),
            dict(DEFAULT, steering_bias="0"),
            dict(DEFAULT, schema="other"),
        ]
        for policy in bad:
            with self.subTest(policy=str(policy)[:100]), self.assertRaises(ValueError):
                validate(policy)
        self.assertEqual(json.loads(validate(DEFAULT)), DEFAULT)

    def test_private_bank_has_persistent_plant_and_disjoint_episodes(self):
        spec = make_spec(0)
        self.assertEqual(spec["schema"], "control-transfer-instance/2")
        self.assertEqual(spec["transfer_track"], "same-plant")
        cases = sum(spec["bank"].values(), [])
        self.assertEqual(len(spec["bank"]["held_out"]), 10)
        self.assertEqual({c["plant_seed"] for c in cases}, {10100})
        self.assertEqual([c["episode_seed"] for c in spec["bank"]["adaptation"]], [10000, 10001, 10002])
        self.assertEqual([c["episode_seed"] for c in spec["bank"]["held_out"]], list(range(10300, 10310)))
        self.assertEqual({c["plant_seed"] for c in sum(make_spec(1)["bank"].values(), [])}, {11100})
        self.assertEqual(len({c["episode_seed"] for c in cases}), len(cases))
        for key in ("plant_seed", "episode_seed", "surfaces", "motor_gain", "steering_gain"):
            self.assertNotIn(key, json.dumps(spec["public"]))
        self.assertEqual(plant_parameters(1), plant_parameters(1))
        self.assertNotEqual(episode_parameters(1)[1], episode_parameters(2)[1])

    def test_spec_hook_uses_only_standard_library(self):
        value = subprocess.check_output(
            [
                sys.executable,
                "-S",
                "-c",
                "import json, sys; from scripts.control_transfer.anycar_spec import make_spec; "
                "assert not any(k.startswith(('mujoco', 'numpy', 'scripts.control_transfer.trusted')) for k in sys.modules); "
                "from scripts.control_transfer.trusted.anycar_spec import make_spec as legacy; "
                "assert legacy is make_spec; print(json.dumps([make_spec(0), make_spec(1)]))",
            ],
            text=True,
        )
        self.assertEqual(json.loads(value), json.loads(json.dumps([make_spec(0), make_spec(1)])))

    def test_nominal_alias_in_isolated_public_package(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            files = (
                "control_public/anycar.py",
                "control_public/anycar_nominal.py",
                "components/anycarbench/__init__.py",
                "components/anycarbench/model.py",
                "components/anycarbench/tracks.py",
                "components/anycarbench/circuits.json",
                "components/anycarbench/compact_routes.json",
            )
            for name in files:
                destination = app / "scripts/control_transfer" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, destination)
            shutil.copytree(app / "scripts/control_transfer/control_public", app / "control_public")
            # -I excludes the checkout, cwd and PYTHONPATH; only this explicit
            # public allowlist is importable alongside installed dependencies.
            program = """
import importlib, importlib.util, json, pathlib, sys
import numpy as np
app = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(app))
assert importlib.util.find_spec('scripts.control_transfer.trusted') is None
trajectories = []
policies = []
for name in ('control_public.anycar_nominal', 'scripts.control_transfer.control_public.anycar_nominal'):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).is_relative_to(app)
    component = importlib.import_module(module.Vehicle.__module__)
    assert pathlib.Path(component.__file__).is_relative_to(app)
    trajectories.append(module.train_rollout(module.DEFAULT))
    policies.append(module.validate(module.DEFAULT))
assert trajectories[0].shape == (1201, 19)
assert np.isfinite(trajectories[0]).all()
np.testing.assert_array_equal(*trajectories)
assert policies[0] == policies[1]
# Exercise circuit imports through both duplicated package paths as well.
a = importlib.import_module('control_public.anycar_nominal')
b = importlib.import_module('scripts.control_transfer.control_public.anycar_nominal')
command = dict(track_id='zigzag', start_fraction=0., speed=.85)
np.testing.assert_array_equal(a.train_rollout(a.DEFAULT, command, horizon=.2), b.train_rollout(b.DEFAULT, command, horizon=.2))
command = dict(track_id='silverstone', route_revision='compact-30s/1', start_fraction=0., speed=45/27.5)
np.testing.assert_array_equal(a.train_rollout(a.DEFAULT, command, horizon=.2), b.train_rollout(b.DEFAULT, command, horizon=.2))
assert not any(name.startswith('scripts.control_transfer.trusted') for name in sys.modules)
print(json.dumps({'shape': list(trajectories[0].shape), 'identical': True}))
"""
            result = subprocess.check_output(
                [sys.executable, "-I", "-c", program, str(app)], cwd=app, text=True, timeout=60
            )
            self.assertEqual(json.loads(result), {"shape": [1201, 19], "identical": True})

    def test_scoring_stationary_slow_reverse_shortcuts(self):
        c = dict(a=4.5, b=3.5, phase=0, direction=1)
        times = np.linspace(0, HORIZON, 1201)
        target = np.array([reference(t, c) for t in times])
        exact = np.zeros((len(times), 11))
        exact[:, :4] = target[:, :4]
        good = score_trajectory(exact, target, c)
        self.assertTrue(good["success"])
        self.assertGreater(good["score"], 95)
        stationary = np.tile(exact[0], (len(times), 1))
        stationary[:, 3] = 0
        self.assertEqual(score_trajectory(stationary, target, c)["score"], 0)
        slow = np.zeros_like(exact)
        slow[:, :4] = np.array([reference(t * 0.25, c)[:4] for t in times])
        slow[:, 3] *= 0.25
        score = score_trajectory(slow, target, c)
        self.assertFalse(score["success"])
        self.assertLess(score["score"], 10)
        reverse = exact[::-1].copy()
        self.assertEqual(score_trajectory(reverse, target, c)["score"], 0)
        shortcut = exact.copy()
        shortcut[:, :2] *= 0.5
        self.assertEqual(score_trajectory(shortcut, target, c)["score"], 0)
        for flag in ("collision", "body_contact", "rollover"):
            self.assertEqual(score_trajectory(exact, target, c, **{flag: True})["score"], 0)

    def test_tuner_depends_only_on_permitted_measurements(self):
        rows = []
        for t in np.arange(0, 10, 0.1):
            u = 0.12 * np.sin(t)
            values = [0.0] * 18
            values[17] = u
            values[10] = 0.9 * u + 0.01
            values[16] = 1
            values[6:10] = [20] * 4
            rows.append(dict(t=float(t), values=values))
        p, diagnosis = fit(DEFAULT, [dict(telemetry=rows)])
        self.assertAlmostEqual(p["steering_scale"], 1 / 0.9, places=5)
        self.assertAlmostEqual(p["drive_scale"], 1.25, places=5)
        self.assertTrue(diagnosis)
        again, _ = fit(p, [dict(telemetry=rows)])
        for name in ("drive_scale", "steering_scale", "steering_bias"):
            self.assertEqual(p[name], again[name])
        validate(p)

    def test_feedback_projection_excludes_private_data_and_rejects_extra_channels(self):
        rows = [dict(t=i * 0.1, values=[0.0] * 18) for i in range(241)]
        record = dict(feedback=dict(telemetry=rows), dynamics=dict(hidden_coefficient=123), metrics=dict(score=100))
        with tempfile.TemporaryDirectory() as folder:
            result = public_feedback(record, folder)
            self.assertEqual(set(result), {"telemetry", "images"})
            self.assertNotIn("hidden_coefficient", json.dumps(result))
            rows[0]["score"] = 100
            with self.assertRaises(ValueError):
                public_feedback(record, folder)
            del rows[0]["score"]
            rows[0]["values"].append(123)
            with self.assertRaises(ValueError):
                public_feedback(record, folder)


class PhysicsTests(unittest.TestCase):
    def vehicle(self, mu=0.8, plant=None):
        v = Vehicle(plant=plant, surfaces=[(-12, 12, mu)], command=dict(a=100, b=100, phase=0, direction=1))
        v.reset(0, 0, 0)
        return v

    def test_floor_priority_controls_actual_tire_contacts(self):
        for mu in (0.08, 0.8):
            v = self.vehicle(mu)
            actual = v.contact_friction()
            self.assertGreaterEqual(len(actual), 4)
            np.testing.assert_allclose(actual, mu, rtol=0, atol=1e-12)
            self.assertTrue(all(v.model.geom_priority[g] == 2 for g in v.surface_ids))

    def test_braking_distance_changes_with_contact_friction(self):
        distances = []
        for mu in (0.08, 0.8):
            v = self.vehicle(mu)
            v.data.qvel[0] = 3
            for n in ("fl", "fr", "bl", "br"):
                v.data.joint(n + "_spin").qvel[0] = 75
            for _ in range(50):
                v.advance([0, 0])
            distances.append(v.state()[0])
        self.assertGreater(distances[0], distances[1] * 1.4)

    def test_skidpad_changes_with_contact_friction(self):
        states = []
        for mu in (0.08, 0.8):
            v = self.vehicle(mu)
            for _ in range(150):
                v.advance([2, 0.25])
            states.append(v.state())
        self.assertGreater(np.linalg.norm(states[0][:2] - states[1][:2]), 0.5)

    def test_transport_delay_has_exact_command_hold(self):
        v = self.vehicle(plant=dict(NOMINAL, delay_steps=4))
        for _ in range(4):
            v.advance([1, 0.2])
            np.testing.assert_array_equal(v.applied, [0, 0])
        v.advance([1, 0.2])
        self.assertGreater(v.applied[0], 0)
        self.assertGreater(v.applied[1], 0)

    def test_mass_com_inertia_modify_real_model(self):
        v = self.vehicle()
        w = self.vehicle(plant=dict(NOMINAL, mass_scale=1.1, inertia_scale=0.9, com_x=0.01))
        self.assertAlmostEqual(w.model.body_mass[1] / v.model.body_mass[1], 1.1)
        np.testing.assert_allclose(w.model.body_inertia[1] / v.model.body_inertia[1], 0.99)
        self.assertAlmostEqual(w.model.body_ipos[1, 0] - v.model.body_ipos[1, 0], 0.01)


if __name__ == "__main__":
    unittest.main()
