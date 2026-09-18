"""Motion-first representative paths for three hedgehog mechanisms."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from .inverse_window import SEED, Kinematics, save, sha
from .geometry import ROOT
from .plan_escape import interpolate

OUTPUT = ROOT/'runs/environment-solvability/hedgehog_in_cage/family_representatives_v1'
FAMILIES = ('oblique_gate','staggered_gates','helical_guide')


def proposal(family):
    source=np.array(json.loads((SEED/'escape_upper.json').read_text())['path'])
    path=source.copy(); phases=['initial_adjustment']*9
    if family=='oblique_gate':
        for i in range(2,8):
            w=np.sin(np.pi*(i-1)/7)
            path[i,1]+=.010*w
            path[i,3:]=(Rotation.from_euler('x',-4*w,degrees=True)*Rotation.from_quat(path[i,3:])).as_quat()
        phases=['initial_adjustment','approach_oblique_gate']+['lateral_oblique_turn']*6+['withdraw']
        params=dict(side_excursion_m=.010,added_tilt_deg=-4.)
    elif family=='staggered_gates':
        path[2:8,1]+=np.array([-.008,-.009,-.012,-.002,.012,.010])
        path[2:8,2]+=np.array([.008,.015,.022,.016,-.008,-.012])
        # Preserve the known grasp branch, then pass a second, deeper gate.
        a=path[8].copy();a[:3]=[.130,.015,.040]
        b=path[8].copy();b[:3]=[.190,.025,.050]
        c=path[8].copy();c[:3]=[.330,.025,.050]
        end=path[-1].copy();end[0]=.380
        path=np.array([*path[:9],a,b,c,end])
        phases=['initial_adjustment','approach_first_gate']+['first_gate_turn']*6+['change_level_between_gates','align_second_gate','pass_second_gate','withdraw']
        params=dict(height_adjustment_m=.022,opposed_side_adjustment_m=.012,second_gate_x_m=.220,second_gate_height_m=.050)
    elif family=='helical_guide':
        for i,angle in zip(range(2,9),[4.,8.,16.,24.,30.,34.,36.]):
            r=Rotation.from_euler('z',angle,degrees=True)
            path[i,:3]=r.apply(path[i,:3])
            path[i,3:]=(r*Rotation.from_quat(path[i,3:])).as_quat()
        r=Rotation.from_euler('z',36,degrees=True)
        path[-1,:3]=r.apply([.200,source[-1,1],source[-1,2]])
        path[-1,3:]=(r*Rotation.from_quat(source[-1,3:])).as_quat()
        phases=['initial_adjustment','approach_helical_guide']+['coupled_turn_and_advance']*6+['withdraw']
        params=dict(added_guide_turn_deg=36.,final_radial_distance_m=.200)
    else:raise ValueError(family)
    return source,path,phases,params


def generate(family, output=OUTPUT, motion_file=None):
    folder=Path(output)/family;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'ik_before_geometry.json').exists():raise ValueError('Preserve existing motion proposal')
    source,path,phases,params=proposal(family)
    override=None
    if motion_file is not None:
        override=json.loads(Path(motion_file).read_text())
        path=np.array(override['path']);phases=override['phases'];params=override['parameters']
        if len(phases)!=len(path)-1:raise ValueError('Every extraction segment requires a phase')
        save(folder/'motion_input.json',override)
    release=json.loads((SEED/'robot_release_plan.json').read_text())
    release_path=np.array(release['path']);release_path[0]=path[-1]
    if family=='staggered_gates':release_path[1:,0]=.450
    if override is not None and 'release_path' in override:release_path=np.array(override['release_path'])
    release_path[0]=path[-1]
    save(folder/'motion_proposal.json',dict(family=family,geometry_pending=True,parameters=params,path=path.tolist(),
        phase_names=phases,seed_solution_sha256=sha(SEED/'escape_upper.json'),
        design_order='known solution -> relative motion change -> continuous IK -> geometry'))
    kin=Kinematics();frames=[];knots=[]
    all_path=np.array([*path,*release_path[1:]])
    names=[*phases,*release['phases']]
    try:
        for i,(a,b) in enumerate(zip(all_path[:-1],all_path[1:])):
            for target in list(interpolate(a,b,.0025))[int(i>0):]:
                actual=kin.solve(target)
                frames.append(dict(qpos=kin.q.tolist(),ball_pose=actual.tolist(),segment=i,stage=names[i]))
            knots.append(len(frames)-1)
            print(f'{family}: IK {i+1}/{len(all_path)-1}, {len(frames)} states',flush=True)
    except Exception as exc:
        save(folder/'ik_failure.json',dict(error=str(exc),segment=i,completed_frames=len(frames),target=target.tolist()))
        raise
    result=dict(family=family,geometry_pending=True,frames=frames,knot_indices=knots,extraction_last_frame=knots[len(path)-2],
        proposed_path=path.tolist(),extraction_phases=phases,release_path=release_path.tolist(),release_phases=release['phases'],
        proposal_sha256=sha(folder/'motion_proposal.json'),grasp_spike='S2',seed_path=source.tolist())
    save(folder/'ik_before_geometry.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('family',choices=FAMILIES);p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--motion-file',type=Path)
    args=p.parse_args();generate(args.family,args.output,args.motion_file)


if __name__=='__main__':main()
