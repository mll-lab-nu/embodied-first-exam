"""Export the MuJoCo physics replay of a trajectory as a studio-film pose bundle (authoring only, never shipped).

The bundle (scene.json + geometry.npz + poses.npz) is the format of the accepted T19 scene film renderer
(tools/studio_renderer.py). Every sampled frame is the simulator state of the replayed motor targets; no object pose
is prescribed. Presentation-only adjustments (disclosed in scene.json "presentation_notes"):
- the stationary filter frame, pleats and cartridge are drawn 4.5 mm further into the housing (they are visual-only
  in the physics model, so the bin mouth would otherwise appear to pass through the frame);
- the visual-only lower-seat lips are not drawn (the lower tabs slide through their footprint);
- the final state is held on screen for ``--final-hold`` seconds (repeated final frame, labelled as such).

    python tools/film_export.py --traj solution/trajectory.npz --out <dir> [--hand sharpa] [--stride 2]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import mujoco
import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))

from replay import load_trajectory  # noqa: E402
from runtime import Session  # noqa: E402

FILTER_SHIFT_M = 0.0045
STAGE_NAMES = ["press the release, remove the bin", "reinstall: tabs first, close until the latch snaps",
               "let go: hold the reinstalled bin", "success"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finish(name, rgba):
    """Presentation materials of the accepted T19 film (export.py), plus the added base skid."""
    result = {"rgba": rgba, "roughness": 0.4, "metallic": 0}
    if "counter" in name:
        result.update(rgba=[0.65, 0.52, 0.38, 1], roughness=0.55, bump={"scale": 500, "strength": 0.12, "distance": 0.00006})
    elif "skid" in name:
        result.update(rgba=[0.035, 0.044, 0.043, 1], roughness=0.6)
    elif "housing" in name or "vac_" in name:
        result.update(rgba=[0.055, 0.24, 0.17, 1], roughness=0.28, coat=0.2,
                      bump={"scale": 2200, "strength": 0.1, "distance": 0.000015})
    elif "container_shell" in name or "container_latch" in name or "container_lower" in name:
        result.update(rgba=[0.43, 0.49, 0.49, 1], roughness=0.15, transmission=0.68, ior=1.47, coat=0.2)
    elif "button" in name or "latch_tooth" in name:
        result.update(rgba=[0.62, 0.025, 0.018, 1], roughness=0.3, coat=0.12)
    elif "handle" in name or "filter_rim" in name or "container_port" in name or "battery_mount" in name:
        result.update(rgba=[0.035, 0.044, 0.043, 1], roughness=0.47,
                      bump={"scale": 1800, "strength": 0.12, "distance": 0.00002})
    elif "filter_cartridge" in name:
        result.update(rgba=[0.83, 0.82, 0.73, 1], roughness=0.9)
    return result


def export(traj, out, hand=None, stride=2, fps=25, final_hold=1.5, camera=None, lens=44.0, crf=20):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    actions, file_hand, _ = load_trajectory(traj)
    s = Session(hand=hand or file_hand)
    m, d = s.model, s.data
    hand_roots = {m.body(name).id for name in ("wrist_stage", "left_wrist_stage")
                  if mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, name) >= 0}
    is_hand_body = np.zeros(m.nbody, bool)
    for b in range(m.nbody):
        p = b
        while p:
            if p in hand_roots:
                is_hand_body[b] = True
                break
            p = int(m.body_parentid[p])
    geometry, meshes, geoms, ids, shifts = {}, {}, [], [], []
    for g in range(m.ngeom):
        mid = int(m.geom_matid[g])
        rgba = (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[g]).tolist()
        name = m.geom(g).name or f"geom_{g}"
        if rgba[3] <= 0 or m.geom_group[g] > 2 or name.startswith("lower_seat_lip"):
            continue
        hand_geom = bool(is_hand_body[m.geom_bodyid[g]])
        if hand_geom and m.geom_contype[g] and m.geom_conaffinity[g] and m.geom_group[g] != 2:
            continue  # hand collision proxies are not drawn; the vendor visual meshes are
        mesh = int(m.geom_dataid[g]) if m.geom_type[g] == 7 else None
        record = {"id": g, "name": name, "body": m.body(m.geom_bodyid[g]).name, "kind": int(m.geom_type[g]),
                  "size": m.geom_size[g].tolist(), "mesh": mesh, "material": mid, "rgba": rgba, "is_hand": hand_geom}
        if not hand_geom:
            record["visual_material"] = finish(name, rgba)
        geoms.append(record)
        ids.append(g)
        shifts.append(name.startswith("filter_"))
        if mesh is not None and str(mesh) not in meshes:
            prefix = f"mesh_{mesh}_"
            for label, adr, num, arr in [("vertices", m.mesh_vertadr, m.mesh_vertnum, m.mesh_vert),
                                         ("faces", m.mesh_faceadr, m.mesh_facenum, m.mesh_face),
                                         ("normals", m.mesh_normaladr, m.mesh_normalnum, m.mesh_normal),
                                         ("face_normals", m.mesh_faceadr, m.mesh_facenum, m.mesh_facenormal)]:
                a, n = int(adr[mesh]), int(num[mesh])
                geometry[prefix + label] = arr[a:a + n].copy()
            meshes[str(mesh)] = {"prefix": prefix, "name": m.mesh(mesh).name, "has_uv": False}
    shifts = np.asarray(shifts)
    vac = m.body("vacuum_body").id
    positions, rotations, frames = [], [], []

    def sample(label=None):
        st = s.status()
        pos = d.geom_xpos[ids].copy()
        pos[shifts] += d.xmat[vac].reshape(3, 3) @ np.array([FILTER_SHIFT_M, 0, 0])
        positions.append(pos)
        rotations.append(d.geom_xmat[ids].reshape(-1, 3, 3).copy())
        frames.append({"step": s.steps, "time_s": round(s.steps * s.control_dt, 4), "state_sha": s.state_sha(),
                       "label": label or "",
                       "status": {"stage": int(st["stage"]), "success": bool(st["success"]), "done": bool(st["done"]),
                                  "failed": bool(st["failed"]), "reason": st["reason"]}})

    sample("initial state")
    for i, row in enumerate(actions):
        s.step(row)
        if (i + 1) % stride == 0 or s.done:
            sample()
        if s.done:
            break
    for _ in range(int(round(final_hold * fps))):
        positions.append(positions[-1].copy())
        rotations.append(rotations[-1].copy())
        frames.append({**frames[-1], "label": "final state held on screen"})
    np.savez_compressed(out / "geometry.npz", **geometry)
    np.savez_compressed(out / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
    materials = [{"name": m.material(i).name, "rgba": m.mat_rgba[i].tolist(), "roughness": 0.4, "metallic": 0}
                 for i in range(m.nmat)]
    config = {
        "task": "vacuum_bin_reseat",
        "display_title": "Remove and reinstall a vacuum dust bin",
        "exposure": -0.6,
        "visual_bevel_m": 0.00045,
        "camera": camera or {"position": [-0.20, -1.06, 1.33], "target": [0.53, -0.11, 0.78], "lens": lens},
        "light_target": [0.69, -0.10, 0.78],
        "lights": [
            {"name": "Large warm key", "offset": [-0.35, -0.7, 1.4], "energy": 180, "size": 1.4, "color": [1, 0.95, 0.88]},
            {"name": "Cool fill", "offset": [0.8, 0.1, 0.8], "energy": 88, "size": 1.0, "color": [0.87, 0.93, 1]},
            {"name": "Plastic edge light", "offset": [-0.5, 0.7, 1.1], "energy": 140, "size": 1.1, "color": [1, 1, 1]},
        ],
    }
    st = s.status()
    payload = {
        "schema_version": 1, "task": "vacuum_bin_reseat", "title": config["display_title"], "config": config,
        "evidence_type": "physical_actuator_replay", "validation_mode": "physical_actuator_replay",
        "scripted_object_motion": False, "prescribed_quantities": [],
        "status": frames[-1]["status"], "probe_only": False, "playback_speed": stride * s.control_dt * fps,
        "hand_label": s.hand_info["model"], "stage_names": STAGE_NAMES, "crf": crf,
        "geoms": geoms, "meshes": meshes, "materials": materials, "frames": frames,
        "files": {n: sha(out / n) for n in ["geometry.npz", "poses.npz"]},
        "trajectory_sha256": sha(traj), "model_xml_sha256": hashlib.sha256(s.xml.encode()).hexdigest(),
        "initial_sha": s.initial_sha, "final_sha": s.state_sha(), "final_features": {k: v for k, v in st.items()},
        "physics_control_steps_per_video_frame": stride,
        "physics_claims": "MuJoCo replay of the recorded motor targets (two wrist stages + fingers) in the frozen task scene; "
                          "objects move only through contact and passive joint dynamics.",
        "presentation_notes": [
            f"filter frame, pleats and cartridge drawn {FILTER_SHIFT_M * 1000:.1f} mm deeper in the housing (visual-only in physics)",
            "visual-only lower-seat lips not drawn",
            f"final state held on screen for {final_hold:g} s (repeated last simulated frame)",
        ],
    }
    (out / "scene.json").write_text(json.dumps(payload, indent=1) + "\n")
    s.close()
    print(json.dumps({"frames": len(frames), "success": st["success"], "reason": st["reason"], "steps": st["steps"],
                      "final_sha": payload["final_sha"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--hand")
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--final-hold", type=float, default=1.5)
    parser.add_argument("--lens", type=float, default=44.0)
    parser.add_argument("--crf", type=int, default=20)
    args = parser.parse_args()
    export(args.traj, args.out, args.hand, args.stride, args.fps, args.final_hold, lens=args.lens, crf=args.crf)
