import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import box, set_initial, position, velocity, body, material, finish
from panda_dynamics.props.fixtures import single_axis
from panda_dynamics.props.mechanisms import gravity_channel, quat_xyz
from panda_dynamics.tasks.predicates import supported


def rolling_cylinder(scene, mass):
    """76 x 38 mm spherocylinder with physical hemispherical end caps.

    PhysX's finite-sided cylinder hull can rest on a facet on a shallow guide.
    This declared rounded-end prop uses an analytic capsule collision, matching
    its visual shape and integrated inertia; it is still a long-axis rigid body.
    """
    b=scene.create_actor_builder()
    b.add_capsule_collision(radius=.019,half_length=.019,material=material(.35,.05))
    b.add_capsule_visual(radius=.019,half_length=.019,material=[.94,.39,.10,1])
    return finish(b,"cylinder",[0,0,.2],mass=mass)


class CylinderRescueRouteDeliver(PandaDynamicEnv):
    TASK = "S11-CylinderRescueRouteDeliver"
    NAMESPACE = "PandaMultiStage"
    TOOL = "receiver"
    TOOL_START = (0.21, -0.18, 0.13)
    REFERENCE_ACCELERATION = .3
    REFERENCE_JERK = .015
    WRIST_DAMPING = (24.,20.,14.)
    MOUNT = (0.12, -0.12, 0.04)
    PHASES = (
        "rolling_interception",
        "axial_alignment",
        "guide_rail_traverse",
        "exit_reception",
        "oriented_moving_delivery",
    )
    INSTRUCTION = "拦截滚动圆柱并制动对齐，放入实体导向重力轨道，在出口接回后按指定轴向交给移动口袋。"

    def build_task(self):
        self.objects["cylinder"] = rolling_cylinder(self.scene, self.params["object_mass"])
        box(
            self.scene,
            "source_lane",
            [0.18, 0.075, 0.012],
            [-0.09, -0.07, 0.123],
            static=True,
            mu=0.1,
        )
        gravity_channel(
            self.scene,
            "guide",
            [-0.08, 0.18, 0.23],
            [0.24, 0.18, 0.23-self.params["guide_drop"]],
            width=0.045,
            mu=0.16,
        )
        box(self.scene,"guide_entry_backstop",[.008,.05,.035],[-.09,.18,.26],static=True,mu=.16)
        self.fixtures["pocket"] = single_axis(
            self.scene,
            "pocket",
            [-0.05, -0.27, 0.07],
            speed=self.params["fixture_speed"],
            force=8.0,
        )

        self.fixtures["pocket"].motion="oscillate"

    def reset_task(self):
        v = self.params["incoming_speed"]
        set_initial(
            self.objects["cylinder"],
            [.09-v*self.params["preview"], -0.07 + self.rng.uniform(-0.004, 0.004), 0.1545],
            [v, 0, 0],
            q=quat_xyz([0, 0, np.pi / 2]),
            angular=[0, v / 0.019, 0],
        )
        self.fixtures["pocket"].reset(
            self.rng.uniform(-0.02, 0.02), self.params["fixture_speed"]
        )
        self.events.flags.update(goal_axis=[0, 1, 0], target=[-0.08, 0.18, 0.23])

    def update_task(self):
        obj = self.objects["cylinder"]
        p = position(obj)
        local = self.local_position(obj)
        held = (
            supported(self, "cylinder", "tool")
            and max(abs(local[:2])) < self.params["tool_half"]
            and 0.013 < local[2] < 0.07
        )
        axis = body(obj).entity_pose.to_transformation_matrix()[:3, 0]
        aligned = abs(axis[1]) > np.cos(0.2)
        if self.phase == 0 and held and not self.contact("cylinder", "source_lane"):
            self.advance(angular_velocity=body(obj).angular_velocity.tolist())
        elif self.phase == 1:
            self.phase_hold(held and aligned and self.relative_speed(obj) < 0.06, 0.3)
        elif self.phase == 2:
            if self.contact("cylinder", "guide") and p[0] < 0.02:
                self.events.once("guide_entry", self.time)
            if (
                self.events.has("guide_entry")
                and p[0] > 0.24
                and not self.contact("cylinder", "tool")
            ):
                self.advance()
        elif self.phase == 3:
            self.phase_hold(held and aligned and not self.contact("cylinder","guide")
                            and self.relative_speed(obj)<.06,.2)
        elif self.phase == 4:
            f = self.fixtures["pocket"]
            relative = (body(f.link).entity_pose.inv() * body(obj).entity_pose).p
            condition = (
                self.contact("cylinder", "pocket") > 0
                and not held
                and np.all(abs(relative[:2]) + .019 + .019*abs(axis[:2]) < .075)
                and .016 < relative[2] and relative[2]+.019+.019*abs(axis[2]) < .063
                and aligned
                and abs(f.v) > .5*self.params["fixture_speed"]
                and self.relative_speed(obj, f.link) < 0.06
            )
            if self.phase_hold(condition, 0.7):
                self.events.physical_success = True

        if self.phase >= 1 and self.contact("cylinder","table"):
            self.events.fail("cylinder_left_route_or_receiver",self.time)
