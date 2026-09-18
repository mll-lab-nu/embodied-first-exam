"""Shared controller initialization for the single and dual arm embodiments."""
from .aloha import AlohaDualArmController
from .franka import FrankaPositionIKController


def initialize_robot_controller(*, scene, manifest, robot_cfg, robot_name="robot",
                                reset_home=True, settle_steps=None):
    name = str(robot_cfg.robot.name)
    classes = {"franka_panda": FrankaPositionIKController, "aloha": AlohaDualArmController}
    if name not in classes:
        raise ValueError(f"Unknown robot controller: {name!r}")
    controller = classes[name](scene=scene, robot=manifest.get(robot_name), cfg=robot_cfg)
    controller.configure()
    if reset_home:
        controller.reset_home(settle_steps=settle_steps)
    return controller
