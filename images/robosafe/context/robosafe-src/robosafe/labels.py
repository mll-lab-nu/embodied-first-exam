"""Track labels (since 0.5.1), apart from the simulator so that a JSON-only reader (`robosafe.metrics` without the
`sim` extra) shows them too. The tracks are labelled A-F wherever a person reads them (reports, listings, docs). The
internal value (`Family.track`, the verdict's "track", task.toml, family ids) keeps its historical letter; only display
goes through here."""
from __future__ import annotations

TRACK_LABEL = {"AB": "A", "C": "B", "D": "C", "E": "D", "F": "E", "G": "F"}


def track_label(t: str) -> str:
    """The label a person reads for the internal track value `t` (unchanged when `t` is not a known track)."""
    return TRACK_LABEL.get(t, t)
