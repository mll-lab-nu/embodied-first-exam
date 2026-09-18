"""One fixed annular frame with one real, rounded arcuate through-slot."""
import json
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from ._staged_lock_geometry import annulus, sector, mesh_xml, inertial


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
