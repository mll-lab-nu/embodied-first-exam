"""Does the cover move actually put one rope across the other? (docx 3.2)

Headless check, no Genesis and no GPU. `planning/swap_crossing_sign_planner.py`
is arithmetic on two polylines, and the one thing that can silently go wrong in
it is arithmetic: the rope leaves the spawn ~99% extended (measured control-line
arc 0.4376 m against a 0.4334 m chord), so *every* placement is reach-clamped,
and the clamp pulls the aim point back along the anchor->target ray. If it pulls
it back past the other rope, the move puts the two side by side instead of across
each other -- the episode runs, looks plausible in the viewer, and ends with zero
crossings instead of a flipped sign.

That failure is pure geometry, so it belongs here rather than in a GPU sweep.
The scene is stubbed: the planner only ever asks it for a rope radius, the braid
x_end, the table height and a strand name.

    python tests/check_swap_crossing_sign_planner.py

Prints one line per case and exits non-zero if any expectation misses.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from topogym.planning.swap_crossing_sign_planner import (  # noqa: E402
    _chord_crossing_fraction,
    make_swap_crossing_sign_rule,
    plan_cover_move,
)

# Measured off the frozen config with `braid.n_strands: 2` / `braid.length: 1`
# (build_braid_spec, seed 0): lanes at +-42.5 mm, control-line arc 0.4376 m.
LANE = 0.0425
ROPE_ARC = 0.4376
X_START = -0.225
X_END = 0.200
TABLE_Z = 0.0
RADIUS = 0.004
# From the task config's `pinch:` block.
KNOBS = dict(
    lift_clearance=0.040,
    place_pullback=0.025,
    tail_clearance=-0.030,
    max_taut_ratio=0.90,
    cover_overshoot=0.070,
)


@dataclass
class _Braid:
    x_end: float = X_END


@dataclass
class _Rope:
    radius: float = RADIUS


@dataclass
class _Cfg:
    rope: _Rope


@dataclass
class _Layout:
    cfg: _Cfg

    def braid_layout(self):
        return _Braid()

    def world_z(self, z):
        return TABLE_Z + float(z)

    def strand_name(self, index):
        return f"rope_{index}"


@dataclass
class _Scene:
    layout: _Layout
    free_end_connectors: dict


@dataclass
class _State:
    crossing_count: int
    is_separated: bool
    min_separation: float = 0.05


def _polyline(start_xy, end_xy, *, arc, lobes=1, samples=80):
    """A rope of length `arc` whose ends sit at `start_xy` / `end_xy`.

    A straight line between the ends would be shorter than the rope actually is,
    and rope length is exactly what the reach clamp is a fraction of -- so the
    slack has to be somewhere. It goes into `lobes` lateral half-waves.

    `lobes` is not cosmetic: it is the one thing about the settled shape that is
    not known without running the physics, and the answer moves the result. One
    lobe is a single wide bow (the largest lateral excursion the slack can make);
    three is a shallow meander. Where the two ropes intersect, and therefore how
    much rope hangs below the hand, depends on it, so the checks below sweep it
    rather than picking one.
    """

    start = np.asarray(start_xy, dtype=float)
    end = np.asarray(end_xy, dtype=float)
    chord = float(np.linalg.norm(end - start))
    if arc <= chord:
        raise ValueError(f"arc {arc} must exceed the chord {chord}")
    direction = (end - start) / chord
    normal = np.array([-direction[1], direction[0]])
    # arc ~= chord * (1 + pi^2 A^2 n^2 / (4 chord^2)) for n half-waves of
    # amplitude A, so amplitude falls off as 1/n for a fixed amount of slack.
    amplitude = chord * float(np.sqrt(4.0 * (arc / chord - 1.0))) / (np.pi * lobes)
    s = np.linspace(0.0, 1.0, samples)
    xy = start[None, :] + np.outer(s, end - start)
    xy = xy + np.outer(np.sin(np.pi * lobes * s) * amplitude, normal)
    z = np.full(samples, TABLE_Z + RADIUS)
    return np.column_stack([xy, z])


def _after_separate(slack: float = ROPE_ARC / 0.4334, lobes: int = 2):
    """The state move 1 leaves behind, for seed 0's braid.

    Word (1,) puts strand 0 on top, so move 1 takes strand 0 off and lays it in
    its own lane (-42.5 mm) overshot 40 mm further out, away from strand 1.
    Strand 1 has not moved, so it is still in its braided shape.
    """

    covered = _polyline(
        (X_START, -LANE), (X_END - 0.025, -LANE - 0.040), arc=ROPE_ARC, lobes=lobes
    )
    chord = float(np.linalg.norm(np.array([X_END - X_START, -2 * LANE])))
    moved = _polyline((X_START, +LANE), (X_END, -LANE), arc=chord * slack, lobes=lobes)
    return {0: covered, 1: moved}


def _crosses(polylines, anchor_xy, target_xy, covered_index):
    return _chord_crossing_fraction(anchor_xy, target_xy, polylines[covered_index]) is not None


def main() -> int:
    failures = 0
    scene = _Scene(layout=_Layout(cfg=_Cfg(rope=_Rope())), free_end_connectors={})

    # 1. Refuses to cover while the ropes are still stacked. Covering then would
    #    re-seat the same relationship, not flip it.
    polylines = _after_separate()
    for count, separated, label in [(1, False, "still crossed"), (0, False, "touching")]:
        planned = plan_cover_move(
            scene, _State(count, separated), polylines, moved=1, covered=0, **KNOBS
        )
        ok = planned is None
        failures += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] refuses to cover when {label}: {planned is None}")

    # 2. The nominal case: a crossing is predicted, and the clamped placement is
    #    genuinely on the far side of the covered rope.
    state = _State(0, True)
    planned = plan_cover_move(scene, state, polylines, moved=1, covered=0, **KNOBS)
    if planned is None:
        print("[FAIL] nominal cover move returned None")
        failures += 1
    else:
        command, plan = planned
        anchor_xy = polylines[1][0, :2]
        settle_xy = np.asarray(command.settle[:2])
        crossed = _crosses(polylines, anchor_xy, settle_xy, 0)
        failures += 0 if crossed else 1
        print(
            f"[{'ok' if crossed else 'FAIL'}] clamped placement crosses the covered rope: "
            f"place=({command.place_xy[0]:+.3f},{command.place_xy[1]:+.3f}) -> "
            f"clamped=({settle_xy[0]:+.3f},{settle_xy[1]:+.3f}) "
            f"arc_to_contact={command.crossing_arc * 1000:.0f}mm "
            f"lift={(command.lift_z - TABLE_Z) * 1000:.0f}mm"
        )
        # The lift has to clear the rope underneath by more than the hanging arc,
        # or the contact point ploughs through it during the traverse.
        lifted = command.lift_z - TABLE_Z > command.crossing_arc
        failures += 0 if lifted else 1
        print(
            f"[{'ok' if lifted else 'FAIL'}] lift {(command.lift_z - TABLE_Z) * 1000:.0f}mm "
            f"exceeds the {command.crossing_arc * 1000:.0f}mm of rope hanging below the hand"
        )
        reach = float(np.linalg.norm(settle_xy - anchor_xy))
        limit = KNOBS["max_taut_ratio"] * float(
            np.linalg.norm(np.diff(polylines[1], axis=0), axis=1).sum()
        )
        within = reach <= limit + 1e-9
        failures += 0 if within else 1
        print(
            f"[{'ok' if within else 'FAIL'}] placement within reach: "
            f"{reach * 1000:.0f}mm <= {limit * 1000:.0f}mm"
        )

    # 3. The number that decides whether this move is runnable at all: how high
    #    the hand has to go. It follows from where the two ropes intersect, and
    #    that depends on the settled shape, which is exactly what a headless
    #    check cannot know -- so sweep the shape and read off the range.
    #
    #    The ceiling is the arm's workspace, `common.manipulation_space.workspace.z`
    #    = [0.03, 0.40]. A plan asking for more than 0.40 is not a plan; the IK
    #    will refuse it at runtime and the move will be reported as failed.
    print("    lobes  slack   crossing@  arc_below_hand  lift    carry_planar")
    lifts = []
    for lobes in (1, 2, 3):
        for slack in (1.0097, 1.05):
            lines = _after_separate(slack, lobes=lobes)
            planned = plan_cover_move(
                scene, _State(0, True), lines, moved=1, covered=0, **KNOBS
            )
            if planned is None:
                print(f"    {lobes:<6} {slack:<7.4f} NO CROSSING PREDICTED")
                failures += 1
                continue
            command, _ = planned
            anchor_xy = lines[1][0, :2]
            lift = command.lift_z - TABLE_Z
            lifts.append(lift)
            carry_planar = float(
                np.linalg.norm(np.asarray(command.carry[:2]) - anchor_xy)
            )
            fraction = 1.0 - command.crossing_arc / float(
                np.linalg.norm(np.diff(lines[1], axis=0), axis=1).sum()
            )
            print(
                f"    {lobes:<6} {slack:<7.4f} {fraction:<10.2f} "
                f"{command.crossing_arc * 1000:<15.0f} {lift * 1000:<7.0f} "
                f"{carry_planar * 1000:.0f}mm"
            )
    ceiling = 0.40
    worst = max(lifts) if lifts else float("inf")
    ok = worst <= ceiling
    failures += 0 if ok else 1
    print(
        f"[{'ok' if ok else 'FAIL'}] worst-case lift {worst * 1000:.0f}mm is within the "
        f"{ceiling * 1000:.0f}mm workspace ceiling"
    )

    # 4. The contrast pair differs by which rope goes back on top, and by nothing
    #    else. If both modes picked the same rope the baseline would be vacuous.
    picks = {}
    for mode in ("oracle", "restack_same"):
        rule = make_swap_crossing_sign_rule(mode)
        planned = rule.decide(
            scene,
            _State(0, True),
            polylines,
            pinch_cfg=type("P", (), KNOBS)(),
            separated_strand=0,
        )
        picks[mode] = None if planned is None else planned[0].strand_index
    ok = picks["oracle"] == 1 and picks["restack_same"] == 0
    failures += 0 if ok else 1
    print(
        f"[{'ok' if ok else 'FAIL'}] contrast pair covers with different ropes: "
        f"oracle=s{picks['oracle']} restack_same=s{picks['restack_same']} "
        f"(separated s0)"
    )

    print(f"\n{'PASS' if failures == 0 else f'{failures} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
