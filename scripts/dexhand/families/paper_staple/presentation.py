"""Authoring film: export native MuJoCo poses of a replayed paper_staple episode for the T36 studio renderer.

The bundle (scene.json + geometry.npz + poses.npz) follows the scene-expansion studio-renderer format, labelled
``physical_actuator_replay`` (no scripted object motion: every pose is read from the physics replay of the rows).
Materials, lights, exposure and camera direction reuse the approved T36 film's presentation config.

    python presentation.py export --traj solution/trajectory.npz --out out/ps-film/export
    gpu-slot python studio_renderer.py --export out/ps-film/export --output out/ps-film/paper_staple.mp4 \
        --engine eevee --width 1280 --height 720 --samples 32 --fps 25
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from replay import load_trajectory
from runtime import Session

HERE = Path(__file__).resolve().parent
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")
STAGE_NAMES = [
    "Misaligned sheets, corner on the anvil mouth",
    "Sheets squared",
    "Corner fed into the throat",
    "Head pressed to its bottom stop",
    "Head released, 1 s hold",
]
DESK = {"rgba": [0.37, 0.28, 0.21, 1], "roughness": 0.65, "bump": {"scale": 220, "strength": 0.17, "distance": 0.0001}}
BLUE = {"rgba": [0.045, 0.15, 0.34, 1], "roughness": 0.26, "coat": 0.3}
STEEL = {"rgba": [0.72, 0.76, 0.8, 1], "roughness": 0.2, "metallic": 0.92}
RUBBER = {"rgba": [0.035, 0.036, 0.037, 1], "roughness": 0.85}
PAPER = {"rgba": [0.965, 0.955, 0.915, 1], "roughness": 0.8, "bump": {"scale": 6000, "strength": 0.15, "distance": 1e-05}}
INK = {"rgba": [0.16, 0.18, 0.16, 1], "roughness": 0.5}
FLOOR = {"rgba": [0.65, 0.66, 0.63, 1], "roughness": 0.5}
CONFIG = {
    "camera": {"position": [1.38, 0.52, 1.36], "target": [0.66, -0.16, 0.86], "lens": 36},
    "light_target": [0.66, -0.06, 0.81],
    "exposure": -0.8,
    "visual_bevel_m": 0.00028,
    "lights": [  # the approved T36 film's three area lights
        {"name": "Soft key", "offset": [0.12, -0.3, 0.85], "energy": 75, "size": 0.75, "color": [1, 0.92, 0.84]},
        {"name": "Fill", "offset": [-0.45, 0.1, 0.6], "energy": 35, "size": 0.65, "color": [0.8, 0.88, 1]},
        {"name": "Blue shell edge", "offset": [0.18, 0.5, 0.65], "energy": 55, "size": 0.6, "color": [1, 0.96, 0.89]},
    ],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def presentation_material(name):
    if name.startswith("desk"):
        return DESK
    if name in ("stapler_base_shell", "stapler_handle_shell"):
        return BLUE
    if name == "rubber_sole":
        return RUBBER
    if name.startswith("sheet_") and name.endswith("_plate"):
        return PAPER
    if "_print_" in name:
        return INK
    if name == "floor":
        return FLOOR
    if name.startswith(("anvil", "magazine", "front_driver", "driver_blade", "paper_stop", "rear_pivot", "return_coil",
                        "feed_tab", "staple_strip")):
        return STEEL
    return None


def export(trajectory, directory, stride=2):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    is_hand = session.checker.is_hand
    arrays, geoms, meshes, ids = {}, [], {}, []
    materials = []
    for mid in range(m.nmat):
        materials.append({"name": m.material(mid).name, "rgba": m.mat_rgba[mid].tolist(), "roughness": 0.35})
    for gid in range(m.ngeom):
        rgba = m.mat_rgba[m.geom_matid[gid]] if m.geom_matid[gid] >= 0 else m.geom_rgba[gid]
        if m.geom_group[gid] > 2 or rgba[3] == 0:
            continue
        name = m.geom(gid).name or f"geom_{gid}"
        if is_hand[gid] and m.geom_contype[gid] and m.geom_group[gid] != 2:
            continue  # collision proxies of the hand are not drawn
        kind = int(m.geom_type[gid])
        mesh = int(m.geom_dataid[gid]) if kind == 7 else None
        record = {"id": gid, "name": name, "kind": kind, "size": m.geom_size[gid].tolist(), "mesh": mesh,
                  "material": int(m.geom_matid[gid]), "rgba": rgba.tolist(), "is_hand": bool(is_hand[gid]),
                  "authored_cad": name.startswith(("anvil_wall", "desk"))}
        override = presentation_material(name)
        if override is not None:
            record["visual_material"] = override
        geoms.append(record)
        ids.append(gid)
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va: va + vn].astype(np.float64)
            arrays[prefix + "faces"] = m.mesh_face[fa: fa + fn].copy()
            arrays[prefix + "normals"] = np.zeros((0, 3))
            arrays[prefix + "face_normals"] = np.zeros((0, 3), dtype=np.int32)
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name, "has_uv": False}
    np.savez_compressed(directory / "geometry.npz", **arrays)
    frames, positions, rotations = [], [], []

    def sample():
        st = session.status()
        frames.append({"step": session.steps, "time_s": float(session.steps * session.control_dt),
                       "state_sha": session.state_sha(),
                       "status": {"stage": st["stage"], "success": st["success"], "failed": st["failed"],
                                  "done": st["done"], "reason": st["reason"]}})
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    sample()
    for i, action in enumerate(actions):
        session.step(action)
        if (i + 1) % stride == 0 or session.done:
            sample()
        if session.done:
            break
    np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    final = session.status()
    title = f"Align and staple three sheets · {session.hand_info['model']} on a Marvin arm"
    payload = {
        "task": "paper_staple",
        "title": title,
        "evidence_type": "physical_actuator_replay",
        "scripted_object_motion": False,
        "prescribed_quantities": [],
        "probe_only": False,
        "playback_speed": 1,
        "stage_names": STAGE_NAMES,
        "frames": frames,
        "geoms": geoms,
        "meshes": meshes,
        "materials": materials,
        "config": {**CONFIG, "display_title": title},
        "status": "success" if final["success"] else final["reason"] or "incomplete",
        "initial_sha": session.initial_sha,
        "final_features": {k: final[k] for k in ("stage", "success", "reason", "steps", "corner_offsets_m",
                                                 "staple_margins_m", "head_angle_rad")},
        "trajectory_sha256": sha(trajectory),
        "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        "physics_sources_sha256": {name: sha(HERE / name) for name in PHYSICS_SOURCES},
        "physics_control_steps_per_video_frame": stride,
        "physics_claims": ["Every pose is read from a physics replay of the actuator rows (MuJoCo 3.4.0); no object "
                           "pose is prescribed. Staple formation is not simulated."],
        "files": {},
    }
    payload["files"] = {name: sha(directory / name) for name in ("geometry.npz", "poses.npz")}
    (directory / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps({"frames": len(frames), "geoms": len(geoms), "status": payload["status"],
                      "final_state_sha": frames[-1]["state_sha"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--traj", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--stride", type=int, default=2)
    a = parser.parse_args()
    export(a.traj, a.out, a.stride)
