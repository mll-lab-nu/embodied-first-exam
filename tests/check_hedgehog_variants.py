"""Deterministic, bounded sampling and portable scene-instance contracts."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch

import numpy as np
from omegaconf import OmegaConf

from topogym.tasks.hedgehog_in_cage.variants import (
    FAMILIES, GenerationRejected, _validate_spec, canonical, choose_family,
    generate, rules, sample, materialize, load_instance, prototype, file_sha, configuration, VERSION,
)


class HedgehogVariants(unittest.TestCase):
    def test_active_pool_replaces_internal_obstacles_and_versions_identity(self):
        self.assertEqual(FAMILIES, ("oblique_gate", "fixed_side_window", "gen_keyhole"))
        self.assertEqual({choose_family(seed) for seed in range(1000)}, set(FAMILIES))
        for retired in ("staggered_gates", "helical_guide"):
            self.assertTrue(prototype(retired)[1]["parent_physically_verified"])
            with self.assertRaises(ValueError):
                sample(1, family=retired)
        cfg, spec = sample(1, family="oblique_gate")
        self.assertEqual(spec.variant.parameters["generator_version"], VERSION)
        self.assertTrue(spec.key.variant_id.startswith(VERSION+"_"))

    def test_moved_first_contact_does_not_mean_negative_path_is_free(self):
        from topogym.tasks.hedgehog_in_cage.variant_validation import build_assets, negative_paths, evaluate, SolidOracle
        cfg, _ = sample(7, family="oblique_gate", overrides=dict(radius_fraction=1, height_fraction=1))
        parent, _, _ = prototype("oblique_gate")
        old = json.loads((parent / "certificate.json").read_text())
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            report = build_assets(cfg, folder)
            oracle = SolidOracle(folder / "assets")
            trace = json.loads((folder / "object_witness.json").read_text())
            self.assertGreater(oracle.distance(np.array(old["finite_controls"]["straight_pull"]["witness"]["pose"])), 0)
            self.assertTrue(evaluate(oracle, negative_paths(trace)["straight_pull"])["collision_found"])
            self.assertGreater(report["continuous_object_witness_clearance_lower_bound_m"], .0005)
            self.assertEqual(file_sha(folder / "assets/hedgehog.urdf"), file_sha(parent / "assets/hedgehog.urdf"))

    def test_seed_repeat_batch_order_and_global_rng_independence(self):
        expected = {s: canonical(asdict(sample(s)[1])) for s in (1, 7, 42)}
        np.random.seed(1234)
        np.random.random(100)
        actual = {s: canonical(asdict(sample(s)[1])) for s in (42, 1, 7)}
        self.assertEqual(expected, actual)

    def test_named_stream_order_and_appearance_are_independent(self):
        first, a = sample(42)
        second, b = sample(42, declarations=list(reversed(rules()["variation"])))
        self.assertEqual(canonical(asdict(a)), canonical(asdict(b)))
        other, c = sample(42, overrides={"cage_wood_tint": .9})
        self.assertEqual(a.variant.parameters["geometry_sha256"], c.variant.parameters["geometry_sha256"])
        self.assertEqual(first.task.center_xy_m, other.task.center_xy_m)
        self.assertEqual(a.layout, c.layout.__class__(**dict(asdict(c.layout), layout_id=a.layout.layout_id)))
        self.assertNotEqual(a.key.variant_id, c.key.variant_id)

    def test_fixed_mode_selects_existing_geometry_without_redesign(self):
        for family in FAMILIES:
            a, sa = sample(1, family=family, mode="fixed")
            b, sb = sample(42, family=family, mode="fixed")
            self.assertEqual(sa.variant.parameters["geometry_sha256"], sb.variant.parameters["geometry_sha256"])
            self.assertEqual(a.task.randomization, b.task.randomization)
            self.assertEqual(a.task.derived_variant.cage_radial_scale, 1)
            self.assertEqual(a.task.derived_variant.cage_height_scale, 1)
            self.assertFalse(sa.resolved_config["validation"]["export_ready"])

    def test_parameter_domain_corners_keep_clearance_and_bottom_anchor(self):
        for family in FAMILIES:
            for sign in (-1, 1):
                cfg, spec = sample(42, family=family, overrides=dict(radius_fraction=sign,
                    height_fraction=sign, center_dx_m=sign*.004, center_dy_m=-sign*.004, yaw_delta_deg=sign*2))
                d = cfg.task.derived_variant
                self.assertGreater(d.parent_path_clearance_lower_bound_m - d.maximum_design_displacement_m, .0005)
                self.assertTrue(d.ball_geometry_frozen and d.family_motion_frozen)
                _validate_spec(spec)

    def test_retries_keep_family_and_change_continuous_axes(self):
        for seed in (1, 7, 42):
            configs = [sample(seed, attempt=a)[0] for a in range(3)]
            self.assertEqual({c.task.randomization.family_id for c in configs}, {choose_family(seed)})
            self.assertEqual(len({c.task.randomization.radius_fraction for c in configs}), 3)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "rejected"
            with patch("topogym.tasks.hedgehog_in_cage.variants.materialize", side_effect=ValueError("blocked test path")):
                with self.assertRaises(GenerationRejected):
                    generate(42, out, max_attempts=2)
            result = json.loads((out / "result.json").read_text())
            self.assertFalse(result["accepted"])
            self.assertEqual(len(result["attempts"]), 2)
            self.assertEqual(len({a["family"] for a in result["attempts"]}), 1)
            self.assertEqual(len({a["instance_sha256"] for a in result["attempts"]}), 2)
            self.assertTrue(all(a["reason"] == "blocked test path" for a in result["attempts"]))

    def test_invalid_input_and_inconsistent_spec_fail(self):
        for seed in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                sample(seed)
        for options in (dict(family="unknown"), dict(mode="unknown"), dict(overrides={"radius_fraction": 2}),
                        dict(overrides={"radius_fraction": float("nan")}), dict(overrides={"typo": 0}),
                        dict(mode="fixed", overrides={"height_fraction": .1})):
            with self.assertRaises(ValueError):
                sample(1, **options)
        _, spec = sample(1)
        objects = deepcopy(spec.layout.objects)
        objects["cage"]["position_m"][0] += .1
        with self.assertRaisesRegex(ValueError, "layout"):
            _validate_spec(replace(spec, layout=replace(spec.layout, objects=objects)))
        params = dict(spec.variant.parameters, family_id="oblique_gate" if spec.variant.parameters["family_id"] != "oblique_gate" else "helical_guide")
        with self.assertRaisesRegex(ValueError, "parameters"):
            _validate_spec(replace(spec, variant=replace(spec.variant, parameters=params)))

    def test_real_qualified_instance_reloads_after_relocation_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "original"
            _, spec = sample(42, family="oblique_gate")
            cfg, written = materialize(spec, folder)
            moved = folder.rename(Path(root) / "relocated")
            with patch("topogym.tasks.hedgehog_in_cage.variants.sample", side_effect=AssertionError("No resampling")):
                reloaded, restored = load_instance(moved)
            self.assertEqual(asdict(written), asdict(restored))
            self.assertEqual(configuration(cfg), configuration(reloaded))
            self.assertEqual(reloaded.run.output, str(moved))
            self.assertFalse(restored.resolved_config["validation"]["export_ready"])
            damaged = moved / "assets/cage_collision_000.obj"
            damaged.write_text(damaged.read_text() + "\n# changed\n")
            with self.assertRaisesRegex(ValueError, "changed"):
                load_instance(moved)


if __name__ == "__main__":
    unittest.main()
