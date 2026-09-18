"""Certify extraction from the exact initial pose built by KeyholeAssembly.

This authored lower-bore start differs from the commercial factory start. The
certificate proves this instance, without imposing the other candidate's stages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .collision import CompoundCollision, certify_motion
from .geometry import ASSET_ROOT, KeyholeAssembly
from .solution import canonical_geometry, load_solution


def initial_relative_pose(scale=3.):
    """Recover each canonical-to-scene transform from the actual mesh vertices."""
    assembly = KeyholeAssembly(scale=scale)
    _, meshes, _ = canonical_geometry(scale)
    transforms = []
    for mesh, body in zip(meshes, assembly.bodies):
        x, y = np.asarray(mesh.vertices), np.asarray(body.visual.vertices)
        u, _, vt = np.linalg.svd((x-x.mean(0)).T @ (y-y.mean(0)))
        r = vt.T @ u.T
        if np.linalg.det(r) < 0:
            vt[-1] *= -1
            r = vt.T @ u.T
        t = y.mean(0)-r@x.mean(0)
        if np.max(np.abs(x@r.T+t-y)) > 1e-10:
            raise ValueError("Canonical geometry does not match the scene solids")
        transforms.append((r,t))
    (rg,tg),(rs,ts) = transforms
    return rg.T@rs, rg.T@(ts-tg)


def fingerprints(path):
    files = [Path(path), ASSET_ROOT/"template.json", Path(__file__)]
    files += [Path(__file__).with_name(n) for n in
              ("geometry.py", "collision.py", "solution.py", "route_probe.py")]
    return {str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def certify(path, output):
    before = fingerprints(path)
    data, _, cells, motions = load_solution(path)
    errors = []
    r0,t0 = initial_relative_pose(data["scale"])
    r,t = motions[0].pose(0)
    initial_error = float(np.linalg.norm(t-t0))
    initial_angle = float(Rotation.from_matrix(r@r0.T).magnitude())
    if initial_error > 1e-9 or initial_angle > 1e-8:
        errors.append("Path does not start at the actual KeyholeAssembly initial pose")
    for a,b in zip(motions,motions[1:]):
        ar,at=a.pose(1);br,bt=b.pose(0)
        if np.linalg.norm(at-bt)>1e-9 or Rotation.from_matrix(ar@br.T).magnitude()>1e-8:
            errors.append(f"Disconnected motions: {a.name} / {b.name}")
    collision = CompoundCollision(*cells)
    segments = []
    margin = .00015
    for i,m in enumerate(motions):
        result = certify_motion(collision,m,margin_m=margin)
        segments.append(dict(stage=data["motions"][i]["stage"],**result))
        if not result["passed"]:
            errors.append(f"Uncertified interval: {m.name}")
        print(f"{i+1}/{len(motions)} {m.name}: {result['passed']}",flush=True)
    gap = float(collision.gap(*motions[-1].pose(1)))
    if gap < .020:
        errors.append("Final separation lower bound is below 20 mm")
    if before != fingerprints(path):
        errors.append("Inputs changed during certification")
    report = dict(certificate_type="current_instance_path_v1",
        scope="continuous geometric extraction of the actual authored KeyholeAssembly initial instance",
        full_geometric_path_verified=not errors,errors=errors,segments=segments,
        scene_scale=data["scale"],clearance_margin_m=margin,final_separation_lower_bound_m=gap,
        initial_position_error_m=initial_error,initial_rotation_error_rad=initial_angle,
        initial_pose_verified_against_scene=True,geometry_modified=False,
        factory_pose_measured=False,exact_official_panel_trajectory=False,
        physics_execution_verified=False,robot_grasp_verified=False,formal_demo_qualified=False,
        fingerprint=before)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    return report


def require_current_instance_certificate(solution, certificate):
    report=json.loads(Path(certificate).read_text())
    data=json.loads(Path(solution).read_text())
    segments=report.get("segments",[])
    if (report.get("certificate_type")!="current_instance_path_v1"
            or not report.get("full_geometric_path_verified") or report.get("errors")
            or not report.get("initial_pose_verified_against_scene")
            or report.get("fingerprint")!=fingerprints(solution)
            or report.get("scene_scale")!=data.get("scale")
            or report.get("clearance_margin_m")!=.00015
            or not np.isfinite(report.get("final_separation_lower_bound_m",np.nan))
            or report["final_separation_lower_bound_m"]<.020
            or len(segments)!=len(data["motions"])
            or any(not s.get("passed") or s.get("name")!=m["name"] or s.get("stage")!=m["stage"]
                   or not np.isfinite(s.get("continuous_gap_lower_bound_m",np.nan))
                   or s["continuous_gap_lower_bound_m"]<.00015
                   for s,m in zip(segments,data["motions"]))):
        raise ValueError("Incomplete, failing, or stale current-instance certificate")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report=certify(args.solution,args.output)
    print(json.dumps({k:v for k,v in report.items() if k not in ("segments","fingerprint")},indent=2))
    if not report["full_geometric_path_verified"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
