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
    # Slot law (shared DrivenFixture "oscillate"): q = offset + 0.20 sin(w (t + shift)), w = fixture_speed / 0.20.
    SLOT_AMPLITUDE = 0.20
    INSTRUCTION = (
        "左手从转动的滚轮输送带上抓起正在移动的长零件并带着它运动到交接点，右手在零件持续运动中夹住它，"
        "两手同时夹持和左手完全松开时零件都不能停下，最后右手在往复滑动的接收槽运动时松手，把零件放进槽里并随槽一起运动。"
    )

    def build_task(self):
        self.fixtures["conveyor"] = roller_conveyor(
            self.scene, "conveyor", [-0.08, -0.08, 0.10], self.params["incoming_speed"]
        )
        self.objects["part"] = box(
            self.scene,
            "part",
            [0.11, 0.017, 0.018],
            [-0.08, -0.13, 0.134],
            mass=self.params["object_mass"],
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
            [-0.08, self.rng.uniform(self.params["part_y_low"], self.params["part_y_high"]), 0.133],
            [0, self.params["incoming_speed"], 0],
        )
        self.fixtures["conveyor"].reset()
        slot = self.fixtures["slot"]
        speed = self.params["fixture_speed"]
        offset = self.rng.uniform(self.params["slot_offset_low"], self.params["slot_offset_high"])
        # Seeded clock phase of the slot oscillation, U(+-fixture_phase). Nominal has
        # fixture_phase = 0 (no draw): reset and motor law are bit-for-bit the original.
        phase = 0.0
        if self.params["fixture_phase"] > 0:
            phase = self.rng.uniform(-self.params["fixture_phase"], self.params["fixture_phase"])
        slot.reset(offset + self.SLOT_AMPLITUDE * np.sin(phase), speed * np.cos(phase))
        slot.phase = offset
        # Clock shift read by before_physics; kept in the event flags so exact
        # snapshots restore it (not an observation).
        self.events.flags["slot_clock_shift"] = phase / (speed / self.SLOT_AMPLITUDE)
        for arm in self.arms.values():
            q = arm.robot.qpos.copy()
            q[7:] = 0.024
            arm.robot.set_qpos(q)
            arm.servo.reset()
            # The real hand closes while the arm continues tracking the belt.
            arm.servo.input.per_dof_synchronization = [Synchronization.TimeIfNecessary]*7 + [Synchronization.No]*2
        self.events.flags.update(
            target=[0.09, 0.05, 0.24], grip_overlap_s=0.0, receiver_only_s=0.0,
            overlap_min_speed=None, release_contact_speed=None, release_min_speed=None,
            slot_speed_at_release=None,
        )

    def before_physics(self):
        # Identical to the base loop except the slot reads its seeded clock
        # shift (0.0 in nominal, so its targets are bit-for-bit unchanged).
        shift = self.events.flags.get("slot_clock_shift", 0.0)
        for name, fixture in self.fixtures.items():
            fixture.step(self.time + shift if name == "slot" else self.time, self.dt)

    def update_task(self):
        obj = self.objects["part"]
        p = position(obj)
        speed = float(np.linalg.norm(velocity(obj)))
        left = bilateral_grip(self, "part", "panda-0")
        right = bilateral_grip(self, "part", "panda-1")
        moving = speed > self.params["handover_speed"]
        flags = self.events.flags
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
                flags["grip_overlap_s"] += self.dt
            # The handover happens in motion: the overlap only counts while the part moves.
            overlap = left and right and moving
            if overlap:
                held = "phase_hold:2" in self.events.holds
                flags["overlap_min_speed"] = min(speed, flags["overlap_min_speed"]) if held else speed
            self.phase_hold(overlap, 0.08, overlap_min_speed=flags.get("overlap_min_speed"))
        elif self.phase == 3:
            donor_contacts = sum(self.contact("part", "left/panda_" + side + suffix)
                                 for side in ("left", "right") for suffix in ("finger", "finger_pad"))
            if donor_contacts >= 1e-8:
                # Part speed at the donor's latest finger contact: the release itself must happen in motion.
                flags["release_contact_speed"] = speed
            released = (
                right
                and donor_contacts < 1e-8
                and sum(self.arms["panda-0"].robot.qpos[7:]) > 0.065
                and flags.get("release_contact_speed") is not None
                and flags["release_contact_speed"] > self.params["handover_speed"]
                and moving
            )
            if released:
                held = "phase_hold:3" in self.events.holds
                flags["receiver_only_s"] += self.dt
                flags["release_min_speed"] = min(speed, flags["release_min_speed"]) if held else speed
                self.phase_hold(True, 0.12, release_contact_speed=flags["release_contact_speed"],
                                release_min_speed=flags["release_min_speed"])
            else:
                self.events.hold("phase_hold:3", False, self.time, 0.12)
        elif self.phase == 4:
            slot = self.fixtures["slot"]
            receiver_contacts = sum(self.contact("part", "right/panda_" + side + suffix)
                                    for side in ("left", "right") for suffix in ("finger", "finger_pad"))
            if receiver_contacts >= 1e-8:
                # Slot speed at the receiver's latest finger contact: the part is let go into a moving slot.
                flags["slot_speed_at_release"] = abs(slot.v)
            local = (body(slot.link).entity_pose.inv() * body(obj).entity_pose).p
            condition = (
                not left
                and not right
                and flags.get("slot_speed_at_release") is not None
                and flags["slot_speed_at_release"] > self.params["release_slot_speed"]
                and self.contact("part", "slot") > 0
                and abs(local[0]) < 0.014
                and abs(local[1]) < 0.045
                and 0.01 < local[2] < 0.06
                and np.linalg.norm(velocity(obj) - body(slot.link).linear_velocity)
                < 0.05
                and abs(slot.v) > 0.02
            )
            if self.phase_hold(condition, 0.7, slot_speed_at_release=flags.get("slot_speed_at_release")):
                self.events.physical_success = True
        if self.phase in (1, 2, 3) and p[2] < 0.13:
            self.events.fail("handover_drop", self.time)
