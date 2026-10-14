import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.fixtures import hinged_prop


class PendulumEnergyRelay(PandaDynamicEnv):
    TASK = "D08-PendulumEnergyRelay"
    NAMESPACE = "PandaMultiStage"
    REFERENCE_ACCELERATION = 0.20
    REFERENCE_JERK = 0.01
    WRIST_DAMPING = (24.0, 20.0, 14.0)
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("exciter", "preparing_brake"),
        ("cleared_exciter", "brake"),
        ("preparing_receiver", "return_driver"),
        ("brake", "cleared_driver"),
        ("damping_support", "cleared_partner"),
    )
    ARM_SETUPS = (
        ArmSetup("fork", (-0.04, -0.02, 0.21), base=(-0.55, -0.22, 0)),
        ArmSetup(
            "fork",
            (0.28, 0.02, 0.21),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    ALLOWED_TOOL_FIXTURES = ("pendulum",)
    PHASES = (
        "left_excitation",
        "right_braking",
        "right_return_impulse",
        "left_recovery",
        "low_energy_hold",
    )
    INSTRUCTION = (
        "左臂激发同一被动摆锤，右臂接住耗能后送回，左臂再次接触并在下垂目标附近稳定。"
    )

    def build_task(self):
        self.fixtures["pendulum"] = hinged_prop(
            self.scene, "pendulum", [0.12, 0, 0.43], length=self.params["length"], mass=self.params["object_mass"]
        )

    def reset_task(self):
        self.fixtures["pendulum"].reset(
            self.rng.uniform(-self.params["initial_angle_range"], self.params["initial_angle_range"]),
            self.rng.uniform(-self.params["initial_angular_speed_range"], self.params["initial_angular_speed_range"]),
        )
        self.events.flags.update(target=[0.12, 0, 0.21])

    def update_task(self):
        f = self.fixtures["pendulum"]
        left = self.contact("pendulum", "left_tool")
        right = self.contact("pendulum", "right_tool")
        if self.phase == 0:
            if (
                left
                and np.linalg.norm(self.arms["panda-0"].tool_body.linear_velocity)
                > 0.03
            ):
                self.events.once("left_active_contact", self.time, impulse=left)
            if self.events.has("left_active_contact") and f.q < -self.params["minimum_excursion"]:
                self.advance(angle=f.q, angular_velocity=f.v)
        elif self.phase == 1 and right and abs(f.v) < 0.45:
            self.advance(angle=f.q)
        elif self.phase == 2:
            if (
                right
                and np.linalg.norm(self.arms["panda-1"].tool_body.linear_velocity)
                > 0.03
            ):
                self.events.once("right_active_return", self.time, impulse=right)
            if (
                self.events.has("right_active_return")
                and f.q > self.params["return_excursion"]
                and f.v > 0.25
                and not right
            ):
                self.advance()
        elif self.phase == 3 and left:
            self.advance(impulse=left)
        elif self.phase == 4:
            if self.phase_hold(abs(f.q) < 0.055 and abs(f.v) < 0.12, 1.0):
                self.events.physical_success = True
