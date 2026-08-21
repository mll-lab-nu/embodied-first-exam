"""Did the beam actually join the two frames? (docx 4.4)

The invariant is `component_count`, and it is defined on the scene's CONSTRAINT
GRAPH, not on anybody's free space -- `docs/develop/framework/task_taxonomy_zh.md`
section 4.4 requires C4 tasks to say which, because 4.1 and 4.3 answer the same
question about a ball's `c_free` and the two are not interchangeable. Here the
nodes are the three rigid assemblies and the edges are the things that hold them
together:

    component_a --[hinge]-- linkbar          always present, the beam is bolted to A
    linkbar --[latch]-- component_b          the merging edge:  2 -> 1
    linkbar --[latch]-- component_a          a cycle edge:      2 -> 2

That is the whole task in three lines. A latch into A2 is a real constraint that
really fires and really holds the beam -- it just joins two nodes that were
already one component, so it changes nothing about how many components there are.
Nothing here inspects the socket's name to decide: the edge is read back from the
solver with `get_weld_constraints` and run through union-find, so an A2 latch fails
for the reason it should rather than because it was labelled the wrong answer.

Two layers, as the C4 contract requires, recorded separately:

- **Constraint graph** -- `component_count`, computed here from the live weld set.
- **Travel test** -- measured by the caller with
  `tasks/connectivity/_travel_probe.py`, because only the caller can step physics.
  Component B is a carriage on a radial rail, so "merged" has a direct physical
  reading: it can no longer travel. At the seat the beam lies along the rail and
  takes the load as a straight push or pull, so the lock is stiff rather than
  incidental.

The rail is not an edge in the graph. It ties the carriage to the table, and the
table is not one of the three assemblies -- the same status as A's own bolts. What
the graph counts is constraints BETWEEN assemblies; what the travel test measures
is whether B still has freedom relative to A. The two answer the same question
from opposite ends, which is why they are worth recording separately.

`judge_disagrees` is the cross-check. The graph saying "merged" while the carriage
travels anyway does not mean the run failed -- it means this judge is wrong, and
the weld or the link mapping is what needs looking at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from topogym.tasks.connectivity.linkbar_merge_components import LINKBAR_SOCKETS

INVARIANT_NAME = "component_count"

# The three rigid assemblies the invariant counts. Everything else in the scene
# (table, robot, the arc markers) is scenery and is not a node.
NODES = ("component_a", "linkbar", "component_b")

# The hinge. It is a structural fact of the scene rather than something an episode
# can change, so it is written here instead of being read back each time.
FIXED_EDGES = (("component_a", "linkbar"),)


def _components(nodes, edges) -> int:
    """Union-find over a handful of nodes."""

    parent = {node: node for node in nodes}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for first, second in edges:
        root_a, root_b = find(first), find(second)
        if root_a != root_b:
            parent[root_a] = root_b
    return len({find(node) for node in nodes})


def link_nodes(merge_scene) -> dict[int, str]:
    """Global link index -> which assembly that link belongs to.

    Only links that can carry a latch are listed. A weld touching anything else is
    not part of this graph and is ignored rather than guessed at.
    """

    mapping = {int(merge_scene.beam_link_idx()): "linkbar"}
    for socket in LINKBAR_SOCKETS:
        mapping[int(merge_scene.socket_link_idx(socket))] = \
            merge_scene.layout.socket_owner(socket)
    return mapping


@dataclass(frozen=True)
class LinkbarMergeState:
    """One reading: what the constraint graph says, and what the travel test said."""

    component_count: int
    latched_socket: str | None
    latch_edges: tuple[tuple[str, str], ...] = ()
    pin_gaps: dict[str, float] = field(default_factory=dict)
    # Physical layer. Supplied by the caller, because only it can step physics.
    travel: float = 0.0
    travel_tested: bool = False
    max_travel: float = 0.0
    min_free_travel: float = 0.0
    # The primitive's own gates (target error, follow error, release drift). A run
    # the arm botched is not evidence about the scene either way.
    rotate_ok: bool = True

    @property
    def invariant_value(self) -> int:
        return int(self.component_count)

    @property
    def merged(self) -> bool:
        """The constraint-graph reading on its own."""

        return bool(self.component_count == 1)

    @property
    def motion_blocked(self) -> bool:
        return bool(self.travel_tested and self.travel <= self.max_travel)

    @property
    def geometry_ok(self) -> bool:
        return self.merged

    @property
    def judge_disagrees(self) -> bool:
        """Graph says merged, carriage travelled anyway -> the judge is wrong, not the run."""

        return bool(self.merged and self.travel_tested and not self.motion_blocked)

    @property
    def probe_uninformative(self) -> bool:
        """An unmerged carriage that did NOT run means the push was too weak to judge.

        Reported rather than folded into success: it says the probe is broken, and
        a probe that cannot move a free carriage would call every run a merge.
        """

        return bool(
            self.travel_tested and not self.merged and self.travel < self.min_free_travel
        )

    @property
    def is_terminal(self) -> bool:
        return bool(self.merged and self.motion_blocked and self.rotate_ok)

    @property
    def failure_label(self) -> str | None:
        if self.is_terminal:
            return None
        if not self.rotate_ok:
            return "rotate_check_failed"
        if self.latched_socket is None:
            return "no_latch"
        if not self.merged:
            return "latched_wrong_socket"
        return "travel_test_failed"

    def to_info(self) -> dict[str, Any]:
        return {
            "invariant": INVARIANT_NAME,
            "invariant_value": self.invariant_value,
            "invariant_signed": False,
            # Required by the C4 contract, and the reason 4.4 cannot share 4.1's
            # and 4.3's readings: those count connected regions of a ball's free
            # space, this counts connected assemblies.
            "space": "constraint_graph",
            "subject": "linkbar",
            "gateway": "socket_latch",
            "component_count": int(self.component_count),
            "latched_socket": self.latched_socket,
            "latch_edges": [list(edge) for edge in self.latch_edges],
            "pin_gaps": {name: float(gap) for name, gap in self.pin_gaps.items()},
            "travel_tested": bool(self.travel_tested),
            "travel": float(self.travel),
            "motion_blocked": bool(self.motion_blocked),
            "rotate_ok": bool(self.rotate_ok),
            "judge_disagrees": bool(self.judge_disagrees),
            "probe_uninformative": bool(self.probe_uninformative),
            "failure_label": self.failure_label,
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class LinkbarMergeEvaluator:
    """Success = the two frames became one component, and the carriage really is locked."""

    def latch_edges(self, merge_scene) -> tuple[tuple[str, str], ...]:
        """Weld edges between assemblies, read from the solver."""

        mapping = link_nodes(merge_scene)
        edges = []
        for first, second in sorted(merge_scene.weld_pairs()):
            node_a, node_b = mapping.get(first), mapping.get(second)
            if node_a is None or node_b is None:
                continue
            edges.append((node_a, node_b))
        return tuple(edges)

    def classify(self, merge_scene, *, travel: float | None = None,
                 rotate_ok: bool = True) -> LinkbarMergeState:
        layout = merge_scene.layout
        edges = self.latch_edges(merge_scene)
        pin_xy = merge_scene.pin_xy()
        # Measured seats, not the ones the layout would derive: component B can be
        # nudged, and a gap quoted against where it used to be is not a reading.
        gaps = {
            name: float(((pin_xy - merge_scene.socket_seat_xy(name)) ** 2).sum() ** 0.5)
            for name in LINKBAR_SOCKETS
        }
        return LinkbarMergeState(
            component_count=_components(NODES, tuple(FIXED_EDGES) + edges),
            latched_socket=merge_scene.latched_socket(),
            latch_edges=edges,
            pin_gaps=gaps,
            travel=0.0 if travel is None else float(travel),
            travel_tested=travel is not None,
            max_travel=layout.max_travel,
            min_free_travel=layout.min_free_travel,
            rotate_ok=bool(rotate_ok),
        )

    def is_success(self, merge_scene, **kwargs) -> bool:
        return self.classify(merge_scene, **kwargs).is_terminal
