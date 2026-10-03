#!/usr/bin/env python3
"""Buzz candidate declaration checks; does not certify an oracle execution."""
from dataclasses import asdict
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.config.registry import task_definition
from topogym.planning.calibration_tools.adapters.buzz_wire import patched_layout, fixture_task, preview


class BuzzGeometryTests(unittest.TestCase):
    def setUp(self):
        self.task_class = task_definition("buzz_wire_3d", "medium")
        self.task = self.task_class(seed=0)
        self.layout = self.task.build_layout()

    def test_only_final_bend_and_post_change(self):
        baseline = asdict(self.layout)
        candidate = patched_layout(self.layout, {"finish_offset_xy_m": [.03, -.02]})
        for key, value in baseline.items():
            if key != "authored_controls_m":
                self.assertEqual(getattr(candidate, key), value)
        sections = dict(self.layout.authored_section_ends)
        before, after = np.asarray(self.layout.authored_controls_m), np.asarray(candidate.authored_controls_m)
        np.testing.assert_array_equal(before[:sections["front_vertical_w"]+1], after[:sections["front_vertical_w"]+1])
        np.testing.assert_array_equal(before[:, 2], after[:, 2])
        np.testing.assert_allclose(after[sections["exit_bend"]:, :2]-before[sections["exit_bend"]:, :2],
                                   np.broadcast_to([.03, -.02], after[sections["exit_bend"]:, :2].shape), atol=1e-15)
        self.assertEqual(asdict(self.layout), baseline)

    def test_rejects_invalid_or_unsupported_edits(self):
        for values in ({"finish_offset_xy_m": [.1, 0]}, {"finish_offset_xy_m": [float("nan"), 0]},
                       {"finish_offset_xy_m": [.055, 0]}, {"terminal_tolerance": 100}):
            with self.assertRaises(ValueError):
                patched_layout(self.layout, values)

    def test_fixture_is_fresh_declaration_and_preserves_task_rules(self):
        pose = {"position_m": [.15, -.4, 1.064], "quaternion_wxyz": [1., 0., 0., 0.]}
        cls = fixture_task(self.task_class, {"finish_offset_xy_m": [.02, 0.]}, initial_wand_pose=pose)
        probe = cls(seed=0)
        self.assertEqual(probe.config, self.task.config)
        self.assertEqual(probe.terminal_revision, self.task.terminal_revision)
        with tempfile.TemporaryDirectory() as folder:
            spec = probe.declare(Path(folder), .92)
            wand = next(e for e in spec.entities if e.name == "wand")
            self.assertEqual(wand.position_m, tuple(pose["position_m"]))
            self.assertFalse(spec.metadata["development_candidate"]["formal_qualification"])
            self.assertIsNone(spec.initial_state)

    def test_preview_keeps_original_tool_and_exports_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            a = preview(self.task, {"finish_offset_xy_m": [0., 0.]}, Path(folder)/"a")
            b = preview(self.task, {"finish_offset_xy_m": [.03, -.02]}, Path(folder)/"b")
            self.assertNotEqual(a["candidate_sha256"], b["candidate_sha256"])
            self.assertEqual(a["base_sha256"], b["base_sha256"])
            self.assertEqual(a["geometry"]["wand_mass_kg"], b["geometry"]["wand_mass_kg"])
            self.assertEqual(a["assets"]["assets/wand.urdf"], b["assets"]["assets/wand.urdf"])
            self.assertFalse(b["physical_execution_verified"])


if __name__ == "__main__":
    unittest.main()
