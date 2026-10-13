"""G1 terrain geometry, fixed-plant banks, numeric ABI and observation boundary checks."""

import ast
import base64
import io
import json
from pathlib import Path
import sys
import unittest

import mujoco
import numpy as np

SRC = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SRC), str(SRC / "components")]
from control_public.g1 import validate
from control_public.weights import shapes, Network
from sim2realbench.g1.terrain import build_model, ground_height, make_spec, terrain_parameters
from sim2realbench.g1.assets import SCENE
from sim2realbench.g1.contract import JOINT_NAMES


def standing_policy():
    values = {name: np.zeros(shape, np.float32) for name, shape in shapes("g1").items()}
    values["std"][:] = 1
    stream = io.BytesIO()
    np.savez_compressed(stream, **values)
    return stream.getvalue()


class Contract(unittest.TestCase):
    def test_banks_are_disjoint_and_share_exactly_one_plant(self):
        a, b = make_spec(0), make_spec(1)
        for spec in [a, b]:
            self.assertEqual("control-transfer-instance/2", spec["schema"])
            self.assertEqual("same-plant", spec["transfer_track"])
            self.assertEqual(10000 + spec["index"] * 1000 + 100, spec["held_out"][0]["plant_seed"])
            self.assertEqual(12, len(spec["held_out"]))
            self.assertEqual(4, len(spec["adaptation"]))
            self.assertEqual({"flat", "slope", "rough", "steps"}, {c["terrain"] for c in spec["held_out"]})
            self.assertEqual(1, len({c["plant_seed"] for c in spec["adaptation"] + spec["held_out"]}))
            self.assertFalse(
                {c["episode_seed"] for c in spec["adaptation"]} & {c["episode_seed"] for c in spec["held_out"]}
            )
        self.assertNotEqual(a["held_out"][0]["plant_seed"], b["held_out"][0]["plant_seed"])

    def test_policy_rejects_executable_extra_fields_and_nonfinite_tensors(self):
        raw = standing_policy()
        payload = {"npz_base64": base64.b64encode(raw).decode()}
        self.assertEqual(raw, validate(payload))
        for invalid in [{**payload, "python": "pass"}, {"npz_base64": "not an archive"}, {"npz_base64": 1}]:
            with self.assertRaises(ValueError):
                validate(invalid)
        with np.load(io.BytesIO(raw)) as z:
            values = dict(z)
        values["w0"][0, 0] = np.nan
        stream = io.BytesIO()
        np.savez(stream, **values)
        with self.assertRaises(ValueError):
            validate({"npz_base64": base64.b64encode(stream.getvalue()).decode()})

    def test_command_blind_negative_ignores_command_and_gait_phase(self):
        import tempfile
        from sim2realbench.g1.validate_terrain import make_command_blind_policy

        rng = np.random.default_rng(5)
        values = {name: rng.normal(0, 0.01, shape).astype(np.float32) for name, shape in shapes("g1").items()}
        values["std"][:] = 1
        with tempfile.TemporaryDirectory() as folder:
            source, dest = Path(folder) / "source.npz", Path(folder) / "negative.npz"
            np.savez(source, **values)
            make_command_blind_policy(source, dest)
            original, negative = Network(source, "g1"), Network(dest, "g1")
            obs = rng.normal(0, 0.1, 98).astype(np.float32)
            zero_command = obs.copy()
            zero_command[6:11] = 0
            expected = original(zero_command)
            np.testing.assert_allclose(negative(obs), expected, rtol=1e-5, atol=1e-7)
            obs[6:11] = [0.8, 0.2, -0.5, 1, -1]
            np.testing.assert_allclose(negative(obs), expected, rtol=1e-5, atol=1e-7)

    def test_joint_abi_unchanged(self):
        abi = json.loads((SRC / "components/sim2realbench/g1/actuator_abi.json").read_text())
        self.assertEqual(JOINT_NAMES, abi["joint_names"].split(","))
        self.assertEqual((512, 98), shapes("g1")["w0"])
        self.assertEqual((29, 128), shapes("g1")["w3"])

    def test_public_training_never_imports_deployment(self):
        source = (SRC / "control_public/g1_training.py").read_text()
        modules = [n.module or "" for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any("trusted" in name or "sim2realbench" in name for name in modules))
        self.assertNotIn("plant_seed", source)
        self.assertNotIn("held_out", source)


@unittest.skipUnless(SCENE.exists(), "Set CONTROL_ASSETS to the prepared public robot assets")
class Geometry(unittest.TestCase):
    def test_real_collision_geometry_preserves_actuators_and_changes_height(self):
        for kind in ["flat", "slope", "rough", "steps"]:
            with self.subTest(kind=kind):
                cfg = terrain_parameters(kind, 0)
                model = build_model(SCENE, cfg)
                data = mujoco.MjData(model)
                mujoco.mj_forward(model, data)
                self.assertEqual(29, model.nu)
                self.assertEqual(36, model.nq)
                self.assertAlmostEqual(0, ground_height(model, data, 0, 0), places=6)
                if kind == "flat":
                    self.assertEqual(0, model.nhfield)
                elif kind == "slope":
                    plane = np.flatnonzero(model.geom_type == mujoco.mjtGeom.mjGEOM_PLANE)
                    self.assertTrue((model.geom_pos[plane, 2] < -0.05).all())
                    self.assertAlmostEqual(2 * cfg["slope"], ground_height(model, data, 3, 0), places=5)
                elif kind == "steps":
                    first = ground_height(model, data, 1 + cfg["step_width"] * 0.5, 0)
                    self.assertAlmostEqual(cfg["step_height"], first, places=6)
                    self.assertEqual(6, sum(model.geom_group == 5) - 1)
                else:
                    self.assertEqual(1, model.nhfield)
                    heights = [ground_height(model, data, x, 0) for x in np.linspace(2, 7, 100)]
                    self.assertGreater(np.ptp(heights), 0.005)
                    self.assertLessEqual(np.max(np.abs(heights)), cfg["rough_amplitude"])

    def test_deterministic_terrain_and_varied_episode_geometry(self):
        a = build_model(SCENE, terrain_parameters("rough", 7))
        b = build_model(SCENE, terrain_parameters("rough", 7))
        c = build_model(SCENE, terrain_parameters("rough", 8))
        np.testing.assert_array_equal(a.hfield_data, b.hfield_data)
        self.assertFalse(np.array_equal(a.hfield_data, c.hfield_data))


if __name__ == "__main__":
    unittest.main()
