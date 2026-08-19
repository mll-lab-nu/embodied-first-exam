"""Did the cloth actually get folded? (docx 1.1)

Two criteria decide, and several more are recorded to say how a failure failed.

**How far the material is from where a finished fold puts it.** Every particle's
destination is arithmetic -- the half beyond the fold line reflected across it,
raised by one cloth thickness -- because the mesh keeps its vertex order. This is
the measure the field uses (SoftGym's ClothFold reward is the distance between
corresponding particles; the binary successes built on it threshold the mean),
so the number can be read against published ones. Scored as a mean AND as the
fraction of particles further than a tolerance, because a mean hides a lump: a
sheet 95% perfect with a twentieth of it 60 mm out of place averages 2.6 mm.

**How much of the covered area carries exactly two layers.** Kept alongside for
two reasons. The category contract (C1, `task_taxonomy_zh.md` 4.1) requires a
structural measure beside a morphological one and forbids deciding on a single
position threshold. And it is the only reading here that does not need particle
identities -- a real robot sees a point cloud, not vertex numbers.

Recorded but not gated: coverage IoU, crease position and straightness, height
variance, layer depth. docx 1.1 names coverage and crease position as joint
criteria, and they were the gates until the per-particle target replaced them --
an 8 mm plan-view grid is a coarser version of an exact 3D destination per
particle, and a sheet put down in the wrong place misses every target, so the
crease term is subsumed once the targets live in world coordinates. They stay in
the output because they identify WHICH failure occurred: measured 2026-08-20 on
this cloth, same grasp point, only the hand's path changed --

    走法              双层率  覆盖 IoU  对角位移   平整度方差
    fold（正确）       0.860   0.870    1.19mm     3.62e-06
    drag（贴地拖）     0.336   0.719   10.49mm     5.64e-06
    crumple（揉成团）  0.145   0.561    8.16mm     5.27e-06

Everything here is plain NumPy over ``(P, 3)`` particle arrays. Genesis is never
imported, so `tests/check_cloth_fold_geometry.py` can feed it synthetic cloth and
check the criteria separate a good fold from the wrong ones without a GPU.

`to_info()` marks ``"topological": false`` so downstream statistics never pool
these readings with the integer invariants of C2/C3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


def _xy(nodes) -> np.ndarray:
    return np.asarray(nodes, dtype=float)[:, :2]


def occupied_cells(nodes, cell: float) -> set[tuple[int, int]]:
    """The ``(x, y)`` cells the cloth covers, on the shared grid.

    Every area- and layer-based measure below bins onto this same grid, so they
    stay comparable with each other and across runs.
    """

    return {
        (int(np.floor(x / cell)), int(np.floor(y / cell))) for x, y in _xy(nodes)
    }


def fold_target_cells(rest_nodes, fold_point, fold_normal, cell: float) -> set:
    """Where a finished fold should land: half the cloth's OWN rest outline.

    Cut from the rest footprint along the fold line rather than taken from an
    idealised box. Folding a square corner-to-corner leaves a triangle (288 cm2),
    while the axis-aligned rectangle spanned by the two corners is 400 cm2 --
    scoring against that rectangle capped a perfect fold at 0.72 and a real one
    read 0.433 against a target it could never fill (2026-08-19). Deriving the
    target from the cloth itself also makes it correct for a rotated layout and
    for fold lines that are not through the centre.
    """

    along = (_xy(rest_nodes) - np.asarray(fold_point, dtype=float)) @ np.asarray(
        fold_normal, dtype=float
    )
    return occupied_cells(np.asarray(rest_nodes, dtype=float)[along < 0.0], cell)


def footprint_iou(nodes, target: set, cell: float) -> float:
    """Shared cells over cells either one covers. 1.0 identical, 0 no overlap."""

    if not target:
        return float("nan")
    covered = occupied_cells(nodes, cell)
    return len(covered & target) / len(covered | target)


def layer_report(nodes, table_z: float, cell: float, particle_size: float) -> dict:
    """How many layers the sheet stacks into, binned into ``(x, y)`` cells.

    In each cell the particles are sorted by height and split wherever the gap to
    the next one exceeds half a particle; the number of runs is the layer count.
    docx 1.1's state change is 层数 1 → 2, so the reading is **cells carrying
    exactly two**, not cells carrying "more than one".

    The distinction is the whole anti-shortcut argument. Scoring "is there a
    vertical break anywhere in this cell" marks a bunched-up cloth as two-layered
    just as readily as a folded one -- a pile has breaks everywhere -- and
    bunching the sheet up is the first shortcut docx names. Counting runs
    separates them: a fold gives 2, a flat sheet 1, a pile many.

    A separation that collapses to ~0 would mean PBD self-collision is leaking
    and layer-based judging is not available at all -- that was the open question
    the spike existed to answer. It does not: measured 2.9-3.4 mm against a 4.0 mm
    particle, so the two layers stay apart.
    """

    nodes = np.asarray(nodes, dtype=float)
    buckets: dict[tuple[int, int], list[float]] = {}
    for index in range(len(nodes)):
        key = (
            int(np.floor(nodes[index, 0] / cell)),
            int(np.floor(nodes[index, 1] / cell)),
        )
        buckets.setdefault(key, []).append(float(nodes[index, 2]) - table_z)

    two_layer, over_layer, gaps, most = 0, 0, [], 0
    for heights in buckets.values():
        ordered = np.sort(np.asarray(heights))
        breaks = np.diff(ordered) if len(ordered) > 1 else np.array([])
        wide = breaks[breaks > 0.5 * particle_size]
        count = len(wide) + 1
        most = max(most, count)
        if count == 2:
            two_layer += 1
            gaps.append(float(wide[0]))
        elif count > 2:
            over_layer += 1
    return {
        "covered_cells": len(buckets),
        "two_layer_cells": two_layer,
        # Cells stacked more than two deep: the direct reading of "bunched up"
        # rather than "folded". Diagnostic for now -- whether it deserves a gate
        # of its own is a question for the measured run, not for a guess.
        "over_layer_cells": over_layer,
        "max_layers": most,
        "gap_median": float(np.median(gaps)) if gaps else float("nan"),
    }


def fold_targets(rest_nodes, fold_point, fold_normal, thickness: float) -> np.ndarray:
    """Where every particle should be once the fold is done, solved in closed form.

    The half on the near side of the line stays where it started; the half beyond
    it is reflected across the line and raised by one cloth thickness. Nothing has
    to be simulated to know this, and no oracle rollout is needed -- the cloth
    keeps its vertex order, so particle *i*'s destination is arithmetic.

    This is the field's standard fold measure (SoftGym's ClothFold reward is the
    distance between corresponding particles of the two halves; the binary
    successes built on it threshold the mean particle distance). Two differences
    from SoftGym's form, both deliberate:

    - targets are in **world coordinates**, not pairwise between the halves. The
      pairwise form is blind to the whole sheet being carried sideways, which is
      why SoftGym adds a separate displacement penalty; putting the targets in
      the world absorbs that failure into the same number.
    - **every** particle is scored, the stationary half included, for the same
      reason.

    ``thickness`` is where the upper layer is expected to sit above the lower.
    One particle is the nominal value; the measured layer gap on this cloth is
    2.9-3.4 mm against a 4.0 mm particle, so the nominal choice carries about a
    1 mm bias on the moving half. Left as a parameter rather than hidden, because
    the calibration run is what should settle it.
    """

    rest_nodes = np.asarray(rest_nodes, dtype=float)
    fold_point = np.asarray(fold_point, dtype=float)
    fold_normal = np.asarray(fold_normal, dtype=float)
    along = (_xy(rest_nodes) - fold_point) @ fold_normal
    targets = rest_nodes.copy()
    moving = along > 0.0
    targets[moving, :2] -= 2.0 * along[moving, None] * fold_normal
    targets[moving, 2] += float(thickness)
    return targets


def particle_error(nodes, targets, tolerance: float) -> tuple[float, float]:
    """``(mean distance, fraction further than ``tolerance``)`` from the targets.

    The mean is the quantity the literature thresholds, so it is what makes these
    numbers comparable to published ones. It cannot be the only reading, because
    a mean hides a small badly-wrong region: 95% of the sheet perfect and 5%
    balled up 60 mm out of place averages to 2.6 mm, under any threshold worth
    setting, while the cloth plainly has a lump in it.

    The companion is a FRACTION rather than a high percentile. A percentile has
    to guess how big the bad region is: on that same 5% lump the 95th percentile
    reads 0.0 mm, because the defect is exactly the part it discards. The
    fraction beyond a tolerance asks the question the other way round -- how much
    of the cloth is visibly not where it belongs -- and holds for a defect of any
    size. It is also not the maximum, which one stray particle would dominate.

    A floor is expected rather than zero. A crease has a bend radius, so the
    particles within a few rows of the fold line physically cannot reach their
    reflected positions -- perfect execution still reads some millimetres.
    """

    distance = np.linalg.norm(
        np.asarray(nodes, dtype=float) - np.asarray(targets, dtype=float), axis=1
    )
    return float(distance.mean()), float((distance > float(tolerance)).mean())


def crease_indices(rest_nodes, fold_point, fold_normal) -> np.ndarray:
    """Which particles started ON the fold line -- the ones that become the crease.

    Available only because the cloth mesh keeps its vertex order through Genesis'
    remesh (`order_preserved=yes` in the spike's log); that is the whole reason
    docx 1.1's "折线位置误差" is measurable at all rather than being guessed from
    the outline.

    One row's worth, taken as the sqrt(P) particles nearest the line. Picking by
    a distance band instead would either come up empty when the line falls
    between rows, or grab three rows and put the band's own thickness into the
    straightness reading as a floor.
    """

    rest_nodes = np.asarray(rest_nodes, dtype=float)
    along = np.abs(
        (_xy(rest_nodes) - np.asarray(fold_point, dtype=float))
        @ np.asarray(fold_normal, dtype=float)
    )
    count = max(3, min(len(rest_nodes), int(round(np.sqrt(len(rest_nodes))))))
    return np.argsort(along)[:count]


def crease_report(nodes, indices, fold_point, fold_normal) -> tuple[float, float]:
    """``(offset, straightness)`` in metres for the material that forms the crease.

    ``offset``        how far that material sits from where the fold line was
                      asked to be. This is docx 1.1's 折线位置误差, and it is the
                      gate rather than "did the far corner move": a sheet dragged
                      bodily across the table puts the crease in the wrong place
                      even if the fold itself was clean.
    ``straightness``  RMS distance from those points to their own best-fit line,
                      i.e. docx 1.1's 折边形成直线. Recorded, not gated -- see
                      `ClothFoldThresholds`.
    """

    indices = np.asarray(indices, dtype=int)
    if len(indices) < 3:
        return float("nan"), float("nan")
    xy = _xy(np.asarray(nodes, dtype=float)[indices])
    signed = (xy - np.asarray(fold_point, dtype=float)) @ np.asarray(
        fold_normal, dtype=float
    )
    # Smallest singular value of the centred points is the total perpendicular
    # spread about the best-fit line; per point that is the RMS deviation.
    spread = np.linalg.svd(xy - xy.mean(axis=0), compute_uv=False)
    return float(abs(signed.mean())), float(spread[-1] / np.sqrt(len(xy)))


def anchor_shift(rest_nodes, nodes, fold_point, fold_normal) -> float:
    """Mean in-plane travel of the half that is NOT supposed to move.

    A diagnostic, not a gate -- `crease_report`'s offset is what docx asks for.
    Kept because it separates "the fold went wrong" from "the whole sheet slid",
    and the second one is a physics problem rather than a planning one: the slide
    is creep, accumulating at a fixed rate per second (0.86-1.11 mm/s measured
    across three carry durations), so it is bounded by how long the carry lasts.
    Whole-sheet mean displacement would say nothing here, since the folded half
    is supposed to travel the full width.
    """

    rest_nodes = np.asarray(rest_nodes, dtype=float)
    nodes = np.asarray(nodes, dtype=float)
    along = (_xy(rest_nodes) - np.asarray(fold_point, dtype=float)) @ np.asarray(
        fold_normal, dtype=float
    )
    staying = np.flatnonzero(along < 0.0)
    if not len(staying):
        return float("nan")
    return float(
        np.linalg.norm(_xy(nodes)[staying] - _xy(rest_nodes)[staying], axis=1).mean()
    )


@dataclass(frozen=True)
class ClothFoldThresholds:
    """What counts as folded: two gates, each answering to a different authority.

    ``particle_error``   how far the material is from where a finished fold puts
                         it. The field's measure, so the number can be read
                         against published ones. Scored as mean AND a high
                         percentile -- see `particle_error` for why the mean
                         alone is not enough.
    ``two_layer_frac``   how much of the covered area carries exactly two layers.
                         Kept because the category contract requires a structural
                         measure alongside a morphological one and forbids
                         deciding on a single position threshold (task_taxonomy
                         4.1), and because it is the only reading here that does
                         not need particle identities -- a real robot sees a point
                         cloud, not vertex numbers.

    Coverage IoU, crease offset, straightness and flatness are recorded but not
    gated by default. Coverage is a coarser version of the particle error (an
    8 mm plan-view grid against an exact 3D destination per particle), and crease
    offset is subsumed once the targets live in world coordinates, since a sheet
    put down in the wrong place misses every target. They stay in the output
    because they say *which way* a failed fold failed; the optional slots let any
    of them be switched back on from config.
    """

    particle_error_mean_max: float
    particle_off_target_frac_max: float
    #: How far a single particle may be from its target before it counts as "not
    #: where it belongs". Sets what `particle_off_target_frac_max` is a fraction
    #: OF, so the two are read together.
    particle_off_target_m: float
    two_layer_frac_min: float
    fold_iou_min: float | None = None
    crease_offset_max: float | None = None
    crease_straightness_max: float | None = None
    flatness_var_max: float | None = None

    @classmethod
    def from_config(cls, success_cfg) -> "ClothFoldThresholds":
        def opt(name):
            value = success_cfg.get(name, None) if hasattr(success_cfg, "get") else None
            return None if value is None else float(value)

        return cls(
            particle_error_mean_max=float(success_cfg["particle_error_mean_max"]),
            particle_off_target_frac_max=float(success_cfg["particle_off_target_frac_max"]),
            particle_off_target_m=float(success_cfg["particle_off_target_m"]),
            two_layer_frac_min=float(success_cfg["two_layer_frac_min"]),
            fold_iou_min=opt("fold_iou_min"),
            crease_offset_max=opt("crease_offset_max"),
            crease_straightness_max=opt("crease_straightness_max"),
            flatness_var_max=opt("flatness_var_max"),
        )


@dataclass(frozen=True)
class ClothFoldState:
    """The five readings plus the thresholds they were judged against."""

    particle_error_mean: float
    particle_off_target_frac: float
    two_layer_frac: float
    fold_iou: float
    crease_offset: float
    crease_straightness: float
    flatness_var: float
    # Recorded for diagnosis; no gate depends on them.
    covered_cells: int
    two_layer_cells: int
    over_layer_cells: int
    max_layers: int
    layer_gap_median: float
    peak_above_table: float
    anchor_shift: float
    thresholds: ClothFoldThresholds

    @property
    def gates(self) -> dict[str, bool]:
        """Each gate on its own, so a failure says which one."""

        limits = self.thresholds
        passed = {
            "particle_error_mean": (
                self.particle_error_mean <= limits.particle_error_mean_max
            ),
            # How much of the cloth is visibly not where it belongs. The
            # mean alone passes a sheet that is 95% perfect with a lump in it.
            "particle_off_target_frac": (
                self.particle_off_target_frac <= limits.particle_off_target_frac_max
            ),
            "two_layer_frac": self.two_layer_frac >= limits.two_layer_frac_min,
        }
        if limits.fold_iou_min is not None:
            passed["fold_iou"] = self.fold_iou >= limits.fold_iou_min
        if limits.crease_offset_max is not None:
            passed["crease_offset"] = self.crease_offset <= limits.crease_offset_max
        if limits.crease_straightness_max is not None:
            passed["crease_straightness"] = (
                self.crease_straightness <= limits.crease_straightness_max
            )
        if limits.flatness_var_max is not None:
            passed["flatness_var"] = self.flatness_var <= limits.flatness_var_max
        return passed

    @property
    def is_terminal(self) -> bool:
        """Conjunction, never a single threshold -- C1 requires it, and the
        anti-shortcut cases in docx 1.1 are exactly why."""

        values = self.gates.values()
        return bool(values) and all(values)

    def invariant(self) -> dict[str, float]:
        """The C1 invariant: a dict of floats, no integer topology involved."""

        return {
            "particle_error_mean_m": float(self.particle_error_mean),
            "particle_off_target_frac": float(self.particle_off_target_frac),
            "two_layer_frac": float(self.two_layer_frac),
            "fold_iou": float(self.fold_iou),
            "crease_offset_m": float(self.crease_offset),
            "crease_straightness_m": float(self.crease_straightness),
            "flatness_var": float(self.flatness_var),
        }

    def to_info(self) -> dict[str, Any]:
        return {
            **self.invariant(),
            "particle_error_mean_mm": float(self.particle_error_mean * 1e3),
            "particle_off_target_m": float(self.thresholds.particle_off_target_m),
            "crease_offset_mm": float(self.crease_offset * 1e3),
            "crease_straightness_mm": float(self.crease_straightness * 1e3),
            "covered_cells": int(self.covered_cells),
            "two_layer_cells": int(self.two_layer_cells),
            "over_layer_cells": int(self.over_layer_cells),
            "max_layers": int(self.max_layers),
            "layer_gap_median_mm": float(self.layer_gap_median * 1e3),
            "peak_above_table_mm": float(self.peak_above_table * 1e3),
            "anchor_shift_mm": float(self.anchor_shift * 1e3),
            "gates": {k: bool(v) for k, v in self.gates.items()},
            "terminal": bool(self.is_terminal),
            # C1 has no integer topological invariant; saying so explicitly keeps
            # downstream statistics from pooling it with C2/C3 readings.
            "topological": False,
        }

    def summary(self) -> str:
        return (
            f"particle_err_mean_mm={self.particle_error_mean * 1e3:.2f} "
            f"off_target_frac={self.particle_off_target_frac:.3f} "
            f"two_layer_frac={self.two_layer_frac:.3f} fold_iou={self.fold_iou:.3f} "
            f"crease_offset_mm={self.crease_offset * 1e3:.2f} "
            f"crease_straightness_mm={self.crease_straightness * 1e3:.2f} "
            f"flatness_var={self.flatness_var:.3e} "
            f"covered_cells={self.covered_cells} two_layer_cells={self.two_layer_cells} "
            f"over_layer_cells={self.over_layer_cells} max_layers={self.max_layers} "
            f"anchor_shift_mm={self.anchor_shift * 1e3:.2f} "
            f"gates={','.join(k for k, v in self.gates.items() if not v) or 'all_pass'} "
            f"terminal={self.is_terminal}"
        )


@dataclass(frozen=True)
class ClothFoldEvaluator:
    """Success = the cloth is folded, judged the way docx 1.1 asks for.

    Takes particle arrays rather than a scene so the same evaluator serves the
    task, the demo and the offline check. `fold_point` / `fold_normal` come from
    the layout: the target fold line, as a point on it and the unit normal
    pointing towards the half that gets lifted.
    """

    thresholds: ClothFoldThresholds
    cell: float
    particle_size: float
    #: Height the upper layer is expected to settle at above the lower one, used
    #: to place the analytic targets. Defaults to one particle when the config
    #: does not say otherwise.
    fold_thickness: float = 0.004

    @classmethod
    def from_config(cls, task_cfg) -> "ClothFoldEvaluator":
        success = task_cfg["success"]
        particle_size = float(task_cfg["cloth"]["particle_size"])
        thickness = success.get("fold_thickness", None) if hasattr(success, "get") else None
        return cls(
            thresholds=ClothFoldThresholds.from_config(success),
            cell=float(success["cell"]),
            particle_size=particle_size,
            fold_thickness=particle_size if thickness is None else float(thickness),
        )

    def classify(
        self, rest_nodes, nodes, *, table_z: float, fold_point, fold_normal
    ) -> ClothFoldState:
        rest_nodes = np.asarray(rest_nodes, dtype=float)
        nodes = np.asarray(nodes, dtype=float)
        if rest_nodes.shape != nodes.shape:
            raise ValueError(
                f"rest and current particle arrays must match: "
                f"{rest_nodes.shape} vs {nodes.shape}"
            )
        fold_point = np.asarray(fold_point, dtype=float)[:2]
        fold_normal = np.asarray(fold_normal, dtype=float)[:2]
        fold_normal = fold_normal / max(float(np.linalg.norm(fold_normal)), 1e-12)

        # The primary reading: distance to where a finished fold puts each
        # particle, solved in closed form from the rest layout.
        err_mean, off_frac = particle_error(
            nodes,
            fold_targets(rest_nodes, fold_point, fold_normal, self.fold_thickness),
            self.thresholds.particle_off_target_m,
        )
        layers = layer_report(nodes, table_z, self.cell, self.particle_size)
        offset, straightness = crease_report(
            nodes, crease_indices(rest_nodes, fold_point, fold_normal), fold_point, fold_normal
        )
        heights = nodes[:, 2] - float(table_z)
        return ClothFoldState(
            particle_error_mean=err_mean,
            particle_off_target_frac=off_frac,
            two_layer_frac=(
                layers["two_layer_cells"] / layers["covered_cells"]
                if layers["covered_cells"]
                else float("nan")
            ),
            fold_iou=footprint_iou(
                nodes,
                fold_target_cells(rest_nodes, fold_point, fold_normal, self.cell),
                self.cell,
            ),
            crease_offset=offset,
            crease_straightness=straightness,
            flatness_var=float(np.var(heights)),
            covered_cells=int(layers["covered_cells"]),
            two_layer_cells=int(layers["two_layer_cells"]),
            over_layer_cells=int(layers["over_layer_cells"]),
            max_layers=int(layers["max_layers"]),
            layer_gap_median=float(layers["gap_median"]),
            peak_above_table=float(heights.max()),
            anchor_shift=anchor_shift(rest_nodes, nodes, fold_point, fold_normal),
            thresholds=self.thresholds,
        )
