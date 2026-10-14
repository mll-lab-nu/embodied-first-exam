import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import ball, set_initial, position
from panda_dynamics.props.fixtures import single_axis
from panda_dynamics.tasks.predicates import cup_catch, free_interval, containment


class ReciprocalCupRelay(PandaDynamicEnv):
    TASK = "D01-ReciprocalCupRelay"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("catcher", "preparing_receiver"),
        ("donor", "moving_receiver"),
        ("clearing_donor", "catcher"),
        ("preparing_receiver", "loaded_carrier"),
        ("moving_receiver", "donor"),
        ("catcher_deliverer", "cleared_partner"),
    )
    ARM_SETUPS = (
        ArmSetup("cup", (0.02, -0.18, 0.22), base=(-0.55, -0.22, 0)),
        ArmSetup(
            "cup",
            (0.19, 0.18, 0.22),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    PHASES = (
        "left_initial_catch",
        "left_to_right_flight",
        "right_catch",
        "second_region",
        "right_to_left_flight",
        "left_catch_and_deliver",
    )
    INSTRUCTION = (
        "左杯接球后抛给移动的右杯，右杯在第二转移区抛回左杯，左杯接住并送入运动容器。"
    )

    def build_task(self):
        self.objects["ball"] = ball(
            self.scene,
            "ball",
            self.params["radius"],
            self.params["object_mass"],
            self.params["restitution"],
        )
        self.fixtures["cart"] = single_axis(
            self.scene,
            "cart",
            [-0.10, -0.29, 0.05],
            speed=self.params["fixture_speed"],
            force=8.0,
        )

    def reset_task(self):
        t = self.params["preview"]
        speed = self.params["incoming_speed"]
        y = self.rng.uniform(-0.11, -0.07)
        set_initial(
            self.objects["ball"],
            [0.03 + speed * t, y, 0.39],
            [
                -speed,
                0,
                (0.22 + 0.028 + self.params["radius"] - 0.39 + 4.905 * t * t) / t,
            ],
        )
        self.events.flags.update(
            target=[0.03, y, 0.22],
            transfer_a=[0.14, 0.02, 0.22],
            transfer_b=[0.0, 0.11, 0.22],
            left_start=self.arms["panda-0"].tool_pose.p.tolist(),
            right_start=self.arms["panda-1"].tool_pose.p.tolist(),
        )
        self.fixtures["cart"].reset(
            self.rng.uniform(-0.02, 0.02), self.params["fixture_speed"]
        )
        self.events.emit("release", 0.0, object="ball")

    def update_task(self):
        left, right = self.arms.values()
        obj = self.objects["ball"]
        if self.phase == 0 and cup_catch(self, "ball", "panda-0", "initial"):
            self.advance()
        elif self.phase == 1:
            if (
                free_interval(self, "ball", "first_transfer_air") > 0.045
                and position(obj)[2] > 0.30
            ):
                self.advance(launch_position=position(obj).tolist())
        elif self.phase == 2 and cup_catch(self, "ball", "panda-1", "right_receive"):
            displacement = float(
                np.linalg.norm(right.tool_pose.p - self.events.flags["right_start"])
            )
            if displacement > 0.04:
                self.advance(receiver_relocation=displacement)
        elif self.phase == 3:
            if np.linalg.norm(
                right.tool_pose.p - [0.13, 0.15, 0.24]
            ) < 0.035 and containment(
                self, "ball", right.tool, 0.06, 0.028, self.params["radius"]
            ):
                self.advance()
        elif self.phase == 4:
            if (
                free_interval(self, "ball", "reverse_transfer_air") > 0.045
                and position(obj)[2] > 0.31
            ):
                self.advance()
        elif self.phase == 5:
            if cup_catch(self, "ball", "panda-0", "left_receive"):
                self.events.once("reverse_catch", self.time)
            cart = self.fixtures["cart"]
            if self.events.has("reverse_catch") and self.events.hold(
                "final",
                containment(self, "ball", cart.link, 0.075, 0.06, self.params["radius"])
                and abs(cart.v) > 0.02
                and not self.contact("ball", left.contact_name),
                self.time,
                0.7,
            ):
                self.advance()
                self.events.physical_success = True
