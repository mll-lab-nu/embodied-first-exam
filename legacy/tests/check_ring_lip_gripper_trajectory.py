"""Validate recorded pickup, unconstrained contact pushing, and released seating."""
import argparse
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from topogym.tasks_legacy.deformation._ring_lip_geometry import seat_report, lip_bounds


def validate(output):
    cfg=OmegaConf.load(output/'simulation_config.yaml')
    data=np.load(output/'trajectory.npz')
    meta=json.loads((output/'frames.json').read_text())
    report=json.loads((output/'report.json').read_text())
    audit=json.loads((output/'gripper_audit.json').read_text())
    positions=data['positions'];origin=np.asarray(cfg.env.frames.task.origin)
    checks={}
    checks['complete_full_demo']=report.get('completed',False) and cfg.run.mode=='full'
    checks['aligned_finite_samples']=(len(positions)==len(meta)==len(data['qpos']) and
                                      np.isfinite(positions).all() and np.isfinite(data['qpos']).all())
    phases=[m['phase'] for m in meta]
    required=['张开夹爪，接近槽外绳圈','合拢夹爪抓住绳圈','提起绳圈','搬运绳圈至槽位上方',
              '张开夹爪，放下绳圈','合拢夹爪形成推压头','撤开机械臂','释放后检查整圈保持']
    indices=[phases.index(p) if p in phases else -1 for p in required]
    checks['pickup_place_push_release_order']=min(indices)>=0 and indices==sorted(indices)
    checks['ring_starts_away_from_groove']=np.linalg.norm(
        positions[0].mean(0)[:2]-origin[:2]-np.asarray(cfg.install.center))>.25
    checks['both_pads_touch_before_assist']=max(report['pickup_checks']['pad_surface_gaps_mm'].values())<=2.
    checks['whole_ring_lifted']=report['pickup_checks']['lowest_ring_point_after_lift_mm']>=100.
    pushes=[m for m in meta if '卡唇' in m['phase']]
    checks['closed_gripper_unconstrained_pushes']=bool(pushes) and all(
        not m['grasp_assist'] and m['half_gap_m']<.0001 for m in pushes)
    hold_indices=[i for i,m in enumerate(meta) if m['phase']=='释放后检查整圈保持']
    checks['released_hold_duration']=len(hold_indices)>=round(cfg.install.release_s*cfg.run.fps)
    checks['whole_ring_stays_seated']=bool(hold_indices) and all(
        not meta[i]['grasp_assist'] and seat_report(positions[i]-origin,cfg.install)['success'] for i in hold_indices)
    checks['no_sampled_gripper_fixture_intrusion']=not audit['fixture_intrusion_frames']
    checks['no_sampled_gripper_table_intrusion']=audit['minimum_table_clearance_mm']>=-.15
    checks['deformation_within_numerical_limit']=(report['max_principal_strain']<=cfg.install.max_principal_strain
                                                 and report['min_tet_volume_ratio']>0)
    final=positions[-1]-origin;delta=final[:,:2]-np.asarray(cfg.install.center)
    radial=np.linalg.norm(delta,axis=1);angle=np.arctan2(delta[:,1],delta[:,0]);coverage=[]
    for i in range(int(cfg.install.lip_count)):
        local=np.angle(np.exp(1j*(angle-np.radians(cfg.install.lip_angles_deg[i]))))
        lo,hi=lip_bounds(cfg.install,i);edges=np.radians(np.linspace(-cfg.install.lip_arc_deg/2,cfg.install.lip_arc_deg/2,6))
        coverage.append([int(((local>=a)&(local<b)&(radial>=lo)&(radial<=hi)&
                             (final[:,2]<cfg.install.wall_z)).sum()) for a,b in zip(edges[:-1],edges[1:])])
    checks['material_under_full_length_of_each_lip']=all(all(n>0 for n in bins) for bins in coverage)
    drift=float(np.linalg.norm(positions[hold_indices]-positions[hold_indices[0]],axis=2).max()*1000) if hold_indices else None
    result=dict(passed=bool(all(checks.values())),checks={k:bool(v) for k,v in checks.items()},
                under_lip_nodes_in_five_angular_bins=coverage,release_hold_max_vertex_drift_mm=drift,
                sampled_frames=len(meta),fps=cfg.run.fps)
    (output/'trajectory_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    validate(parser.parse_args().output)
