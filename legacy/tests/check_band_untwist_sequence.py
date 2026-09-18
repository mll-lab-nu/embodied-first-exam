"""Offline gate for band_untwist's shape module and move model (no GPU, no Genesis).

What it pins down, section by section:

1. shapes (`topogym/tasks_legacy/entangle/_band_shapes.py`): each shape crosses itself
   the number of times it should; the yaml's per-shape over/under leaves raise
   the strand they name, read back as a crossing sequence; the teardrop's rope
   length matches its formula (tangents + far-side arc r(pi + 2 phi)).
2. move model (`topogym/planning/band_untwist_sequence.py`):
   - figure-8 regression: on every layout the GPU has run (the 13 corners of
     `runs/band_untwist_corners/` and seeds 0-9 of the placefix run) the plan is
     one move from the over end, the hand height is the GPU's measured lift to
     within 10 mm, and wherever today's landing already meets the stricter
     limits (swing >= min_rotation_deg, lay-down >= min_lay_down, slack in
     [slack_min, slack_max_single]) it is unchanged to within 5 mm -- the rule
     moves only the landings it has to;
   - the no-drag rule: on the 8 only the over end has a lift, and a lift that
     takes both passes of a crossing (a whole curl) is never offered;
   - one plan per shape: every crossing removed, the predicted crossing
     sequence after each move matches a recount, every landing within the
     limits (a two-move plan lays every rope at ``slack_min_multi`` or
     straighter), and O|-|O with a stub underneath has no plan;
   - the re-plan before a second move (``moves_done=1``, one crossing left)
     keeps the two-move rules: straight lay-down and plugs 7 cm apart;
   - the runtime landing limits (``landing_box``, ``max_reach``) move a landing
     that falls outside them rather than accept it.

    python -B tests/check_band_untwist_sequence.py
"""

from __future__ import annotations

import csv
import importlib.util
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def load_by_path(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fig8 = load_by_path("band_untwist_fig8", "topogym/tasks_legacy/entangle/_figure_eight_geometry.py")
bs = load_by_path("band_untwist_shapes", "topogym/tasks_legacy/entangle/_band_shapes.py")
seq = load_by_path("band_untwist_sequence", "topogym/planning/band_untwist_sequence.py")

COMMON = dict(over_lift=0.012, base_z=0.007, lift_ramp=0.030)
FAILS: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"[{'ok' if ok else 'FAIL'}] {message}")
    if not ok:
        FAILS.append(message)


def sequence_of(points) -> tuple:
    rope = seq.Rope.from_points(points)
    return seq.crossing_sequence(seq.crossings(rope, merge_radius=0.012))


# ------------------------------------------------------------------- shapes


def six(short_over=1, **kw):
    args = dict(loop_radius=0.035, half_angle_deg=45.0, short_len=0.06, stem_len=0.18, short_over=short_over)
    args.update(kw)
    return bs.SixSpec(**args, **COMMON)


def twist(x1=0, x2=1, **kw):
    args = dict(closed_lobe_radius=0.035, middle_lobe_radius=0.030, open_lobe_radius=0.045,
                half_angle_deg=45.0, end_gap=0.080, over_end_x1=x1, over_end_x2=x2)
    args.update(kw)
    return bs.TwistSpec(**args, **COMMON)


def curls(a=1, b=1, side="same", **kw):
    args = dict(loop_radius=0.032, half_angle_deg=30.0, stub_len=0.065, middle_len=0.14,
                stub_side=side, stub_over_a=a, stub_over_b=b)
    args.update(kw)
    return bs.CurlsSpec(**args, **COMMON)


def check_shapes() -> None:
    print("\n== shapes")
    for name, spec, count in (("six", six(), 1), ("twist", twist(), 2), ("curls", curls(), 2),
                              ("curls opposite", curls(side="opposite"), 2)):
        flat = bs.flat_path(spec)
        check(len(bs.flat_crossings(flat)) == count, f"{name}: flat path crosses itself {count} time(s)")
        check(bs.SHAPE_CROSSINGS[name.split()[0]] == count, f"{name}: SHAPE_CROSSINGS says {count}")

    # The yaml leaves raise the strand they name. Rope order runs from end 0.
    expect = {
        "six short tail on top": (six(short_over=1), (("0", "o"), ("0", "u"))),
        "six stem on top": (six(short_over=0), (("0", "u"), ("0", "o"))),
        # twist: X1 is met first from end 0 (end 0's strand), then X2, X2 again, X1 again (end 1's strand)
        "twist end 0 on top at X1, end 1 at X2": (twist(0, 1), (("0", "o"), ("1", "u"), ("1", "o"), ("0", "u"))),
        "twist end 1 on top at both": (twist(1, 1), (("0", "u"), ("1", "u"), ("1", "o"), ("0", "o"))),
        # curls: stub A, XA's loop return (the middle), then the middle into XB, XB's loop return (stub B)
        "curls both stubs on top": (curls(1, 1), (("0", "o"), ("0", "u"), ("1", "u"), ("1", "o"))),
        "curls stub A under, stub B on top": (curls(0, 1), (("0", "u"), ("0", "o"), ("1", "u"), ("1", "o"))),
    }
    for name, (spec, want) in expect.items():
        got = tuple((str(rank), kind) for rank, kind in sequence_of(bs.shape_control_points(spec)))
        check(got == want, f"{name}: crossing sequence {got}")

    # Flipping which strand is raised moves no plug.
    for name, a, b in (("six", six(1), six(0)), ("twist", twist(0, 0), twist(1, 1)), ("curls", curls(1, 1), curls(0, 0))):
        pa, pb = bs.shape_control_points(a), bs.shape_control_points(b)
        same = np.allclose(pa[0, :2], pb[0, :2]) and np.allclose(pa[-1, :2], pb[-1, :2])
        check(same, f"{name}: the plugs sit in the same place whichever strand is on top")

    for phi in (30.0, 45.0, 60.0):
        spec = six(half_angle_deg=phi, arc_points_per_quarter=400)
        loop = bs.arclength(bs.six_path(spec))[-1] - spec.short_len - spec.stem_len
        formula = bs.teardrop_length(spec.loop_radius, phi)
        check(abs(loop - formula) < 1e-5, f"teardrop at {phi:.0f} deg: sampled {loop * 1000:.2f} mm = formula {formula * 1000:.2f} mm")

    lo, _hi = bs.curls_middle_bounds(0.08, 25.0, "same", min_plug_gap=0.075, min_middle=0.10, span=0.05)
    spec = curls(stub_len=0.08, half_angle_deg=25.0, middle_len=lo)
    points = bs.shape_control_points(spec)
    gap = float(np.linalg.norm(points[0, :2] - points[-1, :2]))
    check(abs(gap - 0.075) < 1e-6, f"curls middle lower bound keeps the plugs 75 mm apart: {gap * 1000:.2f} mm")


# ------------------------------------------------------------------- model


MEASURED_LIFT_MM = {0: 208, 1: 225, 2: 183, 3: 193, 4: 208, 5: 163, 6: 164, 7: 216, 8: 233, 9: 170}
# (closed, open, half angle, end_frac) of the corners run on the GPU (runs/band_untwist_corners/*/corners.tsv)
GPU_CORNERS = [(0.032, 0.065, 30, 0), (0.032, 0.065, 30, 1), (0.032, 0.040, 60, 0),
               (0.055, 0.040, 30, 0), (0.032, 0.065, 60, 0), (0.032, 0.040, 30, 0)]


def eight(closed, open_, phi, gap, over_end=0):
    return fig8.FigureEightSpec(closed_lobe_radius=closed, open_lobe_radius=open_, end_gap=gap,
                                half_angle_deg=phi, over_end=over_end, **COMMON)


def landing_shift(spec, params) -> tuple[float, object, bool]:
    """How far the model's landing is from today's replay, the plan, and
    whether today's landing already meets the model's limits."""

    rope = seq.Rope.from_points(fig8.figure_eight_control_points(spec))
    plan = seq.plan(rope, params)
    today, _stay, _contact = fig8.predicted_place(spec, place_clearance=0.035, lift_clearance=0.040)
    # Today's landing measured the model's way: the same lift, landing at `today`.
    move = plan.moves[0]
    lift_xy, arc = np.asarray(move.lift_xy), move.lift.arc(rope)
    q0, q1, qs0, qs1 = seq._remaining(rope, move.lift)
    far = np.minimum(np.abs(qs0 - move.lift.s_lift), np.abs(qs1 - move.lift.s_lift)) > params.lift_point_skip
    lay = float(seq._segment_segment_distance(lift_xy[None], today[None], q0[far], q1[far]).min())
    centre = np.asarray(seq.crossings(rope, merge_radius=params.merge_radius)[move.lift.pivot].xy)
    grasp = rope.end_xy(move.end)
    swing = abs(math.degrees(math.atan2(*(today - centre)[::-1]) - math.atan2(*(grasp - centre)[::-1])))
    swing = min(swing, 360.0 - swing)
    slack = float(np.linalg.norm(today - lift_xy)) / arc
    # Every limit the model now applies to a move that finishes the episode: a
    # corner whose old landing breaks one of them is SUPPOSED to move.
    meets = (lay >= params.min_lay_down and swing >= params.min_rotation_deg
             and params.slack_min <= slack <= params.slack_max_single)
    return float(np.linalg.norm(np.asarray(move.place_xy) - today)), plan, meets


def check_model() -> None:
    print("\n== move model")
    params = seq.ModelParams()
    kept, moved = [], []
    for closed, open_, phi, frac in GPU_CORNERS:
        for over_end in (0, 1):
            spec = eight(closed, open_, phi, fig8.end_gap_from_frac(open_, frac, 0.070, 0.95), over_end)
            shift, plan, meets = landing_shift(spec, params)
            (kept if meets else moved).append(shift)
            check(len(plan.moves) == 1 and plan.moves[0].end == over_end, f"8 corner {closed}/{open_}/{phi}/{frac} over_end={over_end}: one move from the over end")
    check(not kept or max(kept) < 0.005, f"8 GPU-run corners whose landing already meets the limits: unchanged "
          f"(worst {max(kept, default=0) * 1000:.2f} mm over {len(kept)})")
    print(f"       the other {len(moved)} move by {min(moved, default=0) * 1000:.0f}-{max(moved, default=0) * 1000:.0f} mm "
          "(lay-down under 25 mm or swing under 40 deg today; user's decision 2026-09-11)")

    path = REPO / "runs/band_untwist_variation/20260904_placefix_seeds/summary.csv"
    if path.exists():
        kept, worst_lift = [], 0.0
        with path.open() as handle:
            for rec in csv.DictReader(handle):
                spec = eight(float(rec["r_closed"]), float(rec["r_open"]), float(rec["half_angle"]),
                             float(rec["end_gap"]), int(rec["over_end"]))
                shift, plan, meets = landing_shift(spec, params)
                if meets:
                    kept.append(shift)
                worst_lift = max(worst_lift, abs(plan.moves[0].hand_height * 1000 - MEASURED_LIFT_MM[int(rec["seed"])]))
        check(not kept or max(kept) < 0.005, f"8 seeds 0-9 whose landing already meets the limits: unchanged "
              f"(worst {max(kept, default=0) * 1000:.2f} mm over {len(kept)})")
        check(worst_lift < 10.0, f"8 seeds 0-9: hand height within 10 mm of the GPU-measured lift (worst {worst_lift:.1f} mm)")
    else:
        print(f"[skip] {path} missing: seed comparison not run")

    rope = seq.Rope.from_points(fig8.figure_eight_control_points(eight(0.04, 0.05, 45.0, 0.08, 0)))
    found = seq.crossings(rope, merge_radius=0.012)
    ends = sorted({lift.end for lift in seq.lifts(rope, found, params)})
    check(ends == [0], f"8 with end 0 on top: only end 0 can lift without dragging the under strand (got {ends})")
    # Closed lobe 3.2 cm at 60 deg: a whole-curl lift would fit under 40 cm, and it is still not offered.
    small = seq.Rope.from_points(fig8.figure_eight_control_points(eight(0.032, 0.040, 60.0, 0.070, 0)))
    small_found = seq.crossings(small, merge_radius=0.012)
    ends = sorted({lift.end for lift in seq.lifts(small, small_found, params)})
    check(ends == [0], f"8 with a small closed lobe: no whole-curl lift from end 1 either (got {ends})")

    for name, spec, moves in (("six stem on top", six(short_over=0), 1), ("six short tail on top", six(short_over=1), 1),
                              ("twist alternating", twist(0, 1), 2), ("twist same end", twist(0, 0), 1),
                              ("curls stubs on top", curls(1, 1), 2)):
        rope = seq.Rope.from_points(bs.shape_control_points(spec))
        plan = seq.plan(rope, params)
        ok = plan is not None and len(plan.moves) == moves
        check(ok, f"{name}: plan with {moves} move(s)" + ("" if plan is None else f" (got {len(plan.moves)})"))
        if plan is None:
            continue
        recount = [seq.crossing_sequence(seq.crossings(r, merge_radius=0.012)) for r in plan.ropes]
        check(tuple(recount) == plan.predicted and recount[-1] == (), f"{name}: every move's recount matches, none left")
        within = (plan.margin("lay_down_clearance") >= params.min_lay_down - 1e-9
                  and plan.margin("rotation_deg") >= params.min_rotation_deg - 1e-9
                  and plan.margin("slack") >= params.slack_min - 1e-9)
        check(within, f"{name}: every landing swings >= {params.min_rotation_deg:.0f} deg with "
                      f">= 25 mm lay-down and slack >= {params.slack_min}")
        if len(plan.moves) == 1:
            # A move that finishes the episode must not be laid taut: taut, it
            # drags the rope it just freed back over itself (GPU 2026-09-12).
            loose = plan.margin("slack", max) <= params.slack_max_single + 1e-9
            check(loose, f"{name}: the finishing move lays its rope at <= {params.slack_max_single} "
                         f"(got {plan.margin('slack', max):.2f})")
        if len(plan.moves) == 2:
            # The first move leaves a crossing: its laid rope, bowed off the
            # chord either way by the bend the model allows it, keeps the
            # lay-down room from that crossing.
            first = plan.moves[0].margins
            check(first["room"] >= params.min_lay_down - 1e-9,
                  f"{name}: the first move's bowed rope keeps >= 25 mm from the crossing it leaves "
                  f"(room {first['room'] * 1000:.0f} mm on lines bowed {first['bend'] * 1000:.0f} mm)")
            check(plan.moves[1].margins["room"] == float("inf"), f"{name}: the last move leaves no crossing (room inf)")
            check(plan.margin("plug_separation") >= params.min_plug_separation - 1e-9,
                  f"{name}: both landings keep the plugs 7 cm apart")
            check(plan.margin("slack") >= params.slack_min_multi - 1e-9,
                  f"{name}: both moves lay their rope at slack >= {params.slack_min_multi} (got {plan.margin('slack'):.2f})")
            # The rope after the first move, re-planned as the demo does before the second.
            again = seq.plan(plan.ropes[0], params, moves_done=1)
            ok = again is not None and len(again.moves) == 1
            check(ok and again.margin("slack") >= params.slack_min_multi - 1e-9
                  and again.margin("plug_separation") >= params.min_plug_separation - 1e-9,
                  f"{name}: the re-plan before move 2 (moves_done=1) keeps slack >= {params.slack_min_multi} and plugs 7 cm apart")
            alone = seq.plan(plan.ropes[0], params)
            check(alone is not None and alone.margin("slack") < params.slack_min_multi,
                  f"{name}: without moves_done the same rope would be laid looser ({alone.margin('slack'):.2f}) -- the flag matters"
                  if alone is not None else f"{name}: plan on the rope after move 1 exists")

    rope = seq.Rope.from_points(bs.shape_control_points(curls(0, 1)))
    check(seq.plan(rope, params) is None, "curls with stub A underneath: no plan (a whole curl does not come undone)")

    # Flip moves (the twist since 2026-09-13): each move turns the arc from a
    # plug to a pivot 180 deg about the rope's tangent there; the arc lands as
    # its mirror image. Two flips undo the alternating twist; each undone
    # crossing sits >= flip_min_offset off its axis (so it rises on the way
    # over), the mirror image crosses nothing, and the plugs end 7 cm apart.
    flip_params = replace(params, flip_moves=True)
    for name, spec in (("twist alternating", twist(0, 1)), ("twist alternating, other end first", twist(1, 0))):
        rope = seq.Rope.from_points(bs.shape_control_points(spec))
        plan = seq.plan(rope, flip_params)
        ok = plan is not None and len(plan.moves) == 2 and plan.moves[0].kind == "flip"
        check(ok, f"{name} (flips): plan of 2 moves, the first a flip" + ("" if plan is None else f" (got {[m.kind for m in plan.moves]})"))
        if not ok:
            continue
        recount = [seq.crossing_sequence(seq.crossings(r, merge_radius=0.012)) for r in plan.ropes]
        check(tuple(recount) == plan.predicted and recount[-1] == (), f"{name} (flips): every move's recount matches, none left")
        flips_ = [m for m in plan.moves if m.kind == "flip"]
        check(all(m.margins["flip_offset"] >= flip_params.flip_min_offset - 1e-9 for m in flips_),
              f"{name} (flips): every crossing a flip undoes is >= {flip_params.flip_min_offset * 1000:.0f} mm off its axis")
        check(all(m.margins["flip_radius"] <= flip_params.flip_max_radius + 1e-9 for m in flips_)
              and plan.margin("plug_separation") >= params.min_plug_separation - 1e-9
              and plan.margin("lay_down_clearance") >= params.min_lay_down - 1e-9
              and plan.max_hand_height <= params.max_hand_height + 1e-9,
              f"{name} (flips): radius <= {flip_params.flip_max_radius} m, plugs 7 cm apart, >= 25 mm lay-down, hand <= {params.max_hand_height} m "
              f"(radii {[round(m.margins['flip_radius'] * 1000) for m in flips_]} mm)")
        for m, r in zip(plan.moves, [rope, *plan.ropes]):
            if m.kind != "flip":
                # the finishing lay: the "6"'s one-move rules, laid loose
                check(m.margins["slack"] <= params.slack_max_single + 1e-9,
                      f"{name} (flips): the finishing lay is laid no tauter than {params.slack_max_single} (got {m.margins['slack']:.2f})")
                continue
            pivot, axis = seq.flip_axis(r, m.lift.s_lift)
            mirrored = seq.reflect_xy(np.array([m.grasp_xy]), pivot, axis)[0]
            check(np.allclose(mirrored, m.place_xy, atol=1e-9), f"{name} (flips): landing = the plug's mirror image across the axis")
        again = seq.plan(plan.ropes[0], flip_params, moves_done=1)
        check(again is not None and len(again.moves) == 1 and again.moves[0].kind == plan.moves[1].kind,
              f"{name} (flips): the re-plan after flip 1 is one more move of the same kind ({plan.moves[1].kind})")

    # Runtime landing limits: fence off the side the free plan lands on, or pull
    # the reach in below its landing; the plan must move the landing or give up.
    rope = seq.Rope.from_points(bs.shape_control_points(twist(0, 1)))
    free = seq.plan(rope, params)
    x, y = free.moves[0].place_xy
    box = ((-1.0, 1.0), (y + 0.02, 1.0)) if y < 0 else ((-1.0, 1.0), (-1.0, y - 0.02))
    fenced = seq.plan(rope, replace(params, landing_box=box))
    inside = fenced is None or all(box[0][0] <= m.place_xy[0] <= box[0][1] and box[1][0] <= m.place_xy[1] <= box[1][1]
                                   for m in fenced.moves)
    check(inside, f"landing box: every landing inside it (free landing y {y:+.3f}, box y {box[1]})")
    reach = max(float(np.linalg.norm(np.subtract(m.place_xy, params.arm_base_xy))) for m in free.moves) - 0.01
    short = seq.plan(rope, replace(params, max_reach=reach))
    within = short is None or all(np.linalg.norm(np.subtract(m.place_xy, params.arm_base_xy)) <= reach + 1e-9 for m in short.moves)
    check(within, f"max reach {reach:.3f} m: every landing within it")


def main() -> int:
    check_shapes()
    check_model()
    print()
    print("PASS" if not FAILS else f"FAIL ({len(FAILS)})")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
