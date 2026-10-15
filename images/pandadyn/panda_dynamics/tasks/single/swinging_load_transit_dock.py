import numpy as np
import sapien
from ruckig import Synchronization
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import box, container, position, body
from panda_dynamics.props.free_mechanisms import hanging_carrier
from panda_dynamics.tasks.predicates import bilateral_grip, supported


class SwingingLoadTransitDock(PandaDynamicEnv):
    TASK = "S10-SwingingLoadTransitDock"
    NAMESPACE = "PandaMultiStage"
    TOOL = None
    TOOL_START = (-0.03, -0.14, 0.36)
    ALLOW_FINGER_CONTACTS = True
    ALLOWED_FINGER_FIXTURES = ("carrier",)
    PHASES = (
        "grasp_settle_and_damp",
        "obstacle_transit",
        "turn_and_brake",
        "residual_swing_cancel",
        "load_dock",
    )
    INSTRUCTION = "用真实夹爪握住载架，抑制被动悬挂载荷的初始摆动，绕障碍转弯制动，再将载荷低速放入码头。"

    def build_task(self):
        self.fixtures["carrier"] = hanging_carrier(
            self.scene, "carrier", self.TOOL_START, length=self.params["length"]
        )
        self.objects["carrier"] = self.fixtures["carrier"].articulation.links[0]
        self.objects["load"] = self.fixtures["carrier"].articulation.links[1]
        box(self.scene, "obstacle", [0.04, 0.06, 0.055], [0.08, 0, 0.055], static=True)
        for side in (-1, 1):
            box(
                self.scene,
                f"reset_handle_stand_{side}",
                [0.004, 0.045, 0.003],
                [-0.03 + side * 0.053, -0.177, 0.348],
                static=True,
            )
        self.dock = container(
            self.scene,
            "dock",
            [0.07, 0.19, 0.015],
            half=(0.052, 0.05),
            height=0.055,
            static=True,
        )

    def reset_task(self):
        f = self.fixtures["carrier"]
        f.raw.pose = sapien.Pose(self.TOOL_START)
        f.reset(self.params["initial_angle"] + self.rng.uniform(-0.02, 0.02), 0)
        q = self.robot.qpos.copy()
        q[7:] = 0.016
        self.robot.set_qpos(q)
        self.servo.reset()
        self.servo.kp[7:] = 800.0
        self.servo.kd[7:] = 8.0
        self.servo.input.per_dof_synchronization = [Synchronization.TimeIfNecessary]*7 + [Synchronization.No]*2
        self.events.flags.update(
            waypoints=[[-0.05, 0.04, 0.38], [0.0, 0.15, 0.37]],
            waypoint_index=0,
            # Floor 15 mm + bob radius 22 mm + link 150 mm + hinge offset
            # 12 mm gives a supported carrier height of 199 mm.
            goal=[0.07, 0.19, self.params["length"] + 0.049],
        )

    def update_task(self):
        f = self.fixtures["carrier"]
        grip = bilateral_grip(self, "carrier")
        root = position(self.objects["carrier"])
        settled = abs(f.q) < 0.07 and abs(f.v) < 0.18
        if self.phase == 0:
            self.phase_hold(grip and settled, 0.35)
        elif self.phase == 1:
            if (
                grip
                and np.linalg.norm(root - self.events.flags["waypoints"][0]) < 0.035
            ):
                self.advance()
        elif self.phase == 2:
            if (
                grip
                and np.linalg.norm(root - self.events.flags["waypoints"][1]) < 0.035
            ):
                self.advance()
        elif self.phase == 3:
            self.phase_hold(grip and settled, 0.5)
        elif self.phase == 4:
            load = body(self.objects["load"])
            bob = (load.entity_pose * sapien.Pose([0, 0, -f.length])).p
            if self.phase_hold(
                grip
                and settled
                and supported(self, "load", "dock", max_gap=0.010)
                and abs(bob[2] - 0.037) < 0.003
                and np.linalg.norm(bob[:2] - [0.07, 0.19]) < 0.035,
                0.5,
            ):
                self.events.physical_success = True
        if self.contact("load", "obstacle") or self.contact("carrier", "obstacle"):
            self.events.fail("obstacle_collision", self.time)
        # A valid docked grasp is below 0.20 m; distinguish it from a drop.
        if root[2] < 0.16:
            self.events.fail("carrier_grasp_lost", self.time)
