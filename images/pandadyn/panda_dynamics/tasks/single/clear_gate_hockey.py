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
    GREEN,
)
from panda_dynamics.props.fixtures import DrivenFixture
from panda_dynamics.props.mechanisms import quat_xyz
from panda_dynamics.tasks.predicates import crossed

# v6: two physical bank rails; a seeded route designates which one the final
# shot must bank off. Value: a point on the rail's puck-side face (announced at
# reset as the goal "target").
RAILS = {
    "bank_rail": [0.30, -0.222, 0.035],  # long side rail on the robot's right
    "return_rail": [-0.132, 0.035, 0.035],  # short end rail in front of the robot
}
RAIL_GRAY = [0.55, 0.57, 0.60, 1]
RECOVER_X = 0.16  # recovery line: the robot's side is x < RECOVER_X


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
        "先用球拍触击迎面滑来的冰球，再把它击出、使其离拍自由滑行并以足够速度撞开滑动挡块，"
        "待它不受球拍接触地滑回回收线以内后再次击打，使它最后一次离拍后只经本局指定的那条边轨反弹、"
        "不碰另一条边轨，穿过已清开的球门。"
    )

    def route_rail(self):
        """Seeded designated rail. A separate generator keyed by the seed leaves
        the reset draws of self.rng unchanged and is known when the scene is
        built, so the designated rail can be coloured."""
        index = int(np.random.default_rng([int(self.seed_value), 3]).integers(2))
        return ("bank_rail", "return_rail")[index]

    def build_task(self):
        self.rail_name = self.route_rail()
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
            density=self.params["blocker_density"],
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
            color=GREEN if self.rail_name == "return_rail" else RAIL_GRAY,
        )
        box(
            self.scene,
            "bank_rail",
            [0.17, 0.008, 0.035],
            [0.30, -0.23, 0.035],
            static=True,
            restitution=0.7,
            color=GREEN if self.rail_name == "bank_rail" else RAIL_GRAY,
        )
        box(
            self.scene,
            "backstop",
            [0.01, 0.10, 0.035],
            [0.52, 0.06, 0.035],
            static=True,
        )

    def reset_task(self):
        P = self.params
        heading = 0.0
        y = self.rng.uniform(P["start_y_min"], P["start_y_max"])
        if P["incoming_angle"] > 0:
            heading = self.rng.uniform(-P["incoming_angle"], P["incoming_angle"])
        speed = P["incoming_speed"]
        # The square puck slides face-first along its (seeded) heading.
        set_initial(
            self.objects["puck"],
            [0.23, y, 0.0125],
            [-speed * np.cos(heading), speed * np.sin(heading), 0],
            q=[np.cos(-heading / 2), 0, 0, np.sin(-heading / 2)] if heading else (1, 0, 0, 0),
        )
        self.fixtures["blocker"].reset()
        self.events.flags.update(
            goal=[0.46, 0.06, 0.012],
            zone=[0.08, -0.08, 0.012],
            target=list(RAILS[self.rail_name]),
            route_rail=self.rail_name,
        )
        self.events.emit("release", 0.0, object="puck", rail=self.rail_name)

    def update_task(self):
        P = self.params
        flags = self.events.flags
        p = position(self.objects["puck"])
        contact = self.contact("puck", "tool")
        # Free motion: time since the puck last touched the paddle.
        if contact > 0:
            flags["paddle_contact_time"] = self.time
        free = self.time - flags.get("paddle_contact_time", -1e9)
        # Planar puck speed at the end of the previous substep (pre-impact).
        pre_speed = flags.get("puck_speed", 0.0)
        flags["puck_speed"] = float(np.linalg.norm(velocity(self.objects["puck"])[:2]))
        if self.contact("blocker", "tool"):
            self.events.fail("direct_blocker_shortcut", self.time)
        if self.phase == 0 and contact > 0:
            self.advance(impulse=contact)
        elif self.phase == 1:
            if self.contact("puck", "blocker"):
                # v6: only a struck puck in free motion may move the blocker.
                if free < P["strike_free"]:
                    self.events.fail("puck_pushed_into_blocker", self.time)
                elif pre_speed >= P["strike_min_speed"]:
                    self.events.once(
                        "puck_blocker_collision", self.time, free=free, speed=pre_speed
                    )
            if (
                self.events.has("puck_blocker_collision")
                and self.fixtures["blocker"].q > 0.065
            ):
                self.advance(clearance=self.fixtures["blocker"].q)
        elif self.phase == 2:
            # v6: the puck must slide back across the recovery line by itself,
            # untouched by the paddle for the last recover_free seconds.
            previous = self.previous_positions["puck"]
            if previous[0] >= RECOVER_X > p[0] and not contact and free >= P["recover_free"]:
                self.advance(
                    incoming_velocity=velocity(self.objects["puck"]).tolist(), free=free
                )
        elif self.phase == 3 and contact > 0:
            self.advance(impulse=contact)
        elif self.phase == 4:
            # v6: the shot that scores must, since the puck's last paddle
            # contact, bank off the designated rail (>= bank_free after that
            # contact) and touch no other rail; a paddle contact starts a new
            # attempt.
            other = "return_rail" if self.rail_name == "bank_rail" else "bank_rail"
            if contact > 0:
                flags["route_banked"] = False
                flags["route_wrong"] = False
            if self.contact("puck", other):
                flags["route_wrong"] = True
            touching = self.contact("puck", self.rail_name) > 0
            if (
                touching
                and not flags.get("rail_touching")  # contact onset, i.e. a bounce
                and free >= P["bank_free"]
                and not flags.get("route_banked")
            ):
                flags["route_banked"] = True
                self.events.emit("required_bank", self.time, rail=self.rail_name, free=free)
            flags["rail_touching"] = touching
            if crossed(self, "puck", self.events.flags["goal"], half=0.055):
                if (
                    flags.get("route_banked")
                    and not flags.get("route_wrong")
                    and not contact
                    and self.fixtures["blocker"].q > 0.065
                ):
                    self.advance()
                    self.events.physical_success = True
                else:
                    self.events.fail(
                        "wrong_rail" if flags.get("route_wrong") else "skipped_route", self.time
                    )
