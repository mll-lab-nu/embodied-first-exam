import numpy as np
import sapien
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import add_box, box, material, set_initial, position, velocity
from panda_dynamics.props.fixtures import DrivenFixture, single_axis
from panda_dynamics.props.mechanisms import quat_xyz
from panda_dynamics.props.supports import pedestal
from panda_dynamics.tasks.predicates import crossed

# v6: the swing gate across the exit lane. Hinge on the lane's north edge; at
# q = 0 the 0.12 m leaf spans the whole lane (y 0.06..0.18) on the line x = 0.37.
GATE_PIVOT = (0.37, 0.18, 0.0315)
DOOR_X = 0.37
DOOR_Y = 0.12
DOOR_HALF = 0.055


class CyclingGate(DrivenFixture):
    """Swing gate on a finite-torque motor that follows a declared periodic
    profile: closed, a cosine opening ramp to `open_angle`, a hold, a cosine
    closing ramp back to 0, closed again.  The clock offset is drawn at reset
    (hard) and is not exported as the fixture phase; it is observable only
    through the gate's motion."""

    def configure(self, period, open_angle, ramp, hold, close):
        self.period, self.open_angle = float(period), float(open_angle)
        self.ramp, self.hold, self.close = float(ramp), float(hold), float(close)
        self.offset = 0.0

    def profile(self, time):
        tau = (time + self.offset) % self.period
        a, r, h, c = self.open_angle, self.ramp, self.hold, self.close
        if tau < r:
            x = np.pi * tau / r
            return a * (1 - np.cos(x)) / 2, a * np.pi / (2 * r) * np.sin(x)
        tau -= r
        if tau < h:
            return a, 0.0
        tau -= h
        if tau < c:
            x = np.pi * tau / c
            return a * (1 + np.cos(x)) / 2, -a * np.pi / (2 * c) * np.sin(x)
        return 0.0, 0.0

    def reset(self, q=0.0, v=0.0):
        super().reset(q, v)
        self.speed = 0.0
        self.target, velocity_target = self.profile(0.0)
        self.joint.set_drive_target(self.target)
        self.joint.set_drive_velocity_target(velocity_target)

    def step(self, time, dt):
        self.target, velocity_target = self.profile(time)
        self.joint.set_drive_target(self.target)
        self.joint.set_drive_velocity_target(velocity_target)
        effort = np.clip(
            self.kp * (self.target - self.q) + self.kd * (velocity_target - self.v),
            -self.force,
            self.force,
        )
        self.work += float(effort * self.v * dt)

    def state(self):
        return dict(super().state(), offset=self.offset)

    def restore(self, state):
        for k, v in state.items():
            setattr(self, k, v)
        self.joint.set_drive_target(self.target)


def cycling_gate(scene, name, pivot, length=0.12, height=0.055, torque=0.2):
    """Task-local copy of props.mechanisms.passive_gate (same leaf, base and
    vertical hinge) with a 0..1.5 rad hinge range and a motor drive instead of
    the weak spring."""
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name(name + "_base")
    add_box(root, [0.013, 0.013, 0.012], [0, 0, -0.035], color=[0.28, 0.31, 0.34, 1])
    pedestal(root, pivot, top_local=-0.047)
    moving = builder.create_link_builder(root)
    moving.set_name(name)
    axis = quat_xyz([0, -np.pi / 2, 0])
    moving.set_joint_name(name + "_joint")
    moving.set_joint_properties(
        "revolute",
        [[0.0, 1.5]],
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=0.0,
        damping=0.0,
    )
    add_box(
        moving,
        [0.006, length / 2, height / 2],
        [0, -length / 2, height / 2],
        mat=material(0.2, 0.35),
        color=[0.84, 0.57, 0.19, 1],
        density=220,
    )
    add_box(
        moving,
        [0.016, 0.012, 0.012],
        [0, -length, 0.07],
        color=[0.8, 0.35, 0.17, 1],
        density=220,
    )
    builder.initial_pose = sapien.Pose(pivot)
    art = builder.build(name=name + "_fixture", fix_root_link=True)
    fixture = CyclingGate(art, art.links[1], force=torque, kp=2.0, kd=0.03, speed=0.0)
    fixture.motion = "profile"
    return fixture


class MovingBridgePuckRelay(PandaDynamicEnv):
    TASK = "S12-MovingBridgePuckRelay"
    NAMESPACE = "PandaMultiStage"
    TOOL = "paddle"
    # v6: the parked paddle hangs 16 mm above the incoming puck's top face, so
    # the incoming puck passes under it unless the arm lowers it in time.
    TOOL_START = (-0.08, -0.15, 0.10)
    PHASES = (
        "incoming_strike",
        "physical_bridge_transfer",
        "exit_interception",
        "second_strike",
        "closing_gate_goal",
    )
    INSTRUCTION = (
        "用桨板在来球仍以不低于 0.25 m/s 滑行时击中它，使冰球经顺时针转动的转桥到达出口滑道，"
        "在出口再次截获、分开后再击打，让冰球不碰门地趁周期开合的摆门打开时穿过门洞并越过球门线。"
    )

    def build_task(self):
        self.objects["puck"] = box(
            self.scene,
            "puck",
            [0.022, 0.022, 0.012],
            [0.07, -0.13, 0.0465],
            mass=self.params["object_mass"],
            mu=0.15,
            restitution=0.5,
        )
        # v5: (a) the lane's bridge-side edge is moved 25 mm toward the bridge
        # (y edge -0.070 -> -0.045): the bridge end only passes the old edge over
        # y in [-0.10, -0.07] (30 mm), narrower than the 44 mm puck. (b) The
        # three sliding surfaces now step down 2 mm at each hand-off (source
        # 0.034 -> bridge 0.032 -> exit 0.030 instead of all at 0.030): with
        # coplanar sharp edges the sliding puck's front face hit the bridge's
        # top edge with a horizontal contact normal and stopped (measured
        # 0.0047 N s at x=0.080, z=0.030). Length, far edge, friction unchanged.
        box(
            self.scene,
            "source_lane",
            [0.14, 0.0725, 0.012],
            [-0.08, -0.1175, 0.022],
            static=True,
            mu=0.025,
        )
        # v6: rate from the config (`bridge_rate`), turning clockwise (seen from
        # above): the end that faces the source lane reaches the exit lane after
        # a quarter turn instead of three quarters.
        rate = -self.params["bridge_rate"]
        self.fixtures["bridge"] = single_axis(
            self.scene,
            "bridge",
            [0.18, -0.05, 0.032],
            kind="rotary",
            shape="platform",
            speed=rate,
            force=0.5,
            mass=0.20,
            platform_half=(0.10, 0.05),
        )
        box(
            self.scene,
            "exit_lane",
            [0.16, 0.055, 0.014],
            [0.25, 0.12, 0.016],
            static=True,
            mu=0.04,
        )
        # v6: the old gate (0.00012 N m/rad spring, leaf resting on the lane)
        # never moved from q = 1.1. The leaf now clears the lane by 1.5 mm and a
        # finite-torque motor cycles it closed -> open -> closed.
        gate = cycling_gate(
            self.scene, "gate", GATE_PIVOT, torque=self.params["gate_torque"]
        )
        gate.configure(
            self.params["gate_period"],
            self.params["gate_open_angle"],
            self.params["gate_ramp"],
            self.params["gate_hold"],
            self.params["gate_close"],
        )
        self.fixtures["gate"] = gate
        box(
            self.scene,
            "goal_backstop",
            [0.01, 0.07, 0.04],
            [0.54, 0.12, 0.04],
            static=True,
        )

    def reset_task(self):
        lateral = self.params["incoming_lateral"]
        set_initial(
            self.objects["puck"],
            [0.06, -0.13 + self.rng.uniform(-lateral, lateral), 0.0465],
            [-self.params["incoming_speed"], 0, 0],
        )
        spread = self.params["bridge_angle_spread"]
        rate = -self.params["bridge_rate"]
        self.fixtures["bridge"].reset(self.rng.uniform(-spread, spread), rate)
        gate = self.fixtures["gate"]
        gate.offset = (
            self.rng.uniform(0.0, 1.0) * self.params["gate_phase_spread"] * gate.period
        )
        q0, v0 = gate.profile(0.0)
        gate.reset(q0, v0)
        self.events.flags.update(goal=[0.48, 0.12, 0.043], puck_speed_before=0.0)

    def update_task(self):
        contact = self.contact("puck", "tool")
        p = position(self.objects["puck"])
        v = velocity(self.objects["puck"])
        if self.phase == 0 and contact:
            # The puck's speed on the substep before the first paddle contact.
            before = self.events.flags["puck_speed_before"]
            if before >= self.params["strike_min_speed"]:
                self.advance(incoming_speed=before)
            else:
                self.events.fail("strike_on_slow_puck", self.time)
        elif self.phase == 1:
            if self.contact("puck", "bridge"):
                self.events.once("bridge_support", self.time)
            if (
                self.events.has("bridge_support")
                and self.contact("puck", "exit_lane")
                and not self.contact("puck", "bridge")
            ):
                self.advance(exit_velocity=velocity(self.objects["puck"]).tolist())
        elif self.phase == 2 and contact:
            self.advance()
        elif self.phase == 3:
            if not contact:
                self.events.flags.setdefault("separated", self.time)
            if (
                contact
                and self.time - self.events.flags.get("separated", self.time) > 0.035
            ):
                self.advance()
        elif self.phase == 4:
            gate = self.fixtures["gate"]
            previous = self.previous_positions["puck"]
            if self.contact("puck", "gate"):
                self.events.fail("puck_touched_gate", self.time)
            elif previous[0] <= DOOR_X < p[0] and abs(p[1] - DOOR_Y) < DOOR_HALF:
                if gate.q >= self.params["gate_pass_angle"]:
                    self.events.once(
                        "gate_passage", self.time, gate_angle=gate.q, puck_speed=float(np.linalg.norm(v[:2]))
                    )
                else:
                    self.events.fail("gate_not_open_at_doorway", self.time)
            elif crossed(self, "puck", self.events.flags["goal"], half=0.045):
                if (
                    not contact
                    and gate.q > 0.20
                    and self.events.has("gate_passage")
                ):
                    self.advance()
                    self.events.physical_success = True
                else:
                    self.events.fail("closed_gate_or_carried_puck", self.time)
        self.events.flags["puck_speed_before"] = float(np.linalg.norm(v[:2]))
