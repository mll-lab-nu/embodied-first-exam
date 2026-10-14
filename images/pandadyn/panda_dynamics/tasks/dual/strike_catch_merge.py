import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import ball, container, set_initial, position, body
from panda_dynamics.props.mechanisms import gravity_channel
from panda_dynamics.props.release_gate import release_gate
from panda_dynamics.tasks.predicates import cup_catch, containment, free_interval


class StrikeCatchMerge(PandaDynamicEnv):
    TASK = "D02-StrikeCatchMerge"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("striker", "receiver"),
        ("cleared_striker", "catcher"),
        ("preparing_striker", "loaded_carrier"),
        ("striker", "loaded_receiver"),
        ("cleared_striker", "two_ball_catcher"),
        ("cleared_partner", "deliverer"),
    )
    ARM_SETUPS = (
        ArmSetup(
            "paddle",
            (0.10, -0.21, 0.22),
            base=(-0.55, -0.22, 0),
            mount=(0.12, -0.14, 0.04),
        ),
        ArmSetup(
            "cup",
            (0.19, 0.17, 0.18),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    PHASES = (
        "first_redirect",
        "first_catch",
        "loaded_cup_relocation",
        "second_redirect",
        "second_catch",
        "both_delivery",
    )
    INSTRUCTION = "左臂依次将两个闸门放出的球击向不同接收区，右杯接住并保留第一球，再接第二球，最后一起交付。"

    LANE_X = (-0.22, 0.06)
    LANE_START_Z = 0.37
    NOMINAL_LANE_END_Z = 0.28

    def lane_heights(self, end_z):
        """Gate origin and resting ball centre heights on a lane whose lower
        (exit) end is at end_z (upper end fixed). Expressed as offsets from
        the nominal 0.28 m lane, so nominal heights stay exactly 0.358/0.377 m."""

        def floor(z, x):
            x0, x1 = self.LANE_X
            return self.LANE_START_Z + (z - self.LANE_START_Z) * (x - x0) / (x1 - x0)

        def centre(z, x):
            slope = np.arctan2(self.LANE_START_Z - z, self.LANE_X[1] - self.LANE_X[0])
            return floor(z, x - 0.016 * np.sin(slope)) + 0.016 * np.cos(slope)

        nominal = self.NOMINAL_LANE_END_Z
        gate = 0.358 + (floor(end_z, -0.16) - floor(nominal, -0.16))
        ball_z = 0.377 + (centre(end_z, -0.19) - centre(nominal, -0.19))
        return gate, ball_z

    def build_task(self):
        # A lower exit end makes a steeper lane and a faster incoming ball;
        # hard draws each lane's exit height per seed (nominal: no draw).
        jitter = self.params["lane_end_jitter"]
        drop = self.rng.uniform(-jitter, jitter, 2) if jitter > 0 else np.zeros(2)
        self.lane_end = [self.params["lane_end_z"] + float(r) for r in drop]
        for i, y in enumerate((-0.09, 0.09)):
            name = f"ball{i + 1}"
            self.objects[name] = ball(self.scene, name, 0.016, 0.025, 0.1)
            gravity_channel(
                self.scene,
                f"lane{i}",
                [self.LANE_X[0], y, self.LANE_START_Z],
                [self.LANE_X[1], y, self.lane_end[i]],
                width=0.035,
                mu=0.1,
            )
            gate_z, _ = self.lane_heights(self.lane_end[i])
            self.fixtures[f"gate{i}"] = release_gate(
                self.scene, f"gate{i}", [-0.16, y, gate_z]
            )
        # Interior half-widths equal the 0.08 m containment half used by the
        # delivery predicate below (was 0.09 m in x, so a ball resting against
        # either x wall at |local x| = 0.074 m failed the 0.0728 m check).
        self.basin = container(
            self.scene,
            "basin",
            [0.20, 0.32, 0.08],
            half=(0.08, 0.08),
            height=0.075,
            static=True,
        )

    def reset_task(self):
        p = self.params
        for i, y in enumerate((-0.09, 0.09)):
            _, ball_z = self.lane_heights(self.lane_end[i])
            set_initial(self.objects[f"ball{i + 1}"], [-0.19, y, ball_z])
            self.fixtures[f"gate{i}"].reset(0, 0)
        second = p["second_release"] + float(
            self.rng.uniform(-p["second_release_jitter"], p["second_release_jitter"])
        )
        jitter = p["first_release_jitter"]
        first = p["first_release"] + (
            float(self.rng.uniform(-jitter, jitter)) if jitter > 0 else 0.0
        )
        self.events.flags["release_times"] = [first, second]
        self.events.flags.update(right_catch_position=None, target=[0.22, 0.02, 0.18])

    def before_physics(self):
        for i, t in enumerate(self.events.flags["release_times"]):
            f = self.fixtures[f"gate{i}"]
            if self.time < t:
                f.joint.set_drive_target(0)
                f.joint.set_drive_velocity_target(0)
            else:
                f.phase = -f.speed * t
                f.step(self.time, self.dt)
                self.events.once(
                    f"gate{i}_powered_open", self.time, force_limit=f.force
                )

    def update_task(self):
        right = self.arms["panda-1"]
        if self.phase >= 2 and self.phase < 5:
            local = (right.tool_pose.inv() * body(self.objects["ball1"]).entity_pose).p
            if max(abs(local[:2])) > self.params["tool_half"] or local[2] < -0.01:
                self.events.fail("first_ball_spill", self.time)
        if self.phase == 0:
            if free_interval(self, "ball1", "first_flight") > 0.025:
                self.events.once("first_airborne", self.time)
            if self.contact("ball1", "left_tool") and self.events.has("first_airborne"):
                self.advance()
        elif self.phase == 1 and cup_catch(self, "ball1", "panda-1", "first_receive"):
            self.events.flags["right_catch_position"] = right.tool_pose.p.tolist()
            self.advance()
        elif self.phase == 2:
            if np.linalg.norm(
                right.tool_pose.p - self.events.flags["right_catch_position"]
            ) > 0.06 and containment(
                self, "ball1", right.tool, self.params["tool_half"], 0.055, 0.016
            ):
                self.advance()
        elif self.phase == 3:
            if free_interval(self, "ball2", "second_flight") > 0.025:
                self.events.once("second_airborne", self.time)
            if self.contact("ball2", "left_tool") and self.events.has(
                "second_airborne"
            ):
                self.advance()
        elif self.phase == 4 and cup_catch(self, "ball2", "panda-1", "second_receive"):
            if containment(
                self, "ball1", right.tool, self.params["tool_half"], 0.055, 0.016
            ):
                self.advance()
        elif self.phase == 5:
            retained = all(
                containment(self, name, self.basin, 0.08, 0.075, 0.016)
                and not self.contact(name, "right_tool")
                for name in ("ball1", "ball2")
            )
            if self.phase_hold(retained, 0.7):
                self.events.physical_success = True
