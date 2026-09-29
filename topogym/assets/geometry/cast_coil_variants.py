"""Pure asset geometry retained from the previous task generation pipeline."""

from __future__ import annotations




import numpy as np




KINDS = ("eccentric_turn", "split_turn_offset", "axial_screw_turn")

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







"""Pure asset geometry retained from the previous task generation pipeline."""


from copy import deepcopy

import hashlib

import json

import numpy as np

from topogym.assets.geometry.cast_coil import CoilAssembly, partition_solid

PRESETS = {
    "face_small": dict(face_scale=0.95, depth_scale=1.0, corner_cut_ratio=0.0),
    "depth_thick": dict(face_scale=1.0, depth_scale=1.10, corner_cut_ratio=0.0),
    "corner_cut": dict(face_scale=1.0, depth_scale=1.0, corner_cut_ratio=0.25),
}

def coordinate_scale(template):
    params = template.get("appearance_design", {}).get("parameters", {})
    s, d = params.get("face_scale", 1.0), params.get("depth_scale", 1.0)
    return np.array([s, d, s], dtype=float)

def corner_cuts(length, *, pitch=0.00075):
    """Inward staircase at four x/z outer corners, extruded through y."""
    if length == 0:
        return []
    n = int(round(length / pitch))
    if not np.isclose(n * pitch, length, atol=1e-12, rtol=0):
        raise ValueError("This prototype cuts corners on a 0.75 mm grid")
    cuts = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            for i in range(n):
                bounds = np.array(
                    [
                        [0.051 - length + i * pitch, -0.1, 0.051 - (i + 1) * pitch],
                        [0.052, 0.1, 0.052],
                    ]
                )
                cuts.append(np.sort(bounds * [sx, 1, sz], axis=0))
    return np.round(cuts, 12)

def create_template(kind):
    parameters = PRESETS[kind]
    original = CoilAssembly()
    template = deepcopy(original.template)
    s, d, q = (parameters[k] for k in ("face_scale", "depth_scale", "corner_cut_ratio"))
    scale = np.array([s, d, s])
    cuts = corner_cuts(0.021 * q)
    boxes = {}
    for body in original.bodies:
        _, cells = partition_solid(np.round(body.boxes, 12), cuts)
        boxes[body.name] = (cells * scale / original.unit).tolist()
    for key in (
        "outer_width",
        "band_width",
        "bridge_height",
        "bridge_center_clearance",
        "relief_width",
        "relief_depth",
    ):
        template[key] *= s
    for key in ("layer_thickness", "layer_clearance"):
        template[key] *= d
    template.update(
        template_id=f"cast_coil_appearance_{kind}_v1",
        geometry_status="single_parameter_appearance_of_verified_original_prototype",
        authored_boxes_mm=boxes,
        appearance_design=dict(
            kind=kind,
            parameters=parameters,
            seed_template_id=original.template["template_id"],
            seed_archive="2026-09-17_aloha_full",
            seed_template_sha256=hashlib.sha256(
                json.dumps(
                    original.template, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
            changed_parameters=[
                k
                for k, v in parameters.items()
                if v != (0.0 if k == "corner_cut_ratio" else 1.0)
            ],
            corner_cut_length_m=0.021 * s * q,
            corner_method="inward 0.75 mm orthogonal staircase in seed coordinates; not a smooth bevel",
            coordinate_scale=scale.tolist(),
            inherited_route="original slide, quarter-turn, extraction; transformed translations and pivot",
        ),
    )
    return template
