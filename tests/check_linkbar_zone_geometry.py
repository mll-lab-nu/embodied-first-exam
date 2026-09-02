"""Does the linkbar layout's zone arithmetic match its own config? (docx 4.4, reworked)

Headless check, no Genesis and no GPU: `LinkbarRotateLayout` is pure arithmetic on
the task config, so the facts the verifier and the painted zones both rest on can
be settled here:

1. `in_zone` flips exactly at `half_width_deg` either side of a zone's centre.
2. The two zones never claim the same angle (strictly inside; touching zones
   share exactly their boundary angle, which is allowed).
3. `pin_color()` is the target zone's colour, and only that.
4. `validate` rejects the layouts it says it rejects: overlapping spans, a zone
   off the rail, the pin starting inside a zone, both zones the same colour, an
   unknown target -- and accepts the layouts the 2026-09-01 rework exists for:
   both zones on one side of the beam, and two zones touching.

    python tests/check_linkbar_zone_geometry.py

Prints one line per check and exits non-zero if any expectation misses.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.tasks.connectivity.linkbar_rotate_to_zone import (  # noqa: E402
    LINKBAR_ZONES,
    LinkbarRotateLayout,
)

CONFIG = ROOT / "configs" / "task_configs" / "linkbar_rotate_to_zone_topogym_tabletop_v1.yaml"


def load_cfg(**overrides):
    cfg = OmegaConf.load(CONFIG)
    for dotted, value in overrides.items():
        OmegaConf.update(cfg, dotted, value, merge=False)
    return cfg


def expect_reject(failures, label, **overrides) -> None:
    try:
        LinkbarRotateLayout(load_cfg(**overrides)).validate()
    except ValueError as exc:
        print(f"reject {label:20s} -> {str(exc).splitlines()[0][:80]}", flush=True)
    else:
        failures.append(f"validate accepted {label}")


def expect_accept(failures, label, **overrides) -> None:
    try:
        LinkbarRotateLayout(load_cfg(**overrides)).validate()
    except ValueError as exc:
        failures.append(f"validate rejected {label}: {str(exc).splitlines()[0][:80]}")
    else:
        print(f"accept {label:20s}", flush=True)


def main() -> int:
    failures = []
    layout = LinkbarRotateLayout(load_cfg())
    layout.validate()
    half_deg = float(layout.cfg.zones.half_width_deg)
    eps = math.radians(0.1)

    for zone in LINKBAR_ZONES:
        centre = layout.zone_angle(zone)
        half = math.radians(half_deg)
        inside = [centre, centre + half - eps, centre - half + eps]
        outside = [centre + half + eps, centre - half - eps]
        ok = all(layout.in_zone(a, zone) for a in inside) and not any(
            layout.in_zone(a, zone) for a in outside
        )
        print(
            f"zone {zone:5s} centre={math.degrees(centre):+6.1f}deg "
            f"half={half_deg:.1f}deg edge_flips={ok}",
            flush=True,
        )
        if not ok:
            failures.append(f"in_zone did not flip at the edge of {zone}")

    # Strictly inside both spans: sample at a tenth of a degree, offset by a
    # twentieth so a shared boundary (touching zones) is never itself sampled.
    both = [
        math.degrees(a)
        for a in (math.radians(d / 10.0 + 0.05) for d in range(-1800, 1800))
        if layout.in_zone(a, "color_1") and layout.in_zone(a, "color_2")
    ]
    if both:
        failures.append(f"angles on both zones: {both[:3]}...")
    print(f"overlap angles={len(both)}", flush=True)

    target = layout.target_zone()
    other = [z for z in LINKBAR_ZONES if z != target][0]
    if layout.pin_color() != layout.zone_color(target):
        failures.append("pin_color is not the target zone's colour")
    if layout.pin_color() == layout.zone_color(other):
        failures.append("pin_color also matches the other zone")
    print(f"target={target} pin_color={layout.pin_color()} other={layout.zone_color(other)}",
          flush=True)

    swapped = LinkbarRotateLayout(load_cfg(**{"zones.target": other}))
    if swapped.pin_color() != layout.zone_color(other):
        failures.append("pin_color did not follow zones.target")

    # half_width 8: spans 16 wide, centres must be >= 16 apart, >= 10 from init 0,
    # and within [-82, 82] on the +/-90 rail.
    expect_reject(failures, "overlap",
                  **{"zones.color_1.angle_deg": 30.0, "zones.color_2.angle_deg": 45.0})
    expect_reject(failures, "off_rail", **{"zones.color_2.angle_deg": 85.0})
    expect_reject(failures, "pin_in_zone", **{"zones.color_1.angle_deg": 5.0})
    expect_reject(failures, "pin_near_zone", **{"zones.color_1.angle_deg": -9.5})
    expect_reject(failures, "init_off_rail", **{"linkbar.init_angle_deg": 95.0})
    expect_reject(failures, "same_colour", **{"zones.assignment.color_2": "blue"})
    expect_reject(failures, "unknown_target", **{"zones.target": "middle"})
    expect_accept(failures, "same_side",
                  **{"zones.color_1.angle_deg": 30.0, "zones.color_2.angle_deg": 60.0})
    expect_accept(failures, "touching",
                  **{"zones.color_1.angle_deg": 30.0, "zones.color_2.angle_deg": 46.0})
    expect_accept(failures, "rail_edge",
                  **{"zones.color_1.angle_deg": -82.0, "zones.color_2.angle_deg": 82.0})
    expect_accept(failures, "pin_at_margin", **{"zones.color_1.angle_deg": -10.0})
    # Sweep steps follow the sweep at 0.23 deg/step (55 deg -> 240, the accepted
    # rate), floored at 120; sign of the sweep does not matter.
    for sweep_deg, want in ((55.0, 240), (-55.0, 240), (105.0, 457), (15.6, 120), (0.0, 120)):
        got = layout.steps_arc(math.radians(sweep_deg))
        print(f"steps_arc({sweep_deg:+6.1f}deg) = {got}", flush=True)
        if got != want:
            failures.append(f"steps_arc({sweep_deg}) = {got}, expected {want}")

    touching = LinkbarRotateLayout(load_cfg(**{"zones.color_1.angle_deg": 30.0,
                                                "zones.color_2.angle_deg": 46.0}))
    if touching.zone_at(math.radians(37.9)) != "color_1" or \
            touching.zone_at(math.radians(38.1)) != "color_2":
        failures.append("touching zones: zone_at does not switch at the shared edge")

    # The beam's start is derived onto [-15, 15] minus each zone's keep-out
    # (8 + 2 deg). One zone at -5 cuts [-15, 5] out, leaving [5, 15]; a zone at
    # 0 with the other at 20 leaves nothing.
    cut = LinkbarRotateLayout(load_cfg(**{"zones.color_1.angle_deg": -5.0,
                                           "zones.color_2.angle_deg": 60.0}))
    segments = [(round(s, 6), round(e, 6)) for s, e in cut.init_angle_segments()]
    print(f"init segments (zone at -5): {segments}", flush=True)
    if segments != [(5.0, 15.0)]:
        failures.append(f"init_angle_segments = {segments}, expected [(5.0, 15.0)]")
    ends = (cut.init_angle_from_frac(0.0), cut.init_angle_from_frac(1.0))
    if not (abs(ends[0] - 5.0) < 1e-9 and abs(ends[1] - 15.0) < 1e-9):
        failures.append(f"init_angle_from_frac ends = {ends}, expected (5, 15)")
    split = LinkbarRotateLayout(load_cfg(**{"zones.color_1.angle_deg": -40.0,
                                             "zones.color_2.angle_deg": 0.0}))
    segments = [(round(s, 6), round(e, 6)) for s, e in split.init_angle_segments()]
    if segments != [(-15.0, -10.0), (10.0, 15.0)]:
        failures.append(f"split init_angle_segments = {segments}, expected two 5 deg pieces")
    mid = split.init_angle_from_frac(0.5)
    if abs(mid - (-10.0)) > 1e-9 and abs(mid - 10.0) > 1e-9:
        failures.append(f"init_angle_from_frac(0.5) on two equal pieces = {mid}, expected a piece end")
    covered = LinkbarRotateLayout(load_cfg(**{"zones.color_1.angle_deg": -8.0,
                                               "zones.color_2.angle_deg": 12.0}))
    try:
        covered.init_angle_from_frac(0.5)
    except ValueError:
        pass
    else:
        failures.append("init_angle_from_frac accepted zones that cover the whole span")


    for failure in failures:
        print(f"FAIL: {failure}", flush=True)
    print("ok" if not failures else f"{len(failures)} failure(s)", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
