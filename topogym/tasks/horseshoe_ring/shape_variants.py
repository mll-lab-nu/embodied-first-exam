"""Coupled shoe-outline, target-ellipse and chain-length geometry experiments."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

import numpy as np
import fcl
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from .geometry import band_centerline, horseshoe_band
from .independent_motion import IndependentWitness

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT/'runs/demo_metadata/horseshoe_ring/2026-09-16_aloha_full/geometry_evidence/body_poses.json'
OUTPUT = ROOT/'runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1'
BASE_TEMPLATE = ROOT/'assets/tasks/horseshoe_ring/tutorial_solvable_v3/template.json'


@lru_cache(maxsize=1)
def seed():
    return json.loads(SEED.read_text())


def make_template(shape, aspect, chain_length, phase=0., bore_margin_mm=None):
    """A proposal law, not an unconditional solvability guarantee."""
    values = np.asarray([shape, aspect, chain_length, phase], dtype=float)
    if not np.isfinite(values).all() or not -1 <= shape <= 1 or not 1 <= aspect <= 1.35 or not 16 <= chain_length <= 20:
        raise ValueError('Expected shape in [-1,1], aspect in [1,1.35], chain half-length in [16,20] mm')
    t = json.loads(BASE_TEMPLATE.read_text())
    h, c, r = t['horseshoe'], t['chain'], t['target_ring']
    h['terminal_tip_mm'] = band_centerline(h, 1., np.array([np.radians(h['mouth_half_angle_deg'])]))[0,:2].tolist()
    depth = max(0., -shape)*4.
    h['outline_power'] = 2.+max(0.,shape)
    h['waist_depth'] = depth
    # Keep the chain attachment locations fixed while changing the swept band.
    # Increasing the target's long axis also widens the shoe's outer envelope.
    h['ellipse_radii'][1] = 29.+31.*(aspect-1)+depth
    c['link_radii'] = [float(chain_length), 5.]
    c['wire_radius'] = .7
    r['centerline_radii'] = [31.*aspect, 31.]
    if bore_margin_mm is not None:
        if not np.isfinite(bore_margin_mm) or bore_margin_mm <= 0:
            raise ValueError('Bore margin must be positive')
        band,_=horseshoe_band(h,1.)
        half_width=float(band.bounds[1,1]-band.bounds[0,1])/2
        major=half_width+r['wire_radius']-bore_margin_mm
        r['centerline_radii']=[major,major/aspect]
    r['initial_phase_deg'] = float(phase)
    t['template_id'] = 'horseshoe_coupled_shape_candidate_v1'
    t['geometry_status'] = 'Coupled shape proposal; requires its own complete path certificate'
    return t


def retarget_frames(model, indices=None, phase_delta=None):
    """Preserve each seed material-frame motion when the new COM changes."""
    d = seed()
    indices = list(range(len(d['frames']))) if indices is None else list(indices)
    result = []
    for j,index in enumerate(indices):
        original = d['frames'][index]
        frame = {}
        for k,name in enumerate(model.names):
            r = Rotation.from_quat(original[name]['quat'])
            center = np.asarray(original[name]['pos'])+r.apply(model.centers[k]-d['centers'][k])
            if name == 'target_ring' and phase_delta is not None:
                r = r*Rotation.from_euler('x', float(phase_delta[j]), degrees=True)
            frame[name] = dict(pos=center.tolist(),quat=r.as_quat().tolist())
        result.append(frame)
    return result


def probe(params):
    shape, aspect, length, phase = params
    model = IndependentWitness(make_template(shape,aspect,length,phase),seed()['scale'])
    last = len(seed()['frames'])-1
    indices = sorted(set(range(0,3129,96))|set(range(3129,last,8))|{0,last})
    frames = retarget_frames(model,indices)
    minimum, worst = float('inf'), None
    for index,frame in zip(indices,frames):
        ds = model.distances(frame)
        k = int(ds.argmin())
        if ds[k] < minimum:
            minimum = float(ds[k])
            worst = dict(frame=index,pair=[model.names[q] for q in model.pairs[k]])
        if minimum <= .0001:
            break
    return dict(shape=shape,aspect=aspect,chain_length_mm=length,phase_deg=phase,
                coarse_passed=minimum>.0001,minimum_sampled_gap_m=minimum,worst=worst)


class TargetRepair:
    """Local geometric path repair; only a later continuous check certifies it."""
    def __init__(self, model):
        self.model = model
        self.target = model.objects[-1]
        self.request = fcl.DistanceRequest()
        self.contact_request = fcl.CollisionRequest(num_max_contacts=24, enable_contact=True)
        self.calls = 0

    def set_frame(self, frame):
        for name, obj in zip(self.model.names, self.model.objects):
            pose = frame[name]
            obj.setTransform(fcl.Transform(Rotation.from_quat(pose['quat']).as_matrix(), np.asarray(pose['pos'])))
        self.center = np.asarray(frame['target_ring']['pos'])
        self.rotation = Rotation.from_quat(frame['target_ring']['quat'])

    def gaps(self, q):
        self.calls += 1
        r = self.rotation*Rotation.from_euler('xyz',np.asarray(q[3:])*[10,5,5],degrees=True)
        self.target.setTransform(fcl.Transform(r.as_matrix(),self.center+np.asarray(q[:3])*.001))
        ds=[]
        for obj in self.model.objects[:-1]:
            d=fcl.distance(obj,self.target,self.request,fcl.DistanceResult())
            if d<=0:
                result=fcl.CollisionResult()
                fcl.collide(obj,self.target,self.contact_request,result)
                d=-max((contact.penetration_depth for contact in result.contacts),default=.00001)
            ds.append(d*1000)
        return np.asarray(ds)

    def solve(self, previous, rng, margin_mm=.15):
        desired=np.asarray(previous)*.85
        if self.gaps(desired).min()>=margin_mm:
            return desired
        if self.gaps(previous).min()>=margin_mm:
            return np.asarray(previous).copy()
        best=None
        for attempt in range(6):
            initial=np.asarray(previous) if attempt==0 else np.asarray(previous)+rng.normal(size=6)*[3,3,3,2,1,1]
            opt=minimize(lambda q:float(np.sum((q-desired)**2*[1,1,1,.8,2,2])),initial,method='SLSQP',
                bounds=[(-24,24)]*3+[(-12,12),(-5,5),(-5,5)],
                constraints=[dict(type='ineq',fun=lambda q:self.gaps(q)-margin_mm)],
                options=dict(maxiter=45,ftol=1e-6,eps=1e-3))
            if self.gaps(opt.x).min()>=.12:
                best=opt.x
                break
        return best


def repair_path(params, random_seed=0, stride=32, bore_margin_mm=None):
    shape,aspect,length,phase=params
    template=make_template(shape,aspect,length,phase,bore_margin_mm=bore_margin_mm)
    model=IndependentWitness(template,seed()['scale'])
    last=len(seed()['frames'])-1
    indices=sorted(set(range(0,3129,stride))|set(range(3129,last,4))|{0,last})
    raw=retarget_frames(model,indices)
    repair=TargetRepair(model)
    rng=np.random.default_rng(random_seed)
    previous=np.zeros(6)
    edits=[]
    for i,(index,frame) in enumerate(zip(indices,raw)):
        repair.set_frame(frame)
        non_target=[fcl.distance(model.objects[a],model.objects[b],model.request,fcl.DistanceResult())
                    for a,b in model.pairs if b!=len(model.names)-1]
        if min(non_target)<=.0001:
            return dict(passed=False,reason='non_target_collision',frame=index)
        if i==0:
            if repair.gaps(previous).min()<.3:
                return dict(passed=False,reason='initial_ring_clearance',frame=index)
            q=previous.copy()
        else:
            q=repair.solve(previous,rng)
        if q is None:
            return dict(passed=False,reason='local_ring_repair_failed',frame=index,calls=repair.calls,
                        previous_edit=previous.tolist(),previous_gaps_mm=repair.gaps(previous).tolist())
        edits.append(q.tolist());previous=q
        if i%25==0:
            print(f'Repaired {i+1}/{len(indices)} at seed frame {index}',flush=True)
    edits=np.asarray(edits)
    frames,dense=frames_from_edits(model,indices,edits)
    return dict(passed=True,template=template,scale=seed()['scale'],centers=model.centers.tolist(),frames=frames,
        fold_end_index=seed()['fold_end_index'],repair=dict(anchor_indices=indices,anchor_edits=edits.tolist(),
        maximum_translation_offset_m=float(np.linalg.norm(dense[:,:3],axis=1).max()*.001),
        maximum_phase_offset_deg=float(np.abs(dense[:,3]).max()*10),calls=repair.calls),
        qualification='Candidate only; full continuous collision verification still required')


def frames_from_edits(model,indices,edits):
    edits=np.asarray(edits)
    dense=np.column_stack([np.interp(np.arange(len(seed()['frames'])),indices,edits[:,j]) for j in range(6)])
    frames=retarget_frames(model)
    for frame,offset in zip(frames,dense):
        frame['target_ring']['pos']=(np.asarray(frame['target_ring']['pos'])+offset[:3]*.001).tolist()
        frame['target_ring']['quat']=(Rotation.from_quat(frame['target_ring']['quat'])*
            Rotation.from_euler('xyz',offset[3:]*[10,5,5],degrees=True)).as_quat().tolist()
    return frames,dense


def polish_path(reference, template=None, random_seed=0, keep_clear_reference=False):
    """Warm-start every frame from a nearby full path, including new shape COMs."""
    template=deepcopy(template or reference['template'])
    model=IndependentWitness(template,reference['scale'])
    repair=TargetRepair(model)
    rng=np.random.default_rng(random_seed)
    previous=np.zeros(6)
    frames=[];edits=[]
    for index,old in enumerate(reference['frames']):
        frame={}
        for k,name in enumerate(model.names):
            r=Rotation.from_quat(old[name]['quat'])
            p=np.asarray(old[name]['pos'])+r.apply(model.centers[k]-reference['centers'][k])
            frame[name]=dict(pos=p.tolist(),quat=r.as_quat().tolist())
        repair.set_frame(frame)
        if index==0:
            if repair.gaps(previous).min()<.15:
                return dict(passed=False,reason='initial_ring_clearance',frame=index)
            q=previous.copy()
        elif keep_clear_reference and repair.gaps(np.zeros(6)).min()>=.15:
            q=np.zeros(6)
        else:
            q=repair.solve(previous,rng,margin_mm=.25)
        if q is None:
            return dict(passed=False,reason='dense_repair_failed',frame=index,calls=repair.calls)
        frame['target_ring']['pos']=(repair.center+q[:3]*.001).tolist()
        frame['target_ring']['quat']=(repair.rotation*Rotation.from_euler('xyz',q[3:]*[10,5,5],degrees=True)).as_quat().tolist()
        frames.append(frame);edits.append(q.tolist());previous=q
        if index%400==0:print(f'Polished {index+1}/{len(reference["frames"])}',flush=True)
    return dict(passed=True,template=template,scale=reference['scale'],centers=model.centers.tolist(),
        frames=frames,fold_end_index=reference['fold_end_index'],
        repair=dict(method='dense_local_SE3_repair',calls=repair.calls,edits=edits),
        qualification='Candidate only; requires continuous certification')
