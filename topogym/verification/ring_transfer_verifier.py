"""ring_transfer (docx 2.6) readings: which posts the loop encloses, and the path
evidence that says how it got there.

The loop is a closed curve, so "around post P" is a strict topological state:
the winding number of the loop's centerline about P's vertical axis, read in
the top-down projection. For a closed curve that is an integer; a reading far
from one means the centerline could not be recovered (an empty material bin,
a strand passing through the axis), not that the topology is fractional.

Readings are per post -- `winding: {name: int}` -- and the enclosure is the set
of posts wound exactly once. That is the variant axis (docx 2.7's "enclose a
given subset" family) carried in the interface from the start; the A->B
transfer is one goal among the ones this can express.

Numeric functions only in this module for now; the State / Evaluator pair
follows once the spike has shown which readings are stable enough to gate on.
"""

from __future__ import annotations

import numpy as np


def loop_centerline(nodes: np.ndarray, members: list[np.ndarray]) -> np.ndarray:
    """Ordered closed centerline: mean position of each material bin.

    `members` come from the build (`RingTransferSceneBuilder`), one array of
    FEM vertex indices per arc-length bin of the SPAWN shape. tetgen does not
    preserve order, so material identity is the only way to order the loop.
    """

    return np.asarray([nodes[group].mean(axis=0) for group in members], dtype=float)


def post_winding(centerline: np.ndarray, post_xy) -> float:
    """Winding number of a closed xy curve about a point: summed signed turning / 2 pi."""

    pts = np.asarray(centerline, dtype=float)[:, :2] - np.asarray(post_xy, dtype=float)[None, :]
    angles = np.arctan2(pts[:, 1], pts[:, 0])
    steps = np.diff(np.concatenate([angles, angles[:1]]))
    steps = np.arctan2(np.sin(steps), np.cos(steps))
    return float(steps.sum() / (2.0 * np.pi))


def winding_signature(
    centerline: np.ndarray, posts: dict, *, tolerance: float
) -> tuple[dict[str, int], dict[str, float], bool]:
    """Per-post integer windings, the raw readings, and whether all were integral."""

    raw = {name: post_winding(centerline, post.center) for name, post in posts.items()}
    rounded = {name: int(np.rint(value)) for name, value in raw.items()}
    integral = all(abs(raw[name] - rounded[name]) <= tolerance for name in raw)
    return rounded, raw, integral


def enclosure_of(winding: dict[str, int]) -> frozenset:
    return frozenset(name for name, turns in winding.items() if abs(turns) == 1)


def post_surface_gap(nodes: np.ndarray, post) -> float:
    """Closest FEM vertex to the post's shaft surface, over the shaft's height. Negative = inside."""

    pts = np.asarray(nodes, dtype=float)
    inside_height = (pts[:, 2] >= 0.0) & (pts[:, 2] <= post.top_z)
    if not np.any(inside_height):
        return float("inf")
    radial = np.linalg.norm(pts[inside_height, :2] - post.center[None, :], axis=1)
    return float(radial.min() - post.radius)


def post_top_crossed(nodes: np.ndarray, post, *, wrap_band: float) -> bool:
    """Any vertex within `wrap_band` of the axis above the post top: the loop is over it."""

    pts = np.asarray(nodes, dtype=float)
    near = np.linalg.norm(pts[:, :2] - post.center[None, :], axis=1) <= wrap_band
    return bool(np.any(near & (pts[:, 2] > post.top_z)))


def post_contact_count(nodes: np.ndarray, post, *, tube_radius: float, slack: float = 0.002) -> int:
    """Vertices within one tube diameter (plus slack) of the shaft: the loop is touching it."""

    pts = np.asarray(nodes, dtype=float)
    inside_height = (pts[:, 2] >= 0.0) & (pts[:, 2] <= post.top_z)
    radial = np.linalg.norm(pts[:, :2] - post.center[None, :], axis=1)
    return int(np.count_nonzero(inside_height & (radial <= post.radius + 2.0 * tube_radius + slack)))


__all__ = [
    "enclosure_of",
    "loop_centerline",
    "post_contact_count",
    "post_surface_gap",
    "post_top_crossed",
    "post_winding",
    "winding_signature",
]
