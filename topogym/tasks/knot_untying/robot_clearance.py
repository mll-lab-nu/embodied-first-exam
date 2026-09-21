"""Discrete robot geometry checks using measured joints and the IK model.

These checks do not simulate the rope or certify a continuous swept path.
"""
import mujoco
import numpy as np

from .robot_probe import TOOL_OFFSET, rotation


def measured_robot_data(ik, controller):
    data = mujoco.MjData(ik.model)
    indices = {}
    for side, arm in controller.arms.items():
        names = list(controller.cfg.robot.arm_joint_names) + list(controller.cfg.robot.finger_joint_names)
        indices[side] = [int(ik.model.joint(f'{side}/{name}').qposadr[0]) for name in names]
        data.qpos[indices[side]] = np.r_[arm.arm_qpos(), arm.gripper_qpos()]
    return data, indices


def measured_robot_overlap(ik, controller, *, floor_height_m=None, gripper_geometries=None):
    data, _ = measured_robot_data(ik, controller)
    mujoco.mj_forward(ik.model, data)
    contact = min(data.contact, key=lambda c: c.dist, default=None)
    if contact is None or contact.dist >= 0:
        result = dict(penetration_m=0., bodies=[])
    else:
        result = dict(penetration_m=-float(contact.dist),
                      bodies=[ik.model.body(int(ik.model.geom(g).bodyid[0])).name for g in contact.geom])
    if gripper_geometries is not None:
        result['gripper_floor_clearance_m'] = min(gripper_floor_clearance(ik, data, meshes, floor_height_m)
                                                 for meshes in gripper_geometries.values())
    return result


def gripper_geometry(ik, side):
    meshes = []
    for geom in range(ik.model.ngeom):
        body = ik.model.body(int(ik.model.geom_bodyid[geom])).name
        if not body.startswith(f'{side}/') or not any(s in body for s in ('finger', 'gripper', 'wrist')):
            continue
        if ik.model.geom_type[geom] == mujoco.mjtGeom.mjGEOM_MESH:
            mesh = int(ik.model.geom_dataid[geom])
            start, count = int(ik.model.mesh_vertadr[mesh]), int(ik.model.mesh_vertnum[mesh])
            meshes.append((geom, ik.model.mesh_vert[start:start+count].copy(), 0.))
        elif ik.model.geom_type[geom] == mujoco.mjtGeom.mjGEOM_SPHERE:
            meshes.append((geom, np.zeros((1, 3)), float(ik.model.geom_size[geom, 0])))
        else:
            raise ValueError(f'Unsupported gripper geometry: {body}')
    if not meshes:
        raise ValueError('Robot model contains no gripper meshes')
    return meshes


def gripper_floor_clearance(ik, data, meshes, floor_height_m):
    return min(float((ik.mount_position+ik.mount_rotation.apply(
        vertices@data.geom_xmat[geom].reshape(3, 3).T+data.geom_xpos[geom]))[:, 2].min()-radius-floor_height_m)
        for geom, vertices, radius in meshes)


def checked_grasp_approach(ik, controller, side, point, quat, finger_qpos, *, clearance_m=.003,
                           hover_heights_m=(.04, .06, .08), floor_height_m=None,
                           table_clearance_m=.001):
    """Plan the joint approach and vertical descent with a positive margin.

    Restore all IK scratch state even on rejection. Return only robot targets;
    grasp engagement remains the responsibility of the native contact gate.
    """
    data, indices = measured_robot_data(ik, controller)
    start = data.qpos[indices[side][:6]].copy()
    start_fingers = data.qpos[indices[side][6:]].copy()
    old_qpos = ik.data.qpos.copy()
    old_previous = {name: q.copy() for name, q in ik.previous.items()}
    old_margins = ik.model.geom_margin.copy()
    rejected = []
    meshes = gripper_geometry(ik, side) if floor_height_m is not None else None

    def check(q, fingers):
        data.qpos[indices[side][:6]] = q
        data.qpos[indices[side][6:]] = fingers
        mujoco.mj_forward(ik.model, data)
        if any(c.dist < clearance_m-1e-8 for c in data.contact):
            c = min(data.contact, key=lambda c: c.dist)
            bodies = [ik.model.body(int(ik.model.geom(g).bodyid[0])).name for g in c.geom]
            raise ValueError(f'{bodies}: robot clearance {c.dist:.6f} m < {clearance_m:.6f} m')
        if meshes is not None:
            gap = gripper_floor_clearance(ik, data, meshes, floor_height_m)
            if gap < table_clearance_m:
                raise ValueError(f'Gripper/table clearance {gap:.6f} m < {table_clearance_m:.6f} m')

    try:
        ik.model.geom_margin[:] = np.maximum(old_margins, clearance_m)
        for height in hover_heights_m:
            if not np.isfinite(height) or height <= 0:
                raise ValueError('Grasp hover heights must be finite and positive')
            try:
                end = ik.solve(side, point+[0., 0., height]-rotation(quat).apply(TOOL_OFFSET), quat,
                               seed=np.asarray(controller.cfg.home[side][:6]))
                steps = max(2, int(np.ceil(np.max(abs(end-start))/.025)))
                for u in np.linspace(0., 1., steps+1):
                    check(start+(end-start)*u, start_fingers+(finger_qpos-start_fingers)*u)
                for z in np.linspace(height, 0., int(np.ceil(height/.002))+1):
                    q = ik.solve(side, point+[0., 0., z]-rotation(quat).apply(TOOL_OFFSET), quat)
                    check(q, finger_qpos)
                return dict(start_qpos=start, end_qpos=end, hover_height_m=height,
                            minimum_checked_clearance_m=clearance_m,
                            minimum_checked_table_clearance_m=(table_clearance_m if meshes else None),
                            scope='discrete robot poses only; native physics checks remain required')
            except ValueError as exc:
                rejected.append(dict(hover_height_m=height, reason=str(exc)))
        raise ValueError(f'No robot-clear regrasp approach: {rejected}')
    finally:
        ik.model.geom_margin[:] = old_margins
        ik.data.qpos[:] = old_qpos
        ik.previous = old_previous
