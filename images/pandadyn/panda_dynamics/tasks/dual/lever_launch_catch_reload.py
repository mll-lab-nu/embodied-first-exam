import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import ball, box, body, velocity, set_initial, position
from panda_dynamics.props.fixtures import single_axis
from panda_dynamics.props.launchers import build_launcher
from panda_dynamics.tasks.predicates import cup_catch, containment, free_interval


class LeverLaunchCatchReload(PandaDynamicEnv):
    TASK = "D09-LeverLaunchCatchReload"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("cleared_striker", "loader"),
        ("striker", "preparing_catcher"),
        ("cleared_striker", "catcher"),
        ("cleared_striker", "reloader"),
        ("striker", "cleared_loader"),
        ("cleared_striker", "cleared_loader"),
    )
    ARM_SETUPS = (
        ArmSetup(
            "mallet",
            (0.16, -0.11, 0.28),
            base=(-0.44, -0.23, 0),
            mount=(0.12, -0.13, 0.075),
        ),
        ArmSetup(
            "cup",
            (0.12, 0.17, 0.26),
            base=(0.74, 0.23, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    ALLOWED_TOOL_FIXTURES = ("lever", "lever_pad")
    CART_STROKE = 0.20  # amplitude of DrivenFixture's "oscillate" law
    WRIST_DAMPING = (24.0, 20.0, 14.0)
    PHASES = (
        "physical_loading",
        "first_launch",
        "right_catch",
        "reload_and_clear",
        "second_launch",
        "moving_receptacle_retention",
    )
    INSTRUCTION = "右杯装球并撤离，左锤击打实体杠杆让右杯接回；右杯重新装填同一球，左锤再发射到运动容器。"

    def build_task(self):
        box(self.scene,"launcher_pedestal",[.026,.026,.04],[.12,0,.04],static=True)
        self.fixtures["lever"] = build_launcher(self.scene, pad_offset=-0.075)
        f = self.fixtures["lever"]
        # Zero-preload finite passive return spring; no success-triggered kick.
        f.joint.set_drive_properties(0.008, 0.002, 0.12, mode="force")
        f.kp = 0.008
        f.kd = 0.002
        f.force = 0.12
        f.motion = "spring"
        self.objects["ball"] = ball(
            self.scene, "ball", self.params["radius"], self.params["object_mass"], 0.1
        )
        # v5: rail centre moved +0.12 m in y (was -0.15). Under the declared
        # 0.20 m / 0.2 rad/s slider law the old receptacle reached the fixed
        # lever launch plane (y=0) only near its turnaround (|v|~0.026 m/s) in
        # t~10.4-12.1 s, before two loads, a launch and a catch can finish.
        # Centred at -0.03 it crosses y=0 at |v|~0.04 m/s around t~14.9-15.6 s.
        self.fixtures["cart"] = single_axis(
            self.scene,
            "cart",
            [0.28, -0.03, 0.025],
            speed=self.params["fixture_speed"],
            force=8.0,
        )

    def reset_task(self):
        self.fixtures["lever"].reset(0, 0)
        # Declared slider law (DrivenFixture "oscillate", 0.20 m amplitude):
        #   q(t) = offset + 0.20 sin(omega t + phase), omega = fixture_speed / 0.20.
        # offset ~ U(+-fixture_offset); phase ~ U(+-fixture_phase). Nominal has
        # fixture_phase = 0 (no draw, law identical to the original slider).
        cart = self.fixtures["cart"]
        speed = self.params["fixture_speed"]
        span = self.params["fixture_offset"]
        offset = self.rng.uniform(-span, span)
        phase = 0.0
        if self.params["fixture_phase"] > 0:
            phase = self.rng.uniform(-self.params["fixture_phase"], self.params["fixture_phase"])
        omega = speed / self.CART_STROKE
        cart.reset(
            offset + self.CART_STROKE * np.sin(phase), speed * np.cos(phase)
        )
        cart.phase = offset
        # Clock shift fed to the cart's motor law in before_physics; kept in
        # the event flags so exact snapshots restore it (not an observation).
        self.events.flags["cart_clock_shift"] = phase / omega
        set_initial(
            self.objects["ball"],
            self.arms["panda-1"].tool_pose.p + [0, 0, self.params["radius"] + 0.0005],
        )
        self.events.flags.update(robot_work=0.0, launch_count=0, target=[0, 0, 0.142])

    def before_physics(self):
        # Identical to the base loop except the cart reads its seeded clock
        # shift (0.0 in nominal, so its targets are bit-for-bit unchanged).
        shift = self.events.flags.get("cart_clock_shift", 0.0)
        for name, fixture in self.fixtures.items():
            fixture.step(self.time + shift if name == "cart" else self.time, self.dt)

    def update_task(self):
        f = self.fixtures["lever"]
        right = self.arms["panda-1"]
        impulse = self.contact("left_tool", "lever_pad") + self.contact(
            "left_tool", "lever"
        )
        self.events.flags["robot_work"] += impulse * max(
            0.0, -self.arms["panda-0"].tool_body.linear_velocity[2]
        )
        if self.phase in (0, 3):
            local=(body(f.link).entity_pose.inv()*body(self.objects['ball']).entity_pose).p
            loaded = (
                self.contact("ball", "lever") > 0
                and not self.contact("ball", "right_tool")
                and abs(f.q) < 0.12
                and np.linalg.norm(local[:2]-[-.12,0]) < .021
                and .024 < local[2] < .044
                and np.linalg.norm(velocity(self.objects['ball'])-body(f.link).linear_velocity)<.08
            )
            clear = np.linalg.norm(right.tool_pose.p - [0, 0, 0.18]) > 0.16
            if self.events.hold(f'loaded_hold_{self.phase}',loaded,self.time,.1):
                self.events.once(f"load_cycle_{self.phase}", self.time)
            if self.events.has(f"load_cycle_{self.phase}") and clear:
                self.advance()
        elif self.phase in (1, 4):
            key = f"strike_cycle_{self.phase}"
            if impulse:
                self.events.once(key, self.time, impulse=impulse)
            if (
                self.events.has(key)
                and free_interval(self, "ball", f"flight_cycle_{self.phase}") > 0.04
                and position(self.objects["ball"])[2] > 0.20
            ):
                self.events.flags["launch_count"] += 1
                self.advance(lever_velocity=f.v)
        elif self.phase == 2 and cup_catch(
            self, "ball", "panda-1", "intermediate_receive"
        ):
            self.advance()
        elif self.phase == 5:
            cart = self.fixtures["cart"]
            if self.phase_hold(
                containment(self, "ball", cart.link, 0.075, 0.06, self.params["radius"])
                and abs(cart.v) > 0.02,
                0.7,
            ):
                self.events.physical_success = True
        if self.contact("ball", "left_tool"):
            self.events.fail("direct_ball_hit", self.time)
