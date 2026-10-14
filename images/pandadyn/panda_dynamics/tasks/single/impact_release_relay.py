import numpy as np
import sapien
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import (
    ball, box, set_initial, position, velocity, add_box, finish, material,
)
from panda_dynamics.props.mechanisms import gravity_channel, quat_xyz
from panda_dynamics.props.fixtures import DrivenFixture
from panda_dynamics.props.supports import pedestal


def lever_latch(scene, name, pivot, length, tail, height, friction, tail_half=(0.003, 0.012)):
    """Task-local copy of the shared passive gate with a trigger tail.

    The gate plate reaches `length` toward -y across the chute exactly as the
    shared gate does; the same rigid plate continues `tail` toward +y beyond
    the pivot. A -x push on the tail turns the gate the same way (+x at the
    tip) as the retained ball does, so an incoming cue can open it.
    """
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
        [[-1.5, 1.5]],
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=friction,
        damping=0.001,
    )
    add_box(
        moving,
        [0.006, length / 2, height / 2],
        [0, -length / 2, height / 2],
        mat=material(0.2, 0.35),
        color=[0.84, 0.57, 0.19, 1],
        density=220,
    )
    # Light trigger tail at the cue's height; it starts at the pivot hub.
    add_box(
        moving,
        [tail_half[0], tail / 2, tail_half[1]],
        [0, tail / 2, tail_half[1] + 0.001],
        mat=material(0.2, 0.35),
        color=[0.84, 0.57, 0.19, 1],
        density=220,
    )
    # Tip block kept within the plate's height (the shared gate raises it
    # 0.07 m, into the forearm's path above the interception area).
    add_box(
        moving,
        [0.016, 0.012, 0.012],
        [0, -length, height - 0.012],
        color=[0.8, 0.35, 0.17, 1],
        density=220,
    )
    builder.initial_pose = sapien.Pose(pivot)
    art = builder.build(name=name + "_fixture", fix_root_link=True)
    fixture = DrivenFixture(art, art.links[1], force=0, kp=0, kd=0.005, speed=0, phase=0.0)
    fixture.motion = "passive"
    fixture.enabled = False
    fixture.joint.set_friction(friction)
    fixture.reset(0.0, 0)
    return fixture


class ImpactReleaseRelay(PandaDynamicEnv):
    TASK = "S04-ImpactReleaseRelay"
    NAMESPACE = "PandaMultiStage"
    TOOL = "paddle"
    # Planner fractions of the (unchanged) joint limits. The original 0.25/
    # 0.015 cannot follow a strike or a velocity-matched catch; at the base
    # default jerk 0.05 the streamed references excite a j1/j3 mode past the
    # measured 20 ms joint-3 acceleration limit.
    REFERENCE_ACCELERATION = .55
    REFERENCE_JERK = .03
    WRIST_DAMPING = (24.,20.,14.)
    # Layout B: the chute (y=-0.06) and the latch sit near the robot; the cue
    # deck runs beside the chute on +y; the strike station, the chute exit,
    # the interception area, the passage and the zone are all within ~0.3 m.
    CHUTE_Y = -0.06
    CHUTE_TOP = (-0.30, CHUTE_Y, 0.205)
    CHUTE_END = (0.05, CHUTE_Y, 0.045)
    LATCH_PIVOT = (-0.185, 0.0, 0.170)
    LATCH_LENGTH = 0.125
    LATCH_TAIL = 0.13
    LATCH_TAIL_HALF = (0.003, 0.012)
    # Cue impact -> payload clear of the gate and rolling. Measured on the v2
    # evidence: 0.33-0.64 s for prompt releases; 3.4 s for a ball that stopped
    # on the opened gate and crept through on joint friction.
    RELEASE_WINDOW = 1.0
    DECK_X = (-0.33, 0.45)
    DECK_Y = (0.02, 0.21)
    CUE_Y = 0.15
    STRIKE_X = 0.10  # reference station the cue reaches after `preview` s
    # Passage: the original two 0.13 m walls, 0.09 m clear, turned so their
    # axis follows the redirected payload (-y, 33 deg toward +x).
    PASSAGE_ENTRY = (0.285, -0.163)
    PASSAGE_YAW = 0.583
    INTERCEPT_X = 0.10  # payload x beyond which a tool contact intercepts it
    TOOL_START = (0.236, 0.266, 0.197)
    TOOL_QUAT = (np.cos(0.35 / 2), 0, 0, np.sin(0.35 / 2))
    MOUNT = (0.12, -0.13, 0.04)
    # Base 0.10 m nearer than the default so the zone's stop pose is reachable.
    ARM_SETUPS = (ArmSetup("paddle", TOOL_START, base=(-0.45, 0, 0), mount=MOUNT,
                           quaternion=TOOL_QUAT, half=0.05),)
    PHASES = (
        "cue_strike",
        "mechanical_unlatch",
        "payload_interception",
        "passage_redirection",
        "payload_braking",
    )
    INSTRUCTION = (
        "击打来袭撞子打开实体闩锁，拦截从滑道下落的原有球，再改变方向并制动到目标区。"
    )

    def build_task(self):
        self.objects["cue"] = box(
            self.scene,
            "cue",
            [0.02, 0.02, 0.012],
            [0.3, self.CUE_Y, 0.1775],
            mass=0.045,
            mu=0.01,
            restitution=0.45,
        )
        self.objects["payload"] = ball(
            self.scene,
            "payload",
            self.params["radius"],
            self.params["object_mass"],
            0.12,
        )
        # Low-friction deck carrying the cue; 4 mm curbs at its -x end and +y
        # edge keep a spent cue on the deck (both lie below the paddle and the
        # latch tail).
        x0, x1 = self.DECK_X
        y0, y1 = self.DECK_Y
        deck = self.scene.create_actor_builder()
        add_box(deck, [(x1 - x0) / 2, (y1 - y0) / 2, 0.01], mat=material(0.01, 0.05))
        add_box(deck, [0.006, (y1 - y0) / 2, 0.002], [-(x1 - x0) / 2 + 0.006, 0, 0.012],
                mat=material(0.3, 0.05))
        add_box(deck, [(x1 - x0) / 2, 0.003, 0.002], [0, (y1 - y0) / 2 - 0.003, 0.012],
                mat=material(0.3, 0.05))
        finish(deck, "cue_lane", [(x0 + x1) / 2, (y0 + y1) / 2, 0.155], static=True)
        gravity_channel(
            self.scene,
            "payload_chute",
            self.CHUTE_TOP,
            self.CHUTE_END,
            width=0.03,
            wall=0.012,
            mu=0.12,
        )
        self.fixtures["latch"] = lever_latch(
            self.scene,
            "latch",
            self.LATCH_PIVOT,
            self.LATCH_LENGTH,
            self.LATCH_TAIL,
            0.045,
            self.params["latch_friction"],
            self.LATCH_TAIL_HALF,
        )
        # A zero-preload torsion spring retains the ball against gravity. Its
        # fixed equilibrium never changes when a collision or stage occurs.
        latch = self.fixtures["latch"]
        latch.kp, latch.kd, latch.force = self.params["latch_spring"], .001, .08
        latch.motion = "spring"
        latch.joint.set_drive_properties(latch.kp, latch.kd, latch.force, mode="force")
        axis, lateral = self.passage_frame()
        entry = np.array(self.PASSAGE_ENTRY)
        q = (np.cos(self.PASSAGE_YAW / 2), 0, 0, np.sin(self.PASSAGE_YAW / 2))
        for i, side in enumerate((-1, 1)):
            c = entry + 0.065 * axis + side * 0.055 * lateral
            box(
                self.scene,
                f"passage_{i}",
                [0.01, 0.065, 0.03],
                [c[0], c[1], 0.03],
                static=True,
                q=q,
            )

    def passage_frame(self):
        """Unit vectors along the passage (travel direction) and across it."""
        a = self.PASSAGE_YAW
        return np.array([np.sin(a), -np.cos(a)]), np.array([np.cos(a), np.sin(a)])

    def reset_task(self):
        v = self.params["incoming_speed"]
        set_initial(
            self.objects["cue"],
            [self.STRIKE_X + v * self.params["preview"],
             self.CUE_Y + self.rng.uniform(-0.006, 0.006), 0.1775],
            [-v, 0, 0],
        )
        px, py, pz = self.LATCH_PIVOT
        set_initial(self.objects["payload"], [px - 0.048, py - 0.06, 0.193])
        self.fixtures["latch"].reset()
        axis, lateral = self.passage_frame()
        # Same placement as the original: 0.085 m beyond the wall ends,
        # 0.005 m off the passage centreline.
        zone = np.array(self.PASSAGE_ENTRY) + 0.215 * axis - 0.005 * lateral
        zone = [float(zone[0]), float(zone[1]), 0.018]
        self.events.flags.update(zone=zone, target=[px, py - 0.06, 0.17])
        self.events.emit("cue_release", 0.0, object="cue")

    def chute_direction(self):
        d = np.subtract(self.CHUTE_END, self.CHUTE_TOP)
        return d / np.linalg.norm(d)

    def passage_coordinates(self, p):
        """(along, across) payload coordinates from the passage entry."""
        axis, lateral = self.passage_frame()
        d = np.asarray(p[:2]) - np.array(self.PASSAGE_ENTRY)
        return float(d @ axis), float(d @ lateral)

    def update_task(self):
        p = position(self.objects["payload"])
        px = self.LATCH_PIVOT[0]
        if self.contact("tool", "latch"):
            self.events.fail("direct_latch_shortcut", self.time)
        if self.phase == 0 and self.contact("cue", "tool"):
            self.advance()
        elif self.phase == 1:
            if self.contact("cue", "latch"):
                self.events.once("cue_latch_impact", self.time)
            q = self.fixtures["latch"].q
            if (
                self.events.has("cue_latch_impact")
                and abs(q) > 0.45
                and p[0] > px + 0.02
            ):
                if not self.events.has("latch_open"):
                    self.events.emit("latch_open", self.time, latch_angle=q)
                    self.events.flags["latch_open_angle"] = q
            impact = self.events.first_time("cue_latch_impact")
            # A genuine release, not a ball still leaning on the opened gate:
            # after the (unchanged) open-gate condition, the payload centre has
            # passed the blade tip at its current angle by a ball radius plus
            # the plate half-thickness, rolls down the chute at >= 0.4 m/s,
            # and all this within RELEASE_WINDOW of the cue's impact.
            if (
                self.events.has("latch_open")
                and p[0] - px > self.LATCH_LENGTH * np.sin(abs(q)) + self.params["radius"] + 0.006
                and velocity(self.objects["payload"]) @ self.chute_direction() >= 0.4
                and self.time - impact <= self.RELEASE_WINDOW
            ):
                self.advance(latch_angle=self.events.flags["latch_open_angle"])
            elif impact is not None and self.time - impact > self.RELEASE_WINDOW:
                self.events.fail("payload_not_released", self.time)
        elif self.phase == 2:
            if self.contact("payload", "payload_chute"):
                self.events.once("payload_chute_contact", self.time)
            if (
                self.contact("payload", "tool")
                and p[0] > self.INTERCEPT_X
                and self.events.has("payload_chute_contact")
            ):
                self.advance(impulse=self.contact("payload", "tool"))
        elif (
            self.phase == 3
            and abs(self.passage_coordinates(p)[1]) < 0.045
            and self.passage_coordinates(p)[0] > 0.105
            and not self.contact("payload", "tool")
        ):
            self.advance()
        elif self.phase == 4:
            if self.contact("payload", "tool"):
                self.events.once("braking_contact", self.time)
            condition = (
                np.linalg.norm(p[:2] - np.array(self.events.flags["zone"])[:2]) < 0.05
                and np.linalg.norm(velocity(self.objects["payload"])) < 0.035
                and self.contact("payload", "table") > 0
                and self.events.has("braking_contact")
            )
            if self.phase_hold(condition, 0.5):
                self.events.physical_success = True
