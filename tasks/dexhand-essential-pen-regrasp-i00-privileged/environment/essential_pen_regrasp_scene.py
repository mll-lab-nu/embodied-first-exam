"""Task-owned Paper Mate mesh scene with contact-driven pen regrasp."""
import xml.etree.ElementTree as ET
from essential_assets import asset_path
from essential_inhand import features as _base_features, snapshot, _node
import numpy as np
import mujoco


def build(world, spec):
    p=spec['parameters']
    body=_node(world,'body',name='object',pos=p['initial_position'],quat=p['initial_quaternion'])
    _node(body,'freejoint',name='object_free')
    # The real source mesh is adapted to a 150 x 12 mm writing instrument.
    # A same-diameter shaft capsule follows its straight section, and convex
    # meshes fit the source tip/tail. All physical parts count toward contact.
    _node(body,'inertial',pos=(0,0,-.0028),mass=float(p.get("mass_kg",.00656)),diaginertia=(7.4268e-6,7.4268e-6,1.16445e-7))
    _node(body,'geom',name='task_object',type='capsule',size=(.006,.054275),pos=(0,0,-.0028),rgba=(0,0,0,0),group=3,density=0,friction=p.get("object_friction",(1.5,.001,.0001)),condim=6,solref=(.008,1),solimp=(.95,.99,.001))
    _node(body,'geom',name='pen_visible',type='mesh',mesh='pen_body',material='pen_material',contype=0,conaffinity=0,density=0)
    for part in ('tip','tail'):
        _node(body,'geom',name='task_object_'+part,type='mesh',mesh='pen_'+part+'_collision',rgba=(0,0,0,0),group=3,density=0,friction=p.get("object_friction",(1.5,.001,.0001)),condim=6,solref=(.008,1),solimp=(.95,.99,.001))
    # Two narrow painted rings delimit the evaluated grip band without covering
    # the source pen body or adding a second physical contact surface.
    for name,z in [('near',p['grip_band_z']-p['grip_band_half_width_m']),('far',p['grip_band_z']+p['grip_band_half_width_m'])]:
        _node(body,'geom',name='pen_band_'+name,type='cylinder',size=(p['radius_m']*1.002,.00015),pos=(0,0,z),rgba=(.03,.12,.3,1),contype=0,conaffinity=0,density=0)
    return {}


def configure(source,spec):
    assets=source.find('asset')
    _node(assets,'mesh',name='pen_body',file=asset_path(spec,'pen_body.obj'))
    for part in ('tip','tail'):_node(assets,'mesh',name='pen_'+part+'_collision',file=asset_path(spec,'pen_'+part+'_collision.obj'))
    _node(assets,'texture',name='pen_color',type='2d',file=asset_path(spec,'pen_base_color.png'))
    _node(assets,'material',name='pen_material',texture='pen_color',specular=.3,shininess=.18,rgba=(1,1,1,1))


def contact_features(session):
    """Count real contact for the shaft, fitted tip and tail together."""
    m,d=session.model,session.data;obj=d.body('object');p=session.spec['parameters']
    contacts=0;palm=0;grip=set();wrench=np.zeros(6);palm_id=m.body('right_hand_C_MC').id
    for i in range(d.ncon):
        c=d.contact[i]
        for hand,target in [(int(c.geom1),int(c.geom2)),(int(c.geom2),int(c.geom1))]:
            if not (m.geom(target).name or '').startswith('task_object'):continue
            mujoco.mj_contactForce(m,d,i,wrench);force=np.linalg.norm(wrench[:3])
            if force<.005:continue
            body=int(m.geom_bodyid[hand])
            while body and body!=palm_id:body=int(m.body_parentid[body])
            if body!=palm_id:continue
            contacts+=1;name=m.geom(hand).name or ''
            if force>.01 and name.startswith('palm'):palm+=1
            if force>.01 and hand in session._finger_geoms:
                local=obj.xmat.reshape(3,3).T@(c.pos-obj.xpos)
                if abs(local[2]-p['grip_band_z'])<p['grip_band_half_width_m']:grip.add(session._finger_geoms[hand])
    out={'object_hand_contacts':float(contacts),'pen_palm_contacts':float(palm),'pen_grip_contacts':float(len(grip))}
    out.update({'pen_grip_'+f:float(f in grip) for f in ('thumb','index','middle')});return out


def reset(session):
    p=session.spec['parameters'];m,d=session.model,session.data
    d.qpos[session._act_qpos[:6]]=p['initial_wrist']
    for name,value in p['initial_fingers'].items():
        j=m.joint(name).id;d.qpos[m.jnt_qposadr[j]]=np.clip(value,*m.jnt_range[j])
    a=int(m.joint('object_free').qposadr[0]);d.qpos[a:a+3]=p['initial_position'];d.qpos[a+3:a+7]=p['initial_quaternion']
    d.ctrl[:]=d.qpos[session._act_qpos];d.ctrl[:6]=p['initial_wrist'];mujoco.mj_forward(m,d)
    for _ in range(p['settle_steps']):mujoco.mj_step(m,d)
    d.time=0.;mujoco.mj_forward(m,d)
    session._pen_initial_palm_contacts=contact_features(session)['pen_palm_contacts']
    axis=d.body('object').xmat.reshape(3,3)[:,2]
    session._pen_initial_horizontal_error=float(np.arcsin(np.clip(abs(axis[2]),0,1)))
    if p['require_initial_palm_contact'] and session._pen_initial_palm_contacts<1:raise ValueError('The real pen must start against the palm')
    if session._pen_initial_horizontal_error>np.deg2rad(p['initial_horizontal_max_deg']):raise ValueError('The real pen must start nearly horizontal')


def features(session):
    out=_base_features(session);out.update(contact_features(session));return out
