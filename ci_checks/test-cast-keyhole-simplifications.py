#!/usr/bin/env python3
"""Real mesh checks for new channels; not a robot or physics qualification."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.assets.geometry.cast_keyhole_simplified import geometry_record
from topogym.assets.geometry.cast_keyhole import plate_assembly_transforms
from topogym.assets.library import resource_path
from topogym.assets.variation_resources import read_json
from topogym.config.registry import task_definition, variation_registration
from topogym.planning.cast_keyhole.simplified_policy import route_displacements, SimplifiedKeyholePolicy
from topogym.planning.cast_keyhole.policy import PAD_TO_TCP, PARTS
from topogym.tasks.cast_keyhole.common import recommended_grasp_assist
from topogym.evaluation.task_metrics import rigid_asset_vertices, body_points


class SimplificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.scenes = {}
        for level in ("very_easy", "easier"):
            task = task_definition("cast_keyhole", level)()
            cls.scenes[level] = (task, *task.build_assets(Path(cls.folder.name)/level))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_reproducible_resources_and_instances(self):
        for level, (task, _, report) in self.scenes.items():
            self.assertEqual(geometry_record(level), read_json(task.geometry_resource))
            other = task_definition("cast_keyhole", task.variation_id)(seed=0)
            self.assertEqual(other.instance_id, task.instance_id)
            self.assertTrue(report["passed"])
            self.assertEqual([p["euler_number"] for p in report["pieces"]], [2, 0])
            self.assertGreater(report["minimum_initial_surface_clearance_m"], .003)
            from topogym.tasks.cast_keyhole.qualification import placement_qualification
            self.assertIsNone(placement_qualification(task))
        self.assertNotEqual(*(t.instance_id for t, _, _ in self.scenes.values()))

    def test_old_seed_pool_and_asset_identities_are_preserved(self):
        self.assertEqual(variation_registration("cast_keyhole")["variation_id"], "cast_keyhole_easy")
        for seed in range(9):
            row = variation_registration("cast_keyhole", "seeded", seed)
            self.assertEqual(row["difficulty"], ("easy", "medium", "hard")[seed % 3])
        hashes = {
            "F1": "90ca0ec73617ea5f1e108c9a1bdc6e86416b4464bbff6a490240c0dd6cfd0844",
            "F2": "b9a3e81f5cd907b0b6a3660bbd03768e7c54ecd2c8ba108f3e693c3b7a2c0697",
            "F3": "f7d0ec58cdbf3870dbb698f7a7d4f039d3e59756b27304c1f5d561efa756ee14"}
        for family, expected in hashes.items():
            self.assertEqual(hashlib.sha256(resource_path(
                f"variations/cast_keyhole/{family}/geometry.json").read_bytes()).hexdigest(), expected)

    def test_grasp_regions_are_in_the_new_link_frames(self):
        for level, (task, assembly, report) in self.scenes.items():
            origins = {b["name"]: np.asarray(b["origin_m"]) for b in report["bodies"]}
            assist = recommended_grasp_assist(level)
            self.assertEqual(len(assist.targets), 2)
            for target in assist.targets:
                body = next(b for b in assembly.bodies if b.name == target.entity)
                point = np.asarray(target.center_m)+origins[target.entity]
                self.assertTrue(body.visual.contains([point])[0])
                self.assertLess(target.radius_m, .03)

    def test_standard_dimensions_and_original_silver_exterior(self):
        baseline = read_json("variations/cast_keyhole/F1/geometry.json")
        for level, (task, assembly, _) in self.scenes.items():
            record = read_json(task.geometry_resource)
            for name in ("gold", "silver"):
                rings = np.asarray(record["rings_mm"][name][0])
                np.testing.assert_allclose(rings.min(0), [-13., -35.], atol=1e-7)
                np.testing.assert_allclose(rings.max(0), [13., 34.], atol=1e-7)
                np.testing.assert_allclose(np.ptp(rings, axis=0)*record["scale"], [78., 207.])
            self.assertEqual(record["thickness_mm"]*record["scale"], 9.)
            # Compare polygons, independent of vertex ordering/orientation.
            from shapely.geometry import Polygon
            self.assertLess(Polygon(record["rings_mm"]["silver"][0]).symmetric_difference(
                Polygon(baseline["rings_mm"]["silver"][0])).area, 1e-6)

    def test_policy_grasp_points_match_declared_runtime_regions(self):
        for level, (task, _, report) in self.scenes.items():
            with tempfile.TemporaryDirectory() as folder:
                spec = task.declare(folder, .74)
                origins = {b["name"]: np.asarray(b["origin_m"]) for b in report["bodies"]}
                policy = SimplifiedKeyholePolicy(geometry=read_json(task.geometry_resource), variation=level,
                    body_origins=origins, goal_region={}, mount_position=[0., 0., 0.], canonical_vertices={},
                    part="pickup")
                states = {e.name: dict(position_m=e.position_m, quaternion_wxyz=e.quaternion_wxyz)
                          for e in spec.entities}
                policy.obs = dict(privileged=dict(world=dict(bodies=states)))
                targets = policy.grasp_targets(policy.bodies())
                regions = {t.entity: t for t in recommended_grasp_assist(level).targets}
                for side, name in PARTS.items():
                    tcp, rotation = targets[side]
                    expected = body_points(states[name], [regions[name].center_m])[0]
                    np.testing.assert_allclose(tcp-rotation.apply(PAD_TO_TCP), expected, atol=1e-10)

    def test_two_free_pieces_match_all_original_plate_frames_and_placement(self):
        # COMs change with hole geometry; compare authored plate frames instead
        # of requiring identical URDF mass-center positions.
        for parameters in ({}, {"yaw_deg": 25., "center_xy_m": [-.1, .08]}):
            reference = None
            for level in ("easy", "medium", "hard", "very_easy", "easier"):
                with tempfile.TemporaryDirectory() as folder:
                    task = task_definition("cast_keyhole", level)(parameters)
                    self.assertEqual(task.defaults, task_definition("cast_keyhole", "easy").defaults)
                    spec = task.declare(folder, .74)
                    report = spec.metadata["asset_report"]
                    origins = {b["name"]: np.asarray(b["origin_m"]) for b in report["bodies"]}
                    transforms = plate_assembly_transforms(read_json(task.geometry_resource))
                    frames = []
                    self.assertEqual([e.name for e in spec.entities], ["keyhole_gold", "keyhole_silver"])
                    self.assertEqual(task.placement_remainder, ("keyhole_gold",))
                    for entity, metal in zip(spec.entities, ("gold", "silver")):
                        self.assertFalse(entity.fixed)
                        turn = Rotation.from_quat(np.asarray(entity.quaternion_wxyz)[[1, 2, 3, 0]])
                        frame = np.eye(4)
                        frame[:3, :3] = turn.as_matrix() @ transforms[metal][:3, :3]
                        frame[:3, 3] = np.asarray(entity.position_m) + turn.apply(
                            transforms[metal][:3, 3]-origins[entity.name])
                        frames.append(frame)
                        vertices = body_points(dict(position_m=entity.position_m,
                            quaternion_wxyz=entity.quaternion_wxyz), rigid_asset_vertices(entity))
                        self.assertAlmostEqual(vertices[:, 2].min(), .7405, places=7)
                    if reference is None:
                        reference = frames
                    else:
                        np.testing.assert_allclose(frames, reference, atol=1e-9, err_msg=level)

    def test_old_full_policy_cannot_silently_use_new_initial_assembly(self):
        for level, (task, _, report) in self.scenes.items():
            with self.assertRaisesRegex(NotImplementedError, "restored v4 initial pose"):
                SimplifiedKeyholePolicy(geometry=read_json(task.geometry_resource), variation=level,
                    body_origins={b["name"]: b["origin_m"] for b in report["bodies"]},
                    goal_region={}, mount_position=[0., 0., 0.], canonical_vertices={}, part="all")

    @staticmethod
    def _gold_frame():
        return Rotation.from_euler("z", 90, degrees=True)*Rotation.from_euler("x", 90, degrees=True)

    def _transversely_aligned_meshes(self, level):
        """Check the lower channel independently of the as-yet unplanned entry.

        This virtual pose is NOT the default scene or a verified robot motion.
        """
        task, assembly, _ = self.scenes[level]
        record = read_json(task.geometry_resource)
        gold, silver = (body.visual.copy() for body in assembly.bodies)
        source = plate_assembly_transforms(record)["silver"]
        aligned = np.eye(4)
        aligned[:3, 3] = np.array([0., 22., -42.])*record["scale"]/1000.
        silver.apply_transform(aligned @ np.linalg.inv(source))
        return gold, silver

    def test_aligned_channel_clearance_at_three_mm_intervals(self):
        for level in self.scenes:
            gold, silver = self._transversely_aligned_meshes(level)
            manager = trimesh.collision.CollisionManager()
            manager.add_object("gold", gold)
            minimum = float("inf")
            for a, b in zip(route_displacements(level), route_displacements(level)[1:]):
                for u in np.linspace(0., 1., int(np.ceil(np.linalg.norm(b-a)/.003))+1):
                    transform = np.eye(4)
                    transform[:3, 3] = self._gold_frame().apply(a+u*(b-a))
                    self.assertFalse(manager.in_collision_single(silver, transform=transform), (level, u))
                    minimum = min(minimum, manager.min_distance_single(silver, transform=transform))
            self.assertGreater(minimum, .003, level)

    def test_aligned_straight_pull_is_blocked_only_by_easier_offset(self):
        for level in self.scenes:
            gold, silver = self._transversely_aligned_meshes(level)
            manager = trimesh.collision.CollisionManager()
            manager.add_object("gold", gold)
            transform = np.eye(4)
            # Guide bar reaches the middle offset while retaining initial x/attitude.
            transform[:3, 3] = self._gold_frame().apply([0., -.054, 0.])
            self.assertEqual(manager.in_collision_single(silver,
                             transform=transform), level == "easier")

    def test_aligned_diagonal_shortcut_hits_material(self):
        gold, silver = self._transversely_aligned_meshes("easier")
        manager = trimesh.collision.CollisionManager()
        manager.add_object("gold", gold)
        route = route_displacements("easier")
        collisions = []
        for u in np.linspace(0., 1., 41):
            transform = np.eye(4)
            transform[:3, 3] = self._gold_frame().apply(u*route[3])
            collisions.append(manager.in_collision_single(silver, transform=transform))
        self.assertTrue(any(collisions))


if __name__ == "__main__":
    unittest.main()
