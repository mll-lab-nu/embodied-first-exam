import numpy as np
import sapien
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import (
    add_box,
    box,
    material,
    position,
    set_initial,
    velocity,
)
from panda_dynamics.props.fixtures import DrivenFixture
from panda_dynamics.tasks.predicates import crossed

# Motor-driven bank board on the left arm's side of the post wall, at the end
# of the first route's lane. The 80 x 12 x 32 mm board slides along its own
# face line on a prismatic joint (table slot) driven by a finite-force PD
# motor: its face normal stays at BANK_NORMAL, the board itself moves.
BANK_NORMAL = 0.785  # rad, face normal (cos, sin) in the table plane
BANK_CENTER = (-0.04, -0.032, 0.019)  # slot centre: puck contact point for a lane-centre puck
BANK_HALF = (0.006, 0.04, 0.016)  # thickness, length, height half extents
BANK_STROKE = 0.09  # m, slide amplitude along the face line
BANK_MASS = 0.15
BANK_FORCE = 10.0  # N, motor effort limit
BANK_KP, BANK_KD = 80.0, 8.0

STRIKE_SPEED = 0.20  # m/s: a right "strike" must send the puck back toward the left (-x)
STRIKE_GAP = 0.05  # s: the release is counted within this time after the last paddle contact
REBOUND_SPEED = 0.08  # m/s: approach speed of the puck at a counted left-board contact
MIN_BOARD_SHIFT = 0.035  # m between the two left-board contact poses
MIN_BOARD_TURN = 0.24  # rad between them: |<q1, q2>| < cos(turn / 2)
MOVING_BANK = 0.02  # m/s: measured bank slide speed just before a counted bank contact


class BankDrive(DrivenFixture):
    """Declared slide law s(t) = phase + BANK_STROKE * sin(w (t + clock)),
    w = speed / BANK_STROKE (peak speed = config fixture_speed)."""

    clock = 0.0

    def law(self, time):
        w = self.speed / BANK_STROKE
        angle = w * (time + self.clock)
        return (
            self.phase + BANK_STROKE * np.sin(angle),
            self.speed * np.cos(angle),
        )

    def step(self, time, dt):
        if not self.enabled:
            return
        self.target, velocity_target = self.law(time)
        self.joint.set_drive_target(self.target)
        self.joint.set_drive_velocity_target(velocity_target)
        effort = np.clip(
            self.kp * (self.target - self.q) + self.kd * (velocity_target - self.v),
            -self.force,
            self.force,
        )
        self.work += float(effort * self.v * dt)

    def state(self):
        return dict(super().state(), clock=self.clock)


def sliding_bank(scene, name, speed):
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name(name + "_base")
    tangent = BANK_NORMAL + np.pi / 2
    slide = [np.cos(tangent / 2), 0, 0, np.sin(tangent / 2)]  # joint x -> face line
    # Slot plate flush with the worktop (visual only; the joint is the guide).
    root.add_box_visual(
        pose=sapien.Pose([0, 0, 0.0005 - BANK_CENTER[2]], slide),
        half_size=[BANK_STROKE + BANK_HALF[1], 0.008, 0.0005],
        material=[0.22, 0.25, 0.29, 1],
    )
    root.set_mass_and_inertia(1.0, sapien.Pose(), [1e-3, 1e-3, 1e-3])
    board = builder.create_link_builder(root)
    board.set_name(name)
    board.set_joint_name(name + "_joint")
    board.set_joint_properties(
        "prismatic",
        [[-BANK_STROKE - 0.03, BANK_STROKE + 0.03]],
        sapien.Pose(q=slide),
        sapien.Pose(q=slide),
        friction=0.0,
        damping=0.0,
    )
    face = [np.cos(BANK_NORMAL / 2), 0, 0, np.sin(BANK_NORMAL / 2)]
    add_box(
        board,
        BANK_HALF,
        q=face,
        color=[0.85, 0.75, 0.15, 1],
        mat=material(0.05, 0.95),
    )
    builder.initial_pose = sapien.Pose(BANK_CENTER)
    art = builder.build(name=name + "_fixture", fix_root_link=True)
    rb = art.links[1]._objs[0]
    rb.inertia *= BANK_MASS / rb.mass
    rb.mass = BANK_MASS
    fixture = BankDrive(
        art, art.links[1], speed=speed, force=BANK_FORCE, kp=BANK_KP, kd=BANK_KD
    )
    fixture.origin = np.array(BANK_CENTER)
    return fixture


class MovingBankRelay(PandaDynamicEnv):
    TASK = "D06-MovingBankRelay"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("preparing_board", "striker"),
        ("rebound_operator", "preparing_receiver"),
        ("relay_shooter", "striker"),
        ("rebound_operator", "cleared_striker"),
        ("goal_shooter", "cleared_striker"),
    )
    # Both paddles: 100 mm wide, 0.2 kg (config tool_half / tool_mass).
    ARM_SETUPS = (
        ArmSetup(
            "paddle",
            (-0.10, 0.17, 0.045),
            base=(-0.55, -0.22, 0),
        ),
        ArmSetup(
            "paddle",
            (0.27, -0.11, 0.045),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    PHASES = (
        "right_first_strike",
        "left_first_rebound",
        "right_recovery_strike",
        "left_changed_rebound",
        "terminal_goal",
    )
    INSTRUCTION = (
        "右臂把迎面滑来的冰球击回，冰球须穿过第一开口、撞上往复滑动的反弹板后再撞上左臂挡板；"
        "左臂把它送回右侧，右臂再次击回，冰球须穿过第二开口撞上换了位置和角度的左臂挡板，"
        "最后由左臂把同一冰球经第二开口射过球门线。"
    )

    def build_task(self):
        self.objects["puck"] = box(
            self.scene,
            "puck",
            [0.022, 0.022, 0.012],
            [0.12, -0.01, 0.013],
            mass=self.params["object_mass"],
            mu=0.012,
            restitution=0.65,
        )
        box(
            self.scene,
            "return_rail",
            [0.24, 0.008, 0.035],
            [0.15, 0.29, 0.035],
            static=True,
            restitution=0.7,
        )
        for i, y in enumerate((-0.01, 0.16)):
            for sign in (-1, 1):
                box(
                    self.scene,
                    f"route_{i}_{sign}",
                    [0.012, 0.025, 0.03],
                    [0.16, y + sign * 0.075, 0.03],
                    static=True,
                )
        box(
            self.scene,
            "backstop",
            [0.01, 0.07, 0.035],
            [0.48, 0.16, 0.035],
            static=True,
        )
        self.fixtures["bank"] = sliding_bank(
            self.scene, "bank", self.params["fixture_speed"]
        )

    def reset_task(self):
        set_initial(
            self.objects["puck"],
            # Inside the route_0 aperture (posts at y < -0.06 and y > 0.04);
            # the 22 mm half-width puck keeps at least 8 mm clearance.
            [0.12, self.rng.uniform(-0.03, 0.01), 0.0125],
            [self.params["incoming_speed"], 0, 0],
        )
        # Declared bank law (BankDrive.law): s(t) = 0.09 sin(w (t + clock)) m
        # along the face line, w = fixture_speed / 0.09; clock = bank_clock +
        # U(0, fixture_phase * period / (2 pi)) (hard: a full random period).
        bank = self.fixtures["bank"]
        speed = self.params["fixture_speed"]
        w = speed / BANK_STROKE
        clock = self.params["bank_clock"]
        if self.params["fixture_phase"] > 0:
            clock += self.rng.uniform(0.0, self.params["fixture_phase"]) / w
        bank.reset(BANK_STROKE * np.sin(w * clock), speed * np.cos(w * clock))
        bank.phase = 0.0
        bank.clock = clock
        self.events.flags.update(goal=[0.42, 0.16, 0.012])

    # ----- measurements -------------------------------------------------
    def _touch(self, flags):
        for side in ("left", "right"):
            if self.contact("puck", side + "_tool") > 0:
                flags[side + "_touch"] = self.time

    def _struck_back(self, flags):
        """The right paddle has just released the puck, on the right of the
        post wall, travelling toward the left arm at >= STRIKE_SPEED."""
        last = flags.get("right_touch")
        started = flags.get("phase_started", 0.0)
        return (
            last is not None
            and last > started
            and self.time - last <= STRIKE_GAP
            and not self.contact("puck", "right_tool")
            and not self.contact("puck", "left_tool")
            and position(self.objects["puck"])[0] > 0.18
            and velocity(self.objects["puck"])[0] <= -STRIKE_SPEED
        )

    def update_task(self):
        flags = self.events.flags
        puck = self.objects["puck"]
        self._touch(flags)
        left = self.contact("puck", "left_tool") > 0
        right = self.contact("puck", "right_tool") > 0
        approach = flags.get("puck_speed", 0.0)
        if self.phase == 1:
            if crossed(self, "puck", [0.16, -0.01, 0], direction=-1, half=0.048):
                self.events.once("first_route_aperture", self.time)
                flags["route_time"] = self.time
                flags.pop("bank_time", None)
            # Between the aperture and the counted left contact only the bank
            # may touch the puck; a paddle contact first re-arms the route.
            if right or (left and "bank_time" not in flags):
                flags.pop("route_time", None)
                flags.pop("bank_time", None)
            bank = self.fixtures["bank"]
            if (
                "route_time" in flags
                and "bank_time" not in flags
                and self.contact("puck", "bank") > 0
                and flags.get("bank_speed", 0.0) >= MOVING_BANK
            ):
                flags["bank_time"] = self.time
                self.events.emit(
                    "moving_bank_contact",
                    self.time,
                    bank_position=bank.q,
                    bank_speed=flags.get("bank_speed", 0.0),
                    puck_speed=approach,
                )
        if self.phase == 3:
            if crossed(self, "puck", [0.16, 0.16, 0], direction=-1, half=0.048):
                self.events.once("second_route_aperture", self.time)
                flags["route_time"] = self.time
            if right:
                flags.pop("route_time", None)
        if self.phase == 4:
            if crossed(self, "puck", [0.16, 0.16, 0], direction=1, half=0.048):
                self.events.once("goal_route_aperture", self.time)
                flags["goal_route"] = True
            if right:
                flags["goal_route"] = False

        if self.phase in (0, 2):
            if self._struck_back(flags) and (
                self.phase == 0 or self.time - flags["phase_started"] > 0.06
            ):
                self.advance(
                    puck_velocity=velocity(puck).tolist(),
                )
        elif (
            self.phase == 1
            and left
            and "bank_time" in flags
            and approach >= REBOUND_SPEED
        ):
            arm = self.arms["panda-0"]
            flags["first_board_pose"] = np.r_[arm.tool_pose.p, arm.tool_pose.q].tolist()
            flags.pop("route_time", None)
            self.advance(
                impulse=self.contact("puck", "left_tool"), approach_speed=approach
            )
        elif (
            self.phase == 3
            and left
            and "route_time" in flags
            and approach >= REBOUND_SPEED
        ):
            first = np.array(flags["first_board_pose"])
            arm = self.arms["panda-0"]
            if np.linalg.norm(arm.tool_pose.p - first[:3]) > MIN_BOARD_SHIFT and abs(
                np.dot(arm.tool_pose.q, first[3:])
            ) < np.cos(MIN_BOARD_TURN / 2):
                self.advance(
                    impulse=self.contact("puck", "left_tool"), approach_speed=approach
                )
        elif (
            self.phase == 4
            and flags.get("goal_route")
            and crossed(self, "puck", flags["goal"], half=0.055)
            and not right
            and flags.get("left_touch", -1.0) > flags["phase_started"]
        ):
            self.advance()
            self.events.physical_success = True
        flags["puck_speed"] = float(np.linalg.norm(velocity(puck)[:2]))
        flags["bank_speed"] = abs(self.fixtures["bank"].v)
