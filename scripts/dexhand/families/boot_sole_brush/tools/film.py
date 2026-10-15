"""Export exact MuJoCo poses of a physical boot_sole_brush replay for the Blender studio film (authoring only).

python tools/film.py export --trajectory solution/trajectory.npz --export OUT [--stride 4]
python tools/studio_renderer.py --export OUT --output film.mp4 --width 1280 --height 720 --samples 24 --fps 25

The replay runs the frozen Session row by row (the same physics as the graders); every ``stride`` controls the world
pose of every visible geom is saved together with the predicate status and the state hash. The renderer only draws
these poses. Presentation-only choices (materials, camera path, lights) are recorded in scene.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from runtime import ACTION_DIM, Session  # noqa: E402
from scene import hands, robot_parts  # noqa: E402

PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ease(x):
    x = float(np.clip(x, 0, 1))
    return x * x * (3 - 2 * x)


def geometry(session, out):
    """Visible geoms (group <= 2, opaque) with meshes, UVs and textures (scene-T29 bundle format)."""
    m = session.model
    (out / "textures").mkdir(parents=True, exist_ok=True)
    hand_root = m.body("wrist_stage").id
    hand_bodies = set()
    for b in range(m.nbody):
        if b == hand_root or int(m.body_parentid[b]) in hand_bodies:
            hand_bodies.add(b)
    _, robot_rest = robot_parts(m)
    arm_bodies = robot_rest - hand_bodies
    arrays, materials, meshes, geoms, ids = {}, [], {}, [], []
    for i in range(m.nmat):
        record = {"name": m.mat(i).name, "rgba": m.mat_rgba[i].tolist(), "metallic": float(m.mat_metallic[i]),
                  "roughness": float(m.mat_roughness[i]), "textures": {}}
        for role, tid in enumerate(m.mat_texid[i]):
            if tid < 0 or m.tex_type[tid] != mujoco.mjtTexture.mjTEXTURE_2D:
                continue
            h, w, c = int(m.tex_height[tid]), int(m.tex_width[tid]), int(m.tex_nchannel[tid])
            a = int(m.tex_adr[tid])
            pixels = m.tex_data[a : a + h * w * c].reshape(h, w, c)
            rel = f"textures/native-{tid}.png"
            Image.fromarray(pixels).save(out / rel)
            record["textures"][str(role)] = rel
        materials.append(record)
    for i in range(m.ngeom):
        if m.geom_group[i] > 2 or m.geom_rgba[i, 3] == 0:
            continue
        mid = int(m.geom_matid[i])
        rgba = (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[i]).tolist()
        if rgba[3] == 0:
            continue
        kind = int(m.geom_type[i])
        mesh = int(m.geom_dataid[i]) if kind == 7 else None
        name = m.geom(i).name or f"geom_{i}"
        if "_collision" in name and (name.startswith("l_wuji") or name.startswith("r_wuji")):
            continue  # Wuji collision proxies (either hand, incl. the parked left one) are not drawn
        record = {"id": i, "name": name, "body": m.body(int(m.geom_bodyid[i])).name,
                  "is_hand": int(m.geom_bodyid[i]) in hand_bodies, "kind": kind, "size": m.geom_size[i].tolist(),
                  "material": mid, "rgba": rgba, "mesh": mesh}
        if int(m.geom_bodyid[i]) in arm_bodies and not m.geom(i).name:
            # Tianji Marvin visual meshes: native factory rgba per sub-mesh, satin finish (pot_transfer film look).
            record["visual_material"] = {"rgba": rgba, "roughness": 0.29, "metallic": 0.15}
        elif name == "brush_back":
            record["visual_material"] = {"rgba": [0.72, 0.52, 0.29, 1], "roughness": 0.43,
                                         "bump": {"scale": 750, "strength": 0.16, "distance": 0.00012}}
            record["authored_cad"] = True
        elif name.startswith("clod_"):
            record["visual_material"] = {"rgba": [0.32, 0.20, 0.10, 1], "roughness": 0.95,
                                         "bump": {"scale": 1800, "strength": 0.5, "distance": 0.0003}}
        elif name.startswith("tray_"):
            record["visual_material"] = {"rgba": [0.28, 0.37, 0.33, 1], "roughness": 0.52}
        elif name == "counter":
            record["visual_material"] = {"rgba": [0.79, 0.77, 0.71, 1], "roughness": 0.65,
                                         "bump": {"scale": 260, "strength": 0.09, "distance": 0.0001}}
        elif name.startswith("rack_"):
            record["visual_material"] = {"rgba": [0.62, 0.64, 0.66, 1], "metallic": 0.85, "roughness": 0.32}
        ids.append(i)
        geoms.append(record)
        if kind == 7 and str(mesh) not in meshes:
            pre = f"mesh_{mesh}_"
            va, vn = int(m.mesh_vertadr[mesh]), int(m.mesh_vertnum[mesh])
            fa, fn = int(m.mesh_faceadr[mesh]), int(m.mesh_facenum[mesh])
            na, nn = int(m.mesh_normaladr[mesh]), int(m.mesh_normalnum[mesh])
            ta, tn = int(m.mesh_texcoordadr[mesh]), int(m.mesh_texcoordnum[mesh])
            arrays[pre + "vertices"] = m.mesh_vert[va : va + vn].copy()
            arrays[pre + "faces"] = m.mesh_face[fa : fa + fn].copy()
            arrays[pre + "normals"] = m.mesh_normal[na : na + nn].copy()
            arrays[pre + "face_normals"] = m.mesh_facenormal[fa : fa + fn].copy()
            if tn:
                arrays[pre + "uv"] = m.mesh_texcoord[ta : ta + tn].copy()
                arrays[pre + "face_uv"] = m.mesh_facetexcoord[fa : fa + fn].copy()
            # MuJoCo stores OBJ texture V as 1 - v; the renderer restores the source v (Blender convention).
            meshes[str(mesh)] = {"prefix": pre, "has_uv": bool(tn), "name": m.mesh(mesh).name, "uv_flip_v": True}
    # Blender gets the source (unflipped) diffuse and normal maps of the Poly Haven boot with the source UVs.
    boot_mat = next(i for i, r in enumerate(materials) if r["name"] == "boot_rubber")
    shutil.copy2(HERE / "assets/boot/textures/rubber_boots_diff_2k.png", out / "textures/boot_diffuse.png")
    Image.open(HERE / "assets/boot/textures/rubber_boots_nor_gl_2k.jpg").save(out / "textures/boot_normal.png")
    materials[boot_mat]["textures"] = {"1": "textures/boot_diffuse.png", "normal": "textures/boot_normal.png"}
    materials[boot_mat]["roughness"] = 0.55
    return arrays, materials, geoms, meshes, np.asarray(ids)


def camera_path(step, success_step):
    """Wide shot of the robot and the counter from its right-front quarter for the pickup, close-up on the sole while
    brushing, pulled back for the result (the robot stands at the counter's -y edge, facing +y)."""
    wide_p, wide_t = np.array([2.15, 0.85, 2.15]), np.array([0.42, -0.25, 1.06])
    close_p, close_t = np.array([1.40, 0.72, 1.98]), np.array([0.50, 0.0, 1.28])
    end_p, end_t = np.array([2.15, 0.85, 2.2]), np.array([0.44, -0.18, 1.08])
    zoom_in = ease((step - 760) / 80)
    zoom_out = ease((step - (success_step - 70)) / 60)
    p = wide_p + (close_p - wide_p) * zoom_in
    t = wide_t + (close_t - wide_t) * zoom_in
    return p + (end_p - p) * zoom_out, t + (end_t - t) * zoom_out


def phase_of(step, status):
    if status["success"]:
        return "all six clods in the tray, brush withdrawn: success"
    if step < 160:
        return "reach and pinch the brush on the counter"
    if step < 700 and status["stage"] == 0:
        return "lift the brush and carry it over the boot sole"
    if status["stage"] >= 2:
        return "withdraw the brush and hold"
    return f"brush the sole: {status['clods_in_tray']}/6 clods in the tray"


def export(trajectory, out, stride, hand):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    sources = {name: sha(HERE / name) for name in PHYSICS_SOURCES}
    actions, recorded, _ = hands.read_trajectory(trajectory, widths=ACTION_DIM, max_rows=3000)
    session = Session(hand=recorded)
    arrays, materials, geoms, meshes, ids = geometry(session, out)
    d = session.data
    positions, rotations, frames, cam_p, cam_t = [], [], [], [], []
    success_step = None
    probe = Session(hand=recorded)
    success_step = probe.replay(actions)["steps"]
    probe.close()

    def sample():
        st = session.status()
        p, t = camera_path(session.steps, success_step)
        positions.append(d.geom_xpos[ids].copy())
        rotations.append(d.geom_xmat[ids].reshape(-1, 3, 3).copy())
        cam_p.append(p)
        cam_t.append(t)
        frames.append({"step": int(session.steps), "time_s": session.steps * session.control_dt,
                       "phase": phase_of(session.steps, st), "state_sha": session.state_sha(),
                       "status": {k: st[k] for k in ("success", "failed", "done", "stage", "reason", "clods_in_tray",
                                                     "clods_brushed")}})

    sample()
    for i, row in enumerate(actions):
        session.step(row)
        if (i + 1) % stride == 0 or session.done:
            sample()
        if session.done:
            break
    if not session.success:
        raise RuntimeError("The film needs a successful physical replay")
    np.savez_compressed(out / "geometry.npz", **arrays)
    np.savez_compressed(out / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations),
                        camera_positions=np.asarray(cam_p), camera_targets=np.asarray(cam_t))
    if sources != {name: sha(HERE / name) for name in PHYSICS_SOURCES}:
        raise RuntimeError("Physics sources changed during export")
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()
             and p.suffix in (".npz", ".png", ".jpg")}
    title = "Brush the debris off a boot sole"
    payload = {
        "task": "boot_sole_brush", "title": title, "evidence_type": "physical_actuator_replay",
        "validation_mode": "physical_actuator_replay", "scripted_object_motion": False, "probe_only": False,
        "status": {"mode": "physical_actuator_replay", "success": True, "success_step": success_step},
        "trajectory_sha256": sha(trajectory), "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
        "initial_sha": session.initial_sha, "final_sha": session.state_sha(), "source_sha256": sources,
        "geoms": geoms, "meshes": meshes, "materials": materials, "files": files,
        "physics_control_steps_per_video_frame": stride,
        "playback_speed": stride * session.control_dt * 25,
        "physics_claims": ["Only the robot's motor targets (Marvin arm joints and fingers) act; boot, brush and clods move by "
                           "contact and gravity."],
        "config": {
            "display_title": title, "hand_label": "Tianji Marvin arm + " + session.hand_info["model"],
            "camera": {"position": cam_p[0].tolist(), "target": cam_t[0].tolist(), "lens": 40},
            "exposure": -0.3, "visual_bevel_m": 0.001, "light_target": [0.55, 0.05, 1.13],
            "lights": [
                {"name": "Large warm softbox", "offset": [-0.65, -0.65, 0.95], "energy": 160, "size": 1.15,
                 "color": [1, 0.93, 0.83]},
                {"name": "Cool fill", "offset": [0.7, 0.4, 0.7], "energy": 85, "size": 1.0, "color": [0.82, 0.9, 1]},
                {"name": "Top rim", "offset": [0.2, 0.45, 1.25], "energy": 95, "size": 0.8, "color": [1, 1, 1]},
            ],
        },
        "frames": frames,
    }
    (out / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    session.close()
    print(json.dumps({"frames": len(frames), "success_step": success_step, "final_sha": payload["final_sha"],
                      "playback_speed": payload["playback_speed"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export"])
    parser.add_argument("--trajectory", type=Path, default=HERE / "solution/trajectory.npz")
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--stride", type=int, default=4)
    args = parser.parse_args()
    export(args.trajectory, args.export, args.stride, None)
