"""Authoring-only: export the physical picture_hang replay for the Blender studio renderer, then render the PR film.

  python tools/presentation.py export --trajectory solution/trajectory.npz --export <dir> [--stride 2]
  python tools/presentation.py verify --trajectory solution/trajectory.npz --export <dir>
  python tools/presentation.py render --export <dir> --output film.mp4      # Blender 4.5.3 (gpu-slot)

The export holds, for every sampled control, the exact MuJoCo world pose of every visible geom of the replayed
episode (no interpolation), the native verdict, the state hash, the geometry and the print texture, in the bundle
format of the approved T21 scene film's renderer (copied as tools/studio_renderer.py with the approved scene's
materials, lights and cameras). Nothing here steps physics except the replay itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
FAMILY = HERE.parent
sys.path[:0] = [str(FAMILY)]

import numpy as np  # noqa: E402

import replay as R  # noqa: E402
from runtime import Session  # noqa: E402

PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")
APPROVED = {  # the approved T21 scene film's presentation settings (its export config)
    "exposure": -0.8,
    "visual_bevel_m": 0.0007,
    "light_target": [0.55, 0, 1.05],
    "lights": [
        {"name": "Large window", "offset": [-0.9, -0.7, 1.2], "energy": 60, "size": 1.4, "color": [1, 0.94, 0.86]},
        {"name": "Soft room fill", "offset": [-0.4, 0.9, 0.7], "energy": 30.4, "size": 1.2,
         "color": [0.86, 0.93, 1]},
        {"name": "Ceiling bounce", "offset": [0.0, -0.2, 1.6], "energy": 35.2, "size": 1.3, "color": [1, 1, 1]},
    ],
}
# Wave 3 (Marvin arms): the robot stands between the old main camera and the frame, so the main and final views look
# over the robot's right shoulder from the right-front, and the hook close-up looks along the wall from outside the
# left hand.
MAIN = {"position": [-0.80, -2.20, 1.55], "target": [0.42, 0, 0.86], "lens": 28}
HOOK_L = {"position": [0.735, 0.52, 1.40], "target": [0.734, 0.255, 1.382], "lens": 50}
FINAL = {"position": [-0.25, -1.55, 1.50], "target": [0.62, 0, 1.15], "lens": 36}
WALL = {"rgba": [0.65, 0.68, 0.63, 1], "roughness": 0.82, "bump": {"scale": 700, "strength": 0.1, "distance": 6e-05}}
OAK = {"rgba": [0.45, 0.29, 0.17, 1], "roughness": 0.38, "bump": {"scale": 160, "strength": 0.2, "distance": 0.00015}}
FRAME = {"rgba": [0.92, 0.915, 0.89, 1], "roughness": 0.28, "coat": 0.15,
         "bump": {"scale": 900, "strength": 0.08, "distance": 2.5e-05}}
GLASS = {"rgba": [0.97, 0.98, 0.99, 0.08], "roughness": 0.04, "transmission": 0.9, "ior": 1.49}
BRASS = {"rgba": [0.7, 0.49, 0.2, 1], "metallic": 0.82, "roughness": 0.24}
FLOOR = {"rgba": [0.47, 0.45, 0.41, 1], "roughness": 0.8}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def visual_material(name):
    if name == "wall":
        return WALL
    if name.startswith("console"):
        return OAK
    if name.startswith("frame_"):
        return FRAME
    if name == "picture_glazing":
        return GLASS
    if "ring_clip" in name or "ring_wire" in name or name.split("_")[1:2] == ["hook"] and "nail" not in name:
        return BRASS
    if name == "floor":
        return FLOOR
    return None


def camera_for(step, success_step):
    """Main view, then the closer final view from the release on. (Wave 3: no hook close-up: with the arm-mounted
    top grip the hand sits right in front of each hook from every side the camera can take.)"""
    if step >= 540:
        return FINAL
    return MAIN


def export(trajectory, directory, stride=2):
    directory = Path(directory)
    if directory.exists():
        shutil.rmtree(directory)
    (directory / "textures").mkdir(parents=True)
    actions, hand, _ = R.load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    owner = session.checker.body_owner
    ids, geoms, meshes, arrays = [], [], {}, {}
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue  # Sharpa collision meshes (group 3) are not drawn
        name = m.geom(gid).name or f"geom_{gid}"
        if "_wuji_" in name and "_collision" in name:
            continue
        kind = int(m.geom_type[gid])
        mesh = int(m.geom_dataid[gid]) if kind == 7 else None
        record = {"id": gid, "name": name, "body": m.body(int(m.geom_bodyid[gid])).name,
                  "is_hand": owner[int(m.geom_bodyid[gid])] in ("hand_l", "hand_r"), "kind": kind,
                  "size": m.geom_size[gid].tolist(), "material": int(m.geom_matid[gid]),
                  "rgba": m.geom_rgba[gid].tolist(), "mesh": mesh}
        override = visual_material(name)
        if override is not None:
            record["visual_material"] = override
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va:va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa:fa + fn].copy()
            arrays[prefix + "normals"] = np.zeros((0, 3))
            arrays[prefix + "face_normals"] = np.zeros((0, 3), dtype=int)
            has_uv = int(m.mesh_texcoordnum[mesh]) > 0
            if has_uv:
                ta, tn = int(m.mesh_texcoordadr[mesh]), int(m.mesh_texcoordnum[mesh])
                arrays[prefix + "uv"] = m.mesh_texcoord[ta:ta + tn].copy()
                arrays[prefix + "face_uv"] = m.mesh_facetexcoord[fa:fa + fn].copy()
            meshes[str(mesh)] = {"prefix": prefix, "has_uv": has_uv, "name": m.mesh(mesh).name,
                                 "uv_flip_v": True}
        ids.append(gid)
        geoms.append(record)
    materials = []
    for mid in range(m.nmat):
        name = m.material(mid).name
        if name.startswith(("l_hand_", "r_hand_")):
            name = name.split("_")[-1]  # the renderer's hand shading keys on the Sharpa material names
        textures = {}
        tex = int(m.mat_texid[mid, 1])  # mjTEXROLE_RGB
        if tex >= 0:
            # The only textured material is the print: the bundled source PNG, byte for byte (as in the approved
            # T21 film's export).
            shutil.copyfile(FAMILY / "assets/water-lilies.png", directory / "textures" / f"native-{tex}.png")
            textures["1"] = f"textures/native-{tex}.png"
        materials.append({"name": name, "rgba": m.mat_rgba[mid].tolist(), "metallic": -1.0, "roughness": -1.0,
                          "textures": textures})
    np.savez_compressed(directory / "geometry.npz", **arrays)
    frames, positions, rotations, shots = [], [], [], []
    success_step = None

    def sample():
        st = session.status()
        frames.append({"step": session.steps, "time_s": round(session.steps * session.control_dt, 4),
                       "state_sha": session.state_sha(),
                       "status": {"stage": st["stage"], "success": st["success"], "failed": st["failed"],
                                  "reason": st["reason"], "done": st["done"]}})
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())
        shots.append(camera_for(session.steps, success_step))

    sources = {name: sha(FAMILY / name) for name in PHYSICS_SOURCES}
    session.reset()
    sample()
    for i, row in enumerate(actions):
        session.step(row)
        if (i + 1) % stride == 0 or session.done:
            sample()
        if session.done:
            break
    if not session.success:
        raise RuntimeError("the presentation needs a passing physical replay")
    np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob("*")) if p.is_file()}
    payload = {
        "schema_version": 1,
        "title": "Hang a large picture on two wall hooks",
        "task": "picture_hang",
        "evidence_type": "physical_actuator_replay",
        "scripted_object_motion": False,
        "probe_only": False,
        "hand": session.hand,
        "hand_label": "Marvin arms + " + session.hand_info["model"] + " x2",
        "stage_names": ["frame on the console", "lifted, carrying to the wall", "both D-rings on the hooks",
                        "released, hanging"],
        "playback_speed": 1.0,
        "physics_control_steps_per_video_frame": stride,
        "trajectory_sha256": sha(trajectory),
        "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        "initial_sha": session.initial_sha,
        "final_sha": session.state_sha(),
        "status": {k: v for k, v in session.status().items() if k != "features"},
        "source_sha256": sources,
        "geoms": geoms,
        "meshes": meshes,
        "materials": materials,
        "frames": frames,
        "config": {**APPROVED, "display_title": "Hang a large picture on two wall hooks", "camera": MAIN,
                   "camera_frames": shots},
        "files": files,
    }
    (directory / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    session.close()
    print(json.dumps({"frames": len(frames), "final_sha": payload["final_sha"], "success": True,
                      "success_step": payload["status"]["steps"]}))


def verify(trajectory, directory):
    """Replay again and compare every exported pose bit for bit."""
    directory = Path(directory)
    payload = json.loads((directory / "scene.json").read_text())
    poses = np.load(directory / "poses.npz", allow_pickle=False)
    actions, hand, _ = R.load_trajectory(trajectory)
    session = Session(hand=hand)
    ids = [g["id"] for g in payload["geoms"]]
    index = 0

    def compare():
        nonlocal index
        assert payload["frames"][index]["step"] == session.steps
        assert payload["frames"][index]["state_sha"] == session.state_sha()
        assert np.array_equal(poses["positions"][index], session.data.geom_xpos[ids])
        assert np.array_equal(poses["rotations"][index], session.data.geom_xmat[ids].reshape(-1, 3, 3))
        index += 1

    session.reset()
    compare()
    for row in actions:
        session.step(row)
        if index < len(payload["frames"]) and payload["frames"][index]["step"] == session.steps:
            compare()
        if session.done:
            break
    assert index == len(payload["frames"]) and session.success and session.state_sha() == payload["final_sha"]
    print(f"verified {index} exported pose samples against a fresh physical replay")


def render(directory, output, samples, engine, fps, final_hold, limit=0):
    blender = os.environ.get("DEXHAND_BLENDER", "blender")  # Blender 4.5.3 LTS
    command = [sys.executable, str(HERE / "studio_renderer.py"), "--export", str(directory), "--output", str(output),
               "--blender", blender, "--width", "1280", "--height", "720", "--samples", str(samples),
               "--engine", engine, "--fps", str(fps), "--final-hold", str(final_hold)]
    if limit:
        command += ["--limit", str(limit)]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["export", "verify", "render"])
    ap.add_argument("--trajectory", type=Path, default=FAMILY / "solution/trajectory.npz")
    ap.add_argument("--export", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--final-hold", type=float, default=2.0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    elif args.command == "verify":
        verify(args.trajectory, args.export)
    else:
        render(args.export, args.output, args.samples, args.engine, args.fps, args.final_hold, args.limit)
