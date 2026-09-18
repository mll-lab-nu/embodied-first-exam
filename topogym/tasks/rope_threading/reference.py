"""Extract task parameters from Wang's public geometry and first saved frame.

The source files are supplied explicitly; scene construction is fully offline.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

SOURCE = "https://qinengwang-aiden.github.io/demos/constraint_demos/"
REFERENCE = Path(__file__).resolve().parents[3] / "assets/tasks/rope_threading/wang_reference_v1/reference.json"


def extract(geometry_path, manifest_path, phase_path):
    geometry = json.loads(Path(geometry_path).read_text())
    manifest = json.loads(Path(manifest_path).read_text())
    phase = manifest["phases"][0]
    binary = Path(phase_path).read_bytes()
    if hashlib.sha256(binary).hexdigest() != phase["binary"]["sha256"]:
        raise ValueError("Phase binary SHA-256 does not match the public manifest")

    def array(spec):
        values = np.frombuffer(binary, dtype=spec["dtype"], offset=spec["byte_offset"], count=spec["count"])
        if hashlib.sha256(values.tobytes()).hexdigest() != spec["sha256"]:
            raise ValueError("Saved array hash mismatch")
        return values.reshape(spec["shape"])

    poses = array(phase["arrays"]["body_poses"])[0]
    geoms = {g["name"]: g for g in geometry["geoms"] if g["name"]}
    nodes = []
    for i in range(80):
        geom = geoms[f"v4_rope_{i}"]
        pose = poses[geom["body"]]
        local = Rotation.from_quat(geom["quaternion_wxyz"], scalar_first=True)
        ends = np.asarray(geom["position"]) + local.apply([[0, 0, -geom["size"][1]], [0, 0, geom["size"][1]]])
        ends = Rotation.from_quat(pose[3:], scalar_first=True).apply(ends) + pose[:3]
        # Select the capsule endpoint at the body's joint, preserving material order.
        start = int(np.argmin(np.linalg.norm(ends-pose[:3], axis=1)))
        if nodes and not np.allclose(nodes[-1], ends[start], atol=1e-10):
            raise ValueError("Source rope is not a connected material chain")
        if not nodes:
            nodes.append(ends[start])
        nodes.append(ends[1-start])
    rings = []
    normals = ([1., 0., 0.], [.8, .6, 0.], [.3, .9, np.sqrt(.1)])
    for i, normal in enumerate(normals):
        capsules = [geoms[f"v4_ring{i}_{j}"] for j in range(64)]
        center = np.mean([g["position"] for g in capsules], axis=0)
        stand, base = geoms[f"v4_ring{i}_stand"], geoms[f"v4_ring{i}_base"]
        # The stand joins the side of the ring at angle zero, not its bottom.
        point = np.array(stand["position"])
        point[2] += stand["size"][1]
        u = (point-center)/.075
        n = np.asarray(normal)/np.linalg.norm(normal)
        v = np.cross(n, u)
        endpoints = []
        for g in capsules:
            axis = Rotation.from_quat(g["quaternion_wxyz"], scalar_first=True).apply([0, 0, g["size"][1]])
            endpoints.extend([np.array(g["position"])-axis, np.array(g["position"])+axis])
        endpoints = np.asarray(endpoints)
        if np.max(abs((endpoints-center)@n)) > 1e-9 or np.max(abs(np.linalg.norm(endpoints-center, axis=1)-.075)) > 1e-9:
            raise ValueError("Ring endpoints do not match the declared oriented circle")
        rings.append(dict(name=f"R{i+1}", center_m=center.tolist(), normal=n.tolist(),
            basis_u=u.tolist(), basis_v=v.tolist(), radius_m=.075, tube_radius_m=.006,
            segments=64, rgba=capsules[0]["rgba"], stand=stand, base=base))
    table = geoms["table"]
    return dict(schema_version=1, source=SOURCE, source_frame="original MuJoCo world, metres, Z up",
        sources={name: dict(url=SOURCE+url, sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
                 for name, path, url in (("geometry", geometry_path, "data/threading/geometry.json"),
                     ("manifest", manifest_path, "data/threading/manifest.json"),
                     ("phase000", phase_path, "data/threading/phase-000.bin"))},
        source_table_surface_z_m=table["position"][2]+table["size"][2],
        source_table_half_extents_xy_m=table["size"][:2],
        source_robot_qpos=array(phase["telemetry"]["arrays"]["qpos"])[0].tolist(),
        source_initial_time_s=float(array(phase["arrays"]["actual_time_s"])[0]),
        source_initial_crossings=array(phase["arrays"]["inside_crossings"])[0].tolist(),
        rope_radius_m=.004, rope_nodes_m=np.asarray(nodes).tolist(), rings=rings,
        target_material_order=["R1-", "R2+", "R3+"],
        material_direction="v4_rope_link_0 joint -> v4_rope_link_79 distal tip")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--phase", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=REFERENCE)
    args = parser.parse_args()
    result = extract(args.geometry, args.manifest, args.phase)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(args.output)


if __name__ == "__main__":
    main()
