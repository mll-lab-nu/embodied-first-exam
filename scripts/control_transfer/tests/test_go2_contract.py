"""Go2 numeric boundary and task semantics; no GPU or asset dependency."""

import json
import os
import unittest
import tempfile
from pathlib import Path

os.environ["MUJOCO_GL"] = "osmesa"

import numpy as np

from scripts.control_transfer.control_public.go2 import (
    CHANNELS,
    Controller,
    default_policy,
    forward_leg,
    inverse_leg,
    validate,
)
from scripts.control_transfer.trusted.go2 import make_spec
from scripts.control_transfer.components.quadrupedbench.simulation import (
    command,
    episode,
    jump_metrics,
    parameters,
    score,
)


def samples(task, airborne=False, dx=0.85, yaw=2.2):
    states = []
    for i in range(301):
        t = i * 0.02
        phase = np.clip((t - 1.8) / 0.4, 0, 1)
        flight = airborne and 1.8 < t < 2.2
        z = 0.32 + (0.12 * np.sin(np.pi * phase) if flight else 0)
        states.append(
            dict(
                t=t,
                xyz=[float(dx * phase) if task == "forward-jump" else 0.0, 0.0, float(z)],
                rpy=[0, 0, float(yaw * phase)],
                yaw_unwrapped=float(yaw * phase),
                velocity=[0, 0, 0],
                omega=[0, 0, 0],
                ground_contacts=0 if flight else 4,
                feet_contacts=0 if flight else 4,
                bad_contact=False,
                command=[0] * 7,
            )
        )
    return states


class Contract(unittest.TestCase):
    def test_canonical_numeric_roundtrip(self):
        p = default_policy()
        raw = validate(p)
        self.assertEqual(raw, validate(json.loads(raw)))
        self.assertLess(len(raw), 65536)

    def test_rejects_code_extra_keys_nonfinite_and_wrong_shapes(self):
        changes = [
            ("kp", [True] * 12),
            ("kd", [float("nan")] * 12),
            ("joint_bias", [0] * 13),
            ("trajectory", [[0] * 12] * 18),
            ("feedback", [[0] * 7] * 12),
            ("enabled", 1),
            ("schema", "pickle"),
        ]
        for k, v in changes:
            p = default_policy()
            p[k] = v
            with self.subTest(k=k), self.assertRaises(ValueError):
                validate(p)
        p = default_policy()
        p["python"] = "import os"
        with self.assertRaises(ValueError):
            validate(p)
        p = default_policy()
        p["parameters"]["height"] = float("inf")
        with self.assertRaises(ValueError):
            validate(p)

    def test_oversized_policy_file_rejected_before_json_parse(self):
        from scripts.control_transfer.trusted.go2 import rollout

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oversized.json"
            path.write_bytes(b" " * 65537)
            with self.assertRaisesRegex(ValueError, "Policy size limit"):
                rollout(path, {}, Path(tmp) / "out", False)
            self.assertFalse((Path(tmp) / "out").exists())

    def test_named_kinematics_roundtrip(self):
        for side in (-1, 1):
            for q in ([0.1, 0.8, -1.5], [-0.15, 1.1, -2.0]):
                np.testing.assert_allclose(inverse_leg(forward_leg(q, side), side), q, atol=1e-10)

    def test_persistent_plant_disjoint_episode_banks(self):
        for task in ("weave", "attitude", "forward-jump", "yaw-jump"):
            s = make_spec(2, task)
            a, b = s["bank"]["adaptation"], s["bank"]["held_out"]
            self.assertEqual((len(a), len(b)), (3, 10))
            self.assertEqual(s["schema"], "control-transfer-instance/2")
            self.assertEqual(s["transfer_track"], "same-plant")
            self.assertEqual({c["plant_seed"] for c in a + b}, {12100})
            self.assertEqual([c["episode_seed"] for c in a], list(range(12000, 12003)))
            self.assertEqual([c["episode_seed"] for c in b], list(range(12300, 12310)))
            self.assertFalse({c["episode_seed"] for c in a} & {c["episode_seed"] for c in b})
            self.assertEqual(parameters(a[0]["plant_seed"]), parameters(b[-1]["plant_seed"]))
            self.assertNotEqual(
                parameters(a[0]["plant_seed"]), parameters(make_spec(3, task)["bank"]["adaptation"][0]["plant_seed"])
            )

    def test_public_spec_has_no_privileged_values(self):
        text = json.dumps(make_spec(0, "weave")["public"])
        for key in ("plant_seed", "episode_seed", "base_mass_scale", "base_com_shift", "motor_tau", "/opt/"):
            self.assertNotIn(key, text)
        self.assertEqual(len(CHANNELS), 37)
        self.assertNotIn("base_x", CHANNELS)
        self.assertNotIn("reward", CHANNELS)

    def test_controller_sensor_only_signature_and_finite_limits(self):
        c = Controller(default_policy())
        obs = np.r_[np.tile([0, 0.9, -1.8], 4), np.zeros(18)]
        for task in ("weave", "attitude", "forward-jump", "yaw-jump"):
            spec = episode(make_spec(0, task)["bank"]["adaptation"][0])
            for t in (0, 1.5, 1.8, 2.1, 4):
                q, ff = c.targets(t, task, obs, command(t, spec))
                self.assertEqual(q.shape, (12,))
                self.assertTrue(np.isfinite(q).all())
                self.assertTrue(np.isfinite(ff).all())

    def test_walking_to_jump_goal_cannot_pass(self):
        s = samples("forward-jump", False)
        spec = {"task": "forward-jump", "duration": 6, "distance": 0.85}
        r = score(s, spec)
        self.assertFalse(r["success"])
        self.assertFalse(r["flight_detected"])
        self.assertEqual(r["score"], 0)

    def test_ground_spin_cannot_pass_yaw_jump(self):
        r = score(samples("yaw-jump", False), dict(task="yaw-jump", duration=6, yaw=2.2))
        self.assertFalse(r["success"])
        self.assertEqual(r["score"], 0)

    def test_real_flight_and_stable_landing_positive_predicate(self):
        for task in ("forward-jump", "yaw-jump"):
            r = score(samples(task, True), dict(task=task, duration=6, distance=0.85, yaw=2.2))
            self.assertTrue(r["success"], r)
            self.assertGreaterEqual(r["airtime_s"], 0.08)

    def test_hop_then_walk_or_ground_turn_rejected(self):
        for task in ("forward-jump", "yaw-jump"):
            s = samples(task, True, dx=0, yaw=0)
            for state in s:
                if state["t"] > 3:
                    state["xyz"][0] = 0.85 if task == "forward-jump" else 0
                    state["yaw_unwrapped"] = 2.2 if task == "yaw-jump" else 0
            r = score(s, dict(task=task, duration=6, distance=0.85, yaw=2.2))
            self.assertFalse(r["success"])

    def test_collision_and_unstable_touchdown_rejected(self):
        s = samples("forward-jump", True)
        s[150]["bad_contact"] = True
        self.assertEqual(score(s, dict(task="forward-jump", duration=6, distance=0.85))["score"], 0)
        s = samples("forward-jump", True)
        s[-1]["velocity"] = [2, 0, 0]
        self.assertFalse(score(s, dict(task="forward-jump", duration=6, distance=0.85))["success"])

    def test_tiny_contact_dropout_not_a_jump(self):
        s = samples("forward-jump", True)
        for state in s:
            state["xyz"][2] = 0.32
        self.assertFalse(jump_metrics(s, dict(task="forward-jump", distance=0.85))["flight_detected"])


if __name__ == "__main__":
    unittest.main()
