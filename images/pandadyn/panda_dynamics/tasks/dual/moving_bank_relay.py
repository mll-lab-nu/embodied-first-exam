import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import box, set_initial, position, velocity
from panda_dynamics.tasks.predicates import crossed


class MovingBankRelay(PandaDynamicEnv):
    TASK = "D06-MovingBankRelay"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("preparing_board", "striker"),
        ("rebound_operator", "preparing_receiver"),
        ("changing_board", "striker"),
        ("rebound_operator", "cleared_striker"),
        ("board_support", "cleared_striker"),
    )
    ARM_SETUPS = (
        ArmSetup(
            "paddle",
            (-0.015, 0.08, 0.045),
            base=(-0.55, -0.22, 0),
            half=0.075,
            mass=0.22,
        ),
        ArmSetup(
            "paddle",
            (0.27, -0.11, 0.045),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    PHASES = (
        "right_first_strike",
        "left_first_rebound",
        "right_recovery_strike",
        "left_changed_rebound",
        "terminal_goal",
    )
    INSTRUCTION = (
        "右臂两次击打，左臂用有限质量反弹板先后建立不同反弹路线，最终让同一冰球射门。"
    )

    def build_task(self):
        self.objects["puck"] = box(
            self.scene,
            "puck",
            [0.022, 0.022, 0.012],
            [0.12, -0.01, 0.013],
            mass=self.params["object_mass"],
            mu=0.012,
            restitution=0.65,
        )
        box(
            self.scene,
            "return_rail",
            [0.24, 0.008, 0.035],
            [0.15, 0.29, 0.035],
            static=True,
            restitution=0.7,
        )
        for i, y in enumerate((-0.01, 0.16)):
            for sign in (-1, 1):
                box(
                    self.scene,
                    f"route_{i}_{sign}",
                    [0.012, 0.025, 0.03],
                    [0.16, y + sign * 0.075, 0.03],
                    static=True,
                )
        box(
            self.scene,
            "backstop",
            [0.01, 0.07, 0.035],
            [0.48, 0.16, 0.035],
            static=True,
        )

    def reset_task(self):
        set_initial(
            self.objects["puck"],
            # Inside the route_0 aperture (posts at y < -0.06 and y > 0.04);
            # the 22 mm half-width puck keeps at least 8 mm clearance.
            [0.12, self.rng.uniform(-0.03, 0.01), 0.0125],
            [self.params["incoming_speed"], 0, 0],
        )
        self.events.flags.update(goal=[0.42, 0.16, 0.012])

    def update_task(self):
        if self.phase == 1 and crossed(
            self, "puck", [0.16, -0.01, 0], direction=-1, half=0.048
        ):
            self.events.once("first_route_aperture", self.time)
        if self.phase == 3 and crossed(
            self, "puck", [0.16, 0.16, 0], direction=-1, half=0.048
        ):
            self.events.once("second_route_aperture", self.time)
        if self.phase == 0 and self.contact("puck", "right_tool"):
            self.advance()
        elif (
            self.phase == 1
            and self.contact("puck", "left_tool")
            and self.events.has("first_route_aperture")
        ):
            left = self.arms["panda-0"]
            self.events.flags["first_board_pose"] = np.r_[
                left.tool_pose.p, left.tool_pose.q
            ].tolist()
            self.advance(impulse=self.contact("puck", "left_tool"))
        elif (
            self.phase == 2
            and self.contact("puck", "right_tool")
            and self.time - self.events.flags["phase_started"] > 0.06
        ):
            self.advance()
        elif (
            self.phase == 3
            and self.contact("puck", "left_tool")
            and self.events.has("second_route_aperture")
        ):
            first = np.array(self.events.flags["first_board_pose"])
            left = self.arms["panda-0"]
            if np.linalg.norm(left.tool_pose.p - first[:3]) > 0.035 and abs(
                np.dot(left.tool_pose.q, first[3:])
            ) < np.cos(0.12):
                self.advance(impulse=self.contact("puck", "left_tool"))
        elif (
            self.phase == 4
            and crossed(self, "puck", self.events.flags["goal"], half=0.055)
            and not self.contact("puck", "right_tool")
        ):
            self.advance()
            self.events.physical_success = True
