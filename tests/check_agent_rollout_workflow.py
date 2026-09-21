"""Offline checks for operator scripts: frozen inputs, credentials and exit status."""
import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests import agent_rollout_workflow as workflow


class WorkflowChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="topogym-workflow-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def prepare(self, name="run with spaces", *options):
        root = self.root / name
        args = workflow.parser().parse_args([
            "prepare", "--output", str(root), "--task", "counter", "--model", "test-model", *options])
        with redirect_stdout(io.StringIO()):
            workflow.prepare_run(args)
        return root

    def test_shared_suite_and_no_overwrite(self):
        root = self.prepare("first", "--variants", "2", "--access-mode", "both", "--repeats", "3")
        settings = workflow.load_run(root)
        self.assertEqual(settings["expected_trials"], 12)
        agents = workflow.read_json(root / "agents.json")
        self.assertEqual([a["reset_policy"] for a in agents], ["disabled", "same_preset"])
        original = (root / "presets/suite.json").read_bytes()
        second = self.prepare("second", "--suite", str(root / "presets/suite.json"))
        self.assertEqual(workflow.load_run(second)["suite"], settings["suite"])
        self.assertFalse((second / "presets").exists())
        with self.assertRaises(FileExistsError):
            self.prepare("first")
        self.assertEqual((root / "presets/suite.json").read_bytes(), original)

    def test_credentials_stay_in_child_environment_and_pipeline_errors_fail(self):
        root = self.prepare()
        output = io.StringIO()
        args = argparse.Namespace(output=root)

        def fake_evaluate(command, *, cwd, env, check):
            self.assertEqual(env["CODEX_API_KEY"], "workflow-fake-secret")
            self.assertNotIn("TOPOGYM_MODEL_API_KEY", env)
            self.assertNotIn("workflow-fake-secret", " ".join(command))
            self.assertEqual(env["LIBGL_ALWAYS_SOFTWARE"], "0")
            self.assertEqual(env["PYOPENGL_PLATFORM"], "egl")
            evaluation = root / "evaluation"
            evaluation.mkdir()
            workflow.write_json(evaluation / "evaluation.json", dict(
                suite=workflow.load_run(root)["suite"], agents=workflow.read_json(root / "agents.json"), repeats=1))
            workflow.write_json(evaluation / "results.json", [dict(status="pipeline_error", reason="fake failure",
                directory="agent_model_simulator_rollouts/counter/rollout_1/repeat_1")])
            workflow.write_json(evaluation / "summary.json", [dict(agent_id="model", input_mode="simulator",
                task_id="counter", successes=0, trials=1, pipeline_errors=1, usage_complete=False)])
            return subprocess.CompletedProcess(command, 0)

        with patch.dict(os.environ, {"TOPOGYM_MODEL_API_KEY": "workflow-fake-secret",
                                     "CODEX_API_KEY": "old-fake-secret", "LIBGL_ALWAYS_SOFTWARE": "0"}, clear=True), \
                patch.object(workflow.subprocess, "run", side_effect=fake_evaluate), redirect_stdout(output):
            self.assertEqual(workflow.evaluate_run(args), 1)
        self.assertIn("pipeline_error", output.getvalue())
        self.assertNotIn("workflow-fake-secret", output.getvalue())
        for path in root.rglob("*.json"):
            self.assertNotIn("workflow-fake-secret", path.read_text())
        with patch.object(workflow.subprocess, "run") as process:
            with self.assertRaisesRegex(ValueError, "already exists"):
                workflow.evaluate_run(args)
            process.assert_not_called()

    def test_missing_key_rejected_before_starting_evaluation(self):
        root = self.prepare()
        with patch.dict(os.environ, {}, clear=True), patch.object(workflow.sys.stdin, "isatty", return_value=False), \
                patch.object(workflow.subprocess, "run") as process:
            with self.assertRaisesRegex(ValueError, "TOPOGYM_MODEL_API_KEY"):
                workflow.evaluate_run(argparse.Namespace(output=root))
            process.assert_not_called()
        self.assertFalse((root / "evaluation").exists())

    def test_shell_entrypoint_from_another_directory(self):
        root = self.root / "shell run"
        result = subprocess.run(["bash", str(workflow.ROOT / "tests/run_agent_rollout.sh"), "prepare",
            "--python", workflow.sys.executable, "--output", str(root), "--task", "counter",
            "--model", "test-model", "--max-total-steps", "5"],
            cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(workflow.load_run(root)["limits"]["max_total_steps"], 5)

    def test_watch_waits_then_reads_only_public_ledgers(self):
        args = argparse.Namespace(output=self.root, once=True, interval=2)
        output = io.StringIO()
        with redirect_stdout(output):
            workflow.watch_run(args)
        self.assertIn("Waiting", output.getvalue())
        for prefix, used in (("", 10), ("_private/", 999)):
            path = self.root / "evaluation" / prefix / "agent_model_rgb_rollouts/counter/rollout_1/repeat_1/token_budget.json"
            path.parent.mkdir(parents=True)
            workflow.write_json(path, dict(used=used, limit=3000000))
        output = io.StringIO()
        with redirect_stdout(output):
            workflow.watch_run(args)
        self.assertIn('"used": 10', output.getvalue())
        self.assertNotIn("999", output.getvalue())


if __name__ == "__main__":
    unittest.main()
