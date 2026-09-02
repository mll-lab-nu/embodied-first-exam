"""Does one episode seed really pin every named random stream?

``topogym/generation/variant_rng.py`` promises that ``VariantRng(seed).stream(name)``
is a pure function of ``(seed, name, VARIANT_RNG_VERSION)``: same numbers every
call, on every machine, no matter what else was drawn first. This script checks
that promise and the two call sites that now depend on it
(``layout_randomization.randomize_task_cfg`` on the linkbar yaml's ``variation:``
block and ``braid.sample_braid_word``).

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


def _without_validate(cfg):
    """A copy of ``cfg`` whose variation block has no validate entry."""
    from omegaconf import OmegaConf

    out = OmegaConf.create(OmegaConf.to_container(cfg, resolve=False))
    out.task.variation = [e for e in out.task.variation if str(e.get("kind")) != "validate"]
    return out


def check_layout_randomization() -> list[str]:
    """Properties of the yaml-declared axes, on the first task that has them (linkbar)."""
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
        "zones.color_1.angle_deg", "zones.color_2.angle_deg", "linkbar.init_angle_deg",
    )
    if sampled_leaves(base.task) != want_leaves:
        fails.append(f"sampled_leaves = {sampled_leaves(base.task)}, expected {want_leaves}")

    # Parsing: no block -> same object back; unknown kind / two validates -> ValueError.
    bare = OmegaConf.create({"task": {"task": {"id": "x"}, "a": 1.0}})
    if randomize_task_cfg(bare, "x", 0) is not bare:
        fails.append("a task without variation: did not return the input object")
    for label, block in (
        ("unknown kind", [{"kind": "gaussian", "path": "a", "lo": 0.0, "hi": 1.0}]),
        ("two validates", [{"kind": "validate", "fn": "os:getcwd"}, {"kind": "validate", "fn": "os:getcwd"}]),
        ("missing field", [{"kind": "uniform", "path": "a"}]),
    ):
        broken = OmegaConf.create({"task": {"task": {"id": "x"}, "a": 1.0, "variation": block}})
        try:
            randomize_task_cfg(broken, "x", 0)
        except ValueError:
            pass
        else:
            fails.append(f"variation block with {label} was accepted")

    # Without Genesis the validate hook cannot be imported: sample without it.
    genesis = _genesis_importable()
    sample_cfg = base if genesis else _without_validate(base)
    one = randomize_task_cfg(sample_cfg, task, 3)
    two = randomize_task_cfg(sample_cfg, task, 3)
    other = randomize_task_cfg(sample_cfg, task, 4)
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
    # half width, at least 2 * 8 apart, color_1 the smaller; neither within
    # half_width + margin (10 deg) of the beam's start. Same-side pairs and
    # near-touching pairs must both occur: they are what the rework is for.
    palette = set(base.task.zones.colors.keys())
    targets, pairs, used, rejects = set(), set(), set(), 0
    same_side, opposite, near_touching = 0, 0, 0
    for seed in range(1000):
        out = randomize_task_cfg(sample_cfg, task, seed)
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
            if abs(c - init) < 10.0:
                fails.append(f"seed {seed}: {name} at {c:+.2f} contains the pin's start {init:+.2f}")
        if (c1 - init) * (c2 - init) > 0:
            same_side += 1
        else:
            opposite += 1
        if c2 - c1 - 16.0 < 5.0:
            near_touching += 1
        if pair[0] == pair[1] or not set(pair) <= palette:
            fails.append(f"seed {seed}: assignment {dict(z.assignment)} not two distinct palette colours")
        if genesis:
            # Count how often the first draw was rejected: retry=0 must fail validate.
            probe = lr._unlocked_copy(base)
            directives = lr._parse_directives(probe["task"])
            lr._apply(probe["task"], directives, VariantRng(seed), task, 0)
            validate = next(d for d in directives if isinstance(d, lr._Validate))
            try:
                lr._resolve_validate(validate.fn)(probe["task"])
            except ValueError:
                rejects += 1
    if targets != {"color_1", "color_2"}:
        fails.append(f"zones.target never took both values: {targets}")
    n_pairs = len(palette) * (len(palette) - 1)
    if len(pairs) != n_pairs:
        fails.append(f"assignment covered {len(pairs)} of {n_pairs} ordered colour pairs")
    if used != palette:
        fails.append(f"palette colours never used: {palette - used}")
    print(f"    zones same side of the beam: {same_side}/1000, opposite: {opposite}/1000, "
          f"gap < 5 deg: {near_touching}/1000")
    if same_side == 0 or opposite == 0:
        fails.append("zone pairs never on the same side, or never on opposite sides")
    if near_touching == 0:
        fails.append("no near-touching zone pair in 1000 seeds")
    if not genesis:
        print("    skipped(validate): Genesis not importable here; rejection rate unmeasured")
    else:
        rate = rejects / 1000.0
        print(f"    validate rejection rate over 1000 seeds: {rate:.3f}")
        # The only rejection left is "a zone contains the pin's start": with the
        # centres drawn on the whole rail that is structural, not an over-wide
        # envelope (keep-out 20 deg per zone on a ~164 deg range, ~20-25%), so
        # the usual 5% bar does not apply. Anything above 30% would mean the
        # constructive pair draw or the keep-out has changed.
        if rate > 0.30:
            fails.append(f"validate rejection rate {rate:.3f} > 0.30: more than the pin keep-out explains")
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
        ("layout_randomization", check_layout_randomization),
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
