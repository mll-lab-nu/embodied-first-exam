from __future__ import annotations

"""An isometric sheet folded about separated, nonparallel material creases.

Every face stays within one rigid panel. No squeezed mesh, disconnected layers,
or coordinate noise is used to manufacture crumpling. Gravity supplies the final
wrinkles after the visual supports have been constructed in this open geometry.
"""
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class BlanketLayout:
    length_m: float = .60
    width_m: float = .48
    mesh_spacing_m: float = .012
    particle_size_m: float = .008
    birth_gap_particle_ratio: float = 4.
    fold_count: int = 5
    fold_angle_deg: float = 105.
    fold_angle_jitter_deg: float = 10.
    crease_slant: float = .10
    drop_clearance_m: float = .10
    tilt_deg: float = 40.
    yaw_deg: float = 18.
    seed: int = 0
    max_attempts: int = 64
    # Optional curled tail after the alternating pleats. Each hinge remains
    # developable; bending an already thick folded packet would stretch it.
    roll_fold_count: int = 0
    roll_angle_deg: float = 54.
    roll_angle_jitter_deg: float = 12.
    roll_direction: int = -1
    panel_width_jitter: float = .35
    pitch_deg: float = 0.

    def validate(self):
        for key, value in asdict(self).items():
            if not np.isfinite(value):
                raise ValueError(f"Nonfinite {key}")
        for name in ("seed", "fold_count", "max_attempts", "roll_fold_count", "roll_direction"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if self.seed < 0 or self.fold_count < 2 or self.max_attempts < 1:
            raise ValueError("Need a nonnegative seed, at least two folds and a sampling attempt")
        if min(self.length_m, self.width_m, self.mesh_spacing_m, self.particle_size_m,
               self.drop_clearance_m) <= 0 or self.birth_gap_particle_ratio < 3:
            raise ValueError("Dimensions must be positive; birth gap must be at least 3 particle sizes")
        if self.mesh_spacing_m > 2*self.particle_size_m:
            raise ValueError("Control mesh spacing must be at most 2 particle sizes")
        if not 0 <= self.crease_slant < .5 or self.fold_angle_jitter_deg < 0:
            raise ValueError("Invalid crease slant or angle jitter")
        if not 20 < self.fold_angle_deg-self.fold_angle_jitter_deg <= self.fold_angle_deg+self.fold_angle_jitter_deg < 165:
            raise ValueError("Keep open folds between 20 and 165 degrees")
        if self.roll_fold_count < 0 or self.roll_direction not in (-1, 1):
            raise ValueError("Invalid roll hinge count or direction")
        if not 0 <= self.panel_width_jitter < .75 or self.roll_angle_jitter_deg < 0:
            raise ValueError("Invalid roll sampling jitter")
        if not 0 < self.roll_angle_deg-self.roll_angle_jitter_deg <= self.roll_angle_deg+self.roll_angle_jitter_deg < 165:
            raise ValueError("Roll hinges must keep one direction and remain open")


def rotation(axis, angle):
    axis = np.asarray(axis, dtype=float)
    axis /= np.linalg.norm(axis)
    x, y, z = axis
    cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3)*np.cos(angle)+(1-np.cos(angle))*np.outer(axis, axis)+np.sin(angle)*cross


def _fold(uv, creases, angles):
    xyz = np.column_stack((uv, np.zeros(len(uv))))
    transform, translation = np.eye(3), np.zeros(3)
    for (intercept, slant), angle in zip(creases, angles):
        pivot = transform @ np.array([intercept, 0, 0])+translation
        axis = transform @ np.array([slant, 1., 0.])
        turn = rotation(axis, angle)
        downstream = uv[:, 0] >= intercept+slant*uv[:, 1]-1e-10
        xyz[downstream] = (xyz[downstream]-pivot) @ turn.T+pivot
        transform = turn @ transform
        translation = turn @ (translation-pivot)+pivot
    return xyz


def _mesh(layout, creases):
    """A conforming grid including every crease; returns material coordinates."""
    boundaries = np.vstack(([-layout.length_m/2, 0], creases, [layout.length_m/2, 0]))
    y = np.linspace(-layout.width_m/2, layout.width_m/2,
                    int(np.ceil(layout.width_m/layout.mesh_spacing_m))+1)
    rows, faces, panel_quads = [], [], []
    for i, (left, right) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        lo, hi = left[0]+left[1]*y, right[0]+right[1]*y
        if np.min(hi-lo) < 3*layout.particle_size_m:
            raise ValueError("Creases cross or leave a panel narrower than three particles")
        count = int(np.ceil(np.max(hi-lo)/layout.mesh_spacing_m))
        start = len(rows)-1 if i else 0
        for t in np.linspace(0, 1, count+1)[1 if i else 0:]:
            rows.append(np.column_stack((lo+(hi-lo)*t, y)))
        end = len(rows)-1
        panel_quads.append([start*len(y), end*len(y), (end+1)*len(y)-1, (start+1)*len(y)-1])
        for col in range(start, end):
            for row in range(len(y)-1):
                a = col*len(y)+row
                b = a+len(y)
                faces.extend(((a, b, b+1), (a, b+1, a+1)))
    return np.concatenate(rows), np.asarray(faces), np.asarray(panel_quads)


def panel_clearance(vertices, panel_quads):
    """Exact triangle-surface distance including edges, using FCL's BVHs.

    Adjacent panels share a crease, so their gap is necessarily zero. Their
    binding locality is checked against actual remeshed supports after build.
    """
    import trimesh
    panels = [trimesh.Trimesh(vertices[q], [[0, 1, 2], [0, 2, 3]], process=False)
              for q in panel_quads]
    minimum, closest = float("inf"), None
    for i, panel in enumerate(panels[:-2]):
        manager = trimesh.collision.CollisionManager()
        manager.add_object("panel", panel)
        for j in range(i+2, len(panels)):
            other = panels[j]
            gap = 0. if manager.in_collision_single(other) else float(manager.min_distance_single(other))
            if gap < minimum:
                minimum, closest = gap, [i, j]
    return minimum, closest


def generate(layout=BlanketLayout()):
    layout.validate()
    rng = np.random.default_rng(layout.seed)
    required = layout.particle_size_m*layout.birth_gap_particle_ratio
    for attempt in range(layout.max_attempts):
        count = layout.fold_count+layout.roll_fold_count
        if layout.roll_fold_count:
            widths = rng.uniform(1-layout.panel_width_jitter, 1+layout.panel_width_jitter, count+1)
            widths *= layout.length_m/widths.sum()
            intercepts = np.cumsum(widths)[:-1]-layout.length_m/2
        else:
            # Preserve the original variant's random sequence and exact geometry.
            pitch = layout.length_m/(layout.fold_count+1)
            intercepts = np.linspace(-layout.length_m/2, layout.length_m/2, layout.fold_count+2)[1:-1]
            intercepts += rng.uniform(-.10, .10, layout.fold_count)*pitch
        creases = np.column_stack((intercepts, rng.uniform(-layout.crease_slant, layout.crease_slant, count)))
        angles = np.radians(layout.fold_angle_deg+rng.uniform(-layout.fold_angle_jitter_deg,
                              layout.fold_angle_jitter_deg, layout.fold_count)) * (-1.)**np.arange(layout.fold_count)
        if layout.roll_fold_count:
            curl = rng.uniform(layout.roll_angle_deg-layout.roll_angle_jitter_deg,
                               layout.roll_angle_deg+layout.roll_angle_jitter_deg, layout.roll_fold_count)
            angles = np.r_[angles, layout.roll_direction*np.radians(curl)]
        try:
            uv, faces, panels = _mesh(layout, creases)
        except ValueError:
            continue
        vertices = _fold(uv, creases, angles)
        gap, pair = panel_clearance(vertices, panels)
        if gap < required:
            continue
        tilt = rotation([1, 0, 0], np.radians(layout.tilt_deg))
        pitch = rotation([0, 1, 0], np.radians(layout.pitch_deg))
        yaw = rotation([0, 0, 1], np.radians(layout.yaw_deg))
        vertices = vertices @ (yaw @ tilt @ pitch).T
        vertices[:, :2] -= (vertices[:, :2].min(axis=0)+vertices[:, :2].max(axis=0))/2
        vertices[:, 2] += layout.drop_clearance_m-vertices[:, 2].min()
        edges = np.unique(np.sort(np.concatenate((faces[:, :2], faces[:, 1:], faces[:, [2, 0]])), axis=1), axis=0)
        material_lengths = np.linalg.norm(uv[edges[:, 1]]-uv[edges[:, 0]], axis=1)
        ratios = np.linalg.norm(vertices[edges[:, 1]]-vertices[edges[:, 0]], axis=1)/material_lengths
        report = dict(layout=asdict(layout), accepted_attempt=attempt, creases=creases.tolist(),
                      fold_angles_deg=np.degrees(angles).tolist(), minimum_nonadjacent_panel_gap_m=gap,
                      closest_panels=pair, required_gap_m=required,
                      maximum_edge_metric_error=float(np.max(np.abs(ratios-1))),
                      material_area_m2=layout.length_m*layout.width_m,
                      alternating_fold_count=layout.fold_count, roll_hinge_count=layout.roll_fold_count,
                      roll_turn_deg=float(np.abs(np.degrees(angles[layout.fold_count:]).sum())),
                      minimum_birth_height_m=float(vertices[:, 2].min()),
                      maximum_birth_height_m=float(vertices[:, 2].max()),
                      mean_birth_height_m=float(vertices[:, 2].mean()),
                      vertices=len(vertices), faces=len(faces), pinned_particles=0)
        return vertices, faces, uv, panels, report
    raise ValueError(f"No collision-free birth with gap >= {required:g} m in {layout.max_attempts} attempts")


def material_coordinates(points, vertices, uv, panels):
    """Recover material coordinates geometrically, never assuming remesh order."""
    import trimesh
    indices = np.concatenate((panels[:, [0, 1, 2]], panels[:, [0, 2, 3]]))
    mesh = trimesh.Trimesh(vertices, indices, process=False)
    closest, distances, which = trimesh.proximity.closest_point_naive(mesh, np.asarray(points))
    bary = trimesh.triangles.points_to_barycentric(mesh.triangles[which], closest)
    return np.einsum("ni,nij->nj", bary, uv[indices[which]]), distances


def generate_flat_binding(layout):
    """Build material and its visual supports before controlled preparation.

    Cross-folding and torsion are subsequently produced by the PBD solver;
    their strained geometry must never become a new stress-free rest mesh.
    """
    layout.validate()
    uv, faces, panels = _mesh(layout, np.empty((0, 2)))
    vertices = np.column_stack((uv, np.full(len(uv), layout.drop_clearance_m)))
    report = dict(layout=asdict(layout), binding_reference='flat_material_before_preparation',
                  minimum_nonadjacent_panel_gap_m=None, closest_panels=None,
                  required_gap_m=None, maximum_edge_metric_error=0.,
                  material_area_m2=layout.length_m*layout.width_m,
                  minimum_birth_height_m=layout.drop_clearance_m,
                  maximum_birth_height_m=layout.drop_clearance_m,
                  vertices=len(vertices), faces=len(faces), pinned_particles=0)
    return vertices, faces, uv, panels, report


def write_obj(path, vertices, faces, uv, layout):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tex = (uv+[layout.length_m/2, layout.width_m/2])/[layout.length_m, layout.width_m]
    with path.open("w") as stream:
        stream.write("# One continuous blanket; material coordinates retained in UVs.\n")
        for p in vertices:
            stream.write("v %.10f %.10f %.10f\n" % tuple(p))
        for p in tex:
            stream.write("vt %.10f %.10f\n" % tuple(p))
        for face in faces+1:
            stream.write("f "+" ".join(f"{i}/{i}" for i in face)+"\n")


"""Continuous longitudinal pleats and whole-bundle torsion for a soft target.

The material width is integrated by arc length. Cross sections remain ordered
because their lateral tangent is positive. Torsion can still stretch material
along the length, so the actual mesh metric and PBD execution must be checked;
these targets never redefine the material rest shape.
"""
import numpy as np


def gathered_target(uv, length, width, gather, twist, cfg):
    fractions = np.asarray(cfg.panel_fractions, dtype=float)
    if (fractions <= 0).any() or not np.isclose(fractions.sum(), 1.):
        raise ValueError('Positive panel fractions must sum to one')
    if not 0 <= gather <= 1 or not 0 <= twist <= 1:
        raise ValueError('Preparation fractions must lie in [0, 1]')
    # A regular material grid makes the target independent of remeshing order.
    xs = np.linspace(-length/2, length/2, 121)
    ys = np.linspace(-width/2, width/2, 1201)
    creases = width*(np.cumsum(fractions)[:-1]-.5)
    half_band = float(cfg.crease_band_m)/2
    wave = np.ones_like(ys)
    for i, crease in enumerate(creases):
        t = np.clip((ys-crease+half_band)/(2*half_band), 0., 1.)
        t = t*t*(3-2*t)
        wave += 2*(-1.)**(i+1)*t
    s = xs/length+.5
    flare = np.exp(-(s/float(cfg.flare_fraction))**2)+np.exp(-((1-s)/float(cfg.flare_fraction))**2)
    amplitude = np.radians(float(cfg.pleat_angle_deg)-float(cfg.end_opening_deg)*flare)*gather
    phi = amplitude[:, None]*wave
    dy, dz = np.cos(phi), np.sin(phi)
    step = ys[1]-ys[0]
    lateral = np.c_[np.zeros(len(xs)), np.cumsum((dy[:, 1:]+dy[:, :-1])*(step/2), axis=1)]
    vertical = np.c_[np.zeros(len(xs)), np.cumsum((dz[:, 1:]+dz[:, :-1])*(step/2), axis=1)]
    lateral -= lateral.mean(axis=1, keepdims=True)
    vertical -= vertical.mean(axis=1, keepdims=True)
    # End sections rotate less rapidly; more of the turn occurs in the waist.
    phase = s*s*(3-2*s)-.5
    angle = np.radians(float(cfg.twist_angle_deg))*twist*phase
    y = np.cos(angle[:, None])*lateral-np.sin(angle[:, None])*vertical
    z = np.sin(angle[:, None])*lateral+np.cos(angle[:, None])*vertical
    y += float(cfg.centerline_sway_m)*gather*np.sin(2*np.pi*s)[:, None]
    scale = 1+(float(cfg.axial_scale)-1)*twist
    # Bilinear interpolation from the same material coordinates at every stage.
    from scipy.ndimage import map_coordinates
    coords = np.array([(uv[:, 0]/length+.5)*(len(xs)-1),
                       (uv[:, 1]/width+.5)*(len(ys)-1)])
    return np.column_stack((uv[:, 0]*scale,
        map_coordinates(y, coords, order=1, mode='nearest'),
        map_coordinates(z, coords, order=1, mode='nearest')))
