"""T20 standalone legacy OXO rack, initially folded on a real counter.

The storage pose is part of MJCF initialization, never a live object-state edit.
Robots are omitted in the explicitly labelled meta-force view.
"""

import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from rack import DT,HALF,HINGE_OFFSET,LEG_LENGTH,COUNTER_Z,make_rack,materials,node


POINTS={
    'fixed_end_left':('rack',(-HALF,HALF*.7,.0045),8.),
    'fixed_end_right':('rack',(-HALF,-HALF*.7,.0045),8.),
    'moving_end_left':('moving_panel',(HALF,HALF*.7,HINGE_OFFSET+.0045),8.),
    'moving_end_right':('moving_panel',(HALF,-HALF*.7,HINGE_OFFSET+.0045),8.),
    'fixed_rim_near_hinge':('rack',(-.08,HALF,.0045),8.),
    'moving_rim_near_hinge':('moving_panel',(.08,HALF,HINGE_OFFSET+.0045),8.),
}
for p,inward in [('fixed',1),('moving',-1)]:
    for s in ('l','r'):
        POINTS[p+'_foot_'+s]=(p+'_leg_'+s,(inward*(LEG_LENGTH-.004),0,.006),.5)


def build():
    root=ET.Element('mujoco',model='T20 OXO sweater dryer: corrected below-plane hinge axis / polish r1')
    node(root,'compiler',angle='radian')
    opt=node(root,'option',timestep=DT,integrator='implicitfast',iterations=80,cone='elliptic',impratio=10)
    node(opt,'flag',multiccd='enable')
    visual=node(root,'visual');node(visual,'headlight',ambient=(.35,.35,.35),diffuse=(.65,.65,.65))
    asset=node(root,'asset');world=node(root,'worldbody');materials(asset)
    node(asset,'material',name='counter_oak',rgba=(.47,.33,.21,1),specular=.1)
    node(asset,'material',name='counter_base',rgba=(.32,.39,.35,1),specular=.1)
    node(world,'geom',name='floor',type='plane',pos=(0,0,0),size=(3,3,.05),rgba=(.67,.68,.64,1))
    node(world,'geom',name='counter_top',type='box',pos=(.62,0,COUNTER_Z-.025),size=(.55,.48,.025),material='counter_oak',friction=(.7,.002,.0001),solref=(.006,1),condim=4)
    node(world,'geom',name='counter_cabinet',type='box',pos=(.62,0,.35),size=(.51,.44,.35),material='counter_base')
    # Fully stored clamshell, underside up, with both halves/legs folded. The
    # lower half's corner housings rest on the actual counter surface.
    rack=make_rack(world,centre=(.62,.16,COUNTER_Z+.012))
    R=Rotation.from_euler('z',-np.pi/2).as_matrix()@Rotation.from_euler('y',np.pi).as_matrix()
    rack.set('quat',' '.join(map(str,np.roll(Rotation.from_matrix(R).as_quat(),1))))
    child=rack.find("body[@name='moving_panel']")
    child.set('pos','0 0 '+str(-HINGE_OFFSET))
    child.set('quat','0 0 1 0')
    child.find("joint[@name='fold_hinge']").set('ref',str(np.pi))
    # R0=Ry(pi),qref=pi yields Ry(pi)Ry(q-pi)=Ry(q) for EVERY q. The
    # angle map/ranges/stop law are unchanged; the offset side is corrected
    # below the plane, while qpos0=pi
    # defines a properly folded reset without changing task qpos at runtime.
    for name,(body,point,bound) in POINTS.items():
        parent=root.find(f".//body[@name='{body}']")
        node(parent,'site',name=name,pos=point,type='sphere',size=(.003,),rgba=(1,.58,.08,1))
    node(world,'light',pos=(.2,-.7,2),dir=(.3,.4,-1),diffuse=(.8,.8,.77))
    node(world,'light',pos=(1,.7,1.6),dir=(-.3,-.4,-1),diffuse=(.45,.45,.45),castshadow='false')
    return ET.tostring(root,encoding='unicode')


def load():
    xml=build();m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m);mujoco.mj_forward(m,d)
    return xml,m,d
