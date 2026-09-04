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

Five questions, in order:

  - **fit**: do the seven inequalities the layout rests on hold, with what margin?
    (opening wider than the bar, C fits over the bar, nothing hits the table during
    the extraction, nothing hits the arm at reset, the grasp point within reach, the
    hand outside the closed ring at the grasp point)
  - **fidelity**: how far does the chord approximation move each surface, and how
    does that compare with the clearances it has to be small against?
  - **reading**: at spawn, is the pair linked -- one crossing pair and `Lk = -1`
    under the declared projection, with the C closed by the declared chord?
  - **gateway**: the aligning trajectory stays clear the whole way and ends
    unlinked; every non-aligning trajectory jams, and the report says where and how
    deep. The alignment is two straight legs -- lift the ring so the bar sits in the
    middle of its interior, then one straight swing that puts the bar toward the
    opening -- so the approach runs through the hole's empty middle rather than
    along the tube. The shortcut the anti-shortcut contrast guards against is
    skipping the alignment entirely.
  - **variation envelope**: the same four answers at every corner of the yaml's
    `variation:` block (2^n corners over the uniform axes, the grasp azimuth derived
    the way the task's hook derives it), plus two draws that must fail a row --
    the gate is only worth something if it can say no.

Defaults come from the task config, so the gate and the scene cannot drift apart.

    python tests/check_c_ring_clearance.py
    python tests/check_c_ring_clearance.py --segment-deg 15
    python tests/check_c_ring_clearance.py --gap-deg 18      # expect the gate to fail

Needs numpy and PyYAML.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import itertools
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


# ---- variation envelope -----------------------------------------------------


def envelope(cfg: dict) -> dict[str, tuple[float, float]]:
    """Dotted path -> (lo, hi) for every uniform axis in the yaml's ``variation:`` block."""

    return {
        str(entry["path"]): (float(entry["lo"]), float(entry["hi"]))
        for entry in cfg.get("variation", [])
        if entry.get("kind") == "uniform"
    }


def set_leaf(cfg: dict, path: str, value: float) -> None:
    node = cfg
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[key]
    node[leaf] = value


def corner_cfg(cfg: dict, **leaves: float) -> dict:
    """A deep copy of the yaml with the given leaves written and the grasp azimuth
    derived the same way ``unlink_c_ring.derive_task_cfg`` does it."""

    out = copy.deepcopy(cfg)
    for path, value in leaves.items():
        set_leaf(out, path, value)
    out["primitive"]["grasp_azimuth_deg"] = (
        float(out["c_ring"]["gap_azimuth_deg"]) + float(out["primitive"]["grasp_offset_deg"])
    ) % 360.0
    return out


def corner_failures(geometry, cg, closed_band, lift: float) -> list[str]:
    """The fit / reading / gateway / non-gateway verdicts for one geometry, as failures."""

    fails = [
        f"{name}: {value * 1000:+.2f} mm, needs more than {limit * 1000:+.2f} mm"
        for name, value, limit, ok in geometry.checks()
        if not ok
    ]
    spawn_linking = linking(geometry, cg, closed_band, geometry.c_spawn_frame)
    if abs(abs(spawn_linking) - 1.0) > 1e-6:
        fails.append(f"not linked at spawn: Lk = {spawn_linking:+.2f}")
    result = sweep(geometry, cg, geometry.gateway_phases(lift=lift))
    if result["jam_at"] is not None:
        fails.append(f"the gateway jams at {result['jam_at']:.0%}, {-result['jam_depth'] * 1000:.2f} mm deep")
    end_linking = linking(geometry, cg, closed_band, result["end_frame"])
    if abs(end_linking) > 1e-6:
        fails.append(f"the gateway ends still linked: Lk = {end_linking:+.2f}")
    for name, phases in non_gateway_phases(geometry, cg):
        if sweep(geometry, cg, phases)["jam_at"] is None:
            fails.append(f"{name!r} is not blocked")
    return fails


def check_envelope(cfg: dict, cg, closed_band, lift: float) -> list[str]:
    """Every corner of the envelope passes all four questions; two draws outside it fail a row."""

    fails: list[str] = []
    axes = envelope(cfg)
    want = {
        "stand.hang_yaw_deg", "fixed_ring.center_x", "fixed_ring.center_y",
        "c_ring.gap_deg", "c_ring.gap_azimuth_deg",
    }
    if set(axes) != want:
        return [f"variation axes {sorted(axes)} != {sorted(want)}"]

    paths = list(axes)
    tightest: dict[str, float] = {}
    corners = list(itertools.product(*(axes[p] for p in paths)))
    for values in corners:
        leaves = dict(zip(paths, values))
        geometry = cg.scene_geometry(corner_cfg(cfg, **leaves))
        for name, value, limit, _ in geometry.checks():
            margin = value - limit
            if name not in tightest or margin < tightest[name]:
                tightest[name] = margin
        for failure in corner_failures(geometry, cg, closed_band, lift):
            label = " ".join(f"{p.split('.')[-1]}={v:g}" for p, v in leaves.items())
            fails.append(f"corner [{label}]: {failure}")
    for name, margin in tightest.items():
        print(f"  {name:40s} tightest margin {margin * 1000:+8.2f} mm over {len(corners)} corners")

    # Negatives: the two rows added for the envelope must be able to say no.
    hand = cg.scene_geometry(corner_cfg(cfg, **{"c_ring.gap_azimuth_deg": 295.0}))
    if all(ok for name, _, _, ok in hand.checks() if name.startswith("hand clears")):
        fails.append("gap_azimuth_deg=295 should fail 'hand clears the ring at the grasp point'")
    reach = cg.scene_geometry(corner_cfg(cfg, **{"stand.hang_yaw_deg": 0.0}))
    if all(ok for name, _, _, ok in reach.checks() if name.startswith("hand reaches")):
        fails.append("hang_yaw_deg=0 should fail 'hand reaches the grasp point'")
    print(f"  negatives: gap_azimuth 295 -> hand row {hand.hand_clearance * 1000:+.2f} mm, "
          f"hang_yaw 0 -> reach {reach.grasp_reach:.3f} m")
    return fails


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

    lift = float(cfg["primitive"]["slide_lift"])
    travel_mm = (geometry.extract_travel + lift) * 1000.0
    print("\ngateway (must stay clear the whole way and end unlinked)")
    label = f"lift {lift * 1000:.0f} mm, swing to the opening, out {travel_mm:.0f} mm"
    result = sweep(geometry, cg, geometry.gateway_phases(lift=lift))
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

    if args.gap_deg is None and args.segment_deg is None:
        print("\nvariation envelope (every corner must pass all of the above)")
        failures.extend(check_envelope(cfg, cg, closed_band, lift))

    print()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[pass] fit, fidelity, the linked reading, the opening as the only gateway, and the envelope's corners.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
