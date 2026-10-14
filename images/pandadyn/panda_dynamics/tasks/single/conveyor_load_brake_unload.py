from ruckig import Synchronization
import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import (
    box,
    container,
    set_initial,
    position,
    velocity,
    body,
)
from panda_dynamics.props.mechanisms import roller_conveyor, coasting_carriage
from panda_dynamics.tasks.predicates import bilateral_grip


class ConveyorLoadBrakeUnload(PandaDynamicEnv):
    TASK = "S07-ConveyorLoadBrakeUnload"
    NAMESPACE = "PandaMultiStage"
    TOOL = None
    TOOL_START = (-0.13, -0.11, 0.21)
    ALLOW_FINGER_CONTACTS = True
    ALLOWED_FINGER_FIXTURES = ("carriage",)
    PHASES = (
        "moving_acquisition",
        "loaded_carriage_release",
        "handle_braking",
        "payload_regrasp",
        "dock_deposit",
    )
    INSTRUCTION = (
        "从实际滚轮带抓起零件，放到滑行车并松手，再抓住车柄制动，重抓零件放入码头。"
    )

    def build_task(self):
        self.fixtures["conveyor"] = roller_conveyor(
            self.scene, "conveyor", [-0.13, -0.10, 0.1], self.params["incoming_speed"]
        )
        self.fixtures["carriage"] = coasting_carriage(
            self.scene, "carriage", [0.12, 0, 0.11]
        )
        self.objects["part"] = box(
            self.scene,
            "part",
            [0.018] * 3,
            [-0.13, -0.15, 0.133],
            mass=self.params["object_mass"],
            mu=0.65,
        )
        self.dock = container(
            self.scene,
            "dock",
            [0.20, -0.23, 0.015],
            half=(0.065, 0.06),
            height=0.04,
            static=True,
        )

    def reset_task(self):
        # Separate hand timing from arm tracking, with the same rate/effort limits.
        self.servo.input.per_dof_synchronization = [Synchronization.TimeIfNecessary]*7 + [Synchronization.No]*2
        self.fixtures["conveyor"].reset()
        self.fixtures["carriage"].reset(
            -0.16 + self.rng.uniform(-0.01, 0.01), self.params["fixture_speed"]
        )
        set_initial(
            self.objects["part"],
            [-0.13, -0.16, 0.133],
            [0, self.params["incoming_speed"], 0],
        )
        q = self.robot.qpos.copy()
        q[7:] = 0.024
        self.robot.set_qpos(q)
        self.servo.reset()

    def update_task(self):
        obj = self.objects["part"]
        p = position(obj)
        cart = self.fixtures["carriage"]
        grip = bilateral_grip(self, "part")
        if self.phase == 0:
            if grip and np.linalg.norm(velocity(obj)) > 0.025:
                self.events.once(
                    "moving_grip", self.time, speed=float(np.linalg.norm(velocity(obj)))
                )
            if grip and p[2] > 0.20 and self.events.has("moving_grip"):
                self.advance()
        elif self.phase == 1:
            if self.contact("part", "carriage") and not grip and abs(cart.v) > 0.025:
                self.events.flags["unbraked_speed"] = abs(cart.v)
                self.advance()
        elif self.phase == 2:
            handle = bilateral_grip(self, "carriage")
            local = (body(cart.link).entity_pose.inv() * body(obj).entity_pose).p
            if self.phase_hold(
                handle
                and abs(cart.v) < 0.012
                and max(abs(local[:2])) < 0.07
                and self.contact("part", "carriage") > 0,
                0.25,
                braked_speed=abs(cart.v),
            ):
                self.events.once("robot_braked_carriage", self.time)
        elif (
            self.phase == 3
            and grip
            and p[2] > 0.20
            and not self.contact("part", "carriage")
        ):
            self.advance()
        elif self.phase == 4:
            if self.phase_hold(
                not grip
                and self.contact("part", "dock") > 0
                and np.linalg.norm(p[:2] - [0.20, -0.23]) < 0.04
                and np.linalg.norm(velocity(obj)) < 0.03,
                0.5,
            ):
                self.events.physical_success = True
        if self.phase in (2, 3) and p[2] < 0.09:
            self.events.fail("payload_spill", self.time)
