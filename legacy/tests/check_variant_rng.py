"""Does one episode seed really pin every named random stream?

``topogym/generation/variant_rng.py`` promises that ``VariantRng(seed).stream(name)``
is a pure function of ``(seed, name, VARIANT_RNG_VERSION)``: same numbers every
call, on every machine, no matter what else was drawn first. This script checks
that promise and the two call sites that now depend on it
(``layout_randomization.randomize_task_cfg`` on the linkbar, diverter and gate yamls'
``variation:`` blocks, and ``braid.sample_braid_word``).

The golden-value check is deliberate: if someone changes the derivation rule
without bumping ``VARIANT_RNG_VERSION``, every recorded dataset's "seed N" silently
stops matching the scene seed N now builds. This line is where that surfaces.

    python tests/check_variant_rng.py        # numpy only; no Genesis, no GPU
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.generation.braid import sample_braid_word  # noqa: E402
from topogym.generation.layout_randomization import (  # noqa: E402
    has_variation,
    randomize_task_cfg,
    sampled_leaves,
)
from topogym.generation.variant_rng import VARIANT_RNG_VERSION, VariantRng  # noqa: E402

# Measured 2026-08-29 on numpy 2.2.2 (PCG64 + SeedSequence are version-stable by
# numpy's own compatibility policy, so one value is expected to hold on 1.26 too).
_GOLDEN = {"version": 1, "seed": 0, "name": "golden", "uniform": 0.062484451052847945}


def _draws(seed: int, name: str, n: int = 100, **kw) -> np.ndarray:
    return VariantRng(seed).stream(name, **kw).uniform(size=n)


def check_variant_rng() -> list[str]:
    fails: list[str] = []

    # Determinism: same seed + name -> same numbers, across calls and instances.
    a1 = _draws(7, "a")
    a2 = _draws(7, "a")
    if not np.array_equal(a1, a2):
        fails.append("stream('a') differs between two instances of the same seed")
    r = VariantRng(7)
    if not np.array_equal(r.stream("a").uniform(size=100), r.stream("a").uniform(size=100)):
        fails.append("stream('a') differs between two calls on one instance")

    # Name independence and seed sensitivity.
    if np.array_equal(a1, _draws(7, "b")):
        fails.append("stream('a') and stream('b') gave the same numbers")
    if np.array_equal(a1, _draws(8, "a")):
        fails.append("seed 7 and seed 8 gave the same numbers for 'a'")

    # Order independence: drawing 'b' first must not move 'a'.
    r = VariantRng(7)
    r.stream("b").uniform(size=1000)
    if not np.array_equal(r.stream("a").uniform(size=100), a1):
        fails.append("drawing 'b' before 'a' changed 'a'")

    # Retry naming: retry=k is its own stream, distinct from retry=0 and from k+1.
    r0, r1, r2 = _draws(7, "a", retry=0), _draws(7, "a", retry=1), _draws(7, "a", retry=2)
    if np.array_equal(r0, r1) or np.array_equal(r1, r2):
        fails.append("retry streams are not distinct")
    if not np.array_equal(r0, a1):
        fails.append("retry=0 is not the plain stream")

    # No module state: many instances later, seed 7 / 'a' is unchanged.
    for s in range(100):
        VariantRng(s).stream("x").uniform()
    if not np.array_equal(_draws(7, "a"), a1):
        fails.append("constructing other instances changed seed 7 / 'a'")

    # Tiers interleave.
    if [VariantRng(s).tier(3) for s in range(9)] != [0, 1, 2, 0, 1, 2, 0, 1, 2]:
        fails.append("tier(3) is not seed % 3")

    # Golden value: derivation rule unchanged.
    if VARIANT_RNG_VERSION != _GOLDEN["version"]:
        fails.append(
            f"VARIANT_RNG_VERSION is {VARIANT_RNG_VERSION}; golden was measured at "
            f"{_GOLDEN['version']} -- re-measure and update _GOLDEN"
        )
    got = VariantRng(_GOLDEN["seed"]).stream(_GOLDEN["name"]).uniform()
    if got != _GOLDEN["uniform"]:
        fails.append(
            f"golden value drifted: {got!r} != {_GOLDEN['uniform']!r} "
            "(derivation rule changed without a version bump?)"
        )
    return fails


_LINKBAR_CFG = REPO / "configs" / "task_configs" / "linkbar_rotate_to_zone_topogym_tabletop_v1.yaml"


def _linkbar_cfg():
    """``{"task": <linkbar task yaml>}`` as the demo would hand it in."""
    from omegaconf import OmegaConf

    return OmegaConf.create({"task": OmegaConf.load(_LINKBAR_CFG)})


def _genesis_importable() -> bool:
    """The linkbar validate hook imports the task module, which pulls in Genesis."""
    try:
        import topogym.tasks_legacy.connectivity.linkbar_rotate_to_zone  # noqa: F401
    except Exception:
        return False
    return True


# Every task's variation block must keep its first-draw rejection rate under
# this bar (variation_axes_plain_zh.md section 6). Above it the fix is a derived
# entry (sample a unit fraction, map it onto the range the drawn geometry allows)
# or a narrower range -- never more retries.
MAX_REJECTION = 0.02


def _first_draw_rejected(lr, base, task: str, seed: int) -> bool:
    """Would the retry=0 draw for ``seed`` be rejected (by derive or validate)?"""
    probe = lr._unlocked_copy(base)
    directives = lr._parse_directives(probe["task"])
    lr._apply(probe["task"], directives, VariantRng(seed), task, 0)
    try:
        for cls in (lr._Derived, lr._Validate):
            d = next((d for d in directives if isinstance(d, cls)), None)
            if d is not None:
                lr._resolve_fn(d.fn)(probe["task"])
    except ValueError:
        return True
    return False


def check_directives() -> list[str]:
    """Parsing and ordering rules of the variation block, on toy configs (no task module)."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    bare = OmegaConf.create({"task": {"task": {"id": "x"}, "a": 1.0}})
    if randomize_task_cfg(bare, "x", 0) is not bare:
        fails.append("a task without variation: did not return the input object")
    for label, block in (
        ("unknown kind", [{"kind": "gaussian", "path": "a", "lo": 0.0, "hi": 1.0}]),
        ("two validates", [{"kind": "validate", "fn": "os:getcwd"}, {"kind": "validate", "fn": "os:getcwd"}]),
        ("two deriveds", [{"kind": "derived", "fn": "os:getcwd"}, {"kind": "derived", "fn": "os:getcwd"}]),
        ("missing field", [{"kind": "uniform", "path": "a"}]),
        ("derived without fn", [{"kind": "derived"}]),
    ):
        broken = OmegaConf.create({"task": {"task": {"id": "x"}, "a": 1.0, "variation": block}})
        try:
            randomize_task_cfg(broken, "x", 0)
        except ValueError:
            pass
        else:
            fails.append(f"variation block with {label} was accepted")

    # derived runs after sampling and before validate, sees the drawn leaf, and
    # its ValueError counts as a rejection (the next retry redraws).
    seen: list[float] = []

    def derive(task):
        seen.append(float(task["a"]))
        task["b"] = 2.0 * float(task["a"])
        if task["a"] < 0.5:
            raise ValueError("a too small")

    def validate(task):
        if task["b"] != 2.0 * task["a"]:
            raise ValueError("derived leaf not visible to validate")

    plain = {"task": {"task": {"id": "toy"}, "a": 0.0, "b": 0.0, "variation": [
        {"kind": "uniform", "path": "a", "lo": 0.0, "hi": 1.0},
        {"kind": "derived", "fn": derive},
        {"kind": "validate", "fn": validate},
    ]}}
    if sampled_leaves(plain["task"]) != ("a",):
        fails.append(f"derived leaf leaked into sampled_leaves: {sampled_leaves(plain['task'])}")
    outs = [randomize_task_cfg(plain, "toy", seed)["task"] for seed in range(50)]
    if any(o["a"] < 0.5 or o["b"] != 2.0 * o["a"] for o in outs):
        fails.append("derived/validate order: an accepted draw has a < 0.5 or b != 2a")
    if len(seen) <= 50:
        fails.append("derive never saw a rejected draw: the ValueError path was not exercised")
    if plain["task"]["b"] != 0.0:
        fails.append("randomize_task_cfg mutated the plain-dict input")
    # Without a validate entry a derive error is a hard error, not a silent retry.
    no_validate = {"task": {"task": {"id": "toy"}, "a": 0.0, "b": 0.0, "variation": [
        {"kind": "uniform", "path": "a", "lo": 0.0, "hi": 0.4},
        {"kind": "derived", "fn": derive},
    ]}}
    try:
        randomize_task_cfg(no_validate, "toy", 0)
    except ValueError:
        pass
    else:
        fails.append("derive ValueError without a validate entry was swallowed")
    return fails


def check_layout_randomization() -> list[str]:
    """Properties of the linkbar yaml's axes: leaves, envelope, coverage, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = _linkbar_cfg()
    frozen = OmegaConf.to_container(base, resolve=False)
    task = "linkbar_rotate_to_zone"

    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "zones.target", "zones.assignment.color_1", "zones.assignment.color_2",
        "zones.color_1.angle_deg", "zones.color_2.angle_deg", "linkbar.init_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")

    # The derive and validate hooks import the task module, which pulls in Genesis.
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the linkbar hooks cannot run")
        return fails
    one = randomize_task_cfg(base, task, 3)
    two = randomize_task_cfg(base, task, 3)
    other = randomize_task_cfg(base, task, 4)
    if OmegaConf.to_container(one) != OmegaConf.to_container(two):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(other):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")
    if OmegaConf.to_container(base, resolve=False) != frozen:
        fails.append("randomize_task_cfg mutated its input")

    # Per-leaf stream: target is exactly the named stream's draw.
    pick = VariantRng(3).stream("linkbar_rotate_to_zone/zones.target").integers(2)
    if one.task.zones.target != ("color_1", "color_2")[int(pick)]:
        fails.append("zones.target is not the 'linkbar_rotate_to_zone/zones.target' stream")

    # Envelope over 1000 seeds. Zone centres on the +/-90 rail minus the 12 deg
    # half width, at least 2 * 12 apart, color_1 the smaller. The beam's start is
    # derived onto [-15, 15] minus each zone's keep-out (half_width + margin =
    # 14 deg), so no accepted draw has the pin on a zone. Same-side pairs and
    # near-touching pairs must both occur: they are what the rework is for.
    # The three bounds moved with the half width on 2026-09-10 (was 82 / 16 / 10).
    palette = set(base.task.zones.colors.keys())
    targets, pairs, used, rejects = set(), set(), set(), 0
    same_side, opposite, near_touching, split_start = 0, 0, 0, 0
    for seed in range(1000):
        out = randomize_task_cfg(base, task, seed)
        z = out.task.zones
        init = float(out.task.linkbar.init_angle_deg)
        c1, c2 = float(z.color_1.angle_deg), float(z.color_2.angle_deg)
        targets.add(str(z.target))
        pair = (str(z.assignment.color_1), str(z.assignment.color_2))
        pairs.add(pair)
        used.update(pair)
        if not -15.0 <= init <= 15.0:
            fails.append(f"seed {seed}: init {init:+.2f} outside [-15, 15]")
        if not -78.0 <= c1 <= c2 <= 78.0:
            fails.append(f"seed {seed}: centres {c1:+.2f}, {c2:+.2f} not ordered within [-78, 78]")
        if c2 - c1 < 24.0 - 1e-9:
            fails.append(f"seed {seed}: centres {c2 - c1:.2f} apart, spans overlap")
        for name, c in (("color_1", c1), ("color_2", c2)):
            if abs(c - init) < 14.0 - 1e-9:
                fails.append(f"seed {seed}: {name} at {c:+.2f} contains the pin's start {init:+.2f}")
        if (c1 - init) * (c2 - init) > 0:
            same_side += 1
        else:
            opposite += 1
        if c2 - c1 - 24.0 < 5.0:
            near_touching += 1
        if any(abs(c - init) < 16.0 for c in (c1, c2)):
            split_start += 1  # a zone's keep-out cut the span; the start sits next to it
        if pair[0] == pair[1] or not set(pair) <= palette:
            fails.append(f"seed {seed}: assignment {dict(z.assignment)} not two distinct palette colours")
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    if targets != {"color_1", "color_2"}:
        fails.append(f"zones.target never took both values: {targets}")
    n_pairs = len(palette) * (len(palette) - 1)
    if len(pairs) != n_pairs:
        fails.append(f"assignment covered {len(pairs)} of {n_pairs} ordered colour pairs")
    if used != palette:
        fails.append(f"palette colours never used: {palette - used}")
    print(f"    zones same side of the beam: {same_side}/1000, opposite: {opposite}/1000, "
          f"gap < 5 deg: {near_touching}/1000, start within 2 deg of a keep-out: {split_start}/1000")
    if same_side == 0 or opposite == 0:
        fails.append("zone pairs never on the same side, or never on opposite sides")
    if near_touching == 0:
        fails.append("no near-touching zone pair in 1000 seeds")
    if split_start == 0:
        fails.append("the beam's start never landed next to a keep-out: is the derive mapping onto the cut span?")
    rate = rejects / 1000.0
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    # Since 2026-09-02 the start is derived onto the free set, so the only
    # rejection left is the two keep-outs covering the whole +/-15 span (~0.25%).
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: constructive draw broken?")
    return fails


_DIVERTER_CFG = REPO / "configs" / "task_configs" / "diverter_route_ball_topogym_tabletop_v1.yaml"


def check_diverter_randomization() -> list[str]:
    """Properties of the diverter yaml's axes: leaves, envelope, derived ranges, coverage, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_DIVERTER_CFG)})
    task = "diverter_route_ball"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "diverter.dead_end_side", "diverter.init_sealed_side", "target_pad.enabled",
        "branch.angle_deg", "diverter.lever.radius", "ball.speed",
        "channel.fork_frac", "ball.spawn_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the diverter hooks cannot run")
        return fails
    from topogym.tasks_legacy.connectivity.diverter_route_ball import DiverterRouteBallLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")
    pick = VariantRng(3).stream(f"{task}/diverter.dead_end_side").integers(2)
    if one.task.diverter.dead_end_side != ("left", "right")[int(pick)]:
        fails.append("dead_end_side is not the named stream's draw")

    # Envelope over 1000 seeds: the independent axes stay in their ranges; the
    # two derived leaves stay in the range the drawn geometry allows; every
    # check passes; the arm never has to reach past the configured limit; the
    # 2 x 2 x 2 discrete combinations all occur and half the draws need a turn.
    combos, rejects, rotate_needed = set(), 0, 0
    reach_max, fork_lo_seen, fork_hi_seen = 0.0, 0.0, -1.0
    for seed in range(1000):
        out = randomize_task_cfg(base, task, seed)
        t = out.task
        layout = DiverterRouteBallLayout(t)
        combos.add((str(t.diverter.dead_end_side), str(t.diverter.init_sealed_side),
                    bool(t.target_pad.enabled)))
        rotate_needed += t.diverter.dead_end_side != t.diverter.init_sealed_side
        angle, lever, speed = float(t.branch.angle_deg), float(t.diverter.lever.radius), float(t.ball.speed)
        if not 24.0 <= angle <= 36.0:
            fails.append(f"seed {seed}: angle {angle:.2f} outside [24, 36]")
        if not 0.047 <= lever <= 0.063:
            fails.append(f"seed {seed}: lever {lever:.4f} outside [0.047, 0.063]")
        if not 0.090 <= speed <= 0.150:
            fails.append(f"seed {seed}: speed {speed:.3f} outside [0.09, 0.15]")
        fork_lo, fork_hi = layout.fork_origin_x_bounds()
        fork = float(t.channel.fork_origin_x)
        if not fork_lo - 1e-9 <= fork <= fork_hi + 1e-9:
            fails.append(f"seed {seed}: fork {fork:+.4f} outside derived [{fork_lo:+.4f}, {fork_hi:+.4f}]")
        spawn_lo, spawn_hi = layout.release_x_bounds()
        release = float(t.ball.release_x)
        if not spawn_lo - 1e-9 <= release <= spawn_hi + 1e-9:
            fails.append(f"seed {seed}: release {release:+.4f} outside derived [{spawn_lo:+.4f}, {spawn_hi:+.4f}]")
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        reach_max = max(reach_max, layout.knob_reach())
        fork_lo_seen, fork_hi_seen = min(fork_lo_seen, fork), max(fork_hi_seen, fork)
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    if len(combos) != 8:
        fails.append(f"only {len(combos)} of 8 (dead_end, init_sealed, pad) combinations in 1000 seeds")
    if not 0.4 <= rotate_needed / 1000.0 <= 0.6:
        fails.append(f"rotate_needed fraction {rotate_needed / 1000.0:.3f} not near 1/2")
    if reach_max > float(base.task.reach.max_knob_dist) + 1e-9:
        fails.append(f"knob reach {reach_max:.4f} exceeds reach.max_knob_dist")
    rate = rejects / 1000.0
    print(f"    rotate_needed: {rotate_needed}/1000, knob reach max {reach_max:.3f} m, "
          f"fork_origin_x in [{fork_lo_seen:+.3f}, {fork_hi_seen:+.3f}]")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    # Both coupled leaves are derived, so nothing should be rejected at all.
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: derived ranges broken?")
    return fails


_GATE_CFG = REPO / "configs" / "task_configs" / "gate_cage_ball_topogym_tabletop_v1.yaml"


def check_gate_randomization() -> list[str]:
    """Properties of the gate_cage_ball yaml's axes: leaves, envelope, derived ranges, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_GATE_CFG)})
    task = "gate_cage_ball"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "channel.open_end", "ball.radius", "channel.slope_tier", "channel.center_x",
        "gate_rack.y_jitter", "gate_rack.side",
        "channel.flat_end_frac", "ball.release_frac", "gate_rack.x_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the gate hooks cannot run")
        return fails
    from topogym.tasks_legacy.connectivity.gate_cage_ball import GateCageBallLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Envelope over 1000 seeds: independent axes in range, derived leaves in the
    # range the drawn speed / geometry allows, every check passing, and the arm
    # arriving both before and after the ball -- the sign of hover_wait is what
    # separates the trigger rules and must not be constrained away.
    rejects, ball_first, arm_first = 0, 0, 0
    # The two mirrors (2026-09-09). Each has to come up about half the time on its
    # own AND the four combinations have to occur, because the two are meant to be
    # independent: the rack's side is an absolute task-frame y while the open end
    # flips the channel, so "rack beside the entry lane" is a joint reading.
    mirror_counts: dict[tuple[int, int], int] = {}
    tiers_seen: dict[float, int] = {}
    observe: list[float] = []
    usable_idx: list[int] = []
    v_cap: list[float] = []
    # The ball's size is the monotone axis (2026-09-08). What it buys is not the
    # window -- 2 x (closed length - radius) / speed barely moves -- but the strip
    # around the doorway the plate may not be committed into, which the verifier
    # measures as radius + half the plate's thickness. Tracked here so the axis is
    # reported by the quantity it actually changes.
    radii_seen, forbidden = {}, []
    max_hover = 0.0
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        layout = GateCageBallLayout(t)
        speed, cx, ry = float(t.ball.speed), float(t.channel.center_x), float(t.gate_rack.center_y)
        radius = float(t.ball.radius)
        if radius not in (0.024, 0.030, 0.036):
            fails.append(f"seed {seed}: ball.radius {radius} not in (0.024, 0.030, 0.036)")
        radii_seen[radius] = radii_seen.get(radius, 0) + 1
        forbidden.append(2.0 * (radius + 0.5 * float(t.gate.thickness)) / speed)
        max_hover = max(max_hover, layout.hover_wait())
        # The door speed is derived from the slope tier now (2026-09-09), so the
        # thing to check is that the two agree rather than that the speed is in a
        # band: a tier whose speed drifted from its declared row would make the
        # slope a policy reads and the speed it implies disagree.
        tier = int(t.channel.slope_tier)
        row = t.channel.slope_tiers[tier]
        if abs(float(t.channel.entry_slope_deg) - float(row["deg"])) > 1e-12 or abs(float(t.ball.spawn_min_run) - float(row["min_run"])) > 1e-12:
            fails.append(f"seed {seed}: tier {tier} leaves disagree with its row")
        tiers_seen[tier] = tiers_seen.get(tier, 0) + 1
        observe.append(layout.entry_delay())
        usable = layout.sealable_pass()
        if usable is None:
            fails.append(f"seed {seed}: no sealable pass within the hover cap")
        else:
            rows = layout.pass_schedule(layout.t_ready() + 13.0)
            k = next(i + 1 for i, r in enumerate(rows) if abs(r[0] - usable[0]) < 1e-9)
            usable_idx.append(k)
            if (tier == 0) != (k == 1):
                fails.append(f"seed {seed}: tier {tier} usable pass is #{k} (tier 0 <=> pass 1)")
        v_cap.append(layout.speed_at_cap())
        if not -0.020 <= cx <= 0.020:
            fails.append(f"seed {seed}: center_x {cx:+.4f} outside [-0.02, 0.02]")
        open_end = int(t.channel.open_end)
        side = int(t.gate_rack.side)
        if open_end not in (0, 1) or side not in (0, 1):
            fails.append(f"seed {seed}: open_end={open_end} side={side} not both in (0, 1)")
        mirror_counts[(open_end, side)] = mirror_counts.get((open_end, side), 0) + 1
        want_ry = (0.150 if side else -0.150) + float(t.gate_rack.y_jitter)
        if abs(ry - want_ry) > 1e-9:
            fails.append(f"seed {seed}: rack center_y {ry:+.4f} != side+jitter {want_ry:+.4f}")
        if not -0.030 <= float(t.gate_rack.y_jitter) <= 0.030:
            fails.append(f"seed {seed}: rack y_jitter {float(t.gate_rack.y_jitter):+.4f} outside [-0.03, 0.03]")
        for name, value, (lo, hi) in (
            ("flat_end_y", float(t.channel.flat_end_y), layout.flat_end_y_bounds()),
            ("release_y", float(t.ball.release_y), layout.release_y_bounds()),
            ("rack center_x", float(t.gate_rack.center_x), layout.rack_x_bounds()),
        ):
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {name} {value:+.4f} outside derived [{lo:+.4f}, {hi:+.4f}]")
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        if layout.hover_wait() < 0.0:
            ball_first += 1
        else:
            arm_first += 1
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    # hover_wait's sign is reported for the record; the free ball always arrives
    # first (see the usable-pass check above for what now separates the rules).
    if set(radii_seen) != {0.024, 0.030, 0.036}:
        fails.append(f"ball.radius drawn {sorted(radii_seen)}; expected all three")
    if set(tiers_seen) != {0, 1, 2}:
        fails.append(f"slope tiers drawn {sorted(tiers_seen)}; expected all three")
    # Free ball (2026-09-10): the ball always beats the arm to the door and keeps
    # coming back, so what separates the trigger rules is no longer the sign of
    # hover_wait but WHICH pass is the first sealable one -- greedy seals on the
    # arm's arrival whatever the ball is doing. That index has to vary.
    if 1 not in usable_idx or max(usable_idx) < 2:
        fails.append(f"usable pass index should span pass 1 (tier 0) and later passes: {sorted(set(usable_idx))}")
    if min(v_cap) < 0.10 - 1e-9:
        fails.append(f"ball speed at the hover cap {min(v_cap):.3f} under the 0.10 floor")
    if set(mirror_counts) != {(0, 0), (0, 1), (1, 0), (1, 1)}:
        fails.append(f"open_end x rack side drew only {sorted(mirror_counts)}; expected all four")
    for combo, count in sorted(mirror_counts.items()):
        if not 175 <= count <= 325:
            fails.append(f"open_end/side {combo} drawn {count}/1000; expected near 250")
    rate = rejects / 1000.0
    print(f"    open_end x rack side (each ~250/1000): {dict(sorted(mirror_counts.items()))}")
    from collections import Counter
    print(f"    slope {dict(sorted(tiers_seen.items()))}; first arrival "
          f"{min(observe):.2f}..{max(observe):.2f} s; usable pass index {dict(sorted(Counter(usable_idx).items()))}; "
          f"speed at cap {min(v_cap):.3f}..{max(v_cap):.3f} m/s")
    print(f"    ball.radius {dict(sorted(radii_seen.items()))}; "
          f"doorway no-commit strip {min(forbidden):.2f}..{max(forbidden):.2f} s per pass; "
          f"longest hover wait {max_hover:.2f} s (cap {int(base.task.motion.max_hover_steps) * 0.01:.1f} s)")
    print(f"    ball first: {ball_first}/1000, arm first: {arm_first}/1000")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: derived ranges broken?")
    return fails


_BAND_CFG = REPO / "configs" / "task_configs" / "band_untwist_topogym_tabletop_v1.yaml"


def check_band_untwist_randomization() -> list[str]:
    """Properties of the band_untwist yaml's axes: leaves, envelope, derived leaves, rejection.

    Four spawn shapes (`band.shape`), each with its own block of axes; every
    block is drawn every episode and only the drawn shape's is read.
    """
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_BAND_CFG)})
    task = "band_untwist"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "band.shape", "band.heading_deg", "band.center_x_frac", "band.center_y_frac",
        "band.eight.over_end", "band.eight.half_angle_deg", "band.eight.closed_lobe_radius",
        "band.eight.open_lobe_radius", "band.eight.end_frac",
        "band.six.short_over", "band.six.half_angle_deg", "band.six.loop_radius",
        "band.six.short_len", "band.six.stem_len",
        "band.twist.over_end_x1", "band.twist.half_angle_deg",
        "band.twist.closed_lobe_radius", "band.twist.middle_lobe_radius",
        "band.twist.open_lobe_radius", "band.twist.end_frac",
        "band.curls.stub_side", "band.curls.half_angle_deg", "band.curls.loop_radius",
        "band.curls.stub_len", "band.curls.middle_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the band_untwist hooks cannot run")
        return fails
    from topogym.tasks_legacy.entangle.band_untwist import BandUntwistLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Over 1000 seeds: the drawn shape's axes in range, its derived leaves inside
    # the ranges the other axes allow, the centre inside the workspace, every
    # check passing, every shape drawn, every over/under value of every shape
    # drawn (the anti-shortcut axes must actually flip), and a first-draw
    # rejection rate under the bar.
    ranges = {
        "eight": {"half_angle_deg": (30.0, 60.0), "closed_lobe_radius": (0.032, 0.055),
                  "open_lobe_radius": (0.040, 0.065), "end_frac": (0.0, 1.0)},
        "six": {"half_angle_deg": (30.0, 55.0), "loop_radius": (0.030, 0.045),
                "short_len": (0.050, 0.090), "stem_len": (0.120, 0.220)},
        "twist": {"half_angle_deg": (35.0, 55.0), "closed_lobe_radius": (0.030, 0.045),
                  "middle_lobe_radius": (0.025, 0.035), "open_lobe_radius": (0.040, 0.055), "end_frac": (0.0, 1.0)},
        "curls": {"half_angle_deg": (25.0, 35.0), "loop_radius": (0.030, 0.040),
                  "stub_len": (0.050, 0.080), "middle_frac": (0.0, 1.0)},
    }
    flips = {"eight": ("over_end",), "six": ("short_over",), "twist": ("over_end_x1",), "curls": ("stub_side",)}
    counts: dict[str, int] = {shape: 0 for shape in ranges}
    seen: dict[tuple, set] = {}
    rejects, max_lift, moves = 0, 0.0, {}
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        layout = BandUntwistLayout(t)
        shape = str(t.band.shape)
        counts[shape] = counts.get(shape, 0) + 1
        block = t.band[shape]
        for leaf, (lo, hi) in ranges[shape].items():
            value = float(block[leaf])
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {shape}.{leaf} {value:+.4f} outside [{lo}, {hi}]")
        for leaf in flips[shape]:
            seen.setdefault((shape, leaf), set()).add(str(block[leaf]))
        if shape in ("eight", "twist"):
            lo, hi = layout.end_gap_bounds()
            if not lo - 1e-9 <= float(block.end_gap) <= hi + 1e-9:
                fails.append(f"seed {seed}: {shape}.end_gap {float(block.end_gap):+.4f} outside derived [{lo:+.4f}, {hi:+.4f}]")
        if shape == "curls":
            lo, hi = layout.middle_len_bounds()
            if not lo - 1e-9 <= float(block.middle_len) <= hi + 1e-9:
                fails.append(f"seed {seed}: curls.middle_len {float(block.middle_len):+.4f} outside derived [{lo:+.4f}, {hi:+.4f}]")
        if shape == "twist" and int(block.over_end_x2) != 1 - int(block.over_end_x1):
            fails.append(f"seed {seed}: twist drew the same end on top at its two crossings "
                         f"(x1={int(block.over_end_x1)}, x2={int(block.over_end_x2)}); the derive hook should alternate them")
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        plan = layout.plan()
        moves[(shape, len(plan.moves))] = moves.get((shape, len(plan.moves)), 0) + 1
        max_lift = max(max_lift, layout.predicted_lift())
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    for shape, n in counts.items():
        if n == 0:
            fails.append(f"shape {shape} never drawn in 1000 seeds")
    for (shape, leaf), values in sorted(seen.items()):
        if len(values) < 2:
            fails.append(f"{shape}.{leaf} never flipped: {sorted(values)}")
    rate = rejects / 1000.0
    print(f"    shapes over 1000 seeds: {counts}; plan lengths {dict(sorted(moves.items()))}; max planned lift {max_lift:.3f} m")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: derived ranges broken?")
    return fails


_SWAP_CFG = REPO / "configs" / "task_configs" / "swap_crossing_sign_topogym_tabletop_v1.yaml"


def check_swap_crossing_sign_randomization() -> list[str]:
    """Properties of the swap_crossing_sign yaml's axes (2026-09-11 rework: 2-3 ropes x 1-2 crossings).

    Leaves, determinism, every cell and every word drawn, derived leaves inside
    their bounds, the braid following the leaves, all check rows passing after
    acceptance, and the first-draw rejection rate. Whether every drawn layout has
    a move sequence is `tests/check_swap_crossing_sign_planner.py`'s job (a plan
    search is seconds per layout).
    """
    fails: list[str] = []
    from collections import Counter

    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_SWAP_CFG)})
    task = "swap_crossing_sign"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "braid.n_strands", "braid.length", "braid.word_index", "braid.crossing_u", "braid.crossing_gap_u",
        "braid.window_u", "braid.bow_u_0", "braid.bow_u_1", "braid.bow_u_2", "braid.channel_spacing",
        "braid.center_y_u", "braid.x_end",
        # The three-rope two-crossing cell is built by _swap_crossed_pair_scene
        # since 2026-09-12 and has its own block of axes.
        "crossed_pair.cross_u_1", "crossed_pair.cross_u_2", "crossed_pair.anchor_u_1",
        "crossed_pair.anchor_u_2", "crossed_pair.tail_u_1", "crossed_pair.tail_u_2",
        "crossed_pair.center_y_u", "crossed_pair.mirror_u",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the swap_crossing_sign hooks cannot run")
        return fails
    from topogym.tasks_legacy.entangle import _swap_crossed_pair_scene as crossed_scene
    from topogym.tasks_legacy.entangle import _swap_crossing_sign_scene as swap_scene
    from topogym.tasks_legacy.entangle.swap_crossing_sign import SwapCrossingSignLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    rejects, cells, words = 0, Counter(), Counter()
    ranges = {"channel_spacing": (0.072, 0.095), "x_end": (0.16, 0.20), "window_u": (0.0, 1.0)}
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        braid = t.braid
        layout = SwapCrossingSignLayout(t)
        cell = (int(braid.n_strands), int(braid.length))
        cells[cell] += 1
        for leaf, (lo, hi) in ranges.items():
            value = float(braid[leaf])
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {leaf} {value:+.4f} outside [{lo}, {hi}]")
        strip_half = 0.5 * float(t.power_strip.size[1])
        if layout.crossed_pair:
            # The other construction: one straight rope crossed by two others. Its
            # own properties, in its own leaves.
            cp = t.crossed_pair
            spec = layout.braid_spec()
            positions = sorted(c.position[0] for c in spec.crossings)
            if len(spec.crossings) != 2:
                fails.append(f"seed {seed}: crossed-pair cell built {len(spec.crossings)} crossings")
            elif positions[1] - positions[0] < crossed_scene.CROSSING_GAP_MIN - 1e-9:
                fails.append(f"seed {seed}: crossings {positions} closer than {crossed_scene.CROSSING_GAP_MIN}")
            for k in (1, 2):
                angle = crossed_scene.turn_angle_deg(
                    y=float(cp.center_y) + float(cp[f"anchor_dy_{k}"]), turn_x=float(cp[f"turn_x_{k}"]),
                    cross_x=float(cp[f"cross_x_{k}"]), y_straight=float(cp.center_y))
                if angle > crossed_scene.MAX_TURN_DEG + 1e-6:
                    fails.append(f"seed {seed}: rope {k} turns {angle:.1f} deg, past {crossed_scene.MAX_TURN_DEG}")
            if abs(float(cp.center_y)) > strip_half:
                fails.append(f"seed {seed}: crossed-pair center_y {float(cp.center_y):+.4f} off the strip")
            bad = [name for name, _, _, ok in layout.checks() if not ok]
            if bad:
                fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
            if _first_draw_rejected(lr, base, task, seed):
                rejects += 1
            continue
        total = float(braid.x_end) - float(braid.x_start)
        if cell[1] == 1:
            lo, hi = swap_scene.ONE_CROSSING_FRACS
            fracs = (float(braid.crossing_frac),)
        else:
            lo, hi, gap = swap_scene.two_crossing_bounds(float(braid.channel_spacing), total)
            fracs = (float(braid.crossing_frac), float(braid.crossing_frac_2))
            if (fracs[1] - fracs[0]) * total < swap_scene.CROSSING_GAP_MIN - 1e-9:
                fails.append(f"seed {seed}: crossings {fracs} closer than {swap_scene.CROSSING_GAP_MIN}")
        if not all(lo - 1e-9 <= f <= hi + 1e-9 for f in fracs):
            fails.append(f"seed {seed}: crossing fractions {fracs} outside [{lo:.3f}, {hi:.3f}]")
        limit = swap_scene.center_limit(cell[0], float(braid.channel_spacing), strip_half_length=strip_half, tube_radius=float(braid.tube_radius))
        if abs(float(braid.center_y)) > limit + 1e-9:
            fails.append(f"seed {seed}: center_y {float(braid.center_y):+.4f} beyond {limit:.4f}")
        spec = layout.braid_spec()
        if spec.word != swap_scene.braid_word(cell[0], cell[1], int(braid.word_index)):
            fails.append(f"seed {seed}: braid word {spec.word} does not follow word_index {int(braid.word_index)}")
        words[(cell, spec.word)] += 1
        if any(abs(c.position_frac - f) > 1e-12 for c, f in zip(spec.crossings, fracs)):
            fails.append(f"seed {seed}: crossings not where crossing_frac(_2) put them")
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    # (2,2) is rewritten to one crossing by the derivation and (3,2) is built by the
    # other construction, so neither owes a word here.
    missing = [(cell, word) for cell, ws in swap_scene.WORDS.items() for word in ws
               if cell[1] == 1 and words[(cell, word)] == 0]
    if missing:
        fails.append(f"words never drawn in 1000 seeds: {missing}")
    rate = rejects / 1000.0
    print("    cells: " + "  ".join(f"{c[0]}x{c[1]} {cells[c]}" for c in sorted(cells)) + f"; words drawn {len(words)}/{sum(len(w) for c, w in swap_scene.WORDS.items() if c[1] == 1)}")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: envelope no longer fits the rows?")
    return fails


_C_RING_CFG = REPO / "configs" / "task_configs" / "unlink_c_ring_topogym_tabletop_v1.yaml"


def check_unlink_c_ring_randomization() -> list[str]:
    """Properties of the unlink_c_ring yaml's axes: leaves, envelope, derived grasp azimuth, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_C_RING_CFG)})
    task = "unlink_c_ring"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "stand.hang_yaw_deg", "fixed_ring.center_x", "fixed_ring.center_y",
        "c_ring.gap_deg", "c_ring.gap_azimuth_deg",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the unlink_c_ring hooks cannot run")
        return fails
    from topogym.tasks_legacy.entangle.unlink_c_ring import UnlinkCRingLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Envelope over 1000 seeds: every axis in range, the grasp azimuth exactly the
    # opening's azimuth plus the configured offset, every check passing, and a
    # first-draw rejection rate under the bar (expected 0: no row depends on more
    # than one axis, so the envelope was cut to fit the rows).
    rejects, min_hand, min_side = 0, float("inf"), float("inf")
    ranges = {
        "stand.hang_yaw_deg": (165.0, 195.0),
        "fixed_ring.center_x": (0.040, 0.080), "fixed_ring.center_y": (0.035, 0.075),
        "c_ring.gap_deg": (21.5, 28.0), "c_ring.gap_azimuth_deg": (305.0, 325.0),
    }
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        for path, (lo, hi) in ranges.items():
            value = float(OmegaConf.select(t, path))
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {path} {value:+.4f} outside [{lo}, {hi}]")
        want = (float(t.c_ring.gap_azimuth_deg) + float(t.primitive.grasp_offset_deg)) % 360.0
        if abs(float(t.primitive.grasp_azimuth_deg) - want) > 1e-9:
            fails.append(f"seed {seed}: grasp_azimuth_deg {float(t.primitive.grasp_azimuth_deg):.4f} != derived {want:.4f}")
        layout = UnlinkCRingLayout(t)
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        geometry = layout.geometry()
        min_hand = min(min_hand, geometry.hand_clearance)
        min_side = min(min_side, 0.5 * geometry.c_ring.gap_clear_width - geometry.fixed.tube_radius)
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    rate = rejects / 1000.0
    print(f"    min hand clearance {min_hand * 1000:.2f} mm; min opening clearance per side {min_side * 1000:.2f} mm")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: envelope no longer fits the rows?")
    return fails


_BAR_CFG = REPO / "configs" / "task_configs" / "bar_through_hole_topogym_tabletop_v1.yaml"


def check_bar_through_hole_randomization() -> list[str]:
    """Properties of the bar_through_hole yaml's axes: leaves, envelope, derived length /
    grasp offset / cradles, checks, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_BAR_CFG)})
    task = "bar_through_hole"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "aperture.across_flats", "aperture.open_index", "aperture.pitch",
        "bar.rest_x", "bar.rest_y", "panel.x",
        "bar.length_frac", "bar.grasp_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the bar_through_hole hooks cannot run")
        return fails
    from topogym.tasks_legacy.routing.bar_through_hole import (
        END_SETBACK, NEAR_A_BEHIND_CENTRE, BarThroughHoleLayout,
    )

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Envelope over 1000 seeds: every axis in range; the length and the grasp
    # offset inside the ranges the drawn layout allows; the cradles on their
    # formulas; the far seat on the sill; every check passing; first-draw
    # rejection under the bar (expected 0: every row is met by construction).
    rejects = 0
    opens_seen, narrowest = {}, 1.0
    min_side, min_window, min_length, max_length = float("inf"), float("inf"), float("inf"), 0.0
    ranges = {
        "aperture.across_flats": (0.024, 0.038), "aperture.pitch": (0.080, 0.110),
        "bar.rest_x": (-0.080, -0.020), "bar.rest_y": (-0.030, 0.030),
        "panel.x": (0.100, 0.160),
        "bar.length_frac": (0.0, 1.0), "bar.grasp_frac": (0.0, 1.0),
    }
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        for path, (lo, hi) in ranges.items():
            value = float(OmegaConf.select(t, path))
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {path} {value:+.4f} outside [{lo}, {hi}]")
        layout = BarThroughHoleLayout(t)
        length, offset = float(t.bar.length), float(t.bar.grasp_offset)
        lo, hi = layout.length_bounds()
        if not lo - 1e-9 <= length <= hi + 1e-9:
            fails.append(f"seed {seed}: bar.length {length:.4f} outside derived [{lo:.4f}, {hi:.4f}]")
        glo, ghi = layout.grasp_offset_bounds()
        if not glo - 1e-9 <= offset <= ghi + 1e-9:
            fails.append(f"seed {seed}: bar.grasp_offset {offset:.4f} outside derived [{glo:.4f}, {ghi:.4f}]")
        rest_x, panel_x = float(t.bar.rest_x), float(t.panel.x)
        # The far cradle was retired 2026-09-08 -- the shaft is held by the bore
        # alone -- so only the two near ones are derived, and the seat height that
        # used to have to agree with the sill has no second party to agree with.
        want_x = {
            "near_a": rest_x - NEAR_A_BEHIND_CENTRE,
            "near_b": rest_x + 0.5 * length - END_SETBACK,
        }
        for name, want in want_x.items():
            if abs(float(t.cradles[name].x) - want) > 1e-9:
                fails.append(f"seed {seed}: cradles.{name}.x {float(t.cradles[name].x):+.4f} != derived {want:+.4f}")
        if bool(t.cradles.far.enabled):
            fails.append(f"seed {seed}: cradles.far is enabled again; the bore is meant to hold the shaft")
        # Which bore is open is the anti-shortcut axis, and where it puts the
        # shaft is what the rest of the task reads. Both are checked against the
        # one place that decides it.
        open_index = int(t.aperture.open_index)
        if open_index not in (0, 1, 2):
            fails.append(f"seed {seed}: aperture.open_index {open_index} not in (0, 1, 2)")
        opens_seen[open_index] = opens_seen.get(open_index, 0) + 1
        want_y = layout.aperture_center_y(open_index)
        if abs(float(t.aperture.center_y) - want_y) > 1e-9:
            fails.append(
                f"seed {seed}: aperture.center_y {float(t.aperture.center_y):+.4f} "
                f"!= derived {want_y:+.4f} for bore {open_index}"
            )
        narrowest = min(narrowest, layout.narrowest_panel_strip())
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        wlo, whi = layout.push_window()
        min_window = min(min_window, whi - wlo)
        min_side = min(min_side, layout.aperture_inradius - layout.bar_inradius)
        min_length, max_length = min(min_length, length), max(max_length, length)
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    rate = rejects / 1000.0
    print(f"    min lateral clearance per side {min_side * 1000:.2f} mm; min push window {min_window * 1000:.2f} mm; "
          f"length {min_length:.3f}..{max_length:.3f}")
    if set(opens_seen) != {0, 1, 2}:
        fails.append(f"aperture.open_index drawn {sorted(opens_seen)}; expected all three bores")
    print(f"    open bore {dict(sorted(opens_seen.items()))}; narrowest panel strip {narrowest * 1e3:.1f} mm")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: envelope no longer fits the rows?")
    return fails


_ROPE_UNWINDING_CFG = REPO / "configs" / "task_configs" / "rope_unwinding_topogym_tabletop_v1.yaml"


def check_rope_unwinding_randomization() -> list[str]:
    """Properties of the rope_unwinding yaml's axes: leaves, envelope, derived lowest-wrap
    height, both senses and all three turn counts drawn, checks, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_ROPE_UNWINDING_CFG)})
    task = "rope_unwinding"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "winding.start_turns", "winding.direction",
        "fixtures.POST.x", "fixtures.POST.y", "fixtures.S.x", "fixtures.S.y",
        "fixtures.C.x_frac", "fixtures.C.y", "winding.climb_per_turn", "winding.wind_z_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the rope_unwinding hooks cannot run")
        return fails
    from topogym.tasks_legacy.routing._rope_unwinding_geometry import (
        PLUG_TARGET_CLEARANCE, plug_spawn_task_xy, target_x_from_frac, wind_z_bounds,
    )
    from topogym.tasks_legacy.routing.rope_unwinding import RopeUnwindingLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Envelope over 1000 seeds: every axis in range; the lowest wrap's height on
    # its formula inside the window the drawn turns and climb leave; every check
    # passing; all three turn counts and both senses drawn; the reach, slack and
    # detour statistics printed; first-draw rejection under the bar.
    rejects = 0
    ranges = {
        "fixtures.POST.x": (-0.020, 0.060), "fixtures.POST.y": (-0.020, 0.060),
        "fixtures.S.x": (-0.180, -0.120), "fixtures.S.y": (0.070, 0.130),
        "fixtures.C.x_frac": (0.0, 1.0), "fixtures.C.y": (-0.160, -0.100),
        "winding.climb_per_turn": (0.012, 0.016), "winding.wind_z_frac": (0.0, 1.0),
    }
    turns_seen, senses_seen = {}, {}
    max_reach, min_slack, max_slack, detours = 0.0, float("inf"), 0.0, 0
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        for path, (lo, hi) in ranges.items():
            value = float(OmegaConf.select(t, path))
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {path} {value:+.4f} outside [{lo}, {hi}]")
        turns = int(t.winding.start_turns)
        sense = str(t.winding.direction)
        if turns not in (1, 2, 3):
            fails.append(f"seed {seed}: winding.start_turns {turns} not in (1, 2, 3)")
        if sense not in ("ccw", "cw"):
            fails.append(f"seed {seed}: winding.direction {sense!r} not ccw/cw")
        turns_seen[turns] = turns_seen.get(turns, 0) + 1
        senses_seen[sense] = senses_seen.get(sense, 0) + 1
        lo, hi = wind_z_bounds(t)
        want = lo + float(t.winding.wind_z_frac) * (hi - lo)
        if abs(float(t.winding.wind_z_start) - want) > 1e-9:
            fails.append(f"seed {seed}: winding.wind_z_start {float(t.winding.wind_z_start):.4f} != derived {want:.4f}")
        layout = RopeUnwindingLayout(t)
        want = target_x_from_frac(layout, float(t.fixtures.C.x_frac))
        if abs(float(t.fixtures.C.x) - want) > 1e-9:
            fails.append(f"seed {seed}: fixtures.C.x {float(t.fixtures.C.x):.4f} != derived {want:.4f}")
        if not 0.045 - 1e-9 <= float(t.fixtures.C.x) <= 0.105 + 1e-9:
            fails.append(f"seed {seed}: fixtures.C.x {float(t.fixtures.C.x):.4f} outside x_range")
        plug = plug_spawn_task_xy(layout)
        c_xy = (float(t.fixtures.C.x), (1.0 if sense == "ccw" else -1.0) * float(t.fixtures.C.y))
        if float(np.hypot(c_xy[0] - plug[0], c_xy[1] - plug[1])) < PLUG_TARGET_CLEARANCE - 1e-9:
            fails.append(f"seed {seed}: C within {PLUG_TARGET_CLEARANCE} of the plug spawn (derivation broke)")
        rows = layout.checks()
        bad = [name for name, _, _, ok in rows if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        by_name = {name: measured for name, measured, _, _ in rows}
        max_reach = max(max_reach, by_name["hand_reach"])
        min_slack, max_slack = min(min_slack, by_name["slack_in_band"]), max(max_slack, by_name["slack_in_band"])
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    if set(turns_seen) != {1, 2, 3}:
        fails.append(f"start_turns drawn {sorted(turns_seen)}; expected all of 1, 2, 3")
    if set(senses_seen) != {"ccw", "cw"}:
        fails.append(f"direction drawn {sorted(senses_seen)}; expected both ccw and cw")
    rate = rejects / 1000.0
    print(f"    start_turns {dict(sorted(turns_seen.items()))}; direction {dict(sorted(senses_seen.items()))}; "
          f"max hand reach {max_reach:.3f}; slack {min_slack * 100:.1f}..{max_slack * 100:.1f}%")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: envelope no longer fits the rows?")
    return fails


_CLOTH_UNPLEAT_CFG = REPO / "configs" / "task_configs" / "cloth_unpleat_topogym_tabletop_v1.yaml"


def check_cloth_unpleat_randomization() -> list[str]:
    """Properties of the cloth_unpleat yaml's axes (2026-09-11: single / parallel / cross).

    Twenty axes over two different scenes -- a pleated band (`single`,
    `parallel`) and a square sheet folded once each way (`cross`) -- so the
    per-seed body splits in two. Beyond the usual per-axis range and per-formula
    checks it pins the invariants each scene is built on.

    The band:

      - **the plan span is the sum of the flat runs and the pleat widths**, and
        the stored material is the band's length minus it;
      - **stored material adds up pleat by pleat.** It is what the judge's
        `recovered_frac` divides by;
      - **parallel pleats never overlap**: the second three-layer strip stops
        short of the first at every draw.

    The cross, the same conservation law read once per axis:

      - **a fold's arclength minus its plan span is the material it holds**, and
        that equals ``2 * depth + 2 * pi * radius`` by construction;
      - `cloth.material_length` and `cloth.width` are the two arclengths exactly,
        because the judge divides `recovered_frac` by one and
        `width_recovered_frac` by the other;
      - **the crease radii follow the particle size**, half of it for the first
        fold and one and a half for the second -- the two clearance rows read as
        equalities.
    """
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_CLOTH_UNPLEAT_CFG)})
    task = "cloth_unpleat"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "cloth.pleat.layout", "cloth.pleat.a.width", "cloth.band_flip",
        "cloth.pleat.a.crest_height", "cloth.pleat.b.width_frac", "cloth.pleat.b.crest_frac",
        "cloth.center_x_frac", "cloth.pleat.gap_frac", "cloth.lead_frac", "cloth.tail_frac",
        "cloth.cross.flip", "cloth.cross.first.depth_frac", "cloth.cross.second.depth_frac",
        "cloth.cross.first.lead_frac", "cloth.cross.first.tail_frac",
        "cloth.cross.second.lead_frac", "cloth.cross.second.tail_frac",
        "physical.pull_scale", "grasp.edge_inset_frac", "cloth.center_y_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the cloth_unpleat hooks cannot run")
        return fails
    from topogym.tasks_legacy.deformation import _cloth_cross_geometry as cross_geom
    from topogym.tasks_legacy.deformation import _cloth_unpleat_geometry as geom
    from topogym.tasks_legacy.deformation.cloth_unpleat import layout_for

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    rejects = 0
    ranges = {
        "cloth.pleat.a.crest_height": (0.016, 0.028), "physical.pull_scale": (0.98, 1.12),
        "cloth.pleat.b.width_frac": (0.0, 1.0), "cloth.pleat.b.crest_frac": (0.0, 1.0),
        "cloth.center_x_frac": (0.0, 1.0), "cloth.pleat.gap_frac": (0.0, 1.0),
        "cloth.lead_frac": (0.0, 1.0), "cloth.tail_frac": (0.0, 1.0),
        "grasp.edge_inset_frac": (0.0, 1.0), "cloth.center_y_frac": (0.0, 1.0),
        "cloth.cross.first.depth_frac": (0.0, 1.0), "cloth.cross.second.depth_frac": (0.0, 1.0),
        "cloth.cross.first.lead_frac": (0.0, 1.0), "cloth.cross.first.tail_frac": (0.0, 1.0),
        "cloth.cross.second.lead_frac": (0.0, 1.0), "cloth.cross.second.tail_frac": (0.0, 1.0),
    }
    # Each derived leaf against the window it was drawn from. The windows are
    # order-dependent, but every one of them reads only leaves fixed BEFORE it,
    # so they recompute the same on the finished config.
    derived = {
        "cloth.pleat.b.width": (geom.second_width_bounds, "cloth.pleat.b.width_frac", True),
        "cloth.pleat.b.crest_height": (geom.second_crest_bounds, "cloth.pleat.b.crest_frac", True),
        "cloth.center_x": (geom.center_across_bounds, "cloth.center_x_frac", False),
        "cloth.pleat.gap": (geom.gap_bounds, "cloth.pleat.gap_frac", True),
        "cloth.lead": (geom.lead_bounds, "cloth.lead_frac", False),
        "cloth.tail": (geom.tail_bounds, "cloth.tail_frac", False),
        "grasp.edge_inset": (geom.edge_inset_bounds, "grasp.edge_inset_frac", False),
        "cloth.center_y": (geom.center_along_bounds, "cloth.center_y_frac", False),
    }
    # The cross sheet's own windows, in the order `derive_cross_cfg` fixes them.
    # Each reads only leaves settled before it, so they recompute the same on the
    # finished config -- the property the band's table above relies on too.
    cross_derived = (
        ("cloth.cross.first.depth", lambda t: cross_geom.depth_bounds(t, "first"),
         "cloth.cross.first.depth_frac"),
        ("cloth.cross.second.depth", lambda t: cross_geom.depth_bounds(t, "second"),
         "cloth.cross.second.depth_frac"),
        ("cloth.cross.first.lead", lambda t: cross_geom.run_bounds(t, "first", "lead"),
         "cloth.cross.first.lead_frac"),
        ("cloth.cross.first.tail", lambda t: cross_geom.run_bounds(t, "first", "tail"),
         "cloth.cross.first.tail_frac"),
        ("cloth.cross.second.lead", lambda t: cross_geom.run_bounds(t, "second", "lead"),
         "cloth.cross.second.lead_frac"),
        ("cloth.cross.second.tail", lambda t: cross_geom.run_bounds(t, "second", "tail"),
         "cloth.cross.second.tail_frac"),
        ("grasp.edge_inset", cross_geom.cross_edge_inset_bounds, "grasp.edge_inset_frac"),
        ("cloth.center_x", cross_geom.cross_center_across_bounds, "cloth.center_x_frac"),
        ("cloth.center_y", cross_geom.cross_center_along_bounds, "cloth.center_y_frac"),
    )
    layouts_seen, widths_seen, flips_seen = {}, {}, {}
    max_reach, max_pull, lengths = 0.0, 0.0, []
    span_error, stored_error, length_error, overlaps = 0.0, 0.0, 0.0, 0
    cross_error, sheets = 0.0, []
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        for path, (lo, hi) in ranges.items():
            value = float(OmegaConf.select(t, path))
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {path} {value:+.4f} outside [{lo}, {hi}]")
        layout_name = str(t.cloth.pleat.layout)
        width = float(t.cloth.pleat.a.width)
        flip = int(t.cloth.band_flip)
        if layout_name not in ("single", "parallel", "cross"):
            fails.append(f"seed {seed}: cloth.pleat.layout {layout_name!r} not single/parallel/cross")
        if width not in (0.024, 0.027, 0.030):
            fails.append(f"seed {seed}: cloth.pleat.a.width {width} not in (0.024, 0.027, 0.030)")
        if flip not in (1, -1):
            fails.append(f"seed {seed}: cloth.band_flip {flip} not +1/-1")
        layouts_seen[layout_name] = layouts_seen.get(layout_name, 0) + 1
        flips_seen[flip] = flips_seen.get(flip, 0) + 1

        if layout_name == "cross":
            # A different scene: a square sheet folded once each way, not a band.
            # The conservation law is the same statement on each of two axes --
            # arclength minus plan span is the material that fold holds -- and the
            # judge divides by `cloth.material_length` and `cloth.width`, so both
            # have to close exactly.
            for path, bounds, frac_path in cross_derived:
                lo, hi = bounds(t)
                want = lo + float(OmegaConf.select(t, frac_path)) * (hi - lo)
                got = float(OmegaConf.select(t, path))
                if abs(got - want) > 1e-9:
                    fails.append(f"seed {seed}: {path} {got:+.5f} != derived {want:+.5f}")
            if int(t.cloth.cross.flip) not in (1, -1):
                fails.append(f"seed {seed}: cloth.cross.flip {t.cloth.cross.flip} not +1/-1")
            # Both radii follow the particle size: the first fold's stack must be
            # at least one particle thick, and the second fold's crease must clear
            # that stack plus another particle. The second one carries a
            # multiplier because it also sets how badly the fold map stretches the
            # stack (see `cloth.cross.second_radius_particles`); read it rather
            # than pinning a value here, or raising it turns this gate red for no
            # reason -- which is exactly what happened on 2026-09-12.
            particle = float(t.cloth.particle_size)
            second_scale = float(t.cloth.cross.second_radius_particles)
            if second_scale < 1.5 - 1e-9:
                fails.append(f"seed {seed}: second_radius_particles {second_scale} is under the "
                             f"1.5 the clearance rows allow")
            for key, want_radius in zip(("first", "second"), (0.5 * particle, second_scale * particle)):
                if abs(float(t.cloth.cross[key].radius) - want_radius) > 1e-12:
                    fails.append(f"seed {seed}: cross {key} radius should be {want_radius} at "
                                 f"particle {particle}, got {float(t.cloth.cross[key].radius)}")
            dims = cross_geom.cross_dimensions(t)
            for leaf, key, (length, span) in zip(("material_length", "width"), ("first", "second"), dims):
                fold = t.cloth.cross[key]
                held = 2.0 * float(fold.depth) + 2.0 * np.pi * float(fold.radius)
                cross_error = max(cross_error, abs(float(t.cloth[leaf]) - length),
                                  abs((length - span) - held))
            sheets.append((dims[0][0], dims[1][0]))
            layout = layout_for(t)
            for name, measured, limit, ok in layout.checks():
                if not ok:
                    fails.append(f"seed {seed}: cross check {name} failed after acceptance")
            if _first_draw_rejected(lr, base, task, seed):
                rejects += 1
            continue

        widths_seen[width] = widths_seen.get(width, 0) + 1
        two = layout_name != "single"

        for path, (bounds, frac_path, two_only) in derived.items():
            if two_only and not two:
                continue
            lo, hi = bounds(t)
            want = lo + float(OmegaConf.select(t, frac_path)) * (hi - lo)
            got = float(OmegaConf.select(t, path))
            if abs(got - want) > 1e-9:
                fails.append(f"seed {seed}: {path} {got:+.5f} != derived {want:+.5f}")

        layout = layout_for(t)
        marks = layout.landmarks()
        lengths.append(float(marks["material_length"]))
        span_error = max(span_error, abs(
            float(marks["plan_span"]) - sum(marks["runs"]) - sum(p["width"] for p in marks["pleats"])
        ))
        stored_error = max(stored_error, abs(sum(p["stored"] for p in marks["pleats"]) - float(marks["stored"])))
        length_error = max(length_error, abs(float(t.cloth.material_length) - float(marks["material_length"])))
        if two:
            (w1, _), (w2, _) = geom.pleat_sizes(t)
            if float(t.cloth.pleat.gap) < w2 - w1 - 1e-12:
                overlaps += 1

        rows = layout.checks()
        bad = [name for name, _, _, ok in rows if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        by_name = {name: measured for name, measured, _, _ in rows}
        max_reach = max(max_reach, by_name["hand_reach"])
        max_pull = max(max_pull, by_name["pull_within_stroke"])
        for index in range(len(geom.pulls(t))):
            end = geom.pull_end_task(t, index)
            if flip * end[1] < 0.0:
                fails.append(f"seed {seed}: pull {index} should end on the {flip:+d} side, got y {end[1]:+.4f}")
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1

    if set(layouts_seen) != {"single", "parallel", "cross"}:
        fails.append(f"pleat.layout drawn {sorted(layouts_seen)}; expected single, parallel and cross")
    if set(widths_seen) != {0.024, 0.027, 0.030}:
        fails.append(f"pleat.a.width drawn {sorted(widths_seen)}; expected all of 0.024, 0.027, 0.030")
    if set(flips_seen) != {1, -1}:
        fails.append(f"band_flip drawn {sorted(flips_seen)}; expected both +1 and -1")
    for name, value in (("plan span", span_error), ("stored material", stored_error), ("material_length", length_error)):
        if value > 1e-9:
            fails.append(f"the {name} identity is off by {value * 1e3:.6f} mm; it must close exactly")
    if overlaps:
        fails.append(f"parallel pleats overlapped in {overlaps} layouts; the gap floor is supposed to keep them apart")

    rate = rejects / 1000.0
    lengths = np.asarray(lengths)
    print(f"    layout {dict(sorted(layouts_seen.items()))}; a.width {dict(sorted(widths_seen.items()))}; "
          f"band_flip {dict(sorted(flips_seen.items()))}")
    print(f"    band length {lengths.min() * 100:.1f}..{lengths.max() * 100:.1f} cm (median "
          f"{float(np.median(lengths)) * 100:.1f}); max hand reach {max_reach:.3f}; max pull {max_pull * 1e3:.1f} mm")
    print(f"    parallel pleats overlapping: {overlaps}; span / stored / length identities close to "
          f"{max(span_error, stored_error, length_error) * 1e3:.6f} mm")
    if sheets:
        sheet = np.asarray(sheets)
        print(f"    cross sheet {sheet[:, 0].min() * 100:.1f}..{sheet[:, 0].max() * 100:.1f} cm long x "
              f"{sheet[:, 1].min() * 100:.1f}..{sheet[:, 1].max() * 100:.1f} cm wide "
              f"({int((sheet[:, 0] * sheet[:, 1]).max() / 1e-6)} particles at 1 mm, worst case); "
              f"both-axis identities close to {cross_error * 1e3:.6f} mm")
    if cross_error > 1e-9:
        fails.append(f"a cross sheet's arclength identity is off by {cross_error * 1e3:.6f} mm; "
                     f"it must close exactly on both axes")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: envelope no longer fits the rows?")
    return fails


_CLOTH_FOLD_CFG = REPO / "configs" / "task_configs" / "cloth_fold_topogym_tabletop_v1.yaml"


def check_cloth_fold_randomization() -> list[str]:
    """Properties of the cloth_fold yaml's axes: leaves, envelope, the derived sheet
    x position on its formula, all four corners and three fold fractions drawn,
    four checks, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_CLOTH_FOLD_CFG)})
    task = "cloth_fold"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "grasp.corner",
        "cloth.corner_paint.far_left", "cloth.corner_paint.far_right",
        "cloth.corner_paint.near_left", "cloth.corner_paint.near_right",
        "goal.fold_fraction", "cloth.center_y", "physical.fold_slack",
        "cloth.center_x_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the cloth_fold hooks cannot run")
        return fails
    from topogym.tasks_legacy.deformation._cloth_fold_geometry import (
        CORNER_SIGNS, center_x_bounds, corner_colour_name, far_corner_task,
        fold_target_task, grasp_point_task,
    )
    from topogym.tasks_legacy.deformation.cloth_fold import ClothFoldLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Envelope over 1000 seeds: every axis in range; the sheet's x position on
    # its formula inside the window the drawn corner / y / fraction leave under
    # the reach disc; every check passing; all four corners and three fractions;
    # the far corner's reach printed; first-draw rejection under the bar.
    rejects = 0
    ranges = {
        "cloth.center_y": (-0.030, 0.030), "physical.fold_slack": (0.96, 1.00), "cloth.center_x_frac": (0.0, 1.0),
    }
    corners_seen, fractions_seen = {}, {}
    # The colour the sentence names, and how many distinct corner-to-colour
    # assignments the 1000 seeds produce: the point of the axis is that a policy
    # cannot learn "red is the far left corner", so the assignment has to move.
    words_seen, assignments_seen = {}, set()
    max_reach, narrowed, base_xy = 0.0, 0, np.asarray([-0.570, 0.0])
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        for path, (lo, hi) in ranges.items():
            value = float(OmegaConf.select(t, path))
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {path} {value:+.4f} outside [{lo}, {hi}]")
        corner = str(t.grasp.corner)
        fraction = float(t.goal.fold_fraction)
        if corner not in CORNER_SIGNS:
            fails.append(f"seed {seed}: grasp.corner {corner!r} not one of {sorted(CORNER_SIGNS)}")
        if fraction not in (1.0, 0.9, 0.8):
            fails.append(f"seed {seed}: goal.fold_fraction {fraction} not in (1.0, 0.9, 0.8)")
        corners_seen[corner] = corners_seen.get(corner, 0) + 1
        fractions_seen[fraction] = fractions_seen.get(fraction, 0) + 1
        assignment = tuple(str(t.cloth.corner_paint[name]) for name in CORNER_SIGNS)
        if len(set(assignment)) != len(assignment):
            fails.append(f"seed {seed}: cloth.corner_paint {assignment} repeats a colour")
        assignments_seen.add(assignment)
        word = corner_colour_name(t)
        words_seen[word] = words_seen.get(word, 0) + 1
        lo, hi = center_x_bounds(t)
        want = lo + float(t.cloth.center_x_frac) * (hi - lo)
        if abs(float(t.cloth.center_x) - want) > 1e-9:
            fails.append(f"seed {seed}: cloth.center_x {float(t.cloth.center_x):.4f} != derived {want:.4f}")
        if not 0.010 - 1e-9 <= float(t.cloth.center_x) <= 0.070 + 1e-9:
            fails.append(f"seed {seed}: cloth.center_x {float(t.cloth.center_x):.4f} outside [0.010, 0.070]")
        if hi < 0.070 - 1e-9:
            narrowed += 1
        layout = ClothFoldLayout(t)
        rows = layout.checks()
        bad = [name for name, _, _, ok in rows if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        by_name = {name: measured for name, measured, _, _ in rows}
        max_reach = max(max_reach, by_name["far_corner_reach"])
        # The +x one of grasp / put-down, and the one the reach row measures, have
        # to stay the same point. They are picked by different rules (max x vs
        # max distance from the base), and at `fold_fraction` 0.5 a near_* corner
        # puts the sheet's own middle on the +x side, so the old ">" is now ">=".
        far = far_corner_task(t)
        other = (
            grasp_point_task(t)
            if np.allclose(far, fold_target_task(t))
            else fold_target_task(t)
        )
        if far[0] < float(t.cloth.center_x) - 1e-12:
            fails.append(f"seed {seed}: far corner is behind the sheet's middle")
        if np.linalg.norm(far - base_xy) < np.linalg.norm(other - base_xy) - 1e-12:
            fails.append(f"seed {seed}: the +x point is not the one furthest from the arm")
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    if set(corners_seen) != set(CORNER_SIGNS):
        fails.append(f"grasp.corner drawn {sorted(corners_seen)}; expected all four")
    if set(fractions_seen) != {1.0, 0.9, 0.8}:
        fails.append(f"goal.fold_fraction drawn {sorted(fractions_seen)}; expected 1.0, 0.9, 0.8")
    palette = sorted(OmegaConf.to_container(base.task.cloth.palette, resolve=True))
    if sorted(words_seen) != palette:
        fails.append(f"instruction colour drawn {sorted(words_seen)}; expected the whole palette {palette}")
    # 4! = 24 assignments; anything much smaller means the permutation is stuck.
    if len(assignments_seen) < 20:
        fails.append(f"only {len(assignments_seen)} distinct corner-to-colour assignments in 1000 seeds")
    rate = rejects / 1000.0
    print(f"    instruction colour {dict(sorted(words_seen.items()))}; "
          f"{len(assignments_seen)} distinct corner-to-colour assignments")
    print(f"    grasp.corner {dict(sorted(corners_seen.items()))}; "
          f"goal.fold_fraction {dict(sorted(fractions_seen.items()))}; "
          f"max far-corner reach {max_reach:.4f}; center_x window capped by reach in {narrowed} seeds")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: envelope no longer fits the rows?")
    return fails


_CLOTH_UNROLL_CFG = REPO / "configs" / "task_configs" / "cloth_unroll_topogym_tabletop_v1.yaml"


def check_cloth_unroll_randomization() -> list[str]:
    """Properties of the cloth_unroll yaml's axes: leaves, envelope, the three derived
    leaves on their formulas, all three turn counts and both pull sides drawn,
    ten checks, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_CLOTH_UNROLL_CFG)})
    task = "cloth_unroll"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "cloth.pull_side", "cloth.roll.turns", "dispenser.bar_height", "cloth.center_x",
        "cloth.roll.pitch_frac", "cloth.center_y_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the cloth_unroll hooks cannot run")
        return fails
    from topogym.tasks_legacy.deformation._cloth_unroll_geometry import (
        CENTER_ALONG_BASE, CENTER_ALONG_SHIFT, PITCH_MAX, PITCH_MIN,
        center_along_bounds, pitch_bounds, pull_end_task, start_spread_limit,
    )
    from topogym.tasks_legacy.deformation.cloth_unroll import ClothUnrollLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Envelope over 1000 seeds: every axis in range; the layer pitch, the bar's
    # along-axis position and the start-state guard on their formulas inside the
    # windows the drawn turns / bar height leave; every check passing; all three
    # turn counts and both sides drawn; the reach and pull statistics printed;
    # first-draw rejection under the bar.
    rejects = 0
    ranges = {
        "dispenser.bar_height": (0.037, 0.053), "cloth.center_x": (0.010, 0.050),
        "cloth.roll.pitch_frac": (0.0, 1.0), "cloth.center_y_frac": (0.0, 1.0),
    }
    turns_seen, sides_seen = {}, {}
    max_reach, max_pull, narrowed, pitch_capped = 0.0, 0.0, 0, 0
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        for path, (lo, hi) in ranges.items():
            value = float(OmegaConf.select(t, path))
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {path} {value:+.4f} outside [{lo}, {hi}]")
        turns = float(t.cloth.roll.turns)
        side = int(t.cloth.pull_side)
        if turns not in (1.0, 1.25, 1.5):
            fails.append(f"seed {seed}: cloth.roll.turns {turns} not in (1.0, 1.25, 1.5)")
        if side not in (1, -1):
            fails.append(f"seed {seed}: cloth.pull_side {side} not +1/-1")
        turns_seen[turns] = turns_seen.get(turns, 0) + 1
        sides_seen[side] = sides_seen.get(side, 0) + 1
        lo, hi = pitch_bounds(t)
        want = lo + float(t.cloth.roll.pitch_frac) * (hi - lo)
        if abs(float(t.cloth.roll.pitch) - want) > 1e-9:
            fails.append(f"seed {seed}: cloth.roll.pitch {float(t.cloth.roll.pitch):.5f} != derived {want:.5f}")
        if not PITCH_MIN - 1e-9 <= float(t.cloth.roll.pitch) <= PITCH_MAX + 1e-9:
            fails.append(f"seed {seed}: cloth.roll.pitch {float(t.cloth.roll.pitch):.5f} outside [{PITCH_MIN}, {PITCH_MAX}]")
        if hi < PITCH_MAX - 1e-9:
            pitch_capped += 1
        lo, hi = center_along_bounds(t)
        want = lo + float(t.cloth.center_y_frac) * (hi - lo)
        if abs(float(t.cloth.center_y) - want) > 1e-9:
            fails.append(f"seed {seed}: cloth.center_y {float(t.cloth.center_y):+.4f} != derived {want:+.4f}")
        along = side * float(t.cloth.center_y)
        if not CENTER_ALONG_BASE - CENTER_ALONG_SHIFT - 1e-9 <= along <= CENTER_ALONG_BASE + CENTER_ALONG_SHIFT + 1e-9:
            fails.append(f"seed {seed}: cloth.center_y {float(t.cloth.center_y):+.4f} outside the +-0.030 window about {CENTER_ALONG_BASE}")
        if hi - lo < 2.0 * CENTER_ALONG_SHIFT - 1e-9:
            narrowed += 1
        if abs(float(t.grasp.max_start_spread_ratio) - start_spread_limit(t)) > 1e-9:
            fails.append(f"seed {seed}: grasp.max_start_spread_ratio {float(t.grasp.max_start_spread_ratio):.4f} != derived {start_spread_limit(t):.4f}")
        layout = ClothUnrollLayout(t)
        rows = layout.checks()
        bad = [name for name, _, _, ok in rows if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        by_name = {name: measured for name, measured, _, _ in rows}
        max_reach = max(max_reach, by_name["hand_reach"])
        max_pull = max(max_pull, by_name["pull_within_stroke"])
        end = pull_end_task(t)
        if side * end[1] < 0.0:
            fails.append(f"seed {seed}: pull_side {side} but the pull ends at y {end[1]:+.4f}")
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    if set(turns_seen) != {1.0, 1.25, 1.5}:
        fails.append(f"roll.turns drawn {sorted(turns_seen)}; expected all of 1.0, 1.25, 1.5")
    if set(sides_seen) != {1, -1}:
        fails.append(f"pull_side drawn {sorted(sides_seen)}; expected both +1 and -1")
    rate = rejects / 1000.0
    print(f"    roll.turns {dict(sorted(turns_seen.items()))}; pull_side {dict(sorted(sides_seen.items()))}; "
          f"max hand reach {max_reach:.3f}; max pull {max_pull * 1e3:.1f} mm; "
          f"pitch window capped below {PITCH_MAX} in {pitch_capped} seeds; "
          f"centre window narrowed by reach / workspace in {narrowed} seeds")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: envelope no longer fits the rows?")
    return fails


_RING_TRANSFER_CFG = REPO / "configs" / "task_configs" / "ring_transfer_topogym_tabletop_v1.yaml"


def check_ring_transfer_randomization() -> list[str]:
    """Properties of the ring_transfer yaml's axes: leaves, envelope, the pair's
    derived midpoint inside its windows and the posts on the pair, both start
    posts drawn, checks, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_RING_TRANSFER_CFG)})
    task = "ring_transfer"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "ring.on_post", "post_shape.height", "post_shape.radius", "post_shape.head_overhang",
        "pair.spacing", "pair.heading_deg", "pair.mid_x_frac", "pair.mid_y_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the ring_transfer hooks cannot run")
        return fails
    from topogym.tasks_legacy.routing import _ring_transfer_geometry as geo
    from topogym.tasks_legacy.routing.ring_transfer import RingTransferLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Envelope over 1000 seeds: every axis in range; the midpoint on its formula
    # inside the windows the drawn spacing / heading / reach leave; the posts on
    # the pair; the goal post the other one; every check passing; both start
    # posts drawn; reach and window statistics printed; first-draw rejection
    # under the bar.
    rejects = 0
    ranges = {
        "post_shape.height": (0.085, 0.115), "post_shape.radius": (0.013, 0.022),
        "post_shape.head_overhang": (0.008, 0.014), "pair.spacing": (0.180, 0.280),
        "pair.heading_deg": (-30.0, 30.0), "pair.mid_x_frac": (0.0, 1.0), "pair.mid_y_frac": (0.0, 1.0),
    }
    posts_seen: dict[str, int] = {}
    max_reach, min_x_window, min_margin = 0.0, float("inf"), {}
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        for path, (lo, hi) in ranges.items():
            value = float(OmegaConf.select(t, path))
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {path} {value:+.4f} outside [{lo}, {hi}]")
        on_post = str(t.ring.on_post)
        if on_post not in ("A", "B"):
            fails.append(f"seed {seed}: ring.on_post {on_post!r} not A/B")
        posts_seen[on_post] = posts_seen.get(on_post, 0) + 1
        if str(t.goal.on_post) != geo.other_post(on_post):
            fails.append(f"seed {seed}: goal.on_post {t.goal.on_post!r} is not the other post of {on_post!r}")
        layout = RingTransferLayout(t)
        if f"post {on_post} onto post {t.goal.on_post}" not in layout.instruction():
            fails.append(f"seed {seed}: instruction {layout.instruction()!r} does not name both posts in order")
        y_window, x_window = layout.mid_windows()
        want_y = y_window[0] + float(t.pair.mid_y_frac) * (y_window[1] - y_window[0])
        want_x = x_window[0] + float(t.pair.mid_x_frac) * (x_window[1] - x_window[0])
        if abs(float(t.pair.mid_y) - want_y) > 1e-9:
            fails.append(f"seed {seed}: pair.mid_y {float(t.pair.mid_y):+.4f} != derived {want_y:+.4f}")
        if abs(float(t.pair.mid_x) - want_x) > 1e-9:
            fails.append(f"seed {seed}: pair.mid_x {float(t.pair.mid_x):+.4f} != derived {want_x:+.4f}")
        min_x_window = min(min_x_window, x_window[1] - x_window[0])
        for name, center in geo.pair_centers(t.pair).items():
            got = (float(t.posts[name].x), float(t.posts[name].y))
            if abs(got[0] - center[0]) > 1e-9 or abs(got[1] - center[1]) > 1e-9:
                fails.append(f"seed {seed}: posts.{name} {got} not on the pair {center.tolist()}")
        rows = layout.checks()
        bad = [name for name, _, _, ok in rows if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        for name, measured, limit, _ in rows:
            margin = (limit - measured) if name == "hand_reach" else (measured - limit)
            min_margin[name] = min(min_margin.get(name, float("inf")), margin)
        max_reach = max(max_reach, dict((n, m) for n, m, _, _ in rows)["hand_reach"])
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    if set(posts_seen) != {"A", "B"}:
        fails.append(f"ring.on_post drawn {sorted(posts_seen)}; expected both A and B")
    rate = rejects / 1000.0
    tight = sorted(min_margin.items(), key=lambda kv: kv[1])[:3]
    print(f"    on_post {dict(sorted(posts_seen.items()))}; max hand reach {max_reach:.3f}; "
          f"narrowest mid_x window {min_x_window * 1000:.1f} mm; tightest rows "
          + ", ".join(f"{n} {m * 1000:+.1f} mm" for n, m in tight))
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: envelope no longer fits the rows?")
    return fails


_ROPE_WINDING_CFG = REPO / "configs" / "task_configs" / "rope_winding_topogym_tabletop_v1.yaml"


def check_rope_winding_randomization() -> list[str]:
    """Properties of the rope_winding yaml's axes: leaves, envelope, the three derived
    leaves (lowest wrap, target x, spawn-arc sweep) on their rules, both senses and all
    three turn counts drawn, checks, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_ROPE_WINDING_CFG)})
    task = "rope_winding"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "winding.turns", "winding.direction",
        "fixtures.POST.x", "fixtures.POST.y", "fixtures.S.x", "fixtures.S.y",
        "fixtures.C.y_frac", "fixtures.C.x_frac", "winding.climb_per_turn", "winding.wind_z_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the rope_winding hooks cannot run")
        return fails
    from topogym.tasks_legacy.routing._rope_winding_geometry import (
        sweep_from_slack, target_x_from_frac, target_y_from_frac,
    )
    from topogym.tasks_legacy.routing._winding_post_geometry import (
        PLUG_TARGET_CLEARANCE, plug_spawn_task_xy, wind_z_bounds,
    )
    from topogym.tasks_legacy.routing.rope_winding import RopeWindingLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    rejects = 0
    ranges = {
        "fixtures.POST.x": (-0.020, 0.045), "fixtures.POST.y": (-0.020, 0.060),
        "fixtures.S.x": (-0.180, -0.120), "fixtures.S.y": (0.070, 0.130),
        "fixtures.C.y_frac": (0.0, 1.0), "fixtures.C.x_frac": (0.0, 1.0),
        "winding.climb_per_turn": (0.010, 0.016), "winding.wind_z_frac": (0.0, 1.0),
    }
    turns_seen, senses_seen = {}, {}
    max_reach, min_sweep, max_sweep, slid = 0.0, float("inf"), 0.0, 0
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        for path, (lo, hi) in ranges.items():
            value = float(OmegaConf.select(t, path))
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {path} {value:+.4f} outside [{lo}, {hi}]")
        turns, sense = int(t.winding.turns), str(t.winding.direction)
        turns_seen[turns] = turns_seen.get(turns, 0) + 1
        senses_seen[sense] = senses_seen.get(sense, 0) + 1
        lo, hi = wind_z_bounds(t)
        want = lo + float(t.winding.wind_z_frac) * (hi - lo)
        if abs(float(t.winding.wind_z_start) - want) > 1e-9:
            fails.append(f"seed {seed}: winding.wind_z_start {float(t.winding.wind_z_start):.4f} != derived {want:.4f}")
        layout = RopeWindingLayout(t)
        want = target_y_from_frac(layout, float(t.fixtures.C.y_frac))
        if abs(float(t.fixtures.C.y) - want) > 1e-9:
            fails.append(f"seed {seed}: fixtures.C.y {float(t.fixtures.C.y):.4f} != derived {want:.4f}")
        if not -0.160 - 1e-9 <= float(t.fixtures.C.y) <= -0.100 + 1e-9:
            fails.append(f"seed {seed}: fixtures.C.y {float(t.fixtures.C.y):.4f} outside y_range")
        want = target_x_from_frac(layout, float(t.fixtures.C.x_frac))
        if abs(float(t.fixtures.C.x) - want) > 1e-9:
            fails.append(f"seed {seed}: fixtures.C.x {float(t.fixtures.C.x):.4f} != derived {want:.4f}")
        if not 0.045 - 1e-9 <= float(t.fixtures.C.x) <= 0.105 + 1e-9:
            fails.append(f"seed {seed}: fixtures.C.x {float(t.fixtures.C.x):.4f} outside x_range")
        plug = plug_spawn_task_xy(layout)
        if float(np.hypot(float(t.fixtures.C.x) - plug[0], float(t.fixtures.C.y) - plug[1])) < PLUG_TARGET_CLEARANCE - 1e-9:
            fails.append(f"seed {seed}: C within {PLUG_TARGET_CLEARANCE} of the plug spawn (derivation broke)")
        want = sweep_from_slack(layout)
        if abs(float(t.rope.spawn_arc.sweep_deg) - want) > 1e-6:
            fails.append(f"seed {seed}: spawn_arc.sweep_deg {float(t.rope.spawn_arc.sweep_deg):.2f} != solved {want:.2f}")
        rows = layout.checks()
        bad = [name for name, _, _, ok in rows if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        by_name = {name: measured for name, measured, _, _ in rows}
        max_reach = max(max_reach, by_name["hand_reach"])
        min_sweep, max_sweep = min(min_sweep, by_name["sweep_in_range"]), max(max_sweep, by_name["sweep_in_range"])
        # The plug slides back from its default bearing only when the anchor sits
        # north-east of the post; count how often the rule engages.
        bearing = np.degrees(np.arctan2(plug[1] - float(t.fixtures.POST.y), plug[0] - float(t.fixtures.POST.x))) % 360.0
        if bearing < 307.0:
            slid += 1
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    if set(turns_seen) != {1, 2, 3}:
        fails.append(f"turns drawn {sorted(turns_seen)}; expected all of 1, 2, 3")
    if set(senses_seen) != {"ccw", "cw"}:
        fails.append(f"direction drawn {sorted(senses_seen)}; expected both ccw and cw")
    rate = rejects / 1000.0
    print(f"    turns {dict(sorted(turns_seen.items()))}; direction {dict(sorted(senses_seen.items()))}; "
          f"max hand reach {max_reach:.3f}; sweep {min_sweep:.0f}..{max_sweep:.0f} deg; plug slid back in {slid} draws")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: envelope no longer fits the rows?")
    return fails


def check_braid() -> list[str]:
    fails: list[str] = []
    signs = set()
    for s in range(10):
        by_seed = sample_braid_word(n_strands=2, length=1, seed=s)
        by_rng = sample_braid_word(
            n_strands=2, length=1, rng=VariantRng(s).stream("braid/word")
        )
        if by_seed != by_rng:
            fails.append(f"braid seed {s}: seed path {by_seed} != rng path {by_rng}")
        signs.add(int(np.sign(by_seed[0])))
    if signs != {-1, 1}:
        fails.append(f"braid sign over seeds 0..9 is not both signs: {signs}")
    if sample_braid_word(n_strands=3, length=4, seed=5) != sample_braid_word(
        n_strands=3, length=4, seed=5
    ):
        fails.append("braid word not deterministic in seed")
    try:
        sample_braid_word(n_strands=2, length=1)
    except ValueError:
        pass
    else:
        fails.append("sample_braid_word accepted neither seed nor rng")
    return fails


def main() -> int:
    sections = [
        ("variant_rng", check_variant_rng),
        ("directives", check_directives),
        ("layout_randomization(linkbar)", check_layout_randomization),
        ("layout_randomization(diverter)", check_diverter_randomization),
        ("layout_randomization(gate)", check_gate_randomization),
        ("layout_randomization(band_untwist)", check_band_untwist_randomization),
        ("layout_randomization(swap_crossing_sign)", check_swap_crossing_sign_randomization),
        ("layout_randomization(unlink_c_ring)", check_unlink_c_ring_randomization),
        ("layout_randomization(bar_through_hole)", check_bar_through_hole_randomization),
        ("layout_randomization(rope_unwinding)", check_rope_unwinding_randomization),
        ("layout_randomization(rope_winding)", check_rope_winding_randomization),
        ("layout_randomization(ring_transfer)", check_ring_transfer_randomization),
        ("layout_randomization(cloth_unpleat)", check_cloth_unpleat_randomization),
        ("layout_randomization(cloth_unroll)", check_cloth_unroll_randomization),
        ("layout_randomization(cloth_fold)", check_cloth_fold_randomization),
        ("braid", check_braid),
    ]
    total = 0
    for name, fn in sections:
        fails = fn()
        total += len(fails)
        print(f"[{'FAIL' if fails else 'PASS'}] {name}")
        for f in fails:
            print(f"    - {f}")
    print(f"numpy {np.__version__}, VARIANT_RNG_VERSION={VARIANT_RNG_VERSION}")
    print("PASS" if total == 0 else f"FAIL ({total})")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
