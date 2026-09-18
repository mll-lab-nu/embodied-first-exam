"""Load certified inverse-designed solids using the existing Keyhole entity frames."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from .geometry import ASSET_ROOT, KeyholeAssembly, KeyholeBody, geometry_report, write_body
from .inverse_variants import geometry_from_record, sha


def require_variant(geometry_path, motion=None):
    path=Path(geometry_path);folder=path.parent
    record=json.loads(path.read_text());certificate=json.loads((folder/"certificate.json").read_text())
    if (not certificate.get("passed") or certificate["geometry_sha256"]!=sha(path)
        or certificate["ik_input_sha256"]!=sha(folder/"ik_proposal.json")
        or certificate["proposal_sha256"]!=sha(folder/"proposal.json")
        or any(not s["passed"] or s["continuous_gap_lower_bound_m"]<.00015 for s in certificate["segments"])
        or certificate["final_separation_lower_bound_m"]<.02):
        raise ValueError("Missing or stale inverse-geometry certificate")
    for name,digest in certificate["source_fingerprints"].items():
        if sha(Path(__file__).with_name(name))!=digest:
            raise ValueError(f"Certificate implementation changed: {name}")
    if record["source_template_sha256"]!=sha(ASSET_ROOT/"template.json"):
        raise ValueError("The source template changed")
    if motion is not None:
        report=motion["report"]
        if report.get("geometry_sha256")!=sha(path) or not report.get("sampled_robot_scene_clearance_passed"):
            raise ValueError("Motion does not belong to these certified solids")
    return record,certificate


def generate_variant_assets(output,geometry_path):
    record,_=require_variant(geometry_path)
    meshes,cells=geometry_from_record(record)
    assembly=KeyholeAssembly(scale=record["scale"])
    assembly.template=deepcopy(assembly.template)
    assembly.template.update(template_id=record["id"],geometry_status="inverse_designed_from_varied_robot_trajectory",
        inverse_geometry_sha256=sha(geometry_path))
    assembly.bodies=[]
    rx=Rotation.from_euler("x",90,degrees=True).as_matrix()
    rz=Rotation.from_euler("z",90,degrees=True).as_matrix()
    for index,(name,mesh,parts) in enumerate(zip(("gold","silver"),meshes,cells)):
        transform=np.eye(4);transform[:3,:3]=rz@rx if index==0 else rx
        if index==0:transform[2,3]=assembly.template["gold_offset_z"]*assembly.unit
        for part in [mesh,*parts]:part.apply_transform(transform)
        material=record.get("visual_material",{})
        color=tuple(material.get(name,assembly.template["colors"][f"keyhole_{name}"]))
        assembly.template["colors"][f"keyhole_{name}"]=list(color)
        mesh.visual=TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),material=PBRMaterial(
            baseColorFactor=color,metallicFactor=material.get("metallic",.8),roughnessFactor=material.get("roughness",.3)))
        assembly.bodies.append(KeyholeBody(f"keyhole_{name}",mesh,parts,color,record["rings_mm"][name]))
    report=geometry_report(assembly)
    if not report["passed"]:raise ValueError(report)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    report["bodies"]=[write_body(output/b.name,b,record["density_kg_m3"]) for b in assembly.bodies]
    report.update(geometry_modified=True,inverse_geometry_sha256=sha(geometry_path),
        source_record=str(Path(geometry_path).resolve()))
    for name,data in (("template.json",assembly.template),("inverse_geometry.json",record),("geometry_report.json",report)):
        (output/name).write_text(json.dumps(data,indent=2)+"\n")
    (output/"sources.json").write_text((ASSET_ROOT/"sources.json").read_text())
    scene=trimesh.Scene()
    for body in assembly.bodies:scene.add_geometry(body.visual,node_name=body.name,geom_name=body.name)
    scene.export(output/"assembly.glb")
    return assembly,report
