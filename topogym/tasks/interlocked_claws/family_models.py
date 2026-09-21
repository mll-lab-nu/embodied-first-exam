"""Authored B0/C0 solids and relative motion, shared by checks and physics.

Each piece is the union of oriented boxes. The visible boundary and collision
compound describe that same union; mass/inertia come from the solid union.
These are executable engineering prototypes of the earlier concept designs.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

COLORS = ((.74,.40,.24,1.), (.20,.53,.61,1.))
DENSITY = 600.
FAMILIES = ("helical_crown", "helical_claws_balanced_v2", "orthogonal_gate", "orthogonal_gate_balanced_v2")


def pose(position=(0.,0.,0.), rotation=None):
    value = np.eye(4)
    value[:3,3] = position
    if rotation is not None:
        value[:3,:3] = rotation.as_matrix() if isinstance(rotation,Rotation) else rotation
    return value


def rot(axis, degrees):
    return Rotation.from_euler(axis,degrees,degrees=True)


def box(center, size, rotation=None):
    t = pose(center,rotation)
    return dict(size=list(size), pose=t.tolist())


def box_mesh(item):
    return trimesh.creation.box(extents=item["size"], transform=np.array(item["pose"]))


@dataclass
class Part:
    name: str
    boxes: list
    mesh: trimesh.Trimesh
    grasp: np.ndarray  # body -> gripper TCP
    side: str
    finger: float


@dataclass
class Segment:
    name: str
    duration: float
    start: np.ndarray
    end: np.ndarray

    def at(self, fraction):
        u=float(np.clip(fraction,0.,1.))
        u=u**3*(10-15*u+6*u*u)
        delta=Rotation.from_matrix(self.end[:3,:3]@self.start[:3,:3].T).as_rotvec()
        return pose((1-u)*self.start[:3,3]+u*self.end[:3,3],
                    Rotation.from_rotvec(u*delta).as_matrix()@self.start[:3,:3])

    @property
    def rotation_angle(self):
        return float(Rotation.from_matrix(self.end[:3,:3]@self.start[:3,:3].T).magnitude())


class FamilyModel:
    def __init__(self, family):
        if family not in FAMILIES:
            raise ValueError(f"Unknown family: {family}")
        self.family=family
        build=getattr(self,"_"+family)
        boxes, grasps, sides, fingers, initial, targets=build()
        self.parts=[]
        for i,(items,grasp,side,finger) in enumerate(zip(boxes,grasps,sides,fingers)):
            mesh=trimesh.boolean.union([box_mesh(b) for b in items],engine="manifold")
            mesh.density=DENSITY
            if not mesh.is_watertight or not mesh.is_winding_consistent or len(mesh.split()) != 1 or mesh.volume <= 0:
                raise ValueError(f"{family} piece {i} is not one closed solid")
            if np.linalg.eigvalsh(mesh.moment_inertia).min() <= 0:
                raise ValueError("Invalid solid inertia")
            self.parts.append(Part(f"piece_{i}",items,mesh,grasp,side,finger))
        self.initial=[np.eye(4),initial]
        self.segments=[]
        previous=initial
        for name,duration,target in targets:
            self.segments.append(Segment(name,duration,previous,target))
            previous=target
        self.duration=sum(s.duration for s in self.segments)

    def _helical_crown(self):
        cage=[]
        radius=.065
        for i in range(36):
            angle=(i+.5)*2*np.pi/36
            cage.append(box([radius*np.cos(angle),radius*np.sin(angle),-.024],
                            [.023,2*radius*np.tan(np.pi/36)+.002,.012],rot("z",np.rad2deg(angle))))
        zs=np.linspace(-.019,.026,29)
        for base_angle in (0.,120.,240.):
            for lo,hi in zip(zs[:-1],zs[1:]):
                def center(z):
                    theta=np.deg2rad(base_angle+2500*z)
                    return np.array([radius*np.cos(theta),radius*np.sin(theta),z])
                a,b=center(lo),center(hi)
                angle=np.deg2rad(base_angle+2500*(lo+hi)/2)
                radial=np.array([np.cos(angle),np.sin(angle),0.])
                tangent=(b-a)/np.linalg.norm(b-a)
                normal=np.cross(radial,tangent)
                cage.append(box((a+b)/2,[.020,np.linalg.norm(b-a)+.0025,.008],np.column_stack([radial,tangent,normal])))
        cage.append(box([-.113,0.,-.024],[.11,.022,.018]))
        key=[box([0,0,.063],[.018,.018,.148])]
        for height in (0.,.012):
            for angle in (60.+2500*height,180.+2500*height,300.+2500*height):
                r=rot("z",angle)
                key.append(box(r.apply([.044,0.,height]),[.092,.012,.010],r))
        grasps=[pose([-.15,0.,-.024]),pose([0.,0.,.122],rot("z",180)*rot("y",25))]
        p0=np.eye(4)
        targets=[("screw_100deg_40mm",8.,pose([0,0,.04],rot("z",100))),
                 ("clear_crown",3.,pose([0,0,.085],rot("z",100))),
                 ("side_exit",4.,pose([.16,0,.085],rot("z",100)))]
        return [cage,key],grasps,["left","right"],[.0192,.0172],p0,targets

    def _orthogonal_gate(self):
        cage=[]
        # First window normal x; long aperture y. Second normal y; long x.
        for sign in (-1,1):
            cage.append(box([0,sign*.1335,0],[.012,.027,.230]))
            cage.append(box([0,0,sign*.1025],[.012,.294,.025]))
            cage.append(box([.32+(-.1335 if sign<0 else .3935),.12,.075],[.027,.012,.380]))
            cage.append(box([.45,.12,-.1025 if sign<0 else .2525],[.554,.012,.025]))
        cage.append(box([.25,.104,-.104],[.512,.026,.024]))
        cage.append(box([.125,-.1335,-.104],[.274,.026,.024]))
        cage.append(box([.25,-.21675,-.104],[.024,.1935,.024]))
        cage.append(box([.25,-.30,-.052],[.024,.026,.128]))
        key=[box([x,0,0],[.010,.014,.210]) for x in (-.014,.014)]
        key += [box([0,0,-.095],[.044,.014,.014]),
                box([.005,.012,0],[.31,.018,.018])]
        grasps=[pose([.25,-.30,0],rot("z",90)),
                pose([.145,.012,0],rot("x",-90)*rot("z",180)*rot("x",60))]
        first=rot("x",90)
        second=rot("z",90)*first
        p0=pose([-.04,0,0])
        targets=[("first_axis_roll",5.,pose([-.04,0,0],first)),
                 ("first_window_transfer",3.,pose([.18,0,0],first)),
                 ("offset_clearance_lane",2.,pose([.18,-.12,0],first)),
                 ("transfer_between_windows",5.,pose([.26,-.12,0],first)),
                 ("second_axis_yaw",5.,pose([.26,-.12,0],second)),
                 ("align_second_window",2.,pose([.32,-.12,0],second)),
                 ("second_window_exit",6.,pose([.32,.32,0],second))]
        return [cage,key],grasps,["right","left"],[.0212,.0212],p0,targets

    def _helical_claws_balanced_v2(self):
        """Congruent three-start claws, opposed at their open ends.

        Both parts have a base ring, three 205-degree helical fingers and an
        identical handle. A 180-degree axial offset interleaves the fingers;
        the upside-down second part retains the same world-space handedness.
        """
        import copy
        items=[];radius=.065
        for i in range(36):
            angle=(i+.5)*2*np.pi/36
            items.append(box([radius*np.cos(angle),radius*np.sin(angle),-.050],
                             [.020,2*radius*np.tan(np.pi/36)+.002,.012],rot("z",np.rad2deg(angle))))
        zs=np.linspace(-.046,.036,53)
        for base_angle in (0.,120.,240.):
            for lo,hi in zip(zs[:-1],zs[1:]):
                def center(z):
                    theta=np.deg2rad(base_angle+2500*z)
                    return np.array([radius*np.cos(theta),radius*np.sin(theta),z])
                a,b=center(lo),center(hi)
                angle=np.deg2rad(base_angle+2500*(lo+hi)/2)
                radial=np.array([np.cos(angle),np.sin(angle),0.])
                tangent=(b-a)/np.linalg.norm(b-a)
                items.append(box((a+b)/2,[.016,np.linalg.norm(b-a)+.0025,.009],
                                 np.column_stack([radial,tangent,np.cross(radial,tangent)])))
        for angle in (0.,120.,240.):
            r=rot("z",angle)
            items.append(box(r.apply([.032,0,-.050]),[.070,.016,.012],r))
        items.append(box([0,0,-.098],[.018,.018,.106]))
        initial_rotation=rot("z",180)*rot("x",180)
        initial=pose(rotation=initial_rotation)
        targets=[("coupled_screw_first_100deg",6.,pose([0,0,.040],rot("z",100)*initial_rotation)),
                 ("coupled_screw_second_100deg",6.,pose([0,0,.080],rot("z",200)*initial_rotation)),
                 ("separate_tips",2.,pose([0,0,.115],rot("z",200)*initial_rotation))]
        grasps=[pose([0,0,-.130],rot("y",-90)),pose([0,0,-.130],rot("y",-90))]
        return [items,copy.deepcopy(items)],grasps,["left","right"],[.0172,.0172],initial,targets

    def _orthogonal_gate_balanced_v2(self):
        # Congruent 250 x 190 mm frames with 220 x 160 mm apertures.
        # The complete frame is symmetric under (x,y,z)->(y-.12,x+.12,z).
        # Pull through the first window towards -x, keeping the hand outside
        # the frame; then turn towards +y through the second window.
        cage=[]
        for sign in (-1,1):
            cage.append(box([0,sign*.1175,0],[.014,.015,.190]))
            cage.append(box([0,0,sign*.0875],[.014,.250,.015]))
            cage.append(box([-.12+sign*.1175,.12,0],[.015,.014,.190]))
            cage.append(box([-.12,.12,sign*.0875],[.250,.014,.015]))
        key=[box([x,0,0],[.010,.014,.180]) for x in (-.014,.014)]
        key += [box([0,0,-.085],[.044,.014,.014]),
                box([0,.012,0],[.250,.018,.018])]
        grasps=[pose([0,.1175,.065],rot("z",180)),pose([-.113,.012,0],rot("x",-45))]
        first=rot("x",90);second=rot("z",90)*first
        p0=pose([.04,0,0])
        targets=[("first_axis_roll",4.,pose([.04,0,0],first)),
                 ("first_window_pull",4.,pose([-.15,0,0],first)),
                 ("turn_clearance",2.,pose([-.15,-.04,0],first)),
                 ("second_axis_yaw",8.,pose([-.15,-.04,0],second)),
                 ("align_second_window",2.,pose([-.12,0,-.015],second)),
                 ("second_window_exit",6.,pose([-.12,.28,-.015],second))]
        return [cage,key],grasps,["right","left"],[.0170,.0212],p0,targets

    def relative_pose(self, seconds):
        t=max(0.,float(seconds))
        for segment in self.segments:
            if t <= segment.duration:
                return segment.at(t/segment.duration),segment.name
            t-=segment.duration
        return self.segments[-1].end.copy(),"separated"

    def negative_paths(self):
        if self.family=="helical_claws_balanced_v2":
            initial=self.initial[1];r=Rotation.from_matrix(initial[:3,:3])
            return [Segment("pull_without_rotation",4.,initial,pose([0,0,.115],r)),
                    Segment("turn_without_advance",4.,initial,pose(rotation=rot("z",100)*r)),
                    Segment("reverse_screw",4.,initial,pose([0,0,.04],rot("z",-100)*r)),
                    *[Segment(f"premature_side_exit_{axis}_{sign}",4.,initial,
                              pose(np.eye(3)[axis]*sign*.20,r)) for axis in (0,1) for sign in (-1,1)]]
        if self.family=="helical_crown":
            return [Segment("push_without_rotation",4.,self.initial[1],pose([0,0,.04])),
                    Segment("turn_without_advance",4.,self.initial[1],pose(rotation=rot("z",100))),
                    Segment("reverse_screw",4.,self.initial[1],pose([0,0,.04],rot("z",-100))),
                    Segment("premature_side_exit",4.,self.initial[1],pose([.16,0,0]))]
        if self.family=="orthogonal_gate_balanced_v2":
            return [Segment("omit_first_roll",4.,self.initial[1],pose([-.15,0,0])),
                    Segment("omit_second_yaw",4.,pose([-.12,0,-.015],rot("x",90)),
                            pose([-.12,.28,-.015],rot("x",90)))]
        first=rot("x",90)
        return [Segment("omit_first_roll",4.,self.initial[1],pose([.32,0,0])),
                Segment("omit_second_yaw",4.,pose([.32,0,0],first),pose([.32,.32,0],first))]

    def save(self, directory):
        directory=Path(directory)
        directory.mkdir(parents=True,exist_ok=False)
        version={"orthogonal_gate_balanced_v2":"balanced_gate_v2", "helical_claws_balanced_v2":"balanced_helical_claws_v2"}.get(self.family,"authored_compound_v1")
        report=dict(family=self.family,version=version,density_kg_m3=DENSITY,
                    visual_collision_union_equivalent=True,parts=[],initial_poses=[t.tolist() for t in self.initial],
                    segments=[dict(name=s.name,duration=s.duration,start=s.start.tolist(),end=s.end.tolist()) for s in self.segments])
        for part,color in zip(self.parts,COLORS):
            part.mesh.export(directory/f"{part.name}.obj",digits=12,include_texture=False)
            root=ET.Element("robot",name=part.name)
            link=ET.SubElement(root,"link",name=part.name)
            props=part.mesh.mass_properties
            inertia=ET.SubElement(link,"inertial")
            ET.SubElement(inertia,"origin",xyz=" ".join(map(str,props.center_mass)),rpy="0 0 0")
            ET.SubElement(inertia,"mass",value=str(props.mass))
            ET.SubElement(inertia,"inertia",**{f"i{a}{b}":str(props.inertia[j,k]) for a,b,j,k in
                (("x","x",0,0),("y","y",1,1),("z","z",2,2),("x","y",0,1),("x","z",0,2),("y","z",1,2))})
            visual=ET.SubElement(link,"visual")
            ET.SubElement(ET.SubElement(visual,"geometry"),"mesh",filename=f"{part.name}.obj")
            ET.SubElement(ET.SubElement(visual,"material",name=part.name),"color",rgba=" ".join(map(str,color)))
            for item in part.boxes:
                collision=ET.SubElement(link,"collision")
                t=np.asarray(item["pose"])
                ET.SubElement(collision,"origin",xyz=" ".join(map(str,t[:3,3])),
                    rpy=" ".join(map(str,Rotation.from_matrix(t[:3,:3]).as_euler("xyz"))))
                ET.SubElement(ET.SubElement(collision,"geometry"),"box",size=" ".join(map(str,item["size"])))
            ET.indent(root)
            ET.ElementTree(root).write(directory/f"{part.name}.urdf",encoding="unicode")
            report["parts"].append(dict(name=part.name,side=part.side,finger=part.finger,boxes=part.boxes,
                grasp=part.grasp.tolist(),mass_kg=float(props.mass),center_mass=props.center_mass.tolist(),
                inertia=props.inertia.tolist(),watertight=bool(part.mesh.is_watertight),components=1,
                bounds=part.mesh.bounds.tolist(),triangles=len(part.mesh.faces)))
        (directory/"model.json").write_text(json.dumps(report,indent=2)+"\n")
        return report


def geometry_audit(model):
    from types import SimpleNamespace
    from .collision import ClawCollision
    collision=ClawCollision(SimpleNamespace(bodies=model.parts))
    minimum=float("inf");leaves=0;queries=0;failures=[]
    radius=float(np.linalg.norm(model.parts[1].mesh.vertices,axis=1).max())
    for segment in model.segments:
        cache={}
        def gap(u):
            nonlocal queries,minimum
            if u not in cache:
                cache[u]=collision.clearance([np.eye(4),segment.at(u)])
                queries+=1;minimum=min(minimum,cache[u])
            return cache[u]
        def bound(a,b,depth=0):
            nonlocal leaves
            mid=(a+b)/2
            g=min(gap(a),gap(mid),gap(b))
            # Smoothstep has max derivative 1.875. This bounds all material
            # point motion on this original rigid interpolation segment.
            travel=1.875*(b-a)/2*(np.linalg.norm(segment.end[:3,3]-segment.start[:3,3])+radius*segment.rotation_angle)
            if g<0:
                failures.append(dict(phase=segment.name,start=a,end=b,reason="collision"));return
            if gap(mid)>travel+1e-7:
                leaves+=1;return
            if depth>=18:
                failures.append(dict(phase=segment.name,start=a,end=b,reason="unresolved_bound"));return
            bound(a,mid,depth+1);bound(mid,b,depth+1)
        bound(0.,1.)
    controls=[]
    for segment in model.negative_paths():
        witness=next((float(u) for u in np.linspace(0,1,201)
                      if collision.clearance([np.eye(4),segment.at(u)])<0),None)
        controls.append(dict(name=segment.name,blocked=witness is not None,witness_fraction=witness))
    return dict(passed=not failures and all(c["blocked"] for c in controls),
        continuous_pair_path_certified=not failures,minimum_sampled_gap_m=minimum,
        certified_intervals=leaves,queries=queries,failures=failures,negative_controls=controls,
        robot_collision_certified=False,physics_verified=False)
