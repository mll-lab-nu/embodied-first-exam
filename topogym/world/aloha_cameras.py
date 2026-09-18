"""Four ALOHA task views from the pinned upstream optical poses.

The complete optical rig follows the robot adapter's source-frame transform.
Genesis uses square pixels through one vertical FOV. Report both intrinsics;
matching resolution and mounting pose does not imply hardware calibration.
"""
from __future__ import annotations

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

SOURCE = "https://github.com/google-deepmind/mujoco_menagerie/tree/8161bba264d7fa7c99ca301e91e7fb44737676ad/aloha"
CAMERA_NAMES = ("cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist")
FIXED = {
    "cam_high": ("overhead_cam", [0., -.303794, 1.02524], [.976332, .216277, 0., 0.]),
    "cam_low": ("worms_eye_cam", [0., -.377167, .0316055], [.672659, .739953, 0., 0.]),
}
FOCAL_M = np.array([.00193, .00193])
SENSOR_M = np.array([.003896, .002140])


def optical_pose(position, rotation):
    position = np.asarray(position, dtype=float)
    return dict(pos=position.tolist(), lookat=(position+rotation.apply([0, 0, -1])).tolist(),
                up=rotation.apply([0, 1, 0]).tolist())


def make_aloha_rig(source_origin, *, table_rotation=None, resolution=(1280, 720), low_pitch_offset_deg=0.):
    """Return camera configurations plus explicit source/calibration metadata."""
    origin = np.asarray(source_origin, dtype=float)
    rotation = table_rotation if table_rotation is not None else Rotation.identity()
    width, height = resolution
    fov = float(np.degrees(2*np.arctan(SENSOR_M[1]/(2*FOCAL_M[1]))))
    common = dict(res=list(resolution), fov=fov, near=.005, far=12.)
    cameras, sources = {}, {}
    for name, (source_name, position, wxyz) in FIXED.items():
        local = Rotation.from_quat(np.asarray(wxyz)[[1, 2, 3, 0]])
        if name == "cam_low":
            local = local*Rotation.from_euler("x", low_pitch_offset_deg, degrees=True)
        cameras[name] = dict(common, **optical_pose(origin+rotation.apply(position), rotation*local))
        sources[name] = dict(file="scene.xml", camera=source_name, frame="source model frame to shared world")
    wrist = optical_pose([0, -.0824748, -.0095955], Rotation.from_euler("x", 2.70525955359))
    for side in ("left", "right"):
        name = f"cam_{side}_wrist"
        cameras[name] = dict(common, **optical_pose(origin+[0, 0, .3], Rotation.identity()),
            attach=dict(enabled=True, entity="robot", link=f"{side}/gripper_base",
                        offset_pos=wrist["pos"], offset_lookat=wrist["lookat"], offset_up=wrist["up"]))
        sources[name] = dict(file="aloha.xml", camera=f"wrist_cam_{side}", frame=f"{side}/gripper_base")
    fx, fy = np.asarray(resolution)*FOCAL_M/SENSOR_M
    source_k = [[float(fx), 0, width/2], [0, float(fy), height/2], [0, 0, 1]]
    genesis_k = [[float(fy), 0, width/2], [0, float(fy), height/2], [0, 0, 1]]
    metadata = dict(source=SOURCE, recording_names_source="https://github.com/tonyzhaozh/aloha/blob/main/aloha_scripts/robot_utils.py",
        cameras=sources, source_frame_origin_m=origin.tolist(), resolution=list(resolution), vertical_fov_deg=fov,
        source_intrinsics=source_k, configured_genesis_intrinsics=genesis_k,
        focal_x_relative_error=float(fy/fx-1), hardware_calibration_equivalent=False,
        cam_low_pitch_offset_deg=float(low_pitch_offset_deg),
        optical_note="Pinned mounts and vertical FOV; Genesis scalar FOV uses square pixels, unlike the source sensor aspect ratio.")
    return cameras, metadata


def configure_aloha_rig(cfg, *, keep=("room", "oblique"), resolution=(1280, 720), low_pitch_offset_deg=0.):
    if cfg.robot_control.robot.name != "aloha":
        raise ValueError("The ALOHA observation rig requires the paired ALOHA model")
    from .tabletop import tabletop_frames_from_config
    frames = tabletop_frames_from_config(cfg.env)
    # The shared task frame has XY=(0, 0), while the ALOHA pair is translated
    # along the table. Source cameras are centred on the symmetric robot pair.
    origin = np.asarray(cfg.env.robot_mount.pos, dtype=float).copy()
    # The MJCF adapter lowers both source bases by 20 mm. Apply the same
    # source-frame translation to the external cameras to retain their poses
    # relative to the robot and its attached wrist cameras.
    rotation = Rotation.from_euler("xyz", cfg.env.robot_mount.euler, degrees=True)
    adapter_z = -.02+float(cfg.robot_control.robot.get("base_riser_height_m", 0.))
    origin += rotation.apply([0, 0, adapter_z])
    cameras, metadata = make_aloha_rig(origin, table_rotation=rotation, resolution=resolution,
                                     low_pitch_offset_deg=low_pitch_offset_deg)
    metadata["source_frame_origin_m"] = origin.tolist()
    metadata["local_table_surface_z_m"] = float(frames.table_surface_origin[2])
    metadata["robot_adapter_z_translation_m"] = adapter_z
    metadata["frame_note"] = "External cameras share the robot adapter translation, including any declared base riser."
    for name in keep:
        if name in cfg.env.cameras:
            cameras[name] = OmegaConf.to_container(cfg.env.cameras[name], resolve=True)
    cfg.env.cameras = OmegaConf.create(cameras)
    if "camera_rig" in cfg.env:
        cfg.env.camera_rig = OmegaConf.create(dict(id="aloha_canonical_observation",
            observation_cameras=list(CAMERA_NAMES), preview_cameras=list(cameras)))
    return metadata
