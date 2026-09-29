"""Public pinhole calibration and poses, independent of simulator state access."""
import math


def pinhole_intrinsics(resolution_px, vertical_fov_deg):
    """Ideal square-pixel calibration shared by declarations and live frames."""
    width, height = resolution_px
    angle = float(vertical_fov_deg)
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (width, height)):
        raise ValueError("Camera resolution must contain positive integer pixels")
    if not math.isfinite(angle) or not 0 < angle < 180:
        raise ValueError("Vertical camera FOV must lie between 0 and 180 degrees")
    focal = height / (2 * math.tan(math.radians(angle) / 2))
    return dict(resolution_px=[width, height], vertical_fov_deg=angle,
                K_px=[[focal, 0., width / 2], [0., focal, height / 2], [0., 0., 1.]],
                distortion="none (ideal simulated pinhole)",
                camera_cv_axes="+x right, +y down, +z forward; pixels u right, v down, origin top-left",
                projection="[u,v,1] proportional to K_px @ (T_camera_cv_from_world @ [X,Y,Z,1])[:3]",
                calibration_note="Genesis vertical FOV / square pixels; not real hardware calibration")


def optical_transform(pos, lookat, up):
    """OpenGL camera to parent transform (+x right, +y up, -z forward)."""
    import numpy as np
    pos, lookat, up = (np.asarray(v, dtype=float) for v in (pos, lookat, up))
    z = pos-lookat
    z /= np.linalg.norm(z)
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    transform = np.eye(4)
    transform[:3, :3] = np.column_stack((x, np.cross(z, x), z))
    transform[:3, 3] = pos
    return transform


def pose_metadata(transform):
    import numpy as np
    gl = np.asarray(transform, dtype=float)
    cv = gl @ np.diag([1., -1., -1., 1.])
    return dict(T_world_from_camera_cv=cv.tolist(),
                T_camera_cv_from_world=np.linalg.inv(cv).tolist(),
                position_world_m=gl[:3, 3].tolist(),
                forward_world=(-gl[:3, 2]).tolist(), up_world=gl[:3, 1].tolist())


def camera_contract(configs):
    """Fixed world poses or moving link-relative poses; never export placeholders."""
    result = {}
    for name, config in configs.items():
        info = pinhole_intrinsics(config["res"], config["fov"])
        info["clipping_m"] = [config["near"], config["far"]]
        attach = config.get("attach", {})
        if attach.get("enabled"):
            transform = optical_transform(*(attach["offset_"+k] for k in ("pos", "lookat", "up")))
            # Same algebra as world poses, labelled as link-local here.
            local = pose_metadata(transform)["T_world_from_camera_cv"]
            info.update(motion="wrist_attached", parent_link=attach["link"],
                T_parent_link_from_camera_cv=local,
                world_pose="Read SensorFrame.camera_metadata for this state; mount link differs from hand_pos link")
        else:
            info.update(motion="fixed", **pose_metadata(optical_transform(
                *(config[k] for k in ("pos", "lookat", "up")))))
        result[name] = info
    return result
