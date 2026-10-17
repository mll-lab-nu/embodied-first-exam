"""Authoring film (not shipped): export exact native poses of a passing replay, render with Blender, encode the film.

    python presentation.py export --trajectory solution/trajectory.npz --export film_export --stride 5
    DEXHAND_BLENDER=<blender 4.5.3> python studio_renderer.py --export film_export --output film.mp4 \
        --engine eevee --width 1280 --height 720 --samples 32 --frames-only
    python presentation.py encode --export film_export --output film.mp4 --fps 20

The export replays the trajectory in a fresh Session and samples every ``stride`` controls; the renderer applies the
saved geom transforms only (no interpolation, no synthesized motion). Visual finishes follow the approved T27 scene
film (pale pine grain, grey table, metal screws, same camera and lights).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np

from replay import load_trajectory
from runtime import Session

HERE = Path(__file__).resolve().parent
TITLE = "Assemble a wooden stool cross brace"
STAGE_NAMES = ["initial loose parts", "brace lifted", "brace dowel seated", "side frame lifted",
               "all eight dowels seated"]
PINE = {"rgba": [0.83, 0.72, 0.54, 1], "roughness": 0.52, "textures": {"base_color": "pine-grain.png"},
        "bump": {"scale": 160, "strength": 0.12, "distance": 3.5e-05}}
CONFIG = {  # the approved T27 film's studio configuration
    "display_title": TITLE,
    "exposure": -1.1,
    "visual_bevel_m": 0.0007,
    "camera": {"position": [1.85, -1.35, 1.92], "target": [0.70, 0.08, 0.95], "lens": 50},
    "light_target": [0.65, 0.05, 0.9],
    "lights": [
        {"name": "Warm large softbox", "offset": [0.1, -1.2, 1.4], "energy": 341.0, "size": 1.5, "color": [1, 0.94, 0.87]},
        {"name": "Soft cool fill", "offset": [1, 0.3, 0.9], "energy": 173.6, "size": 1.2, "color": [0.85, 0.92, 1]},
        {"name": "Rear edge", "offset": [-0.8, 0.8, 1.3], "energy": 217.0, "size": 1.4, "color": [1, 1, 1]},
    ],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finish(name, owner, kind):
    if name == "floor":
        return {"rgba": [0.53, 0.56, 0.54, 1], "roughness": 0.85}
    if name == "table":
        return {"rgba": [0.34, 0.38, 0.38, 1], "roughness": 0.62, "coat": 0.08,
                "bump": {"scale": 450, "strength": 0.1, "distance": 2e-05}}
    if name.startswith("table_leg"):
        return {"rgba": [0.65, 0.67, 0.65, 1], "roughness": 0.62, "coat": 0.06}
    if name.startswith("screw_"):
        return {"rgba": [0.8, 0.81, 0.8, 1], "metallic": 0.85, "roughness": 0.25}
    if "_dowel_" in name:
        return {"rgba": [0.74, 0.58, 0.38, 1], "roughness": 0.55,
                "bump": {"scale": 300, "strength": 0.08, "distance": 2e-05}}
    if owner == "hand":
        return None
    return PINE


def export(trajectory, directory, stride=5):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _names = load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    arrays, geoms, meshes, materials = {}, [], {}, []
    material_index = {}
    ids = []
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue
        name = m.geom(gid).name or f"geom_{gid}"
        owner = session.owner.get(int(m.geom_bodyid[gid]), "world")
        kind = int(m.geom_type[gid])
        mesh = int(m.geom_dataid[gid]) if kind == 7 else None
        mid = int(m.geom_matid[gid])
        record = {"id": gid, "name": "ordinary_table" if name == "table" else name, "kind": kind,
                  "size": m.geom_size[gid].tolist(), "mesh": mesh, "material": -1,
                  "rgba": m.geom_rgba[gid].tolist(), "is_hand": owner == "hand", "authored_cad": owner != "hand"}
        if owner == "hand" and mid >= 0:
            mat_name = m.material(mid).name
            if mat_name not in material_index:
                material_index[mat_name] = len(materials)
                materials.append({"name": mat_name, "rgba": m.mat_rgba[mid].tolist(), "roughness": 0.35})
            record["material"] = material_index[mat_name]
        visual = finish(name, owner, kind)
        if visual is not None:
            record["visual_material"] = visual
        if mesh is not None and str(mesh) not in meshes:
            prefix = f"mesh_{mesh}_"
            for label, adr, num, arr in (("vertices", m.mesh_vertadr, m.mesh_vertnum, m.mesh_vert),
                                         ("faces", m.mesh_faceadr, m.mesh_facenum, m.mesh_face),
                                         ("normals", m.mesh_normaladr, m.mesh_normalnum, m.mesh_normal),
                                         ("face_normals", m.mesh_faceadr, m.mesh_facenum, m.mesh_facenormal)):
                a, n = int(adr[mesh]), int(num[mesh])
                arrays[prefix + label] = arr[a : a + n].copy()
            textured = owner != "hand"
            if textured:
                arrays[prefix + "uv"] = arrays[prefix + "vertices"][:, :2] * 12 + 0.5
                arrays[prefix + "face_uv"] = arrays[prefix + "faces"].copy()
            meshes[str(mesh)] = {"name": m.mesh(mesh).name, "prefix": prefix, "has_uv": textured, "uv_flip_v": False}
        geoms.append(record)
        ids.append(gid)
    np.savez_compressed(directory / "geometry.npz", **arrays)
    shutil.copy2(HERE / "assets/pine-grain.png", directory / "pine-grain.png")
    frames, positions, rotations = [], [], []

    def sample():
        st = session.status()
        frames.append({"step": session.steps, "time_s": round(session.steps * session.control_dt, 4),
                       "status": {"stage": st["stage"], "success": bool(st["success"]), "failed": bool(st["failed"]),
                                  "done": bool(st["done"]), "reason": st["reason"],
                                  "seated_interfaces": st["seated_interfaces"]},
                       "state_sha": session.state_sha()})
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    try:
        sample()
        for i, action in enumerate(actions):
            session.step(action)
            if (i + 1) % stride == 0 or session.done:
                sample()
            if session.done:
                break
        if not session.success:
            raise RuntimeError("The film requires a passing native replay")
        np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
        files = {p.name: sha(p) for p in sorted(directory.iterdir()) if p.is_file() and p.name != "scene.json"}
        payload = {
            "schema_version": 1,
            "task": "stool_brace_insert",
            "title": TITLE,
            "config": CONFIG,
            "evidence_type": "physical_actuator_replay",
            "scripted_object_motion": False,
            "hand": session.hand,
            "hand_model": session.hand_info["model"],
            "materials": materials,
            "meshes": meshes,
            "geoms": geoms,
            "frames": frames,
            "fps": 20,
            "stride": stride,
            "playback_speed": stride * session.control_dt * 20,
            "probe_only": False,
            "stage_names": STAGE_NAMES,
            "status": frames[-1]["status"],
            "trajectory_sha256": sha(trajectory),
            "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
            "initial_sha": session.initial_sha,
            "final_sha": session.state_sha(),
            "files": files,
        }
        (directory / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    finally:
        session.close()
    print(json.dumps({"frames": len(frames), "final_sha": payload["final_sha"], "success": True}))


def encode(directory, output, fps=20, hold_s=2.0, crf=23):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    directory, output = Path(directory), Path(output)
    payload = json.loads((directory / "scene.json").read_text())
    frames_dir = output.with_suffix("").with_name(output.stem + "-frames")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    speed = payload["playback_speed"]

    def card(index):
        frame = payload["frames"][index]
        status = frame["status"]
        pic = Image.open(frames_dir / f"{index:06d}.png").convert("RGB")
        draw = ImageDraw.Draw(pic)
        title = f"{TITLE} · {payload['hand_model']}"
        verdict = "PASS" if status["success"] else ("FAIL: " + status["reason"]) if status["failed"] else "IN PROGRESS"
        detail = f"{verdict} · physics replay, {speed:g}x · {frame['time_s']:.1f} s"
        stage = STAGE_NAMES[min(status["stage"], 4)]
        footer = f"stage {status['stage']}/4: {stage} · dowels seated {status['seated_interfaces']}/8"
        width = max(draw.textlength(title, font=font), draw.textlength(detail, font=small)) + 28
        draw.rounded_rectangle((20, 18, 20 + width, 75), radius=7, fill=(245, 244, 237))
        draw.text((32, 25), title, font=font, fill=(35, 45, 40))
        draw.text((32, 50), detail, font=small, fill=(61, 104, 75) if status["success"] else (90, 94, 88))
        fw = draw.textlength(footer, font=small) + 20
        bottom = pic.height - 18
        draw.rounded_rectangle((20, bottom - 28, 20 + fw, bottom), radius=4, fill=(245, 244, 237))
        draw.text((30, bottom - 22), footer, font=small, fill=(90, 94, 88))
        return np.asarray(pic)

    count = len(payload["frames"])
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1, pixelformat="yuv420p",
                            ffmpeg_params=["-threads", "2", "-crf", str(crf), "-preset", "slow",
                                           "-movflags", "+faststart"]) as writer:
        for index in range(count):
            frame = card(index)
            writer.append_data(frame)
        # The episode ends at success; the last native state is shown for a short still (no new motion).
        for _ in range(round(fps * hold_s)):
            writer.append_data(frame)
    Image.fromarray(frame).save(output.with_suffix(".png"))
    report = {"video": output.name, "video_sha256": sha(output), "bytes": output.stat().st_size, "fps": fps,
              "frames": count, "final_hold_s": hold_s, "playback_speed": speed, "hand": payload["hand"],
              "trajectory_sha256": payload["trajectory_sha256"], "final_sha": payload["final_sha"],
              "export_manifest_sha256": sha(directory / "scene.json"), "renderer": "Blender 4.5.3 (studio_renderer.py)",
              "presentation_only": True, "scripted_object_motion": False}
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=5)
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--crf", type=int, default=23)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    else:
        encode(args.export, args.output, args.fps, crf=args.crf)
