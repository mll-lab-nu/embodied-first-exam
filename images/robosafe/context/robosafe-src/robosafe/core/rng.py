"""Deterministic random streams.

Every random draw in the benchmark comes from `stream(seed, name, counter)`: a generator that depends only on its three
arguments, so a replay in a fresh process sees the same numbers whatever else has happened in between.
"""
from __future__ import annotations

import zlib

import numpy as np


def stream(seed: int, name: str, counter: int = 0) -> np.random.Generator:
    key = [int(seed) & 0xFFFFFFFF, zlib.crc32(name.encode("utf8")), int(counter) & 0xFFFFFFFF]
    return np.random.Generator(np.random.Philox(np.random.SeedSequence(key)))
