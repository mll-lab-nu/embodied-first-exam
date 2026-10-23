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
    INSTRUCTION = "用真实夹爪握住载架并抑制被动悬挂载荷的初始摆动，带它经过障碍块旁的路径点且不碰障碍块，在转弯处的第二个路径点制动停稳并消除残余摆动，再将载荷低速放入码头。"
    # v6: "brake" and "slowly into the dock" are checked. Speeds are 50 ms
    # displacement averages (immune to per-substep grip-contact chatter, same
    # meaning at 1000 and 2000 Hz).
    SPEED_WINDOW = 0.05
    BRAKE_HOLD = 0.2
    DOCK_CENTER = (0.07, 0.19)
    # Outer wall half-extents (opening half + 5 mm wall), rim top z, bob radius.
    DOCK_OUTER_HALF = (0.057, 0.055)
    DOCK_RIM_Z = 0.07
    BOB_RADIUS = 0.022

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

    def _window_speeds(self, root, bob):
        """Mean carrier-root and bob-centre speeds over the last SPEED_WINDOW s."""
        track = self.events.flags.setdefault("speed_track", [])
        track.append([float(self.time), *map(float, root), *map(float, bob)])
        while len(track) > 1 and self.time - track[1][0] >= self.SPEED_WINDOW - 1e-9:
            track.pop(0)
        span = self.time - track[0][0]
        if span <= 0:
            return 0.0, 0.0
        old = np.asarray(track[0][1:])
        return (
            float(np.linalg.norm(root - old[:3]) / span),
            float(np.linalg.norm(bob - old[3:]) / span),
        )

    def update_task(self):
        f = self.fixtures["carrier"]
        grip = bilateral_grip(self, "carrier")
        root = position(self.objects["carrier"])
        load = body(self.objects["load"])
        bob = (load.entity_pose * sapien.Pose([0, 0, -f.length])).p
        carrier_speed, bob_speed = self._window_speeds(root, bob)
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
            # Turn point reached AND braked: the carrier must stay below
            # brake_speed for BRAKE_HOLD s inside the waypoint ball.
            self.phase_hold(
                grip
                and np.linalg.norm(root - self.events.flags["waypoints"][1]) < 0.035
                and carrier_speed < self.params["brake_speed"],
                self.BRAKE_HOLD,
                carrier_speed=carrier_speed,
            )
        elif self.phase == 3:
            self.phase_hold(grip and settled, 0.5)
        elif self.phase == 4:
            if self.phase_hold(
                grip
                and settled
                and supported(self, "load", "dock", max_gap=0.010)
                and abs(bob[2] - 0.037) < 0.003
                and np.linalg.norm(bob[:2] - [0.07, 0.19]) < 0.035,
                0.5,
            ):
                self.events.physical_success = True
        # Slow dock entry: once the ball's bottom is below the dock rim within
        # reach of the dock walls (every possible ball-dock contact lies in
        # this zone), its speed must stay below dock_entry_speed.
        if (
            not self.events.physical_success
            and abs(bob[0] - self.DOCK_CENTER[0]) < self.DOCK_OUTER_HALF[0] + self.BOB_RADIUS
            and abs(bob[1] - self.DOCK_CENTER[1]) < self.DOCK_OUTER_HALF[1] + self.BOB_RADIUS
            and bob[2] - self.BOB_RADIUS < self.DOCK_RIM_Z
        ):
            if "dock_entry" not in self.events.flags:
                self.events.flags["dock_entry"] = self.time
                self.events.emit("dock_entry", self.time, speed=bob_speed)
            if bob_speed > self.params["dock_entry_speed"]:
                self.events.fail("dock_entry_too_fast", self.time)
        if self.contact("load", "obstacle") or self.contact("carrier", "obstacle"):
            self.events.fail("obstacle_collision", self.time)
        # A valid docked grasp is below 0.20 m; distinguish it from a drop.
        if root[2] < 0.16:
            self.events.fail("carrier_grasp_lost", self.time)
