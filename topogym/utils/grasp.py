"""Pure grasp declarations and geometry; no scene, controller or physics writes.

Contact filtering and material intersection adapted from historical Fiber and
Blanket helpers at cb60f01b32786cc9c26f754f91b7be4bef3f9ca6. No legacy imports.
"""
from dataclasses import dataclass
import math
import numpy as np
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class GraspTarget:
    """Owner-declared spherical grasp region in an authored rigid link frame."""
    entity: str
    link: str
    center_m: tuple[float, float, float] = (0., 0., 0.)
    radius_m: float = .03

    def __post_init__(self):
        if not all(isinstance(v, str) and v for v in (self.entity, self.link)):
            raise ValueError("Grasp entity and link must be nonempty names")
        center = np.asarray(self.center_m, dtype=float)
        if center.shape != (3,) or not np.isfinite(center).all():
            raise ValueError("Grasp center must contain three finite coordinates")
        if isinstance(self.radius_m, bool) or not math.isfinite(self.radius_m) or self.radius_m <= 0:
            raise ValueError("Grasp radius must be finite and positive")
        object.__setattr__(self, "center_m", tuple(map(float, center)))

    @property
    def key(self):
        return (self.entity, self.link)


@dataclass(frozen=True)
class SoftGraspTarget:
    """Allowed material region; dynamic indices are chosen only near the hand.

    Bounds/radii are in rest-material metres (rope arc length or cloth UV).
    Empty bounds allow the whole entity except permanent/fixed constraints.
    """
    entity: str
    material_min_m: tuple[float, ...] = ()
    material_max_m: tuple[float, ...] = ()
    spatial_radius_m: float = .014
    material_radius_m: float = .018
    contact_distance_m: float = .006
    max_strain_ratio: float = 1.3
    strength: float = 100.

    def __post_init__(self):
        if not isinstance(self.entity, str) or not self.entity:
            raise ValueError("Soft grasp entity must be named")
        lo, hi = np.asarray(self.material_min_m), np.asarray(self.material_max_m)
        if lo.ndim != 1 or hi.shape != lo.shape or len(lo) not in (0, 1, 2):
            raise ValueError("Material bounds must be matching arc-length or UV coordinates")
        if not np.isfinite(lo).all() or not np.isfinite(hi).all() or np.any(lo > hi):
            raise ValueError("Invalid material bounds")
        object.__setattr__(self, "material_min_m", tuple(map(float, lo)))
        object.__setattr__(self, "material_max_m", tuple(map(float, hi)))
        for name in ("spatial_radius_m", "material_radius_m", "contact_distance_m", "strength", "max_strain_ratio"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid {name}")
        if self.max_strain_ratio <= 1:
            raise ValueError("max_strain_ratio must exceed one")

    @property
    def key(self):
        return (self.entity,)


@dataclass(frozen=True)
class GraspAssistConfig:
    """Episode configuration, never a policy command. Disabled by default."""
    model: str = "none"
    targets: tuple[GraspTarget | SoftGraspTarget, ...] = ()
    stable_time_s: float = .02
    max_tcp_distance_m: float = .06
    max_penetration_m: float = .002
    max_translation_error_m: float = .01
    max_rotation_error_rad: float = .15
    max_finger_opening_fraction: float = .15
    intent_deadband: float = .002
    # "close": a hand whose gripper is already commanded closed at episode birth
    # (a pregrasp segment0) may acquire without a later closing command.
    initial_intent: str = "open"

    def __post_init__(self):
        if self.initial_intent not in {"open", "close"}:
            raise ValueError("initial_intent must be open or close")
        if self.model not in {"none", "contact_weld_v1", "ipc_soft_band_v1", "pbd_local_patch_v1"}:
            raise ValueError("Unsupported grasp assistance model")
        targets = tuple(self.targets)
        target_type = GraspTarget if self.model in {"none", "contact_weld_v1"} else SoftGraspTarget
        if not all(isinstance(t, target_type) for t in targets):
            raise ValueError(f"Grasp targets must be {target_type.__name__} declarations")
        if target_type is SoftGraspTarget:
            dimension = 1 if self.model == "ipc_soft_band_v1" else 2
            if any(t.material_min_m and len(t.material_min_m) != dimension for t in targets):
                raise ValueError("Material bounds dimension does not match grasp model")
        if len({t.key for t in targets}) != len(targets):
            raise ValueError("Declare each grasp link once")
        if (self.model == "none") != (not targets):
            raise ValueError("Enabled assist requires targets; disabled assist accepts none")
        object.__setattr__(self, "targets", targets)
        for name in ("stable_time_s", "max_tcp_distance_m", "max_penetration_m",
                     "max_translation_error_m", "max_rotation_error_rad", "max_finger_opening_fraction", "intent_deadband"):
            v = getattr(self, name)
            if isinstance(v, bool) or not math.isfinite(v) or v <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.intent_deadband >= 1:
            raise ValueError("intent_deadband must be a fraction below one")
        if self.max_finger_opening_fraction > 1:
            raise ValueError("max_finger_opening_fraction must be at most one")


def closed_fraction(value, open_value, closed_value):
    values = np.asarray([value, open_value, closed_value], dtype=float)
    if not np.isfinite(values).all() or open_value == closed_value:
        raise ValueError("Invalid gripper coordinate semantics")
    return float((value - open_value) / (closed_value - open_value))


def rotation(quaternion_wxyz):
    q = np.asarray(quaternion_wxyz, dtype=float)
    if q.shape != (4,) or not np.isfinite(q).all() or abs(np.linalg.norm(q)-1.) > 1.e-5:
        raise ValueError("Expected unit wxyz orientation")
    return Rotation.from_quat(q[[1, 2, 3, 0]])


def relative_pose(parent_position, parent_quaternion, position, quaternion):
    r = rotation(parent_quaternion)
    return dict(position_m=r.inv().apply(np.asarray(position)-parent_position).tolist(),
                quaternion_wxyz=(r.inv()*rotation(quaternion)).as_quat()[[3, 0, 1, 2]].tolist())


def relative_error(reference, actual):
    return (float(np.linalg.norm(np.asarray(reference["position_m"])-actual["position_m"])),
            float((rotation(reference["quaternion_wxyz"]).inv()*rotation(actual["quaternion_wxyz"])).magnitude()))


def bilateral_contact_rows(contacts, fingers, target_link, *, center_m, radius_m, max_penetration_m):
    """One native contact snapshot, one target link, both distinct fingers.

    Never merge contacts from different substeps or different candidate links.
    Negative penetration is speculative separation, not acquisition evidence.
    """
    if len(set(fingers)) != 2:
        raise ValueError("Exactly two distinct finger links are required")
    a, b = (np.asarray(contacts[k]).reshape(-1) for k in ("link_a", "link_b"))
    depth = np.asarray(contacts["penetration"]).reshape(-1)
    position = np.asarray(contacts["position"]).reshape(-1, 3)
    if len({len(a), len(b), len(depth), len(position)}) != 1:
        raise ValueError("Mismatched contact arrays")
    valid = (np.isfinite(depth) & (depth >= 0) & (depth <= max_penetration_m)
             & np.isfinite(position).all(axis=1)
             & (np.linalg.norm(position-np.asarray(center_m), axis=1) <= radius_m))
    rows = []
    for finger in fingers:
        indices = np.flatnonzero(valid & (((a == target_link) & (b == finger)) |
                                          ((b == target_link) & (a == finger))))
        if not len(indices):
            return ()
        rows.extend(indices.tolist())
    return tuple(sorted(set(rows)))


def material_patch(positions, material_coordinates, center_index, *, spatial_radius_m, material_radius_m):
    """Spatial intersection with material neighbourhood; empty stays empty."""
    x, uv = np.asarray(positions), np.asarray(material_coordinates)
    if x.ndim != 2 or x.shape[1] != 3 or uv.ndim != 2 or len(x) != len(uv):
        raise ValueError("Invalid material patch arrays")
    if not np.isfinite(x).all() or not np.isfinite(uv).all():
        raise ValueError("Nonfinite material patch")
    if type(center_index) is not int or not 0 <= center_index < len(x):
        raise ValueError("Invalid material index")
    if not all(np.isfinite(v) and v > 0 for v in (spatial_radius_m, material_radius_m)):
        raise ValueError("Patch radii must be finite and positive")
    return np.flatnonzero((np.linalg.norm(x-x[center_index], axis=1) <= spatial_radius_m) &
                         (np.linalg.norm(uv-uv[center_index], axis=1) <= material_radius_m))


def surface_distances(points, vertices, faces):
    """Unsigned distances to actual triangles, not to a TCP or vertex cloud."""
    import trimesh
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    return trimesh.proximity.closest_point_naive(mesh, np.asarray(points))[1]


def material_components(indices, coordinates, radius):
    """Stable connected components in material space; separated layers stay apart."""
    from scipy.spatial import cKDTree
    indices = np.asarray(indices, dtype=int)
    tree = cKDTree(np.asarray(coordinates)[indices])
    remaining, result = set(range(len(indices))), []
    while remaining:
        todo, found = [min(remaining)], []
        while todo:
            k = todo.pop()
            if k not in remaining:
                continue
            remaining.remove(k)
            found.append(int(indices[k]))
            todo.extend(i for i in tree.query_ball_point(tree.data[k], radius) if i in remaining)
        result.append(np.array(sorted(found), dtype=int))
    return result


def exposed_patch(positions, material, indices, *, radius, clearance):
    """Reject a patch under a materially distant layer (gravity-up convention)."""
    x, uv, indices = np.asarray(positions), np.asarray(material), np.asarray(indices)
    for i in indices:
        local = np.linalg.norm(x[:, :2]-x[i, :2], axis=1) <= radius
        remote = np.linalg.norm(uv-uv[i], axis=1) > 2*radius
        if np.any(local & remote & (x[:, 2] > x[i, 2]+clearance)):
            return False
    return True
