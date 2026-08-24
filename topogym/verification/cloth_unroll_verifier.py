"""Did the roll actually get paid out? (docx 1.3)

docx 1.3 names three criteria: 无自重叠区域 + 端到端距离 ≈ 材料长度 + 累计转角低于
阈值. **Two of them gate here, and the third cannot be built.**

The first two are the same arithmetic `cloth_unpleat` already runs, because the
end state is the same event -- one layer, flat, all the material given back -- so
this module imports them rather than restating them. What is new is the fixture:
the band is wound on a bar, and both new readings are about that bar.

**The cumulative turn angle is not available.** It needs the material points
sorted along the band's length, and Genesis' remesh does not preserve vertex
order -- measured 2026-08-23 on this mesh family: a 595-vertex control mesh came
back as 2283 particles with a 198 mm maximum offset. Without an order there is no
"along the band". The criterion is not silently dropped; it is replaced by two
readings that catch what it was there to catch, both recorded rather than gated
until there are measured runs to place a threshold from:

- **out-of-plane thickness**, the third singular value of the particle cloud.
  A band lying flat is about one cloth thickness deep; half a turn left in it
  stands a ridge up and this reading rises. That is the residual-twist half of
  the criterion.
- **wound particles**, how many are still within a couple of particles of the
  bar's axis. A fully paid-out band leaves none. That is the "still rolled" half,
  and it is also the reading that separates this scene's own failure -- the roll
  torn off the bar -- from a roll that simply did not turn.

Recorded but not gated alongside them: stretch, flatness, and the layer
histogram.

**`band_shift` is deliberately absent**, and it is worth saying so because 1.2
gates its calibration on it. That reading measures the far end of the band -- the
stretch of cloth no correct motion moves, because table friction holds it while
the fold in front of it is opened. This scene has no such stretch: the anchor is
the bar, not the cloth, and a correct unroll moves every particle, the inner end
most of all as it comes off the bar and onto the table. Reporting it here would
say a perfect unroll slid 150 mm. What it was there to catch -- the band towed
whole instead of paid out -- is `on_bar` plus the layer gate: a towed band is
still a roll, so it keeps its layers and leaves the bar together.

Everything here is plain NumPy over ``(P, 3)`` particle arrays. Genesis is never
imported, so `tests/check_cloth_unroll_geometry.py` can feed it synthetic cloth
and check the criteria separate a real unroll from the wrong ones without a GPU.

`to_info()` marks ``"topological": false`` so downstream statistics never pool
these readings with the integer invariants of C2/C3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.verification.cloth_fold_verifier import (
    layer_report,
    occupied_cells,
    stretch_report,
)
from topogym.verification.cloth_unpleat_verifier import (
    peak_height,
    rect_grid_neighbours,
    simulated_grid_shape,
    single_layer_fraction,
    spread_span,
)


def bar_distance(nodes, *, bar_centre, bar_height: float, material_axis: int) -> np.ndarray:
    """Each particle's distance from the bar's AXIS, in the plane across it.

    Distance to the axis rather than to the bar's centre point: the bar is a line,
    and material that has slid along it is no less wound than material that has
    not. Which is also why this drops the along-bar coordinate entirely.
    """

    nodes = np.asarray(nodes, dtype=float)
    axis = int(material_axis)
    offset = np.stack(
        [nodes[:, axis] - float(np.asarray(bar_centre, dtype=float)[axis]),
         nodes[:, 2] - float(bar_height)],
        axis=1,
    )
    return np.linalg.norm(offset, axis=1)


def wound_particles(nodes, *, bar_centre, bar_height: float, material_axis: int, reach: float) -> int:
    """How many particles are still wrapped on the bar, within ``reach`` of its axis.

    Zero for a band that has been paid out, and zero as well for one that was
    torn off the bar entirely -- those two are told apart by the other readings
    (a torn-off band keeps its layers and its short span), not by this one alone.
    """

    return int(
        np.count_nonzero(
            bar_distance(
                nodes, bar_centre=bar_centre, bar_height=bar_height, material_axis=material_axis
            )
            <= float(reach)
        )
    )


def out_of_plane_thickness(nodes) -> float:
    """How thick the particle cloud is perpendicular to its own best-fit plane.

    The third singular value of the centred cloud, scaled back out of the SVD's
    normalisation so it reads in metres: for a flat band this is about one cloth
    thickness, and it grows with anything standing up out of the plane -- a
    remaining curl, a ridge, a fold left behind.

    Stands in for docx 1.3's 累计转角, which cannot be computed here (see the
    module docstring). It is strictly weaker: it cannot tell a half turn from a
    fold. That is why it is recorded rather than gated.
    """

    nodes = np.asarray(nodes, dtype=float)
    if len(nodes) < 3:
        return 0.0
    centred = nodes - nodes.mean(axis=0)
    singular = np.linalg.svd(centred, compute_uv=False)
    return float(singular[2] / np.sqrt(len(nodes)))


@dataclass(frozen=True)
class ClothUnrollThresholds:
    """What counts as unrolled: two gates joined by AND, plus optional slots.

    ``single_layer_frac_min``  the covered area is one layer deep. The structural
                               reading, and the direct form of docx's 无自重叠区域.
    ``recovered_frac_min``     the material the roll held has been given back, as
                               a share of what it held. The morphological one, and
                               the direct form of 端到端距离 ≈ 材料长度.

    A conjunction of one of each kind is what the category contract requires
    (C1, `task_taxonomy_zh.md` 4.1), and a single length threshold is what it
    forbids -- a band towed off the bar without turning recovers length without
    recovering layers.

    Everything below ships as ``null``. The optional slots exist so any of them
    can be switched on from config once there are measured runs to place them
    from; ``on_bar_max`` is the one most likely to be promoted, since it is the
    only reading that distinguishes this scene's own failure mode.
    """

    single_layer_frac_min: float
    recovered_frac_min: float
    out_of_plane_max: float | None = None
    on_bar_max: int | None = None
    stretch_max: float | None = None
    flatness_var_max: float | None = None

    @classmethod
    def from_config(cls, success_cfg) -> "ClothUnrollThresholds":
        def opt(name):
            value = success_cfg.get(name, None) if hasattr(success_cfg, "get") else None
            return None if value is None else float(value)

        on_bar = success_cfg.get("on_bar_max", None) if hasattr(success_cfg, "get") else None
        return cls(
            single_layer_frac_min=float(success_cfg["single_layer_frac_min"]),
            recovered_frac_min=float(success_cfg["recovered_frac_min"]),
            out_of_plane_max=opt("out_of_plane_max"),
            on_bar_max=None if on_bar is None else int(on_bar),
            stretch_max=opt("stretch_max"),
            flatness_var_max=opt("flatness_var_max"),
        )


@dataclass(frozen=True)
class ClothUnrollState:
    """The two gated readings plus everything recorded for diagnosis."""

    single_layer_frac: float
    recovered_frac: float
    spread_ratio: float
    spread_span: float
    peak_above_table: float
    out_of_plane: float
    on_bar: int
    flatness_var: float
    # Recorded for diagnosis; no gate depends on them.
    covered_cells: int
    two_layer_cells: int
    over_layer_cells: int
    max_layers: int
    stretch_mean: float
    stretch_max: float
    stretch_frac_over: float
    thresholds: ClothUnrollThresholds

    @property
    def gates(self) -> dict[str, bool]:
        """Each gate on its own, so a failure says which one."""

        limits = self.thresholds
        passed = {
            "single_layer_frac": self.single_layer_frac >= limits.single_layer_frac_min,
            "recovered_frac": self.recovered_frac >= limits.recovered_frac_min,
        }
        if limits.on_bar_max is not None:
            passed["on_bar"] = self.on_bar <= limits.on_bar_max
        if limits.out_of_plane_max is not None:
            passed["out_of_plane"] = self.out_of_plane <= limits.out_of_plane_max
        if limits.stretch_max is not None:
            passed["stretch"] = self.stretch_max <= limits.stretch_max
        if limits.flatness_var_max is not None:
            passed["flatness_var"] = self.flatness_var <= limits.flatness_var_max
        return passed

    @property
    def is_terminal(self) -> bool:
        """Conjunction, never a single threshold -- C1 requires it, and a band
        towed off the bar rather than paid out is exactly why: it recovers length
        without recovering layers."""

        values = self.gates.values()
        return bool(values) and all(values)

    def invariant(self) -> dict[str, float]:
        """The C1 invariant: a dict of floats, no integer topology involved."""

        return {
            "single_layer_frac": float(self.single_layer_frac),
            "recovered_frac": float(self.recovered_frac),
            "spread_ratio": float(self.spread_ratio),
            "out_of_plane_m": float(self.out_of_plane),
            "flatness_var": float(self.flatness_var),
        }

    def to_info(self) -> dict[str, Any]:
        return {
            **self.invariant(),
            "spread_span_mm": float(self.spread_span * 1e3),
            "peak_above_table_mm": float(self.peak_above_table * 1e3),
            "out_of_plane_mm": float(self.out_of_plane * 1e3),
            "on_bar": int(self.on_bar),
            "covered_cells": int(self.covered_cells),
            "two_layer_cells": int(self.two_layer_cells),
            "over_layer_cells": int(self.over_layer_cells),
            "max_layers": int(self.max_layers),
            "stretch_mean": float(self.stretch_mean),
            "stretch_max": float(self.stretch_max),
            "stretch_frac_over": float(self.stretch_frac_over),
            "gates": {k: bool(v) for k, v in self.gates.items()},
            "terminal": bool(self.is_terminal),
            # C1 has no integer topological invariant; saying so explicitly keeps
            # downstream statistics from pooling it with C2/C3 readings.
            "topological": False,
        }

    def summary(self) -> str:
        return (
            f"single_layer_frac={self.single_layer_frac:.3f} "
            f"recovered_frac={self.recovered_frac:.3f} "
            f"spread_ratio={self.spread_ratio:.3f} "
            f"spread_mm={self.spread_span * 1e3:.1f} "
            f"on_bar={self.on_bar} "
            f"out_of_plane_mm={self.out_of_plane * 1e3:.2f} "
            f"peak_mm={self.peak_above_table * 1e3:.2f} "
            f"covered_cells={self.covered_cells} "
            f"two_layer_cells={self.two_layer_cells} "
            f"over_layer_cells={self.over_layer_cells} "
            f"max_layers={self.max_layers} "
            f"flatness_var={self.flatness_var:.3e} "
            f"stretch_mean={self.stretch_mean:.3f} "
            f"stretch_max={self.stretch_max:.3f} "
            f"stretch_frac_over={self.stretch_frac_over:.3f} "
            f"gates={','.join(k for k, v in self.gates.items() if not v) or 'all_pass'} "
            f"terminal={self.is_terminal}"
        )


@dataclass(frozen=True)
class ClothUnrollEvaluator:
    """Success = the roll is gone and the material is back, per docx 1.3.

    Takes particle arrays rather than a scene so the same evaluator serves the
    task, the demo and the offline check.
    """

    thresholds: ClothUnrollThresholds
    cell: float
    particle_size: float
    material_length: float
    #: How close to the bar's axis still counts as wound. Bar radius plus two
    #: particles: wide enough that a turn resting ON the bar is inside it,
    #: narrow enough that the second turn is not.
    on_bar_reach: float
    #: World axis the band's length runs along, 0 for x and 1 for y. Spread,
    #: shift and the bar's own offset are all statements about that axis, so the
    #: judge has to be told which one rather than assuming the band has not been
    #: turned. Read from the same config key the layout reads.
    material_axis: int = 1

    @classmethod
    def from_config(cls, task_cfg) -> "ClothUnrollEvaluator":
        axis = str(task_cfg["cloth"]["material_axis"]).lower()
        if axis not in ("x", "y"):
            raise ValueError(f"cloth.material_axis must be 'x' or 'y', got {axis!r}.")
        particle = float(task_cfg["cloth"]["particle_size"])
        return cls(
            thresholds=ClothUnrollThresholds.from_config(task_cfg["success"]),
            cell=float(task_cfg["success"]["cell"]),
            particle_size=particle,
            material_length=float(task_cfg["cloth"]["material_length"]),
            on_bar_reach=float(task_cfg["dispenser"]["bar_radius"]) + 2.0 * particle,
            material_axis=0 if axis == "x" else 1,
        )

    def classify(
        self, rest_nodes, nodes, *, table_z: float, bar_centre, bar_height: float, grid=None
    ) -> ClothUnrollState:
        """Judge one end state.

        ``bar_centre`` is the bar axis' world ``(x, y)`` and ``bar_height`` its
        world z -- both taken from the layout rather than rebuilt from config,
        because only the layout knows where the task origin sits. ``grid`` is
        ``(cols, rows)`` of the control mesh and is optional: the stretch report
        is diagnostic, and when the remesh has changed the particle count away
        from a clean subdivision the honest reading is NaN rather than a search
        that would pair up material folded against itself.
        """

        nodes = np.asarray(nodes, dtype=float)
        rest_nodes = np.asarray(rest_nodes, dtype=float)
        layers = layer_report(nodes, float(table_z), self.cell, self.particle_size)
        span = spread_span(nodes, self.material_axis)
        # How much of what the roll was holding at the START has come back. The
        # denominator is the band's own stored material, measured on the rest
        # state rather than taken from the config, so a roll that relaxed a
        # little before the arm arrived is not credited to the arm.
        rest_span = spread_span(rest_nodes, self.material_axis)
        stored = max(self.material_length - rest_span, 1e-9)
        heights = nodes[:, 2] - float(table_z)

        shape = None if grid is None else simulated_grid_shape(len(rest_nodes), grid)
        stretch = {"mean": float("nan"), "max": float("nan"), "frac_over": float("nan")}
        if shape is not None:
            stretch = stretch_report(rest_nodes, nodes, rect_grid_neighbours(*shape))

        return ClothUnrollState(
            single_layer_frac=single_layer_fraction(layers),
            recovered_frac=(span - rest_span) / stored,
            spread_ratio=span / max(self.material_length, 1e-9),
            spread_span=span,
            peak_above_table=peak_height(nodes, table_z),
            out_of_plane=out_of_plane_thickness(nodes),
            on_bar=wound_particles(
                nodes,
                bar_centre=bar_centre,
                bar_height=bar_height,
                material_axis=self.material_axis,
                reach=self.on_bar_reach,
            ),
            flatness_var=float(np.var(heights)),
            covered_cells=int(layers["covered_cells"]),
            two_layer_cells=int(layers["two_layer_cells"]),
            over_layer_cells=int(layers["over_layer_cells"]),
            max_layers=int(layers["max_layers"]),
            stretch_mean=float(stretch["mean"]),
            stretch_max=float(stretch["max"]),
            stretch_frac_over=float(stretch["frac_over"]),
            thresholds=self.thresholds,
        )

    def covered(self, nodes) -> int:
        return len(occupied_cells(nodes, self.cell))
