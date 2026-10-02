"""Independent numerical audit of a frozen Horseshoe robot execution.

Recompute geometry, chain incidence and the fixed placement predicate from
every recorded physical tick. A disabled historical terminal is never changed
retroactively. Sampling is at World ticks, not a continuous dynamics proof.
"""
from dataclasses import replace
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

from topogym.evaluation.task_metrics import placement_candidate
from topogym.planning.rigid_reference.feedback import body_pose
from topogym.planning.rigid_reference.geometry import freeze_scene
from topogym.utils.io import write_json_atomic
from topogym.utils.grasp import held_finger_contact_mask


STATE_FIELDS=('episode_id','branch_id','state_id','physics_step')


def _state_key(state):
    return tuple(state[key] for key in STATE_FIELDS)


def _audit_robot_observations(step_files, expected_states, limits, *, prefix):
    """Match robot rows to the exact bounded monitor states, across segments."""
    covered=set();failures=[];maximum_residue=0.
    for steps in step_files:
        with steps.open() as stream:
            for line in stream:
                if prefix and not line.endswith('\n'):break
                row=json.loads(line);key=_state_key(row['state'])
                # A live prefix can be followed by a rewind's initial row,
                # or by newer ticks. Neither belongs to this monitor snapshot.
                # Monitored post-rewind ticks remain included and still fail
                # the separate continuous-history check.
                if key not in expected_states:continue
                if not {'left','right'}<=row.get('robot',{}).keys():continue
                covered.add(key)
                for side,state in row['robot'].items():
                    q=np.asarray(state['joint_position_rad'])
                    residue=float(np.maximum(limits[:,0]-q,q-limits[:,1]).max())
                    maximum_residue=max(maximum_residue,residue)
                    if residue>1e-6:
                        failures.append(dict(tick=row['state']['physics_step'],
                            reason='observed_joint_limit_violation',side=side,violation_rad=residue))
    missing=expected_states-covered
    if missing:
        failures.append(dict(reason='missing_robot_observations',count=len(missing),
            examples=[dict(zip(STATE_FIELDS,key)) for key in sorted(missing)[:10]]))
    return maximum_residue,dict(expected_states=len(expected_states),
        covered_states=len(covered),complete=not missing),failures


def audit_run(root, *, prefix=False):
    root=Path(root).resolve()
    report=json.loads((root/'run_report.json').read_text())
    runtime=root/'horseshoe_runtime_identity.json'
    if runtime.exists():
        metadata=json.loads(runtime.read_text())
        for key in ('instance_id','seed'):
            if key in report and report[key]!=metadata[key]:raise ValueError(f'Conflicting runtime {key}')
        report={**metadata,**report}
    config=report['config']
    task,_,_,_,identity=freeze_scene('horseshoe_ring',config['variation_id'],report['seed'],root/'audit_assets')
    if identity['instance_id']!=report['instance_id']:
        raise ValueError('Audit geometry/goal identity differs from the recorded execution')
    source=json.loads((root/'run_source_manifest.json').read_text())
    source_valid=all(hashlib.sha256((root/'source_snapshot'/name).read_bytes()).hexdigest()==digest for name,digest in source.items())
    # New executions bind the task's contact policy explicitly. Historical
    # records without it retain the old uniform 1 mm audit and force gate.
    contact_policy=report.get('terminal',{}).get('contact_penetration')
    if contact_policy is not None and contact_policy!=task.terminal_metadata()['contact_penetration']:
        raise ValueError('Recorded contact policy differs from the auditor task')
    other_limit=float(contact_policy['other_contacts_m']) if contact_policy else .001
    held_limit=float(contact_policy['held_finger_contacts_m']) if contact_policy else .001
    dt=float(config['physics_dt_s']);failures=[];previous=None;active_before=False;stable=0.;best_stable=0.
    first_goal=None;count=0;max_depth=0.;acquired={};lost=[];phases={};birth=None;last=None
    max_robot_self_depth=0.;max_robot_table_depth=0.
    max_other_depth=0.;max_held_depth=0.
    link_names=report.get('contact_link_names',{})
    initial_linkage=None;linkage=None
    expected_robot_states=set()
    acquisition_covered=bool(report.get('grasp_finger_links'));acquisition_valid=True
    artifact=root/'private/horseshoe_monitor.jsonl'
    digest=hashlib.sha256()
    with artifact.open('rb') as stream:
        # A live run may append more records during the audit. Bind this
        # diagnostic to the complete lines already present at entry.
        limit=artifact.stat().st_size if prefix else None
        for line in stream:
            if limit is not None and (stream.tell()>limit or not line.endswith(b'\n')):break
            digest.update(line);row=json.loads(line)
            state,world=row['state'],row['world'];count+=1
            expected_robot_states.add(_state_key(state))
            if birth is None:birth=state
            tick=int(state['physics_step'])
            if (previous is None and tick!=0 or previous is not None and tick!=previous+1
                    or state['branch_id']!=0 or state['episode_id']!=birth['episode_id']):
                failures.append(dict(tick=tick,reason='noncontinuous_history'))
            previous=tick;last=row
            phases.setdefault(row['phase'],dict(first_tick=tick,last_tick=tick))['last_tick']=tick
            poses={n:body_pose(world['bodies'][n]) for n in task.placement_vertices}
            loops={}
            for n,loop in task.assembly.loops.items():
                p,r=poses[loop.body]
                loops[n]=replace(loop,center=p+r.apply(loop.center-task.body_origins[loop.body]),rotation=r*loop.rotation)
            linkage={a+'|'+b:loops[a].linking(loops[b]) for a,b in itertools.combinations(loops,2)
                     if loops[a].body!=loops[b].body}
            if initial_linkage is None:initial_linkage=linkage
            changed={pair:dict(initial=initial_linkage[pair],current=value) for pair,value in linkage.items()
                     if value!=initial_linkage[pair]}
            if changed:failures.append(dict(tick=tick,reason='closed_loop_passage',pairs=changed))
            if any(abs(loops[a].linking(loops[b]))!=1 for a,b in task.assembly.edges):
                failures.append(dict(tick=tick,reason='chain_connection_lost'))
            task_links={i for n in task.placement_vertices for i in world['bodies'][n]['link_indices']}
            contacts=world['contacts']
            depth=max((float(d) for a,b,d in zip(contacts['link_a'],contacts['link_b'],contacts['penetration'])
                       if a in task_links or b in task_links),default=0.)
            max_depth=max(max_depth,depth)
            involved=(np.isin(contacts['link_a'],list(task_links)) |
                      np.isin(contacts['link_b'],list(task_links)))
            held=(held_finger_contact_mask(contacts,report.get('grasp_finger_links',{}),
                                          task_links,world.get('grasp')) if contact_policy else
                  np.zeros(len(contacts['penetration']),dtype=bool))
            penetration=np.asarray(contacts['penetration'])
            other_depth=float(penetration[involved & ~held].max(initial=0.))
            held_depth=float(penetration[involved & held].max(initial=0.))
            max_other_depth=max(max_other_depth,other_depth);max_held_depth=max(max_held_depth,held_depth)
            if other_depth>other_limit:
                failures.append(dict(tick=tick,reason='task_penetration_above_1mm',depth_m=other_depth))
            if held_depth>held_limit:
                failures.append(dict(tick=tick,reason='held_finger_penetration_above_task_limit',
                                     depth_m=held_depth,limit_m=held_limit))
            for a,b,d in zip(contacts['link_a'],contacts['link_b'],contacts['penetration']):
                na,nb=link_names.get(str(a),''),link_names.get(str(b),'')
                if na.startswith('robot/') and nb.startswith('robot/'):
                    max_robot_self_depth=max(max_robot_self_depth,float(d))
                    if d>.001:failures.append(dict(tick=tick,reason='robot_self_penetration_above_1mm',links=[na,nb],depth_m=float(d)))
                for robot,other in ((na,nb),(nb,na)):
                    if (robot.startswith('robot/') and other.startswith('table/')
                            and robot.rsplit('/',1)[-1] not in {'base_link','waist_link','shoulder_link'}):
                        max_robot_table_depth=max(max_robot_table_depth,float(d))
                        if d>.001:failures.append(dict(tick=tick,reason='robot_table_penetration_above_1mm',links=[robot,other],depth_m=float(d)))
            for event in world['grasp']['events']:
                if event['event']=='acquired':
                    acquired.setdefault(event['hand'],[]).append(event)
                    binding=event['binding'];evidence=binding['acquisition_evidence']
                    target_link=binding['links'][1]
                    seen=set()
                    for a,b,d,f in zip(contacts['link_a'],contacts['link_b'],contacts['penetration'],contacts['force']):
                        force_ok=contact_policy is not None or np.linalg.norm(f)>0
                        if target_link in (a,b) and 0<=d<=config['grasp_assist']['max_penetration_m'] and force_ok:
                            seen.add(b if a==target_link else a)
                    expected=set(report.get('grasp_finger_links',{}).get(event['hand'],()))
                    valid=(acquisition_covered and len(expected)==2 and expected<=seen
                           and evidence['physics_step']==tick and event['effective_from_physics_step']==tick+1)
                    acquisition_valid &= valid
                elif event['event']=='lost':lost.append(event)
            reached,failure,metrics=placement_candidate(world,task.goal_region,task.placement_vertices,
                                                       task.placement_targets,task.placement_remainder)
            active=reached and failure is None
            stable=stable+dt if active and active_before else 0.
            active_before=active;best_stable=max(best_stable,stable)
            if active and first_goal is None:first_goal=tick
            if row['task']['result']['reason'] not in (None,'Goal stable'):
                failures.append(dict(tick=tick,reason='native_task_failure',detail=row['task']['result']['reason']))
    if last is None:raise ValueError('Empty physical evidence')
    if not prefix and count!=report['physics_steps']+1:failures.append(dict(reason='missing_physics_ticks'))
    # Check actual first action evidence against the declared ALOHA home.
    step_files=sorted((root/'segments').glob('segment_*/steps.jsonl'),
                      key=lambda p:int(p.parent.name.rsplit('_',1)[1]))
    if not step_files:raise ValueError('Missing robot/action evidence')
    with step_files[0].open() as stream:first=json.loads(next(stream))
    from topogym.config.scene import load_scene_config
    from topogym.simulator import SimulatorConfig
    scene=load_scene_config(SimulatorConfig(task_id='horseshoe_ring',robot_id='aloha',enable_rgb=False,compute_backend='cpu'))
    home_ok=all(np.allclose(first['robot'][s]['joint_position_rad'],list(scene.robot_control.home[s])[:6],atol=1e-9,rtol=0)
                for s in ('left','right'))
    limits=np.asarray(scene.robot_control.robot.arm_joint_limits)
    maximum_joint_limit_residue,robot_coverage,robot_failures=_audit_robot_observations(
        step_files,expected_robot_states,limits,prefix=prefix)
    failures.extend(robot_failures)
    workflow=root/'qualification/workflow.json'
    rewinds=len(json.loads(workflow.read_text()).get('rewinds',())) if workflow.exists() else 0
    native=bool(report.get('task_success',False))
    raw=best_stable+1e-12>=float(task.config['stable_duration_s'])
    qualified=not prefix and not rewinds and source_valid and home_ok and not failures and not lost and raw and acquisition_valid and bool(acquired)
    result=dict(schema_version=1,source_snapshot_valid=source_valid,from_default_home=home_ok,
        diagnostic_prefix=prefix,last_audited_state=last['state'],
        auditor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        physical_evidence_sha256=digest.hexdigest(),identity=identity,physics_ticks=count,
        continuous_from_birth=(not any(f.get('reason')=='noncontinuous_history' for f in failures)
                               and (prefix or not rewinds)),
        workflow_rewinds=rewinds,robot_observation_coverage=robot_coverage,
        maximum_task_contact_penetration_m=max_depth,chain_connections_intact=not any(f.get('reason')=='chain_connection_lost' for f in failures),
        contact_policy=contact_policy or dict(other_contacts_m=.001,held_finger_contacts_m=.001,
                                             scope='historical uniform audit; original verdict not relaxed'),
        maximum_other_task_contact_penetration_m=max_other_depth,
        maximum_held_finger_contact_penetration_m=max_held_depth,
        maximum_robot_self_contact_penetration_m=max_robot_self_depth,
        maximum_robot_table_contact_penetration_m=max_robot_table_depth,
        maximum_observed_joint_limit_residue_rad=maximum_joint_limit_residue,
        joint_limit_numerical_allowance_rad=1e-6,
        initial_loop_linkage=initial_linkage,final_loop_linkage=linkage,
        all_closed_loop_linkages_preserved=not any(f.get('reason')=='closed_loop_passage' for f in failures),
        grasp_acquisitions=acquired,grasp_losses=lost,phases=phases,failures=failures,
        bilateral_acquisition_coverage=acquisition_covered,bilateral_acquisitions_valid=acquisition_valid and acquisition_covered,
        first_raw_goal_tick=first_goal,maximum_raw_goal_stable_time_s=best_stable,
        eligible_for_terminal_qualification=qualified,native_task_success=native,
        accepted_proof=bool(qualified and native),
        scope='finite recorded instance; World-tick numerical audit; contact-triggered assisted grasp; no continuous-time or pure-friction claim')
    write_json_atomic(root/('prefix_audit.json' if prefix else 'independent_audit.json'),result)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('--prefix',action='store_true',help='Audit a bounded live prefix; cannot grant qualification')
    args=parser.parse_args()
    result=audit_run(args.run,prefix=args.prefix)
    print(json.dumps({k:v for k,v in result.items() if k not in ('identity','grasp_acquisitions','phases')},indent=2))
