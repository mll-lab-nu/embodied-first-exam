"""Visible double-sided arcuate slots and collision end stops for lock rotors."""
from pathlib import Path
import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals
from PIL import Image

from ._staged_lock_geometry import sector, mesh_xml, inertial


def limit_assets(g, cfg, folder, disc_color, mount_z=None):
    """Return moving visuals/colliders and a fixed, bolted stop-frame URDF.

    All dimensions scale with disc radius. The pin occupies +/-2 degrees;
    physical stop faces lie two degrees beyond the specified hinge endpoints.
    """
    if cfg.get('style','rails') == 'single_ring':
        from ._staged_lock_ring import ring_limit_assets
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
