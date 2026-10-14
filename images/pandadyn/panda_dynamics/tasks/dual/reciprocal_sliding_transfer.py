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
    INSTRUCTION = "左盘加速滑移把方块交给匹配运动的右盘，右盘制动后换位反向交回左盘，最后卸到实体支撑台。"

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
        local = [0.040, self.rng.uniform(-0.004, 0.004), 0.0185]
        set_initial(self.objects["block"], self.arms["panda-0"].tool_pose.p + local)
        self.events.flags.update(
            start_local=local, right_receive_pose=None, max_unsupported_interval=0.0
        )

    def update_task(self):
        obj = self.objects["block"]
        left, right = self.arms.values()
        on_left = supported(self, "block", "left_tool")
        on_right = supported(self, "block", "right_tool")
        l = (left.tool_pose.inv() * body(obj).entity_pose).p
        r = (right.tool_pose.inv() * body(obj).entity_pose).p
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
            if self.phase_hold(
                on_right
                and not on_left
                and max(abs(r[:2])) < 0.065
                and self.relative_speed(obj, right.tool) < 0.05,
                0.3,
            ):
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
            self.phase_hold(
                on_left
                and not on_right
                and max(abs(l[:2])) < 0.065
                and self.relative_speed(obj, left.tool) < 0.05,
                0.3,
            )
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
