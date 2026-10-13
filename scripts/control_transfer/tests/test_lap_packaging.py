"""Full-lap packaging, public budgets and revision boundaries; stdlib-only."""

import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.control_transfer.specs import spec
from scripts.control_transfer.components.anycarbench.tracks import track_ids, route_metadata
from scripts.control_transfer.trusted.runtime_limits import runtime_limits, LAP_AGENT_SECONDS, LAP_FAMILY
from scripts.control_transfer.gen_tasks import render
from scripts.control_transfer.check_contract import check


class LapPackaging(unittest.TestCase):
    def test_all_catalog_budgets_are_bounded(self):
        for name in track_ids():
            s = spec("anycar-circuit-lap-v2-" + name, 0)
            limits = runtime_limits(s)
            self.assertEqual(s["public"]["horizon_s"], route_metadata(name)["horizon_s"])
            self.assertLessEqual(3 * limits["request_seconds"] + 1800, LAP_AGENT_SECONDS)
            self.assertGreaterEqual(
                limits["collect_seconds"],
                10 * (limits["worker_seconds"] + limits["replay_seconds"]) + limits["request_seconds"],
            )
            self.assertTrue(all(c["full_lap"] for bank in s["bank"].values() for c in bank))
        self.assertEqual(runtime_limits(spec("anycar", 0))["worker_seconds"], 600)

    def test_unbounded_or_inconsistent_private_specs_rejected(self):
        for field, value in [("horizon_s", float("nan")), ("horizon_s", 4001), ("horizon_s", "400")]:
            s = spec("anycar-circuit-lap-v2-silverstone-8", 0)
            s["public"][field] = value
            with self.assertRaises(ValueError):
                runtime_limits(s)
        s = spec("anycar-circuit-lap-v2-silverstone-8", 0)
        s["bank"]["adaptation"][0]["full_lap"] = False
        with self.assertRaises(ValueError):
            runtime_limits(s)

    def test_generated_limits_and_admission_are_frozen(self):
        with tempfile.TemporaryDirectory() as td:
            task = Path(td) / "control-transfer-anycar-circuit-lap-v2-silverstone-8-i00-standard"
            old = os.umask(0o022)
            try:
                render(task, "anycar-circuit-lap-v2-silverstone-8", 0)
            finally:
                os.umask(old)
            self.assertEqual(check(task), [])
            d = tomllib.loads((task / "task.toml").read_text())
            s = json.loads((task / "tests/instance.json").read_text())
            limits = runtime_limits(s)
            self.assertEqual(d["metadata"]["family"], LAP_FAMILY)
            self.assertEqual(d["metadata"]["oracle"], "none")
            self.assertEqual(d["agent"]["timeout_sec"], LAP_AGENT_SECONDS)
            collect = next(c for c in d["verifier"]["collect"] if c["service"] == "sim")
            self.assertGreater(collect["timeout_sec"], limits["collect_seconds"])
            public = task / "environment/public"
            self.assertFalse(any(p.name == "runtime_limits.py" or "trusted" in p.parts for p in public.rglob("*")))
            self.assertTrue((public / "scripts/control_transfer/components/anycarbench/route_lengths.json").is_file())
            s["bank"]["adaptation"][0]["full_lap"] = False
            (task / "environment/sim/instance.json").write_text(json.dumps(s))
            self.assertTrue(check(task))

    def test_sector_defaults_remain_separate(self):
        s = spec("anycar-circuit-v1-silverstone-8", 0)
        self.assertEqual(s["task_variant"], "circuit-sector/1")
        self.assertEqual(s["public"]["horizon_s"], 24)
        self.assertTrue(all("full_lap" not in c for b in s["bank"].values() for c in b))
        self.assertFalse(runtime_limits(s)["uniform_images"])


if __name__ == "__main__":
    unittest.main()
