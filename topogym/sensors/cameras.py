"""Camera helpers shared by datasets, live recordings and task adapters."""


def create_camera(scene, config, entities, *, name="camera", include_robot=True):
    """Create and bind a sensor within the caller's Scene build lifecycle."""
    import numpy as np
    from genesis.utils.geom import pos_lookat_up_to_T

    camera = scene.add_camera(
        res=tuple(config.res),
        pos=tuple(config.pos),
        lookat=tuple(config.lookat),
        up=tuple(config.get("up", [0, 0, 1])),
        fov=float(config.fov),
        near=float(config.get("near", 0.1)),
        far=float(config.get("far", 20.0)),
        debug=bool(config.get("debug", False)),
        GUI=False,
    )
    attach = config.get("attach")
    if attach is not None and attach.get("enabled", True):
        entity_name = str(attach.get("entity", "robot"))
        if entity_name == "robot" and not include_robot:
            return camera
        link = entities.get(entity_name).get_link(str(attach.get("link", "hand")))
        transform = attach.get("offset_T")
        if transform is None:
            transform = pos_lookat_up_to_T(
                np.asarray(attach.get("offset_pos", [0, 0, 0])),
                np.asarray(attach.get("offset_lookat", [0.1, 0, 0])),
                np.asarray(attach.get("offset_up", [0, 0, 1])),
            )
        transform = np.asarray(transform, dtype=float)
        if transform.shape != (4, 4) or not np.isfinite(transform).all():
            raise ValueError(f"{name}: invalid camera mount transform")
        camera.attach(link, transform)
    return camera


def update_dynamic_camera(camera):
    if getattr(camera, "_attached_link", None) is not None:
        camera.move_to_attach()
    elif getattr(camera, "_followed_entity", None) is not None:
        camera.update_following()


def add_preview_camera(scene, manifest, *, res, pos, lookat, fov, renderer="nyx"):
    """Give standalone fixture probes the shared room without changing physics."""
    from topogym.world.visuals.presentation import (
        default_presentation_config,
        prepare_presentation,
    )

    cfg = default_presentation_config()
    if renderer != "nyx":
        raise ValueError("Fixture previews use the shared Nyx renderer")
    cfg.renderer.type = renderer
    cfg.cameras = {
        "preview": dict(
            res=res, pos=pos, lookat=lookat, fov=fov, up=[0, 0, 1], near=0.1, far=20.0
        )
    }
    camera = create_camera(
        scene, cfg.cameras.preview, manifest.entities, name="preview"
    )
    cameras = {"preview": camera}
    prepare_presentation(scene, manifest, cfg, cameras)
    return cameras["preview"]
