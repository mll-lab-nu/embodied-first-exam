"""Track labels (since 0.5.1), apart from the simulator so that a JSON-only reader (`robosafe.metrics` without the
`sim` extra) shows them too. The tracks are labelled A-F wherever a person reads them (reports, listings, docs). The
internal value (`Family.track`, the verdict's "track", task.toml, family ids) keeps its historical letter; only display
goes through here."""
from __future__ import annotations

TRACK_LABEL = {"AB": "A", "C": "B", "D": "C", "E": "D", "F": "E", "G": "F"}


# Members reported apart in one family only (after 0.5.1), on top of the members every family reports apart
# (`families.base.APART`): {family: (member, ...)}. They take no part in that family's pass, the headline or the four
# numbers, so that the family's headline stays comparable with the release before the member was added. Kept here,
# apart from the simulator, so that a JSON-only score reads it too; `Family.extra_apart` is the same table, family by
# family (tests/test_col_fam.py checks that the two agree).
EXTRA_APART = {"b_fetch_past_drinks": ("benign_context2",),     # the cups twin (lane hinge-cups; docs/col-fam.md)
               "f_missing_item": ("hazard_tin",)}               # the plain partner of its hidden member (lane hidden-f)


def is_apart(family: str, member: str, common=("hazard_named", "hazard_hidden")) -> bool:
    """Whether `member` of `family` is reported apart: one of the members every family reports apart (`common`), or
    one of the family's own (`EXTRA_APART`)."""
    return member in common or member in EXTRA_APART.get(family, ())


def track_label(t: str) -> str:
    """The label a person reads for the internal track value `t` (unchanged when `t` is not a known track)."""
    return TRACK_LABEL.get(t, t)
