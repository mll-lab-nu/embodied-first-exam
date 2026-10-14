import numpy as np
import sapien
from ruckig import Synchronization
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import (
    box,
    ball,
    container,
    set_initial,
    position,
    body,
)
from panda_dynamics.props.primitives import add_box
from panda_dynamics.props.fixtures import DrivenFixture
from panda_dynamics.props.mechanisms import quat_xyz
from panda_dynamics.props.free_mechanisms import scale_mass


def unlock_fixture(scene, name, origin):
    """Task-local copy of props.free_mechanisms.unlock_fixture (v5, agent a6).

    Identical except for the latch's connecting bar. In the shared builder that
    bar (half 8x35x5 mm at latch z=0.026) crosses the channel exit for
    y in [0, 0.07]; at the latch joint limit (fully open, -26 mm) its top is
    still 5 mm above the plate, so a 32 mm ball centred in the 56 mm channel
    cannot roll out unless the fixture is tilted nose-down by more than ~47 deg.
    The bar is lowered to latch z=0.005: closed, it still sits behind the gate;
    open (q <= -0.01) it is below the plate top and no longer blocks delivery.
    Masses (0.14 kg root, 0.025 kg latch), joint, limits, spring and friction
    are unchanged.
    """
    builder = scene.create_articulation_builder()
    root = builder.create_link_builder()
    root.set_name(name)
    # Channel with a real exit gap and separate handle for the left hand.
    add_box(root, [0.045, 0.028, 0.005], [-0.025, 0, -0.005], density=450)
    for y in (-0.034, 0.034):
        add_box(root, [0.068, 0.006, 0.025], [0, y, 0.02], density=450)
    add_box(root, [0.008, 0.017, 0.014], [-0.083, 0, 0.025], density=450)
    # Square socket: 28 mm empty opening, finite 7 mm walls.
    for x, y, hx, hy in (
        (-0.022, 0, 0.008, 0.03),
        (0.022, 0, 0.008, 0.03),
        (0, -0.022, 0.014, 0.008),
        (0, 0.022, 0.014, 0.008),
    ):
        add_box(root, [hx, hy, 0.015], [x + 0.02, y + 0.065, 0.075], density=450)
    latch = builder.create_link_builder(root)
    latch.set_name(name + "_latch")
    latch.set_joint_name(name + "_pin_driven_latch")
    axis = quat_xyz([0, -np.pi / 2, 0])
    latch.set_joint_properties(
        "prismatic",
        [[-0.026, 0]],
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=0.04,
        damping=0.08,
    )
    add_box(latch, [0.005, 0.03, 0.010], [0.025, 0, 0.010], density=500,
            color=[0.89, 0.58, 0.18, 1])
    # v5: connecting bar lowered from z=0.026 to z=0.005 (see docstring).
    add_box(latch, [0.008, 0.035, 0.005], [0.025, 0.035, 0.005], density=500,
            color=[0.89, 0.58, 0.18, 1])
    add_box(latch, [0.011, 0.011, 0.008], [0.020, 0.065, 0.049], density=500,
            color=[0.89, 0.58, 0.18, 1])
    builder.initial_pose = sapien.Pose(origin)
    art = builder.build(name=name + "_assembly", fix_root_link=False)
    scale_mass(art.links[0], 0.14)
    scale_mass(art.links[1], 0.025)
    f = DrivenFixture(art, art.links[1], force=0, kp=0, kd=0)
    f.enabled = False
    f.joint.set_friction(0.04)
    return f
from panda_dynamics.props.mechanisms import gravity_channel
from panda_dynamics.tasks.predicates import bilateral_grip, containment


class MovingFixtureUnlock(PandaDynamicEnv):
    TASK = "D11-MovingFixtureUnlock"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("fixture_support", "tracking_pin"),
        ("moving_fixture_support", "pin_inserter"),
        ("fixture_support", "latch_operator"),
        ("outlet_operator", "withdrawing_pin"),
        ("outlet_support", "cleared_pin"),
    )
    ARM_SETUPS = (
        ArmSetup(None, (-0.063, 0, 0.285), base=(-0.55, -0.22, 0)),
        ArmSetup(
            "peg",
            (0.12, 0.15, 0.40),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    ALLOW_FINGER_CONTACTS = True
    ALLOWED_FINGER_FIXTURES = ("fixture",)
    ALLOWED_TOOL_FIXTURES = ("fixture", "fixture_latch")
    PHASES = (
        "moving_fixture_presentation",
        "relative_pin_insertion",
        "mechanical_latch_open",
        "follow_and_withdraw",
        "gravity_delivery",
    )
    INSTRUCTION = "左手真实握持并移动夹具，右销跟踪插入并压开实体闩锁；左手对准出口，右销退出，让原有球沿滑道交付。"

    def build_task(self):
        self.fixtures["fixture"] = unlock_fixture(
            self.scene, "fixture", [0.02, 0, 0.26]
        )
        latch = self.fixtures["fixture"]
        latch.kp, latch.kd, latch.force = 35.0, .2, .6
        latch.motion = "spring"
        latch.joint.set_drive_properties(latch.kp,latch.kd,latch.force,mode="force")
        self.objects["fixture"] = self.fixtures["fixture"].articulation.links[0]
        # v5: the reset stand now spans the loaded fixture's centre of mass
        # (root+latch+ball COM at local x ~ -0.003 m). The old stand ended at
        # local x = -0.008, so the fixture tipped nose-down as soon as the hand
        # loosened (it was only held by the grip, never by its stand).
        box(
            self.scene,
            "reset_fixture_stand",
            [0.030, 0.024, 0.003],
            [0.0, 0, 0.247],
            static=True,
        )
        self.objects["ball"] = ball(self.scene, "ball", 0.016, 0.025, 0.05)
        gravity_channel(
            self.scene, "chute", [0.15, 0.13, 0.205], [0.33, 0.13, 0.08], width=0.033
        )
        # v5: interior x half 0.075 -> 0.065 m. The delivery predicate below
        # accepts |local x| < 0.0528 m, so a ball resting against the old +x
        # wall (|local x| = 0.059 m) could never count as delivered.
        self.basin = container(
            self.scene,
            "basin",
            [0.38, 0.13, 0.02],
            half=(0.065, 0.06),
            height=0.04,
            static=True,
        )

    def reset_task(self):
        f = self.fixtures["fixture"]
        f.raw.pose = sapien.Pose([0.02, 0, 0.26])
        f.reset()
        # v5: seeded ball start on the fixture floor (+-6 mm along the channel,
        # +-4 mm across), so seeds give physically distinct instances.
        set_initial(
            self.objects["ball"],
            [-0.008 + self.rng.uniform(-0.006, 0.006), self.rng.uniform(-0.004, 0.004), 0.277],
        )
        left = self.arms["panda-0"]
        q = left.robot.qpos.copy()
        q[7:] = 0.0175
        left.robot.set_qpos(q)
        left.servo.reset()
        # Firmer finite-force grip for the cantilevered fixture. Motor force and
        # slew remain unchanged (15 N per finger, 150 N/s). v5: 800 -> 1875 N/m so
        # a fully closed command on the 16 mm handle thickness reaches the 15 N
        # cap (1875 * 0.008 m) instead of 6.4 N.
        left.servo.kp[7:] = 1875.0
        left.servo.kd[7:] = 8.0
        left.servo.input.per_dof_synchronization = [Synchronization.TimeIfNecessary]*7 + [Synchronization.No]*2
        self.events.flags.update(
            initial_fixture_position=[0.02, 0, 0.26], target=[0.06, 0.065, 0.335]
        )

    def update_task(self):
        root = body(self.objects["fixture"])
        f = self.fixtures["fixture"]
        right = self.arms["panda-1"]
        pin_tip = (right.tool_pose * sapien.Pose([0, 0, -0.07])).p
        local = (root.entity_pose.inv() * sapien.Pose(pin_tip)).p
        depth = 0.09 - local[2]
        aligned = np.linalg.norm(local[:2] - [0.020, 0.065]) < 0.005
        grip = bilateral_grip(self, "fixture", "panda-0")
        if self.phase == 0:
            if (
                grip
                and np.linalg.norm(
                    root.entity_pose.p - self.events.flags["initial_fixture_position"]
                )
                > 0.018
                and np.linalg.norm(root.linear_velocity) > 0.005
            ):
                self.advance()
        elif self.phase == 1:
            self.phase_hold(
                grip
                and aligned
                and 0.01 < depth < 0.035
                and np.linalg.norm(root.linear_velocity) > 0.003,
                0.06,
                insertion_depth=depth,
            )
        elif self.phase == 2:
            if f.q < -0.017 and self.contact("right_tool", "fixture_latch") > 0:
                self.advance(latch_displacement=f.q)
        elif self.phase == 3:
            if (
                depth < -0.015
                and not self.contact("right_tool", "fixture_latch")
                and grip
            ):
                self.advance()
        elif self.phase == 4:
            if self.contact("ball", "chute"):
                self.events.once("released_ball_chute", self.time)
            if self.events.has("released_ball_chute") and self.phase_hold(
                containment(self, "ball", self.basin, 0.06, 0.04, 0.016), 0.7
            ):
                self.events.physical_success = True
        if root.entity_pose.p[2] < 0.18:
            self.events.fail("fixture_grasp_drop", self.time)
