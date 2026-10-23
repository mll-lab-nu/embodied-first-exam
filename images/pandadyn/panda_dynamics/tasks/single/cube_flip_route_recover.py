import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import (
    box,
    container_shapes,
    finish,
    material,
    set_initial,
    position,
    velocity,
    body,
)
from panda_dynamics.props.mechanisms import gravity_channel
from panda_dynamics.tasks.predicates import inertial_flip, face_up
from panda_dynamics.robots.arm import ArmSetup

# v5 (option A): the chute's top edge starts 2 mm below the launch surface
# (z 0.140 -> 0.138): with the higher chute friction the cube's front-bottom edge
# caught on the coplanar chute start edge while being pushed (measured stop at
# x=0.138 and a joint-7 jolt).
CHUTE_START = np.array([0.16, 0.0, 0.138])
# v5 (option A): low end moved 2 cm toward the arm (x 0.38 -> 0.36): the blade
# reaches x <= 0.356-0.37 here, and the cube must be pushed fully past the chute
# end (centre >= end + 0.022) to lie flat on the pocket floor.
CHUTE_END = np.array([0.36, 0.0, 0.035])
_run = CHUTE_END - CHUTE_START
# Upward unit normal of the chute's sliding surface (27.25 deg slope).
CHUTE_NORMAL = np.array([-_run[2], 0.0, _run[0]]) / np.linalg.norm(_run)
# Unit vector down the chute.
CHUTE_DOWN = _run / np.linalg.norm(_run)
# v6: arm base 0.15 m closer (x -0.55 -> -0.40): at -0.55 the chute's low end is
# at the edge of the side-mounted blade's workspace (~0.2 m/s there); from -0.40
# the blade can race ahead of the sliding cube (measured peak 0.40-0.44 m/s).
ARM_BASE = (-0.40, 0.0, 0.0)
# Pocket at the chute's low end: floor flush with the chute end, open toward it.
POCKET_CENTER = np.array([0.41, 0.0])  # floor flush with the (moved) chute end
POCKET_FLOOR_Z = float(CHUTE_END[2])


def face_up_on_surface(env, name, local_axis, normal, tolerance):
    """Same measure as predicates.face_up, against a supporting surface normal."""
    matrix = body(env.objects[name]).entity_pose.to_transformation_matrix()[:3, :3]
    return float(np.dot(matrix @ np.asarray(local_axis), normal)) > np.cos(tolerance)


class CubeFlipRouteRecover(PandaDynamicEnv):
    TASK = "S06-CubeFlipRouteRecover"
    NAMESPACE = "PandaMultiStage"
    TOOL = "pusher"
    MOUNT = (0.12, 0.13, 0.04)
    TOOL_START = (-0.05, -0.08, 0.179)
    ARM_SETUPS = (ArmSetup(TOOL, TOOL_START, base=ARM_BASE, mount=MOUNT),)
    PHASES = (
        "momentum_face_flip",
        "oriented_chute_entry",
        "downstream_intercept",
        "pocket_delivery",
    )
    INSTRUCTION = (
        "用工具推方块使其倾斜，在倾角未到 45° 且方块仍在转动时离开，让它不被再次触碰地自行翻过 45° "
        "到相邻面并在发射台上停稳，再让它以翻起的面朝上进入斜滑道，无接触地自行加速下滑一段后，"
        "在低端从下坡一侧截住仍在滑动的方块，最后使它以同一面朝上停稳在滑道末端的槽里。"
    )

    def build_task(self):
        h = self.params["cube_half"]
        self.objects["cube"] = box(
            self.scene,
            "cube",
            [h] * 3,
            [0.035, 0, 0.14 + h],
            mass=self.params["object_mass"],
            mu=0.65,
            restitution=0.3,
        )
        box(
            self.scene,
            "launch_surface",
            [0.14, 0.09, 0.02],
            [0.02, 0, 0.12],
            static=True,
            mu=0.65,
        )
        # v6: chute friction from the config (nominal 0.47, hard 0.43; option A
        # had 0.65). Mean cube/chute static friction 0.56 (hard 0.54) > tan 27.25
        # deg = 0.515 > mean dynamic 0.476 (hard 0.459): a cube at rest stays,
        # but the cube that tips onto the chute keeps sliding by itself and
        # accelerates (measured ~0.35 / ~0.49 m/s^2) to ~0.39 / ~0.44 m/s at the
        # low end. Left alone it enters the pocket fast and tumbles onto another
        # face (measured), so it has to be intercepted while it slides.
        gravity_channel(
            self.scene, "chute", CHUTE_START.tolist(), CHUTE_END.tolist(), width=0.05,
            mu=self.params["chute_friction"],
        )
        # v5: same pocket size/material as before, moved from the side of the
        # route to the chute's low end. Its floor is flush with the chute end and
        # the chute-facing wall is open, so a sliding cube can enter it.
        builder = self.scene.create_actor_builder()
        container_shapes(
            builder, (0.06, 0.06), 0.012, mat=material(0.4, 0.03),
            open_side=True, open_sign=-1,
        )
        self.pocket = finish(
            builder, "pocket", [*POCKET_CENTER, POCKET_FLOOR_Z], static=True
        )

    def reset_task(self):
        jx, jy = self.params["start_jitter_x"], self.params["start_jitter_y"]
        set_initial(
            self.objects["cube"],
            [
                0.035 + self.rng.uniform(-jx, jx),
                self.rng.uniform(-jy, jy),
                0.14 + self.params["cube_half"] + 0.0005,
            ],
        )
        self.events.flags.update(
            goal=[*POCKET_CENTER, POCKET_FLOOR_Z + self.params["cube_half"]],
            target_face=[-1, 0, 0],
        )

    def update_task(self):
        obj = self.objects["cube"]
        p = position(obj)
        if self.phase == 0:
            self.phase_hold(
                inertial_flip(self, "cube", "tool", "flip", [-1, 0, 0])
                and self.contact("cube", "launch_surface") > 0,
                0.25,
            )
        elif (
            self.phase == 1
            and self.contact("cube", "chute")
            and p[0] > 0.18
            # v5: the flipped face is measured against the chute surface it
            # rides on; the 0.35 rad tolerance is unchanged.
            and face_up_on_surface(self, "cube", [-1, 0, 0], CHUTE_NORMAL, 0.35)
        ):
            self.events.flags["intercept:free_from"] = float((p - CHUTE_START) @ CHUTE_DOWN)
            self.advance()
        elif self.phase == 2:
            # v6 (tightened): the downstream intercept is the blade meeting the
            # cube while it is still sliding down the chute by itself: contact
            # past x = 0.32 with the cube on the chute, the blade on its downhill
            # side, after a contact-free slide of at least free_slide, at an
            # incoming (previous-substep) speed down the chute of at least
            # incoming_speed. Any other cube-tool contact restarts the free slide.
            flags = self.events.flags
            s = float((p - CHUTE_START) @ CHUTE_DOWN)
            along = float(velocity(obj) @ CHUTE_DOWN)
            if self.contact("cube", "tool") > 0:
                free = s - flags["intercept:free_from"]
                incoming = flags.get("intercept:previous_speed", 0.0)
                if (
                    p[0] > 0.32
                    and self.contact("cube", "chute") > 0
                    and float((self.tool_pose.p - p) @ CHUTE_DOWN) > 0
                    and free >= self.params["free_slide"]
                    and incoming >= self.params["incoming_speed"]
                ):
                    self.advance(
                        incoming_velocity=velocity(obj).tolist(),
                        incoming_speed=incoming,
                        free_slide=free,
                    )
                else:
                    flags["intercept:free_from"] = s
            flags["intercept:previous_speed"] = along
        elif self.phase == 3:
            condition = (
                self.contact("cube", "pocket") > 0
                and np.linalg.norm(p[:2] - POCKET_CENTER) < 0.04
                and face_up(self, "cube", [-1, 0, 0])
                and np.linalg.norm(velocity(obj)) < 0.04
                and np.linalg.norm(body(obj).angular_velocity) < 0.2
            )
            if self.phase_hold(condition, 0.5):
                self.events.physical_success = True
