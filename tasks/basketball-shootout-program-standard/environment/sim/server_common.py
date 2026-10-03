"""Shared by the basketball services (single player and duel): the camera images and the spec's fixed parts."""
from __future__ import annotations

import base64
import io
import math

import numpy as np

import bball
import court

TILE = (640, 480)
STRIP_TILE = (400, 300)
STRIP_NOTE = ("2 rows x 4 columns, 400 x 300 tiles, 100 ms apart around the ball's closest approach to the hoop. "
              "Row 1: rim camera (side view of the hoop); row 2: your shooter_zoom camera.")
VIEW_NOTE = ("2 x 2 grid of 640 x 480 tiles. Top left: shooter_wide, top right: shooter_zoom (both on your shooter, "
             "looking along its heading, 8 deg up); bottom left: broadcast; bottom right: baseline (fixed). Camera "
             "poses and intrinsics: `game spec`.")


def _png(arr) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(arr).save(b, format="PNG")
    return b.getvalue()


def _label(img, text):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    dr.rectangle((0, 0, 8 + 6 * len(text), 16), fill=(0, 0, 0))
    dr.text((4, 3), text, fill=(255, 255, 255))
    return np.asarray(im)


def view_b64(g) -> str:
    w, h = TILE
    t = {c: _label(g.render_cam(c, w, h), c) for c in g.CAMS}
    img = np.concatenate([np.concatenate([t["shooter_wide"], t["shooter_zoom"]], 1),
                          np.concatenate([t["broadcast"], t["baseline"]], 1)], 0)
    return base64.b64encode(_png(img)).decode()


def strip_b64(g, res: dict) -> str | None:
    """The shot, 4 frames 100 ms apart around its closest approach to the hoop: rim camera (row 1), shooter zoom (row 2)."""
    snaps = g.last_snaps
    if not snaps:
        return None
    i0 = res.get("nearest_snap", len(snaps) - 1)
    if i0 is None or i0 < 0:
        i0 = len(snaps) - 1
    w, h = STRIP_TILE
    rows = []
    for cam in ("rim", "shooter_zoom"):
        tiles = []
        for off in (-20, -10, 0, 10):
            j = min(max(i0 + off, 0), len(snaps) - 1)
            tiles.append(_label(g.render_snap(snaps[j], cam, w, h), f"{cam}  {off * 10:+d} ms"))
        rows.append(np.concatenate(tiles, 1))
    return base64.b64encode(_png(np.concatenate(rows, 0))).decode()


def cam_spec():
    focal = lambda fovy, h: round((h / 2) / math.tan(math.radians(fovy) / 2), 3)  # noqa: E731
    cams = []
    for name, off in (("shooter_wide", [0, 0]), ("shooter_zoom", [TILE[0], 0])):
        fovy = court.SHOOTER_WIDE_FOVY if name == "shooter_wide" else court.SHOOTER_ZOOM_FOVY
        cams.append({"name": name, "mount": "on the shooter (moves with it)",
                     "pos_in_shooter_frame": list(court.SHOOTER_CAM_POS), "pitch_up_deg": court.SHOOTER_CAM_PITCH_DEG,
                     "orientation": f"optical axis along the shooter's heading (+x of its frame), pitched up "
                                    f"{court.SHOOTER_CAM_PITCH_DEG} deg, no roll; image right = -y of its frame",
                     "fovy_deg": fovy, "tile_px": list(TILE), "tile_offset_px": off, "focal_px": focal(fovy, TILE[1]),
                     "principal_point_px": [TILE[0] / 2, TILE[1] / 2]})
    for name, c in court.WORLD_CAMS.items():
        tile = TILE if name != "rim" else STRIP_TILE
        cams.append({"name": name, "mount": "fixed in the world", "pos": list(c["pos"]), "look_at": list(c["target"]),
                     "up_hint": [0, 0, 1], "fovy_deg": c["fovy"], "tile_px": list(tile),
                     "tile_offset_px": {"broadcast": [0, TILE[1]], "baseline": [TILE[0], TILE[1]]}.get(name),
                     "focal_px": focal(c["fovy"], tile[1]), "principal_point_px": [tile[0] / 2, tile[1] / 2]})
    return cams


def spec_common(n_shots: int) -> dict:
    """The parts of `game spec` both services share (the shot, release, ball, defender, court, cameras)."""
    return {
        "simulator": "mujoco 3.3.7", "robot": "franka-panda on a 1.0 m pedestal with a ball cup (launcher)",
        "shots": n_shots,
        "action": "{'type':'shoot','angle_deg','speed','spin_hz','yaw_deg'}",
        "shot": {"angle_deg": "release elevation above horizontal", "speed": "release speed m/s",
                 "spin_hz": "backspin in revolutions per second (negative = topspin)",
                 "yaw_deg": "release direction relative to the shooter's heading, + = to the left (counter-clockwise "
                            "from above)", "limits": bball.LIMITS},
        "release": {"point_in_shooter_frame": [round(bball.REL_FWD, 4), 0.0, round(bball.REL_H, 4)],
                    "note": "the release point turns with the yaw about the shooter's vertical axis: "
                            "shooter_pos + REL_FWD * (cos(h + yaw), sin(h + yaw)) at height REL_H, h = heading",
                    "throw_to_release_s": bball.THROW_RELEASE_S, "execution_scatter_1sigma": bball.NOISE},
        "ball": {"radius_m": court.BALL_R, "mass_kg": court.BALL_M, "drag": f"F = -{bball.C_D:.5f} |v| v (N)",
                 "drag_coef_n_s2_m2": round(bball.C_D, 7), "magnus": f"F = {bball.C_M:.6f} (omega x v) (N)",
                 "magnus_coef": round(bball.C_M, 8), "gravity": 9.81,
                 "spin_axis": "backspin: omega = 2 pi spin_hz (d x z), d = the horizontal release direction"},
        "defender": {"distance_m": f"min({bball.DEF_START_MAX}, {bball.DEF_START_FRAC} x your distance to the hoop) "
                                   "(shooter's axis to defender's axis)", "stands_on": "the line from you to the hoop",
                     "hands_top_m": 2.545, "moves": "never (it stands with its hands up)",
                     "blocked": "a ball whose first contact is the defender is blocked and does not count"},
        "scoring": "a make (the ball drops through the rim from above) counts 1, from any spot",
        "court": {"markings": "NBA court markings and equipment sizes", "hoop_centre": list(court.HOOP), "rim_inner_diameter_m": 2 * court.RIM_R_IN,
                  "rim_tube_diameter_m": 2 * court.RIM_TUBE,
                  "backboard": "1.83 x 1.07 m, front face 0.381 m behind the rim centre, bottom edge 2.90 m; "
                               "shooter's square 0.61 x 0.45 m above the rim",
                  "lines": {"baseline_y": court.BASELINE_Y, "free_throw_line_y": court.FT_Y, "lane_width_m": 4.88,
                            "free_throw_circle_radius_m": 1.8, "three_point_arc_radius_m": court.THREE_R,
                            "three_point_corner_x_m": court.THREE_CORNER_X,
                            "sidelines_x": [-court.HALF_W, court.HALF_W], "line_width_m": 0.05},
                  "frame": "hoop centre above (0, 0); the court is y < 0, the baseline y = +1.60; z up"},
        "cameras": cam_spec(),
        "not_given": "the shooter's position and heading and the spots' distances: judge them from the images",
    }


