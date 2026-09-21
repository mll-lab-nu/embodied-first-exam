"""MuJoCo rigid stops and a length-constrained flexible cord.

This explicit approximation uses 1D flex elements with negligible bending
stiffness, nonlocal self contacts, two sliding bored beads, and pivoting stops.
It is not FEM. The task's volumetric FEM candidate lives in fem.py;
historical recordings and this legacy executor retain their original model.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from .geometry import SlottedPostLayout, centerline, make_meshes


def values(v):
    return " ".join(f"{x:.12g}" for x in np.asarray(v).ravel())


def wxyz(r):
    return r.as_quat()[[3, 0, 1, 2]]


def capture_sources(output):
    """Freeze execution code before a long run can outlive workspace edits."""
    folder=Path(output)/'runtime_sources'
    folder.mkdir(parents=True,exist_ok=False)
    for path in Path(__file__).parent.glob('*.py'):
        shutil.copy2(path,folder/path.name)


@dataclass(frozen=True)
class PhysicsSettings:
    dt: float = .000125
    segment_m: float = .008
    rope_density: float = 700.
    node_damping: float = .01
    wood_density: float = 650.
    friction: float = .35
    contact_time_s: float = .001
    contact_impedance: float = .999
    ccd_tolerance_m: float = 1e-9
    ccd_iterations: int = 100


def build_model(output, settings=PhysicsSettings(), layout=SlottedPostLayout(), robot=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    capture_sources(output)
    layout.validate()
    if settings.dt <= 0 or settings.segment_m <= 0:
        raise ValueError("Positive integration and discretization steps required")
    if robot:
        from omegaconf import OmegaConf
        from topogym.robot.assets import robot_asset
        cfg = OmegaConf.load(Path(__file__).resolve().parents[3]/"configs/robot_control_configs/aloha_position_ik.yaml")
        root = ET.parse(robot_asset(cfg)).getroot()
        for element in list(root.findall('keyframe'))+list(root.findall('option')):
            root.remove(element)
        for body in root.findall('.//body'):
            body.set('gravcomp', '1')
        for joint in root.findall('worldbody//joint'):
            joint.set('actuatorgravcomp', 'true')
        world = root.find('worldbody')
        asset = root.find('asset')
        default = root.find('default')
        equality = root.find('equality')
        for p in root.findall('default/default/default/position'):
            if p.get('kp') != '2000':
                p.set('kp', '3000'); p.set('kv', '100')
    else:
        root = ET.Element('mujoco', model='slotted_post_ring_physical_v1')
        ET.SubElement(root, 'compiler', angle='radian', autolimits='true')
        world = ET.SubElement(root, 'worldbody')
        asset = ET.SubElement(root, 'asset')
        default = ET.SubElement(root, 'default')
        equality = ET.SubElement(root, 'equality')
    if equality is None:
        equality = ET.SubElement(root, 'equality')
    option = ET.SubElement(root, 'option', timestep=str(settings.dt), integrator='implicitfast',
                          solver='Newton', iterations='100', tolerance='1e-10', cone='elliptic',
                          jacobian='sparse', gravity='0 0 -9.81',
                          ccd_tolerance=str(settings.ccd_tolerance_m),
                          ccd_iterations=str(settings.ccd_iterations))
    ET.SubElement(option, 'flag', energy='enable')
    ET.SubElement(default, 'geom', friction=f'{settings.friction} .002 .00005', condim='3',
                  solref=f'{settings.contact_time_s} 1', solimp=f'{settings.contact_impedance} .9999 .001 .5 2',
                  margin='0', gap='0')
    contact = root.find('contact')
    if contact is None:
        contact = ET.SubElement(root, 'contact')
    ET.SubElement(world, 'geom', name='table', type='plane', size='1.5 1.5 .05', rgba='.82 .83 .81 1')
    ET.SubElement(world, 'light', pos='0 -1 2', dir='0 .3 -1', diffuse='.8 .8 .8')
    ET.SubElement(world, 'light', pos='1 1 1.5', dir='-.3 -.3 -1', diffuse='.5 .5 .5')
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='1280', offheight='960')
    ET.SubElement(visual, 'headlight', diffuse='.5 .5 .5', ambient='.3 .3 .3', specular='.2 .2 .2')
    parts, _ = make_meshes(layout)
    colors = dict(base='.65 .40 .20 1', post='.32 .13 .055 1', target_ring='.4 .20 .07 1',
                  bead_left='.80 .58 .29 1', bead_right='.80 .58 .29 1',
                  disc_left='.48 .25 .10 1', disc_right='.48 .25 .10 1')

    def visual_mesh(body, name, shift=(0, 0, 0)):
        mesh = parts[name].copy()
        mesh.apply_translation(-np.asarray(shift))
        mesh.export(output/f'{name}.obj')
        ET.SubElement(asset, 'mesh', name=f'{name}_visual', file=str(output/f'{name}.obj'))
        ET.SubElement(body, 'geom', name=f'{name}_visual', type='mesh', mesh=f'{name}_visual',
                      contype='0', conaffinity='0', mass='0', group='2', rgba=colors[name])

    base = ET.SubElement(world, 'body', name='base')
    ET.SubElement(base, 'geom', name='base_collision', type='box',
                  size=values([layout.base_width_m/2, layout.base_depth_m/2, layout.base_height_m/2]),
                  pos=values([0, 0, layout.base_height_m/2]), group='3')
    visual_mesh(base, 'base')
    post = ET.SubElement(world, 'body', name='post')
    vertices, faces = trimesh.creation.triangulate_polygon(layout.post_polygon(), engine='earcut')
    for i, face in enumerate(faces):
        tri = vertices[face]
        cloud = np.vstack([np.column_stack([tri[:, 0], np.full(3, y), tri[:, 1]])
                           for y in (-layout.post_depth_m/2, layout.post_depth_m/2)])
        mesh = trimesh.convex.convex_hull(cloud)
        ET.SubElement(asset, 'mesh', name=f'post_piece_{i}', vertex=values(mesh.vertices), face=values(mesh.faces))
        ET.SubElement(post, 'geom', name=f'post_collision_{i}', type='mesh', mesh=f'post_piece_{i}', group='3')
    visual_mesh(post, 'post')
    ring = ET.SubElement(world, 'body', name='target_ring', pos=values([0, 0, layout.ring_z]))
    ET.SubElement(ring, 'freejoint', name='ring_free')
    for i in range(64):
        angles = np.array([i, i+1])*2*np.pi/64
        points = np.column_stack([layout.ring_major_radius_m*np.cos(angles),
                                  layout.ring_major_radius_m*np.sin(angles), np.zeros(2)])
        ET.SubElement(ring, 'geom', name=f'ring_collision_{i}', type='capsule', fromto=values(points),
                      size=str(layout.ring_tube_radius_m), density=str(settings.wood_density), group='3')
    # Compound capsules overlap; use exact solid torus mass and inertia.
    mass = settings.wood_density*2*np.pi**2*layout.ring_major_radius_m*layout.ring_tube_radius_m**2
    ix = mass*(.5*layout.ring_major_radius_m**2+.625*layout.ring_tube_radius_m**2)
    iz = mass*(layout.ring_major_radius_m**2+.75*layout.ring_tube_radius_m**2)
    ET.SubElement(ring, 'inertial', pos='0 0 0', mass=str(mass), diaginertia=values([ix, ix, iz]))
    visual_mesh(ring, 'target_ring', [0, 0, layout.ring_z])

    cord = centerline(layout, settings.segment_m)
    length = np.linalg.norm(np.diff(cord, axis=0), axis=1)
    for i, point in enumerate(cord):
        body = ET.SubElement(world, 'body', name=f'cord_{i}', pos=values(point))
        for axis in range(3):
            ET.SubElement(body, 'joint', name=f'cord_{i}_{axis}', type='slide',
                          axis=values(np.eye(3)[axis]), damping=str(settings.node_damping))
        mass = settings.rope_density*np.pi*layout.rope_radius_m**2*(
            length[0]/2 if i == 0 else length[-1]/2 if i == len(cord)-1 else (length[i-1]+length[i])/2)
        ET.SubElement(body, 'inertial', pos='0 0 0', mass=str(mass), diaginertia='1e-9 1e-9 1e-9')
        ET.SubElement(body, 'site', name=f'cord_node_{i}' if i < len(cord)-1 else 'cord_tip',
                      pos='0 0 0', size='.001', group='4')
    deformable = ET.SubElement(root, 'deformable')
    flex = ET.SubElement(deformable, 'flex', name='cord', dim='1', radius=str(layout.rope_radius_m),
                        body=' '.join(f'cord_{i}' for i in range(len(cord))),
                        element=values(np.column_stack([np.arange(len(length)), np.arange(1, len(cord))])),
                        rgba='.90 .88 .80 1')
    ET.SubElement(flex, 'contact', selfcollide='auto', internal='true', condim='3',
                  friction=f'{settings.friction} .002 .00005', solref=f'{settings.contact_time_s} 1',
                  solimp=f'{settings.contact_impedance} .9999 .001 .5 2')
    ET.SubElement(equality, 'flex', name='cord_lengths', flex='cord',
                  solref='.001 1', solimp='.9999 .99999 .001 .5 2')
    bead_indices = {}
    for side, control in (('left', 2), ('right', 15)):
        point = layout.cord_controls()[control]
        i = int(np.argmin(np.linalg.norm(cord-point, axis=1)))
        bead_indices[side] = i
        rotation = Rotation.from_matrix(trimesh.geometry.align_vectors([0, 0, 1], cord[i+1]-cord[i-1])[:3,:3])
        bead = ET.SubElement(world, 'body', name=f'bead_{side}', pos=values(cord[i]), quat=values(wxyz(rotation)))
        ET.SubElement(bead, 'freejoint', name=f'bead_{side}_free')
        r, h = layout.bead_radius_m, layout.bead_hole_radius_m
        z = np.linspace(-np.sqrt(r*r-h*h), np.sqrt(r*r-h*h), 25)
        rho = np.sqrt(r*r-z*z)
        for k in range(16):
            angles = np.linspace(k*2*np.pi/16, (k+1)*2*np.pi/16, 3)
            cloud = np.concatenate([np.column_stack([rho*np.cos(a), rho*np.sin(a), z]) for a in angles])
            mesh = trimesh.convex.convex_hull(cloud)
            meshname = f'bead_{side}_wedge_{k}'
            ET.SubElement(asset, 'mesh', name=meshname, vertex=values(mesh.vertices), face=values(mesh.faces))
            ET.SubElement(bead, 'geom', name=meshname, type='mesh', mesh=meshname,
                          density=str(settings.wood_density), rgba=colors[f'bead_{side}'])

    for side, x, y, endpoint in (('left', -.092, -.324, 0), ('right', .104, -.320, -1)):
        pos = np.array([x, y, layout.floor_clearance_m+layout.disc_thickness_m/2])
        body = ET.SubElement(world, 'body', name=f'disc_{side}', pos=values(pos))
        ET.SubElement(body, 'freejoint', name=f'disc_{side}_free')
        ET.SubElement(body, 'geom', name=f'disc_{side}_collision', type='cylinder',
                      size=values([layout.disc_radius_m, layout.disc_thickness_m/2]),
                      density=str(settings.wood_density), group='3')
        visual_mesh(body, f'disc_{side}', pos)
        ET.SubElement(body, 'site', name=f'disc_{side}_anchor', pos=values(cord[endpoint]-pos), size='.001', group='4')
        ET.SubElement(equality, 'connect', name=f'terminal_{side}',
                      site1=f'disc_{side}_anchor', site2='cord_node_0' if endpoint == 0 else 'cord_tip',
                      solref='.002 1', solimp='.999 .9999 .001 .5 2')

    xml = ET.tostring(root, encoding='unicode')
    (output/'scene.xml').write_text(xml)
    spec = dict(layout=asdict(layout), settings=asdict(settings), cord_nodes=cord.tolist(),
                cord_segment_lengths=length.tolist(), bead_indices=bead_indices,
                robot=robot,
                rope_model='length-constrained 1D flex capsules; negligible bending stiffness',
                beads='independent free bored rigid bodies; contact-mediated sliding along cord',
                terminals='two permanent positional connections, free pivot rotation',
                collision_approximations='64 overlapping ring capsules; convex post prisms and bored bead wedges; solid discs with exterior knot attachment sites')
    (output/'model_spec.json').write_text(json.dumps(spec, indent=2)+'\n')
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    if robot:
        home = [0, -.96, 1.16, 0, -.3, 0, .037, .037]
        data.qpos[:16] = home*2
        data.ctrl[:] = data.qpos[model.jnt_qposadr[model.actuator_trnid[:, 0]]]
    mujoco.mj_forward(model, data)
    mujoco.mj_saveModel(model, str(output/'scene.mjb'))
    return model, data, spec


def node_positions(model, data):
    ids = [i for i in range(model.nsite) if model.site(i).name.startswith('cord_node_') or model.site(i).name == 'cord_tip']
    return data.site_xpos[ids].copy()


def contact_summary(model, data):
    depths = {}
    for c in data.contact:
        if c.dist >= 0:
            continue
        a, b = [model.geom(int(i)).name or '' if i >= 0 else 'cord_flex' for i in (c.geom1, c.geom2)]
        kind = 'cord_self' if a.startswith('cord_') and b.startswith('cord_') else 'solid'
        if a == 'table' or b == 'table':
            kind = 'table'
        elif 'post_' in a or 'post_' in b:
            kind = 'post'
        depths[kind] = max(depths.get(kind, 0.), float(-c.dist))
    return depths
