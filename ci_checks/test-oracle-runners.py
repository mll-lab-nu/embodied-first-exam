#!/usr/bin/env python3
"""Oracle success/stop contracts and relocated CLIs; no new physics execution."""
import ast
from copy import deepcopy
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.oracle_runners.run_lock_picking_policy import finish_run, run_segments
from scripts.test_policy_cube_transfer import snapshot
from topogym.planning.lock_picking.robot_audit import completion_errors, recompute_task_tick

spec = importlib.util.spec_from_file_location("lock_terminal_fixtures", ROOT / "ci_checks/test-lock-picking-terminal.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

RUNNERS = (
    "run_buzz_wire_policy", "run_cast_coil_policy", "run_cast_keyhole_policy",
    "run_hedgehog_oracle", "run_hedgehog_policy", "run_horseshoe_policy",
    "run_interlocked_claws_policy", "run_lock_picking_policy",
    "run_rigid_reference_policy", "run_solvability_workflow",
    "run_blanket_oracle",
    "run_knot_oracle", "run_knot_branching",
)


class RecordedTerminalRunner:
    """Use actual Lock predicates on synthetic measured poses, without an engine."""
    def __init__(self, *, tier="easy", reason="env_terminal", ticks=6,
                 failure=False, incomplete=False, success_on_pickup=False):
        task, self.state = fixtures.fixture(tier, offset=.001)
        self.state["assist_active"] = True
        self.state["bodies"]["lock_key"].update(linear_velocity_m_s=[0., 0., 0.],
                                              angular_velocity_rad_s=[0., 0., 0.])
        task.initialize(self.state)
        self.env = SimpleNamespace(_task=task, _world=SimpleNamespace(physics_step=0))
        self.reason, self.ticks, self.failure, self.incomplete = reason, ticks, failure, incomplete
        self.success_on_pickup = success_on_pickup
        self.calls = []

    def run_policy(self, *, request_id, policy, **kwargs):
        self.calls.append(request_id)
        if request_id == "lock-pickup" and not self.success_on_pickup:
            policy.completed = True
            return dict(reason="policy_done", evidence_complete=True, physics_tick_complete=True)
        if self.failure:
            self.state["articulations"]["lock_disc_0"]["joints"]["disc_hinge"]["position"] = [.4]
        for step in range(1, self.ticks + 1):
            self.state["physics_step"] = self.env._world.physics_step = step
            self.env._task.update(self.state, .1)
            if self.env._task.result.terminated:
                break
        return dict(reason=self.reason, evidence_complete=not self.incomplete,
                    physics_tick_complete=not self.incomplete)


def execute(runner, part="solve"):
    report = dict(segments=[], status="running", completion_contract="task_success" if part == "solve" else "pickup")
    def factory(name):
        return SimpleNamespace(phase=name, completed=False), "synthetic-submission"
    run_segments(runner, part=part, policy_factory=factory, report=report, save_report=lambda: None)
    finish_run(runner.env._task, runner.state, part=part, report=report)
    return report


class LockRunnerTests(unittest.TestCase):
    def test_native_success_stops_without_release_in_all_tiers(self):
        for tier in ("easy", "medium", "hard"):
            with self.subTest(tier=tier):
                runner = RecordedTerminalRunner(tier=tier)
                report = execute(runner)
                self.assertEqual(report["status"], "task_success")
                self.assertTrue(report["task_success"])
                self.assertFalse(report["policy_completed"])
                self.assertFalse(report["released_at_end"])
                self.assertFalse(report["independent_goal_check"]["resting_insertion_observed"])
                self.assertEqual(runner.calls, ["lock-pickup", "lock-solve"])
                self.assertEqual(runner.env._world.physics_step, 6)

    def test_does_not_start_another_segment_after_terminal_success(self):
        runner = RecordedTerminalRunner(success_on_pickup=True)
        self.assertTrue(execute(runner)["task_success"])
        self.assertEqual(runner.calls, ["lock-pickup"])

    def test_terminal_failure_is_not_success(self):
        runner = RecordedTerminalRunner(failure=True)
        with self.assertRaisesRegex(RuntimeError, "without success"):
            execute(runner)
        self.assertTrue(runner.env._task.result.terminated)
        self.assertFalse(runner.env._task.result.task_success)

    def test_time_limit_and_execution_errors_still_fail(self):
        for reason in ("env_time_limit", "policy_error", "evidence_error"):
            with self.subTest(reason=reason), self.assertRaisesRegex(RuntimeError, reason):
                execute(RecordedTerminalRunner(reason=reason))

    def test_incomplete_evidence_cannot_pass_even_if_the_task_succeeded(self):
        with self.assertRaisesRegex(RuntimeError, "evidence is incomplete"):
            execute(RecordedTerminalRunner(incomplete=True))

    def test_policy_done_and_raw_goal_do_not_replace_the_stability_window(self):
        runner = RecordedTerminalRunner(reason="policy_done", ticks=3)
        with self.assertRaisesRegex(RuntimeError, "without confirmed Task success"):
            execute(runner)
        self.assertTrue(runner.env._task.evaluate_state(runner.state)[0])
        self.assertFalse(runner.env._task.result.task_success)

    def test_partial_pickup_does_not_claim_a_solved_task(self):
        report = execute(RecordedTerminalRunner(), part="pickup")
        self.assertEqual(report["status"], "pickup_passed")
        self.assertFalse(report["task_success"])

    def test_released_poses_still_finish_after_native_success(self):
        runner = RecordedTerminalRunner()
        runner.state["assist_active"] = False
        report = execute(runner)
        self.assertEqual(report["status"], "task_success")
        self.assertTrue(report["independent_goal_check"]["resting_insertion_observed"])


class CompletionAuditTests(unittest.TestCase):
    phases = {"close_and_wait_for_automatic_assist", "lift_to_lock_axis", "insert_third_disc",
              "open_for_supported_regrasp", "close_for_automatic_regrasp", "insert_endpoint"}
    events = ["acquired", "released", "acquired"]
    report = dict(completion_contract="task_success", status="task_success", task_result=dict(task_success=True))

    def check_completion(self, report=None, phases=None, events=None, **kwargs):
        options = dict(retreats=2, expected=2, released_completion=False, native_success=True)
        options.update(kwargs)
        return completion_errors(self.report if report is None else report,
            self.phases if phases is None else phases, self.events if events is None else events, **options)

    def test_native_success_does_not_require_final_release(self):
        self.assertEqual(self.check_completion(), [])
        self.assertEqual(self.check_completion(events=self.events+["released"]), [])

    def test_still_requires_recomputed_success_and_robot_process(self):
        for kwargs in (dict(native_success=False), dict(retreats=1),
                       dict(phases=self.phases-{"insert_third_disc"}), dict(events=["acquired"])):
            with self.subTest(kwargs=kwargs):
                self.assertTrue(self.check_completion(**kwargs))
        bad = deepcopy(self.report)
        bad["task_result"]["task_success"] = False
        self.assertTrue(self.check_completion(report=bad))

    def test_legacy_report_keeps_original_release_acceptance(self):
        old = dict(status="route_completed", task_result=dict(task_success=False))
        self.assertTrue(self.check_completion(report=old))
        self.assertEqual(self.check_completion(report=old, released_completion=True, native_success=False,
            phases=self.phases | {"release_at_goal", "withdraw_gripper", "verify_stable_insertion"},
            events=self.events+["released"]), [])

    def test_audit_recomputes_stable_success_and_rejects_forged_flags(self):
        for tier in ("easy", "medium", "hard"):
            with self.subTest(tier=tier):
                task, world = fixtures.fixture(tier, offset=.001)
                for tick in range(7):
                    world["physics_step"] = tick
                    saved = dict(task_success=tick == 6, terminated=tick == 6)
                    self.assertEqual(recompute_task_tick(task, world, saved, .1), [])
                self.assertTrue(task.result.task_success)
                world["physics_step"] = 7
                self.assertIn("continued after Task termination", recompute_task_tick(task, world, saved, .1)[0])
        task, world = fixtures.fixture()
        fake = dict(task_success=True, terminated=True)
        self.assertTrue(recompute_task_tick(task, world, fake, .1))
        self.assertFalse(task.result.task_success)

    def test_audit_rejects_success_claim_before_confirmation_window(self):
        task, world = fixtures.fixture()
        for tick in range(3):
            world["physics_step"] = tick
            self.assertEqual(recompute_task_tick(task, world, dict(task_success=False, terminated=False), .1), [])
        # An early claimed success still fails when only 0.2 s has elapsed.
        world["physics_step"] = 3
        self.assertTrue(recompute_task_tick(task, world, dict(task_success=True, terminated=True), .1))
        self.assertFalse(task.result.task_success)


class RunnerMigrationTests(unittest.TestCase):
    def test_all_modules_import_from_the_runner_directory(self):
        for name in RUNNERS:
            with self.subTest(runner=name):
                module = importlib.import_module("scripts.oracle_runners."+name)
                self.assertEqual(module.ROOT, ROOT)
                self.assertFalse((ROOT / "scripts" / (name+".py")).exists())

    def test_every_cli_help_works_from_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as cwd:
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            for name in RUNNERS:
                with self.subTest(runner=name):
                    result = subprocess.run([sys.executable, str(ROOT / "scripts/oracle_runners" / (name+".py")), "--help"],
                        cwd=cwd, env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                    self.assertIn("--output", result.stdout)

    def test_source_snapshot_contains_all_relocated_worker_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture, output = Path(folder)/"repo", Path(folder)/"run"
            output.mkdir()
            target = fixture / "scripts/oracle_runners"
            target.mkdir(parents=True)
            for path in (ROOT / "scripts/oracle_runners").glob("*.py"):
                shutil.copy2(path, target/path.name)
            with patch("scripts.test_policy_cube_transfer.ROOT", fixture):
                source = snapshot(output)
            manifest = json.loads((output / "source_manifest.json").read_text())
            for name in RUNNERS:
                rel = "scripts/oracle_runners/"+name+".py"
                self.assertIn(rel, manifest)
                self.assertEqual((source / rel).read_bytes(), (ROOT / rel).read_bytes())
                module = ast.parse((source / rel).read_text())
                workers = [n.value for n in ast.walk(module) if isinstance(n, ast.Constant)
                           and isinstance(n.value, str) and n.value.startswith("scripts/") and n.value.endswith(".py")]
                for worker in workers:
                    self.assertTrue((source / worker).is_file(), worker)
                if name not in {"run_hedgehog_policy", "run_interlocked_claws_policy", "run_knot_oracle", "run_knot_branching"}:
                    self.assertIn(rel, workers)


if __name__ == "__main__":
    unittest.main()
