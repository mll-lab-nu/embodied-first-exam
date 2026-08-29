"""Per-episode seed -> named, independent random streams.

One episode has one integer seed. Everything random about that episode (which
side the dead end is on, where the post sits, the cloth texture, waypoint noise)
must be a pure function of that seed, so the episode can be rebuilt bit-for-bit
on any machine at any later date.

The naive way -- one ``default_rng(seed)`` that every axis draws from in code
order -- breaks that promise the first time an axis is added or reordered: every
axis drawn *after* the change gets different numbers for the same seed, and a
dataset that says "seed 7" no longer matches the scene seed 7 now produces.

``VariantRng`` avoids that by deriving one stream *per name*. Each stream is a
pure function of ``(seed, name, VARIANT_RNG_VERSION)``:

- ``name`` is hashed with SHA-256 (not Python's ``hash()``, which is salted per
  process) and the leading 8 bytes become a ``SeedSequence`` spawn key;
- ``SeedSequence(seed, spawn_key=(key,))`` is deterministic in numpy 1.26 and 2.x.

Consequences:

- Adding, removing or reordering axes never changes another axis's draws.
- ``stream(name)`` called twice returns two fresh generators with identical
  sequences. There is no hidden counter. One name is meant to have one consumer
  per episode; if a sample is rejected and must be redrawn, pass ``retry=k`` so the
  k-th redraw is itself a pure function of the seed.
- No module-level state. Construct one instance per episode; threads and batched
  environments each hold their own instance. Nothing here needs a lock.
- ``tier(n)`` is ``seed % n`` and consumes no randomness. It picks the difficulty
  tier once tiers exist, so tiers interleave across any seed list.

Name convention: ``"<task_id>/<config.leaf.path>"`` for layout axes
(``"rope_winding/fixtures.POST.pos"``); reserved prefixes ``"visual/"`` (textures,
colours), ``"demo/"`` (execution-time noise such as waypoint jitter) and
``"braid/word"`` for the braid sampler. Bump ``VARIANT_RNG_VERSION`` if the
derivation rule ever changes; the old mapping cannot be reproduced otherwise.
"""

from __future__ import annotations

import hashlib

import numpy as np

# Derivation-rule version. Part of the hash input, so a rule change under the same
# number is impossible to hide; recorded alongside the seed by the generators.
VARIANT_RNG_VERSION = 1


def _spawn_key(name: str) -> int:
    payload = f"v{VARIANT_RNG_VERSION}/{name}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little")


class VariantRng:
    """Named random streams derived from one episode seed. See module docstring."""

    __slots__ = ("_seed",)

    def __init__(self, seed: int):
        self._seed = int(seed)

    @property
    def seed(self) -> int:
        return self._seed

    def stream(self, name: str, *, retry: int = 0) -> np.random.Generator:
        """A fresh generator for ``name``; identical every time for the same seed.

        ``retry`` > 0 names the k-th redraw after a rejected sample, so rejection
        sampling stays a pure function of the seed instead of depending on how
        many draws happened before.
        """
        if not name:
            raise ValueError("VariantRng.stream needs a non-empty name.")
        if int(retry) < 0:
            raise ValueError(f"retry must be >= 0, got {retry}.")
        full = name if int(retry) == 0 else f"{name}#retry{int(retry)}"
        return np.random.default_rng(
            np.random.SeedSequence(self._seed, spawn_key=(_spawn_key(full),))
        )

    def tier(self, n: int) -> int:
        """``seed % n``: which of ``n`` interleaved tiers this episode belongs to."""
        if int(n) <= 0:
            raise ValueError(f"n must be >= 1, got {n}.")
        return self._seed % int(n)

    def __repr__(self) -> str:
        return f"VariantRng(seed={self._seed})"
