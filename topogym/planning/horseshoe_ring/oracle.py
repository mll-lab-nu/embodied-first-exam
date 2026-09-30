"""Independently check an object-space oracle against the current assets.

Historical references are inputs, never imported executable code. Each body
uses linear COM translation and shortest SLERP. Adaptive interval bounds
cover every point of each rigid surface, not only sampled poses. This does
not establish a path from the newer settled birth state, passive chain
dynamics, robot reachability, table clearance or native Task success.
"""
from itertools import combinations
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.geometry import matrix, interpolate
from topogym.solvers.collision.triangle_meshes import TriangleMeshPair


def load_reference(path, assembly):
    path = Path(path)
    raw = path.read_bytes()
    data = json.loads(raw)
    if data['template'] != assembly.template or data['scale'] != assembly.scale:
        raise ValueError('Object reference does not match current geometry and scale')
    names = {b.name for b in assembly.bodies}
    frames = []
    for frame in data['frames']:
        if set(frame) != names:
            raise ValueError('Object reference must include every puzzle body')
        poses = {}
        for name, body in frame.items():
            p, q = np.asarray(body['pos'], float), np.asarray(body['quat'], float)
            if p.shape != (3,) or q.shape != (4,) or not np.isfinite(np.r_[p,q]).all() or not np.isclose(q@q, 1.):
                raise ValueError('Invalid object reference pose')
            poses[name] = (p, Rotation.from_quat(q))
        frames.append(poses)
    if len(frames) < 2:
        raise ValueError('A motion reference needs at least two frames')
    for body in assembly.bodies:
        p,r=frames[0][body.name]
        if np.linalg.norm(p-body.visual.center_mass)>1e-9 or r.magnitude()>1e-9:
            raise ValueError('Reference must start at the canonical assembly qualified by the geometry report')
    return frames, dict(source=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(),
                        frames=len(frames), fold_end_index=data['fold_end_index'],initial_matches_canonical_assembly=True)


def certify_reference(meshes, frames, *, margin_m=.00005, distance_error_m=.000001, max_depth=20, progress=None,
                      initial_geometry=None):
    if not 0 < distance_error_m < margin_m or max_depth < 1:
        raise ValueError('Positive numerical error and a larger clearance margin are required')
    pairs = {pair:TriangleMeshPair([meshes[n] for n in pair]) for pair in combinations(meshes, 2)}
    radii = {n:float(np.linalg.norm(m.vertices, axis=1).max()) for n,m in meshes.items()}
    minimum, queries, leaves, failures = float('inf'), 0, 0, []
    edge_bounds = []
    for index, (start, end) in enumerate(zip(frames[:-1], frames[1:])):
        edge_minimum = float('inf')
        travel = {n:float(np.linalg.norm(end[n][0]-start[n][0])+radii[n]*(end[n][1]*start[n][1].inv()).magnitude())
                  for n in meshes}
        for (a,b), checker in pairs.items():
            stack = [(0.,1.,0)]
            while stack:
                lo,hi,depth = stack.pop();u=(lo+hi)/2
                pa,pb = interpolate(start[a],end[a],u),interpolate(start[b],end[b],u)
                gap=checker.clearance([matrix(*pa),matrix(*pb)]);queries+=1
                lower=gap-distance_error_m-(travel[a]+travel[b])*(hi-lo)/2
                if lower>margin_m:
                    edge_minimum=min(edge_minimum,lower);leaves+=1
                elif gap<=margin_m+distance_error_m or depth>=max_depth:
                    failures.append(dict(edge=index,bodies=[a,b],fraction=u,gap_m=gap,depth=depth,
                                         reason='intersection_or_insufficient_clearance' if gap<=margin_m+distance_error_m else 'unresolved_interval'))
                    break
                else:
                    stack.extend([(lo,u,depth+1),(u,hi,depth+1)])
            if failures:break
        if failures:break
        edge_bounds.append(edge_minimum);minimum=min(minimum,edge_minimum)
        if progress and index%100==0:progress(index,queries,minimum)
    return dict(passed=not failures, continuous_surface_clearance=not failures, edges_checked=len(edge_bounds),
                requested_margin_m=margin_m, distance_error_m=distance_error_m,
                minimum_clearance_lower_bound_m=minimum if np.isfinite(minimum) else None,
                edge_clearance_lower_bounds_m=edge_bounds, queries=queries, leaves=leaves, failures=failures,
                interpolation='linear COM translation and shortest quaternion SLERP',
                coverage='current visual surfaces and enclosed authored collision primitives; inter-body surfaces only',
                initial_solid_containment_checked=bool(initial_geometry and initial_geometry['passed']),
                canonical_initial_geometry=initial_geometry,
                settled_birth_prefix_verified=False, robot_execution_verified=False,
                passive_chain_dynamics_verified=False, lab_obstacles_verified=False, task_success=False)


def balanced_fold(frames, anchor, *, start_rotation=None):
    """Distribute the relative shoe turn between both wrists.

    Common rigid transforms preserve the certified inter-object geometry.
    Their interpolation still needs its own robot and table check. Quaternion
    signs are unwrapped before taking a square root to avoid jumps at pi.
    """
    anchor=np.asarray(anchor,float)
    common=Rotation.identity() if start_rotation is None else start_rotation
    previous=np.array([0.,0.,0.,1.]);result=[]
    for frame in frames:
        left=frame['horseshoe_left'];right=frame['horseshoe_right']
        relative=left[1].inv()*right[1]
        q=relative.as_quat()
        if q@previous<0:q=-q
        previous=q
        xyz,w=q[:3],q[3];norm=np.linalg.norm(xyz)
        vector=np.zeros(3) if norm<1e-12 else xyz/norm*(2*np.arctan2(norm,w))
        rotation=common*Rotation.from_rotvec(-.5*vector)*left[1].inv()
        center=(left[0]+right[0])/2
        result.append({n:(anchor+rotation.apply(p-center),rotation*r) for n,(p,r) in frame.items()})
    return result


def expand_coupled_plan(reference, plan):
    """Preserve every source relative pose between sparse coupled IK samples."""
    from topogym.planning.rigid_reference.feedback import body_pose
    if 'world_frames' in plan:
        if not plan['passed'] or len(plan['world_frames'])<2:
            raise ValueError('Dense world motion did not pass its checks')
        frames=[]
        for frame in plan['world_frames']:
            if set(frame)!=set(reference[0]):raise ValueError('Dense world frame omits a puzzle body')
            for value in frame.values():
                p=np.asarray(value['position_m']);q=np.asarray(value['quaternion_wxyz'])
                if p.shape!=(3,) or q.shape!=(4,) or not np.isfinite(np.r_[p,q]).all() or not np.isclose(q@q,1.):
                    raise ValueError('Invalid dense world pose')
            frames.append({n:body_pose(v) for n,v in frame.items()})
        return frames
    samples=plan['frames']
    if not plan['passed'] or not samples or samples[0]['reference_index']!=0:
        raise ValueError('A passed coupled plan starting at reference zero is required')
    result=[];cursor=0
    for index in range(samples[-1]['reference_index']+1):
        while cursor+1<len(samples)-1 and samples[cursor+1]['reference_index']<index:cursor+=1
        a,b=samples[cursor],samples[min(cursor+1,len(samples)-1)]
        lo,hi=a['reference_index'],b['reference_index']
        u=0. if hi==lo else (index-lo)/(hi-lo)
        wp,wr=interpolate(body_pose(a['bodies']['horseshoe_left']),body_pose(b['bodies']['horseshoe_left']),u)
        lp,lr=reference[index]['horseshoe_left'];common=wr*lr.inv()
        result.append({n:(wp+common.apply(p-lp),common*r) for n,(p,r) in reference[index].items()})
    return result
