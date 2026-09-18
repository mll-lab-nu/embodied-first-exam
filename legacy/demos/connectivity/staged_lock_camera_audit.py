"""Render raw three-view observations of the same-direction staged lock.

The wrist sensor is attached to an extracted Panda hand with a prescribed pose;
there is no full arm, IK, contact-driven grasp or learned policy in this audit.
Both resolutions are native Nyx renders, without state diagrams or image crops.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import genesis as gs
import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
import torch

from demos.connectivity import staged_lock_nyx_demo as demo
from demos.connectivity import _staged_lock_classic_endpoint_model as model
from topogym.world import nyx

ROOT = Path(__file__).resolve().parents[2]


def camera_rig(layout, wrist_mount="stock"):
    # Front means the key-entry side (-x); side is offset toward -y. Both
    # exterior cameras have a component along the disc normal: exact side-on
    # viewing would collapse the apertures to thin edges.
    if layout == "wide":
        exterior = {
            "front_oblique": ([-.95, -.55, 1.55], [-.08, 0, 1.11], 60.),
            "side_oblique": ([-.40, -.95, 1.50], [.10, 0, 1.11], 60.),
        }
    else:
        exterior = {
            "front_oblique": ([-.62, -.43, 1.34], [.13, 0, 1.11], 40.),
            "side_oblique": ([-.28, -.58, 1.36], [.13, 0, 1.11], 40.),
        }
        if layout == "complementary":
            # Move the entry-side camera across the axis and farther off-axis.
            # This exposes rear apertures hidden in the focused front view and
            # gives complementary occlusion instead of two similar images.
            exterior["front_oblique"] = ([-.40, .62, 1.34], [.13, 0, 1.11], 40.)
    rig = {}
    for suffix, res in (("", [640, 360]), ("_policy", [320, 180])):
        for name, (pos, lookat, fov) in exterior.items():
            rig[name + suffix] = dict(res=res, pos=pos, lookat=lookat,
                                     up=[0, 0, 1], fov=fov, near=.01, far=12.)
        rig["wrist" + suffix] = dict(
            res=res, pos=[-.7, 0, 1.16], lookat=[.1, 0, 1.11], up=[0, 0, 1],
            fov=90., near=.01, far=3.,
            # Existing TopoGym hand-local mount, not a camera that tracks slots.
            attach=dict(enabled=True, entity="audit_hand", link="hand",
                        offset_pos=[.050, 0, .005], offset_lookat=[.065, 0, .170],
                        offset_up=[1, 0, 0]))
        if wrist_mount == "offset":
            # A proposed 100mm lateral bracket, pointing back toward the tool
            # axis. Rigid and fixed in hand coordinates; no oracle look-at.
            rig["wrist" + suffix]["fov"] = 60.
            rig["wrist" + suffix]["attach"].update(
                offset_pos=[.100, 0, .025], offset_lookat=[0, 0, .400])
    return rig


def write_hand_asset(output):
    """Keep the supplied Panda visual geometry and two finger joints."""
    source = Path(gs.__file__).parent / "assets/xml/franka_emika_panda/panda.xml"
    original = ET.parse(source).getroot()
    root = ET.Element("mujoco", model="camera_audit_hand")
    ET.SubElement(root, "compiler", angle="radian", meshdir=str(source.parent / "assets"), autolimits="true")
    root.append(deepcopy(original.find("default")))
    root.append(deepcopy(original.find("asset")))
    world = ET.SubElement(root, "worldbody")
    hand = deepcopy(original.find(".//body[@name='hand']"))
    hand.set("pos", "0 0 0")
    hand.set("quat", "1 0 0 0")
    hand.set("childclass", "panda")
    ET.SubElement(hand, "freejoint", name="hand_root")
    world.append(hand)
    path = output / "panda_hand.xml"
    ET.ElementTree(root).write(path, encoding="unicode")
    return path


def place_hand(hand, pose):
    # Hand +z points along the key; rotate the entire hand with the key.
    # Fingers straddle the 62mm-diameter bow. This is a visual grasp hypothesis,
    # not validated force closure. The hand origin is 102.9mm behind its pads.
    rotation = Rotation.from_rotvec(np.array([-np.deg2rad(pose.key_deg), 0, 0])) * Rotation.from_euler("y", 90, degrees=True)
    q = rotation.as_quat()  # xyzw -> Genesis wxyz
    position = np.array([pose.tip_x - .480 - .1029, 0, model.AXIS_Z])
    hand.set_pos(position, zero_velocity=True)
    hand.set_quat(q[[3, 0, 1, 2]], zero_velocity=True)
    indices = [hand.get_joint(name).dofs_idx_local[0] for name in ("finger_joint1", "finger_joint2")]
    hand.set_dofs_position([.031, .031], dofs_idx_local=indices, zero_velocity=True)
    return position, rotation.as_matrix()


def check_wrist(sensor, hand, hand_pos, hand_rotation, camera):
    # Inspect the pose actually submitted to Nyx after read(), rather than
    # trusting the requested camera config or the hand command alone.
    actual_hand = hand.get_link("hand").get_pos().cpu().numpy()
    if not np.allclose(actual_hand, hand_pos, atol=2e-5):
        raise RuntimeError("Hand drifted from prescribed audit pose")
    expected_pos = hand_pos + hand_rotation @ np.array(camera["attach"]["offset_pos"])
    expected_lookat = hand_pos + hand_rotation @ np.array(camera["attach"]["offset_lookat"])
    actual_pos = sensor._attached_pos[0].cpu().numpy()
    actual_lookat = sensor._attached_lookat[0].cpu().numpy()
    # Camera lookat distance may be normalized internally. Compare direction.
    expected_direction = expected_lookat - expected_pos
    expected_direction /= np.linalg.norm(expected_direction)
    actual_direction = actual_lookat - actual_pos
    actual_direction /= np.linalg.norm(actual_direction)
    error = max(float(np.max(np.abs(actual_pos - expected_pos))),
                float(np.max(np.abs(actual_direction - expected_direction))))
    if error > 5e-5:
        raise RuntimeError(f"Wrist attachment mismatch: {error}")
    return dict(pos=actual_pos.tolist(), direction=actual_direction.tolist(), max_abs_error=error)


def write_gallery(output, snapshots, video):
    # HTML only arranges the actual rendered sensor files; it renders no scene.
    names = ("front_oblique", "side_oblique", "wrist")
    html = ['<!doctype html><meta charset="utf-8"><title>Lock camera audit</title>',
            '<style>body{background:#18212a;color:#eee;font:16px sans-serif;margin:24px} '
            '.row{display:flex;gap:12px;flex-wrap:wrap}figure{margin:0 0 24px} '
            'img,video{max-width:100%;display:block}figcaption{padding:8px 0}</style>',
            '<h1>锁片相机观察对照</h1>',
            '<p>原始 Genesis + Nyx 图像，无孔型示意图、角度或动作标签。'
            'wrist 固定于独立 Panda 手爪；运动学回放，无完整机械臂、IK 或接触抓握验证。</p>',
            '<p>上排 640×360；下排 320×180 原生渲染。图片按原始像素展示。</p>']
    if video:
        html.append('<h2>三路同步回放（约 41 秒）</h2>'
                    '<p>左：front_oblique；中：side_oblique；右：wrist。</p>'
                    '<video controls muted src="three_views.mp4"></video>'
                    '<p>以下为各路原始视频：</p><div class="row">')
        for name in names:
            html.append(f'<figure><video width="640" controls muted src="{name}.mp4"></video><figcaption>{name}</figcaption></figure>')
        html.append('</div>')
    for label in snapshots:
        html.append(f'<h2>{label}</h2>')
        for suffix in ("", "_policy"):
            html.append('<div class="row">')
            for name in names:
                html.append(f'<figure><img src="{label}_{name}{suffix}.png"><figcaption>{name}{suffix}</figcaption></figure>')
            html.append('</div>')
    (output / "index.html").write_text('\n'.join(html), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", choices=("wide", "focused", "complementary"), default="complementary")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--wrist-mount", choices=("stock", "offset"), default="stock")
    parser.add_argument("--fps", type=int, default=8)
    parser.add_argument("--spp", type=int, default=32)
    parser.add_argument("--disc-roughness", type=float, default=.3)
    parser.add_argument("--disc-metallic", type=float, default=.75)
    args = parser.parse_args()
    if args.fps <= 0 or args.spp <= 0:
        parser.error("fps and spp must be positive")
    if not torch.cuda.is_available():
        raise RuntimeError("Nyx needs CUDA: use .venv-gs121-nyx on the GPU host")
    output = args.output or ROOT / "runs/staged_lock_camera_audit" / (args.layout + ("_wrist_offset" if args.wrist_mount == "offset" else ""))
    output.mkdir(parents=True, exist_ok=True)
    gs.init(backend=gs.cuda, logging_level="warning", seed=0)
    demo.m = model
    holder = {}

    def prepare(scene, manifest):
        holder["hand"] = manifest.add("audit_hand", scene.add_entity(
            gs.morphs.MJCF(file=str(write_hand_asset(output)), collision=False), name="audit_hand"))

    rig = camera_rig(args.layout, args.wrist_mount)
    scene, sensors, discs, key, endpoint = demo.build_scene(args, output, camera_rig=rig, prepare_scene=prepare)
    hand = holder["hand"]
    states = model.timeline(args.fps)
    wrist_records = []

    def render(pose):
        position, rotation = place_hand(hand, pose)
        demo.set_pose(scene, discs, key, endpoint, pose)
        images = {name: nyx.rgb(sensor) for name, sensor in sensors.items()}
        record = check_wrist(sensors["wrist"], hand, position, rotation, rig["wrist"])
        check_wrist(sensors["wrist_policy"], hand, position, rotation, rig["wrist_policy"])
        wrist_records.append(record)
        return images

    snapshots = {}
    selected = {0: "initial", 6: "depth2", 10: "aligned_before_depth3", 11: "depth3", 15: "final"}
    for index, label in selected.items():
        snapshots[label] = [pose for beat, pose in states if beat == index][-1]
    aligned = snapshots["aligned_before_depth3"]
    changed = replace(aligned, disc_deg=(*aligned.disc_deg[:2], aligned.disc_deg[2] + 30))
    assert not model.geometry_errors(changed)
    assert model.can_insert(aligned, 3) and not model.can_insert(changed, 3)
    snapshots["counterfactual_d3_plus30"] = changed
    for label, pose in snapshots.items():
        images = render(pose)
        for name, rgb in images.items():
            Image.fromarray(rgb).save(output / f"{label}_{name}.png")
        print(f"Snapshot {label}", flush=True)

    frames = []
    if args.video:
        with ExitStack() as stack:
            writers = {name: stack.enter_context(imageio.get_writer(
                str(output / f"{name}.mp4"), fps=args.fps, codec="libx264", quality=8,
                macro_block_size=1, ffmpeg_log_level="error", ffmpeg_params=["-movflags", "+faststart"]))
                for name in sensors}
            previous = None
            for frame, (beat, pose) in enumerate(states):
                if pose != previous:
                    images = render(pose)
                    previous = pose
                for name, writer in writers.items():
                    writer.append_data(images[name])
                frames.append(dict(frame=frame, time_s=frame / args.fps, beat=beat,
                                   pose=asdict(pose), wrist=wrist_records[-1]))
                if frame % 80 == 0:
                    print(f"Video {frame}/{len(states)}", flush=True)
        (output / "frames.json").write_text(json.dumps(frames, indent=2) + '\n')
        for suffix in ("", "_policy"):
            inputs = []
            for name in ("front_oblique", "side_oblique", "wrist"):
                inputs.extend(["-i", str(output / f"{name}{suffix}.mp4")])
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", *inputs,
                            "-filter_complex", "[0:v][1:v][2:v]hstack=inputs=3[v]", "-map", "[v]",
                            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                            str(output / f"three_views{suffix}.mp4")], check=True)

    report = dict(layout=args.layout, cameras=rig, spp=args.spp,
                  disc_material=dict(roughness=args.disc_roughness, metallic=args.disc_metallic),
                  snapshots={k: asdict(v) for k, v in snapshots.items()},
                  counterfactual=dict(changed_only="D3 angle +30 degrees", target_depth=3,
                                      aligned_can_insert=True, changed_can_insert=False),
                  wrist_attachment_max_abs_error=max(r["max_abs_error"] for r in wrist_records),
                  wrist_mount=args.wrist_mount,
                  wrist_mount_description="existing TopoGym offset" if args.wrist_mount == "stock" else "proposed 100mm lateral bracket; physical bracket not modeled",
                  full_arm=False, ik_validated=False, grasp_contact_validated=False,
                  mechanism="unchanged same-direction classic_endpoint geometry; scripted poses",
                  policy_evaluated=False, visibility_quantitatively_validated=False,
                  video_frames=len(frames), fps=args.fps,
                  native_resolutions=[[640, 360], [320, 180]])
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    write_gallery(output, snapshots, args.video)
    print(f"Saved {output / 'index.html'}", flush=True)


if __name__ == "__main__":
    main()
