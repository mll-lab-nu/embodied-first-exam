"""Retarget both hands together; never jitter puzzle poses under unchanged qpos."""
from copy import deepcopy
import json

import numpy as np
from omegaconf import OmegaConf
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .inverse_variants import pack, save, sha
from .robot_motion import Kinematics, bodies_from_fk


def retarget(folder, selected, robot_config):
    shift = np.array([selected["center_dx_m"], selected["center_dy_m"], 0.])
    yaw = float(selected["yaw_deg"])
    if not yaw and not np.any(shift):
        return
    rotation = Rotation.from_euler("z", yaw, degrees=True).as_matrix()
    center = np.array([0., 0., .28])
    kin = Kinematics(OmegaConf.create(robot_config))
    trace = json.loads((folder / "ik_proposal.json").read_text())
    kin.q = np.array(trace["frames"][0]["qpos"])
    maximum = np.zeros(4)
    indices = kin.indices["left"] + kin.indices["right"]
    for frame in trace["frames"]:
        old = deepcopy(frame["grasp_targets"])
        midpoint = center + shift + rotation @ ((np.array(old["left"]["pos"]) + old["right"]["pos"])/2 - center)
        wanted = frame["relative_pose"]
        relative_r = Rotation.from_quat(wanted["quaternion_xyzw"]).as_matrix()
        relative_t = np.array(wanted["translation_mm"]) * .003
        gold_target = rotation @ Rotation.from_quat(frame["bodies"]["keyhole_gold"]["quat"]).as_matrix()
        previous = kin.q[indices].copy()

        def residual(q):
            kin.q[indices] = q
            (rg, tg), (rs, ts) = bodies_from_fk(kin)
            current_center = (kin.pose("left")[0] + kin.pose("right")[0])/2
            # Keep relative puzzle motion, hand midpoint and world yaw. Common
            # pitch/roll remain free so a near-limit arm is not overconstrained.
            return np.r_[20*(rg.T @ (ts-tg) - relative_t),
                Rotation.from_matrix(rg.T @ rs @ relative_r.T).as_rotvec(),
                10*(current_center-midpoint),
                Rotation.from_matrix(rg @ gold_target.T).as_rotvec()[2],
                .00003*(q-previous)]

        limits = np.tile(kin.limits, (2, 1))
        fit = least_squares(residual, previous, bounds=(limits[:, 0]+1e-6, limits[:, 1]-1e-6),
            max_nfev=180, ftol=1e-11, xtol=1e-11, gtol=1e-11)
        e = residual(fit.x)
        error = np.array([np.linalg.norm(e[:3])/20, np.linalg.norm(e[3:6]),
                          np.linalg.norm(e[6:9])/10, abs(e[9])])
        maximum = np.maximum(maximum, error)
        if np.any(error > [.00001, .00005, .00001, .00005]):
            raise ValueError(f"Coupled pose retargeting unreachable: {error.tolist()}")
        bodies = bodies_from_fk(kin)
        (rg, tg), (rs, ts) = bodies
        frame["qpos"] = kin.q.tolist()
        frame["bodies"] = {n: dict(pos=p.tolist(), quat=Rotation.from_matrix(r).as_quat().tolist())
            for n, (r, p) in zip(("keyhole_gold", "keyhole_silver"), bodies)}
        frame["grasp_targets"] = {side: dict(pos=kin.pose(side)[0].tolist(),
            quat=Rotation.from_matrix(kin.pose(side)[1]).as_quat().tolist()) for side in ("left", "right")}
        frame["relative_pose"] = pack(rg.T @ rs, rg.T @ (ts - tg))
    proposal = json.loads((folder / "proposal.json").read_text())
    proposal.update(scene_pose_jitter=dict(translation_m=shift.tolist(), yaw_deg=yaw),
                    family_ik_frozen=False, family_relative_motion_preserved=True)
    save(folder / "proposal.json", proposal)
    trace["report"].update(source_proposal_sha256=sha(folder / "proposal.json"),
        family_ik_reused=False, pose_retargeted=True, max_relative_ik_position_error_m=float(maximum[0]),
        max_relative_ik_rotation_error_rad=float(maximum[1]), max_midpoint_error_m=float(maximum[2]),
        max_world_yaw_residual_rad=float(maximum[3]), common_pitch_roll_free=True)
    save(folder / "ik_proposal.json", trace)
    record = json.loads((folder / "geometry.json").read_text())
    record.update(source_proposal_sha256=sha(folder / "proposal.json"),
                  input_trace_sha256=sha(folder / "ik_proposal.json"), scene_pose_jitter=proposal["scene_pose_jitter"])
    save(folder / "geometry.json", record)
