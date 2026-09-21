"""Canonical task / varaition / camera paths for published demo videos.

The ``varaition_`` spelling is the user-selected repository convention.
Aliases name the existing fixed representatives; new IDs stay separate.
"""

from pathlib import Path
import re


_ALIASES = {
    "buzz_wire_3d": {
        "F1_compact_toy_s70_v2": "f1_vertical_wave",
        "F2_compact_toy_s70_v2": "f2_over_under_eight",
        "F3_compact_toy_s70_v2": "f3_plane_switch",
        "F2_rounded18mm": "f2_rounded18mm_diagnostic",
    },
    "fiber_bundling": {
        "thin_copper_rod_v1_08cores_r13.5mm": "standard_08_r13p5mm",
    },
    "lock_picking": {
        "standard_150mm_three_teeth_two_retreats": "standard_150mm",
    },
    "knot_untying": {"trefoil_open_v1": "trefoil"},
    "blanket_flatten": {"suspended_irregular_folds_v1": "simple_folds"},
    "horseshoe_ring": {
        "tutorial_solvable_v3_gravity_replanned_v1": "baseline",
        "paired_horseshoes_tutorial_solvable_v3": "baseline",
        "F1": "f1",
        "F2": "f2",
        "F3": "f3",
    },
    "cast_coil": {"cast_coil_photo_prototype_v1": "baseline_assembly"},
    "orbits": {"static_base_centered_v5": "base_centered"},
}


def demo_video_root(root, task, variant):
    """Return a path only; do not create, replace, or qualify any artifacts."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", task):
        raise ValueError("Use a task ID, not a filesystem path")
    name = _ALIASES.get(task, {}).get(str(variant), str(variant))
    name = name.removeprefix("varaition_")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("Use a nonempty variant ID, not a filesystem path")
    slug = name.lower().replace(".", "p")
    return Path(root) / "demos" / task / f"varaition_{slug}"
