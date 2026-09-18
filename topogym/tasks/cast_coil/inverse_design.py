"""Motion-first synthesis of three Coil variants from the successful IK seed.

The stationary part is grown within a bounded design envelope then carved by
conservatively padded samples of the moving part's swept volume. Exact box
compounds remain authoritative for visualization, collision and mass.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import label, binary_opening

from .geometry import CoilAssembly, merge_cells, occupied, partition_solid
from .verification import (
    Motion,
    CompoundCollision,
    box_corners,
    certify_motion,
    prototype_route,
)

KINDS = ("eccentric_turn", "split_turn_offset", "axial_screw_turn")
TITLES = {
    "eccentric_turn": "偏心转动",
    "split_turn_offset": "两段转动与错位解锁",
    "axial_screw_turn": "旋转与轴向推进",
}
FAMILY_PARAMETERS = {
    "eccentric_turn": ("pivot_offset_mm", 3.0),
    "split_turn_offset": ("step_height_mm", 6.0),
    "axial_screw_turn": ("axial_advance_mm", 6.0),
}


def family_parameter(kind, parameters=None):
    """Resolve an instance dimension; this does not certify its geometry."""
    if kind not in FAMILY_PARAMETERS:
        raise ValueError(kind)
    key, default = FAMILY_PARAMETERS[kind]
    parameters = {} if parameters is None else parameters
    if set(parameters) - {key}:
        raise ValueError(f"{kind} only accepts {key}")
    value = float(parameters.get(key, default))
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{key} must be finite and positive")
    return value / 1000


@dataclass
class ScrewMotion(Motion):
    advance: np.ndarray | None = None

    def pose(self, u):
        r, t = super().pose(u)
        return r, t + self.advance * u

    def point_speed_bound(self, corners):
        return super().point_speed_bound(corners) + float(np.linalg.norm(self.advance))


def variant_route(kind, parameters=None):
    if kind not in KINDS:
        raise ValueError(kind)
    amount = family_parameter(kind, parameters)
    pivot = np.array([0.0045, 0.0, -0.0315])
    slide = np.array([-0.02175, 0.0, 0.0])
    if kind == "eccentric_turn":
        pivot += [amount, 0, 0]
        slide += [-2 * amount, 0, 0]
    moves = [Motion("prototype_slide", 1.5, np.eye(3), np.zeros(3), slide)]
    kw = dict(axis=np.array([0.0, 1.0, 0.0]), pivot=pivot)
    if kind == "split_turn_offset":
        moves.append(
            Motion("turn_first_45", 1.5, np.eye(3), slide, angle_rad=-np.pi / 4, **kw)
        )
        r, t = moves[-1].pose(1)
        shift = np.array([0.0, 0.0, amount])
        moves.append(Motion("intermediate_offset", 1.0, r, t, t + shift))
        r, t = moves[-1].pose(1)
        moves.append(
            Motion(
                "turn_second_45",
                1.5,
                r,
                t,
                axis=kw["axis"],
                pivot=pivot + shift,
                angle_rad=-np.pi / 4,
            )
        )
    elif kind == "axial_screw_turn":
        moves.append(
            ScrewMotion(
                "screw_turn",
                3.0,
                np.eye(3),
                slide,
                angle_rad=-np.pi / 2,
                advance=np.array([0.0, amount, 0.0]),
                **kw,
            )
        )
    else:
        moves.append(
            Motion(
                "prototype_quarter_turn",
                3.0,
                np.eye(3),
                slide,
                angle_rad=-np.pi / 2,
                **kw,
            )
        )
    r, t = moves[-1].pose(1)
    moves.append(Motion("prototype_extract", 2.5, r, t, t + [0.207, 0, 0]))
    return moves


def sample_route(motions, boxes, displacement_m=0.00015):
    corners = box_corners(boxes)
    samples = []
    for motion in motions:
        n = max(
            2, int(np.ceil(motion.point_speed_bound(corners) / (2 * displacement_m)))
        )
        for u in np.linspace(0, 1, n + 1):
            samples.append((*motion.pose(float(u)), motion.name))
    return samples


def synthesize(kind, output, *, pitch=0.0015, growth=0.006, parameters=None):
    amount = family_parameter(kind, parameters)
    output = Path(output)
    if (output / "template.json").exists():
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    original = CoilAssembly()
    gold, silver = [b.boxes for b in original.bodies]
    # Existing material planes are retained exactly; only the added carving grid
    # is approximate. Cell-wise intersection is conservative, not point occupancy.
    all_boxes = np.concatenate((gold, silver))
    axes = [
        np.unique(
            np.round(
                np.r_[
                    np.arange(
                        all_boxes[:, 0, k].min(), all_boxes[:, 1, k].max(), pitch
                    ),
                    all_boxes[:, :, k].ravel(),
                ],
                10,
            )
        )
        for k in range(3)
    ]
    cx, cy, cz = [(a[:-1] + a[1:]) / 2 for a in axes]
    hx, hy, hz = [np.diff(a) / 2 for a in axes]
    xx, zz = np.meshgrid(cx, cz, indexing="ij")
    hhx, hhz = np.meshgrid(hx, hz, indexing="ij")
    xz = np.c_[xx.ravel(), zz.ravel()]
    half = np.c_[hhx.ravel(), hhz.ravel()]
    points = np.empty((len(cy), len(xz), 3))
    points[:, :, 0] = xz[:, 0]
    points[:, :, 2] = xz[:, 1]
    points[:, :, 1] = cy[:, None]
    base = occupied(points, gold)
    enlarged = gold.copy()
    enlarged[:, 0, [0, 2]] -= growth
    enlarged[:, 1, [0, 2]] += growth
    if kind == "axial_screw_turn":
        # Material here can obstruct a turn without axial advance. Its actual
        # surviving shape is determined by the requested screw trajectory.
        enlarged[:, 1, 1] += amount
    keep = occupied(points, enlarged)
    # Preserve the central through-bore and original external bounding box.
    keep &= ~((np.abs(points[:, :, 0]) < 0.018) & (np.abs(points[:, :, 2]) < 0.018))
    # The original opposing grasp faces must remain unchanged.
    protected = (
        (np.abs(points[:, :, 0] + 0.022) < 0.011)
        & (points[:, :, 1] < -0.024)
        & (points[:, :, 2] > 0.022)
    )
    keep[protected] = base[protected]
    samples = sample_route(variant_route(kind, parameters), silver)
    padding_xz = 0.0012
    padding_y = 0.00060
    for sample_index, (r, t, _) in enumerate(samples):
        rot = r[np.ix_([0, 2], [0, 2])]
        projected_axes = np.concatenate((np.eye(2), rot.T))
        a_radius = half @ np.abs(projected_axes.T)
        for low, high in silver:
            center = (low + high) / 2
            h = (high - low) / 2
            moved = r @ center + t
            yhit = np.abs(cy - moved[1]) <= hy + h[1] + padding_y
            if not yhit.any():
                continue
            gaps = (
                np.abs((xz - moved[[0, 2]]) @ projected_axes.T)
                - a_radius
                - h[[0, 2]] @ np.abs(rot.T @ projected_axes.T)
            )
            hit = np.all(gaps <= padding_xz, axis=1)
            if hit.any():
                keep[np.ix_(yhit, hit)] = False
        if sample_index % 500 == 0:
            print(kind, "sweep", sample_index, "/", len(samples), flush=True)
    lost_grasp = int(np.count_nonzero(base & protected & ~keep))
    if lost_grasp:
        raise RuntimeError(f"Candidate removes {lost_grasp} protected grasp cells")
    solid = keep.reshape(len(cy), len(cx), len(cz)).transpose(1, 0, 2)
    if kind == "axial_screw_turn":
        # Remove grid-scale ridges and diagonal edge contacts; this is a subset
        # operation, so it cannot invalidate the previously carved clearance.
        solid = binary_opening(solid, structure=np.ones((3, 3, 3), dtype=bool))
    labels, _ = label(solid)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    biggest = int(np.argmax(sizes))
    removed_islands = int(sizes.sum() - sizes[biggest])
    solid = labels == biggest
    retained = solid.transpose(1, 0, 2).reshape(keep.shape)
    lost_grasp = int(np.count_nonzero(base & protected & ~retained))
    if lost_grasp:
        raise RuntimeError(f"Mesh cleanup removes {lost_grasp} protected grasp cells")
    indices = np.argwhere(solid)
    cells = np.stack(
        [
            np.stack([axes[k][indices[:, k]] for k in range(3)], axis=1),
            np.stack([axes[k][indices[:, k] + 1] for k in range(3)], axis=1),
        ],
        axis=1,
    )
    boxes = merge_cells(cells)
    mesh, boxes = partition_solid(boxes, [])
    collision = CompoundCollision(boxes, silver)
    certs = [
        certify_motion(collision, m, margin_m=0.00006)
        for m in variant_route(kind, parameters)
    ]
    baseline = [
        certify_motion(collision, m, margin_m=0.00006)
        for m in prototype_route(original)
    ]
    negative = []
    for k in range(3):
        for sign in (-1, 1):
            m = Motion(
                f"straight_{k}_{sign}",
                1.0,
                np.eye(3),
                np.zeros(3),
                np.eye(3)[k] * sign * 0.24,
            )
            negative.append(certify_motion(collision, m, margin_m=0.00006))
    operation_controls = {}
    if kind == "axial_screw_turn":
        slide = variant_route(kind, parameters)[0].end_translation
        advance_first = Motion(
            "advance_before_turn", 1.0, np.eye(3), slide, slide + [0, amount, 0]
        )
        operation_controls["advance_before_turn"] = certify_motion(
            collision, advance_first, margin_m=0.00006
        )
    template = dict(original.template)
    template["central_bore_half_width_mm"] = 6.0
    template.update(
        template_id=f"cast_coil_inverse_{kind}_v1",
        geometry_status="motion_first_inverse_designed_prototype",
        authored_boxes_mm={
            original.bodies[0].name: (boxes / original.unit).tolist(),
            original.bodies[1].name: (silver / original.unit).tolist(),
        },
        inverse_design=dict(
            kind=kind,
            seed="2026-09-17_aloha_full/executed_plan.json",
            pitch_m=pitch,
            growth_m=growth,
            sample_displacement_bound_m=0.00015,
            sweep_padding_xz_m=padding_xz,
            sweep_padding_y_m=padding_y,
        ),
    )
    if parameters is not None:
        key = FAMILY_PARAMETERS[kind][0]
        template["inverse_design"]["parameters"] = {key: amount * 1000}
        template["template_id"] = f"cast_coil_inverse_{kind}_{key}_{amount * 1000:g}mm_v1"
    report = dict(
        kind=kind,
        sweep_samples=len(samples),
        boxes=len(boxes),
        volume_m3=float(mesh.volume),
        volume_ratio_to_seed=float(mesh.volume / original.bodies[0].visual.volume),
        watertight=bool(mesh.is_watertight),
        components=len(mesh.split()),
        euler_number=int(mesh.euler_number),
        removed_disconnected_cells=removed_islands,
        protected_grasp_cells_removed=lost_grasp,
        route=certs,
        route_certified=all(c["passed"] for c in certs),
        seed_route_still_passes=all(c["passed"] for c in baseline),
        seed_route=baseline,
        straight_controls=negative,
        operation_controls=operation_controls,
        all_straight_controls_blocked=not any(c["passed"] for c in negative),
        continuous_robot_path_verified=False,
        physical_execution_verified=False,
    )
    (output / "template.json").write_text(json.dumps(template, indent=2) + "\n")
    (output / "synthesis_report.json").write_text(json.dumps(report, indent=2) + "\n")
    mesh.export(output / "gold_inspection.ply")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("route", "seed_route", "straight_controls")
            }
        ),
        flush=True,
    )
    return template, report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--kind", choices=KINDS, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--pitch", type=float, default=0.0015)
    p.add_argument("--growth", type=float, default=0.006)
    p.add_argument("--parameter-mm", type=float, help="Family pivot offset, step height, or axial advance; experimental, not a certified range")
    a = p.parse_args()
    parameters = None if a.parameter_mm is None else {FAMILY_PARAMETERS[a.kind][0]: a.parameter_mm}
    synthesize(a.kind, a.output, pitch=a.pitch, growth=a.growth, parameters=parameters)
