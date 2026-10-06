#!/usr/bin/env python3
"""Check the soft grasp admission (SoftGraspBackend.candidates, used by the PBD and IPC grasp assists every World tick
while a hand closes without a hold) against its previous implementation, without a GPU.

    python scripts/check_grasp_candidates_exact.py [--cases 3000] [--seed 0] [--kinds cloth,rope]

The installed candidates() computes finger-surface distances only where they can matter (within the contact distance,
or the nearest; a rigorous lower bound decides) and builds each patch from its center's cached material neighbourhood;
exposed_patch tests only particles inside the patch's horizontal reach. The reference below is the previous code,
verbatim apart from `self` -> `backend` (topogym 4d6f6d74d: SoftGraspBackend.candidates, utils.grasp.material_patch and
exposed_patch). Random cases meet two finger boxes at random poses, gaps and spec values, with a convex obstacle, held
regions and remembered candidates; both run on copies of the same backend. cloth: folded sheets (one to three layers) on
the PBD backend's admission (material = 2-D rest coordinates); rope: tetrahedral-rope-like vertex sets (rings of surface
vertices around a centerline, bends and crossings, an anchored end) on the IPC backend's (material = arc length,
candidates only on surface vertices, forbidden anchor vertices).
Pass: identical results and identical backend state afterwards (admission records, regions with their evidence, last
candidates), floats compared by bits. Reports the share of cases with contact, qualified patches, occlusion and
candidates, and the time of both."""
import argparse, json, sys, time
from copy import deepcopy
from types import SimpleNamespace
from unittest import mock

import numpy as np


def reference_material_patch(positions, material_coordinates, center_index, *, spatial_radius_m, material_radius_m):
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


def reference_exposed_patch(positions, material, indices, *, radius, clearance):
    x, uv, indices = np.asarray(positions), np.asarray(material), np.asarray(indices)
    for i in indices:
        local = np.linalg.norm(x[:, :2]-x[i, :2], axis=1) <= radius
        remote = np.linalg.norm(uv-uv[i], axis=1) > 2*radius
        if np.any(local & remote & (x[:, 2] > x[i, 2]+clearance)):
            return False
    return True


def reference_candidates(backend, hand, geometry):
    from scipy.spatial import ConvexHull
    from topogym.utils.grasp import material_components, rotation, surface_distances
    group = backend.robot.groups[hand]
    tcp = geometry['position'] + rotation(geometry['quaternion']).apply(group.tcp_position_in_hand_m)
    results = []
    for name, spec in backend.specs.items():
        x, uv = backend.positions(name), backend.material[name]
        near = backend.candidate_mask(name) & (np.linalg.norm(x-tcp, axis=1) <= backend.config.max_tcp_distance_m)
        indices = np.flatnonzero(near)
        strain = backend.strain_ratio(name, x)
        backend._admission[hand] = dict(entity=name, nearby_vertices=len(indices), qualified_region_centers=0,
                                        max_material_edge_ratio=strain, occluded_region_centers=0,
                                        obstacle_rejected_region_centers=0,
                                        require_exposed_patch=spec.require_exposed_patch)
        if not np.isfinite(x).all() or strain > spec.max_strain_ratio:
            backend._admission[hand]['rejection'] = 'material_strain_or_nonfinite'
            continue
        if not len(indices):
            continue
        nearby = np.flatnonzero(np.linalg.norm(x-tcp, axis=1) <=
                                backend.config.max_tcp_distance_m+spec.spatial_radius_m)
        distances = np.full((2, len(x)), np.inf)
        inside_finger = np.zeros(len(x), dtype=bool)
        for side, (vertices, faces) in enumerate(geometry['surfaces']):
            distances[side, nearby] = surface_distances(x[nearby], vertices, faces)
            hull = ConvexHull(vertices)
            signed = (x[nearby] @ hull.equations[:, :3].T + hull.equations[:, 3]).max(axis=1)
            inside_finger[nearby] |= signed < -backend.config.max_penetration_m
        contact = (distances <= spec.contact_distance_m) & backend.candidate_mask(name)[None, :]
        backend._admission[hand]['minimum_finger_distances_m'] = distances.min(axis=1).tolist()
        patches = {}
        for center in indices:
            center = int(center)
            patch = reference_material_patch(x, uv, center, spatial_radius_m=spec.spatial_radius_m,
                                             material_radius_m=spec.material_radius_m)
            if (not len(patch) or not np.all(backend.allowed(name)[patch]) or inside_finger[patch].any()
                    or not np.all(contact[:, patch].any(axis=1))):
                continue
            patches[center] = patch
        backend._admission[hand]['qualified_region_centers'] = len(patches)
        for component in material_components(list(patches), uv, spec.material_radius_m):
            previous = backend.last_candidates.get((hand, name))
            ordered = sorted(map(int, component), key=lambda i: (i != previous, np.linalg.norm(x[i]-tcp), i))
            for center in ordered:
                patch = patches[center]
                if (spec.require_exposed_patch and not reference_exposed_patch(
                        x, uv, patch, radius=spec.spatial_radius_m, clearance=spec.contact_distance_m)):
                    backend._admission[hand]['occluded_region_centers'] += 1
                    continue
                if backend.penetration_reason(name, patch):
                    backend._admission[hand]['obstacle_rejected_region_centers'] += 1
                    continue
                key = (name, center)
                if key not in backend.active:
                    backend.regions[key] = dict(indices=patch.tolist(), evidence=dict(
                        source=backend.evidence_source, physics_step=backend.world.physics_step,
                        finger_surface_gaps_m=distances[:, patch].min(axis=1).tolist()))
                backend.last_candidates[hand, name] = center
                results.append(key)
                break
    return sorted(results)


def differences(a, b, path=""):
    """Exact structural comparison (types, keys and order, floats and arrays by bits)."""
    if type(a) is not type(b):
        return [f"{path}: {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        out = [] if list(a) == list(b) else [f"{path}: keys {list(a)} != {list(b)}"]
        return out + [d for k in a if k in b for d in differences(a[k], b[k], f"{path}/{k}")]
    if isinstance(a, (list, tuple)):
        out = [] if len(a) == len(b) else [f"{path}: length {len(a)} != {len(b)}"]
        return out + [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    if isinstance(a, float):
        return [] if np.float64(a).tobytes() == np.float64(b).tobytes() else [f"{path}: {a!r} != {b!r}"]
    if isinstance(a, np.ndarray):
        return [] if (a.dtype, a.shape, a.tobytes()) == (b.dtype, b.shape, b.tobytes()) else [f"{path}: array"]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def box(rng, center, extents):
    import trimesh
    from scipy.spatial.transform import Rotation
    transform = np.eye(4)
    transform[:3, :3] = Rotation.from_rotvec(rng.normal(0, .6, 3)).as_matrix()
    transform[:3, 3] = center
    mesh = trimesh.creation.box(extents=extents, transform=transform)
    return np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=int)


def cloth(rng):
    """A folded sheet: positions, material coordinates (the rest grid), the backend class and its extra attributes."""
    from topogym.world.physics.grasp_pbd import PBDGraspBackend
    spacing = rng.uniform(.004, .012)
    nx, ny = (int(v) for v in rng.integers(12, 46, size=2))
    u, v = np.meshgrid(np.arange(nx)*spacing, np.arange(ny)*spacing, indexing="ij")
    uv = np.column_stack([u.ravel(), v.ravel()])
    x = np.column_stack([uv, np.zeros(len(uv))])
    for layer in range(int(rng.integers(0, 3))):              # folds: reflect over a crease, one layer higher
        crease = rng.uniform(.3, .8)*x[:, 0].max()
        over = x[:, 0] > crease
        x[over, 0] = 2*crease-x[over, 0]
        x[over, 2] = 2*rng.uniform(.002, .008)*(layer+1)-x[over, 2]
        x[:, :2] = x[:, :2] @ np.array([[0., 1.], [-1., 0.]])  # next crease along the other axis
    x += rng.normal(0, rng.choice([1e-4, 1e-3, 3e-3]), x.shape)
    fixed = rng.random(len(x)) < rng.choice([0., .01])      # permanently fixed birth particles are never candidates
    return x, uv, np.column_stack([uv, np.zeros(len(uv))]), PBDGraspBackend, dict(_birth_free=dict(cloth=~fixed))


def rope(rng):
    """A rope: rings of surface vertices around centerline vertices (material = arc length), bent on the table, with a
    crossing lifted over the rest and an anchored (forbidden) end."""
    from topogym.world.physics.grasp_ipc import IPCGraspBackend
    ds, radius, sides = rng.uniform(.003, .008), rng.uniform(.003, .008), int(rng.integers(4, 9))
    n = int(rng.integers(60, 260))
    s = np.arange(n)*ds
    turn = np.cumsum(rng.normal(0, rng.uniform(.02, .25), n))          # heading along the table
    center = np.column_stack([np.cumsum(np.cos(turn))*ds, np.cumsum(np.sin(turn))*ds, np.full(n, radius)])
    if rng.random() < .5:                                               # fold the far part back over the near part
        k = int(rng.integers(n//3, n-n//4))
        center[k:, :2] = 2*center[k, :2]-center[k:, :2]+rng.normal(0, radius, 2)
        center[k:, 2] += 2*radius
    tangent = np.gradient(center, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
    normal = np.cross(tangent, [0., 0., 1.])
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    binormal = np.cross(tangent, normal)
    angles = 2*np.pi*np.arange(sides)/sides
    ring = (center[:, None, :]+radius*(np.cos(angles)[None, :, None]*normal[:, None, :]
                                        + np.sin(angles)[None, :, None]*binormal[:, None, :])).reshape(-1, 3)
    x = np.concatenate([center, ring])+rng.normal(0, rng.choice([1e-5, 3e-4]), (n*(sides+1), 3))
    material = np.concatenate([s, np.repeat(s, sides)])[:, None]
    rest = np.concatenate([np.column_stack([s, np.zeros((n, 2))]),
                           (np.column_stack([np.repeat(s, sides), np.zeros((n*sides, 2))])
                            + radius*np.tile(np.column_stack([np.zeros(sides), np.cos(angles), np.sin(angles)]), (n, 1)))])
    surface = np.r_[np.zeros(n, bool), np.ones(n*sides, bool)]
    forbidden = material[:, 0] < rng.choice([0., .02])
    return x, material, rest, IPCGraspBackend, dict(forbidden=dict(rope=forbidden), surface_masks=dict(rope=surface))


def make_case(rng, kind):
    """One case of `kind` (cloth / rope): two finger boxes around a TCP near the material, a convex obstacle."""
    from topogym.utils.grasp import GraspAssistConfig, SoftGraspTarget
    name = kind
    x, material, rest, cls, extra = (cloth if kind == "cloth" else rope)(rng)
    spec = SoftGraspTarget(name, spatial_radius_m=float(rng.uniform(.008, .022)),
                           material_radius_m=float(rng.uniform(.01, .026)),
                           contact_distance_m=float(rng.uniform(.002, .01)), max_strain_ratio=float(rng.uniform(1.2, 3.)),
                           require_exposed_patch=bool(rng.random() < (.8 if kind == "cloth" else .3)))
    config = GraspAssistConfig(model="pbd_local_patch_v1" if kind == "cloth" else "ipc_soft_band_v1", targets=(spec,),
                               max_tcp_distance_m=float(rng.uniform(.03, .08)),
                               max_penetration_m=float(rng.uniform(.001, .006)))
    tcp = x[int(rng.integers(len(x)))]+rng.normal(0, .006, 3)
    axis = rng.normal(0, 1, 3)
    axis /= np.linalg.norm(axis)
    gap = rng.uniform(0., .025)
    surfaces = [box(rng, tcp+sign*(gap/2+.004)*axis, rng.uniform(.006, .03, 3)) for sign in (-1, 1)]
    geometry = dict(position=tcp, quaternion=[1., 0., 0., 0.], surfaces=surfaces)
    backend = cls.__new__(cls)
    for key, value in extra.items():
        setattr(backend, key, value)
    backend.specs, backend.config, backend.evidence_source = {name: spec}, config, "check"
    backend.material, backend.identities, backend.edges, backend.rest_lengths = {}, {}, {}, {}
    backend.initialize_material(name, material, rest)
    backend.robot = SimpleNamespace(groups=dict(left=SimpleNamespace(tcp_position_in_hand_m=(0., 0., 0.)),
                                                right=SimpleNamespace(tcp_position_in_hand_m=(0., 0., 0.))))
    obstacle = box(rng, tcp+rng.normal(0, .03, 3), rng.uniform(.01, .06, 3))[0]
    geoms = [SimpleNamespace(is_convex=True, get_verts=lambda v=obstacle: v.copy()),
             SimpleNamespace(is_convex=False, get_verts=lambda: None)]
    backend.world = SimpleNamespace(physics_step=int(rng.integers(0, 10**6)), entities={
        "robot": SimpleNamespace(links=[]), name: SimpleNamespace(), "obstacle": SimpleNamespace(
            links=[SimpleNamespace(geoms=geoms)])})
    backend.positions = lambda name, x=x: x.copy()
    backend.regions, backend.active, backend.last_candidates, backend._admission = {}, {}, {}, {}
    backend._last_health = {}
    near = np.flatnonzero(np.linalg.norm(x-tcp, axis=1) <= config.max_tcp_distance_m)
    if len(near) and rng.random() < .4:
        backend.last_candidates["right", name] = int(rng.choice(near))
    if len(near) and rng.random() < .3:
        held = (name, int(rng.choice(near)))
        backend.active[held] = dict(hand="left", target=held)
        backend.regions[held] = dict(indices=[held[1]], evidence={})
    return backend, geometry


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--kinds", default="cloth,rope")
    a = ap.parse_args()
    import topogym.world.physics.grasp_soft as soft
    rng = np.random.default_rng(a.seed)
    kinds = a.kinds.split(",")
    blank = lambda: dict(cases=0, differing=0, contact=0, qualified=0, occluded=0, candidates=0, reference_s=0.0,
                         installed_s=0.0)
    r = dict(blank(), by_kind={k: blank() for k in kinds}, first_differences=[])
    state = lambda b: deepcopy(dict(regions=b.regions, active=b.active, last_candidates=b.last_candidates,
                                    admission=b._admission))
    for case in range(a.cases):
        kind = kinds[case % len(kinds)]
        backend, geometry = make_case(rng, kind)
        reference = deepcopy(backend)
        reference.positions, reference.world = backend.positions, backend.world
        t = time.perf_counter()
        expected = reference_candidates(reference, "right", geometry)
        reference_s = time.perf_counter()-t
        with mock.patch.object(soft, "read_grasp_geometry", lambda robot, hand: geometry):
            t = time.perf_counter()
            result = backend.candidates("right")
            installed_s = time.perf_counter()-t
        diffs = differences(result, expected, "result") + differences(state(backend), state(reference), "state")
        admission = reference._admission.get("right", {})
        for d in (r, r["by_kind"][kind]):
            d["cases"] += 1
            d["reference_s"] += reference_s
            d["installed_s"] += installed_s
            d["contact"] += int(min(admission.get("minimum_finger_distances_m", [np.inf]))
                                <= backend.specs[kind].contact_distance_m)
            d["qualified"] += int(admission.get("qualified_region_centers", 0) > 0)
            d["occluded"] += int(admission.get("occluded_region_centers", 0) > 0)
            d["candidates"] += int(bool(expected))
            d["differing"] += int(bool(diffs))
        if diffs and len(r["first_differences"]) < 10:
            r["first_differences"].append([kind] + diffs[:5])
    for d in [r] + list(r["by_kind"].values()):
        d["reference_s"], d["installed_s"] = round(d["reference_s"], 2), round(d["installed_s"], 2)
    r["passed"] = bool(r["cases"] and not r["differing"])
    print(json.dumps(r, indent=1))
    sys.exit(0 if r["passed"] else 1)


if __name__ == "__main__":
    main()
