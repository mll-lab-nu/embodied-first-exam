"""Search a collision-checked rigid-body escape; never changes asset geometry."""
import argparse
import hashlib
import json
from pathlib import Path

import fcl
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from .geometry import ROOT


class CollisionOracle:
    def __init__(self, asset_dir):
        self.objects = []
        self.meshes = []
        self.calls = 0
        self.asset_dir = Path(asset_dir)
        for name in ("cage", "hedgehog"):
            mesh = trimesh.util.concatenate([trimesh.load(p, force="mesh") for p in
                sorted(self.asset_dir.glob(f"{name}_collision_*.obj"))])
            model = fcl.BVHModel()
            model.beginModel(len(mesh.vertices), len(mesh.faces))
            model.addSubModel(mesh.vertices, mesh.faces)
            model.endModel()
            self.objects.append(fcl.CollisionObject(model))
            self.meshes.append(mesh)

    def distance(self, q):
        self.calls += 1
        rotation = Rotation.from_quat(q[3:]).as_matrix()
        self.objects[1].setTransform(fcl.Transform(rotation, q[:3]))
        return fcl.distance(*self.objects, fcl.DistanceRequest(), fcl.DistanceResult())


def interpolate(a, b, resolution=.0002):
    ra, rb = Rotation.from_quat(a[3:]), Rotation.from_quat(b[3:])
    delta = (rb * ra.inv()).as_rotvec()
    # Upper bound on any point's travel: translation plus radius * angle.
    travel = np.linalg.norm(b[:3]-a[:3]) + .092*np.linalg.norm(delta)
    count = max(1, int(np.ceil(travel/resolution)))
    for t in np.linspace(0, 1, count+1):
        yield np.r_[a[:3]+t*(b[:3]-a[:3]), (Rotation.from_rotvec(t*delta)*ra).as_quat()]


def search(oracle, start, goal, seconds=60, margin=.0004, bounds=None, extra_valid=None):
    from ompl import base as ob, geometric as og
    space = ob.SE3StateSpace()
    limits = ob.RealVectorBounds(3)
    for i, (lo, hi) in enumerate(bounds or [(-.035,.17),(-.032,.032),(-.052,.052)]):
        limits.setLow(i, lo)
        limits.setHigh(i, hi)
    space.setBounds(limits)
    space.setSubspaceWeight(1, .055)
    setup = og.SimpleSetup(space)
    def values(state):
        r = state.rotation()
        return np.array([state.getX(),state.getY(),state.getZ(),r.x,r.y,r.z,r.w])
    def valid(state):
        q = values(state)
        return bool((extra_valid is None or extra_valid(q)) and oracle.distance(q) > margin)
    setup.setStateValidityChecker(valid)
    setup.getSpaceInformation().setStateValidityCheckingResolution(.0005)
    states=[]
    for q in (start, goal):
        state=space.allocState()
        state.setXYZ(*q[:3]); r=state.rotation();r.x,r.y,r.z,r.w=q[3:]
        states.append(state)
    setup.setStartAndGoalStates(*states)
    planner=og.RRTConnect(setup.getSpaceInformation())
    planner.setRange(.008)
    setup.setPlanner(planner)
    setup.solve(seconds)
    if not setup.haveExactSolutionPath():
        return None
    setup.simplifySolution(3.)
    return [values(s) for s in setup.getSolutionPath().getStates()]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runs/environment_bootstrap/hedgehog_in_cage/classic_wood")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--mode", choices=["display", "constructive"], default="display")
    parser.add_argument("--verify", metavar="PATH_JSON", help="Recheck a saved witness without a new random search")
    args=parser.parse_args()
    output=ROOT/args.output
    oracle=CollisionOracle(output/"assets")
    if args.verify:
        source=output/args.verify
        witness=json.loads(source.read_text())
        path=[np.asarray(q) for q in witness["path"]]
        resolution=.00005
        radius=float(np.linalg.norm(oracle.meshes[1].vertices,axis=1).max())
        if radius>.092:
            raise ValueError("The interpolation radius bound does not cover this geometry")
        distances=[oracle.distance(q) for a,b in zip(path[:-1],path[1:]) for q in interpolate(a,b,resolution)]
        minimum=float(min(distances))
        direct_collision=None
        for x in np.arange(path[0][0],path[-1][0]+.00025,.00025):
            q=path[0].copy();q[0]=x
            if oracle.distance(q)<=0:
                direct_collision=float(x)
                break
        result=dict(passed=minimum>resolution,source=source.name,
            minimum_sampled_clearance_m=minimum,swept_motion_bound_m=resolution,
            continuous_clearance_lower_bound_m=minimum-resolution,checked_samples=len(distances),
            fixed_orientation_straight_pull_collision_x_m=direct_collision,
            asset_manifest_sha256=hashlib.sha256((output/"assets/sha256.json").read_bytes()).hexdigest(),
            witness_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            scope="geometry_only; robot execution and release require separate dynamic evidence")
        (output/"escape_verification.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result),flush=True)
        if not result["passed"]:
            raise SystemExit(1)
        return
    initial=json.loads((output/"assets/asset_report.json").read_text())["initial_pose"]
    start=np.r_[initial["position_m"],np.array(initial["quaternion_wxyz"])[[1,2,3,0]]]
    # Candidate poses guide the widest-window search only. They are rechecked
    # against current meshes and cannot be accepted as a connected route.
    prior=ROOT/"runs/environment-solvability/hedgehog_in_cage/classic_initial/gate_candidates.jsonl"
    gates=[]
    for line in prior.read_text().splitlines():
        pose=np.array(json.loads(line)["pose"])
        gates.append(np.r_[pose[:3],Rotation.from_rotvec(pose[3:]).as_quat()])
    if args.mode == "constructive":
        start=gates[0]
    goal=gates[-1].copy();goal[0]=.165
    print(json.dumps(dict(mode=args.mode,start=start.tolist(),start_clearance=oracle.distance(start),
        gate_clearances=[oracle.distance(q) for q in gates])),flush=True)
    path=search(oracle,start,goal,args.seconds)
    if path is None:
        # The official turning sequence suggests staged progress through the
        # window; check each connection instead of interpolating unchecked poses.
        path=[start]
        for gate in gates[1:]+[goal]:
            part=search(oracle,path[-1],gate,args.seconds/3)
            if part is None:
                path=None
                break
            path.extend(part[1:])
    result=dict(found=path is not None, mode=args.mode, validity_checks=oracle.calls,
        geometry_modified=False, robot_feasibility_verified=False, dynamics_verified=False,
        asset_manifest_sha256=hashlib.sha256((output/"assets/sha256.json").read_bytes()).hexdigest())
    if path is not None:
        dense=np.asarray([q for a,b in zip(path[:-1],path[1:]) for q in interpolate(a,b)])
        distances=np.array([oracle.distance(q) for q in dense])
        result.update(minimum_sampled_clearance_m=float(distances.min()),
            swept_motion_bound_m=.0002, continuous_clearance_lower_bound_m=float(distances.min()-.0002),
            checked_samples=len(dense), path=[q.tolist() for q in path],
            initial_pose_changed=args.mode=="constructive")
        result["found"]=bool(distances.min() > .0002)
        if result["found"]:
            np.savez(output/f"escape_{args.mode}.npz",poses=dense,clearances=distances)
    (output/f"escape_{args.mode}.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="path"}),flush=True)


if __name__=="__main__":
    main()
