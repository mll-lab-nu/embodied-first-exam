"""Relative disassembly route (silver relative to gold), ported from the old simplified oracle.

Source: ``topogym/planning/cast_keyhole/simplified_policy.py`` (``route_displacements``, ``channel_guides``,
``bar_point``, ``transverse_rotation``, ``align_to_channel``, ``extract_from_channel``).

All poses are of the PLATE frames (authored outline frame, scaled metres): a relative configuration is
(R, c) = silver plate rotation in the gold plate frame, and the silver bar point (plate (0,-25.65,0)*scale)
expressed in the gold plate frame.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

import keyhole_geometry as kg


def route_displacements(tier, scale=3.):
    if tier == "very_easy":
        points = [(-3.65, 5.), (-3.65, -45.)]
    elif tier == "easier":
        points = [(-3.65, 5.), (-3.65, -3.), (3.5, -3.), (3.5, -20.), (-3.65, -20.), (-3.65, -45.)]
    else:
        raise ValueError(tier)
    points = np.asarray(points, float)
    return np.c_[(points - points[0]) * scale / 1000., np.zeros(len(points))]


def channel_guides(tier, scale=3.):
    entry = np.asarray([(0., 21.35, 0.), (-2.875, 12., 0.), (-2.875, 6.5, 0.), (-3.65, 5., 0.)]) * scale / 1000.
    return np.vstack((entry, entry[-1] + route_displacements(tier, scale)[1:]))


def bar_point(scale=3.):
    return np.array([0., -25.65, 0.]) * scale / 1000.


def plate_rotations(record):
    t = kg.plate_assembly_transforms(record)
    return {n: Rotation.from_matrix(t[n][:3, :3]) for n in kg.NAMES}, {n: t[n][:3, 3] for n in kg.NAMES}


def nominal_relative(record):
    """Start relative configuration (R_rel, bar point in gold plate frame)."""
    rot, pos = plate_rotations(record)
    r_rel = rot["gold"].inv() * rot["silver"]
    c = rot["gold"].inv().apply(pos["silver"] + rot["silver"].apply(bar_point(record["scale"])) - pos["gold"])
    return r_rel, c


def route(record, tier, turn_sign=+1, n_turn=60, step_m=.0005):
    """Dense list of (R_rel, c) along: turn 45 deg, turn to 90 deg (about the gold normal through the bar
    point), then the channel guides. turn_sign=-1 is the mirrored key turn."""
    r0, c0 = nominal_relative(record)
    scale = record["scale"]
    guides = channel_guides(tier, scale)
    mid = Rotation.from_euler("z", turn_sign * 45, degrees=True) * r0
    final = Rotation.from_euler("z", turn_sign * 90, degrees=True) * r0
    out = []
    # stage 1 and 2 (old: stand_and_turn_silver, turn_silver_to_channel); bar point moves c0 -> guides[0]
    seg = [(r0, mid), (mid, final)]
    for k, (a, b) in enumerate(seg):
        s = Slerp([0, 1], Rotation.from_quat([a.as_quat(), b.as_quat()]))
        for u in np.linspace(0, 1, n_turn + 1)[(1 if k else 0):]:
            frac = (k + u) / 2
            out.append((s(u), c0 + frac * (guides[0] - c0), f"turn{k}"))
    last = guides[0]
    for i, g in enumerate(guides[1:]):
        n = max(2, int(np.ceil(np.linalg.norm(g - last) / step_m)))
        for u in np.linspace(0, 1, n + 1)[1:]:
            out.append((final, last + u * (g - last), f"channel{i}"))
        last = g
    return out


def silver_plate_pose_in_gold(r_rel, c, scale=3.):
    """Silver plate origin in the gold plate frame for a relative configuration."""
    return c - r_rel.apply(bar_point(scale))
