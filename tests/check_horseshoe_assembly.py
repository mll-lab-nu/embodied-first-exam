"""Reject impossible/misassembled replicas before starting the rigid solver."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from topogym.tasks.catalog import load_card
from topogym.tasks.horseshoe_ring.geometry import (
    HorseshoeAssembly, Loop, ellipse, generate_assets, geometry_report, load_template,
)


class HorseshoeAssemblyChecks(unittest.TestCase):
    def test_full_initial_assembly_is_linked_and_collision_free(self):
        assembly = HorseshoeAssembly()
        report = geometry_report(assembly)
        self.assertTrue(report["passed"])
        self.assertEqual(report["body_count"], 9)
        self.assertEqual(len(report["topology"]["adjacent_pairs"]), 8)
        self.assertTrue(report["topology"]["target_encloses_both_chain_spans"])
        self.assertFalse(report["extraction_route_verified"])
        self.assertGreater(report["minimum_clearance_lower_bound_m"], .001)
        for body in assembly.bodies:
            self.assertTrue(body.visual.is_watertight)
            self.assertGreater(body.visual.volume, 0)
            self.assertTrue(all(part.is_watertight and part.is_convex for part in body.convex))

    def test_target_moved_to_the_side_is_not_a_valid_puzzle(self):
        assembly = HorseshoeAssembly()
        assembly.loops["target_ring"].center += [0., .3, 0.]
        report = assembly.topology_report()
        self.assertTrue(report["target_not_hopf_linked_to_any_single_loop"])
        self.assertFalse(report["target_encloses_both_chain_spans"])

    def test_tutorial_structure_has_two_free_links_and_rolled_attached_eyes(self):
        path = Path(__file__).resolve().parents[1]/"assets/tasks/horseshoe_ring/tutorial_structure_v2/template.json"
        assembly = HorseshoeAssembly(load_template(path))
        report = geometry_report(assembly)
        self.assertTrue(report["passed"])
        self.assertEqual(report["body_count"], 5)
        self.assertEqual(len(report["topology"]["adjacent_pairs"]), 4)
        for body in assembly.bodies[:2]:
            band = trimesh.util.concatenate(body.convex)
            for eye in body.loops:
                np.testing.assert_allclose(eye.rotation.apply([0, 0, 1]), [0, -1, 0], atol=1e-12)
                _, distances, _ = trimesh.proximity.closest_point(band, eye.points(count=256))
                self.assertLess(float(distances.min()), eye.wire_radius)
        bad = load_template(path)
        bad["horseshoe"]["eye_roll_deg"] = float("nan")
        with self.assertRaisesRegex(ValueError, "roll must be finite"):
            HorseshoeAssembly(bad)

    def test_actual_hopf_link_and_unlinked_loops_are_distinguished(self):
        a = Loop("a", "a", np.zeros(3), Rotation.identity(), np.ones(2), .03, 128)
        b = Loop("b", "b", np.array([1., 0., 0.]), Rotation.from_euler("x", 90, degrees=True),
                 np.ones(2), .03, 128)
        self.assertEqual(abs(a.linking(b)), 1)
        b.center[0] = 3.
        self.assertEqual(a.linking(b), 0)

    def test_bad_chain_counts_spacing_and_target_bore_are_rejected(self):
        template = load_template()
        for n in (0, 2, 4):
            bad = deepcopy(template)
            bad["chain"]["links_per_span"] = n
            with self.assertRaises(ValueError):
                HorseshoeAssembly(bad)
        bad = deepcopy(template)
        bad["chain"]["center_spacing"] = 30.
        self.assertFalse(geometry_report(HorseshoeAssembly(bad))["passed"])
        bad = deepcopy(template)
        bad["target_ring"]["centerline_radius"] = 19.
        self.assertFalse(geometry_report(HorseshoeAssembly(bad))["passed"])

    def test_horseshoe_openings_remain_open_in_collision_geometry(self):
        assembly = HorseshoeAssembly()
        for body in (b for b in assembly.bodies if b.convex):
            # The line between the two terminal-eye centers crosses the open
            # mouth, whereas the missing sector of a solid annulus would block it.
            a, b = (loop.center for loop in body.loops)
            samples = np.linspace(a, b, 100)
            mesh = trimesh.util.concatenate(body.convex)
            _, distances, _ = trimesh.proximity.closest_point(mesh, samples)
            self.assertGreater(float(distances.min()), .003)
            # Terminal eye roots must touch their horseshoe, not float beside it.
            for eye in body.loops:
                _, distances, _ = trimesh.proximity.closest_point(mesh, eye.points(count=256))
                self.assertLess(float(distances.min()), eye.wire_radius)

    def test_export_is_nine_free_single_bodies_with_explicit_inertial_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            assembly, report = generate_assets(Path(tmp))
            for info in report["bodies"]:
                name = info["name"]
                root = ET.parse(Path(tmp)/name/f"{name}.urdf").getroot()
                self.assertEqual(len(root.findall("link")), 1)
                self.assertEqual(root.findall("joint"), [])
                self.assertEqual(root.find("link/inertial/origin").attrib["xyz"], "0 0 0")
                self.assertGreater(float(root.find("link/inertial/mass").attrib["value"]), 0)
                self.assertGreater(np.linalg.eigvalsh(info["inertia_kg_m2"]).min(), 0)
                self.assertGreater(len(root.findall("link/collision")), 24)
                for node in root.findall(".//mesh"):
                    self.assertTrue((Path(tmp)/name/node.attrib["filename"]).is_file())
            scene = trimesh.load(Path(tmp)/"assembly.glb", force="scene")
            self.assertEqual(len(scene.geometry), 9)

    def test_legacy_probe_dimensions_are_independent_of_photo_replica(self):
        card = load_card("horseshoe_ring")["baseline"]
        self.assertEqual(card["probe"]["centerline_radius_m"], .04)
        self.assertEqual(card["probe"]["tube_radius_m"], .004)
        t, scale = load_template(), card["scene_scale"]
        np.testing.assert_allclose(card["chain"]["link_centerline_radii_m"],
                                   np.array(t["chain"]["link_radii"])*scale/1000)
        self.assertAlmostEqual(card["chain"]["tube_radius_m"], t["chain"]["wire_radius"]*scale/1000)


if __name__ == "__main__":
    unittest.main()
