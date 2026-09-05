"""Rope Unwinding (task book 2.5): take a rope that is wound on a post off it.

The mirror of Rope Winding, and built the same way: a Cable Routing scene with
the winding fixture set, so the builder subclasses Cable Routing's. What makes
it a different task is

- the initial state: the rope spawns ALREADY WOUND `winding.start_turns` times
  around the post (the `helix_around` entry of `routes.initial`), its anchor end
  pinned at the terminal and its plug lying on the board;
- the oracle: the same planner as rope_winding, orbiting the other way and
  descending from the top wrap (`winding.turns: 0` with `start_turns > 0`,
  `topogym/planning/rope_winding_planner.py`);
- the criterion: the same signed winding number, with target 0
  (`topogym/supervision/rope_winding.py`).

Variation (2026-09-04): the task yaml's ``variation:`` block draws the turn
count, the wrap sense, the three fixture positions and the climb, and a unit
fraction for the lowest wrap's height that `derive_task_cfg` maps onto the
window the drawn turns and climb leave under the post top. The spawn route's
lead-in and plug point are rules of the layout (`routes.initial`), not leaves.
The feasibility rows live in `_rope_unwinding_geometry.py` (numpy only, so
the offline gate reads the same rows without Genesis).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ._rope_unwinding_geometry import (
    fixture_task_pos,
    rope_unwinding_checks,
    target_x_from_frac,
    wind_z_from_frac,
)
from .cable_routing import (
    CableRoutingLayout,
    CableRoutingScene,
    CableRoutingSceneBuilder,
)


@dataclass(frozen=True)
class RopeUnwindingLayout(CableRoutingLayout):
    """Cable Routing's layout plus the task's feasibility rows.

    `winding.direction: cw` is the mirror layout: the yaml's fixture positions
    are the ccw instance's, and `fixture_pos` reflects them in y for cw
    (`_rope_unwinding_geometry.mirror_sign`). Everything downstream -- the
    spawn route, the planner, the winding metrics, the scene -- reads
    positions through here, so the whole scene mirrors together.
    """

    def fixture_pos(self, name: str, *, z: float | None = None) -> np.ndarray:
        pos = fixture_task_pos(self.cfg, name)
        if z is not None:
            pos[2] = float(z)
        return self.position_to_world(pos)

    def checks(self) -> list[tuple[str, float, float, bool]]:
        """``[(name, measured, limit, ok)]``: what a spawnable, solvable layout needs.

        One list for the randomizer's reject step, the offline gate, the corner
        harness and the demo's start-up print. Metres throughout.
        """

        return rope_unwinding_checks(self)

    def validate(self) -> None:
        """Refuse a layout that fails any check, instead of building it anyway."""

        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"rope_unwinding layout check {name} failed: "
                    f"measured {measured:+.4f} against {limit:+.4f}."
                )


RopeUnwindingScene = CableRoutingScene


class RopeUnwindingSceneBuilder(CableRoutingSceneBuilder):
    """Cable Routing's scene assembly, driven by the rope_unwinding task config."""

    layout_cls = RopeUnwindingLayout

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
            raise ValueError(f"rope_unwinding: rope.radius {got} != prefabs.rope_pbd.radius {want}")
        want = float(prefabs.rope_routing_post.base_height)
        got = float(task_cfg.fixtures.POST.base_height)
        if abs(want - got) > 1e-9:
            raise ValueError(
                f"rope_unwinding: POST.base_height {got} != prefabs.rope_routing_post.base_height {want}"
            )
    if common is not None:
        ws = common.manipulation_space.workspace
        for axis in ("x", "y"):
            want = [float(v) for v in ws[axis]]
            got = [float(v) for v in task_cfg.workspace[axis]]
            if want != got:
                raise ValueError(
                    f"rope_unwinding: workspace.{axis} {got} != manipulation_space.workspace.{axis} {want}"
                )


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Runs after the axes are drawn and before ``validate_task_cfg``. Order
    matters: the lowest wrap's height (needs the drawn turn count and climb),
    then the target's x (needs the plug's spawn point, which the layout builds
    from the post, the anchor, the turn count and the sense). A ``ValueError``
    (empty window) rejects the draw.
    """

    task_cfg.winding.wind_z_start = wind_z_from_frac(task_cfg, float(task_cfg.winding.wind_z_frac))
    layout = RopeUnwindingLayout(task_cfg)
    task_cfg.fixtures.C.x = target_x_from_frac(layout, float(task_cfg.fixtures.C.x_frac))


def validate_task_cfg(task_cfg) -> None:
    """Validation hook named by the task yaml's ``variation:`` block.

    `layout_randomization.randomize_task_cfg` calls it after each draw; a
    ``ValueError`` rejects the draw and the whole set of axes is resampled.
    """

    RopeUnwindingLayout(task_cfg).validate()


__all__ = [
    "RopeUnwindingLayout",
    "RopeUnwindingScene",
    "RopeUnwindingSceneBuilder",
    "derive_task_cfg",
    "validate_task_cfg",
]
