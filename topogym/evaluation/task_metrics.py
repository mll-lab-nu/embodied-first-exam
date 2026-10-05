"""Read-only terminal measurements. No engine access, latch or goal registry."""
import numpy as np
from scipy.spatial.transform import Rotation
from topogym.utils.geometry.regions import points3, placement_measurements


def body_points(body, vertices):
    p, q = np.asarray(body["position_m"], float), np.asarray(body["quaternion_wxyz"], float)
    if p.shape != (3,) or q.shape != (4,) or not np.isfinite(np.r_[p, q]).all() or np.linalg.norm(q) < 1e-12:
        raise ValueError("Invalid body pose")
    return Rotation.from_quat(q[[1, 2, 3, 0]]).apply(points3(vertices))+p


def body_points_batch(bodies, vertices):
    """[body_points(body, vertices) for body in bodies] as one (bodies, vertices, 3) array, bit for bit.

    One batched Rotation when every vertex has at most one nonzero coordinate (link origins, points on a link axis): each
    rotated coordinate is then a single product plus exact zeros, so the batched and the per-body rotations round alike
    (scipy's batched apply sums general vertices in another order). Any other vertex, and any pose that is not a finite (3,)
    position with a nonzero (4,) quaternion, goes through body_points per body, which also raises its error on the first
    invalid pose. scripts/check_fiber_fast_paths.py compares both on random poses."""
    v = points3(vertices)
    p = q = None
    if np.all(np.count_nonzero(v, axis=1) <= 1):
        try:
            p = np.array([np.asarray(body["position_m"], float) for body in bodies])
            q = np.array([np.asarray(body["quaternion_wxyz"], float) for body in bodies])
        except (TypeError, ValueError):
            p = q = None
    if (p is None or p.shape != (len(bodies), 3) or q.shape != (len(bodies), 4) or not np.isfinite(p).all()
            or not np.isfinite(q).all() or not (np.linalg.norm(q, axis=1) >= 1e-12).all()):
        return np.array([body_points(body, v) for body in bodies]).reshape(len(bodies), len(v), 3)
    rotation = Rotation.from_quat(q[:, [1, 2, 3, 0]])
    return np.stack([rotation.apply(np.tile(x, (len(p), 1)))+p for x in v], axis=1)


def quiet_body(body, linear_limit=.001, angular_limit=.02):
    if not np.isfinite([linear_limit, angular_limit]).all() or min(linear_limit, angular_limit) < 0:
        raise ValueError("Invalid velocity thresholds")
    v, w = np.asarray(body["linear_velocity_m_s"], float), np.asarray(body["angular_velocity_rad_s"], float)
    if v.shape != (3,) or w.shape != (3,) or not np.isfinite(np.r_[v, w]).all():
        raise ValueError("Invalid body velocity")
    return bool(np.linalg.norm(v) <= linear_limit and np.linalg.norm(w) <= angular_limit)


def soft_speed(fem_state, limit=.001):
    p, v = points3(fem_state["position_m"]), points3(fem_state["velocity_m_s"])
    if p.shape != v.shape or not np.isfinite(limit) or limit < 0:
        raise ValueError("Invalid soft velocity array/limit")
    speeds = np.linalg.norm(v, axis=1)
    return bool(speeds.max() <= limit), dict(maximum_speed_m_s=float(speeds.max()), p99_speed_m_s=float(np.quantile(speeds, .99)))


def ipc_integrity(state, soft_names, attachment_names=(), residual_limit=.002):
    """None is unavailable, False is observed broken, True is qualified evidence."""
    ipc = state.get("ipc")
    if not ipc or "native_valid" not in ipc:
        return None
    if not isinstance(ipc["native_valid"], (bool, np.bool_)):
        raise ValueError("Invalid IPC validity flag")
    if not ipc["native_valid"]:
        return False
    ratios, residuals = ipc["volume_ratio"], ipc["attachment_residual_m"]
    for name in soft_names:
        values = np.asarray([ratios[name]["minimum"], ratios[name]["maximum"]], float)
        if not np.isfinite(values).all():
            raise ValueError("Invalid IPC volume diagnostic")
        if values[0] <= 0 or values[1] < values[0]:
            return False
    for name in attachment_names:
        value = float(residuals[name])
        if not np.isfinite(value) or value < 0:
            raise ValueError("Invalid attachment residual")
        if value > residual_limit:
            return False
    return True


def placement_candidate(state, region, local_vertices, targets, remainder, *, soft_names=(), attachment_names=(), linear_limit=.001, angular_limit=.02):
    """Complete caller-supplied geometry, with explicit immutable entity roles."""
    if not targets or not remainder or set(targets) & set(remainder):
        raise ValueError("Invalid placement entity partition")
    clouds, quiet = {}, True
    for name in (*targets, *remainder):
        if name in soft_names:
            clouds[name] = points3(state["fem"][name]["position_m"])
            if name in targets:
                quiet &= soft_speed(state["fem"][name], linear_limit)[0]
        else:
            clouds[name] = body_points(state["bodies"][name], local_vertices[name])
            if name in targets:
                quiet &= quiet_body(state["bodies"][name], linear_limit, angular_limit)
    integrity = ipc_integrity(state, soft_names, attachment_names) if soft_names else True
    metrics = placement_measurements(region, {k: clouds[k] for k in targets}, {k: clouds[k] for k in remainder})
    metrics.update(quiet=bool(quiet), connections_intact=integrity,
                   evaluation_status="unavailable" if integrity is None else "available",
                   holding_allowed=True)
    reached = metrics["all_target_inside"] and metrics["remainder_on_system_side"] and quiet and integrity is True
    return bool(reached), "connection_or_volume_invalid" if integrity is False else None, metrics


def contact_role_hits(events, roles_a, roles_b):
    """Filter role-resolved *touches*, not proximity candidates or link names.

    World must later produce these records with geometry identities and a
    coverage declaration. Empty events alone say nothing about coverage.
    """
    hits = []
    for event in events:
        a, b = event["role_a"], event["role_b"]
        if not isinstance(event["touching"], (bool, np.bool_)):
            raise ValueError("Contact event requires an explicit touching flag")
        if event["touching"] and ((a in roles_a and b in roles_b) or (b in roles_a and a in roles_b)):
            hits.append(dict(event))
    return hits


def rigid_asset_vertices(spec):
    """Cache visual AND collision geometry in the authored rigid root frame.

    Analytic surfaces use conservative boxes. Articulated assets must instead
    supply per-link geometry and are deliberately rejected here.
    """
    from itertools import product
    from pathlib import Path
    import xml.etree.ElementTree as ET
    import trimesh
    corners = np.array(list(product((-1., 1.), repeat=3)))
    if spec.morph_type == "box":
        return corners*np.asarray(spec.morph_options["size"])/2
    if spec.morph_type == "mesh":
        return np.asarray(trimesh.load(spec.asset_path, force="mesh", process=False).vertices).copy()
    if spec.morph_type != "urdf":
        raise ValueError(f"Unsupported rigid asset {spec.morph_type}")
    path = Path(spec.asset_path)
    root = ET.parse(path).getroot()
    def transform(node):
        m = np.eye(4)
        if node is not None:
            m[:3, 3] = np.fromstring(node.get("xyz", "0 0 0"), sep=" ")
            m[:3, :3] = Rotation.from_euler("xyz", np.fromstring(node.get("rpy", "0 0 0"), sep=" ")).as_matrix()
        return m
    joints = root.findall("joint")
    if any(j.get("type") != "fixed" for j in joints):
        raise ValueError("Articulated asset needs per-link geometry")
    children = {j.find("child").get("link") for j in joints}
    frames = {link.get("name"): np.eye(4) for link in root.findall("link") if link.get("name") not in children}
    pending = list(joints)
    while pending:
        ready = [j for j in pending if j.find("parent").get("link") in frames]
        if not ready:
            raise ValueError("Invalid URDF tree")
        for j in ready:
            frames[j.find("child").get("link")] = frames[j.find("parent").get("link")] @ transform(j.find("origin"))
            pending.remove(j)
    points = []
    for link in root.findall("link"):
        for piece in (*link.findall("visual"), *link.findall("collision")):
            geometry = piece.find("geometry")
            shape = list(geometry)[0]
            if shape.tag == "mesh":
                mesh_path = Path(shape.get("filename"))
                if not mesh_path.is_absolute():
                    mesh_path = path.parent/mesh_path
                p = np.asarray(trimesh.load(mesh_path, force="mesh", process=False).vertices)
                p = p*np.fromstring(shape.get("scale", "1 1 1"), sep=" ")
            elif shape.tag == "box":
                p = corners*np.fromstring(shape.get("size"), sep=" ")/2
            elif shape.tag in {"sphere", "cylinder"}:
                radius = float(shape.get("radius"))
                p = corners*[radius, radius, radius if shape.tag == "sphere" else float(shape.get("length"))/2]
            else:
                raise ValueError(f"Unsupported collision shape {shape.tag}")
            m = frames[link.get("name")] @ transform(piece.find("origin"))
            points.append(p @ m[:3,:3].T+m[:3,3])
    return points3(np.vstack(points))
