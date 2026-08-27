"""Does the linkbar layout's zone arithmetic match its own config? (docx 4.4, reworked)

Headless check, no Genesis and no GPU: `LinkbarRotateLayout` is pure arithmetic on
the task config, so the facts the verifier and the painted zones both rest on can
be settled here:

1. `in_zone` flips exactly at `half_width_deg` either side of a zone's centre.
2. The two zones never claim the same angle.
3. `pin_color()` is the target zone's colour, and only that.
4. `validate` rejects the layouts it says it rejects: same side, out of sweep
   range, overlapping spans, both zones the same colour, an unknown target.

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

    both = [
        math.degrees(a)
        for a in (math.radians(d / 10.0) for d in range(-1800, 1801))
        if layout.in_zone(a, "left") and layout.in_zone(a, "right")
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

    expect_reject(failures, "same_side", **{"zones.right.angle_deg": 40.0})
    expect_reject(failures, "sweep_too_small", **{"zones.left.angle_deg": 20.0})
    expect_reject(failures, "sweep_too_large", **{"zones.left.angle_deg": 80.0})
    expect_reject(failures, "overlap",
                  **{"zones.left.angle_deg": 36.0, "zones.right.angle_deg": -36.0,
                     "zones.half_width_deg": 35.0})
    expect_reject(failures, "same_colour", **{"zones.assignment.right": "orange"})
    expect_reject(failures, "unknown_target", **{"zones.target": "middle"})

    for failure in failures:
        print(f"FAIL: {failure}", flush=True)
    print("ok" if not failures else f"{len(failures)} failure(s)", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
