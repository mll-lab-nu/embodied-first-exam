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

**Recovered fraction** is material conservation: the pleat holds a known length
of cloth, and giving it back is the same event as the pleat ceasing to exist.
This is what makes 「压扁」 and 「展开」 strictly separable, which is the property
docx 1.2 asks the judge to have.

It is measured as the share of the STORED material that came back, not as the
band's length over its material length. Those two look interchangeable and are
not: the raw ratio starts at 0.764 rather than at zero, so it can only ever move
through 0.236, and a threshold of 0.90 on it -- which reads as "nearly all of
it" -- actually passes a band that has given back barely more than half its
pleat. Measured 2026-08-23: a run that recovered 40.9 mm of 61.4 mm scored 0.921
and passed. The recovered fraction says 0.67 for the same run, which is what it
is.

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


def material_dimensions(material, nodes, *, particle_size, material_axis, length, width):
    """Lengths between opposite material edges, invariant to rigid rotation.

    A rotated or sheared square can enlarge BOTH world-axis bounding boxes
    without releasing either fold. Track the actual material edges instead.
    The edge-strip inset is normalized out against the flat reference itself.
    """
    material, nodes = np.asarray(material), np.asarray(nodes)
    if material.shape != nodes.shape:
        raise ValueError("cross material reference must match the remeshed particles")
    vectors, spans = [], []
    for axis, full in ((material_axis, length), (1-material_axis, width)):
        at = material[:, axis]
        low, high = at <= at.min() + particle_size, at >= at.max() - particle_size
        vector = nodes[high, :2].mean(axis=0) - nodes[low, :2].mean(axis=0)
        reference = material[high, :2].mean(axis=0) - material[low, :2].mean(axis=0)
        spans.append(float(np.linalg.norm(vector) / np.linalg.norm(reference) * full))
        vectors.append(vector)
    cosine = abs(float(vectors[0] @ vectors[1])) / max(
        float(np.linalg.norm(vectors[0]) * np.linalg.norm(vectors[1])), 1e-12)
    return spans, cosine


def band_shift(
    rest_nodes,
    nodes,
    *,
    cols: int | None = None,
    keep: float = 0.25,
    axis: int = 1,
    pulled_ends: tuple = (1.0,),
) -> float:
    """How far the band's ANCHOR travelled, in metres.

    The anchor is the material farthest from every end the gripper takes: table
    friction holds it while the pleats are opened around it. A band that was
    towed instead of unfolded moves it, and moves it by roughly the whole drag.

    ``pulled_ends`` says which ends are taken, as +-1 along the material order
    (index 0 is the lead-in end, so -1 is that end and +1 the other). With ONE
    pull the anchor is the opposite end, which is the reading this has taken
    since 2026-08-23. With TWO -- a pleat at each end of the band, pulled one at
    a time (2026-09-09) -- neither end is still, and the anchor is the middle:
    reading the far quarter there would report the second pull's own travel as a
    slide, and reading the middle on a ONE-pull layout reports half the stored
    material as one (measured on the offline gate's flat case: 27.6 mm against
    the correct 0.0).

    ``keep`` is the fraction of the band that counts as the anchor, measured
    along the MATERIAL when ``cols`` (the simulated grid's material-direction
    width) is known. Material order is the right axis and plan-view x is not:
    at rest a pleat's two arms hang over the flat run, so selecting by x alone
    picks up the very material the motion is supposed to move and reports a
    correct unfold as a 44 mm slide.

    Without ``cols`` the fallback selects by position along ``axis`` AND by
    height together, which separates the same two things whenever the arms are
    still up.

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

    ends = tuple(float(v) for v in pulled_ends) or (1.0,)

    def _farthest(position, low: float, high: float):
        """Mask of the ``keep`` fraction of ``position`` farthest from every
        grasped end, where ``low``/``high`` are the -1 and +1 ends' coordinates."""

        away = None
        for end in ends:
            at = high if end >= 0.0 else low
            distance = np.abs(position - at)
            away = distance if away is None else np.minimum(away, distance)
        cut = np.quantile(away, 1.0 - float(keep))
        return away >= cut

    if cols is not None and int(cols) > 1:
        cols = int(cols)
        columns = (np.arange(len(rest_nodes)) % cols).astype(float)
        selected = np.flatnonzero(_farthest(columns, 0.0, float(cols - 1)))
    else:
        along, zs = rest_nodes[:, int(axis)], rest_nodes[:, 2]
        # "On the table" relative to the band's own lowest material, so this does
        # not need to know where the table is.
        # A collapsed pleat's middle layer can lie below half the total height.
        # Only the table layer belongs to the anchor selection.
        floor = float(zs.min()) + min(0.001, 0.5 * float(zs.max() - zs.min()))
        picked = _farthest(along, float(along.min()), float(along.max()))
        selected = np.flatnonzero(picked & (zs <= floor))
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
    ``recovered_frac_min``     the material the pleat held has been given back,
                               as a share of what it held. The morphological one.
                               Together they satisfy the category contract's
                               requirement for a conjunction of the two kinds
                               (C1, `task_taxonomy_zh.md` 4.1).

    ``max_height_m`` is optional and ships as ``null`` -- see the module
    docstring for why. Band shift, stretch and flatness are likewise recorded
    rather than gated; the optional slots let any of them be switched on from
    config once there are measured runs to place them from.
    """

    single_layer_frac_min: float
    recovered_frac_min: float
    max_height_m: float | None = None
    spread_ratio_min: float | None = None
    band_shift_max: float | None = None
    stretch_max: float | None = None
    flatness_var_max: float | None = None
    #: How much wider than the band's own width its plan-view footprint may end
    #: up ACROSS the material axis. A straight band reads its width plus a few
    #: mm of particle fuzz; a band that unfolded into a bend -- a slanted crease
    #: pulled along the band's axis leaves a kink at the crease -- reads more.
    #: Measured 2026-09-10 before the pull direction followed the crease: +3..+7
    #: mm at zero slant, +43 mm at 34 degrees, and the two layer/length gates
    #: passed the bent band. Recorded first, gated once the fixed runs are in.
    across_excess_max: float | None = None

    @classmethod
    def from_config(cls, success_cfg) -> "ClothUnpleatThresholds":
        def opt(name):
            value = success_cfg.get(name, None) if hasattr(success_cfg, "get") else None
            return None if value is None else float(value)

        return cls(
            single_layer_frac_min=float(success_cfg["single_layer_frac_min"]),
            recovered_frac_min=float(success_cfg["recovered_frac_min"]),
            max_height_m=opt("max_height_m"),
            spread_ratio_min=opt("spread_ratio_min"),
            band_shift_max=opt("band_shift_max"),
            stretch_max=opt("stretch_max"),
            flatness_var_max=opt("flatness_var_max"),
            across_excess_max=opt("across_excess_max"),
        )


@dataclass(frozen=True)
class ClothUnpleatState:
    """The three readings plus everything recorded for diagnosis."""

    peak_above_table: float
    #: Plan-view extent across the material axis minus the band's width, metres.
    across_excess: float
    single_layer_frac: float
    recovered_frac: float
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

    # Only cross folds store material across the band as well as along it.
    width_recovered_frac: float | None = None
    material_orthogonality: float | None = None

    @property
    def gates(self) -> dict[str, bool]:
        """Each gate on its own, so a failure says which one."""

        limits = self.thresholds
        passed = {
            "single_layer_frac": self.single_layer_frac >= limits.single_layer_frac_min,
            "recovered_frac": self.recovered_frac >= limits.recovered_frac_min,
        }
        if self.width_recovered_frac is not None:
            passed["width_recovered_frac"] = self.width_recovered_frac >= limits.recovered_frac_min
            passed["material_orthogonality"] = self.material_orthogonality <= 0.15
        if limits.spread_ratio_min is not None:
            passed["spread_ratio"] = self.spread_ratio >= limits.spread_ratio_min
        if limits.max_height_m is not None:
            passed["max_height"] = self.peak_above_table <= limits.max_height_m
        if limits.band_shift_max is not None:
            passed["band_shift"] = self.band_shift <= limits.band_shift_max
        if limits.stretch_max is not None:
            passed["stretch"] = self.stretch_max <= limits.stretch_max
        if limits.across_excess_max is not None:
            passed["across_excess"] = self.across_excess <= limits.across_excess_max
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
            "recovered_frac": float(self.recovered_frac),
            "spread_ratio": float(self.spread_ratio),
            "flatness_var": float(self.flatness_var),
        }

    def to_info(self) -> dict[str, Any]:
        return {
            **self.invariant(),
            "width_recovered_frac": self.width_recovered_frac,
            "material_orthogonality": self.material_orthogonality,
            "peak_above_table_mm": float(self.peak_above_table * 1e3),
            "spread_span_mm": float(self.spread_span * 1e3),
            "across_excess_mm": float(self.across_excess * 1e3),
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
            f"recovered_frac={self.recovered_frac:.3f} "
            + (f"width_recovered_frac={self.width_recovered_frac:.3f} "
               f"material_orthogonality={self.material_orthogonality:.3f} "
               if self.width_recovered_frac is not None else "")
            +
            f"spread_ratio={self.spread_ratio:.3f} "
            f"spread_mm={self.spread_span * 1e3:.1f} "
            f"band_shift_mm={self.band_shift * 1e3:.2f} "
            f"across_excess_mm={self.across_excess * 1e3:.1f} "
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
    #: Which ends of the material order the gripper takes, as +-1 (index 0 is
    #: the lead-in end). One pleat is one pull at the +1 end; two pleats are one
    #: at each. Only `band_shift` needs it -- the anchor is what is farthest from
    #: all of them.
    pulled_ends: tuple = (1.0,)
    #: The band's own width, what `across_excess` is measured against.
    band_width: float = 0.120
    cross: bool = False
    material_nodes: Any = None
    across_pull_sign: float = -1.0

    @classmethod
    def from_config(cls, task_cfg, *, material_nodes=None) -> "ClothUnpleatEvaluator":
        cloth = task_cfg["cloth"]
        axis = str(cloth["material_axis"]).lower()
        if axis not in ("x", "y"):
            raise ValueError(f"cloth.material_axis must be 'x' or 'y', got {axis!r}.")
        flip = float(cloth.get("band_flip", 1) if hasattr(cloth, "get") else 1)
        flip = -1.0 if flip < 0 else 1.0
        # Every pull takes the same end (2026-09-10), so the anchor is always the
        # other one, however many pleats there are.
        ends = (flip,)
        return cls(
            thresholds=ClothUnpleatThresholds.from_config(task_cfg["success"]),
            cell=float(task_cfg["success"]["cell"]),
            particle_size=float(cloth["particle_size"]),
            material_length=float(cloth["material_length"]),
            material_axis=0 if axis == "x" else 1,
            pulled_ends=ends,
            band_width=float(cloth["width"]),
            cross=str(cloth["pleat"]["layout"]) == "cross",
            material_nodes=material_nodes,
            across_pull_sign=float(cloth.get("cross", {}).get("flip", -1)),
        )

    def classify(self, rest_nodes, nodes, *, table_z: float, grid=None, pairs=None) -> ClothUnpleatState:
        """Judge one end state. ``grid`` is ``(cols, rows)`` of the control mesh.

        ``grid`` is optional because the stretch report is diagnostic: when the
        remesh has changed the particle count away from a clean subdivision there
        is no neighbour arithmetic to be had, and the honest reading is NaN rather
        than a search that would pair up material folded against itself.
        """

        nodes = np.asarray(nodes, dtype=float)
        rest_nodes = np.asarray(rest_nodes, dtype=float)
        # The layer grid is anchored to the SETTLED band's own corner, not the
        # world origin. The band's position is a variation axis, and a
        # world-anchored 8 mm grid reads a different three-layer count for the
        # same physical pleat depending on where the layer edges fall relative
        # to the cell boundaries: the 2026-09-05 corner sweep read 24 and 6
        # cells for two bands that differed only by a 60 mm (7.5 cell) shift,
        # with identical peak height and spread, and the start-state guard
        # (min 12) aborted the second. Anchoring on the rest cloud makes the
        # reading a function of the cloth alone; the end state is binned on the
        # same grid so the two moments stay comparable.
        origin = rest_nodes[:, :2].min(axis=0)
        layers = layer_report(nodes, float(table_z), self.cell, self.particle_size, origin=origin)
        span = spread_span(nodes, self.material_axis)
        # How much of what the pleat was holding at the START has come back. The
        # denominator is the band's own stored material, measured on the rest
        # state rather than taken from the config, so a pleat that relaxed a
        # little before the arm arrived is not credited to the arm.
        rest_span = spread_span(rest_nodes, self.material_axis)
        width_recovered = None
        orthogonality = None
        if self.cross:
            if self.material_nodes is None:
                raise ValueError("cross evaluator requires the flat remeshed material reference")
            settings = dict(particle_size=self.particle_size, material_axis=self.material_axis,
                            length=self.material_length, width=self.band_width)
            current, orthogonality = material_dimensions(self.material_nodes, nodes, **settings)
            initial, _ = material_dimensions(self.material_nodes, rest_nodes, **settings)
            span, rest_span = current[0], initial[0]
            width_recovered = (current[1] - initial[1]) / max(self.band_width - initial[1], 1e-9)
        stored = max(self.material_length - rest_span, 1e-9)
        heights = nodes[:, 2] - float(table_z)

        shape = None if grid is None else simulated_grid_shape(len(rest_nodes), grid)
        stretch = {"mean": float("nan"), "max": float("nan"), "frac_over": float("nan")}
        if pairs is not None:
            stretch = stretch_report(self.material_nodes if self.cross else rest_nodes, nodes, pairs)
        elif shape is not None:
            stretch = stretch_report(rest_nodes, nodes, rect_grid_neighbours(*shape))

        anchor_shift = band_shift(rest_nodes, nodes, cols=shape[0] if shape else None,
                                  axis=self.material_axis, pulled_ends=self.pulled_ends)
        if self.cross:
            anchor = np.ones(len(nodes), dtype=bool)
            for axis, sign in ((self.material_axis, self.pulled_ends[0]),
                               (1-self.material_axis, self.across_pull_sign)):
                coordinate = np.asarray(self.material_nodes)[:, axis] * sign
                anchor &= coordinate <= np.quantile(coordinate, 0.25)
            anchor_shift = float(np.linalg.norm(nodes[anchor].mean(axis=0) - rest_nodes[anchor].mean(axis=0)))

        return ClothUnpleatState(
            peak_above_table=peak_height(nodes, table_z),
            across_excess=(current[1] if self.cross else spread_span(nodes, 1 - self.material_axis)) - self.band_width,
            single_layer_frac=single_layer_fraction(layers),
            recovered_frac=(span - rest_span) / stored,
            spread_ratio=span / max(self.material_length, 1e-9),
            spread_span=span,
            band_shift=anchor_shift,
            flatness_var=float(np.var(heights)),
            covered_cells=int(layers["covered_cells"]),
            two_layer_cells=int(layers["two_layer_cells"]),
            over_layer_cells=int(layers["over_layer_cells"]),
            max_layers=int(layers["max_layers"]),
            stretch_mean=float(stretch["mean"]),
            stretch_max=float(stretch["max"]),
            stretch_frac_over=float(stretch["frac_over"]),
            thresholds=self.thresholds,
            width_recovered_frac=width_recovered,
            material_orthogonality=orthogonality,
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
