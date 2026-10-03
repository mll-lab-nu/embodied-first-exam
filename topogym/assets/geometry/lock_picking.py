from __future__ import annotations

"""Geometry for a passive-disc lock, free rigid key and physical pickup rests.

Collision pieces are explicit convex sectors. No convex hull spans a hole.
Angles run from +z toward +y, i.e. about the negative x axis.
"""
from dataclasses import dataclass, replace, asdict
from typing import ClassVar
from pathlib import Path
import json
import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals
from PIL import Image
from copy import deepcopy
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt

DISC_COLORS = ((.46, .28, .66), (.20, .43, .60), (.72, .34, .22))
ENDPOINT_COLOR = (.10, .34, .28)


def angle_error(a, b):
    return abs((a-b+180.) % 360.-180.)


@dataclass(frozen=True)
class LockGeometry:
    # Class constants preserve the serialized identity of the original geometry.
    disc_count: ClassVar[int] = 3
    tab_count: ClassVar[int] = 3
    first_x: float = .20
    center_y: float = .20
    axis_z: float = 1.105
    pitch: float = .085
    disc_radius: float = .08
    disc_thickness: float = .01
    bore_radius: float = .014
    slot_radius: float = .045
    slot_half_deg: float = 14.
    tab_radius: float = .036
    tab_half_deg: float = 4.
    tab_thickness: float = .005
    shaft_radius: float = .0065
    grip_offset: float = .300
    handle_radius: float = .018
    slots: tuple = ((0.,90.,210.), (30.,150.,270.), (0.,180.,300.))
    initial_disc_deg: tuple = (20.,-5.,-25.)
    initial_key_deg: float = 0.
    endpoint_deg: float = 0.

    @classmethod
    def from_config(cls, cfg):
        values = dict(cfg)
        values['slots'] = tuple(tuple(float(v) for v in row) for row in values['slots'])
        values['initial_disc_deg'] = tuple(float(v) for v in values['initial_disc_deg'])
        result = cls(**values)
        result.validate()
        return result

    def validate(self):
        if len(self.slots) != self.disc_count or len(self.initial_disc_deg) != self.disc_count:
            raise ValueError(f'{self.disc_count} passive discs are required')
        if not 0 < self.shaft_radius < self.bore_radius < self.tab_radius < self.slot_radius < self.disc_radius:
            raise ValueError('Invalid radial clearance')
        if not 0 < self.tab_half_deg < self.slot_half_deg < 30:
            raise ValueError('Invalid angular clearance')
        if self.pitch <= 2*self.disc_thickness or self.grip_offset <= self.disc_count*self.pitch + .03:
            raise ValueError('Insufficient axial separation or handle clearance')
        for row in self.slots:
            if not row or any(angle_error(a,b) <= 2*self.slot_half_deg for i,a in enumerate(row) for b in row[i+1:]):
                raise ValueError('Slots must be distinct and non-overlapping')

    def tip_x(self, depth):
        return self.first_x + (depth-1)*self.pitch

    def disc_x(self, i):
        return self.first_x + i*self.pitch

    def grip_pos(self, depth):
        return np.array([self.tip_x(depth)-self.grip_offset, self.center_y, self.axis_z])

    def slot_margin(self, angle, disc_angle, i):
        return self.slot_half_deg-self.tab_half_deg-min(angle_error(angle, disc_angle+s) for s in self.slots[i])

    def clearance(self, depth, angle, disc_angles, tolerance=0.):
        # Check all tabs against the finite thickness of every crossed disc.
        issues=[]
        for tab in range(self.tab_count):
            x=self.tip_x(depth)-tab*self.pitch
            for i in range(self.disc_count):
                if abs(x-self.disc_x(i)) < (self.tab_thickness+self.disc_thickness)/2:
                    if self.slot_margin(angle,disc_angles[i],i) < -tolerance:
                        issues.append(f'tab{tab}/disc{i}')
            if abs(x-self.disc_x(self.disc_count)) < (self.tab_thickness+self.disc_thickness)/2:
                if self.slot_half_deg-self.tab_half_deg-angle_error(angle,self.endpoint_deg) < -tolerance:
                    issues.append(f'tab{tab}/endpoint')
        return issues


VARIANTS=('aligned_entry','reindexed','asymmetric','tight_clearance','limited_two_retreats')


def variant_geometry(g, name, seed):
    if name not in VARIANTS:
        raise ValueError(f'Unknown variant {name}: {VARIANTS}')
    rng=np.random.default_rng(seed)
    if name == 'limited_two_retreats':
        g=replace(g,slots=((-60.,-30.,0.),(-60.,),(0.,)),
                  initial_disc_deg=(0.,0.,0.),initial_key_deg=0.,endpoint_deg=0.,slot_half_deg=8.)
        g.validate()
        return g
    if name != 'aligned_entry':
        # Modest continuous angles keep the first physical family in a
        # reachable wrist range. Distinct slot patterns are independent of RGB.
        g=replace(g,initial_disc_deg=tuple(rng.uniform(-35,35,3)), initial_key_deg=float(rng.uniform(-15,15)))
    if name == 'asymmetric':
        g=replace(g,slots=((0.,100.,225.), (15.,145.,265.), (0.,170.,290.)),
                  endpoint_deg=float(rng.uniform(-15,15)))
    if name == 'tight_clearance':
        g=replace(g,slot_half_deg=10.)
    g.validate()
    return g


def annulus(inner, outer, thickness, samples=720):
    a=np.arange(samples)*2*np.pi/samples
    vertices=[]
    for x in (-thickness/2,thickness/2):
        for r in (np.asarray(inner(np.degrees(a))),np.asarray(outer(np.degrees(a)))):
            vertices.extend(np.c_[np.full(samples,x),r*np.sin(a),r*np.cos(a)])
    faces=[]
    for i in range(samples):
        j=(i+1)%samples
        for q in ((i,j,samples+j,samples+i),(2*samples+i,3*samples+i,3*samples+j,2*samples+j),
                  (i,2*samples+i,2*samples+j,j),(samples+i,samples+j,3*samples+j,3*samples+i)):
            faces.extend(((q[0],q[1],q[2]),(q[0],q[2],q[3])))
    mesh=trimesh.Trimesh(vertices,faces,process=True)
    mesh.fix_normals()
    return mesh


def sector(r0,r1,a0,a1,thickness):
    a=np.radians([a0,a1])
    vertices=[[x,r*np.sin(t),r*np.cos(t)] for x in (-thickness/2,thickness/2) for r in (r0,r1) for t in a]
    return trimesh.convex.convex_hull(np.asarray(vertices))


def rounded_square_radius(angles, half_extent, corner_radius):
    """Radial boundary of a rounded square in the local yz plane."""
    a=np.radians(angles)
    u,v=np.abs(np.sin(a)),np.abs(np.cos(a))
    flat=half_extent/np.maximum(u,v)
    c=half_extent-corner_radius
    dot=c*(u+v)
    arc=dot+np.sqrt(np.maximum(0.,dot*dot-(2*c*c-corner_radius*corner_radius)))
    return np.where(np.minimum(u,v)*flat<=c,flat,arc)


def disc_assets(g, slots, folder, *, goal_plate=False):
    folder.mkdir(parents=True,exist_ok=True)
    def inner(a):
        err=np.minimum.reduce([np.abs((a-s+180)%360-180) for s in slots])
        return np.where(err <= g.slot_half_deg,g.slot_radius,g.bore_radius)
    def outer(a):
        return (rounded_square_radius(a,g.disc_radius,.15*g.disc_radius) if goal_plate
                else np.full_like(a,g.disc_radius))
    mesh=annulus(inner,outer,g.disc_thickness)
    trimesh.graph.smooth_shade(mesh).export(folder/'visual.obj',include_normals=True)
    # Insert each slot boundary into the angular grid so no piece bridges it.
    boundaries=sorted(set([*np.arange(0.,360.,10.),*[(s+d)%360 for s in slots for d in (-g.slot_half_deg,g.slot_half_deg)]]))
    paths=[]
    for i,a0 in enumerate(boundaries):
        a1=boundaries[i+1] if i+1<len(boundaries) else 360.
        r=float(inner(np.array([(a0+a1)/2]))[0])
        p=folder/f'collision_{i:02d}.obj'
        if goal_plate:
            # Preserve exactly the same bore/slot faces as the circular plate;
            # only the two outer vertices of each convex piece change.
            angles=np.radians([a0,a1])
            radii=outer(np.array([a0,a1]))
            vertices=[[x,radius*np.sin(a),radius*np.cos(a)]
                      for x in (-g.disc_thickness/2,g.disc_thickness/2)
                      for j,a in enumerate(angles) for radius in (r,radii[j])]
            trimesh.convex.convex_hull(np.asarray(vertices)).export(p)
        else:
            sector(r,g.disc_radius,a0,a1,g.disc_thickness).export(p)
        paths.append(p)
    return folder/'visual.obj',paths


def inertial(mass, inertia=.0002):
    return f'<inertial><origin xyz="0 0 0"/><mass value="{mass}"/><inertia ixx="{inertia}" iyy="{inertia}" izz="{inertia}" ixy="0" ixz="0" iyz="0"/></inertial>'


def mesh_xml(path, tag, color=None):
    mat='' if color is None else f'<material name="finish"><color rgba="{" ".join(map(str,(*color,1)))}"/></material>'
    return f'<{tag}><geometry><mesh filename="{path.resolve()}"/></geometry>{mat}</{tag}>'


def write_disc(g, slots, folder, mass, damping, color, fixed=False, stop=None, mount_z=None):
    visual,collisions=disc_assets(g,slots,folder)
    body=inertial(mass)+mesh_xml(visual,'visual',color)+''.join(mesh_xml(p,'collision') for p in collisions)
    joint_type='continuous'
    limits=''
    if stop is not None:
        if fixed: raise ValueError('A fixed panel cannot have rotor stops')
        pass  # Definitions share this geometry module.
        moving,_=limit_assets(g,stop,folder/'limits',color,mount_z=mount_z)
        body=inertial(mass)+moving+''.join(mesh_xml(p,'collision') for p in collisions)
        if abs(float(stop.bounds_deg[1])-float(stop.bounds_deg[0])-360.)>1e-8:
            lo,hi=np.radians(stop.bounds_deg)
            joint_type='revolute'
            limits=f'<limit lower="{lo}" upper="{hi}" effort="2" velocity="2"/>'
    if fixed:
        xml=f'<robot name="endpoint"><link name="disc">{body}</link></robot>'
    else:
        xml=f'''<robot name="disc"><link name="base"/><link name="disc">{body}</link>
        <joint name="disc_hinge" type="{joint_type}"><parent link="base"/><child link="disc"/><origin xyz="0 0 0" rpy="0 0 0"/>
        <axis xyz="-1 0 0"/>{limits}<dynamics damping="{damping}" friction="0"/></joint></robot>'''
    p=folder/'disc.urdf';p.write_text(xml)
    return p


def write_endpoint(g, folder):
    """Fixed square goal panel, with the original finite-thickness keyhole."""
    visual,collisions=disc_assets(g,(g.endpoint_deg,),folder,goal_plate=True)
    body=inertial(.2)+mesh_xml(visual,'visual',ENDPOINT_COLOR)+''.join(mesh_xml(p,'collision') for p in collisions)
    path=folder/'goal.urdf'
    path.write_text(f'<robot name="endpoint"><link name="disc">{body}</link></robot>')
    return path


def goal_mark_assets(g, folder):
    """Static GOAL lettering on both physical faces, plus four mounting bolts.

    Letters are stroke geometry, so the marks work in both renderers without
    an image overlay or a label that changes when the task succeeds.
    """
    glyphs=[[(1,1),(0,1),(0,0),(1,0),(1,.5),(.55,.5)],
            [(0,0),(0,1),(1,1),(1,0),(0,0)],
            [(0,0),(.5,1),(1,0),None,(.2,.4),(.8,.4)],
            [(0,1),(0,0),(1,0)]]
    marks=[];bolts=[]
    width,height,gap=.105*g.disc_radius,.145*g.disc_radius,.035*g.disc_radius
    total=4*width+3*gap
    stroke=.016*g.disc_radius
    for sign in (-1,1):
        face=sign*(g.disc_thickness/2+.0006)
        for i,glyph in enumerate(glyphs):
            previous=None
            for point in glyph:
                if point is not None and previous is not None:
                    a=np.array([sign*(-total/2+i*(width+gap)+previous[0]*width),.69*g.disc_radius+previous[1]*height])
                    b=np.array([sign*(-total/2+i*(width+gap)+point[0]*width),.69*g.disc_radius+point[1]*height])
                    delta=b-a
                    line=trimesh.creation.box(extents=(.0008,float(np.linalg.norm(delta))+stroke,stroke))
                    line.apply_transform(trimesh.transformations.rotation_matrix(np.arctan2(delta[1],delta[0]),(1,0,0)))
                    line.apply_translation((face,*((a+b)/2)))
                    marks.append(line)
                previous=point
        for sy in (-1,1):
            for sz in (-1,1):
                bolt=trimesh.creation.cylinder(radius=.052*g.disc_radius,height=.0016,sections=6)
                bolt.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,(0,1,0)))
                bolt.apply_translation((face,sy*.775*g.disc_radius,sz*.775*g.disc_radius))
                bolts.append(bolt)
    paths={}
    for name,pieces in (('label',marks),('bolts',bolts)):
        path=folder/f'{name}.obj'
        trimesh.util.concatenate(pieces).export(path)
        paths[name]=path
    return paths


def write_key(g, folder, mass, visual_finish=None):
    folder.mkdir(parents=True,exist_ok=True)
    length=g.grip_offset+.035
    shaft=trimesh.creation.cylinder(radius=g.shaft_radius,height=length,sections=32)
    shaft.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,(0,1,0)))
    shaft.apply_translation((-length/2+.015,0,0))
    pieces=[shaft]
    for i in range(g.tab_count):
        tab=sector(g.shaft_radius,g.tab_radius,-g.tab_half_deg,g.tab_half_deg,g.tab_thickness)
        tab.apply_translation((-i*g.pitch,0,0));pieces.append(tab)
    handle=trimesh.creation.cylinder(radius=g.handle_radius,height=.035,sections=32)
    handle.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,(0,1,0)))
    handle.apply_translation((-g.grip_offset,0,0));pieces.append(handle)
    paths=[]
    for i,piece in enumerate(pieces):
        p=folder/f'part{i}.obj';piece.export(p);paths.append(p)
    compound=trimesh.util.concatenate(pieces)
    # Uniform-density compound approximation, including the heavier handle.
    # A free key needs its COM and inertia, rather than an origin at its tip.
    com=compound.center_mass
    inertia_tensor=compound.moment_inertia*(mass/compound.volume)
    terms=' '.join(f'{name}="{inertia_tensor[i,j]:.12g}"' for name,i,j in
                   (('ixx',0,0),('iyy',1,1),('izz',2,2),('ixy',0,1),('ixz',0,2),('iyz',1,2)))
    body_inertial=f'<inertial><origin xyz="{" ".join(map(str,com))}"/><mass value="{mass}"/><inertia {terms}/></inertial>'
    mesh=trimesh.graph.smooth_shade(compound)
    color=(.68,.71,.72)
    if visual_finish is None:
        visual=folder/'visual.obj'
        mesh.export(visual,include_normals=True)
    else:
        # Nyx imports URDFs as nested scenes: a parent surface override does
        # not reliably replace the child mesh material. Embed PBR in the
        # visual asset itself; all collision pieces above remain unchanged.
        from trimesh.visual.material import PBRMaterial
        from trimesh.visual.texture import TextureVisuals
        color=tuple(float(x) for x in visual_finish['color'])
        mesh.visual=TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),material=PBRMaterial(
            baseColorFactor=(*color,1.),metallicFactor=float(visual_finish['metallic']),
            roughnessFactor=float(visual_finish['roughness'])))
        visual=folder/'visual.glb'
        mesh.export(visual,include_normals=True)
        color=None  # URDF RGB must not replace the embedded PBR material.
    body=body_inertial+mesh_xml(visual,'visual',color)+''.join(mesh_xml(p,'collision') for p in paths)
    xml=f'<robot name="free_key"><link name="key">{body}</link></robot>'
    p=folder/'key.urdf';p.write_text(xml)
    (folder/'geometry.json').write_text(json.dumps(asdict(g),indent=2))
    return p


def key_rest_layout(g):
    """A lower tray with two 90-degree V supports; the handle overhangs it."""
    top=g.axis_z-.100
    return dict(tray_top=top,tray_start=g.tip_x(0)-g.grip_offset+.045,
                tray_end=g.first_x-.05,tray_width=.070,tray_thickness=.012,
                cradle_x=[g.tip_x(0)-g.grip_offset+.065,g.tip_x(0)-.035],
                cradle_half_width=.018,cradle_thickness=.016,
                resting_axis_z=top+np.sqrt(2)*g.shaft_radius)


def write_key_cradle(rest,folder):
    """Two convex triangular prisms form an open V, supported by the tray."""
    folder.mkdir(parents=True,exist_ok=True)
    paths=[]
    for sign in (-1,1):
        w=sign*rest['cradle_half_width'];h=rest['cradle_half_width']
        points=[[x,y,z] for x in (-rest['cradle_thickness']/2,rest['cradle_thickness']/2)
                for y,z in ((0,0),(w,0),(w,h))]
        p=folder/f'v_side_{sign}.obj'
        trimesh.convex.convex_hull(np.asarray(points)).export(p)
        paths.append(p)
    return paths


"""Visible double-sided arcuate slots and collision end stops for lock rotors."""



def limit_assets(g, cfg, folder, disc_color, mount_z=None):
    """Return moving visuals/colliders and a fixed, bolted stop-frame URDF.

    All dimensions scale with disc radius. The pin occupies +/-2 degrees;
    physical stop faces lie two degrees beyond the specified hinge endpoints.
    """
    if cfg.get('style','rails') == 'single_ring':
        pass  # Definitions share this geometry module.
        return ring_limit_assets(g,cfg,folder,disc_color,mount_z)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lo, hi = map(float, cfg.bounds_deg)
    phase = float(cfg.get('ear_phase_deg', -35.))
    if not -180 < lo < hi < 180 or not -75 <= lo+phase < hi+phase <= 10:
        raise ValueError('Stop travel must fit the upper, camera-facing bearing clearance')
    scale = g.disc_radius/.08
    moving = []; fixed = []
    palette = dict(ear=(.98, .61, .025), rail=(.14, .19, .23),
                   stop=(.86, .22, .055), tick=(.88, .90, .85), bolt=(.55, .60, .62),
                   disc=disc_color)

    def add(parts, mesh, name, collision=True):
        mesh.apply_scale(scale)
        path = folder/f'{len(moving)+len(fixed):03d}_{name}.obj'
        mesh.export(path)
        parts.append((mesh, name, mesh_xml(path, 'collision') if collision else ''))

    def arc(parts, inner, outer, a0, a1, width, x, name, collision=True):
        angles = np.linspace(a0, a1, max(2, int(np.ceil((a1-a0)/5))+1))
        for a, b in zip(angles, angles[1:]):
            mesh = sector(inner, outer, a, b, width)
            mesh.apply_translation((x, 0, 0))
            add(parts, mesh, name, collision)

    # Radial ear overlaps the rotor rim; axial pins engage both visible slots.
    arc(moving, .074, .108, phase-3, phase+3, .008, 0, 'ear')
    for sign in (-1, 1):
        arc(moving, .100, .108, phase-2, phase+2, .019, sign*.0125, 'ear')
        for inner, outer in ((.092, .098), (.110, .124)):
            arc(fixed, inner, outer, lo+phase-10, hi+phase+10,
                .007, sign*.015, 'rail')
        for a, b in ((lo+phase-10, lo+phase-2), (hi+phase+2, hi+phase+10)):
            arc(fixed, .098, .124, a, b, .010, sign*.015, 'stop')
            angle = np.radians((a+b)/2)
            bolt = trimesh.creation.cylinder(radius=.0035, height=.002, sections=6)
            bolt.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, (0, 1, 0)))
            bolt.apply_translation((sign*.021, .117*np.sin(angle), .117*np.cos(angle)))
            add(fixed, bolt, 'bolt', False)
        for a in np.arange(lo, hi+.001, 10):
            arc(fixed, .116, .123, a+phase-.35, a+phase+.35,
                .0007, sign*.019, 'tick', False)
        # Visible bracket joins the fixed arc to the existing left bearing.
        brackets=[((.007, .010, .059), (sign*.015, -.109, .0145))]
        if sign == -1:
            brackets.append(((.044, .027, .010), (0, -.098, -.010)))
        for size, pos in brackets:
            bracket = trimesh.creation.box(extents=size)
            bracket.apply_translation(pos)
            add(fixed, bracket, 'rail')
    def visual_xml(parts, name):
        # Nyx 0.1.4 addresses URDF visuals by link name, so many independent
        # visuals on one link alias each other. Export ONE textured mesh/link.
        # UV swatches preserve part colours without multiple visual transforms.
        vertices=[]; faces=[]; uv=[]; count=0
        colors=list(palette)
        for mesh, color, _ in parts:
            vertices.extend(mesh.vertices); faces.extend(mesh.faces+count)
            uv.extend([[ (colors.index(color)+.5)/len(colors), .5]]*len(mesh.vertices))
            count+=len(mesh.vertices)
        pixels=np.array([[np.array(palette[color])*255 for color in colors]],dtype=np.uint8)
        texture=Image.fromarray(pixels).resize((32*len(colors),32),Image.Resampling.NEAREST)
        combined=trimesh.Trimesh(vertices=np.array(vertices),faces=np.array(faces),process=False)
        combined.visual=TextureVisuals(uv=np.array(uv),material=PBRMaterial(
            baseColorTexture=texture,metallicFactor=.25,roughnessFactor=.43))
        path=folder/f'{name}.glb'
        combined.export(path,include_normals=True)
        return mesh_xml(path,'visual')+''.join(part[2] for part in parts)

    moving.insert(0,(trimesh.load(folder.parent/'visual.obj',process=False),'disc',''))
    path = folder/'stop_frame.urdf'
    path.write_text('<robot name="visible_stop_frame"><link name="frame">'+
                    inertial(.15)+visual_xml(fixed,'frame_visual')+'</link></robot>')
    return visual_xml(moving,'rotor_visual'), path


"""One fixed annular frame with one real, rounded arcuate through-slot."""



def slot_profile(angles, lo, hi, phase, radius=.097, half_width=.0055, pin_radius=.004):
    """Radial interval cut by a buffered circular arc, with round end caps.

    Trim centreline endpoints by the pin/slot clearance, so the finite pin
    meets the round cap at the requested hinge limit, rather than past it.
    """
    if hi-lo >= 360.-1e-8:
        return (np.full_like(np.asarray(angles,dtype=float),radius-half_width),
                np.full_like(np.asarray(angles,dtype=float),radius+half_width))
    trim=np.degrees(2*np.arcsin((half_width-pin_radius)/(2*radius)))
    a0,a1=lo+phase+trim,hi+phase-trim
    if a1<=a0: raise ValueError('Slot stroke is shorter than pin clearance')
    angle=(np.asarray(angles)-(a0+a1)/2+180)%360-180+(a0+a1)/2
    delta=np.radians(angle-np.clip(angle,a0,a1))
    middle=radius*np.cos(delta)
    discriminant=half_width**2-(radius*np.sin(delta))**2
    active=(discriminant>0)&(np.abs(delta)<np.pi/2)
    half=np.sqrt(np.maximum(0,discriminant))
    return np.where(active,middle-half,radius),np.where(active,middle+half,radius)


def ring_limit_assets(g,cfg,folder,disc_color,mount_z=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    lo,hi=map(float,cfg.bounds_deg);phase=float(cfg.get('ear_phase_deg',-35))
    full_turn=abs(hi-lo-360.)<1e-8
    if not full_turn and (not -180<lo<hi<180 or hi-lo>150):
        raise ValueError('Single-slot ring expects a stroke between 0 and 150 degrees')
    scale=g.disc_radius/.08
    mount=(-.157 if mount_z is None else float(mount_z)/scale)
    radius=.097;inner=.083;outer=.112;thickness=.014;pin_radius=.004
    palette=dict(frame=(.52,.55,.57),disc=tuple(disc_color),bolt=(.66,.69,.71))
    moving=[];fixed=[];counter=0

    def visual(parts,mesh,color):
        mesh=trimesh.graph.smooth_shade(mesh);mesh.apply_scale(scale)
        parts.append((mesh,color,''))

    def collision(parts,mesh,name):
        nonlocal counter
        mesh=mesh.copy();mesh.apply_scale(scale)
        path=folder/f'{counter:04d}_{name}.obj';counter+=1
        mesh.export(path)
        parts.append((None,None,mesh_xml(path,'collision')))

    def solid(parts,mesh,color,name):
        visual(parts,mesh,color);collision(parts,mesh,name)

    def profile(a): return slot_profile(a,lo,hi,phase,radius=radius,pin_radius=pin_radius)
    # Two radial bands share a seam only outside the one opening. Their outer
    # boundary is a complete circle, with no rail gaps or decorative extra slots.
    ring_parts=(annulus(lambda a:np.full_like(a,inner),lambda a:profile(a)[0],thickness,1440),
                annulus(lambda a:profile(a)[1],lambda a:np.full_like(a,outer),thickness,1440))
    for mesh in ring_parts:
        visual(fixed,trimesh.graph.smooth_shade(mesh),'frame')

    # Explicit convex collision wedges preserve both the centre bore and slot.
    # Refine the two rounded end caps; straight arc walls use 2 degree sectors.
    trim=np.degrees(2*np.arcsin((.0055-pin_radius)/(2*radius)))
    cap_angles=[] if full_turn else [lo+phase+trim,hi+phase-trim]
    edges=sorted(set([*np.arange(0.,360.,2.),360.,
        *[float(a%360) for cap in cap_angles for a in np.arange(cap-3.6,cap+3.61,.15)]]))
    for a,b in zip(edges,edges[1:]):
        if b-a<1e-7: continue
        lower,upper=profile(np.array([a,b]))
        for small,big in ((np.full(2,inner),lower),(upper,np.full(2,outer))):
            vertices=[[x,r*np.sin(t),r*np.cos(t)] for x in (-thickness/2,thickness/2)
                      for j,t in enumerate(np.radians([a,b])) for r in (small[j],big[j])]
            collision(fixed,trimesh.convex.convex_hull(np.array(vertices)),'ring')

    # Continuous, matching-grey mounting feet replace the separate old bearings.
    foot_top=mount+.015
    for sign in (-1,1):
        top=-.052
        leg=trimesh.creation.box(extents=(.020 if full_turn else .026,.020,top-foot_top))
        leg.apply_translation((.026 if full_turn else 0,sign*.090,(top+foot_top)/2))
        solid(fixed,leg,'frame','leg')
    foot=trimesh.creation.box(extents=(.060 if full_turn else .036,.228,.016))
    foot.apply_translation((.014 if full_turn else 0,0,mount+.007))
    solid(fixed,foot,'frame','foot')

    if full_turn:
        # A 360-degree through-slot separates two concentric bands. Rear
        # bridges support the inner band without crossing the pin's swept
        # volume (the rear end of the pin is x=+10 mm).
        for angle in (-125.,125.):
            bridge=sector(.085,.110,angle-5,angle+5,.006)
            bridge.apply_translation((.025,0,0))
            solid(fixed,bridge,'frame','rear_bridge')
            for r0,r1 in ((.084,.090),(.105,.111)):
                post=sector(r0,r1,angle-5,angle+5,.019)
                post.apply_translation((.0165,0,0))
                solid(fixed,post,'frame','rear_spacer')

    # A stepped same-colour ear sits in front of the fixed ring. Its root meets
    # the rotor rim inside the ring bore; only the round pin crosses the slot.
    for r0,r1,width,x in ((.073,.081,.016,-.004),(.075,.103,.008,-.014)):
        ear=sector(r0,r1,phase-4,phase+4,width)
        ear.apply_translation((x,0,0))
        solid(moving,ear,'disc','ear')
    theta=np.radians(phase)
    for rad,width,x,name,collide in ((pin_radius,.027,-.0035,'pin',True),(.0057,.006,-.020,'head',False)):
        pin=trimesh.creation.cylinder(radius=rad,height=width,sections=64)
        pin.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,(0,1,0)))
        pin.apply_translation((x,radius*np.sin(theta),radius*np.cos(theta)))
        visual(moving,pin,'bolt')
        if collide: collision(moving,pin,name)
    # The existing disc mesh already has world-scale dimensions.
    moving.insert(0,(trimesh.load(folder.parent/'visual.obj',process=False),'disc',''))

    def export(parts,name):
        vertices=[];faces=[];uv=[];count=0;colors=list(palette)
        for mesh,color,_ in parts:
            if mesh is None: continue
            vertices.extend(mesh.vertices);faces.extend(mesh.faces+count)
            uv.extend([[(colors.index(color)+.5)/len(colors),.5]]*len(mesh.vertices))
            count+=len(mesh.vertices)
        pixels=np.array([[np.array(palette[c])*255 for c in colors]],dtype=np.uint8)
        texture=Image.fromarray(pixels).resize((96,32),Image.Resampling.NEAREST)
        mesh=trimesh.Trimesh(vertices=np.array(vertices),faces=np.array(faces),process=False)
        mesh.visual=TextureVisuals(uv=np.array(uv),material=PBRMaterial(
            baseColorTexture=texture,metallicFactor=.35,roughnessFactor=.45))
        path=folder/f'{name}.glb';mesh.export(path,include_normals=True)
        return mesh_xml(path,'visual')+''.join(item[2] for item in parts)

    frame=folder/'stop_frame.urdf'
    frame.write_text('<robot name="single_slot_ring"><link name="frame">'+
                     inertial(.25)+export(fixed,'frame_visual')+'</link></robot>')
    (folder/'ring_geometry.json').write_text(json.dumps(dict(
        style='single_ring',slot_count=1,fixed=True,ring_inner_radius=inner*scale,
        ring_outer_radius=outer*scale,ring_thickness=thickness*scale,
        slot_center_radius=radius*scale,slot_width=.011*scale,pin_radius=pin_radius*scale,
        bounds_deg=[lo,hi],continuous_rotation=full_turn,ear_phase_deg=phase,frame_color=palette['frame'],
        frame_metallic=.35,frame_roughness=.45,mount_z=mount*scale),indent=2)+'\n')
    return export(moving,'rotor_visual'),frame


def export_assets(g, stops, cfg, folder):
    colors = disc_colors(cfg.task)
    finish = cfg.task.get('visual', {}).get('plate_finish')
    outline = cfg.task.get('visual', {}).get('aperture_outline')
    floor = float(cfg.env.frames.table_surface.origin[2])
    for i in range(3):
        path = write_disc(g, g.slots[i], folder / f"disc{i}", float(cfg.task.physics.disc_mass),
                   float(cfg.task.physics.disc_damping), colors[i], stop=stops[i],
                   mount_z=floor + .028 - g.axis_z)
        paint_aperture_outline(path, g, g.slots[i], colors[i], outline, finish=finish)
    write_key(g, folder / "key", float(cfg.task.physics.key_mass))
    path = write_endpoint(g, folder / "endpoint")
    paint_aperture_outline(path, g, (g.endpoint_deg,), ENDPOINT_COLOR, outline, goal_plate=True)


# Visual assets authored with this task geometry.



def disc_colors(task_cfg):
    values = np.asarray(task_cfg.get('visual', {}).get('disc_colors', DISC_COLORS), dtype=float)
    if values.shape != (3, 3) or not np.all(np.isfinite(values)) or np.any((values < 0) | (values > 1)):
        raise ValueError('Expected three finite RGB disc colors in [0,1]')
    return values.tolist()


def paint_aperture_outline(urdf_path, g, slots, disc_color, cfg, *, goal_plate=False, finish=None):
    urdf_path = Path(urdf_path)
    if cfg is None or not bool(cfg.get('enabled', False)):
        (urdf_path.parent/'aperture_outline.json').unlink(missing_ok=True)
        return
    width = float(cfg.get('width_m', .0015))
    color = np.asarray(cfg.get('color_rgb', [1., .95, 0.]), dtype=float)
    if not np.isfinite(width) or not 0 < width < g.disc_radius-g.slot_radius:
        raise ValueError('Aperture paint width must fit on the solid rotor face')
    if color.shape != (3,) or not np.all(np.isfinite(color)) or np.any((color<0)|(color>1)):
        raise ValueError('Outline color must be finite RGB in [0,1]')
    tree = ET.parse(urdf_path)
    visuals = tree.findall('.//visual/geometry/mesh')
    if len(visuals) != 1:
        raise ValueError('Rotor outline expects the single combined visual mesh')
    source = Path(visuals[0].get('filename'))
    mesh = trimesh.load(source, force='mesh', process=False)

    size, strip_height = 2048, 32
    extent = g.disc_radius * 1.02
    angles = np.arange(720) * 2*np.pi/720
    degrees = np.degrees(angles)
    error = np.minimum.reduce([np.abs((degrees-s+180)%360-180) for s in slots])
    radii = np.where(error <= g.slot_half_deg, g.slot_radius, g.bore_radius)
    # Texture rows run downwards; +z runs upwards on the physical rotor.
    pixel = np.c_[(radii*np.sin(angles)/extent+1)*(size-1)/2,
                  (1-radii*np.cos(angles)/extent)*(size-1)/2]
    opening = Image.new('L', (size, size))
    ImageDraw.Draw(opening).polygon([tuple(p) for p in pixel], fill=255)
    solid = np.asarray(opening) == 0
    distance_m = distance_transform_edt(solid) * (2*extent/(size-1))
    paint = solid & (distance_m <= width)
    face = np.empty((size, size, 3), dtype=np.uint8)
    face[:] = (np.asarray(disc_color)*255).astype(np.uint8)
    face[paint] = np.rint(color*255).astype(np.uint8)

    if mesh.visual.kind == 'texture':
        material = deepcopy(mesh.visual.material)
        original = material.baseColorTexture.convert('RGB')
        uv = np.asarray(mesh.visual.uv).copy()
    else:
        material = PBRMaterial(metallicFactor=.35, roughnessFactor=.45)
        original = Image.new('RGB', (1, 1), tuple((np.asarray(disc_color)*255).astype(int)))
        uv = np.full((len(mesh.vertices), 2), .5)
    height = size + strip_height
    atlas = Image.new('RGB', (size, height))
    atlas.paste(original.resize((size, strip_height), Image.Resampling.NEAREST), (0, 0))
    atlas.paste(Image.fromarray(face), (0, strip_height))
    # Preserve existing ear/pin colours in a separate strip of the same atlas.
    uv[:, 1] = 1-(1-uv[:, 1])*strip_height/height
    v = mesh.vertices
    rotor_faces = np.isclose(np.abs(v[:, 0]), g.disc_thickness/2, atol=2e-7, rtol=0)
    # The square goal's corners lie outside the rotor radius; map its complete
    # face so triangles do not interpolate between the face and hardware strip.
    radius = np.max(np.abs(v[:, 1:3]), axis=1) if goal_plate else np.linalg.norm(v[:, 1:3], axis=1)
    rotor_faces &= radius <= g.disc_radius+1e-7
    if not np.any(rotor_faces):
        raise ValueError('No rotor face vertices found for aperture paint')
    uv[rotor_faces, 0] = (v[rotor_faces, 1]/extent+1)/2
    uv[rotor_faces, 1] = 1-(strip_height+(1-v[rotor_faces, 2]/extent)*size/2)/height
    material.baseColorTexture = atlas
    if finish is not None:
        for name, attribute in (('metallic', 'metallicFactor'), ('roughness', 'roughnessFactor')):
            value = float(finish[name])
            if not np.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Invalid visual finish')
            setattr(material, attribute, value)
    mesh.visual = TextureVisuals(uv=uv, material=material)
    target = urdf_path.parent/'outlined_visual.glb'
    mesh.export(target, include_normals=True)
    visuals[0].set('filename', str(target.resolve()))
    # The embedded texture owns both the plate colour and the yellow paint.
    # A uniform URDF material would tint or replace it on the plain goal mesh.
    for visual in tree.findall('.//visual'):
        for finish in visual.findall('material'):
            visual.remove(finish)
    tree.write(urdf_path, encoding='unicode')
    (urdf_path.parent/'aperture_outline.json').write_text(json.dumps(dict(
        enabled=True, width_m=width, color_rgb=color.tolist(), both_faces=True,
        paint_side='solid side of the aperture silhouette', boundary_samples=720,
        geometry_changed=False, collision_changed=False,
        source_visual=str(source), outlined_visual=str(target.resolve()),
    ), indent=2)+'\n')
