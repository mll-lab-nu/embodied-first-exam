#!/usr/bin/env python3
"""Check topogym.world.physics.release_geometry.ReleaseGeometry.read (the release-confirmation boxes and robot cover
planes, read at every World.read_state of a family with a final release) against its previous per-entry loop, without a
GPU or a scene.

    python scripts/check_release_geometry_batched.py [--cases 300] [--seed 0]

The installed read computes every entry's box (position + turn @ center, abs(turn) @ half) and every robot entry's
planes (planes @ turn.T, offsets - normals @ position) as stacked matmuls, robot entries grouped by plane count; numpy
evaluates a stacked product with the same kernel as the single product of the same shape, so the numbers are the
loop's (a stack over unequal shapes would not be: a per-plane 1 x 3 product differs in about half the rows). The
reference below is the previous read(), verbatim apart from `self` -> `geometry`. Random cases: robot and target entries
(sphere / box / mesh-like centers and half extents, robot cover-plane sets of 0-800 planes), random geometry poses, with
and without exact robot contact. Pass: identical results (keys and order, arrays by dtype / shape / bytes)."""
import argparse, json, sys, time
from types import SimpleNamespace

import numpy as np
from scipy.spatial.transform import Rotation


def reference_read(geometry):
    from topogym.utils.arrays import to_numpy
    boxes = {name: [] for name in (*geometry.targets, "robot")}
    robot_planes, robot_poses = [], []
    if geometry.entries:
        indices = [e[1] for e in geometry.entries]
        solver = geometry.world.scene.sim.rigid_solver
        p = to_numpy(solver.get_geoms_pos(indices, relative=False)).reshape(-1, 3)
        q = to_numpy(solver.get_geoms_quat(indices, relative=False)).reshape(-1, 4)
        r = Rotation.from_quat(q[:, [1, 2, 3, 0]]).as_matrix()
        for (name, _, local_center, local_half, planes), position, turn in zip(geometry.entries, p, r, strict=True):
            center, half = position+turn@local_center, np.abs(turn)@local_half
            boxes[name].append([center-half, center+half])
            if name == "robot":
                normals = planes[:, :3] @ turn.T
                robot_planes.append(np.c_[normals, planes[:, 3]-normals@position])
                if geometry.exact_robot_contact:
                    robot_poses.append(dict(position_m=position.copy(), rotation=turn.copy()))
    result = dict(schema_version=3 if geometry.exact_robot_contact else 2, physics_step=geometry.world.physics_step,
        complete=bool(geometry.complete), robot_present=geometry.robot_present,
        robot_bounds_m=np.asarray(boxes["robot"]).reshape(-1, 2, 3),
        target_bounds_m={name: np.asarray(boxes[name]).reshape(-1, 2, 3) for name in geometry.targets},
        robot_convex_planes_m=robot_planes, fem_elements=dict(geometry.fem_elements))
    if geometry.exact_robot_contact:
        result.update(robot_solids=geometry.robot_solids, robot_solid_poses=robot_poses)
    return result


def differences(a, b, path=""):
    if type(a) is not type(b):
        return [f"{path}: {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        out = [] if list(a) == list(b) else [f"{path}: keys {list(a)} != {list(b)}"]
        return out + [d for k in a if k in b for d in differences(a[k], b[k], f"{path}/{k}")]
    if isinstance(a, (list, tuple)):
        out = [] if len(a) == len(b) else [f"{path}: length {len(a)} != {len(b)}"]
        return out + [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    if isinstance(a, np.ndarray):
        same = a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()
        return [] if same else [f"{path}: array {a.dtype}{a.shape} != {b.dtype}{b.shape}"]
    if isinstance(a, float):
        return [] if np.float64(a).tobytes() == np.float64(b).tobytes() else [f"{path}: {a!r} != {b!r}"]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def make_case(rng):
    from topogym.world.physics.release_geometry import ReleaseGeometry
    targets = tuple(f"target_{i}" for i in range(int(rng.integers(0, 3))))
    entries = []
    for name in ("robot",)*int(rng.integers(0, 30)) + tuple(t for t in targets for _ in range(int(rng.integers(1, 40)))):
        kind = rng.choice(["sphere", "box", "mesh"])
        if kind == "sphere":
            center, half = np.zeros(3), np.repeat(rng.uniform(.001, .05), 3)
        elif kind == "box":
            center, half = np.zeros(3), rng.uniform(.001, .2, 3)/2
        else:
            vertices = rng.normal(0, .05, (20, 3)).astype(rng.choice([np.float32, np.float64]))
            center, half = (vertices.min(0)+vertices.max(0))/2, (vertices.max(0)-vertices.min(0))/2
        k = int(rng.choice([0, 0, int(rng.integers(4, 60)), int(rng.integers(100, 800))])) if name == "robot" else 0
        planes = rng.normal(0, 1, (k, 4))
        if k:
            planes[:, :3] /= np.linalg.norm(planes[:, :3], axis=1, keepdims=True)
        entries.append((name, len(entries), center, half, planes))
    order = rng.permutation(len(entries))           # robot and target entries interleaved, as geoms are
    entries = [entries[i] for i in order]
    position = rng.normal(0, .6, (len(entries), 3))
    quat = Rotation.random(max(len(entries), 1), random_state=int(rng.integers(1 << 30))).as_quat()[:len(entries)]
    wxyz = quat[:, [3, 0, 1, 2]]
    solver = SimpleNamespace(get_geoms_pos=lambda idx, relative=False: position[idx],     # rows by geom index
                             get_geoms_quat=lambda idx, relative=False: wxyz[idx])
    geometry = ReleaseGeometry.__new__(ReleaseGeometry)
    geometry.world = SimpleNamespace(physics_step=int(rng.integers(0, 10**6)),
                                     scene=SimpleNamespace(sim=SimpleNamespace(rigid_solver=solver)))
    geometry.robot_present, geometry.targets, geometry.entries = True, targets, entries
    geometry.complete, geometry.fem_elements = bool(rng.random() < .9), {}
    geometry.exact_robot_contact = bool(rng.random() < .3)
    geometry.robot_solids = [dict(link="l", geom_index=0)] if geometry.exact_robot_contact else []
    return geometry


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    r = dict(cases=0, differing=0, entries=0, planes=0, reference_s=0.0, installed_s=0.0, first_differences=[])
    for _ in range(a.cases):
        geometry = make_case(rng)
        t = time.perf_counter(); expected = reference_read(geometry); r["reference_s"] += time.perf_counter()-t
        t = time.perf_counter(); result = geometry.read(); r["installed_s"] += time.perf_counter()-t
        again = geometry.read()                      # the second read uses the cached batch
        diffs = differences(result, expected, "first") + differences(again, expected, "second")
        r["cases"] += 1
        r["entries"] += len(geometry.entries)
        r["planes"] += sum(len(e[4]) for e in geometry.entries)
        if diffs:
            r["differing"] += 1
            if len(r["first_differences"]) < 10:
                r["first_differences"].append(diffs[:5])
    r["reference_s"], r["installed_s"] = round(r["reference_s"], 2), round(r["installed_s"], 2)
    r["passed"] = bool(r["cases"] and not r["differing"])
    print(json.dumps(r, indent=1))
    sys.exit(0 if r["passed"] else 1)


if __name__ == "__main__":
    main()
