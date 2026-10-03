"""Read-only draping and bilateral rope-grip measurements in world coordinates."""
import hashlib
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.evaluation.task_metrics import body_points
from topogym.utils.arrays import to_numpy
from topogym.utils.geometry.passage import aperture_crossings
from topogym.utils.grasp import surface_distances


def world_ring(ring, state):
    body = state['bodies'][ring['name']]
    turn = Rotation.from_quat(np.asarray(body['quaternion_wxyz'])[[1, 2, 3, 0]])
    return dict(ring, center_m=body_points(body, [ring['center_m']])[0],
                **{key: turn.apply(ring[key]) for key in ('normal', 'basis_u', 'basis_v')})


def drape_measurements(points, ring, rope_radius, limits):
    """Require a finite strand supported across the inside of the lower rim."""
    p = np.asarray(points)
    delta = p - ring['center_m']
    axial = delta @ ring['normal']
    u, v = delta @ ring['basis_u'], delta @ ring['basis_v']
    radial = np.hypot(u, v)
    distance = np.where(v >= 0, np.hypot(axial, radial-ring['radius_m']),
                        np.sqrt(axial**2 + (abs(u)-ring['radius_m'])**2 + v**2))
    clearance = distance - ring['tube_radius_m'] - rope_radius
    arclength = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    hits, ambiguous = aperture_crossings(p, ring['center_m'], ring['normal'], ring['radius_m'])
    supports = []
    for hit in hits:
        coordinate = float(hit['material_coordinate'])
        i = min(int(coordinate), len(p)-2)
        t = coordinate-i
        point = p[i]*(1-t) + p[i+1]*t
        local = point-ring['center_m']
        down = float(local @ ring['basis_v'])
        gap = ring['radius_m']-float(np.linalg.norm(local))-ring['tube_radius_m']-rope_radius
        s = float(arclength[i]*(1-t)+arclength[i+1]*t)
        span = limits['drape_span_m']
        length_ok = min(s, arclength[-1]-s) >= max(span, limits['minimum_drape_length_m']/2)
        ends = np.array([np.interp(s-span, arclength, axial), np.interp(s+span, arclength, axial)])
        across = bool(ends[0]*ends[1] < 0 and min(abs(ends)) > ring['tube_radius_m']+rope_radius)
        supported = bool(down >= .5*ring['radius_m'] and
                         -limits['support_penetration_m'] <= gap <= limits['support_gap_m'])
        if length_ok and across and supported:
            supports.append(dict(material_coordinate=coordinate, clearance_m=gap, point_m=point.tolist()))
    clear = bool(clearance.min() >= -limits['support_penetration_m'])
    return dict(draped=bool(supports and clear and not ambiguous), support_points=supports,
                rim_clear=clear, minimum_rim_clearance_m=float(clearance.min()), ambiguous=bool(ambiguous))


def cache_finger_surfaces(robot, description):
    """Freeze authored finger-local collision meshes for pure state evaluation."""
    result = {}
    for group in description.groups:
        if group.grasp is None:
            continue
        fingers = []
        for name in group.grasp.finger_links:
            link = robot.get_link(name)
            position = to_numpy(link.get_pos()).reshape(3)
            turn = Rotation.from_quat(to_numpy(link.get_quat()).reshape(4)[[1, 2, 3, 0]])
            vertices, faces, offset = [], [], 0
            for geom in link.geoms:
                local = turn.inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-position)
                vertices.append(local)
                faces.append(np.asarray(geom.init_faces)+offset)
                offset += len(local)
            if vertices:
                fingers.append((name, np.concatenate(vertices), np.concatenate(faces)))
        if len(fingers) == 2:
            result[group.name] = fingers
    return result


def rope_grips(state, surface_indices, fingers, ring, limits):
    """Admit healthy soft grasps or both physical fingers touching one end band.

    Uses actual FEM surface vertices and actual finger collision triangles;
    TCP proximity, commands, and single-finger touches are insufficient.
    """
    soft = state['fem']['rope']
    p, s = np.asarray(soft['position_m']), np.asarray(soft['material_s_m'])
    identity = hashlib.sha256(s[:, None].tobytes()).hexdigest()
    results = {}
    for hand in ('left', 'right'):
        live = state.get('grasp', {}).get('hands', {}).get(hand, {})
        binding = live.get('binding')
        indices, source = None, None
        if (state.get('assist_model') == 'ipc_soft_band_v1' and live.get('phase') == 'holding'
                and live.get('solved_ticks', 0) > 0 and binding
                and binding.get('hand') == hand and binding.get('target', [None])[0] == 'rope'
                and binding.get('material_identity') == identity):
            indices = np.asarray(binding['indices'], dtype=int)
            if not len(indices) or indices.min() < 0 or indices.max() >= len(p):
                raise ValueError('Invalid live rope-grasp material indices')
            source = 'healthy_contact_gated_soft_grasp'
        elif hand in fingers:
            contacts = []
            for name, local, faces in fingers[hand]:
                vertices = body_points(state['articulations']['robot']['links'][name], local)
                gap = limits['handoff_contact_gap_m']
                subset = np.asarray(surface_indices)
                subset = subset[np.all((p[subset] >= vertices.min(axis=0)-gap) &
                                       (p[subset] <= vertices.max(axis=0)+gap), axis=1)]
                near = subset[surface_distances(p[subset], vertices, faces) <= gap] if len(subset) else subset
                contacts.append(near)
            matches = []
            for distances in (s-s.min(), s.max()-s):
                bands = [idx[distances[idx] <= limits['handoff_band_m']] for idx in contacts]
                if all(len(idx) for idx in bands):
                    adjacent = abs(s[bands[0]][:, None]-s[bands[1]][None, :]) <= .02
                    if adjacent.any():
                        matches.append(np.unique(np.r_[bands[0][adjacent.any(1)], bands[1][adjacent.any(0)]]))
            if len(matches) == 1:
                indices, source = matches[0], 'bilateral_finger_surface_contact'
        if indices is None:
            continue
        end = ('start' if np.max(s[indices]-s.min()) <= limits['handoff_band_m'] else
               'end' if np.max(s.max()-s[indices]) <= limits['handoff_band_m'] else None)
        if end is not None:
            center = p[indices].mean(axis=0)
            results[hand] = dict(endpoint=end, axial_m=float((center-ring['center_m']) @ ring['normal']),
                                 material_min_m=float(s[indices].min()), material_max_m=float(s[indices].max()),
                                 evidence=source)
    return results
