#!/usr/bin/env python3
"""Mesh and continuous translation checks; no simulator/robot qualification."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.assets.geometry.cast_coil_simplified import (
    BAFFLE_REVISION, LEVELS, SimplifiedCoilAssembly, generate_assets, geometry_record, geometry_report)
from topogym.assets.variation_resources import read_json
from topogym.assets.geometry.cast_coil import occupied


def translation_collision(fixed, moving, start, end, margin=0.):
    """Continuous slab intersection for ALL box pairs; touching is not overlap.

    Each pair contributes an interval of translation parameters with positive
    overlap on all axes. This checks the segment between endpoints as well.
    Only fixed-orientation translations are covered by this calculation.
    """
    a = np.asarray(fixed).copy()
    a[:, 0] -= margin
    a[:, 1] += margin
    b = np.asarray(moving)
    start, end = np.asarray(start), np.asarray(end)
    enter = np.zeros((len(a), len(b)))
    leave = np.ones_like(enter)
    eligible = np.ones_like(enter, dtype=bool)
    for k, v in enumerate(end-start):
        lower = a[:, None, 0, k]-b[None, :, 1, k]-start[k]+1e-12
        upper = a[:, None, 1, k]-b[None, :, 0, k]-start[k]-1e-12
        if abs(v) < 1e-15:
            eligible &= (lower < 0) & (upper > 0)
        else:
            first, last = np.minimum(lower/v, upper/v), np.maximum(lower/v, upper/v)
            enter = np.maximum(enter, first)
            leave = np.minimum(leave, last)
    hits = eligible & (enter < leave-1e-12)
    if not hits.any():
        return None
    values = np.where(hits, enter, np.inf)
    i, j = np.unravel_index(np.argmin(values), values.shape)
    return dict(fixed_box=int(i), moving_box=int(j), enter_t=float(enter[i, j]),
                leave_t=float(leave[i, j]))


def motion_report(assembly):
    a, b = (body.boxes for body in assembly.bodies)
    s = assembly.record["parameters"]["slide_mm"]*.001
    entry_y = s if assembly.record["model_revision"] == BAFFLE_REVISION else -s
    points = [[.08, entry_y, 0.], [0., entry_y, 0.]]
    if s:
        points.append([0., 0., 0.])
    correct = [dict(start_m=u, end_m=v,
                    collision=translation_collision(a, b, u, v),
                    collision_with_025mm_padding=translation_collision(a, b, u, v, .00025))
               for u, v in zip(points, points[1:])]
    negatives = {}
    if s:
        paths = dict(direct_at_final_y=([.08, 0., 0.], [0., 0., 0.]),
                     diagonal_shortcut=([.08, entry_y, 0.], [0., 0., 0.]),
                     premature_slide=([.007, entry_y, 0.], [.007, 0., 0.]),
                     pull_out_without_reverse_slide=([0., 0., 0.], [.08, 0., 0.]),
                     insert_past_stop=([0., entry_y, 0.], [-.003, entry_y, 0.]))
        if assembly.record["model_revision"] == BAFFLE_REVISION:
            paths["slide_past_pocket_end"] = ([0., 0., 0.], [0., -.003, 0.])
        negatives = {name: dict(start_m=u, end_m=v, collision=translation_collision(a, b, u, v))
                     for name, (u, v) in paths.items()}
    elif assembly.record["model_revision"] == "cubic_comb_v2":
        paths = dict(vertical_misalignment=([.08, 0., .002], [0., 0., .002]),
                     insert_past_stop=([0., 0., 0.], [-.002, 0., 0.]))
        negatives = {name: dict(start_m=u, end_m=v, collision=translation_collision(a, b, u, v))
                     for name, (u, v) in paths.items()}
    return dict(method="continuous slab intersection of orthogonal collision boxes",
        scope="fixed relative orientation; no robot/gripper or arbitrary rotation search",
        correct_segments=correct, blocked_counterexamples=negatives,
        intermediate_relative_position_error_m=s,
        passed=bool(all(row["collision_with_025mm_padding"] is None for row in correct)
                    and all(row["collision"] is not None for row in negatives.values())))


class SimplifiedCoilGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assemblies = {level: SimplifiedCoilAssembly(level) for level in LEVELS}

    def test_two_connected_solids_form_intended_cube(self):
        for level, assembly in self.assemblies.items():
            with self.subTest(level=level):
                report = geometry_report(assembly)
                self.assertTrue(report["passed"], report)
                np.testing.assert_allclose(report["assembled_extent_m"], [.102]*3, atol=1e-12)
                self.assertFalse(report["central_bore_open"])
                self.assertEqual(len(report["pieces"]), 2)

    def test_very_easy_large_fingers_fill_center_through_full_depth(self):
        gold, silver = self.assemblies["very_easy"].bodies
        centers = [[0., y, z] for y in (-.05, 0., .05)
                   for z in (-.0408, -.0204, 0., .0204, .0408)]
        np.testing.assert_array_equal(occupied(centers, gold.boxes), [True, False, True, False, True]*3)
        np.testing.assert_array_equal(occupied(centers, silver.boxes), [False, True, False, True, False]*3)
        # No short hidden pegs: every collision box spans the entire cube depth.
        for body in (gold, silver):
            np.testing.assert_allclose(body.boxes[:, 0, 1], -.051)
            np.testing.assert_allclose(body.boxes[:, 1, 1], .051)

    def test_full_translation_segments_and_mechanical_counterexamples(self):
        for level, assembly in self.assemblies.items():
            with self.subTest(level=level):
                report = motion_report(assembly)
                self.assertTrue(report["passed"], report)
                if level == "easier":
                    self.assertGreater(report["intermediate_relative_position_error_m"], .001)

    def test_continuous_check_detects_collision_between_clear_endpoints(self):
        unit = np.array([[[0., 0., 0.], [1., 1., 1.]]])
        self.assertIsNone(translation_collision(unit, unit, [2, 0, 0], [2, 0, 0]))
        self.assertIsNone(translation_collision(unit, unit, [-2, 0, 0], [-2, 0, 0]))
        self.assertIsNotNone(translation_collision(unit, unit, [-2, 0, 0], [2, 0, 0]))
        self.assertIsNone(translation_collision(unit, unit, [-2, 1, 0], [2, 1, 0]))

    def test_export_preserves_com_frames_and_collision_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            for level in LEVELS:
                folder = Path(tmp)/level
                assembly, report = generate_assets(folder, level=level)
                for body, item in zip(assembly.bodies, report["bodies"]):
                    origin = np.array(item["origin_m"])
                    mesh = trimesh.load(folder/body.name/f"{body.name}.glb", force="mesh")
                    np.testing.assert_allclose(mesh.bounds+origin, body.visual.bounds, atol=1e-8)
                    root = ET.parse(folder/body.name/f"{body.name}.urdf").getroot()
                    collisions = root.findall("./link/collision")
                    self.assertEqual(len(collisions), len(body.boxes))
                    for node, bounds in zip(collisions, body.boxes):
                        center = np.fromstring(node.find("origin").attrib["xyz"], sep=" ") + origin
                        size = np.fromstring(node.find("geometry/box").attrib["size"], sep=" ")
                        np.testing.assert_allclose([center-size/2, center+size/2], bounds, atol=1e-9)
                    self.assertGreater(np.linalg.eigvalsh(item["inertia_kg_m2"]).min(), 0)

    def test_easier_root_pocket_is_open_and_leaves_rear_connection(self):
        gold, silver = self.assemblies["easier"].bodies
        # Root pocket is genuinely empty silver volume, open through tongue
        # thickness and at the front edge. The gold bar occupies it at closure.
        probe = [[.025, -.05, z] for z in (-.032, 0., .032)]
        self.assertFalse(occupied(probe, silver.boxes).any())
        self.assertTrue(occupied(probe, gold.boxes).all())
        self.assertTrue(occupied([[.025, -.03, 0.], [.0333, -.03, 0.]], silver.boxes).all())
        self.assertFalse(occupied([[.025, -.03, 0.]], gold.boxes).any())
        # The large tongue, not just its outer wall, spans the entire depth.
        self.assertTrue(occupied([[0., -.051, 0.], [0., .051, 0.]], silver.boxes).all())
        for body in (gold, silver):
            self.assertAlmostEqual(body.visual.extents[1], .102)

    def test_invalid_baffle_cannot_destroy_entry_or_rear_connection(self):
        for key, value in (("wall_mm", 51.), ("slide_mm", 2.),
                           ("baffle_width_mm", 66.), ("baffle_depth_mm", 90.)):
            record = deepcopy(geometry_record("easier"))
            record["parameters"][key] = value
            with self.subTest(parameter=key), self.assertRaises(ValueError):
                SimplifiedCoilAssembly(record=record)

    def test_invalid_comb_cannot_remove_spine_or_merge_fingers(self):
        for key, value in (("tooth_reach_mm", 51.), ("seam_mm", 21.),
                           ("band_count", 4), ("slide_mm", 1.)):
            record = deepcopy(geometry_record("very_easy"))
            record["parameters"][key] = value
            with self.subTest(parameter=key), self.assertRaises(ValueError):
                SimplifiedCoilAssembly(record=record)

    def test_packaged_candidates_match_authored_version(self):
        for level in LEVELS:
            record = read_json(f"variations/cast_coil/{level}/geometry.json")
            self.assertEqual(record, geometry_record(level))


if __name__ == "__main__":
    unittest.main()
