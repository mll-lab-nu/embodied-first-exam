#!/usr/bin/env python3
"""Exercise release/instance selection and negative paths without a simulator."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "ci_checks")]
import topogym_versions as V
from v15_fixtures import bound_task
from topogym.tasks.release_profile import environment_inputs
from topogym_merge_candidate import candidate_inputs
from regrade_trials import original_task
ACTIVE = V.release(ROOT)["tooling_version"]     # the bound release under test (written for v15)


class Selection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.task = bound_task(self.folder / "topogym-cast-coil-easy-i00-privileged")

    def tearDown(self):
        self.temp.cleanup()

    def test_current_bound_task_and_private_copy_pass(self):
        self.assertEqual(V.require_task(self.task)["release"]["tooling_version"], ACTIVE)
        copy = self.folder / "private" / self.task.name
        shutil.copytree(self.task, copy)
        (copy / "solution").mkdir(exist_ok=True)
        (copy / "solution/oracle.py").write_text("# private strategy\n")
        V.require_task(copy)

    def test_old_version_is_rejected_even_with_valid_binding(self):
        p = self.task / "task.toml"
        p.write_text(p.read_text().replace(f'tooling_version = "{ACTIVE}"', 'tooling_version = "14"'))
        with self.assertRaisesRegex(ValueError, f"require tooling {ACTIVE}"):
            V.require_task(self.task)

    def test_missing_release_receipt_cannot_fall_back(self):
        (self.task / "task_release.json").unlink()
        with self.assertRaises(FileNotFoundError):
            V.require_task(self.task)

    def test_wrong_public_runtime_cannot_be_relabelled(self):
        p = self.task / "task_release.json"
        record = json.loads(p.read_text()); record["release"]["source"]["sha256"] = "0" * 64
        p.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "selected frozen release"):
            V.require_task(self.task)

    def test_verifier_asset_is_checked_independently(self):
        (self.task / "tests/instance_assets/extra.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "assets differ"):
            V.require_task(self.task)

    def test_image_tag_drift_prevents_launch(self):
        with patch("topogym.planning.harbor_bridge.binding.inspect_image", return_value={"id": "sha256:" + "1" * 64}):
            with self.assertRaisesRegex(ValueError, "tag moved"):
                V.require_task(self.task, inspect_docker=True)

    def test_registered_task_requires_catalog(self):
        with self.assertRaisesRegex(ValueError, "catalog has not been frozen"):
            V.require_task(self.task, registered=True)

    def test_batch_cannot_resume_with_different_selection(self):
        # Catalog membership is tested independently; this isolates persistent batch selection.
        first = V.require_task(self.task)
        with patch.object(V, "require_task", return_value=first):
            V.freeze_run(self.folder / "run.json", [self.task])
        with patch.object(V, "require_task", return_value={**first, "task": "other"}):
            with self.assertRaisesRegex(ValueError, "different tasks/release"):
                V.freeze_run(self.folder / "run.json", [self.task])

    def test_regrade_uses_recorded_path_and_rejects_ambiguous_path(self):
        trial = self.folder / "trial"; trial.mkdir()
        record = trial / "result.json"
        record.write_text(json.dumps(dict(task_name=self.task.name, task_id=dict(path=str(self.task)))))
        self.assertEqual(original_task(trial), self.task)
        record.write_text(json.dumps(dict(task_name=self.task.name)))
        with self.assertRaisesRegex(ValueError, "no recorded task path"):
            original_task(trial)

    def test_sampled_rope_preserves_draws_and_uses_fixed_environment(self):
        from topogym.planning.rope_threading.profiles import contact_relaxed_profile
        for tier in ("easy", "medium", "hard"):
            draws = dict(geometry=dict(translation_m=[.01, -.005, 0.], yaw_deg=1.25), rope_finish="hemp")
            params, overrides, _ = environment_inputs("rope_threading", tier, variation="seeded", seed=123, parameters=draws)
            self.assertEqual(params["geometry"]["translation_m"], draws["geometry"]["translation_m"])
            self.assertEqual(params["geometry"]["yaw_deg"], draws["geometry"]["yaw_deg"])
            self.assertEqual(overrides, contact_relaxed_profile(tier)["simulator_overrides"])
            self.assertEqual(params["rope_material"], contact_relaxed_profile(tier)["task_parameters"]["rope_material"])
            source = ROOT / f"tasks/topogym-rope-threading-{tier}-i00-privileged/environment/instance.json"
            _, fixed_overrides, _, _, _ = candidate_inputs("rope_threading", tier, json.loads(source.read_text()), source)
            self.assertEqual(overrides, fixed_overrides)
            self.assertNotIn("ring_yaw_deg", draws["geometry"])

    def test_rope_below_easy_tiers_share_the_environment_and_keep_their_scene(self):
        from topogym.config.registry import task_definition
        from topogym.planning.rope_threading.profiles import contact_relaxed_profile
        regular = contact_relaxed_profile("easy")
        easy_source = ROOT / "tasks/topogym-rope-threading-easy-i00-privileged/environment/instance.json"
        _, _, easy_config, _, _ = candidate_inputs("rope_threading", "easy", json.loads(easy_source.read_text()), easy_source)
        for tier in ("very_easy", "easier"):
            params, overrides, changes = environment_inputs("rope_threading", tier)
            self.assertTrue(changes)
            self.assertEqual(overrides, regular["simulator_overrides"])
            # Everything but the original tiers' ring layout, which is scene geometry.
            self.assertEqual(params, {k: v for k, v in regular["task_parameters"].items() if k != "geometry"})
            # The merge path takes exactly these inputs; the simulator dict equals rope easy's but for the scene fields.
            selection = dict(variation_id=tier, seed=0, simulator={}, qualification="unbuilt selection")
            built, built_overrides, config, _, _ = candidate_inputs("rope_threading", tier, selection,
                                                                    Path("unused/instance.json"))
            self.assertEqual((built, built_overrides), (params, overrides))
            scene = ("variation_id", "task_parameters")
            self.assertEqual({k: v for k, v in config.items() if k not in scene},
                             {k: v for k, v in easy_config.items() if k not in scene})
            # The Task accepts the profile and keeps its own ring layout and terminal definition.
            own = task_definition("rope_threading", tier)()
            task = task_definition("rope_threading", tier)(params)
            self.assertEqual(task.config["geometry"], own.config["geometry"])
            self.assertEqual(task.config["terminal"], {**own.config["terminal"], "maximum_speed_m_s": .01})
            self.assertEqual((task.config["rope_robot_contact"], task.config["rope_reference_shape"]), ("fingers", "initial"))
        for family, tier in (("knot_untying", "very_easy"), ("rope_threading", "base")):
            with self.assertRaisesRegex(ValueError, "No .* profile"):
                environment_inputs(family, tier)

    def test_blanket_sampling_never_resolves_host_physics_resources(self):
        from sample_difficulty_instances import sample_instances
        with patch("topogym.world.physics.initial_state_compatibility.resource_profile",
                   side_effect=AssertionError("controller must not resolve runtime-specific resources")):
            rows = sample_instances(dict(task_ids=["blanket_flatten"], sampling_seed=20260929, samples_per_difficulty=1))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["initial_state_pending"] for row in rows))
        self.assertTrue(all(row["effective_task_parameters"]["initialization_mode"] == "frozen" for row in rows))
        self.assertTrue(all(row["effective_task_parameters"]["initial_state_path"] is None for row in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
