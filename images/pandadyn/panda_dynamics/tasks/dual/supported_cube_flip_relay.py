import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import (
    box,
    container,
    set_initial,
    position,
    body,
    velocity,
)
from panda_dynamics.tasks.predicates import inertial_flip, face_up, supported


class SupportedCubeFlipRelay(PandaDynamicEnv):
    TASK = "D13-SupportedCubeFlipRelay"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("tray_support", "preparing_pusher"),
        ("moving_support", "impulse_pusher"),
        ("repositioning_support", "cleared_pusher"),
        ("moving_support", "impulse_pusher"),
        ("oriented_carrier", "cleared_pusher"),
    )
    ARM_SETUPS = (
        ArmSetup(
            "tray", (0.04, -0.035, 0.23), base=(-0.55, -0.22, 0), half=0.12, mass=0.22
        ),
        ArmSetup(
            "pusher",
            (0.16, 0.02, 0.268),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    PHASES = (
        "support_presentation",
        "first_inertial_flip",
        "second_contact_geometry",
        "second_inertial_flip",
        "oriented_output",
    )
    INSTRUCTION = "左盘提供移动支撑，右推杆两次短促施加角动量完成相邻面翻转，左盘缓冲并把正确朝向的方块运到输出区。"

    def build_task(self):
        h = self.params["cube_half"]
        self.objects["cube"] = box(
            self.scene,
            "cube",
            [h] * 3,
            [0.06, -0.035, 0.23 + h],
            mass=self.params["object_mass"],
            mu=0.65,
            restitution=0.25,
        )

    def reset_task(self):
        # v5: cube starts 20 mm toward the pusher side of the 0.12 m tray, so
        # two adjacent-face pivots toward -x (2 x 44 mm) end clear of the tray
        # adapter bar that overhangs the -x wall by 12 mm.
        set_initial(
            self.objects["cube"],
            [
                0.06,
                self.rng.uniform(-0.038, -0.032),
                0.23 + self.params["cube_half"] + 0.0005,
            ],
        )
        self.events.flags.update(
            target=[0.08, 0.015, 0.23],
            goal=[-0.04, 0.16, 0.25],
            first_cube_position=None,
        )

    def update_task(self):
        left = self.arms["panda-0"]
        obj = self.objects["cube"]
        local = (left.tool_pose.inv() * body(obj).entity_pose).p
        retained = max(abs(local[:2])) < 0.115 and local[2] > -0.01
        if not retained:
            self.events.fail("cube_lost_from_tray", self.time)
        if (
            self.phase == 0
            and supported(self, "cube", "left_tool")
            and np.linalg.norm(left.tool_pose.p - self.events.flags["target"]) < 0.025
        ):
            self.advance()
        elif self.phase == 1:
            if self.phase_hold(
                inertial_flip(self, "cube", "right_tool", "first", [1, 0, 0])
                and supported(self, "cube", "left_tool"),
                0.25,
            ):
                self.events.flags["first_cube_position"] = position(obj).tolist()
        elif self.phase == 2:
            if (
                supported(self, "cube", "left_tool")
                and np.linalg.norm(
                    position(obj) - self.events.flags["first_cube_position"]
                )
                > 0.025
                and not self.contact("cube", "right_tool")
            ):
                self.advance()
        elif self.phase == 3:
            self.phase_hold(
                inertial_flip(
                    self,
                    "cube",
                    "right_tool",
                    "second",
                    [0, 0, -1],
                    balance_axis=[1, 0, 0],
                )
                and supported(self, "cube", "left_tool"),
                0.25,
            )
        elif self.phase == 4:
            condition = (
                supported(self, "cube", "left_tool")
                and face_up(self, "cube", [0, 0, -1])
                and np.linalg.norm(left.tool_pose.p - self.events.flags["goal"]) < 0.025
                and self.relative_speed(obj, left.tool) < 0.04
            )
            if self.phase_hold(condition, 0.5):
                self.events.physical_success = True
