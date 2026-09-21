"""Static task-12 geometry and integration checks; no physics qualification."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf

from topogym.tasks.catalog import TASK_IDS, load_card
from topogym.tasks.slotted_post_ring.geometry import (
    SlottedPostLayout, generate_assets, geometry_report, make_meshes,
)
from topogym.tasks.slotted_post_ring.scene import SlottedPostScene


class SlottedPostChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = SlottedPostLayout()
        cls.parts, cls.cord = make_meshes(cls.layout)

    def test_initial_holes_clearance_and_routing(self):
        report = geometry_report(self.layout, self.parts, self.cord)
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["physics_qualified"])
        # Cord is one connected capped tube; beads and discs each have one hole.
        self.assertEqual(len(self.parts["cord"].split()), 1)
        for name in ("post", "target_ring", "bead_left", "bead_right", "disc_left", "disc_right"):
            self.assertEqual(self.parts[name].euler_number, 0, name)

    def test_filled_slot_is_rejected(self):
        parts = dict(self.parts, post=self.parts["post"].convex_hull)
        report = geometry_report(self.layout, parts, self.cord)
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["post_and_ring_have_real_holes"])

    def test_missing_slot_crossing_is_rejected(self):
        displaced = self.cord.copy()
        displaced[:, 0] += .2
        report = geometry_report(self.layout, self.parts, displaced)
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["cord_passes_slot_once"])

    def test_invalid_aperture_relations_rejected(self):
        for change in (dict(slot_width_m=.045), dict(disc_radius_m=.045),
                       dict(disc_thickness_m=.03), dict(ring_major_radius_m=.03),
                       dict(slot_width_m=.019), dict(slot_top_m=.213),
                       dict(rope_radius_m=float("nan")), dict(slot_top_m=.4)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.layout, **change).validate()

    def test_asset_reload_preserves_layout_and_continuous_rope(self):
        import json
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            layout, report = generate_assets(folder, self.layout)
            reloaded = SlottedPostLayout(**json.loads((folder/"layout.json").read_text()))
            self.assertEqual(layout, reloaded)
            np.testing.assert_array_equal(np.load(folder/"cord_centerline.npy"), self.cord)
            self.assertEqual(report, json.loads((folder/"geometry_report.json").read_text()))
            for name, digest in json.loads((folder/"sha256.json").read_text()).items():
                self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(), digest)

    def test_config_catalog_and_static_step_guard(self):
        self.assertEqual(TASK_IDS[11], "slotted_post_ring")
        self.assertEqual(load_card("slotted_post_ring")["physics"]["qualification"], "unqualified")
        with initialize_config_dir(version_base="1.3", config_dir=str(Path(__file__).resolve().parents[1]/"configs")):
            cfg = compose(config_name="slotted_post_ring_preview")
            OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
            self.assertEqual(cfg.robot_control.robot.name, "aloha")
            self.assertEqual(cfg.task.mode, "static_inspection")
        task = SlottedPostScene(None, self.layout, {}, {})
        with self.assertRaisesRegex(RuntimeError, "Static reconstruction"):
            task.step()


if __name__ == "__main__":
    unittest.main()
