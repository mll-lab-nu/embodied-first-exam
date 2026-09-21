"""Seed/pipeline contracts; physical acceptance is exercised separately on CPU."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from omegaconf import OmegaConf

from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.runtime.episode_runner import EpisodeRunContext
from topogym.tasks.cast_keyhole import variants as v
from topogym.tasks.cast_keyhole.variant_runner import KeyholeVariantRunner, load_spec


class SeedGeneratorChecks(unittest.TestCase):
    def test_boolean_roundoff_slit_does_not_become_an_extra_mesh_hole(self):
        from shapely.geometry import Polygon
        from topogym.tasks.cast_keyhole.family_variants import normalize_outer_stock
        from topogym.tasks.cast_keyhole.inverse_variants import geometry_from_record, polygon_record
        polygon = Polygon([(0, 0), (4, 0), (4, 4), (2, 4), (2, 1),
                           (2-1e-14, 1), (2-1e-14, 4), (0, 4)])
        cleaned = normalize_outer_stock(polygon)
        self.assertLess(polygon.symmetric_difference(cleaned).area, 1e-10)
        record = dict(thickness_mm=3., rings_mm=dict(gold=polygon_record(cleaned), silver=polygon_record(cleaned)))
        meshes, _ = geometry_from_record(record)
        self.assertTrue(meshes[0].is_watertight)
        self.assertEqual(meshes[0].euler_number, 2)

    def test_one_seed_reproduces_across_batch_order_and_shards(self):
        seeds = [0, 1, 2, 7, 19, 23, 29, 999]
        expected = {s: asdict(v.sample(s)[1]) for s in seeds}
        for shard in (seeds[::-2], seeds[-2::-2]):
            for seed in shard:
                self.assertEqual(asdict(v.sample(seed)[1]), expected[seed])
        self.assertEqual(len({d["key"]["variant_id"] for d in expected.values()}), len(seeds))

    def test_named_axes_order_and_unrelated_draw_do_not_change_values(self):
        base = OmegaConf.create(deepcopy(v._base_config()))
        before = OmegaConf.to_container(base, resolve=True)
        first = randomize_task_cfg(base, "cast_keyhole", 19)
        reordered = OmegaConf.create(before)
        entries = list(reordered.task.variation)
        reordered.task.variation = entries[-2::-1] + [entries[-1]]
        second = randomize_task_cfg(reordered, "cast_keyhole", 19)
        v.VariantRng(19).stream("visual/unused_new_axis").random(100)
        third = randomize_task_cfg(base, "cast_keyhole", 19)
        self.assertEqual(first.task.randomization, second.task.randomization)
        self.assertEqual(first.task.randomization, third.task.randomization)
        self.assertEqual(OmegaConf.to_container(base, resolve=True), before)

    def test_fixed_designs_have_no_hidden_parameter_jitter(self):
        for family in v.FAMILIES:
            for style in v.STYLES:
                a = v.sample(3, family=family, style=style, mode="fixed")[1]
                b = v.sample(900, family=family, style=style, mode="fixed")[1]
                self.assertEqual(a.variant.parameters["selected"], b.variant.parameters["selected"])
                for key, value in v.DEFAULTS.items():
                    self.assertEqual(a.variant.parameters["selected"][key], value)

    def test_rejection_retries_keep_family_and_style_but_resample_micro_axes(self):
        first = v.sample(29)[1].variant.parameters["selected"]
        for attempt in (1, 2, 50):
            item = v.sample(29, attempt=attempt)[1].variant.parameters["selected"]
            self.assertEqual((item["family"], item["style"]), (first["family"], first["style"]))
            self.assertNotEqual(item["width_scale"], first["width_scale"])
            self.assertEqual(item, v.sample(29, attempt=attempt)[1].variant.parameters["selected"])

    def test_invalid_axes_cannot_bypass_validation(self):
        for seed in (-1, True, 1.5, "7"):
            with self.assertRaises(ValueError):
                v.sample(seed)
        for kw in (dict(family="F4"), dict(style="D"), dict(mode="demo"), dict(attempt=-1),
                   dict(overrides={"radius": 1}), dict(overrides={"width_scale": float("nan")}),
                   dict(overrides={"yaw_deg": 30}), dict(overrides={"palette": True}),
                   dict(mode="fixed", overrides={"width_scale": 1.01})):
            with self.subTest(kw=kw), self.assertRaises((ValueError, TypeError)):
                v.sample(19, **kw)

    def test_episode_round_trip_and_tampered_config_rejection(self):
        _, spec = v.sample(19)
        with TemporaryDirectory() as folder:
            p = Path(folder) / "spec.json"
            v.save(p, asdict(spec))
            recovered = load_spec(p)
            self.assertEqual(asdict(spec), asdict(recovered))
            v.check_spec(recovered)
        changed = deepcopy(spec.resolved_config)
        changed["task"]["randomization"]["width_scale"] = 1.01
        with self.assertRaisesRegex(ValueError, "differs"):
            v.check_spec(replace(spec, resolved_config=changed))
        changed = deepcopy(spec.resolved_config)
        changed["env"]["sim"]["dt"] *= 2
        with self.assertRaisesRegex(ValueError, "configuration"):
            v.check_spec(replace(spec, resolved_config=changed))

    def test_catalog_is_portable_and_checks_all_core_bytes(self):
        pool = v.catalog(verify=True)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            v.save(root / "catalog.json", pool)
            with patch.object(v, "ASSETS", root), self.assertRaises((ValueError, FileNotFoundError)):
                v.catalog(verify=True)

    def test_failed_preparation_has_bounded_retries_and_no_success_or_h5(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "attempts"
            with patch.object(v, "prepare", side_effect=ValueError("infeasible geometry")) as fake:
                with self.assertRaisesRegex(ValueError, "No accepted"):
                    v.generate(19, root, max_attempts=2)
            self.assertEqual(fake.call_count, 2)
            report = json.loads((root / "attempts.json").read_text())
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["attempts"]), 2)
            self.assertFalse(list(root.rglob("*.h5")))
            with self.assertRaises(FileExistsError):
                v.generate(19, root)

    def test_runner_never_marks_a_sample_or_failure_as_physical_success(self):
        _, spec = v.sample(19)
        with TemporaryDirectory() as temp:
            with patch("topogym.tasks.cast_keyhole.variant_runner.prepare", side_effect=ValueError("rejected")):
                result = KeyholeVariantRunner(Path(temp) / "run").run(EpisodeRunContext(spec))
            self.assertFalse(result.success)
            self.assertFalse(result.stable_ready)
            self.assertFalse(result.export_ready)
            self.assertIn("rejected", result.failure_reason)


if __name__ == "__main__":
    unittest.main()
