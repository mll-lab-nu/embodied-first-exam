"""Free-body tasks that require independent fingertip motion at a fixed wrist."""
from __future__ import annotations
import math
import xml.etree.ElementTree as ET
import mujoco
import numpy as np

TASK_IDS = {'essential_cube_reorient', 'essential_pen_regrasp'}
PALM_BODY = 'right_hand_C_MC'
PALM_AXES = np.array([[0.,0.,1.],[0.,-1.,0.],[1.,0.,0.]])

def _node(parent, tag, **kwargs):
    return ET.SubElement(parent,tag,{k:' '.join(map(str,v)) if isinstance(v,(list,tuple)) else str(v) for k,v in kwargs.items()})

def _geom(parent,name,kind,size,pos=(0,0,0),color=(.15,.53,.83,1),**kwargs):
    attrs={'density':500,'friction':(1.5,.001,.0001),'condim':6,'solref':(.008,1),'solimp':(.95,.99,.001)}
    attrs.update(kwargs)
    return _node(parent,'geom',name=name,type=kind,size=size,pos=pos,rgba=color,**attrs)

def build(world,spec):
    """Add a normal-gravity free object; no external constraint or actuator."""
    p=spec['parameters']
    contact={}
    for parameter,attribute in [('contact_solver_priority','priority'),('contact_solver_solimp','solimp'),('contact_solver_solref','solref')]:
        if parameter in p:contact[attribute]=p[parameter]
    b=_node(world,'body',name='object',pos=p.get('initial_position',[.025,-.02,.35]),quat=p.get('initial_quaternion',[1,0,0,0]))
    _node(b,'freejoint',name='object_free')
    if spec['id']=='essential_cube_reorient':
        side=p.get('side_m',.028)
        _geom(b,'task_object',p.get('collision_shape','box'),[side/2] if p.get('collision_shape')=='sphere' else [side/2]*3,**contact)
        colors=[(.95,.2,.18,1),(.2,.82,.3,1),(.95,.65,.15,1)]
        for i,col in enumerate(colors):
            if p.get('collision_shape')=='sphere':
                pos=[0.,0.,0.];pos[i]=side*.465
                _geom(b,f'object_marker_{i}','sphere',[side*.075],pos,col,contype=0,conaffinity=0,density=0)
            else:
                size=[side*.30]*3;size[i]=.0005
                pos=[0.,0.,0.];pos[i]=side/2+.0006
                _geom(b,f'object_marker_{i}','box',size,pos,col,contype=0,conaffinity=0,density=0)
    else:
        radius=p.get('radius_m',.006)
        half=p.get('length_m',.12)/2-radius
        _geom(b,'task_object','capsule',[radius,half],**contact)
        _geom(b,'object_tip','sphere',[radius*.9],(0,0,half),(.95,.63,.12,1),contype=0,conaffinity=0,density=0)
        _geom(b,'object_grip_band','cylinder',[radius*1.025,p.get('grip_band_half_width_m',.018)],(0,0,p.get('grip_band_z',.025)),(.95,.63,.12,1),contype=0,conaffinity=0,density=0)
    return {}

def reset(session):
    """Initialize only the permitted, fixed starting pose and hand joints."""
    p=session.spec['parameters'];m,d=session.model,session.data
    d.qpos[session._act_qpos[:6]]=p.get('initial_wrist',[-.08,0,.29,0,0,0])
    joints=p.get('initial_fingers',{})
    for name,value in joints.items():
        j=m.joint(name).id;d.qpos[m.jnt_qposadr[j]]=np.clip(value,*m.jnt_range[j])
    j=m.joint('object_free').id;a=m.jnt_qposadr[j]
    d.qpos[a:a+3]=p.get('initial_position',[.025,-.02,.35])
    d.qpos[a+3:a+7]=p.get('initial_quaternion',[1,0,0,0])
    d.ctrl[:]=d.qpos[session._act_qpos]
    d.ctrl[:6]=p.get('initial_wrist',[-.08,0,.29,0,0,0])
    mujoco.mj_forward(m,d)
    if p.get('reset_gravity_compensation',False):
        adr=m.jnt_dofadr[session._act_jids]
        d.ctrl[6:]+=d.qfrc_bias[adr[6:]]/m.actuator_gainprm[6:,0]
        d.ctrl[:]=np.clip(d.ctrl,*m.actuator_ctrlrange.T)
    for _ in range(p.get('settle_steps',0)):
        mujoco.mj_step(m,d)
    d.time=0.0
    mujoco.mj_forward(m,d)
    if session.task=='essential_pen_regrasp':
        palm_contacts=0;wrench=np.zeros(6)
        for i in range(d.ncon):
            c=d.contact[i];names=[m.geom(int(g)).name or '' for g in (c.geom1,c.geom2)]
            if 'task_object' in names and any(name.startswith('palm') for name in names):
                mujoco.mj_contactForce(m,d,i,wrench)
                if np.linalg.norm(wrench[:3])>.01:palm_contacts+=1
        session._pen_initial_palm_contacts=float(palm_contacts)
        axis=d.body('object').xmat.reshape(3,3)[:,2]
        session._pen_initial_horizontal_error=math.asin(float(np.clip(abs(axis[2]),0,1)))
        if p.get('require_initial_palm_contact',False) and palm_contacts<1:
            raise ValueError('The frozen pen reset must begin against the palm')
        if session._pen_initial_horizontal_error>math.radians(p.get('initial_horizontal_max_deg',90)):
            raise ValueError('The frozen pen reset must begin nearly horizontal')

def _angle(rotation):
    return math.acos(float(np.clip((np.trace(rotation)-1)/2,-1,1)))

def _rotation(axis,angle):
    c,s=math.cos(angle),math.sin(angle)
    if axis==0:return np.array([[1,0,0],[0,c,-s],[0,s,c]])
    if axis==1:return np.array([[c,0,s],[0,1,0],[-s,0,c]])
    return np.array([[c,-s,0],[s,c,0],[0,0,1]])

def features(session):
    """Measure the physical object pose and contact geometry in the palm frame."""
    m,d=session.model,session.data;palm=d.body(PALM_BODY);obj=d.body('object')
    frame=palm.xmat.reshape(3,3)@PALM_AXES
    relative=frame.T@obj.xmat.reshape(3,3)
    initial=session._orientation_initial['object'];rotation=relative@initial.T
    xyz=frame.T@(obj.xpos-palm.xpos)-session._relative_initial['object']
    out={'object_displacement':float(np.linalg.norm(xyz)),'object_height':float(obj.xpos[2]),'object_palm_distance':float(np.linalg.norm(obj.xpos-palm.xpos))}
    hand_contacts=0
    wrench=np.zeros(6)
    for i in range(d.ncon):
        contact=d.contact[i]
        names=[m.geom(int(g)).name or '' for g in (contact.geom1,contact.geom2)]
        if 'task_object' not in names:continue
        other_geom=int(contact.geom2) if names[0]=='task_object' else int(contact.geom1)
        hand_body=int(m.geom_bodyid[other_geom]);palm_id=m.body(PALM_BODY).id
        while hand_body and hand_body!=palm_id:hand_body=int(m.body_parentid[hand_body])
        if hand_body!=palm_id:continue
        mujoco.mj_contactForce(m,d,i,wrench)
        if np.linalg.norm(wrench[:3])>.005:hand_contacts+=1
    out['object_hand_contacts']=float(hand_contacts)
    if session.task=='essential_cube_reorient':
        first=_rotation(1,math.pi/2);second=_rotation(0,math.pi/2)@first
        out.update(cube_error_1=_angle(rotation@first.T),cube_error_2=_angle(rotation@second.T),cube_error_3=_angle(rotation))
    else:
        axis=initial[:,2]
        out.update(pen_axial=float(xyz@axis),pen_angle=math.acos(float(np.clip(relative[:,2]@axis,-1,1))))
        grip_contacts=set();palm_contacts=0
        wrench=np.zeros(6)
        for i in range(d.ncon):
            c=d.contact[i];g1,g2=int(c.geom1),int(c.geom2)
            for hand,objg in [(g1,g2),(g2,g1)]:
                if (m.geom(objg).name or '')!='task_object':continue
                mujoco.mj_contactForce(m,d,i,wrench)
                if np.linalg.norm(wrench[:3])<.01:continue
                hn=m.geom(hand).name or ''
                if hn.startswith('palm'):palm_contacts+=1
                if hand in session._finger_geoms:
                    local=obj.xmat.reshape(3,3).T@(c.pos-obj.xpos)
                    if abs(local[2]-session.spec['parameters'].get('grip_band_z',.025))<session.spec['parameters'].get('grip_band_half_width_m',.018):grip_contacts.add(session._finger_geoms[hand])
        out.update(pen_grip_contacts=float(len(grip_contacts)),pen_palm_contacts=float(palm_contacts),pen_initial_palm_contacts=session._pen_initial_palm_contacts,pen_initial_horizontal_error=session._pen_initial_horizontal_error)
        for finger in ('thumb','index','middle'):
            out['pen_grip_'+finger]=float(finger in grip_contacts)
    return out


def configure(source, spec):
    """Optionally separate friction regularization from normal pad compliance.

    Explicit pairs retain the default scene's mixed normal and friction material
    values. Only the friction solver time constant is changed by this declared
    instance parameter; no object joint, force, or motion constraint is added.
    """
    p=spec['parameters']
    if 'contact_friction_solref' not in p:
        return
    contact=source.find('contact')
    if contact is None:
        contact=_node(source,'contact')
    for finger in ('thumb','index','middle','ring','pinky'):
        _node(contact,'pair',name=f'object_{finger}_patch',geom1='task_object',geom2=f'right_{finger}_fingertip_collision',condim=6,friction=(1.5,1.5,.005,.0001,.0001),solref=(.034,.95),solimp=(.925,.97,.001,.5,2),solreffriction=p['contact_friction_solref'])


def snapshot(session):
    """Fingerprint immutable reset evidence separately from current contacts."""
    if session.task!='essential_pen_regrasp':
        return {}
    return {'initial_palm_contacts':session._pen_initial_palm_contacts,'initial_horizontal_error':session._pen_initial_horizontal_error}
