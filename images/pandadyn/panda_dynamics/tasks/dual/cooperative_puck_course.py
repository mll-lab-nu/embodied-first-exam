import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import box, set_initial, position, velocity
from panda_dynamics.tasks.predicates import crossed


class CooperativePuckCourse(PandaDynamicEnv):
    TASK = "D03-CooperativePuckCourse"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    # v5: back to the base-class planning fractions (were .25/.015). The lowered
    # fractions made the Ruckig reference overshoot contact-height paddle moves
    # by ~7 mm (paddle commanded to z=.034 reached .0267 and touched the table);
    # measured FER velocity/acceleration/jerk/torque limits are still enforced.
    REFERENCE_ACCELERATION = .55
    REFERENCE_JERK = .05
    WRIST_DAMPING = (24.,20.,14.)
    ROLE_LABELS = (
        ("striker", "preparing_receiver"),
        ("preparing_receiver", "striker"),
        ("striker", "preparing_receiver"),
        ("cleared_partner", "goal_striker"),
    )
    ARM_SETUPS = (
        ArmSetup("paddle", (-0.05, -0.18, 0.048), base=(-0.55, -0.22, 0)),
        ArmSetup(
            "paddle",
            (0.28, 0.12, 0.048),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    PHASES = (
        "left_first_pass",
        "right_return_route",
        "left_diagonal_pass",
        "right_terminal_shot",
    )
    INSTRUCTION = (
        "左、右、左、右依次用挡板击打同一冰球：左臂把它从滑进来的开口打回右侧，"
        "右臂把它打过靠长挡边的开口回到左侧，左臂再把它打过中间开口，"
        "最后右臂把它射过球门线，每次过线时冰球须已离开挡板；"
        "困难档中第一击必须迎击仍在滑来的冰球并直接把它打回开口，第三击必须斜穿中间开口。"
    )

    def build_task(self):
        self.objects["puck"] = box(
            self.scene,
            "puck",
            [0.022, 0.022, 0.012],
            [0.22, -0.13, 0.013],
            mass=self.params["object_mass"],
            mu=self.params["puck_friction"],
            restitution=self.params["puck_restitution"],
        )
        for index, (x, y) in enumerate(
            ((0.12, -0.22), (0.12, -0.045), (0.12, 0.095), (0.12, 0.26))
        ):
            box(
                self.scene,
                f"route_post_{index}",
                [0.016, 0.025, 0.035],
                [x, y, 0.035],
                static=True,
                restitution=0.7,
            )
        # Side wall beyond the last post (bounds +y overshoots; no check uses it).
        box(
            self.scene,
            "return_rail",
            [0.26, 0.008, 0.035],
            [0.14, 0.31, 0.035],
            static=True,
            restitution=0.7,
        )
        box(
            self.scene,
            "goal_backstop",
            [0.01, 0.065, 0.035],
            [0.53, -0.02, 0.035],
            static=True,
        )

    def reset_task(self):
        # Incoming puck: it crosses the post line x=0.12 at y=-0.13+U(+-incoming_offset)
        # with heading U(+-incoming_angle) and starts at x=start_x+U(0, start_spread)
        # (seeded arrival time). Nominal keeps angle and spread at 0, which reproduces
        # the original draw [0.23, -0.13+U(+-0.014)], v=[-0.35, 0, 0] bit for bit.
        P = self.params
        offset = self.rng.uniform(-P["incoming_offset"], P["incoming_offset"])
        heading = (
            self.rng.uniform(-P["incoming_angle"], P["incoming_angle"])
            if P["incoming_angle"] > 0
            else 0.0
        )
        lead = self.rng.uniform(0.0, P["start_spread"]) if P["start_spread"] > 0 else 0.0
        x0 = P["start_x"] + lead
        speed = P["incoming_speed"]
        set_initial(
            self.objects["puck"],
            [x0, -0.13 + offset + (x0 - 0.12) * np.tan(heading), 0.0125],
            [-speed * np.cos(heading), -speed * np.sin(heading) if heading else 0, 0],
        )
        self.events.flags.update(
            goal=[0.46, -0.02, 0.012],
            passages=[[0.12, -0.13, 0.012], [0.12, 0.19, 0.012], [0.12, 0.025, 0.012]],
            last_strike=-10.0,
        )
        if P["volley_speed"] > 0:
            self.events.flags["puck_previous_velocity"] = velocity(
                self.objects["puck"]
            ).tolist()

    def update_task(self):
        P = self.params
        stage = self.phase
        name = ("left_tool", "right_tool", "left_tool", "right_tool")[min(stage, 3)]
        key = f"strike_{stage}"
        arm = self.arms["panda-0" if stage % 2 == 0 else "panda-1"]
        volley = stage == 0 and P["volley_speed"] > 0
        if (
            self.contact("puck", name)
            and not self.events.has(key)
            and np.linalg.norm(arm.tool_body.linear_velocity) > 0.035
        ):
            if self.time - self.events.flags["last_strike"] > 0.06:
                metrics = dict(tool=name, impulse=self.contact("puck", name))
                if volley:
                    # Hard: the first left strike must meet the puck while it still
                    # slides toward the left arm (velocity of the previous substep).
                    incoming = -float(
                        self.events.flags.get("puck_previous_velocity", (0.0,))[0]
                    )
                    metrics["approach_speed"] = incoming
                self.events.once(key, self.time, **metrics)
                self.events.flags["last_strike"] = self.time
                if volley and incoming < P["volley_speed"]:
                    self.events.fail("first_strike_not_volley", self.time)
        if volley and not self.events.has(key):
            self.events.flags["puck_previous_velocity"] = velocity(
                self.objects["puck"]
            ).tolist()
        if not self.events.has(key):
            return
        free = (
            not self.contact("puck", name)
            and self.time - self.events.first_time(key) > 0.035
        )
        if (
            stage < 3
            and free
            and crossed(
                self,
                "puck",
                self.events.flags["passages"][stage],
                direction=1 if stage != 1 else -1,
                half=0.055,
            )
        ):
            outgoing = velocity(self.objects["puck"])
            if stage == 2 and P["diagonal_angle"] > 0:
                # Hard: the middle-gap pass must be diagonal, i.e. the puck's
                # horizontal velocity makes at least diagonal_angle with the x axis.
                angle = float(np.arctan2(abs(outgoing[1]), outgoing[0]))
                if angle < P["diagonal_angle"]:
                    self.events.fail("middle_pass_not_diagonal", self.time)
                    return
                self.advance(outgoing_velocity=outgoing.tolist(), crossing_angle=angle)
            else:
                self.advance(outgoing_velocity=outgoing.tolist())
        elif (
            stage == 3
            and free
            and crossed(self, "puck", self.events.flags["goal"], half=0.05)
        ):
            self.advance()
            self.events.physical_success = True
        elif (
            volley
            and P["volley_window"] > 0
            and self.time - self.events.first_time(key) > P["volley_window"]
        ):
            # Hard: the volley itself must return the puck through the entry gap.
            self.events.fail("volley_return_too_slow", self.time)
