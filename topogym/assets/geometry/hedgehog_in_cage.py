from __future__ import annotations

"""Generate inspectable compound assets; all dimensions derive from one template.

The reconstruction has no certified solution. Each cage collision piece is
convex; no hull is ever taken across the complete cage or complete hedgehog.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from topogym.utils.geometry.rigid_geometry import vector_text

from topogym.assets.library import resource_path


def load_template(path=None):
    data = json.loads(Path(path or resource_path("hedgehog_in_cage/template.json")).read_text())
    cage, ball = data["cage"], data["hedgehog"]
    if data["units"] != "mm" or len(ball["spikes"]) != 10:
        raise ValueError("CLASSIC three-star requires an explicit 10-spike mm template")
    if not (0 < cage["wall_thickness"] < cage["outer_diameter"] / 2):
        raise ValueError("Invalid cage wall")
    if not (0 < cage["collar_height"] < cage["height"] / 2):
        raise ValueError("Invalid cage collar")
    if len(cage["window_widths"]) != cage["window_count"] or len(cage["window_centers_deg"]) != cage["window_count"]:
        raise ValueError("Each window requires a width and an angle")
    widths = np.asarray(cage["window_widths"])
    if np.any(widths <= 2 * cage["corner_radius"]) or widths.max() >= cage["outer_diameter"] - 2 * cage["wall_thickness"]:
        raise ValueError("Window width must fit the inner cage diameter")
    if ball["spike_shape"] != "cylinder":
        raise ValueError("Hedgehog projections must be flat-ended cylinders")
    if not (0 < ball["spike_radius"] < ball["core_radius"]):
        raise ValueError("Invalid core or spike radii")
    for spike in ball["spikes"]:
        if spike["exposed_length"] <= 0 or np.linalg.norm(spike["direction"]) < 1e-10:
            raise ValueError("Invalid spike")
    return data


@dataclass
class HedgehogLayout:
    template: dict
    scale: float = 3.0

    def __post_init__(self):
        if not np.isfinite(self.scale) or self.scale <= 0:
            raise ValueError("Scale must be finite and positive")

    @property
    def unit(self):
        return self.scale / 1000

    def spike_segments(self):
        ball = self.template["hedgehog"]
        result = []
        for spike in ball["spikes"]:
            direction = np.asarray(spike["direction"], dtype=float)
            direction /= np.linalg.norm(direction)
            # Embed the root into the sphere; the exposed length is measured
            # from the nominal sphere surface to the flat cylinder end.
            a = direction * (ball["core_radius"] - .6) * self.unit
            b = direction * (ball["core_radius"] + spike["exposed_length"]) * self.unit
            result.append((a, b))
        return result


def band_mesh(angles, inner, outer, lower, upper, closed=True):
    """Watertight annular band or sector, including non-flat window edges."""
    n = len(angles)
    lower, upper = np.broadcast_to(lower, (n,)), np.broadcast_to(upper, (n,))
    vertices = []
    for angle, lo, hi in zip(angles, lower, upper):
        for radius, z in ((outer, lo), (outer, hi), (inner, lo), (inner, hi)):
            vertices.append([radius * np.cos(angle), radius * np.sin(angle), z])
    faces = []
    for i in range(n if closed else n - 1):
        a, b = 4 * i, 4 * ((i + 1) % n)
        for q in ((a, b, b+1, a+1), (a+2, a+3, b+3, b+2),
                  (a, a+2, b+2, b), (a+1, b+1, b+3, a+3)):
            faces.extend([(q[0], q[1], q[2]), (q[0], q[2], q[3])])
    if not closed:
        for q in ((0, 1, 3, 2), (4*(n-1), 4*(n-1)+2, 4*(n-1)+3, 4*(n-1)+1)):
            faces.extend([(q[0], q[1], q[2]), (q[0], q[2], q[3])])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    mesh.fix_normals()
    return mesh


def cage_meshes(layout):
    c, u = layout.template["cage"], layout.unit
    outer = c["outer_diameter"] / 2 * u
    inner = outer - c["wall_thickness"] * u
    half = c["height"] / 2 * u
    rim = half - c["collar_height"] * u
    corner = c["corner_radius"] * u
    centers = np.radians(c["window_centers_deg"])
    widths = np.asarray(c["window_widths"]) * u
    # Widths are chord widths at the inner wall. Explicit boundary samples
    # prevent the sampling grid from silently changing a window's width.
    half_angles = np.arcsin(widths / (2 * inner))
    boundaries = np.r_[centers-half_angles, centers+half_angles] % (2*np.pi)
    angles = np.unique(np.r_[np.linspace(0, 2*np.pi, c["angular_segments"], endpoint=False), boundaries])
    delta = (angles[:, None] - centers + np.pi) % (2*np.pi) - np.pi
    selected = np.argmin(np.abs(delta), axis=1)
    distance = np.abs(delta[np.arange(len(angles)), selected])
    in_window = distance <= half_angles[selected] + 1e-10
    offset = inner * np.sin(distance)
    edge_distance = np.maximum(offset - (widths[selected]/2 - corner), 0)
    rise = corner - np.sqrt(np.maximum(corner**2 - edge_distance**2, 0))
    low = np.where(in_window, -rim + rise, -rim + corner)
    high = -low
    visual = [band_mesh(angles, inner, outer, -half, low),
              band_mesh(angles, inner, outer, high, half)]
    collision = []
    for i in range(len(angles)):
        j = (i+1) % len(angles)
        pair = np.array([angles[i], angles[j] if j else 2*np.pi])
        midpoint = pair.mean() % (2*np.pi)
        d = np.abs((midpoint-centers+np.pi) % (2*np.pi)-np.pi)
        open_segment = bool(np.any(d < half_angles))
        for lower, upper in ((np.full(2, -half), low[[i, j]]),
                             (high[[i, j]], np.full(2, half))):
            collision.append(band_mesh(pair, inner, outer, lower, upper, False).convex_hull)
        if not open_segment:
            mesh = band_mesh(pair, inner, outer, low[[i, j]], high[[i, j]], False)
            visual.append(mesh)
            collision.append(mesh.convex_hull)
    # Thick rims extend toward the smaller axial holes, as in the reference
    # appearance; openings remain open in both visual and collision meshes.
    hole = c["collar_hole_radius"] * u
    for lo, hi in ((-half, -rim), (rim, half)):
        visual.append(band_mesh(angles, hole, inner, lo, hi))
        for i in range(len(angles)):
            pair = [angles[i], angles[(i+1) % len(angles)] if i+1 < len(angles) else 2*np.pi]
            collision.append(band_mesh(pair, hole, inner, lo, hi, False).convex_hull)
    return trimesh.util.concatenate(visual), collision


def hedgehog_meshes(layout):
    b, u = layout.template["hedgehog"], layout.unit
    core = trimesh.creation.icosphere(subdivisions=3, radius=b["core_radius"]*u)
    pieces = [core]
    for start, end in layout.spike_segments():
        length = np.linalg.norm(end-start)
        # The "spikes" are constant-radius wooden dowels with flat end caps.
        mesh = trimesh.creation.cylinder(
            radius=b["spike_radius"]*u, height=length, sections=32)
        transform = trimesh.geometry.align_vectors([0, 0, 1], (end-start)/length)
        transform[:3, 3] = (start + end) / 2
        mesh.apply_transform(transform)
        pieces.append(mesh)
    return trimesh.util.concatenate(pieces), pieces


def write_body(folder, name, visual, collision, color, density, finish="metal"):
    folder.mkdir(parents=True, exist_ok=True)
    visual.export(folder / f"{name}.obj")
    if finish == "wood":
        from topogym.assets.surfaces import wood_visual
        light = name == "hedgehog"
        visual = wood_visual(visual, resource_path("hedgehog_in_cage/materials/"+("light_wood.png" if light else "dark_wood.png")),
            roughness=.62 if light else .67,
            tile_size=float(visual.extents.max()) * (.7 if light else .8),
            grain_horizontal=light)
        color = (1., 1., 1., 1.)
    elif finish == "metal":
        from trimesh.visual.material import PBRMaterial
        from trimesh.visual.texture import TextureVisuals
        visual.visual = TextureVisuals(uv=np.zeros((len(visual.vertices), 2)),
            material=PBRMaterial(baseColorFactor=color, metallicFactor=.75,
                                 roughnessFactor=.32 if name == "hedgehog" else .42))
    else:
        raise ValueError(f"Unknown visual finish: {finish}")
    visual.export(folder / f"{name}.glb", include_normals=True)
    root = ET.Element("robot", name=name)
    link = ET.SubElement(root, "link", name=name)
    # Provisional composite inertia. Overlap at embedded spike roots is
    # explicitly retained; this is not a manufacturer mass measurement.
    aggregate = trimesh.util.concatenate(collision)
    aggregate.density = density
    properties = aggregate.mass_properties
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "origin", xyz=vector_text(properties.center_mass))
    ET.SubElement(inertial, "mass", value=str(properties.mass))
    matrix = properties.inertia
    ET.SubElement(inertial, "inertia", **{f"i{a}{b}": str(matrix[i, j])
        for a,b,i,j in (("x","x",0,0),("y","y",1,1),("z","z",2,2),
                         ("x","y",0,1),("x","z",0,2),("y","z",1,2))})
    node = ET.SubElement(link, "visual")
    ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename=f"{name}.glb")
    ET.SubElement(ET.SubElement(node, "material", name=finish), "color", rgba=vector_text(color))
    for i, mesh in enumerate(collision):
        file = f"{name}_collision_{i:03d}.obj"
        mesh.export(folder / file)
        ET.SubElement(ET.SubElement(ET.SubElement(link, "collision"), "geometry"), "mesh", filename=file)
    ET.indent(root)
    ET.ElementTree(root).write(folder / f"{name}.urdf", encoding="unicode", xml_declaration=True)
    return dict(collision_parts=len(collision), mass_kg=float(properties.mass), visual_finish=finish,
                all_parts_watertight=all(m.is_watertight for m in collision),
                all_parts_convex=all(m.is_convex for m in collision),
                mass_model="density-based additive parts; embedded-root overlap retained")


def clearance_samples(layout, spacing=None):
    spacing = spacing or .35 * layout.unit
    b = layout.template["hedgehog"]
    points, radii = [np.zeros((1, 3))], [np.array([b["core_radius"] * layout.unit])]
    for a, end in layout.spike_segments():
        n = int(np.ceil(np.linalg.norm(end-a)/spacing)) + 1
        points.append(np.linspace(a, end, n))
        # Cylinder radius plus half a sampling interval gives a conservative
        # continuous-distance lower bound, including the flat end caps.
        radii.append(np.full(n, b["spike_radius"]*layout.unit + spacing/2))
    return np.concatenate(points), np.concatenate(radii)


def pose_clearance(cage, points, radii, position, rotation):
    world = rotation.apply(points) + position
    _, distances, _ = trimesh.proximity.closest_point(cage, world)
    return float(np.min(distances-radii))


def choose_initial_pose(layout, cage):
    """Find a collision-free display pose; this is NOT an assembly path.

    Core is restricted to the hollow interior. Continuous spike centerlines
    connect it to every tip, so a cage crossing cannot hide between samples.
    """
    points, radii = clearance_samples(layout)
    rng = np.random.default_rng(17)
    position = np.array([0., 0., 0.])
    rotation = None
    trials = 0
    for candidate in Rotation.random(240, random_state=rng):
        trials += 1
        margin = pose_clearance(cage, points, radii, position, candidate)
        if margin > .4 * layout.unit:
            rotation = candidate
            break
    if rotation is None:
        raise ValueError("No nonintersecting initial pose found; review geometry")
    # Lower without stepping physics until the conservative envelope nearly
    # meets the cage. Gravity stability is deliberately not asserted.
    step = .25 * layout.unit
    for _ in range(160):
        candidate = position - [0, 0, step]
        margin = pose_clearance(cage, points, radii, candidate, rotation)
        if margin < .1 * layout.unit:
            break
        position = candidate
    margin = pose_clearance(cage, points, radii, position, rotation)
    q = rotation.as_quat()
    return dict(position_m=position.tolist(), quaternion_wxyz=q[[3,0,1,2]].tolist(),
                minimum_conservative_clearance_m=margin, orientation_trials=trials,
                seed=17, gravity_settled=False, assembly_route_verified=False,
                clearance_method="mesh distance to sphere + conservative sampled spike cylinders; half-spacing inflation")


def generate_assets(folder, scale=3., template_path=None, finish="metal"):
    folder = Path(folder).resolve()
    layout = HedgehogLayout(load_template(template_path), scale)
    cage, cage_parts = cage_meshes(layout)
    ball, ball_parts = hedgehog_meshes(layout)
    report = dict(template_id=layout.template["template_id"], scale=scale,
                  geometry_status=layout.template["geometry_status"],
                  cage=write_body(folder, "cage", cage, cage_parts, (.30,.36,.42,1), 2700, finish),
                  hedgehog=write_body(folder, "hedgehog", ball, ball_parts, (.80,.83,.86,1), 2700, finish),
                  initial_pose=choose_initial_pose(layout, trimesh.util.concatenate(cage_parts)),
                  reference_route_verified=False, physics_qualified=False)
    (folder / "template.json").write_text(json.dumps(layout.template, indent=2)+"\n")
    (folder / "asset_report.json").write_text(json.dumps(report, indent=2)+"\n")
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.suffix in (".obj", ".glb", ".urdf", ".json") and p.name != "sha256.json"}
    (folder / "sha256.json").write_text(json.dumps(files, indent=2)+"\n")
    return layout, report


"""Pure asset geometry retained from the previous task generation pipeline."""


from pathlib import Path

import numpy as np

from scipy.spatial import cKDTree

import trimesh

def union64(cells):
    import manifold3d as m
    from trimesh.iteration import reduce_cascade
    solids=[m.Manifold(m.Mesh64(vert_properties=np.asarray(c.vertices,dtype=np.float64),tri_verts=np.asarray(c.faces,dtype=np.uint64))) for c in cells]
    solid=reduce_cascade(lambda a,b:a+b,solids)
    if solid.status()!=m.Error.NoError:raise ValueError(f'Boolean failure: {solid.status()}')
    mesh=solid.to_mesh64()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties),faces=np.asarray(mesh.tri_verts),process=False)

class Sweep:
    def __init__(self, folder):
        self.folder=Path(folder)
        with np.load(self.folder/'sweep.npz') as data:
            self.radii=data['radii'].copy();self.points=[data[f'points_{i}'].copy() for i in range(len(self.radii))]
        self.trees=[cKDTree(p) for p in self.points]
    def distance(self, points):
        points=np.asarray(points);distance=np.full(len(points),np.inf)
        for tree,r in zip(self.trees,self.radii):distance=np.minimum(distance,tree.query(points,workers=4)[0]-r)
        return distance

def boxes_from_mask(mask, max_second=None):
    """Disjoint maximal rectangular blocks in a 3D occupancy grid."""
    remaining=mask.copy();blocks=[]
    for i,j,k in zip(*np.where(mask)):
        if not remaining[i,j,k]:continue
        endk=k+1
        while endk<mask.shape[2] and remaining[i,j,endk]:endk+=1
        endj=j+1
        while endj<mask.shape[1] and (max_second is None or endj-j<max_second) and remaining[i,endj,k:endk].all():endj+=1
        endi=i+1
        while endi<mask.shape[0] and remaining[endi,j:endj,k:endk].all():endi+=1
        remaining[i:endi,j:endj,k:endk]=False;blocks.append((i,endi,j,endj,k,endk))
    return blocks

def annular_cells(family, sweep):
    inner,outer=(.068,.078) if family=='helical_guide' else (.0585,.0675)
    rs=np.unique(np.r_[np.linspace(.033,inner,int(np.ceil((inner-.033)/.003))+1),np.linspace(inner,outer,5)])
    angles=np.linspace(-np.pi,np.pi,121);zs=np.linspace(-.12,.12,81)
    r=(rs[:-1]+rs[1:])/2;t=(angles[:-1]+angles[1:])/2;z=(zs[:-1]+zs[1:])/2
    R,T,Z=np.meshgrid(r,t,z,indexing='ij');centers=np.stack([R*np.cos(T),R*np.sin(T),Z],axis=-1)
    # Circumspheres cover each candidate convex annular voxel.
    radius=np.zeros(R.shape)
    for ir in (0,1):
        for it in (0,1):
            for iz in (0,1):
                rr,tt,zz=np.meshgrid(rs[ir:len(rs)-1+ir],angles[it:len(angles)-1+it],zs[iz:len(zs)-1+iz],indexing='ij')
                v=np.stack([rr*np.cos(tt),rr*np.sin(tt),zz],axis=-1)
                radius=np.maximum(radius,np.linalg.norm(v-centers,axis=-1))
    rims=np.abs(Z)>=.09
    twist=(Z/.09)*np.deg2rad(52) if family=='helical_guide' else np.zeros_like(Z)
    window_centers=np.deg2rad(np.arange(5)*72)
    open_region=np.zeros(R.shape,dtype=bool)
    for i,center in enumerate(window_centers):
        offset=twist
        if family=='oblique_gate' and i==0:offset=(Z/.09)*np.deg2rad(14)
        delta=(T-center-offset+np.pi)%(2*np.pi)-np.pi
        half=np.deg2rad(23 if i else 20)
        open_region|=abs(delta)<half
    stock=rims | ((R>inner)&~open_region)
    # Whole convex cells stay outside the positive sweep, with its built-in margin.
    ids=np.flatnonzero(stock);safe=np.zeros(stock.size,dtype=bool)
    gap=sweep.distance(centers.reshape(-1,3)[ids])-radius.ravel()[ids]
    safe[ids]=gap>0
    mask=safe.reshape(stock.shape)
    cells=[]
    for i,ii,j,jj,k,kk in boxes_from_mask(mask,max_second=3):
        vertices=[[rr*np.cos(tt),rr*np.sin(tt),zz] for rr in (rs[i],rs[ii]) for tt in (angles[j],angles[jj]) for zz in (zs[k],zs[kk])]
        cells.append(trimesh.convex.convex_hull(np.array(vertices)))
    return cells,dict(stock_voxels=int(stock.sum()),safe_voxels=int(mask.sum()),merged_cells=len(cells),outer_radius_m=outer)

def rectangular_gate_cells(sweep):
    xs=np.linspace(-.006,.226,117);ys=np.linspace(-.090,.090,91);zs=np.linspace(-.12,.17,146)
    x,y,z=[(a[:-1]+a[1:])/2 for a in (xs,ys,zs)]
    X,Y,Z=np.meshgrid(x,y,z,indexing='ij');centers=np.stack([X,Y,Z],axis=-1)
    gate=(X>=.214)
    rails=(abs(abs(Y)-.064)<.004)&(abs(abs(Z)-.105)<.004)
    stock=gate|rails
    radius=np.sqrt(np.diff(xs)[:,None,None]**2+np.diff(ys)[None,:,None]**2+np.diff(zs)[None,None,:]**2)/2
    ids=np.flatnonzero(stock);safe=np.zeros(stock.size,dtype=bool)
    safe[ids]=sweep.distance(centers.reshape(-1,3)[ids])-radius.ravel()[ids]>0
    cells=[]
    for i,ii,j,jj,k,kk in boxes_from_mask(safe.reshape(stock.shape)):
        lo=np.array([xs[i],ys[j],zs[k]]);hi=np.array([xs[ii],ys[jj],zs[kk]])
        cells.append(trimesh.creation.box(extents=hi-lo,transform=trimesh.transformations.translation_matrix((hi+lo)/2)))
    return cells,dict(stock_voxels=int(stock.sum()),safe_voxels=int(safe.sum()),merged_cells=len(cells))
