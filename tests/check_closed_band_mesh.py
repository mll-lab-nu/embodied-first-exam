"""Offline gate for the closed elastic band: its skin, its seam, and its topology.

The band is docx 3.3's asset (`docs/develop/tasks/task_environment_buildout_zh.md`
calls it the closed elastic ring, the one capability that blocks that task). This
is the check that runs before any GPU time is spent on it, and it answers three
separate questions:

  - **skin**: is the periodic sweep a valid closed tube -- watertight, one
    orientation, and no coarser lengthwise than it is around the section? Same
    two-directions-must-match rule as `tests/check_rope_tube_mesh.py`, which
    cannot be used here because it assumes two end caps and an open ring count.

  - **seam**: closing a Bishop frame around a loop costs `-H + 2*pi*k` of twist,
    and `k` decides the band's self-linking number. `Lk = 0` is the flat O; a band
    spawned at `Lk = +-1` looks identical and can never be flipped flat, so the
    task would be unsolvable for a reason no amount of physics tuning would find.
    The gate is `Lk == 0`, and the report prints what the obvious choice of `k`
    (the one that minimises twist) would have given instead.

  - **reading**: does the self-crossing count answer 0 / 1 / 2 on an O, a
    figure-8, and a wrong-way flip -- and still answer 1 when the 8 is squashed
    flat so the crossing is hidden? That last case is docx 3.3's stated
    anti-shortcut, executable here with no simulator.

Defaults are read from the spike's own config files so the two cannot drift.

    python tests/check_closed_band_mesh.py
    python tests/check_closed_band_mesh.py --half-turns -1 --radial 12
    python tests/check_closed_band_mesh.py --obj out.obj     # also write the mesh

Needs numpy and PyYAML.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]

# Gates.
#
# The lengthwise rule is `check_rope_tube_mesh.py`'s: judge the ring pitch against
# the bend it sits on (sagitta d^2/8R) and let neither direction of the
# tessellation be coarser than the other.
#
# A closed band's built-in twist is NOT zero -- unlike an open rope, where it is
# zero by construction and any reading means the frame drifted. Here it is the
# `Tw` the seam closure had to buy, so what is gated instead is that the twist is
# spread evenly: no single ring may be sheared by more than half a facet, or the
# skin visibly steps at that ring.
MAX_RING_TWIST_FRACTION_OF_FACET = 0.5
MIN_CURVATURE_OVER_RADIUS = 1.0
SELF_LINKING_TARGET = 0


def load_closed_band():
    """Load `topogym/world/closed_band.py` without running `topogym.world`'s init.

    That init imports Genesis (`world/lighting.py:17`). The module itself is pure
    numpy, and this gate is meant to run anywhere -- including a checkout with no
    CUDA and no solver installed -- so it is loaded from its path instead.
    """

    path = REPO / "topogym" / "world" / "closed_band.py"
    spec = importlib.util.spec_from_file_location("topogym_closed_band", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def config_defaults() -> dict:
    """Literal values from the spike's configs -- no Hydra, no interpolation."""

    run = yaml.safe_load((REPO / "configs/run_configs/closed_band_spike.yaml").read_text(encoding="utf-8"))
    primary = yaml.safe_load((REPO / "configs/closed_band_spike.yaml").read_text(encoding="utf-8"))
    prefabs = yaml.safe_load((REPO / "configs/prefab_configs/topogym_prefabs_v1.yaml").read_text(encoding="utf-8"))
    band, mesh = run["band"], primary["task"]["rope"]["mesh"]
    return {
        "perimeter": float(band["perimeter"]),
        "loop_radius": float(band["loop_radius"]),
        "peg_center": [float(value) for value in band["peg_center"]],
        "peg_radius": float(band["peg_radius"]),
        "half_turns": float(band["half_turns"]),
        "merge_radius": float(band["crossing_merge_radius"]),
        "segment_length": float(mesh["segment_length"]),
        "radial": int(mesh["radial_segments"]),
        "radius": float(prefabs["rope_pbd"]["radius"]),
        "d_hat": float(prefabs["rope_fem"]["contact_d_hat"]),
    }


def edge_multiplicities(faces: np.ndarray) -> Counter:
    edges: Counter = Counter()
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            edges[(min(u, v), max(u, v))] += 1
    return Counter(edges.values())


def signed_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    tri = vertices[faces]
    return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)


def curvature_radii(centers: np.ndarray) -> np.ndarray:
    """Circumradius of each consecutive triple, wrapping around the loop."""

    a = np.roll(centers, 1, axis=0)
    b = centers
    c = np.roll(centers, -1, axis=0)
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    return np.where(area > 1e-12, ab * bc * ca / (4.0 * np.maximum(area, 1e-12)), np.inf)


def ring_twist_deg(skin: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Rotation of vertex 0 about the local tangent, ring to ring, wrapping.

    The closed counterpart of `check_rope_tube_mesh.built_in_twist_deg`; the only
    difference is that the last ring is compared against the first.
    """

    tangents = np.roll(centers, -1, axis=0) - centers
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    spoke = skin[:, 0, :] - centers
    v0, v1 = spoke, np.roll(spoke, -1, axis=0)
    v0 = v0 - np.sum(v0 * tangents, axis=1)[:, None] * tangents
    v1 = v1 - np.sum(v1 * tangents, axis=1)[:, None] * tangents
    v0 /= np.linalg.norm(v0, axis=1)[:, None]
    v1 /= np.linalg.norm(v1, axis=1)[:, None]
    sin = np.sum(np.cross(v0, v1) * tangents, axis=1)
    return np.degrees(np.arctan2(sin, np.sum(v0 * v1, axis=1)))


def min_nonadjacent_distance(centerline: np.ndarray, *, skip: int) -> float:
    """Closest approach between parts of the loop more than ``skip`` samples apart."""

    count = len(centerline)
    dist = np.linalg.norm(centerline[:, None, :] - centerline[None, :, :], axis=2)
    index = np.arange(count)
    cyclic = np.abs(index[:, None] - index[None, :])
    dist[np.minimum(cyclic, count - cyclic) <= skip] = np.inf
    return float(dist.min())


def check_reading(cb, defaults: dict, failures: list) -> None:
    """The self-crossing count on curves whose answer is known by construction."""

    def curve(half_turns: float, perimeter: float, depth_scale: float = 1.0):
        pts = cb.hanging_band_centerline(
            perimeter=perimeter,
            loop_radius=defaults["loop_radius"],
            peg_center=defaults["peg_center"],
            half_turns=half_turns,
            segment_length=defaults["segment_length"],
        )
        # Squashing is a scale toward the wall along the viewing axis: the picture
        # is untouched, only the depth that separates the strands shrinks.
        pts[:, 0] = defaults["peg_center"][0] + depth_scale * (pts[:, 0] - defaults["peg_center"][0])
        return pts

    # A band that has taken two half turns is physically shorter between the caps,
    # so the wrong-way case is generated on a longer band rather than a shorter
    # loop -- the count is what is under test, not the dimensions.
    long_band = 1.5 * defaults["perimeter"]
    cases = [
        ("flat O", curve(0.0, defaults["perimeter"]), 0),
        ("figure-8", curve(1.0, defaults["perimeter"]), 1),
        ("figure-8 mirrored", curve(-1.0, defaults["perimeter"]), 1),
        ("wrong-way flip (two half turns)", curve(2.0, long_band), 2),
        ("figure-8 squashed onto the wall", curve(1.0, defaults["perimeter"], 0.02), 1),
    ]
    print()
    print("self-crossing reading")
    for name, pts, expected in cases:
        hits = cb.band_self_crossings(
            pts, merge_radius=defaults["merge_radius"], skip_adjacent=2
        )
        signs = [hit.sign for hit in hits]
        gaps = [f"{hit.gap * 1000:.1f}" for hit in hits]
        verdict = "ok" if len(hits) == expected else "WRONG"
        print(
            f"  {name:38s} {len(hits)} (want {expected}) {verdict}  "
            f"signs {signs} depth gaps {gaps} mm"
        )
        if len(hits) != expected:
            failures.append(f"self-crossing count on '{name}' read {len(hits)}, want {expected}")


def main() -> int:
    cb = load_closed_band()
    defaults = config_defaults()

    parser = argparse.ArgumentParser(description="Closed band skin / seam / reading gate.")
    parser.add_argument("--perimeter", type=float, default=defaults["perimeter"])
    parser.add_argument("--loop-radius", type=float, default=defaults["loop_radius"])
    # The spawned mesh is the FLAT O -- the spike winds the figure-8 in-solver
    # rather than spawning it (see `tests/closed_band_spike.py`), so 0.0 is what
    # actually gets tetrahedralized. The wound shape is still checked, in the
    # rationale section below.
    parser.add_argument("--half-turns", type=float, default=0.0)
    parser.add_argument("--radius", type=float, default=defaults["radius"])
    parser.add_argument("--radial", type=int, default=defaults["radial"])
    parser.add_argument("--segment-length", type=float, default=defaults["segment_length"])
    parser.add_argument("--d-hat", type=float, default=defaults["d_hat"])
    parser.add_argument("--obj", type=Path, default=None, help="also write the mesh here")
    args = parser.parse_args()

    failures: list[str] = []
    peg = np.asarray(defaults["peg_center"], dtype=float)

    centerline = cb.hanging_band_centerline(
        perimeter=args.perimeter,
        loop_radius=args.loop_radius,
        peg_center=peg,
        half_turns=args.half_turns,
        segment_length=args.segment_length,
    )
    frames = cb.closed_transport_frames(
        centerline, tube_radius=args.radius, self_linking_target=SELF_LINKING_TARGET
    )
    vertices, faces = cb.closed_tube_mesh(
        centerline, frames, radius=args.radius, radial_segments=args.radial
    )
    skin = vertices.reshape(len(centerline), args.radial, 3)
    centers = skin.mean(axis=1)

    print(f"band           perimeter {frames.perimeter:.4f} m, {args.half_turns:+.1f} half turns")
    print(
        f"               loop radius {args.loop_radius * 1000:.1f} mm on a peg at "
        f"{np.round(peg * 1000, 1).tolist()} mm, tube radius {args.radius * 1000:.1f} mm"
    )
    print(
        f"               hangs from z {centerline[:, 2].max() * 1000:.1f} mm down to "
        f"{centerline[:, 2].min() * 1000:.1f} mm"
    )
    print(f"mesh           {len(centerline)} rings x {args.radial} = {len(vertices)} verts, {len(faces)} faces")

    # --- skin -----------------------------------------------------------------
    multiplicity = edge_multiplicities(faces)
    edge_count = sum(multiplicity.values())
    euler = len(vertices) - edge_count + len(faces)
    volume = signed_volume(vertices, faces)
    exact = np.pi * args.radius**2 * frames.perimeter
    facet_ratio = (args.radial / (2.0 * np.pi)) * np.sin(2.0 * np.pi / args.radial)
    print(
        f"watertight     edge multiplicity {dict(multiplicity)} over {edge_count} edges, "
        f"V-E+F = {euler} (a torus is 0)"
    )
    print(
        f"volume         {volume * 1e6:.2f} cm^3 vs {exact * facet_ratio * 1e6:.2f} cm^3 for a "
        f"{args.radial}-gon section ({exact * 1e6:.2f} round)"
    )
    if set(multiplicity) != {2}:
        failures.append(f"mesh is not watertight: edge multiplicities {dict(multiplicity)}")
    if euler != 0:
        failures.append(f"V-E+F = {euler}, not the 0 a torus must have")
    if volume <= 0.0:
        failures.append(f"signed volume {volume * 1e6:.2f} cm^3 <= 0: face winding is inconsistent")

    spacing = np.linalg.norm(np.roll(centers, -1, axis=0) - centers, axis=1)
    curv = curvature_radii(centers)
    sagitta = args.radius * (1.0 - np.cos(np.pi / args.radial))
    pitch = 0.5 * (spacing + np.roll(spacing, 1))
    lengthwise = pitch * pitch / (8.0 * curv)
    worst = int(np.argmax(lengthwise))
    tightest = int(np.argmin(curv))
    over_radius = float(curv[tightest] / args.radius)
    print(
        f"cross section  sagitta {sagitta * 1000:.3f} mm ({sagitta / args.radius * 100:.1f}% of r)"
    )
    print(
        f"lengthwise     sagitta max {lengthwise[worst] * 1000:.3f} mm (ring pitch "
        f"{pitch[worst] * 1000:.2f} mm on R {curv[worst] * 1000:.1f} mm), "
        f"median {np.median(lengthwise) * 1000:.3f} mm"
    )
    print(
        f"tightest bend  R {curv[tightest] * 1000:.1f} mm = {over_radius:.2f} x tube radius"
    )
    if lengthwise[worst] > sagitta:
        failures.append(
            f"lengthwise sagitta {lengthwise[worst] * 1000:.3f} mm exceeds the cross-section's "
            f"{sagitta * 1000:.3f} mm -- the ring pitch is the coarser direction"
        )
    if over_radius < MIN_CURVATURE_OVER_RADIUS:
        failures.append(
            f"tightest bend {over_radius:.2f}x tube radius < {MIN_CURVATURE_OVER_RADIUS} "
            "(the skin folds into itself there)"
        )

    # --- seam -----------------------------------------------------------------
    nearest = int(np.rint(frames.holonomy_turns))
    trapped = SELF_LINKING_TARGET + (nearest - frames.closure_turns)
    twist = ring_twist_deg(skin, centers)
    facet_deg = 360.0 / args.radial
    print()
    print(
        f"seam           Bishop holonomy {frames.holonomy_turns:+.4f} turns; closed with "
        f"k = {frames.closure_turns} (least-twist k would be {nearest})"
    )
    print(
        f"self-linking   Lk = {frames.self_linking} at Tw = {frames.twist_turns:+.4f} turns "
        f"(so Wr = {-frames.twist_turns:+.4f}); least-twist k would have given Lk = {trapped}"
    )
    print(
        f"ring twist     {twist.sum():+.2f} deg over the loop "
        f"({twist.sum() / 360.0:+.4f} turns), worst single ring {np.abs(twist).max():.2f} deg "
        f"of a {facet_deg:.1f} deg facet"
    )
    if frames.self_linking != SELF_LINKING_TARGET:
        failures.append(
            f"self-linking Lk = {frames.self_linking}, not {SELF_LINKING_TARGET}: this band "
            "cannot be flipped flat no matter what the solver does"
        )
    if abs(twist.sum() / 360.0 - frames.twist_turns) > 0.01:
        failures.append(
            f"the mesh carries {twist.sum() / 360.0:+.4f} turns of twist but the frames claim "
            f"{frames.twist_turns:+.4f} -- the sweep and the closure disagree"
        )
    if float(np.abs(twist).max()) > MAX_RING_TWIST_FRACTION_OF_FACET * facet_deg:
        failures.append(
            f"one ring is sheared {np.abs(twist).max():.2f} deg, over "
            f"{MAX_RING_TWIST_FRACTION_OF_FACET:.0%} of a {facet_deg:.1f} deg facet -- the "
            "closure is not spread evenly"
        )

    # --- spawn clearance ------------------------------------------------------
    skip = max(2, int(np.ceil(4.0 * args.radius / args.segment_length)))
    closest = min_nonadjacent_distance(centerline, skip=skip)
    needed = 2.0 * args.radius + 2.0 * args.d_hat
    peg_gap = args.loop_radius - defaults["peg_radius"] - args.radius
    print()
    print(
        f"self clearance {closest * 1000:.2f} mm between parts of the loop more than {skip} "
        f"samples apart; the barrier needs {needed * 1000:.2f} mm "
        f"(2r + 2 d_hat, d_hat {args.d_hat * 1000:.1f} mm)"
    )
    print(
        f"peg clearance  {peg_gap * 1000:.2f} mm between the tube's inner surface and a "
        f"{defaults['peg_radius'] * 1000:.1f} mm peg"
    )
    if closest < needed:
        failures.append(
            f"the band spawns {closest * 1000:.2f} mm from itself, inside the "
            f"{needed * 1000:.2f} mm the contact barrier needs"
        )
    if peg_gap < args.d_hat:
        failures.append(
            f"the band spawns {peg_gap * 1000:.2f} mm off the peg, inside the barrier's "
            f"{args.d_hat * 1000:.1f} mm -- widen loop_radius"
        )

    # --- why the spike spawns flat --------------------------------------------
    # The state the band is wound to, checked here even though it is never meshed:
    # its least-twist framing lands on Lk = +-1, which is a band that cannot be
    # flipped flat. Spawning the O and winding in-solver sidesteps the choice
    # entirely (no motion changes Lk), and this is the reading that says why.
    wound = cb.hanging_band_centerline(
        perimeter=args.perimeter,
        loop_radius=args.loop_radius,
        peg_center=peg,
        half_turns=defaults["half_turns"],
        segment_length=args.segment_length,
    )
    wound_frames = cb.closed_transport_frames(
        wound, tube_radius=args.radius, self_linking_target=SELF_LINKING_TARGET
    )
    wound_nearest = int(np.rint(wound_frames.holonomy_turns))
    print()
    print(
        f"wound state    {defaults['half_turns']:+.1f} half turns hangs to z "
        f"{wound[:, 2].min() * 1000:.1f} mm ({(wound[:, 2].min() - centerline[:, 2].min()) * 1000:+.1f} "
        f"mm against the flat O), {len(cb.band_self_crossings(wound, merge_radius=defaults['merge_radius']))} "
        "self-crossings"
    )
    print(
        f"               Lk = {wound_frames.self_linking} at Tw = "
        f"{wound_frames.twist_turns:+.4f} turns with k = {wound_frames.closure_turns}; "
        f"least-twist k = {wound_nearest} would have given Lk = "
        f"{SELF_LINKING_TARGET + wound_nearest - wound_frames.closure_turns} -- a band that "
        "cannot be flipped flat"
    )
    if wound_frames.self_linking != SELF_LINKING_TARGET:
        failures.append(
            f"the wound state reads Lk = {wound_frames.self_linking}: winding the O in-solver "
            "must not change the self-linking"
        )

    check_reading(cb, {**defaults, "loop_radius": args.loop_radius,
                       "segment_length": args.segment_length,
                       "perimeter": args.perimeter}, failures)

    if args.obj is not None:
        args.obj.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Generated by tests/check_closed_band_mesh.py"]
        lines += [f"v {v[0]:.8f} {v[1]:.8f} {v[2]:.8f}" for v in vertices]
        lines += [f"f {f[0] + 1} {f[1] + 1} {f[2] + 1}" for f in faces]
        args.obj.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nwrote {args.obj}")

    print()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[pass] skin, seam, self-linking, clearances, and the self-crossing reading.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
