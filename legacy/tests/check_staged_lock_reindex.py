"""Necessary retreat certificate and continuous ring geometry regressions."""

import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
import xml.etree.ElementTree as ET
import numpy as np
import trimesh
from omegaconf import OmegaConf
from topogym.tasks_legacy.connectivity._staged_lock_geometry import (
    LockGeometry,
    variant_geometry,
    write_disc,
)
from topogym.tasks_legacy.connectivity._staged_lock_ring import slot_profile
from topogym.planning.staged_lock_reindex import certificate


class ReindexTests(unittest.TestCase):
    def setUp(self):
        self.g = variant_geometry(LockGeometry(), "limited_two_retreats", 0)
        self.stops = OmegaConf.create(
            [
                dict(style="single_ring", bounds_deg=b, ear_phase_deg=-35)
                for b in ([-15, 15], [-10, 75], [-180, 180])
            ]
        )

    def test_backlash_and_free_gaps_still_require_two_resets(self):
        proof = certificate(self.g, self.stops)
        self.assertEqual(proof["minimum_required_decoupling_retreats"], 2)
        self.assertEqual(proof["shortest_branch_sequences"], [[0, 1, 2]])
        self.assertEqual(
            proof["relative_rotor_angle_bands_deg"], [(-8, 8), (22, 38), (52, 68)]
        )

    def test_wider_front_stop_removes_necessary_retreats(self):
        self.stops[0].bounds_deg = [-75, 75]
        self.assertEqual(
            certificate(self.g, self.stops)["minimum_required_decoupling_retreats"], 0
        )

    def test_excessive_backlash_is_not_falsely_certified(self):
        with self.assertRaisesRegex(ValueError, "gap reindexing"):
            certificate(replace(self.g, slot_half_deg=14), self.stops)

    def test_continuous_geometric_two_retreat_witness(self):
        # Ideal centreline coupling witness, independent of the robot oracle.
        # The key is explicitly allowed to change azimuth at depth 1.5.
        states = [
            (0, -60, [0, 0, 0]),
            (1, -60, [0, 0, 0]),
            (2, -60, [0, 0, 0]),
            (2, -45, [15, 15, 0]),
            (1, -45, [15, 15, 0]),
            (1, -75, [-15, 15, 0]),
            (1.5, -75, [-15, 15, 0]),
            (1.5, -45, [-15, 15, 0]),
            (2, -45, [-15, 15, 0]),
            (2, -15, [15, 45, 0]),
            (1, -15, [15, 45, 0]),
            (1, -45, [-15, 45, 0]),
            (1.5, -45, [-15, 45, 0]),
            (1.5, -15, [-15, 45, 0]),
            (2, -15, [-15, 45, 0]),
            (2, 0, [0, 60, 0]),
            (3, 0, [0, 60, 0]),
            (4, 0, [0, 60, 0]),
        ]
        for before, after in zip(states, states[1:]):
            for f in np.linspace(0, 1, 101):
                depth = before[0] + f * (after[0] - before[0])
                angle = before[1] + f * (after[1] - before[1])
                discs = np.array(before[2]) + f * (np.array(after[2]) - before[2])
                self.assertFalse(self.g.clearance(depth, angle, discs))
                for value, stop in zip(discs, self.stops):
                    self.assertTrue(
                        stop.bounds_deg[0] - 1e-8 <= value <= stop.bounds_deg[1] + 1e-8
                    )
        self.assertEqual(sum(b[0] < a[0] for a, b in zip(states, states[1:])), 2)

    def test_full_slot_is_continuous_and_its_supports_clear_the_pin(self):
        angles = np.arange(0, 360, 5.0)
        a, b = slot_profile(angles, -180, 180, -35)
        np.testing.assert_allclose(b - a, 0.011)
        with tempfile.TemporaryDirectory() as directory:
            path = write_disc(
                self.g,
                self.g.slots[2],
                Path(directory) / "disc",
                0.12,
                0.03,
                (0.7, 0.3, 0.2),
                stop=self.stops[2],
                mount_z=-0.157,
            )
            joint = ET.parse(path).find("joint")
            self.assertEqual(joint.get("type"), "continuous")
            self.assertIsNone(joint.find("limit"))
            frame = ET.parse(path.parent / "limits/stop_frame.urdf")
            planes = []
            for item in frame.findall(".//collision/geometry/mesh"):
                m = trimesh.load(item.get("filename"), process=False)
                planes.append((m.triangles_center, m.face_normals))
            for angle in np.radians(angles):
                # Probe the entire pin's radial clearance and both axial ends,
                # especially the lower arc next to the mounting legs.
                for r in (0.093, 0.097, 0.101):
                    for x in (-0.017, 0.0, 0.010):
                        p = np.array([x, r * np.sin(angle), r * np.cos(angle)])
                        self.assertFalse(
                            any(
                                np.all(np.sum((p - c) * n, axis=1) < -1e-9)
                                for c, n in planes
                            ),
                            (float(np.degrees(angle)), r, x),
                        )


if __name__ == "__main__":
    unittest.main()
