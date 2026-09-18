"""Certified coupled shape perturbations around fully solved reference cases.

Distance certificates concern the actual URDF convex/capsule compounds. Matching
convex vertices and capsule endpoints provide conservative Hausdorff bounds;
the source cover clearance therefore transfers to every declared time interval.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.distance import cdist
from scipy.spatial.transform import Rotation

from .geometry import HorseshoeAssembly


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def body_change_bound(before,after):
    if len(before.convex)!=len(after.convex) or len(before.loops)!=len(after.loops):
        raise ValueError('Shape transfer cannot change collision-piece counts or topology')
    bounds=[]
    for a,b in zip(before.convex,after.convex):
        distances=cdist(a.vertices,b.vertices)
        # Distance to the nearest vertex bounds distance to its convex hull;
        # convexity extends this bound to the entire convex piece.
        bounds.append(max(distances.min(0).max(),distances.min(1).max()))
    for a,b in zip(before.loops,after.loops):
        if a.name!=b.name or a.segments!=b.segments:
            raise ValueError('Loop correspondence changed')
        bounds.append(np.linalg.norm(a.points()-b.points(),axis=1).max()+abs(a.wire_radius-b.wire_radius))
    return float(max(bounds,default=0.))


class ShapeNeighborhood:
    def __init__(self, path, certificate):
        if not certificate.get('passed') or digest(path['template'])!=certificate['template_sha256'] or digest(path['frames'])!=certificate['frames_sha256']:
            raise ValueError('Reference path and geometry must match a complete certificate')
        if not certificate.get('continuous_collision_free') or certificate.get('scale')!=path['scale']:
            raise ValueError('Reference needs a continuous certificate at the same scale')
        self.path=path
        self.certificate=certificate
        self.assembly=HorseshoeAssembly(path['template'],path['scale'])
        if not np.allclose(path['centers'],[b.visual.center_mass for b in self.assembly.bodies],atol=1e-12,rtol=0):
            raise ValueError('Reference COMs do not match its geometry')
        self.names=[b.name for b in self.assembly.bodies]
        self.rotations={n:Rotation.from_quat([f[n]['quat'] for f in path['frames']]) for n in self.names}
        self.max_angles={n:float((r[:-1].inv()*r[1:]).magnitude().max()) for n,r in self.rotations.items()}
        self.pair_bounds=certificate['minimum_pair_clearance_lower_bounds_m']
        expected={a+'--'+b for i,a in enumerate(self.names) for b in self.names[i+1:]}
        if set(self.pair_bounds)!=expected or any(v is None or v<=0 for v in self.pair_bounds.values()):
            raise ValueError('A complete positive bound for every body pair is required')
        implementations=certificate.get('implementation_sha256',{})
        if set(implementations)!={'geometry.py','solvability.py','independent_motion.py'}:
            raise ValueError('Reference implementation fingerprints are required')
        for name,sha in implementations.items():
            if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()!=sha:
                raise ValueError(f'Reference implementation changed: {name}; recertify it before reuse')

    def assess(self, template, margin_m=.00005):
        if not np.isfinite(margin_m) or margin_m<=0:
            raise ValueError('Need a positive finite geometric clearance')
        assembly=HorseshoeAssembly(template,self.path['scale'])
        if [b.name for b in assembly.bodies]!=self.names:
            raise ValueError('Body topology changed')
        bounds={};centers=[]
        for k,(before,after) in enumerate(zip(self.assembly.bodies,assembly.bodies)):
            center=after.visual.center_mass;centers.append(center)
            change=body_change_bound(before,after)
            dc=center-np.asarray(self.path['centers'][k])
            # New COM samples are retargeted exactly. During COM-linear /
            # shortest-SLERP interpolation the additional chord error is at
            # most theta * ||delta_COM|| / 2 over each unit interval.
            chord=.5*self.max_angles[before.name]*np.linalg.norm(dc)
            bounds[before.name]=dict(primitive_hausdorff_bound_m=change,
                com_interpolation_bound_m=float(chord),total_bound_m=float(change+chord))
        lower={}
        for pair,gap in self.pair_bounds.items():
            a,b=pair.split('--')
            lower[pair]=float(gap-bounds[a]['total_bound_m']-bounds[b]['total_bound_m'])
        return dict(passed=min(lower.values())>=margin_m,requested_margin_m=margin_m,
                    body_bounds=bounds,pair_clearance_lower_bounds_m=lower,
                    minimum_clearance_lower_bound_m=min(lower.values()),centers=np.asarray(centers).tolist())

    def materialize(self,template,assessment):
        actual=self.assess(template,assessment['requested_margin_m'])
        if not actual['passed']:
            raise ValueError('Candidate is outside the certified coupled neighborhood')
        frames=deepcopy(self.path['frames'])
        for k,n in enumerate(self.names):
            dc=np.asarray(actual['centers'][k])-self.path['centers'][k]
            shifts=self.rotations[n].apply(dc)
            for f,shift in zip(frames,shifts):
                f[n]['pos']=(np.asarray(f[n]['pos'])+shift).tolist()
        result=dict(template=template,scale=self.path['scale'],centers=actual['centers'],frames=frames,
                    fold_end_index=self.path['fold_end_index'])
        certificate=dict(actual,template_sha256=digest(template),frames_sha256=digest(frames),
            scale=self.path['scale'],lab_obstacle_collision_verified=False,
            scope='Continuous positive clearance transferred to the actual convex/capsule geometry by per-body perturbation bounds',
            interpolation='Each new body COM is linear and orientation follows shortest SLERP, as in the source certificate',
            source_template_sha256=self.certificate['template_sha256'],source_frames_sha256=self.certificate['frames_sha256'],
            source_certificate_sha256=digest(self.certificate),source_requested_margin_m=self.certificate['requested_margin_m'],
            robot_execution_verified=False,dynamic_execution_verified=False,
            note='Positive primitive clearance, initial loop topology and full final separation are checked; no robot or force guarantee')
        assembly=HorseshoeAssembly(template,self.path['scale'])
        topology=assembly.topology_report()
        initial=all(np.allclose(frames[0][n]['pos'],c,atol=1e-9,rtol=0)
            and np.allclose(Rotation.from_quat(frames[0][n]['quat']).as_matrix(),np.eye(3),atol=1e-9)
            for n,c in zip(self.names,actual['centers']))
        bounds=[]
        for body,center in zip(assembly.bodies,actual['centers']):
            pose=frames[-1][body.name];r=Rotation.from_quat(pose['quat']);p=np.asarray(pose['pos'])
            pieces=[]
            for convex in body.convex:
                points=r.apply(convex.vertices-center)+p
                pieces.append(np.array([points.min(0),points.max(0)]))
            for loop in body.loops:
                points=r.apply(loop.points()-center)+p
                pieces.append(np.array([points.min(0)-loop.wire_radius,points.max(0)+loop.wire_radius]))
            bounds.append(np.array([np.min([b[0] for b in pieces],0),np.max([b[1] for b in pieces],0)]))
        target=bounds[-1];obstacle=np.array([np.min([b[0] for b in bounds[:-1]],0),np.max([b[1] for b in bounds[:-1]],0)])
        gap=float(np.maximum(target[0]-obstacle[1],obstacle[0]-target[1]).max())
        if not(initial and topology['adjacent_pairs_linked'] and not topology['unexpected_linked_pairs']
               and topology['target_encloses_both_chain_spans'] and topology['target_not_hopf_linked_to_any_single_loop'] and gap>0):
            raise ValueError('Initial topology or final extraction failed')
        certificate.update(initial_matches_template=True,initial_topology=topology,goal=dict(separated=True,separation_m=gap))
        return result,certificate
