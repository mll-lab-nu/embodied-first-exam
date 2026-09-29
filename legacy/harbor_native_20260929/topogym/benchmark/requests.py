"""Validate an entire request before mutating the simulator."""
from dataclasses import dataclass
import math
import numpy as np


def number(value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{name} must be finite in [{lo}, {hi}]")
    return float(value)


@dataclass
class Request:
    cameras: list
    fps: float
    video: str
    depth: str
    ticks: int
    rows: object = None
    action_type: str = "joint_position"
    interpolate: str = "hold"
    clipped: object = None
    note: str = ""


def validate(meta, parts, spec, *, submit):
    if not isinstance(meta, dict):
        raise ValueError("Request metadata must be an object")
    common = {"cameras", "video_fps", "video", "depth", "include_depth"}
    allowed = common | ({"type", "dt", "interpolate", "note"} if submit else {"seconds"})
    if set(meta) - allowed:
        raise ValueError("Unknown request fields")
    cameras = meta.get("cameras", spec["default_cameras"])
    if not isinstance(cameras, list) or any(not isinstance(x, str) for x in cameras):
        raise ValueError("cameras must be a list of names")
    cameras = list(dict.fromkeys(x for x in cameras if x in spec["cameras"]))
    fps = number(meta.get("video_fps", spec.get("video_fps", 30)), "video_fps", .1, spec["control_hz"])
    video = meta.get("video", "mp4" if submit else "frames")
    if video not in ("mp4", "frames", "both", "none"):
        raise ValueError("Invalid video format")
    if type(meta.get("include_depth", False)) is not bool:
        raise ValueError("include_depth must be boolean")
    depth = meta.get("depth", "legacy" if meta.get("include_depth") else "none")
    if type(depth) is bool:
        depth = "last" if depth else "none"
    if depth not in ("none", "last", "frames", "legacy") or depth == "legacy" and "depth" in meta:
        raise ValueError("Invalid depth mode")
    if depth != "none" and not all(spec["cameras"][c]["depth"] for c in cameras):
        raise ValueError("Depth is not enabled")
    hz = spec["control_hz"]
    if not submit:
        if parts:
            raise ValueError("observe does not accept binary parts")
        seconds = number(meta.get("seconds", 0), "seconds", 0, spec["max_watch_s"])
        return Request(cameras, fps, video, depth, int(math.ceil(seconds * hz - 1e-9)))
    kind = meta.get("type")
    if not isinstance(kind, str) or kind not in ("joint_position", "ee_pose"):
        raise ValueError("Unsupported action type")
    if set(parts) != {"actions"}:
        raise ValueError("submit requires exactly one actions part")
    rows = parts["actions"].get("data")
    dim = spec["action_types"][kind]["dim"]
    if not isinstance(rows, np.ndarray) or rows.dtype.kind != "f" or rows.dtype.itemsize != 4 or rows.ndim != 2 or rows.shape[1] != dim or not len(rows) or not np.isfinite(rows).all():
        raise ValueError(f"actions must be finite float32 (T, {dim}), T > 0")
    dt = number(meta.get("dt", 1/hz), "dt", 1/hz, .5)
    ticks = round(dt * hz)
    if not math.isclose(dt * hz, ticks, rel_tol=0, abs_tol=1e-6):
        raise ValueError("dt must be a control-period multiple")
    if len(rows)*ticks/hz > spec["max_chunk_s"] + 1e-9:
        raise ValueError("Chunk too long")
    interpolation = meta.get("interpolate", "linear")
    if interpolation not in ("linear", "hold"):
        raise ValueError("Invalid interpolation")
    note = meta.get("note", "")
    if not isinstance(note, str) or len(note) > 4096:
        raise ValueError("note must be a short string")
    rows = rows.astype(np.float64, copy=True)
    clipped = []
    if kind == "joint_position":
        limits = np.asarray(spec["action_types"][kind]["limits"])
        limited = np.clip(rows, limits[:, 0], limits[:, 1])
        clipped = [dict(row=int(r), index=int(c), reason="joint_limit") for r,c in np.argwhere(rows != limited)]
        rows = limited
    else:
        for i, gripper in enumerate(spec["robot_spec"]["grippers"].values()):
            quaternion = rows[:, 8*i+3:8*i+7]
            if not np.allclose(np.linalg.norm(quaternion, axis=1), 1, atol=1e-5, rtol=0):
                raise ValueError("ee_pose requires unit wxyz quaternions")
            column = 8*i+7
            limited = np.clip(rows[:, column], *gripper["command"]["range"])
            clipped.extend(dict(row=int(r), index=column, reason="gripper_limit") for r in np.flatnonzero(rows[:, column] != limited))
            rows[:, column] = limited
    return Request(cameras, fps, video, depth, ticks, rows, kind, interpolation, clipped, note)
