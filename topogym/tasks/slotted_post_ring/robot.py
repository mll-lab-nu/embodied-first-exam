"""ALOHA physical grasp exploration, with explicit pregrasp assistance."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.tasks.cast_coil.robot_plan import Kinematics, PAD_CENTER
from .physics import PhysicsSettings, build_model, values, wxyz, node_positions, contact_summary
from .geometry import SlottedPostLayout


def rotation(x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    x /= np.linalg.norm(x); y /= np.linalg.norm(y)
    return Rotation.from_matrix(np.column_stack([x, y, np.cross(x, y)]))


def robot_contacts(model, data):
    result = []
    for c in data.contact:
        if c.dist >= 0:
            continue
        names = [model.body(model.geom_bodyid[g]).name if g >= 0 else 'cord' for g in c.geom]
        if not any('/' in n for n in names):
            continue
        if all(n.endswith('/base_link') or n == 'world' for n in names):
            continue
        grasp = (any(n.startswith('left/') and 'finger' in n for n in names) and 'target_ring' in names
                 or any(n.startswith('right/') and 'finger' in n for n in names) and 'bead_right' in names)
        result.append(dict(kind='assisted_grasp_contact' if grasp else 'forbidden_robot_contact',
                           bodies=names, depth_m=float(-c.dist)))
    return result


def execute(source, output, dt=.000125, plan_only=False):
    source, output = Path(source), Path(output)
    specification=json.loads((source/'model/model_spec.json').read_text())
    if specification.get('fem'):
        raise ValueError('The historical robot executor requires a 1D cord source. '
                         'Volumetric FEM robot execution is not yet implemented or qualified.')
    output.mkdir(parents=True, exist_ok=False)
    settings = PhysicsSettings(**specification['settings'])
    model, data, _ = build_model(output/'model', replace(settings, dt=dt),
                               layout=SlottedPostLayout(**specification['layout']),robot=True)
    initial = np.load(source/'final_state.npz')
    data.qpos[16:] = initial['qpos']; data.qvel[16:] = initial['qvel']
    mujoco.mj_forward(model, data)
    ring = data.xpos[model.body('target_ring').id].copy()
    bead = data.xpos[model.body('bead_right').id].copy()
    cfg = OmegaConf.load(Path(__file__).resolve().parents[3]/'configs/robot_control_configs/aloha_position_ik.yaml')
    k = Kinematics(cfg)
    rotations = {'left':rotation([1,0,-1],[1,0,1]), 'right':rotation([0,-1,-1],[1,0,0])}
    start = {'left':ring+[-.061,0,0], 'right':bead}
    for side in ('left','right'):
        errors = k.solve(side, start[side], rotations[side])
        if errors[0] > 1e-5 or errors[1] > 1e-4:
            raise RuntimeError(f'Initial {side} grasp is unreachable: {errors}')
        for name in ('left_finger','right_finger'):
            k.q[k.model.joint(f'{side}/{name}').qposadr[0]] = .018 if side == 'left' else .0277
    data.qpos[:16] = k.q
    mujoco.mj_forward(model, data)
    root = ET.parse(output/'model/scene.xml').getroot()
    equality = root.find('equality')
    hand = model.body('left/gripper_link').id
    rh = Rotation.from_matrix(data.xmat[hand].reshape(3,3))
    rr = Rotation.from_matrix(data.xmat[model.body('target_ring').id].reshape(3,3))
    relative = rh.inv().apply(ring-data.xpos[hand])
    ET.SubElement(equality,'weld',name='left_ring_grasp',body1='left/gripper_link',body2='target_ring',
                  relpose=values(np.r_[relative,wxyz(rh.inv()*rr)]),torquescale='.1',
                  solref='.002 1',solimp='.999 .9999 .001 .5 2')
    gripper = root.find(".//body[@name='right/gripper_link']")
    ET.SubElement(gripper,'site',name='right_assisted_bead_tcp',pos=values(PAD_CENTER),group='4',size='.001')
    body = root.find(".//body[@name='bead_right']")
    ET.SubElement(body,'site',name='right_bead_center',pos='0 0 0',group='4',size='.001')
    ET.SubElement(equality,'connect',name='right_bead_grasp',site1='right_assisted_bead_tcp',site2='right_bead_center',
                  solref='.002 1',solimp='.999 .9999 .001 .5 2')
    xml = ET.tostring(root,encoding='unicode');(output/'model/scene.xml').write_text(xml)
    state = data.qpos.copy(); velocity = data.qvel.copy()
    model = mujoco.MjModel.from_xml_string(xml); data = mujoco.MjData(model)
    data.qpos[:] = state; data.qvel[:] = velocity
    mujoco.mj_forward(model,data)
    mujoco.mj_saveModel(model,str(output/'model/scene.mjb'))
    actuated = model.jnt_qposadr[model.actuator_trnid[:,0]]
    data.ctrl[:] = data.qpos[actuated]
    initial_contacts = robot_contacts(model,data)
    invalid = [c for c in initial_contacts if c['kind']=='forbidden_robot_contact' and c['depth_m']>.0001]
    (output/'initial_grasp_check.json').write_text(json.dumps(dict(contacts=initial_contacts,passed=not invalid,
            pregrasp=True,assistance='left weld and right ball connection; no friction-only grasp claim'),indent=2)+'\n')
    if invalid or plan_only:
        np.savez_compressed(output/'initial_state.npz',qpos=data.qpos,qvel=data.qvel)
        print(json.dumps(dict(initial_grasp_passed=not invalid,contacts=initial_contacts),indent=2))
        return
    left = np.array([-.061,.012,.034])
    stages = [('pregrasp_hold',1.,start,True,True),
              ('position_ring',2.,{'left':left,'right':bead},True,True),
              ('bead_lift',3.,{'left':left,'right':[.11,-.09,.10]},True,True),
              ('bead_around_post',3.,{'left':left,'right':[.11,.085,.10]},True,True),
              ('bead_inside',3.,{'left':left,'right':[0,.042,.10]},True,True),
              ('bead_lower',2.,{'left':left,'right':[0,.042,.045]},True,True),
              ('release_bead',1.,{'left':left,'right':[0,.042,.045]},True,False),
              ('retreat_right',3.,{'left':left,'right':[.11,.085,.10]},True,False),
              ('release_ring',1.,{'left':left,'right':[.11,.085,.10]},False,False),
              ('retreat_left',3.,{'left':[-.18,.012,.20],'right':[.11,.085,.10]},False,False),
              ('free_settle',3.,{'left':[-.18,.012,.20],'right':[.11,.085,.10]},False,False)]
    # Solve and validate the whole Cartesian plan before the physical run.
    rows=[]; last={s:np.asarray(p) for s,p in start.items()}; now=0.; bad=[]
    for phase, duration, target, held_left, held_right in stages:
        target={s:np.asarray(p) for s,p in target.items()}
        for local in np.arange(0,duration+.025,.05):
            u=min(1,local/duration); blend=u*u*u*(10-15*u+6*u*u)
            for side, held in [('left',held_left),('right',held_right)]:
                p=last[side]*(1-blend)+target[side]*blend
                ep,ea=k.solve(side,p,rotations[side])
                if ep>1e-5 or ea>1e-4:bad.append(dict(phase=phase,side=side,position_m=ep,angle_rad=ea))
                for finger in ('left_finger','right_finger'):
                    k.q[k.model.joint(f'{side}/{finger}').qposadr[0]]=(.018 if side=='left' else .0277) if held else .037
            rows.append(dict(time_s=now+local,q=k.q.copy().tolist(),phase=phase,held=[held_left,held_right]))
        now+=duration; last=target
    (output/'plan.json').write_text(json.dumps(dict(rows=rows,failures=bad),indent=2)+'\n')
    if bad:raise RuntimeError(f'{len(bad)} unreachable plan samples')
    frames=[]; vframes=[]; eqframes=[]; times=[]; phases=[]; nodes=[]; controls=[]
    samples=np.array([r['time_s'] for r in rows]); qs=np.array([r['q'] for r in rows]);depths={}; violations=[]
    wall=time.monotonic();last_phase=None; max_force=np.zeros(model.nu)
    max_joint_force=np.zeros(16); max_attachment=0.; max_stretch=0.; max_bead_error=0.; tail_speed=0.
    lengths=np.asarray(json.loads((output/'model/model_spec.json').read_text())['cord_segment_lengths'])
    cord_sites=[i for i in range(model.nsite) if model.site(i).name.startswith('cord_node_') or model.site(i).name=='cord_tip']
    dynamic_rigids=[model.body(n).id for n in ('target_ring','bead_left','bead_right','disc_left','disc_right')]
    for step in range(round(now/dt)+1):
        t=data.time; i=min(np.searchsorted(samples,t,side='right')-1,len(rows)-2);i=max(i,0)
        u=np.clip((t-samples[i])/max(samples[i+1]-samples[i],1e-12),0,1)
        command=qs[i]*(1-u)+qs[i+1]*u;data.ctrl[:]=command[actuated]
        for grasp,held in zip(('left_ring_grasp','right_bead_grasp'),rows[i]['held']):data.eq_active[model.equality(grasp).id]=held
        mujoco.mj_step1(model,data)
        for key,value in contact_summary(model,data).items():depths[key]=max(depths.get(key,0),value)
        invalid=[c for c in robot_contacts(model,data) if c['kind']=='forbidden_robot_contact' and c['depth_m']>.0005]
        if invalid and len(violations)<100:violations.append(dict(time_s=t,contacts=invalid))
        points=data.site_xpos[cord_sites].copy()
        max_stretch=max(max_stretch,float(np.max(np.abs(np.linalg.norm(np.diff(points,axis=0),axis=1)/lengths-1))))
        for side,node in [('left',0),('right',-1)]:
            max_attachment=max(max_attachment,float(np.linalg.norm(data.site_xpos[model.site(f'disc_{side}_anchor').id]-points[node])))
        if data.eq_active[model.equality('right_bead_grasp').id]:
            max_bead_error=max(max_bead_error,float(np.linalg.norm(data.site_xpos[model.site('right_assisted_bead_tcp').id]-data.site_xpos[model.site('right_bead_center').id])))
        if t>=now-2:
            velocity=np.zeros(6)
            for body in dynamic_rigids:
                mujoco.mj_objectVelocity(model,data,mujoco.mjtObj.mjOBJ_BODY,body,velocity,0)
                tail_speed=max(tail_speed,float(np.linalg.norm(velocity[3:])))
        if step%round(.05/dt)==0:
            frames.append(data.qpos.copy());vframes.append(data.qvel.copy());eqframes.append(data.eq_active.copy())
            times.append(t);phases.append(rows[i]['phase']);nodes.append(points);controls.append(data.ctrl.copy())
        if rows[i]['phase']!=last_phase:
            last_phase=rows[i]['phase'];print(last_phase,'t',round(t,2),'wall',round(time.monotonic()-wall,1),flush=True)
        if t<now:
            mujoco.mj_step2(model,data)
            max_force=np.maximum(max_force,np.abs(data.actuator_force))
            max_joint_force=np.maximum(max_joint_force,np.abs(data.qfrc_actuator[:16]))
    warnings={mujoco.mjtWarning(i).name:int(w.number) for i,w in enumerate(data.warning) if w.number}
    checks=dict(no_forbidden_contacts=not violations,contact_depth=max(depths.values(),default=0)<.0005,
                terminal_attachment=max_attachment<.0005,limited_stretch=max_stretch<.005,
                assisted_bead_connection=max_bead_error<.001,final_rigid_speed=tail_speed<.002,
                joint_force_limits=bool(np.all(max_joint_force<=model.jnt_actfrcrange[:16,1]+1e-8)),
                no_warnings=not warnings,all_assistance_released=not any(data.eq_active[model.equality(n).id] for n in ('left_ring_grasp','right_bead_grasp')))
    report=dict(scope='partial_robot_bead_repositioning',passed=all(checks.values()),checks=checks,
                full_robot_demo=False,robot_execution=True,
                pregrasp=True,assistance='left ring weld; right bead ball connection',pose_writes_after_initialization=False,
                fps=20,simulated_seconds=float(data.time),max_contact_depth_m=depths,forbidden_contacts=violations,
                maximum_unclamped_actuator_force=max_force.tolist(),maximum_actual_generalized_joint_force=max_joint_force.tolist(),
                max_endpoint_error_m=max_attachment,max_relative_segment_extension=max_stretch,
                max_assisted_bead_error_m=max_bead_error,max_final_two_seconds_rigid_speed_m_s=tail_speed,warnings=warnings,
                audit_frequency='every integration step')
    np.savez_compressed(output/'states.npz',qpos=frames,qvel=vframes,eq_active=eqframes,time_s=times,
                        phase=phases,cord_nodes=nodes,ctrl=controls)
    np.savez_compressed(output/'final_state.npz',qpos=data.qpos,qvel=data.qvel,time_s=data.time)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--dt',type=float,default=.000125)
    p.add_argument('--initial-grasp-only','--plan-only',dest='plan_only',action='store_true',
                   help='Check only the initial pregrasp; do not plan or execute the trajectory')
    a=p.parse_args();execute(a.source,a.output,a.dt,a.plan_only)
