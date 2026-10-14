import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import ball, set_initial, position, velocity
from panda_dynamics.props.fixtures import single_axis
from panda_dynamics.tasks.predicates import cup_catch, free_interval, containment


class TossRecatchDelivery(PandaDynamicEnv):
    TASK = "S09-TossRecatchDelivery"
    NAMESPACE = "PandaMultiStage"
    TOOL = "toss_cup"  # Permanently open +x pouring lip; unchanged for all stages.
    TOOL_START = (0.03, -0.15, 0.22)
    # v5: a real self toss needs a sustained > g downward cup acceleration;
    # the low jerk fraction keeps j2/j4 from overshooting at the reversal.
    REFERENCE_ACCELERATION = 0.9
    REFERENCE_JERK = 0.02
    PHASES = (
        "initial_catch",
        "launch_region",
        "self_toss",
        "displaced_recatch",
        "moving_receiver_delivery",
    )
    INSTRUCTION = (
        "接住来球后到达发射区，用同一浅杯自然抛起、侧移并再接住，最后释放到经过的容器。"
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
            [0.23, -0.15, 0.08],
            speed=self.params["fixture_speed"],
            force=8.0,
        )

    def reset_task(self):
        t = self.params["preview"]
        y = self.rng.uniform(-0.07, -0.03)
        speed = self.params["incoming_speed"]
        set_initial(
            self.objects["ball"],
            [0.05 + speed * t, y, 0.39],
            [
                -speed,
                0,
                (0.22 + 0.028 + self.params["radius"] - 0.39 + 4.905 * t * t) / t,
            ],
        )
        self.fixtures["cart"].reset(
            self.rng.uniform(-0.03, 0.03), self.params["fixture_speed"]
        )
        self.events.flags.update(
            # v5: launch region moved to where the arm has > g downward authority
            # (was [0.03, 0.07, 0.24], max ~10.6 m/s^2 even at 100% FER).
            target=[0.05, y, 0.22], launch_region=[0.30, -0.10, 0.30]
        )
        self.events.emit("release", 0.0, object="ball")

    def update_task(self):
        if self.phase == 0 and cup_catch(self, "ball", "panda-0", "first"):
            self.advance()
        elif (
            self.phase == 1
            and np.linalg.norm(self.tool_pose.p - self.events.flags["launch_region"])
            < 0.025
        ):
            self.events.flags["launch_cup_position"] = self.tool_pose.p.tolist()
            self.advance()
        elif self.phase == 2:
            # v5: a genuine self toss. The ball must leave the cup FLOOR while
            # the cup is near level, moving upward in the world (vz > 0.2 m/s)
            # and away from the floor relative to the cup (> 0.03 m/s along the
            # floor normal); it must then stay contact-free for >= 0.06 s and
            # rise more than lip + radius above the floor both in the cup frame
            # and in world height. Merely lifting the cup with the ball, or
            # pouring it over the open lip, cannot satisfy this. The original
            # active_upward_launch condition is still required as well.
            ball = self.objects["ball"]
            p, v = position(ball), velocity(ball)
            lip, radius = self.params["tool_height"], self.params["radius"]
            flags = self.events.flags
            # Original condition, kept as an additional conjunct (strict tightening).
            if v[2] > .2 and p[2] > flags["launch_cup_position"][2] + .06:
                self.events.once("active_upward_launch", self.time)
            local = self.local_position(ball)
            airborne = not any("ball" in pair for pair in self.contacts)
            if self.contact("ball", "tool") > 0:
                flags["toss_last_cup_contact"] = self.time
                flags.pop("toss_separation", None)
            elif (
                airborne
                and "toss_separation" not in flags
                and self.time - flags.get("toss_last_cup_contact", -1.0) <= 0.06
                and local[2] < radius + 0.012
            ):
                pose = self.tool_pose
                up = pose.to_transformation_matrix()[:3, 2]
                rb = self.tool_body
                com = (rb.entity_pose * rb.cmass_local_pose).p
                floor_v = rb.linear_velocity + np.cross(rb.angular_velocity, p - com)
                normal_speed = float((v - floor_v) @ up)
                if v[2] > 0.2 and normal_speed > 0.03 and up[2] > np.cos(0.35):
                    flags["toss_separation"] = dict(time=self.time, cup=pose.p.tolist())
                    self.events.emit("ball_separation", self.time, ball_vz=float(v[2]),
                                     relative_normal_speed=normal_speed)
            separation = flags.get("toss_separation")
            if separation is not None and not airborne and self.contact("ball", "tool") == 0:
                flags.pop("toss_separation", None)
            elif separation is not None and airborne:
                clearance = min(float(local[2]), float(p[2] - self.tool_pose.p[2]))
                if (
                    self.events.has("active_upward_launch")
                    and self.time - separation["time"] >= 0.06
                    and clearance > lip + radius
                ):
                    flags["release_cup_position"] = separation["cup"]
                    self.advance(clearance=clearance)
        elif self.phase == 3:
            if (
                cup_catch(self, "ball", "panda-0", "recatch")
                and np.linalg.norm(
                    self.tool_pose.p[:2]
                    - np.array(self.events.flags["release_cup_position"])[:2]
                )
                > 0.03
            ):
                self.advance()
        elif self.phase == 4:
            cart = self.fixtures["cart"]
            if self.phase_hold(
                containment(self, "ball", cart.link, 0.075, 0.06, self.params["radius"])
                and not self.contact("ball", "tool")
                and abs(cart.v) > 0.02,
                0.7,
            ):
                self.events.physical_success = True
