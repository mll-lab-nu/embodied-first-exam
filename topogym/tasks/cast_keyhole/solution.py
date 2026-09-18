"""Continuous collision certificates for tutorial-stage Keyhole candidates.

The two canonical plates retain the original template and thickness. A search
result is a candidate until every connecting interval is certified here. This
module neither moves simulation bodies nor qualifies a robot recording.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .collision import CompoundCollision, Motion, certify_motion
from .geometry import ASSET_ROOT, extrude_slabs, load_template, outlines, polygon_slabs
from .route_probe import PoseSegment

STAGES = (
    "initial_quarter_turn", "engage_first_notch", "transfer_to_second_notch",
    "align_first_turn", "first_half_turn", "thread_lower_bore",
    "transfer_to_penultimate_notch", "transfer_to_last_notch",
    "align_second_turn", "second_half_turn", "withdraw",
)


def source_fingerprints(path):
    files = [Path(path),ASSET_ROOT/"template.json",ASSET_ROOT/"route_candidates.json",
             Path(__file__),Path(__file__).with_name("geometry.py"),Path(__file__).with_name("collision.py"),
             Path(__file__).with_name("route_probe.py")]
    return {str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def canonical_geometry(scale=3.):
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("Positive finite scale required")
    t = load_template()
    meshes, cells = [], []
    for name in ("gold", "silver"):
        mesh, parts = extrude_slabs(polygon_slabs(outlines(t,name)),t["thickness"])
        meshes.append(mesh.apply_scale(scale*.001))
        cells.append([p.apply_scale(scale*.001) for p in parts])
    return t, meshes, cells


def unpack_pose(value,scale):
    p, q = np.asarray(value["translation_mm"],dtype=float), np.asarray(value["quaternion_xyzw"],dtype=float)
    if (p.shape != (3,) or q.shape != (4,) or not np.isfinite(np.r_[p,q]).all()
            or abs(np.linalg.norm(q)-1) > 1e-6):
        raise ValueError("Invalid metric pose or non-unit quaternion")
    return Rotation.from_quat(q).as_matrix(), p*scale*.001


def read_motion(item,scale):
    r, p = unpack_pose(item["start"],scale)
    if item["type"] == "pose_segment":
        er, ep = unpack_pose(item["end"],scale)
        return PoseSegment(item["name"],r,er,p,ep)
    if item["type"] == "pivot":
        axis, pivot = np.asarray(item["axis"],dtype=float), np.asarray(item["pivot_mm"],dtype=float)
        angle = float(item["angle_rad"])
        if (axis.shape != (3,) or pivot.shape != (3,) or not np.isfinite(np.r_[axis,pivot,angle]).all()
                or abs(np.linalg.norm(axis)-1) > 1e-8):
            raise ValueError("Invalid pivot / axis")
        return Motion(item["name"],r,p,axis=axis,pivot=pivot*scale*.001,angle_rad=angle)
    raise ValueError("Unknown motion type")


def load_solution(path):
    data = json.loads(Path(path).read_text())
    if data.get("units") != "mm" or data.get("moving_piece") != "silver" or data.get("fixed_piece") != "gold":
        raise ValueError("Expected canonical gold-fixed, silver-moving millimetre poses")
    scale = float(data["scale"])
    _,meshes,cells = canonical_geometry(scale)
    motions = [read_motion(item,scale) for item in data["motions"]]
    if not motions:
        raise ValueError("Empty solution")
    return data,meshes,cells,motions


def certify(path,output):
    fingerprint = source_fingerprints(path)
    data,meshes,cells,motions = load_solution(path)
    errors = []
    stages = []
    for item in data["motions"]:
        if not stages or stages[-1] != item["stage"]:
            stages.append(item["stage"])
    if tuple(stages) != STAGES:
        errors.append("Missing or reordered tutorial stages")
    for a,b in zip(motions,motions[1:]):
        ar,ap = a.pose(1.);br,bp = b.pose(0.)
        if np.linalg.norm(ap-bp)>1e-9 or Rotation.from_matrix(ar@br.T).magnitude()>1e-8:
            errors.append(f"Disconnected motions: {a.name} / {b.name}")
    source = json.loads((ASSET_ROOT/"route_candidates.json").read_text())
    initial_r,initial_p = motions[0].pose(0.)
    if (not np.allclose(initial_r,source["initial_silver_rotation"],atol=1e-9,rtol=0)
            or not np.allclose(initial_p,np.array(source["initial_silver_translation_mm"])*data["scale"]*.001,atol=1e-9,rtol=0)):
        errors.append("Initial assembled pose differs from the documented candidate")
    for stage in ("first_half_turn","second_half_turn"):
        group = [m for m,item in zip(motions,data["motions"]) if item["stage"]==stage]
        if len(group)!=1 or not isinstance(group[0],Motion) or abs(abs(group[0].angle_rad)-np.pi)>1e-8:
            errors.append(f"Missing explicit half-turn: {stage}")
    collision = CompoundCollision(*cells)
    margin = .00015
    segments = []
    for i,motion in enumerate(motions):
        result = certify_motion(collision,motion,margin_m=margin)
        segments.append(dict(stage=data["motions"][i]["stage"],**result))
        if not result["passed"]:
            errors.append(f"Uncertified interval: {motion.name}")
        print(f"{i+1}/{len(motions)} {motion.name}: {result['passed']}",flush=True)
    final_gap = collision.gap(*motions[-1].pose(1.))
    if final_gap < .020:
        errors.append("Final separation lower bound must exceed 20 mm")
    if source_fingerprints(path) != fingerprint:
        errors.append("Source changed during certification")
    report = dict(scope="full geometric candidate following tutorial milestones; not robot execution",
        full_geometric_path_verified=not errors,errors=errors,stages=stages,segments=segments,
        scene_scale=data["scale"],clearance_margin_m=margin,final_separation_lower_bound_m=final_gap,
        fingerprint=fingerprint,
        initial_pose_is_documented_candidate=True,factory_pose_measured=False,geometry_modified=False,
        exact_official_panel_trajectory=False,physics_execution_verified=False,
        robot_grasp_verified=False,formal_demo_qualified=False)
    output = Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    return report


def require_current_full_certificate(solution,certificate):
    """Fail before starting physics if any route evidence is absent or stale."""
    report = json.loads(Path(certificate).read_text())
    if not report.get("full_geometric_path_verified") or report.get("errors"):
        raise ValueError("Full route geometry must pass first")
    data = json.loads(Path(solution).read_text())
    segments = report.get("segments",[])
    if (report.get("fingerprint") != source_fingerprints(solution)
            or report.get("stages") != list(STAGES)
            or report.get("scene_scale") != data.get("scale")
            or report.get("clearance_margin_m") != .00015
            or not np.isfinite(report.get("final_separation_lower_bound_m",np.nan))
            or report["final_separation_lower_bound_m"] < .020
            or len(segments) != len(data["motions"])
            or any(not s.get("passed") or s.get("name") != m["name"] or s.get("stage") != m["stage"]
                   or not np.isfinite(s.get("continuous_gap_lower_bound_m",np.nan))
                   or s["continuous_gap_lower_bound_m"] < .00015
                   for s,m in zip(segments,data["motions"]))):
        raise ValueError("Incomplete or stale full-route certificate")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    result = certify(args.solution,args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ("segments","fingerprint")},indent=2))
    if not result["full_geometric_path_verified"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
