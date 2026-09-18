"""Does the linkbar layout's zone arithmetic match its own config? (docx 4.4, reworked)

Headless check, no Genesis and no GPU: `LinkbarRotateLayout` is pure arithmetic on
the task config, so the facts the verifier and the painted zones both rest on can
be settled here:

1. `in_zone` flips exactly at `half_width_deg` either side of a zone's centre.
2. The two zones never claim the same angle (strictly inside; touching zones
   share exactly their boundary angle, which is allowed).
3. No part of the beam is painted a zone's colour, and the target reaches a
   policy only through the instruction (which names the colour) and `goal_id`
   (that colour's index), which have to agree -- the 2026-09-09 change that took
   every marker colour off the beam.
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

from topogym.tasks_legacy.connectivity.linkbar_rotate_to_zone import (  # noqa: E402
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
    # Nothing on the beam is painted a zone's colour. The parts the builder paints
    # -- beam, shaft (which the pin, its collar and the knob's cap share) and knob
    # -- must all stay off the palette, or "turn to the zone that matches the part
    # on the beam" would answer the task without reading the sentence.
    bar = layout.cfg.linkbar
    palette = {
        name: [float(v) for v in layout.cfg.zones.colors[name]]
        for name in layout.cfg.zones.colors
    }
    beam_parts = {
        "beam": [float(v) for v in bar.beam.color],
        "axle/pin/collar/cap": [float(v) for v in bar.axle.color],
        "knob": [float(v) for v in bar.knob.color],
    }
    for part, rgb in beam_parts.items():
        for name, zone_rgb in palette.items():
            if rgb == zone_rgb:
                failures.append(
                    f"the beam's {part} is painted {name}, a zone colour: "
                    "the marker on the beam is back"
                )
    print(f"beam parts={beam_parts} palette={sorted(palette)}", flush=True)

    # The target reaches a policy two ways, and the two have to agree: the
    # sentence names a colour, and the integer is that colour's index.
    if layout.zone_for_colour(layout.target_colour()) != target:
        failures.append(
            f"zone_for_colour({layout.target_colour()!r}) is not the target zone {target}"
        )
    colour_keys = [str(name) for name in layout.cfg.zones.colors]
    if colour_keys[layout.goal_id()] != layout.target_colour():
        failures.append(
            f"goal_id {layout.goal_id()} does not index back to the target colour "
            f"{layout.target_colour()!r} in {colour_keys}"
        )
    print(f"target={target} target_colour={layout.target_colour()} "
          f"goal_id={layout.goal_id()} "
          f"zones={[layout.zone_color_name(z) for z in LINKBAR_ZONES]}", flush=True)

    # ... and the sentence is what names the target, so it has to follow the draw.
    swapped = LinkbarRotateLayout(load_cfg(**{"zones.target": other}))
    if layout.instruction() == swapped.instruction():
        failures.append("the instruction does not change when zones.target does")
    if layout.zone_color_name(target) not in layout.instruction():
        failures.append(f"the instruction does not name the target's colour: {layout.instruction()!r}")
    if swapped.goal_id() == layout.goal_id():
        failures.append("goal_id does not change when zones.target does")
    print(f"instruction={layout.instruction()!r} / target {other}: {swapped.instruction()!r}",
          flush=True)

    # What `validate` refuses, each expressed against the config's own numbers:
    # spans are 2 * half_width wide, centres must be >= 2 * half_width apart and
    # >= half_width + pin_start_margin from the beam's start, and must sit within
    # the rail's ends minus the half width.
    keep_out_deg = half_deg + float(layout.cfg.zones.pin_start_margin_deg)
    expect_reject(failures, "overlap",
                  **{"zones.color_1.angle_deg": 30.0,
                     "zones.color_2.angle_deg": 30.0 + 2.0 * half_deg - 1.0})
    expect_reject(failures, "off_rail",
                  **{"zones.color_2.angle_deg": float(layout.cfg.rail.end_deg) - half_deg + 1.0})
    expect_reject(failures, "pin_in_zone", **{"zones.color_1.angle_deg": 0.5 * half_deg})
    expect_reject(failures, "pin_near_zone", **{"zones.color_1.angle_deg": -(keep_out_deg - 0.5)})
    expect_reject(failures, "init_off_rail", **{"linkbar.init_angle_deg": 95.0})
    expect_reject(failures, "same_colour", **{"zones.assignment.color_2": "red"})
    expect_reject(failures, "unknown_target", **{"zones.target": "middle"})
    # These four are the boundary of what `validate` accepts, so they are computed
    # from the config's own half width and margin rather than written down: the
    # half width moved 8 -> 12 deg on 2026-09-10 and hard-coded copies of it here
    # turned into eight spurious failures.
    keep_out = half_deg + float(layout.cfg.zones.pin_start_margin_deg)
    rail_edge_deg = float(layout.cfg.rail.end_deg) - half_deg
    expect_accept(failures, "same_side",
                  **{"zones.color_1.angle_deg": 30.0,
                     "zones.color_2.angle_deg": 30.0 + 2.0 * half_deg + 6.0})
    expect_accept(failures, "touching",
                  **{"zones.color_1.angle_deg": 30.0,
                     "zones.color_2.angle_deg": 30.0 + 2.0 * half_deg})
    expect_accept(failures, "rail_edge",
                  **{"zones.color_1.angle_deg": -rail_edge_deg,
                     "zones.color_2.angle_deg": rail_edge_deg})
    expect_accept(failures, "pin_at_margin", **{"zones.color_1.angle_deg": -keep_out})
    # Sweep steps follow the sweep at 0.23 deg/step (55 deg -> 240, the accepted
    # rate), floored at 120; sign of the sweep does not matter.
    for sweep_deg, want in ((55.0, 240), (-55.0, 240), (105.0, 457), (15.6, 120), (0.0, 120)):
        got = layout.steps_arc(math.radians(sweep_deg))
        print(f"steps_arc({sweep_deg:+6.1f}deg) = {got}", flush=True)
        if got != want:
            failures.append(f"steps_arc({sweep_deg}) = {got}, expected {want}")

    edge = 30.0 + half_deg  # the angle the two touching zones share
    touching = LinkbarRotateLayout(load_cfg(**{"zones.color_1.angle_deg": 30.0,
                                                "zones.color_2.angle_deg": 30.0 + 2.0 * half_deg}))
    if touching.zone_at(math.radians(edge - 0.1)) != "color_1" or \
            touching.zone_at(math.radians(edge + 0.1)) != "color_2":
        failures.append("touching zones: zone_at does not switch at the shared edge")

    # The beam's start is derived onto init_span minus each zone's keep-out
    # (half_width + pin_start_margin). A zone just inside the span's low end cuts
    # a piece off the bottom; a zone at 0 splits the span in two; two zones
    # straddling it leave nothing. All three expectations follow from keep_out.
    lo_span, hi_span = (float(v) for v in layout.cfg.linkbar.init_span_deg)
    one_side = lo_span - 1.0  # a zone here cuts [lo_span, one_side + keep_out]
    cut = LinkbarRotateLayout(load_cfg(**{"zones.color_1.angle_deg": one_side,
                                           "zones.color_2.angle_deg": 60.0}))
    want_cut = [(round(one_side + keep_out, 6), round(hi_span, 6))]
    segments = [(round(s, 6), round(e, 6)) for s, e in cut.init_angle_segments()]
    print(f"init segments (zone at {one_side:+.0f}): {segments}", flush=True)
    if segments != want_cut:
        failures.append(f"init_angle_segments = {segments}, expected {want_cut}")
    ends = (cut.init_angle_from_frac(0.0), cut.init_angle_from_frac(1.0))
    if not (abs(ends[0] - want_cut[0][0]) < 1e-9 and abs(ends[1] - hi_span) < 1e-9):
        failures.append(f"init_angle_from_frac ends = {ends}, expected {want_cut[0]}")
    split = LinkbarRotateLayout(load_cfg(**{"zones.color_1.angle_deg": -(2.0 * keep_out + 2.0),
                                             "zones.color_2.angle_deg": 0.0}))
    want_split = [(round(lo_span, 6), round(-keep_out, 6)), (round(keep_out, 6), round(hi_span, 6))]
    segments = [(round(s, 6), round(e, 6)) for s, e in split.init_angle_segments()]
    if segments != want_split:
        failures.append(f"split init_angle_segments = {segments}, expected {want_split}")
    mid = split.init_angle_from_frac(0.5)
    if abs(mid - (-keep_out)) > 1e-9 and abs(mid - keep_out) > 1e-9:
        failures.append(f"init_angle_from_frac(0.5) on two equal pieces = {mid}, expected a piece end")
    # Two keep-outs that between them cover the whole init span: the first starts
    # its keep-out exactly at the span's low end, the second picks up where the
    # first leaves off. Their centres are 2 * keep_out apart, which clears the
    # 2 * half_width separation rule because the margin is positive.
    first = lo_span + keep_out
    covered = LinkbarRotateLayout(load_cfg(**{"zones.color_1.angle_deg": first,
                                               "zones.color_2.angle_deg": first + 2.0 * keep_out}))
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
