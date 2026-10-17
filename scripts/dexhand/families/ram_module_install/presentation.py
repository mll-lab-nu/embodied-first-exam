"""Authoring film (not shipped): export exact native poses of the physical oracle replay, render them with the T28
studio look in Blender 4.5.3 (studio_renderer.py), and encode a captioned H.264 film.

Every rendered pose is a sampled MuJoCo state of the actuator-only replay (no object or hand motion is synthesized or
interpolated); only surfaces, lights and cameras are presentation choices, taken from the accepted T28 scene film.
"""

from __future__ import annotations

import argparse
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import subprocess

import mujoco
import numpy as np
from PIL import Image

from replay import load_actions
from runtime import Session

HERE = Path(__file__).resolve().parent
BLENDER = os.environ.get("BLENDER", "blender")
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")
TITLE = "Install a desktop RAM module"

# The T28 film's camera (zooming from the bench overview to the outer socket), Blender lens in mm.
WIDE = dict(position=[1.03, -0.50, 1.10], target=[0.69, -0.10, 0.875], lens=36.0)
CLOSE = dict(position=[0.80, -0.22, 1.025], target=[0.576, 0.004, 0.862], lens=46.0)
LIGHTS = [  # T28 lighting r3 (offsets from the light target), plus its diffuse front socket fill
    dict(name="Bench softbox", offset=[0.1, -0.25, 0.45], energy=2.8, size=0.5, color=[1, 0.94, 0.87]),
    dict(name="Cool PCB fill", offset=[0.25, 0.25, 0.3], energy=1.8, size=0.4, color=[0.85, 0.94, 1]),
    dict(name="Edge highlight", offset=[-0.3, 0.12, 0.38], energy=2.0, size=0.3, color=[1, 1, 1]),
    dict(name="Diffuse front socket fill", offset=[0.38, -0.06, 0.20], energy=2.4, size=0.40, color=[1, 0.97, 0.94]),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def camera_for(step, zoom_start, zoom_end):
    a = smooth((step - zoom_start) / max(1, zoom_end - zoom_start))
    return {k: (np.asarray(WIDE[k]) + (np.asarray(CLOSE[k]) - np.asarray(WIDE[k])) * a).tolist() for k in WIDE}


def materials_of(model, directory):
    (directory / "textures").mkdir(exist_ok=True)
    records = []
    for mid in range(model.nmat):
        name = model.mat(mid).name
        record = dict(name=name, rgba=model.mat_rgba[mid].tolist(), metallic=0.0, roughness=0.4, textures={})
        # T28 export_utils finishes (visual only)
        if name in ("gold", "brass", "steel", "aluminium"):
            record.update(metallic=0.8, roughness=0.27)
        if name == "pcb":
            record.update(rgba=[0.035, 0.36, 0.17, 1], roughness=0.45)
        if name in ("black", "chip"):
            record.update(rgba=[0.11, 0.12, 0.13, 1], roughness=0.38)
        if name == "board":
            record.update(rgba=[0.16, 0.19, 0.21, 1], roughness=0.57)
        if name == "foam":
            record.update(roughness=0.9)
        for role, tid in enumerate(model.mat_texid[mid]):
            if tid < 0 or int(model.tex_type[tid]) != int(mujoco.mjtTexture.mjTEXTURE_2D):
                continue
            h, w, c = int(model.tex_height[tid]), int(model.tex_width[tid]), int(model.tex_nchannel[tid])
            pixels = model.tex_data[int(model.tex_adr[tid]) : int(model.tex_adr[tid]) + h * w * c].reshape(h, w, c)
            relative = f"textures/native-{tid}.png"
            Image.fromarray(pixels).save(directory / relative)
            record["textures"][str(role)] = relative
        records.append(record)
    return records


def export(trajectory, directory, stride=4):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sources = {name: sha(HERE / name) for name in PHYSICS_SOURCES}
    session = Session()
    m = session.model
    owner = session.checker.owner
    arrays, geoms, meshes, ids = {}, [], {}, []
    for gid in range(m.ngeom):
        if m.geom_group[gid] > 2 or m.geom_rgba[gid, 3] == 0:
            continue
        kind, mid = int(m.geom_type[gid]), int(m.geom_matid[gid])
        mesh = int(m.geom_dataid[gid]) if kind == 7 else None
        body = m.body(int(m.geom_bodyid[gid])).name
        record = dict(id=gid, name=m.geom(gid).name or f"geom_{gid}", body=body,
                      is_hand=owner.get(int(m.geom_bodyid[gid])) == "hand", kind=kind, size=m.geom_size[gid].tolist(),
                      material=mid, rgba=(m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist(), mesh=mesh)
        if record["name"].startswith("pcb_") or record["name"] in ("fixed_catch", "latch_catch"):
            record["authored_cad"] = True
        if body.startswith("socket_"):  # T28 lighting r3 dark-polymer separation
            record["visual_material"] = dict(rgba=[0.13, 0.14, 0.15, 1], roughness=0.73)
        elif body in ("moving_latch", "fixed_retainer"):
            record["visual_material"] = dict(rgba=[0.17, 0.18, 0.19, 1], roughness=0.73)
        if mesh is not None and str(mesh) not in meshes:
            prefix = f"mesh_{mesh}_"
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            na, nn = int(m.mesh_normaladr[mesh]), int(m.mesh_normalnum[mesh])
            arrays[prefix + "vertices"] = m.mesh_vert[va : va + vn].copy()
            arrays[prefix + "faces"] = m.mesh_face[fa : fa + fn].copy()
            arrays[prefix + "normals"] = m.mesh_normal[na : na + nn].copy()
            arrays[prefix + "face_normals"] = m.mesh_facenormal[fa : fa + fn].copy()
            meshes[str(mesh)] = dict(prefix=prefix, name=m.mesh(mesh).name)
        ids.append(gid)
        geoms.append(record)
    materials = materials_of(m, directory)
    np.savez_compressed(directory / "geometry.npz", **arrays)
    actions = load_actions(trajectory)
    phases_path = Path(trajectory).with_suffix(".phases.npy")
    phases = np.load(phases_path) if phases_path.is_file() else np.full(len(actions), "actuator replay")
    frames, positions, rotations = [], [], []

    def sample(phase):
        frames.append(dict(step=session.steps, time_s=round(float(session.data.time), 4), phase=str(phase),
                           state_sha=session.state_sha(), features=session.features()))
        positions.append(session.data.geom_xpos[ids].copy())
        rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    try:
        sample("module in its foam holder")
        for i, action in enumerate(actions):
            session.step(action)
            if (i + 1) % stride == 0 or session.done:
                sample(phases[i])
            if session.done:
                break
        if not session.success:
            raise RuntimeError("The film requires a passing complete native replay")
        steps = [f["step"] for f in frames]
        carry = [i for i, p in enumerate(phases) if str(p).startswith("carry")]
        zoom_start, zoom_end = (carry[0], carry[-1] + 120) if carry else (300, 600)
        for f in frames:
            f["camera"] = camera_for(f["step"], zoom_start, zoom_end)
        np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
        if sources != {name: sha(HERE / name) for name in PHYSICS_SOURCES}:
            raise RuntimeError("Physics sources changed during export")
        files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob("*"))
                 if p.is_file() and p.name != "scene.json" and "frames" not in p.parts}
        payload = dict(
            schema_version=1, task="ram_module_install", title=TITLE, evidence_type="physical_actuator_replay",
            scripted_object_motion=False, trajectory_sha256=sha(trajectory),
            model_xml_sha256=hashlib.sha256(session.xml.encode()).hexdigest(), initial_sha=session.initial_sha,
            final_sha=session.state_sha(), verdict=session.features(), source_sha256=sources, files=files,
            materials=materials, geoms=geoms, meshes=meshes, frames=frames, control_dt=session.control_dt,
            stride=stride, fps=25, playback_speed=stride * session.control_dt * 25, hand=session.hand_info["model"],
            config=dict(exposure=-0.25, light_target=[0.57, -0.02, 0.85], lights=LIGHTS, visual_bevel_m=0.00005),
            zoom_steps=[zoom_start, zoom_end], last_step=steps[-1])
        (directory / "scene.json").write_text(json.dumps(payload, indent=2) + "\n")
    finally:
        session.close()
    print(json.dumps(dict(frames=len(frames), final_sha=payload["final_sha"], success=payload["verdict"]["success"])))


def checked_bundle(directory):
    directory = Path(directory)
    payload = json.loads((directory / "scene.json").read_text())
    for name, expected in payload["files"].items():
        if sha(directory / name) != expected:
            raise ValueError("Export integrity mismatch: " + name)
    return payload


def encode(directory, output, hold_seconds=2.5):
    import imageio.v2 as imageio
    from PIL import ImageDraw, ImageFont

    payload = checked_bundle(directory)
    output = Path(output)
    frame_dir = output.with_suffix("").with_name(output.stem + "-frames")
    manifest = json.loads((frame_dir / "render.json").read_text())
    fps = payload["fps"]
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 21)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    with imageio.get_writer(output, fps=fps, codec="libx264", macro_block_size=1, pixelformat="yuv420p",
                            ffmpeg_params=["-crf", "23", "-preset", "slow", "-movflags", "+faststart"]) as writer:
        for index in manifest["indices"]:
            pic = Image.open(frame_dir / f"{index:06d}.png").convert("RGB")
            draw = ImageDraw.Draw(pic)
            record = payload["frames"][index]
            f = record["features"]
            title = TITLE
            detail = f"{payload['hand']} | physics replay, {payload['playback_speed']:g}x"
            width = max(draw.textlength(title, font=font), draw.textlength(detail, font=small)) + 30
            draw.rounded_rectangle((20, 18, 20 + width, 80), radius=8, fill=(245, 244, 237))
            draw.text((32, 25), title, font=font, fill=(35, 45, 40))
            draw.text((32, 56), detail, font=small, fill=(85, 92, 88))
            state = "INSTALLED: seated and latched, hand released" if f["success"] else str(record["phase"])
            label = f"{state} | stage {f['stage']}/3 | latch {max(f['latch_rad'], 0):.2f} rad | {record['time_s']:.1f} s"
            width = draw.textlength(label, font=small) + 25
            draw.rounded_rectangle((20, 720 - 48, 20 + width, 720 - 17), radius=5, fill=(245, 244, 237))
            draw.text((32, 720 - 43), label, font=small, fill=(35, 58, 43))
            frame = np.asarray(pic)
            writer.append_data(frame)
        for _ in range(round(fps * hold_seconds)):
            writer.append_data(frame)
    pic.save(output.with_suffix(".png"))
    report = dict(renderer="Blender " + manifest["engine"], presentation_only=True, scripted_object_motion=False,
                  trajectory_sha256=payload["trajectory_sha256"], native_final_sha=payload["final_sha"],
                  native_verdict_success=payload["verdict"]["success"], pose_manifest_sha256=sha(Path(directory) / "scene.json"),
                  video_sha256=sha(output), playback_speed=payload["playback_speed"], render=manifest)
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Encoded {output}")


def render(directory, output, samples, engine, still=None, frame_step=1, cpu=False, threads=4):
    command = [BLENDER, "-b", "-t", str(threads), "-P", str(HERE / "studio_renderer.py"), "--", "--export", str(directory),
               "--output", str(output), "--samples", str(samples), "--engine", engine, "--frame-step", str(frame_step)]
    if still:
        command += ["--still", still]
    if cpu:
        command += ["--cpu"]
    env = os.environ.copy()
    if engine == "eevee" and not env.get("__EGL_VENDOR_LIBRARY_FILENAMES"):
        library = ctypes.util.find_library("EGL_nvidia")
        if library:
            vendor = Path(output).with_suffix(".egl-vendor.json").resolve()
            vendor.write_text(json.dumps({"file_format_version": "1.0.0", "ICD": {"library_path": library}}) + "\n")
            env["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(vendor)
            env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    with Path(output).with_suffix(".render.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, env=env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "render", "encode"])
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--engine", choices=["cycles", "eevee"], default="eevee")
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--still", choices=["initial", "middle", "final"])
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride)
    elif args.command == "encode":
        encode(args.export, args.output)
    else:
        render(args.export, args.output, args.samples, args.engine, args.still, args.frame_step, args.cpu, args.threads)
        if not args.still:
            encode(args.export, args.output)
