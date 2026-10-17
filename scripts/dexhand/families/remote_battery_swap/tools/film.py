"""Authoring-only PR film: export exact native poses of a physical replay, render them in Blender, encode an mp4.

    python tools/film.py export --trajectory solution/trajectory.npz --export out/film --stride 4
    python tools/film.py render --export out/film --output out/remote_battery_swap.mp4 [--engine eevee|cycles]

`export` replays the rows in MuJoCo (the task's own Session) and stores, every `stride` controls, the world pose of
every visible geom; Blender only re-draws those poses with presentation materials (no motion is synthesized or
interpolated). Pattern: families/assemble_hamburger/presentation.py; look: the approved T07 studio film.
"""

from __future__ import annotations

import argparse
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

sys.path.append(str(HERE.parents[1] / "shared"))
import arm_rig  # noqa: E402

BLENDER = os.environ.get("BLENDER", "blender")  # Blender 4.5.3 LTS (authoring films only)
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")
# collision-only geoms that are real visible features of the remote (group 3 in the MJCF)
EXTRA_VISIBLE = ("cradle_rib_neg", "cradle_rib_pos", "positive_terminal_block", "negative_terminal_block")
TITLE = "Replace the remote battery"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(trajectory, directory, stride=4, hand_filter=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = hands.read_trajectory(trajectory, widths={"sharpa": 58, "wuji": 54}, max_rows=6000,
                                             task="remote_battery_swap")
    session = Session(hand=hand)
    m = session.model
    owner = dict(session.owner)
    for body in arm_rig.robot_body_ids(m):  # stand + arm links: their own (factory) materials in the film
        owner[body] = "arm"
    arrays, geoms, meshes, ids = {}, [], {}, []
    for gid in range(m.ngeom):
        name = m.geom(gid).name or f"geom_{gid}"
        visible = (m.geom_group[gid] <= 2 and m.geom_rgba[gid, 3] > 0) or name in EXTRA_VISIBLE
        if not visible or name == "floor":
            continue
        if name.startswith(("r_wuji_", "l_wuji_")) and "_collision" in name:
            continue
        kind = int(m.geom_type[gid])
        mesh = int(m.geom_dataid[gid]) if kind == 7 else None
        mid = int(m.geom_matid[gid])
        ids.append(gid)
        geoms.append({
            "id": gid, "name": name, "kind": kind, "size": m.geom_size[gid].tolist(), "mesh": mesh,
            "owner": owner.get(int(m.geom_bodyid[gid]), "world"),
            "material": m.material(mid).name if mid >= 0 else "",
            "rgba": (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist(),
        })
        if mesh is not None and str(mesh) not in meshes:
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            prefix = f"mesh_{mesh}_"
            arrays[prefix + "vertices"] = m.mesh_vert[va:va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa:fa + fn].copy()
            ta, tn = int(m.mesh_texcoordadr[mesh]), int(m.mesh_texcoordnum[mesh])
            if ta >= 0 and tn > 0:
                uv = m.mesh_texcoord[ta:ta + tn]
                arrays[prefix + "corner_uv"] = uv[m.mesh_facetexcoord[fa:fa + fn]].copy()
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name, "has_uv": prefix + "corner_uv" in arrays}
    np.savez_compressed(directory / "geometry.npz", **arrays)
    for texture in ("new_aa_wrap.png", "old_aa_wrap.png"):
        shutil.copyfile(HERE / "assets" / texture, directory / texture)
    phases_file = Path(trajectory).with_name("phases.npz")
    phases = (np.load(phases_file)["phases"] if phases_file.is_file() else np.full(len(actions), "actuator replay"))
    frames, positions, rotations = [], [], []

    def sample(phase):
        f = session.features()
        frames.append({"step": session.steps, "phase": str(phase), "state_sha": session.state_sha(),
                       "success": bool(session.success), "failure": session.failure,
                       "stages": f.get("stages_latched", {}), "hold_steps": f.get("hold_steps", 0),
                       "stage": f.get("stage", 0)})
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    sample("initial state")
    for i, row in enumerate(actions):
        session.step(row)
        if (i + 1) % stride == 0 or session.done:
            sample(phases[i] if i < len(phases) else "")
        if session.done:
            break
    np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    files = {p.name: sha(p) for p in sorted(directory.iterdir()) if p.is_file() and p.name != "scene.json"}
    payload = {
        "task": "remote_battery_swap", "title": TITLE, "hand": hand, "hand_model": session.hand_info["model"],
        "evidence_type": "physical_actuator_replay", "scripted_object_motion": False,
        "trajectory_sha256": sha(trajectory), "final_sha": session.state_sha(), "success": bool(session.success),
        "failure": session.failure, "steps": session.steps,
        "source_sha256": {name: sha(HERE / name) for name in PHYSICS_SOURCES},
        "files": files, "geoms": geoms, "meshes": meshes, "frames": frames, "control_dt": session.control_dt,
        "stride": stride, "fps": 25, "playback_speed": stride * session.control_dt * 25,
        "floor_z": session.config.get("floor_z", 0.0),
    }
    (directory / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    session.close()
    print(json.dumps({"frames": len(frames), "success": payload["success"], "failure": payload["failure"],
                      "steps": payload["steps"], "final_sha": payload["final_sha"]}))


def encode(directory, output, max_mb=9.0):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont

    directory, output = Path(directory), Path(output)
    payload = json.loads((directory / "scene.json").read_text())
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    fps = payload["fps"]
    big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 19)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    speed = f"{payload['playback_speed'] * manifest.get('frame_step', 1):g}"
    crf = 20
    while True:
        last = None
        with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1,
                                ffmpeg_params=["-crf", str(crf), "-preset", "slow", "-pix_fmt", "yuv420p",
                                               "-movflags", "+faststart"]) as writer:
            for index in manifest["indices"]:
                pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
                record = payload["frames"][index]
                draw = ImageDraw.Draw(pic, "RGBA")
                draw.rounded_rectangle((18, 16, 470, 74), radius=9, fill=(250, 246, 240, 225))
                draw.text((32, 22), TITLE, font=big, fill=(38, 42, 46))
                state = "SUCCESS" if record["success"] else ("FAIL: " + record["failure"] if record["failure"] else "")
                draw.text((32, 48), f"{payload['hand_model']}  ·  physics replay, {speed}x"
                          + (f"  ·  {state}" if state else ""), font=small,
                          fill=(46, 120, 70) if record["success"] else (90, 96, 100))
                stages = record["stages"]
                marks = [("door open", "cover_open"), ("old AA in tray", "old_cell_in_tray"),
                         ("new AA seated (+ to gold)", "new_cell_seated"), ("door shut + latched", "cover_closed")]
                text = "   ".join(("✓ " if stages.get(key) else "○ ") + label for label, key in marks)
                w = draw.textlength(text, font=small)
                draw.rounded_rectangle((18, 688, 36 + w, 712), radius=7, fill=(250, 246, 240, 210))
                draw.text((27, 691), text, font=small, fill=(60, 66, 70))
                writer.append_data(np.asarray(pic))
                last = pic
            for _ in range(round(fps * 2)):
                writer.append_data(np.asarray(last))
        if output.stat().st_size <= max_mb * 1e6 or crf >= 32:
            break
        crf += 3
    last.save(output.with_suffix(".png"))
    report = {"renderer": "Blender " + manifest.get("blender_version", "") + " " + manifest["engine"],
              "presentation_only": True, "scripted_object_motion": False,
              "trajectory_sha256": payload["trajectory_sha256"], "native_final_sha": payload["final_sha"],
              "native_success": payload["success"], "crf": crf,
              "playback_speed": payload["playback_speed"] * manifest.get("frame_step", 1),
              "video_sha256": sha(output), "bytes": output.stat().st_size, "render": manifest}
    output.with_suffix(".json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({"video": str(output), "bytes": output.stat().st_size, "crf": crf}))


def render(directory, output, engine, samples, limit=None, frame_step=1):
    command = [BLENDER, "-b", "-t", "8", "-P", str(HERE / "tools/studio_renderer.py"), "--", "--export",
               str(directory), "--output", str(output), "--engine", engine, "--samples", str(samples),
               "--frame-step", str(frame_step)]
    if limit:
        command += ["--limit", str(limit)]
    env = os.environ.copy()
    if not env.get("__EGL_VENDOR_LIBRARY_FILENAMES"):
        library = ctypes.util.find_library("EGL_nvidia")
        if library:
            vendor = Path(output).with_suffix(".egl-vendor.json").resolve()
            vendor.write_text(json.dumps({"file_format_version": "1.0.0", "ICD": {"library_path": library}}) + "\n")
            env["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(vendor)
    env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with Path(output).with_suffix(".render.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, env=env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "render", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--frame-step", type=int, default=1)
    a = parser.parse_args()
    if a.command == "export":
        export(a.trajectory, a.export, a.stride)
    elif a.command == "render":
        render(a.export, a.output, a.engine, a.samples, a.limit, a.frame_step)
        if not a.limit:
            encode(a.export, a.output)
    else:
        encode(a.export, a.output)
