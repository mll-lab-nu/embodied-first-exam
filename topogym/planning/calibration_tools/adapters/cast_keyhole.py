"""Keyhole candidates built from the existing slab and asset-writing primitives."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import trimesh

from ..contracts import UnsupportedCapability, digest


def preview(task, parameters, output):
    from topogym.assets.variation_resources import read_json
    from topogym.assets.geometry.cast_keyhole import (
        KeyholeAssembly, KeyholeBody, polygon_slabs, extrude_slabs,
        plate_assembly_transforms, geometry_report, write_body)
    from topogym.tasks.base import merge_parameters
    from topogym.utils.io import sha256_file, write_json_atomic
    if task.task_id != "cast_keyhole" or not task.geometry_resource:
        raise UnsupportedCapability("Geometry preview currently requires a frozen Cast Keyhole variant")
    allowed = {"rings_mm", "layers", "thickness_mm", "density_kg_m3", "gold_offset_z_mm", "scale"}
    if not isinstance(parameters, dict) or set(parameters) - allowed:
        raise ValueError(f"Geometry parameters must be among {sorted(allowed)}")
    original = read_json(task.geometry_resource)
    record = merge_parameters(original, parameters)
    for key in ("scale", "thickness_mm", "density_kg_m3"):
        if not np.isfinite(record[key]) or record[key] <= 0:
            raise ValueError(f"{key} must be positive")
    assembly = KeyholeAssembly(scale=record["scale"])
    assembly.template = deepcopy(assembly.template)
    assembly.template.update(template_id=record["id"] + "_development",
                             geometry_status="development_candidate_unqualified")
    assembly.bodies = []
    transforms = plate_assembly_transforms(record)
    sections = {}
    for name in ("gold", "silver"):
        layers = record.get("layers", {}).get(name, [dict(
            z_min_mm=-record["thickness_mm"]/2, z_max_mm=record["thickness_mm"]/2,
            rings_mm=record["rings_mm"][name])])
        layer_meshes, cells = [], []
        for layer in layers:
            lo, hi = layer["z_min_mm"], layer["z_max_mm"]
            rings = [np.asarray(r, dtype=float) for r in layer["rings_mm"]]
            if not np.isfinite([lo, hi]).all() or hi <= lo or any(
                    r.ndim != 2 or r.shape[1] != 2 or len(r) < 3 or not np.isfinite(r).all() for r in rings):
                raise ValueError("Invalid geometry layer")
            mesh, parts = extrude_slabs(polygon_slabs(rings), hi-lo)
            for part in [mesh, *parts]:
                part.apply_translation([0, 0, (hi+lo)/2])
                part.apply_scale(assembly.unit)
            layer_meshes.append(mesh)
            cells.extend(parts)
        mesh = layer_meshes[0] if len(layer_meshes) == 1 else trimesh.boolean.union(layer_meshes, engine="manifold")
        for part in [mesh, *cells]:
            part.apply_transform(transforms[name])
        color = tuple(record.get("visual_material", {}).get(name, assembly.template["colors"][f"keyhole_{name}"]))
        from trimesh.visual.material import PBRMaterial
        from trimesh.visual.texture import TextureVisuals
        mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)),
                                    material=PBRMaterial(baseColorFactor=color))
        assembly.bodies.append(KeyholeBody("keyhole_" + name, mesh, cells, color, record["rings_mm"][name]))
        # Exact planar contours, rather than an image pretending to be an engine frame.
        sections[name] = layers
    report = geometry_report(assembly)
    if not report["passed"]:
        raise ValueError(f"Candidate failed geometry validation: {report}")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    bodies = [write_body(output / body.name, body, record["density_kg_m3"]) for body in assembly.bodies]
    trimesh.Scene([b.visual for b in assembly.bodies]).export(output / "assembly.glb")
    write_json_atomic(output / "geometry.json", record)
    write_json_atomic(output / "sections.json", sections)
    manifest = dict(candidate_id=output.name, source_resource=task.geometry_resource,
                    base_sha256=digest(original), candidate_sha256=digest(record), parameters=parameters,
                    geometry=report, bodies=bodies, requires_rebuild=True,
                    physical_execution_verified=False,
                    assets={str(p.relative_to(output)): sha256_file(p) for p in sorted(output.rglob("*")) if p.is_file()})
    write_json_atomic(output / "manifest.json", manifest)
    return dict(manifest, output=str(output))
