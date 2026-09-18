"""Offline health check for a rope's spawn tube skin (the OBJ fed to tetgen).

What Genesis renders for a volumetric FEM body is the boundary of the tet mesh,
but tetgen has been keeping this skin's facets verbatim (a 2026-08-19 run fed it
4920 facets and got 4920 boundary faces back, all 937 Steiner points interior),
so the two coincide and a static-frame artefact is measurable here. Shading is
not a suspect: Genesis smooths vertex normals by default and re-averages them
every frame, so only geometry can show.

What it reports, and why each number is here:
  - cross-section facet error -- how far the n-gon sits from a true circle; the
    source of the lengthwise ridges. 12 segments on a 4mm tube gives 0.136mm
    (3.4% of the radius), 20 gives 0.049mm;
  - lengthwise facet error -- the ring pitch judged against the bend it sits on
    (sagitta d^2/8R), and the gate: neither direction of the tessellation may be
    coarser than the other. This is what caught the terminal U-turn sampled at
    30 degrees (0.268mm of lengthwise error against 0.136mm across);
  - ring spacing spread -- reported, not gated. A tighter bend SHOULD carry
    denser rings; what is wrong is a density step in a STRAIGHT stretch, which
    `reserve_endpoint_footprint` used to leave at an end that never got refilled;
  - minimum centerline curvature radius against the tube radius -- below ~2 the
    rings bunch visibly on the inside of the bend, below 1 the skin folds into
    itself. The 8mm terminal U-turn sits at exactly 2.0;
  - built-in twist -- the skin is built on a parallel-transported (Bishop) frame,
    so this must be ~0; a non-zero value means the frame drifted.

    python tests/check_rope_tube_mesh.py --obj <path> --radial 20

Pass a tube OBJ produced by the shared rope mesh builder. No archived task
or pre-existing task-specific cache is selected implicitly.

Needs numpy only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# Gates.
#
# The lengthwise gate is NOT "rings must be evenly spaced": a tighter bend
# SHOULD carry denser rings, and the entry arc legitimately runs at 1.4mm where
# the body runs at 3.5mm. What matters is the polygonal error each direction of
# the tessellation contributes, so the ring pitch is judged against the local
# bend radius (sagitta d^2/8R) and held to the error the cross-section already
# has. Neither direction may be visibly worse than the other.
#
# Twist is a property of the Bishop frame the skin is built on -- it is zero by
# construction, so any real value means the frame drifted. The curvature bound
# is the "does the tube fold into itself" line, not a style rule: the terminal
# U-turn is deliberately tight (2.0x) and is reported, not gated.
MAX_BUILT_IN_TWIST_DEG = 1.0
MIN_CURVATURE_OVER_RADIUS = 1.0


def read_obj_vertices(path: Path) -> np.ndarray:
    verts = []
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            verts.append([float(value) for value in line.split()[1:4]])
    if len(verts) < 8:
        raise SystemExit(f"{path} has {len(verts)} vertices; not a tube mesh.")
    return np.asarray(verts, dtype=float)


def curvature_radii(centers: np.ndarray) -> np.ndarray:
    """Circumradius of each consecutive point triple."""

    a, b, c = centers[:-2], centers[1:-1], centers[2:]
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    return np.where(area > 1e-12, ab * bc * ca / (4.0 * np.maximum(area, 1e-12)), np.inf)


def built_in_twist_deg(skin: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Per-ring rotation of vertex 0 about the local tangent, in degrees."""

    tangents = np.diff(centers, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    first = skin[:, 0, :] - centers
    v0, v1 = first[:-1], first[1:]
    v0 = v0 - (np.sum(v0 * tangents, axis=1)[:, None] * tangents)
    v1 = v1 - (np.sum(v1 * tangents, axis=1)[:, None] * tangents)
    v0 /= np.linalg.norm(v0, axis=1)[:, None]
    v1 /= np.linalg.norm(v1, axis=1)[:, None]
    sin = np.sum(np.cross(v0, v1) * tangents, axis=1)
    return np.degrees(np.arctan2(sin, np.sum(v0 * v1, axis=1)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obj", type=Path, required=True)
    parser.add_argument("--radial", type=int, default=20, help="rope.mesh.radial_segments")
    args = parser.parse_args()

    if not args.obj.exists():
        raise SystemExit(f"{args.obj} not found; pass an existing tube OBJ.")

    verts = read_obj_vertices(args.obj)
    radial = int(args.radial)
    # The two trailing vertices are the cap centers (make_elastic_tube_mesh).
    if (len(verts) - 2) % radial:
        raise SystemExit(
            f"{len(verts)} vertices is not radial_segments={radial} x rings + 2 caps; "
            "pass the --radial this mesh was built with."
        )
    rings = (len(verts) - 2) // radial
    skin = verts[: rings * radial].reshape(rings, radial, 3)
    centers = skin.mean(axis=1)
    radii = np.linalg.norm(skin - centers[:, None, :], axis=2).mean(axis=1)
    spacing = np.linalg.norm(np.diff(centers, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(spacing)])
    tube_radius = float(radii.mean())

    print(f"obj            {args.obj}")
    print(f"rings          {rings} x radial {radial}  (skin verts {rings * radial} + 2 caps)")
    print(f"length         {arc[-1]:.4f} m")
    print(f"tube radius    {tube_radius * 1000:.3f} mm  (min {radii.min() * 1000:.3f} max {radii.max() * 1000:.3f})")

    ratio = float(spacing.max() / spacing.min())
    print(
        f"ring spacing   mean {spacing.mean() * 1000:.2f} mm  "
        f"min {spacing.min() * 1000:.2f}  max {spacing.max() * 1000:.2f}  max/min {ratio:.2f}"
    )

    sagitta = tube_radius * (1.0 - np.cos(np.pi / radial))
    chord = 2.0 * tube_radius * np.sin(np.pi / radial)
    print(
        f"cross section  sagitta {sagitta * 1000:.3f} mm ({sagitta / tube_radius * 100:.1f}% of r), "
        f"facet chord {chord * 1000:.2f} mm"
    )

    curv = curvature_radii(centers)
    tightest = int(np.argmin(curv))
    over_radius = float(curv[tightest] / tube_radius)
    print(
        f"tightest bend  R {curv[tightest] * 1000:.1f} mm at s={arc[tightest + 1]:.4f} m  "
        f"= {over_radius:.2f} x tube radius  (median R {np.median(curv) * 1000:.0f} mm)"
    )

    # Lengthwise facet error: the ring pitch measured against the bend it sits on.
    pitch = 0.5 * (spacing[:-1] + spacing[1:])
    lengthwise = pitch * pitch / (8.0 * curv)
    worst = int(np.argmax(lengthwise))
    print(
        f"lengthwise     sagitta max {lengthwise[worst] * 1000:.3f} mm at s={arc[worst + 1]:.4f} m "
        f"(pitch {pitch[worst] * 1000:.2f} mm on R {curv[worst] * 1000:.1f} mm), "
        f"median {np.median(lengthwise) * 1000:.3f} mm"
    )

    twist = built_in_twist_deg(skin, centers)
    total_twist = float(twist.sum())
    print(
        f"built-in twist {total_twist:+.2f} deg total ({total_twist / 360.0:+.3f} turns), "
        f"worst single ring {np.abs(twist).max():.2f} deg"
    )

    failures = []
    if lengthwise[worst] > sagitta:
        failures.append(
            f"lengthwise sagitta {lengthwise[worst] * 1000:.3f} mm at s={arc[worst + 1]:.4f} m "
            f"exceeds the cross-section's {sagitta * 1000:.3f} mm -- the ring pitch is the "
            "coarser of the two directions there"
        )
    if abs(total_twist) > MAX_BUILT_IN_TWIST_DEG:
        failures.append(f"built-in twist {total_twist:+.2f} deg exceeds {MAX_BUILT_IN_TWIST_DEG}")
    if over_radius < MIN_CURVATURE_OVER_RADIUS:
        failures.append(
            f"tightest bend {over_radius:.2f}x tube radius < {MIN_CURVATURE_OVER_RADIUS} "
            "(the skin folds into itself there)"
        )

    print()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[pass] lengthwise sagitta, built-in twist, and bend radius are all within bounds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
