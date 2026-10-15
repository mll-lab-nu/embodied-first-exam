"""Native hinged thin-panel paper reduction with real punched contact holes.

Each sheet has a free root, four broad bending strips and three independently
bending punched margins. This deliberately coarse plate reduction preserves
out-of-plane contact compliance and perforation topology without vertex motors.
"""

import xml.etree.ElementTree as ET
import numpy as np
from scipy.spatial import Delaunay

WIDTH, HEIGHT, THICKNESS = 0.1397, 0.2159, 0.0001
STATIONS = np.array([-0.06985, 0, 0.06985])
HOLE_RADIUS, MARGIN, STRIP = 0.003175, 0.009525, 0.025
D = 2e9 * THICKNESS**3 / (12 * (1 - 0.30**2))


def node(parent, tag, **kw):
    return ET.SubElement(parent,tag,{k:" ".join(map(str,v)) if isinstance(v,(tuple,list,np.ndarray)) else str(v) for k,v in kw.items()})


def perforated_panel(low, high):
    """Return a triangular material mesh with one genuinely empty hole."""
    center=np.array([MARGIN-STRIP,0.0])
    points=[[-STRIP,low],[0,low],[0,high],[-STRIP,high]]
    loop=[]
    for radius in [HOLE_RADIUS,0.0065]:
        for angle in np.arange(16)*2*np.pi/16:
            if radius==HOLE_RADIUS:
                loop.append(len(points))
            points.append((center+radius*np.array([np.cos(angle),np.sin(angle)])).tolist())
    points=np.asarray(points)
    faces=Delaunay(points).simplices
    faces=np.asarray([f for f in faces if np.linalg.norm(points[f].mean(axis=0)-center)>HOLE_RADIUS*0.999])
    for i,f in enumerate(faces):
        v=points[f]
        if np.cross(v[1]-v[0],v[2]-v[0])<0:
            faces[i]=f[[0,2,1]]
    counts={}
    for f in faces:
        for a,b in zip(f,np.roll(f,-1)):
            e=tuple(sorted((int(a),int(b))));counts[e]=counts.get(e,0)+1
    assert all(counts.get(tuple(sorted((a,b))))==1 for a,b in zip(loop,np.roll(loop,-1)))
    return points,faces,loop


def inertia(parent, mass, w, h, cx):
    node(parent,"inertial",pos=(cx,0,0),mass=mass,diaginertia=(mass*(h*h+THICKNESS**2)/12,mass*(w*w+THICKNESS**2)/12,mass*(w*w+h*h)/12))


def add_pages(root,origin,pages=2):
    world,assets=root.find("worldbody"),root.find("asset")
    cut=np.linspace(STRIP,WIDTH,5)
    boundaries=np.r_[-HEIGHT/2,(STATIONS[:-1]+STATIONS[1:])/2,HEIGHT/2]
    holes=[]
    for p in range(pages):
        body=node(world,"body",name=f"page_{p}",pos=np.asarray(origin)+(0,0,p*0.00045))
        node(body,"freejoint",name=f"page_{p}_free")
        parent=body
        for j,(a,b) in enumerate(zip(cut[:-1],cut[1:])):
            width=b-a
            if j:
                parent=node(parent,"body",name=f"page_{p}_strip_{j}",pos=(cut[j]-cut[j-1],0,0) if j>1 else (cut[j],0,0))
                node(parent,"joint",name=f"page_{p}_bend_{j}",type="hinge",axis=(0,1,0),range=(-1.45,1.45),stiffness=D*HEIGHT/width,damping=0.000004,armature=0)
            center=(a+b)/2 if j==0 else width/2
            node(parent,"geom",name=f"page_{p}_paper_strip_{j}",type="box",pos=(center,0,0),size=(width/2,HEIGHT/2,THICKNESS/2),mass=width*HEIGHT*.08,
                 material="paper_stock",friction=(0.45,0.0001,0.00001),solref=(0.002,1),solimp=(0.99,0.999,0.00005))
        for i,y in enumerate(STATIONS):
            low,high=boundaries[i]-y,boundaries[i+1]-y
            panel=node(body,"body",name=f"page_{p}_punched_{i}",pos=(STRIP,y,0))
            node(panel,"joint",name=f"page_{p}_margin_bend_{i}",type="hinge",axis=(0,1,0),range=(-1.45,1.45),stiffness=D*(high-low)/STRIP,damping=0.000002,armature=0)
            points,faces,loop=perforated_panel(low,high)
            area=STRIP*(high-low)-np.pi*HOLE_RADIUS**2
            inertia(panel,area*.08,STRIP,high-low,-STRIP/2)
            for k,face in enumerate(faces):
                xy=points[face]
                vertices=np.r_[np.c_[xy,np.full(3,-THICKNESS/2)],np.c_[xy,np.full(3,THICKNESS/2)]]
                mesh=f"page_{p}_punch_{i}_tri_{k}"
                node(assets,"mesh",name=mesh,vertex=vertices.ravel(),face=np.array([[0,2,1],[3,4,5],[0,1,4],[0,4,3],[1,2,5],[1,5,4],[2,0,3],[2,3,5]]).ravel())
                node(panel,"geom",name=mesh,type="mesh",mesh=mesh,mass=0,material="paper_stock",friction=(0.45,0.0001,0.00001),solref=(0.002,1),solimp=(0.99,0.999,0.00005))
            holes.append(dict(page=p,hole=i,body=f"page_{p}_punched_{i}",points=np.c_[points[loop],np.zeros(len(loop))].tolist()))
    return dict(hole_records=holes,material_thickness_m=THICKNESS,model="seven passive thin panels per sheet",bending_rigidity_nm=D)
