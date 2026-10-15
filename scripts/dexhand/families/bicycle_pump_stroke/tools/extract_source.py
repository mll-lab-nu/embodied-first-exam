"""Authoring-only: copy the approved T50 scene geometry into this family's assets/ (run once).

Source (read-only): the approved scene-expansion export ``scene-v4`` of T50 (Topeak MINI MORPH + Schwalbe Big Apple
57-406 wheel): ``scene.json`` (visible geoms, sizes, colours, PBR hints), ``geometry.npz`` (mesh vertices/faces) and
``trajectory.npz`` (authoritative visible world transforms per film frame). We freeze the static props (bench, wheel,
valve, connected head, hose) at film frame ``FRAME`` (head locked on the valve, piston fully extended) and keep the
pump's own geometry (barrel, foot, piston rod, T handle) in its body frame; the runtime rebuilds the pump as a free
body with a passive piston. Writes ``assets/t50_scene.json``, ``assets/meshes/*.obj`` and ``assets/manifest.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

FRAME = 50  # stage "Twenty-eight full piston strokes", head locked, piston at full extension (0.20 m)
KIND = {0: "plane", 2: "sphere", 3: "capsule", 4: "ellipsoid", 5: "cylinder", 6: "box", 7: "mesh"}
PUMP_BODIES = {"pump_barrel", "piston"}
DROP_BODIES = {"seal_plunger"} | {f"gasket_{i}" for i in range(8)}  # hidden inside the head shell


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quat_from_matrix(R):
    from scipy.spatial.transform import Rotation

    x, y, z, w = Rotation.from_matrix(R).as_quat()
    q = np.array([w, x, y, z])
    return q if q[0] >= 0 else -q


def write_obj(path, vertices, faces):
    lines = ["# T50 scene-v4 visual mesh (copied verbatim from geometry.npz)"]
    lines += [f"v {x:.7f} {y:.7f} {z:.7f}" for x, y, z in vertices]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="the approved T50 scene-expansion film export folder (scene-v4)")
    parser.add_argument("--out", required=True, help="family assets/ folder")
    args = parser.parse_args()
    src, out = Path(args.source), Path(args.out)
    (out / "meshes").mkdir(parents=True, exist_ok=True)
    scene = json.loads((src / "scene.json").read_text())
    geometry = np.load(src / "geometry.npz")
    trajectory = np.load(src / "trajectory.npz")
    positions, rotations = trajectory["geom_positions"][FRAME], trajectory["geom_rotations"][FRAME]
    pump_index = [g["name"] for g in scene["geoms"]].index("barrel")
    pump_origin = positions[pump_index] - rotations[pump_index] @ np.array([0, 0, 0.129])
    geoms, meshes = [], {}
    rim = {"vertices": [], "faces": []}
    for i, g in enumerate(scene["geoms"]):
        if g["body"] in DROP_BODIES:
            continue
        vm = g.get("visual_material", {})
        item = {
            "name": g["name"],
            "type": KIND[g["kind"]],
            "body": g["body"],
            "size": [float(v) for v in g["size"]],
            "rgba": [float(v) for v in vm.get("rgba", g["rgba"])],
            "metallic": float(vm.get("metallic", 0) or 0),
            "roughness": float(vm.get("roughness", 0.5) or 0.5),
        }
        R, p = rotations[i], positions[i]
        if g["body"] in PUMP_BODIES:
            # Pump-local pose (the pump is rebuilt as a free body; piston geoms relative to the extended piston).
            item["pos"] = (p - pump_origin).tolist()
        else:
            item["pos"] = p.tolist()
        item["quat"] = quat_from_matrix(R).tolist()
        if item["type"] == "mesh":
            key = int(g["mesh"])
            v, f = geometry[f"mesh_{key}_vertices"], geometry[f"mesh_{key}_faces"]
            if g["name"].startswith("rim_piece_"):
                # Merge the 134 convex rim sectors (real 8.5 mm valve bore kept) into one static world mesh.
                base = sum(len(x) for x in rim["vertices"])
                rim["vertices"].append(v @ R.T + p)
                rim["faces"].append(f + base)
                continue
            name = g["name"]
            write_obj(out / "meshes" / f"{name}.obj", v, f)
            item["mesh"] = f"meshes/{name}.obj"
        geoms.append(item)
    rim_v, rim_f = np.concatenate(rim["vertices"]), np.concatenate(rim["faces"])
    write_obj(out / "meshes" / "rim.obj", rim_v, rim_f)
    rim_geom = [g for g in scene["geoms"] if g["name"] == "rim_piece_0"][0]
    geoms.append({
        "name": "rim", "type": "mesh", "body": "wheel", "size": [1, 1, 1], "mesh": "meshes/rim.obj",
        "rgba": rim_geom["visual_material"]["rgba"], "metallic": rim_geom["visual_material"]["metallic"],
        "roughness": rim_geom["visual_material"]["roughness"], "pos": [0, 0, 0], "quat": [1, 0, 0, 0],
    })
    hub = [g["name"] for g in scene["geoms"]].index("hub")
    payload = {
        "source": "approved T50 scene-expansion film export scene-v4 (scene.json, geometry.npz, trajectory.npz)",
        "source_sha256": {name: sha(src / name) for name in ("scene.json", "geometry.npz", "trajectory.npz", "model.xml")},
        "frame": FRAME,
        "pump_origin_world": pump_origin.tolist(),
        "wheel_center_world": positions[hub].tolist(),
        "wheel_rotation_world": rotations[hub].tolist(),
        "camera": scene["config"]["camera"],
        "lights": scene["config"]["lights"],
        "geoms": geoms,
    }
    (out / "t50_scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    manifest = {
        "description": "T50 bicycle-pump scene assets copied from the approved scene-v4 export by tools/extract_source.py",
        "files": {
            str(path.relative_to(out)): {"sha256": sha(path), "bytes": path.stat().st_size}
            for path in sorted(out.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps({k: v["bytes"] for k, v in manifest["files"].items()}, indent=1))


if __name__ == "__main__":
    main()
