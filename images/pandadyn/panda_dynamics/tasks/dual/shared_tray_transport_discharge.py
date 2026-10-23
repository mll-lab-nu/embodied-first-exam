import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import (
    ball,
    container,
    set_initial,
    position,
    body,
    container_shapes,
    add_box,
    finish,
)
from panda_dynamics.tasks.predicates import containment, supported


class SharedTrayTransportDischarge(PandaDynamicEnv):
    TASK = "D04-SharedTrayTransportDischarge"
    NAMESPACE = "PandaMultiStage"
    REFERENCE_ACCELERATION = 0.30
    REFERENCE_JERK = 0.025
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("left_support", "right_support"),
        ("left_support", "right_support"),
        ("left_support", "right_support"),
        ("left_support", "right_support"),
        ("left_support", "right_support"),
    )
    ARM_SETUPS = (
        ArmSetup(
            "support_fork",
            (-0.075, 0, 0.22),
            base=(-0.55, -0.22, 0),
            half=0.035,
            mass=0.12,
        ),
        ArmSetup(
            "support_fork",
            (0.215, 0, 0.22),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
            half=0.035,
            mass=0.12,
        ),
    )
    PHASES = (
        "shared_support",
        "transport_turn",
        "disturbance_recovery",
        "exit_alignment",
        "natural_discharge",
    )
    INSTRUCTION = (
        "两臂只靠叉托接触共同托住载球托盘，并在共同支撑下依次经过两个路点、在小球受突然推力后让它回到盘心附近稳住、"
        "再把托盘移到盆边，最后让小球离开托盘落入盆中静止，托盘全程不得掉落。"
    )

    def build_task(self):
        builder = self.scene.create_actor_builder()
        container_shapes(builder, (0.10, 0.12), 0.009)
        for sign in (-1, 1):
            add_box(builder, [0.024, 0.030, 0.004], [sign * 0.125, 0, 0], density=500)
        self.objects["tray"] = finish(builder, "tray", [0.07, 0, 0.225], mass=0.25)
        self.objects["ball"] = ball(
            self.scene, "ball", self.params["radius"], self.params["object_mass"], 0.05
        )
        self.basin = container(
            self.scene,
            "basin",
            [0.30, 0.18, 0.08],
            half=(0.105, 0.10),
            height=0.08,
            static=True,
        )

    def reset_task(self):
        set_initial(self.objects["tray"], [0.07, 0, 0.225])
        set_initial(
            self.objects["ball"], [0.07 + self.rng.uniform(-0.006, 0.006), 0, 0.244]
        )
        self.events.flags.update(
            waypoints=[[0.12, -0.04, 0.27], [0.02, 0.08, 0.27]],
            waypoint_index=0,
            impulse_applied=0.0,
            support_impulses={"left": 0.0, "right": 0.0},
        )

    def before_physics(self):
        super().before_physics()
        if self.phase == 2:
            start = self.events.flags["phase_started"]
            if self.time - start < 0.03:
                force = self.params["disturbance_impulse"] / 0.03
                body(self.objects["ball"]).add_force_at_point(
                    [force, 0, 0], position(self.objects["ball"]), mode="force"
                )
                self.events.flags["impulse_applied"] += force * self.dt

    def update_task(self):
        tray = self.objects["tray"]
        p = position(tray)
        ball_local = (
            body(tray).entity_pose.inv() * body(self.objects["ball"]).entity_pose
        ).p
        supports = []
        for arm in self.arms.values():
            self.events.flags["support_impulses"][arm.role] += self.contact(
                "tray", arm.contact_name
            )
            supports.append(supported(self, "tray", arm.contact_name, 0.04))
        shared = all(supports)
        inside = (
            max(abs(ball_local[:2] / np.array([0.11, 0.16]))) < 1
            and ball_local[2] > -0.01
        )
        if self.phase < 4 and not inside:
            self.events.fail("ball_spill", self.time)
        if p[2] < 0.17:
            self.events.fail("shared_support_drop", self.time)
        if self.phase == 0:
            self.phase_hold(shared and inside, 0.35)
        elif self.phase == 1:
            i = self.events.flags["waypoint_index"]
            if shared and np.linalg.norm(p - self.events.flags["waypoints"][i]) < 0.025:
                self.events.emit("waypoint", self.time, index=i)
                self.events.flags["waypoint_index"] += 1
                if i == 1:
                    self.advance()
        elif self.phase == 2:
            condition = (
                shared
                and self.events.flags["impulse_applied"]
                >= 0.95 * self.params["disturbance_impulse"]
                and np.linalg.norm(ball_local[:2]) < 0.045
                and self.relative_speed(self.objects["ball"], tray) < 0.07
            )
            self.phase_hold(
                condition, 0.4, measured_impulse=self.events.flags["impulse_applied"]
            )
        elif self.phase == 3:
            if shared and np.linalg.norm(p[:2] - [0.12, 0.18]) < 0.04:
                self.advance()
        elif self.phase == 4:
            if self.phase_hold(
                containment(self, "ball", self.basin, 0.10, 0.08, self.params["radius"])
                and not self.contact("ball", "tray"),
                0.7,
            ):
                self.events.physical_success = True
