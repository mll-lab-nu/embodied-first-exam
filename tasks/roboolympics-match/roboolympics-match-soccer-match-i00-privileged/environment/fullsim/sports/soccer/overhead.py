"""Overhead cameras of humanoid soccer 2 v 2 (the formats with perception = "overhead": match_overhead, duel_overhead).

Like the shared vision of RoboCup SSL (sports/soccer_ssl sim/camera.py: a camera bar 4 m above the field, cameras
looking straight down, ideal images, 40 ms latency), scaled to the humanoid pitch and the robots' height: two cameras
CAMERA_HEIGHT above the floor, one over each half, straight down. Each camera covers its half of the boarded area
(|x| <= 5.3, |y| <= 3.8 m: the 10 x 7 m pitch, the boards and a margin) at the height of the robots' heads
(ROBOT_TOP), plus OVERLAP past the halfway line, so a robot on the line is whole in at least one tile.

Each team sees the field in its own frame (the frame of its robots' state): image right = the team's +x (the
direction it attacks), image up = the team's +y; tile 0 = the team's own half, tile 1 = the opponents' half. For team
B the cameras are the mirror images of team A's (the world rotated by 180 degrees about z), so both teams get the same
pictures of the same situation (mirror symmetry). The images show the world VISION_LATENCY_S ago (the plugin's
render_state), an ideal pinhole camera without noise or distortion.

    camera_defs(team)          the cameras in renderers/base.CameraDef dict form, WORLD frame (what the task's renderer
                               draws; Match.cameras(seat))
    calibration(team)          the same cameras in the TEAM frame, with focal length and principal point (game spec)
    project(cam, p) / ground_point(cam, u, v, z)   the pinhole model of renderers/base.CameraDef (u right, v down)
"""
from __future__ import annotations

import math

import numpy as np

CAMERA_HEIGHT = 6.0          # m above the floor (an overhead camera rig of a 10 x 7 m pitch; SSL: 4 m for 0.15 m robots)
ROBOT_TOP = 1.15             # m: the Booster T1's head (coverage is checked at this height)
OVERLAP = 0.40               # m: each camera sees this far past the halfway line at ROBOT_TOP
HALF = (5.3, 3.8)            # m: half extents of the area seen (pitch 5.0 x 3.5 + boards + margin)
TILE = (600, 800)            # (width, height) per tile: a half is taller (y) than it is long (x)
VISION_LATENCY_S = 0.04      # the images show the world this long ago (as SSL's vision)
NAME = "overhead"


def _fovy(half_x, half_y, w, h, depth):
    """The vertical field of view (deg) whose w x h picture covers +-half_x by +-half_y at `depth`."""
    return math.degrees(2 * math.atan(max(half_y / depth, half_x / depth * h / w)))


def _team_defs():
    """The cameras in the team frame: tile 0 over the own half (x < 0), tile 1 over the opponents' half."""
    w, h = TILE
    X, Y = HALF
    hx = X / 2 + OVERLAP / 2
    cx = X / 2 - OVERLAP / 2
    fovy = _fovy(hx, Y, w, h, CAMERA_HEIGHT - ROBOT_TOP)
    return [{"name": f"{NAME}{i}", "pos": [x, 0.0, CAMERA_HEIGHT], "lookat": [x, 0.0, 0.0], "up": [0.0, 1.0, 0.0],
             "fovy_deg": round(fovy, 4), "width": w, "height": h} for i, x in enumerate((-cx, cx))]


def camera_defs(team: str) -> list[dict]:
    """The team's cameras in the world frame (team A's frame is the world frame; team B's is the world turned by 180
    degrees about z)."""
    s = 1.0 if team == "A" else -1.0
    out = []
    for d in _team_defs():
        out.append({**d, "pos": [s * d["pos"][0], s * d["pos"][1], d["pos"][2]],
                    "lookat": [s * d["lookat"][0], s * d["lookat"][1], 0.0], "up": [0.0, s, 0.0]})
    return out


def focal_px(cam) -> float:
    return (cam["height"] / 2) / math.tan(math.radians(cam["fovy_deg"]) / 2)


def calibration(team: str = "A") -> list[dict]:
    """The cameras as the team sees them (team frame) with the pinhole parameters (game spec)."""
    out = []
    for d in _team_defs():
        out.append({**d, "focal_px": round(focal_px(d), 4), "principal_point_px": [d["width"] / 2, d["height"] / 2],
                    "metres_per_px_floor": round(CAMERA_HEIGHT / focal_px(d), 6)})
    return out


def _basis(cam):
    fwd = np.subtract(cam["lookat"], cam["pos"]).astype(float)
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, cam["up"])
    right /= np.linalg.norm(right)
    return right, np.cross(right, fwd), fwd


def project(cam, point):
    """Pixel (u, v) of a point (in the frame of `cam`), None behind the camera."""
    right, up, fwd = _basis(cam)
    d = np.subtract(point, cam["pos"])
    depth = float(d @ fwd)
    if depth <= 1e-9:
        return None
    f = focal_px(cam)
    return (cam["width"] / 2 + f * float(d @ right) / depth, cam["height"] / 2 - f * float(d @ up) / depth)


def ground_point(cam, u, v, z=0.0):
    """The point at height z seen at pixel (u, v) (the inverse of project on the plane z)."""
    right, up, fwd = _basis(cam)
    f = focal_px(cam)
    ray = fwd + right * (u - cam["width"] / 2) / f - up * (v - cam["height"] / 2) / f
    t = (z - cam["pos"][2]) / ray[2]
    return np.asarray(cam["pos"], float) + t * ray
