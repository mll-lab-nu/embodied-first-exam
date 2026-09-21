"""Native ALOHA actuators coupled to the Orbits cord planning model.

All dynamics use task-local coordinates; renderers apply the configured shared
tabletop transform. The source robot meshes, inertias and joint limits retain
their original scale. Grasp equalities start disabled.
"""
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .dynamics import build_probe, vector
from .workspace import PAD_CENTER


def build_robot_model(path,cfg,*,dt=.0005,spacing=.0075,initial_points=None,handle_position=None):
    from topogym.robot.assets import robot_asset
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    _,points,layout=build_probe(path.parent/'probe_model.xml',dt=dt,spacing=spacing,
                                initial_points=initial_points,handle_position=handle_position)
    probe=ET.parse(path.parent/'probe_model.xml').getroot()
    root=ET.parse(robot_asset(cfg.robot_control)).getroot()
    for name in ['option','keyframe']:
        item=root.find(name)
        if item is not None:root.remove(item)
    root.append(deepcopy(probe.find('option')))
    root.find('compiler').set('angle','radian')
    defaults=root.find('default')
    child=ET.SubElement(defaults,'default',{'class':'orbits_defaults'})
    child.extend(deepcopy(list(probe.find('default'))))
    for geom in probe.findall('.//worldbody//geom'):
        geom.set('class','orbits_defaults')
    world=root.find('worldbody')
    yaw=Rotation.from_euler('z',float(cfg.task.yaw_deg),degrees=True)
    mount=np.asarray(cfg.env.robot_mount.pos)
    origin=np.r_[cfg.task.origin_xy_m,float(cfg.env.frames.table_surface.origin[2])]
    for body in world.findall('body'):
        position=np.fromstring(body.get('pos','0 0 0'),sep=' ')
        quat=np.fromstring(body.get('quat','1 0 0 0'),sep=' ')
        body.set('pos',vector(yaw.inv().apply(position+mount-origin)))
        rotation=yaw.inv()*Rotation.from_quat(quat[[1,2,3,0]])
        body.set('quat',vector(rotation.as_quat()[[3,0,1,2]]))
        for sub in body.iter('body'):sub.set('gravcomp','1')
    for side in ['left','right']:
        hand=root.find(f".//body[@name='{side}/gripper_link']")
        if hand is None:raise ValueError(f'Missing {side} gripper link')
        ET.SubElement(hand,'site',name=f'{side}_tcp',pos=vector(PAD_CENTER),size='.001',rgba='0 0 0 0')
        for i in range(2):
            ET.SubElement(hand,'site',name=f'{side}_grasp_{i}',pos=vector(PAD_CENTER),size='.001',rgba='0 0 0 0')
    world.extend(deepcopy(list(probe.find('worldbody'))))
    for name in ['asset','equality','deformable']:
        source=probe.find(name)
        if source is None:continue
        target=root.find(name)
        if target is None:target=ET.SubElement(root,name)
        target.extend(deepcopy(list(source)))
    equality=root.find('equality')
    for name,site in [('bight','left_grasp_0'),('handle','right_grasp_0'),('fold_0','left_grasp_0'),('fold_1','right_grasp_0')]:
        eq=equality.find(f"connect[@name='grasp_{name}']")
        eq.set('site1',site);eq.set('active','false')
    # Native source finger contacts, mimic equalities and all 14 actuators
    # remain present. No cable node or robot pose is driven by a mocap body.
    for body in list(world.findall('body')):
        if body.get('name','').startswith('probe_'):world.remove(body)
    ET.indent(root);ET.ElementTree(root).write(path,encoding='unicode')
    model=mujoco.MjModel.from_xml_path(str(path));data=mujoco.MjData(model)
    for side in ['left','right']:
        names=list(cfg.robot_control.robot.arm_joint_names)+list(cfg.robot_control.robot.finger_joint_names)
        for name,value in zip(names,cfg.robot_control.home[side]):
            data.qpos[model.joint(f'{side}/{name}').qposadr[0]]=value
    for i in range(model.nu):
        joint=int(model.actuator_trnid[i,0]);data.ctrl[i]=data.qpos[model.jnt_qposadr[joint]]
    mujoco.mj_forward(model,data)
    return model,data,points,layout
