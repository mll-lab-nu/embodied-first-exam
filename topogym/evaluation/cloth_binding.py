"""Pure-array diagnostics for a cloth's *actual* visual support table.

Material coordinates must come from the birth/rest material, in metres, in
particle/visual order after remeshing. They cannot be inferred from folded XYZ.
Passing these checks is not a contact, material-integrity or settling proof.
"""
from __future__ import annotations

import numpy as np


def audit_visual_binding(
    particle_positions_m, visual_positions_m, particle_material_uv_m,
    visual_material_uv_m, support_indices, support_weights, *,
    material_distance_limit_m, reconstruction_tolerance_m,
    material_reconstruction_tolerance_m, weight_sum_tolerance=1e-5,
):
    """Check entity-local supports, material locality and affine reconstruction.

    Shape/index/threshold errors raise ValueError. Nonfinite data produces a
    failed JSON-safe report. Negative affine weights and rank-two flat sheets
    are allowed. Locality checks include zero-weight supports: a selected
    neighbour outside the material patch is still an invalid binding candidate.
    Limits are explicit; there is no universal multiple of particle spacing.
    """
    limits = dict(material_distance_limit_m=material_distance_limit_m,
                  reconstruction_tolerance_m=reconstruction_tolerance_m,
                  material_reconstruction_tolerance_m=material_reconstruction_tolerance_m,
                  weight_sum_tolerance=weight_sum_tolerance)
    if any(not np.isfinite(v) or v < 0 for v in limits.values()):
        raise ValueError("Binding tolerances must be finite and nonnegative")
    p, v, puv, vuv, w = [np.asarray(x, dtype=float) for x in (
        particle_positions_m, visual_positions_m, particle_material_uv_m,
        visual_material_uv_m, support_weights)]
    idx = np.asarray(support_indices)
    for name, value, width in (("particles", p, 3), ("visual vertices", v, 3),
                               ("particle UV", puv, 2), ("visual UV", vuv, 2)):
        if value.ndim != 2 or value.shape[1] != width or not len(value):
            raise ValueError(f"Expected nonempty Nx{width} {name}")
    if len(puv) != len(p) or len(vuv) != len(v):
        raise ValueError("Material coordinates must match remeshed vertex order/count")
    if (idx.ndim != 2 or idx.shape[0] != len(v) or not idx.shape[1]
            or w.shape != idx.shape or idx.dtype.kind not in "iu"):
        raise ValueError("Expected matching VxK integer supports and weights")
    if (idx < 0).any() or (idx >= len(p)).any():
        raise ValueError("Visual support references a particle outside this entity")
    finite = all(np.isfinite(a).all() for a in (p, v, puv, vuv, w))
    report = dict(scope="visual_binding_only", actual_particle_count=len(p),
                  visual_vertex_count=len(v), support_count=idx.shape[1],
                  limits={k: float(value) for k, value in limits.items()},
                  checks={"finite": bool(finite)}, passed=False)
    if not finite:
        return report
    locality = np.linalg.norm(puv[idx]-vuv[:, None, :], axis=2)
    reconstructed = np.einsum("vk,vkj->vj", w, p[idx])
    flattened = np.einsum("vk,vkj->vj", w, puv[idx])
    error = np.linalg.norm(reconstructed-v, axis=1)
    flat_error = np.linalg.norm(flattened-vuv, axis=1)
    sums = abs(w.sum(axis=1)-1)
    amplification = abs(w).sum(axis=1)
    if not all(np.isfinite(a).all() for a in (locality, reconstructed, flattened, error, flat_error, sums, amplification)):
        report["checks"]["finite_arithmetic"] = False
        return report
    nonlocal_count = int(np.count_nonzero(locality > material_distance_limit_m))
    report.update(
        maximum_support_material_distance_m=float(locality.max()),
        nonlocal_support_count=nonlocal_count,
        maximum_reconstruction_error_m=float(error.max()),
        virtual_flatten_maximum_material_error_m=float(flat_error.max()),
        maximum_weight_sum_error=float(sums.max()),
        maximum_absolute_weight_sum=float(amplification.max()),
        negative_weight_count=int(np.count_nonzero(w < 0)),
    )
    report["checks"].update(
        material_locality=nonlocal_count == 0,
        position_reconstruction=bool(error.max() <= reconstruction_tolerance_m),
        material_reconstruction=bool(flat_error.max() <= material_reconstruction_tolerance_m),
        affine_weight_sum=bool(sums.max() <= weight_sum_tolerance),
    )
    report["passed"] = all(report["checks"].values())
    return report
