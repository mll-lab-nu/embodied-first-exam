"""Seed identity, coupling, recovery and family-specific assembly contracts."""

from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from omegaconf import OmegaConf

from topogym.tasks.cast_coil.assembly_task import required_assembly_phases
from topogym.tasks.cast_coil.geometry import CoilAssembly
from topogym.tasks.cast_coil.inverse_design import KINDS
from topogym.tasks.cast_coil.robot_archive import qualify_report, REQUIRED_PHASES
from topogym.tasks.cast_coil.variants import (
    canonical,
    sample,
    load_instance,
    generate,
    validate_parameters,
    derive,
    check_geometry,
)
from topogym.tasks.cast_coil.verification import assembly_route
from tests.check_cast_coil_robot import completed_recording


class SeedVariantChecks(unittest.TestCase):
    def test_repeat_order_and_global_rng_do_not_change_instance(self):
        expected = {seed: canonical(asdict(sample(seed)[1])) for seed in (7, 13, 1)}
        np.random.seed(987)
        np.random.random(100)
        actual = {seed: canonical(asdict(sample(seed)[1])) for seed in (1, 7, 13)}
        self.assertEqual(expected, actual)

    def test_seeds_change_geometry_and_layout_and_cover_all_families(self):
        configs = [sample(seed)[0] for seed in range(24)]
        self.assertEqual({c.task.randomization.family_id for c in configs}, set(KINDS))
        self.assertEqual(len({c.task.variant for c in configs}), len(configs))
        self.assertEqual(
            len({tuple(c.task.center_xy_m) for c in configs}), len(configs)
        )
        self.assertTrue(
            all(
                c.task.objective == "assemble" and c.task.goal.instruction
                for c in configs
            )
        )

    def test_existing_sampler_is_used_and_config_input_is_not_mutated(self):
        cfg, _ = sample(9)
        before = OmegaConf.to_container(cfg, resolve=True)
        first, _ = sample(14, config=cfg)
        cfg.task.variation = list(reversed(cfg.task.variation))
        second, _ = sample(14, config=cfg)
        self.assertEqual(first.task.template, second.task.template)
        self.assertEqual(first.task.randomization, second.task.randomization)
        cfg.task.variation = list(reversed(cfg.task.variation))
        self.assertEqual(before, OmegaConf.to_container(cfg, resolve=True))

    def test_conditioned_depth_and_mass_at_parameter_corners(self):
        for family in KINDS:
            cfg, _ = sample(0, family=family, representative=True)
            for s in (0.97, 1.03):
                for depth_fraction in (0, 1):
                    for delta in (0.0, 1.5):
                        cfg.task.randomization.face_scale = s
                        cfg.task.randomization.depth_fraction = depth_fraction
                        cfg.task.randomization.profile_delta_mm = delta
                        derive(cfg.task)
                        validate_parameters(cfg.task)
                        d = cfg.task.derived_variant.parameters.depth_scale
                        self.assertTrue(0.94 <= d <= 1.06)
                        self.assertTrue(
                            all(
                                0.9 - 1e-12 <= r <= 1.1 + 1e-12
                                for r in cfg.task.derived_variant.mass_ratios
                            )
                        )

    def test_scale_transforms_geometry_and_screw_motion_together(self):
        cfg, _ = sample(6, family="axial_screw_turn")
        a = CoilAssembly(OmegaConf.to_container(cfg.task.template, resolve=True))
        scale = cfg.task.derived_variant.parameters
        route = assembly_route(a)
        np.testing.assert_allclose(route[1].advance, [0, 0.009 * scale.depth_scale, 0])
        self.assertAlmostEqual(a.template["outer_width"], 34 * scale.face_scale)

    def test_three_representatives_have_continuous_assembly_witnesses(self):
        for family in KINDS:
            cfg, _ = sample(0, family=family, representative=True)
            report = check_geometry(cfg)
            self.assertEqual(report["status"], "passed")
            self.assertGreaterEqual(min(report["initial_xy_surface_gap_m"]), 0.01)
            self.assertGreaterEqual(report["minimum_certified_gap_m"], 0.0002)
            self.assertTrue(all(c["blocked"] for c in report["other_family_controls"]))
            self.assertGreaterEqual(
                report["route_table_clearance"]["minimum_route_table_clearance_m"],
                0.01 - 1e-12,
            )
            if family == "eccentric_turn":
                self.assertGreater(report["route_table_clearance"]["lift_m"], 0.09)

    def test_saved_instance_loads_without_resampling_and_detects_tampering(self):
        cfg, spec = sample(42)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "instance.json"
            payload = asdict(spec)
            path.write_text(canonical(payload))
            with patch(
                "topogym.tasks.cast_coil.variants.sample",
                side_effect=AssertionError("Must not resample"),
            ):
                restored = load_instance(path)
            self.assertEqual(restored.task, cfg.task)
            payload["resolved_config"]["task"]["yaw_deg"] += 1
            path.write_text(canonical(payload))
            with self.assertRaisesRegex(ValueError, "hash"):
                load_instance(path)

    def test_rejections_are_bounded_logged_and_do_not_return_success(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "candidate"
            with patch(
                "topogym.tasks.cast_coil.variants.check_geometry",
                side_effect=ValueError("test blocked geometry"),
            ):
                with self.assertRaisesRegex(RuntimeError, "2 attempts"):
                    generate(3, out, family=KINDS[0], robot=False, max_attempts=2)
            report = json.loads((out / "result.json").read_text())
            self.assertFalse(report["accepted"])
            self.assertEqual(len(report["attempts"]), 2)
            self.assertNotEqual(
                report["attempts"][0]["instance_id"],
                report["attempts"][1]["instance_id"],
            )
            self.assertTrue(all(not a["accepted"] for a in report["attempts"]))

    def test_bad_seed_and_unknown_family_fail(self):
        for seed in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                sample(seed)
        with self.assertRaises(ValueError):
            sample(0, family="unknown")
        cfg, _ = sample(0, family="axial_screw_turn", representative=True)
        cfg.task.randomization.profile_delta_mm = 0.75
        with self.assertRaisesRegex(ValueError, "outline"):
            validate_parameters(cfg.task)

    def test_family_assembly_cannot_skip_its_distinguishing_phase(self):
        for family in KINDS:
            phases = (
                REQUIRED_PHASES
                - {
                    "prototype_slide",
                    "prototype_quarter_turn",
                    "prototype_extract",
                    "place_silver",
                    "place_gold",
                }
            ) | required_assembly_phases(family)
            report = dict(
                completed_recording(),
                objective="assemble",
                inverse_design_kind=family,
                goal_assembled=True,
                final_relative_position_error_m=0.0001,
                final_relative_rotation_error_rad=0.001,
                initial_xy_surface_gap_m=[0.08, 0.078],
                phases=[dict(name=p) for p in phases],
            )
            qualify_report(report)
            special = {
                "eccentric_turn": "assembly_quarter_turn",
                "split_turn_offset": "assembly_reverse_intermediate_offset",
                "axial_screw_turn": "assembly_reverse_screw_turn",
            }[family]
            report["phases"] = [p for p in report["phases"] if p["name"] != special]
            with self.assertRaises(ValueError):
                qualify_report(report)


if __name__ == "__main__":
    unittest.main()
