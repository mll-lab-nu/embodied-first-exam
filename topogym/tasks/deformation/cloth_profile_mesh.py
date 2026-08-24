"""Control meshes for cloth that does not start out flat.

`cloth_fold.cloth_sheet_mesh` covers the one case where the cloth lies flat.
docx 1.2, 1.3 and 1.5 all start from cloth that is folded, rolled or gathered,
and geometrically they are the same construction: a polyline in the
material-height plane swept sideways. This file is that construction. docx 1.2's pleat and 1.3's spiral are both
profiles here; 1.5's gathered stack is the same call with a third polyline.

**Every edge is held to the same length.** Genesis remeshes the control mesh
isotropically to `PBDOptions.particle_size`, and vertex order surviving that
remesh is what makes layer counting and material conservation measurable at all
(the reasoning, and the measurements behind it, are in
`configs/task_configs/cloth_fold_topogym_tabletop_v1.yaml`). A profile sampled
at a uniform arc length keeps the mesh as close to the flat sheet's regular grid
as a folded shape can be.

Corners are always sampled exactly, by giving each straight segment its own
whole number of intervals rather than walking one global spacing along the whole
polyline. A crease that falls between two samples gets rounded off, and the
creases ARE the pleat -- rounding one off shortens the material and moves the
point the gripper is supposed to pinch. The cost is that segment spacings differ
by a few percent from each other; `edge_report` prints the spread so it can be
read against `particle_size` rather than assumed small.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np


def resample_polyline(corners, spacing: float) -> np.ndarray:
    """Samples along a polyline, uniform within each segment, corners included.

    ``spacing`` is a target: each segment takes the whole number of intervals
    closest to it, so the corners stay on the sampled path.
    """

    corners = np.asarray(corners, dtype=float)
    if corners.ndim != 2 or len(corners) < 2:
        raise ValueError(f"need at least two corners, got shape {corners.shape}.")
    if spacing <= 0.0:
        raise ValueError(f"spacing must be positive, got {spacing}.")

    samples = [corners[0]]
    for start, end in zip(corners[:-1], corners[1:]):
        length = float(np.linalg.norm(end - start))
        if length <= 0.0:
            raise ValueError("polyline has a zero-length segment.")
        intervals = max(1, int(round(length / float(spacing))))
        for step in range(1, intervals + 1):
            samples.append(start + (end - start) * (step / intervals))
    return np.asarray(samples, dtype=float)


def polyline_length(points) -> float:
    points = np.asarray(points, dtype=float)
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def pleat_profile(
    *, material_length: float, pleat_width: float, crest_height: float, rest_z: float
) -> np.ndarray:
    """Corners of a band carrying one standing pleat, in material order.

    The shape is a knife pleat that has not been pressed down: the band runs
    along the table, doubles back and upward to a crest, comes back down past the
    crease and continues. Written as (material, z): the first coordinate runs
    along the band and is already centred on its plan-view middle, the second is
    height above the table. Which world axis the material ends up on is
    `sweep_profile_mesh`'s business, not this function's.

    ::

                       crest (the gripper pinches this edge)
                        /\\
              arm_up   /  \\  arm_down
                      /    \\
        --------------+     +------------------
          lead-in   crease            tail

    In plan view the span between the crest and the crease carries three layers
    -- the lead-in underneath, and both arms over it -- which is docx 1.2's
    「局部三层重叠」. Everything either side of it carries one.

    The material stored in the pleat is ``material_length`` minus the plan span,
    and it is what a successful unfold has to give back: docx 1.2's 「材料守恒使
    『褶皱消失』与『长度恢复』严格绑定」. It is not a free parameter -- it follows
    from the two arms, which follow from ``pleat_width`` and ``crest_height``.
    """

    width, height = float(pleat_width), float(crest_height)
    if width <= 0.0 or height <= 0.0:
        raise ValueError("pleat_width and crest_height must both be positive.")

    arm_up = math.hypot(width, height)
    arm_down = math.hypot(2.0 * width, height)
    # Chosen so the pleat sits in the middle of the band: the flat runs either
    # side differ by exactly the plan width the pleat occupies past the crease.
    lead = 0.5 * (float(material_length) - arm_up - arm_down + width)
    tail = lead - width
    if tail <= 0.0:
        raise ValueError(
            f"material_length={material_length} is too short for a pleat of "
            f"width={width} height={height}: it leaves no flat band past the "
            f"crest (needs more than {arm_up + arm_down + width:.4f} m)."
        )

    return np.array(
        [
            [-lead, rest_z],          # band start, on the table
            [0.0, rest_z],            # lower crease: the band doubles back here
            [-width, rest_z + height],  # crest
            [width, rest_z],          # the second arm lands back on the table
            [width + tail, rest_z],   # band end
        ],
        dtype=float,
    )


def pleat_landmarks(profile) -> dict:
    """The points a planner and a judge need, read off the profile itself."""

    profile = np.asarray(profile, dtype=float)
    crease, crest = profile[1], profile[2]
    material = polyline_length(profile)
    span = float(profile[:, 0].max() - profile[:, 0].min())
    return {
        # Material coordinates along the band, NOT world x -- which world axis
        # the band runs along is the caller's choice (`sweep_profile_mesh`).
        "crease_s": float(crease[0]),
        "crest_s": float(crest[0]),
        "crest_z": float(crest[1]),
        # How far the crest is from the crease THROUGH THE MATERIAL. The crest
        # can only travel on a circle of this radius about the crease, the same
        # constraint docx 1.1's arc comes from.
        "arm_length": float(np.linalg.norm(crest - crease)),
        "material_length": material,
        "plan_span": span,
        "stored": material - span,
    }


def spiral_profile(
    *,
    material_length: float,
    bar_radius: float,
    clearance: float,
    pitch: float,
    turns: float,
    bar_height: float,
    rest_z: float,
    spacing: float,
) -> np.ndarray:
    """A band wound on a horizontal bar, hanging off it and lying on the table.

    docx 1.3's roll, in the arrangement of a washroom paper dispenser: the band
    spirals around a rigid bar, leaves it tangentially, hangs down and runs flat
    along the table. Written as (material, height) like `pleat_profile`, except
    that the first coordinate is measured from the BAR's axis rather than from
    the band's plan-view middle -- a rolled band has no useful middle, and the
    bar is the thing every other landmark is relative to.

    ::

              .-~~~-.
             ( ((|)) )     spiral, `turns` turns, wound clockwise
              '-~~~-'|     leaves at the +material side, tangent down
                     |     drape
        -------------+------------------------  table
                     '------ flat run ------'   <- the gripper takes this end

    **Why it leaves from the side and not the bottom.** The tangent to a spiral
    at its outermost point is perpendicular to the radius there, so a band that
    leaves at the side falls straight down and a band that leaves at the bottom
    sets off horizontally at roll height and has to kink to reach the table.
    Ending on the side is both the shape a real dispenser has and the one with no
    crease in it. Measured on the shipped numbers: the exit tangent is
    (+0.043, -0.999), i.e. within 2.5 degrees of vertical.

    The winding is CLOCKWISE (the angle decreases as material is paid out) so
    that the exit lands on the +material side and the flat run heads the same
    way. Winding the other way would put the flat run on the far side of the
    bar, under the roll.

    ``spacing`` is the target edge length of the control mesh. The spiral is
    sampled at that spacing here rather than being handed to `resample_polyline`
    as a curve, because that function resamples per SEGMENT: a densely sampled
    curve would keep its own density and ignore the target. Sampling here and
    then passing the result through `resample_polyline` is a no-op on the spiral
    and still subdivides the two straight pieces, which is what keeps the whole
    control mesh at one edge length.

    The chords cut the corner of the spiral by r(1 - cos(spacing/2r)); at the
    shipped 7.5 mm spacing and a 9 mm inner radius that is 0.77 mm, under a
    particle radius, so the simulated roll is not measurably smaller than the
    designed one.
    """

    r_in = float(bar_radius) + float(clearance)
    if float(clearance) <= 0.0 or float(pitch) <= 0.0 or float(turns) <= 0.0:
        raise ValueError("clearance, pitch and turns must all be positive.")

    sweep = 2.0 * math.pi * float(turns)
    # Sample by arc length rather than by angle: the spiral's radius grows, so a
    # uniform angle step would make the outer turns coarser than the inner ones.
    coarse = np.linspace(0.0, sweep, max(64, int(sweep * 200)))
    radius = r_in + float(pitch) * coarse / (2.0 * math.pi)
    angle = sweep - coarse
    curve = np.stack(
        [radius * np.cos(angle), float(bar_height) + radius * np.sin(angle)], axis=1
    )
    arc = np.concatenate(
        [[0.0], np.cumsum(np.linalg.norm(np.diff(curve, axis=0), axis=1))]
    )
    steps = max(2, int(round(float(arc[-1]) / float(spacing))))
    spiral = np.stack(
        [
            np.interp(np.linspace(0.0, float(arc[-1]), steps + 1), arc, curve[:, 0]),
            np.interp(np.linspace(0.0, float(arc[-1]), steps + 1), arc, curve[:, 1]),
        ],
        axis=1,
    )

    r_out = float(radius[-1])
    drape = float(bar_height) - float(rest_z)
    # Against the SAMPLED polyline's length, not the dense curve's. The chords
    # cut corners, so the two differ by a couple of millimetres -- and the total
    # has to come out at exactly `material_length`, because that is the
    # denominator the material-conservation judge divides by.
    flat = float(material_length) - float(polyline_length(spiral)) - drape
    # The attachment disc has to land on the flat run, and the grasp is inset
    # from its end. Anything shorter and the gripper has nothing to take hold of.
    if flat <= 4.0 * float(spacing):
        raise ValueError(
            f"material_length={material_length} leaves a flat run of {flat:.4f} m "
            f"after {arc[-1]:.4f} m of spiral and {drape:.4f} m of drape; the "
            f"gripper needs more than {4.0 * float(spacing):.4f} m to grasp."
        )

    return np.vstack(
        [
            spiral,
            [[r_out, float(rest_z)], [r_out + flat, float(rest_z)]],
        ]
    )


def spiral_landmarks(profile, *, bar_height: float, rest_z: float) -> dict:
    """The quantities a planner and a judge need, read off the profile itself."""

    profile = np.asarray(profile, dtype=float)
    material = polyline_length(profile)
    span = float(profile[:, 0].max() - profile[:, 0].min())
    # The spiral ends where the band first reaches the table; everything after is
    # the flat run the gripper works on.
    on_table = np.flatnonzero(profile[:, 1] <= float(rest_z) + 1e-9)
    exit_index = int(on_table[0]) if on_table.size else len(profile) - 2
    inner_s = float(profile[0, 0])
    free_end_s = float(profile[-1, 0])
    return {
        # Offsets from the BAR's axis along the material direction.
        "inner_s": inner_s,
        "exit_s": float(profile[exit_index, 0]),
        "free_end_s": free_end_s,
        "flat_run": free_end_s - float(profile[exit_index, 0]),
        "roll_radius": float(np.abs(profile[:exit_index, 0]).max()),
        # How much material is wound up.
        "rolled": float(polyline_length(profile[: exit_index + 1])) - (
            float(bar_height) - float(rest_z)
        ),
        # **How far the free end has to MOVE for the band to end up flat.**
        #
        # Not the same as `rolled`, and conflating the two is a mistake with a
        # measured cost: `cloth_unroll` pulled `rolled` on 2026-08-24 and finished
        # with 60 mm of material folded over the paid-out band instead of laid
        # flat, because the drape hanging from the bar also has to be laid out and
        # nothing had budgeted travel for it.
        #
        # Once flat, the band runs from its inner end to `material_length` beyond
        # it, and the inner end lands about where it sat on the bar. So the free
        # end finishes at `inner_s + material_length`, and the travel is that
        # minus where it started. Note what is NOT in this: the roll's radius,
        # pitch and turn count all cancel -- winding tighter or looser moves the
        # free end's START, not its FINISH.
        "flat_travel": inner_s + material - free_end_s,
        "material_length": material,
        "plan_span": span,
        "stored": material - span,
    }


def sweep_profile_mesh(
    profile,
    *,
    width: float,
    spacing: float,
    centre,
    table_z: float,
    path: Path,
    material_axis: int = 0,
):
    """Sweep an ``(N, 2)`` profile along the other horizontal axis, as an OBJ.

    The profile's first coordinate runs along ``material_axis`` (0 for world x,
    1 for world y) and its second is height above the table; the sweep goes along
    whichever of the two is left.

    Returns ``(vertices, faces, cols, rows)``. Vertices are ordered
    ``row * cols + col`` with ``col`` running along the material and ``row``
    across the width, matching `cloth_sheet_mesh` so the same neighbour
    arithmetic works on both.

    **The UVs put the material along u and the width along v.** The texture's
    stripes are bands of constant v (`world/textures.py:_base_colour`), so this
    makes each stripe a band of constant WIDTH running the length of the band --
    and the pleat's crease, which runs across the width, cuts every one of them.
    That is the whole reason the stripes are there: a crease parallel to the
    stripes hides material between two of them and looks much the same before and
    after, while a crease across them visibly interrupts each stripe and puts it
    back on unfolding.

    The pairing with the texture's own ``size_m`` is not optional -- see
    `texture_size_m`, which exists so the two cannot drift apart.
    """

    profile = np.asarray(profile, dtype=float)
    material_axis = int(material_axis)
    if material_axis not in (0, 1):
        raise ValueError(f"material_axis must be 0 (x) or 1 (y), got {material_axis}.")
    sweep_axis = 1 - material_axis

    rows = max(2, int(round(float(width) / float(spacing))) + 1)
    offsets = np.linspace(-0.5 * float(width), 0.5 * float(width), rows)
    cols = len(profile)

    centre = np.asarray(centre, dtype=float)
    vertices = np.zeros((rows * cols, 3), dtype=float)
    index = 0
    for offset in offsets:
        for point in profile:
            vertices[index, material_axis] = centre[material_axis] + point[0]
            vertices[index, sweep_axis] = centre[sweep_axis] + offset
            vertices[index, 2] = table_z + point[1]
            index += 1

    # Arc length along the profile, normalised. u has to follow the MATERIAL
    # rather than a world coordinate, or the texture bunches up wherever the
    # profile leaves the horizontal and doubles back on itself at the pleat.
    steps = np.linalg.norm(np.diff(profile, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(steps)])
    arc = arc / max(float(arc[-1]), 1e-12)
    uvs = np.array(
        [
            [float(arc[col]), row / max(1, rows - 1)]
            for row in range(rows)
            for col in range(cols)
        ],
        dtype=float,
    )

    faces = []
    for row in range(rows - 1):
        for col in range(cols - 1):
            lower_left = row * cols + col
            lower_right = lower_left + 1
            upper_left = lower_left + cols
            upper_right = upper_left + 1
            faces.append([lower_left, lower_right, upper_right])
            faces.append([lower_left, upper_right, upper_left])

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for vertex in vertices:
            handle.write(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}\n")
        for uv in uvs:
            handle.write(f"vt {uv[0]:.6f} {uv[1]:.6f}\n")
        for face in faces:
            handle.write(
                "f " + " ".join(f"{index + 1}/{index + 1}" for index in face) + "\n"
            )
    return vertices, np.asarray(faces, dtype=int), cols, rows


def texture_size_m(material_length: float, width: float) -> list:
    """``size_m`` for `world/textures.fabric_weave`, ordered ``(u, v)``.

    Exists so the mesh's UV layout and the texture's stripe axis cannot drift
    apart. `fabric_weave` bands its stripes along ``size_m[1]``, which is the v
    axis, and `sweep_profile_mesh` puts the WIDTH on v -- so the width goes
    second. Swap either one on its own and the stripes turn parallel to the
    crease, which is exactly the arrangement the stripes exist to avoid.
    """

    return [float(material_length), float(width)]


def edge_report(vertices, cols: int, rows: int) -> str:
    """Shortest and longest edge in the grid, against the target spacing.

    Printed rather than asserted. The remesher's behaviour is a measured fact in
    this repo, not a documented one, so the honest thing is to show the spread
    and let the settle run say whether it mattered.
    """

    vertices = np.asarray(vertices, dtype=float)
    index = np.arange(cols * rows).reshape(rows, cols)
    along = np.linalg.norm(
        vertices[index[:, 1:].ravel()] - vertices[index[:, :-1].ravel()], axis=1
    )
    across = np.linalg.norm(
        vertices[index[1:, :].ravel()] - vertices[index[:-1, :].ravel()], axis=1
    )
    return (
        f"cols={cols} rows={rows} vertices={len(vertices)} "
        f"along_mm={along.min() * 1e3:.2f}..{along.max() * 1e3:.2f} "
        f"across_mm={across.min() * 1e3:.2f}..{across.max() * 1e3:.2f}"
    )
