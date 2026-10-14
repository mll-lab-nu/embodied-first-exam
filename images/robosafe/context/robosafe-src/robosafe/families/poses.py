"""Moves made of `move_tcp` and `gripper`: what the scripted solutions of the pose interface share (docs/MOTION.md 5).

A scripted solution acts through the agent's tools and nothing else. Where to send the hand is worked out here from
where things are in the driver's private copy of the episode (ground truth, as `Driver.pixel_of` uses for the pixel
tools): the asset's own grasp of a thing from above, how far the thing hangs below the pinch point, where the wrist
camera has to be to look at a point. Nothing here plans a way or tests one for collisions: the heights of the
crossings are the caller's, as they are an agent's with this interface.
"""
from __future__ import annotations

import math

import numpy as np

from robosafe.families.driver import DriverError
from robosafe.sim import actions as A
from robosafe.sim import tf

OPEN_MARGIN = 0.024         # m: the fingers are opened this much wider than the thing before the hand comes down
CLOSE_UNDER = 0.015         # m: ... and closed to this much less than its width (they stop on it)
HOVER = 0.10                # m: the hand comes down on a thing from this far above its grasp
SHORT = 0.006               # m: a descent that is stopped this close to the grasp still counts
# the wrist camera in the hand's frame (origin at the pinch point, z out of the hand): what the agents' document says
WRIST_EYE = np.array([0.085, 0.0, -0.100])
WRIST_FORWARD = np.array([-0.3162, 0.0, 0.9487])


def yaw_of(closing) -> float:
    """The `yaw` of a hand that points straight down and closes its fingers along `closing` (a direction in the
    bench frame; its sign does not matter): between -90 and 90 degrees."""
    yaw = math.degrees(math.atan2(-float(closing[0]), float(closing[1])))
    return (yaw + 90.0) % 180.0 - 90.0


def top_grasp(d, obj: str) -> dict:
    """The asset's grasp of `obj` from above, where the object is now: the pinch point (`pos`), the hand's `yaw`, the
    thing's `width` between the fingers, and how far it reaches below the pinch point (`under`)."""
    w = d.mirror.world
    for g in A.grasps_of(w, obj, prefer="top"):
        if g["type"] == "top":
            pos = np.asarray(g["pose"][0], dtype=np.float64)
            closing = tf.rotate(g["pose"][1], [0.0, 1.0, 0.0])
            return {"object": obj, "pos": pos, "yaw": round(yaw_of(closing), 1), "width": float(g["width"]),
                    "under": float(pos[2] - w.box(obj)[0][2])}
    raise DriverError(f"{obj!r} has no grasp from above")


def take(d, obj: str, lift: float = 0.12, hover: float = HOVER) -> dict:
    """Take `obj` from above and raise it by `lift`: open, go to above it, come down, close, go up. Returns the grasp
    (`top_grasp`), with `pos` where the pinch point now is."""
    g = top_grasp(d, obj)
    x, y, z = g["pos"]
    d.gripper(round(min(g["width"] + OPEN_MARGIN, 0.085) * 1e3, 1))
    d.go_tcp(x, y, z + hover, g["yaw"])
    # the way down: fingers that come to rest on the thing a few millimetres short of the grasp (the loop of a towel
    # that lies flat) can still close on it, as they do in `pick`
    out = d.move_tcp(x, y, z, g["yaw"], speed=0.5, check=False)
    if not out.get("ok") or (out["result"]["status"] != "ok" and out["result"]["position_error_mm"] > SHORT * 1e3):
        raise DriverError(f"the hand did not get down to {obj!r}: {out.get('error') or out['result']}")
    out = d.gripper(round(max(g["width"] - CLOSE_UNDER, 0.0) * 1e3, 1))
    if not out["result"]["holding"]:
        raise DriverError(f"the fingers closed at {g['pos'].round(3).tolist()} and hold nothing")
    d.go_tcp(x, y, z + lift, g["yaw"])
    w = d.mirror.world                          # how far it hangs below the pinch point now that it is off the table
    return {**g, "pos": np.array([x, y, z + lift]), "under": float(w.tcp_pose()[0][2] - w.box(obj)[0][2])}


def carry(d, g: dict, x: float, y: float, z: float, yaw: float | None = None) -> dict:
    """Carry what was taken (`g`, from `take`) to the pinch point (x, y, z): up or down where the hand is, then across
    at that height. Nothing is tested: `z` must clear what stands on the way."""
    yaw = g["yaw"] if yaw is None else yaw
    here = g["pos"]
    if abs(float(here[2]) - z) > 1e-3:
        d.go_tcp(here[0], here[1], z, g["yaw"])
    d.go_tcp(x, y, z, yaw)
    return {**g, "pos": np.array([x, y, z]), "yaw": yaw}


def put(d, g: dict, spot, above: float = 0.004, rise: float = 0.12) -> dict:
    """Put what the hand holds down at `spot` (where its underside is to rest): across at the height the hand is at,
    straight down until the underside is `above` the spot, open, straight up by `rise`."""
    spot = np.asarray(spot, dtype=np.float64)
    z = float(spot[2]) + g["under"] + above
    if float(np.linalg.norm(g["pos"][:2] - spot[:2])) > 1e-3:
        g = carry(d, g, spot[0], spot[1], float(g["pos"][2]))
    d.go_tcp(spot[0], spot[1], z, g["yaw"], speed=0.5)
    d.gripper(round(min(g["width"] + OPEN_MARGIN, 0.085) * 1e3, 1))
    d.go_tcp(spot[0], spot[1], z + rise, g["yaw"])
    return {**g, "pos": np.array([spot[0], spot[1], z + rise])}


def view(d, point, side: str = "front", distance: float = 0.30, elevation_deg: float = 37.0):
    """Bring the wrist camera to look at `point` from `side` (`above`, `front`, `back`, `left`, `right`), `distance`
    from it: the pose of the hand is worked out from where the camera sits in the hand (the agents' document gives
    the same numbers), and the hand goes there by `move_tcp`. The image's "up" is kept up. From the front at
    0.30 m a label 3 cm wide is about 40 pixels wide in the `wrist` image."""
    point = np.asarray(d.where(point) if isinstance(point, str) else point, dtype=np.float64)
    e = math.radians(elevation_deg)
    flat = {"front": (0.0, -1.0), "back": (0.0, 1.0), "left": (-1.0, 0.0), "right": (1.0, 0.0)}
    if side == "above":
        out, up = np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])
    else:
        out, up = np.array([flat[side][0] * math.cos(e), flat[side][1] * math.cos(e), math.sin(e)]), np.array([0.0, 0.0, 1.0])
    eye = point + out * distance
    forward = -out
    # the camera's axes in the bench frame: forward, and "down" as nearly opposite to `up` as forward allows
    down = tf.unit(-up - float(np.dot(-up, forward)) * forward)
    right = np.cross(down, forward)
    # the same three axes in the hand's frame (the document's table): right (0, 1, 0), down, forward
    c_down = np.array([-0.9487, 0.0, -0.3162])
    hand_from_cam = np.stack([np.array([0.0, 1.0, 0.0]), c_down, WRIST_FORWARD], axis=1)
    bench_from_cam = np.stack([right, down, forward], axis=1)
    rot = bench_from_cam @ hand_from_cam.T                  # the hand's axes in the bench frame
    quat = tf.mat_to_quat(rot)
    pos = eye - rot @ WRIST_EYE
    pos[2] = max(float(pos[2]), 0.05)
    return d.go_tcp(*pos, *tf.ypr_from_quat(quat))
