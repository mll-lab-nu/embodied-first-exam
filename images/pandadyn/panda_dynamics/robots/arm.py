"""One stock Panda's existing controller, model and tool in a shared scene."""

from dataclasses import dataclass
import numpy as np
import sapien


@dataclass
class ArmSetup:
    tool: str | None
    start: tuple[float, float, float]
    base: tuple[float, float, float] = (-0.55, 0, 0)
    yaw: float = 0.0
    mount: tuple[float, float, float] = (0.12, 0, 0.04)
    quaternion: tuple[float, float, float, float] = (1, 0, 0, 0)
    half: float = 0.065
    mass: float = 0.2


@dataclass
class ArmRuntime:
    uid: str
    role: str
    setup: ArmSetup
    agent: object
    robot: object
    ik: object
    servo: object = None
    telemetry: object = None
    tool: object = None
    tool_body: object = None
    initial_tool_position: object = None

    @property
    def mount_pose(self):
        return sapien.Pose(self.setup.mount, [0, 1, 0, 0])

    @property
    def tool_pose(self):
        return (
            self.tool_body if self.tool is not None else self.agent.tcp._objs[0]
        ).entity_pose

    @property
    def contact_name(self):
        return "tool" if self.role == "single" else f"{self.role}_tool"

    def parked_action(self):
        return np.r_[self.robot.qpos[:7], sum(self.robot.qpos[7:])]
