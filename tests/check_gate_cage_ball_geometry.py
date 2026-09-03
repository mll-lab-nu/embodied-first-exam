"""Does the gate_cage_ball layout stay solvable across its variation envelope?

Headless check, no GPU: `GateCageBallLayout` is arithmetic on a config and the
trigger rules are arithmetic on a ball state, so the claims the variation block
rests on can be settled here:

1. Every accepted draw (seed 0-199) passes `checks()`, and the three derived
   leaves land inside the ranges the drawn speed / geometry allows.
2. At the envelope's corners (speed x the three unit fractions) the checks still
   pass and the timing numbers are printed, so a reader can see the margins.
3. The layout's copy of the arm's timing (t_ready, insert_duration) equals what
   `GatedInsertPrimitive` computes from the same motion config.
4. The three trigger rules answer as their docstrings say on synthetic ball
   states: the oracle waits outside, commits with margin, refuses too late;
   greedy always commits; fixed_delay commits exactly when its clock is due.

    python tests/check_gate_cage_ball_geometry.py

Prints one line per check and exits non-zero if any expectation misses.
"""

from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.generation.layout_randomization import randomize_task_cfg  # noqa: E402
from topogym.planning.gate_cage_ball_planner import make_trigger_rule  # noqa: E402
from topogym.primitives.gated_insert import GatedInsertPrimitive  # noqa: E402
from topogym.tasks.connectivity.gate_cage_ball import (  # noqa: E402
    GateCageBallLayout,
    derive_task_cfg,
)

CONFIG = ROOT / "configs" / "task_configs" / "gate_cage_ball_topogym_tabletop_v1.yaml"
TASK = "gate_cage_ball"


def load_cfg(**overrides):
    cfg = OmegaConf.load(CONFIG)
    for dotted, value in overrides.items():
        OmegaConf.update(cfg, dotted, value, merge=False)
    return cfg


def layout_at(*, speed: float, flat_frac: float, release_frac: float, rack_frac: float,
              **overrides) -> GateCageBallLayout:
    cfg = load_cfg(**{"ball.speed": speed, "channel.flat_end_frac": flat_frac,
                      "ball.release_frac": release_frac, "gate_rack.x_frac": rack_frac},
                   **overrides)
    derive_task_cfg(cfg)
    return GateCageBallLayout(cfg)


def checks_line(layout: GateCageBallLayout) -> str:
    return " ".join(f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
                    for name, measured, limit, ok in layout.checks())


def main() -> int:
    failures: list[str] = []
    base = OmegaConf.create({"task": load_cfg()})

    # 1. Accepted draws pass every check; derived leaves inside their ranges.
    for seed in range(200):
        task = randomize_task_cfg(base, TASK, seed).task
        layout = GateCageBallLayout(task)
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            failures.append(f"seed {seed}: checks failed: {bad}")
        for name, value, (lo, hi) in (
            ("flat_end_y", float(task.channel.flat_end_y), layout.flat_end_y_bounds()),
            ("release_y", float(task.ball.release_y), layout.release_y_bounds()),
            ("rack center_x", float(task.gate_rack.center_x), layout.rack_x_bounds()),
        ):
            if not lo - 1e-9 <= value <= hi + 1e-9:
                failures.append(f"seed {seed}: {name} outside its derived range")
    print("seeds 0-199: checks pass, derived leaves in range", flush=True)

    # 2. Envelope corners.
    for speed, flat_frac, release_frac, rack_frac in product((0.08, 0.16), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)):
        layout = layout_at(speed=speed, flat_frac=flat_frac, release_frac=release_frac, rack_frac=rack_frac)
        label = f"v={speed:.2f} flat={flat_frac:.0f} rel={release_frac:.0f} rack={rack_frac:.0f}"
        print(f"corner {label}: flat_end_y={layout.flat_end_y:+.4f} release_y={float(layout.cfg.ball.release_y):+.4f} "
              f"rack_x={float(layout.cfg.gate_rack.center_x):+.4f} entry_delay={layout.entry_delay():.2f}s "
              f"window={layout.predicted_window():.2f}s hover_wait={layout.hover_wait():+.2f}s "
              f"slack={layout.ready_margin():+.2f}s", flush=True)
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            failures.append(f"corner {label}: checks failed: {bad}")
    print("corners x16: checks pass", flush=True)

    # Beyond the envelope the derived range must close, not silently clamp.
    for label, overrides in (
        ("lane_too_short", {"channel.entry_start_y": -0.060}),
        ("arm_too_slow", {"motion.steps_per_phase": 200}),
    ):
        try:
            layout_at(speed=0.16, flat_frac=0.0, release_frac=1.0, rack_frac=0.5, **overrides)
        except ValueError as exc:
            print(f"reject {label:16s} -> {str(exc).splitlines()[0][:90]}", flush=True)
        else:
            failures.append(f"derive accepted {label}")

    # A lowered approach height derives fine (no axis depends on it) but must fail
    # validate(): 0.220 leaves the pads 12 mm over the parked plate, under the 30 mm gate.
    low = layout_at(speed=0.12, flat_frac=0.5, release_frac=0.5, rack_frac=0.5,
                    **{"motion.approach_z": 0.220})
    try:
        low.validate()
    except ValueError as exc:
        print(f"reject approach_too_low -> {str(exc).splitlines()[0][:90]}", flush=True)
    else:
        failures.append("validate accepted approach_z=0.220 (pad clearance 12 mm)")

    # 3. The layout's timing equals the primitive's.
    layout = GateCageBallLayout(load_cfg())
    motion = layout.cfg.motion
    primitive = GatedInsertPrimitive(
        approach_z=0.0, grasp_z=0.0, carry_z=0.0, hover_z=0.0, seated_z=0.0, clear_z=0.0,
        steps_per_phase=int(motion.steps_per_phase), gripper_steps=int(motion.gripper_steps),
        insert_steps=int(motion.insert_steps), grasp_qpos=float(motion.grasp_qpos),
        close_hold_steps=int(motion.close_hold_steps),
        insert_settle_steps=int(motion.insert_settle_steps),
    )
    dt = layout.sim_dt
    if abs(primitive.time_to_station(dt) - layout.t_ready()) > 1e-9:
        failures.append(f"t_ready {layout.t_ready():.3f} != primitive {primitive.time_to_station(dt):.3f}")
    if abs(primitive.insert_duration(dt) - layout.insert_duration()) > 1e-9:
        failures.append(f"insert_duration {layout.insert_duration():.3f} != primitive {primitive.insert_duration(dt):.3f}")
    print(f"timing: t_ready={layout.t_ready():.2f}s insert_duration={layout.insert_duration():.2f}s "
          f"(primitive agrees) default entry_delay={layout.entry_delay():.2f}s window={layout.predicted_window():.2f}s",
          flush=True)
    print(f"default checks: {checks_line(layout)}", flush=True)

    # 4. Trigger rules on synthetic ball states.
    kw = dict(door_y=layout.door_y, insert_duration=layout.insert_duration(),
              safety_margin=float(layout.cfg.timing.safety_margin), fixed_delay_s=3.6)
    oracle, greedy, fixed = (make_trigger_rule(m, **kw) for m in ("oracle", "greedy", "fixed_delay"))
    cases = (
        # (ball_y, ball_vy, elapsed) -> expected commit for oracle / greedy / fixed
        ((-0.10, +0.12, 2.5), (False, True, False)),   # outside, approaching
        ((+0.10, +0.12, 2.5), (True, True, False)),    # inside, receding: no deadline
        ((+0.10, -0.12, 3.0), (False, True, False)),   # inside, 0.83 s to door < 1.3 + 0.15
        ((+0.11, -0.05, 3.6), (True, True, True)),     # inside, 2.2 s to door: enough; clock due
    )
    for (y, vy, elapsed), want in cases:
        got = tuple(r.decide(y, vy, elapsed_s=elapsed).commit for r in (oracle, greedy, fixed))
        print(f"rules ball_y={y:+.2f} vy={vy:+.2f} t={elapsed:.1f}s -> oracle/greedy/fixed commit={got}", flush=True)
        if got != want:
            failures.append(f"rules at y={y} vy={vy} t={elapsed}: {got}, expected {want}")
    try:
        make_trigger_rule("random", **kw)
    except ValueError:
        pass
    else:
        failures.append("make_trigger_rule accepted an unknown mode")

    for failure in failures:
        print(f"FAIL: {failure}", flush=True)
    print("ok" if not failures else f"{len(failures)} failure(s)", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
