"""Open annular groove with one-sided, local retaining lips (SI units)."""
from __future__ import annotations

import numpy as np
import trimesh


def sector_mesh(inner, outer, z0, z1, start=0., stop=360., segments=128):
    """Watertight annular sector, with the exact same visible/contact surface."""
    closed = abs(stop - start - 360.) < 1e-6
    angles = np.radians(np.linspace(start, stop, segments, endpoint=not closed))
    vertices = np.array([[r*np.cos(a), r*np.sin(a), z]
                         for a in angles for z in (z0, z1) for r in (inner, outer)])
    faces = []
    for i in range(len(angles) if closed else len(angles)-1):
        a, b = 4*i, 4*((i+1) % len(angles))
        for quad in ((a,a+1,b+1,b), (a+2,b+2,b+3,a+3),
                     (a,b,b+2,a+2), (a+1,a+3,b+3,b+1)):
            faces.extend(((quad[0],quad[1],quad[2]),(quad[0],quad[2],quad[3])))
    if not closed:
        for quad in ((0,2,3,1), (4*(len(angles)-1),4*(len(angles)-1)+1,
                                4*(len(angles)-1)+3,4*(len(angles)-1)+2)):
            faces.extend(((quad[0],quad[1],quad[2]),(quad[0],quad[2],quad[3])))
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    mesh.fix_normals()
    if not mesh.is_watertight or mesh.volume <= 0:
        raise ValueError('Fixture must be a watertight positive-volume solid')
    return mesh


def validate_geometry(cfg):
    n = int(cfg.lip_count)
    if n not in (1, 2, 3):
        raise ValueError('lip_count must be 1, 2 or 3')
    if not 0 < float(cfg.lip_arc_deg) <= 90:
        raise ValueError('This demo requires short local lips (0 < arc <= 90 degrees)')
    r = float(cfg.tube_radius)
    gap = float(cfg.lip_opening)
    barrier = float(cfg.rope.fem.contact_d_hat)
    width = float(cfg.groove_outer-cfg.groove_inner)
    if not 2*r + 2*barrier < gap < width:
        raise ValueError('The one-sided opening must admit the tube plus contact margin')
    if cfg.wall_z - cfg.floor_z < 2*r + 2*barrier:
        raise ValueError('Not enough space under the lip')
    if not cfg.groove_inner+r+barrier < cfg.radius < cfg.groove_outer-r-barrier:
        raise ValueError('Rest ring does not fit inside the groove')
    angles = np.radians(np.asarray(cfg.lip_angles_deg[:n]))
    for i in range(n):
        if str(cfg.lip_sides[i]) not in ('inner', 'outer'):
            raise ValueError('lip_sides must be inner or outer')
        for j in range(i):
            distance = abs(np.degrees(np.angle(np.exp(1j*(angles[i]-angles[j])))))
            if distance <= cfg.lip_arc_deg:
                raise ValueError('Lips must be separate local arcs')
    return dict(lip_count=n, ordinary_groove_width_mm=1000*width,
                local_opening_mm=1000*gap, tube_diameter_mm=2000*r,
                under_lip_height_mm=1000*(cfg.wall_z-cfg.floor_z),
                arc_per_lip_deg=float(cfg.lip_arc_deg),
                total_covered_fraction=n*float(cfg.lip_arc_deg)/360.,
                fixed_bridge=False)


def lip_bounds(cfg, index):
    if str(cfg.lip_sides[index]) == 'outer':
        return float(cfg.groove_inner+cfg.lip_opening), float(cfg.groove_outer+.012)
    return float(cfg.groove_inner-.012), float(cfg.groove_outer-cfg.lip_opening)


def clearance_radius(cfg, index):
    inner, outer = lip_bounds(cfg, index)
    margin = cfg.tube_radius + 2*cfg.rope.fem.contact_d_hat
    return inner-margin if str(cfg.lip_sides[index]) == 'outer' else outer+margin


def seat_report(points, cfg):
    """Whole material surface must lie inside the cavity after all drivers release."""
    points = np.asarray(points)
    radial = np.linalg.norm(points[:, :2]-np.asarray(cfg.center), axis=1)
    tolerance = 0.001
    inside = ((radial >= cfg.groove_inner-tolerance) &
              (radial <= cfg.groove_outer+tolerance) &
              (points[:,2] >= cfg.floor_z-tolerance) &
              (points[:,2] <= cfg.wall_z+tolerance))
    azimuth = np.arctan2(points[:,1]-cfg.center[1], points[:,0]-cfg.center[0])
    lips = []
    for i in range(int(cfg.lip_count)):
        angle = np.radians(cfg.lip_angles_deg[i])
        selected = np.abs(np.angle(np.exp(1j*(azimuth-angle)))) < np.radians(cfg.lip_arc_deg/2)
        lo, hi = lip_bounds(cfg, i)
        under = selected & (radial>=lo) & (radial<=hi)
        lips.append(dict(index=i+1, material_nodes=int(selected.sum()),
                         nodes_under_overhang=int(under.sum()),
                         below_lip=bool(selected.any() and np.all(points[selected,2]<cfg.wall_z+tolerance))))
    return dict(all_nodes_in_groove=bool(inside.all()), seated_fraction=float(inside.mean()),
                radial_range_mm=(1000*np.array([radial.min(),radial.max()])).tolist(),
                height_range_mm=(1000*np.array([points[:,2].min(),points[:,2].max()])).tolist(),
                lips=lips, success=bool(inside.all() and all(l['below_lip'] and l['nodes_under_overhang'] for l in lips)))


def inside_fixture(points, cfg, tolerance=0.00015):
    """Point-in-solid check against the designed annuli and local lip sectors.

    Intended for densely sampled tool envelopes, not an exact mesh CCD claim.
    """
    p=np.asarray(points)
    radius=np.linalg.norm(p[:,:2]-np.asarray(cfg.center),axis=1)
    z=p[:,2]
    def annulus(lo,hi,bottom,top):
        return ((radius>lo+tolerance)&(radius<hi-tolerance)&
                (z>bottom+tolerance)&(z<top-tolerance))
    base_inner=float(cfg.get('base_inner',.074))
    base_outer=float(cfg.get('base_outer',.137))
    base_bottom=float(cfg.get('base_bottom',.009))
    inside=annulus(base_inner,base_outer,base_bottom,cfg.floor_z)
    inside|=annulus(base_inner,cfg.groove_inner,cfg.floor_z,cfg.wall_z)
    inside|=annulus(cfg.groove_outer,base_outer,cfg.floor_z,cfg.wall_z)
    angle=np.arctan2(p[:,1]-cfg.center[1],p[:,0]-cfg.center[0])
    for i in range(int(cfg.lip_count)):
        lo,hi=lip_bounds(cfg,i)
        delta=np.abs(np.angle(np.exp(1j*(angle-np.radians(cfg.lip_angles_deg[i])))))
        inside|=annulus(lo,hi,cfg.wall_z,cfg.lip_top_z)&(delta<np.radians(cfg.lip_arc_deg/2)-tolerance/.107)
    return inside
