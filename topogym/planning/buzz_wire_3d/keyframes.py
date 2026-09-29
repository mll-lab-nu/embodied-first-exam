"""Connect a small set of measured poses, adding guide points only as needed.

This is a read-only, fixed-grasp planner. A certificate covers sampled IK and
collision checks, not grasp acquisition, release dynamics, or Task success.
"""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .policy import rotation


def resolve_keyframes(world, keyframes):
    """Resolve entity-local poses using one unlimited observation.

    Each row has position_m and quaternion_wxyz. If entity is supplied, these
    are local to that body's observed frame; otherwise they are world poses.
    No coordinates are written back to the simulation.
    """
    resolved = []
    for row in keyframes:
        p = np.asarray(row["position_m"], dtype=float)
        if p.shape != (3,) or not np.isfinite(p).all():
            raise ValueError("A keyframe position must contain three finite values")
        r = rotation(row["quaternion_wxyz"])
        if row.get("entity") is not None:
            body = world["bodies"][row["entity"]]
            origin = np.asarray(body["position_m"], dtype=float)
            basis = rotation(body["quaternion_wxyz"])
            p, r = origin + basis.apply(p), basis * r
        resolved.append(dict(label=row.get("label", str(len(resolved))),
                             position_m=p.tolist(),
                             quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist()))
    return resolved


def connect_held_guide(kin, guide, offset_p, offset_r, *, mandatory_indices=(),
                       minimum_clearance=.0015, maximum_material_step=.0005,
                       maximum_joint_step=.0015, allow_wand_support=False,
                       joint_speed=.08, translation_speed=.006, rotation_speed=.15):
    """Try direct connections; retain a guide point only if a check fails.

    guide contains world poses, is ordered, and belongs to ONE fixed grasp. Its first pose must
    match the measured seed and grasp transform. Mandatory points preserve
    task-specific gates. Rejected edges are split at the guide's greatest
    deviation from their straight-position/shortest-rotation interpolation.
    The IK seed is propagated along the connected path and restored on exit.
    No failed shortcut is included in the returned plan.
    """
    if len(guide) < 2:
        raise ValueError("At least a measured start and one target are required")
    if minimum_clearance <= 0 or maximum_material_step <= 0 or maximum_joint_step <= 0:
        raise ValueError("Clearance and sampling steps must be positive")
    if any(not isinstance(i, (int, np.integer)) or not 0 <= i < len(guide)
           for i in mandatory_indices):
        raise ValueError("Mandatory indices must refer to guide poses")
    poses = resolve_keyframes({"bodies": {}}, guide)
    ps = np.asarray([row["position_m"] for row in poses])
    rs = Rotation.from_quat(np.asarray([row["quaternion_wxyz"] for row in poses])[:, [1, 2, 3, 0]])
    initial_seed = kin.seed.copy()
    tcp_p, tcp_r = kin.tcp_pose(initial_seed)
    start_r = tcp_r * offset_r.inv()
    start_p = tcp_p - start_r.apply(offset_p)
    if np.linalg.norm(start_p-ps[0]) > .0002 or (start_r*rs[0].inv()).magnitude() > .002:
        raise ValueError("Guide does not start at the measured fixed-grasp pose")
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(ps, axis=0), axis=1)
                              + .09*(rs[1:]*rs[:-1].inv()).magnitude())]
    anchors = sorted({0, len(guide)-1, *mandatory_indices})
    selected, rejected, edges, frames, references = [0], [], [], [], []
    elapsed = 0.

    def split_index(a, b):
        length = arc[b]-arc[a]
        u = ((arc[a+1:b]-arc[a])/length if length > 1e-12
             else np.linspace(0., 1., b-a+1)[1:-1])
        turn = Slerp([0., 1.], Rotation.from_quat([rs[a].as_quat(), rs[b].as_quat()]))
        errors = (np.linalg.norm(ps[a+1:b]-(ps[a]+u[:, None]*(ps[b]-ps[a])), axis=1)
                  + .09*(rs[a+1:b]*turn(u).inv()).magnitude())
        return a+1+int(np.argmax(errors)) if errors.max() > 1e-10 else (a+b)//2

    def connect(a, b):
        nonlocal elapsed
        saved = kin.seed.copy()
        try:
            segment = kin.plan_held_waypoints(
                [(ps[b], rs[b])], offset_p, offset_r,
                allow_wand_support=allow_wand_support,
                minimum_clearance=minimum_clearance,
                maximum_material_step=maximum_material_step)
            refs = kin.joint_references(
                segment, offset_p, offset_r, joint_speed=joint_speed,
                translation_speed=translation_speed, rotation_speed=rotation_speed,
                maximum_joint_step=maximum_joint_step,
                allow_wand_support=allow_wand_support)
            # joint_references has its own lower bound. Apply this caller's
            # requested bound to the actual joint-interpolated body poses too.
            gaps = [kin.clearance(saved, (start_p, start_r),
                                  allow_wand_support=allow_wand_support)] if a == 0 else []
            for row in refs:
                q = np.asarray(row["qpos"])
                tp, tr = kin.tcp_pose(q)
                rr = tr*offset_r.inv()
                gaps.append(kin.clearance(q, (tp-rr.apply(offset_p), rr),
                                          allow_wand_support=allow_wand_support))
            if gaps and (not np.isfinite(gaps).all() or min(gaps) < minimum_clearance):
                raise ValueError("Joint interpolation violates the requested clearance")
        except ValueError as error:
            kin.seed = saved
            rejected.append(dict(start=a, end=b, reason=str(error)))
            if b == a+1:
                raise ValueError(f"Guide edge {a}->{b} remains infeasible: {error}") from error
            middle = split_index(a, b)
            connect(a, middle)
            connect(middle, b)
            return
        kin.seed = np.asarray(segment[-1]["qpos"])
        frames.extend(segment if not frames else segment[1:])
        for row in (refs[1:] if references else refs):
            references.append(dict(row, time_s=row["time_s"]+elapsed))
        if refs:
            elapsed = references[-1]["time_s"]
        selected.append(b)
        edges.append(dict(start=a, end=b, checked_joint_samples=len(refs),
                          minimum_clearance_m=min(gaps) if gaps else None))

    try:
        for a, b in zip(anchors, anchors[1:]):
            connect(a, b)
    finally:
        kin.seed = initial_seed
    return dict(scope="sampled fixed-grasp IK/collision path; no physical execution",
                guide_pose_count=len(guide), keyframe_count=len(selected),
                keyframe_indices=selected, keyframes=[poses[i] for i in selected],
                mandatory_indices=anchors, edges=edges, rejected_shortcuts=rejected,
                maximum_material_step_m=maximum_material_step,
                maximum_joint_step_rad=maximum_joint_step,
                requested_clearance_m=minimum_clearance,
                frames=frames, refs=references, task_success_verified=False)
