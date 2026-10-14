import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import box, set_initial, position, velocity
from panda_dynamics.tasks.predicates import crossed


class CooperativePuckCourse(PandaDynamicEnv):
    TASK = "D03-CooperativePuckCourse"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    # v5: back to the base-class planning fractions (were .25/.015). The lowered
    # fractions made the Ruckig reference overshoot contact-height paddle moves
    # by ~7 mm (paddle commanded to z=.034 reached .0267 and touched the table);
    # measured FER velocity/acceleration/jerk/torque limits are still enforced.
    REFERENCE_ACCELERATION = .55
    REFERENCE_JERK = .05
    WRIST_DAMPING = (24.,20.,14.)
    ROLE_LABELS = (
        ("striker", "preparing_receiver"),
        ("preparing_receiver", "striker"),
        ("striker", "preparing_receiver"),
        ("cleared_partner", "goal_striker"),
    )
    ARM_SETUPS = (
        ArmSetup("paddle", (-0.05, -0.18, 0.048), base=(-0.55, -0.22, 0)),
        ArmSetup(
            "paddle",
            (0.28, 0.12, 0.048),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    PHASES = (
        "left_first_pass",
        "right_return_route",
        "left_diagonal_pass",
        "right_terminal_shot",
    )
    INSTRUCTION = (
        "左、右、左、右依次击打同一冰球，经过三个不同的实体通道，最后由右侧射入球门。"
    )

    def build_task(self):
        self.objects["puck"] = box(
            self.scene,
            "puck",
            [0.022, 0.022, 0.012],
            [0.22, -0.13, 0.013],
            mass=self.params["object_mass"],
            mu=0.015,
            restitution=0.55,
        )
        for index, (x, y) in enumerate(
            ((0.12, -0.22), (0.12, -0.045), (0.12, 0.095), (0.12, 0.26))
        ):
            box(
                self.scene,
                f"route_post_{index}",
                [0.016, 0.025, 0.035],
                [x, y, 0.035],
                static=True,
                restitution=0.7,
            )
        box(
            self.scene,
            "return_rail",
            [0.26, 0.008, 0.035],
            [0.14, 0.31, 0.035],
            static=True,
            restitution=0.7,
        )
        box(
            self.scene,
            "goal_backstop",
            [0.01, 0.065, 0.035],
            [0.53, -0.02, 0.035],
            static=True,
        )

    def reset_task(self):
        set_initial(
            self.objects["puck"],
            [0.23, -0.13 + self.rng.uniform(-0.014, 0.014), 0.0125],
            [-self.params["incoming_speed"], 0, 0],
        )
        self.events.flags.update(
            goal=[0.46, -0.02, 0.012],
            passages=[[0.12, -0.13, 0.012], [0.12, 0.19, 0.012], [0.12, 0.025, 0.012]],
            last_strike=-10.0,
        )

    def update_task(self):
        stage = self.phase
        name = ("left_tool", "right_tool", "left_tool", "right_tool")[min(stage, 3)]
        key = f"strike_{stage}"
        arm = self.arms["panda-0" if stage % 2 == 0 else "panda-1"]
        if (
            self.contact("puck", name)
            and not self.events.has(key)
            and np.linalg.norm(arm.tool_body.linear_velocity) > 0.035
        ):
            if self.time - self.events.flags["last_strike"] > 0.06:
                self.events.once(
                    key, self.time, tool=name, impulse=self.contact("puck", name)
                )
                self.events.flags["last_strike"] = self.time
        if not self.events.has(key):
            return
        free = (
            not self.contact("puck", name)
            and self.time - self.events.first_time(key) > 0.035
        )
        if (
            stage < 3
            and free
            and crossed(
                self,
                "puck",
                self.events.flags["passages"][stage],
                direction=1 if stage != 1 else -1,
                half=0.055,
            )
        ):
            self.advance(outgoing_velocity=velocity(self.objects["puck"]).tolist())
        elif (
            stage == 3
            and free
            and crossed(self, "puck", self.events.flags["goal"], half=0.05)
        ):
            self.advance()
            self.events.physical_success = True
