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

PROTOCOL_VERSION = 3
STATE_KEY = {"joint_abs": "joint", "ee_abs": "ee"}  # the measured state sent with each action space


@dataclass(frozen=True)
class PolicySpec:
    """What a model needs and returns; sent by the server first, taken from the model config's ``spec``."""
    name: str                     # checkpoint name, e.g. "pi05_droid_jointpos"
    embodiment: str               # TopoGym robot_id: "aloha" | "panda_robotiq"
    cameras: tuple[str, ...]      # TopoGym camera names, in the order of the model's image slots
    action_space: str             # "joint_abs" | "ee_abs"
    control_hz: float             # control frequency of the training data
    chunk_size: int               # H: targets predicted per inference
    execute_steps: int            # k: targets executed before the next inference
    reach_tolerance_m: float = 0.0  # ee_abs: hold each target until every TCP is this close (0 = one step each)
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self):
        object.__setattr__(self, "cameras", tuple(self.cameras))
        if self.reach_tolerance_m and self.action_space != "ee_abs":
            raise ValueError(f"{self.name}: reach_tolerance_m needs ee_abs targets")


@dataclass(frozen=True)
class Observation:
    images: dict[str, np.ndarray]   # camera -> (480, 848, 3) uint8 as rendered; models crop and resize
    state: dict[str, np.ndarray]    # {STATE_KEY[action_space]: standard float32 vector of measured values}
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
