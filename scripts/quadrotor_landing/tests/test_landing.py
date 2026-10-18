import copy
from functools import wraps
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from scripts.quadrotor_landing.public.policy import Controller, DEFAULT, validate
from scripts.quadrotor_landing.public.model import HORIZON, TASK_VERSION, SCORE_VERSION, sample_task
from scripts.quadrotor_landing.trusted.residual import Residual
from scripts.quadrotor_landing.reference.train import fit
from scripts.quadrotor_landing.trusted.grade import grade
from scripts.quadrotor_landing.trusted.server import parse
from scripts.quadrotor_landing.trusted.session import Session, public_feedback
from scripts.quadrotor_landing.trusted.simulation import rollout
from scripts.quadrotor_landing.trusted.scoring import SettlingTimer, score_metrics, full_credit_time
from scripts.quadrotor_landing.trusted.oracle import prepare_bank, load_bank

ASSET = os.environ.get("LANDING_TEST_RESIDUAL")


def mock_oracle_for_session_lifecycle(fn):
    """Lifecycle unit tests do not repeat nonlinear optimization. Separate tests
    below exercise actual oracle preparation, hash checks, and simulator replay.
    """

    @wraps(fn)
    def wrapped(*args, **kwargs):
        def refs(bank, *_):
            return {split: [{"oracle_time_s": 6.0} for _ in cases] for split, cases in bank.items()}

        with (
            patch("scripts.quadrotor_landing.trusted.session.prepare_bank", return_value="unit-test-only"),
            patch("scripts.quadrotor_landing.trusted.session.load_bank", side_effect=refs),
        ):
            return fn(*args, **kwargs)

    return wrapped


class InterfaceTests(unittest.TestCase):
    def test_policy_rejects_executable_and_nonfinite_inputs(self):
        for change in [
            {"path": "/data/state.json"},
            {"kp_z": float("nan")},
            {"kp_z": True},
            {"residual_coefficients": [0] * 6},
            {"residual_coefficients": [float("inf")] * 5},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate({**DEFAULT, **change})
        with self.assertRaises(ValueError):
            parse(b'{"x":1,"x":2}')
        with self.assertRaises(ValueError):
            parse(b'{"x":NaN}')

    def test_no_privileged_fields_can_be_added_to_feedback(self):
        with self.assertRaises(ValueError):
            public_feedback(
                {"schema": "landing-feedback/2", "observations": [], "frames": [], "force_z": 3.0}, Path(".")
            )
        with self.assertRaises(ValueError):
            public_feedback(
                {
                    "schema": "landing-feedback/2",
                    "observations": [],
                    "frames": [{"time_s": 0.0, "name": "../state.json"}],
                },
                Path("."),
            )

    def test_nominal_lands_and_do_nothing_fails(self):
        _, good = rollout(seed=71, reference_time_s=6.0)
        self.assertTrue(good["metrics"]["success"])
        with patch.object(Controller, "act", return_value=np.zeros(4)):
            _, bad = rollout(seed=71, reference_time_s=6.0)
        self.assertFalse(bad["metrics"]["success"])
        self.assertGreater(bad["metrics"]["impact_speed_m_s"], 0.4)
        self.assertEqual(bad["metrics"]["score"], 0.0)
        self.assertIsNone(bad["metrics"]["completion_time_s"])
        self.assertLess(bad["metrics"]["touchdown_time_s"], good["metrics"]["touchdown_time_s"])

    def test_random_start_and_fixed_pad_are_distinct_and_reproducible(self):
        first = []
        for seed in range(200):
            start, pad = sample_task(np.random.default_rng(seed))
            again = sample_task(np.random.default_rng(seed))
            np.testing.assert_array_equal(start, again[0])
            np.testing.assert_array_equal(pad, again[1])
            self.assertTrue(np.all(np.abs(start[:2]) <= 1))
            self.assertTrue(np.all(np.abs(pad[:2]) <= 1))
            self.assertTrue(0.8 <= start[2] <= 1.5)
            self.assertGreaterEqual(np.linalg.norm(start[:2] - pad[:2]), 0.5)
            first.append(pad[:2])
        self.assertTrue(np.all(np.ptp(first, axis=0) > 1.8))

    def test_cross_arena_landing_and_wrong_pad_rejection(self):
        start, pad = [-1, 1, 1.5], [1, -1, 0]
        public, good = rollout(seed=9, initial_position=start, pad_position=pad, reference_time_s=6.0)
        self.assertTrue(good["metrics"]["success"])
        self.assertLess(good["metrics"]["final_xy_error_m"], 0.15)
        self.assertTrue(all(o["pad_position"] == pad for o in public["observations"]))
        act = Controller.act

        def origin_target(controller, obs, oracle_force=None):
            return act(controller, {**obs, "pad_position": [0, 0, 0]}, oracle_force)

        with patch.object(Controller, "act", origin_target):
            _, wrong = rollout(seed=9, initial_position=start, pad_position=pad, reference_time_s=6.0)
        self.assertFalse(wrong["metrics"]["success"])
        self.assertTrue(wrong["metrics"]["off_pad_contact"])
        self.assertEqual(wrong["metrics"]["score"], 0.0)
        self.assertGreater(wrong["metrics"]["final_xy_error_m"], 1.0)


class ScoringTests(unittest.TestCase):
    def test_stability_loss_cancels_early_completion(self):
        timer = SettlingTimer()
        for _ in range(100):
            timer.update(True)
        self.assertIsNone(timer.completion_time_s)
        timer.update(True)
        self.assertEqual(timer.completion_time_s, 1.01)
        for _ in range(50):
            timer.update(True)
        self.assertEqual(timer.completion_time_s, 1.01)
        timer.update(False)  # Takeoff or instability after an early stable landing.
        self.assertIsNone(timer.completion_time_s)
        self.assertEqual(timer.duration_s, 0.0)
        for _ in range(100):
            timer.update(True)
        self.assertIsNone(timer.completion_time_s)
        timer.update(True)
        self.assertEqual(timer.completion_time_s, 2.53)
        self.assertEqual(timer.duration_s, 1.0)
        boundary = SettlingTimer()
        for _ in range(1499):
            boundary.update(False)
        for _ in range(100):
            boundary.update(True)
        self.assertIsNone(boundary.completion_time_s)
        boundary.update(True)
        self.assertEqual(boundary.completion_time_s, HORIZON)

    def test_score_deadline_safety_and_invalid_completion(self):
        reference = 6.0
        threshold = full_credit_time(reference)
        self.assertAlmostEqual(threshold, 6.6)
        for t in (5.0, reference, threshold):
            self.assertEqual(score_metrics(True, t, reference)["score"], 100.0)
        self.assertLess(score_metrics(True, threshold + 0.01, reference)["score"], 100.0)
        self.assertEqual(score_metrics(True, HORIZON, reference)["score"], 60.0)
        for t in (6.0, 10.0, 14.0, 16.0):
            failed = score_metrics(False, t, reference)
            self.assertEqual(failed["score"], 0.0)
            self.assertEqual(failed["time_bonus_points"], 0.0)
            self.assertIsNone(failed["completion_time_s"])
        for invalid in [None, float("nan"), float("inf"), 0.99, 16.01]:
            with self.subTest(time=invalid), self.assertRaises(ValueError):
                score_metrics(True, invalid, reference)
        for invalid in [None, True, float("nan"), 0.0, 15.0, 16.0]:
            for success in (True, False):
                with self.subTest(reference=invalid, success=success), self.assertRaises(ValueError):
                    score_metrics(success, 10.0, invalid)
        self.assertGreater(score_metrics(True, 10.0, 8.0)["score"], score_metrics(True, 10.0, 6.0)["score"])

    def test_faster_safe_policy_beats_slow_safe_policy(self):
        results = []
        for approach, descent in [(2.0, 4.0), (4.0, 6.0), (5.0, 9.0)]:
            _, record = rollout(
                {**DEFAULT, "approach_s": approach, "descent_s": descent}, seed=71, reference_time_s=5.0
            )
            metrics = record["metrics"]
            self.assertTrue(metrics["success"])
            self.assertEqual(record["score_version"], SCORE_VERSION)
            self.assertGreaterEqual(metrics["completion_time_s"], metrics["touchdown_time_s"] + 1.0)
            results.append(metrics)
        self.assertLess(results[0]["completion_time_s"], results[1]["completion_time_s"])
        self.assertLess(results[1]["completion_time_s"], results[2]["completion_time_s"])
        self.assertGreater(results[0]["score"], results[1]["score"])
        self.assertGreater(results[1]["score"], results[2]["score"])


@unittest.skipUnless(ASSET, "Set LANDING_TEST_RESIDUAL to an operator-prepared residual.npz")
class ResidualTests(unittest.TestCase):
    def test_full_residual_uses_velocity_attitude_rpm_and_quaternion_convention(self):
        plant = Residual(ASSET)
        p, v, q, rpm = [0.3, 0.7, 0.5], [0, 0, 0], [1, 0, 0, 0], [6508] * 4
        base = plant.force(p, v, q, rpm)
        self.assertEqual(base.shape, (3,))
        self.assertGreater(np.linalg.norm(base[:2]), 0.1)
        np.testing.assert_array_equal(base, plant.force(p, v, [-1, 0, 0, 0], rpm))
        np.testing.assert_array_equal(base, plant.force([-0.8, 0.9, 0.5], v, q, rpm))
        for vel, quat, motors in [([0.5, -0.2, 0], q, rpm), (v, [0.995, 0.1, 0, 0], rpm), (v, q, [5500] * 4)]:
            self.assertGreater(np.linalg.norm(base - plant.force(p, vel, quat, motors)), 1e-4)

    def test_mismatch_oracle_and_three_feedback_rounds(self):
        policy = copy.deepcopy(DEFAULT)
        feedbacks = []
        heights = []
        for i in range(3):
            public, private = rollout(policy, residual_path=ASSET, seed=71, reference_time_s=6.0)
            feedbacks.append(public)
            heights.append(private["metrics"]["final_clearance_m"])
            if i == 0:
                self.assertFalse(private["metrics"]["success"])
                self.assertEqual(private["metrics"]["score"], 0.0)
            if i < 2:
                policy, _ = fit(feedbacks, policy)
        self.assertGreater(heights[0], heights[1])
        self.assertLess(heights[2], 0.01)
        self.assertTrue(private["metrics"]["success"])
        _, oracle = rollout({**DEFAULT, "approach_s": 2.0, "descent_s": 4.0}, residual_path=ASSET, seed=71, oracle=True)
        self.assertTrue(oracle["metrics"]["success"])

    def test_seeded_observations_and_render_independence(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = rollout(residual_path=ASSET, seed=83, out=Path(d) / "rendered", render=True, reference_time_s=6.0)
            c, e = rollout(residual_path=ASSET, seed=83, reference_time_s=6.0)
            self.assertEqual(a["observations"], c["observations"])
            self.assertEqual(b, e)
            self.assertEqual(len(a["frames"]), int(HORIZON))
            view = public_feedback(a, Path(d) / "rendered")
            self.assertEqual(set(view), {"observations", "images"})
            for forbidden in (
                "residual_force_world_N",
                "residual_scale",
                "seed",
                "contact",
                "metrics",
                "trajectory",
                "initial_position",
                "completion_time_s",
                "score",
                "success_points",
                "time_bonus_points",
                "oracle_reference_time_s",
                "full_credit_time_s",
            ):
                self.assertNotIn('"' + forbidden + '"', json.dumps(view))
            self.assertEqual(len(view["observations"]), int(HORIZON * 20))

    def test_oracle_uses_exact_state_despite_corrupted_measurements(self):
        from scripts.quadrotor_landing.trusted import simulation

        policy = {**DEFAULT, "approach_s": 2.0, "descent_s": 4.0}
        _, clean = rollout(policy, residual_path=ASSET, seed=71, oracle=True)
        original = simulation.observation

        def corrupt(*args):
            obs = original(*args)
            return {
                **obs,
                "position": [100.0] * 3,
                "velocity": [100.0] * 3,
                "omega": [100.0] * 3,
                "quaternion": [0, 1, 0, 0],
                "rotor_rpm": [0.0] * 4,
            }

        with patch.object(simulation, "observation", side_effect=corrupt):
            public, corrupted = rollout(policy, residual_path=ASSET, seed=71, oracle=True)
        self.assertEqual(clean, corrupted)
        self.assertTrue(clean["metrics"]["success"])
        self.assertIsNone(clean["metrics"]["score"])  # Ungraded diagnostic, no hardcoded reference.
        self.assertEqual(public["observations"][0]["position"], [100.0] * 3)

    def test_real_oracle_bank_replay_and_tamper_rejection(self):
        from scripts.quadrotor_landing.trusted import oracle

        small = {"population": 5, "generations": 0, "polish_steps": [], "seed": 0}
        bank = {"adaptation": [{"seed": 71, "scale": 1.0}], "held_out": [{"seed": 101, "scale": 1.0}]}
        with tempfile.TemporaryDirectory() as d, patch.object(oracle, "SEARCH", small):
            root = Path(d) / "oracle"
            signature = prepare_bank(bank, ASSET, root, workers=2)
            refs = load_bank(bank, ASSET, root, signature)
            ref = refs["adaptation"][0]
            self.assertTrue(ref["replay_verified"])
            self.assertFalse(ref["global_optimality_certified"])
            self.assertIsNone(ref["optimality_gap_s"])
            self.assertEqual(score_metrics(True, ref["oracle_time_s"], ref["oracle_time_s"])["score"], 100.0)
            with self.assertRaisesRegex(ValueError, "stale"):
                load_bank({**bank, "held_out": [{"seed": 999, "scale": 1.0}]}, ASSET, root, signature)
            with patch.object(oracle, "SEARCH", {**small, "generations": 1}):
                with self.assertRaisesRegex(ValueError, "stale"):
                    load_bank(bank, ASSET, root, signature)
            path = root / "adaptation-0/policy.json"
            original = path.read_bytes()
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "evidence changed"):
                load_bank(bank, ASSET, root, signature)
            path.write_bytes(original)
            replay = root / "held_out-0/replay-0/record.json"
            original = replay.read_bytes()
            replay.write_text("{}")
            with self.assertRaisesRegex(ValueError, "replay changed"):
                load_bank(bank, ASSET, root, signature)
            replay.write_bytes(original)
            path = root / "bank.json"
            manifest = json.loads(path.read_text())
            manifest["references"]["adaptation"][0]["oracle_time_s"] += 1
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "bank changed"):
                load_bank(bank, ASSET, root, signature)

    @mock_oracle_for_session_lifecycle
    def test_budgets_restart_seal_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "session"
            bank = {"adaptation": [{"seed": 71, "scale": 1.0}], "held_out": [{"seed": 101, "scale": 1.0}]}
            s = Session(root, ASSET, bank=bank, render=False)
            description = s.call("describe", {})
            self.assertEqual(description["task_version"], TASK_VERSION)
            self.assertEqual(description["scoring"]["version"], SCORE_VERSION)
            self.assertIn("error", s.call("state", {}))
            for i in range(3):
                self.assertNotIn("error", s.call("deploy", {"policy": DEFAULT, "diagnosis": "test"}))
            s = Session(root, ASSET, render=False)
            self.assertEqual(s.call("describe", {})["rounds_remaining"], 0)
            self.assertIn("error", s.call("deploy", {"policy": DEFAULT, "diagnosis": "test"}))
            self.assertIn("error", s.call("seal", {"round_id": "../state.json", "summary": ""}))
            self.assertTrue(s.call("seal", {"round_id": "round-3", "summary": "test"})["sealed"])
            self.assertIn("error", s.call("deploy", {"policy": DEFAULT, "diagnosis": "test"}))
            s = Session(root, ASSET, render=False)
            self.assertIn("error", s.call("describe", {}))
            (root / "round-3/policy.json").write_text(json.dumps({**DEFAULT, "kp_z": 2.0}))
            with self.assertRaisesRegex(ValueError, "policy changed"):
                grade(root, ASSET, render=False)

    @mock_oracle_for_session_lifecycle
    def test_binary_score_session_cannot_resume_or_be_regraded(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "session"
            session = Session(root, ASSET, render=False)
            session.state["task_version"] = "random-pad-landing/3"
            session.persist()
            with self.assertRaisesRegex(ValueError, "task version changed"):
                Session(root, ASSET, render=False)
            with self.assertRaisesRegex(ValueError, "Task version changed"):
                grade(root, ASSET, render=False)

    @mock_oracle_for_session_lifecycle
    def test_crash_charges_round_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "session"
            s = Session(root, ASSET, render=False)
            with patch("scripts.quadrotor_landing.trusted.session.rollout", side_effect=RuntimeError("crash")):
                with self.assertRaises(RuntimeError):
                    s.call("deploy", {"policy": DEFAULT, "diagnosis": "test"})
            resumed = Session(root, ASSET, render=False)
            self.assertEqual(len(resumed.state["rounds"]), 1)
            self.assertTrue(resumed.state["infrastructure_error"])
            self.assertIn("error", resumed.call("deploy", {"policy": DEFAULT, "diagnosis": "retry"}))


if __name__ == "__main__":
    unittest.main()
