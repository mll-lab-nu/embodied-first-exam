"""Public pinhole calibration and poses, independent of simulator state access."""
import math


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
        width, height = config["res"]
        focal = height/(2*math.tan(math.radians(config["fov"])/2))
        info = dict(resolution_px=[width, height], vertical_fov_deg=config["fov"],
            clipping_m=[config["near"], config["far"]],
            K_px=[[focal, 0, width/2], [0, focal, height/2], [0, 0, 1]],
            distortion="none (ideal simulated pinhole)",
            camera_cv_axes="+x right, +y down, +z forward; pixels u right, v down, origin top-left",
            projection="[u,v,1] proportional to K_px @ (T_camera_cv_from_world @ [X,Y,Z,1])[:3]",
            calibration_note="Genesis vertical FOV / square pixels; not real hardware calibration")
        attach = config.get("attach", {})
        if attach.get("enabled"):
            transform = optical_transform(*(attach["offset_"+k] for k in ("pos", "lookat", "up")))
            # Same algebra as world poses, labelled as link-local here.
            local = pose_metadata(transform)["T_world_from_camera_cv"]
            info.update(motion="wrist_attached", parent_link=attach["link"],
                T_parent_link_from_camera_cv=local,
                world_pose="Read observation.camera_poses for this frame; mount link differs from hand_pos link")
        else:
            info.update(motion="fixed", **pose_metadata(optical_transform(
                *(config[k] for k in ("pos", "lookat", "up")))))
        result[name] = info
    return result
