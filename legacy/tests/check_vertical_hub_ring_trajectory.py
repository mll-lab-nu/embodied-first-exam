"""Audit saved physical samples; report installation outcome separately."""
import argparse
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from demos.deformation.vertical_hub_ring_demo import reading


def validate(output, require_success=False):
    cfg=OmegaConf.load(output/'simulation_config.yaml')
    data=np.load(output/'trajectory.npz')
    meta=json.loads((output/'frames.json').read_text())
    report=json.loads((output/'report.json').read_text())
    audit=json.loads((output/'gripper_audit.json').read_text())
    release=json.loads((output/'release_audit.json').read_text())
    positions=data['positions'];origin=np.asarray(cfg.env.frames.task.origin)
    angles=np.arctan2(data['initial'][:,1]-origin[1]-cfg.hub.source_center[1],
                      data['initial'][:,0]-origin[0]-cfg.hub.source_center[0])
    edges=np.linspace(-np.pi,np.pi,33)
    groups=[np.flatnonzero((angles>=a)&(angles<b)) for a,b in zip(edges[:-1],edges[1:])]
    checks={
        'aligned_finite_samples':len(positions)==len(meta)==len(data['qpos']) and len(meta)>0
            and np.isfinite(positions).all() and np.isfinite(data['qpos']).all(),
        'regular_physical_time':np.allclose(np.diff([m['time_s'] for m in meta]),1/cfg.run.fps),
        'no_installed_material_pins':report['installed_material_constraints']==0,
        'at_most_one_assisted_grasp':report['maximum_simultaneous_grasps']==1
            and all(m['active_grasp'] is None or isinstance(m['active_grasp'],int) for m in meta),
        'both_real_pads_contact_at_each_grasp':bool(report['grasp_checks']) and all(
            max(g['pad_surface_gaps_mm'].values())<=2 for g in report['grasp_checks']),
        'no_sampled_gripper_fixture_intrusion':not audit['fixture_intrusion_frames'],
        'no_sampled_gripper_table_intrusion':audit['minimum_table_clearance_mm']>=-.15,
        'no_sampled_arm_fixture_intrusion':not audit['arm_fixture_intrusions'],
        'no_sampled_material_fixture_intrusion':not audit['material_fixture_intrusions'],
        'no_sampled_material_arm_intrusion':not audit['material_arm_intrusions'],
        'no_sampled_material_table_intrusion':audit['minimum_ring_table_clearance_mm']>=-.15,
        'ik_position_error_below_3mm':report['max_ik_error_mm']<=3,
        'deformation_within_numerical_limit':report['max_principal_strain']<=cfg.hub.max_principal_strain
            and report['min_tet_volume_ratio']>0,
    }
    phases=[m['phase'] for m in meta]
    lift=[i for i,p in enumerate(phases) if p=='提起，观察自由段下垂']
    hold=[i for i,p in enumerate(phases) if p=='无夹持释放保持检查']
    support=[i for i,p in enumerate(phases) if p=='检查无夹持的上段保持']
    probe=hold if cfg.run.strategy=='bottom_first' else support
    checks['assist_disabled_observation_completed']=len(probe)>=cfg.run.fps and all(meta[i]['active_grasp'] is None for i in probe)
    checks['no_execution_or_numerical_abort']=report['error'] in (None,'The hub did not retain the released top material')
    final=reading(positions[-1]-origin,cfg.hub,data['top_indices'],groups)
    successful_hold=bool(hold) and all(meta[i]['active_grasp'] is None and
        reading(positions[i]-origin,cfg.hub,data['top_indices'],groups)['success'] for i in hold)
    observed_success=bool(report['completed'] and successful_hold and final['success'] and release['tool_clear_during_observation'])
    checks['reported_outcome_matches_saved_geometry']=observed_success==report['success']
    checks['whole_ring_lifted_from_table']=bool(lift) and (positions[lift[-1],:,2]-origin[2]).min()>.03
    if require_success:
        checks['complete_installation_and_released_hold']=observed_success and len(hold)>=round(cfg.hub.release_s*cfg.run.fps)
    result=dict(passed=bool(all(checks.values())),checks={k:bool(v) for k,v in checks.items()},
                installation_success=observed_success,final_geometry=final,
                tool_clear_during_observation=release['tool_clear_during_observation'],
                lifted_ring_height_range_mm=((positions[lift[-1],:,2]-origin[2])*1000)[[np.argmin(positions[lift[-1],:,2]),np.argmax(positions[lift[-1],:,2])]].tolist() if lift else None,
                scope='Recorded FEM trajectory and discrete gripper geometry audit; no claim of controller robustness')
    (output/'trajectory_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    parser.add_argument('--require-success',action='store_true')
    args=parser.parse_args();validate(args.output,args.require_success)
