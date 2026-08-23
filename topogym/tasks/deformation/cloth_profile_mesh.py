"""Control meshes for cloth that does not start out flat.

`cloth_fold.cloth_sheet_mesh` covers the one case where the cloth lies flat.
docx 1.2, 1.3 and 1.5 all start from cloth that is folded, rolled or gathered,
and geometrically they are the same construction: a polyline in the x-z plane
swept along y. This file is that construction. docx 1.2's standing pleat is its
first profile; 1.3's spiral and 1.5's gathered stack are the same call with a
different polyline.

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
    crease and continues. Written as (x, z) with x already centred on the band's
    plan-view middle and z measured above the table.

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
        "crease_x": float(crease[0]),
        "crest_x": float(crest[0]),
        "crest_z": float(crest[1]),
        # How far the crest is from the crease THROUGH THE MATERIAL. The crest
        # can only travel on a circle of this radius about the crease, the same
        # constraint docx 1.1's arc comes from.
        "arm_length": float(np.linalg.norm(crest - crease)),
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
):
    """Sweep an ``(N, 2)`` x-z profile along y and write it as an OBJ.

    Returns ``(vertices, faces, cols, rows)``. Vertices are ordered
    ``row * cols + col`` with ``col`` running along the material and ``row``
    across the width, matching `cloth_sheet_mesh` so the same neighbour
    arithmetic works on both.

    **The UVs are laid out with the material direction along v, not u.** The
    texture's stripes are bands of constant v (`world/textures.py:_base_colour`),
    so this puts them across the material -- which is the direction the pleat
    stores and gives back. A stripe pattern running the other way looks the same
    before and after the unfold and shows nothing.
    """

    profile = np.asarray(profile, dtype=float)
    rows = max(2, int(round(float(width) / float(spacing))) + 1)
    ys = np.linspace(-0.5 * float(width), 0.5 * float(width), rows)
    cols = len(profile)

    centre = np.asarray(centre, dtype=float)
    vertices = np.array(
        [
            [centre[0] + point[0], centre[1] + y, table_z + point[1]]
            for y in ys
            for point in profile
        ],
        dtype=float,
    )

    # Arc length along the profile, normalised: v has to follow the MATERIAL, not
    # the x coordinate, or the texture bunches up wherever the profile leaves the
    # horizontal and doubles back on itself at the pleat.
    steps = np.linalg.norm(np.diff(profile, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(steps)])
    arc = arc / max(float(arc[-1]), 1e-12)
    uvs = np.array(
        [[row / max(1, rows - 1), float(arc[col])] for row in range(rows) for col in range(cols)],
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
