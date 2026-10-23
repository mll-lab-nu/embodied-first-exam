import numpy as np
import sapien
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import box, set_initial, position, velocity
from panda_dynamics.props.mechanisms import passive_gate
from panda_dynamics.tasks.predicates import bilateral_grip, crossed

# Handle block of passive_gate(length=0.13) in the gate link frame (link origin
# on the hinge axis at the pivot; the leaf box spans local z 0..0.055, the
# handle box sits on top of the free end).
HANDLE_CENTER = np.array([0.0, -0.13, 0.07])
HANDLE_HALF = np.array([0.016, 0.012, 0.012])
HANDLE_TOLERANCE = 0.002  # leaf top (local z 0.055) stays outside: 0.058 - 0.002 > 0.055
GRIP_IMPULSE = 1e-7  # same per-finger threshold as predicates.bilateral_grip
GATE_OPEN = 0.3  # |q| the held gate must keep while the right arm uses the opening


class SpringGateSwitchyard(PandaDynamicEnv):
    TASK = "D07-SpringGateSwitchyard"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("gate_operator", "preparing_striker"),
        ("gate_operator", "preparing_striker"),
        ("gate_operator", "preparing_striker"),
        ("gate_operator", "preparing_striker"),
        ("gate_operator", "preparing_striker"),
    )
    ARM_SETUPS = (
        ArmSetup(None, (0.04, -0.10, 0.16), base=(-0.55, -0.22, 0)),
        ArmSetup(
            "paddle",
            (0.30, -0.08, 0.045),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    ALLOW_FINGER_CONTACTS = True
    ALLOWED_FINGER_FIXTURES = ("gate",)
    PHASES = (
        "left_gate_open",
        "right_loop_shot",
        "gate_reconfiguration",
        "return_interception",
        "final_gate_shot",
    )
    INSTRUCTION = (
        "左手两指夹住弹簧门末端的把手、把门朝右臂一侧推开，并在之后各阶段判定时仍夹着把手、门保持开着；"
        "右拍把冰球击过门轴送到场地远端，冰球碰到上护栏时门须已换到另一侧，"
        "随后右拍再次触到冰球，并把它射过场地开口外挡块前的球门线。"
    )

    def build_task(self):
        self.fixtures["gate"] = passive_gate(
            self.scene,
            "gate",
            [0.10, 0.05, 0.015],
            length=0.13,
            spring=0.015,
            friction=0.0002,
        )
        self.objects["puck"] = box(
            self.scene,
            "puck",
            [0.022, 0.022, 0.012],
            [0.20, -0.06, 0.013],
            mass=self.params["object_mass"],
            mu=0.01,
            restitution=0.65,
        )
        for name, half, p in (
            ("far_rail", [0.008, 0.18, 0.03], [-0.12, 0.05, 0.03]),
            ("upper_rail", [0.20, 0.008, 0.03], [0.08, 0.23, 0.03]),
            ("lower_rail", [0.20, 0.008, 0.03], [0.08, -0.15, 0.03]),
        ):
            box(
                self.scene,
                name,
                half,
                p,
                static=True,
                mu=self.params["rail_friction"],
                restitution=0.75,
            )
        box(self.scene, "backstop", [0.01, 0.07, 0.03], [0.48, 0.15, 0.03], static=True)

    def reset_task(self):
        self.fixtures["gate"].reset(0, 0)
        set_initial(
            self.objects["puck"],
            [0.20, -0.06 + self.rng.uniform(-0.008, 0.008), 0.0125],
            [self.params["incoming_speed"], 0, 0],
        )
        self.events.flags.update(goal=[0.43, 0.15, 0.012])

    def handle_grip(self):
        """Both left fingers press on the gate HANDLE (not merely the leaf).

        Returns (gripped, metrics). Only contact points of the current physics
        substep whose position, expressed in the gate link frame, lies inside the
        handle box grown by HANDLE_TOLERANCE count; each finger (finger or pad
        link) needs a summed handle impulse above GRIP_IMPULSE.
        """
        inverse = self.fixtures["gate"].raw.links[1].entity_pose.inv()
        impulse = {"left": 0.0, "right": 0.0}
        depth = {"left": -1.0, "right": -1.0}
        # largest distance of a counted point from the handle's y/z edges (no
        # tolerance): how far onto the handle block the finger presses
        yz = {"left": -1.0, "right": -1.0}
        for record in reversed(self.contact_records):
            if record["time"] != self.time:
                break
            pair = record["pair"]
            if "gate" not in pair:
                continue
            other = pair[1] if pair[0] == "gate" else pair[0]
            side = next(
                (
                    s
                    for s in impulse
                    if other in (f"left/panda_{s}finger", f"left/panda_{s}finger_pad")
                ),
                None,
            )
            if side is None:
                continue
            for point in record["points"]:
                local = (inverse * sapien.Pose(point["position"])).p
                inside = float(np.min(HANDLE_HALF + HANDLE_TOLERANCE - np.abs(local - HANDLE_CENTER)))
                if inside >= 0.0:
                    impulse[side] += float(np.linalg.norm(point["impulse_vector"]))
                    depth[side] = max(depth[side], inside)
                    yz[side] = max(yz[side], float(np.min(HANDLE_HALF[1:] - np.abs(local - HANDLE_CENTER)[1:])))
        gripped = all(value > GRIP_IMPULSE for value in impulse.values())
        return gripped, dict(
            handle_impulse=[impulse["left"], impulse["right"]],
            handle_depth=[depth["left"], depth["right"]],
            handle_yz_margin=[yz["left"], yz["right"]],
            gate_q=float(self.fixtures["gate"].q),
        )

    def gate_held(self, condition):
        """Bilateral grip on the handle plus a gate-angle condition."""
        if not condition or not bilateral_grip(self, "gate", "panda-0"):
            return False, None
        gripped, metrics = self.handle_grip()
        return gripped, metrics

    def update_task(self):
        gate = self.fixtures["gate"]
        if self.phase == 0:
            held, metrics = self.gate_held(gate.q > 0.5)
            if held:
                self.advance(**metrics)
        elif self.phase == 1:
            if self.contact("puck", "right_tool") and not self.events.has("first_shot"):
                held, metrics = self.gate_held(abs(gate.q) > GATE_OPEN)
                if held:
                    self.events.once("first_shot", self.time, **metrics)
            if (
                self.events.has("first_shot")
                and position(self.objects["puck"])[0] < -0.05
                and not self.contact("puck", "right_tool")
            ):
                held, metrics = self.gate_held(abs(gate.q) > GATE_OPEN)
                if held:
                    self.events.flags["loop_crossing"] = self.time
                    self.advance(
                        puck_speed=float(np.linalg.norm(velocity(self.objects["puck"])[:2])),
                        **metrics,
                    )
        elif self.phase == 2:
            # Hard (loop_window > 0): the shot must carry the puck round the loop
            # on its own: the upper-rail contact has to follow the hinge crossing
            # within loop_window seconds with no paddle contact in between.
            window = self.params["loop_window"]
            loop_time = self.time - self.events.flags["loop_crossing"]
            if window > 0 and (loop_time > window or self.contact("puck", "right_tool")):
                self.events.fail("loop_not_free", self.time)
                return
            if self.contact("puck", "upper_rail"):
                held, metrics = self.gate_held(gate.q < -0.35)
                if held:
                    self.advance(loop_time=float(loop_time), **metrics)
        elif self.phase == 3 and self.contact("puck", "right_tool"):
            # Hard: an interception of the still-moving return puck (its
            # planar speed just before the paddle contact).
            speed = float(np.linalg.norm(self.events.flags.get("puck_previous_velocity", [0, 0])))
            held, metrics = self.gate_held(abs(gate.q) > GATE_OPEN)
            if held:
                if speed < self.params["intercept_min_speed"]:
                    self.events.fail("static_interception", self.time)
                    return
                self.events.flags["return_strike"] = self.time
                self.advance(puck_speed=speed, **metrics)
        elif self.phase == 4:
            if (
                crossed(self, "puck", self.events.flags["goal"], half=0.055)
                and not self.contact("puck", "right_tool")
            ):
                held, metrics = self.gate_held(abs(gate.q) > GATE_OPEN)
                if held:
                    self.advance(
                        puck_speed=float(np.linalg.norm(velocity(self.objects["puck"])[:2])),
                        crossing_y=float(position(self.objects["puck"])[1]),
                        **metrics,
                    )
                    self.events.physical_success = True
        if self.phase == 3:
            v = velocity(self.objects["puck"])[:2]
            if not self.contact("puck", "right_tool"):
                self.events.flags["puck_previous_velocity"] = [float(v[0]), float(v[1])]
