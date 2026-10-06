#!/usr/bin/env python3
"""Below-easy build/packaging contracts; no physics or original-tier trials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import topogym_merge_candidate as candidate
from topogym.planning.harbor_bridge.catalog import BELOW_EASY_FAMILIES, session_callback
from topogym.planning.harbor_bridge.packaging import collect_helpers
from topogym.planning.harbor_bridge.references import reference_data


class BelowEasy(unittest.TestCase):
    def test_all_selections_build_exact_tiers_and_twins(self):
        with tempfile.TemporaryDirectory() as temp, patch("difficulty_release.source_files",
                return_value={"images/topogym/uipc-build.json": "test"}):
            out = Path(temp) / "candidate"
            candidate.prepare(out, BELOW_EASY_FAMILIES, ("very_easy", "easier"), image="local:below-easy-test")
            document = json.loads((out / "candidate.json").read_text())
            rows = document["instances"]
            self.assertEqual(len(rows), len(BELOW_EASY_FAMILIES)*2)
            self.assertEqual({r["tier"] for r in rows}, {"very_easy", "easier"})
            for row in rows:
                self.assertFalse(row["physics_qualified"])
                slug = Path(row["source"]).parent.parent.name.removesuffix("-privileged")
                self.assertIn(row["tier"].replace("_", "-"), slug)
                commands = [c["argv"] for c in row["commands"]]
                make = next(c for c in commands if "make-instance" in c)
                self.assertEqual(make[make.index("--variation") + 1], row["tier"])
                config = json.loads((out / "inputs" / slug / "expected_config.json").read_text())
                self.assertEqual(config["seed"], 0)
                self.assertEqual(config["variation_id"], row["tier"])
                self.assertFalse(config.get("task_parameters"))
                if row["family"] == "rope_threading":
                    self.assertEqual(config["grasp_assist"]["model"], "ipc_soft_band_v1")
                    self.assertEqual(config["grasp_assist"]["targets"][0]["entity"], "rope")
                self.assertTrue(any("topogym_mk_task.py" in " ".join(c) for c in commands))
                self.assertTrue(any("topogym_mk_limited.py" in " ".join(c) for c in commands))

    def test_private_dependencies_are_portable_and_do_not_reuse_other_tier_recipes(self):
        for family in BELOW_EASY_FAMILIES:
            for tier in ("very_easy", "easier"):
                files, includes = reference_data(ROOT, family, tier, 0)
                helpers = collect_helpers(ROOT, session_callback(family, tier).split(":")[0], includes)
                self.assertTrue(helpers)
                self.assertTrue(all(f"/{tier}/" in name for name in files))
        self.assertIsNone(session_callback("horseshoe_ring", "very_easy"))
        self.assertEqual(session_callback("hedgehog_in_cage", "easier"),
                         "topogym.planning.harbor_bridge.below_easy:run_feedback_policy")
        with self.assertRaises(ValueError):
            reference_data(ROOT, "fiber_bundling", "very_easy", 1)

    def test_callback_rejects_wrong_tier_before_execution(self):
        from types import SimpleNamespace
        from topogym.planning.harbor_bridge.below_easy import run_feedback_policy
        session = SimpleNamespace(task="cast_coil", n_steps=0, _resets=0,
            env=SimpleNamespace(_task=SimpleNamespace(variation_id="easier")))
        with self.assertRaisesRegex(ValueError, "differs"):
            run_feedback_policy(session, Path("unused"), variation="very_easy")

    def test_rope_rejects_missing_or_wrong_grasp_configuration_before_startup(self):
        from types import SimpleNamespace
        from topogym.planning.harbor_bridge.below_easy import run_feedback_policy
        for assist in (None, {"model": "none"}, {"model": "ipc_soft_band_v1", "targets": [{"entity": "other"}]}):
            session = SimpleNamespace(task="rope_threading", n_steps=0, _resets=0,
                env=SimpleNamespace(_task=SimpleNamespace(variation_id="easier"),
                                    config=SimpleNamespace(grasp_assist=assist)))
            with patch("topogym.planning.harbor_bridge.below_easy.prepare_output") as prepare:
                with self.assertRaisesRegex(ValueError, "requires declared ipc_soft_band_v1"):
                    run_feedback_policy(session, Path("unused"), variation="easier")
                prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
