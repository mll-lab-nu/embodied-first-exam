"""Resolve the packaged common tabletop profile without building a simulator."""

from pathlib import Path


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
