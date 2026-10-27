"""Scripted expert geometry of the dough tasks (pure numpy): tool-frame waypoints from the episode's plan.

A *script* is a list of steps ``{"op": "close" | "open"}``, ``{"op": "wait", "ticks": n}`` or
``{"op": "move", "xyz": [x, y, z], "yaw": rad, "label": str}``: the tool's working-face pose in the env-local frame (tool +z up,
yawed about z; the scraper's blade normal is its +x).  The policy turns them into end-effector targets via :func:`eef_for_tool`.
"""

from __future__ import annotations

import math
from typing import Dict, List

import numpy as np


def quat_mul(a, b):
    """Hamilton product of wxyz quaternions."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ]
    )


def quat_conj(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


def quat_rotate(q, v):
    w, x, y, z = q
    u = np.array([x, y, z])
    v = np.asarray(v, float)
    return v + 2.0 * np.cross(u, np.cross(u, v) + w * v)


def yaw_quat(yaw: float):
    return np.array([math.cos(0.5 * yaw), 0.0, 0.0, math.sin(0.5 * yaw)])


def eef_for_tool(tool_xyz, tool_yaw: float, rel_pos, rel_quat):
    """Eef pose (xyz, wxyz) that puts the tool's working face at ``tool_xyz`` with its z up, yawed ``tool_yaw``.

    ``rel_pos`` / ``rel_quat``: the tool frame in the eef frame (the grip transform)."""
    tq = yaw_quat(tool_yaw)
    eq = quat_mul(tq, quat_conj(rel_quat))
    eq = eq / np.linalg.norm(eq)
    epos = np.asarray(tool_xyz, float) - quat_rotate(eq, rel_pos)
    return epos, eq


def press_script(plan: Dict, p: Dict) -> List[Dict]:
    """Press the strip A->B: hover above A, press to the target thickness, dwell, move laterally to B, dwell, lift.

    ``plan``: the scene info (press_a_*, press_b_*, anchor); ``p``: the task params (target_thickness, hover ...)."""
    anc = np.asarray(plan["anchor"], float)
    a = np.array([plan["press_a_x"], plan["press_a_y"]]) + anc[:2]
    b = np.array([plan["press_b_x"], plan["press_b_y"]]) + anc[:2]
    z0 = float(anc[2])
    hover = z0 + float(p.get("hover", 0.045))
    z_press = z0 + float(p.get("target_thickness", 0.010)) - float(p.get("press_bias", 0.0))
    yaw = float(np.deg2rad(p.get("tool_yaw_deg_cmd", 0.0)))
    steps = [
        {"op": "close", "label": "grip"},
        {"op": "move", "xyz": [a[0], a[1], hover], "yaw": yaw, "label": "hover_a"},
        {"op": "move", "xyz": [a[0], a[1], z_press], "yaw": yaw, "label": "press"},
        {"op": "wait", "ticks": int(p.get("dwell_ticks", 20)), "label": "dwell"},
        {"op": "move", "xyz": [b[0], b[1], z_press], "yaw": yaw, "label": "drag"},
        {"op": "wait", "ticks": int(p.get("dwell_ticks", 20)), "label": "dwell2"},
        {"op": "move", "xyz": [b[0], b[1], z0 + float(p.get("lift_z", 0.07))], "yaw": yaw, "label": "lift"},
    ]
    return steps


def pickup_steps(plan: Dict, p: Dict, yaw: float) -> List[Dict]:
    """Pick the tool out of its rack (``tool_pickup``): open, hover above the tool's live start pose (``plan['tool_start']``,
    env-local xyz + wxyz), descend so the nominal grip lands on the handle, close for real, lift it clear of the groove.
    Moves before the close are ``free``: the tool is not in the hand yet, so the policy checks the hand, not the tool, against
    them.  ``measure_grip`` on the lift: from there on the moves use the measured tool-in-hand pose."""
    t = np.asarray(plan["tool_start"], float)
    x, y, z = (float(v) for v in t[:3])
    up = float(p.get("pickup_hover", 0.06))
    clear = float(p.get("pickup_lift", 0.04))  # the groove is 10 mm deep: 40 mm lifts the blade well clear of the rails
    return [
        {"op": "open", "label": "open"},
        {"op": "move", "xyz": [x, y, z + up], "yaw": yaw, "free": True, "label": "pregrasp"},
        {"op": "move", "xyz": [x, y, z], "yaw": yaw, "free": True, "label": "grasp"},
        {"op": "close", "pickup": True, "label": "grip"},
        {"op": "move", "xyz": [x, y, z + clear], "yaw": yaw, "measure_grip": True, "label": "lift_tool"},
    ]


def fill_script(plan: Dict, p: Dict) -> List[Dict]:
    """Scrape the heap over the tray: blade behind the heap, down to ``blade_z``, push along the tray, lift, optional return
    level pass.  The blade normal (tool +x) points along the push direction."""
    anc = np.asarray(plan["anchor"], float)
    ix = float(plan["inner_x"])
    side = float(plan["side"])  # heap on the +x (side > 0) or -x side: push toward the other side
    z0 = float(anc[2])
    hover = z0 + float(p.get("hover", 0.05))
    level = float(plan["fill_level"])
    z_cut = z0 + float(p.get("blade_z", max(0.004, level * float(p.get("blade_level_frac", 1.0)))))
    z_end = z0 + float(
        p.get("blade_z_end", z_cut - z0)
    )  # the blade height at the far end: a ramp spreads the deposit evenly
    direction = np.array([-side, 0.0])
    # the blade is a symmetric plate: its normal along +-push, so yaw is only needed modulo pi (a 180 deg wrist turn is out of reach)
    yaw = math.atan2(direction[1], direction[0])
    yaw = yaw - math.pi if yaw > 0.5 * math.pi + 1e-9 else yaw + math.pi if yaw < -0.5 * math.pi - 1e-9 else yaw
    start = anc[:2] + np.array([side * (0.5 * ix - float(p.get("start_margin", 0.0))), 0.0])
    # start behind the heap's back wall edge (inside the tray), end short of the far wall
    far = anc[:2] + np.array([-side * (0.5 * ix - float(p.get("end_margin", 0.012))), 0.0])
    steps = pickup_steps(plan, p, yaw) if p.get("tool_pickup", False) else [{"op": "close", "label": "grip"}]
    for k in range(int(p.get("passes", 1))):
        steps += [
            # a picked-up tool creeps a few mm down in the gel grip on every push (compliant contact): re-measure the grip in the air before each pass
            {
                "op": "move",
                "xyz": [start[0], start[1], hover],
                "yaw": yaw,
                "label": f"hover_start{k}",
                **({"measure_grip": True} if p.get("tool_pickup", False) else {}),
            },
            {"op": "move", "xyz": [start[0], start[1], z_cut], "yaw": yaw, "label": f"lower{k}"},
            {"op": "move", "xyz": [far[0], far[1], z_end], "yaw": yaw, "label": f"push{k}"},
            {"op": "wait", "ticks": int(p.get("dwell_ticks", 15)), "label": f"dwell{k}"},
            {"op": "move", "xyz": [far[0], far[1], hover], "yaw": yaw, "label": f"lift_far{k}"},
        ]
    if p.get("return_pass", False):
        z2 = z0 + float(p.get("level_pass_z", level))
        steps += [
            {"op": "move", "xyz": [start[0], start[1], hover], "yaw": yaw, "label": "return"},
            {"op": "move", "xyz": [start[0], start[1], z2], "yaw": yaw, "label": "lower2"},
            {"op": "move", "xyz": [far[0] * 0.5 + start[0] * 0.5, far[1], z2], "yaw": yaw, "label": "level"},
        ]
    last = next(st["xyz"] for st in reversed(steps) if st["op"] == "move")
    steps.append(
        {"op": "move", "xyz": [last[0], last[1], z0 + float(p.get("lift_z", 0.07))], "yaw": yaw, "label": "lift"}
    )
    return steps


def plug_script(plan: Dict, p: Dict) -> List[Dict]:
    """Carrier variant of the plug insertion: grip the carrier, hover with the plug 2 cm above the hole, descend until the plug is
    seated, optionally release the plug and withdraw.  The tool frame = the carrier's bottom face = the plug's top face."""
    anc = np.asarray(plan["anchor"], float)  # hole centre at the hole's top face height
    hole = anc[:2] + np.array([plan.get("hole_x", 0.0), plan.get("hole_y", 0.0)])
    length = float(p.get("plug_size", [0.018, 0.018, 0.030])[2])
    depth = float(plan["hole_depth"])
    z_top = float(anc[2])
    z_hover = z_top + length + float(p.get("hover_gap", 0.02))
    z_seat = z_top + length - depth + float(p.get("seat_margin", 0.001)) - float(p.get("press_bias", 0.0))
    steps = [
        {"op": "close", "label": "grip"},
        {"op": "move", "xyz": [hole[0], hole[1], z_hover], "yaw": 0.0, "label": "hover"},
        {"op": "move", "xyz": [hole[0], hole[1], z_top + length + 0.002], "yaw": 0.0, "label": "approach"},
        {"op": "move", "xyz": [hole[0], hole[1], z_seat], "yaw": 0.0, "label": "insert"},
        {"op": "wait", "ticks": int(p.get("dwell_ticks", 15)), "label": "dwell"},
    ]
    if p.get(
        "release_plug", False
    ):  # optional: let go (the released rubber plug may spring back out of the hole) and withdraw
        steps += [
            {"op": "open", "attach": True, "label": "release"},
            {"op": "move", "xyz": [hole[0], hole[1], z_hover + 0.03], "yaw": 0.0, "label": "retreat"},
        ]
    return steps
