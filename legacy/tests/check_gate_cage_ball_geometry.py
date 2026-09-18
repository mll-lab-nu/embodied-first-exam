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

import numpy as np  # noqa: E402

from topogym.generation.layout_randomization import randomize_task_cfg  # noqa: E402
from topogym.planning.gate_cage_ball_planner import make_trigger_rule  # noqa: E402
from topogym.primitives.gated_insert import GatedInsertPrimitive  # noqa: E402
from topogym.tasks_legacy.connectivity.gate_cage_ball import (  # noqa: E402
    GateCageBallLayout,
    derive_task_cfg,
)
from topogym.verification.gate_cage_ball_verifier import GateCageBallEvaluator  # noqa: E402

CONFIG = ROOT / "configs" / "task_configs" / "gate_cage_ball_topogym_tabletop_v1.yaml"
TASK = "gate_cage_ball"


def load_cfg(**overrides):
    cfg = OmegaConf.load(CONFIG)
    for dotted, value in overrides.items():
        OmegaConf.update(cfg, dotted, value, merge=False)
    return cfg


def layout_at(*, tier: int, flat_frac: float, release_frac: float, rack_frac: float,
              **overrides) -> GateCageBallLayout:
    """A layout at one corner. The slope tier is drawn; angle, release floor and speed follow it."""

    cfg = load_cfg(**{"channel.slope_tier": tier, "channel.flat_end_frac": flat_frac,
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

    # 2. Envelope corners. The slope tier replaced the free speed axis
    # (2026-09-09), so the corners run over the three tiers rather than over two
    # speed endpoints -- which also fixes a staleness: this used to probe
    # 0.08/0.16 m/s, the envelope the 2026-09-08 slow-down retired.
    corners = 0
    for tier, flat_frac, release_frac, rack_frac in product((0, 1, 2), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)):
        layout = layout_at(tier=tier, flat_frac=flat_frac, release_frac=release_frac, rack_frac=rack_frac)
        label = f"tier={tier} flat={flat_frac:.0f} rel={release_frac:.0f} rack={rack_frac:.0f}"
        usable = layout.sealable_pass()
        # The tiers' defining property: tier 0's first pass is the arm's, the
        # steeper tiers' first pass has come and gone before the arm is there.
        rows = layout.pass_schedule(layout.t_ready() + 13.0)
        idx = next((i + 1 for i, r in enumerate(rows) if usable and abs(r[0] - usable[0]) < 1e-9), None)
        if tier == 0 and idx != 1:
            failures.append(f"corner {label}: tier 0 should be sealable on pass 1, got pass {idx}")
        if tier > 0 and (idx is None or idx < 2):
            failures.append(f"corner {label}: tier {tier} should miss pass 1, got pass {idx}")
        print(f"corner {label}: v_door={layout.ball_speed:.3f} rise={layout.ramp_rise() * 100:.2f}cm "
              f"usable_pass_at={usable[0] if usable else float('nan'):.2f}s v_at_cap={layout.speed_at_cap():.3f} "
              f"flat_end_y={layout.flat_end_y:+.4f} release_y={float(layout.cfg.ball.release_y):+.4f} "
              f"entry_delay={layout.entry_delay():.2f}s "
              f"window={layout.predicted_window():.2f}s hover_wait={layout.hover_wait():+.2f}s "
              f"slack={layout.ready_margin():+.2f}s", flush=True)
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            failures.append(f"corner {label}: checks failed: {bad}")
        corners += 1
    print(f"corners x{corners}: checks pass", flush=True)

    # The free ball's arithmetic: the first arrival is the rolling-from-rest
    # time down the slope plus the level strip, the pass schedule starts there,
    # and the window the checks use is the dwell of the first pass the arm can
    # take. None of it is obvious by reading, and all of it is one line to check.
    for slope in (0, 1, 2):
        lay = layout_at(tier=slope, flat_frac=0.5, release_frac=0.5, rack_frac=0.5)
        a = lay.entry_gravity_accel()
        run = lay.ramp_run()
        arrival = (2.0 * run / a) ** 0.5 + (lay.door_y - lay.ramp_end_y()) / lay.ball_speed
        if abs(lay.entry_delay() - arrival) > 1e-9:
            failures.append(f"slope {slope}: entry_delay {lay.entry_delay():.4f} != {arrival:.4f}")
        if abs(lay.ball_speed - (2.0 * a * run) ** 0.5) > 1e-9:
            failures.append(f"slope {slope}: ball_speed is not sqrt(2 a s)")
        rows = lay.pass_schedule(lay.t_ready() + 13.0)
        if not rows or abs(rows[0][0] - lay.entry_delay()) > 1e-9:
            failures.append(f"slope {slope}: pass schedule does not start at the first arrival")
        if any(rows[i + 1][2] <= rows[i][2] for i in range(len(rows) - 1)):
            failures.append(f"slope {slope}: passes are not getting longer")
        usable = lay.sealable_pass()
        if usable is None or abs(lay.predicted_window() - usable[2]) > 1e-9:
            failures.append(f"slope {slope}: predicted_window is not the usable pass's dwell")
        print(f"free tier={slope} slope={float(lay.cfg.channel.entry_slope_deg):.1f}deg rise={lay.ramp_rise() * 100:.2f}cm run={run * 100:.1f}cm "
              f"v_door={lay.ball_speed:.3f} passes=" + " ".join(f"{t:.2f}s/{d:.2f}s" for t, _, d in rows)
              + f" usable={usable[0]:.2f}s", flush=True)

    # The seal deadline for a free ball is the plate reaching the ball's crown,
    # not its seat: earlier than the seat, later for a smaller ball, and it is
    # what the pass schedule and the planner both use.
    prev = None
    for r in (0.024, 0.030, 0.036):
        lay = layout_at(tier=1, flat_frac=0.5, release_frac=0.5, rack_frac=0.5, **{"ball.radius": r})
        blk = lay.block_duration()
        if not 0.3 < blk < lay.insert_duration():
            failures.append(f"block_duration {blk:.3f}s at r={r} is not between 0.3 s and the seat time")
        if prev is not None and blk >= prev:
            failures.append(f"block_duration should shrink with a bigger ball ({prev:.3f} -> {blk:.3f})")
        if abs(lay.seal_deadline() - blk) > 1e-12:
            failures.append("seal_deadline is not block_duration for the free ball")
        prev = blk
        print(f"deadline r={r*1000:.0f}mm block={blk:.3f}s seat={lay.insert_duration():.2f}s", flush=True)

    # Beyond the envelope the derived range must close, not silently clamp.
    for label, overrides in (
        ("lane_too_short", {"channel.entry_start_y": -0.060}),
    ):
        try:
            layout_at(tier=1, flat_frac=0.0, release_frac=1.0, rack_frac=0.5, **overrides)
        except ValueError as exc:
            print(f"reject {label:16s} -> {str(exc).splitlines()[0][:90]}", flush=True)
        else:
            failures.append(f"derive accepted {label}")

    # A lowered approach height derives fine (no axis depends on it) but must fail
    # validate(): 0.220 leaves the pads 12 mm over the parked plate, under the 30 mm gate.
    low = layout_at(tier=1, flat_frac=0.5, release_frac=0.5, rack_frac=0.5,
                    **{"motion.approach_z": 0.220})
    try:
        low.validate()
    except ValueError as exc:
        print(f"reject approach_too_low -> {str(exc).splitlines()[0][:90]}", flush=True)
    else:
        failures.append("validate accepted approach_z=0.220 (pad clearance 12 mm)")

    # A hover cap too short for any sealable pass derives fine but must fail
    # validate(): with 0.1 s of hover the arm never sees a pass at all.
    short = layout_at(tier=2, flat_frac=0.0, release_frac=1.0, rack_frac=0.5,
                      **{"motion.max_hover_steps": 10})
    try:
        short.validate()
    except ValueError as exc:
        print(f"reject cap_too_short  -> {str(exc).splitlines()[0][:90]}", flush=True)
    else:
        failures.append("validate accepted a 0.1 s hover cap with no sealable pass")

    # 3. The layout's timing equals the primitive's.
    layout = GateCageBallLayout(load_cfg())
    motion = layout.cfg.motion
    primitive = GatedInsertPrimitive(
        approach_z=0.0, grasp_z=0.0, carry_z=0.0, hover_z=0.0, seated_z=0.0, clear_z=0.0,
        steps_per_phase=int(motion.steps_per_phase), approach_steps=int(motion.approach_steps),
        gripper_steps=int(motion.gripper_steps),
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

    # 5. The `channel.open_end` mirror moves the channel and nothing else.
    #
    # The whole point of keeping the config leaves as DISTANCES from the doorway
    # is that every timing formula is a difference of two of them and so cannot
    # notice the mirror. Asserting that here is what stops a future edit from
    # quietly making one of them depend on absolute y.
    straight = layout_at(tier=1, flat_frac=0.5, release_frac=0.5, rack_frac=0.5)
    mirrored = layout_at(tier=1, flat_frac=0.5, release_frac=0.5, rack_frac=0.5,
                         **{"channel.open_end": 1})
    for name, reading in (
        ("entry_delay", GateCageBallLayout.entry_delay),
        ("predicted_window", GateCageBallLayout.predicted_window),
        ("t_ready", GateCageBallLayout.t_ready),
        ("insert_duration", GateCageBallLayout.insert_duration),
        ("hover_wait", GateCageBallLayout.hover_wait),
        ("ready_margin", GateCageBallLayout.ready_margin),
        ("window_margin", GateCageBallLayout.window_margin),
        ("hover_reach", GateCageBallLayout.hover_reach),
    ):
        if abs(reading(straight) - reading(mirrored)) > 1e-12:
            failures.append(
                f"open_end changed {name}: {reading(straight):.6f} -> {reading(mirrored):.6f}"
            )
    if [n for n, _, _, ok in mirrored.checks() if not ok]:
        failures.append("mirrored layout fails checks")
    # ... while every emitted position flips about the doorway.
    lo_s, hi_s = straight.lane_bounds()
    lo_m, hi_m = mirrored.lane_bounds()
    if abs(lo_s + hi_m) > 1e-12 or abs(hi_s + lo_m) > 1e-12:
        failures.append(f"lane_bounds did not mirror: {(lo_s, hi_s)} vs {(lo_m, hi_m)}")
    spawn_s = float(straight.ball_release_center()[1])
    spawn_m = float(mirrored.ball_release_center()[1])
    if abs(spawn_s + spawn_m) > 1e-12:
        failures.append(f"spawn y did not mirror: {spawn_s:+.4f} vs {spawn_m:+.4f}")
    if straight.depth(+0.10) <= 0 or mirrored.depth(+0.10) >= 0:
        failures.append("depth() does not follow the mirror")
    print(f"mirror: timing identical, lane {lo_s:+.3f}..{hi_s:+.3f} -> {lo_m:+.3f}..{hi_m:+.3f}, "
          f"spawn {spawn_s:+.4f} -> {spawn_m:+.4f}", flush=True)

    # The oracle must read a mirrored ball exactly as it reads a straight one.
    for (y, vy, elapsed), want in cases:
        mirror_rule = make_trigger_rule(
            "oracle", door_y=layout.door_y, insert_duration=layout.insert_duration(),
            safety_margin=float(layout.cfg.timing.safety_margin), fixed_delay_s=3.6,
            inward=-1.0,
        )
        got = mirror_rule.decide(-y, -vy, elapsed_s=elapsed)
        straight_got = oracle.decide(y, vy, elapsed_s=elapsed)
        if got.commit != straight_got.commit or got.reason != straight_got.reason:
            failures.append(
                f"mirrored oracle at y={-y} vy={-vy}: {got.reason}, "
                f"straight said {straight_got.reason}"
            )
    print("mirror: oracle reads a mirrored ball the same way", flush=True)

    # 6. The judge's flood fill under the mirror. A stand-in scene rather than a
    # built one: `classify` only ever asks the layout for geometry and the two
    # entities for a position, and this is the reading that decides success --
    # getting the mirror wrong here would score episodes backwards in silence.
    class _Entity:
        def __init__(self, pos):
            self.pos = np.asarray(pos, dtype=float)

        def get_pos(self):
            return self.pos

    class _Scene:
        def __init__(self, layout, ball_xyz, gate_xyz):
            self.layout = layout
            self._ball = _Entity(ball_xyz)
            self._gate = _Entity(gate_xyz)

        def ball_entity(self):
            return self._ball

        def gate_entity(self):
            return self._gate

    evaluator = GateCageBallEvaluator()
    for tag, lay in (("straight", straight), ("mirrored", mirrored)):
        r = lay.ball_radius
        inside_y = lay.lane_y(0.5 * (lay.door_y + lay.flat_end_y))
        outside_y = lay.lane_y(lay.entry_start_y + 0.10)
        seated_z = 0.5 * (float(lay.cfg.gate.seated_bottom_z) + float(lay.cfg.gate.seated_top_z))
        sealed = _Scene(lay, (lay.center_x, inside_y, lay.floor_top_z + r),
                        (lay.center_x, lay.door_y, seated_z))
        open_door = _Scene(lay, (lay.center_x, inside_y, lay.floor_top_z + r),
                           (lay.center_x, lay.door_y, seated_z + 0.30))
        locked_out = _Scene(lay, (lay.center_x, outside_y, lay.floor_top_z + r),
                            (lay.center_x, lay.door_y, seated_z))
        want = (("sealed", sealed, True, None),
                ("gate_up", open_door, False, "gate_not_sealed"),
                ("ball_left_outside", locked_out, False, "ball_outside"))
        for case, scene_obj, want_ok, want_label in want:
            state = evaluator.classify(scene_obj)
            got = (bool(state.is_terminal), state.failure_label)
            print(f"judge {tag:8s} {case:18s} inside={state.inside} caged={state.caged} "
                  f"terminal={state.is_terminal} label={state.failure_label}", flush=True)
            if got != (want_ok, want_label):
                failures.append(f"judge {tag}/{case}: {got}, expected {(want_ok, want_label)}")

    for failure in failures:
        print(f"FAIL: {failure}", flush=True)
    print("ok" if not failures else f"{len(failures)} failure(s)", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
