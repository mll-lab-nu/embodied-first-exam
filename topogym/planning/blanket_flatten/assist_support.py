"""Compatibility entry for old runners; Blanket now declares its own birth UV.

The public task and PBD binder provide material coordinates in every process,
including Harbor's agent and verifier. No oracle-only patch is installed.
"""


def enable():
    """Retained for existing callers; shared runtime needs no activation."""
