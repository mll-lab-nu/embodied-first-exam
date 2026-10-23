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
    INSTRUCTION = "左盘托住方块，在两次翻转时都保持移动、两次之间带方块换位；右推杆每次短促推击并在方块越过平衡棱前离开，使方块靠惯性翻到相邻面、最终原底面朝上；左盘再把方块运到输出区停稳。"

    def build_task(self):
        h = self.params["cube_half"]
        self.objects["cube"] = box(
            self.scene,
            "cube",
            [h] * 3,
            [0.06, -0.035, 0.23 + h],
            mass=self.params["object_mass"],
            mu=self.params["cube_friction"],
            restitution=self.params["cube_restitution"],
        )

    def reset_task(self):
        # v5: cube starts 20 mm toward the pusher side of the 0.12 m tray, so
        # two adjacent-face pivots toward -x (2 x 44 mm) end clear of the tray
        # adapter bar that overhangs the -x wall by 12 mm.
        # v6: seeded start spread is configurable (hard: wider x/y and a yaw);
        # nominal keeps the single y draw U(-0.038, -0.032) and x = 0.06.
        p = self.params
        y = self.rng.uniform(
            round(-0.035 - p["cube_y_spread"], 6), round(-0.035 + p["cube_y_spread"], 6)
        )
        x = 0.06
        if p["cube_x_spread"] > 0:
            x += self.rng.uniform(-p["cube_x_spread"], p["cube_x_spread"])
        q = (1, 0, 0, 0)
        if p["cube_yaw_spread"] > 0:
            yaw = self.rng.uniform(-p["cube_yaw_spread"], p["cube_yaw_spread"])
            q = (np.cos(yaw / 2), 0, 0, np.sin(yaw / 2))
        set_initial(
            self.objects["cube"],
            [x, y, 0.23 + p["cube_half"] + 0.0005],
            q=q,
        )
        self.events.flags.update(
            target=[0.08, 0.015, 0.23],
            goal=[-0.04, 0.16, 0.25],
            first_cube_position=None,
        )

    def moving_support(self, key):
        """v6: the left tray must be moving while it supports each flip.

        A push segment starts at the first pusher-cube contact after a contact
        gap > 20 ms (the release gap used by inertial_flip). From that onset
        until the cube passes the balance edge, the measured tray speed must
        never drop below support_min_speed; otherwise the run fails with
        static_support_flip. Call before inertial_flip on every step.
        """
        flags = self.events.flags
        if flags.get(key + ":support_judged"):
            return
        speed = float(np.linalg.norm(self.arms["panda-0"].tool_body.linear_velocity))
        if self.contact("cube", "right_tool") > 0:
            last = flags.get(key + ":push_last_contact")
            if last is None or self.time - last > 0.02:
                flags[key + ":push_onset"] = self.time
                flags[key + ":support_min_speed"] = speed
            flags[key + ":push_last_contact"] = self.time
        if key + ":push_onset" in flags:
            flags[key + ":support_min_speed"] = min(flags[key + ":support_min_speed"], speed)

    def judge_support(self, key):
        flags = self.events.flags
        if flags.get(key + ":support_judged") or not self.events.has(key + ":inertial_crossing"):
            return
        flags[key + ":support_judged"] = True
        minimum = flags.get(key + ":support_min_speed", 0.0)
        self.events.once(
            key + ":moving_support",
            self.time,
            min_tray_speed=minimum,
            push_onset=flags.get(key + ":push_onset"),
            required=self.params["support_min_speed"],
        )
        if minimum < self.params["support_min_speed"]:
            self.events.fail("static_support_flip", self.time)

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
            self.moving_support("first")
            flipped = inertial_flip(self, "cube", "right_tool", "first", [1, 0, 0])
            self.judge_support("first")
            if self.phase_hold(
                flipped and supported(self, "cube", "left_tool"),
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
            self.moving_support("second")
            flipped = inertial_flip(
                self,
                "cube",
                "right_tool",
                "second",
                [0, 0, -1],
                balance_axis=[1, 0, 0],
            )
            self.judge_support("second")
            self.phase_hold(
                flipped and supported(self, "cube", "left_tool"),
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
