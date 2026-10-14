from ruckig import Synchronization
import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import box, set_initial, position, velocity, body
from panda_dynamics.props.fixtures import single_axis
from panda_dynamics.props.mechanisms import roller_conveyor
from panda_dynamics.tasks.predicates import bilateral_grip


class MovingGraspHandover(PandaDynamicEnv):
    TASK = "D10-MovingGraspHandover"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("moving_grasper", "preparing_receiver"),
        ("moving_donor", "tracking_receiver"),
        ("donor_grip", "receiver_grip"),
        ("releasing_donor", "sole_support"),
        ("cleared_donor", "slot_deliverer"),
    )
    ARM_SETUPS = (
        ArmSetup(None, (-0.10, -0.10, 0.20), base=(-0.55, -0.23, 0)),
        ArmSetup(None, (0.19, 0.16, 0.23), base=(0.74, 0.23, 0), yaw=np.pi),
    )
    ALLOW_FINGER_CONTACTS = True
    PHASES = (
        "moving_pickup",
        "moving_presentation",
        "overlapping_grips",
        "donor_release",
        "receiver_slot_delivery",
    )
    INSTRUCTION = "左手从真实滚轮带抓起长零件，在运动中交给右手，左手完全松开后由右手放入运动接收槽。"

    def build_task(self):
        self.fixtures["conveyor"] = roller_conveyor(
            self.scene, "conveyor", [-0.08, -0.08, 0.10], self.params["incoming_speed"]
        )
        self.objects["part"] = box(
            self.scene,
            "part",
            [0.11, 0.017, 0.018],
            [-0.08, -0.13, 0.134],
            mass=0.065,
            mu=0.8,
        )
        self.fixtures["slot"] = single_axis(
            self.scene,
            "slot",
            [0.24, 0.03, 0.10],
            speed=self.params["fixture_speed"],
            force=8.0,
            cup_half=(0.125, 0.065),
        )

    def reset_task(self):
        set_initial(
            self.objects["part"],
            [-0.08, self.rng.uniform(-0.15, -0.12), 0.133],
            [0, self.params["incoming_speed"], 0],
        )
        self.fixtures["conveyor"].reset()
        self.fixtures["slot"].reset(
            self.rng.uniform(-0.06, -0.02), self.params["fixture_speed"]
        )
        for arm in self.arms.values():
            q = arm.robot.qpos.copy()
            q[7:] = 0.024
            arm.robot.set_qpos(q)
            arm.servo.reset()
            # The real hand closes while the arm continues tracking the belt.
            arm.servo.input.per_dof_synchronization = [Synchronization.TimeIfNecessary]*7 + [Synchronization.No]*2
        self.events.flags.update(
            target=[0.09, 0.05, 0.24], grip_overlap_s=0.0, receiver_only_s=0.0
        )

    def update_task(self):
        obj = self.objects["part"]
        p = position(obj)
        speed = float(np.linalg.norm(velocity(obj)))
        left = bilateral_grip(self, "part", "panda-0")
        right = bilateral_grip(self, "part", "panda-1")
        if self.phase == 0:
            if left and speed > 0.025:
                self.events.once("moving_grip", self.time, speed=speed)
            if left and p[2] > 0.21 and self.events.has("moving_grip"):
                self.advance()
        elif self.phase == 1:
            if left and np.linalg.norm(p - [0.09, 0.05, 0.24]) < 0.07 and speed > 0.015:
                self.advance(presentation_speed=speed)
        elif self.phase == 2:
            if left and right:
                self.events.flags["grip_overlap_s"] += self.dt
            self.phase_hold(left and right, 0.08)
        elif self.phase == 3:
            donor_contacts = sum(self.contact("part", "left/panda_" + side + suffix)
                                 for side in ("left", "right") for suffix in ("finger", "finger_pad"))
            if right and donor_contacts < 1e-8 and sum(self.arms["panda-0"].robot.qpos[7:]) > 0.065:
                self.events.flags["receiver_only_s"] += self.dt
                self.phase_hold(True, 0.12)
            else:
                self.events.hold("phase_hold:3", False, self.time, 0.12)
        elif self.phase == 4:
            slot = self.fixtures["slot"]
            local = (body(slot.link).entity_pose.inv() * body(obj).entity_pose).p
            condition = (
                not left
                and not right
                and self.contact("part", "slot") > 0
                and abs(local[0]) < 0.014
                and abs(local[1]) < 0.045
                and 0.01 < local[2] < 0.06
                and np.linalg.norm(velocity(obj) - body(slot.link).linear_velocity)
                < 0.05
                and abs(slot.v) > 0.02
            )
            if self.phase_hold(condition, 0.7):
                self.events.physical_success = True
        if self.phase in (1, 2, 3) and p[2] < 0.13:
            self.events.fail("handover_drop", self.time)
