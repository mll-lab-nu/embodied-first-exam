"""Does the diverter layout stay buildable and solvable across its variation envelope?

Headless check, no GPU: `DiverterRouteBallLayout` is arithmetic on a config, the
planner is arithmetic on a layout, and the judge's flood fill only needs the
layout and a flap angle. So the claims the variation block rests on can be
settled here instead of in a GPU sweep:

1. Every accepted draw (seed 0-199) passes `checks()`, and the derived leaves
   land inside the ranges the drawn geometry allows.
2. At the envelope's corners (angle x lever x fork_frac x spawn_frac) the checks
   still pass and the numbers are printed, so a reader can see the margins.
3. The oracle turns exactly when the flap does not already seal the dead end;
   `fixed_direction` is right on half of the 2 x 2.
4. The judge agrees with the analytic bypass gap: half-open blocks the ball,
   seated routes it -- at the default geometry and at every corner.
5. `steps_arc` follows the sweep at 0.23 deg/step, floored at 60.

    python tests/check_diverter_geometry.py

Prints one line per check and exits non-zero if any expectation misses.
"""

from __future__ import annotations

import math
import sys
from itertools import product
from pathlib import Path
from types import SimpleNamespace

from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.generation.layout_randomization import randomize_task_cfg  # noqa: E402
from topogym.planning.diverter_route_ball_planner import make_rule  # noqa: E402
from topogym.tasks.connectivity.diverter_route_ball import (  # noqa: E402
    SIDES,
    DiverterRouteBallLayout,
    derive_task_cfg,
    other_side,
)
from topogym.verification import DiverterRouteBallEvaluator  # noqa: E402

CONFIG = ROOT / "configs" / "task_configs" / "diverter_route_ball_topogym_tabletop_v1.yaml"
TASK = "diverter_route_ball"


def load_cfg(**overrides):
    cfg = OmegaConf.load(CONFIG)
    for dotted, value in overrides.items():
        OmegaConf.update(cfg, dotted, value, merge=False)
    return cfg


def layout_at(*, angle_deg: float, lever: float, fork_frac: float, spawn_frac: float,
              **overrides) -> DiverterRouteBallLayout:
    """A layout with the two derived leaves resolved, as the randomizer would leave it."""
    cfg = load_cfg(**{"branch.angle_deg": angle_deg, "diverter.lever.radius": lever,
                      "channel.fork_frac": fork_frac, "ball.spawn_frac": spawn_frac},
                   **overrides)
    derive_task_cfg(cfg)
    return DiverterRouteBallLayout(cfg)


def judge_reachable(layout: DiverterRouteBallLayout, flap_angle: float) -> bool:
    """The judge's flood fill, on a stub scene: it only asks for the layout and the flap angle."""
    scene = SimpleNamespace(layout=layout, flap_angle=lambda: float(flap_angle))
    return DiverterRouteBallEvaluator().target_reachable(scene)


def checks_line(layout: DiverterRouteBallLayout) -> str:
    return " ".join(f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
                    for name, measured, limit, ok in layout.checks())


def main() -> int:
    failures: list[str] = []
    base = OmegaConf.create({"task": load_cfg()})

    # 1. Accepted draws pass every check; derived leaves inside their ranges.
    for seed in range(200):
        task = randomize_task_cfg(base, TASK, seed).task
        layout = DiverterRouteBallLayout(task)
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            failures.append(f"seed {seed}: checks failed: {bad}")
        lo, hi = layout.fork_origin_x_bounds()
        if not lo - 1e-9 <= float(task.channel.fork_origin_x) <= hi + 1e-9:
            failures.append(f"seed {seed}: fork_origin_x outside its derived range")
        lo, hi = layout.release_x_bounds()
        if not lo - 1e-9 <= float(task.ball.release_x) <= hi + 1e-9:
            failures.append(f"seed {seed}: release_x outside its derived range")
    print("seeds 0-199: checks pass, derived leaves in range", flush=True)

    # 2. Envelope corners: print the margins; 4. judge agrees at each corner.
    corners = list(product((24.0, 36.0), (0.047, 0.063), (0.0, 1.0), (0.0, 1.0)))
    for angle_deg, lever, fork_frac, spawn_frac in corners:
        layout = layout_at(angle_deg=angle_deg, lever=lever, fork_frac=fork_frac, spawn_frac=spawn_frac)
        label = f"a={angle_deg:4.1f} r={lever:.3f} fork_frac={fork_frac:.0f} spawn_frac={spawn_frac:.0f}"
        print(f"corner {label}: fork_x={layout.fork_origin_x:+.4f} release_x={float(layout.cfg.ball.release_x):+.4f} "
              f"knob_reach={layout.knob_reach():.4f} bypass={layout.half_open_bypass_gap():.4f} "
              f"flap_len={layout.flap_length:.4f}", flush=True)
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            failures.append(f"corner {label}: checks failed: {bad}")
        if judge_reachable(layout, 0.0):
            failures.append(f"corner {label}: judge says the half-open flap lets the ball through")
        live = layout.live_side
        if not judge_reachable(layout, layout.target_angle(live)):
            failures.append(f"corner {label}: judge says the seated flap does not route to {live}")
        if judge_reachable(layout, layout.target_angle(other_side(live))):
            failures.append(f"corner {label}: judge says sealing the live side still routes to it")
    print(f"corners x{len(corners)}: half-open blocked, seated routed (judge flood fill)", flush=True)

    # Beyond the envelope the derived range must close, not silently clamp: a
    # fork ceiling below the floor, or a reach limit no fork position meets.
    for label, overrides in (
        ("reach_too_short", {"reach.max_knob_dist": 0.60}),
        ("lane_too_short", {"channel.fork_x_min": -0.190, "channel.fork_x_max": -0.190}),
    ):
        try:
            layout_at(angle_deg=24.0, lever=0.063, fork_frac=1.0, spawn_frac=1.0, **overrides)
        except ValueError as exc:
            print(f"reject {label:16s} -> {str(exc).splitlines()[0][:90]}", flush=True)
        else:
            failures.append(f"derive accepted {label}")

    # 3. Rules over the 2 x 2 of (dead end, initial seal).
    oracle, fixed = make_rule("oracle"), make_rule("fixed_direction")
    fixed_right = 0
    for dead, sealed in product(SIDES, SIDES):
        layout = DiverterRouteBallLayout(load_cfg(**{"diverter.dead_end_side": dead,
                                                      "diverter.init_sealed_side": sealed}))
        start = layout.seat_angle(sealed)
        plan = oracle.decide(layout, start, layout.commanded_side)
        want_turn = dead != sealed
        if plan.rotate != want_turn:
            failures.append(f"oracle dead={dead} sealed={sealed}: rotate={plan.rotate}, expected {want_turn}")
        if abs(plan.target_angle - layout.seat_angle(dead)) > 1e-9:
            failures.append(f"oracle dead={dead} sealed={sealed}: target does not seal the dead end")
        contrast = fixed.decide(layout, start, layout.commanded_side)
        right = abs(contrast.target_angle - layout.seat_angle(dead)) < 1e-9
        fixed_right += right
        print(f"dead={dead:5s} sealed={sealed:5s} | oracle rotate={plan.rotate} "
              f"target={math.degrees(plan.target_angle):+.0f}deg | fixed_direction {'right' if right else 'wrong'}",
              flush=True)
    if fixed_right != 2:
        failures.append(f"fixed_direction right on {fixed_right}/4, expected 2")

    # 5. Sweep steps at 0.23 deg/step (linkbar's rate), floored at 60.
    layout = DiverterRouteBallLayout(load_cfg())
    for sweep_deg, want in ((60.0, 261), (-60.0, 261), (48.0, 209), (72.0, 314), (10.0, 60), (0.0, 60)):
        got = layout.steps_arc(math.radians(sweep_deg))
        if got != want:
            failures.append(f"steps_arc({sweep_deg}) = {got}, expected {want}")
    print("steps_arc: 60 deg -> 261, 48 -> 209, 72 -> 314, floor 60", flush=True)

    print(f"default checks: {checks_line(layout)}", flush=True)

    for failure in failures:
        print(f"FAIL: {failure}", flush=True)
    print("ok" if not failures else f"{len(failures)} failure(s)", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
