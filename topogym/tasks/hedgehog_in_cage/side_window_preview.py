"""Render an audited object-only side-window witness; no physics is executed."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation, Slerp
from scipy.spatial import cKDTree

from .variants import ROOT, file_sha, save


def render(folder):
    folder = Path(folder).resolve()
    report = json.loads((folder / "report.json").read_text())
    if not report["accepted"]:
        raise ValueError("A certified object path is required before rendering")
    for name, digest in json.loads((folder / "files_sha256.json").read_text()).items():
        if file_sha(folder / name) != digest:
            raise ValueError(f"Probe artifact changed: {name}")
    video = ROOT / "demos/hedgehog_in_cage/detail" / f"{folder.name}_kinematic_detail.mp4"
    if video.exists():
        raise FileExistsError(video)
    video.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
    import genesis as gs
    import imageio.v2 as imageio
    import trimesh
    from PIL import Image
    from topogym.world.lighting import vis_options

    gs.init(backend=gs.cpu, precision="64", logging_level="warning", seed=0)
    scene = gs.Scene(show_viewer=False, vis_options=vis_options(),
                     rigid_options=gs.options.RigidOptions(enable_collision=False),
                     renderer=gs.renderers.Rasterizer())
    origin = np.array([0., 0., .12])
    scene.add_entity(gs.morphs.Box(size=(1.2, 1.2, .025), pos=(0, 0, -.0125), fixed=True),
                     surface=gs.surfaces.Plastic(color=(.72, .74, .76)))
    cage = scene.add_entity(gs.morphs.Mesh(file=str(folder / "assets/cage.glb"), pos=origin,
                                   fixed=True, collision=False, decimate=False,
                                   file_meshes_are_zup=True, align=False))
    ball = scene.add_entity(gs.morphs.Mesh(file=str(folder / "assets/hedgehog.glb"),
                                         pos=origin, fixed=False, decimate=False,
                                         file_meshes_are_zup=True, align=False))
    camera_spec = dict(res=(960, 720), pos=(.57, -.30, .32),
                       lookat=(.075, 0, .13), fov=42, GUI=False)
    camera = scene.add_camera(**camera_spec)
    scene.build()
    path = np.array(json.loads((folder / "path.json").read_text())["path"])
    rotations = Rotation.from_quat(path[:, 3:])
    angles = (rotations[1:] * rotations[:-1].inv()).magnitude()
    lengths = np.linalg.norm(np.diff(path[:, :3], axis=0), axis=1) + .092 * angles
    # Ignore exact repeated poses to keep Slerp's key times strictly increasing.
    keep = np.r_[True, lengths > 1e-12]
    path = path[keep]
    times = np.r_[0., np.cumsum(lengths[lengths > 1e-12])]
    rotations = Slerp(times, Rotation.from_quat(path[:, 3:]))
    fps = 20
    samples = np.r_[np.zeros(fps), np.linspace(0, times[-1], 12*fps), np.full(fps, times[-1])]
    poses = np.column_stack([*[np.interp(samples, times, path[:, i]) for i in range(3)],
                             rotations(samples).as_quat()])
    reference = {n:trimesh.load(folder / f"assets/{n}.glb", force="mesh").vertices
                 for n in ("cage", "hedgehog")}
    def visual_error(entity, name, position, quaternion):
        actual = np.concatenate([g.get_vverts().cpu().numpy() for g in entity.vgeoms])
        local = Rotation.from_quat(quaternion).inv().apply(actual-position)
        expected = reference[name]
        return max(float(cKDTree(local).query(expected)[0].max()),
                   float(cKDTree(expected).query(local)[0].max()))
    maximum_error = visual_error(cage, "cage", origin, [0, 0, 0, 1])
    if maximum_error > 1e-6:
        raise ValueError("Rendered cage coordinates differ from the audited geometry")
    with imageio.get_writer(video, fps=fps, codec="libx264", quality=8, macro_block_size=1,
                            ffmpeg_params=["-threads", "2"], ffmpeg_log_level="error") as writer:
        for i, pose in enumerate(poses):
            ball.set_pos(origin + pose[:3])
            ball.set_quat(pose[[6, 3, 4, 5]])
            scene.visualizer.update_visual_states(force_render=True)
            maximum_error = max(maximum_error, visual_error(ball, "hedgehog", origin+pose[:3], pose[3:]))
            if maximum_error > 1e-6:
                raise ValueError("Rendered ball coordinates differ from the audited path")
            rgb = camera.render(force_render=True)[0].copy()
            writer.append_data(rgb)
            if i in (0, len(poses)//2, len(poses)-1):
                Image.fromarray(rgb).save(folder / f"detail_frame_{i:03d}.png")
            if i % 40 == 0:
                print(f"Kinematic preview {i+1}/{len(poses)}", flush=True)
    save(folder / "render_frames.json", dict(poses_xyz_xyzw=poses.tolist(), origin=origin.tolist()))
    save(folder / "archive_manifest.json", dict(
        task="hedgehog_in_cage", instance=folder.name, camera="detail", camera_spec=camera_spec,
        video=str(video.relative_to(ROOT)), video_sha256=file_sha(video), fps=fps,
        frame_count=len(poses), duration_s=len(poses)/fps,
        scope="object-only kinematic extraction; not a robot or dynamics demonstration",
        physics_steps=0, robot_present=False, collision_verification="FCL probe report",
        maximum_visual_vertex_error_m=maximum_error,
        probe_files_manifest_sha256=file_sha(folder / "files_sha256.json"),
        path_sha256=file_sha(folder / "path.json"), report_sha256=file_sha(folder / "report.json"),
        render_frames_sha256=file_sha(folder / "render_frames.json")))
    print(video, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    render(parser.parse_args().folder)
