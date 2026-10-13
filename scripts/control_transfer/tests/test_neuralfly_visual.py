"""Render-only isolation checks; detailed assets are optional for basic CI."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from scripts.control_transfer.control_public.fly import Vehicle
from scripts.control_transfer.neuralfly_visual import asset_directory, load_assets
from scripts.control_transfer.neuralfly_video import Video


class NeuralFlyVisualTests(unittest.TestCase):
    def test_missing_or_modified_assets_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                load_assets(d)
            p = Path(d) / "assets/X2_lowpoly.obj"
            p.parent.mkdir()
            p.write_text("not the pinned mesh")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_assets(d)

    @unittest.skipUnless((asset_directory() / "LICENSE").exists(), "public Skydio assets not installed")
    def test_separate_render_model_does_not_mutate_physics(self):
        vehicle = Vehicle([0.3, -0.4, 1.9], mass_scale=1.02)
        model, data = vehicle.model, vehicle.data
        before = {
            name: getattr(model, name).copy()
            for name in ("body_mass", "body_inertia", "geom_size", "geom_type", "geom_contype", "geom_conaffinity")
        }
        state = np.r_[data.qpos, data.qvel, data.qacc].tobytes()
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"NEURALFLY_VISUAL_STYLE": "skydio-x2/1"}):
            video = Video(model, Path(d) / "test.mp4", [0, 0, 1.8])
            try:
                self.assertIsNot(video.render_model, model)
                self.assertIsNot(video.visual_data, data)
                self.assertGreater(video.render_model.nmesh, 0)
                video.frame(data)
                np.testing.assert_array_equal(video.visual_data.qpos, data.qpos)
            finally:
                video.close()
        self.assertEqual(state, np.r_[data.qpos, data.qvel, data.qacc].tobytes())
        for name, expected in before.items():
            np.testing.assert_array_equal(getattr(model, name), expected)


if __name__ == "__main__":
    unittest.main()
