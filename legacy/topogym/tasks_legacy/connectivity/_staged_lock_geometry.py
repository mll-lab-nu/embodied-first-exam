"""Geometry for a passive-disc lock, free rigid key and physical pickup rests.

Collision pieces are explicit convex sectors. No convex hull spans a hole.
Angles run from +z toward +y, i.e. about the negative x axis.
"""
from dataclasses import dataclass, replace, asdict
from pathlib import Path
import json
import numpy as np
import trimesh


def angle_error(a, b):
    return abs((a-b+180.) % 360.-180.)


@dataclass(frozen=True)
class LockGeometry:
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
        if len(self.slots) != 3 or len(self.initial_disc_deg) != 3:
            raise ValueError('Three passive discs are required')
        if not 0 < self.shaft_radius < self.bore_radius < self.tab_radius < self.slot_radius < self.disc_radius:
            raise ValueError('Invalid radial clearance')
        if not 0 < self.tab_half_deg < self.slot_half_deg < 30:
            raise ValueError('Invalid angular clearance')
        if self.pitch <= 2*self.disc_thickness or self.grip_offset <= 3*self.pitch + .03:
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
        for tab in range(3):
            x=self.tip_x(depth)-tab*self.pitch
            for i in range(3):
                if abs(x-self.disc_x(i)) < (self.tab_thickness+self.disc_thickness)/2:
                    if self.slot_margin(angle,disc_angles[i],i) < -tolerance:
                        issues.append(f'tab{tab}/disc{i}')
            if abs(x-self.disc_x(3)) < (self.tab_thickness+self.disc_thickness)/2:
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
        from ._staged_lock_limits import limit_assets
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
    body=inertial(.2)+mesh_xml(visual,'visual',(.10,.34,.28))+''.join(mesh_xml(p,'collision') for p in collisions)
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
    for i in range(3):
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
