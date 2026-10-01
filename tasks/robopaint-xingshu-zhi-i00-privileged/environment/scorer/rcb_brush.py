"""
rcb_brush.py — task-local tooling for the RoboPaint BRUSH tasks (families kaishu, lettering, acrylic, oil), where the stroke itself
matters: pressure, speed, direction, lift and (for a broad nib) the pen's orientation. Same scene, robot, recording and replay
machinery as rcb_paint.py (the line drawings): ManiSkill 3.0.1 / SAPIEN 3.0.3 (PhysX on the CPU), a Franka Panda holding a brush
whose TCP is the tip, the tip sampled after every physics step (100 Hz), strokes = continuous contacts, ink / paint fetched from
wells, a frozen instance, open-loop replay in fresh processes. Only the physics of the mark differs per medium.

Media (instance["medium"])
--------------------------
calligraphy : Chinese brush writing. The mark is the dynamic virtual brush of Wang, Chen, Deng, Hutchinson and Dellaert, "Robot
              Calligraphy using Pseudospectral Optimal Control in Conjunction with a Novel Dynamic Brush Model", IROS 2020 (arXiv
              1911.08002), re-implemented from the paper (no code was released): brush state (x, y, z, w, d, o, θ), width w and
              drag d follow the press depth z with inertia K_w = K_d = 0.02 (paper eqs. 6-7), the offset o between the handle's
              projection and the mark's root is o = min(Offset(z), |π(X) - root|) (eq. 8: the hairs stay put on the paper until the
              handle is Offset(z) away, then the root is dragged along), θ is the direction from the root to the handle projection
              (eqs. 1, 9); the footprint is a flat end of width w at the root with a quadratic (parabolic) drag tail of length d
              pointing away from the handle (Fig. 3). Width/Drag/Offset(z) are the paper's Fig. 4 fits to a real brush (read off the
              figure: see BRUSH_WANG). Black ink from an ink stone; a dip loads ink and restores the brush (w = d = o = 0), like the
              paper's ink-stone routine.
broad_nib   : Western broad-edge lettering: a chisel nib (a segment of the nib width along the tool's y axis) at the tip; the part
              of the edge below the paper writes.
pointed_pen : pointed-pen lettering (copperplate): a flexible split steel point; its tines spread apart along the tool's y axis
              as it is pressed (width from the press depth), so pressure makes the shades and a light touch the hairlines.
mypaint     : acrylic / oil painting with libmypaint 1.6.1 (ISC) brushes (mypaint-brushes 2.0.2, CC0) through a small C shim.

Scene      : ManiSkill's drawing-table scene with the MAIN sheet (the one that is scored) and a PRACTICE sheet on the robot's right
             (-y) for test strokes (never scored, never counted), a plate on the robot's left (+y) with the ink stone / paint wells,
             cameras: canvas_cam (overhead, main sheet), practice_cam (overhead, practice sheet), scene_cam, side_cam.
Target     : the picture target.png (1024 px covering the main sheet) next to instance.json; its pixels enter instance_sha.
Trajectory : (T, 7) absolute joint-position targets panda_joint1..7 (rad), one row per 20 Hz control step, ManiSkill pd_joint_pos.
Score      : Session.score() = the grader's metrics of the main sheet (+ success, final_reward). Where the instance has no scoring
             data (the agent's copy), score() asks the scoring service (rcb_scorer.py in its own container): it sends the actions
             executed since the last reset, the service replays them on its copy and returns the metrics only (agent_metrics()).

CLI
---
  python rcb_brush.py replay  --instance instance.json --traj traj.npz [--video replay.mp4] [--canvas-out canvas.png]
  python rcb_brush.py render  --instance instance.json --traj traj.npz --out replay.mp4
  python rcb_brush.py run-oracle --instance instance.json --code oracle.py --out traj.npz
  python rcb_brush.py selftest --instance instance.json [--traj traj.npz]
  (graders only, with rcb_brush_score.py: make-instance, make-agent-instance, score)

Python (what the unlimited agent gets)
--------------------------------------
  from rcb_brush import Session
  s = Session(instance="/app/instance.json")
  p = s.primitives()                  # thin wrappers of the low-level action: move_tip, move_joints, hold, set_joint_targets, ik, fk
  s.tip_pose(); s.joint_positions(); s.press_depth(); s.pen_down(); s.wells(); s.sheet_facts()
  s.canvas(); s.canvas("practice"); s.ink(); s.score(); s.strokes(); s.brush_state()     # privileged
  s.target_image()                    # the target picture (target.png)
  s.render_frame("canvas_cam"); s.render_grid(); s.render_video(actions, path)
  s.record_start(); ...; a = s.record_stop(); s.replay(a); s.save_trajectory(a, path)
  s.camera_info(); s.render_depth("canvas_cam")                  # calibration + mounting; z-depth (m) pixel-aligned with render_frame
  s.robot_spec(); s.kinematics_spec(); s.kinematics(req)         # the robot's spec sheet; stateless FK / IK (= the limited /kinematics)
  s.joint_velocities(); s.joint_efforts()                        # measured joint velocities; PD drive-effort estimate
"""
from __future__ import annotations

import os
os.environ.setdefault("PYTHONUNBUFFERED", "1")
import argparse
import hashlib
import json
import math
import sys
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any, Callable

import numpy as np

warnings.filterwarnings("ignore")
TORCH_THREADS = int(os.environ.get("RCB_TORCH_THREADS", "4"))
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
SESSION_LOG_KEEP = os.environ.get("RCB_SESSION_LOG_KEEP", "/logs/agent/rcb_session_log.jsonl")

# --------------------------------------------------------------------------- constants (frozen into instance.json)
CONTROL_HZ = 20                      # ManiSkill's drawing scene: control 20 Hz, sim 100 Hz
SIM_HZ = 100
ACTION_DIM = 7
MAX_STEPS = 72_000                   # runaway guard only (1 h of simulated time)
MAX_VIDEO_FRAMES = int(os.environ.get("RCB_MAX_VIDEO_FRAMES", "600"))   # replay videos subsample long trajectories to at most this many frames (P/3)
PAPER_SIDE_M = math.sqrt(0.254 * 0.2032)   # 0.2272 m: the RoboPaint paper (FRIDA's stroke-library canvas as a square)
SHEET_PX = 1024                      # main sheet raster: 0.2219 mm / px
PAPER_CENTER = (-0.10, 0.0)          # world xy of the main sheet's centre (the drawing board's centre)
PAPER_Z = 0.02                       # paper surface = the board top
PRACTICE_CENTER = (-0.10, -0.1856)   # practice sheet on the robot's right, 22 mm from the main sheet
PRACTICE_PX = (1024, 448)            # rows (along x) x cols (along y) at the main sheet's pixel size: 227.2 x 99.4 mm
ROBOT_BASE = (-0.615, 0.0, 0.0)
REST_QPOS = (0.0, math.pi / 8, 0.0, -math.pi * 5 / 8, 0.0, math.pi * 3 / 4, math.pi / 4)   # PandaStick "rest" keyframe
PLATE_CENTER = (-0.10, 0.150)        # the ink / paint plate on the robot's left (+y), as in the line-drawing tasks
PLATE_HALF = (0.100, 0.022, 0.003)   # 200 x 44 x 6 mm, top z = 0.026, with collision
MAX_TIP_SPEED = 0.25                 # m/s, standard-mode ee_pose rows
TOL_MM = 1.0                         # boundary tolerance of the score
ENV_ID = "RCB-BrushCanvas-v1"
VIDEO_CAMERAS = ("canvas_cam", "practice_cam", "scene_cam", "side_cam")
ACTION_LAYOUT = ("7 entries per control step (20 Hz): panda_joint1..7 absolute joint-position targets (rad), ManiSkill pd_joint_pos "
                 "(PD stiffness 1e3, damping 1e2, gravity compensated). World frame: z up, table top z = 0, robot base at "
                 "(-0.615, 0, 0), x forward (away from the base). Quaternions are WXYZ.")
JOINT_NAMES = tuple(f"panda_joint{i}" for i in range(1, ACTION_DIM + 1))
TOOL_FRAME = "tip"                   # the tool frame of the kinematics / robot spec: the brush tip = the TCP (link panda_hand_tcp)
IK_DEFAULTS = {"tol_pos_m": 0.001, "tol_rot_rad": 0.01, "max_iters": 200}
PAPER_RGB = (0.972, 0.957, 0.925)    # warm white (xuan paper look); the scored quantity is the ink coverage, not the colour
INK_RGB = (0.075, 0.072, 0.080)      # Chinese ink (near black)

# Wang et al. 2020, Fig. 4 (width, drag and offset of the brush mark vs the brush height z, all in cm; the three panels share the
# y axis). Read off the figure's fitted curves (m3/refs/wang2020_fig4_fits.png, pixel positions of the curve end points and the
# offset maximum): Width(z) = -0.030 + 1.187 z (line through (0, -0.03) and (1.5, 1.75)); Drag(z) = 0.138 + 1.075 z (through
# (0, 0.138) and (1.5, 1.75)); Offset(z) = 1.115 - 0.967 (z - 1.091)^2 (a parabola through (0, -0.036), its maximum 1.115 at
# z = 1.091 and (1.5, 0.953)). The paper fits "a polynomial relationship" but prints no coefficients; the calibration range is
# z in [0, 1.5] cm, beyond which we saturate (the hairs are fully spread). Negative values are clamped to 0. K_w = K_d = 0.02 is
# the paper's value ("we have used 0.02"); the paper does not state its sampling interval, we apply it per 100 Hz physics step.
BRUSH_WANG = {"model": "wang2020", "width_cm": [1.187, -0.030], "drag_cm": [1.075, 0.138],
              "offset_cm": [-0.967, 2 * 0.967 * 1.091, 1.115 - 0.967 * 1.091 ** 2],
              "z_max_cm": 1.5, "k_w": 0.02, "k_d": 0.02, "theta_eps_m": 1e-4, "theta_eps_contact_m": 1e-3,
              "bristle_m": 0.030, "bristle_r": 0.0045, "substep_m": 2.5e-4, "substep_deg": 3.0}


# Broad-edge (chisel) nib (family B): a rigid steel nib whose writing edge is a straight segment of the nib width along the tool's
# y axis (at the start pose: along the writing line, pen angle 0), `nib_thick_m` thick (the hairline). The part of the edge below the
# paper surface writes (a tilted pen writes with one corner); the mark is the edge swept along the tip's path. No width change with
# pressure (a rigid nib); `bristle_m` = the collision-free nib length (the holder stops a press of 6 mm). CalliRewrite's
# chisel-tip marker (a rotated rectangle) is the simpler reference; here the edge comes from the robot's full tool pose.
BRUSH_NIB = {"model": "broad_nib", "nib_width_m": 0.004, "nib_thick_m": 0.0004, "bristle_m": 0.006, "bristle_r": 0.0021,
             "substep_m": 2.0e-4, "substep_deg": 2.0}


# Pointed flexible pen (copperplate, family lettering): a split steel point whose two tines spread apart when it is pressed. The
# spread is perpendicular to the slit, along the tool's y axis (at the start pose: along the writing line). Unpressed (a press of
# up to flex_start_m = 1 mm, a light touch: the dead zone keeps a position-controlled arm's hairlines in contact) the point writes a hairline of hairline_m; deeper, the spread grows linearly with the press depth (a
# cantilever spring: tine spread proportional to the point's deflection) up to max_width_m at full_flex_m, and stays there (the
# tines are fully open). The mark = the ink between the tines: the tine segment (tip +- (w - hairline)/2 along the y axis,
# projected on the paper) swept along the path, each footprint a capsule of the hairline's thickness; so a pressed stroke is wide
# only where it moves across the spread axis (a downstroke pulled along the slit) and a sideways move stays thin, as with a real
# point. Real flexible nibs (e.g. Leonardt Principal, Hunt 101, Gillott 303) write ~0.1-0.2 mm hairlines and open to ~1-2 mm;
# the hairline here is 0.4 mm because the scored raster is 0.22 mm per pixel (a thinner line would not reach half a pixel's
# coverage everywhere), the full shade 2.0 mm (a very flexible nib at full flex), the press scale a few millimetres so that a
# position-controlled arm can set it. bristle_m = the collision-free point length (the holder stops a press of 6 mm).
BRUSH_POINTED = {"model": "pointed_pen", "hairline_m": 0.0004, "max_width_m": 0.0020, "flex_start_m": 0.0010, "full_flex_m": 0.0035,
                 "bristle_m": 0.006, "bristle_r": 0.0008, "visual_w_m": 0.0012, "substep_m": 2.0e-4, "substep_deg": 2.0}


# Oil / acrylic (family C): libmypaint 1.6.1 (ISC; built in the image with a one-line determinism patch, malloc -> calloc of the
# brush) through the rcb_mypaint C shim (a fixed tiled surface implementing MyPaintSurface2), with a mypaint-brushes 2.0.2 preset
# (CC0; the .myb text is frozen into the instance). Per physics step the tip over a sheet is one motion event: position (px),
# pressure = press depth / full_press_m, tilt from the brush axis, barrel rotation from the tool's yaw, dtime = 0.01 s; the
# engine derives speed, direction and its random input itself. A dip loads the well's colour and a fresh brush (smudge state and
# RNG restart). radius_log_offset scales the preset's dabs to the paper (0.22 mm / px).
BRUSH_MYPAINT = {"model": "mypaint", "preset": "tanda/oil-01-paint", "radius_log_offset": 1.0, "full_press_m": 0.015,
                 "bristle_m": 0.015, "bristle_r": 0.004, "libmypaint": "1.6.1 + calloc patch", "mypaint_brushes": "2.0.2"}
MYPAINT_LIB = os.environ.get("RCB_MYPAINT_LIB", "/opt/mypaint/lib/librcbmypaint.so")
MYPAINT_BRUSHES = os.environ.get("RCB_MYPAINT_BRUSHES", "/opt/mypaint/brushes")


def _log(*a: Any) -> None:
    print("[rcb]", *a, file=sys.stderr, flush=True)


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    line = json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n"
    for path, need_dir in ((SESSION_LOG, False), (SESSION_LOG_KEEP, True)):
        if not path or (need_dir and not os.path.isdir(os.path.dirname(path))):
            continue
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as f:
                f.write(line)
        except OSError:
            pass


class PrimitiveError(RuntimeError):
    """A primitive could not be executed (the episode is still alive unless said otherwise)."""


def sha16(*chunks: bytes) -> str:
    h = hashlib.sha1()
    for c in chunks:
        h.update(c)
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------- small quaternion helpers (wxyz)
def quat_mul(a, b) -> np.ndarray:
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_to_mat(q) -> np.ndarray:
    w, x, y, z = np.asarray(q, np.float64) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def quat_slerp(a, b, t: float) -> np.ndarray:
    a = np.asarray(a, np.float64); b = np.asarray(b, np.float64)
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + t * (b - a)
        return q / np.linalg.norm(q)
    th = math.acos(min(1.0, d))
    return (math.sin((1 - t) * th) * a + math.sin(t * th) * b) / math.sin(th)


def hex_rgb(h: str) -> tuple[float, float, float]:
    h = h.strip().lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# --------------------------------------------------------------------------- sheets (paper frames)
class Sheet:
    """A rectangular paper sheet lying flat on the board. Raster: rows along -x (row 0 = the far edge, +x), columns along -y
    (column 0 = the left edge seen from the robot's base, +y); pixel centres at integer (col u, row v). Paper millimetres: X to the
    robot's right (= col direction), Y towards the robot (= row direction), origin at the far-left corner."""
    def __init__(self, name: str, center, rows: int, cols: int, px_m: float, z: float = PAPER_Z):
        self.name, self.center = name, (float(center[0]), float(center[1]))
        self.rows, self.cols, self.px_m, self.z = int(rows), int(cols), float(px_m), float(z)
        self.size_x, self.size_y = self.rows * self.px_m, self.cols * self.px_m          # extent along world x / y (m)
        self.x_far, self.y_left = self.center[0] + self.size_x / 2, self.center[1] + self.size_y / 2

    def world_to_px(self, x, y):
        return (self.y_left - np.asarray(y, np.float64)) / self.px_m - 0.5, (self.x_far - np.asarray(x, np.float64)) / self.px_m - 0.5

    def px_to_world(self, u, v):
        return self.x_far - (np.asarray(v, np.float64) + 0.5) * self.px_m, self.y_left - (np.asarray(u, np.float64) + 0.5) * self.px_m

    def mm_to_world(self, X, Y):
        return self.x_far - np.asarray(Y, np.float64) / 1000.0, self.y_left - np.asarray(X, np.float64) / 1000.0

    def world_to_mm(self, x, y):
        return (self.y_left - np.asarray(y, np.float64)) * 1000.0, (self.x_far - np.asarray(x, np.float64)) * 1000.0

    def mm_to_px(self, X, Y):
        return np.asarray(X, np.float64) / 1000.0 / self.px_m - 0.5, np.asarray(Y, np.float64) / 1000.0 / self.px_m - 0.5

    def inside(self, x, y) -> bool:
        return abs(x - self.center[0]) <= self.size_x / 2 and abs(y - self.center[1]) <= self.size_y / 2

    def facts(self) -> dict:
        return {"name": self.name, "center_xy": list(self.center), "surface_z": self.z, "size_m": [round(self.size_x, 6), round(self.size_y, 6)],
                "raster_px": [self.rows, self.cols], "mm_per_px": round(self.px_m * 1000, 6)}


def sheets_from_inst(inst: dict) -> dict[str, Sheet]:
    out = {}
    for s in inst["sheets"]:
        out[s["name"]] = Sheet(s["name"], s["center_xy"], s["rows"], s["cols"], s["px_m"], s["z"])
    return out


# --------------------------------------------------------------------------- wells (ink stone / paints)
class Wells:
    def __init__(self, d: dict):
        self.d = d
        self.names = [w["name"] for w in d["wells"]]
        self.rgb = np.asarray([w["rgb"] for w in d["wells"]], np.float64)
        self.xy = np.asarray([w["center_xy"] for w in d["wells"]], np.float64)
        self.r = np.asarray([w["radius_m"] for w in d["wells"]], np.float64)
        self.surface_z = float(d["surface_z"])

    def well_at(self, x: float, y: float, z: float) -> int | None:
        if z >= self.surface_z:
            return None
        dd = np.hypot(self.xy[:, 0] - x, self.xy[:, 1] - y)
        i = int(np.argmin(dd))
        return i if dd[i] < self.r[i] else None


def build_wells(wells: list[tuple[str, str]], radius_m: float, plate_center=PLATE_CENTER, spacing=0.038, depth_m=0.002,
                rule: str = "", rows: int = 1, plate_half=PLATE_HALF) -> dict:
    """Wells on the plate, laid out in `rows` rows (along x, `spacing` apart; the rows `spacing` apart along y, first row nearest to
    the paper)."""
    n = len(wells)
    per = int(math.ceil(n / rows))
    top = PAPER_Z + 2 * plate_half[2]
    ws = []
    for i, (nm, hx) in enumerate(wells):
        r, c = divmod(i, per)
        m = min(per, n - r * per)
        ws.append({"name": nm, "hex": hx, "rgb": [round(v, 6) for v in hex_rgb(hx)],
                   "center_xy": [round(plate_center[0] + (c - (m - 1) / 2) * spacing, 6), round(plate_center[1] + (r - (rows - 1) / 2) * spacing, 6)],
                   "radius_m": radius_m})
    return {"plate_center_xy": list(plate_center), "plate_half_size": list(plate_half), "plate_top_z": round(top, 6),
            "surface_z": round(top + depth_m, 6), "wells": ws, "rule": rule}


# --------------------------------------------------------------------------- the target as a picture; the metrics the agent gets
AGENT_METRICS_REGISTER = ("register_dx_mm", "register_dy_mm", "register_shift_mm", "register_at_edge")   # the alignment (snapshot 21)
AGENT_METRICS_INK = ("success", "final_reward", "iou", "boundary_precision", "boundary_recall", "boundary_f", "ink_precision",
                     "ink_recall", "min_stroke_coverage", "mean_stroke_coverage", "stray_frac", "missing_frac", "ink_area_mm2", "n_strokes",
                     "n_practice_strokes", "n_dry_strokes", "max_strokes", "stroke_count_ok", "iou_unregistered") + AGENT_METRICS_REGISTER
AGENT_METRICS_PAINT = ("success", "final_reward", "de_mean", "de_p90", "de_bad_frac", "de_mean_sheet", "ssim_L", "paint_iou",
                       "paint_area_mm2", "n_strokes", "n_practice_strokes", "n_dry_strokes", "max_strokes", "stroke_count_ok",
                       "de_mean_coarse", "ssim_L_fine", "edge_corr", "region_cov_min", "region_cov_mean",
                       "de_mean_unregistered") + AGENT_METRICS_REGISTER
SCORER_URLS = ("http://scorer:8001", "http://localhost:8001")              # the privileged mode's scoring service (compose `scorer`)


def agent_metrics(m: dict) -> dict:
    """The part of the grader's metrics that the scoring service returns to the agent: the rule's quantities and the continuous
    scores (no per-stroke, ordering or target-size quantities)."""
    keep = AGENT_METRICS_PAINT if "de_mean" in m else AGENT_METRICS_INK
    return {k: v for k, v in m.items() if k in keep}


class TargetPicture:
    """The target as everyone has it: the picture target.png (RGB, covering the main sheet exactly)."""
    def __init__(self, path: str | Path):
        from PIL import Image
        self.path = str(path)
        self.rgb = np.asarray(Image.open(self.path).convert("RGB"), np.uint8)
        self.sha = sha16(self.rgb.tobytes())

    def image(self) -> np.ndarray:
        return self.rgb.copy()


# --------------------------------------------------------------------------- the calligraphy brush (Wang et al. 2020)
class WangBrush:
    """Dynamic virtual brush of Wang, Chen, Deng, Hutchinson, Dellaert (IROS 2020, arXiv 1911.08002, Sec. IV-B), re-implemented from
    the paper. State (x, y, z, w, d, o, θ) + the mark's root. One update per 100 Hz physics step from the tip (= the end effector X;
    the brush is held vertically, so π(X) is the tip's xy) and the press depth z (m, > 0 below the paper):
        w <- K_w w + (1 - K_w) Width(z)          d <- K_d d + (1 - K_d) Drag(z)                           (eqs. 6, 7)
        o <- min(Offset(z), |π(X) - root|)        the hairs stay put on the paper until the handle is Offset(z) away   (eq. 8)
        θ <- direction from the root to π(X)      root <- π(X) - o V(θ)                                     (eqs. 1, 9)
    Width/Drag/Offset(z) = the Fig. 4 fits (BRUSH_WANG), 0 when the tip is not below the paper (the hairs straighten: o = 0, the
    root snaps to the handle). Gaps filled here (documented in DESIGN): eq. 9 as printed (V^-1(root - π(X))) has the opposite sign of
    eq. 1; we follow eq. 1 and Fig. 3 (the flat end faces the handle, the drag tail points away from it). θ keeps its value while
    |π(X) - root| <= theta_eps: 0.1 mm in the air, where the root follows the handle, so θ becomes the direction of travel, which
    gives the paper's "θ initialised to the initial trajectory direction" at the next touch-down; 1 mm in contact, because eq. 9 is
    ill-conditioned while the root is under the handle: pressing straight down on a real (jittering) robot made θ spin and the drag
    tail sweep a disc at every touch-down (measured, DESIGN §17). A dip restores the brush (w = d = o = 0, θ unset), as the paper's
    ink-stone routine does."""
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.wc, self.dc, self.oc = (np.asarray(cfg[k], np.float64) for k in ("width_cm", "drag_cm", "offset_cm"))
        self.zmax_m = float(cfg["z_max_cm"]) / 100.0
        self.kw, self.kd, self.eps = float(cfg["k_w"]), float(cfg["k_d"]), float(cfg["theta_eps_m"])
        self.eps_contact = float(cfg.get("theta_eps_contact_m", cfg["theta_eps_m"]))
        self.restore()

    def restore(self) -> None:
        self.w = 0.0; self.d = 0.0; self.o = 0.0; self.theta: float | None = None; self.root: tuple[float, float] | None = None

    def _cm(self, c: np.ndarray, z_m: float) -> float:
        return max(0.0, float(np.polyval(c, min(z_m, self.zmax_m) * 100.0)) / 100.0)

    def width_of(self, z_m: float) -> float:
        return self._cm(self.wc, z_m) if z_m > 0 else 0.0

    def drag_of(self, z_m: float) -> float:
        return self._cm(self.dc, z_m) if z_m > 0 else 0.0

    def offset_of(self, z_m: float) -> float:
        return self._cm(self.oc, z_m) if z_m > 0 else 0.0

    def step(self, x: float, y: float, z_m: float) -> None:
        W, D, O = self.width_of(z_m), self.drag_of(z_m), self.offset_of(z_m)
        self.w = self.kw * self.w + (1.0 - self.kw) * W
        self.d = self.kd * self.d + (1.0 - self.kd) * D
        if self.root is None:
            self.root = (x, y)
        vx, vy = x - self.root[0], y - self.root[1]
        L = math.hypot(vx, vy)
        o = min(O, L)
        if L > (self.eps_contact if z_m > 0 else self.eps):
            self.theta = math.atan2(vy, vx)
        if L > 0.0:
            k = o / L
            self.root = (x - vx * k, y - vy * k)
        self.o = o

    def state(self) -> dict:
        return {"w_m": self.w, "d_m": self.d, "o_m": self.o, "theta_rad": self.theta, "root_xy": list(self.root) if self.root else None}


def _wang_footprint(sheet: Sheet, rx: float, ry: float, th: float, w: float, d: float):
    """Anti-aliased coverage of one mark on the sheet raster: flat end of width w at the root (rx, ry), facing the handle
    (direction th), and the parabolic drag tail s <= d (1 - 4 t^2 / w^2) of length d pointing away from it (Fig. 3). Coverage from
    an approximate signed distance (min of the flat end and the parabola's first-order distance), 1 px wide edge.
    -> (r0, c0, alpha (h, w) float32) or None."""
    if w <= 1e-6:
        return None
    ex, ey = math.cos(th), math.sin(th); nx, ny = -ey, ex
    hw = w / 2
    xs = [rx + hw * nx, rx - hw * nx, rx - d * ex + hw * nx, rx - d * ex - hw * nx]
    ys = [ry + hw * ny, ry - hw * ny, ry - d * ey + hw * ny, ry - d * ey - hw * ny]
    us, vs = sheet.world_to_px(np.asarray(xs), np.asarray(ys))
    c0 = max(0, int(math.floor(us.min())) - 1); c1 = min(sheet.cols - 1, int(math.ceil(us.max())) + 1)
    r0 = max(0, int(math.floor(vs.min())) - 1); r1 = min(sheet.rows - 1, int(math.ceil(vs.max())) + 1)
    if c1 < c0 or r1 < r0:
        return None
    px = sheet.px_m
    X = sheet.x_far - (np.arange(r0, r1 + 1, dtype=np.float64) + 0.5) * px          # (h,) world x of the pixel rows
    Y = sheet.y_left - (np.arange(c0, c1 + 1, dtype=np.float64) + 0.5) * px         # (w,) world y of the pixel columns
    qx = X[:, None] - rx; qy = Y[None, :] - ry
    s = -(qx * ex + qy * ey)                                                         # along the tail (>= 0 inside)
    t = qx * nx + qy * ny                                                            # across
    f_par = d * (1.0 - 4.0 * t * t / (w * w)) - s
    g = np.sqrt(1.0 + (8.0 * d * t / (w * w)) ** 2)
    sd = np.minimum(s, f_par / g)
    a = np.clip(sd / px + 0.5, 0.0, 1.0).astype(np.float32)
    return r0, c0, a


class CalligraphyPainter:
    """Tip samples -> brush dynamics -> ink on the sheets. One stroke = one continuous contact of the tip with a sheet (tip over the
    sheet and below its surface). The brush starts dry; a tip in the ink stone (inside its circle, below the ink surface) loads ink
    and restores the brush. A stroke is inked iff the brush carried ink when it touched the sheet (no depletion). Marks: every
    physics step's footprint plus interpolated footprints in between (root moved <= substep_m, θ turned <= substep_deg), max-
    composited (opaque ink). Deterministic: pure float64 arithmetic in a fixed order."""
    def __init__(self, brush_cfg: dict, sheets: dict[str, Sheet], wells: Wells):
        self.cfg, self.sheets, self.wells = brush_cfg, sheets, wells
        self.reset()

    def _new_brush(self):
        return WangBrush(self.cfg)

    def reset(self) -> None:
        self.brush = self._new_brush()
        self.ink = {n: np.zeros((s.rows, s.cols), np.float32) for n, s in self.sheets.items()}
        self.strokes: list[dict] = []
        self.cur: dict | None = None
        self.loaded = False
        self.in_well: int | None = None
        self.version = 0
        self.n_steps = 0
        self.stats = {"samples": 0, "contact_samples": 0, "max_press_m": 0.0, "max_tilt_deg_in_contact": 0.0, "max_speed_in_contact_mps": 0.0,
                      "handle_contact_samples": 0, "n_dips": 0, "dry_strokes": 0}
        self._prev_xy = None

    def _sheet_at(self, x: float, y: float) -> Sheet | None:
        for s in self.sheets.values():
            if s.inside(x, y):
                return s
        return None

    def sample(self, p, R) -> None:
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        st = self.stats; st["samples"] += 1
        w = self.wells.well_at(x, y, z)
        if w is not None:
            if w != self.in_well:
                st["n_dips"] += 1
            self.loaded = True
            self.brush.restore()
            self.version += 1
        self.in_well = w
        sheet = self._sheet_at(x, y)
        zp = PAPER_Z - z                                   # press depth on the board / paper (the sheets lie on the board)
        if w is not None or (sheet is None and self.wells.d["plate_center_xy"] and abs(x - self.wells.d["plate_center_xy"][0]) <= self.wells.d["plate_half_size"][0]
                             and abs(y - self.wells.d["plate_center_xy"][1]) <= self.wells.d["plate_half_size"][1]):
            zp = 0.0                                       # over the ink plate: the hairs do not bend against the board
        self.brush.step(x, y, zp)
        contact = sheet is not None and z < sheet.z
        if contact:
            st["contact_samples"] += 1
            st["max_press_m"] = max(st["max_press_m"], sheet.z - z)
            if sheet.z - z > float(self.cfg["bristle_m"]) - 0.0005:
                st["handle_contact_samples"] += 1
            axis = np.asarray(R, np.float64)[:, 2]
            st["max_tilt_deg_in_contact"] = max(st["max_tilt_deg_in_contact"], math.degrees(math.acos(max(-1.0, min(1.0, -float(axis[2]))))))
            if self._prev_xy is not None:
                st["max_speed_in_contact_mps"] = max(st["max_speed_in_contact_mps"], math.hypot(x - self._prev_xy[0], y - self._prev_xy[1]) * SIM_HZ)
            if self.cur is not None and self.cur["sheet"] != sheet.name:
                self._end_stroke()
            if self.cur is None:
                self._start_stroke(sheet)
            self._add(x, y, sheet.z - z)
        elif self.cur is not None:
            self._end_stroke()
        self._prev_xy = (x, y)
        self.n_steps += 1

    # ---- strokes
    def _start_stroke(self, sheet: Sheet) -> None:
        if not self.loaded:
            self.stats["dry_strokes"] += 1
        self.cur = {"sheet": sheet.name, "inked": self.loaded, "start_sample": self.stats["samples"] - 1, "samples": [],
                    "acc": np.zeros((sheet.rows, sheet.cols), np.float32) if self.loaded else None, "bbox": None, "last_fp": None}
        self.version += 1

    def _add(self, x: float, y: float, zp: float) -> None:
        b = self.brush; c = self.cur
        th = b.theta if b.theta is not None else 0.0
        c["samples"].append((x, y, zp, b.w, b.d, b.o, th, b.root[0], b.root[1]))
        if not c["inked"]:
            return
        fp = (b.root[0], b.root[1], th, b.w, b.d)
        prev = c["last_fp"]
        if prev is None:
            fps = [fp]
        else:
            dth = (fp[2] - prev[2] + math.pi) % (2 * math.pi) - math.pi
            n = max(1, int(math.ceil(max(math.hypot(fp[0] - prev[0], fp[1] - prev[1]) / float(self.cfg["substep_m"]),
                                         abs(math.degrees(dth)) / float(self.cfg["substep_deg"])))))
            fps = [(prev[0] + (fp[0] - prev[0]) * k / n, prev[1] + (fp[1] - prev[1]) * k / n, prev[2] + dth * k / n,
                    prev[3] + (fp[3] - prev[3]) * k / n, prev[4] + (fp[4] - prev[4]) * k / n) for k in range(1, n + 1)]
        c["last_fp"] = fp
        sheet = self.sheets[c["sheet"]]
        for f in fps:
            r = _wang_footprint(sheet, *f)
            if r is None:
                continue
            r0, c0, a = r
            sl = (slice(r0, r0 + a.shape[0]), slice(c0, c0 + a.shape[1]))
            np.maximum(c["acc"][sl], a, out=c["acc"][sl])
            bb = (r0, r0 + a.shape[0], c0, c0 + a.shape[1])
            c["bbox"] = bb if c["bbox"] is None else (min(c["bbox"][0], bb[0]), max(c["bbox"][1], bb[1]), min(c["bbox"][2], bb[2]), max(c["bbox"][3], bb[3]))
        self.version += 1

    def _end_stroke(self) -> None:
        c = self.cur
        if c is None:
            return
        rec = {"sheet": c["sheet"], "inked": bool(c["inked"]), "start_sample": c["start_sample"],
               "samples": np.asarray(c["samples"], np.float64).reshape(-1, 9)}
        P = rec["samples"]
        rec["length_mm"] = float(np.sum(np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1]))) * 1000) if len(P) > 1 else 0.0
        rec["max_press_mm"] = float(P[:, 2].max() * 1000) if len(P) else 0.0
        if c["inked"] and c["bbox"] is not None:
            r0, r1, c0, c1 = c["bbox"]
            sub = c["acc"][r0:r1, c0:c1]
            ink = self.ink[c["sheet"]]
            np.maximum(ink[r0:r1, c0:c1], sub, out=ink[r0:r1, c0:c1])
            rec["mask_bbox"] = (r0, c0); rec["mask"] = np.round(sub * 255).astype(np.uint8)
        else:
            rec["mask_bbox"] = (0, 0); rec["mask"] = np.zeros((0, 0), np.uint8)
        self.strokes.append(rec)
        self.cur = None
        self.version += 1

    def finish(self) -> None:
        self._end_stroke()

    def display_ink(self, sheet: str = "main") -> np.ndarray:
        """Ink coverage of a sheet including the stroke in progress (the committed ink is not modified)."""
        c = self.cur
        if c is None or not c["inked"] or c["sheet"] != sheet or c["bbox"] is None:
            return self.ink[sheet]
        out = self.ink[sheet].copy()
        r0, r1, c0, c1 = c["bbox"]
        np.maximum(out[r0:r1, c0:c1], c["acc"][r0:r1, c0:c1], out=out[r0:r1, c0:c1])
        return out

    def display(self, sheet: str = "main") -> np.ndarray:
        a = self.display_ink(sheet)[..., None]
        return np.asarray(PAPER_RGB, np.float32) * (1 - a) + np.asarray(INK_RGB, np.float32) * a

    def brush_rgb(self):
        return INK_RGB if self.loaded else None

    def brush_state(self) -> dict:
        return {**self.brush.state(), "loaded": self.loaded}

    def state_bytes(self) -> bytes:
        b = self.brush
        vals = [b.w, b.d, b.o, -9.0 if b.theta is None else b.theta, *(b.root if b.root else (-9.0, -9.0)), float(self.loaded)]
        return np.asarray(vals, np.float64).tobytes()


def _segment_footprint(sheet: Sheet, x0: float, y0: float, x1: float, y1: float, thick: float):
    """Anti-aliased coverage of a thin rectangle: the segment (x0, y0)-(x1, y1) (world) with thickness `thick` (square ends, no
    extension past the end points). -> (r0, c0, alpha) or None."""
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 1e-7 and thick < 1e-7:
        return None
    ex, ey = ((x1 - x0) / L, (y1 - y0) / L) if L >= 1e-7 else (1.0, 0.0)
    nx, ny = -ey, ex
    ht = thick / 2
    xs = [x0 + ht * nx, x0 - ht * nx, x1 + ht * nx, x1 - ht * nx]; ys = [y0 + ht * ny, y0 - ht * ny, y1 + ht * ny, y1 - ht * ny]
    us, vs = sheet.world_to_px(np.asarray(xs), np.asarray(ys))
    c0 = max(0, int(math.floor(us.min())) - 1); c1 = min(sheet.cols - 1, int(math.ceil(us.max())) + 1)
    r0 = max(0, int(math.floor(vs.min())) - 1); r1 = min(sheet.rows - 1, int(math.ceil(vs.max())) + 1)
    if c1 < c0 or r1 < r0:
        return None
    px = sheet.px_m
    X = sheet.x_far - (np.arange(r0, r1 + 1, dtype=np.float64) + 0.5) * px
    Y = sheet.y_left - (np.arange(c0, c1 + 1, dtype=np.float64) + 0.5) * px
    qx = X[:, None] - (x0 + x1) / 2; qy = Y[None, :] - (y0 + y1) / 2
    a_ = L / 2 - np.abs(qx * ex + qy * ey)                  # distance inside along the edge
    b_ = ht - np.abs(qx * nx + qy * ny)                     # distance inside across
    sd = np.minimum(a_, b_)
    return r0, c0, np.clip(sd / px + 0.5, 0.0, 1.0).astype(np.float32)


class NibPainter(CalligraphyPainter):
    """Broad-edge nib (BRUSH_NIB): per physics step the contacting part of the nib's edge (the segment tip +- w/2 along the tool's y
    axis, clipped to z < the sheet's surface), swept between steps by interpolated sub-steps; max-composited opaque ink. Same stroke,
    dip and sheet bookkeeping as the calligraphy painter; a dip only loads ink (a steel nib has no state to restore)."""
    def _new_brush(self):
        self._edge = None
        return None

    def sample(self, p, R) -> None:
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        st = self.stats; st["samples"] += 1
        w = self.wells.well_at(x, y, z)
        if w is not None:
            if w != self.in_well:
                st["n_dips"] += 1
            self.loaded = True; self.version += 1
        self.in_well = w
        Rm = np.asarray(R, np.float64)
        e = Rm[:, 1]; hw = float(self.cfg["nib_width_m"]) / 2
        a, b = np.array([x, y, z]) - hw * e, np.array([x, y, z]) + hw * e
        self._edge = (a, b)
        sheet = self._sheet_at(x, y)
        contact = sheet is not None and min(a[2], b[2]) < sheet.z
        if contact:
            st["contact_samples"] += 1
            st["max_press_m"] = max(st["max_press_m"], sheet.z - z)
            if sheet.z - z > float(self.cfg["bristle_m"]) - 0.0005:
                st["handle_contact_samples"] += 1
            st["max_tilt_deg_in_contact"] = max(st["max_tilt_deg_in_contact"], math.degrees(math.acos(max(-1.0, min(1.0, -float(Rm[2, 2]))))))
            if self._prev_xy is not None:
                st["max_speed_in_contact_mps"] = max(st["max_speed_in_contact_mps"], math.hypot(x - self._prev_xy[0], y - self._prev_xy[1]) * SIM_HZ)
            if self.cur is not None and self.cur["sheet"] != sheet.name:
                self._end_stroke()
            if self.cur is None:
                self._start_stroke(sheet)
            self._add_edge(x, y, sheet.z - z, a, b, sheet)
        elif self.cur is not None:
            self._end_stroke()
        self._prev_xy = (x, y)
        self.n_steps += 1

    @staticmethod
    def _clip_edge(a: np.ndarray, b: np.ndarray, zs: float):
        """The part of the 3-D edge a-b below the plane z = zs, as world xy end points (or None)."""
        if a[2] >= zs and b[2] >= zs:
            return None
        if a[2] < zs and b[2] < zs:
            return a[:2].copy(), b[:2].copy()
        t = (zs - a[2]) / (b[2] - a[2])
        m = a + (b - a) * t
        return (a[:2].copy(), m[:2].copy()) if a[2] < zs else (m[:2].copy(), b[:2].copy())

    def _add_edge(self, x, y, zp, a, b, sheet) -> None:
        c = self.cur
        ang = math.atan2(float(b[1] - a[1]), float(b[0] - a[0]))
        c["samples"].append((x, y, zp, float(self.cfg["nib_width_m"]), 0.0, 0.0, ang, x, y))
        if not c["inked"]:
            return
        seg = self._clip_edge(a, b, sheet.z)
        if seg is None:
            return
        cur = (seg[0], seg[1])
        prev = c["last_fp"]
        if prev is None:
            fps = [cur]
        else:
            d0 = max(np.linalg.norm(cur[0] - prev[0]), np.linalg.norm(cur[1] - prev[1]))
            a0 = math.atan2(*(prev[1] - prev[0])[::-1]); a1 = math.atan2(*(cur[1] - cur[0])[::-1])
            dth = abs((a1 - a0 + math.pi) % (2 * math.pi) - math.pi)
            n = max(1, int(math.ceil(max(d0 / float(self.cfg["substep_m"]), math.degrees(dth) / float(self.cfg["substep_deg"])))))
            fps = [(prev[0] + (cur[0] - prev[0]) * k / n, prev[1] + (cur[1] - prev[1]) * k / n) for k in range(1, n + 1)]
        c["last_fp"] = cur
        th = float(self.cfg["nib_thick_m"])
        for (p0, p1) in fps:
            r = _segment_footprint(sheet, float(p0[0]), float(p0[1]), float(p1[0]), float(p1[1]), th)
            if r is None:
                continue
            r0, c0, al = r
            sl = (slice(r0, r0 + al.shape[0]), slice(c0, c0 + al.shape[1]))
            np.maximum(c["acc"][sl], al, out=c["acc"][sl])
            bb = (r0, r0 + al.shape[0], c0, c0 + al.shape[1])
            c["bbox"] = bb if c["bbox"] is None else (min(c["bbox"][0], bb[0]), max(c["bbox"][1], bb[1]), min(c["bbox"][2], bb[2]), max(c["bbox"][3], bb[3]))
        self.version += 1

    def brush_rgb(self):
        return INK_RGB if self.loaded else (0.62, 0.62, 0.66)

    def brush_state(self) -> dict:
        """The nib's edge now: end points (world xyz) and its pen angle (the edge's direction in the writer's view, 0 = along the
        writing line, counter-clockwise positive), plus whether ink is loaded."""
        if self._edge is None:
            return {"edge": None, "pen_angle_deg": None, "loaded": self.loaded}
        a, b = self._edge
        ex, ey = float(b[0] - a[0]), float(b[1] - a[1])
        return {"edge": [a.tolist(), b.tolist()], "pen_angle_deg": math.degrees(math.atan2(ex, -ey)), "loaded": self.loaded}

    def state_bytes(self) -> bytes:
        return np.asarray([float(self.loaded)], np.float64).tobytes()


def _capsule_footprint(sheet: Sheet, x0: float, y0: float, x1: float, y1: float, thick: float):
    """Anti-aliased coverage of a capsule: the points within thick / 2 of the segment (x0, y0)-(x1, y1) (world), round ends.
    -> (r0, c0, alpha) or None."""
    ht = thick / 2
    xs = [min(x0, x1) - ht, max(x0, x1) + ht]; ys = [min(y0, y1) - ht, max(y0, y1) + ht]
    us, vs = sheet.world_to_px(np.asarray(xs), np.asarray(ys))
    c0 = max(0, int(math.floor(us.min())) - 1); c1 = min(sheet.cols - 1, int(math.ceil(us.max())) + 1)
    r0 = max(0, int(math.floor(vs.min())) - 1); r1 = min(sheet.rows - 1, int(math.ceil(vs.max())) + 1)
    if c1 < c0 or r1 < r0:
        return None
    px = sheet.px_m
    X = sheet.x_far - (np.arange(r0, r1 + 1, dtype=np.float64) + 0.5) * px
    Y = sheet.y_left - (np.arange(c0, c1 + 1, dtype=np.float64) + 0.5) * px
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    qx = X[:, None] - x0; qy = Y[None, :] - y0
    t = np.clip((qx * dx + qy * dy) / L2, 0.0, 1.0) if L2 > 1e-14 else np.zeros_like(qx * qy)
    d = np.hypot(qx - t * dx, qy - t * dy)
    return r0, c0, np.clip((ht - d) / px + 0.5, 0.0, 1.0).astype(np.float32)


class PointedPenPainter(NibPainter):
    """Pointed flexible pen (BRUSH_POINTED): per physics step in contact (tip below a sheet's surface over the sheet) the tine
    segment (tip +- (w - hairline) / 2 along the tool's y axis projected on the paper, w = width_of(press depth)), swept between
    steps by interpolated sub-steps, each footprint a capsule of the hairline's thickness; max-composited opaque ink. Same stroke,
    dip and sheet bookkeeping as the broad nib."""
    def width_of(self, press_m: float) -> float:
        c = self.cfg
        p0, p1, w0, w1 = float(c["flex_start_m"]), float(c["full_flex_m"]), float(c["hairline_m"]), float(c["max_width_m"])
        return w0 + (w1 - w0) * min(1.0, max(0.0, (press_m - p0) / (p1 - p0)))

    def sample(self, p, R) -> None:
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        st = self.stats; st["samples"] += 1
        w = self.wells.well_at(x, y, z)
        if w is not None:
            if w != self.in_well:
                st["n_dips"] += 1
            self.loaded = True; self.version += 1
        self.in_well = w
        Rm = np.asarray(R, np.float64)
        e = Rm[:2, 1]; ne = math.hypot(float(e[0]), float(e[1]))
        e = e / ne if ne > 1e-9 else np.array([0.0, -1.0])
        sheet = self._sheet_at(x, y)
        contact = sheet is not None and z < sheet.z
        press = (sheet.z - z) if contact else 0.0
        width = self.width_of(press) if contact else float(self.cfg["hairline_m"])
        hl = max(0.0, width - float(self.cfg["hairline_m"])) / 2
        a, b = np.array([x, y]) - hl * e, np.array([x, y]) + hl * e
        self._edge = (np.array([a[0], a[1], z]), np.array([b[0], b[1], z]), width, press)
        if contact:
            st["contact_samples"] += 1
            st["max_press_m"] = max(st["max_press_m"], press)
            if press > float(self.cfg["bristle_m"]) - 0.0005:
                st["handle_contact_samples"] += 1
            st["max_tilt_deg_in_contact"] = max(st["max_tilt_deg_in_contact"], math.degrees(math.acos(max(-1.0, min(1.0, -float(Rm[2, 2]))))))
            if self._prev_xy is not None:
                st["max_speed_in_contact_mps"] = max(st["max_speed_in_contact_mps"], math.hypot(x - self._prev_xy[0], y - self._prev_xy[1]) * SIM_HZ)
            if self.cur is not None and self.cur["sheet"] != sheet.name:
                self._end_stroke()
            if self.cur is None:
                self._start_stroke(sheet)
            self._add_tines(x, y, press, width, a, b, sheet)
        elif self.cur is not None:
            self._end_stroke()
        self._prev_xy = (x, y)
        self.n_steps += 1

    def _add_tines(self, x, y, press, width, a, b, sheet) -> None:
        c = self.cur
        ang = math.atan2(float(b[1] - a[1]), float(b[0] - a[0])) if width > float(self.cfg["hairline_m"]) else 0.0
        c["samples"].append((x, y, press, width, 0.0, 0.0, ang, x, y))
        if not c["inked"]:
            return
        cur = (a, b)
        prev = c["last_fp"]
        if prev is None:
            fps = [cur]
        else:
            d0 = max(np.linalg.norm(cur[0] - prev[0]), np.linalg.norm(cur[1] - prev[1]))
            n = max(1, int(math.ceil(d0 / float(self.cfg["substep_m"]))))
            fps = [(prev[0] + (cur[0] - prev[0]) * k / n, prev[1] + (cur[1] - prev[1]) * k / n) for k in range(1, n + 1)]
        c["last_fp"] = cur
        th = float(self.cfg["hairline_m"])
        for (p0, p1) in fps:
            r = _capsule_footprint(sheet, float(p0[0]), float(p0[1]), float(p1[0]), float(p1[1]), th)
            if r is None:
                continue
            r0, c0, al = r
            sl = (slice(r0, r0 + al.shape[0]), slice(c0, c0 + al.shape[1]))
            np.maximum(c["acc"][sl], al, out=c["acc"][sl])
            bb = (r0, r0 + al.shape[0], c0, c0 + al.shape[1])
            c["bbox"] = bb if c["bbox"] is None else (min(c["bbox"][0], bb[0]), max(c["bbox"][1], bb[1]), min(c["bbox"][2], bb[2]), max(c["bbox"][3], bb[3]))
        self.version += 1

    def brush_state(self) -> dict:
        """The point now: its xyz, the press depth, the width it writes at that press, the spread axis (the tool's y axis) as an
        angle in the writer's view (0 = along the writing line, counter-clockwise positive), and whether ink is loaded."""
        if self._edge is None:
            return {"point": None, "press_m": None, "width_m": None, "spread_axis_deg": None, "loaded": self.loaded}
        a, b, width, press = self._edge
        m = (a + b) / 2
        return {"point": m.tolist(), "press_m": float(press), "width_m": float(width),
                "spread_axis_deg": math.degrees(math.atan2(float(b[0] - a[0]), -float(b[1] - a[1]))) if width > float(self.cfg["hairline_m"]) else None,
                "loaded": self.loaded}


class _MyPaintLib:
    """ctypes access to libmypaint through the rcb_mypaint shim (one instance per process)."""
    _inst = None

    def __init__(self, lib: str):
        import ctypes as C
        L = C.CDLL(lib)
        vp = C.c_void_p
        L.rcb_surface_new.restype = vp; L.rcb_surface_new.argtypes = [C.c_int, C.c_int]
        L.rcb_surface_free.argtypes = [vp]; L.rcb_surface_clear.argtypes = [vp]
        L.rcb_surface_read.argtypes = [vp, C.POINTER(C.c_uint16)]; L.rcb_surface_write.argtypes = [vp, C.POINTER(C.c_uint16)]
        L.rcb_brush_new.restype = vp; L.rcb_brush_new.argtypes = [C.c_char_p]; L.rcb_brush_free.argtypes = [vp]
        L.rcb_setting_id.restype = C.c_int; L.rcb_setting_id.argtypes = [C.c_char_p]
        L.rcb_brush_set_base.argtypes = [vp, C.c_int, C.c_float]
        L.rcb_brush_get_base.restype = C.c_float; L.rcb_brush_get_base.argtypes = [vp, C.c_int]
        L.rcb_brush_reset.argtypes = [vp]; L.rcb_brush_new_stroke.argtypes = [vp]
        L.rcb_stroke_to.restype = C.c_int
        L.rcb_stroke_to.argtypes = [vp, vp, C.c_float, C.c_float, C.c_float, C.c_float, C.c_float, C.c_double, C.c_float, C.POINTER(C.c_int)]
        self.L, self.C = L, C

    @classmethod
    def get(cls, lib: str = MYPAINT_LIB) -> "_MyPaintLib":
        if cls._inst is None:
            cls._inst = cls(lib)
        return cls._inst


class MyPaintPainter(CalligraphyPainter):
    """libmypaint painter (BRUSH_MYPAINT): one mypaint surface per sheet (a transparent paint layer over the paper), one brush.
    Tip samples over a sheet are motion events (pressure 0 above the paper, so the engine follows the motion); leaving a sheet ends
    the engine's stroke (it is reset before the next event, so no dab is interpolated across the jump). Stroke bookkeeping (count,
    sheet, dry) as for the other media; no per-stroke masks (the painting metrics are image-level)."""
    def _new_brush(self):
        self.mp = _MyPaintLib.get()
        C = self.mp.C
        if getattr(self, "surf", None):
            for p_ in self.surf.values():
                self.mp.L.rcb_surface_clear(p_)
        else:
            self.surf = {n: self.mp.L.rcb_surface_new(s.cols, s.rows) for n, s in self.sheets.items()}
        if getattr(self, "mbrush", None):
            self.mp.L.rcb_brush_free(self.mbrush)
        self.mbrush = None
        self.color = None
        self._on = None
        self._layer_cache = {}
        self._last_pr = 0.0
        return None

    def _load(self, k: int) -> None:
        """A dip: a fresh brush from the frozen preset, coloured with well k."""
        import colorsys
        L = self.mp.L
        if self.mbrush:
            L.rcb_brush_free(self.mbrush)
        self.mbrush = L.rcb_brush_new(self.cfg["preset_json"].encode())
        if not self.mbrush:
            raise RuntimeError("libmypaint could not parse the frozen brush preset")
        rid = L.rcb_setting_id(b"radius_logarithmic")
        L.rcb_brush_set_base(self.mbrush, rid, float(L.rcb_brush_get_base(self.mbrush, rid)) + float(self.cfg["radius_log_offset"]))
        h, sat, v = colorsys.rgb_to_hsv(*self.wells.rgb[k])
        for name, val in (("color_h", h), ("color_s", sat), ("color_v", v)):
            L.rcb_brush_set_base(self.mbrush, L.rcb_setting_id(name.encode()), float(val))
        L.rcb_brush_reset(self.mbrush)
        self.color = k
        self._on = None
        self._last_pr = 0.0

    def sample(self, p, R) -> None:
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        st = self.stats; st["samples"] += 1
        w = self.wells.well_at(x, y, z)
        if w is not None:
            if w != self.in_well:
                st["n_dips"] += 1
            if w != self.color or w != self.in_well:
                self._load(w)
            self.loaded = True; self.version += 1
        self.in_well = w
        sheet = self._sheet_at(x, y)
        Rm = np.asarray(R, np.float64)
        contact = sheet is not None and z < sheet.z
        if contact:
            st["contact_samples"] += 1
            st["max_press_m"] = max(st["max_press_m"], sheet.z - z)
            if sheet.z - z > float(self.cfg["bristle_m"]) - 0.0005:
                st["handle_contact_samples"] += 1
            st["max_tilt_deg_in_contact"] = max(st["max_tilt_deg_in_contact"], math.degrees(math.acos(max(-1.0, min(1.0, -float(Rm[2, 2]))))))
            if self._prev_xy is not None:
                st["max_speed_in_contact_mps"] = max(st["max_speed_in_contact_mps"], math.hypot(x - self._prev_xy[0], y - self._prev_xy[1]) * SIM_HZ)
            if self.cur is not None and self.cur["sheet"] != sheet.name:
                self._end_stroke()
            if self.cur is None:
                self._start_stroke(sheet)
                self.cur["acc"] = None
            self.cur["samples"].append((x, y, sheet.z - z, 0.0, 0.0, 0.0, 0.0, x, y))
        elif self.cur is not None:
            self._end_stroke()
        if self.mbrush and sheet is not None and z < sheet.z + 0.02:        # motion events near a sheet (within 2 cm)
            if self._on != sheet.name:
                self.mp.L.rcb_brush_reset(self.mbrush); self._on = sheet.name; self._last_pr = 0.0
            u, v = sheet.world_to_px(x, y)
            pr = min(1.0, max(0.0, (sheet.z - z) / float(self.cfg["full_press_m"]))) if (contact and self.loaded) else 0.0
            ax = -Rm[:, 2]                                                   # brush axis (tip -> handle is +axis): tilt components
            xt, yt = float(-ax[1]), float(-ax[0])                            # image x = -world y, image y = -world x
            yaw = math.atan2(Rm[1, 0], Rm[0, 0]) % (2 * math.pi)
            self.mp.L.rcb_stroke_to(self.mbrush, self.surf[sheet.name], float(u) + 0.5, float(v) + 0.5, pr, max(-1.0, min(1.0, xt)),
                                    max(-1.0, min(1.0, yt)), 1.0 / SIM_HZ, yaw / (2 * math.pi), None)
            # any engine call may have drawn: libmypaint interpolates the pressure between events, so the event after the last
            # pressed one still lays dabs (the read cache must not keep a layer from before them; found: a video replay, which reads
            # the sheets every frame, ended with a stale cache and a different state hash than a plain replay)
            self._layer_cache.pop(sheet.name, None)
            if pr > 0 or self._last_pr > 0:
                self.version += 1
            self._last_pr = pr
        elif self._on is not None and (sheet is None or z >= sheet.z + 0.02):
            self._on = None; self._last_pr = 0.0
        self._prev_xy = (x, y)
        self.n_steps += 1

    def _end_stroke(self) -> None:
        c = self.cur
        if c is None:
            return
        P = np.asarray(c["samples"], np.float64).reshape(-1, 9)
        rec = {"sheet": c["sheet"], "inked": bool(c["inked"]), "start_sample": c["start_sample"], "samples": P,
               "length_mm": float(np.sum(np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1]))) * 1000) if len(P) > 1 else 0.0,
               "max_press_mm": float(P[:, 2].max() * 1000) if len(P) else 0.0, "mask_bbox": (0, 0), "mask": np.zeros((0, 0), np.uint8),
               "color": None if self.color is None else self.wells.names[self.color]}
        self.strokes.append(rec)
        self.cur = None
        self.version += 1

    def layer(self, sheet: str = "main") -> np.ndarray:
        """The sheet's paint layer: premultiplied RGBA, float32 in [0, 1] (libmypaint's 1.0 = 32768)."""
        if sheet not in self._layer_cache:
            s_ = self.sheets[sheet]
            buf = np.empty((s_.rows, s_.cols, 4), np.uint16)
            self.mp.L.rcb_surface_read(self.surf[sheet], buf.ctypes.data_as(self.mp.C.POINTER(self.mp.C.c_uint16)))
            self._layer_cache[sheet] = buf
        return self._layer_cache[sheet].astype(np.float32) / 32768.0

    def display_ink(self, sheet: str = "main") -> np.ndarray:
        return np.clip(self.layer(sheet)[..., 3], 0.0, 1.0)

    def display(self, sheet: str = "main") -> np.ndarray:
        a = self.layer(sheet)
        return np.clip(a[..., :3] + (1.0 - a[..., 3:4]) * np.asarray(PAPER_RGB, np.float32), 0.0, 1.0)

    def brush_rgb(self):
        return None if self.color is None else tuple(float(v) for v in self.wells.rgb[self.color])

    def brush_state(self) -> dict:
        return {"loaded": self.loaded, "color": None if self.color is None else self.wells.names[self.color]}

    def state_bytes(self) -> bytes:
        h = hashlib.sha1()
        for n in sorted(self.sheets):
            self.layer(n)
            h.update(self._layer_cache[n].tobytes())
        return h.digest() + np.asarray([float(self.loaded), -1.0 if self.color is None else float(self.color)], np.float64).tobytes()


def make_painter(inst: dict, sheets: dict[str, Sheet], wells: Wells):
    if inst["medium"] == "calligraphy":
        return CalligraphyPainter(inst["brush"], sheets, wells)
    if inst["medium"] == "broad_nib":
        return NibPainter(inst["brush"], sheets, wells)
    if inst["medium"] == "pointed_pen":
        return PointedPenPainter(inst["brush"], sheets, wells)
    if inst["medium"] == "mypaint":
        return MyPaintPainter(inst["brush"], sheets, wells)
    raise ValueError(f"unknown medium {inst['medium']!r}")


# --------------------------------------------------------------------------- ManiSkill: the brush robot and the scene
_REGISTERED: dict[str, Any] = {}


def _brush_urdf(bristle_m: float, bristle_r: float, dry_rgb=(0.86, 0.80, 0.68), nib_w: float | None = None) -> str:
    """PandaStick's URDF (ManiSkill 3.0.1) with a collision-free bristle tuft of length bristle_m below the rigid stick and the TCP
    moved to its tip (the stick keeps its collision: a hard stop at a press of bristle_m). nib_w: a flat nib instead of a round tuft
    (a box visual nib_w wide along the tool's y axis, 1 mm thick), so the cameras show its orientation."""
    from mani_skill import PACKAGE_ASSET_DIR
    src = os.path.join(PACKAGE_ASSET_DIR, "robots/panda/panda_stick.urdf")
    s = open(src).read()
    d = os.path.join(PACKAGE_ASSET_DIR, "robots/panda")
    s = s.replace('filename="franka_description/', f'filename="{d}/franka_description/')
    old = '<origin rpy="0 0 0" xyz="0 0 0.15"/>\n    <parent link="panda_hand"/>'
    if old not in s:
        raise RuntimeError("panda_stick.urdf is not the ManiSkill 3.0.1 layout this tooling was written for")
    s = s.replace(old, f'<origin rpy="0 0 0" xyz="0 0 {0.15 + bristle_m:.4f}"/>\n    <parent link="panda_hand"/>')
    geom = (f'        <box size="0.0010 {nib_w:.4f} {bristle_m:.4f}"/>\n' if nib_w else f'        <cylinder radius="{bristle_r}" length="{bristle_m:.4f}"/>\n')
    tuft = (f'    <visual>\n      <origin xyz="0 0 {0.15 + bristle_m / 2:.4f}" rpy="0 0 0"/>\n      <geometry>\n'
            + geom + '      </geometry>\n'
            f'      <material name="bristle"><color rgba="{dry_rgb[0]} {dry_rgb[1]} {dry_rgb[2]} 1"/></material>\n    </visual>\n')
    anchor = '  </link>\n  <link name="panda_hand_tcp"/>'
    if anchor not in s:
        raise RuntimeError("panda_stick.urdf is not the ManiSkill 3.0.1 layout this tooling was written for")
    s = s.replace(anchor, tuft + anchor)
    out = os.path.join(tempfile.gettempdir(), f"rcb_brush_urdf_{sha16(s.encode())}")
    os.makedirs(out, exist_ok=True)
    fn = os.path.join(out, "panda_brush.urdf")
    if not os.path.exists(fn):
        tmp = fn + f".{os.getpid()}"
        open(tmp, "w").write(s); os.replace(tmp, fn)
        tmp = fn[:-4] + f"srdf.{os.getpid()}"
        open(tmp, "w").write(open(src[:-4] + "srdf").read()); os.replace(tmp, fn[:-4] + "srdf")
    return fn


def _register(bristle_m: float, bristle_r: float, nib_w: float | None = None) -> str:
    """Register the brush robot (one agent uid per tuft geometry) and the brushwork env with ManiSkill (once per process)."""
    uid = f"panda_brushwork_{int(round(bristle_m * 1e4))}_{int(round(bristle_r * 1e4))}" + (f"_nib{int(round(nib_w * 1e4))}" if nib_w else "")
    if uid in _REGISTERED:
        return uid
    import sapien
    from mani_skill.agents.registration import register_agent
    from mani_skill.agents.robots.panda.panda_stick import PandaStick
    from mani_skill.envs.sapien_env import BaseEnv
    from mani_skill.sensors.camera import CameraConfig
    from mani_skill.utils import sapien_utils
    from mani_skill.utils.registration import register_env
    from mani_skill.utils.scene_builder.table.scene_builder import TableSceneBuilder
    from mani_skill.utils.structs.types import SceneConfig, SimConfig

    agent_cls = type(f"_PandaBrush_{uid}", (PandaStick,), {"uid": uid, "urdf_path": _brush_urdf(bristle_m, bristle_r, nib_w=nib_w)})
    register_agent()(agent_cls)
    if "env" not in _REGISTERED:
        @register_env(ENV_ID, max_episode_steps=None)
        class _BrushCanvasEnv(BaseEnv):
            """ManiSkill's drawing-table scene with the brush robot, the main + practice sheets (textured planes: their rasters) and the ink plate."""
            SUPPORTED_REWARD_MODES = ["none"]

            def __init__(self, *args, robot_uids=None, painter=None, scene_cfg: dict | None = None, rest_qpos=REST_QPOS, **kwargs):
                self.painter = painter
                self.scene_cfg = scene_cfg or {}
                self.sheets = painter.sheets if painter else {}
                self.wells = painter.wells if painter else None
                self.bristle_r = float(self.scene_cfg.get("bristle_r", 0.0035))
                self.nib_w = self.scene_cfg.get("nib_w")
                self.tuft = None; self._tuft_color = "dry"
                self.rest_qpos = np.asarray(rest_qpos, np.float32)
                self.SUPPORTED_ROBOTS = [robot_uids]
                super().__init__(*args, robot_uids=robot_uids, **kwargs)

            @property
            def _default_sim_config(self):
                return SimConfig(sim_freq=SIM_HZ, control_freq=CONTROL_HZ,
                                 scene_config=SceneConfig(contact_offset=0.01, solver_position_iterations=4, solver_velocity_iterations=0))

            @property
            def _default_sensor_configs(self):
                return []

            @property
            def _default_human_render_camera_configs(self):
                out = []
                m = self.sheets.get("main")
                if m is not None:
                    (cx, cy), z = m.center, m.z
                    out.append(CameraConfig("canvas_cam", pose=sapien_utils.look_at([cx, cy, z + 0.60], [cx, cy, z], up=[1, 0, 0]),
                                            width=1024, height=1024, fov=0.43, near=0.01, far=10))
                pr = self.sheets.get("practice")
                if pr is not None:
                    (px_, py_), z = pr.center, pr.z
                    fov = 2 * math.atan((pr.size_x / 2 + 0.012) / 0.45)
                    out.append(CameraConfig("practice_cam", pose=sapien_utils.look_at([px_, py_, z + 0.45], [px_, py_, z], up=[1, 0, 0]),
                                            width=512, height=1024, fov=fov, near=0.01, far=10))
                cx, cy = (m.center if m is not None else PAPER_CENTER)
                out += [CameraConfig("scene_cam", pose=sapien_utils.look_at([0.3, 0, 0.8], [0, 0, 0.1]), width=640, height=480, fov=1.2, near=0.01, far=100),
                        CameraConfig("side_cam", pose=sapien_utils.look_at([cx, cy - 0.42, PAPER_Z + 0.05], [cx, cy, PAPER_Z]), width=640, height=360, fov=0.9, near=0.01, far=10)]
                return out

            def _load_agent(self, options: dict):
                super()._load_agent(options, sapien.Pose(p=list(ROBOT_BASE)))

            def _load_scene(self, options: dict):
                self.table_scene = TableSceneBuilder(self, robot_init_qpos_noise=0)
                self.table_scene.build()
                b = self.scene.create_actor_builder()                       # the drawing board (0.8 x 1.2 m, 2 cm thick)
                b.add_box_visual(half_size=[0.4, 0.6, PAPER_Z / 2], material=sapien.render.RenderMaterial(base_color=[0.80, 0.80, 0.78, 1]))
                b.add_box_collision(half_size=[0.4, 0.6, PAPER_Z / 2])
                b.initial_pose = sapien.Pose(p=[-0.1, 0, PAPER_Z / 2])
                self.board = b.build_static(name="board")
                self.sheet_tex = {}
                if self.scene.can_render():
                    for name, sh in self.sheets.items():
                        tex = sapien.render.RenderTexture2D(np.full((sh.cols, sh.rows, 4), 255, np.uint8), format="R8G8B8A8Unorm", mipmap_levels=1,
                                                            filter_mode="linear", address_mode="edge", srgb=True)
                        mat = sapien.render.RenderMaterial(base_color=[1, 1, 1, 1], roughness=0.9, specular=0.0)
                        mat.base_color_texture = tex
                        b = self.scene.create_actor_builder()
                        b.add_plane_visual(pose=sapien.Pose(q=[0.70710678, 0, -0.70710678, 0]), scale=[1, sh.size_y / 2, sh.size_x / 2], material=mat)
                        b.initial_pose = sapien.Pose(p=[sh.center[0], sh.center[1], sh.z + 2e-4])
                        b.build_kinematic(name=f"sheet_{name}")
                        self.sheet_tex[name] = tex
                if self.wells is not None:                                  # the ink / paint plate (collision: a hard stop for the handle)
                    d = self.wells.d
                    (tx, ty), (hx, hy, hz) = d["plate_center_xy"], d["plate_half_size"]
                    b = self.scene.create_actor_builder()
                    b.add_box_visual(half_size=[hx, hy, hz], material=sapien.render.RenderMaterial(base_color=[0.90, 0.90, 0.88, 1], roughness=0.3))
                    b.add_box_collision(half_size=[hx, hy, hz])
                    liquid_h = float(d["surface_z"]) - float(d["plate_top_z"])
                    for w in d["wells"]:                                    # ink / paint puddles: visual only (liquid)
                        lin = [float(v) for v in srgb_to_linear(w["rgb"])]
                        b.add_cylinder_visual(radius=float(w["radius_m"]), half_length=liquid_h / 2,
                                              pose=sapien.Pose(p=[w["center_xy"][0] - tx, w["center_xy"][1] - ty, hz + liquid_h / 2], q=[0.70710678, 0, 0.70710678, 0]),
                                              material=sapien.render.RenderMaterial(base_color=lin + [1], roughness=0.6, specular=0.2))
                    b.initial_pose = sapien.Pose(p=[tx, ty, float(d["plate_top_z"]) - hz])
                    self.plate_actor = b.build_static(name="plate")

            def _initialize_episode(self, env_idx, options):
                self.table_scene.initialize(env_idx)
                self.agent.reset(np.asarray(options.get("qpos", self.rest_qpos), np.float32)[None])
                self.agent.robot.set_pose(sapien.Pose(p=list(ROBOT_BASE)))
                if self.painter is not None:
                    self.painter.reset()

            def _after_simulation_step(self):
                if self.painter is not None:
                    pose = self.agent.tcp.pose
                    q = pose.q[0].cpu().numpy().astype(np.float64)
                    self.painter.sample(pose.p[0].cpu().numpy().astype(np.float64), quat_to_mat(q))

            def evaluate(self):
                return {}

            def set_tuft_color(self, rgb) -> None:
                key = None if rgb is None else tuple(float(v) for v in rgb)
                if key == self._tuft_color:
                    return
                self._tuft_color = key
                if self.tuft is None:
                    for link in self.agent.robot.get_links():
                        for obj in link._objs:
                            rb = obj.entity.find_component_by_type(sapien.render.RenderBodyComponent)
                            for sh in (rb.render_shapes if rb is not None else []):
                                if self.nib_w and isinstance(sh, sapien.render.RenderShapeBox) and abs(float(sh.half_size[1]) - self.nib_w / 2) < 1e-6:
                                    self.tuft = sh
                                elif not self.nib_w and isinstance(sh, sapien.render.RenderShapeCylinder) and abs(float(sh.radius) - self.bristle_r) < 1e-6:
                                    self.tuft = sh
                    if self.tuft is None:
                        return
                c = (0.86, 0.80, 0.68) if rgb is None else rgb
                self.tuft.material.base_color = [float(v) for v in srgb_to_linear(c)] + [1.0]

            def upload_sheet(self, name: str, img: np.ndarray) -> None:
                tex = self.sheet_tex.get(name)
                if tex is None:
                    return
                # the plane primitive's texture rows run from -y to +y and its columns from -x to +x (rcb_paint's quadrant test);
                # sheet rows run from +x to -x and columns from +y to -y: flip both axes and transpose
                rgb = np.round(np.clip(img, 0, 1) * 255).astype(np.uint8)[::-1, ::-1].transpose(1, 0, 2)
                rgba = np.concatenate([rgb, np.full(rgb.shape[:2] + (1,), 255, np.uint8)], -1)
                tex.upload(np.ascontiguousarray(rgba))

        _REGISTERED["env"] = _BrushCanvasEnv
    _REGISTERED[uid] = agent_cls
    return uid


# --------------------------------------------------------------------------- the agent's Session
class Session:
    VIDEO_CAMERAS = VIDEO_CAMERAS

    def __init__(self, instance: str | Path | None = None, *, inst: dict | None = None, task: str | None = None, strict: bool = False,
                 render: bool = True, max_steps: int | None = None, base_dir: str | None = None):
        t0 = time.time()
        if inst is None:
            if instance is None:
                raise ValueError("Session needs instance=<instance.json>")
            inst = json.load(open(instance))
        if task is not None and inst.get("task") != task:
            raise ValueError(f"instance task {inst.get('task')!r} != session task {task!r}")
        self.inst = inst
        self.task, self.medium = inst["task"], inst["medium"]
        self.sheets = sheets_from_inst(inst)
        self.geo = self.sheets["main"]
        self.wells_ = Wells(inst["wells"])
        base = base_dir or (os.path.dirname(os.path.abspath(instance)) if instance is not None else os.getcwd())
        self.picture = TargetPicture(os.path.join(base, inst["target"].get("image", "target.png")))
        self.truth = None                   # the graders' / scoring service's copy only (rcb_brush_score)
        if inst.get("truth"):
            import rcb_brush_score as G
            self.truth = G.load_truth(inst, self.geo, base, self.picture)
        self._since_reset: list[np.ndarray] = []      # actions since the last reset (what the scoring service replays)
        import uuid
        self._client_id = uuid.uuid4().hex
        self._scorer_url: str | None = None
        self.painter = make_painter(inst, self.sheets, self.wells_)
        self.max_steps = int(max_steps or inst.get("max_steps", MAX_STEPS))
        nib_w = inst["brush"].get("nib_width_m") or inst["brush"].get("visual_w_m")
        uid = _register(float(inst["brush"]["bristle_m"]), float(inst["brush"]["bristle_r"]), float(nib_w) if nib_w else None)
        import gymnasium as gym
        import torch
        torch.set_num_threads(TORCH_THREADS)
        self.th = torch
        self.render_enabled = False
        env = None
        kw = dict(obs_mode="state", control_mode="pd_joint_pos", reward_mode="none", sim_backend="physx_cpu", robot_uids=uid,
                  painter=self.painter, scene_cfg={"bristle_r": float(inst["brush"]["bristle_r"]), "nib_w": float(nib_w) if nib_w else None},
                  rest_qpos=inst["robot_qpos"])
        if render and os.environ.get("RCB_RENDER", "1") == "1":
            try:
                env = gym.make(ENV_ID, render_mode="rgb_array", render_backend="cpu", **kw)
                self.render_enabled = True
            except Exception as exc:  # noqa: BLE001
                _log(f"rendering unavailable ({str(exc)[:120]}); continuing without cameras "
                     "(SAPIEN still needs a Vulkan device to build the scene's visual shapes)")
                env = None
        if env is None:
            env = gym.make(ENV_ID, render_backend="none", **kw)
        self.env = env
        self.u = env.unwrapped
        self.robot = self.u.agent.robot
        self.env.reset(seed=0, options={"qpos": inst["robot_qpos"]})
        self._pm = self.robot._objs[0].create_pinocchio_model()
        self._tcp_idx = [l.name for l in self.robot.get_links()].index("panda_hand_tcp")
        self._base = self.robot.pose.sp
        self.n_steps, self._resets, self._total_steps = 0, 0, 0
        self._recording: list[np.ndarray] | None = None
        self._targets = self.joint_positions().astype(np.float64)
        self._down_quat = np.asarray(self.u.agent.tcp.pose.sp.q, np.float64)    # the rest pose points the brush straight down
        self._links = [l.name for l in self.robot.get_links()]                  # the kinematic model's constants (read once)
        self._qlim = np.asarray(self.robot.get_qlimits()[0].cpu().numpy(), np.float64)[:ACTION_DIM]
        self._drives = [(float(o.stiffness), float(o.damping), float(o.force_limit), float(o.max_velocity))
                        for o in (j._objs[0] for j in self.robot.get_active_joints()[:ACTION_DIM])]
        self.instance_sha = self._instance_sha()
        expected = inst.get("instance_sha")
        self.instance_exact = expected is None or expected == self.instance_sha
        if self.truth is not None and inst["target"].get("truth_sha") not in (None, self.truth.sha):
            self.instance_exact = False                          # the graders' copy: its scoring data must be the frozen one
        self.instance_matches = self.instance_exact
        if not self.instance_exact:
            msg = f"instance sha {self.instance_sha} != expected {expected} (tooling / simulator version drift?)"
            if strict:
                raise RuntimeError(msg)
            _log("WARNING:", msg)
        self._frame_version = -1
        self._end_logged = False
        _slog("session_start", task=self.task)
        import atexit
        atexit.register(self._log_end)
        _log(f"session ready in {time.time() - t0:.1f}s; instance_sha={self.instance_sha}; render={self.render_enabled}")

    # ---- state
    def _instance_sha(self) -> str:
        consts = json.dumps({"medium": self.medium, "sheets": self.inst["sheets"], "wells": self.inst["wells"], "brush": self.inst["brush"],
                             "control_hz": CONTROL_HZ, "sim_hz": SIM_HZ}, sort_keys=True).encode()
        return sha16(self.state_sha().encode(), self.picture.sha.encode(), consts)

    def state_sha(self) -> str:
        """sha of every sheet's ink (committed + in progress), the robot state, the stroke count and the brush state."""
        q = self.robot.get_qpos()[0].cpu().numpy().astype(np.float32); dq = self.robot.get_qvel()[0].cpu().numpy().astype(np.float32)
        inks = b"".join(np.ascontiguousarray(self.painter.display_ink(n)).tobytes() for n in sorted(self.sheets))
        return sha16(inks, q.tobytes(), dq.tobytes(), np.int64(len(self.painter.strokes) + (1 if self.painter.cur else 0)).tobytes(),
                     self.painter.state_bytes())

    def joint_positions(self) -> np.ndarray:
        return self.robot.get_qpos()[0].cpu().numpy().astype(np.float64)[:ACTION_DIM]

    def joint_velocities(self) -> np.ndarray:
        """Measured joint velocities (rad/s), panda_joint1..7."""
        return self.robot.get_qvel()[0].cpu().numpy().astype(np.float64)[:ACTION_DIM]

    def joint_efforts(self) -> np.ndarray:
        """PD drive-effort estimate per joint (N m): stiffness * (target - q) - damping * qdot from the measured q, qdot and the current
        joint targets (hold_action()), clipped at the drive's force limit, as the simulator's drive computes it. The robot's links
        carry no gravity in this simulator, so it is about 0 at rest; it rises while the arm lags a moving target or presses on
        something with its rigid parts."""
        q, dq, t = self.joint_positions(), self.joint_velocities(), self._targets
        kp, kd, fl = (np.asarray([d[i] for d in self._drives], np.float64) for i in range(3))
        return np.clip(kp * (t - q) - kd * dq, -fl, fl)

    def tip_pose(self) -> tuple[np.ndarray, np.ndarray]:
        """Measured brush-tip pose (world): position (m), quaternion wxyz. The tip is the TCP (the tip of the unbent tuft)."""
        p = self.u.agent.tcp.pose
        return p.p[0].cpu().numpy().astype(np.float64), p.q[0].cpu().numpy().astype(np.float64)

    def press_depth(self) -> float:
        """How far the tip is below the paper surface (m; negative = above)."""
        return PAPER_Z - float(self.tip_pose()[0][2])

    def pen_down(self) -> bool:
        p = self.tip_pose()[0]
        return any(s.inside(p[0], p[1]) and p[2] < s.z for s in self.sheets.values())

    def canvas(self, sheet: str = "main") -> np.ndarray:
        """Exact image of a sheet (uint8 RGB; row 0 = the far edge, col 0 = the left edge seen from the base), incl. a stroke in progress."""
        return np.round(np.clip(self.painter.display(sheet), 0, 1) * 255).astype(np.uint8)

    def ink(self, sheet: str = "main") -> np.ndarray:
        """Exact ink coverage of a sheet (float32 in [0, 1]); the score uses coverage >= 0.5."""
        return self.painter.display_ink(sheet).copy()

    def target_image(self) -> np.ndarray:
        """The target picture (target.png: uint8 RGB covering the main sheet, 1024 px)."""
        return self.picture.image()

    def wells(self) -> list[dict]:
        return [dict(w, surface_z=self.wells_.surface_z) for w in self.inst["wells"]["wells"]]

    def sheet_facts(self) -> dict:
        return {n: s.facts() for n, s in self.sheets.items()}

    def strokes(self) -> list[dict]:
        """Committed strokes: sheet, inked, start_sample, samples (N, 9: tip x, y, press depth, then the brush state w, d, o, θ,
        root x, root y after the sample), length_mm, max_press_mm, mask_bbox + mask (uint8 coverage of the stroke's own ink)."""
        return [dict(s) for s in self.painter.strokes]

    def brush_state(self) -> dict:
        """The brush model's state now (privileged). Calligraphy: width w, drag d, offset o (m), orientation θ (rad), root (world xy);
        broad nib: the edge and the pen angle; both: whether ink is loaded."""
        return self.painter.brush_state()

    def score(self) -> dict[str, float]:
        """The grader's metrics of the main sheet + success and final_reward. In the agent's container this asks the scoring
        service (see _remote_score)."""
        if self.truth is None:
            return self._remote_score()
        import rcb_brush_score as G
        strokes = list(self.painter.strokes)
        if self.painter.cur is not None:        # a stroke still pressed on the paper counts (its ink is in display_ink)
            strokes = strokes + [{"sheet": self.painter.cur["sheet"], "inked": self.painter.cur["inked"], "mask_bbox": (0, 0), "mask": np.zeros((0, 0), np.uint8)}]
        return G.score_session(self, strokes)

    def _remote_score(self) -> dict[str, float]:
        """POST the actions executed since the last reset (float32 (T, 7)) to the scoring service, which replays them on its own
        copy of this frozen instance and answers with the metrics (agent_metrics()) of the resulting main sheet."""
        import urllib.error
        import urllib.request
        body = np.asarray(self._since_reset, np.float32).reshape(-1, ACTION_DIM).tobytes()
        urls = [u for u in [os.environ.get("RCB_SCORER_URL")] + list(self.inst.get("scorer_urls", SCORER_URLS)) if u]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline, last = time.time() + 180.0, None
        while True:
            for u in ([self._scorer_url] if self._scorer_url else urls):
                req = urllib.request.Request(u.rstrip("/") + "/score", data=body, method="POST",
                                             headers={"Content-Type": "application/octet-stream", "X-RCB-Client": self._client_id})
                try:
                    with opener.open(req, timeout=1800) as r:
                        d = json.loads(r.read())
                    self._scorer_url = u
                    return d["metrics"]
                except urllib.error.HTTPError as exc:
                    raise RuntimeError(f"scoring service: HTTP {exc.code}: {exc.read()[:300].decode(errors='replace')}") from None
                except (urllib.error.URLError, OSError) as exc:
                    last = exc
            self._scorer_url = None
            if time.time() > deadline:
                raise RuntimeError(f"the scoring service is not reachable ({last!r}); s.score() needs it (tried {urls})")
            time.sleep(2.0)

    def status(self) -> dict[str, Any]:
        sc = self.score()
        return {**sc, "sim_steps": int(self.n_steps), "resets": self._resets, "loaded": self.painter.loaded,
                "n_contacts": len(self.painter.strokes) + (1 if self.painter.cur else 0), "pen_down": self.pen_down(),
                "state_sha": self.state_sha(), **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in self.painter.stats.items()}}

    # ---- stepping
    def reset(self) -> None:
        """Back to the frozen instance: blank sheets, dry brush, robot at its start joints (exact)."""
        _slog("reset", task=self.task, n=self._resets + 1, sim_steps_before=self.n_steps)
        self._resets += 1
        self._total_steps += self.n_steps
        self.n_steps = 0
        self._recording = None
        self._since_reset = []
        self.env.reset(seed=0, options={"qpos": self.inst["robot_qpos"]})
        self._targets = self.joint_positions().astype(np.float64)
        self._frame_version = -1

    def step(self, action) -> None:
        """One low-level action (7 absolute joint targets, rad) for one control step (1/20 s = 5 physics steps)."""
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        if a.size != ACTION_DIM:
            raise ValueError(f"action must have {ACTION_DIM} entries, got {a.size}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains nan/inf")
        if self.n_steps >= self.max_steps:
            raise PrimitiveError(f"runaway guard: {self.max_steps} control steps in this episode; reset() to start over")
        if self._recording is not None:
            self._recording.append(a.copy())
        self._since_reset.append(a.copy())
        self.env.step(self.th.as_tensor(a[None]))
        self._targets = a.astype(np.float64)
        self.n_steps += 1

    def hold_action(self) -> np.ndarray:
        return self._targets.astype(np.float32).copy()

    # ---- kinematics
    def ik(self, pos, quat_wxyz=None, q_init=None) -> tuple[np.ndarray, bool, float]:
        """Joint targets (7) that put the brush tip at `pos` (world) with orientation `quat_wxyz` (default: straight down, as at the
        start). SAPIEN's Pinocchio CLIK, no collision checking. -> (q, converged, residual)."""
        import sapien
        q0 = np.asarray(self._targets if q_init is None else q_init, np.float64)
        quat = self._down_quat if quat_wxyz is None else np.asarray(quat_wxyz, np.float64) / np.linalg.norm(quat_wxyz)
        tgt = self._base.inv() * sapien.Pose(np.asarray(pos, np.float64), quat)
        full = np.concatenate([q0, np.zeros(max(0, self.robot.max_dof - ACTION_DIM))]) if self.robot.max_dof > ACTION_DIM else q0
        q, ok, err = self._pm.compute_inverse_kinematics(self._tcp_idx, tgt, initial_qpos=full, active_qmask=[1] * self.robot.max_dof,
                                                         max_iterations=200)
        return np.asarray(q, np.float64)[:ACTION_DIM], bool(ok), float(np.linalg.norm(np.asarray(err)))

    def fk(self, q) -> tuple[np.ndarray, np.ndarray]:
        """Tip pose (world) for joint positions q (7)."""
        self._pm.compute_forward_kinematics(np.asarray(q, np.float64))
        p = self._base * self._pm.get_link_pose(self._tcp_idx)
        return np.asarray(p.p, np.float64), np.asarray(p.q, np.float64)

    def tip_down_quat(self, yaw: float = 0.0) -> np.ndarray:
        """Brush pointing straight down, rotated by `yaw` (rad) about the vertical axis relative to the start orientation."""
        return quat_mul([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)], self._down_quat)

    # ---- the robot's spec sheet and a stateless kinematics query (rcb-limited/2.2; the limited sidecar serves the same answers)
    def _frame_index(self, frame: str) -> int:
        return self._tcp_idx if frame == TOOL_FRAME else self._links.index(frame)

    def _fk_frames(self, q, frames) -> dict:
        """World poses [x, y, z, qw, qx, qy, qz] of `frames` for joint positions q (7) from the kinematic model; no simulator state."""
        self._pm.compute_forward_kinematics(np.asarray(q, np.float64))
        out = {}
        for f in frames:
            p = self._base * self._pm.get_link_pose(self._frame_index(f))
            out[f] = np.concatenate([np.asarray(p.p, np.float64), np.asarray(p.q, np.float64)])
        return out

    def kinematics_spec(self) -> dict:
        """What kinematics() (and the standard mode's /kinematics) answers: the q layout, the frames, the IK solver and its defaults."""
        return {"endpoint": "/kinematics", "joint_names": list(JOINT_NAMES), "frame": "world", "quaternion_order": "wxyz",
                "links": [n for n in self._links if n != "panda_hand_tcp"] + [TOOL_FRAME],
                "tcp_frames": [TOOL_FRAME], "ee_frames": [TOOL_FRAME], "ik_targets": [TOOL_FRAME],
                "ik": {"solver": "SAPIEN 3.0.3 Pinocchio CLIK (damped least squares) from the seed: the solver of the ee_pose action and "
                                 "move_tip", "joints": "all 7 move", **IK_DEFAULTS,
                       "seed_default": "the start joint positions (never the current ones: the answer depends on the request only)",
                       "result": "clamped to the joint limits; ok = the clamped result meets both tolerances", "collision_checking": "none"},
                "stateless": True,
                "note": f"the robot's kinematic model (the articulation's Pinocchio model); poses in the world frame (the base is fixed); "
                        f"'{TOOL_FRAME}' = the tool point (robot_spec.tcp), the other frames are the Panda's links"}

    def robot_spec(self) -> dict:
        """The robot's spec sheet (the standard mode's /spec robot_spec): joints and their limits as the simulator applies them, the
        drives' gains, the rates and the tool frame. Robot facts only (no gripper: the tool is fixed to the hand)."""
        import re
        rated = {}
        try:              # the Franka's rated limits, as ManiSkill's URDF states them (the simulator applies the drive's own limits)
            from mani_skill import PACKAGE_ASSET_DIR
            urdf = open(os.path.join(PACKAGE_ASSET_DIR, "robots/panda/panda_stick.urdf")).read()
            for m in re.finditer(r'<joint name="(panda_joint\d)"[^>]*>.*?<limit ([^/]*)/>', urdf, re.S):
                a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2)))
                rated[m.group(1)] = (float(a["velocity"]), float(a["effort"]))
        except Exception:  # noqa: BLE001
            rated = {}
        joints = []
        for n, (lo, hi), (kp, kd, fl, vmax) in zip(JOINT_NAMES, self._qlim, self._drives):
            j = {"name": n, "type": "revolute", "unit": "rad", "position_limits": [round(float(lo), 6), round(float(hi), 6)],
                 "velocity_limit": vmax, "effort_limit": fl, "group": "arm"}
            if n in rated:
                j.update({"rated_velocity": rated[n][0], "rated_effort": rated[n][1],
                          "rated_source": "Franka Emika Panda rated limits, as ManiSkill's Panda URDF states them"})
            j["note"] = ("the simulator applies velocity_limit (PhysX's joint speed cap) and effort_limit (its PD drive clips the torque "
                         "there); rated_* are the manufacturer's values")
            joints.append(j)
        hand = self._links.index("panda_hand")
        self._pm.compute_forward_kinematics(np.asarray(self.inst["robot_qpos"], np.float64))
        h_T_t = self._pm.get_link_pose(hand).inv() * self._pm.get_link_pose(self._tcp_idx)
        T = np.asarray(h_T_t.to_transformation_matrix(), np.float64).round(6) + 0.0      # float32 model; micrometre precision
        tool = {"calligraphy": "the brush tip: the tip of the unbent tuft", "mypaint": "the brush tip: the tip of the unbent tuft",
                "broad_nib": "the middle of the nib's writing edge (the edge lies along this frame's y axis)",
                "pointed_pen": "the pen's point (its tines spread along this frame's y axis)"}.get(self.medium, "the tool's tip")
        base = self._base
        return {"name": "franka-panda",
                "description": "Franka Emika Panda arm, 7 revolute joints, fixed base (ManiSkill 3.0.1 PandaStick: a rigid stick in place "
                               "of the gripper, the task's tool at its end)",
                "base": {"type": "fixed", "pose": [round(float(v), 6) + 0.0 for v in list(base.p) + list(base.q)]},   # float32 pose, to 1 um
                "joints": joints,
                "grippers": {},
                "controller": {"type": "joint-position PD per joint (ManiSkill pd_joint_pos: absolute targets, held for the 5 physics "
                                       "steps of a control step)", "control_hz": CONTROL_HZ, "physics_hz": SIM_HZ,
                               "gains": {n: {"stiffness": d[0], "damping": d[1]} for n, d in zip(JOINT_NAMES, self._drives)},
                               "note": "drive torque = stiffness * (target - q) - damping * qdot, clipped at effort_limit; the robot's "
                                       "links carry no gravity in this simulator"},
                "tcp": {TOOL_FRAME: {"parent_link": "panda_hand", "link_T_frame": T.tolist(),
                                     "definition": f"the tool point = {tool}, on the hand's z axis beyond the rigid stick; the TCP, the "
                                                   f"frame of the ee_pose action and of the proprio tip pose; the tool is fixed to "
                                                   f"the hand (no gripper)"}}}

    def _kin_request(self, body: dict) -> dict:
        """Validate a kinematics request (the limited /kinematics rules: ValueError on a malformed one) and fill its defaults."""
        if not isinstance(body, dict):
            raise ValueError("the request must be a dict")
        kin = self.kinematics_spec()

        def vec(x, n, what):
            a = None if x is None else np.asarray(x, np.float64).reshape(-1)
            if a is None or a.size != n or not np.all(np.isfinite(a)):
                raise ValueError(f"{what} must be {n} finite numbers")
            return a.tolist()

        def pose(x, what):
            p = vec(x, 7, what)
            nq = math.sqrt(sum(v * v for v in p[3:]))
            if nq < 1e-6:
                raise ValueError(f"{what}: quaternion has zero norm")
            return p[:3] + [v / nq for v in p[3:]]
        if body.get("base_pose") is not None:
            raise ValueError("base_pose is only accepted by a mobile robot (this one has a fixed base)")
        op = body.get("op")
        if op == "fk":
            links = body.get("links") or list(kin["links"])
            if not isinstance(links, list) or any(l not in kin["links"] for l in links):
                raise ValueError(f"links must be a list of names from {kin['links']}")
            return {"op": "fk", "q": vec(body.get("q"), ACTION_DIM, "q"), "links": links, "base_pose": None}
        if op == "ik":
            tg = body.get("targets")
            if not isinstance(tg, dict) or not tg or any(k not in kin["ik_targets"] for k in tg):
                raise ValueError(f"targets must map frames from {kin['ik_targets']} to poses")
            tp, tr, it = (float(body.get("tol_pos_m", IK_DEFAULTS["tol_pos_m"])), float(body.get("tol_rot_rad", IK_DEFAULTS["tol_rot_rad"])),
                          int(body.get("max_iters", IK_DEFAULTS["max_iters"])))
            if not (1e-5 <= tp <= 0.5 and 1e-4 <= tr <= 3.2 and 1 <= it <= 5000):
                raise ValueError("tol_pos_m in [1e-5, 0.5], tol_rot_rad in [1e-4, 3.2], max_iters in [1, 5000]")
            return {"op": "ik", "targets": {k: pose(v, f"targets[{k}]") for k, v in tg.items()},
                    "seed": None if body.get("seed") is None else vec(body["seed"], ACTION_DIM, "seed"), "base_pose": None,
                    "tol_pos_m": tp, "tol_rot_rad": tr, "max_iters": it}
        raise ValueError("op must be 'fk' or 'ik'")

    def kinematics(self, req: dict) -> dict:
        """Stateless forward / inverse kinematics of the robot's model (never reads or changes the simulator state, never steps):
          {"op": "fk", "q": q7, "links": [frames]?}  -> {"ok": True, "op": "fk", "frame": "world", "poses": {frame: [x,y,z, qw,qx,qy,qz]}}
          {"op": "ik", "targets": {"tip": pose7}, "seed": q7?, "tol_pos_m"?, "tol_rot_rad"?, "max_iters"?}
              -> {"ok", "op": "ik", "frame": "world", "q": q7 | None, "error": {"tip": {"pos_m", "rot_rad"}}}
        Frames: kinematics_spec()["links"] (the Panda's links and "tip", the tool point). IK starts from the seed (default: the start
        joint positions), clamps the result to the joint limits; ok = it meets both tolerances. Exactly the limited /kinematics answer."""
        import sapien
        r = self._kin_request(req)
        if r["op"] == "fk":
            poses = self._fk_frames(r["q"], r["links"])
            return {"ok": True, "op": "fk", "frame": "world", "poses": {k: [float(v) for v in p] for k, p in poses.items()}}
        seed = np.asarray(r["seed"] if r["seed"] is not None else self.inst["robot_qpos"], np.float64)
        (frame, tgt), = r["targets"].items()
        tgt = np.asarray(tgt, np.float64)
        pose = self._base.inv() * sapien.Pose(tgt[:3], tgt[3:])
        q, _, _ = self._pm.compute_inverse_kinematics(self._frame_index(frame), pose, initial_qpos=seed, active_qmask=[1] * ACTION_DIM,
                                                      eps=1e-6, max_iterations=int(r["max_iters"]))
        q = np.asarray(q, np.float64)[:ACTION_DIM]
        if not np.all(np.isfinite(q)):
            return {"ok": False, "op": "ik", "frame": "world", "q": None, "error": {frame: {"pos_m": None, "rot_rad": None}}}
        q = np.clip(q, self._qlim[:, 0], self._qlim[:, 1])
        got = self._fk_frames(q, [frame])[frame]
        ep = float(np.linalg.norm(got[:3] - tgt[:3]))
        er = 2.0 * math.acos(min(1.0, abs(float(np.dot(got[3:] / np.linalg.norm(got[3:]), tgt[3:])))))
        return {"ok": bool(ep <= r["tol_pos_m"] and er <= r["tol_rot_rad"]), "op": "ik", "frame": "world", "q": [float(v) for v in q],
                "error": {frame: {"pos_m": ep, "rot_rad": er}}}

    # ---- thin primitives (identical to rcb_paint's)
    def primitives(self) -> dict[str, Callable]:
        s = self

        def hold(steps: int = 10):
            """Keep the current joint targets for `steps` control steps."""
            for _ in range(int(steps)):
                s.step(s._targets)

        def set_joint_targets(q, steps: int = 1):
            """Command absolute joint targets q (7) and keep them for `steps` control steps."""
            for _ in range(int(steps)):
                s.step(np.asarray(q, np.float64))

        def move_joints(q, *, max_dq: float = 0.03, settle: int = 0):
            """Linear joint-space move from the current targets to q (7), at most `max_dq` rad per control step, then `settle` holds."""
            q = np.asarray(q, np.float64); q0 = s._targets.copy()
            n = max(1, int(math.ceil(float(np.max(np.abs(q - q0))) / max(1e-6, max_dq))))
            for k in range(1, n + 1):
                s.step(q0 + (q - q0) * k / n)
            hold(settle)
            return {"steps": n + settle}

        def move_tip(pos, quat_wxyz=None, *, speed: float = 0.05, settle: int = 0):
            """Straight-line move of the brush tip from where it is now to `pos` (world, m) at `speed` (m/s): one IK solve per control
            step (Pinocchio CLIK, warm-started, no collision checking), orientation slerped to `quat_wxyz` (default straight down).
            The PD controller lags behind moving targets; `settle` extra control steps hold the last target.
            Returns {steps, ik_failures, tip_error_mm}."""
            p1 = np.asarray(pos, np.float64)
            p0, q0 = s.tip_pose()
            q1 = s._down_quat if quat_wxyz is None else np.asarray(quat_wxyz, np.float64) / np.linalg.norm(quat_wxyz)
            n = max(1, int(math.ceil(float(np.linalg.norm(p1 - p0)) / max(1e-6, speed / CONTROL_HZ))))
            fails = 0
            for k in range(1, n + 1):
                t = k / n
                q, ok, _ = s.ik(p0 + (p1 - p0) * t, quat_slerp(q0, q1, t))
                if not ok:
                    fails += 1
                s.step(q if ok else s._targets)
            hold(settle)
            return {"steps": n + int(settle), "ik_failures": fails, "tip_error_mm": round(float(np.linalg.norm(s.tip_pose()[0] - p1)) * 1000, 3)}

        return {"hold": hold, "set_joint_targets": set_joint_targets, "move_joints": move_joints, "move_tip": move_tip,
                "ik": s.ik, "fk": s.fk, "tip_down_quat": s.tip_down_quat, "get_tip_pose": s.tip_pose, "get_joint_targets": s.hold_action}

    # ---- recording / trajectories
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        acts = np.stack(self._recording) if self._recording else np.zeros((0, ACTION_DIM), np.float32)
        self._recording = None
        _slog("record", task=self.task, n_actions=int(len(acts)))
        return acts.astype(np.float32)

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        np.savez(path, actions=np.asarray(actions, dtype=np.float32), task=self.task, instance_sha=self.instance_sha,
                 action_dim=ACTION_DIM, action_layout=ACTION_LAYOUT, control_hz=CONTROL_HZ, meta=json.dumps(meta or {}))

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        """reset(), then the actions open-loop; a stroke still pressed at the end is committed. Returns status() (incl. the score)."""
        self.reset()
        for a in np.asarray(actions, dtype=np.float32):
            self.step(a)
        self.painter.finish()
        st = self.status()
        _slog("replay", task=self.task, n_actions=int(len(actions)), final_reward=st["final_reward"])
        return st

    # ---- rendering
    def _sync(self) -> None:
        if self.painter.version != self._frame_version:
            for n in self.sheets:
                self.u.upload_sheet(n, self.painter.display(n))
            self.u.set_tuft_color(self.painter.brush_rgb())
            self._frame_version = self.painter.version

    def render_frame(self, camera: str = "canvas_cam", size: tuple[int, int] | None = None) -> np.ndarray:
        """RGB (H, W, 3) uint8 of one camera (VIDEO_CAMERAS) for the current state; "canvas" / "practice" = the exact sheet images."""
        if camera in ("canvas", "practice"):
            img = self.canvas("main" if camera == "canvas" else "practice")
        else:
            if not self.render_enabled:
                raise RuntimeError("rendering is unavailable in this process (no Vulkan device)")
            if camera not in self.VIDEO_CAMERAS:
                raise KeyError(f"unknown camera {camera!r}; known: {self.VIDEO_CAMERAS + ('canvas', 'practice')}")
            self._sync()
            self.u.scene.update_render(update_sensors=False, update_human_render_cameras=True)
            img = self.u.scene.get_human_render_camera_images(camera)[camera][0].cpu().numpy().astype(np.uint8)
        if size is not None and (img.shape[1], img.shape[0]) != tuple(size):
            from PIL import Image
            img = np.asarray(Image.fromarray(img).resize(tuple(size), Image.BILINEAR))
        return img

    def camera_params(self, camera: str) -> dict:
        """One camera's calibration now: intrinsic_cv (3x3), extrinsic_cv (3x4 world -> camera, OpenCV axes), cam2world_gl (4x4)."""
        cam = self.u.scene.human_render_cameras[camera]
        prm = cam.get_params()
        return {k: np.asarray(prm[k][0].cpu().numpy(), np.float64).tolist() for k in ("intrinsic_cv", "extrinsic_cv", "cam2world_gl")}

    def _camera(self, camera: str):
        if camera not in self.VIDEO_CAMERAS:
            raise KeyError(f"unknown camera {camera!r}; known: {self.VIDEO_CAMERAS}")
        if not self.render_enabled:
            raise RuntimeError("rendering is unavailable in this process (no Vulkan device)")
        return self.u.scene.human_render_cameras[camera]

    def camera_info(self, cameras=None) -> dict:
        """Calibration and mounting of the cameras (default: all of VIDEO_CAMERAS) for the current state, JSON-ready lists:
        {cam: {"intrinsic_cv": 3x3 K (OpenCV: u = fx X/Z + cx), "extrinsic_cv": 3x4 world -> camera (OpenCV axes: x right, y down,
        z forward), "cam2world_gl": 4x4 camera pose (OpenGL axes: x right, y up, z backward), "image_size": [W, H], "mount": {"type":
        "static", "extrinsic_cv", "cam2world_gl"}, "moves": False}}. All four cameras are static. Reads, never steps."""
        cams = self.VIDEO_CAMERAS if cameras is None else ((cameras,) if isinstance(cameras, str) else tuple(cameras))
        out = {}
        for c in cams:
            cfg = self._camera(c).config
            prm = self.camera_params(c)
            out[c] = {**prm, "image_size": [int(cfg.width), int(cfg.height)],
                      "mount": {"type": "static", "extrinsic_cv": prm["extrinsic_cv"], "cam2world_gl": prm["cam2world_gl"]}, "moves": False}
        return out

    def render_depth(self, camera: str = "canvas_cam") -> np.ndarray:
        """z-depth of one camera (VIDEO_CAMERAS) for the current state: float32 (H, W) metres along the optical axis (the Z of the
        OpenCV camera frame), the same pixel grid as render_frame(camera); 0 = no reading (nothing rendered within the camera's far
        plane). From the renderer's depth buffer, so it is geometry only: ink and paint are colours on the sheets and never show in
        it. Reads the state, never steps it."""
        self._camera(camera)
        self.u.scene.update_render(update_sensors=False, update_human_render_cameras=True)
        self.u.scene.human_render_cameras[camera].capture()
        return self._depth_of(camera)

    def _depth_of(self, camera: str) -> np.ndarray:
        """z-depth (see render_depth) of the camera's last capture (render_frame / render_depth), from its [0, 1] depth buffer."""
        cam = self.u.scene.human_render_cameras[camera]
        d = cam.camera.get_picture(["GbufferDepth"])[0]
        d = np.asarray(d.cpu().numpy() if hasattr(d, "cpu") else d, np.float64).reshape(int(cam.config.height), int(cam.config.width))
        n, f = float(cam.config.near), float(cam.config.far)
        z = n * f / (f - d * (f - n))                    # the perspective depth mapping inverted (d = 1: the far plane, nothing there)
        z[~(d < 1.0)] = 0.0
        return z.astype(np.float32)

    def render_grid(self, cameras: tuple[str, ...] = ("canvas_cam", "scene_cam", "side_cam", "canvas"), cols: int = 2,
                    size: tuple[int, int] = (320, 240)) -> np.ndarray:
        tiles = [self.render_frame(c, size=size) for c in cameras]
        while len(tiles) % cols:
            tiles.append(np.zeros_like(tiles[0]))
        return np.concatenate([np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)], axis=0)

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 2, fps: int = 10,
                     cameras: tuple[str, ...] = ("canvas_cam", "scene_cam", "side_cam", "canvas"), cols: int = 2,
                     size: tuple[int, int] = (320, 240)) -> dict[str, Any]:
        """Replay `actions` from the frozen instance and write an MP4 tiling `cameras`, one frame every `every` control steps,
        and `<path>.last.png`. Returns the final status plus n_frames."""
        import imageio.v2 as imageio
        if not self.render_enabled:
            cameras = tuple(c for c in cameras if c in ("canvas", "practice")) or ("canvas",)
        self.reset()
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            last = self.render_grid(cameras, cols=cols, size=size); w.append_data(last); n += 1
            A = np.asarray(actions, dtype=np.float32)
            for i, a in enumerate(A):
                self.step(a)
                if (i + 1) % every == 0 or i == len(A) - 1:
                    if i == len(A) - 1:
                        self.painter.finish()
                    last = self.render_grid(cameras, cols=cols, size=size); w.append_data(last); n += 1
        self.painter.finish()
        imageio.imwrite(str(path.with_suffix(".last.png")), last)
        return {**self.status(), "n_frames": n, "video": str(path)}

    # ---- oracle / bookkeeping
    def exec_code(self, code: str, extra: dict | None = None) -> dict[str, Any]:
        ns = {"s": self, "session": self, "p": self.primitives(), "np": np, "math": math, **(extra or {})}
        exec(compile(code, "<oracle>", "exec"), ns)
        return ns

    def _log_end(self) -> None:
        if not self._end_logged:
            self._end_logged = True
            _slog("session_end", task=self.task, sim_steps=int(self._total_steps + self.n_steps), resets=self._resets)

    def close(self) -> None:
        self._log_end()
        try:
            self.env.close()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- instance + CLI
def _versions() -> dict:
    out = {}
    for mod in ("mani_skill", "sapien", "torch", "numpy", "scipy"):
        try:
            m = __import__(mod); out[mod] = getattr(m, "__version__", "?")
        except Exception:  # noqa: BLE001
            out[mod] = None
    return out


def default_sheets() -> list[dict]:
    px = PAPER_SIDE_M / SHEET_PX
    return [{"name": "main", "center_xy": list(PAPER_CENTER), "rows": SHEET_PX, "cols": SHEET_PX, "px_m": px, "z": PAPER_Z, "scored": True},
            {"name": "practice", "center_xy": list(PRACTICE_CENTER), "rows": PRACTICE_PX[0], "cols": PRACTICE_PX[1], "px_m": px, "z": PAPER_Z,
             "scored": False}]


def _load_traj(path: str) -> dict[str, Any]:
    d = np.load(path, allow_pickle=False)
    return {k: d[k] for k in d.files}


def cmd_replay(a) -> None:
    d = _load_traj(a.traj)
    s = Session(instance=a.instance, render=bool(a.video), max_steps=None)
    acts = np.asarray(d["actions"], np.float32)
    t0 = time.time()
    video_error = None
    if a.video:
        try:
            st = s.render_video(acts, a.video, every=max(a.every, int(math.ceil(len(acts) / MAX_VIDEO_FRAMES))), fps=a.fps)
        except Exception as exc:  # noqa: BLE001 — e.g. "cannot create buffer" when the GPU's memory is full: the video is optional
            video_error = repr(exc)[:300]
            _log(f"replay video failed ({video_error}); replaying without cameras (the state does not depend on rendering)")
            st = s.replay(acts)
    else:
        st = s.replay(acts)
    if video_error:
        st["video_error"] = video_error
    st["replay_wall_s"] = round(time.time() - t0, 2)
    if a.canvas_out:
        from PIL import Image
        Image.fromarray(s.canvas("main")).save(a.canvas_out)
        Image.fromarray(s.canvas("practice")).save(str(Path(a.canvas_out).with_name(Path(a.canvas_out).stem + "_practice.png")))
        if s.medium == "mypaint":        # the paint coverage of the main sheet (to freeze a painted canvas as a painting target)
            np.savez_compressed(str(Path(a.canvas_out).with_name(Path(a.canvas_out).stem + "_alpha.npz")),
                                alpha=np.round(np.clip(s.ink("main"), 0, 1) * 255).astype(np.uint8))
    print(json.dumps({"replays": [st], "instance_exact": s.instance_exact, "instance_matches": s.instance_matches, "instance_sha": s.instance_sha,
                      "n_actions": int(len(acts)), "versions": _versions()}))
    s.close()


def cmd_render(a) -> None:
    d = _load_traj(a.traj)
    s = Session(instance=a.instance)
    print(json.dumps(s.render_video(np.asarray(d["actions"], np.float32), a.out, every=a.every, fps=a.fps)))
    s.close()


def cmd_run_oracle(a) -> None:
    s = Session(instance=a.instance, render=False)
    s.record_start()
    s.exec_code(open(a.code).read())
    acts = s.record_stop()
    s.painter.finish()
    live = s.status()
    s.save_trajectory(acts, a.out, meta={"source": "oracle", "code": os.path.basename(a.code)})
    rep = s.replay(acts)
    print(json.dumps({"n_actions": int(len(acts)), "live": live, "replay": rep, "live_matches_replay": live["state_sha"] == rep["state_sha"]}))
    s.close()


def cmd_selftest(a) -> None:
    """(1) in-process replay x2 == fresh-process replay x2 (state hash), (2) the footprint renderer is order-independent where it must be."""
    s = Session(instance=a.instance, render=False)
    out = {}
    if a.traj:
        acts = np.asarray(_load_traj(a.traj)["actions"], np.float32)
        shas = [s.replay(acts)["state_sha"] for _ in range(2)]
        out["inprocess_replays"] = shas
        import subprocess
        fresh = []
        for _ in range(2):
            p = subprocess.run([sys.executable, os.path.abspath(__file__), "replay", "--instance", a.instance, "--traj", a.traj],
                               capture_output=True, text=True, env={**os.environ, "RCB_SESSION_LOG": ""})
            lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
            fresh.append(json.loads(lines[-1])["replays"][0]["state_sha"] if lines else f"rc={p.returncode}")
        out["fresh_replays"] = fresh
        out["deterministic"] = len(set(shas + fresh)) == 1
    out["pass"] = out.get("deterministic", True)
    print(json.dumps(out))
    s.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("replay"); q.add_argument("--task"); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--video"); q.add_argument("--every", type=int, default=2); q.add_argument("--fps", type=int, default=10); q.add_argument("--canvas-out")
    q = sub.add_parser("render"); q.add_argument("--task"); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--out", required=True); q.add_argument("--every", type=int, default=2); q.add_argument("--fps", type=int, default=10)
    q = sub.add_parser("run-oracle"); q.add_argument("--task"); q.add_argument("--instance", required=True); q.add_argument("--code", required=True); q.add_argument("--out", required=True)
    q = sub.add_parser("selftest"); q.add_argument("--instance", required=True); q.add_argument("--traj")
    a = p.parse_args()
    {"replay": cmd_replay, "render": cmd_render, "run-oracle": cmd_run_oracle, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
