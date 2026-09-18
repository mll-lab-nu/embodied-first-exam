"""Guard motion-first geometry and the provenance of offline physical videos."""

import hashlib
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from topogym.tasks.cast_coil.geometry import (
    CoilAssembly,
    geometry_report,
    load_template,
)
from topogym.tasks.cast_coil.inverse_design import FAMILY_PARAMETERS, KINDS, variant_route
from topogym.tasks.cast_coil.render_physical_trace import verified_frames
from topogym.tasks.cast_coil.robot_archive import qualify_report
from topogym.tasks.cast_coil.verification import (
    CompoundCollision,
    assembly_route,
    box_corners,
    certify_motion,
    prototype_route,
)
from tests.check_cast_coil_robot import completed_recording

ASSETS = (
    Path(__file__).resolve().parents[1] / "assets/tasks/cast_coil/inverse_variants_v1"
)


class InverseGeometryChecks(unittest.TestCase):
    def test_family_dimensions_reach_the_executed_route(self):
        for kind in KINDS:
            key, _ = FAMILY_PARAMETERS[kind]
            template = deepcopy(load_template(ASSETS / kind / "template.json"))
            template["inverse_design"]["parameters"] = {key: 9.0}
            route = assembly_route(CoilAssembly(template))
            for a, b in zip(route, route[1:]):
                for left, right in zip(a.pose(1), b.pose(0)):
                    np.testing.assert_allclose(left, right, atol=1e-14)
            if kind == "eccentric_turn":
                np.testing.assert_allclose(route[0].pose(1)[1], [-0.03975, 0, 0])
                np.testing.assert_allclose(route[1].pivot, [.0135, 0, -.0315])
            elif kind == "split_turn_offset":
                np.testing.assert_allclose(route[2].pose(1)[1] - route[2].pose(0)[1], [0, 0, .009])
                np.testing.assert_allclose(route[3].pivot - route[1].pivot, [0, 0, .009])
            else:
                np.testing.assert_allclose(route[1].advance, [0, .009, 0])
                self.assertAlmostEqual(route[1].pose(.5)[1][1], .0045)

    def test_family_dimension_rejects_cross_family_keys_and_invalid_values(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                variant_route("eccentric_turn", {"pivot_offset_mm": value})
        with self.assertRaises(ValueError):
            variant_route("eccentric_turn", {"step_height_mm": 6})

    def test_appearance_transform_preserves_family_motion_and_screw_advance(self):
        scale = np.array([.95, 1.1, .95])
        for kind in KINDS:
            key, _ = FAMILY_PARAMETERS[kind]
            template = deepcopy(load_template(ASSETS / kind / "template.json"))
            template["inverse_design"]["parameters"] = {key: 9.0}
            template["appearance_design"] = dict(parameters=dict(face_scale=.95, depth_scale=1.1))
            route = assembly_route(CoilAssembly(template))
            original = variant_route(kind, {key: 9.0})
            self.assertEqual([m.name for m in route], [m.name for m in original])
            for a, b in zip(route, original):
                for u in (0, .37, 1):
                    ra, ta = a.pose(u)
                    rb, tb = b.pose(u)
                    np.testing.assert_allclose(ra, rb, atol=1e-14)
                    np.testing.assert_allclose(ta, scale * tb, atol=1e-14)

    def test_published_structures_are_valid_and_require_changed_routes(self):
        seed = CoilAssembly()
        for kind in KINDS:
            with self.subTest(kind=kind):
                assembly = CoilAssembly(load_template(ASSETS / kind / "template.json"))
                self.assertTrue(geometry_report(assembly)["passed"])
                np.testing.assert_array_equal(
                    assembly.bodies[1].boxes, seed.bodies[1].boxes
                )
                self.assertNotAlmostEqual(
                    assembly.bodies[0].visual.volume, seed.bodies[0].visual.volume
                )
                collision = CompoundCollision(*(b.boxes for b in assembly.bodies))
                route = assembly_route(assembly)
                self.assertTrue(
                    all(
                        certify_motion(collision, m, margin_m=0.00006)["passed"]
                        for m in route
                    )
                )
                self.assertFalse(
                    all(
                        certify_motion(collision, m, margin_m=0.00006)["passed"]
                        for m in prototype_route(seed)
                    )
                )
                for a, b in zip(route, route[1:]):
                    for left, right in zip(a.pose(1), b.pose(0)):
                        np.testing.assert_allclose(left, right, atol=1e-14)

    def test_screw_speed_bound_includes_axial_motion(self):
        motion = variant_route("axial_screw_turn")[1]
        corners = box_corners(CoilAssembly().bodies[1].boxes)
        previous = None
        du = 0.01
        bound = motion.point_speed_bound(corners)
        for u in np.linspace(0, 1, 101):
            r, t = motion.pose(u)
            points = corners @ r.T + t
            if previous is not None:
                self.assertLessEqual(
                    np.linalg.norm(points - previous, axis=1).max(), bound * du + 1e-12
                )
            previous = points
        np.testing.assert_allclose(motion.pose(1)[1][1], 0.006)

    def test_variant_specific_intermediate_phase_cannot_be_omitted(self):
        report = completed_recording()
        report["inverse_design_kind"] = "split_turn_offset"
        with self.assertRaises(ValueError):
            qualify_report(report)
        report["phases"] += [
            dict(name=m.name) for m in variant_route("split_turn_offset")
        ]
        qualify_report(report)
        report["phases"] = [
            p for p in report["phases"] if p["name"] != "intermediate_offset"
        ]
        with self.assertRaises(ValueError):
            qualify_report(report)


class PhysicalFrameChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.frames = [
            dict(
                frame=i,
                step=20 * i,
                time_s=0.05 * i,
                phase="settle",
                grasp_assistance_active=False,
            )
            for i in range(3)
        ]
        self.report = dict(
            completed_recording(),
            dt=0.0025,
            simulated_seconds=0.1025,
            physical_frame_count=3,
            physical_frame_fps=20,
        )
        self.save()

    def save(self):
        text = "".join(json.dumps(f) + "\n" for f in self.frames)
        (self.folder / "render_states.jsonl").write_text(text)
        self.report["render_states_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        (self.folder / "result.json").write_text(json.dumps(self.report))

    def test_exact_uniform_physical_frames_are_accepted(self):
        _, frames = verified_frames(self.folder)
        self.assertEqual(frames, self.frames)

    def test_corrupted_trace_is_rejected(self):
        with (self.folder / "render_states.jsonl").open("a") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            verified_frames(self.folder)

    def test_changed_physical_step_cannot_be_rendered(self):
        self.frames[1]["step"] += 1
        self.save()
        with self.assertRaisesRegex(ValueError, "physical step"):
            verified_frames(self.folder)

    def test_missing_release_or_no_physics_cannot_be_rendered(self):
        self.report["physics_steps"] = 0
        self.save()
        with self.assertRaises(ValueError):
            verified_frames(self.folder)
        self.report["physics_steps"] = 1000
        self.frames[-1]["grasp_assistance_active"] = True
        self.save()
        with self.assertRaisesRegex(ValueError, "released"):
            verified_frames(self.folder)


if __name__ == "__main__":
    unittest.main()
