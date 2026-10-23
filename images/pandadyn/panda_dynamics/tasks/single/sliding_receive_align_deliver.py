import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import box, set_initial, position, velocity
from panda_dynamics.props.fixtures import single_axis
from panda_dynamics.tasks.predicates import supported


class SlidingReceiveAlignDeliver(PandaDynamicEnv):
    TASK = "S05-SlidingReceiveAlignDeliver"
    NAMESPACE = "PandaMultiStage"
    TOOL = "receiver"
    REFERENCE_ACCELERATION = 0.55
    TOOL_START = (0.21, -0.18, 0.13)
    MOUNT = (0.12, 0.12, 0.04)
    PHASES = (
        "source_to_tray",
        "inertial_staging",
        "transport_turn",
        "match_receiver",
        "support_transfer",
    )
    INSTRUCTION = (
        "接住滑块，用近水平托盘加速滑移定位，经过转弯，再匹配运动支撑台并卸载同一滑块。"
    )

    def build_task(self):
        box(
            self.scene,
            "lane",
            [0.18, 0.055, 0.012],
            [-0.078, 0, 0.123],
            static=True,
            mu=0.015,
        )
        self.objects["block"] = box(
            self.scene,
            "block",
            [0.018] * 3,
            [-0.2, 0, 0.154],
            mass=self.params["object_mass"],
            mu=self.params["friction"],
        )
        self.fixtures["receiver"] = single_axis(
            self.scene,
            "receiver",
            [self.params["receiver_base_x"], 0.26, 0.13],
            shape="platform",
            speed=self.params["fixture_speed"],
            force=8.0,
            slider_axis="x",
        )

    # Declared receiver law (DrivenFixture "oscillate", 0.20 m stroke):
    #   q(t) = offset + 0.20 sin(omega t + phase), omega = fixture_speed / 0.20,
    #   offset ~ U(+-fixture_offset), phase ~ U(+-fixture_phase).
    # Nominal has fixture_phase = 0: no extra draw and the original law.
    RECEIVER_STROKE = 0.20

    def reset_task(self):
        spread = self.params["lateral_spread"]
        set_initial(
            self.objects["block"],
            [-0.17, self.rng.uniform(-spread, spread), 0.1535],
            [self.params["incoming_speed"], 0, 0],
        )
        receiver = self.fixtures["receiver"]
        speed = self.params["fixture_speed"]
        span = self.params["fixture_offset"]
        offset = self.rng.uniform(-span, span)
        phase = 0.0
        if self.params["fixture_phase"] > 0:
            phase = self.rng.uniform(
                -self.params["fixture_phase"], self.params["fixture_phase"]
            )
            # Clock shift for the receiver's motor law (before_physics); kept
            # in the event flags so exact snapshots restore it.
            self.events.flags["receiver_clock_shift"] = phase / (
                speed / self.RECEIVER_STROKE
            )
        receiver.reset(
            offset + self.RECEIVER_STROKE * np.sin(phase), speed * np.cos(phase)
        )
        receiver.phase = offset
        self.events.flags.update(
            waypoints=[[0.08, 0.13, 0.22], [0.19, 0.20, 0.22]],
            waypoint_index=0,
            staging=[self.params["target_offset"], 0, 0.018],
        )
        self.events.emit("release", 0.0, object="block")

    def before_physics(self):
        # Base loop, except the receiver reads its seeded clock shift (absent
        # in nominal, so its motor targets are bit-for-bit unchanged).
        shift = self.events.flags.get("receiver_clock_shift", 0.0)
        for name, fixture in self.fixtures.items():
            fixture.step(self.time + shift if name == "receiver" else self.time, self.dt)

    def update_task(self):
        obj = self.objects["block"]
        p = position(obj)
        local = self.local_position(obj)
        flags = self.events.flags
        on_tool = supported(self, "block", "tool")
        if self.contact("block", "lane"):
            self.events.once("source_support", self.time)
        if self.phase == 0:
            if self.events.hold(
                "received_settle",
                self.events.has("source_support")
                and on_tool
                and not self.contact("block", "lane")
                and p[0] > 0.12
                and self.relative_speed(obj) < 0.05,
                self.time,
                0.10,
            ):
                flags["received_local"] = local.tolist()
                self.advance()
        elif self.phase == 1:
            tilt = np.arccos(
                np.clip(self.tool_pose.to_transformation_matrix()[2, 2], -1, 1)
            )
            if tilt > np.deg2rad(2.1):
                self.events.fail("tilt_only_shortcut", self.time)
            slip = float(
                np.linalg.norm(local[:2] - np.array(flags["received_local"])[:2])
            )
            if (
                self.telemetry.rows
                and np.linalg.norm(self.telemetry.rows[-1]["tcp_a"][:2])
                > self.params["friction"] * 9.81 * 1.1
            ):
                self.events.once("active_tray_acceleration", self.time)
            if slip > 0.025 and self.events.has("active_tray_acceleration"):
                self.events.once("inertial_slip", self.time, slip=slip)
            self.phase_hold(
                self.events.has("inertial_slip")
                and on_tool
                and np.linalg.norm(local[:2] - np.array(flags["staging"])[:2])
                < self.params["target_tolerance"]
                and self.relative_speed(obj) < 0.045,
                0.3,
            )
        elif self.phase == 2:
            index = flags["waypoint_index"]
            if (
                np.linalg.norm(self.tool_pose.p - flags["waypoints"][index]) < 0.022
                and on_tool
            ):
                self.events.emit("waypoint", self.time, index=index)
                flags["waypoint_index"] += 1
                if flags["waypoint_index"] == 2:
                    self.advance()
        elif self.phase == 3:
            f = self.fixtures["receiver"]
            if (
                on_tool
                and np.linalg.norm(
                    self.tool_body.linear_velocity - f.link._objs[0].linear_velocity
                )
                < 0.05
                and np.linalg.norm(
                    self.tool_pose.p
                    - (f.link._objs[0].entity_pose.p + [0.34, 0, 0.008])
                )
                < 0.012
                and abs(f.v) >= self.params["receiver_min_speed"]
            ):
                self.advance()
        elif self.phase == 4:
            f = self.fixtures["receiver"]
            minimum = self.params["receiver_min_speed"]
            if minimum > 0 and not self.events.has("receiver_touchdown"):
                # Hard: the hand-off must land on a platform that is moving.
                # Its speed is read one substep before the first block contact,
                # so the impact itself cannot change the verdict.
                if self.contact("block", "receiver") > 0:
                    speed = flags.get("receiver_speed_before", abs(f.v))
                    self.events.emit("receiver_touchdown", self.time, speed=speed)
                    if speed < minimum:
                        self.events.fail("static_receiver_transfer", self.time)
                flags["receiver_speed_before"] = abs(f.v)
            relative = p - f.link._objs[0].entity_pose.p
            condition = (
                self.contact("block", "receiver") > 0
                and not on_tool
                and max(abs(relative[:2])) < 0.07
                and np.linalg.norm(velocity(obj) - f.link._objs[0].linear_velocity)
                < 0.045
            )
            if self.phase_hold(condition, 0.5):
                self.events.physical_success = True
        if self.phase in (1, 2, 3) and (
            local[2] < -0.015 or max(abs(local[:2])) > self.params["tool_half"] + 0.02
        ):
            self.events.fail("spill", self.time)
