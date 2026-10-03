"""Approved single-span Buzz Wire layouts at the easy toy's physical scale.

The endpoints, deck and wand come from the current easy layout. Only the wire
between the vertical entry and exit is replaced; all coordinates are metres.
"""

from dataclasses import replace

import numpy as np
from scipy.interpolate import BPoly

from .buzz_wire_3d import BuzzWireLayout


def _sideways_down_wave(u, amplitude):
    """Keep the first sine lobe sideways and turn the second lobe downward.

    A short C2 bridge joins the different bending planes without the sharp
    corner that rotating just one half at the sine's zero crossing would make.
    """
    phase = u * u * (3 - 2 * u)
    wave = amplitude * np.sin(2 * np.pi * phase)
    offsets = np.c_[np.maximum(wave, 0.), np.minimum(wave, 0.)]
    join = np.array([.4, .6])
    angle = 2 * np.pi * join * join * (3 - 2 * join)
    rate = 12 * np.pi * join * (1 - join)
    acceleration = 12 * np.pi * (1 - 2 * join)
    value = amplitude * np.sin(angle)
    first = amplitude * np.cos(angle) * rate
    second = amplitude * (np.cos(angle) * acceleration - np.sin(angle) * rate ** 2)
    bridge = BPoly.from_derivatives(join, [
        [[value[0], 0.], [first[0], 0.], [second[0], 0.]],
        [[0., value[1]], [0., first[1]], [0., second[1]]],
    ])
    middle = (u >= join[0]) & (u <= join[1])
    offsets[middle] = bridge(u[middle])
    return offsets


def simplified_layout(reference: BuzzWireLayout, difficulty: str) -> BuzzWireLayout:
    """Build an elevated straight span or sideways-then-down sine-like lobes.

    The easier span has one horizontal lobe and one vertical downward lobe.
    No frozen orientation/offset witness from the old maze is reused.
    """
    if difficulty not in {"very_easy", "easier"}:
        raise ValueError(f"Unknown simplified Buzz Wire difficulty: {difficulty!r}")
    original = np.asarray(reference.authored_controls_m, dtype=float)
    start, finish = original[[0, -1]]
    if not np.allclose(start[1:], finish[1:]) or finish[0] <= start[0]:
        raise ValueError("Simplified routes require the easy layout's aligned endpoints")
    top = float(original[:, 2].max())
    radius = .040
    amplitude = .035 if difficulty == "easier" else 0.
    x0, x1, y = float(start[0]), float(finish[0]), float(start[1])
    shoulder = top - radius
    if shoulder <= start[2] or x1 - x0 <= 2 * radius:
        raise ValueError("Easy route is too small for the rounded single-span layout")

    points, sections = [], []

    def append(name, coordinates):
        rows = np.asarray(coordinates, dtype=float)
        if points:
            if not np.allclose(points[-1], rows[0], atol=1e-12, rtol=0):
                raise ValueError("Simplified route sections must meet")
            rows = rows[1:]
        points.extend(map(tuple, rows))
        sections.append((name, len(points) - 1))

    z = np.linspace(start[2], shoulder, 80)
    append("start_post", np.c_[np.full_like(z, x0), np.full_like(z, y), z])
    angle = np.linspace(0., np.pi / 2, 64)
    append("entry_elbow", np.c_[x0 + radius * (1 - np.cos(angle)),
                                np.full_like(angle, y), shoulder + radius * np.sin(angle)])
    u = np.linspace(0., 1., 301)
    offsets = _sideways_down_wave(u, amplitude) if amplitude else np.zeros((len(u), 2))
    append("sideways_then_down" if amplitude else "straight_span",
           np.c_[x0 + radius + u * (x1 - x0 - 2 * radius),
                 y + offsets[:, 0], top + offsets[:, 1]])
    append("exit_elbow", np.c_[x1 - radius + radius * np.sin(angle),
                               np.full_like(angle, y), shoulder + radius * np.cos(angle)])
    z = np.linspace(shoulder, finish[2], 80)
    append("finish_post", np.c_[np.full_like(z, x1), np.full_like(z, y), z])
    layout = replace(reference, template_id="authored_multistage_v1",
                     authored_controls_m=tuple(points), authored_section_ends=tuple(sections),
                     orientation_knots_wxyz=(), center_offset_knots_m=())
    layout.validate()
    return layout
