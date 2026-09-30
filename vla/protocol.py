"""Messages shared by the evaluation and model processes; standard library and NumPy only.

Wire format of one message (sent with ``Connection.send_bytes``, never pickle):
``[4-byte big-endian header length][UTF-8 JSON header][raw bytes of array 0][array 1]...``.
The header is ``{"msg": <message with each array replaced by {"__array__": i}>, "arrays": [{dtype, shape}, ...]}``.

Message types: server -> client ``spec`` (PolicySpec fields) and ``error`` (``message``);
client -> server ``reset`` (``seed``, answered by ``ok``) and ``infer`` (Observation fields, answered by
``chunk`` with ``actions``).
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import struct

import numpy as np

PROTOCOL_VERSION = 2


@dataclass(frozen=True)
class PolicySpec:
    """What a model needs and returns; sent by the server first, taken from the model config's ``spec``."""
    name: str                     # checkpoint name, e.g. "pi05_droid_jointpos"
    embodiment: str               # TopoGym robot_id: "aloha" | "panda_robotiq"
    cameras: tuple[str, ...]      # TopoGym camera names, in the order of the model's image slots
    state_keys: tuple[str, ...]   # ("joint",) | ("ee",) | ("joint", "ee")
    action_space: str             # "joint_abs" | "ee_abs"
    control_hz: float             # control frequency of the training data
    chunk_size: int               # H: targets predicted per inference
    execute_steps: int            # k: targets executed before the next inference
    reach_tolerance_m: float = 0.0  # ee_abs: hold each target until every TCP is this close (0 = one step each)
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self):
        object.__setattr__(self, "cameras", tuple(self.cameras))
        object.__setattr__(self, "state_keys", tuple(self.state_keys))
        if (self.reach_tolerance_m or self.action_space == "ee_abs") and "ee" not in self.state_keys:
            raise ValueError(f"{self.name}: ee_abs and reach_tolerance_m need the ee state (state_keys)")
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(f"Model server speaks protocol version {self.protocol_version}, "
                             f"this side speaks {PROTOCOL_VERSION}")


@dataclass(frozen=True)
class Observation:
    images: dict[str, np.ndarray]   # camera -> (480, 848, 3) uint8 at native resolution
    state: dict[str, np.ndarray]    # state key -> standard float32 vector (measured values)
    instruction: str
    episode_id: str
    step: int                       # control step index, from 0


@dataclass(frozen=True)
class ActionChunk:
    actions: np.ndarray             # (H, D) float32 absolute targets in the action_space standard layout


def encode(msg: dict) -> bytes:
    arrays = []

    def pack(value):
        if isinstance(value, np.ndarray):
            arrays.append(np.ascontiguousarray(value))
            return {"__array__": len(arrays) - 1}
        if isinstance(value, dict):
            return {key: pack(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [pack(item) for item in value]
        return value

    header = json.dumps(dict(msg=pack(msg), arrays=[dict(dtype=a.dtype.str, shape=a.shape) for a in arrays]))
    header = header.encode()
    return b"".join([struct.pack(">I", len(header)), header, *(a.tobytes() for a in arrays)])


def decode(data: bytes) -> dict:
    size, = struct.unpack_from(">I", data)
    header = json.loads(data[4:4 + size])
    arrays, offset = [], 4 + size
    for meta in header["arrays"]:
        dtype, count = np.dtype(meta["dtype"]), math.prod(meta["shape"])
        arrays.append(np.frombuffer(data, dtype, count, offset).reshape(meta["shape"]))
        offset += count * dtype.itemsize
    if offset != len(data):
        raise ValueError("Message size differs from its header's array sizes")

    def unpack(value):
        if isinstance(value, dict):
            if value.keys() == {"__array__"}:
                return arrays[value["__array__"]]
            return {key: unpack(item) for key, item in value.items()}
        if isinstance(value, list):
            return [unpack(item) for item in value]
        return value

    return unpack(header["msg"])
