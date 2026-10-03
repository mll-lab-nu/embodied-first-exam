"""Candidate declaration integrity, not physical task acceptance."""
import tempfile
import unittest
from pathlib import Path

from topogym.config.registry import task_definition
from topogym.assets.variation_resources import read_json
from topogym.tasks.horseshoe_ring import common
from .adapters.horseshoe_ring import declaration, template_candidate, preview, rebase_poses, normal_passage_guard
from .candidates import validate_candidate


class HorseshoeModelTests(unittest.TestCase):
    def setUp(self):
        self.task = task_definition("horseshoe_ring", "easy")(seed=0)
        self.original = read_json(self.task.template_resource)

    def test_rejects_unknown_or_malformed_geometry(self):
        for patch in ({"chain": {"wire_radius": .1}}, {"horseshoe": {"thickness": -1}},
                      {"target_ring": {"centerline_radii": [30]}},
                      {"target_ring": {"wire_radius": float("nan")}}):
            with self.assertRaises(ValueError):
                template_candidate(self.task, patch)
        with self.assertRaises(ValueError):
            validate_candidate({"geometry": {"anything": {}}})

    def test_normal_passage_guard_proves_obstruction_without_certifying_large_ring(self):
        proposed = normal_passage_guard(self.task, {"target_ring": {
            "centerline_radii": [37.05060466333426, 35.38152825079453]}})
        self.assertEqual(proposed["status"], "blocked_proven")
        for shoe in proposed["shoes"].values():
            self.assertGreater(shoe["obstruction_margin_lower_bound_m"], .019)
        oversized = normal_passage_guard(self.task, {"target_ring": {
            "centerline_radii": [60, 60]}})
        self.assertEqual(oversized["status"], "inconclusive")
        self.assertFalse(oversized["tilted_passage_checked"])

    def test_ring_phase_preserves_normal_obstruction_and_rejects_invalid_angles(self):
        base = normal_passage_guard(self.task, {})
        changed = normal_passage_guard(self.task, {"target_ring": {"initial_phase_deg": 90}})
        self.assertEqual(base["aperture_diameter_upper_bound_m"], changed["aperture_diameter_upper_bound_m"])
        self.assertEqual(changed["status"], "blocked_proven")
        for phase in (-1, 360, float("nan"), [90]):
            with self.assertRaises(ValueError):
                template_candidate(self.task, {"target_ring": {"initial_phase_deg": phase}})

    def test_pose_window_distinguishes_sampled_rest_from_native_quiet(self):
        from copy import deepcopy
        from .adapters.horseshoe_ring import settled_pose_window
        poses = read_json(self.task.layout_resource)["poses"]
        rows = [dict(state=dict(episode_id="test", branch_id=0, physics_step=i, sim_time_s=i*.5),
                     world=dict(bodies={name: dict(deepcopy(value), linear_velocity_m_s=[0, 0, .01],
                         angular_velocity_rad_s=[0, 0, 1.]) for name, value in poses.items()},
                         contacts=dict(penetration=[])),
                     task=dict(result=dict(terminated=False, metrics=dict(quiet=False)))) for i in range(3)]
        result = settled_pose_window(self.task, {}, rows)
        self.assertTrue(result["passed"])
        self.assertFalse(result["formal_qualification"])
        self.assertEqual(result["native_quiet_samples"], 0)
        self.assertEqual(result["peak_final_substep_angular_velocity_rad_s"]["target_ring"], 1.)
        drifting = deepcopy(rows)
        for body in drifting[-1]["world"]["bodies"].values():
            body["position_m"][0] += .001
        self.assertIn("material_window_too_large", settled_pose_window(self.task, {}, drifting)["failures"])
        broken = deepcopy(rows)
        broken[-1]["state"]["physics_step"] += 1
        with self.assertRaises(ValueError):
            settled_pose_window(self.task, {}, broken)
        assisted = deepcopy(rows)
        assisted[-1]["world"]["grasp"] = dict(hands=dict(left=dict(binding="horseshoe_left")))
        self.assertIn("assisted_binding_in_passive_rest_window",
                      settled_pose_window(self.task, {}, assisted)["failures"])
        for duration in (True, float("nan"), 0):
            with self.assertRaises(ValueError):
                settled_pose_window(self.task, {}, rows, duration_s=duration)

    def test_declaration_restores_on_failure_without_modifying_resource(self):
        generate = common.generate_assets
        with self.assertRaises(RuntimeError):
            with declaration(self.task, {"horseshoe": {"thickness": 3}}):
                self.assertIsNot(common.generate_assets, generate)
                raise RuntimeError("injected declaration failure")
        self.assertIs(common.generate_assets, generate)
        self.assertEqual(read_json(self.task.template_resource), self.original)

    def test_initial_layout_lift_preserves_relative_pose_and_source(self):
        import numpy as np
        from topogym.assets import variation_resources
        original = read_json(self.task.layout_resource)
        with declaration(self.task, {}, initial_layout_lift_m=.003) as report:
            lifted = variation_resources.read_json(self.task.layout_resource)
            for name, value in original["poses"].items():
                np.testing.assert_allclose(np.asarray(lifted["poses"][name]["position_m"])
                    - value["position_m"], [0, 0, .003], atol=1e-12)
            self.assertTrue(report["relative_material_frames_preserved"])
            self.assertFalse(report["settled_layout_requalified"])
        self.assertEqual(read_json(self.task.layout_resource), original)
        for bad in (True, -.001, .021, float("inf")):
            with self.assertRaises(ValueError):
                validate_candidate({"geometry": {"parameters": {}, "initial_layout_lift_m": bad}})

    def test_retargeted_reference_loads_but_drops_original_qualification(self):
        import json
        from topogym.assets.geometry.horseshoe_ring import HorseshoeAssembly
        from topogym.planning.horseshoe_ring.oracle import load_reference
        from .adapters.horseshoe_ring import retarget_reference
        base = HorseshoeAssembly(self.original, scale=2)
        frame = {b.name: dict(pos=b.visual.center_mass.tolist(), quat=[0, 0, 0, 1]) for b in base.bodies}
        patch = {"horseshoe": {"thickness": 3}}
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.json", Path(directory) / "candidate.json"
            source.write_text(json.dumps(dict(template=self.original, scale=2, frames=[frame, frame],
                fold_end_index=1, passed=True, qualification="old success", repair={"passed": True})))
            result = retarget_reference(self.task, patch, source, output)
            self.assertFalse(result["passed"])
            self.assertFalse(result["formal_qualification"])
            self.assertNotIn("repair", result)
            self.assertEqual(json.loads(source.read_text())["qualification"], "old success")
            with self.assertRaises(ValueError):
                retarget_reference(self.task, patch, source, source)
            candidate = HorseshoeAssembly(template_candidate(self.task, patch)[1], scale=2)
            frames, metadata = load_reference(output, candidate)
            self.assertEqual(len(frames), 2)
            self.assertTrue(metadata["initial_matches_canonical_assembly"])

    def test_com_rebase_preserves_authored_eye_positions(self):
        import numpy as np
        from topogym.assets.geometry.horseshoe_ring import HorseshoeAssembly
        from topogym.planning.rigid_reference.feedback import body_pose
        patch = {"horseshoe": {"thickness": 3, "band_width": 7}}
        poses = read_json(self.task.layout_resource)["poses"]
        result = rebase_poses(self.task, patch, poses)
        before = HorseshoeAssembly(self.original, scale=2)
        after = HorseshoeAssembly(template_candidate(self.task, patch)[1], scale=2)
        self.assertGreater(np.linalg.norm(result["com_shift_local_m"]["horseshoe_left"]), .001)
        origins = {b.name: b.visual.center_mass for b in before.bodies}
        for body in after.bodies:
            p, r = body_pose(poses[body.name])
            new_p, new_r = body_pose(result["poses"][body.name])
            np.testing.assert_allclose(p-r.apply(origins[body.name]),
                new_p-new_r.apply(body.visual.center_mass), atol=1e-12)

    def test_probe_rebuild_uses_candidate_shape_and_rebased_layout(self):
        import numpy as np
        from .geometry import RigidProbe
        config = dict(task_id="horseshoe_ring", variation_id="easy", robot_id="aloha",
                      compute_backend="cpu", enable_rgb=False, seed=0)
        patch = {"horseshoe": {"thickness": 3, "band_width": 7}}
        with tempfile.TemporaryDirectory() as directory:
            base = RigidProbe(config, Path(directory) / "base")
            candidate = RigidProbe(config, Path(directory) / "candidate", geometry_parameters=patch)
            expected = rebase_poses(self.task, patch, base.inspect()["bodies"])
            for name, value in candidate.inspect()["bodies"].items():
                np.testing.assert_allclose(value["position_m"], expected["poses"][name]["position_m"], atol=1e-12)
            self.assertEqual(candidate.task.assembly.template["horseshoe"]["thickness"], 3)
            self.assertEqual(base.task.assembly.template["horseshoe"]["thickness"], 4)
            self.assertNotEqual(base.scene_revision, candidate.scene_revision)

    def test_candidate_regenerates_mass_and_preserves_chain_topology(self):
        with tempfile.TemporaryDirectory() as directory:
            base = preview(self.task, {}, Path(directory) / "base")
            changed = preview(self.task, {"horseshoe": {"thickness": 3}}, Path(directory) / "changed")
            self.assertTrue(changed["geometry"]["passed"])
            self.assertEqual(base["geometry"]["topology"], changed["geometry"]["topology"])
            masses = lambda row: {b["name"]: b["mass_kg"] for b in row["bodies"]}
            self.assertLess(masses(changed)["horseshoe_left"], masses(base)["horseshoe_left"])
            self.assertEqual(masses(changed)["target_ring"], masses(base)["target_ring"])
            self.assertFalse(changed["settled_layout_requalified"])
            self.assertNotEqual(changed["candidate_sha256"], base["candidate_sha256"])


if __name__ == "__main__":
    unittest.main()
