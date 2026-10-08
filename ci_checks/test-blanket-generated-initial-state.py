#!/usr/bin/env python3
"""Generated Blanket birth states (topogym/world/physics/pbd_initial_state_generation.py): when the stored archive
applies, nothing changes; otherwise the instance's recorded recipe is realized, cached and identified by its hashes; the
standard grader accepts a generated state only when the live episode and the replay started from the same one. No GPU
physics here: the realization itself is validated on a GPU host (2026-10-08 journal)."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.assets.library import resource_path
from topogym.config.registry import task_definition
from topogym.tasks.base import InitialStateSpec
from topogym.utils.io import canonical_hash, sha256_file
from topogym.world.initial_state import read_archive_manifest
import topogym.world.physics.pbd_initial_state_generation as G
from topogym.world.physics.initial_state_compatibility import resource_profile

V2 = {"very_easy": "blanket_flatten/corner_folds_archive_v1/cuda_sm89_mp128_87407517a32a/very_easy/seed_0/manifest.json",
      "easier": "blanket_flatten/corner_folds_archive_v1/cuda_sm89_mp128_87407517a32a/easier/seed_0/manifest.json",
      "easy": "blanket_flatten/gathered_archive_v2/cuda_sm89_mp128_87407517a32a/easy/seed_0/manifest.json",
      "medium": "blanket_flatten/gathered_archive_v2/cuda_sm89_mp128_87407517a32a/medium/seed_0/manifest.json",
      "hard": "blanket_flatten/gathered_archive_v2/cuda_sm89_mp128_87407517a32a/hard/seed_0/manifest.json"}
V1 = "blanket_flatten/gathered_scene_v1/hard/seed_0/manifest.json"


def frozen_task(tier, resource):
    path = resource_path(resource)
    return task_definition("blanket_flatten", tier)(
        dict(initial_state_resource=resource, initial_state_sha256=sha256_file(path))), path


def archive_profile(path):
    return resource_profile(read_archive_manifest(path)["metadata"]["backend"])


class Decision(unittest.TestCase):
    def test_the_stored_archive_of_the_runtime_profile_is_restored_unchanged(self):
        for tier, resource in V2.items():
            task, path = frozen_task(tier, resource)
            own = archive_profile(path)
            with patch.object(G, "resource_profile", lambda backend=None, own=own: own if backend is None else resource_profile(backend)), \
                    patch.object(G, "_realize", side_effect=AssertionError("generated on the stored profile")):
                self.assertIsNone(G.ensure_initial_state(None, None, task))
            self.assertIsNone(task.generated_initial_state)
            self.assertEqual(task.frozen_initial_state(), InitialStateSpec(path, sha256_file(path), acceptance="scene_layout"))

    def test_another_profile_realizes_the_recorded_recipe_and_declares_it(self):
        task, path = frozen_task("hard", V2["hard"])
        calls = []

        def realize(config, scene_config, task_, runtime, reference):
            calls.append((runtime, reference))
            return dict(status="passed", manifest_path="/cache/x/state/manifest.json", manifest_sha256="a"*64,
                        recipe_match=True, cache="miss")
        with patch.object(G, "resource_profile", lambda backend=None: "cuda_sm120_mp188_test" if backend is None else resource_profile(backend)), \
                patch.object(G, "_realize", realize):
            record = G.ensure_initial_state(None, None, task)
        (runtime, reference), = calls
        self.assertEqual(runtime, "cuda_sm120_mp188_test")
        self.assertEqual(reference["manifest_sha256"], sha256_file(path))
        self.assertEqual(reference["resource_profile"], archive_profile(path))
        self.assertEqual(task.frozen_initial_state(), InitialStateSpec("/cache/x/state/manifest.json", "a"*64, acceptance="scene_layout"))
        self.assertNotIn("manifest_path", record)

    def test_v1_archives_authored_scenes_and_other_families_are_untouched(self):
        task, _ = frozen_task("hard", V1)
        authored = task_definition("blanket_flatten", "base")({"initialization_mode": "authored"})
        other = task_definition("cast_coil", "easy")()
        with patch.object(G, "resource_profile", lambda backend=None: "cuda_sm120_mp188_test" if backend is None else resource_profile(backend)), \
                patch.object(G, "_realize", side_effect=AssertionError("generated")):
            for item in (task, authored, other):
                self.assertIsNone(G.ensure_initial_state(None, None, item))

    def test_family_recipes_reproduce_the_recorded_preparations(self):
        """The fallback recipe (an instance without any archive) is the one the shipped archives record."""
        for tier, resource in V2.items():
            task, path = frozen_task(tier, resource)
            _, profile, preparation = task.initial_state_recipe()
            recorded = read_archive_manifest(path)["metadata"]["qualification"]["preparation"]
            self.assertEqual(recorded["parameters"], json.loads(json.dumps(asdict(preparation))), tier)
            self.assertEqual(type(profile)(**recorded["profile"]), profile, tier)   # later options at their defaults
            self.assertEqual(recorded["kind"], G.PREPARATION_KIND)


class Cache(unittest.TestCase):
    def test_entries_are_reused_only_as_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            entry = Path(folder)/"entry"
            (entry/"state").mkdir(parents=True)
            (entry/"state/manifest.json").write_text("{}")
            recipe = dict(schema=G.SCHEMA, seed=0)
            (entry/"recipe.json").write_text(json.dumps(recipe))
            record = dict(status="passed", recipe_sha256=canonical_hash(recipe),
                          manifest_sha256=sha256_file(entry/"state/manifest.json"))
            (entry/"generation.json").write_text(json.dumps(record))
            self.assertIsNone(G._cached(Path(folder)/"absent", recipe))
            self.assertEqual(G._cached(entry, recipe), record)
            with self.assertRaises(G.InitialStateGenerationError):
                G._cached(entry, dict(recipe, seed=1))
            (entry/"state/manifest.json").write_text('{"x": 1}')
            with self.assertRaises(G.InitialStateGenerationError):
                G._cached(entry, recipe)

    def test_runtime_physics_enters_the_recipe_record(self):
        with patch.dict(G._RUNTIME_PHYSICS, clear=True):
            G.register_runtime_physics("tooling", dict(version="x", margin=0.05))
            self.assertEqual(G.runtime_physics(), {"tooling": {"margin": 0.05, "version": "x"}})


class StandardGrader(unittest.TestCase):
    def grade(self, rows):
        source = (ROOT/"harbor_templates/topogym/limited/tests/grade.py").read_text()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            lock = dict(schema_version=1, fixture=True)
            (folder/"runtime_binding.json").write_text(json.dumps(lock))
            wanted = hashlib.sha256(json.dumps(lock, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            (folder/"final.json").write_text(json.dumps(dict(finalized=True, success=True, replay_success=True,
                                                             instance_matches=True, deterministic=True)))
            (folder/"trajectory.npz").write_bytes(b"fixture-only")
            for name, row in zip(("startup_binding.json", "replay.verdict.json"), rows):
                (folder/name).write_text(json.dumps(dict(row, runtime_binding=dict(binding_id=wanted))))
            code = source.replace("/data/", str(folder)+"/").replace("/tests/", str(folder)+"/")
            code = code.replace("/logs/verifier", str(folder/"verifier"))
            exec(compile(code, "standard_grade", "exec"), {})
            return json.loads((folder/"verifier/reward.json").read_text())

    def test_generated_states_count_only_when_live_and_replay_share_one(self):
        state = dict(source="generated", manifest_sha256="m"*64, recipe_match=True)
        generated = dict(instance_exact=False, instance_generated=True, instance_sha="s1", initial_state=state)
        exact = dict(instance_exact=True, instance_generated=False, instance_sha="e1",
                     initial_state=dict(source="stored", manifest_sha256="t"*64))
        cases = {
            "exact": ([exact, exact], 1),
            "legacy exact rows": ([dict(instance_exact=True), dict(instance_exact=True)], 1),
            "generated": ([generated, generated], 1),
            "other generated archive": ([generated, dict(generated, initial_state=dict(state, manifest_sha256="n"*64))], 0),
            "other start state": ([generated, dict(generated, instance_sha="s2")], 0),
            "live generated, replay exact": ([generated, exact], 0),
            "recipe differs": ([dict(generated, initial_state=dict(state, recipe_match=False))]*2, 0),
            "neither": ([dict(instance_exact=False)]*2, 0),
        }
        for name, (rows, success) in cases.items():
            reward = self.grade(rows)
            self.assertEqual(reward["success"], success, name)
            self.assertEqual(reward["runtime_binding_ok"], success, name)
            self.assertEqual(reward["initial_state_generated"], int(any(r.get("instance_generated") for r in rows)), name)


if __name__ == "__main__":
    unittest.main()
