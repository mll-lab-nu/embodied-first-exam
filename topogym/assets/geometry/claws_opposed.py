"""Approved opposed-hand acute-window prototype, independent graspable solids."""
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from .interlocked_claws import load_reference, reference_body_poses, DENSITY, COLORS
from .hedgehog_in_cage import write_body

def box(center, size, rotation=None):
    T=np.eye(4); T[:3,3]=center
    if rotation is not None: T[:3,:3]=rotation
    mesh = trimesh.creation.box(size, transform=T)
    mesh.metadata['collision'] = dict(kind='box',size=list(size),transform=T.tolist())
    return mesh

def rod(a,b,r=.006):
    a,b=np.array(a),np.array(b)
    T=trimesh.geometry.align_vectors([0,0,1],b-a)
    T[:3,3]=(a+b)/2
    mesh = trimesh.creation.cylinder(radius=r,height=np.linalg.norm(b-a),sections=24,transform=T)
    mesh.metadata['collision'] = dict(kind='cylinder',radius=r,length=float(np.linalg.norm(b-a)),transform=T.tolist())
    return mesh


def build_opposed_windows(folder, gate_extra_m=(0., 0.)):
    """gate_extra_m widens gates A/B: real metres added to each aperture side."""
    folder=Path(folder)
    q=np.tile([0.,-.96,1.16,0.,-.2,0.,.0222,.0222],2)
    frames=reference_body_poses(load_reference(),q)
    tcps=[(frames[i]@np.array([.13,0,-.003,1]))[:3] for i in (7,17)]
    SCALE=(tcps[1][0]-tcps[0][0])/.593
    ANGLE=55.
    R=Rotation.from_euler('z',ANGLE,degrees=True).as_matrix()
    origin=tcps[0]-np.array([-.22,0,.08])*SCALE
    ea,eb=(float(e)/SCALE for e in gate_extra_m)
    def frame(center, rotation, e):
        # (160+2e) x (180+2e) mm clear aperture; 12 mm square frame sections.
        c=np.array(center)
        return [box(c+rotation@np.array(p),size,rotation) for p,size in [
            ((0,-.086-e,0),(.012,.012,.204+2*e)),((0,.086+e,0),(.012,.012,.204+2*e)),
            ((0,0,-.096-e),(.012,.162+2*e,.012)),((0,0,.096+e),(.012,.162+2*e,.012))]]

    gate_a=frame([0,0,0],np.eye(3),ea)
    gate_b=frame([.18,0,0],R,eb)
    connectors=[]
    for z in (-.096,.096):
        for y in (-.086,.086):
            a=np.array([0,y+np.sign(y)*ea,z+np.sign(z)*ea])
            b=np.array([0,y+np.sign(y)*eb,z+np.sign(z)*eb])
            connectors.append(rod(a,np.array([.18,0,0])+R@b,.0045))
    # Rear U frame routes around the hook; a central axial tang faces the left hand.
    basket=[rod([0,-.086-ea,.08],[-.14,-.11,.08],.008),
            rod([0,.086+ea,.08],[-.14,.11,.08],.008),
            rod([-.14,-.11,.08],[-.14,.11,.08],.008),
            rod([-.14,0,.08],[-.26,0,.08],.008),
            box([-.22,0,.08],[.07,.028/SCALE,.024/SCALE])]
    wood_parts=gate_a+gate_b+connectors+basket

    # J hook: a long upper shaft, a deep return, and a short upturned nose.
    # Head initially left of gate A; the shaft already threads both windows.
    hook_points=[(.41,0,.08),(-.072,0,.08),(-.072,0,-.12),(-.030,0,-.12),(-.030,0,-.065)]
    hook_meshes=[rod(a,b,.006) for a,b in zip(hook_points,hook_points[1:])]
    for p in hook_points[1:-1]:
        m=trimesh.creation.icosphere(subdivisions=2,radius=.006);m.apply_translation(p)
        T=np.eye(4);T[:3,3]=p
        m.metadata['collision']=dict(kind='sphere',radius=.006,transform=T.tolist())
        hook_meshes.append(m)
    hook_meshes.append(box([.373,0,.08],[.07,.028/SCALE,.024/SCALE]))



    bodies=[]
    for i,parts in enumerate((wood_parts,hook_meshes)):
        for part in parts: part.apply_scale(SCALE)
        mesh=trimesh.boolean.union(parts,engine='manifold')
        if not mesh.is_watertight or len(mesh.split())!=1:
            raise ValueError("Each claw must be one connected solid")
        name=f"piece_{i}"
        write_body(folder,name,mesh,[mesh],COLORS[i],DENSITY,finish='wood' if i==0 else 'metal')
        # Exact primitive compounds retain the apertures and avoid a single
        # coarse whole-object SDF inventing millimetres of finger penetration.
        import xml.etree.ElementTree as ET
        tree=ET.parse(folder/f'{name}.urdf');link=tree.getroot().find('link')
        for node in list(link.findall('collision')):link.remove(node)
        for part in parts:
            primitive=part.metadata['collision'];T=np.asarray(primitive['transform'])
            node=ET.SubElement(link,'collision')
            ET.SubElement(node,'origin',xyz=' '.join(map(str,T[:3,3]*SCALE)),
                rpy=' '.join(map(str,Rotation.from_matrix(T[:3,:3]).as_euler('xyz'))))
            geom=ET.SubElement(node,'geometry');kind=primitive['kind']
            if kind=='box':values={'size':' '.join(map(str,np.asarray(primitive['size'])*SCALE))}
            elif kind=='cylinder':values={'radius':str(primitive['radius']*SCALE),'length':str(primitive['length']*SCALE)}
            else:values={'radius':str(primitive['radius']*SCALE)}
            ET.SubElement(geom,kind,**values)
        ET.indent(tree);tree.write(folder/f'{name}.urdf',encoding='unicode')
        (folder/f'{name}_collision_000.obj').unlink()
        pose=np.eye(4);pose[:3,3]=origin
        bodies.append(SimpleNamespace(name=name,mesh=mesh,pose=pose,color=COLORS[i],asset_path=folder/f'{name}.urdf'))
    manager=trimesh.collision.CollisionManager();manager.add_object('frame',bodies[0].mesh)
    if manager.in_collision_single(bodies[1].mesh):raise ValueError('Initial claws intersect')
    report=dict(family='acute_windows_opposed',angle_deg=ANGLE,scale=SCALE,
        gate_extra_per_side_m=[float(e) for e in gate_extra_m],
        aperture_m=[(.160+2*ea)*SCALE,(.180+2*ea)*SCALE],
        gate_b_aperture_m=[(.160+2*eb)*SCALE,(.180+2*eb)*SCALE],
        initial_surface_gap_m=float(manager.min_distance_single(bodies[1].mesh)),
        finger_joint_position_m=.0222,grip_width_m=.028,grip_height_m=.024,
        collision_model='compound_boxes_cylinders_spheres',
        robot_geometry_modified=False,initialization='bilateral friction pregrasp',
        full_path_verified=False,two_turns_necessary_verified=False)
    (folder/'geometry_report.json').write_text(json.dumps(report,indent=2)+'\n')
    return SimpleNamespace(bodies=bodies,reference={'density_kg_m3':DENSITY}),report,q
