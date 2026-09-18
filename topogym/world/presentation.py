"""Shared pre-build background, finishes and RGB camera backend wiring."""
from pathlib import Path

from omegaconf import OmegaConf


def default_presentation_config():
    """The same preset used by Hydra, for standalone fixture scenes."""
    return OmegaConf.load(Path(__file__).resolve().parents[2] /
                          "configs/presentation_configs/nyx_lab.yaml")


def prepare_presentation(scene, manifest, env_cfg, cameras):
    """Call after task entities/cameras exist and before scene.build().

    Mutate the shared camera mapping so recording and dataset consumers keep
    their camera.render() contract. Raster cameras remain available for rig
    calibration and explicit comparisons via camera.raster_camera.
    """
    from . import nyx_lab

    presentation = env_cfg.get("presentation", {})
    background = str(presentation.get("background", "checker"))
    dressing = nyx_lab.add_lab(scene, manifest, background)
    backend = str(env_cfg.get("renderer", {}).get("type", "auto"))
    if backend == "auto":
        backend = "batch" if int(env_cfg.get("sim", {}).get("n_envs", 0)) > 0 else "rasterizer"
    for camera in cameras.values():
        camera.renderer_type = backend
        camera.presentation_background = background
    result = dict(renderer=backend, background=background, dressing=dressing, finishes={})
    if backend != "nyx":
        return result

    from . import nyx

    rules = list(presentation.get("appearance", [])) + list(env_cfg.get("appearance", []))
    result["finishes"] = nyx.apply_finishes(manifest, rules)
    for index, (name, camera) in enumerate(list(cameras.items())):
        if name in env_cfg.cameras:
            camera_cfg = OmegaConf.create(OmegaConf.to_container(env_cfg.cameras[name], resolve=True))
        else:
            # Task-local inspection cameras can be appended before finalize().
            values = {key: getattr(camera, key) for key in ("res", "fov", "near", "far")}
            # Genesis 1.2.1's public world-pose properties exist only after build.
            values.update({key: getattr(camera, f"_initial_{key}").cpu().tolist()
                           for key in ("pos", "lookat", "up")})
            camera_cfg = OmegaConf.create(values)
        # Mirror the builder's static fallback when a robot is omitted.
        attach = camera_cfg.get("attach")
        if attach is not None and str(attach.get("entity", "robot")) == "robot" and "robot" not in manifest.entities:
            camera_cfg.attach.enabled = False
        sensor = nyx.add_camera(scene, env_cfg.renderer, camera_cfg, manifest, include_lighting=index == 0)
        cameras[name] = nyx.NyxCamera(camera, sensor)
    return result


def add_preview_camera(scene, manifest, *, res, pos, lookat, fov, renderer="nyx"):
    """Give standalone fixture probes the shared room without changing physics."""
    cfg = default_presentation_config()
    if renderer not in {"nyx", "rasterizer"}:
        raise ValueError("Fixture preview renderer must be nyx or rasterizer")
    cfg.renderer.type = renderer
    camera = scene.add_camera(res=res, pos=pos, lookat=lookat, fov=fov, GUI=False)
    cfg.cameras = {"preview": dict(res=res, pos=pos, lookat=lookat, fov=fov, up=[0, 0, 1],
                                   near=camera.near, far=camera.far)}
    cameras = {"preview": camera}
    prepare_presentation(scene, manifest, cfg, cameras)
    return cameras["preview"]
