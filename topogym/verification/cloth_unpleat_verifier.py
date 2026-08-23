"""Did the pleat actually get spread out? (docx 1.2)

docx 1.2 names three criteria: 最大高度低于阈值 + 覆盖区域单层 + 总铺展长度 ≈
材料全长. **Two of them gate here, and the third is recorded.**

**Height** is dropped to a diagnostic, and the reason is measured rather than
chosen. docx's third criterion assumes the pleat stands, so that pressing it flat
is a distinct wrong answer that passes on height and fails on the other two.
This cloth cannot stand: Genesis' PBD cloth ignores `bending_compliance`
entirely (1e-1 through 1e-8 gave identical settles, 2026-08-23), so nothing holds
a crease, and the authored pleat lies down inside 25 steps. The starting state
therefore already passes any height threshold that a finished unfold would pass,
and a gate that is satisfied before the episode begins is worse than no gate --
it looks like a criterion and does no work. See the task config for the sweep.

**Single-layer fraction** is the structural reading the category contract asks
for beside a morphological one (C1, `task_taxonomy_zh.md` 4.1). It is also the
only one of the three that does not need particle identities -- a real robot sees
a point cloud, not vertex numbers.

**Spread ratio** is material conservation: the pleat holds a known length of
cloth, and giving it back is the same event as the pleat ceasing to exist. This
is what makes 「压扁」 and 「展开」 strictly separable, which is the property
docx 1.2 asks the judge to have.

Recorded but not gated: how far the whole band slid (the reading that tells an
unfold from a tow), stretch, flatness, and the layer histogram. `band_shift` is
the one to watch -- an over-pulled band passes all three gates and is a different
execution, not a failed one, so it is measured rather than rejected.

Everything here is plain NumPy over ``(P, 3)`` particle arrays. Genesis is never
imported, so `tests/check_cloth_unpleat_geometry.py` can feed it synthetic cloth
and check the criteria separate a good unfold from the wrong ones without a GPU.

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


def peak_height(nodes, table_z: float) -> float:
    """Highest point of the band above the table."""

    return float(np.asarray(nodes, dtype=float)[:, 2].max() - float(table_z))


def spread_span(nodes, axis: int = 1) -> float:
    """How far the band reaches along its own length axis, in metres.

    One axis rather than a bounding box: the band's length direction is the one
    the pleat stores material in, and a band that has been fanned out sideways has
    not given the pleat back. Measuring the axis the material lives on keeps the
    reading tied to the conservation argument rather than to the outline's size.
    """

    values = np.asarray(nodes, dtype=float)[:, int(axis)]
    return float(values.max() - values.min())


def single_layer_fraction(layers: dict) -> float:
    """Share of covered cells carrying exactly one layer.

    Derived from `layer_report`'s counts rather than measured separately, so the
    layer definition (runs separated by more than half a particle) is stated once.
    """

    covered = int(layers["covered_cells"])
    if covered <= 0:
        return 0.0
    stacked = int(layers["two_layer_cells"]) + int(layers["over_layer_cells"])
    return float(covered - stacked) / float(covered)


def band_shift(
    rest_nodes, nodes, *, cols: int | None = None, keep: float = 0.25, axis: int = 1
) -> float:
    """How far the far end of the band travelled, in metres.

    The far end -- the flat run behind the crease -- is the part no correct
    motion moves: table friction holds it while the pleat is opened in front of
    it. A band that was towed instead of unfolded moves it, and moves it by
    roughly the whole drag.

    ``keep`` is the fraction of the band that counts as "the far end", measured
    along the MATERIAL when ``cols`` (the simulated grid's material-direction
    width) is known. Material order is the right axis and plan-view x is not:
    at rest the pleat's two arms hang over the flat run, so selecting by x alone
    picks up the very material the motion is supposed to move and reports a
    correct unfold as a 44 mm slide.

    Without ``cols`` the fallback takes the far end by position along ``axis``
    AND by height together, which separates the same two things whenever the arms
    are still up.

    Not a gate. It is the reading that tells an over-pull from an unfold, and both
    are executions rather than one being a failure, so the judge reports it and
    lets the caller decide.
    """

    rest_nodes = np.asarray(rest_nodes, dtype=float)
    nodes = np.asarray(nodes, dtype=float)
    if len(rest_nodes) != len(nodes):
        raise ValueError(
            f"band_shift compares the same particles before and after, so the "
            f"two arrays must be index-aligned; got {len(rest_nodes)} rest and "
            f"{len(nodes)} current."
        )

    if cols is not None and int(cols) > 1:
        cols = int(cols)
        columns = np.arange(len(rest_nodes)) % cols
        selected = np.flatnonzero(columns < max(1, int(round(float(keep) * cols))))
    else:
        along, zs = rest_nodes[:, int(axis)], rest_nodes[:, 2]
        cutoff = float(along.min()) + float(keep) * float(along.max() - along.min())
        # "On the table" relative to the band's own lowest material, so this does
        # not need to know where the table is.
        floor = float(zs.min()) + 0.5 * float(zs.max() - zs.min())
        selected = np.flatnonzero((along <= cutoff) & (zs <= floor))
    if selected.size == 0:
        return float("nan")
    return float(
        np.linalg.norm(
            nodes[selected].mean(axis=0) - rest_nodes[selected].mean(axis=0)
        )
    )


def rect_grid_neighbours(cols: int, rows: int) -> np.ndarray:
    """Neighbour index pairs for a ``rows x cols`` grid, in ``row * cols + col`` order.

    `cloth_fold_verifier.grid_neighbours` infers a SQUARE side from the particle
    count, which a band is not. Same arithmetic otherwise, and same reason for
    doing it by arithmetic rather than by nearest-neighbour search: a folded band
    puts unrelated material within a particle of itself, so a search answers the
    wrong question.
    """

    cols, rows = int(cols), int(rows)
    if cols < 2 or rows < 2:
        raise ValueError(f"need at least a 2x2 grid, got {cols}x{rows}.")
    index = np.arange(cols * rows).reshape(rows, cols)
    along = np.column_stack([index[:, :-1].ravel(), index[:, 1:].ravel()])
    across = np.column_stack([index[:-1, :].ravel(), index[1:, :].ravel()])
    return np.vstack([along, across])


@dataclass(frozen=True)
class ClothUnpleatThresholds:
    """What counts as unpleated: the three gates docx 1.2 names, joined by AND.

    ``single_layer_frac_min``  the covered area is one layer deep again.
                               The structural reading.
    ``spread_ratio_min``       the material the pleat held has been given back.
                               The morphological one. Together they satisfy the
                               category contract's requirement for a conjunction
                               of the two kinds (C1, `task_taxonomy_zh.md` 4.1).

    ``max_height_m`` is optional and ships as ``null`` -- see the module
    docstring for why. Band shift, stretch and flatness are likewise recorded
    rather than gated; the optional slots let any of them be switched on from
    config once there are measured runs to place them from.
    """

    single_layer_frac_min: float
    spread_ratio_min: float
    max_height_m: float | None = None
    band_shift_max: float | None = None
    stretch_max: float | None = None
    flatness_var_max: float | None = None

    @classmethod
    def from_config(cls, success_cfg) -> "ClothUnpleatThresholds":
        def opt(name):
            value = success_cfg.get(name, None) if hasattr(success_cfg, "get") else None
            return None if value is None else float(value)

        return cls(
            single_layer_frac_min=float(success_cfg["single_layer_frac_min"]),
            spread_ratio_min=float(success_cfg["spread_ratio_min"]),
            max_height_m=opt("max_height_m"),
            band_shift_max=opt("band_shift_max"),
            stretch_max=opt("stretch_max"),
            flatness_var_max=opt("flatness_var_max"),
        )


@dataclass(frozen=True)
class ClothUnpleatState:
    """The three readings plus everything recorded for diagnosis."""

    peak_above_table: float
    single_layer_frac: float
    spread_ratio: float
    spread_span: float
    band_shift: float
    flatness_var: float
    # Recorded for diagnosis; no gate depends on them.
    covered_cells: int
    two_layer_cells: int
    over_layer_cells: int
    max_layers: int
    stretch_mean: float
    stretch_max: float
    stretch_frac_over: float
    thresholds: ClothUnpleatThresholds

    @property
    def gates(self) -> dict[str, bool]:
        """Each gate on its own, so a failure says which one."""

        limits = self.thresholds
        passed = {
            "single_layer_frac": self.single_layer_frac >= limits.single_layer_frac_min,
            "spread_ratio": self.spread_ratio >= limits.spread_ratio_min,
        }
        if limits.max_height_m is not None:
            passed["max_height"] = self.peak_above_table <= limits.max_height_m
        if limits.band_shift_max is not None:
            passed["band_shift"] = self.band_shift <= limits.band_shift_max
        if limits.stretch_max is not None:
            passed["stretch"] = self.stretch_max <= limits.stretch_max
        if limits.flatness_var_max is not None:
            passed["flatness_var"] = self.flatness_var <= limits.flatness_var_max
        return passed

    @property
    def is_terminal(self) -> bool:
        """Conjunction, never a single threshold -- C1 requires it, and a band that
        was towed rather than unfolded is exactly why: it recovers length without
        recovering layers."""

        values = self.gates.values()
        return bool(values) and all(values)

    def invariant(self) -> dict[str, float]:
        """The C1 invariant: a dict of floats, no integer topology involved."""

        return {
            "peak_above_table_m": float(self.peak_above_table),
            "single_layer_frac": float(self.single_layer_frac),
            "spread_ratio": float(self.spread_ratio),
            "flatness_var": float(self.flatness_var),
        }

    def to_info(self) -> dict[str, Any]:
        return {
            **self.invariant(),
            "peak_above_table_mm": float(self.peak_above_table * 1e3),
            "spread_span_mm": float(self.spread_span * 1e3),
            "band_shift_mm": float(self.band_shift * 1e3),
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
            f"peak_mm={self.peak_above_table * 1e3:.2f} "
            f"single_layer_frac={self.single_layer_frac:.3f} "
            f"spread_ratio={self.spread_ratio:.3f} "
            f"spread_mm={self.spread_span * 1e3:.1f} "
            f"band_shift_mm={self.band_shift * 1e3:.2f} "
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
class ClothUnpleatEvaluator:
    """Success = the pleat is gone and the material is back, per docx 1.2.

    Takes particle arrays rather than a scene so the same evaluator serves the
    task, the demo and the offline check.
    """

    thresholds: ClothUnpleatThresholds
    cell: float
    particle_size: float
    material_length: float
    #: World axis the band's length runs along, 0 for x and 1 for y. The spread
    #: and shift readings are both statements about that axis, so the judge has
    #: to be told which one it is rather than assuming the band has not been
    #: turned. Read from the same config key the layout reads.
    material_axis: int = 1

    @classmethod
    def from_config(cls, task_cfg) -> "ClothUnpleatEvaluator":
        axis = str(task_cfg["cloth"]["material_axis"]).lower()
        if axis not in ("x", "y"):
            raise ValueError(f"cloth.material_axis must be 'x' or 'y', got {axis!r}.")
        return cls(
            thresholds=ClothUnpleatThresholds.from_config(task_cfg["success"]),
            cell=float(task_cfg["success"]["cell"]),
            particle_size=float(task_cfg["cloth"]["particle_size"]),
            material_length=float(task_cfg["cloth"]["material_length"]),
            material_axis=0 if axis == "x" else 1,
        )

    def classify(self, rest_nodes, nodes, *, table_z: float, grid=None) -> ClothUnpleatState:
        """Judge one end state. ``grid`` is ``(cols, rows)`` of the control mesh.

        ``grid`` is optional because the stretch report is diagnostic: when the
        remesh has changed the particle count away from a clean subdivision there
        is no neighbour arithmetic to be had, and the honest reading is NaN rather
        than a search that would pair up material folded against itself.
        """

        nodes = np.asarray(nodes, dtype=float)
        rest_nodes = np.asarray(rest_nodes, dtype=float)
        layers = layer_report(nodes, float(table_z), self.cell, self.particle_size)
        span = spread_span(nodes, self.material_axis)
        heights = nodes[:, 2] - float(table_z)

        shape = None if grid is None else simulated_grid_shape(len(rest_nodes), grid)
        stretch = {"mean": float("nan"), "max": float("nan"), "frac_over": float("nan")}
        if shape is not None:
            stretch = stretch_report(rest_nodes, nodes, rect_grid_neighbours(*shape))

        return ClothUnpleatState(
            peak_above_table=peak_height(nodes, table_z),
            single_layer_frac=single_layer_fraction(layers),
            spread_ratio=span / max(self.material_length, 1e-9),
            spread_span=span,
            band_shift=band_shift(
                rest_nodes,
                nodes,
                cols=shape[0] if shape else None,
                axis=self.material_axis,
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


def simulated_grid_shape(count: int, grid) -> tuple[int, int] | None:
    """The simulated grid's ``(cols, rows)``, or None when it is not a grid.

    Genesis subdivides the control mesh, so the simulated grid is some
    ``(2^k (cols-1) + 1) x (2^k (rows-1) + 1)``. Solving for k rather than
    assuming it means the reading survives a particle_size change; returning None
    rather than guessing means nothing downstream silently pairs up the wrong
    particles when the remesh was not a clean subdivision at all.
    """

    cols, rows = int(grid[0]), int(grid[1])
    for level in range(0, 6):
        factor = 2**level
        wide = factor * (cols - 1) + 1
        tall = factor * (rows - 1) + 1
        if wide * tall == int(count):
            return wide, tall
    return None


def simulated_grid_pairs(rest_nodes, grid):
    """Neighbour pairs for the simulated particles, or None if they are not a grid."""

    shape = simulated_grid_shape(len(rest_nodes), grid)
    return None if shape is None else rect_grid_neighbours(*shape)
