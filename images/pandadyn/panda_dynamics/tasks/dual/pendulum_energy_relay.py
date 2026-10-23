import numpy as np
from scipy.spatial.transform import Rotation
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.fixtures import hinged_prop


class PendulumEnergyRelay(PandaDynamicEnv):
    TASK = "D08-PendulumEnergyRelay"
    NAMESPACE = "PandaMultiStage"
    REFERENCE_ACCELERATION = 0.55
    REFERENCE_JERK = 0.05
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
        "左臂推动被动摆锤向右摆过规定角度；右臂须在摆锤仍快速摆动时接住它，使其能量至少减少六成并降到低速，"
        "再主动推动使其向左摆过规定角度；左臂再次接触后，摆锤须在右臂不接触的情况下于下垂位置附近低速保持 1 s。"
    )

    def build_task(self):
        f = self.fixtures["pendulum"] = hinged_prop(
            self.scene, "pendulum", [0.12, 0, 0.43], length=self.params["length"], mass=self.params["object_mass"]
        )
        # Mechanical energy of the swinging link about its hinge, from the simulated mass properties.
        rb = f.link._objs[0]
        q = rb.cmass_local_pose.q
        rotation = Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_matrix()
        com = np.asarray(rb.cmass_local_pose.p, dtype=float)
        inertia = rotation @ np.diag(rb.inertia) @ rotation.T
        # The hinge axis is the link-frame y axis through the link origin (the pivot).
        self.pendulum_inertia = float(inertia[1, 1] + rb.mass * (com[0] ** 2 + com[2] ** 2))
        self.pendulum_weight_moment = float(rb.mass * 9.81 * np.hypot(com[0], com[2]))

    def pendulum_energy(self, q, v):
        """Swing energy (J) relative to hanging at rest."""
        return self.pendulum_weight_moment * (1.0 - np.cos(q)) + 0.5 * self.pendulum_inertia * v * v

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
        flags = self.events.flags
        if self.phase == 0:
            if (
                left
                and np.linalg.norm(self.arms["panda-0"].tool_body.linear_velocity)
                > 0.03
            ):
                self.events.once("left_active_contact", self.time, impulse=left)
            if self.events.has("left_active_contact") and f.q < -self.params["minimum_excursion"]:
                self.advance(angle=f.q, angular_velocity=f.v)
        elif self.phase == 1:
            # The right paddle must start its catch while the pendulum still swings fast, and the
            # swing energy must then fall by brake_energy_drop while only the right paddle touches it.
            catch = flags.get("brake_catch")
            if catch is not None and (left or self.time - catch["time"] > self.params["brake_window"]):
                self.events.emit("brake_catch_void", self.time, left_contact=bool(left))
                catch = None
            previous = flags.get("pendulum_previous")
            if (
                catch is None
                and right
                and not left
                and not flags.get("right_contact_previous")
                and previous is not None
                and abs(previous[1]) >= self.params["brake_min_speed"]
            ):
                catch = dict(
                    angle=previous[0],
                    angular_speed=abs(previous[1]),
                    energy=float(self.pendulum_energy(*previous)),
                )
                self.events.emit("brake_catch_onset", self.time, **catch)
                catch["time"] = self.time
            flags["brake_catch"] = catch
            energy = float(self.pendulum_energy(f.q, f.v))
            if (
                catch is not None
                and right
                and abs(f.v) < 0.45
                and energy <= (1.0 - self.params["brake_energy_drop"]) * catch["energy"]
            ):
                self.advance(
                    angle=f.q,
                    angular_velocity=f.v,
                    catch_angular_speed=catch["angular_speed"],
                    energy_ratio=energy / catch["energy"],
                )
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
            if self.phase_hold(abs(f.q) < 0.055 and abs(f.v) < 0.12 and not right, 1.0):
                self.events.physical_success = True
        flags["pendulum_previous"] = [f.q, f.v]
        flags["right_contact_previous"] = bool(right)
