"""Authoring-only: export the native poses of a physical replay for the Blender studio film (tools/studio_film.py).

The bundle has the layout of the approved T50 film export (scene-v4: scene.json + geometry.npz + poses.npz), so the
T50 studio renderer's materials, lights and camera are reused. Every sampled pose is MuJoCo's own geom_xpos/xmat
of a fresh actuator-only replay of the given trajectory; nothing is prescribed. ``verify`` replays again and checks
every sample bit for bit.

python tools/film_export.py export --trajectory solution/trajectory.npz --export <film dir> --source-scene \
    <approved T50 film export>/scene.json --stride 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runtime import TASK, Session  # noqa: E402
from scene import arm_rig, hands  # noqa: E402

PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")
STAGE_NAMES = ["Head pushed onto the valve and locked", "28 full piston strokes", "Tire pressure target reached",
               "Head unlocked and pulled off the valve", "Released: 1 s hold", "Complete: tire at target pressure, head off"]
WIDTHS = {"sharpa": 58, "wuji": 54}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def visible(model, gid):
    return model.geom_group[gid] <= 2 and model.geom_rgba[gid, 3] > 0 and not (
        (model.geom(gid).name or "").startswith(("r_wuji_", "l_wuji_")) and "_collision" in (model.geom(gid).name or ""))


def export(trajectory, directory, source_scene, stride=3, hold_s=1.5, fps=25):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = hands.read_trajectory(trajectory, widths=WIDTHS, max_rows=5000, task=TASK)
    source = json.loads(Path(source_scene).read_text())
    presentation = {g["name"]: g.get("visual_material") for g in source["geoms"] if g.get("visual_material")}
    session = Session(hand=hand)
    m = session.model
    materials = [{"name": m.material(i).name, "rgba": m.mat_rgba[i].tolist(), "metallic": -1.0, "roughness": -1.0}
                 for i in range(m.nmat)]
    arrays, geoms, meshes, ids = {}, [], {}, []
    arm_bodies = set(arm_rig.robot_body_ids(m))     # Marvin stand + arm links (drawn with their factory finish)
    for gid in range(m.ngeom):
        if not visible(m, gid):
            continue
        name = m.geom(gid).name or f"geom_{gid}"
        owner = session.owner.get(int(m.geom_bodyid[gid]), "world")
        if int(m.geom_bodyid[gid]) in arm_bodies:
            owner = "arm"
        mesh = int(m.geom_dataid[gid]) if int(m.geom_type[gid]) == 7 else None
        record = {
            "id": gid,
            "name": name,
            "kind": int(m.geom_type[gid]),
            "body": m.body(int(m.geom_bodyid[gid])).name or "world",
            "size": m.geom_size[gid].tolist(),
            "mesh": mesh,
            "material": int(m.geom_matid[gid]),
            "rgba": (m.mat_rgba[m.geom_matid[gid]] if m.geom_matid[gid] >= 0 else m.geom_rgba[gid]).tolist(),
            "is_hand": owner == "hand",
        }
        if owner == "arm":
            record["material"] = -1
            record["visual_material"] = {"rgba": record["rgba"], "metallic": 0.15, "roughness": 0.29}
        elif owner != "hand":
            look = presentation.get(name)
            if look is None and name == "rim":
                look = presentation.get("rim_piece_0")
            if look is not None:
                record["visual_material"] = look
            if name == "rim":
                record["authored_cad"] = True  # merged convex rim sectors: flat-shaded like the approved film
        if record["is_hand"] and hand == "wuji":
            # Wuji vendor visual meshes: the same studio shell/rubber split as the Sharpa Wave (dark links rubber).
            record["material"] = -1
            record["visual_material"] = {"rgba": [0.9, 0.92, 0.92, 1] if np.mean(record["rgba"][:3]) > 0.4
                                         else [0.22, 0.29, 0.25, 1], "metallic": 0, "roughness": 0.3}
        geoms.append(record)
        ids.append(gid)
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va: va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa: fa + fn].copy()
            arrays[prefix + "normals"] = np.zeros((0, 3))
            arrays[prefix + "face_normals"] = np.zeros((0, 3), dtype=np.int32)
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name, "has_uv": False}
    np.savez_compressed(directory / "geometry.npz", **arrays)
    frames, positions, rotations = [], [], []

    def sample():
        f = session.status()
        frames.append({
            "step": session.steps,
            "time_s": float(session.data.time),
            "state_sha": session.state_sha(),
            "status": {"stage": int(f["stage"]), "success": bool(f["success"]), "done": bool(f["done"]),
                       "failed": bool(f["failed"]), "reason": f["reason"], "strokes": int(f["strokes"]),
                       "tire_gauge_pa": float(f["tire_gauge_pa"]), "piston_depth_m": float(f["piston_depth_m"]),
                       "released_hold_steps": int(f["released_hold_steps"]),
                       "head_connected": bool(f["head_connected"]),
                       "head_disconnected": bool(f["head_disconnected"])},
        })
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    sample()
    for i, action in enumerate(actions):
        session.step(action)
        if (i + 1) % stride == 0 or session.done:
            sample()
        if session.done:
            break
    final = session.status()
    # The final state is held on screen (a still of the last native sample, not new motion).
    hold_frames = round(hold_s * fps)
    for _ in range(hold_frames):
        frames.append(dict(frames[-1], held=True))
        positions.append(positions[-1])
        rotations.append(rotations[-1])
    np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    config = dict(source["config"])
    config["display_title"] = "Inflate a tire with a portable bicycle pump"
    payload = {
        "task": TASK,
        "title": "Inflate a tire with a portable bicycle pump",
        "hand": hand,
        "hand_model": session.hand_info["model"],
        "config": config,
        "materials": materials,
        "geoms": geoms,
        "meshes": meshes,
        "frames": frames,
        "fps": fps,
        "stride": stride,
        "playback_speed": stride * session.control_dt * fps,
        "held_final_frames": hold_frames,
        "probe_only": False,
        "status": {k: final[k] for k in ("success", "reason", "steps", "strokes", "tire_gauge_pa", "stage")},
        "stage_names": STAGE_NAMES,
        "evidence_type": "physical_actuator_replay",
        "validation_mode": "physical_actuator_replay",
        "scripted_object_motion": False,
        "trajectory_sha256": sha(trajectory),
        "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        "initial_sha": session.initial_sha,
        "final_sha": session.state_sha(),
        "source_sha256": {name: sha(HERE / name) for name in PHYSICS_SOURCES},
        "files": {name: sha(directory / name) for name in ("geometry.npz", "poses.npz")},
    }
    (directory / "scene.json").write_text(json.dumps(payload, indent=1, default=float) + "\n")
    session.close()
    print(json.dumps({"frames": len(frames), "geoms": len(geoms), "success": final["success"],
                      "steps": final["steps"], "final_sha": payload["final_sha"]}))


def verify(trajectory, directory):
    directory = Path(directory)
    payload = json.loads((directory / "scene.json").read_text())
    for name, expected in payload["files"].items():
        assert sha(directory / name) == expected, name
    poses = np.load(directory / "poses.npz")
    actions, hand, _ = hands.read_trajectory(trajectory, widths=WIDTHS, max_rows=5000, task=TASK)
    session = Session(hand=hand)
    ids = [g["id"] for g in payload["geoms"]]
    live = [k for k, f in enumerate(payload["frames"]) if not f.get("held")]
    index = 0

    def compare():
        nonlocal index
        k = live[index]
        assert payload["frames"][k]["state_sha"] == session.state_sha()
        assert np.array_equal(poses["positions"][k], session.data.geom_xpos[ids])
        assert np.array_equal(poses["rotations"][k], session.data.geom_xmat[ids].reshape(-1, 3, 3))
        index += 1

    compare()
    for action in actions:
        session.step(action)
        if index < len(live) and payload["frames"][live[index]]["step"] == session.steps:
            compare()
        if session.done:
            break
    assert index == len(live) and session.state_sha() == payload["final_sha"]
    print(f"verified {index} native pose samples; final {session.status()['reason']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "verify"])
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--source-scene", type=Path)
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--hold-s", type=float, default=1.5)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.source_scene, args.stride, args.hold_s)
    else:
        verify(args.trajectory, args.export)
