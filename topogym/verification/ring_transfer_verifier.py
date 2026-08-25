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


# ---------------------------------------------------------------------------
# State / Evaluator (the judging contract; readings above are what they read)
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field  # noqa: E402


@dataclass(frozen=True)
class RingTransferThresholds:
    winding_tolerance: float
    min_surface_gap: float

    @classmethod
    def from_config(cls, success_cfg) -> "RingTransferThresholds":
        return cls(
            winding_tolerance=float(success_cfg.winding_tolerance),
            min_surface_gap=float(success_cfg.min_surface_gap),
        )


@dataclass
class RingTransferWatch:
    """Path evidence accumulated every step: which post tops the loop went over,
    and how close it came to any shaft. The end state alone cannot tell a loop
    that was carried over a post from one that was threaded through it."""

    posts: dict
    tube_radius: float
    top_crossed: dict[str, bool] = field(default_factory=dict)
    min_gap: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.top_crossed = {name: False for name in self.posts}
        self.min_gap = {name: float("inf") for name in self.posts}

    def check(self, nodes: np.ndarray) -> None:
        for name, post in self.posts.items():
            band = post.radius + 3.0 * self.tube_radius
            self.top_crossed[name] = self.top_crossed[name] or post_top_crossed(nodes, post, wrap_band=band)
            self.min_gap[name] = min(self.min_gap[name], post_surface_gap(nodes, post))


@dataclass(frozen=True)
class RingTransferState:
    winding: dict[str, int]
    raw_winding: dict[str, float]
    integral: bool
    enclosure: frozenset
    goal: frozenset
    required_crossings: frozenset  # posts whose top had to be crossed
    top_crossed: dict[str, bool]
    min_gap: dict[str, float]
    length_ratio: float
    min_surface_gap: float

    @property
    def enclosure_ok(self) -> bool:
        return self.integral and self.enclosure == self.goal

    @property
    def path_ok(self) -> bool:
        return all(self.top_crossed.get(name, False) for name in self.required_crossings)

    @property
    def penetrated(self) -> bool:
        return any(gap < self.min_surface_gap for gap in self.min_gap.values())

    @property
    def is_terminal(self) -> bool:
        return self.enclosure_ok and self.path_ok and not self.penetrated

    def to_info(self) -> dict:
        return {
            "winding": dict(self.winding),
            "raw_winding": {k: round(v, 3) for k, v in self.raw_winding.items()},
            "integral": self.integral,
            "enclosure": sorted(self.enclosure),
            "goal": sorted(self.goal),
            "top_crossed": dict(self.top_crossed),
            "min_gap_mm": {k: round(v * 1000.0, 2) for k, v in self.min_gap.items()},
            "length_ratio": round(self.length_ratio, 4),
            "enclosure_ok": self.enclosure_ok,
            "path_ok": self.path_ok,
            "penetrated": self.penetrated,
            "is_terminal": self.is_terminal,
        }

    def summary(self) -> str:
        return (
            f"winding={self.winding} enclosure={sorted(self.enclosure)} goal={sorted(self.goal)} "
            f"top_crossed={self.top_crossed} min_gap_mm={ {k: round(v * 1000, 1) for k, v in self.min_gap.items()} } "
            f"length_ratio={self.length_ratio:.3f} terminal={self.is_terminal}"
        )


class RingTransferEvaluator:
    def __init__(self, *, posts: dict, goal, required_crossings, thresholds: RingTransferThresholds) -> None:
        self.posts = posts
        self.goal = frozenset(goal)
        self.required_crossings = frozenset(required_crossings)
        self.thresholds = thresholds

    @classmethod
    def from_layout(cls, layout, task_cfg) -> "RingTransferEvaluator":
        return cls(
            posts=layout.posts,
            goal=[str(name) for name in task_cfg.goal.enclosure],
            required_crossings=[name for name, _ in layout.crossings()],
            thresholds=RingTransferThresholds.from_config(task_cfg.success),
        )

    def classify(self, nodes: np.ndarray, members, *, spawn_perimeter: float, watch: RingTransferWatch | None) -> RingTransferState:
        line = loop_centerline(nodes, members)
        winding, raw, integral = winding_signature(line, self.posts, tolerance=self.thresholds.winding_tolerance)
        steps = np.linalg.norm(np.roll(line, -1, axis=0) - line, axis=1)
        return RingTransferState(
            winding={k: abs(v) for k, v in winding.items()},
            raw_winding=raw,
            integral=integral,
            enclosure=enclosure_of(winding),
            goal=self.goal,
            required_crossings=self.required_crossings,
            top_crossed=dict(watch.top_crossed) if watch is not None else {},
            min_gap=dict(watch.min_gap) if watch is not None else {},
            length_ratio=float(steps.sum() / spawn_perimeter),
            min_surface_gap=self.thresholds.min_surface_gap,
        )


__all__ += [
    "RingTransferEvaluator",
    "RingTransferState",
    "RingTransferThresholds",
    "RingTransferWatch",
]
