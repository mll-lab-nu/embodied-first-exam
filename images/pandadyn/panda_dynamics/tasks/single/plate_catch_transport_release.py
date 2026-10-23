import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import ball, set_initial, position, velocity
from panda_dynamics.props.fixtures import single_axis
from panda_dynamics.tasks.predicates import ball_on_plate, containment, free_interval


class PlateCatchTransportRelease(PandaDynamicEnv):
    TASK = "S02-PlateCatchTransportRelease"
    NAMESPACE = "PandaMultiStage"
    TOOL = "plate"
    REFERENCE_ACCELERATION = 0.55
    REFERENCE_JERK = 0.05
    TOOL_START = (0.01, -0.055, 0.22)
    PHASES = (
        "airborne_plate_catch",
        "recenter",
        "turning_transport",
        "rolling_recovery",
        "moving_basin_release",
    )
    INSTRUCTION = (
        "用无边平板在空中接住抛来的球并让它在板中心停稳，托着球沿转弯路线依次经过两个固定路点且不让球滚落，"
        "再让球重新在板中心停稳，最后把球送进往复移动中的盆，"
        "在盆持续移动时让球在盆中稳住且不再接触平板。"
    )

    def build_task(self):
        self.objects["ball"] = ball(
            self.scene,
            "ball",
            self.params["radius"],
            self.params["object_mass"],
            self.params["restitution"],
        )
        self.fixtures["basin"] = single_axis(
            self.scene,
            "basin",
            [0.29, -0.23, 0.045],
            speed=self.params["fixture_speed"],
            force=8.0,
        )

    def reset_task(self):
        y = self.rng.uniform(-0.04, 0.01)
        set_initial(
            self.objects["ball"],
            [0.06, y, 0.42],
            [self.params["incoming_speed"], 0, self.params["incoming_vertical_speed"]],
        )
        self.fixtures["basin"].reset(
            self.rng.uniform(-0.04, 0.0), self.params["fixture_speed"]
        )
        self.events.flags.update(
            waypoints=[[0.0, 0.08, 0.27], [0.18, 0.13, 0.25]],
            waypoint_index=0,
            target=[0.075, y, 0.22],
        )
        self.events.emit("release", 0.0, object="ball")

    def update_task(self):
        obj = self.objects["ball"]
        local = self.local_position(obj)
        supported = ball_on_plate(self, "ball")
        if self.phase == 0:
            if free_interval(self, "ball", "incoming_flight") > 0.05:
                self.events.once("airborne", self.time)
            if self.contact("ball", "tool") and self.events.has("airborne"):
                self.advance(impact_speed=float(np.linalg.norm(velocity(obj))))
        elif self.phase == 1:
            self.phase_hold(
                supported
                and np.linalg.norm(local[:2]) < 0.035
                and self.relative_speed(obj) < 0.08,
                0.3,
            )
        elif self.phase == 2:
            i = self.events.flags["waypoint_index"]
            if (
                supported
                and np.linalg.norm(self.tool_pose.p - self.events.flags["waypoints"][i])
                < 0.025
            ):
                self.events.emit("waypoint", self.time, index=i)
                self.events.flags["waypoint_index"] += 1
                if i == 1:
                    self.advance()
        elif self.phase == 3:
            self.phase_hold(
                supported
                and np.linalg.norm(local[:2]) < 0.035
                and self.relative_speed(obj) < 0.04,
                0.4,
            )
        elif self.phase == 4:
            basin = self.fixtures["basin"]
            if self.phase_hold(
                containment(
                    self, "ball", basin.link, 0.075, 0.06, self.params["radius"]
                )
                and not self.contact("ball", "tool")
                and abs(basin.v) > 0.02,
                0.7,
            ):
                self.events.physical_success = True
        if self.phase in (1, 2, 3) and (
            max(abs(local[:2])) > self.params["tool_half"] or local[2] < -0.01
        ):
            self.events.fail("rimless_plate_spill", self.time)
