"""Free-held, passive articulated objects for essential dexterity tasks.

Only the hand receives actuator targets. Initial inverse kinematics positions
fingers before simulation starts; all subsequent object motion comes from
ordinary gravity, joints and contact.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
import mujoco
import numpy as np

TASK_IDS = {"essential_cube_layer", "essential_held_joystick"}


def node(parent, tag, **attributes):
    return ET.SubElement(parent, tag, {key: " ".join(map(str, value)) if isinstance(value, (tuple, list)) else str(value) for key, value in attributes.items()})


def geom(parent, name, kind="box", size=(.02,.02,.01), pos=(0,0,0), rgba=(.14,.47,.75,1), **attributes):
    return node(parent,"geom",name=name,type=kind,size=size,pos=pos,rgba=rgba,density=500,friction="1.5 0.02 0.002",solref="0.008 1",solimp="0.95 0.99 0.001",**attributes)


def build(world, spec):
    """Add a free object and unactuated mechanism, and return joint reset values."""
    p=spec.get("parameters",{})
    position=p.get("object_position",[-.01,0,.328])
    obj=node(world,"body",name="object",pos=position,quat=p.get("object_quaternion", [1,0,0,0]))
    node(obj,"freejoint",name="object_free")
    initial={}
    if spec["id"] == "essential_cube_layer":
        half=float(p.get("side_m",.05))/2
        geom(obj,"task_cube_base",size=(half,half,half*.66),pos=(0,0,-half*.34),rgba=(.16,.18,.22,1))
        top=node(obj,"body",name="task_cube_top",pos=(0,0,half*.68))
        node(top,"joint",name="top_turn",type="hinge",axis=(0,0,1),limited="false",damping=.0003,frictionloss=.00001,armature=.00001)
        geom(top,"task_cube_top_collision",size=(half,half,half*.31),rgba=(.16,.18,.22,1))
        # Stickers are visual only and do not alter the contact geometry.
        colors=[(.92,.2,.18,1),(.16,.72,.27,1),(.12,.38,.9,1),(.96,.55,.13,1)]
        for layer,z in enumerate([-half*.68,-half*.02,half*.68]):
            parent=top if layer==2 else obj
            local_z=0 if layer==2 else z
            for side,color in enumerate(colors):
                for col in [-1,0,1]:
                    offset=col*half*.65
                    if side%2==0:
                        pos=(half*1.005*(1 if side==0 else -1),offset,local_z)
                        size=(.00015,half*.285,half*.285)
                    else:
                        pos=(offset,half*1.005*(1 if side==1 else -1),local_z)
                        size=(half*.285,.00015,half*.285)
                    geom(parent,f"cube_sticker_{layer}_{side}_{col+1}",size=size,pos=pos,rgba=color,contype=0,conaffinity=0)
        for i in [-1,0,1]:
            for j in [-1,0,1]:
                geom(top,f"cube_top_sticker_{i+1}_{j+1}",size=(half*.285,half*.285,.00015),pos=(i*half*.65,j*half*.65,half*.311),rgba=(.96,.86,.15,1),contype=0,conaffinity=0)
        initial["top_turn"]=0
    else:
        geom(obj,"task_controller_shell",size=(.032,.027,.012),rgba=(.2,.25,.31,1))
        pivot=p.get("joystick_pivot",[.007,-.023,.017])
        gimbal=node(obj,"body",name="task_joystick_gimbal",pos=pivot)
        node(gimbal,"inertial",pos=(0,0,0),mass=.002,diaginertia=(.000001,.000001,.000001))
        node(gimbal,"joint",name="joystick_x",type="hinge",axis=(0,1,0),range=(-.48,.48),damping=.001,stiffness=.005,armature=.000002)
        stick=node(gimbal,"body",name="task_joystick_stick")
        node(stick,"joint",name="joystick_y",type="hinge",axis=(-1,0,0),range=(-.48,.48),damping=.001,stiffness=.005,armature=.000002)
        length=float(p.get("stick_length", .026))
        geom(stick,"task_joystick_stem","capsule",(.0035,length/2),pos=(0,0,length/2),rgba=(.55,.58,.64,1))
        if p.get("flat_cap", False):
            geom(stick,"task_joystick_knob","cylinder",(.012,.003),pos=(0,0,length),rgba=(.95,.62,.12,1))
        else:
            geom(stick,"task_joystick_knob","sphere",(.011,),pos=(0,0,length),rgba=(.95,.62,.12,1))
        geom(obj,"controller_pivot_visual","cylinder",(.014,.002),pos=pivot,rgba=(.12,.14,.17,1),contype=0,conaffinity=0)
        initial.update(joystick_x=0,joystick_y=0)
    return initial


def reset(session):
    """Apply a declared initial hand pose, without adding object constraints."""
    p=session.spec.get("parameters",{})
    if hasattr(session,"_articulated_reference"): del session._articulated_reference
    for name,value in p.get("initial_hand_joints",{}).items():
        joint=session.model.joint(name)
        session.data.qpos[int(joint.qposadr[0])]=float(value)
    session.data.ctrl[:]=session.data.qpos[session._act_qpos]
    mujoco.mj_forward(session.model,session.data)
    for _ in range(int(p.get("settle_steps", 0))):
        mujoco.mj_step(session.model,session.data)
    session.data.time=0
    session.data.ctrl[:6]=p.get("initial_wrist", [-.08,0,.29,0,0,0])
    mujoco.mj_forward(session.model,session.data)


def features(session):
    """Measure holder stability and independent base/mechanism contact."""
    body=session.data.body("object")
    reference=getattr(session,"_articulated_reference",None)
    if reference is None:
        reference=(body.xpos.copy(),body.xmat.reshape(3,3).copy())
        session._articulated_reference=reference
    pos,rotation=reference
    result={"body_drift":float(np.linalg.norm(body.xpos-pos)),"body_rotation":math.acos(float(np.clip((np.trace(body.xmat.reshape(3,3)@rotation.T)-1)/2,-1,1)))}
    base=set(); mechanism=set()
    force=np.zeros(6)
    for i in range(session.data.ncon):
        c=session.data.contact[i]
        mujoco.mj_contactForce(session.model,session.data,i,force)
        if np.linalg.norm(force[:3])<.005: continue
        for finger,target in [(int(c.geom1),int(c.geom2)),(int(c.geom2),int(c.geom1))]:
            finger_name=session._finger_geoms.get(finger)
            if finger_name is None:
                geom_name=session.model.geom(finger).name or ""
                finger_name=next((f for f in ["thumb","index","middle","ring","pinky"] if geom_name.startswith("right_"+f+"_")),None)
            if finger_name is None: continue
            name=session.model.geom(target).name or ""
            if name in {"task_cube_base","task_controller_shell"}: base.add(finger_name)
            elif name in {"task_cube_top_collision","task_joystick_knob","task_joystick_stem"}: mechanism.add(finger_name)
    result.update(base_contacts=float(len(base)),mechanism_contacts=float(len(mechanism)))
    return result
