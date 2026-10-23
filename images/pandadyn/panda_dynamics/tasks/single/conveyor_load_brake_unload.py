from ruckig import Synchronization
import numpy as np
import sapien
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

FINGER_SIDES = {
    "panda_leftfinger": "left",
    "panda_leftfinger_pad": "left",
    "panda_rightfinger": "right",
    "panda_rightfinger_pad": "right",
}
# Contact points may sit up to this far outside the handle box (solver
# separation/penetration); the 6 mm gap to the tray end wall stays excluded.
HANDLE_TOLERANCE = 0.002
# The carriage must be stopped by the handle grip, not by a rail end stop.
END_STOP_MARGIN = 0.005


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
        "趁零件在滚轮输送带上移动时夹起并举高，放进仍在滑行的小车后松手，"
        "再赶在小车撞上导轨端点之前用两指只夹住它的竖直把手把车刹停（零件留在车内），"
        "然后从车上重新夹起零件，放进码头盒松手并让它静止。"
    )

    def build_task(self):
        self.fixtures["conveyor"] = roller_conveyor(
            self.scene, "conveyor", [-0.13, -0.10, 0.1], self.params["incoming_speed"]
        )
        self.fixtures["carriage"] = coasting_carriage(
            self.scene, "carriage", [0.12, 0, 0.11]
        )
        # The handle is the tall box of the carriage link (half 0.014 x 0.018 x
        # 0.038 m at local (0.11, 0, 0.035)); read it from the built geometry.
        shapes = [
            s
            for s in body(self.fixtures["carriage"].link).collision_shapes
            if hasattr(s, "half_size")
        ]
        handle = max(shapes, key=lambda s: s.half_size[2])
        self.handle_center = np.asarray(handle.local_pose.p, dtype=float)
        self.handle_half = np.asarray(handle.half_size, dtype=float)
        self.rail_limits = np.asarray(
            self.fixtures["carriage"].joint.get_limits()[0], dtype=float
        )
        self._step_records = []
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
        p = self.params
        # Separate hand timing from arm tracking, with the same rate/effort limits.
        self.servo.input.per_dof_synchronization = [Synchronization.TimeIfNecessary]*7 + [Synchronization.No]*2
        self.fixtures["conveyor"].reset()
        # Seeded draws in fixed order; a zero spread draws nothing (nominal keeps
        # the single carriage draw it has always made).
        def spread(key):
            return self.rng.uniform(-p[key], p[key]) if p[key] > 0 else 0.0

        carriage_start = p["carriage_start"] + spread("carriage_start_spread")
        carriage_speed = p["fixture_speed"] + spread("fixture_speed_spread")
        part_y = -0.16 + spread("part_start_spread")
        part_x = -0.13 + spread("part_lateral_spread")
        self.fixtures["carriage"].reset(carriage_start, carriage_speed)
        set_initial(
            self.objects["part"],
            [part_x, part_y, 0.133],
            [0, p["incoming_speed"], 0],
        )
        q = self.robot.qpos.copy()
        q[7:] = 0.024
        self.robot.set_qpos(q)
        self.servo.reset()
        self._step_records = []

    def read_contacts(self):
        start = len(self.contact_records)
        super().read_contacts()
        self._step_records = self.contact_records[start:]

    def handle_grip(self):
        """Both fingers touch the carriage and every finger-carriage contact
        point of this physics step lies on the handle box (carriage-link frame)."""
        inverse = body(self.fixtures["carriage"].link).entity_pose.inv()
        on_handle = {"left": 0.0, "right": 0.0}
        for record in self._step_records:
            pair = record["pair"]
            if "carriage" not in pair:
                continue
            side = FINGER_SIDES.get(pair[0] if pair[1] == "carriage" else pair[1])
            if side is None:
                continue
            for point in record["points"]:
                impulse = float(np.linalg.norm(point["impulse_vector"]))
                if impulse < 1e-9:
                    continue
                local = (inverse * sapien.Pose(point["position"])).p
                if np.any(
                    abs(local - self.handle_center)
                    > self.handle_half + HANDLE_TOLERANCE
                ):
                    return False
                on_handle[side] += impulse
        return min(on_handle.values()) > 1e-7

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
            if (
                self.contact("part", "carriage")
                and not grip
                and abs(cart.v) > self.params["release_min_speed"]
            ):
                self.events.flags["unbraked_speed"] = abs(cart.v)
                self.advance()
        elif self.phase == 2:
            handle = bilateral_grip(self, "carriage") and self.handle_grip()
            local = (body(cart.link).entity_pose.inv() * body(obj).entity_pose).p
            if self.phase_hold(
                handle
                and abs(cart.v) < 0.012
                and max(abs(local[:2])) < 0.07
                and self.contact("part", "carriage") > 0,
                0.25,
                braked_speed=abs(cart.v),
                brake_position=cart.q,
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
        if self.phase <= 2 and not (
            self.rail_limits[0] + END_STOP_MARGIN
            < cart.q
            < self.rail_limits[1] - END_STOP_MARGIN
        ):
            self.events.fail("carriage_hit_end_stop", self.time)
