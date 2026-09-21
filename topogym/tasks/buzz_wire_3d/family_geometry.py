"""Deterministic family geometry, derived from the authored designs."""

from pathlib import Path
import numpy as np
import yaml

COLORS = ["entry", "middle", "exit", "final"]


def clean(points):
    points = np.asarray(points, dtype=float)
    return points[np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 1e-10]]


def line(a, b):
    return np.linspace(a, b, 60)


def vertical_wave_controls(spec):
    """Two or three authored arches with one smooth fore/aft excursion.

    The end posts are part of the same open wire. Depth is a smooth function
    of horizontal travel, so the vertical legs retain vertical tangents.
    """
    prototype = spec["prototypes"][spec["default_prototype"]]
    p = prototype["nominal"]
    count = prototype["fixed_structure"]["peak_count"]
    radius = p["turn_radius_m"]
    low, high = p["low_height_m"], p["high_height_m"]
    depth = p["depth_span_m"]
    if count not in (2, 3) or radius <= 0 or high - low < 2 * radius + 0.020:
        raise ValueError("Vertical wave needs distinct arches and connecting legs")
    left = -(2 * count - 1) * radius
    x = left
    controls = line([x, 0, 0.040], [x, 0, high - radius])
    ends = [["start_post", len(controls) - 1]]
    for index in range(2 * count - 1):
        peak = index % 2 == 0
        z = high - radius if peak else low + radius
        theta = np.linspace(np.pi, 0 if peak else 2 * np.pi, 120)
        arc = np.c_[
            x + radius + radius * np.cos(theta),
            np.zeros_like(theta),
            z + radius * np.sin(theta),
        ]
        controls = clean(np.vstack([controls, line(controls[-1], arc[0]), arc]))
        label = f"arch_{index // 2 + 1}" if peak else f"valley_{index // 2 + 1}"
        ends.append([label, len(controls) - 1])
        x += 2 * radius
    controls = clean(np.vstack([controls, line(controls[-1], [x, 0, 0.040])]))
    ends.append(["finish_post", len(controls) - 1])
    fraction = (controls[:, 0] - left) / (-2 * left)
    controls[:, 1] = -depth / 2 * np.cos(2 * np.pi * fraction)
    return controls, ends


def comb(stage):
    p, place = stage["nominal"], stage["sketch_placement"]
    r, x, lo = p["turn_radius_m"], place["start_x_m"], place["y_min_m"]
    hi, z = lo + p["straight_run_m"], p["height_m"]
    pieces = [line([x, lo, z], [x, hi, z])]
    for i in range(stage["return_count"]):
        y = hi if i % 2 == 0 else lo
        t = np.linspace(np.pi, 0 if i % 2 == 0 else 2 * np.pi, 90)
        pieces.append(
            np.c_[x + r + r * np.cos(t), y + r * np.sin(t), np.full_like(t, z)]
        )
        x += 2 * r
        end_y = lo if i % 2 == 0 else hi
        if i == stage["return_count"] - 1:
            end_y = lo + 0.55 * p["straight_run_m"]
        pieces.append(line(pieces[-1][-1], [x, end_y, z]))
    return clean(np.concatenate(pieces))


def eight(stage):
    p, place = stage["nominal"], stage["sketch_placement"]
    cut = np.deg2rad(p["end_cut_angle_deg"])
    t = np.linspace(1.5 * np.pi - cut, -0.5 * np.pi + cut, 800)
    return np.c_[
        place["center_x_m"] + p["right_lobe_extent_m"] * np.sin(t),
        place["center_y_m"] + p["depth_span_m"] / 2 * np.sin(2 * t),
        p["center_height_m"] + p["crossing_height_gap_m"] / 2 * np.cos(t),
    ]


def w_valleys(stage):
    p, place = stage["nominal"], stage["sketch_placement"]
    r, low, high = p["turn_radius_m"], p["low_height_m"], p["high_height_m"]
    x, y = place["start_x_m"], p["front_y_m"]
    pieces = [line([x, y, high - 0.010], [x, y, low + r])]
    for i in range(3):
        bottom = i % 2 == 0
        z = low + r if bottom else high - r
        t = np.linspace(np.pi, 2 * np.pi if bottom else 0, 90)
        start = np.array([x, y, z])
        pieces.append(line(pieces[-1][-1], start))
        pieces.append(
            np.c_[x + r + r * np.cos(t), np.full_like(t, y), z + r * np.sin(t)]
        )
        x += 2 * r
    pieces.append(line(pieces[-1][-1], [x, y, high - 0.010]))
    return clean(np.concatenate(pieces))


def omega(stage, sweep):
    p, place = stage["nominal"], stage["sketch_placement"]
    t = np.deg2rad(
        np.linspace(place["start_angle_deg"], place["start_angle_deg"] + sweep, 250)
    )
    return np.c_[
        np.full_like(t, place["plane_x_m"]),
        p["center_y_m"] + p["radius_m"] * np.cos(t),
        p["center_height_m"] + p["radius_m"] * np.sin(t),
    ]


def coil(stage, turns):
    p, place = stage["nominal"], stage["sketch_placement"]
    alpha = np.deg2rad(p["plane_tilt_deg"])
    axis = np.array([np.cos(alpha), 0, np.sin(alpha)])
    u = np.array([0, 1, 0])
    v = np.cross(axis, u)
    s = np.linspace(0, 1, 250)
    t = np.deg2rad(place["start_angle_deg"]) + turns * 2 * np.pi * s
    return (
        np.asarray(place["center_m"])
        + s[:, None] * p["axial_advance_m"] * axis
        + p["radius_m"] * (np.cos(t)[:, None] * u + np.sin(t)[:, None] * v)
    )


def join(a, b, handle):
    da, db = a[-1] - a[-2], b[1] - b[0]
    controls = [
        a[-1],
        a[-1] + handle * da / np.linalg.norm(da),
        b[0] - handle * db / np.linalg.norm(db),
        b[0],
    ]
    t = np.linspace(0, 1, 100)[:, None]
    return (
        (1 - t) ** 3 * controls[0]
        + 3 * (1 - t) ** 2 * t * controls[1]
        + 3 * (1 - t) * t**2 * controls[2]
        + t**3 * controls[3]
    )


def compose(path):
    spec = yaml.safe_load(Path(path).read_text())
    proto = spec["prototypes"][spec["default_prototype"]]
    curves = []
    for name in proto["stage_order"]:
        stage = proto["stages"][name]
        motif = stage["motif"]
        if motif == "horizontal_parallel_returns":
            points = comb(stage)
        elif motif == "open_over_under_figure_eight":
            points = eight(stage)
        elif motif == "two_valleys_and_one_crest":
            points = w_valleys(stage)
        elif motif == "open_omega_return":
            points = omega(stage, proto["fixed_structure"]["omega_sweep_deg"])
        elif motif == "inclined_open_helix":
            points = coil(stage, proto["fixed_structure"]["coil_turns"])
        else:
            raise ValueError(motif)
        curves.append((name, points))
    pieces = []
    for i, (name, points) in enumerate(curves):
        if i:
            connector = join(
                curves[i - 1][1], points, proto["nominal"]["connector_handle_m"]
            )
            pieces.append(("connector", connector, "#8b9298"))
        pieces.append((name, points, COLORS[i]))
    return spec, proto, pieces
