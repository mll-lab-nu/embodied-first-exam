"""Certify partial geometric motions, with explicit missing-route gates."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .collision import CompoundCollision, Motion, certify_motion
from .geometry import ASSET_ROOT, load_template, outlines, polygon_slabs, extrude_slabs


@dataclass
class PoseSegment:
    name: str
    start_rotation: np.ndarray
    end_rotation: np.ndarray
    start_translation: np.ndarray
    end_translation: np.ndarray

    def pose(self, u):
        delta = Rotation.from_matrix(self.end_rotation@self.start_rotation.T).as_rotvec()
        return (Rotation.from_rotvec(delta*u).as_matrix()@self.start_rotation,
                (1-u)*self.start_translation+u*self.end_translation)

    def speed_bound(self, points):
        angle = Rotation.from_matrix(self.end_rotation@self.start_rotation.T).magnitude()
        return float(angle*np.linalg.norm(points,axis=1).max()
                     +np.linalg.norm(self.end_translation-self.start_translation))


def candidates():
    source = json.loads((ASSET_ROOT/"route_candidates.json").read_text())
    unit = source["scale"]*.001
    template = load_template()
    meshes, cells = [], []
    for name in ("gold", "silver"):
        mesh, parts = extrude_slabs(polygon_slabs(outlines(template,name)),template["thickness"])
        meshes.append(mesh.apply_scale(unit))
        cells.append([part.apply_scale(unit) for part in parts])
    collision = CompoundCollision(*cells)
    first = Motion("cap_quarter_turn",np.array(source["initial_silver_rotation"],dtype=float),
        np.array(source["initial_silver_translation_mm"])*unit,
        axis=np.array(source["quarter_turn_axis"],dtype=float),
        angle_rad=np.deg2rad(source["quarter_turn_degrees"]),
        pivot=np.array(source["quarter_turn_pivot_mm"])*unit)
    down = Rotation.from_euler("x",-90,degrees=True).as_matrix()
    poses = [(Rotation.from_euler("z",q["yaw_rad"]).as_matrix()@down,
              np.array(q["translation_mm"])*unit) for q in source["first_notch_waypoints"]]
    end = first.pose(1.)
    if not np.allclose(end[0],poses[0][0],atol=1e-10) or not np.allclose(end[1],poses[0][1],atol=1e-10):
        raise ValueError("Candidate motions are disconnected")
    motions = [first]+[PoseSegment(f"first_notch_approach_{i+1}",a[0],b[0],a[1],b[1])
                       for i,(a,b) in enumerate(zip(poses,poses[1:]))]
    # A clear target and start do not prove a route between them.
    wrong = PoseSegment("rejected_direct_notch_transfer",poses[-1][0],down,poses[-1][1],
                        np.array([13.15,1.1,11.85])*unit)
    return source,meshes,collision,motions,wrong


def probe(output):
    source,meshes,collision,motions,wrong = candidates()
    margin = .00015  # 0.05 mm in the authored dimensions; scene scale is 3.
    results = [certify_motion(collision,m,margin_m=margin) for m in motions]
    negative = certify_motion(collision,wrong,margin_m=margin)
    report = dict(scope="partial geometric candidate; not a physics trajectory",scale=source["scale"],
        partial_approach_certified=all(r["passed"] for r in results),segments=results,
        negative_control=negative,margin_m=margin,
        source_correspondence=source["correspondence"],
        fingerprint={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (ASSET_ROOT/"template.json",ASSET_ROOT/"route_candidates.json",Path(__file__),
             Path(__file__).with_name("collision.py"),Path(__file__).with_name("geometry.py"))},
        missing_stages=["first to second notch with vertical slot changes", "first in-plane half-turn",
            "lower slot traverse", "second in-plane half-turn", "exit and full separation"],
        official_route_verified=False,robot_grasp_verified=False,formal_demo_qualified=False,
        search_failure_is_not_unsolvability_proof=True)
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    (output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    # Export three diagnostic projections of the certified partial motion only.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    selected = [motions[0].pose(0.),motions[0].pose(1.),motions[-1].pose(1.)]
    fig,axes = plt.subplots(3,3,figsize=(11,10))
    for row,(i,j,label) in enumerate(((0,1,"XY / top"),(0,2,"XZ / front"),(1,2,"YZ / side"))):
        for col,(rotation,translation) in enumerate(selected):
            ax = axes[row,col]
            for mesh,R,t,color in ((meshes[0],np.eye(3),np.zeros(3),"#ba903e"),
                                   (meshes[1],rotation,translation,"#8095a4")):
                vertices = (mesh.vertices@R.T+t)*1000
                polygons = vertices[mesh.faces][...,[i,j]]
                ax.add_collection(PolyCollection(polygons,facecolor=color,edgecolor=color,linewidth=.1,alpha=.6))
                ax.update_datalim(vertices[:,[i,j]])
            ax.autoscale_view(); ax.set_aspect("equal"); ax.set_xlabel(label+" (scene mm)")
            if row == 0:
                ax.set_title(("Candidate linked start","Quarter turn end","First notch candidate")[col])
    fig.suptitle("Cast Keyhole: partial geometric checks only — no physics / no robot solution")
    fig.tight_layout()
    fig.savefig(output/"partial_route_views.png",dpi=150)
    plt.close(fig)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    result = probe(args.output)
    print(json.dumps(result,indent=2))
    if not result["partial_approach_certified"] or result["negative_control"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
