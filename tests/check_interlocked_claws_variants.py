"""Replay identity, honest family availability, and scene/geometry coupling."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from omegaconf import OmegaConf
from hydra import initialize_config_dir
from hydra.core.global_hydra import GlobalHydra

from topogym.tasks.interlocked_claws.geometry import ClawAssembly, reference_body_poses
from topogym.tasks.interlocked_claws.reference import ReferenceMotion
from topogym.tasks.catalog import load_card
from topogym.generation.layout_randomization import _resolve_fn
from topogym.tasks.interlocked_claws.variants import (
    FAMILIES, DatasetNotReady, FamilyUnavailable, assert_runtime_supported,
    canonical, generate, load_instance, materialize, motion_targets,
    prepare_episode, sample, transform_pose, _base_config, ROOT, ideal_pair_certificate,
)


class ClawVariantChecks(unittest.TestCase):
    def test_task_card_exposes_real_pipeline_entrypoints(self):
        hooks = load_card("interlocked_claws")["variant_generation"]
        cfg, spec = _resolve_fn(hooks["sample_entrypoint"])(7, family="claw_weave")
        self.assertEqual(spec.task_id, "interlocked_claws")
        self.assertEqual(cfg.task.seed, 7)
        self.assertIs(_resolve_fn(hooks["materialize_entrypoint"]), generate)
        self.assertIs(_resolve_fn(hooks["restore_entrypoint"]), prepare_episode)
        self.assertFalse(hooks["dataset_enabled"])

    def test_seed_replay_independent_of_draw_order_and_global_rng(self):
        expected = {seed: canonical(asdict(sample(seed)[1])) for seed in (7, 11, 2)}
        np.random.seed(901)
        np.random.random(80)
        observed = {seed: canonical(asdict(sample(seed)[1])) for seed in (2, 7, 11)}
        self.assertEqual(expected, observed)

    def test_all_three_declared_families_selected_and_locked_across_retries(self):
        configs = [sample(seed)[0] for seed in range(24)]
        self.assertEqual({str(cfg.task.seed_variant.family_id) for cfg in configs}, set(FAMILIES))
        for seed in (0, 1, 3):
            families = [str(sample(seed, attempt=attempt)[0].task.seed_variant.family_id) for attempt in range(3)]
            self.assertEqual(len(set(families)), 1)

    def test_fixed_prototype_does_not_randomly_resynthesize_geometry(self):
        configs = [sample(seed, family="claw_weave")[0] for seed in range(8)]
        for cfg in configs:
            p = cfg.task.seed_variant
            self.assertEqual((p.scale, p.dx_m, p.dy_m, p.yaw_deg), (1., 0., 0., 0.))
        self.assertGreater(len({canonical(OmegaConf.to_container(c.task.render_variant)) for c in configs}), 1)

    def test_fixed_visual_draws_share_mechanical_and_split_identity(self):
        specs = [sample(seed, family="claw_weave")[1] for seed in (1, 2, 3)]
        self.assertEqual(len({s.variant.parameters["mechanical_sha256"] for s in specs}), 1)
        self.assertEqual(len({s.variant.parameters["split_group"] for s in specs}), 1)
        self.assertEqual(len({s.key.variant_id for s in specs}), 3)

    def test_axis_order_and_extra_visual_axis_do_not_change_existing_draws(self):
        base, _ = sample(4)
        before = OmegaConf.to_container(base, resolve=True)
        a, _ = sample(8, config=base, parameter_mode="similarity_candidate")
        self.assertEqual(before, OmegaConf.to_container(base, resolve=True))
        base.task.variation = list(reversed(base.task.variation))
        base.task.extra_visual = .5
        base.task.variation.append(dict(kind="uniform", path="extra_visual", lo=0., hi=1.))
        b, _ = sample(8, config=base, parameter_mode="similarity_candidate")
        self.assertEqual(a.task.seed_variant, b.task.seed_variant)
        self.assertEqual(before["task"]["seed"], 4)

    def test_fresh_sampler_works_inside_hydra_and_parallel_workers(self):
        expected = {seed: canonical(asdict(sample(seed)[1])) for seed in (2, 3, 7)}
        _base_config.cache_clear()
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            active = GlobalHydra.instance().hydra
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(lambda seed: (seed, canonical(asdict(sample(seed)[1]))), (7, 2, 3)))
            self.assertIs(GlobalHydra.instance().hydra, active)
        self.assertEqual(dict(results), expected)

    def test_saved_spec_reloads_without_resampling_and_rejects_tampering(self):
        cfg, spec = sample(23, family="claw_weave")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"instance.json"
            original = asdict(spec)
            path.write_text(canonical(original))
            with patch("topogym.tasks.interlocked_claws.variants.sample", side_effect=AssertionError("resampling")):
                loaded = load_instance(path)
                self.assertEqual(loaded.task.render_variant, cfg.task.render_variant)
            for location in ("parameters", "config", "instruction"):
                data = json.loads(canonical(original))
                if location == "parameters": data["variant"]["parameters"]["split_group"] = "wrong"
                if location == "config": data["resolved_config"]["task"]["seed_variant"]["scale"] = 1.01
                if location == "instruction": data["variant"]["instruction"] = "wrong"
                path.write_text(canonical(data))
                with self.assertRaisesRegex(ValueError, "hash"):
                    load_instance(path)

    def test_material_change_reaches_actual_mesh_without_changing_physics(self):
        a, _ = sample(4, family="claw_weave")
        b, _ = sample(5, family="claw_weave")
        first = ClawAssembly(render_variant=a.task.render_variant)
        second = ClawAssembly(render_variant=b.task.render_variant)
        self.assertNotEqual(first.roughness, second.roughness)
        for x,y in zip(first.bodies, second.bodies):
            np.testing.assert_array_equal(x.mesh.triangles, y.mesh.triangles)
            np.testing.assert_array_equal(x.pose, y.pose)
            self.assertEqual(x.mesh.mass, y.mesh.mass)
        self.assertAlmostEqual(first.bodies[0].mesh.visual.material.roughnessFactor, a.task.render_variant.roughness)
        for i in range(2):
            rule = next(r for r in reversed(a.env.appearance) if r.pattern == f"claw_{i}")
            self.assertEqual(list(rule.color), list(a.task.render_variant.colors[i][:3]))
            self.assertEqual(rule.roughness, first.roughness)

    def test_similarity_transforms_surface_points_grasps_and_motion_together(self):
        cfg, _ = sample(7, family="claw_weave", parameter_mode="similarity_candidate")
        p = cfg.task.seed_variant
        source = ReferenceMotion()
        assembly = ClawAssembly()
        for seconds in (0., 21., 87.22, 140., source.duration):
            q, _, original, held, phase = source.sample(seconds)
            changed, flags, name = motion_targets(cfg, seconds)
            self.assertEqual((held, phase), (flags, name))
            frames = reference_body_poses(source.reference, q)
            for i, (body, old, new) in enumerate(zip(assembly.bodies, original, changed)):
                v = body.mesh.vertices[::150]
                world = v @ old[:3,:3].T + old[:3,3]
                transformed = (float(p.scale)*v) @ new[:3,:3].T + new[:3,3]
                common = transform_pose(np.eye(4), p)
                expected = float(p.scale)*world @ common[:3,:3].T + common[:3,3]
                np.testing.assert_allclose(transformed, expected, atol=1e-14)
                if held[i]:
                    grasp = source.grasps[i].copy()
                    grasp[:3,3] *= float(p.scale)
                    hand = transform_pose(frames[body.source["gripper_body"]], p)
                    np.testing.assert_allclose(hand @ grasp, new, atol=1e-14)
        certificate = ideal_pair_certificate(cfg)
        self.assertTrue(certificate["passed"])
        self.assertGreater(certificate["minimum_ideal_clearance_lower_bound_m"], 0.)
        self.assertFalse(certificate["robot_ik_certified"])
        self.assertFalse(certificate["dynamics_certified"])

    def test_unimplemented_family_fails_once_without_fallback_or_dummy_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            for family in FAMILIES[1:]:
                result = generate(9, Path(temp)/family, family=family, max_attempts=4)
                self.assertFalse(result["materialized"])
                self.assertFalse(result["dataset_eligible"])
                self.assertEqual(result["family_id"], family)
                self.assertEqual(len(result["attempts"]), 1)
                self.assertEqual(result["attempts"][0]["error_type"], "FamilyUnavailable")
                self.assertFalse((Path(temp)/family/"attempt_00/assets").exists())

    def test_retry_budget_logs_all_failures_and_never_switches_family(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("topogym.tasks.interlocked_claws.variants.materialize", side_effect=ValueError("fixture collision")):
                result = generate(0, Path(temp)/"failed", max_attempts=3, parameter_mode="similarity_candidate")
            self.assertFalse(result["materialized"])
            self.assertEqual(len(result["attempts"]), 3)
            self.assertEqual({a["family_id"] for a in result["attempts"]}, {"claw_weave"})
            self.assertEqual(len({a["instance_id"] for a in result["attempts"]}), 3)

    def test_future_pipeline_can_load_fixed_instance_and_blocks_unqualified_export(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"instance.json"
            _, spec = sample(5, family="claw_weave")
            path.write_text(canonical(asdict(spec)))
            self.assertEqual(prepare_episode(path).task.seed, 5)
            with self.assertRaisesRegex(DatasetNotReady, "generic_contact_controls_failed"):
                prepare_episode(path, for_dataset=True)

    def test_runtime_rejects_geometry_changes_instead_of_reusing_old_ik(self):
        cfg, _ = sample(1, family="claw_weave", parameter_mode="similarity_candidate")
        with self.assertRaisesRegex(ValueError, "newly solved robot IK"):
            assert_runtime_supported(cfg.task)
        cfg, _ = sample(1, family="helical_crown")
        with self.assertRaises(FamilyUnavailable):
            assert_runtime_supported(cfg.task)

    def test_bad_inputs_and_video_directory_rejected_before_writing(self):
        for value in (-1, True, 1.5):
            with self.assertRaises(ValueError): sample(value)
        with self.assertRaises(ValueError): sample(0, family="unknown")
        with self.assertRaises(ValueError): sample(0, parameter_mode="unknown")
        with self.assertRaises(ValueError): sample(0, attempt=-1)
        with self.assertRaises(ValueError): generate(0, "demos/interlocked_claws/forbidden")


if __name__ == "__main__":
    unittest.main()
