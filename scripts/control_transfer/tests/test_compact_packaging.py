"""Compact route revision, deadline, public-export and legacy compatibility contracts."""

import copy
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
from scripts.control_transfer.components.anycarbench.tracks import track_ids, compact_catalog
from scripts.control_transfer.trusted.runtime_limits import runtime_limits, LAP_AGENT_SECONDS, LAP_FAMILY
from scripts.control_transfer.gen_tasks import render
from scripts.control_transfer.check_contract import check

NAME = "anycar-circuit-compact-v3-silverstone-8"


class CompactPackaging(unittest.TestCase):
    def test_all_routes_use_compact_geometry_and_standard_budget(self):
        self.assertEqual(len(track_ids()), 160)
        for name in track_ids():
            for index in range(2):
                s = spec("anycar-circuit-compact-v3-" + name, index)
                public = s["public"]
                self.assertEqual(s["task_variant"], "circuit-compact-lap/3")
                self.assertEqual(public["route_revision"], "compact-30s/1")
                self.assertEqual(public["horizon_s"], 30)
                self.assertEqual(public["target_lap_time_s"], 28)
                self.assertAlmostEqual(public["scaled_length_m"], 45, places=8)
                self.assertEqual(
                    public["geometry_modifications"]["minor_axis_widening"],
                    compact_catalog()["routes"][name]["minor_axis_widening"],
                )
                limits = runtime_limits(s)
                self.assertLess(3 * limits["request_seconds"] + 1800, 14400)
                self.assertGreaterEqual(
                    limits["collect_seconds"],
                    limits["request_seconds"] + 10 * (limits["worker_seconds"] + limits["replay_seconds"]),
                )
                for cases in s["bank"].values():
                    for case in cases:
                        self.assertEqual(case["plant_seed"], 10100 + 1000 * index)
                        self.assertEqual(case["route_revision"], "compact-30s/1")
                        self.assertTrue(case["full_lap"])

    def test_private_revision_mismatch_fails_closed(self):
        source = spec(NAME, 0)
        for key, value in [("horizon_s", 31), ("horizon_s", float("nan")), ("route_revision", "circuit-lap/2")]:
            s = copy.deepcopy(source)
            s["public"][key] = value
            with self.assertRaises(ValueError):
                runtime_limits(s)
        for key, value in [("route_revision", "circuit-lap/2"), ("full_lap", False), ("track_id", "monaco-6")]:
            s = copy.deepcopy(source)
            s["bank"]["held_out"][0][key] = value
            with self.assertRaises(ValueError):
                runtime_limits(s)

    def test_generated_public_export_and_standard_cutoff(self):
        with tempfile.TemporaryDirectory() as td:
            task = Path(td) / ("control-transfer-" + NAME + "-i00-standard")
            old = os.umask(0o022)
            try:
                render(task, NAME, 0)
            finally:
                os.umask(old)
            self.assertEqual(check(task), [])
            meta = tomllib.loads((task / "task.toml").read_text())
            self.assertEqual(meta["agent"]["timeout_sec"], 14400)
            self.assertNotEqual(meta["metadata"]["family"], LAP_FAMILY)
            self.assertEqual(meta["metadata"]["oracle"], "full")   # its reference run, gen_tasks.EVIDENCE (#329 review)
            public = task / "environment/public"
            p = json.loads((public / "task-spec.json").read_text())
            self.assertEqual(p["image_interval_s"], 1)
            self.assertIn("0 through 30", p["image_sampling"])
            self.assertEqual(p["request_timeout_s"], 1200)
            self.assertIn("CONTROL_DEPLOY_TIMEOUT_S=1200", (task / "environment/Dockerfile").read_text())
            self.assertTrue((public / "scripts/control_transfer/components/anycarbench/compact_routes.json").is_file())
            self.assertFalse(
                any("trusted" in p.parts or p.name == "anycar_compact_routes.py" for p in public.rglob("*"))
            )
            collect = next(c for c in meta["verifier"]["collect"] if c["service"] == "sim")
            self.assertGreater(collect["timeout_sec"], runtime_limits(spec(NAME, 0))["collect_seconds"])
            p["horizon_s"] = 40
            (public / "task-spec.json").write_text(json.dumps(p))
            self.assertTrue(check(task))

    def test_sector_and_long_lap_remain_distinct(self):
        sector = spec("anycar-circuit-v1-silverstone-8", 0)
        lap = spec("anycar-circuit-lap-v2-silverstone-8", 0)
        self.assertEqual(sector["public"]["horizon_s"], 24)
        self.assertGreater(lap["public"]["horizon_s"], 390)
        self.assertEqual(LAP_AGENT_SECONDS, 129600)
        for s in (sector, lap):
            self.assertTrue(all("route_revision" not in c for bank in s["bank"].values() for c in bank))
        self.assertTrue(runtime_limits(lap)["uniform_images"])
        self.assertFalse(runtime_limits(sector)["uniform_images"])


if __name__ == "__main__":
    unittest.main()
