"""Resolve the packaged common tabletop profile without building a simulator."""

from pathlib import Path


_TASK_CAMERA_PROFILES = {
    "lock_picking": "lock_picking_observation",
    "buzz_wire_3d": "buzz_wire_3d_observation",
}


def load_scene_config(config):
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf

    from .registry import task_registration

    robot_id = (
        config.robot_id
        if config.robot_id != "auto"
        else task_registration(config.task_id).default_robot
    )
    root = Path(__file__).parent / "profiles"
    with initialize_config_dir(config_dir=str(root.resolve()), version_base="1.3"):
        scene = compose(config_name=f"tabletop_{robot_id}")
    # Task framing is calibrated for the standard Panda scene. Keep the robot's
    # resolution, wrist mount and observation keys when merging fixed views.
    camera_profile = _TASK_CAMERA_PROFILES.get(config.task_id)
    if camera_profile is not None and robot_id == "panda_robotiq":
        scene.env = OmegaConf.merge(
            scene.env, OmegaConf.load(root / "camera_configs" / f"{camera_profile}.yaml")
        )
        primary = scene.env.cameras.agentview
        scene.env.viewer.camera_pos = primary.pos
        scene.env.viewer.camera_lookat = primary.lookat
        scene.env.viewer.camera_fov = primary.fov
    scene.env.genesis.backend = config.compute_backend
    scene.env.genesis.precision = config.precision
    scene.env.sim.dt = config.physics_dt_s
    scene.env.sim.substeps = config.solver_substeps
    scene.env.sim.n_envs = 0
    scene.env.renderer.type = config.render_backend
    scene.robot_control.home.settle_steps = 0
    scene.robot_control.robot.asset_root = (
        None if config.asset_root is None else str(config.asset_root)
    )
    # Replace the inherited rig before building cameras. Extra parent views must
    # not be rendered and then merely hidden from the public observation.
    selected = list(scene.env.camera_rig.observation_cameras)
    scene.env.cameras = {name: OmegaConf.to_container(scene.env.cameras[name], resolve=True)
                         for name in selected}
    if not config.enable_rgb:
        scene.env.cameras = {}
    OmegaConf.resolve(scene)
    return scene
