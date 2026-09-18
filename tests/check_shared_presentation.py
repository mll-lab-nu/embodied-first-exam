"""CPU checks for shared Nyx configuration and existing RGB consumers.

Run: .venv-gs121-nyx/bin/python -m unittest tests.check_shared_presentation
The actual CUDA render/recording check lives in presentation_preview.py.
"""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf
import torch

from topogym.data.episode_dataset_writer import _grab_rgb
from topogym.utils.recording import recording_session
from topogym.world import nyx
from topogym.world.presentation import default_presentation_config, prepare_presentation
from topogym.world.tabletop import StandardTabletopSceneBuilder
from topogym.core import EntityManifest

ROOT = Path(__file__).resolve().parents[1]


class SharedPresentationTests(unittest.TestCase):
    def test_default_and_explicit_renderer_choices(self):
        with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
            for name in ("presentation_preview", "lock_picking_baseline", "lock_picking_spaced_preview", "hedgehog_in_cage_classic_preview"):
                cfg = compose(config_name=name)
                self.assertEqual(cfg.env.renderer.type, "nyx", name)
                self.assertEqual(cfg.env.presentation.background, "compact_lab", name)
                self.assertEqual(len(cfg.env.renderer.lights), 4, name)
                self.assertEqual(len(cfg.env.presentation.appearance), 2, name)
            fem = compose(config_name="presentation_preview", overrides=["env_configs@env=world_tabletop_fem_v1"])
            self.assertEqual(fem.env.renderer.type, "nyx")
            self.assertEqual(fem.env.presentation.background, "compact_lab")
            cfg = compose(config_name="presentation_preview", overrides=["env.renderer.type=rasterizer",
                          "env.genesis.backend=cpu", "env.presentation.background=checker"])
            self.assertIsNone(StandardTabletopSceneBuilder(cfg.env, cfg.robot_control)._select_renderer())
            cfg.env.renderer.type = "nyx"
            cfg.env.sim.n_envs = 2
            with self.assertRaisesRegex(ValueError, "type=batch"):
                StandardTabletopSceneBuilder(cfg.env, cfg.robot_control)._select_renderer()

    def test_single_room_light_set_and_no_robot_wrist_fallback(self):
        cfg = default_presentation_config()
        cam = dict(res=[8, 6], pos=[1, 0, 1], lookat=[0, 0, 0], up=[0, 0, 1], fov=45)
        cfg.cameras = dict(front=cam, wrist=dict(**cam, attach=dict(entity="robot", enabled=True)))
        cfg.appearance = [dict(pattern="test_object", color=[1, 0, 0], metallic=0, roughness=.5)]
        cameras = dict(front=Mock(), wrist=Mock())
        with patch("topogym.world.nyx_lab.add_lab", return_value=["lab_floor"]) as lab, \
             patch.object(nyx, "apply_finishes", return_value={}) as finishes, \
             patch.object(nyx, "add_camera", return_value=Mock()) as add, \
             patch.object(nyx, "NyxCamera", side_effect=lambda camera, sensor: (camera, sensor)):
            prepare_presentation(Mock(), EntityManifest(), cfg, cameras)
        lab.assert_called_once()
        self.assertEqual([c.kwargs["include_lighting"] for c in add.call_args_list], [True, False])
        self.assertFalse(add.call_args_list[1].args[2].attach.enabled)
        self.assertTrue(cfg.cameras.wrist.attach.enabled)  # no caller config mutation
        self.assertEqual([r.pattern for r in finishes.call_args.args[1]], ["table", "table_frame*", "test_object"])

    def camera(self):
        options = SimpleNamespace(pos=[1., 0, 1], lookat=[0., 0, 0], up=[0., 0, 1])
        frame = torch.full((1, 6, 8, 3), 80, dtype=torch.uint8)
        sensor = SimpleNamespace(_options=options, read=lambda: SimpleNamespace(rgb=frame),
                                 update_camera_pose=Mock())
        raster = SimpleNamespace(transform=nyx.pos_lookat_up_to_T(np.array(options.pos),
                                 np.array(options.lookat), np.array(options.up)).astype(np.float32),
                                 _attached_link=None, _followed_entity=None, _in_recording=False,
                                 _recorded_imgs=[], res=(8, 6))
        raster.start_recording = lambda: setattr(raster, "_in_recording", True)
        raster.stop_recording = Mock()
        return nyx.NyxCamera(raster, sensor), frame

    def test_dataset_rgb_is_a_snapshot_and_free_camera_pose_updates(self):
        camera, cache = self.camera()
        first = _grab_rgb(camera)
        cache.fill_(99)
        self.assertTrue(np.all(first == 80))
        camera.raster_camera.transform[0, 3] += .2
        self.assertTrue(np.all(_grab_rgb(camera) == 99))
        camera.sensor.update_camera_pose.assert_called_once()
        with self.assertRaisesRegex(NotImplementedError, "RGB only"):
            camera.render(depth=True)

    def test_existing_recording_stride_uses_nyx_frames(self):
        camera, _ = self.camera()
        scene = SimpleNamespace(step=Mock())
        original_step = scene.step
        with recording_session(scene, [("front", camera)], save_to="/tmp/nyx-contract.mp4", every_n_steps=2):
            for _ in range(4):
                scene.step()
        self.assertIs(scene.step, original_step)
        self.assertEqual(len(camera._recorded_imgs), 2)
        self.assertTrue(np.all(camera._recorded_imgs[0] == 80))
        camera.stop_recording.assert_called_once()

    def test_attached_camera_reuses_shared_pass_and_invalidates_same_step_reset(self):
        camera, _ = self.camera()
        raster, sensor = camera.raster_camera, camera.sensor
        raster._attached_link = object()
        raster.move_to_attach = Mock()
        raster.transform[0, 3] += .2
        matrix = raster.transform
        sensor._attached_pos = torch.tensor(matrix[None, :3, 3])
        sensor._attached_lookat = torch.tensor((matrix[:3, 3] - matrix[:3, 2])[None])
        sensor._attached_up = torch.tensor(matrix[None, :3, 1])
        sensor._stale = False
        camera.render()
        self.assertFalse(sensor._stale)  # another sensor already rendered this pose
        raster.transform[0, 3] += .1
        camera.render()
        self.assertTrue(sensor._stale)  # reset at the same scene.t needs a fresh pass

    def test_assets_are_independent_of_working_directory(self):
        with patch("pathlib.Path.cwd", return_value=Path("/tmp")):
            self.assertEqual(nyx.asset_path(".external/a.hdr"), ROOT / ".external/a.hdr")


if __name__ == "__main__":
    unittest.main()
