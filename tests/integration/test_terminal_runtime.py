"""Real terminal wiring evidence; these probes do not qualify solved policies."""
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import traceback
import xml.etree.ElementTree as ET
import numpy as np
import pytest

from runtime_evidence import RuntimeEvidence
from topogym.config import SimulatorConfig
from topogym.simulator.env import Env
from topogym.utils.arrays import to_numpy
from topogym.utils.io import to_jsonable

pytestmark=[pytest.mark.genesis,pytest.mark.render]
TASKS=('buzz_wire_3d','lock_picking','fiber_bundling','rope_threading','knot_untying',
       'cast_keyhole','horseshoe_ring','hedgehog_in_cage','interlocked_claws','slotted_post_ring','orbits',
       'cast_coil','blanket_flatten')


def setup(name,task_id):
    root=os.environ.get('TOPOGYM_TEST_OUTPUT')
    assert root, 'Use scripts/test_base_tasks.py --checks terminal'
    cfg=SimulatorConfig(task_id=task_id,variation_id=os.environ.get('TOPOGYM_TEST_VARIATION','base'),
        compute_backend='cuda',precision='64',enable_rgb=True,enable_privileged=True,
        work_dir=Path(root)/name/'episodes')
    evidence=RuntimeEvidence(Path(root)/name,task_id,cfg)
    evidence.report['scope']='Terminal mechanism/wiring only; no successful robot task or reachable placement claim'
    evidence.save()
    return Env(cfg), evidence


@pytest.mark.parametrize('task_id',TASKS)
def test_terminal_birth_and_rewind(task_id):
    env,evidence=setup('terminal_'+task_id,task_id); failure=None
    try:
        with evidence.stage('cuda_preflight'):
            assert evidence.report['hardware']['cuda_available'], 'CUDA unavailable; runtime qualification not executed'
        with evidence.stage('real_birth') as stage:
            obs,info=env.reset(seed=0)
            evidence.sample(env,obs,info,label='initial')
            stage['terminal_metadata']=to_jsonable(env.episode_metadata['terminal'])
            birth=env.state_history[0].ref
            original_task=to_jsonable(env._task.get_state())
            original_events=deepcopy(env._world.read_state().get('contact_events'))
            original_release=to_jsonable(env._world.read_state().get('release_geometry'))
            if env._task.final_settling_spec() is not None:
                assert original_release['complete'], original_release
                assert original_release['physics_step']==0
                assert original_release['robot_present'] and original_release['robot_bounds_m']
                assert 'final_settling' in original_task
            if task_id=='buzz_wire_3d':
                assert original_events['geometry_roles_complete']
                assert original_events['substeps_complete']
            if task_id=='fiber_bundling':
                assert original_events['geometry_roles_complete'] and original_events['robot_geometry_complete']
                assert original_events['substeps_complete']
                assert env._task.goal_complete and info['evaluation_status']=='available'
                assert env._task.task_state['contact_coverage_complete']
            if hasattr(env._task,'goal_region'):
                assert 'goal_region' in env._world.entities
                assert not env._world.entities['goal_region'].geoms
                assert not env._task.result.metrics['all_target_inside']
        with evidence.stage('default_timing_monitor'):
            for _ in range(8):
                obs,_,done,truncated,info=env.step({})
                evidence.sample(env,obs,info)
                assert not done and not truncated, info
                if task_id=='buzz_wire_3d':
                    summary=env._world.read_state()['contact_events']
                    assert summary['sampled_substeps']==env.config.solver_substeps
                    assert summary['substeps_complete'] and summary['geometry_roles_complete']
                    assert summary==env._world.read_state()['contact_events']
                if task_id=='fiber_bundling':
                    summary=env._world.read_state()['contact_events']
                    assert summary['sampled_substeps']==env.config.solver_substeps
                    assert summary['substeps_complete'] and summary['robot_geometry_complete']
                    assert env._task.task_state['contact_coverage_complete']
        with evidence.stage('restore_terminal_history_and_event_summary'):
            obs,info=env.privileged.rewind_to(birth)
            evidence.sample(env,obs,info,label='rewind')
            assert to_jsonable(env._task.get_state())==original_task
            assert env._world.read_state().get('contact_events')==original_events
            assert to_jsonable(env._world.read_state().get('release_geometry'))==original_release
        if task_id=='buzz_wire_3d':
            with evidence.stage('deliberate_geometric_touch_probe') as stage:
                # Owner-only mechanism probe, explicitly not a robot action/solution.
                monitor=env._world._contact_collector
                geoms=[g for e in env._world.entities.values() for l in getattr(e,'links',()) for g in l.geoms]
                wire=next(g for g in geoms if monitor.roles.get(g.idx)=='wire_metal' and g.type.name=='SPHERE')
                wand=next(g for g in geoms if monitor.roles.get(g.idx)=='wand_metal' and g.type.name=='SPHERE')
                entity=env._world.entities['wand']
                delta=to_numpy(wire.get_pos(relative=False))-to_numpy(wand.get_pos(relative=False))
                delta[2]+=float(wire.data[0]+wand.data[0])-.00005
                entity.set_pos(to_numpy(entity.get_pos(relative=False))+delta,zero_velocity=True,relative=False)
                stage['external_pose_probe_offset_m']=delta.tolist()
                obs,_,done,truncated,info=env.interaction().step({})
                evidence.sample(env,obs,info,label='touch_probe')
                assert done and not truncated and info['failure_code']=='wire_touched'
                assert info['task_outcome']=='failure' and info['physics_steps']==1
                assert env._world.read_state()['contact_events']['substeps_complete']
                obs,info=env.privileged.rewind_to(birth)
                evidence.sample(env,obs,info,label='rewind_before_touch')
                assert not env._task.result.terminated
                assert to_jsonable(env._task.get_state())==original_task
    except BaseException:
        failure=traceback.format_exc(); raise
    finally:
        try: evidence.close(failure)
        finally: env.close()


@pytest.mark.parametrize('target_role',('fiber_strand','fiber_sheath'))
def test_fiber_native_gripper_contact_probe(target_role):
    """Owner pose intervention and native collision query, not a robot solution.

    A static narrowphase query first isolates shape identity, followed by a
    normal Env action to check sampled contacts and public terminal feedback.
    """
    env,evidence=setup('terminal_fiber_'+target_role,'fiber_bundling'); failure=None
    try:
        with evidence.stage('cuda_preflight'):
            assert evidence.report['hardware']['cuda_available'], 'CUDA unavailable; contact probe not executed'
        with evidence.stage('real_birth'):
            obs,info=env.reset(seed=0); evidence.sample(env,obs,info,label='initial')
            birth=env.state_history[0].ref
            original=to_jsonable(env._task.get_state())
            events=deepcopy(env._world.read_state()['contact_events'])
            monitor=env._world._contact_collector
            assert events['geometry_roles_complete'] and events['robot_geometry_complete']
        with evidence.stage('native_collision_pose_probe') as stage:
            robot=env._world.entities['robot']
            gripper=next(g for link in robot.links if link.name=='left_finger' for g in link.geoms)
            target_name=('fiber_00_08' if target_role=='fiber_strand' else 'trunk_03')
            target=next(g for link in env._world.entities['fiber_bundle'].links if link.name==target_name
                        for g in link.geoms if g.type.name==('CAPSULE' if target_role=='fiber_strand' else 'CYLINDER'))
            assert monitor.roles[target.idx]==target_role and monitor.robot_parts[gripper.idx]=='gripper'
            delta=to_numpy(target.get_pos(relative=False))-to_numpy(gripper.get_pos(relative=False))
            stage['intervention']='Translate the whole robot at physics_step=0 to first shallow contact; query collision, then advance a normal Env action'
            stage['target_geom']=target_name
            aligned=to_numpy(robot.get_pos(relative=False))+delta
            def pose_contacts(height):
                robot.set_pos(aligned+np.array([0.,0.,height]),zero_velocity=True,relative=False)
                monitor.birth()
                return env._world.read_state()['contact_events']
            def desired_contacts(summary):
                return [event for event in summary['events'] if any(
                    event[f'role_{a}']==target_role and event[f'role_{b}']=='robot'
                    and event[f'robot_part_{b}']=='gripper' for a,b in (('a','b'),('b','a')))]
            # Start above the bundle, then find the first native collision.
            # Center overlap would create centimetres of penetration and is
            # unsuitable for the shared runtime evidence's 1 mm safety bound.
            clear=.3
            assert not desired_contacts(pose_contacts(clear))
            for height in np.linspace(.29,0.,30):
                if desired_contacts(pose_contacts(float(height))):
                    contact=float(height)
                    break
                clear=float(height)
            else:
                raise AssertionError('No gripper contact along the owner pose probe')
            for _ in range(18):
                height=(clear+contact)/2
                if desired_contacts(pose_contacts(height)):
                    contact=height
                else:
                    clear=height
            summary=pose_contacts(contact-.00005)
            stage['robot_translation_m']=(delta+np.array([0.,0.,contact-.00005])).tolist()
            stage['maximum_initial_penetration_m']=max((event['penetration_m'] for event in summary['events']),default=0.)
            assert stage['maximum_initial_penetration_m']<=.001
            state=env._world.read_state()
            summary=state['contact_events']
            assert desired_contacts(summary), 'Native gripper contact with the target material was not observed'
            reached,reason,metrics,_=env._task.evaluate_transition(state,env._task.task_state)
            stage['measured_contacts']=to_jsonable(summary)
            stage['task_predicate']=dict(reached=bool(reached),failure=reason,metrics=to_jsonable(metrics))
            assert reason==('fiber_gripper_contact' if target_role=='fiber_strand' else None)
        with evidence.stage('native_contact_tick') as stage:
            # RecordingSession requires increasing saved state IDs; the pose
            # intervention is documented above and recorded after a real tick.
            obs,reward,done,truncated,info=env.interaction().step({})
            evidence.sample(env,obs,info,label='owner_contact_tick')
            stage['public_feedback']=to_jsonable(info)
            summary=env._world.read_state()['contact_events']
            assert summary['substeps_complete'] and summary['sampled_substeps']==env.config.solver_substeps
            if target_role=='fiber_strand':
                assert done and not truncated and reward==0
                assert info['task_outcome']=='failure' and info['failure_code']=='task_failed'
                assert env._task.result.reason=='fiber_gripper_contact' and info['physics_steps']==1
            else:
                assert not done and not truncated and info['task_outcome']=='ongoing'
        with evidence.stage('rewind_before_pose_probe'):
            obs,info=env.privileged.rewind_to(birth); evidence.sample(env,obs,info,label='rewind')
            assert to_jsonable(env._task.get_state())==original
            assert env._world.read_state()['contact_events']==events
    except BaseException:
        failure=traceback.format_exc(); raise
    finally:
        try: evidence.close(failure)
        finally: env.close()


@pytest.mark.parametrize('with_frame',(True,False),ids=('pin_slot','negative_control'))
def test_lock_physical_stops_without_joint_limits(with_frame,monkeypatch):
    """Torque an isolated real rotor, with URDF angular limits removed in both cases."""
    from topogym.tasks.lock_picking.common import LockPickingTask
    import topogym.simulator.env as module
    class Probe(LockPickingTask):
        def declare(self,*args,**kwargs):
            spec=super().declare(*args,**kwargs)
            disc=next(e for e in spec.entities if e.name=='lock_disc_0')
            tree=ET.parse(disc.asset_path)
            joint=tree.find(".//joint[@name='disc_hinge']")
            joint.set('type','continuous')
            limit=joint.find('limit')
            if limit is not None:
                limit.attrib.pop('lower',None); limit.attrib.pop('upper',None)
            tree.write(disc.asset_path)
            keep={'lock_base','lock_disc_0'} | ({'lock_frame_0'} if with_frame else set())
            return replace(spec,entities=tuple(e for e in spec.entities if e.name in keep),
                metadata={**spec.metadata,'probe_joint_limits_disabled':True,'probe_stop_frame_present':with_frame})
        def evaluate_state(self,state):
            return False,None,{'evaluation_status':'unavailable','mechanism_probe':True}
    monkeypatch.setattr(module,'task_definition',lambda *args:Probe)
    name='terminal_lock_'+('pin_slot' if with_frame else 'negative_control')
    env,evidence=setup(name,'lock_picking'); failure=None
    try:
        with evidence.stage('cuda_preflight'):
            assert evidence.report['hardware']['cuda_available'], 'CUDA unavailable; runtime qualification not executed'
        with evidence.stage('joint_limits_disabled_birth') as stage:
            obs,info=env.reset(seed=0); evidence.sample(env,obs,info,label='initial')
            stage['mechanism']=dict(joint_limits=False,physical_frame=with_frame,external_torque_nm=.02)
            rotor=env._world.entities['lock_disc_0']; joint=rotor.get_joint('disc_hinge')
            indices=joint.dofs_idx_local
            limits=np.stack([to_numpy(v) for v in rotor.get_dofs_limit(indices)])
            assert not np.isfinite(limits).any(), limits
            lo,hi=env._task.config['rotor_stops'][0]['bounds_deg']
            anchor=env.state_history[0].ref
        def drive(torque,steps,label):
            trace=[]
            rotor.control_dofs_force([torque],indices)
            for _ in range(steps):
                obs,_,done,timeout,info=env.step({})
                evidence.sample(env,obs,info,label=label)
                angle=float(np.degrees(to_numpy(rotor.get_dofs_position(indices)).item()))
                trace.append(angle)
                assert not done and not timeout
            return trace
        with evidence.stage('positive_torque_at_stop') as stage:
            forward=drive(.02,160,'positive_torque')
            stage['angles_deg']=forward
            if with_frame:
                assert max(forward)<=hi+.5 and forward[-1]>=hi-2
                assert min(forward)>=lo-.5
            else:
                assert max(forward)>hi+5, 'Negative control must cross the absent stop'
        if with_frame:
            with evidence.stage('reverse_torque_leaves_stop_and_hits_other_end') as stage:
                reverse=drive(-.02,200,'reverse_torque'); stage['angles_deg']=reverse
                assert min(reverse)>=lo-.5 and reverse[-1]<=lo+2
            with evidence.stage('rewind_and_replay_torque') as stage:
                obs,info=env.privileged.rewind_to(anchor)
                evidence.sample(env,obs,info,label='rewind')
                replay=drive(.02,160,'replay_positive_torque')
                stage['maximum_angle_error_deg']=float(np.max(np.abs(np.array(replay)-forward)))
                np.testing.assert_allclose(replay,forward,rtol=0,atol=.02)
    except BaseException:
        failure=traceback.format_exc(); raise
    finally:
        try: evidence.close(failure)
        finally: env.close()
