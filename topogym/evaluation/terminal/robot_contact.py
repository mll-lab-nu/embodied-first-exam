"""FEM release: active-link clearance, fixed-link contact, no solid overlap.

Bounds only certify separation or select exact work. They never label an
overlap as penetration. Every collider is checked, including fixed bases.
"""
from functools import lru_cache

import numpy as np

from .clearance import validate_robot_planes
from topogym.utils.geometry.solid_contact import MeasuredCollider, RESOLUTION_M
from topogym.utils.geometry.volume_geometry import rigid_cover_vertices


@lru_cache(maxsize=128)
def _solid(kind, convex, data_bytes, vertex_bytes, face_bytes):
    vertices = np.frombuffer(vertex_bytes, dtype=np.float64).reshape(-1, 3)
    faces = np.frombuffer(face_bytes, dtype=np.int64).reshape(-1, 3)
    data = np.frombuffer(data_bytes, dtype=np.float64)
    cover, _ = rigid_cover_vertices(kind, data, vertices)
    return MeasuredCollider(dict(native_type=kind, native_convex=convex,
        native_data=data, primitive_position_in_link_m=[0., 0., 0.]), vertices, faces, cover)


def _placed(entry, pose):
    return _solid(entry['native_type'], entry['native_convex'],
        np.asarray(entry['native_data'], dtype=np.float64).tobytes(),
        np.asarray(entry['vertices_m'], dtype=np.float64).tobytes(),
        np.asarray(entry['faces'], dtype=np.int64).tobytes()).placed(
            pose['rotation'], pose['position_m'])


def evaluate_robot_contact(current, topology, geometry, active_clearance_m):
    robot = np.asarray(geometry['robot_bounds_m'])
    entries, poses = geometry['robot_solids'], geometry['robot_solid_poses']
    if len(entries) != len(robot) or len(poses) != len(robot):
        raise ValueError('Exact robot collider coverage differs from bounds')
    if any(type(e.get('fixed_to_world')) is not bool or type(e.get('native_convex')) is not bool for e in entries):
        raise ValueError('Missing native robot mobility/geometry classification')
    planes = validate_robot_planes(geometry['robot_convex_planes_m'], len(robot))
    active_minimum, fixed_minimum = None, None
    failures, contacts, queries = [], 0, 0
    for name, elements in topology.items():
        corners = current[name][elements]
        lo, hi = corners.min(1), corners.max(1)
        for i, (box, cover, entry, pose) in enumerate(zip(robot, planes, entries, poses, strict=True)):
            fixed = entry['fixed_to_world']
            required = 0. if fixed else active_clearance_m
            refine_below = RESOLUTION_M if fixed else required+RESOLUTION_M
            whole_gap = np.maximum(np.maximum(lo.min(0)-box[1], box[0]-hi.max(0)), 0.)
            minimum = float(np.linalg.norm(whole_gap))
            if minimum < refine_below:
                lower = np.linalg.norm(np.maximum(np.maximum(lo-box[1], box[0]-hi), 0.), axis=1)
                close = np.flatnonzero(lower < refine_below)
                if len(cover):
                    for start in range(0, len(close), 256):
                        indices = close[start:start+256]
                        signed = corners[indices] @ cover[:, :3].T+cover[:, 3]
                        lower[indices] = np.maximum(lower[indices], signed.min(1).max(1)-RESOLUTION_M)
                close = np.flatnonzero(lower < refine_below)
                collider, clearance_failure = None, False
                for index in close:
                    if collider is None:
                        try:
                            collider = _placed(entry, pose)
                        except (ValueError, KeyError):
                            failures.append(dict(target=name, collider=i, link=entry.get('link'), relation='unresolved'))
                            break
                    queries += 1
                    try:
                        relation, distance = collider.clearance_from_tet(corners[index], required)
                    except ValueError:
                        relation, distance = 'unresolved', 0.
                    if relation in {'penetrating', 'unresolved'}:
                        failures.append(dict(target=name, collider=i, link=entry.get('link'), cell=int(index),
                            relation=relation, gap_m=distance, fixed_to_world=fixed))
                        break
                    if not fixed and distance+RESOLUTION_M < required and not clearance_failure:
                        failures.append(dict(target=name, collider=i, link=entry.get('link'), cell=int(index),
                            relation=relation, gap_m=distance, fixed_to_world=False))
                        clearance_failure = True
                    contacts += int(relation == 'contact')
                    lower[index] = distance
                minimum = float(lower.min())
            if fixed:
                fixed_minimum = minimum if fixed_minimum is None else min(fixed_minimum, minimum)
            else:
                active_minimum = minimum if active_minimum is None else min(active_minimum, minimum)
    return not failures, dict(active_clearance_lower_bound_m=active_minimum,
        fixed_clearance_lower_bound_m=fixed_minimum, active_clearance_required_m=active_clearance_m,
        fixed_boundary_contacts=contacts, exact_cell_queries=queries,
        robot_contact_failures=failures, robot_no_penetration=not any(
            f['relation'] in {'penetrating', 'unresolved'} for f in failures),
        geometry_resolution_m=RESOLUTION_M, fixed_contact_allowed=True)
