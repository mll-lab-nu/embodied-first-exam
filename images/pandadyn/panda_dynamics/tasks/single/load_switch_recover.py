from ruckig import Synchronization
import numpy as np
import sapien
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import (
    box,
    container,
    set_initial,
    position,
    velocity,
    body, ball, material,
)
from panda_dynamics.props.mechanisms import roller_conveyor, passive_gate, quat_xyz
from panda_dynamics.tasks.predicates import bilateral_grip


def ball_transfer_cart(scene, name, origin):
    """Passive ball-transfer bearings: four free spheres in spherical sockets.

    Each socket constrains only translation relative to the chassis. The three
    rotational axes remain free, with zero motor stiffness/damping. Contact with
    the gate can therefore redirect the cart without a wheel-steering impulse.
    Chassis, bearings and payload are distinct massive dynamic bodies; these
    declared prop joints never connect the payload or the robot to the cart.
    """
    chassis=container(scene,name,origin,half=(.065,.055),height=.012,mass=.16)
    bearings=[]; joints=[]
    for i,(x,y) in enumerate(((-.05,-.04),(-.05,.04),(.05,-.04),(.05,.04))):
        offset=np.array([x,y,-.026])
        bearing=ball(scene,f"{name}_bearing_{i}",.018,.008,.02,mu=.65)
        set_initial(bearing,np.asarray(origin)+offset)
        drive=scene.create_drive(chassis,sapien.Pose(offset),bearing,sapien.Pose())
        drive.set_limit_x(0,0);drive.set_limit_y(0,0);drive.set_limit_z(0,0)
        bearings.append((bearing,offset));joints.append(drive)
    return chassis,bearings,joints


class LoadSwitchRecover(PandaDynamicEnv):
    TASK = "S08-LoadSwitchRecover"
    NAMESPACE = "PandaMultiStage"
    TOOL = None
    TOOL_START = (-0.13, -0.13, 0.20)
    ALLOW_FINGER_CONTACTS = True
    ALLOWED_FINGER_FIXTURES = ("switch",)
    PHASES = (
        "moving_part_pickup",
        "load_coasting_cart",
        "physical_switch_operation",
        "selected_branch",
        "payload_recovery",
    )
    INSTRUCTION = "从滚轮带抓取零件并装入滑行车，在车行进时转动实体道岔，然后到指定支路回收原零件。"

    def build_task(self):
        self.fixtures["conveyor"] = roller_conveyor(
            self.scene, "conveyor", [-0.16, -0.13, 0.10], self.params["incoming_speed"]
        )
        chassis,self.cart_bearings,self.cart_joints=ball_transfer_cart(self.scene,"cart",[0,-.41,.045])
        self.objects["cart"]=chassis
        for i,(bearing,_) in enumerate(self.cart_bearings):
            self.objects[f"cart_bearing_{i}"]=bearing
        self.objects["part"] = box(
            self.scene,
            "part",
            [0.018] * 3,
            [-0.16, -0.18, 0.133],
            mass=self.params["object_mass"],
            mu=0.65,
        )
        self.fixtures["switch"] = passive_gate(
            self.scene,
            "switch",
            [0.0, 0.30, 0.01],
            length=0.14,
            height=0.045,
            friction=0.08,
        )
        for sign in (-1, 1):
            box(
                self.scene,
                f"entry_rail_{sign}",
                [0.008, 0.10, 0.025],
                [sign * 0.083, -0.22, 0.025],
                static=True,
            )
            box(
                self.scene,
                f"branch_rail_{sign}",
                [0.008, 0.12, 0.025],
                [sign * 0.16, 0.43, 0.025],
                q=quat_xyz([0, 0, -sign * 0.55]),
                static=True,
            )
            container(
                self.scene,
                f"dock_{sign}",
                [sign * 0.16, 0.46, 0.003],
                half=(0.07, 0.06),
                height=0.018,
                static=True,
            )

    def reset_task(self):
        # Separate hand timing from arm tracking, with the same rate/effort limits.
        self.servo.input.per_dof_synchronization = [Synchronization.TimeIfNecessary]*7 + [Synchronization.No]*2
        self.servo.kd[7:] = 8.0
        # v5: declared seeded instance variation:
        # receiver phase = cart start along its entry rail (+-10 mm, i.e.
        # +-0.25 s at 0.04 m/s) and incoming lateral offset of the part on the
        # roller belt (+-4 mm). Previously only the branch was drawn, so all
        # seeds collapsed onto two physical instances per difficulty.
        receiver_phase = self.rng.uniform(-0.01, 0.01)
        lateral = self.rng.uniform(-0.004, 0.004)
        origin=np.array([0.,-.41+receiver_phase,.045])
        speed=self.params["fixture_speed"]
        set_initial(self.objects["cart"],origin,[0,speed,0])
        for bearing,offset in self.cart_bearings:
            set_initial(bearing,origin+offset,[0,speed,0],angular=[-speed/.018,0,0])
        self.fixtures["conveyor"].reset()
        self.fixtures["switch"].reset(0, 0)
        set_initial(
            self.objects["part"],
            [-0.16 + lateral, -0.18, 0.133],
            [0, self.params["incoming_speed"], 0],
        )
        self.events.flags.update(
            branch=int(self.rng.choice([-1, 1])), target=[0.0, 0.30, 0.08]
        )

    def update_task(self):
        grip = bilateral_grip(self, "part")
        p = position(self.objects["part"])
        cart = position(self.objects["cart"])
        branch = self.events.flags["branch"]
        if self.phase == 0:
            if grip and np.linalg.norm(velocity(self.objects["part"])) > 0.025:
                self.events.once("moving_pickup", self.time)
            if grip and p[2] > 0.20 and self.events.has("moving_pickup"):
                self.advance()
        elif (
            self.phase == 1
            and not grip
            and self.contact("part", "cart")
            and np.linalg.norm(velocity(self.objects["cart"])) > 0.02
        ):
            self.advance()
        elif self.phase == 2:
            finger_contact = sum(self.contact("switch", "panda_" + side + suffix)
                                 for side in ("left", "right")
                                 for suffix in ("finger", "finger_pad"))
            if finger_contact > 1e-7:
                self.events.once("physical_switch_contact", self.time)
            if (
                self.events.has("physical_switch_contact")
                and -branch * self.fixtures["switch"].q > 0.50
                and abs(self.fixtures["switch"].v) < 0.12
                and cart[1] < 0.105
            ):
                self.advance()
            elif self.contact("cart", "switch") or cart[1] > 0.105:
                self.events.fail("missed_switch_deadline", self.time)
        elif self.phase == 3:
            if self.contact("cart", "switch"):
                self.events.once("physical_branch_selection", self.time)
            if self.contact("cart", f"branch_rail_{branch}"):
                self.events.once("selected_branch_rail_contact", self.time)
            if (
                self.events.has("physical_branch_selection")
                and self.events.has("selected_branch_rail_contact")
                and cart[1] > 0.23
                and branch * cart[0] > 0.08
            ):
                self.advance()
        elif self.phase == 4:
            if abs(cart[0]) > .27 or cart[1] > .43:
                self.events.fail("missed_downstream_recovery_window", self.time)
            if self.phase_hold(
                grip and p[2] > cart[2] + 0.10 and not self.contact("part", "cart"), 0.5
            ):
                self.events.physical_success = True
        if self.phase in (2, 3) and p[2] < 0.018:
            self.events.fail("loaded_cart_spill", self.time)
