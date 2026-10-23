import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import box, set_initial, position, velocity, body
from panda_dynamics.tasks.predicates import supported


class ReciprocalSlidingTransfer(PandaDynamicEnv):
    TASK = "D12-ReciprocalSlidingTransfer"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("inertial_donor", "matched_receiver"),
        ("cleared_donor", "braking_receiver"),
        ("preparing_receiver", "loaded_carrier"),
        ("braking_receiver", "inertial_donor"),
        ("deliverer", "cleared_partner"),
    )
    ARM_SETUPS = (
        ArmSetup("scoop", (-0.015, -0.04, 0.19), base=(-0.55, -0.22, 0), half=0.08),
        ArmSetup(
            "scoop",
            (0.175, -0.04, 0.187),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
            half=0.08,
        ),
    )
    PHASES = (
        "left_inertial_slip",
        "right_receive_and_brake",
        "reverse_geometry",
        "left_receive_and_brake",
        "final_support_deposit",
    )
    INSTRUCTION = "左盘让方块滑出并交给与它同步运动的右盘（方块落上右盘时右盘速度不低于规定值），右盘随后在限定时间内制动、带着方块停稳；右盘带块换位后用同样方式把方块交回同步运动的左盘、由左盘制动停稳，最后把方块卸到实体支撑台上。"

    def build_task(self):
        self.objects["block"] = box(
            self.scene,
            "block",
            [0.018] * 3,
            [0, 0, 0.2],
            mass=self.params["object_mass"],
            mu=self.params["friction"],
        )
        self.output = box(
            self.scene,
            "output",
            [0.10, 0.075, 0.012],
            [0.18, -0.22, 0.118],
            static=True,
            mu=0.4,
        )

    def reset_task(self):
        # Nominal draws exactly one lateral offset (same stream as before);
        # hard also shifts the start along the tray.
        lateral = self.params["start_spread_y"]
        along = self.params["start_spread_x"]
        local = [0.040, self.rng.uniform(-lateral, lateral), 0.0185]
        if along > 0:
            local[0] += self.rng.uniform(-along, along)
        set_initial(self.objects["block"], self.arms["panda-0"].tool_pose.p + local)
        self.events.flags.update(
            start_local=local, right_receive_pose=None, max_unsupported_interval=0.0
        )

    def track_arrival(self, side, arm, other, on):
        """Record the receiving tray's motion each time the block comes onto
        it: horizontal tray speed and its velocity mismatch to the other tray."""
        flags = self.events.flags
        if on and not flags.get(side + "_supported", False):
            v = body(arm.tool).linear_velocity
            u = body(other.tool).linear_velocity
            flags[side + "_arrival"] = dict(
                time=float(self.time),
                speed=float(np.linalg.norm(v[:2])),
                mismatch=float(np.linalg.norm((v - u)[:2])),
            )
        flags[side + "_supported"] = bool(on)

    def braked_receive(self, side, arm, holding):
        """The block arrived while the receiver moved (matched to the donor) and
        the receiver has since braked to rest, starting the hold within the
        brake window after that arrival."""
        arrival = self.events.flags.get(side + "_arrival")
        if not holding or arrival is None:
            return False, {}
        rest = float(np.linalg.norm(body(arm.tool).linear_velocity))
        start = self.events.holds.get(f"phase_hold:{self.phase}", self.time)
        metrics = dict(
            arrival_speed=arrival["speed"],
            arrival_mismatch=arrival["mismatch"],
            rest_after=float(start - arrival["time"]),
        )
        ok = (
            arrival["speed"] >= self.params["receiver_min_speed"]
            and arrival["mismatch"] <= self.params["match_tolerance"]
            and rest < self.params["rest_speed"]
            and start - arrival["time"] <= self.params["brake_window"]
        )
        return ok, metrics

    def update_task(self):
        obj = self.objects["block"]
        left, right = self.arms.values()
        on_left = supported(self, "block", "left_tool")
        on_right = supported(self, "block", "right_tool")
        l = (left.tool_pose.inv() * body(obj).entity_pose).p
        r = (right.tool_pose.inv() * body(obj).entity_pose).p
        self.track_arrival("right", right, left, on_right)
        self.track_arrival("left", left, right, on_left)
        for arm in (left, right):
            angle = np.arccos(
                np.clip(arm.tool_pose.to_transformation_matrix()[2, 2], -1, 1)
            )
            if self.phase < 4 and angle > np.deg2rad(2.1):
                self.events.fail("tilt_only_shortcut", self.time)
        if not on_left and not on_right:
            self.events.flags.setdefault("no_support_since", self.time)
            elapsed = self.time - self.events.flags["no_support_since"]
            self.events.flags["max_unsupported_interval"] = max(
                elapsed, self.events.flags["max_unsupported_interval"]
            )
            if self.phase < 4 and elapsed > 0.09:
                self.events.fail("airborne_transfer_shortcut", self.time)
        else:
            self.events.flags.pop("no_support_since", None)
        if (
            self.phase == 0
            and on_left
            and l[0] - self.events.flags["start_local"][0] > 0.028
        ):
            self.advance()
        elif self.phase == 1:
            ok, metrics = self.braked_receive(
                "right",
                right,
                on_right
                and not on_left
                and max(abs(r[:2])) < 0.065
                and self.relative_speed(obj, right.tool) < 0.05,
            )
            if self.phase_hold(ok, 0.3, **metrics):
                self.events.flags["right_receive_pose"] = right.tool_pose.p.tolist()
        elif self.phase == 2:
            if (
                on_right
                and np.linalg.norm(
                    right.tool_pose.p - self.events.flags["right_receive_pose"]
                )
                > 0.06
            ):
                self.advance()
        elif self.phase == 3:
            ok, metrics = self.braked_receive(
                "left",
                left,
                on_left
                and not on_right
                and max(abs(l[:2])) < 0.065
                and self.relative_speed(obj, left.tool) < 0.05,
            )
            self.phase_hold(ok, 0.3, **metrics)
        elif self.phase == 4:
            if self.phase_hold(
                self.contact("block", "output") > 0
                and not on_left
                and not on_right
                and np.linalg.norm(position(obj)[:2] - [0.18, -0.22]) < 0.065
                and np.linalg.norm(velocity(obj)) < 0.04,
                0.5,
            ):
                self.events.physical_success = True
