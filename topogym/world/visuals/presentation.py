"""Shared pre-build background, finishes and RGB camera backend wiring."""

from pathlib import Path

from omegaconf import OmegaConf


def default_presentation_config():
    """The same preset used by Hydra, for standalone fixture scenes."""
    return OmegaConf.load(
        Path(__file__).resolve().parents[2]
        / "config/profiles/presentation_configs/compact_lab.yaml"
    )


def prepare_presentation(scene, manifest, env_cfg, cameras):
    """Call after task entities/cameras exist and before scene.build().

    Mutate the shared camera mapping so recording and dataset consumers keep
    their camera.render() contract. Raster cameras remain available for rig
    calibration and explicit comparisons via camera.raster_camera.
    """
    from topogym.world.lab import BACKGROUND_ID, add_lab

    presentation = env_cfg.get("presentation", {})
    background = str(presentation.get("background", BACKGROUND_ID))
    if background != BACKGROUND_ID:
        raise ValueError("Only the compact_lab background is supported")
    backend = str(env_cfg.get("renderer", {}).get("type", "nyx"))
    if backend != "nyx":
        raise ValueError("Simulator RGB requires the Nyx renderer")
    dressing = add_lab(scene, manifest)
    for camera in cameras.values():
        camera.renderer_type = backend
        camera.presentation_background = background
    result = dict(
        renderer=backend if cameras else "none", background=background,
        dressing=dressing, finishes={}
    )
    if not cameras:
        return result

    from topogym.world.visuals import nyx
    from topogym.sensors.renderers import nyx as nyx_camera

    rules = list(presentation.get("appearance", [])) + list(
        env_cfg.get("appearance", [])
    )
    result["finishes"] = nyx.apply_finishes(manifest, rules)
    for index, (name, camera) in enumerate(list(cameras.items())):
        if name in env_cfg.cameras:
            camera_cfg = OmegaConf.create(
                OmegaConf.to_container(env_cfg.cameras[name], resolve=True)
            )
        else:
            # Task-local inspection cameras can be appended before finalize().
            values = {
                key: getattr(camera, key) for key in ("res", "fov", "near", "far")
            }
            # Genesis 1.2.1's public world-pose properties exist only after build.
            values.update(
                {
                    key: getattr(camera, f"_initial_{key}").cpu().tolist()
                    for key in ("pos", "lookat", "up")
                }
            )
            camera_cfg = OmegaConf.create(values)
        # Mirror the builder's static fallback when a robot is omitted.
        attach = camera_cfg.get("attach")
        if (
            attach is not None
            and str(attach.get("entity", "robot")) == "robot"
            and "robot" not in manifest.entities
        ):
            camera_cfg.attach.enabled = False
        sensor = nyx_camera.add_camera(
            scene, env_cfg.renderer, camera_cfg, manifest, include_lighting=index == 0
        )
        cameras[name] = nyx_camera.NyxCamera(camera, sensor)
    return result
