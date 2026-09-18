"""Nyx camera and pre-build surface overrides, tested with gs121/plugin 0.1.4.

Loaded by the shared presentation path only when Nyx is selected.
No rigid material, collision mesh, pose, mass, or controller is modified here.
"""

from fnmatch import fnmatchcase
from pathlib import Path

import genesis as gs
from genesis.utils.geom import pos_lookat_up_to_T
import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals


def asset_path(value) -> Path:
    """Resolve preset assets against the repository, independent of Hydra cwd."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path(__file__).resolve().parents[2] / path


def apply_finishes(manifest, rules) -> dict:
    """Apply explicit PBR finishes before build, to both entity and visual meshes.

    Nyx 0.1.4's geometry exporter drops roughness and metalness for ColorVisuals.
    Use texture visuals on explicitly styled meshes so its surface export path
    carries the full finish. Geometry, UV-independent color and physics stay intact.
    URDFs take a separate nested-scene path: child visuals may keep their source
    material despite the parent override. Those assets must embed their PBR
    finish at generation time (as the staged-lock key does).
    """
    applied = {}
    for name, entity in manifest.entities.items():
        finish = None
        for rule in rules:
            if fnmatchcase(name, str(rule.pattern)):
                finish = rule
        if finish is None:
            continue
        color = tuple(float(v) for v in finish.color)
        maps = {key: asset_path(finish[key]) for key in ("diffuse_map", "normal_map") if key in finish}
        for path in maps.values():
            if not path.is_file():
                raise FileNotFoundError(f"Missing material: {path}; run scripts/prepare_nyx_studio.py")
        surfaces = [entity.surface]
        for geom in entity.vgeoms:
            geom.vmesh.set_color(color)
            surfaces.append(geom.vmesh.surface)
        for surface in surfaces:
            surface.color = np.asarray(color)
            surface.diffuse_texture = gs.textures.ColorTexture(color=color)
            surface.metallic = float(finish.metallic)
            surface.roughness = float(finish.roughness)
            surface.roughness_texture = gs.textures.ColorTexture(color=(surface.roughness,))
            for key, slot in (("diffuse_map", "diffuse_texture"), ("normal_map", "normal_texture")):
                if key in maps:
                    setattr(surface, slot, gs.textures.ImageTexture(image_path=str(maps[key])))
        for geom in entity.vgeoms:
            # Preserve the primitive's UVs for image maps. Nyx's native boxes use
            # their built-in face UVs; the rasterizer reads these mesh UVs.
            uv = geom.vmesh.uvs
            if uv is None:
                uv = np.zeros((len(geom.vmesh.verts), 2))
            images = {}
            for key, slot in (("diffuse_map", "baseColorTexture"), ("normal_map", "normalTexture")):
                if key in maps:
                    with Image.open(maps[key]) as source:
                        images[slot] = source.convert("RGB")
            geom.vmesh.trimesh.visual = TextureVisuals(
                uv=uv,
                material=PBRMaterial(
                    baseColorFactor=(np.asarray((*color[:3], 1.0)) * 255).astype(np.uint8),
                    metallicFactor=float(finish.metallic),
                    roughnessFactor=float(finish.roughness),
                    **images,
                ),
            )
        applied[name] = {"color": color, "metallic": float(finish.metallic),
                         "roughness": float(finish.roughness), **{k: str(v) for k, v in maps.items()}}
    return applied


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
        raise RuntimeError("Nyx requires .venv-gs121-nyx; run INSTALL_NYX=1 bash env_setup_gs121.sh, "
                           "or select env.renderer.type=rasterizer.") from exc

    if str(renderer_cfg.type) != "nyx":
        raise ValueError("This camera requires env.renderer.type=nyx")
    path = asset_path(renderer_cfg.env_map)
    if not path.is_file():
        raise FileNotFoundError(f"Missing HDRI: {path}; run scripts/prepare_nyx_studio.py")
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
    its render method is never called by this adapter. Nyx 0.1.4 supplies RGB
    only, so requesting other modalities is an explicit error.
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

    def render(self, rgb=True, depth=False, segmentation=False, colorize_seg=False,
               normal=False, antialiasing=False, force_render=False):
        if depth or segmentation or normal:
            raise NotImplementedError("Nyx 0.1.4 supports RGB only; use env.renderer.type=rasterizer "
                                      "for depth, segmentation or normals.")
        if not rgb:
            return None, None, None, None
        from topogym.utils.recording import update_dynamic_camera

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
        frame = self._rgb()
        if self.raster_camera._in_recording:
            self.raster_camera._recorded_imgs.append(frame)
        return frame, None, None, None

    def _rgb(self):
        return rgb(self.sensor)
