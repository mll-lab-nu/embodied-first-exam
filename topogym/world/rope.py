"""Shared PBD elastic-tube rope prefab (module A).

The rope pipeline battle-tested on Untangle — parallel-transport tube meshing,
PBD solver options, and the ``PBD.Elastic`` material — lives here so every rope
task (untangle, cable_routing, future ones) builds ropes the same way instead
of importing across task modules or copy-pasting the constructor blocks.

Parameter single-source: the canonical physics values live in
``configs/prefab_configs/topogym_prefabs_v1.yaml`` (``prefabs.rope_pbd``); task
configs reference them per field via ``${prefabs.rope_pbd.*}`` and keep only
task-local fields (mesh resolution, layout, anchoring) explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np


@dataclass(frozen=True)
class RopeMesh:
    path: Path
    centerline: np.ndarray
    vertices: np.ndarray
    faces: np.ndarray
    endpoint_centers: tuple[np.ndarray, np.ndarray]


@dataclass(frozen=True)
class RopeEndpointHandle:
    name: str
    entity: Any
    start_center: np.ndarray
    end_center: np.ndarray
    start_indices: tuple[int, ...]
    end_indices: tuple[int, ...]
    start_pin: Any | None = None
    end_pin: Any | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_mesh_dir(path_like) -> Path:
    path = Path(str(path_like))
    if not path.is_absolute():
        path = _repo_root() / path
    return path


def safe_asset_name(name: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in str(name))


def tensor_to_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.asarray(value)


def sample_polyline(points: np.ndarray, *, max_segment_length: float) -> np.ndarray:
    if len(points) < 2:
        raise ValueError("A rope strand needs at least two control points.")
    if max_segment_length <= 0.0:
        raise ValueError("rope.mesh.segment_length must be positive.")

    sampled = [np.asarray(points[0], dtype=float)]
    for start, end in zip(points, points[1:]):
        start = np.asarray(start, dtype=float)
        end = np.asarray(end, dtype=float)
        length = float(np.linalg.norm(end - start))
        if length <= 1e-8:
            continue
        steps = max(1, int(ceil(length / max_segment_length)))
        for step in range(1, steps + 1):
            alpha = step / steps
            sampled.append((1.0 - alpha) * start + alpha * end)
    if len(sampled) < 2:
        raise ValueError("A rope strand collapsed to fewer than two sampled points.")
    return np.stack(sampled, axis=0)


def catmull_rom_centerline(
    control_points: np.ndarray,
    *,
    max_segment_length: float,
    alpha: float = 0.5,
) -> np.ndarray:
    """Smooth centerline through ``control_points`` via a centripetal Catmull-Rom
    spline, resampled at ~``max_segment_length`` arc-length spacing.

    Rounds the hard corners of a hand-authored waypoint polyline (each corner is
    a curvature discontinuity that renders as a facet) while passing through the
    original control points, so a validated route's shape/clearances are kept.
    The endpoints get a reflected phantom control point so the spline starts/ends
    at the true endpoints. ``alpha=0.5`` (centripetal) avoids cusps/self-overlap.
    """

    pts = np.asarray(control_points, dtype=float)
    if len(pts) < 2:
        raise ValueError("catmull_rom_centerline needs >= 2 control points.")
    if len(pts) == 2:
        return sample_polyline(pts, max_segment_length=max_segment_length)

    ext = np.vstack([pts[0] + (pts[0] - pts[1]), pts, pts[-1] + (pts[-1] - pts[-2])])
    out: list[np.ndarray] = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]

        def _tj(ti: float, a: np.ndarray, b: np.ndarray) -> float:
            d = float(np.linalg.norm(b - a))
            return ti + (d ** alpha if d > 1e-9 else 1e-9)

        t0 = 0.0
        t1 = _tj(t0, p0, p1)
        t2 = _tj(t1, p1, p2)
        t3 = _tj(t2, p2, p3)
        seg_len = float(np.linalg.norm(p2 - p1))
        n = max(2, int(ceil(seg_len / max_segment_length)))
        for t in np.linspace(t1, t2, n, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out.append(pts[-1])
    return np.stack(out, axis=0)


def reserve_endpoint_footprint(
    polyline: np.ndarray, reach: float, *, ends: tuple[str, ...] = ("start", "end")
) -> np.ndarray:
    """Drop interior points within ``reach`` arc-length of the named ends, keeping
    the two true endpoints.

    ``with_end_entries`` displaces each endpoint by a fixed reach and inserts a
    U-turn+landing; on a dense (splined) polyline the untouched neighbours within
    that reach collide with the landing and self-intersect the swept tube. Clearing
    the footprint restores the sparse-endpoint condition the entries assume.

    ``ends`` must name exactly the ends that will get an entry. Clearing an end
    that is never refilled leaves the rope with a ``reach``-long chord where the
    body is dense -- for the flat plug pose that was the last 28mm, resampled at
    4.7mm against a 3.5mm body, right where the gripper closes.
    """

    selected = tuple(str(end) for end in ends)
    unknown = [end for end in selected if end not in ("start", "end")]
    if unknown:
        raise ValueError(f"reserve_endpoint_footprint: unknown ends {unknown}.")

    pts = np.asarray(polyline, dtype=float)
    if len(pts) < 3 or not selected:
        return pts
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(s[-1])
    keep = np.ones(len(pts), dtype=bool)
    if "start" in selected:
        keep &= s > reach
    if "end" in selected:
        keep &= s < total - reach
    keep[0] = keep[-1] = True
    out = pts[keep]
    if len(out) < 3:
        return pts
    return out


def parallel_transport_frames(
    centerline: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-sample (tangent, normal, binormal) frames along a centerline.

    Tangents are central differences at interior samples. The normal is
    parallel-transported (minimal rotation between successive tangents), i.e. a
    Bishop frame: zero twist about the tangent by construction -- the property
    both the tube skin and the FEM straight-rest mapping rely on.
    """

    if len(centerline) < 2:
        raise ValueError("parallel_transport_frames needs >= 2 centerline points.")

    def _unit(vec: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vec))
        if norm <= 1e-12:
            raise ValueError("Degenerate rope centerline segment.")
        return vec / norm

    tangents = []
    for index in range(len(centerline)):
        if index == 0:
            tangent = centerline[1] - centerline[0]
        elif index == len(centerline) - 1:
            tangent = centerline[-1] - centerline[-2]
        else:
            tangent = centerline[index + 1] - centerline[index - 1]
        tangents.append(_unit(np.asarray(tangent, dtype=float)))

    normal = np.cross(np.array([0.0, 0.0, 1.0]), tangents[0])
    if float(np.linalg.norm(normal)) <= 1e-8:
        normal = np.cross(np.array([1.0, 0.0, 0.0]), tangents[0])
    normal = _unit(normal)

    normals = []
    binormals = []
    for index in range(len(centerline)):
        if index > 0:
            axis = np.cross(tangents[index - 1], tangents[index])
            sin_angle = float(np.linalg.norm(axis))
            if sin_angle > 1e-12:
                cos_angle = float(
                    np.clip(np.dot(tangents[index - 1], tangents[index]), -1.0, 1.0)
                )
                axis = axis / sin_angle
                angle = float(np.arctan2(sin_angle, cos_angle))
                normal = (
                    normal * np.cos(angle)
                    + np.cross(axis, normal) * np.sin(angle)
                    + axis * float(np.dot(axis, normal)) * (1.0 - np.cos(angle))
                )
            # Re-orthogonalize against drift so rings stay perpendicular to the tube.
            normal = _unit(
                normal - float(np.dot(normal, tangents[index])) * tangents[index]
            )
        normals.append(normal)
        binormals.append(np.cross(tangents[index], normal))
    return (
        np.asarray(tangents, dtype=float),
        np.asarray(normals, dtype=float),
        np.asarray(binormals, dtype=float),
    )


def tube_material_coords(vertices: np.ndarray, centerline: np.ndarray) -> np.ndarray:
    """Material coordinates of tube vertices: ``(arc_length, n_offset, b_offset)``.

    Every vertex (surface rings AND tetgen's interior Steiner points) is
    projected onto the centerline polyline, giving its arc length ``s`` plus its
    cross-section offsets in the same parallel-transported (Bishop) frames the
    skin was built with. Two consumers:

    - the FEM straight-rest mapping (`genesis_ipc_vertex_constraints`), which
      lays these out along +x to get a stress-free straight tube;
    - rope-state supervision, which bins nodes by ``s`` to recover an ordered
      centerline from an unordered tet mesh (tetgen does not preserve order).

    ``vertices`` must be the SPAWN positions -- the ones the centerline
    describes.

    The arc length carries the vertex's TANGENTIAL residual, not just its
    foot point's arc length. Without it the map collapses at sharp centerline
    corners (the connector exit arcs): every vertex in the wedge around a
    corner projects onto the same point, so they would all be handed the same
    arc length, flattening that wedge to zero thickness and inverting the tets
    inside it. libuipc rejects the rest mesh outright when that happens
    ("determinant of the tetrahedron is non-positive"). For a foot strictly
    inside a segment the residual is zero by construction, so this changes
    nothing away from corners.
    """

    pts = np.asarray(centerline, dtype=float)
    verts = np.asarray(vertices, dtype=np.float64)
    if len(pts) < 2:
        raise ValueError("tube_material_coords needs >= 2 centerline points.")
    seg = np.diff(pts, axis=0)
    seg_len = np.linalg.norm(seg, axis=1)
    s_acc = np.concatenate([[0.0], np.cumsum(seg_len)])
    tangents, normals, binormals = parallel_transport_frames(pts)
    del binormals  # rebuilt per vertex from the interpolated frame below

    # Point-to-segment projection against every segment, keeping the closest.
    # Chunked because the intermediates are (chunk x n_seg x 3): a production
    # rope is ~1e4-1e5 tet nodes against ~1e2 segments, which is gigabytes in
    # one shot and a few MB per chunk.
    out = np.empty((len(verts), 3), dtype=float)
    for start in range(0, len(verts), 4096):
        block = verts[start : start + 4096]
        diff = block[:, None, :] - pts[None, :-1, :]
        t = np.einsum("vsk,sk->vs", diff, seg) / np.maximum(seg_len**2, 1e-18)[None, :]
        t = np.clip(t, 0.0, 1.0)
        foot = pts[None, :-1, :] + t[:, :, None] * seg[None, :, :]
        dist2 = np.sum((block[:, None, :] - foot) ** 2, axis=2)
        j = np.argmin(dist2, axis=1)
        rows = np.arange(len(block))
        t_best = t[rows, j]
        foot_best = foot[rows, j]
        # Frames interpolated between the segment's end samples (they vary slowly).
        tangent = tangents[j] * (1.0 - t_best)[:, None] + tangents[j + 1] * t_best[:, None]
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-12)
        normal = normals[j] * (1.0 - t_best)[:, None] + normals[j + 1] * t_best[:, None]
        normal -= tangent * np.einsum("vk,vk->v", normal, tangent)[:, None]
        normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
        binormal = np.cross(tangent, normal)
        rel = block - foot_best
        out[start : start + len(block), 0] = (
            s_acc[j] + t_best * seg_len[j] + np.einsum("vk,vk->v", rel, tangent)
        )
        out[start : start + len(block), 1] = np.einsum("vk,vk->v", rel, normal)
        out[start : start + len(block), 2] = np.einsum("vk,vk->v", rel, binormal)
    return out


def make_elastic_tube_mesh(
    centerline: np.ndarray,
    *,
    radius: float,
    radial_segments: int,
) -> tuple[np.ndarray, np.ndarray]:
    if radius <= 0.0:
        raise ValueError("rope.radius must be positive.")
    if radial_segments < 4:
        raise ValueError("rope.mesh.radial_segments must be at least 4.")
    if len(centerline) < 2:
        raise ValueError("A tube mesh needs at least two centerline points.")

    # Ring frames are parallel-transported along the centerline so the tube stays
    # valid on vertical runs (connector top exit); a fixed world-z binormal would
    # fold the rings flat on vertical segments and self-intersect the mesh. For
    # flat board-level ropes this frame reduces to the pre-parallel-transport one.
    _tangents, normals, binormals = parallel_transport_frames(centerline)

    vertices = []
    for index, point in enumerate(centerline):
        normal = normals[index]
        binormal = binormals[index]
        for ring_index in range(radial_segments):
            theta = 2.0 * np.pi * ring_index / radial_segments
            offset = radius * (np.cos(theta) * normal + np.sin(theta) * binormal)
            vertices.append(point + offset)

    faces = []
    for index in range(len(centerline) - 1):
        ring_0 = index * radial_segments
        ring_1 = (index + 1) * radial_segments
        for ring_index in range(radial_segments):
            next_ring_index = (ring_index + 1) % radial_segments
            faces.append([ring_0 + ring_index, ring_0 + next_ring_index, ring_1 + ring_index])
            faces.append([ring_0 + next_ring_index, ring_1 + next_ring_index, ring_1 + ring_index])

    start_center = len(vertices)
    vertices.append(centerline[0])
    end_center = len(vertices)
    vertices.append(centerline[-1])
    end_ring = (len(centerline) - 1) * radial_segments
    for ring_index in range(radial_segments):
        next_ring_index = (ring_index + 1) % radial_segments
        faces.append([start_center, next_ring_index, ring_index])
        faces.append([end_center, end_ring + ring_index, end_ring + next_ring_index])

    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=int)


def self_contact_clearance(radius: float, radial_segments: int, ring_spacing: float) -> float:
    """Closest distance between two of the tube's own non-adjacent surface primitives.

    IPC's barrier only skips primitive pairs that share a vertex, so this is the
    separation the contact distance has to stay under. Two directions compete:
    around the section, a vertex against the edge two steps away; along the tube,
    a ring against the ring two away. The circumferential term shrinks with
    ``radial_segments`` (4mm tube: 3.06mm at 8, 2.07mm at 12, 1.25mm at 20).
    """

    theta = np.pi / float(radial_segments)
    # Vertex at angle 0 against the chord spanning [theta*2, theta*4], the
    # nearest edge it shares no vertex with.
    vertex = np.array([radius, 0.0])
    start = radius * np.array([np.cos(2.0 * theta), np.sin(2.0 * theta)])
    end = radius * np.array([np.cos(4.0 * theta), np.sin(4.0 * theta)])
    edge = end - start
    t = float(np.clip(np.dot(vertex - start, edge) / np.dot(edge, edge), 0.0, 1.0))
    circumferential = float(np.linalg.norm(vertex - (start + t * edge)))
    return min(circumferential, 2.0 * float(ring_spacing))


def check_self_contact_clearance(
    *, radius: float, radial_segments: int, ring_spacing: float, contact_d_hat: float
) -> None:
    """Reject a contact distance that reaches the tube's own surface.

    A barrier that spans the rope's own skin pushes every non-adjacent pair of
    its surface primitives apart, for the whole episode. Measured on rope_winding
    (2026-08-20): the rope ripples along its full length, shortens toward the
    centre of its spawn arc (a near-incompressible section cannot widen without
    it), and accumulates twist that turns into a telephone-cord coil -- 2.67
    turns with the barrier violated, 0.17 with it clear.

    Past the clearance the barrier is unambiguously inside the skin and this
    raises. Between 75% and 100% there is no margin left for deformation to eat,
    which is where cable_routing's 12-segment section at 2mm sits; that prints
    the same arithmetic and keeps going, because no run has measured it.
    """

    clearance = self_contact_clearance(radius, radial_segments, ring_spacing)
    detail = (
        f"rope.fem.contact_d_hat={float(contact_d_hat):.4f} m against a self-surface "
        f"clearance of {clearance:.4f} m (radius {radius:.4f} m, {radial_segments} radial "
        f"segments, {ring_spacing:.4f} m rings). Lower contact_d_hat below "
        f"{0.75 * clearance:.4f} m, or coarsen the skin."
    )
    if float(contact_d_hat) >= clearance:
        raise SystemExit(f"The IPC barrier spans the rope's own surface: {detail}")
    if float(contact_d_hat) > 0.75 * clearance:
        print(f"rope self-contact clearance has no margin left: {detail}", flush=True)


def write_obj(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Generated by topogym.world.rope; do not edit by hand."]
    for vertex in vertices:
        lines.append(f"v {vertex[0]:.8f} {vertex[1]:.8f} {vertex[2]:.8f}")
    for face in faces:
        lines.append(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def endpoint_particle_indices(rope_entity, endpoint_centers, *, radius: float) -> list[int]:
    particles = tensor_to_numpy(rope_entity.get_particles_pos())
    if particles.ndim == 3:
        particles = particles[0]
    indices: set[int] = set()
    for center in endpoint_centers:
        dist = np.linalg.norm(particles - np.asarray(center, dtype=float), axis=1)
        near = np.flatnonzero(dist <= radius)
        if len(near) == 0:
            near = np.array([int(np.argmin(dist))], dtype=int)
        indices.update(int(index) for index in near)
    return sorted(indices)


class TabletopParticleFriction:
    """Coulomb friction between PBD particles and a horizontal surface.

    Genesis does not provide this. Its deformable-vs-rigid friction
    (``legacy_coupler._func_collide_in_rigid_geom``) scales the tangential
    reduction by the *normal velocity* and only runs while a particle is moving
    into the surface, so a rope already resting on a table gets essentially no
    friction no matter how high ``coup_friction`` is set. ``PBD.Elastic`` has no
    damping term either (its ``*_relaxation`` fields are constraint relaxation).
    The result is that nothing stops a disturbed rope: it slides and swings
    indefinitely. See ``docs/develop/physics/pbd_tabletop_friction_zh.md``.

    This supplies the missing dissipation with the textbook model instead: a
    particle held against the surface feels ``N = m*g``, so it decelerates at
    ``mu * g`` regardless of how fast it is going.

    **Velocity only, never position.** A PBD substep ends with
    ``vel = (pos - ipos) / dt``, so any externally written position jump is
    reconstructed as a huge velocity -- that is the mechanism behind this repo's
    ropes getting flung to the solver domain corner. Writing velocity is safe: it
    just seeds the next substep's prediction, which is exactly where a friction
    impulse belongs.

    Segments lifted clear of the surface fall outside ``contact_band`` and are
    left completely alone, so a rope being carried by the gripper is unaffected
    without needing to know which rope that is.

    **`min_height` adds the NORMAL half of the same gap, and it is off by
    default.** Genesis' PBD-vs-rigid contact is not a penetration barrier -- it
    is resolved at the velocity level while a particle moves into the surface,
    with no real normal force (`docs/develop/physics/pbd_tabletop_friction_zh.md`
    section 6). Material held down by something else therefore sinks and stays
    sunk. Measured 2026-08-24 on `cloth_unroll`: dragging the band by a
    kinematically attached patch put particles 1.7 mm BELOW the table top, 3.7 mm
    under where a resting particle centre belongs, which is 92% of a particle
    diameter -- and since Genesis renders a PBD cloth at its particle centres,
    with no thickness, the cloth visibly disappeared into the table.

    Set `min_height` to where a resting particle CENTRE belongs (one particle
    radius above the surface) and anything below it is given a separation
    velocity. Still velocity only, so the position-write hazard above does not
    apply. Left at None everywhere it has not been measured: turning it on
    changes contact behaviour, and every other task's thresholds were calibrated
    without it.
    """

    #: Fraction of the penetration depth recovered per step. Half rather than
    #: all: a single-step snap back is the position-write failure mode wearing a
    #: velocity disguise, and PBD reconstructs `vel = (pos - ipos) / dt` anyway.
    LIFT_GAIN = 0.5
    #: Ceiling on the separation speed, m/s. A deeply buried particle climbs out
    #: over several steps instead of being launched. 0.1 m/s is 1 mm per step at
    #: dt=0.01 -- two orders below the `disp_limit` the divergence watch trips on.
    MAX_LIFT_SPEED = 0.1

    def __init__(
        self,
        scene: Any,
        entities,
        *,
        surface_z: float,
        contact_band: float,
        static_mu: float,
        kinetic_mu: float,
        dt: float,
        gravity: float,
        max_load_factor: float = 3.0,
        min_height: float | None = None,
    ) -> None:
        self.scene = scene
        self.entities = list(entities)
        self.surface_z = float(surface_z)
        self.contact_band = float(contact_band)
        self.static_mu = float(static_mu)
        self.kinetic_mu = float(kinetic_mu)
        self.dt = float(dt)
        self.gravity = abs(float(gravity))
        self.max_load_factor = float(max_load_factor)
        self.min_height = None if min_height is None else float(min_height)
        self._orig_step = None

    def apply(self) -> None:
        """Apply one step's worth of friction to whatever is touching the surface."""

        for entity in self.entities:
            positions = tensor_to_numpy(entity.get_particles_pos())
            if positions.ndim == 3:
                positions = positions[0]
            contact = np.flatnonzero(
                positions[:, 2] <= self.surface_z + self.contact_band
            )
            if contact.size == 0:
                continue

            # The whole rope's weight presses through only the particles that
            # actually touch -- an octagonal cross-section rests on 2-3 of its 8
            # vertices. Charging each contact particle only its own m*g would
            # dilute the rope's deceleration by that ratio; this restores the
            # textbook mu*g for the rope as a whole.
            #
            # The cap matters and its direction is easy to get backwards. A rope
            # mostly held by the gripper has few contacts, so the raw ratio
            # *grows* -- but its weight is on the gripper, not the table, so the
            # normal load there is small. Capping near the geometric ratio of a
            # resting rope (~8/3) keeps a resting rope correct while stopping a
            # lifted one from being over-damped through its last few contacts.
            load_factor = min(
                float(len(positions)) / float(contact.size), self.max_load_factor
            )
            stop_speed = self.static_mu * self.gravity * self.dt * load_factor
            delta_v = self.kinetic_mu * self.gravity * self.dt * load_factor

            velocities = tensor_to_numpy(entity.get_particles_vel())
            if velocities.ndim == 3:
                velocities = velocities[0]
            velocities = np.array(velocities, dtype=float)

            planar = velocities[contact, :2]
            speed = np.linalg.norm(planar, axis=1)
            # Below the static threshold the particle stops dead rather than
            # reversing, which is what a naive `v -= delta` would do.
            moving = speed > stop_speed
            scale = np.zeros_like(speed)
            np.divide(
                np.maximum(speed - delta_v, 0.0),
                speed,
                out=scale,
                where=moving,
            )
            velocities[contact, :2] = planar * scale[:, None]
            entity.set_particles_vel(
                velocities[contact], particles_idx_local=contact.tolist()
            )

            # The normal half, when asked for. Separate from the tangential write
            # above because it selects a DIFFERENT set: `contact` is everything
            # near the surface, this is only what has gone under it.
            if self.min_height is None:
                continue
            floor = self.surface_z + self.min_height
            under = np.flatnonzero(positions[:, 2] < floor)
            if under.size == 0:
                continue
            lift = np.minimum(
                (floor - positions[under, 2]) / self.dt * self.LIFT_GAIN,
                self.MAX_LIFT_SPEED,
            )
            normal = np.array(velocities[under], dtype=float)
            normal[:, 2] = np.maximum(normal[:, 2], lift)
            entity.set_particles_vel(normal, particles_idx_local=under.tolist())

    def install(self) -> TabletopParticleFriction:
        """Wrap ``scene.step`` so friction is applied after every step."""

        if self._orig_step is not None:
            return self
        self._orig_step = self.scene.step

        def wrapped_step(*args, **kwargs):
            result = self._orig_step(*args, **kwargs)
            self.apply()
            return result

        self.scene.step = wrapped_step
        return self

    def uninstall(self) -> None:
        if self._orig_step is not None:
            self.scene.step = self._orig_step
            self._orig_step = None


def pbd_options(rope_cfg) -> gs.options.PBDOptions:
    """Scene-level PBD solver options from a task's ``rope:`` (or film) block."""

    return gs.options.PBDOptions(
        particle_size=float(rope_cfg.particle_size),
        max_stretch_solver_iterations=int(rope_cfg.pbd.max_stretch_solver_iterations),
        max_bending_solver_iterations=int(rope_cfg.pbd.max_bending_solver_iterations),
        max_volume_solver_iterations=int(rope_cfg.pbd.max_volume_solver_iterations),
    )


def elastic_material(rope_cfg) -> gs.materials.PBD.Elastic:
    """``PBD.Elastic`` material from a task's ``rope.elastic:`` block."""

    elastic = rope_cfg.elastic
    return gs.materials.PBD.Elastic(
        rho=float(elastic.rho),
        static_friction=float(elastic.static_friction),
        kinetic_friction=float(elastic.kinetic_friction),
        stretch_compliance=float(elastic.stretch_compliance),
        bending_compliance=float(elastic.bending_compliance),
        volume_compliance=float(elastic.volume_compliance),
        stretch_relaxation=float(elastic.stretch_relaxation),
        bending_relaxation=float(elastic.bending_relaxation),
        volume_relaxation=float(elastic.volume_relaxation),
    )


def tube_morph(path, rope_cfg) -> gs.morphs.Mesh:
    """Standard mesh morph for a generated rope tube OBJ."""

    return gs.morphs.Mesh(
        file=str(path),
        pos=(0.0, 0.0, 0.0),
        scale=1.0,
        decimate=False,
        convexify=False,
        fixed=False,
        maxvolume=float(rope_cfg.mesh.maxvolume),
        force_retet=True,
        file_meshes_are_zup=True,
    )


def unit_xy(vec: np.ndarray) -> np.ndarray:
    xy = np.asarray(vec[:2], dtype=float)
    norm = float(np.linalg.norm(xy))
    if norm <= 1e-8:
        return np.array([1.0, 0.0], dtype=float)
    return xy / norm


def revolve_profile(profile, radial_segments: int) -> tuple[np.ndarray, np.ndarray]:
    """Surface-of-revolution mesh from a ``(z, r)`` profile revolved around the local z-axis.

    ``r > 0`` -> a ring of ``radial_segments`` vertices; ``r == 0`` -> a single axis point.
    Consecutive same-``z`` points give a flat annulus (used for the flange steps). The open
    first/last rings are capped. Returns ``(vertices, faces)`` (faces 0-indexed).
    """

    profile = [(float(z), float(r)) for z, r in profile]
    if len(profile) < 2:
        raise ValueError("connector profile needs >= 2 (z, r) points.")
    vertices: list[list[float]] = []
    rings: list[tuple[int, int]] = []  # (start_index, count); count==1 for an axis apex
    for z, r in profile:
        if r <= 1e-9:
            rings.append((len(vertices), 1))
            vertices.append([0.0, 0.0, z])
        else:
            rings.append((len(vertices), int(radial_segments)))
            for k in range(radial_segments):
                theta = 2.0 * np.pi * k / radial_segments
                vertices.append([r * np.cos(theta), r * np.sin(theta), z])

    faces: list[list[int]] = []
    for i in range(len(profile) - 1):
        (s0, c0), (s1, c1) = rings[i], rings[i + 1]
        if c0 == radial_segments and c1 == radial_segments:
            for k in range(radial_segments):
                nk = (k + 1) % radial_segments
                faces.append([s0 + k, s0 + nk, s1 + k])
                faces.append([s0 + nk, s1 + nk, s1 + k])
        elif c0 == 1 and c1 == radial_segments:
            for k in range(radial_segments):
                nk = (k + 1) % radial_segments
                faces.append([s0, s1 + k, s1 + nk])
        elif c0 == radial_segments and c1 == 1:
            for k in range(radial_segments):
                nk = (k + 1) % radial_segments
                faces.append([s1, s0 + nk, s0 + k])

    for (start, count), flip in ((rings[0], True), (rings[-1], False)):
        if count != radial_segments:
            continue
        center = len(vertices)
        vertices.append([0.0, 0.0, profile[0][0] if flip else profile[-1][0]])
        for k in range(radial_segments):
            nk = (k + 1) % radial_segments
            faces.append([center, start + k, start + nk] if flip else [center, start + nk, start + k])
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=int)


def connector_grasp_height(connector_cfg) -> float:
    """Height of the connector's local origin (grasp-column center) above the board top."""
    flange_height = float(getattr(connector_cfg, "flange_height", 0.005))
    column_height = float(getattr(connector_cfg, "column_height", 0.035))
    return flange_height + 0.5 * column_height


def connector_cap_top(connector_cfg) -> float:
    """Height of the connector's rounded cap apex above the board top."""
    flange_height = float(getattr(connector_cfg, "flange_height", 0.005))
    column_height = float(getattr(connector_cfg, "column_height", 0.035))
    # Mirrors the cap_height default in connector_mesh.
    return flange_height + column_height + 0.35 * column_height


def connector_mesh(
    *,
    pin_depth: float,
    pin_radius: float,
    flange_radius: float,
    flange_height: float,
    column_radius: float,
    column_height: float,
    grip_rings: int = 2,
    grip_depth: float = 0.0015,
    cap_height: float | None = None,
    radial_segments: int = 16,
) -> tuple[np.ndarray, np.ndarray]:
    """Plug connector as a solid of revolution (local origin at the grasp-column center).

    Profile bottom->top: a mesh-only pin below the board (into the hole/port), a flange
    sitting on the board (radius > hole), a grasp column with a couple of grip-ring grooves,
    and a rounded top. The local origin sits at the grasp-column center so entity poses,
    grasp targets, and socket-seat targets all reference the same point.
    """

    cap_height = 0.35 * column_height if cap_height is None else float(cap_height)
    col_base = flange_height
    col_top = flange_height + column_height
    ring_zs = [col_base + column_height * (j + 1) / (grip_rings + 1) for j in range(max(0, grip_rings))]
    groove = min(0.0025, column_height / (2 * (grip_rings + 1))) if grip_rings > 0 else 0.0

    profile: list[tuple[float, float]] = [
        (-pin_depth, 0.6 * pin_radius),
        (-0.4 * pin_depth, pin_radius),
        (0.0, pin_radius),
        (0.0, flange_radius),
        (flange_height, flange_radius),
        (flange_height, column_radius),
    ]
    column_zs = [col_base]
    for rz in ring_zs:
        column_zs += [rz - groove, rz, rz + groove]
    column_zs.append(col_top)
    for z in column_zs:
        radius = column_radius - grip_depth if any(abs(z - rz) < 1e-6 for rz in ring_zs) else column_radius
        profile.append((z, radius))
    n_cap = 4
    for j in range(1, n_cap + 1):
        frac = j / n_cap
        profile.append((col_top + cap_height * np.sin(0.5 * np.pi * frac), max(0.0, column_radius * np.cos(0.5 * np.pi * frac))))
    origin_z = flange_height + 0.5 * column_height
    profile = [(z - origin_z, r) for z, r in profile]
    return revolve_profile(profile, radial_segments)


def connector_obj_path(connector_cfg, *, default_output_dir) -> Path:
    """Generate (once per build) the shared plug-connector OBJ, returning its path.

    All endpoint connectors of a task share one geometry (positioned/colored per
    entity), so the mesh is written a single time under the rope mesh cache dir.
    """

    mesh_dir = resolve_mesh_dir(getattr(connector_cfg, "output_dir", default_output_dir))
    path = mesh_dir / "endpoint_connector.obj"
    vertices, faces = connector_mesh(
        pin_depth=float(getattr(connector_cfg, "pin_depth", 0.010)),
        pin_radius=float(getattr(connector_cfg, "pin_radius", 0.0055)),
        flange_radius=float(getattr(connector_cfg, "flange_radius", 0.011)),
        flange_height=float(getattr(connector_cfg, "flange_height", 0.005)),
        column_radius=float(getattr(connector_cfg, "column_radius", 0.0075)),
        column_height=float(getattr(connector_cfg, "column_height", 0.035)),
        grip_rings=int(getattr(connector_cfg, "grip_rings", 2)),
        radial_segments=int(getattr(connector_cfg, "radial_segments", 16)),
    )
    write_obj(path, vertices, faces)
    return path


def connector_anchor_indices(
    rope_entity, tip_center, *, axis_radius: float, z_top: float, positions=None
) -> list[int]:
    """Particles of the in-connector vertical rope run: an axis-aligned cylinder
    from the rope tip up to the exit arc.

    Anchoring this full run (instead of a small sphere at the tip) is physically
    consistent — that rope section sits inside the rigid connector/gland — and it
    removes the free cantilever stub above a sphere band whose edge particle gets
    torn between fixed and free neighbors at spawn (single-particle PBD blowup to
    the solver-domain corner).
    """

    if positions is None:
        particles = tensor_to_numpy(rope_entity.get_particles_pos())
    else:
        # Solver-agnostic path (rope_backends): the caller supplies node
        # positions, the selection itself is pure geometry.
        particles = np.asarray(positions, dtype=float)
    if particles.ndim == 3:
        particles = particles[0]
    tip = np.asarray(tip_center, dtype=float)
    radial = np.linalg.norm(particles[:, :2] - tip[None, :2], axis=1)
    mask = (
        (radial <= float(axis_radius))
        & (particles[:, 2] >= tip[2] - float(axis_radius))
        & (particles[:, 2] <= float(z_top))
    )
    indices = np.flatnonzero(mask)
    if len(indices) == 0:
        dist = np.linalg.norm(particles - tip[None, :], axis=1)
        indices = np.array([int(np.argmin(dist))], dtype=int)
    return sorted(int(index) for index in indices)


def with_end_entries(
    polyline: np.ndarray,
    *,
    rope_radius: float,
    start_entry: dict,
    end_entry: dict,
) -> np.ndarray:
    """Route both rope ends down their endpoint fixtures (mesh-only change).

    ``start_entry``/``end_entry`` are ``{"tip_z": ..., "exit_z": ...}`` in world
    coordinates: the tip sits inside the fixture (plug column / terminal body)
    so the anchored particle band lies within it; the exit arc starts above the
    fixture top so the tube leaves vertically through it. The U-turn must be an
    arc: a sharp corner self-intersects the swept tube and tetgen rejects the
    mesh. Task-level topology/route ground truth reads the raw control points
    and is unaffected.

    Either entry may be ``None``, leaving that end of the polyline untouched.
    That is what a fitting lying on its side wants: its bore is horizontal, so
    the rope runs straight into it and there is nothing to climb over.
    """

    arc_radius = max(0.008, 2.0 * float(rope_radius))
    landing_radius = 2.0 * float(rope_radius)
    adjusted = np.asarray(polyline, dtype=float).copy()
    entries: list[np.ndarray | None] = []
    for (end_index, neighbor_index), entry in (
        ((0, 1), start_entry),
        ((-1, -2), end_entry),
    ):
        if entry is None:
            entries.append(None)
            continue
        tip_z = float(entry["tip_z"])
        exit_z = float(entry["exit_z"])
        end_xy = adjusted[end_index, :2].copy()
        rope_z = float(adjusted[end_index, 2])
        direction = unit_xy(adjusted[neighbor_index] - adjusted[end_index])
        points = [np.array([end_xy[0], end_xy[1], tip_z])]
        # Semicircular U-turn over the fixture top: vertical exit along the
        # axis, vertical descent 2*arc_radius beside it.
        #
        # Sampled at 10 degrees, not 30. These points are inserted AFTER the
        # spline, so nothing rounds them afterwards -- `sample_polyline` only
        # cuts the chords linearly. At 30 degrees the U-turn is a literal
        # 7-gon whose chord sagitta is 0.27mm on a 4mm tube, twice the
        # circumferential facet error, and it reads as a lengthwise crease;
        # the parallel-transported ring frame also had to swing a full 30
        # degrees at each of those vertices. 10 degrees puts the sagitta at
        # 0.030mm and adds 0.4mm of rope.
        center_xy = end_xy + arc_radius * direction
        for theta in np.deg2rad(np.arange(180.0, -1.0, -10.0)):
            arc_xy = center_xy + arc_radius * np.cos(theta) * direction
            points.append(
                np.array([arc_xy[0], arc_xy[1], exit_z + arc_radius * np.sin(theta)])
            )
        # Quarter-arc landing: vertical descent eases into the board-level run.
        landing_center = end_xy + (2.0 * arc_radius + landing_radius) * direction
        for phi in np.deg2rad(np.arange(0.0, 91.0, 10.0)):
            landing_xy = landing_center - landing_radius * np.cos(phi) * direction
            points.append(
                np.array(
                    [
                        landing_xy[0],
                        landing_xy[1],
                        rope_z + landing_radius * (1.0 - np.sin(phi)),
                    ]
                )
            )
        adjusted[end_index, :2] += (2.0 * arc_radius + landing_radius) * direction
        entries.append(np.stack(points, axis=0))
    parts = [part for part in (entries[0], adjusted) if part is not None]
    if entries[1] is not None:
        parts.append(entries[1][::-1])
    return np.concatenate(parts, axis=0)


def connector_entry_heights(connector_cfg, *, base_z: float) -> dict:
    """Entry heights for a plug connector whose flange rests at ``base_z``."""

    return {
        "tip_z": base_z + connector_grasp_height(connector_cfg),
        # Lowered exit-arc profile (2026-07-11). Kept for the record — previous:
        # exit_z = base_z + connector_cap_top(connector_cfg) + 0.006
        "exit_z": base_z + connector_cap_top(connector_cfg) + 0.003,
    }


def with_connector_entries(
    polyline: np.ndarray,
    connector_cfg,
    *,
    board_z: float,
    rope_radius: float,
) -> np.ndarray:
    """Both ends are plug connectors sitting directly on the board (untangle)."""

    entry = connector_entry_heights(connector_cfg, base_z=board_z)
    return with_end_entries(
        polyline,
        rope_radius=rope_radius,
        start_entry=entry,
        end_entry=entry,
    )


def fixed_terminal_mesh(terminal_cfg) -> tuple[np.ndarray, np.ndarray]:
    """Industrial fixed terminal the cable permanently emerges from.

    Revolve profile bottom->top: base plate, housing body, gland neck (the rope
    exits vertically through the gland). Local origin z=0 at the base bottom —
    place the entity at board z.
    """

    base_radius = float(getattr(terminal_cfg, "base_radius", 0.016))
    base_height = float(getattr(terminal_cfg, "base_height", 0.004))
    body_radius = float(getattr(terminal_cfg, "body_radius", 0.012))
    body_height = float(getattr(terminal_cfg, "body_height", 0.014))
    gland_radius = float(getattr(terminal_cfg, "gland_radius", 0.006))
    gland_height = float(getattr(terminal_cfg, "gland_height", 0.006))
    radial_segments = int(getattr(terminal_cfg, "radial_segments", 16))
    body_top = base_height + body_height
    profile = [
        (0.0, base_radius),
        (base_height, base_radius),
        (base_height, body_radius),
        (body_top, body_radius),
        (body_top, gland_radius),
        (body_top + gland_height, gland_radius),
    ]
    return revolve_profile(profile, radial_segments)


def fixed_terminal_heights(terminal_cfg) -> tuple[float, float]:
    """(rope tip, entry-arc exit) heights above the terminal base."""

    base_height = float(getattr(terminal_cfg, "base_height", 0.004))
    body_height = float(getattr(terminal_cfg, "body_height", 0.014))
    gland_height = float(getattr(terminal_cfg, "gland_height", 0.006))
    tip = base_height + 0.5 * body_height
    exit_z = base_height + body_height + gland_height + 0.003
    return tip, exit_z


def fixed_terminal_obj_path(terminal_cfg, *, default_output_dir) -> Path:
    mesh_dir = resolve_mesh_dir(getattr(terminal_cfg, "output_dir", default_output_dir))
    path = mesh_dir / "fixed_terminal.obj"
    vertices, faces = fixed_terminal_mesh(terminal_cfg)
    write_obj(path, vertices, faces)
    return path


def routing_post_base_mesh(post_cfg) -> tuple[np.ndarray, np.ndarray]:
    """Steep convex base cone for a routing post (collision-real).

    A single solid "flare + shaft" is NOT convex (a steep base ramp followed by
    a straight shaft violates convexity), and its hull would fatten the wrap
    radius. So the post is compound: the original shaft CYLINDER keeps the wrap
    radius, and this separate frustum (convex on its own) provides the steep
    ramp that removes the post-by-table 90-degree wedge (cable iter-3: a rope
    dragged along the table slides up instead of ejecting). Origin z=0 at base.
    """

    shaft_radius = float(getattr(post_cfg, "radius", 0.012))
    base_radius = float(getattr(post_cfg, "base_radius", shaft_radius + 0.004))
    base_height = float(getattr(post_cfg, "base_height", 0.010))
    radial_segments = int(getattr(post_cfg, "post_radial_segments", 24))
    profile = [
        (0.0, base_radius),
        (base_height, shaft_radius),
    ]
    return revolve_profile(profile, radial_segments)


def routing_post_base_obj_path(post_cfg, *, default_output_dir, name: str = "routing_post_base") -> Path:
    mesh_dir = resolve_mesh_dir(getattr(post_cfg, "output_dir", default_output_dir))
    path = mesh_dir / f"{name}.obj"
    vertices, faces = routing_post_base_mesh(post_cfg)
    write_obj(path, vertices, faces)
    return path


