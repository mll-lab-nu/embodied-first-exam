#!/usr/bin/env python3
"""Check the per-tick finiteness walk of GenesisWorld.read_state (topogym.world.finite.require_finite, iterative since
image 0.2.9) against the recursive topogym.world.state.require_finite_state it replaced there: same verdict, same
exception type and message (the first bad path in the recursive order) on random nested states with non-finite numbers
planted in arrays, Python / NumPy scalars and complex values, inside dicts, mapping proxies, ordered dicts, lists, tuples
and named tuples.

    python scripts/check_fast_paths.py [--trees 20000] [--seed 0]

Needs only NumPy (loads both modules by path, so no Genesis). Exit 1 on any difference. The batched rigid readout with its
cached entity layouts is checked against the per-link getters by scripts/check_read_state_batch.py."""
import argparse
import importlib.util
import math
import sys
import time
from collections import OrderedDict, namedtuple
from pathlib import Path
from types import MappingProxyType

import numpy as np

def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / rel)
    module = sys.modules[name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


state = load("topogym.world.state", "topogym/world/state.py")    # finite._explain imports it on a failure
finite = load("topogym.world.finite", "topogym/world/finite.py")
reference = state.require_finite_state


Pair = namedtuple("Pair", "a b")
BAD = (math.nan, math.inf, -math.inf)


def leaf(rng, p_bad):
    bad = rng.random() < p_bad
    kind = rng.integers(14)
    x = float(rng.choice(BAD)) if bad else float(rng.normal())
    if kind == 0:
        return x
    if kind == 1:
        return np.float64(x)
    if kind == 2:
        return np.float32(x)
    if kind == 3:
        return np.float16(x)
    if kind == 4:
        return complex(x, 0.0) if rng.random() < .5 else complex(0.0, x)
    if kind in (5, 6, 7):
        dtype = (np.float64, np.float32, np.complex128)[kind - 5]
        a = rng.normal(size=tuple(rng.integers(1, 4, size=rng.integers(0, 3)))).astype(dtype)
        if bad:
            a.reshape(-1)[rng.integers(a.size)] = rng.choice(BAD)
        return a
    if kind == 8:
        return rng.integers(-5, 5, size=3)               # integer array: never checked
    if kind == 9:
        return np.array([math.nan, 1.0], dtype=object)    # object array: never checked
    if kind == 10:
        return int(rng.integers(100))
    if kind == 11:
        return bool(rng.integers(2))
    if kind == 12:
        return None if rng.random() < .5 else "nan"
    return np.int64(rng.integers(9))


def tree(rng, depth, p_bad):
    if depth == 0 or rng.random() < .25:
        return leaf(rng, p_bad)
    n = int(rng.integers(0, 5))
    children = [tree(rng, depth - 1, p_bad) for _ in range(n)]
    kind = rng.integers(6)
    if kind == 0:
        return {f"k{i}": c for i, c in enumerate(children)}
    if kind == 1:
        return MappingProxyType({i: c for i, c in enumerate(children)})
    if kind == 2:
        return OrderedDict((f"o{i}", c) for i, c in enumerate(children))
    if kind == 3:
        return children
    if kind == 4:
        return tuple(children)
    return Pair(children[0] if children else 1.0, children[-1] if children else 2.0)


def outcome(fn, value):
    try:
        fn(value)
        return None
    except Exception as error:  # noqa: BLE001 - the comparison is the point
        return type(error).__name__, str(error)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trees", type=int, default=20000); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    diffs, failing = [], 0
    with np.errstate(all="ignore"):
        for i in range(a.trees):
            value = tree(rng, int(rng.integers(1, 6)), float(rng.choice((0.0, 0.01, 0.1))))
            want, got = outcome(reference, value), outcome(finite.require_finite, value)
            failing += want is not None
            if want != got:
                diffs.append(dict(tree=i, reference=want, iterative=got))
        big = dict(bodies={f"b{i}": dict(position_m=np.zeros(3), quaternion_wxyz=np.ones(4), link_indices=(1, 2, 3))
                           for i in range(40)},
                   articulations={f"a{i}": dict(joints={f"j{k}": dict(position=np.zeros(1), velocity=np.zeros(1))
                                                         for k in range(16)},
                                                links={f"l{k}": dict(position_m=np.zeros(3), quaternion_wxyz=np.ones(4))
                                                       for k in range(20)}) for i in range(3)},
                   physics_step=10, sim_time_s=0.025, assist_active=False, assist_model="none")
        times = {}
        for name, fn in (("reference", reference), ("iterative", finite.require_finite)):
            t = time.perf_counter()
            for _ in range(200):
                fn(big)
            times[name] = (time.perf_counter() - t) / 200
    print(f"trees {a.trees}: {failing} with a non-finite number; differences {len(diffs)}")
    print(f"two-arm-sized state: reference {times['reference'] * 1e3:.2f} ms, iterative {times['iterative'] * 1e3:.2f} ms")
    for d in diffs[:10]:
        print(d)
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
