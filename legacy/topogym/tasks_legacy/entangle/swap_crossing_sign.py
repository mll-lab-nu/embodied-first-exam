"""docx 3.2 -- make the other rope lie on top at every crossing.

Scene: 2 or 3 ropes grow out of a power strip, each first runs an S bend, then
swaps lanes with a neighbour 1 or 2 times at sampled positions, then a straight
tail carries it to a flat plug. The robot only grasps plugs. The episode
succeeds when every crossing the spawn had is still there -- same two ropes, in
the same order along each rope -- with the other rope on top (judged on the end
state only: `verification/swap_crossing_sign_verifier.py`).

History. Until 2026-09-10 this module was an alias of `untangle_continuous`'s
classes: the frozen untangle scene is already two ropes crossing once, and only
the goal differed. The rework (plan `valiant-soaring-pretzel`, decisions of
2026-09-10/11) made the configs diverge -- rope count and crossing count are
axes, crossings sit at sampled positions with sampled windows, the lead-in
bends -- so the layout is a subclass now. The builder, meshing, anchoring and
settling are untangle's, unchanged; untangle_continuous still builds with its own
layout and its own frozen check rows (`_swap_crossing_sign_geometry.braid_checks`).

Why the task needs more than two moves, and why the oracle is a search: see
`planning/swap_crossing_sign_sequence.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from topogym.generation.braid import BraidLayout

from . import _swap_crossed_pair_scene as crossed_pair_scene
from . import _swap_crossing_sign_scene as swap_scene
from .untangle_continuous import (
    UntangleContinuousLayout,
    UntangleContinuousScene as SwapCrossingSignScene,
    UntangleContinuousSceneBuilder,
    _list,
    settle_scene,
)


@dataclass(frozen=True)
class SwapCrossingSignLayout(UntangleContinuousLayout):
    """Rope geometry from swap's scalar leaves (see the task yaml's ``braid:`` block)."""

    @property
    def length(self) -> int:
        return int(self.cfg.braid.length)

    @property
    def word(self) -> tuple[int, ...]:
        return swap_scene.braid_word(self.n_strands, self.length, int(getattr(self.cfg.braid, "word_index", 0)))

    def crossing_fractions(self) -> tuple[float, ...]:
        braid_cfg = self.cfg.braid
        if self.length == 1:
            return (float(braid_cfg.crossing_frac),)
        return (float(braid_cfg.crossing_frac), float(braid_cfg.crossing_frac_2))

    def bows(self) -> list[float]:
        braid_cfg = self.cfg.braid
        unit = [float(getattr(braid_cfg, f"bow_u_{k}", 0.0)) for k in range(self.n_strands)]
        return swap_scene.bow_amplitudes(unit, spacing=float(braid_cfg.channel_spacing))

    @property
    def crossed_pair(self) -> bool:
        """Is this the three-rope two-crossing cell, which is built the other way?

        That cell's two crossings sit on different pairs, made by two ropes lying
        across a third (`_swap_crossed_pair_scene.py`), because the lane-swap
        construction puts both crossings on one rope's middle and then needs two
        consecutive precise lays to flip them -- five GPU episodes failed that way
        on 2026-09-11/12. The one-crossing cells keep the lane-swap construction.
        """

        return self.n_strands == 3 and self.length == 2

    def crossed_pair_leaves(self) -> dict:
        """The ``crossed_pair:`` block as a plain dict, with the plug x the axis drew."""

        cfg = self.cfg.crossed_pair
        leaves = {key: float(cfg[key]) for key in cfg}
        leaves["x_end"] = float(self.cfg.braid.x_end)
        return leaves

    def braid_layout(self) -> BraidLayout:
        return self.braid_spec().layout

    def braid_spec(self):
        """Deterministic in the leaves alone (no seed stream: the leaves are the variant)."""

        if self.crossed_pair:
            return crossed_pair_scene.spec_from_leaves(self.crossed_pair_leaves())
        return swap_scene.spec_from_leaves(self.cfg.braid)

    def checks(self) -> list[tuple[str, float, float, bool]]:
        spec = self.braid_spec()
        braid_cfg, ws = self.cfg.braid, self.cfg.workspace
        connector = self.cfg.rope.free_end_connector
        strip_size = _list(self.cfg.power_strip.size)
        if self.crossed_pair:
            return crossed_pair_scene.scene_checks(
                spec,
                self.crossed_pair_leaves(),
                min_plug_gap=float(getattr(connector, "min_clearance", 0.07)),
                plug_ahead=0.5 * float(connector.column_height) + float(connector.flange_height) + float(connector.pin_depth),
                flange_radius=float(connector.flange_radius),
                workspace_x=(float(ws.x[0]), float(ws.x[1])),
                workspace_y=(float(ws.y[0]), float(ws.y[1])),
                workspace_margin=float(ws.margin),
                merge_radius=float(self.cfg.success.crossing_merge_radius),
            )
        return swap_scene.scene_checks(
            spec.control_points,
            spec.crossings,
            spec.layout,
            tube_radius=float(braid_cfg.tube_radius),
            min_plug_gap=float(getattr(connector, "min_clearance", 0.07)),
            plug_ahead=0.5 * float(connector.column_height) + float(connector.flange_height) + float(connector.pin_depth),
            flange_radius=float(connector.flange_radius),
            strip_half_length=0.5 * float(strip_size[1]),
            workspace_x=(float(ws.x[0]), float(ws.x[1])),
            workspace_y=(float(ws.y[0]), float(ws.y[1])),
            workspace_margin=float(ws.margin),
            merge_radius=float(self.cfg.success.crossing_merge_radius),
        )

    def validate(self) -> None:
        for name, measured, limit, ok in self.checks():
            if not ok:
                raise ValueError(
                    f"swap_crossing_sign layout check {name} failed: measured {measured:+.4f} against {limit:+.4f}."
                )

    @cached_property
    def spawn_plan(self):
        """The offline sequence planner's plan from the spawn geometry (None if it finds none)."""

        from topogym.planning.swap_crossing_sign_sequence import (
            code_of,
            params_from_config,
            plan_sequence,
            rope_lays,
            target_for,
        )

        spec = self.braid_spec()
        params = params_from_config(self.cfg)
        state = rope_lays({k: swap_scene.densify(v, 0.01) for k, v in spec.control_points.items()})
        return plan_sequence(state, target_for("oracle", code_of(state, params)), params)

    def predicted_lift(self) -> float:
        plan = self.spawn_plan
        return float("nan") if plan is None else float(plan.max_hand_height)


class SwapCrossingSignSceneBuilder(UntangleContinuousSceneBuilder):
    layout_cls = SwapCrossingSignLayout

    def _table_material(self):
        # ``rope.table_friction`` is the table's coup_friction on both paths. The
        # IPC coupler pairs it with the rope's ``fem.friction_mu`` by geometric mean
        # (genesis ipc_coupler/coupler.py); the shared builder leaves the IPC table
        # at Genesis's default 0.1, so until 2026-09-13 rope-on-table friction was
        # sqrt(0.3 x 0.1) = 0.17 whatever the yaml said. band_untwist measured the
        # yaml's 0.8 (pair 0.49) cutting the rope dragged by a swung tail ~30 %.
        import genesis as gs

        if self._rope_backend.name != "pbd":
            return gs.materials.Rigid(coup_type="ipc_only", coup_friction=float(self.task_cfg.rope.table_friction))
        return gs.materials.Rigid(coup_friction=float(self.task_cfg.rope.table_friction))


def derive_task_cfg(task_cfg) -> None:
    """Derivation hook named by the task yaml's ``variation:`` block.

    Writes the leaves whose range depends on other axes: the crossing positions
    (their bounds move with the crossing count and the lane pitch) and the
    left-right shift (its bound moves with the rope count and the lane pitch, so
    every outlet stays on the power strip). Draws nothing.

    The three-rope two-crossing cell is built the other way (see
    `SwapCrossingSignLayout.crossed_pair`), so its own block is derived too --
    always, so that a config carries a buildable arrangement whichever cell the
    rope-count and crossing-count axes drew.
    """

    strip_half = 0.5 * float(_list(task_cfg.power_strip.size)[1])
    swap_scene.derive_leaves(task_cfg.braid, strip_half_length=strip_half)
    ws = task_cfg.workspace
    leaves = {key: float(task_cfg.crossed_pair[key]) for key in task_cfg.crossed_pair}
    leaves["x_end"] = float(task_cfg.braid.x_end)
    crossed_pair_scene.derive_leaves(
        leaves,
        strip_half_length=strip_half,
        workspace_x=(float(ws.x[0]), float(ws.x[1])),
        workspace_y=(float(ws.y[0]), float(ws.y[1])),
        workspace_margin=float(ws.margin),
    )
    for key, value in leaves.items():
        task_cfg.crossed_pair[key] = float(value)


def validate_task_cfg(task_cfg) -> None:
    """Validation hook: the layout's check rows (a ValueError rejects the draw)."""

    SwapCrossingSignLayout(task_cfg).validate()


__all__ = [
    "SwapCrossingSignLayout",
    "SwapCrossingSignScene",
    "SwapCrossingSignSceneBuilder",
    "derive_task_cfg",
    "settle_scene",
    "validate_task_cfg",
]
