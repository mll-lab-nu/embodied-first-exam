"""Task-owned real Joy-Con shell and passive two-axis physical thumbstick."""
import json,math
import numpy as np
from essential_assets import asset_path
from essential_articulated import node,reset


def build(world,spec):
    p=spec['parameters'];parts=json.loads(open(asset_path(spec,'parts.json')).read())
    obj=node(world,'body',name='object',pos=p['object_position'],quat=p.get('object_quaternion',[1,0,0,0]))
    node(obj,'freejoint',name='object_free')
    node(obj,'inertial',pos=(0,-.022,.00214),mass=.024,diaginertia=(1.35e-5,2.33e-6,1.46e-5))
    for i,item in enumerate(parts['parts']):
        if item['moving']:continue
        material={'Grey_Sections1':'joycon_grey','Red_Sections':'joycon_red','Lights':'joycon_led'}[item['material']]
        node(obj,'geom',name=f'joycon_visible_{i:02d}',type='mesh',mesh=f'joycon_part_{i:02d}',material=material,contype=0,conaffinity=0,density=0)
    for i,_ in enumerate(parts['collision_shell']):
        node(obj,'geom',name='task_controller_shell' if i==0 else f'task_controller_shell_{i:02d}',type='mesh',mesh=f'joycon_collision_{i:02d}',group=3,rgba=(0,0,0,0),density=0,friction=(1.5,.02,.002),solref=(.008,1),solimp=(.95,.99,.001))
    pivot=parts['pivot_m'];gimbal=node(obj,'body',name='task_joystick_gimbal',pos=pivot)
    node(gimbal,'inertial',pos=(0,0,0),mass=.0005,diaginertia=(1e-7,1e-7,1e-7))
    node(gimbal,'joint',name='joystick_x',type='hinge',axis=(0,1,0),range=(-.48,.48),damping=p.get("joystick_damping",.001),stiffness=.005,armature=.000002)
    stick=node(gimbal,'body',name='task_joystick_stick')
    node(stick,'joint',name='joystick_y',type='hinge',axis=(-1,0,0),range=(-.48,.48),damping=p.get("joystick_damping",.001),stiffness=.005,armature=.000002)
    for i,item in enumerate(parts['parts']):
        if not item['moving']:continue
        name='task_joystick_knob' if 'Joystick_top' in item['name'] else 'task_joystick_stem'
        node(stick,'geom',name=name,type='mesh',mesh=f'joycon_part_{i:02d}',material='joycon_grey',density=650,friction=(1.5,.02,.002),solref=(.008,1),solimp=(.95,.99,.001))
    return {'joystick_x':0,'joystick_y':0}


def configure(source,spec):
    assets=source.find('asset');parts=json.loads(open(asset_path(spec,'parts.json')).read())
    for i,item in enumerate(parts['parts']):node(assets,'mesh',name=f'joycon_part_{i:02d}',file=asset_path(spec,item['file']))
    for i,filename in enumerate(parts['collision_shell']):node(assets,'mesh',name=f'joycon_collision_{i:02d}',file=asset_path(spec,filename))
    for material in ('grey','red','led'):
        node(assets,'texture',name=f'joycon_{material}_color',type='2d',file=asset_path(spec,f'joycon_{material}_base_color.png'))
        node(assets,'material',name=f'joycon_{material}',texture=f'joycon_{material}_color',rgba=(1,1,1,1),specular=.3,shininess=.25)
    contact=source.find('contact')
    node(contact,'exclude',body1='object',body2='task_joystick_stick')


def features(session):
    body=session.data.body('object');reference=getattr(session,'_articulated_reference',None)
    if reference is None:
        reference=(body.xpos.copy(),body.xmat.reshape(3,3).copy());session._articulated_reference=reference
    pos,rotation=reference
    out={'body_drift':float(np.linalg.norm(body.xpos-pos)),'body_rotation':math.acos(float(np.clip((np.trace(body.xmat.reshape(3,3)@rotation.T)-1)/2,-1,1)))}
    base=set();mechanism=set();force=np.zeros(6)
    import mujoco
    for i in range(session.data.ncon):
        c=session.data.contact[i];mujoco.mj_contactForce(session.model,session.data,i,force)
        if np.linalg.norm(force[:3])<.005:continue
        for hand,target in [(int(c.geom1),int(c.geom2)),(int(c.geom2),int(c.geom1))]:
            name=session.model.geom(hand).name or ''
            finger=next((f for f in ('thumb','index','middle','ring','pinky') if name.startswith('right_'+f+'_')),None)
            if finger is None:continue
            object_name=session.model.geom(target).name or ''
            if object_name.startswith('task_controller_shell'):base.add(finger)
            elif object_name in ('task_joystick_knob','task_joystick_stem'):mechanism.add(finger)
    out.update(base_contacts=float(len(base)),mechanism_contacts=float(len(mechanism)));return out
