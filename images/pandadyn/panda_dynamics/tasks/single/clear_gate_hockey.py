import numpy as np
import sapien
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import (
    box,
    add_box,
    material,
    set_initial,
    position,
    velocity,
)
from panda_dynamics.props.fixtures import DrivenFixture
from panda_dynamics.props.mechanisms import quat_xyz
from panda_dynamics.tasks.predicates import crossed


class ClearGateHockey(PandaDynamicEnv):
    TASK = "S03-ClearGateHockey"
    NAMESPACE = "PandaMultiStage"
    TOOL = "paddle"
    TOOL_START = (0.03, -0.20, 0.045)
    PHASES = (
        "first_strike",
        "clear_blocker",
        "recover_deflection",
        "second_strike",
        "bank_and_goal",
    )
    INSTRUCTION = (
        "击打来球清开滑动挡块，回收实际反弹的同一冰球，再经指定边轨通过清开的球门。"
    )

    def build_task(self):
        self.objects["puck"] = box(
            self.scene,
            "puck",
            [0.022, 0.022, 0.012],
            [0.23, -0.12, 0.0125],
            mass=self.params["object_mass"],
            mu=self.params["table_friction"],
            restitution=0.65,
        )
        b = self.scene.create_articulation_builder()
        root = b.create_link_builder()
        root.set_name("blocker_base")
        moving = b.create_link_builder(root)
        moving.set_name("blocker")
        axis = quat_xyz([0, 0, np.pi / 2])
        moving.set_joint_name("blocker_slide")
        moving.set_joint_properties(
            "prismatic",
            [[0, 0.17]],
            sapien.Pose(q=axis),
            sapien.Pose(q=axis),
            friction=0.015,
            damping=0,
        )
        add_box(
            moving,
            [0.015, 0.07, 0.032],
            q=quat_xyz([0, 0, -0.6]),
            mat=material(0.05, 0.65),
            density=250,
        )
        b.initial_pose = sapien.Pose([0.29, 0.06, 0.032])
        art = b.build(name="blocker_fixture", fix_root_link=True)
        self.fixtures["blocker"] = DrivenFixture(art, art.links[1], force=0, kp=0, kd=0)
        self.fixtures["blocker"].enabled = False
        # A small physical slide friction dissipates the clearing impulse.
        # Without it the stop reflected the blocker back into the bank route.
        self.fixtures["blocker"].joint.set_friction(self.params["blocker_friction"])
        box(
            self.scene, "return_rail", [0.008, 0.10, 0.035],
            [-0.14, 0.035, 0.035], static=True, restitution=0.65,
        )
        box(
            self.scene,
            "bank_rail",
            [0.17, 0.008, 0.035],
            [0.30, -0.23, 0.035],
            static=True,
            restitution=0.7,
        )
        box(
            self.scene,
            "backstop",
            [0.01, 0.10, 0.035],
            [0.52, 0.06, 0.035],
            static=True,
        )

    def reset_task(self):
        set_initial(
            self.objects["puck"],
            [0.23, self.rng.uniform(-0.14, -0.10), 0.0125],
            [-self.params["incoming_speed"], 0, 0],
        )
        self.fixtures["blocker"].reset()
        self.events.flags.update(goal=[0.46, 0.06, 0.012], zone=[0.08, -0.08, 0.012])
        self.events.emit("release", 0.0, object="puck")

    def update_task(self):
        p = position(self.objects["puck"])
        contact = self.contact("puck", "tool")
        if self.contact("blocker", "tool"):
            self.events.fail("direct_blocker_shortcut", self.time)
        if self.phase == 0 and contact > 0:
            self.advance(impulse=contact)
        elif self.phase == 1:
            if self.contact("puck", "blocker"):
                self.events.once("puck_blocker_collision", self.time)
            if (
                self.events.has("puck_blocker_collision")
                and self.fixtures["blocker"].q > 0.065
            ):
                self.advance(clearance=self.fixtures["blocker"].q)
        elif self.phase == 2 and p[0] < 0.16 and not contact:
            self.advance(incoming_velocity=velocity(self.objects["puck"]).tolist())
        elif self.phase == 3 and contact > 0:
            self.advance(impulse=contact)
        elif self.phase == 4:
            if self.contact("puck", "bank_rail"):
                self.events.once("required_bank", self.time)
            if crossed(self, "puck", self.events.flags["goal"], half=0.055):
                if (
                    self.events.has("required_bank")
                    and not contact
                    and self.fixtures["blocker"].q > 0.065
                ):
                    self.advance()
                    self.events.physical_success = True
                else:
                    self.events.fail("skipped_route", self.time)
