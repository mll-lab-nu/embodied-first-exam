"""Export exact native page-turn poses for the Blender studio film (authoring only, never shipped).

`export` replays a trajectory in a fresh Session and saves every visible geom's world pose at a fixed stride, the
visual meshes (with UVs for the printed pages) and the page textures, in the bundle format read by
`studio_renderer.py` (adapted from the T39 scene's renderer). `verify` replays again and checks every saved pose
bit for bit. Rendering never feeds back into physics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import mujoco
import numpy as np

from replay import load_trajectory
from runtime import Session

HERE = Path(__file__).resolve().parent
PHYSICS_SOURCES = ("task.json", "runtime.py", "scene.py", "checker.py", "replay.py")
STAGE_NAMES = [
    "Pages 4 / 5 · fingertip catches the fore-edge of leaf 2",
    "Leaf 2 lifted above 30°",
    "Leaf 2 carried past vertical",
    "Leaf 2 on the left stack · hand released · 1 s hold",
    "Pages 6 / 7 · exactly one page turned",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def board_finish():
    return dict(rgba=[0.88, 0.86, 0.78, 1], roughness=0.8, bump=dict(scale=3000, strength=0.04, distance=0.000008))


def export(trajectory, directory, stride=2, hold_start=15, hold_end=40, config_path=None):
    directory = Path(directory)
    if directory.exists():
        shutil.rmtree(directory)
    (directory / "assets").mkdir(parents=True)
    sources = {name: sha(HERE / name) for name in PHYSICS_SOURCES}
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    m = session.model
    hand_body = session.checker.hand_body
    from scene import arm_rig

    robot_bodies = arm_rig.robot_body_ids(m)  # stand + arm links (drawn with the Tianji factory colours)
    for name in sorted(p.name for p in (HERE / "assets").iterdir() if p.suffix == ".png"):
        shutil.copy(HERE / "assets" / name, directory / "assets" / name)
    materials = []
    for mid in range(m.nmat):
        name = m.material(mid).name
        texture = None
        if name.startswith("print_"):
            texture = "assets/page-%02d.png" % int(name.split("_")[1])
        elif name == "cover_print":
            texture = "assets/cover.png"
        materials.append(dict(name=name, rgba=m.mat_rgba[mid].tolist(), roughness=0.72, metallic=0,
                              textures={"base_color": texture} if texture else {}))
    geoms, ids, meshes, arrays = [], [], {}, {}
    for gid in range(m.ngeom):
        name = m.geom(gid).name or f"geom_{gid}"
        kind = int(m.geom_type[gid])
        if m.geom_group[gid] > 2:
            continue
        mid = int(m.geom_matid[gid])
        rgba = (m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[gid]).tolist()
        if rgba[3] == 0:
            continue
        is_robot = int(m.geom_bodyid[gid]) in robot_bodies
        is_hand = bool(hand_body[m.geom_bodyid[gid]]) and not is_robot
        if is_hand and (m.geom_contype[gid] or m.geom_conaffinity[gid]):
            continue  # collision proxies of the hand are not drawn
        mesh = int(m.geom_dataid[gid]) if kind == 7 else None
        record = dict(id=gid, name=name, body=m.body(int(m.geom_bodyid[gid])).name, kind=kind,
                      size=m.geom_size[gid].tolist(), mesh=mesh, material=mid, rgba=rgba, is_hand=is_hand,
                      authored_cad=not is_hand)
        if is_robot:
            record["visual_material"] = dict(rgba=rgba, roughness=0.29, metallic=0.15)  # pot_shelf_transfer arm look
        if kind == 0:
            record["visual_material"] = dict(rgba=[0.30, 0.33, 0.34, 1], roughness=0.82)
        elif name == "table":
            record["name"] = "desk"  # keep the desk at its true size in the studio (the renderer widens "table")
            record["visual_material"] = dict(rgba=[0.55, 0.39, 0.25, 1], roughness=0.48,
                                             bump=dict(scale=320, strength=0.08, distance=0.000025))
        elif name.endswith("_board_visual"):
            record["visual_material"] = board_finish()
        geoms.append(record)
        ids.append(gid)
        if mesh is not None and str(mesh) not in meshes:
            prefix = f"mesh_{mesh}_"
            for label, adr, num, array in [
                ("vertices", m.mesh_vertadr, m.mesh_vertnum, m.mesh_vert),
                ("faces", m.mesh_faceadr, m.mesh_facenum, m.mesh_face),
                ("normals", m.mesh_normaladr, m.mesh_normalnum, m.mesh_normal),
                ("face_normals", m.mesh_faceadr, m.mesh_facenum, m.mesh_facenormal),
                ("uv", m.mesh_texcoordadr, m.mesh_texcoordnum, m.mesh_texcoord),
                ("face_uv", m.mesh_faceadr, m.mesh_facenum, m.mesh_facetexcoord),
            ]:
                start, count = int(adr[mesh]), int(num[mesh])
                arrays[prefix + label] = array[start:start + count].copy() if start >= 0 else np.empty((0, 2))
            mesh_name = m.mesh(mesh).name
            # The print meshes carry inline UVs whose v was flipped for MuJoCo's image rows; Blender reads PNG rows
            # bottom-up, so the renderer flips v back. Verso u is already reversed in the model.
            meshes[str(mesh)] = dict(prefix=prefix, name=mesh_name, has_uv=bool(m.mesh_texcoordnum[mesh]),
                                     uv_flip_v=mesh_name.startswith("print_face"))
    np.savez_compressed(directory / "geometry.npz", **arrays)
    frames, positions, rotations = [], [], []

    def sample(repeat=1):
        status = session.status()
        record = dict(
            time_s=float(session.steps * session.control_dt),
            step=session.steps,
            state_sha=session.state_sha(),
            status=dict(stage=int(status["stage"]), success=bool(status["success"]), failed=bool(status["failed"]),
                        done=bool(status["done"]), target_angle_deg=status["target_angle_deg"]),
        )
        for _ in range(repeat):
            frames.append(record)
            positions.append(session.data.geom_xpos[ids].copy())
            rotations.append(session.data.geom_xmat[ids].reshape(-1, 3, 3).copy())

    try:
        sample(1 + hold_start)  # presentation hold of the frozen start (no simulated dwell)
        for i, action in enumerate(actions):
            session.step(action)
            if (i + 1) % stride == 0 or session.done or i == len(actions) - 1:
                sample()
            if session.done:
                break  # the episode ends at success (or failure); later rows are not executed
        if not session.success:
            raise RuntimeError("The presentation film needs a passing complete native replay")
        sample(hold_end)  # presentation hold of the final state (no simulated dwell)
        np.savez_compressed(directory / "poses.npz", positions=np.asarray(positions), rotations=np.asarray(rotations))
        if sources != {name: sha(HERE / name) for name in PHYSICS_SOURCES}:
            raise RuntimeError("Physics sources changed during export")
        config = json.loads(Path(config_path).read_text()) if config_path else {}
        payload = dict(
            task="book_page_turn",
            title="Turn one board-book page",
            hand=session.hand,
            hand_title=session.hand_info["model"],
            evidence_type="physical_actuator_replay",
            scripted_object_motion=False,
            physics_claims=["MuJoCo 3.4.0 actuator-only replay of the oracle rows (Marvin arms + hands); the board moves only by contact"],
            presentation_holds={"start_frames": hold_start, "end_frames": hold_end},
            geoms=geoms,
            meshes=meshes,
            materials=materials,
            frames=frames,
            config=config,
            stride=stride,
            playback_speed=1.0,
            probe_only=False,
            status=frames[-1]["status"],
            stage_names=STAGE_NAMES,
            trajectory_sha256=sha(trajectory),
            model_xml_sha256=hashlib.sha256(session.xml.encode()).hexdigest(),
            initial_sha=session.initial_sha,
            final_sha=session.state_sha(),
            source_sha256=sources,
            files={str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob("*")) if p.is_file()},
        )
        (directory / "scene.json").write_text(json.dumps(payload, indent=2) + "\n")
    finally:
        session.close()
    print(json.dumps({"frames": len(frames), "final_sha": payload["final_sha"], "success": True}))


def verify(trajectory, directory):
    directory = Path(directory)
    payload = json.loads((directory / "scene.json").read_text())
    poses = np.load(directory / "poses.npz")
    actions, hand, _ = load_trajectory(trajectory)
    session = Session(hand=hand)
    ids = [g["id"] for g in payload["geoms"]]
    try:
        for index, record in enumerate(payload["frames"]):
            while session.steps < record["step"]:
                session.step(actions[session.steps])
            assert record["state_sha"] == session.state_sha(), index
            assert np.array_equal(poses["positions"][index], session.data.geom_xpos[ids]), index
            assert np.array_equal(poses["rotations"][index], session.data.geom_xmat[ids].reshape(-1, 3, 3)), index
        assert session.success and session.state_sha() == payload["final_sha"]
    finally:
        session.close()
    print(f"Verified {len(payload['frames'])} exact native pose samples and the passing final state")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "verify"])
    parser.add_argument("--trajectory", type=Path, default=HERE / "solution/trajectory.npz")
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="presentation config JSON (camera, lights, exposure, title)")
    parser.add_argument("--stride", type=int, default=2)
    args = parser.parse_args()
    if args.command == "export":
        export(args.trajectory, args.export, args.stride, config_path=args.config)
    else:
        verify(args.trajectory, args.export)
