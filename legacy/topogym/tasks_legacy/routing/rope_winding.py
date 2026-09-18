"""Rope Winding (task book 2.4): wind a rope N turns around a post, then place it.

The scene is a Cable Routing scene with a different fixture set: same asset
family (routing post, fixed terminal, industrial plug, flush ports), same rope
backend seam (anchor band at the terminal, follow band at the plug), same layout
and route readers. So the builder subclasses Cable Routing's rather than copying
it -- what makes this a different task is not how the scene is assembled but

- the oracle: one helix around a single post instead of a hand-authored
  multi-peg route (`topogym/planning/rope_winding_planner.py`), and
- the criterion: a signed winding number instead of a side-of-peg signature
  (`topogym/supervision/rope_winding.py`, which also owns the `task.winding`
  reading both of those share).

Variation (2026-09-05, variation plan section 6.2 step 6): the task yaml's
``variation:`` block draws the turn count, the instructed sense, the three
fixture positions and the climb, plus a unit fraction each for the lowest
wrap's height and the target's x; `derive_task_cfg` maps those onto the
windows the drawn geometry allows and then solves the spawn arc's sweep so
the rope's slack sits mid-band whatever the turn count and positions are.
The plug's spawn point is a rule of the post and the anchor
(`routes.initial`), not a leaf. The feasibility rows live in
`_rope_winding_geometry.py` (numpy only, shared with the offline gate).
"""

from __future__ import annotations

from dataclasses import dataclass

from ._rope_winding_geometry import (
    rope_winding_checks,
    sweep_from_slack,
    target_x_from_frac,
    target_y_from_frac,
)
from ._winding_post_geometry import wind_z_from_frac
from .cable_routing import (
    CableRoutingLayout,
    CableRoutingScene,
    CableRoutingSceneBuilder,
)


@dataclass(frozen=True)
class RopeWindingLayout(CableRoutingLayout):
    """Cable Routing's layout plus the task's feasibility rows."""

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a spawnable, solvable layout needs.

        One list for the randomizer's reject step, the offline gate, the corner
        harness and the demo's start-up print. Metres throughout.
        """

        return rope_winding_checks(self)

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"rope_winding layout check {name} failed: "
                    f"measured {measured:+.4f} against {limit:+.4f}."
                )


RopeWindingScene = CableRoutingScene


class RopeWindingSceneBuilder(CableRoutingSceneBuilder):
    """Cable Routing's scene assembly, driven by the rope_winding task config."""

    layout_cls = RopeWindingLayout

    def build(self, *, show_viewer: bool = False, include_robot: bool = True):
        _assert_literal_copies(self.task_cfg)
        self.layout.validate()
        return super().build(show_viewer=show_viewer, include_robot=include_robot)


def _assert_literal_copies(task_cfg) -> None:
    """The yaml's literal copies of prefab / common values must still match them.

    `checks()` reads `rope.radius`, `POST.base_height` and `workspace`, and the
    variation harness loads the task yaml alone, where `${prefabs...}` and
    `${common...}` cannot resolve -- so the task yaml carries literals, and the
    one place with both in hand asserts they agree.
    """

    root = task_cfg._get_root() if hasattr(task_cfg, "_get_root") else None
    prefabs = getattr(root, "prefabs", None) if root is not None else None
    common = getattr(root, "common", None) if root is not None else None
    if prefabs is not None:
        want = float(prefabs.rope_pbd.radius)
        got = float(task_cfg.rope.radius)
        if abs(want - got) > 1e-9:
            raise ValueError(f"rope_winding: rope.radius {got} != prefabs.rope_pbd.radius {want}")
        want = float(prefabs.rope_routing_post.base_height)
        got = float(task_cfg.fixtures.POST.base_height)
        if abs(want - got) > 1e-9:
            raise ValueError(
                f"rope_winding: POST.base_height {got} != prefabs.rope_routing_post.base_height {want}"
            )
    if common is not None:
        ws = common.manipulation_space.workspace
        for axis in ("x", "y"):
            want = [float(v) for v in ws[axis]]
            got = [float(v) for v in task_cfg.workspace[axis]]
            if want != got:
                raise ValueError(
                    f"rope_winding: workspace.{axis} {got} != manipulation_space.workspace.{axis} {want}"
                )


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``. Order
    matters: the lowest wrap's height (needs the drawn turn count and climb),
    then the target's y and x (need the plug's spawn point and the wrap's
    exit: C goes where the plug keeps clear of it and the straight run to it
    closes on the target winding), then the spawn arc's sweep (needs the target: the
    rope is tightest with the plug held over C). A ``ValueError`` (empty
    window) rejects the draw.
    """

    task_cfg.winding.wind_z_start = wind_z_from_frac(task_cfg, float(task_cfg.winding.wind_z_frac))
    task_cfg.fixtures.C.y = target_y_from_frac(RopeWindingLayout(task_cfg), float(task_cfg.fixtures.C.y_frac))
    task_cfg.fixtures.C.x = target_x_from_frac(RopeWindingLayout(task_cfg), float(task_cfg.fixtures.C.x_frac))
    task_cfg.rope.spawn_arc.sweep_deg = sweep_from_slack(RopeWindingLayout(task_cfg))


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled.
    """

    RopeWindingLayout(task_cfg).validate()


#: How each ``winding.direction`` token is named in the instruction sentence.
#: The yaml tokens are what the demo used to print verbatim; a policy reading
#: "wind it ccw" gets a word from no natural language.
DIRECTION_WORDS = {"ccw": "counter-clockwise", "cw": "clockwise"}

#: How each turn count is named. The noun rides along with the numeral so the
#: sentence agrees in number -- "one turn", not "1 turns".
TURN_WORDS = {1: "one turn", 2: "two turns", 3: "three turns"}


def render_instruction(task_cfg) -> str:
    """Instruction hook named by the task yaml's ``goal.instruction_fn``.

    Serves both rope_winding and rope_unwinding: the two share this module and
    differ in which turn count the sentence should name. Winding counts the
    turns to make (``winding.turns``, with ``start_turns`` absent or 0);
    unwinding counts the turns already on the post (``winding.start_turns``,
    with ``turns`` 0). The same branch the demo used before this moved into the
    config: whichever count is larger is the one the sentence is about.

    Only rope_winding *needs* the sentence -- there the post and rope look
    identical under either direction, so the picture cannot say which way to go.
    For rope_unwinding the direction is visible (``cw`` mirrors the whole layout
    and the rope spawns already wound), so naming it is harmless but is not
    what makes the episode solvable.
    """

    winding = task_cfg.winding
    turns = max(int(getattr(winding, "turns", 0) or 0), int(getattr(winding, "start_turns", 0) or 0))
    direction = str(winding.direction).lower()
    for value, table, leaf in ((direction, DIRECTION_WORDS, "direction"), (turns, TURN_WORDS, "turns")):
        if value not in table:
            raise ValueError(
                f"winding.{leaf}={value!r} has no phrase in this module's word table; "
                "the sentence the policy reads is built from it, so that value would "
                "be commanded but never stated."
            )
    return str(task_cfg.goal.instruction).format(
        turns=TURN_WORDS[turns], direction=DIRECTION_WORDS[direction]
    )


__all__ = [
    "DIRECTION_WORDS",
    "TURN_WORDS",
    "RopeWindingLayout",
    "render_instruction",
    "RopeWindingScene",
    "RopeWindingSceneBuilder",
    "derive_task_cfg",
    "validate_task_cfg",
]
