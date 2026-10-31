"""Shared data types and constants.

Conventions: metres, radians, seconds; quaternions are
``wxyz``; a pose is a 7-vector ``[x y z qw qx qy qz]`` in the env frame (the world
frame of the single env, origin at the world origin).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import Any, Dict, Optional

import numpy as np

# --------------------------------------------------------------------------- timing
PHYSICS_DT: float = 1.0 / 120.0
"""PhysX step."""
DECIMATION: int = 2
"""Physics substeps per control tick (60 Hz control)."""
CONTROL_DT: float = PHYSICS_DT * DECIMATION
RECORD_STRIDE: int = 2
"""Control ticks per recorded sample (30 Hz data)."""

# --------------------------------------------------------------------------- robot
JOINT_NAMES = (
    "J1_1_joint",
    "J1_2_joint",
    "J1_3_joint",
    "J1_4_joint",
    "J1_5_joint",
    "J1_6_joint",
    "J2_1_joint",
    "J2_2_joint",
    "J2_3_joint",
    "J2_4_joint",
    "J2_5_joint",
    "J2_6_joint",
    "J1_7_joint",
    "J1_8_joint",
    "J2_7_joint",
    "J2_8_joint",
)
"""Canonical joint order: right arm, left arm, right fingers, left fingers."""
NUM_JOINTS = len(JOINT_NAMES)
RIGHT_ARM_SLICE = slice(0, 6)
LEFT_ARM_SLICE = slice(6, 12)
RIGHT_FINGER_SLICE = slice(12, 14)
LEFT_FINGER_SLICE = slice(14, 16)

EE_LINKS = ("J1_6", "J2_6")
"""End-effector links, right then left."""
GEL_BODIES = ("gsmini_left", "gsmini_right")
"""Gel pad bodies of the tactile (right) gripper; welded to J1_7 and J1_8."""

GRIPPER_OPEN: int = 0
GRIPPER_CLOSE: int = 1
GRIPPER_OPEN_Q: float = 0.010
"""Open finger target: J*_7 = +0.010, J*_8 = -0.010."""
GRIPPER_CLOSE_Q: float = 0.038
"""Default close magnitude: J*_7 = -0.038, J*_8 = +0.038 (drawer task: 0.041)."""
GRIPPER_WIDTH_OFFSET: float = 0.082
"""gripper_width = 0.082 + q7 - q8."""

PARKED_LEFT_ARM = (0.776, 0.144, -0.157, -0.013, 0.0, -0.224)
"""Idle left arm (J2_1..J2_6) used by every single-arm task."""

TABLE_TOP_Z: float = 1.102
ROBOT_BASE_POS = (-0.5, 0.0, 1.1)


class ArmIndex(IntEnum):
    """Index of an arm in the 2-slot action/observation layout."""

    RIGHT = 0
    LEFT = 1


# --------------------------------------------------------------------------- pose
Pose7 = np.ndarray
"""Alias for a float64 array of shape (7,): ``[x y z qw qx qy qz]``."""


def pose7(x: float, y: float, z: float, qw: float = 1.0, qx: float = 0.0, qy: float = 0.0, qz: float = 0.0) -> Pose7:
    """Build a pose vector."""
    return np.array([x, y, z, qw, qx, qy, qz], dtype=np.float64)


def nan_pose7() -> Pose7:
    """A pose of NaNs: *hold the current pose* in an action."""
    return np.full(7, np.nan, dtype=np.float64)


IDENTITY_POSE7: Pose7 = pose7(0.0, 0.0, 0.0)

# --------------------------------------------------------------------------- observation
ObsDict = Dict[str, Dict[str, np.ndarray]]
"""``{"policy": {...}, "privileged": {...}}``."""


# --------------------------------------------------------------------------- action
@dataclass
class Action:
    """One control tick of commands.

    Attributes:
        ee_target: ``(14,)`` right pose7 followed by left pose7, env frame. A NaN
            anywhere in an arm's 7 numbers means *hold that arm*.
        gripper: ``(2,)`` ints, ``[right, left]`` in ``{0: open, 1: close}``.
        gripper_gap: optional ``(2,)`` finger-gap override in metres; NaN entries
            fall back to the binary command. Recorded datasets only keep the binary
            command.
    """

    ee_target: np.ndarray
    gripper: np.ndarray
    gripper_gap: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        self.ee_target = np.asarray(self.ee_target, dtype=np.float64).reshape(14)
        self.gripper = np.asarray(self.gripper, dtype=np.int64).reshape(2)
        if self.gripper_gap is not None:
            self.gripper_gap = np.asarray(self.gripper_gap, dtype=np.float64).reshape(2)

    @classmethod
    def hold(cls, gripper=(GRIPPER_OPEN, GRIPPER_OPEN)) -> "Action":
        """Hold both arms where they are."""
        return cls(np.full(14, np.nan), np.asarray(gripper))

    @classmethod
    def from_vector(cls, vec: np.ndarray) -> "Action":
        """Inverse of :meth:`to_vector`."""
        vec = np.asarray(vec, dtype=np.float64).reshape(16)
        return cls(vec[:14], np.rint(vec[14:16]).astype(np.int64))

    def to_vector(self) -> np.ndarray:
        """``(16,)`` float32 as stored in datasets: 14 pose numbers + 2 gripper flags."""
        return np.concatenate([self.ee_target, self.gripper.astype(np.float64)]).astype(np.float32)

    def arm(self, arm: int) -> np.ndarray:
        """View of one arm's 7 numbers."""
        return self.ee_target[7 * arm : 7 * arm + 7]

    def copy(self) -> "Action":
        return Action(
            self.ee_target.copy(), self.gripper.copy(), None if self.gripper_gap is None else self.gripper_gap.copy()
        )


# --------------------------------------------------------------------------- phases / episodes
@dataclass(frozen=True)
class Phase:
    """A scripted-policy phase (recorded as ``phase`` in the dataset)."""

    id: int
    name: str


@dataclass
class EpisodeMeta:
    """Sidecar metadata of one recorded episode."""

    episode_id: int
    seed: int
    elapsed_steps: int
    success: bool
    source_type: str = "scripted"
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("extra")
        d.update(self.extra)
        return d
