"""Contact-respecting force-driven solution exploration; no robot claims."""
import argparse
from collections import deque
import json
from pathlib import Path
import shutil
import sys
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .physics import capture_sources, contact_summary, node_positions


def pose(data, body):
    return data.xpos[body].copy(), Rotation.from_matrix(data.xmat[body].reshape(3, 3))


def cord_disk_crossings(model, data, inner_radius=.051):
    """Count cord crossings of the ring's open disk (a necessary release gate)."""
    center, rotation = pose(data, model.body('target_ring').id)
    local = rotation.inv().apply(node_positions(model, data)-center)
    a, b = local[:-1], local[1:]
    ids = np.flatnonzero(a[:, 2]*b[:, 2] < 0)
    if not len(ids):
        return 0
    u = -a[ids, 2]/(b[ids, 2]-a[ids, 2])
    crossings = a[ids]+u[:, None]*(b[ids]-a[ids])
    return int(np.sum(np.linalg.norm(crossings[:, :2], axis=1) < inner_radius))


def route():
    """Unqualified full candidate including the essential ring-through-slot step.

    Runtime contact, stretch, tracking and release gates determine acceptance.
    This route is retained for reproducible development, not as a solved policy.
    """
    return [['position_ring', 2.0, {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]]}],
     ['lift_bead_outside_ring',
      3.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]], 'bead_right': [[0.11, -0.09, 0.1], None]}],
     ['bead_around_post_above_ring',
      3.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]], 'bead_right': [[0.11, 0.085, 0.1], None]}],
     ['bead_over_ring_into_center',
      3.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]], 'bead_right': [[0, 0.042, 0.1], None]}],
     ['lower_bead_inside_ring',
      2.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]], 'bead_right': [[0, 0.042, 0.045], None]}],
     ['lift_disc_clear_of_table',
      3.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]], 'disc_right': [[0.1, -0.25, 0.13], [0, 0, 0, 1]]}],
     ['disc_to_right',
      3.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]],
       'disc_right': [[0.17, -0.02, 0.16], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]]}],
     ['disc_to_rear',
      3.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]],
       'disc_right': [[0.1, 0.13, 0.19], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]]}],
     ['disc_align',
      2.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]],
       'disc_right': [[-0.004, 0.09, 0.19], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]]}],
     ['disc_through_slot',
      4.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]],
       'disc_right': [[-0.004, -0.09, 0.19], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]]}],
     ['disc_clear_post',
      3.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]],
       'disc_right': [[0.1, -0.18, 0.14], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]]}],
     ['disc_lay_flat',
      3.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]], 'disc_right': [[0.1, -0.24, 0.08], [0, 0, 0, 1]]}],
     ['disc_lower_to_table',
      3.0,
      {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]], 'disc_right': [[0.1, -0.24, 0.0065], [0, 0, 0, 1]]}],
     ['release_disc', 2.0, {'target_ring': [[0, 0.012, 0.034], [0, 0, 0, 1]]}],
     ['lift_ring_above_post', 6, {'target_ring': [[0, 0.012, 0.34], [0, 0, 0, 1]]}],
     ['ring_front_above_post', 5.0, {'target_ring': [[0, -0.14, 0.34], [0, 0, 0, 1]]}],
     ['ring_edgewise_in_front',
      5.0,
      {'target_ring': [[0, -0.14, 0.2], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]]}],
     ['ring_align_slot',
      3.0,
      {'target_ring': [[0, -0.14, 0.17], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]]}],
     ['bead_hold_left_of_ring',
      4.0,
      {'target_ring': [[0, -0.14, 0.17], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]],
       'bead_right': [[-0.06, 0.14, 0.17], None]}],
     ['ring_itself_through_slot',
      7.0,
      {'target_ring': [[0, 0.14, 0.17], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]],
       'bead_right': [[-0.06, 0.14, 0.17], None]}],
     ['bead_through_ring_to_release',
      5.0,
      {'target_ring': [[0, 0.14, 0.17], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]],
       'bead_right': [[0.08, 0.14, 0.17], None]}],
     ['release_bead_before_carry',
      3,
      {'target_ring': [[0, 0.14, 0.17], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]]}],
     ['ring_carry_left',
      4.0,
      {'target_ring': [[-0.24, 0.14, 0.17], [0.0, 0.7071067811865475, 0.0, 0.7071067811865476]],
       'bead_right': [[0.08, 0.14, 0.17], None]}],
     ['lay_ring_flat', 4.0, {'target_ring': [[-0.24, 0.14, 0.1], [0, 0, 0, 1]]}],
     ['ring_lower_to_table', 4.0, {'target_ring': [[-0.24, 0.14, 0.012], [0, 0, 0, 1]]}],
     ['release_and_settle', 5.0, {}]]

def execute(source, output, schedule=None, until=None, force_limit=3., torque_limit=.05, pinch_cord=False, max_settle_extra=0.):
    source, output = Path(source), Path(output)
    specification=json.loads((source/'model/model_spec.json').read_text())
    if specification.get('fem'):
        raise ValueError('This historical full-route executor audits the 1D cord only. '
                         'Use fem_probe for volumetric FEM; full FEM manipulation needs volume/contact auditing.')
    output.mkdir(parents=True, exist_ok=False)
    capture_sources(output)
    shutil.copytree(source/'model', output/'model')
    if pinch_cord:
        tree = ET.parse(output/'model/scene.xml')
        for side in ('left','right'):
            ET.SubElement(tree.getroot().find('equality'), 'connect', name=f'pinch_{side}',
                          body1=f'bead_{side}', body2='cord_0', anchor='0 0 0', active='false',
                          solref='.002 1', solimp='.999 .9999 .001 .5 2')
        tree.write(output/'model/scene.xml', encoding='unicode')
        model = mujoco.MjModel.from_xml_path(str(output/'model/scene.xml'))
    else:
        model = mujoco.MjModel.from_binary_path(str(output/'model/scene.mjb'))
    data = mujoco.MjData(model)
    initial = np.load(source/'final_state.npz')
    data.qpos[:] = initial['qpos']; data.qvel[:] = initial['qvel']
    mujoco.mj_forward(model, data)
    dt = model.opt.timestep
    schedule = schedule or route()
    frames=[]; velocities=[]; times=[]; phases=[]; nodes=[]; actions=[]; depths={}; errors={}
    equalities=[]; equality_data=[]; equality_bodies=[]; pinch_events=[]
    max_force=0.; max_torque=0.; max_attach=0.; max_stretch=0.; worst_stretch=None
    lengths = np.asarray(json.loads((output/'model/model_spec.json').read_text())['cord_segment_lengths'])
    steps = 0; wall=time.monotonic(); executed_schedule=[]; settling_extensions=[]
    cord_sites=[i for i in range(model.nsite) if model.site(i).name.startswith('cord_node_') or model.site(i).name=='cord_tip']
    rigid_ids=[model.body(n).id for n in ('target_ring','bead_left','bead_right','disc_left','disc_right')]
    tail=deque()
    for name, seconds, commands in schedule:
        executed_schedule.append([name, seconds, commands])
        if pinch_cord:
            for side in ('left','right'):
                e=model.equality(f'pinch_{side}').id
                held=f'bead_{side}' in commands
                if held and not data.eq_active[e]:
                    bead_id=model.body(f'bead_{side}').id
                    i=int(np.argmin(np.linalg.norm(node_positions(model,data)-data.xpos[bead_id],axis=1)))
                    node_id=model.body(f'cord_{i}').id
                    model.eq_obj2id[e]=node_id
                    model.eq_data[e,:3]=0
                    model.eq_data[e,3:6]=data.xpos[bead_id]-data.xpos[node_id]
                    pinch_events.append(dict(time_s=float(data.time),side=side,node=i,offset=model.eq_data[e,3:6].tolist()))
                data.eq_active[e]=held
        ids={n:model.body(n).id for n in commands}
        # A compliant contact can prevent reaching the previous setpoint. Start
        # the next interpolation at the measured pose so it cannot jump ahead.
        starts={n:pose(data,ids[n]) for n in commands}
        ends={n:(np.array(v[0]), Rotation.from_quat(v[1]) if v[1] is not None else starts[n][1]) for n,v in commands.items()}
        lerps={n:Slerp([0,1],Rotation.from_matrix([starts[n][1].as_matrix(),ends[n][1].as_matrix()])) for n in commands}
        stage_error={n:0. for n in commands}
        extra=max_settle_extra if not commands else 0.
        for tick in range(round((seconds+extra)/dt)):
            # Split stepping computes current contacts once. The audit and trace
            # below describe the same pre-integration state as the applied force.
            mujoco.mj_step1(model,data)
            u=(tick+1)/round(seconds/dt)
            smooth=u*u*u*(10-15*u+6*u*u)
            ds=30*u*u*(1-u)*(1-u)/seconds
            data.xfrc_applied[:]=0
            for n,body in ids.items():
                actual,r=pose(data,body)
                target=(1-smooth)*starts[n][0]+smooth*ends[n][0]
                velocity=np.zeros(6)
                mujoco.mj_objectVelocity(model,data,mujoco.mjtObj.mjOBJ_BODY,body,velocity,0)
                mass=model.body_mass[body]
                kp=400. if n.startswith('bead') else 1200.
                desired_v=ds*(ends[n][0]-starts[n][0])
                force=kp*(target-actual)+2*np.sqrt(kp*mass)*(desired_v-velocity[3:])+[0,0,mass*9.81]
                force*=min(1.,force_limit/max(np.linalg.norm(force),1e-12))
                torque=np.zeros(3)
                if commands[n][1] is not None:
                    angle=(lerps[n]([smooth])[0]*r.inv()).as_rotvec()
                    torque=3.*angle-.04*velocity[:3]
                    torque*=min(1.,torque_limit/max(np.linalg.norm(torque),1e-12))
                data.xfrc_applied[body]=np.r_[force,torque]
                max_force=max(max_force,float(np.linalg.norm(force)));max_torque=max(max_torque,float(np.linalg.norm(torque)))
                stage_error[n]=max(stage_error[n],float(np.linalg.norm(target-actual)))
            for key,value in contact_summary(model,data).items():
                depths[key]=max(depths.get(key,0),value)
            points=data.site_xpos[cord_sites].copy()
            segment_errors=np.abs(np.linalg.norm(np.diff(points,axis=0),axis=1)/lengths-1)
            current_stretch=float(np.max(segment_errors))
            if current_stretch>max_stretch:
                worst_stretch=dict(time_s=float(data.time),phase=name,segment=int(np.argmax(segment_errors)),
                                   relative_error=current_stretch)
                max_stretch=current_stretch
            for side,node in (('left',0),('right',-1)):
                max_attach=max(max_attach,float(np.linalg.norm(data.site_xpos[model.site(f'disc_{side}_anchor').id]-points[node])))
            speed=0.; velocity=np.zeros(6)
            for body in rigid_ids:
                mujoco.mj_objectVelocity(model,data,mujoco.mjtObj.mjOBJ_BODY,body,velocity,0)
                speed=max(speed,float(np.linalg.norm(velocity[3:])))
            tail.append((float(data.time),speed,not bool(commands)))
            while tail and tail[0][0]<data.time-2:tail.popleft()
            if steps%round(.05/dt)==0:
                frames.append(data.qpos.copy());velocities.append(data.qvel.copy());times.append(data.time)
                phases.append(name);nodes.append(points);actions.append(data.xfrc_applied.copy())
                equalities.append(data.eq_active.copy());equality_data.append(model.eq_data.copy());equality_bodies.append(model.eq_obj2id.copy())
            mujoco.mj_step2(model,data)
            steps+=1
            if (not commands and tick+1>=round(seconds/dt) and steps%round(.05/dt)==0
                    and tail and tail[-1][0]-tail[0][0]>1.99 and max(row[1] for row in tail)<.002):
                break
        actual_seconds=(tick+1)*dt
        executed_schedule[-1][1]=actual_seconds
        if extra:
            settling_extensions.append(dict(phase=name,requested_seconds=seconds,executed_seconds=actual_seconds,max_extra_seconds=extra))
        mujoco.mj_forward(model,data)
        errors[name]=stage_error
        print(name,'t',round(data.time,2),'wall',round(time.monotonic()-wall,1),'error',stage_error,
              'depths',depths,'stretch',max_stretch,'disk_crossings',cord_disk_crossings(model,data),flush=True)
        (output/'checkpoints').mkdir(exist_ok=True)
        np.savez_compressed(output/'checkpoints'/f'{name}.npz',qpos=data.qpos,qvel=data.qvel,time_s=data.time)
        np.savez_compressed(output/'final_state.npz',qpos=data.qpos,qvel=data.qvel,time_s=data.time)
        if until==name:
            break
    ring=data.xpos[model.body('target_ring').id].copy()
    dist=float(np.linalg.norm(ring[:2]))
    warnings={mujoco.mjtWarning(i).name:int(w.number) for i,w in enumerate(data.warning) if w.number}
    checks=dict(ring_away_from_post=dist>.19,ring_on_table=bool(abs(ring[2]-.01)<.002),
                cord_clear_of_ring_disk=cord_disk_crossings(model,data)==0,
                no_active_external_hold=not np.any(data.xfrc_applied),
                no_warnings=not warnings,contact_depth=max(depths.values(),default=0)<.0005,
                limited_stretch=max_stretch<.005,terminal_attachment=max_attach<.0005,
                finite_state=bool(np.all(np.isfinite(data.qpos)) and np.all(np.isfinite(data.qvel))),
                last_two_seconds_released=bool(tail and tail[-1][0]-tail[0][0]>1.99 and all(row[2] for row in tail)),
                final_rigid_speed=bool(tail and max(row[1] for row in tail)<.002),
                tracking=max((v for stage in errors.values() for v in stage.values()),default=0)<.005)
    report=dict(scope='force_driven_fixture_attempt',passed=all(checks.values()),checks=checks,
                full_robot_demo=False,robot_execution=False,pose_writes_after_initialization=False,
                fps=20,simulated_seconds=float(data.time),max_contact_depth_m=depths,
                stage_errors_m=errors,max_external_force_n=max_force,max_external_torque_nm=max_torque,
                max_endpoint_error_m=max_attach,max_relative_segment_extension=max_stretch,
                final_ring_position=ring.tolist(),warnings=warnings)
    report['audit_frequency']='every integration step'
    report['max_final_two_seconds_rigid_speed_m_s']=max((row[1] for row in tail),default=None)
    report['settling_extensions']=settling_extensions
    report['controller_limits'] = dict(force_n=force_limit, torque_nm=torque_limit)
    report['assisted_bead_and_cord_pinch'] = pinch_cord
    report['pinch_events'] = pinch_events
    report['final_cord_disk_crossings'] = cord_disk_crossings(model,data)
    report['worst_segment_extension'] = worst_stretch
    report['stage_start_policy'] = 'measured body pose; minimum-jerk setpoint interpolation'
    np.savez_compressed(output/'states.npz',qpos=frames,qvel=velocities,time_s=times,phase=phases,cord_nodes=nodes,xfrc_applied=actions,
                        eq_active=equalities,eq_data=equality_data,eq_obj2id=equality_bodies)
    mujoco.mj_saveModel(model,str(output/'model/scene.mjb'))
    np.savez_compressed(output/'final_state.npz',qpos=data.qpos,qvel=data.qvel,time_s=data.time)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'schedule.json').write_text(json.dumps(executed_schedule,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    return report


def interactive_stages():
    """Accept JSON stage triples while retaining one continuous MjData episode.

    Simulation time pauses while awaiting the next stage. No state is reset or
    replayed. A JSON object with ``finish: true`` ends and saves the recording.
    """
    for line in sys.stdin:
        item=json.loads(line)
        if isinstance(item,dict) and item.get('finish'):
            return
        if not isinstance(item,list) or len(item)!=3 or float(item[1])<=0:
            raise ValueError('Expected [name, positive seconds, body commands]')
        yield item


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--schedule');p.add_argument('--until')
    p.add_argument('--force-limit', type=float, default=3.)
    p.add_argument('--torque-limit', type=float, default=.05)
    p.add_argument('--pinch-cord', action='store_true')
    p.add_argument('--max-settle-extra',type=float,default=0.,help='Extend unforced stages until the last two seconds meet the speed gate, up to this additional duration')
    p.add_argument('--interactive',action='store_true',help='Read stage triples from stdin; retain one physical episode')
    a=p.parse_args()
    if a.interactive and a.schedule:p.error('--interactive and --schedule are mutually exclusive')
    execute(a.source,a.output,interactive_stages() if a.interactive else json.loads(Path(a.schedule).read_text()) if a.schedule else None,
            a.until,a.force_limit,a.torque_limit,a.pinch_cord,a.max_settle_extra)
