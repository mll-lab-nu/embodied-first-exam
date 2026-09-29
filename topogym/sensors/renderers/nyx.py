"""Shared runtime Nyx RGB camera implementation; never advances physics."""
import numpy as np
from omegaconf import OmegaConf
from genesis.utils.geom import pos_lookat_up_to_T
from topogym.assets.library import visual_asset_path as asset_path

def camera_kwargs(camera_cfg, manifest) -> dict:
    """Translate the shared camera rig, including its link-local wrist transform."""
    camera = {k: OmegaConf.to_container(camera_cfg[k], resolve=True)
              if OmegaConf.is_config(camera_cfg[k]) else camera_cfg[k]
              for k in ("res", "pos", "lookat", "up", "fov")}
    # Same defaults as StandardTabletopBuilder, not Nyx's different far default.
    camera.update(near=float(camera_cfg.get("near", 0.1)), far=float(camera_cfg.get("far", 20.0)))
    attach = camera_cfg.get("attach")
    if attach is not None and attach.get("enabled", True):
        entity = manifest.get(str(attach.get("entity", "robot")))
        link = entity.get_link(str(attach.get("link", "hand")))
        offset = attach.get("offset_T")
        if offset is None:
            offset = pos_lookat_up_to_T(
                np.asarray(attach.get("offset_pos", [0, 0, 0])),
                np.asarray(attach.get("offset_lookat", [0.1, 0, 0])),
                np.asarray(attach.get("offset_up", [0, 0, 1])),
            )
        camera.update(entity_idx=entity.idx, link_idx_local=link.idx_local,
                      offset_T=np.asarray(offset).tolist())
    return camera


def add_camera(scene, renderer_cfg, camera_cfg, manifest, *, include_lighting=True):
    """Add a native Nyx sensor using the same rig as the regular renderer."""
    try:
        import gs_nyx.nyx_py_sdk as nps
        from gs_nyx_plugin.nyx_camera_options import NyxCameraOptions
    except ImportError as exc:
        raise RuntimeError("Nyx RGB requires gs-nyx and gs-nyx-plugin; use .venv-gs121-nyx "
                           "or install requirements/uv-topogym-gs121-nyx.txt in a CUDA environment.") from exc

    if str(renderer_cfg.type) != "nyx":
        raise ValueError("This camera requires env.renderer.type=nyx")
    path = asset_path(renderer_cfg.env_map)
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing HDRI: {path}; run scripts/prepare_nyx_studio.py or set "
            "TOPOGYM_VISUAL_ASSET_ROOT to the prepared visual asset directory"
        )
    environment = nps.EnvironmentMapAsset()
    environment.texture = str(path)
    environment.layout = nps.EEnvMapLayout.LongLat
    environment.multiplier = float(renderer_cfg.env_intensity)
    camera = camera_kwargs(camera_cfg, manifest)
    return scene.add_sensor(NyxCameraOptions(
        **camera,
        spp=int(renderer_cfg.spp),
        denoise=bool(renderer_cfg.denoise),
        # Nyx collects lights from all sensors into ONE shared scene.
        env_maps=(environment,) if include_lighting else (),
        lights=OmegaConf.to_container(renderer_cfg.lights, resolve=True) if include_lighting else [],
    ))


def rgb(sensor) -> np.ndarray:
    """Copy a single-environment frame out of Nyx's mutable CUDA cache."""
    frame = sensor.read().rgb
    # Genesis squeezes the environment axis when scene.build(n_envs=0).
    if frame.ndim == 3:
        return frame.cpu().numpy().copy()
    if frame.ndim != 4 or frame.shape[0] != 1:
        raise ValueError("The shared Nyx RGB camera expects a single environment")
    return frame[0].cpu().numpy().copy()


class NyxCamera:
    """Nyx RGB with the existing Genesis camera/recording/calibration interface.

    Genesis' raster camera owns calibration, dynamic pose and video buffers;
    RGB always comes from Nyx. Opt-in geometrical depth comes from Genesis'
    raster depth buffer at the identical camera pose, without rendering RGB.
    """

    def __init__(self, raster_camera, sensor):
        self.raster_camera = raster_camera
        self.sensor = sensor
        options = sensor._options
        self._last_transform = pos_lookat_up_to_T(
            np.asarray(options.pos), np.asarray(options.lookat), np.asarray(options.up),
        ).astype(np.float32)

    def __getattr__(self, name):
        return getattr(self.raster_camera, name)

    def invalidate_frame(self):
        """A new Env state can share a tick with a different historical branch."""
        self.sensor._stale = True

    def render(self, rgb=True, depth=False, segmentation=False, colorize_seg=False,
               normal=False, antialiasing=False, force_render=False):
        if segmentation or normal:
            raise NotImplementedError("Segmentation and normals are not exposed")
        if not rgb and not depth:
            return None, None, None, None
        from topogym.sensors.cameras import update_dynamic_camera

        update_dynamic_camera(self.raster_camera)
        # The native sensor follows attached links itself. For free/follow
        # cameras, propagate set_pose() changes, including same-step changes.
        transform = np.asarray(self.raster_camera.transform)
        if getattr(self.raster_camera, "_attached_link", None) is None:
            if self._last_transform is None or not np.array_equal(transform, self._last_transform):
                self.sensor.update_camera_pose(pos=transform[:3, 3],
                                               lookat=transform[:3, 3] - transform[:3, 2],
                                               up=transform[:3, 1])
        elif not np.array_equal(transform, self._last_transform):
            # Another camera's read may already have refreshed this sensor in
            # Nyx's shared pass. Invalidate only an actually outdated pose (e.g.
            # a diagnostic/reset that moves a link without advancing scene.t).
            submitted = None
            if self.sensor._attached_pos is not None:
                submitted = pos_lookat_up_to_T(*[
                    getattr(self.sensor, f"_attached_{key}")[0].cpu().numpy()
                    for key in ("pos", "lookat", "up")
                ])
            if submitted is None or not np.allclose(transform, submitted, rtol=0, atol=5e-6):
                self.sensor._stale = True
        self._last_transform = transform.copy()
        if force_render:
            self.sensor._stale = True
        frame = self._rgb() if rgb else None
        depth_frame = None
        if depth:
            # Explicit geometric depth modality; never substitute raster RGB.
            depth_frame = self.raster_camera.render(rgb=False, depth=True)[1]
        if rgb and self.raster_camera._in_recording:
            self.raster_camera._recorded_imgs.append(frame)
        return frame, depth_frame, None, None

    def _rgb(self):
        return rgb(self.sensor)
