"""Shared pieces of `hazard_hidden` for the track-F families (docs/hidden/hidden-f.md): the close view of the control
interface's references.

Under the control interface there is no `look`: a reference that has to read what a fixed camera does not show
brings the wrist camera there itself, as rows of `ee_pose`. `close_view` does it for one target: the hand closed,
raised, taken round to a standoff on the line of sight, in until the wrist camera is `distance` from the target,
a moment there, and back the same way to where it started (with the hand as it was). The camera's place and line of
sight on the hand are read off the driver's own copy of the world (`World.camera_pose("wrist")` against
`World.tcp_pose()`), so nothing here is tied to one robot's numbers; the poses themselves were checked on the UR5e
(a family offers this path on the robots it was admitted on and falls back to its compiled skill reference
elsewhere)."""
from __future__ import annotations

import math

import numpy as np

from robosafebench.sim import tf

STEP_S = 0.02           # one control step (`world.CONTROL_DT`)
CHUNK = 400             # rows per `act` call (8 s, within `episode.MAX_CHUNK_S`)


def _canon(q) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    return -q if q[0] < 0 else q


def _leg(a, qa, b, qb, seconds: float, grip: float) -> list:
    """Rows from pose (a, qa) to (b, qb), eased at both ends."""
    n = max(int(round(seconds / STEP_S)), 1)
    out = []
    for i in range(1, n + 1):
        s = 0.5 - 0.5 * math.cos(math.pi * i / n)
        q = _canon(tf.slerp(qa, qb, s))
        out.append([float(v) for v in a + (b - a) * s] + [float(v) for v in q] + [float(grip)])
    return out


def camera_on_hand(world) -> tuple[np.ndarray, np.ndarray]:
    """The wrist camera's place and line of sight in the frame of the TCP."""
    p, q = world.tcp_pose()
    c, look = world.camera_pose("wrist")
    inv = tf.quat_conj(q)
    return tf.rotate(inv, np.asarray(c) - np.asarray(p)), tf.unit(tf.rotate(inv, look))


def hand_for_view(world, camera_at, sight) -> tuple[np.ndarray, np.ndarray]:
    """The TCP pose that puts the wrist camera at `camera_at` looking along `sight` (bench frame), the camera's image
    upright (the tool's +x, the image's up, on the upper side)."""
    off, look = camera_on_hand(world)
    sight = tf.unit(np.asarray(sight, dtype=np.float64))
    side = np.cross(np.array([0.0, 0.0, 1.0]), sight)
    side = tf.unit(side) if float(np.linalg.norm(side)) > 1e-6 else np.array([1.0, 0.0, 0.0])
    # a frame on the hand: the line of sight, and the tool's y made square to it (it is square on the UR5e and the FR3):
    # the tool's y is kept level, so that the hand's x and z stand in the upright plane of the line of sight
    b_local = np.array([0.0, 1.0, 0.0]) - float(look[1]) * look
    b_local = tf.unit(b_local) if float(np.linalg.norm(b_local)) > 1e-6 else np.array([1.0, 0.0, 0.0])
    src = np.column_stack([look, b_local, np.cross(look, b_local)])
    best = None
    for flip in (1.0, -1.0):
        dst = np.column_stack([sight, flip * side, np.cross(sight, flip * side)])
        m = dst @ src.T
        up = float((m @ np.array([1.0, 0.0, 0.0]))[2])
        if best is None or up > best[0]:
            best = (up, m)
    m = best[1]
    quat = _canon(tf.mat_to_quat(m))
    return np.asarray(camera_at, dtype=np.float64) - m @ off, quat


def close_view(d, target, sight, distance: float, standoff: float = 0.12, clear_z: float = 0.30, hold_s: float = 0.6,
               legs_s=(3.0, 1.5, 2.0, 2.0, 1.0, 3.0), approach=None) -> dict:
    """Bring the wrist camera to `distance` from `target` (a point, bench frame), looking along `sight`, and back.
    The hand comes in to its pose from `standoff` away along `approach` (default: back along the line of sight).
    Sent as `act` rows of `ee_pose`. Returns {"camera": where the camera was to stand, "tcp": the TCP there}."""
    w = d.mirror.world
    target = np.asarray(target, dtype=np.float64)
    sight = tf.unit(np.asarray(sight, dtype=np.float64))
    cam = target - distance * sight
    tcp, quat = hand_for_view(w, cam, sight)
    start = np.asarray(d.mirror.command("ee_pose"), dtype=np.float64)
    p0, q0, g0 = start[:3], start[3:7], float(start[7])
    out = tcp + standoff * (tf.unit(np.asarray(approach, dtype=np.float64)) if approach is not None else -sight)
    above = np.array([out[0], out[1], max(float(out[2]), clear_z)])
    t_up, t_out, t_in, t_back, t_down, t_home = legs_s
    legs = [_leg(p0, q0, above, quat, t_up, 1.0), _leg(above, quat, out, quat, t_out, 1.0), _leg(out, quat, tcp, quat, t_in, 1.0),
            _leg(tcp, quat, tcp, quat, hold_s, 1.0), _leg(tcp, quat, out, quat, t_back, 1.0), _leg(out, quat, above, quat, t_down, 1.0),
            _leg(above, quat, p0, q0, t_home, g0)]
    for rows in legs:
        for k in range(0, len(rows), CHUNK):
            d.call("act", type="ee_pose", rows=rows[k:k + CHUNK])
    return {"camera": cam.tolist(), "tcp": tcp.tolist()}
