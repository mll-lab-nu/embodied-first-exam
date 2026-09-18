"""Audit the final forward aperture passage in a saved physical trajectory.

This is a sampled geometric diagnostic, complementary to native per-step
contact checks. Temporal interpolation is used only here, never for videos or
physical execution. Earlier approaches may cross the ring plane outside the
hole and retract; each material sample's LAST forward crossing must use it.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from .geometry import FiberLayout


def final_crossings(times, points, center):
    """Return last negative-to-positive plane crossings for material samples."""
    times = np.asarray(times)
    relative = np.asarray(points) - np.asarray(center)
    before, after = relative[:-1], relative[1:]
    forward = (before[..., 0] < 0) & (after[..., 0] >= 0)
    indices = np.where(forward, np.arange(len(forward))[:, None], -1).max(axis=0)
    found = indices >= 0
    safe = np.maximum(indices, 0)
    columns = np.arange(points.shape[1])
    a, b = before[safe, columns], after[safe, columns]
    denominator = b[:, 0] - a[:, 0]
    fraction = np.divide(-a[:, 0], denominator, out=np.zeros_like(denominator), where=denominator != 0)
    crossed = a + fraction[:, None] * (b - a)
    crossing_times = times[safe] + fraction * (times[safe + 1] - times[safe])
    return found, np.linalg.norm(crossed[:, 1:], axis=-1), crossing_times


def assess(run, spacing_m=.0005):
    run = Path(run)
    if spacing_m <= 0:
        raise ValueError("Material sampling spacing must be positive")
    cfg = OmegaConf.load(run / "config.yaml")
    layout = FiberLayout(**cfg.task.geometry)
    report = json.loads((run / "report.json").read_text())
    center = np.array([*cfg.task.trunk_origin_xy_m,
        float(cfg.env.frames.table_surface.origin[2]) + float(cfg.task.axis_height_m)])
    center[0] += layout.trunk_length_m + float(cfg.task.ring_distance_from_roots_m)
    with np.load(run / "trajectory.npz") as archive:
        times, fibers = archive["time_s"], archive["fibers"]
    if len(times) < 2 or not np.isfinite(fibers).all() or np.any(np.diff(times) < 0):
        raise ValueError("Require a finite chronological trajectory from reset")
    subdivisions = int(np.ceil(layout.fiber_length_m / layout.fiber_segments / spacing_m))
    fractions = np.arange(subdivisions) / subdivisions
    tolerance = float(report["plan"]["fine_contact_penetration_limit_m"])
    strands = []
    for wire in range(layout.fiber_count):
        vertices = fibers[:, wire]
        interior = vertices[:, :-1, None, :] + fractions[None, None, :, None] * np.diff(vertices, axis=1)[:, :, None, :]
        points = np.concatenate((interior.reshape(len(times), -1, 3), vertices[:, -1:, :]), axis=1)
        found, radii, crossing_times = final_crossings(times, points, center)
        outside = radii + layout.fiber_radius_m - layout.minimum_aperture_radius
        initial_near = bool((points[0, :, 0] + layout.fiber_radius_m < center[0] - layout.ring_tube_radius_m).all())
        final_beyond = bool((points[-1, :, 0] - layout.fiber_radius_m > center[0] + layout.ring_tube_radius_m).all())
        valid = found & (outside <= tolerance)
        worst = int(np.argmax(np.where(found, outside, np.inf)))
        strands.append(dict(strand=wire, sampled_material_points=points.shape[1],
            initial_entirely_near=initial_near, final_entirely_beyond=final_beyond,
            every_sample_crossed_forward=bool(found.all()), every_last_crossing_inside_with_contact_tolerance=bool(valid.all()),
            max_outer_crossing_radius_m=float((radii[found] + layout.fiber_radius_m).max()) if found.any() else None,
            min_conservative_aperture_clearance_m=float(-outside[found].max()) if found.any() else None,
            failed_sample_indices=np.flatnonzero(~valid).tolist(),
            worst_sample_index=worst, worst_sample_crossing_time_s=float(crossing_times[worst]) if found[worst] else None,
            passed=initial_near and final_beyond and bool(valid.all())))
    return dict(scope="sampled final forward material passage; supplements native per-step contact checks; not a continuous-time collision certificate",
        source_directory=str(run), trajectory_sha256=hashlib.sha256((run / "trajectory.npz").read_bytes()).hexdigest(),
        report_sha256=hashlib.sha256((run / "report.json").read_bytes()).hexdigest(),
        sampled_passage_passed=all(s["passed"] for s in strands),
        max_saved_time_gap_s=float(np.diff(times).max()), nominal_material_sample_spacing_m=layout.fiber_length_m/layout.fiber_segments/subdivisions,
        temporal_interpolation="linear between saved physical observations, diagnostic only",
        ring_center_m=center.tolist(), conservative_aperture_radius_m=layout.minimum_aperture_radius,
        fine_radius_m=layout.fiber_radius_m, contact_penetration_tolerance_m=tolerance, strands=strands)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = assess(args.run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "strands"}, indent=2))
    if not result["sampled_passage_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
