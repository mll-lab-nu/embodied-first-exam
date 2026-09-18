"""Repair discontinuities in a candidate's fixed-obstacle extraction phase."""
from copy import deepcopy

import fcl
import numpy as np
from scipy.spatial.transform import Rotation

from .independent_motion import IndependentWitness, interpolate


def segment_clear(model, a, b, margin_m=.0001, depth=16):
    """Check the declared COM-linear / SLERP segment, including its interior."""
    def check(a, b, da, db, depth):
        if min(da.min(), db.min()) <= margin_m:
            return False
        travel = model.motion_bounds(a, b)
        lower = np.minimum(da, db)-.5*np.array([travel[i]+travel[j] for i,j in model.pairs])
        if lower.min() >= margin_m:
            return True
        if depth == 0:
            return False
        mid = interpolate(a, b, .5)
        dm = model.distances(mid)
        return check(a, mid, da, dm, depth-1) and check(mid, b, dm, db, depth-1)
    return check(a, b, model.distances(a), model.distances(b), depth)


def plan_bridge(model, a, b, timeout=20., margin_m=.0001):
    """Plan a local ring detour, then independently certify every output edge."""
    from ompl import base as ob, geometric as og

    for name in model.names[:-1]:
        if not np.allclose(a[name]['pos'], b[name]['pos'], atol=1e-12, rtol=0) or \
                (Rotation.from_quat(a[name]['quat']).inv()*Rotation.from_quat(b[name]['quat'])).magnitude() > 1e-12:
            raise ValueError('Ring-only bridge requires fixed obstacles')
    pa = np.asarray(a['target_ring']['pos'])
    ra = Rotation.from_quat(a['target_ring']['quat'])
    start = np.zeros(6)
    end = np.r_[np.asarray(b['target_ring']['pos'])-pa,
                (ra.inv()*Rotation.from_quat(b['target_ring']['quat'])).as_rotvec()*.05]
    model.distances(a)
    def pose(q):
        return dict(pos=(pa+q[:3]).tolist(), quat=(ra*Rotation.from_rotvec(q[3:]/.05)).as_quat().tolist())
    def valid(state):
        q=np.array([state[i] for i in range(6)])
        p=pose(q)
        model.objects[-1].setTransform(fcl.Transform(Rotation.from_quat(p['quat']).as_matrix(),np.asarray(p['pos'])))
        return all(fcl.distance(o,model.objects[-1],model.request,fcl.DistanceResult())>margin_m*1.001 for o in model.objects[:-1])
    space=ob.RealVectorStateSpace(6)
    bounds=ob.RealVectorBounds(6)
    for i in range(6):
        padding=.012 if i<3 else .025
        bounds.setLow(i,float(min(start[i],end[i])-padding))
        bounds.setHigh(i,float(max(start[i],end[i])+padding))
    space.setBounds(bounds)
    setup=og.SimpleSetup(space)
    setup.setStateValidityChecker(valid)
    setup.getSpaceInformation().setStateValidityCheckingResolution(.0004)
    sa,sb=space.allocState(),space.allocState()
    for i in range(6): sa[i],sb[i]=float(start[i]),float(end[i])
    setup.setStartAndGoalStates(sa,sb,1e-8)
    planner=og.RRTConnect(setup.getSpaceInformation());planner.setRange(.003)
    setup.setPlanner(planner);setup.solve(timeout)
    if not setup.haveExactSolutionPath():
        raise RuntimeError('No exact local ring bridge found')
    points=np.array([[s[i] for i in range(6)] for s in setup.getSolutionPath().getStates()])
    states=[]
    for qa,qb in zip(points[:-1],points[1:]):
        steps=max(2,int(np.ceil(np.linalg.norm(qb-qa)/.0004))+1)
        states.extend((1-t)*qa+t*qb for t in np.linspace(0,1,steps)[:-1])
    states.append(points[-1])
    frames=[]
    for q in states:
        frame=deepcopy(a);frame['target_ring']=pose(q);frames.append(frame)
    frames[0],frames[-1]=deepcopy(a),deepcopy(b)
    if not all(segment_clear(model,x,y,margin_m) for x,y in zip(frames[:-1],frames[1:])):
        raise RuntimeError('Sampled planner bridge failed continuous certification')
    return frames


def repair_extraction(reference, max_bridges=12):
    result=deepcopy(reference)
    model=IndependentWitness(result['template'],result['scale'])
    frames=result['frames'];index=result['fold_end_index'];repairs=[]
    while index<len(frames)-1:
        if segment_clear(model,frames[index],frames[index+1]):
            index+=1
            continue
        if len(repairs)>=max_bridges:
            raise RuntimeError('Extraction bridge budget exhausted')
        bridge=None
        for attempt in range(3):
            try:
                bridge=plan_bridge(model,frames[index],frames[index+1])
                break
            except RuntimeError as e:
                print(f'Bridge {index} attempt {attempt+1}: {e}',flush=True)
        if bridge is None:
            raise RuntimeError(f'Could not bridge segment {index}')
        frames[index:index+2]=bridge
        repairs.append(dict(segment=index,frames=len(bridge)))
        print(f'Certified bridge at {index}: {len(bridge)} frames',flush=True)
        index+=len(bridge)-1
    result['extraction_bridges']=repairs
    result['qualification']='Candidate with certified local bridges; requires full-path certificate'
    return result
