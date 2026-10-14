"""Random numbers by name (docs/framework_zh.md §5, rule 4 of the sport rules): every random draw of a sport comes from
a stream named by the sport, seeded from the match seed and the name only, so a stream never depends on how many
draws another stream made, and a replay in a fresh process draws the same numbers."""
from __future__ import annotations

import hashlib

import numpy as np


def stream(cfg_or_seed, name: str) -> np.random.Generator:
    seed = getattr(cfg_or_seed, "seed", cfg_or_seed)
    sport = getattr(cfg_or_seed, "sport", "")
    h = hashlib.sha256(f"{sport}|{int(seed)}|{name}".encode()).digest()
    return np.random.Generator(np.random.PCG64(int.from_bytes(h[:16], "little")))
