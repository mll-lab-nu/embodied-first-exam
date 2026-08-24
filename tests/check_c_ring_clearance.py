"""Offline gate for docx 3.4: does the C's opening work as the only way out?

`docs/develop/tasks/rigid_first_track_zh.md` section 4.5 rates this task's risk as
high for one reason: its anti-shortcut is not enforced by a rule, it is enforced by
collision. "Pulling flat or twisting jams on the ring body" is only true if the
segmented approximation of the two rings is faithful enough that the opening is the
size it claims to be. Section 7.3 therefore asks for exactly this check before any of
the task is built -- fixed ring plus C ring, a handful of non-gateway trajectories,
and evidence that every one of them jams.

None of it needs a solver. Both rings are unions of cylinders, so "do they touch" is
the distance between two sets of segments minus their radii, which is exact for the
bodies the scene actually loads -- not for an idealised torus. What the GPU spike
adds later is whether the scene is *stable*, which geometry cannot answer.

Four questions, in order:

  - **fit**: do the five inequalities the layout rests on hold, with what margin?
    (opening wider than the bar, C fits over the bar, nothing hits the table during
    the extraction, nothing hits the arm at reset)
  - **fidelity**: how far does the chord approximation move each surface, and how
    does that compare with the clearances it has to be small against?
  - **reading**: at spawn, is the pair linked -- one crossing pair and `Lk = -1`
    under the declared projection, with the C closed by the declared chord?
  - **gateway**: the aligning trajectory stays clear the whole way and ends unlinked;
    every non-aligning trajectory jams, and the report says where and how deep. There
    is exactly ONE, because the alignment is a slide and the ring never turns: the
    opening's direction in the world is fixed, so only one ring centre puts the bar on
    it. The roll this replaced had two mirror solutions -- opening turned up and
    dropped out, opening turned down and lifted out -- because turning moves the
    opening's world direction too. Which way round the arc the centre travels is the
    only alternative left, and it is probed on its own line: the long way is stopped
    by the stand, not by the interlock. The shortcut the anti-shortcut contrast guards
    against is not sliding at all.

Defaults come from the task config, so the gate and the scene cannot drift apart.

    python tests/check_c_ring_clearance.py
    python tests/check_c_ring_clearance.py --segment-deg 15
    python tests/check_c_ring_clearance.py --gap-deg 18      # expect the gate to fail

Needs numpy and PyYAML.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
TASK_CONFIG = REPO / "configs/task_configs/unlink_c_ring_topogym_tabletop_v1.yaml"

# How far a non-gateway trajectory is carried before giving up on it jamming. Long
# enough that a path which is genuinely open reaches daylight: the C's outer diameter
# plus the fixed ring's.
PROBE_TRAVEL = 0.100
PROBE_SAMPLES = 160


def load_module(name: str, relative: str):
    """Load a pure-numpy module by path, skipping its package's Genesis-importing init."""

    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def long_way_gateway_phases(geometry, cg, *, carry: float = 0.090):
    """The same alignment, reached round the other side of the circle.

    There is exactly one place the ring's centre can sit for the bar to be at the
    opening: the ring never turns, so the opening's direction in the world is fixed.
    That is a change from the roll this trajectory replaced, which had two mirror
    solutions -- opening turned up and dropped out, opening turned down and lifted
    out -- because turning moves the opening's world direction too.

    So the only alternative left is which way round the arc the centre travels, and it
    is worth probing rather than assuming: the long way carries the ring's body most
    of the way round the bar, and whether that is a second gateway or a jam is a fact
    about this layout, not something to declare. Probed here instead of in the
    non-gateway list because if it does stay clear it is a correct answer, not a
    shortcut.
    """

    waypoints = cg.slide_waypoints(
        geometry, geometry.c_rest_frame, chords=8, the_long_way=True
    )
    opening = cg.extract_direction(geometry, geometry.c_rest_frame)
    phases = [
        ("translate", tuple(float(v) for v in after - before))
        for before, after in zip(waypoints[:-1], waypoints[1:])
    ]
    phases.append(
        ("translate", tuple(float(v) for v in -geometry.extract_travel * opening))
    )
    phases.append(
        ("translate", tuple(float(v) for v in float(carry) * geometry.hang_direction))
    )
    return tuple(phases)


def non_gateway_phases(geometry, cg) -> list[tuple[str, tuple]]:
    """The trajectories that must all jam, and why each one is worth probing.

    These are the shortcuts a policy that has not understood the interlock would
    take: they start and finish where the real motion does, or close to it, and they
    differ in the one thing that matters -- the opening was never brought onto the
    bar. Turning the wrong way is NOT among them; it is a second gateway, see
    `mirror_gateway_phases`.
    """

    along = geometry.tube_direction
    across = np.cross(along, [0.0, 0.0, 1.0])
    travel = PROBE_TRAVEL
    return [
        ("drop without turning", (("translate", (0.0, 0.0, -travel)),)),
        ("lift without turning", (("translate", (0.0, 0.0, travel)),)),
        ("slide along the bar", (("translate", tuple(travel * along)),)),
        ("slide back along the bar", (("translate", tuple(-travel * along)),)),
        ("pull across the bar", (("translate", tuple(travel * across)),)),
        ("push across the bar", (("translate", tuple(-travel * across)),)),
        # The plain pick-and-place: lift the part, carry it aside, put it down.
        ("lift and carry aside", (("translate", (0.0, 0.0, travel)),
                                  ("translate", tuple(travel * across)))),
    ]


def sweep(geometry, cg, phases) -> dict:
    """Walk one trajectory and report the worst clearance and where it first jams.

    Both the other ring and the stand can stop the C, so both count as a jam; which
    one it was is read off the same sample rather than off the whole sweep, or a path
    that grazes the post late would be blamed for a jam on the ring early.
    """

    fixed_axes = geometry.fixed_axes()
    worst_ring, worst_stand = np.inf, np.inf
    jam_at, jam_depth, blocker = None, 0.0, None
    frame = geometry.c_rest_frame
    for index in range(PROBE_SAMPLES + 1):
        progress = index / PROBE_SAMPLES
        frame = cg.apply_phases(geometry.c_rest_frame, phases, progress)
        c_axes = geometry.c_axes(frame)
        ring = cg.surface_gap(fixed_axes, c_axes)
        stand = cg.surface_gap(geometry.stand_axes, c_axes)
        worst_ring, worst_stand = min(worst_ring, ring), min(worst_stand, stand)
        if jam_at is None and min(ring, stand) < -geometry.jam_depth:
            jam_at = progress
            jam_depth = min(ring, stand)
            blocker = "the closed ring" if ring <= stand else "the stand"
    return {
        "ring": worst_ring,
        "stand": worst_stand,
        "jam_at": jam_at,
        "jam_depth": jam_depth,
        "blocker": blocker,
        "end_frame": frame,
    }


def linking(geometry, cg, closed_band, frame) -> float:
    return closed_band.linking_number(
        cg.centerline(geometry.fixed, geometry.fixed_frame),
        cg.centerline(geometry.c_ring, frame, closure_samples=geometry.closure_samples),
        projection=geometry.projection,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gap-deg", type=float, default=None, help="override the C's opening")
    parser.add_argument("--segment-deg", type=float, default=None, help="override both chains")
    args = parser.parse_args()

    cg = load_module("c_ring_geometry", "topogym/tasks/entangle/_c_ring_geometry.py")
    closed_band = load_module("topogym_closed_band", "topogym/world/closed_band.py")

    cfg = yaml.safe_load(TASK_CONFIG.read_text(encoding="utf-8"))
    if args.gap_deg is not None:
        cfg["c_ring"]["gap_deg"] = args.gap_deg
    if args.segment_deg is not None:
        cfg["c_ring"]["segment_deg"] = args.segment_deg
        cfg["fixed_ring"]["segment_deg"] = args.segment_deg
    geometry = cg.scene_geometry(cfg)
    failures: list[str] = []

    print(f"unlink_c_ring geometry gate -- {TASK_CONFIG.relative_to(REPO)}\n")

    print("fit")
    for name, value, limit, ok in geometry.checks():
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {name:38s} {value * 1000:+8.2f} mm  >  {limit * 1000:+6.2f} mm")
        if not ok:
            failures.append(f"{name}: {value * 1000:+.2f} mm, needs more than {limit * 1000:+.2f} mm")

    fixed_segments = len(cg.segment_specs(geometry.fixed, geometry.fixed_frame))
    c_segments = len(cg.segment_specs(geometry.c_ring, geometry.c_rest_frame, geometry.tab))
    print("\nfidelity")
    print(
        f"  closed ring {fixed_segments:3d} cylinders, chord sagitta "
        f"{geometry.fixed.sagitta * 1000:.3f} mm"
    )
    print(
        f"  C ring      {c_segments:3d} cylinders"
        f"{' (last is the tab)' if geometry.tab is not None else ''}, chord sagitta "
        f"{geometry.c_ring.sagitta * 1000:.3f} mm"
    )
    print(
        f"  opening {geometry.c_ring.gap_clear_width * 1000:.2f} mm around a "
        f"{2 * geometry.fixed.tube_radius * 1000:.2f} mm bar: "
        f"{(geometry.c_ring.gap_clear_width - 2 * geometry.fixed.tube_radius) * 500:.2f} mm each "
        f"side, against a worst chord error of "
        f"{max(geometry.fixed.sagitta, geometry.c_ring.sagitta) * 1000:.3f} mm"
    )
    print(f"  jam threshold {geometry.jam_depth * 1000:.2f} mm of interpenetration")

    resting = cg.surface_gap(geometry.fixed_axes(), geometry.c_axes(geometry.c_rest_frame))
    spawn = cg.surface_gap(geometry.fixed_axes(), geometry.c_axes(geometry.c_spawn_frame))
    spawn_linking = linking(geometry, cg, closed_band, geometry.c_spawn_frame)
    print("\nreading")
    print(f"  resting on the bar   surface gap {resting * 1000:+.3f} mm (contact, within the chord error)")
    print(f"  spawn, {cfg['c_ring']['spawn_drop'] * 1000:.0f} mm higher   surface gap {spawn * 1000:+.3f} mm")
    viewer = geometry.projection[2]
    print(
        f"  projection: looking along ({viewer[0]:+.3f}, {viewer[1]:+.3f}, {viewer[2]:+.3f}), "
        "the bisector of the two ring normals"
    )
    print(f"  linking number at spawn {spawn_linking:+.1f} under that projection")
    if spawn <= 0.0:
        failures.append(f"the C spawns interpenetrating the closed ring by {-spawn * 1000:.2f} mm")
    if abs(abs(spawn_linking) - 1.0) > 1e-6:
        failures.append(f"the pair does not read as linked at spawn: Lk = {spawn_linking:+.2f}")

    travel_mm = geometry.extract_travel * 1000.0
    print("\ngateway (the one trajectory that unlinks -- clear all the way, ends unlinked)")
    label = f"slide to the opening, out {travel_mm:.0f} mm, carry away"
    result = sweep(geometry, cg, geometry.gateway_phases())
    end_linking = linking(geometry, cg, closed_band, result["end_frame"])
    ok = result["jam_at"] is None and abs(end_linking) <= 1e-6
    print(
        f"  [{'ok  ' if ok else 'FAIL'}] {label}:"
        f"  ring {result['ring'] * 1000:+.2f} mm   stand {result['stand'] * 1000:+.2f} mm"
        f"   end Lk {end_linking:+.1f}"
    )
    if result["jam_at"] is not None:
        failures.append(
            f"the gateway jams at {result['jam_at']:.0%} of the way through, "
            f"{-result['jam_depth'] * 1000:.2f} mm deep"
        )
    if abs(end_linking) > 1e-6:
        failures.append(f"the gateway ends still linked: Lk = {end_linking:+.2f}")

    # One alignment, not two. The ring never turns, so the opening's direction in the
    # world is fixed and only one centre puts the bar on it -- where the roll this
    # replaced had two mirror-image solutions. The only alternative left is which way
    # round the arc the centre travels, and the answer is a fact about this layout:
    # measured 2026-08-23, the long way is stopped by the STAND while the interlock
    # alone would have let it through. The post is load-bearing for uniqueness here,
    # which is worth printing rather than leaving implied.
    print("\nthe long way round the same arc (must be blocked)")
    long_way = sweep(geometry, cg, long_way_gateway_phases(geometry, cg))
    if long_way["jam_at"] is None:
        print(f"  [FAIL] never jams, closest ring {long_way['ring'] * 1000:+.2f} mm")
        failures.append(
            "the long way round is not blocked -- this layout has two gateways, and "
            "both the oracle and the anti-shortcut contrast assume one"
        )
    else:
        print(
            f"  [ok  ] jams at {long_way['jam_at']:4.0%} on {long_way['blocker']}, "
            f"{-long_way['jam_depth'] * 1000:5.2f} mm deep"
            f"   (interlock alone: {long_way['ring'] * 1000:+6.2f} mm)"
        )

    print("\nnon-gateway (every one of these must jam)")
    for name, phases in non_gateway_phases(geometry, cg):
        probe = sweep(geometry, cg, phases)
        if probe["jam_at"] is None:
            print(f"  [FAIL] {name:32s} never jams, closest {probe['ring'] * 1000:+.2f} mm")
            failures.append(f"{name!r} is not blocked -- the opening is not the only way out")
            continue
        # The stand can get in the way before the interlock does. Printing the
        # ring's own worst separation alongside says whether the interlock would
        # still have stopped this path on its own, which is the property the task
        # is actually claiming.
        print(
            f"  [ok  ] {name:32s} jams at {probe['jam_at']:4.0%} on {probe['blocker']}, "
            f"{-probe['jam_depth'] * 1000:5.2f} mm deep"
            f"   (interlock alone: {probe['ring'] * 1000:+6.2f} mm)"
        )

    print()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[pass] fit, fidelity, the linked reading, and the opening as the only gateway.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
