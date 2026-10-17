"""Authoring only: export exact native poses of a physical replay for the Blender studio film.

The bundle format is the one of the T48 scene film (`scripts/scene_expansion/tasks/drink_tray/trajectory_r1/
studio_render.py`): `scene.json` (geoms, meshes, materials, sampled frames with state hashes), `geometry.npz` (local
vertices/faces) and `poses.npz` (world position + rotation of every exported object at every sampled control).
Nothing is interpolated or synthesised: every pose comes from `Session.step` of the given trajectory, sampled every
`stride` controls. The tray's 365 convex pieces are exported as one mesh in the tray body frame (same geometry).

Usage (from the family folder): python tools/presentation.py --trajectory solution/trajectory.npz --export <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from replay import load_trajectory  # noqa: E402
from runtime import Session  # noqa: E402

PAINT = dict(rgba=[0.78, 0.82, 0.78, 1], metallic=0.28, roughness=0.26, coat=0.15,
             bump=dict(scale=1800, strength=0.06, distance=0.000015))
STONE = dict(rgba=[0.57, 0.52, 0.43, 1], roughness=0.55, bump=dict(scale=320, strength=0.14, distance=0.00008))
DARK = dict(rgba=[0.11, 0.16, 0.15, 1], metallic=0.15, roughness=0.4)
STEEL = dict(rgba=[0.62, 0.67, 0.69, 1], metallic=0.93, roughness=0.24)
WATER = dict(rgba=[0.38, 0.70, 0.82, 1], transmission=0.72, ior=1.333, roughness=0.07, coat=0.1)
FLOOR = dict(rgba=[0.43, 0.47, 0.46, 1], roughness=0.8)
STAGES = ["approach: fingertips into the handle slots", "tray lifted, carrying", "tray placed on the receiving counter",
          "released: glasses upright, 1 s hold"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mesh_arrays(m, mesh_id):
    va, vn = int(m.mesh_vertadr[mesh_id]), int(m.mesh_vertnum[mesh_id])
    fa, fn = int(m.mesh_faceadr[mesh_id]), int(m.mesh_facenum[mesh_id])
    return m.mesh_vert[va:va + vn].astype(float).copy(), m.mesh_face[fa:fa + fn].astype(np.int64).copy()


def export(trajectory, directory, stride=2, hand="sharpa", title="Carry a tray with two filled glasses"):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, recorded, _ = load_trajectory(trajectory)
    session = Session(hand=recorded)
    m, d = session.model, session.data
    arrays, meshes, geoms = {}, {}, []
    tracks = []  # (kind, index): ("geom", gid) or ("body", bid)

    def add_mesh(name, vertices, faces):
        key = str(len(meshes))
        prefix = f"mesh_{key}_"
        arrays.update({prefix + "vertices": vertices, prefix + "faces": faces,
                       prefix + "normals": np.zeros((0, 3)), prefix + "face_normals": np.full(faces.shape, -1),
                       prefix + "uv": np.zeros((0, 2)), prefix + "face_uv": np.full(faces.shape, -1)})
        meshes[key] = {"name": name, "prefix": prefix, "has_uv": False}
        return int(key)

    def add(name, kind, size, track, mesh=None, visual=None, is_hand=False, material=-1, rgba=(1, 1, 1, 1)):
        record = {"name": name, "kind": int(kind), "size": [float(v) for v in size], "mesh": mesh,
                  "material": material, "rgba": [float(v) for v in rgba], "is_hand": is_hand}
        if visual:
            record["visual_material"] = visual
        geoms.append(record)
        tracks.append(track)

    # Tray: every piece (floor, rim bands, perforated web) joined in the tray body frame.
    tray = m.body("tray").id
    blocks, offset = [], 0
    faces_all = []
    for g in range(m.ngeom):
        if m.geom_bodyid[g] != tray or m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        v, f = mesh_arrays(m, int(m.geom_dataid[g]))
        R = np.zeros(9)
        mujoco.mju_quat2Mat(R, m.geom_quat[g])
        blocks.append(v @ R.reshape(3, 3).T + m.geom_pos[g])
        faces_all.append(f + offset)
        offset += len(v)
    tray_mesh = add_mesh("ROMANTISK original perforated serving tray", np.vstack(blocks), np.vstack(faces_all))
    add("ROMANTISK original perforated serving tray", 7, [1, 1, 1], ("body", tray), tray_mesh, PAINT)
    # Glasses, water volumes, bottle: the scene's own visual meshes.
    for i, cup in enumerate(("cup_0", "cup_1")):
        for suffix, label, visual in (("_glass_visual", f"POKAL {i + 1} smooth fluted glass", None),
                                      ("_water_visual", f"150 mL water volume {i + 1}", WATER)):
            g = m.geom(cup + suffix).id
            mid = int(m.geom_dataid[g])
            key = add_mesh(label, *mesh_arrays(m, mid))
            add(label, 7, [1, 1, 1], ("geom", g), key, visual or dict(rgba=[0.94, 0.98, 0.96, 1], transmission=1,
                                                                       ior=1.47, roughness=0.065))
    g = m.geom("bottle_visual").id
    add("Fixed stainless bottle obstacle", 7, [1, 1, 1], ("geom", g), add_mesh("bottle", *mesh_arrays(m, int(m.geom_dataid[g]))), STEEL)
    for i in range(2):
        g = m.geom(f"counter_{i}").id
        add(f"Stone countertop {i + 1}", 6, m.geom_size[g], ("geom", g), visual=STONE)
        for j in range(4):
            g = m.geom(f"counter_{i}_leg_{j}").id
            add(f"Cabinet leg {i}_{j}", 6, m.geom_size[g], ("geom", g), visual=DARK)
    add("Warm studio floor", 6, [4.0, 4.0, 0.015], ("floor", None), visual=FLOOR)
    # Hands: every visible (group <= 2, non-collision) geom below a wrist stage.
    materials = [{"name": "silver", "rgba": [0.79, 0.82, 0.93, 1], "roughness": 0.3},
                 {"name": "green", "rgba": [0.2, 1, 0.2, 1], "roughness": 0.6}]
    owner = session.checker.geom_owner
    for g in range(m.ngeom):
        if owner[g] != "hand" or m.geom_group[g] > 2 or m.geom_rgba[g, 3] == 0:
            continue
        name = m.geom(g).name or f"hand_geom_{g}"
        if "_collision" in name or m.geom_contype[g]:
            continue
        matname = m.material(int(m.geom_matid[g])).name if m.geom_matid[g] >= 0 else ""
        kind = int(m.geom_type[g])
        key = add_mesh(name, *mesh_arrays(m, int(m.geom_dataid[g]))) if kind == 7 else None
        add(name, kind, m.geom_size[g], ("geom", g), key, is_hand=True, material=1 if "green" in matname else 0,
            rgba=m.geom_rgba[g])

    positions, rotations, frames = [], [], []
    floor_pos = np.array([0.5, 0.0, -0.015])

    def sample():
        st = session.status()
        pos, rot = [], []
        for kind, index in tracks:
            if kind == "body":
                pos.append(d.xpos[index].copy())
                rot.append(d.xmat[index].reshape(3, 3).copy())
            elif kind == "geom":
                pos.append(d.geom_xpos[index].copy())
                rot.append(d.geom_xmat[index].reshape(3, 3).copy())
            else:
                pos.append(floor_pos.copy())
                rot.append(np.eye(3))
        positions.append(pos)
        rotations.append(rot)
        frames.append({"time_s": round(st["steps"] * session.control_dt, 4), "step": st["steps"],
                       "state_sha": session.state_sha(),
                       "status": {"stage": st["stage"], "success": st["success"], "failed": st["failed"],
                                  "done": st["done"], "reason": st["reason"], "hold_steps": st["hold_steps"]}})

    sample()
    for i, row in enumerate(actions):
        session.step(row)
        if (i + 1) % stride == 0 or session.done:
            sample()
        if session.done:
            break
    final = session.status()
    np.savez_compressed(directory / "geometry.npz", **arrays)
    np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    payload = {
        "task": "tray_glass_carry",
        "title": title,
        "evidence_type": "physical_actuator_replay",
        "scripted_object_motion": False,
        "physics_claims": ["Every pose comes from MuJoCo integration of the recorded motor targets (Session.step)."],
        "prescribed_quantities": [],
        "hand": recorded,
        "materials": materials,
        "meshes": meshes,
        "geoms": geoms,
        "frames": frames,
        "stage_names": STAGES,
        "playback_speed": 1,
        "physics_control_steps_per_video_frame": stride,
        "probe_only": False,
        "status": "success" if final["success"] else ("failure: " + final["reason"]),
        "initial_sha": session.initial_sha,
        "final_features": {k: v for k, v in final.items() if k != "features"},
        "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        "trajectory_sha256": sha(trajectory),
        "final_state_sha": session.state_sha(),
        "config": {
            "display_title": title,
            "exposure": -0.35,
            "visual_bevel_m": 0.00025,
            "camera": {"position": [1.30, -1.27, 1.78], "target": [0.565, -0.035, 0.97], "lens": 46},
            "light_target": [0.56, 0, 0.92],
            "lights": [
                {"name": "Large warm key", "offset": [-0.5, -0.7, 1.3], "energy": 75, "size": 1.2,
                 "color": [1, 0.92, 0.82]},
                {"name": "Cool window", "offset": [0.6, 0.45, 1.1], "energy": 95, "size": 1, "color": [0.84, 0.92, 1]},
                {"name": "Glass reflection strip", "offset": [-0.5, 0.4, 0.6], "energy": 65, "size": 0.6,
                 "color": [1, 1, 1]},
            ],
        },
        "files": {name: sha(directory / name) for name in ("geometry.npz", "poses.npz")},
    }
    (directory / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    session.close()
    print(json.dumps({"frames": len(frames), "geoms": len(geoms), "status": payload["status"],
                      "final_state_sha": payload["final_state_sha"]}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectory", type=Path, required=True)
    ap.add_argument("--export", type=Path, required=True)
    ap.add_argument("--stride", type=int, default=2)
    args = ap.parse_args()
    export(args.trajectory, args.export, args.stride)
