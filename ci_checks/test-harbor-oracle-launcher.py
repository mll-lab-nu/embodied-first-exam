#!/usr/bin/env python3
"""Exercise shell queue dispatch with synthetic rewards, never physical evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bash_scripts/run_harbor_oracle_grades.sh"


class Launcher(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="oracle queue ")
        self.root = Path(self.temp.name)
        self.tasks = self.root / "candidate tasks"
        for family in ("cast-coil", "cast-keyhole"):
            for mode in ("privileged", "standard"):
                task = self.tasks / f"topogym-{family}-easy-i00-{mode}"
                task.mkdir(parents=True)
                (task / "task_release.json").write_text("{}")
        self.shim = self.root / "test python"
        self.shim.write_text("#!" + sys.executable + "\n" + '''
import json,os,sys
from pathlib import Path
if len(sys.argv)>1 and sys.argv[1].endswith('/test_harbor_oracles.py'):
    a=sys.argv[2:]
    def value(name): return a[a.index(name)+1]
    out=Path(value('--output')); out.mkdir()
    family=value('--families'); smoke='--smoke-steps' in a
    ok=family=='cast_keyhole' or smoke
    rows=[dict(mode=mode,status='smoke_passed' if smoke else 'passed' if ok else
               'score_failed' if mode=='privileged' else 'blocked_dependency',
               grade=0 if smoke or not ok else 1,errors=[]) for mode in ('privileged','standard')]
    (out/'results.json').write_text(json.dumps(dict(status='complete',tasks=rows)))
    with open(os.environ['TEST_DISPATCH_LOG'],'a') as f: f.write(json.dumps(a)+'\\n')
    raise SystemExit(0 if ok else 1)
os.execv(os.environ['TEST_REAL_PYTHON'],[os.environ['TEST_REAL_PYTHON'],*sys.argv[1:]])
''')
        self.shim.chmod(0o755)
        self.env = dict(os.environ, TOPOGYM_PYTHON=str(self.shim), TOPOGYM_HARBOR=sys.executable,
                        TEST_REAL_PYTHON=sys.executable, TEST_DISPATCH_LOG=str(self.root / "dispatch.jsonl"))

    def tearDown(self):
        self.temp.cleanup()

    def run_queue(self, *args):
        return subprocess.run(["bash", str(SCRIPT), "--output", str(self.root / "output"),
                               "--tasks-root", str(self.tasks), *args], env=self.env,
                              text=True, capture_output=True, timeout=30)

    def test_plan_has_33_cases_and_does_not_create_output(self):
        result = self.run_queue("--plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 33)
        self.assertNotIn("orbits", result.stdout)
        self.assertNotIn("slotted", result.stdout)
        self.assertFalse((self.root / "output").exists())

    def test_failed_task_does_not_skip_next_and_resume_preserves_results(self):
        args = ["--families", "cast_coil,cast_keyhole", "--tiers", "easy"]
        result = self.run_queue(*args)
        self.assertEqual(result.returncode, 1, result.stderr)
        summary = json.loads((self.root / "output/summary.json").read_text())
        self.assertFalse(summary["all_passed"])
        self.assertEqual([r["status"] for r in summary["tasks"]],
                         ["score_failed", "blocked_dependency", "passed", "passed"])
        before = (self.root / "dispatch.jsonl").read_bytes()
        self.assertEqual(self.run_queue(*args, "--resume").returncode, 1)
        self.assertEqual((self.root / "dispatch.jsonl").read_bytes(), before)
        self.assertNotEqual(self.run_queue(*args, "--resume", "--smoke-steps", "3").returncode, 0)
        self.assertNotEqual(self.run_queue(*args).returncode, 0)

    def test_smoke_forwards_real_budget_and_has_distinct_scope(self):
        result = self.run_queue("--families", "cast_coil", "--tiers", "easy",
                                "--smoke-steps", "3", "--wall-seconds", "600")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads((self.root / "output/summary.json").read_text())
        self.assertEqual(summary["scope"], "connectivity smoke")
        self.assertTrue(summary["all_passed"])
        self.assertEqual([r["grade"] for r in summary["tasks"]], [0, 0])
        argv = json.loads((self.root / "dispatch.jsonl").read_text())
        self.assertEqual(argv[argv.index("--smoke-steps")+1], "3")
        self.assertEqual(argv[argv.index("--wall-seconds")+1], "600")

    def test_unsupported_tier_is_rejected_before_work(self):
        self.assertEqual(self.run_queue("--tiers", "very_easy").returncode, 2)
        self.assertFalse((self.root / "output").exists())


if __name__ == "__main__":
    unittest.main()
