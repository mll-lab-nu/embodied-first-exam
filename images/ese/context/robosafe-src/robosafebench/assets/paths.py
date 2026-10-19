"""Resolve the vendored runtime dependencies in checkouts and distributions."""
from __future__ import annotations

import os
from pathlib import Path


def third_party_dir() -> Path:
    """Use an explicit override or the bundled data; retain older checkout support."""
    override = os.environ.get("ROBOSAFEBENCH_THIRD_PARTY")
    if override:
        return Path(override)
    bundled = Path(__file__).with_name("data") / "third_party"
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parents[2] / "assets" / "third_party"
