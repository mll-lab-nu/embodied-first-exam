"""Flat grasp pads added to the original independent hard claw pieces."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from .interlocked_claws import reference_body_poses


def add_grip_blocks(assembly, folder):
    frames = reference_body_poses(assembly.reference, assembly.initial_qpos)
    for body in assembly.bodies:
        hand = frames[body.source['gripper_body']]
        transform = np.linalg.inv(body.pose)@hand
        transform[:3,3] += transform[:3,:3]@np.array([.13,0.,-.003])
        size = [.030,.028,.024]
        block = trimesh.creation.box(size, transform=transform)
        combined = trimesh.boolean.union([body.mesh,block],engine='manifold')
        if not combined.is_watertight or len(combined.split()) != 1:
            raise ValueError('Hard claw grip must join its existing piece')
        combined.density = assembly.reference['density_kg_m3']
        body.mesh = combined
        root = Path(folder)/body.name
        combined.export(root/'mesh_with_grip.obj',digits=12,include_texture=False)
        path = root/f'{body.name}.urdf'
        tree = ET.parse(path);link = tree.getroot().find('link')
        link.find('visual/geometry/mesh').set('filename','mesh_with_grip.obj')
        node = ET.SubElement(link,'collision')
        ET.SubElement(node,'origin',xyz=' '.join(map(str,transform[:3,3])),
            rpy=' '.join(map(str,Rotation.from_matrix(transform[:3,:3]).as_euler('xyz'))))
        ET.SubElement(ET.SubElement(node,'geometry'),'box',size=' '.join(map(str,size)))
        props = combined.mass_properties;inertia = link.find('inertial')
        inertia.find('origin').set('xyz',' '.join(map(str,props.center_mass)))
        inertia.find('mass').set('value',str(props.mass))
        inertia.find('inertia').attrib.update({f'i{a}{b}':str(props.inertia[i,j])
            for a,b,i,j in [('x','x',0,0),('y','y',1,1),('z','z',2,2),('x','y',0,1),('x','z',0,2),('y','z',1,2)]})
        ET.indent(tree);tree.write(path,encoding='unicode')
    world = [b.mesh.copy().apply_transform(b.pose) for b in assembly.bodies]
    collider = trimesh.collision.CollisionManager();collider.add_object('first',world[0])
    if collider.in_collision_single(world[1]):
        raise ValueError('Hard grasp pads intersect the other claw')
