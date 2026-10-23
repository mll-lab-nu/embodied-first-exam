import numpy as np
import sapien
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import ball, container, set_initial, body, position
from panda_dynamics.tasks.predicates import cup_catch, containment


class MovingRampRelay(PandaDynamicEnv):
    TASK = "D05-MovingRampRelay"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("donor", "channel_operator"),
        ("relocating_receiver", "moving_outlet"),
        ("catcher", "channel_support"),
        ("donor", "changed_channel"),
        ("relocating_receiver", "moving_outlet"),
        ("catcher_deliverer", "channel_support"),
    )
    ARM_SETUPS = (
        ArmSetup("cup", (-0.04, -0.14, 0.23), base=(-0.55, -0.22, 0)),
        ArmSetup(
            "channel",
            (0.18, 0.10, 0.24),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            mount=(0.12, 0.12, 0.04),
            quaternion=(0, 0, 0, 1),
            half=0.14,
            mass=0.25,
        ),
    )
    PHASES = (
        "first_channel_entry",
        "first_moving_exit",
        "first_catch",
        "second_channel_entry",
        "second_moving_exit",
        "second_catch_and_delivery",
    )
    INSTRUCTION = (
        "左杯把球倒进右臂斜槽的入口一侧，球离开出口的瞬间出口须在移动（nominal ≥0.10 m/s，hard ≥0.25 m/s），"
        "球腾空后落回左杯并稳住；斜槽转到与第一次至少相差 0.3 rad 的朝向再来一次，"
        "最后左杯把同一球倒入高架方盆，球不碰杯、停稳 0.7 s。"
    )

    def build_task(self):
        self.objects["ball"] = ball(
            self.scene,
            "ball",
            self.params["radius"],
            self.params["object_mass"],
            self.params["restitution"],
        )
        self.basin = container(
            self.scene,
            "basin",
            [0.04, -0.24, 0.08],
            half=(0.075, 0.075),
            height=0.06,
            static=True,
        )

    def reset_task(self):
        # Seeded resting spot inside the upright left cup (interior half-width
        # 0.07 m minus the 0.018 m radius: nominal +/-0.015 m leaves >=0.037 m
        # of floor margin, hard +/-0.03 m leaves >=0.022 m).
        spread = self.params["ball_offset"]
        offset = self.rng.uniform(-spread, spread, 2)
        # Hard: the ball starts rolling (without slip) at ball_roll_speed in a
        # seeded horizontal direction inside the cup (nominal 0: no draw).
        roll = self.params["ball_roll_speed"]
        velocity, spin = np.zeros(3), np.zeros(3)
        if roll > 0:
            heading = self.rng.uniform(0.0, 2.0 * np.pi)
            velocity = roll * np.array([np.cos(heading), np.sin(heading), 0.0])
            spin = np.cross([0.0, 0.0, 1.0], velocity) / self.params["radius"]
        set_initial(
            self.objects["ball"],
            self.arms["panda-0"].tool_pose.p
            + [offset[0], offset[1], self.params["radius"] + 0.0005],
            velocity=velocity,
            angular=spin,
        )
        self.events.flags.update(first_channel_pose=None, target=[0.18, 0.10, 0.24])

    def outlet_speed(self, arm):
        """World speed of the channel's outlet end (tool-frame +x tip)."""
        rb = arm.tool_body
        tip = (arm.tool_pose * sapien.Pose([self.params["right_tool_half"], 0, 0])).p
        com = (rb.entity_pose * rb.cmass_local_pose).p
        v = rb.linear_velocity + np.cross(rb.angular_velocity, tip - com)
        return float(np.linalg.norm(v))

    def update_task(self):
        right = self.arms["panda-1"]
        local = (right.tool_pose.inv() * body(self.objects["ball"]).entity_pose).p
        if self.phase in (0, 3):
            if (
                self.contact("ball", "right_tool")
                and local[0] < -0.045
                and not self.contact("ball", "left_tool")
            ):
                if self.phase == 0:
                    self.events.flags["first_channel_pose"] = np.r_[
                        right.tool_pose.p, right.tool_pose.q
                    ].tolist()
                else:
                    initial = np.array(self.events.flags["first_channel_pose"])
                    difference = abs(np.dot(right.tool_pose.q, initial[3:]))
                    if difference > np.cos(0.15):
                        return
                self.advance(entry_local=local.tolist())
        elif self.phase in (1, 4):
            if local[0] > 0.13 and not self.contact("ball", "right_tool"):
                # "Moving outlet": the outlet end of the channel must be moving
                # at >= outlet_min_speed when the ball leaves it (both
                # difficulties; hard demands a faster outlet).
                speed = self.outlet_speed(right)
                if speed < self.params["outlet_min_speed"]:
                    self.events.fail("static_outlet_exit", self.time)
                    return
                self.advance(outlet_pose=right.tool_pose.p.tolist(), outlet_speed=speed)
        elif self.phase == 2 and cup_catch(self, "ball", "panda-0", "route1_receive"):
            self.advance()
        elif self.phase == 5:
            if cup_catch(self, "ball", "panda-0", "route2_receive"):
                self.events.once("second_received", self.time)
            if self.events.has("second_received") and self.phase_hold(
                containment(
                    self, "ball", self.basin, 0.075, 0.06, self.params["radius"]
                )
                and not self.contact("ball", "left_tool"),
                0.7,
            ):
                self.events.physical_success = True
