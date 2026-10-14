"""Raw 1 kHz records; measured derivatives reported raw and over a 20 ms window."""

from __future__ import annotations
import numpy as np
from .robots import panda_limits as lim
from .props.primitives import body


class Telemetry:
    def __init__(self, dt: float):
        self.dt = dt
        self.rows = []
        self.previous_velocity = None
        self.previous_tcp_velocity = None
        self.violations = set()

    def sample(self, env, arm=None):
        arm = arm or env
        servo = arm.servo
        q, v = arm.robot.qpos.copy(), arm.robot.qvel.copy()
        a = (
            np.zeros(9)
            if self.previous_velocity is None
            else (v - self.previous_velocity) / self.dt
        )
        self.previous_velocity = v.copy()
        tcp = arm.agent.tcp._objs[0]
        tcp_v = tcp.linear_velocity.copy()
        tcp_a = (
            np.zeros(3)
            if self.previous_tcp_velocity is None
            else (tcp_v - self.previous_tcp_velocity) / self.dt
        )
        self.previous_tcp_velocity = tcp_v.copy()
        tool_body = arm.tool_body if arm.tool is not None else tcp
        # PhysX linear velocity is at COM. Correct to the explicitly logged tool origin.
        tip_v = tool_body.linear_velocity + np.cross(
            tool_body.angular_velocity,
            tool_body.entity_pose.p
            - (tool_body.entity_pose * tool_body.cmass_local_pose).p,
        )
        row = dict(
            time=env.time,
            q=q,
            v=v,
            a=a,
            reference=servo.reference.copy(),
            reference_v=servo.reference_velocity.copy(),
            reference_a=servo.reference_acceleration.copy(),
            reference_j=servo.reference_jerk.copy(),
            torque=servo.torque.copy(),
            torque_rate=(servo.torque - servo.previous_torque) / self.dt,
            tcp_p=tcp.entity_pose.p.copy(),
            tcp_v=tcp_v,
            tcp_a=tcp_a,
            tcp_w=tcp.angular_velocity.copy(),
            tip_p=arm.tool_pose.p.copy(),
            tip_v=tip_v.copy(),
            tip_w=(
                arm.tool_body.angular_velocity
                if arm.tool is not None
                else tcp.angular_velocity
            ).copy(),
        )
        row.update(
            reference_tcp_v=servo.reference_tcp_velocity.copy(),
            reference_tcp_a=servo.reference_tcp_acceleration.copy(),
            reference_tcp_w=servo.reference_tcp_omega.copy(),
        )
        for name, obj in env.objects.items():
            rb = body(obj)
            row["object_" + name + "_p"] = rb.entity_pose.p.copy()
            row["object_" + name + "_v"] = rb.linear_velocity.copy()
            row["object_" + name + "_w"] = rb.angular_velocity.copy()
            rotation = (
                rb.entity_pose * rb.cmass_local_pose
            ).to_transformation_matrix()[:3, :3]
            local_omega = rotation.T @ rb.angular_velocity
            row["object_" + name + "_energy"] = float(
                0.5 * rb.mass * np.dot(rb.linear_velocity, rb.linear_velocity)
                + 0.5 * np.dot(rb.inertia, local_omega**2)
                + rb.mass * 9.81 * (rb.entity_pose * rb.cmass_local_pose).p[2]
            )
        for name, fixture in env.fixtures.items():
            row["fixture_" + name] = np.array([fixture.q, fixture.v, fixture.work])
        self.rows.append(row)
        if not all(np.isfinite(value).all() for value in row.values()):
            self.violations.add("nonfinite_physics")
        if np.any(q[:7] < lim.LOWER - 0.002) or np.any(q[:7] > lim.UPPER + 0.002):
            self.violations.add("joint_position")
        if np.any(abs(v[:7]) > lim.VELOCITY * 1.01):
            self.violations.add("measured_joint_speed")
        if np.any(abs(v[7:]) > 0.051):
            self.violations.add("finger_speed")
        if (
            np.linalg.norm(tcp_v) > lim.CART_SPEED * 1.01
            or np.linalg.norm(tcp.angular_velocity) > lim.CART_OMEGA * 1.01
        ):
            self.violations.add("measured_cartesian_speed")
        if (
            np.linalg.norm(servo.reference_tcp_velocity) > lim.CART_SPEED * 1.01
            or np.linalg.norm(servo.reference_tcp_omega) > lim.CART_OMEGA * 1.01
        ):
            self.violations.add("reference_cartesian_speed")
        if np.any(abs(servo.torque[:7]) > lim.TORQUE + 1e-4) or np.any(
            abs(row["torque_rate"][:7]) > lim.TORQUE_RATE + 0.1
        ):
            self.violations.add("actuator_limit")
        if (
            np.any(abs(servo.reference_velocity[:7]) > lim.VELOCITY + 1e-4)
            or np.any(abs(servo.reference_acceleration[:7]) > lim.ACCELERATION + 1e-3)
            or np.any(abs(servo.reference_jerk[:7]) > lim.JERK + 1.0)
        ):
            self.violations.add("reference_limit")
        n = round(0.020 / self.dt)
        if len(self.rows) > n:
            window_a = (v - self.rows[-n - 1]["v"]) / (n * self.dt)
            if np.any(abs(window_a[:7]) > lim.ACCELERATION * 1.05):
                self.violations.add("measured_joint_acceleration_20ms")
            window_tcp_a = (tcp_v - self.rows[-n - 1]["tcp_v"]) / (n * self.dt)
            window_alpha = (row["tcp_w"] - self.rows[-n - 1]["tcp_w"]) / (n * self.dt)
            if (
                np.linalg.norm(window_tcp_a) > lim.CART_ACCELERATION * 1.05
                or np.linalg.norm(window_alpha) > lim.CART_ALPHA * 1.05
            ):
                self.violations.add("measured_cartesian_acceleration_20ms")
            reference_a = (
                servo.reference_tcp_velocity - self.rows[-n - 1]["reference_tcp_v"]
            ) / (n * self.dt)
            reference_alpha = (
                servo.reference_tcp_omega - self.rows[-n - 1]["reference_tcp_w"]
            ) / (n * self.dt)
            if (
                np.linalg.norm(reference_a) > lim.CART_ACCELERATION * 1.05
                or np.linalg.norm(reference_alpha) > lim.CART_ALPHA * 1.05
            ):
                self.violations.add("reference_cartesian_acceleration_20ms")
        if len(self.rows) > 2 * n:
            jerk = (v - 2 * self.rows[-n - 1]["v"] + self.rows[-2 * n - 1]["v"]) / (
                n * self.dt
            ) ** 2
            if np.any(abs(jerk[:7]) > lim.JERK * 1.05):
                self.violations.add("measured_joint_jerk_20ms")

    def arrays(self):
        return (
            {key: np.asarray([r[key] for r in self.rows]) for key in self.rows[0]}
            if self.rows
            else {}
        )

    def summary(self):
        data = self.arrays()
        if not data:
            return {"violations": sorted(self.violations)}
        result = {
            f"peak_{key}": np.max(abs(data[key]), axis=0).tolist()
            for key in (
                "v",
                "a",
                "reference_v",
                "reference_a",
                "reference_j",
                "torque",
                "torque_rate",
            )
        }
        result.update(
            {
                f"peak_{key}_norm": float(np.max(np.linalg.norm(data[key], axis=1)))
                for key in (
                    "tcp_v",
                    "tcp_a",
                    "tcp_w",
                    "tip_v",
                    "reference_tcp_v",
                    "reference_tcp_a",
                    "reference_tcp_w",
                )
            }
        )
        n = round(0.020 / self.dt)
        if len(data["v"]) > n:
            result["peak_acceleration_20ms"] = np.max(
                abs((data["v"][n:] - data["v"][:-n]) / (n * self.dt)), axis=0
            ).tolist()
        if len(data["v"]) > 2 * n:
            result["peak_jerk_20ms"] = np.max(
                abs(
                    (data["v"][2 * n :] - 2 * data["v"][n:-n] + data["v"][: -2 * n])
                    / (n * self.dt) ** 2
                ),
                axis=0,
            ).tolist()
            result["peak_raw_jerk"] = np.max(
                abs(np.diff(data["a"], axis=0) / self.dt), axis=0
            ).tolist()
        result["motor_work_J"] = float(np.sum(data["torque"] * data["v"]) * self.dt)
        result["object_peak_speeds"] = {
            key: float(np.max(np.linalg.norm(value, axis=1)))
            for key, value in data.items()
            if key.startswith("object_") and key.endswith("_v")
        }
        result["maximum_tool_relocation"] = float(
            np.max(np.linalg.norm(data["tip_p"] - data["tip_p"][0], axis=1))
        )
        result["violations"] = sorted(self.violations)
        result["filter_convention"] = (
            "Raw records retained. Acceleration validity uses 20 ms endpoint difference, 5% numeric tolerance; speed uses every raw substep with 1% tolerance. No overspeed samples suppressed."
        )
        return result
