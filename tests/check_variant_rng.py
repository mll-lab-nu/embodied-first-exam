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
        import topogym.tasks.connectivity.linkbar_rotate_to_zone  # noqa: F401
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

    # Envelope over 1000 seeds. Zone centres on the +/-90 rail minus the 8 deg
    # half width, at least 2 * 8 apart, color_1 the smaller. The beam's start is
    # derived onto [-15, 15] minus each zone's keep-out (half_width + margin =
    # 10 deg), so no accepted draw has the pin on a zone. Same-side pairs and
    # near-touching pairs must both occur: they are what the rework is for.
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
        if not -82.0 <= c1 <= c2 <= 82.0:
            fails.append(f"seed {seed}: centres {c1:+.2f}, {c2:+.2f} not ordered within [-82, 82]")
        if c2 - c1 < 16.0 - 1e-9:
            fails.append(f"seed {seed}: centres {c2 - c1:.2f} apart, spans overlap")
        for name, c in (("color_1", c1), ("color_2", c2)):
            if abs(c - init) < 10.0 - 1e-9:
                fails.append(f"seed {seed}: {name} at {c:+.2f} contains the pin's start {init:+.2f}")
        if (c1 - init) * (c2 - init) > 0:
            same_side += 1
        else:
            opposite += 1
        if c2 - c1 - 16.0 < 5.0:
            near_touching += 1
        if any(abs(c - init) < 12.0 for c in (c1, c2)):
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
    from topogym.tasks.connectivity.diverter_route_ball import DiverterRouteBallLayout

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
        "ball.speed", "channel.center_x", "gate_rack.center_y",
        "channel.flat_end_frac", "ball.release_frac", "gate_rack.x_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the gate hooks cannot run")
        return fails
    from topogym.tasks.connectivity.gate_cage_ball import GateCageBallLayout

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
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        layout = GateCageBallLayout(t)
        speed, cx, ry = float(t.ball.speed), float(t.channel.center_x), float(t.gate_rack.center_y)
        if not 0.080 <= speed <= 0.160:
            fails.append(f"seed {seed}: speed {speed:.3f} outside [0.08, 0.16]")
        if not 0.055 <= cx <= 0.095:
            fails.append(f"seed {seed}: center_x {cx:+.4f} outside [0.055, 0.095]")
        if not -0.030 <= ry <= 0.030:
            fails.append(f"seed {seed}: rack center_y {ry:+.4f} outside [-0.03, 0.03]")
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
    if ball_first == 0 or arm_first == 0:
        fails.append(f"hover_wait never changed sign (ball first {ball_first}, arm first {arm_first})")
    rate = rejects / 1000.0
    print(f"    ball first: {ball_first}/1000, arm first: {arm_first}/1000")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: derived ranges broken?")
    return fails


_BAND_CFG = REPO / "configs" / "task_configs" / "band_untwist_topogym_tabletop_v1.yaml"


def check_band_untwist_randomization() -> list[str]:
    """Properties of the band_untwist yaml's axes: leaves, envelope, derived end gap, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_BAND_CFG)})
    task = "band_untwist"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "figure_eight.over_end", "figure_eight.heading_deg",
        "figure_eight.center_x", "figure_eight.center_y",
        "figure_eight.half_angle_deg", "figure_eight.closed_lobe_radius",
        "figure_eight.open_lobe_radius", "figure_eight.end_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the band_untwist hooks cannot run")
        return fails
    from topogym.tasks.entangle.band_untwist import BandUntwistLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Envelope over 1000 seeds: independent axes in range, the end gap inside the
    # range the drawn open lobe allows, every check passing, both over ends drawn
    # (the anti-shortcut axis must actually flip), and a first-draw rejection
    # rate under the bar.
    rejects, over_end_counts, max_lift = 0, {0: 0, 1: 0}, 0.0
    ranges = {
        "heading_deg": (-30.0, 30.0), "center_x": (-0.010, 0.050), "center_y": (-0.030, 0.030),
        "half_angle_deg": (30.0, 60.0), "closed_lobe_radius": (0.032, 0.055),
        "open_lobe_radius": (0.040, 0.065), "end_frac": (0.0, 1.0),
    }
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        layout = BandUntwistLayout(t)
        eight = t.figure_eight
        for leaf, (lo, hi) in ranges.items():
            value = float(eight[leaf])
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {leaf} {value:+.4f} outside [{lo}, {hi}]")
        lo, hi = layout.end_gap_bounds()
        if not lo - 1e-9 <= float(eight.end_gap) <= hi + 1e-9:
            fails.append(f"seed {seed}: end_gap {float(eight.end_gap):+.4f} outside derived [{lo:+.4f}, {hi:+.4f}]")
        if int(eight.over_end) not in over_end_counts:
            fails.append(f"seed {seed}: over_end {eight.over_end} not in {{0, 1}}")
        else:
            over_end_counts[int(eight.over_end)] += 1
        bad = [name for name, _, _, ok in layout.checks() if not ok]
        if bad:
            fails.append(f"seed {seed}: checks failed after acceptance: {bad}")
        max_lift = max(max_lift, layout.predicted_lift())
        if _first_draw_rejected(lr, base, task, seed):
            rejects += 1
    if over_end_counts[0] == 0 or over_end_counts[1] == 0:
        fails.append(f"over_end never flipped: {over_end_counts}")
    rate = rejects / 1000.0
    print(f"    over_end 0: {over_end_counts[0]}/1000, 1: {over_end_counts[1]}/1000; max predicted lift {max_lift:.3f} m")
    print(f"    first-draw rejection rate over 1000 seeds: {rate:.3f} (bar {MAX_REJECTION})")
    if rate > MAX_REJECTION:
        fails.append(f"first-draw rejection rate {rate:.3f} > {MAX_REJECTION}: derived ranges broken?")
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
    from topogym.tasks.entangle.unlink_c_ring import UnlinkCRingLayout

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
        "aperture.across_flats", "bar.rest_x", "bar.rest_y", "panel.x",
        "bar.length_frac", "bar.grasp_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the bar_through_hole hooks cannot run")
        return fails
    from topogym.tasks.routing.bar_through_hole import (
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
    min_side, min_window, min_length, max_length = float("inf"), float("inf"), float("inf"), 0.0
    ranges = {
        "aperture.across_flats": (0.029, 0.038),
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
        want_x = {
            "near_a": rest_x - NEAR_A_BEHIND_CENTRE,
            "near_b": rest_x + 0.5 * length - END_SETBACK,
            "far": panel_x + 0.5 * length - END_SETBACK,
        }
        for name, want in want_x.items():
            if abs(float(t.cradles[name].x) - want) > 1e-9:
                fails.append(f"seed {seed}: cradles.{name}.x {float(t.cradles[name].x):+.4f} != derived {want:+.4f}")
        want_seat = float(t.aperture.center_z) - 0.5 * float(t.aperture.across_flats) + 0.5 * float(t.bar.across_flats)
        if abs(float(t.cradles.far.seat_axis_z) - want_seat) > 1e-9:
            fails.append(f"seed {seed}: cradles.far.seat_axis_z {float(t.cradles.far.seat_axis_z):.4f} != sill + inradius {want_seat:.4f}")
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
    from topogym.tasks.routing._rope_unwinding_geometry import (
        PLUG_TARGET_CLEARANCE, plug_spawn_task_xy, target_x_from_frac, wind_z_bounds,
    )
    from topogym.tasks.routing.rope_unwinding import RopeUnwindingLayout

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
    """Properties of the cloth_unpleat yaml's axes: leaves, envelope, the two derived
    leaves on their formulas, all three pleat widths and both pull sides drawn,
    seven checks, rejection."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    import topogym.generation.layout_randomization as lr

    base = OmegaConf.create({"task": OmegaConf.load(_CLOTH_UNPLEAT_CFG)})
    task = "cloth_unpleat"
    if not has_variation(base.task):
        return [f"{task} yaml has no variation: block"]
    want_leaves = (
        "cloth.pleat.width", "cloth.pull_side", "cloth.pleat.crest_height", "cloth.center_x",
        "physical.pull_scale", "grasp.edge_inset_frac", "cloth.center_y_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the cloth_unpleat hooks cannot run")
        return fails
    from topogym.tasks.deformation._cloth_unpleat_geometry import (
        center_along_bounds, edge_inset_bounds, pull_end_task,
    )
    from topogym.tasks.deformation.cloth_unpleat import ClothUnpleatLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    # Envelope over 1000 seeds: every axis in range; the grasp inset and the
    # band's along-axis position on their formulas inside the windows the drawn
    # pleat leaves; every check passing; all three widths and both sides drawn;
    # the reach and pull statistics printed; first-draw rejection under the bar.
    rejects = 0
    ranges = {
        "cloth.pleat.crest_height": (0.016, 0.028), "cloth.center_x": (0.010, 0.070),
        "physical.pull_scale": (0.98, 1.12), "grasp.edge_inset_frac": (0.0, 1.0), "cloth.center_y_frac": (0.0, 1.0),
    }
    widths_seen, sides_seen = {}, {}
    max_reach, max_pull, narrowed = 0.0, 0.0, 0
    for seed in range(1000):
        t = randomize_task_cfg(base, task, seed).task
        for path, (lo, hi) in ranges.items():
            value = float(OmegaConf.select(t, path))
            if not lo - 1e-9 <= value <= hi + 1e-9:
                fails.append(f"seed {seed}: {path} {value:+.4f} outside [{lo}, {hi}]")
        width = float(t.cloth.pleat.width)
        side = int(t.cloth.pull_side)
        if width not in (0.024, 0.030, 0.035):
            fails.append(f"seed {seed}: cloth.pleat.width {width} not in (0.024, 0.030, 0.035)")
        if side not in (1, -1):
            fails.append(f"seed {seed}: cloth.pull_side {side} not +1/-1")
        widths_seen[width] = widths_seen.get(width, 0) + 1
        sides_seen[side] = sides_seen.get(side, 0) + 1
        lo, hi = edge_inset_bounds(t)
        want = lo + float(t.grasp.edge_inset_frac) * (hi - lo)
        if abs(float(t.grasp.edge_inset) - want) > 1e-9:
            fails.append(f"seed {seed}: grasp.edge_inset {float(t.grasp.edge_inset):.4f} != derived {want:.4f}")
        if not 0.008 - 1e-9 <= float(t.grasp.edge_inset) <= 0.018 + 1e-9:
            fails.append(f"seed {seed}: grasp.edge_inset {float(t.grasp.edge_inset):.4f} outside [0.008, 0.018]")
        lo, hi = center_along_bounds(t)
        want = lo + float(t.cloth.center_y_frac) * (hi - lo)
        if abs(float(t.cloth.center_y) - want) > 1e-9:
            fails.append(f"seed {seed}: cloth.center_y {float(t.cloth.center_y):+.4f} != derived {want:+.4f}")
        if not -0.030 - 1e-9 <= float(t.cloth.center_y) <= 0.030 + 1e-9:
            fails.append(f"seed {seed}: cloth.center_y {float(t.cloth.center_y):+.4f} outside +-0.030")
        if hi - lo < 0.060 - 1e-9:
            narrowed += 1
        layout = ClothUnpleatLayout(t)
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
    if set(widths_seen) != {0.024, 0.030, 0.035}:
        fails.append(f"pleat.width drawn {sorted(widths_seen)}; expected all of 0.024, 0.030, 0.035")
    if set(sides_seen) != {1, -1}:
        fails.append(f"pull_side drawn {sorted(sides_seen)}; expected both +1 and -1")
    rate = rejects / 1000.0
    print(f"    pleat.width {dict(sorted(widths_seen.items()))}; pull_side {dict(sorted(sides_seen.items()))}; "
          f"max hand reach {max_reach:.3f}; max pull {max_pull * 1e3:.1f} mm; "
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
    from topogym.tasks.routing import _ring_transfer_geometry as geo
    from topogym.tasks.routing.ring_transfer import RingTransferLayout

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
        "fixtures.C.x_frac", "fixtures.C.y", "winding.climb_per_turn", "winding.wind_z_frac",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")
    if not _genesis_importable():
        print("    skipped: Genesis not importable here; the rope_winding hooks cannot run")
        return fails
    from topogym.tasks.routing._rope_winding_geometry import sweep_from_slack
    from topogym.tasks.routing._winding_post_geometry import (
        PLUG_TARGET_CLEARANCE, plug_spawn_task_xy, target_x_from_frac, wind_z_bounds,
    )
    from topogym.tasks.routing.rope_winding import RopeWindingLayout

    one = randomize_task_cfg(base, task, 3)
    if OmegaConf.to_container(one) != OmegaConf.to_container(randomize_task_cfg(base, task, 3)):
        fails.append(f"{task}: seed 3 twice gave different configs")
    if OmegaConf.to_container(one) == OmegaConf.to_container(randomize_task_cfg(base, task, 4)):
        fails.append(f"{task}: seed 3 and seed 4 gave the same config")

    rejects = 0
    ranges = {
        "fixtures.POST.x": (-0.020, 0.045), "fixtures.POST.y": (-0.020, 0.060),
        "fixtures.S.x": (-0.180, -0.120), "fixtures.S.y": (0.070, 0.130),
        "fixtures.C.x_frac": (0.0, 1.0), "fixtures.C.y": (-0.160, -0.100),
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
        want = target_x_from_frac(layout, float(t.fixtures.C.x_frac))
        if abs(float(t.fixtures.C.x) - want) > 1e-9:
            fails.append(f"seed {seed}: fixtures.C.x {float(t.fixtures.C.x):.4f} != derived {want:.4f}")
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
        ("layout_randomization(unlink_c_ring)", check_unlink_c_ring_randomization),
        ("layout_randomization(bar_through_hole)", check_bar_through_hole_randomization),
        ("layout_randomization(rope_unwinding)", check_rope_unwinding_randomization),
        ("layout_randomization(rope_winding)", check_rope_winding_randomization),
        ("layout_randomization(ring_transfer)", check_ring_transfer_randomization),
        ("layout_randomization(cloth_unpleat)", check_cloth_unpleat_randomization),
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
