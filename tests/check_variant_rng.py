"""Does one episode seed really pin every named random stream?

``topogym/generation/variant_rng.py`` promises that ``VariantRng(seed).stream(name)``
is a pure function of ``(seed, name, VARIANT_RNG_VERSION)``: same numbers every
call, on every machine, no matter what else was drawn first. This script checks
that promise and the two call sites that now depend on it
(``layout_randomization.randomize_task_cfg`` on the linkbar registry entry and
``braid.sample_braid_word``).

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
    randomize_task_cfg,
    registered_tasks,
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


def _linkbar_validator():
    """The real Layout validator if Genesis is importable here, else None."""
    try:
        from topogym.tasks.connectivity.linkbar_rotate_to_zone import LinkbarRotateLayout
    except Exception:
        return None
    return lambda task_cfg: LinkbarRotateLayout(task_cfg).validate()


def check_layout_randomization() -> list[str]:
    """Registry-level properties, on the first registered task (linkbar)."""
    fails: list[str] = []
    from omegaconf import OmegaConf

    base = _linkbar_cfg()
    frozen = OmegaConf.to_container(base, resolve=False)
    task = "linkbar_rotate_to_zone"

    if task not in registered_tasks():
        return [f"{task} is not registered"]
    if randomize_task_cfg(base, "no_such_task", 0) is not base:
        fails.append("unregistered task did not return the input object")

    # The registry entry can be exercised without Genesis only if its _Validate is
    # swapped for a pure-python stand-in; do that via monkeypatch of the hook.
    import topogym.generation.layout_randomization as lr

    validator = _linkbar_validator()
    stand_in = validator or (lambda task_cfg: None)
    original = lr._validate_linkbar_rotate_to_zone
    lr._validate_linkbar_rotate_to_zone = stand_in
    for d in lr._REGISTRY[task]:
        if isinstance(d, lr._Validate):
            lr._REGISTRY[task][lr._REGISTRY[task].index(d)] = lr._Validate(stand_in, d.max_retries)
    try:
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
        if one.task.zones.target != ("left", "right")[int(pick)]:
            fails.append("zones.target is not the 'linkbar_rotate_to_zone/zones.target' stream")

        # Envelope over 1000 seeds.
        targets, swaps, rejects = set(), set(), 0
        for seed in range(1000):
            out = randomize_task_cfg(base, task, seed)
            z = out.task.zones
            init = float(out.task.linkbar.init_angle_deg)
            left, right = float(z.left.angle_deg), float(z.right.angle_deg)
            targets.add(str(z.target))
            swaps.add((str(z.assignment.left), str(z.assignment.right)))
            if not -15.0 <= init <= 15.0:
                fails.append(f"seed {seed}: init {init:+.2f} outside [-15, 15]")
            for name, sweep in (("left", left - init), ("right", right - init)):
                if not 35.0 <= abs(sweep) <= 75.0:
                    fails.append(f"seed {seed}: |sweep {name}| = {abs(sweep):.2f} outside [35, 75]")
            if (left - init) * (right - init) >= 0:
                fails.append(f"seed {seed}: zones on the same side")
            if {str(z.assignment.left), str(z.assignment.right)} != {"orange", "blue"}:
                fails.append(f"seed {seed}: assignment {dict(z.assignment)} is not a permutation")
            if validator is not None:
                # Count how often the first draw was rejected: retry=0 must fail validate.
                probe = lr._unlocked_copy(base)
                lr._apply(probe["task"], lr._REGISTRY[task], VariantRng(seed), task, 0)
                try:
                    validator(probe["task"])
                except ValueError:
                    rejects += 1
        if targets != {"left", "right"}:
            fails.append(f"zones.target never took both values: {targets}")
        if len(swaps) != 2:
            fails.append(f"assignment never swapped: {swaps}")
        if validator is None:
            print("    skipped(validate): Genesis not importable here; rejection rate unmeasured")
        else:
            rate = rejects / 1000.0
            print(f"    validate rejection rate over 1000 seeds: {rate:.3f}")
            if rate > 0.05:
                fails.append(f"validate rejection rate {rate:.3f} > 0.05: envelope too wide")
    finally:
        lr._validate_linkbar_rotate_to_zone = original
        for i, d in enumerate(lr._REGISTRY[task]):
            if isinstance(d, lr._Validate):
                lr._REGISTRY[task][i] = lr._Validate(original, d.max_retries)
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
