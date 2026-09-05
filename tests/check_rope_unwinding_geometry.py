"""Offline gate for the rope_unwinding layout: spawn helix, oracle, and topology.

rope_winding's mirror (task book 2.5): the rope spawns already wound
`winding.start_turns` times around the post and the oracle takes it off. Runs
the REAL planner, the REAL route expansion (`helix_around`) and the REAL
winding-number code against the REAL task config through the stand-in layout of
`check_rope_winding_geometry.py`, so a layout edit that breaks the task is
caught without a GPU run.

What it proves:
  - the spawn route reads exactly +-start_turns before anything moves, sits on
    the post's shaft clear of its surface, and its wraps clear each other;
  - the free tail leaves the top wrap without a kink and without running back
    into the post;
  - the oracle orbits AGAINST the wrap, descends one wrap per turn from the top
    one, and stays below the post top (the gateway is never used);
  - taking the wraps off one by one reads start_turns, ..., 1, 0 on a taut rope,
    and the forced wrong-way orbit reads 2 * start_turns (the contrast pair);
  - the rope is long enough at its tightest moment -- the START, with every
    wrap still on -- with margin, and the table of `spawn_arc.sweep_deg` per
    `start_turns` is printed for the config;
  - (variation, 2026-09-04) the spawn route's rules restore the hand-written
    baseline (lead-in, plug point, lowest wrap, target x), a cw wrap is the
    ccw layout mirrored in y, every vertex of the yaml's `variation:` envelope
    passes the twelve feasibility rows, and two out-of-envelope layouts fail.

    python tests/check_rope_unwinding_geometry.py
    python tests/check_rope_unwinding_geometry.py --start-turns 3 --sweep-deg 130

Needs the project venv (numpy + PyYAML; `topogym.planning` and
`topogym.supervision.rope_winding` are numpy-only).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.check_rope_winding_geometry import (  # noqa: E402
    PREFABS,
    TASK_ORIGIN,
    StandInLayout,
    check,
    densify,
    failures,
    wrap,
)
from topogym.planning.rope_winding_planner import (  # noqa: E402
    SLACK_BAND,
    WindingSpec,
    free_end_winding_delta,
    plan_rope_winding_route,
    post_center,
    spawn_winding,
    taut_demand,
)
from topogym.planning.waypoint import helix_route_points  # noqa: E402
from topogym.primitives.pick_place import HAND_TO_PAD_Z  # noqa: E402
from topogym.supervision.rope_winding import (  # noqa: E402
    winding_number,
    winding_sweep,
    winding_topological,
)
from topogym.tasks.routing._rope_unwinding_geometry import (  # noqa: E402
    fixture_task_pos,
    rope_unwinding_checks,
    target_x_from_frac,
    wind_z_bounds,
    wind_z_from_frac,
)

TASK_CFG = REPO / "configs" / "task_configs" / "rope_unwinding_topogym_tabletop_v1.yaml"
# Underside of the hand's collision body, above the finger pads (`hand_c` z
# lower bound 0.0259 against HAND_TO_PAD_Z) -- what would hit the post's top.
PALM_ABOVE_PADS = HAND_TO_PAD_Z - 0.0259


def polyline_length(points) -> float:
    return float(np.sum(np.linalg.norm(np.diff(np.asarray(points, dtype=float), axis=0), axis=1)))


def arc_length(chord: float, sweep_deg: float) -> float:
    sweep = abs(math.radians(sweep_deg))
    return chord * sweep / (2.0 * math.sin(0.5 * sweep))


def sweep_for_length(chord: float, length: float) -> float:
    """The arc sweep (degrees) whose length over `chord` is `length`; bisection."""

    low, high = 1.0, 359.0
    for _ in range(60):
        mid = 0.5 * (low + high)
        if arc_length(chord, mid) < length:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


class UnwindingStandIn(StandInLayout):
    """The stand-in with rope_unwinding's mirror rule: a cw wrap reflects every
    fixture in y (`_rope_unwinding_geometry.mirror_sign`), as `RopeUnwindingLayout` does."""

    def fixture_pos(self, name, *, z=None):
        pos = fixture_task_pos(self.cfg, name)
        if z is not None:
            pos[2] = float(z)
        return self.position_to_world(pos)


def resolve(raw, prefabs, *, start_turns=None, sweep_deg=None):
    """Dereference the `${}` interpolations the checks below read."""

    if abs(float(raw["rope"]["radius"]) - float(prefabs["rope_pbd"]["radius"])) > 1e-12:
        raise SystemExit("rope.radius in the task yaml must equal prefabs.rope_pbd.radius (literal copy)")
    if abs(float(raw["fixtures"]["POST"]["base_height"]) - float(prefabs["rope_routing_post"]["base_height"])) > 1e-12:
        raise SystemExit("POST.base_height in the task yaml must equal prefabs.rope_routing_post.base_height")
    raw["rope"]["endpoint_handle"]["z_offset"] = raw["physical_handle"]["z_offset"]
    if start_turns is not None:
        raw["winding"]["start_turns"] = int(start_turns)
    if sweep_deg is not None:
        raw["rope"]["spawn_arc"]["sweep_deg"] = float(sweep_deg)
    return raw


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-turns", type=int, help="override task.winding.start_turns")
    parser.add_argument("--sweep-deg", type=float, help="override task.rope.spawn_arc.sweep_deg")
    args = parser.parse_args(argv)

    prefabs = yaml.safe_load(PREFABS.read_text(encoding="utf-8"))
    raw = resolve(
        yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")),
        prefabs,
        start_turns=args.start_turns,
        sweep_deg=args.sweep_deg,
    )
    cfg = wrap(raw)
    layout = UnwindingStandIn(cfg)
    spec = WindingSpec.from_config(cfg)
    center = post_center(layout, spec)
    post = cfg.fixtures[spec.post]
    rope_r = float(cfg.rope.radius)
    settle_radius = float(post.radius) + rope_r
    wrap_band = float(post.radius) + 2.0 * rope_r
    post_top_task = float(post.z) + 0.5 * float(post.height)
    post_top = layout.world_z(post_top_task)
    anchor = layout.route_point({"fixture": "S", "relation": "center"})

    print(
        f"rope_unwinding: start_turns={spec.start_turns} turns={spec.turns} "
        f"direction={spec.direction} orbit={'ccw' if spec.orbit_sign > 0 else 'cw'} "
        f"initial_winding={spec.initial_winding:+.1f} target_winding={spec.target_winding:+.1f}"
    )
    check("the episode starts wound and ends unwound", spec.start_turns > 0 and spec.turns == 0)
    check(
        "the hand orbits against the wrap",
        spec.orbit_sign == -spec.sign and spec.orbit_direction is None,
        f"wrap {spec.direction}, orbit sign {spec.orbit_sign:+.0f}",
    )

    print("\nspawn")
    spawn = layout.route_polyline("initial")
    dense = densify(spawn)
    radial = np.linalg.norm(spawn[:, :2] - center[None, :2], axis=1)
    on_post = radial <= wrap_band
    helix = spawn[on_post]
    check(
        "the spawn route already reads +-start_turns",
        abs(winding_number(dense, center, wrap_band) - spec.initial_winding) < 1e-6,
        f"winding {winding_number(dense, center, wrap_band):+.3f}, sweep "
        f"{winding_sweep(dense, center, wrap_band):+.3f} turns",
    )
    check(
        "the wraps sit on the post's shaft, clear of its surface",
        bool(len(helix)) and float(radial[on_post].min()) >= settle_radius - 1e-9,
        f"centreline radius {radial[on_post].min():.4f}..{radial[on_post].max():.4f} vs "
        f"settled {settle_radius:.4f} (post {float(post.radius):.3f} + rope {rope_r:.3f})",
    )
    turn_gap = spec.climb_per_turn - 2.0 * rope_r
    check(
        "consecutive wraps clear each other",
        turn_gap > 0.0,
        f"{turn_gap * 1000:+.1f} mm between wraps (climb {spec.climb_per_turn * 1000:.0f} mm, "
        f"rope {2 * rope_r * 1000:.0f} mm thick)",
    )
    top_wrap = spec.wind_z_start + spec.start_turns * spec.climb_per_turn + rope_r
    check(
        "the whole spiral fits below the post top",
        top_wrap <= post_top_task - 0.010 + 1e-9,
        f"top wrap at {top_wrap:.3f} vs {post_top_task - 0.010:.3f} usable; this post "
        f"holds {int((post_top_task - 0.010 - spec.wind_z_start) // spec.climb_per_turn)} wraps",
    )
    flare_top = float(prefabs["rope_routing_post"]["base_height"])
    check(
        "the bottom wrap is above the post's flared base",
        spec.wind_z_start - rope_r > flare_top,
        f"bottom wrap underside {(spec.wind_z_start - rope_r) * 1000:.0f} mm vs flare "
        f"{flare_top * 1000:.0f} mm",
    )
    # The free tail: from the top wrap to the plug on the board. It has to leave
    # along the wrap's own tangent (a kink there is a bend the rope takes at
    # spawn, on the post's surface) and must not swing back into the post.
    last_on = int(np.flatnonzero(on_post)[-1])
    tangent = spawn[last_on] - spawn[last_on - 1]
    leave = spawn[last_on + 1] - spawn[last_on]
    kink = math.degrees(
        math.acos(
            float(np.dot(tangent[:2], leave[:2]))
            / (np.linalg.norm(tangent[:2]) * np.linalg.norm(leave[:2]))
        )
    )
    check(
        "the tail leaves the top wrap along its tangent",
        kink < 30.0,
        f"{kink:.1f} degrees between the wrap's tangent and the tail's first leg",
    )
    tail_radial = radial[last_on + 1 :]
    check(
        "the tail does not run back into the post",
        bool(np.all(tail_radial[1:] > wrap_band)),
        f"closest tail point {tail_radial[1:].min():.4f} from the axis vs band {wrap_band:.4f}",
    )
    check(
        "the tail descends to the board without a fold",
        float(spawn[-1][2]) < float(spawn[last_on][2])
        and (spawn[last_on][2] - spawn[-1][2]) / polyline_length(spawn[last_on:]) < 0.5,
        f"drops {(spawn[last_on][2] - spawn[-1][2]) * 1000:.0f} mm over "
        f"{polyline_length(spawn[last_on:]) * 1000:.0f} mm of tail",
    )

    print("\noracle")
    command, plan = plan_rope_winding_route(layout)
    labels = [waypoint.label for waypoint in plan.waypoints]
    points = np.array([waypoint.position for waypoint in plan.waypoints])
    detour = "to_C_around" in labels
    expected = 2 + spec.start_turns * spec.arc_points_per_turn + 3 + int(detour)
    check(
        "waypoint count = lift + entry + start_turns*points + exit (+ around) + hover + place",
        len(labels) == expected,
        f"{len(labels)} (expected {expected}); "
        + ("the run to C goes round the far side of the post" if detour else "straight to C"),
    )
    orbit = [index for index, label in enumerate(labels) if label.startswith("wind_t")]
    radii = np.linalg.norm(points[orbit][:, :2] - center[None, :2], axis=1)
    check(
        "orbit points sit on wind_radius",
        bool(np.allclose(radii, spec.wind_radius)),
        f"{radii.min():.4f}..{radii.max():.4f} vs {spec.wind_radius}",
    )
    heights = points[orbit][:, 2]
    entry_z = points[labels.index("wind_entry")][2]
    check(
        "the orbit starts level with the top wrap and descends one wrap per turn",
        abs(entry_z - layout.world_z(spec.wind_z_start + spec.start_turns * spec.climb_per_turn))
        < 1e-9
        and bool(np.all(np.diff(heights) < 0))
        and abs(heights[-1] - layout.world_z(spec.wind_z_start)) < 1e-9,
        f"{entry_z - TASK_ORIGIN[2]:.4f} -> {heights[-1] - TASK_ORIGIN[2]:.4f} over "
        f"{spec.orbit_turns} turns",
    )
    check(
        "oracle stays below the post top (the gateway is not used)",
        float(heights.max()) < post_top,
        f"max {heights.max():.4f} vs top {post_top:.4f}",
    )
    palm_bottom = float(heights.min()) + PALM_ABOVE_PADS
    check(
        "the palm clears the post top at every orbit height",
        palm_bottom > post_top,
        f"palm underside {palm_bottom - TASK_ORIGIN[2]:.3f} at the lowest orbit vs post top "
        f"{post_top_task:.3f}",
    )
    azimuths = np.unwrap(np.arctan2(points[orbit][:, 1] - center[1], points[orbit][:, 0] - center[0]))
    check(
        "the orbit turns against the wrap",
        abs((azimuths[-1] - azimuths[0]) / (2.0 * math.pi) + spec.sign * (spec.orbit_turns - 1.0 / spec.arc_points_per_turn)) < 1e-6,
        f"hand sweeps {(azimuths[-1] - azimuths[0]) / (2 * math.pi):+.3f} turns, wrap is {spec.direction}",
    )

    print("\ntopology")
    # A taut rope after k orbits: anchor -> the wraps still on (start_turns - k)
    # -> straight to the hand. The count has to step down by exactly one per
    # orbit and end at zero; that is what separates unwinding from dragging the
    # plug around the post.
    readings = []
    for taken in range(spec.start_turns + 1):
        left = spec.start_turns - taken
        hand = points[orbit[taken * spec.arc_points_per_turn - 1]] if taken else points[orbit[0]]
        if left:
            rope = [anchor]
            rope.extend(
                helix_route_points(
                    anchor,
                    center,
                    settle_radius,
                    left,
                    spec.climb_per_turn,
                    spec.sign,
                    z_start=layout.world_z(spec.wind_z_start),
                )
            )
            rope.append(hand)
        else:
            rope = [anchor, hand]
        readings.append(
            (
                winding_number(densify(np.asarray(rope)), center, wrap_band),
                winding_topological(densify(np.asarray(rope)), center),
            )
        )
    check(
        "taking the wraps off one by one reads start_turns, ..., 1, 0",
        all(
            abs(on_post - spec.sign * (spec.start_turns - taken)) < 1e-6
            and abs(whole - spec.sign * (spec.start_turns - taken)) < 1e-6
            for taken, (on_post, whole) in enumerate(readings)
        ),
        " -> ".join(f"{on_post:+.2f}/{whole:+.2f}" for on_post, whole in readings)
        + " (on post / whole rope)",
    )
    # The verdict's invariant must not be fooled by slack. The shape a peeled
    # wrap took on 2026-08-27 (start_turns=2): the rope comes in from the anchor
    # along its tangent, is dragged against the post three quarters of the way
    # round, and its slack goes back the OTHER way round the outside to the hand.
    # On the post that is 0.73 of a turn and rounds to one; round the whole
    # rope, closed end to end, it is nothing -- and the hand has orbited exactly
    # start_turns times, so nothing is right.
    hug_turns = 0.73
    hug = [anchor]
    hug.extend(
        helix_route_points(anchor, center, settle_radius, hug_turns, 0.0, spec.sign, z_start=anchor[2])
    )
    hug_end = float(np.arctan2(hug[-1][1] - center[1], hug[-1][0] - center[0]))
    hand = points[orbit[-1]]
    hand_bearing = float(np.arctan2(hand[1] - center[1], hand[0] - center[0]))
    back = (hand_bearing - hug_end) % (2.0 * np.pi) - 2.0 * np.pi  # the cw way
    hug.extend(
        [
            center + np.array([0.05 * np.cos(a), 0.05 * np.sin(a), 0.0])
            for a in np.linspace(hug_end, hug_end + back, 60)
        ]
    )
    hug.append(hand)
    hug = densify(np.asarray(hug))
    check(
        "a loose three-quarter hug reads as a wrap on the post but not on the whole rope",
        abs(winding_number(hug, center, wrap_band) - spec.sign) < 1e-6
        and abs(winding_topological(hug, center)) < 1e-6,
        f"on post {winding_number(hug, center, wrap_band):+.2f}, whole rope "
        f"{winding_topological(hug, center):+.2f}",
    )
    check(
        "the planned orbit lands on the target",
        abs(spec.expected_winding - spec.target_winding) < 1e-9,
        f"expected {spec.expected_winding:+.1f}, target {spec.target_winding:+.1f}",
    )
    # The count is closed from the free end back to the anchor, so it moves
    # whenever the free end crosses the ray opposite the anchor -- on the way
    # to C as much as during the orbits. 2026-08-27: two and three wraps both
    # read 0 after the last orbit and +1 at C, because the straight run to C
    # crossed that ray once more. The planner now picks the side; this is the
    # sum along the whole free-end path, spawn to C.
    spawn_reading = spawn_winding(layout, spec)
    delta = free_end_winding_delta([spawn[-1]] + list(points), center, anchor)
    check(
        "the spawn route reads start_turns with the task's closure too",
        abs(spawn_reading - spec.initial_winding) < 1e-6,
        f"{spawn_reading:+.2f}",
    )
    check(
        "spawn reading + the free end's whole path (orbits AND the run to C) = target",
        abs(spawn_reading + delta - spec.target_winding) < 1e-6,
        f"{spawn_reading:+.0f} {delta:+d} = {spawn_reading + delta:+.0f}, target "
        f"{spec.target_winding:+.0f}"
        + (" (via to_C_around)" if detour else ""),
    )
    straight = [spawn[-1]] + [p for p, l in zip(points, labels) if l != "to_C_around"]
    if detour:
        check(
            "...and the straight run to C would have been one off",
            abs(spawn_reading + free_end_winding_delta(straight, center, anchor) - spec.target_winding) > 0.5,
            f"straight: {spawn_reading + free_end_winding_delta(straight, center, anchor):+.0f}",
        )
    wrong = WindingSpec.from_config(
        wrap({**raw, "winding": {**raw["winding"], "orbit_direction": raw["winding"]["direction"]}})
    )
    check(
        "the forced wrong-way orbit reads 2 * start_turns (the contrast pair)",
        wrong.orbit_sign == spec.sign
        and abs(wrong.expected_winding - 2.0 * spec.initial_winding) < 1e-9,
        f"orbit_direction={wrong.orbit_direction}: expected {wrong.expected_winding:+.1f} "
        f"against a target of {wrong.target_winding:+.1f}",
    )

    print("\nrope length")
    length = polyline_length(spawn)
    need, at = taut_demand(layout, spec, plan.waypoints)
    slack = (length - need) / need
    low, high = SLACK_BAND
    check(
        "the tightest moment is the start, with every wrap still on",
        at in ("lift_from_port", "wind_entry") or at.startswith("wind_t1_"),
        f"{need:.3f} m needed at {at}",
    )
    check(
        "slack stays in the band that neither coils nor over-tightens",
        low <= slack <= high,
        f"{slack * 100:.1f}% at start_turns={spec.start_turns}, sweep "
        f"{float(cfg.rope.spawn_arc.sweep_deg):.0f}deg, rope {length:.3f} m",
    )
    # The pairing table: one wrap costs `2 pi * settle_radius` of demand but the
    # spawn helix (a standoff wider) pays most of it back, so the tail's sweep
    # moves only slowly with the count.
    print(
        f"  [--] one wrap on the post eats {2 * math.pi * settle_radius * 1000:.0f} mm; "
        "the tail arc's sweep is what pays the difference"
    )
    tail_chord = float(np.linalg.norm(spawn[-1][:2] - spawn[last_on][:2]))
    for start_turns in (1, 2, 3):
        variant = wrap(
            resolve(
                yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")),
                prefabs,
                start_turns=start_turns,
                sweep_deg=float(cfg.rope.spawn_arc.sweep_deg),
            )
        )
        variant_layout = UnwindingStandIn(variant)
        variant_spec = WindingSpec.from_config(variant)
        _, variant_plan = plan_rope_winding_route(variant_layout)
        variant_spawn = variant_layout.route_polyline("initial")
        variant_need, _ = taut_demand(variant_layout, variant_spec, variant_plan.waypoints)
        without_tail = polyline_length(variant_spawn) - arc_length(
            tail_chord, float(cfg.rope.spawn_arc.sweep_deg)
        )
        wanted = variant_need * (1.0 + 0.5 * (low + high)) - without_tail
        signed = math.copysign(
            sweep_for_length(tail_chord, wanted), float(cfg.rope.spawn_arc.sweep_deg)
        )
        print(
            f"  [--] start_turns={start_turns}: needs {variant_need:.3f} m taut, so "
            f"sweep_deg ~{signed:.0f} for mid-band"
        )

    print("\nvariation envelope")
    _check_variation_envelope(prefabs)

    print("\n" + ("FAIL: " + ", ".join(failures) if failures else "PASS: all checks"))
    return 1 if failures else 0


def _set(raw, dotted, value):
    node = raw
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


def _derived_layout(raw):
    """The yaml's two derivations by hand (the hooks live in a module that imports Genesis)."""

    cfg = wrap(raw)
    raw["winding"]["wind_z_start"] = wind_z_from_frac(cfg, float(raw["winding"]["wind_z_frac"]))
    cfg = wrap(raw)
    raw["fixtures"]["C"]["x"] = target_x_from_frac(UnwindingStandIn(cfg), float(raw["fixtures"]["C"]["x_frac"]))
    return UnwindingStandIn(wrap(raw))


def _check_variation_envelope(prefabs) -> None:
    import itertools

    base = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
    layout = UnwindingStandIn(wrap(base))
    spawn = layout.route_polyline("initial") - TASK_ORIGIN
    lead_in, plug = spawn[1], spawn[-1]
    # The rules restore the hand-written baseline. The plug moves 28 mm from
    # the old literal (-0.006, -0.218): that point sat 5 degrees off the top
    # wrap's tangent, the rule puts it on it.
    check(
        "the lead-in rule restores the hand-written point (-0.114, 0.083)",
        abs(lead_in[0] + 0.114) < 0.001 and abs(lead_in[1] - 0.083) < 0.001,
        f"({lead_in[0]:+.4f}, {lead_in[1]:+.4f})",
    )
    check(
        "the tail-arc rule puts the plug on the top wrap's tangent at (-0.034, -0.214)",
        abs(plug[0] + 0.034) < 0.001 and abs(plug[1] + 0.214) < 0.001,
        f"({plug[0]:+.4f}, {plug[1]:+.4f}), chord {float(base['rope']['spawn_arc']['chord']):.3f}",
    )
    derived = _derived_layout(resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs))
    check(
        "wind_z_frac 0.5 and C.x_frac 0.5 restore wind_z_start 0.045 and C.x 0.075",
        abs(float(derived.cfg.winding.wind_z_start) - 0.045) < 1e-9
        and abs(float(derived.cfg.fixtures.C.x) - 0.075) < 1e-9,
        f"wind_z_start {float(derived.cfg.winding.wind_z_start):.4f}, C.x {float(derived.cfg.fixtures.C.x):.4f}",
    )
    three = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs, start_turns=3)
    three["winding"]["climb_per_turn"] = 0.016
    lo, hi = wind_z_bounds(wrap(three))
    check(
        "three wraps of 0.016 leave the lowest wrap the window [0.035, 0.043]",
        abs(lo - 0.035) < 1e-9 and abs(hi - 0.043) < 1e-9,
        f"[{lo:.3f}, {hi:.3f}]",
    )
    # cw is the mirror layout: same spawn route and same oracle waypoints with
    # y negated, so every feasibility row reads the same for the two senses.
    mirrored = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
    mirrored["winding"]["direction"] = "cw"
    cw = UnwindingStandIn(wrap(mirrored))
    cw_spawn = cw.route_polyline("initial") - TASK_ORIGIN
    _, ccw_plan = plan_rope_winding_route(layout)
    _, cw_plan = plan_rope_winding_route(cw)
    ccw_pts = np.array([w.position for w in ccw_plan.waypoints]) - TASK_ORIGIN
    cw_pts = np.array([w.position for w in cw_plan.waypoints]) - TASK_ORIGIN
    check(
        "a cw wrap is the ccw layout mirrored in y (spawn route and oracle waypoints)",
        cw_spawn.shape == spawn.shape
        and bool(np.allclose(cw_spawn * np.array([1.0, -1.0, 1.0]), spawn, atol=1e-9))
        and cw_pts.shape == ccw_pts.shape
        and bool(np.allclose(cw_pts * np.array([1.0, -1.0, 1.0]), ccw_pts, atol=1e-9)),
        f"{len(cw_spawn)} spawn points, {len(cw_pts)} waypoints",
    )
    rows = {name: (measured, limit, ok) for name, measured, limit, ok in rope_unwinding_checks(layout)}
    check(
        "the twelve feasibility rows pass on the baseline",
        len(rows) == 12 and all(ok for _, _, ok in rows.values()),
        " ".join(f"{n}={m:+.4f}" for n, (m, _, _) in rows.items()),
    )

    # Every vertex of the envelope: each uniform axis at both ends, each choice
    # axis at every value, through the two derivations and the twelve rows.
    axes = []
    for entry in base["variation"]:
        if entry["kind"] == "uniform":
            axes.append((entry["path"], [float(entry["lo"]), float(entry["hi"])]))
        elif entry["kind"] == "choice":
            axes.append((entry["path"], list(entry["values"])))
    tightest: dict[str, float] = {}
    infeasible = []
    count = 0
    for values in itertools.product(*(vals for _, vals in axes)):
        raw = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
        for (path, _), value in zip(axes, values):
            _set(raw, path, value)
        count += 1
        try:
            corner = _derived_layout(raw)
            bad = [n for n, _, _, ok in rope_unwinding_checks(corner) if not ok]
            for n, m, l, _ in rope_unwinding_checks(corner):
                margin = (l - m) if n == "hand_reach" else (m - l)
                tightest[n] = min(tightest.get(n, float("inf")), margin)
        except ValueError as exc:
            bad = [f"derive: {exc}"]
        if bad:
            infeasible.append((values, bad))
    check(
        f"all {count} envelope corners are feasible",
        not infeasible,
        f"{len(infeasible)} infeasible" + (f"; first: {infeasible[0]}" if infeasible else ""),
    )
    print("  [--] tightest margin per row over the corners: " + " ".join(f"{n}={m:+.4f}" for n, m in tightest.items()))

    # Out of the envelope, the rows say no.
    far = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
    far["fixtures"]["POST"]["x"] = 0.060
    far["reach"]["max_hand_dist"] = 0.700
    far_rows = {n: ok for n, _, _, ok in rope_unwinding_checks(_derived_layout(far))}
    check("a post at x=0.060 fails hand_reach against the 0.700 bar the rigid tasks use", not far_rows["hand_reach"])
    near = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
    near["fixtures"]["S"]["x"], near["fixtures"]["S"]["y"] = -0.050, 0.050
    near_rows = {n: ok for n, _, _, ok in rope_unwinding_checks(_derived_layout(near))}
    check("an anchor 42 mm from the post fails anchor_clears_post", not near_rows["anchor_clears_post"])
    # The contrast pair must not make a layout infeasible: with the orbit forced
    # the wrap's own way the rows still pass (they plan with the oracle's orbit),
    # and the planner drops the detour instead of raising on a layout that
    # needs one (the wrong-way run then reads 2 * start_turns, as the verdict
    # should see).
    forced = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs)
    forced["winding"]["orbit_direction"] = "same"
    forced_rows = {n: ok for n, _, _, ok in rope_unwinding_checks(_derived_layout(forced))}
    check("orbit_direction=same leaves the twelve rows unchanged", all(forced_rows.values()))
    detour_raw = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs, start_turns=3)
    detour_raw["fixtures"]["POST"]["x"], detour_raw["fixtures"]["POST"]["y"] = -0.020, -0.020
    detour_raw["fixtures"]["S"]["x"], detour_raw["fixtures"]["S"]["y"] = -0.120, 0.130
    detour_raw["fixtures"]["C"]["x_frac"], detour_raw["fixtures"]["C"]["y"] = 1.0, -0.100
    detour_layout = _derived_layout(detour_raw)
    _, detour_plan = plan_rope_winding_route(detour_layout)
    detour_raw["winding"]["orbit_direction"] = "same"
    _, forced_plan = plan_rope_winding_route(_derived_layout(detour_raw))
    check(
        "a layout that needs to_C_around goes straight when the orbit is forced wrong",
        any(w.label == "to_C_around" for w in detour_plan.waypoints)
        and not any(w.label == "to_C_around" for w in forced_plan.waypoints),
        f"oracle {len(detour_plan.waypoints)} waypoints, forced {len(forced_plan.waypoints)}",
    )
    tight = resolve(yaml.safe_load(TASK_CFG.read_text(encoding="utf-8")), prefabs, start_turns=3)
    tight["winding"]["climb_per_turn"] = 0.010
    tight_rows = {n: ok for n, _, _, ok in rope_unwinding_checks(_derived_layout(tight))}
    check(
        "three wraps at climb 0.010 fail wrap_gap (tetgen self-intersects the tube at a 2 mm skin gap)",
        not tight_rows["wrap_gap"],
    )


if __name__ == "__main__":
    raise SystemExit(main())
