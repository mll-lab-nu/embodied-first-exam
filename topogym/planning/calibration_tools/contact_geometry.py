"""Read-only contact provenance and distances between actual collision surfaces."""
import numpy as np

from .contracts import UnsupportedCapability, json_value


def contacts(env, entities=None):
    from .inspection import contact_summary
    from topogym.utils.arrays import to_numpy
    world = env._world
    # Query once so optional positions refer to exactly the same native buffer rows.
    solver = world.scene.sim.rigid_solver
    values = solver.collider.get_contacts(as_tensor=True, to_torch=True) if solver.is_active else {}
    converted = {k: to_numpy(v) for k, v in values.items() if k in {"link_a", "link_b", "force", "penetration", "position", "pos"}}
    measured = dict(physics_step=world.physics_step, contacts=converted)
    result = contact_summary(measured, world.entities, entities)
    positions = converted.get("position", converted.get("pos"))
    if positions is not None:
        positions = np.asarray(positions).reshape(-1, 3)
        a, b = np.asarray(converted["link_a"]).reshape(-1), np.asarray(converted["link_b"]).reshape(-1)
        if len(positions) != len(a):
            raise ValueError("Native contact positions and pairs have different lengths")
        names = {link.idx: name for name, entity in world.entities.items() for link in getattr(entity, "links", ())}
        selected = set(entities) if entities is not None else None
        valid = [i for i, (first, second) in enumerate(zip(a, b)) if first >= 0 and second >= 0 and
                 (selected is None or names.get(int(first)) in selected or names.get(int(second)) in selected)]
        for row, index in zip(result["contacts"], valid):
            row["contact_position_world_m"] = positions[index].tolist()
        result["contact_positions_available"] = True
    for row in result["contacts"]:
        row["source"] = "genesis_rigid_contact_buffer"
    coupler = world.scene.sim.coupler
    result.update(ipc=dict(active=hasattr(coupler, "_ipc_world"), contacts=None,
        force_available=False, contact_points_available=False,
        reason="native IPC pair/force/position mapping is not exposed by this adapter",
        ownership=getattr(coupler, "contact_ownership", None)),
        physics_steps_advanced=0, scope="sampled backend contacts; surface proximity is reported separately")
    return result


def link_surface(env, name, source="auto"):
    """Return world-space vertices and triangle IDs from the selected built backend."""
    import trimesh
    from topogym.utils.arrays import to_numpy
    link = env._robot.entity.get_link(name)
    coupler = env._world.scene.sim.coupler
    ipc = hasattr(coupler, "_abd_state_geom")
    if source not in {"auto", "ipc", "genesis"}:
        raise ValueError("source must be auto, ipc or genesis")
    if source == "ipc" or source == "auto" and ipc:
        if not ipc or link not in coupler._abd_slots_by_link:
            raise UnsupportedCapability("Native IPC finger surface is unavailable")
        import uipc
        slots = coupler._abd_slots_by_link[link]
        if len(slots) != 1:
            raise UnsupportedCapability("Gripper geometry currently supports one environment")
        geometry = slots[0].geometry()
        index = list(coupler._abd_slots_by_link).index(link)
        transforms = np.asarray(coupler._abd_state_geom.instances().find(uipc.builtin.transform).view())
        local = np.asarray(geometry.positions().view()).reshape(-1, 3)
        transform = transforms[index]
        vertices = local @ transform[:3, :3].T+transform[:3, 3]
        faces = np.asarray(geometry.triangles().find(uipc.builtin.topo).view()).reshape(-1, 3)
        return vertices, faces, "ipc_affine_collision_surface"
    meshes = [trimesh.Trimesh(to_numpy(g.get_verts()).reshape(-1, 3), np.asarray(g.init_faces), process=False)
              for g in link.geoms if g.contype or g.conaffinity]
    if not meshes:
        raise UnsupportedCapability("Finger has no imported collision surface")
    mesh = trimesh.util.concatenate(meshes)
    return np.asarray(mesh.vertices), np.asarray(mesh.faces), "genesis_collision_surface"


def surface_distance(left, right):
    """Triangle surface distance and witnesses; never reports a measured force."""
    import trimesh
    first, second = trimesh.collision.CollisionManager(), trimesh.collision.CollisionManager()
    first.add_object("left", trimesh.Trimesh(*left, process=False))
    second.add_object("right", trimesh.Trimesh(*right, process=False))
    hit = bool(first.in_collision_other(second))
    gap, data = first.min_distance_other(second, return_data=True)
    points = None
    if not hit and np.isfinite(gap):
        points = dict(left_world_m=data.point("left").tolist(), right_world_m=data.point("right").tolist())
    return dict(distance_m=0. if hit else float(gap) if np.isfinite(gap) else None,
                surfaces_intersect=hit, nearest_points=points, measurement="triangle_surface_geometry",
                penetration_depth_m=None, contact_force_n=None)


def _patch(surface, indices):
    vertices, faces = surface
    if not isinstance(indices, (list, tuple)) or not indices or any(type(i) is not int for i in indices):
        raise ValueError("Pad faces must be a nonempty list of triangle indices")
    if len(set(indices)) != len(indices) or min(indices) < 0 or max(indices) >= len(faces):
        raise ValueError("Pad face indices must be distinct and within the reported surface")
    return vertices, faces[indices]


def gripper_geometry(env, hand=None, *, pad_faces=None, source="auto"):
    """Whole-finger surface clearance by default; named pad patches opt in explicitly."""
    robot, hands = env._robot, {}
    if hand is not None and hand not in robot.groups:
        raise ValueError("Unknown hand")
    pad_faces = pad_faces or {}
    if not set(pad_faces) <= robot.groups.keys():
        raise ValueError("Unknown pad_faces hand")
    q = robot.observe()
    targets = robot.capture_state().targets
    for side, group in robot.groups.items():
        if hand is not None and hand != side:
            continue
        if group.grasp is None or len(group.grasp.finger_links) != 2:
            hands[side] = dict(available=False, reason="two opposing finger links are not declared")
            continue
        names = group.grasp.finger_links
        surfaces = [link_surface(env, n, source) for n in names]
        distance = surface_distance(*[s[:2] for s in surfaces])
        pad = None
        if side in pad_faces:
            patches = pad_faces[side]
            if set(patches) != set(names):
                raise ValueError("Declare pad triangle indices for both exact finger link names")
            pad = surface_distance(*[_patch(s[:2], patches[n]) for n, s in zip(names, surfaces)])
        hands[side] = dict(available=True, finger_links=list(names),
            source=[s[2] for s in surfaces], triangle_counts=[len(s[1]) for s in surfaces],
            actual_finger_coordinates={k: v for k, v in q[side].items() if k.startswith("finger_position_")},
            commanded_gripper_coordinate=targets.get(side, {}).get(group.gripper_field),
            coordinate_unit="m" if group.gripper_field.endswith("_m") else "rad",
            finger_surface_clearance=distance, pad_surface_clearance=pad,
            pad_definition="caller_selected_triangles" if pad is not None else "unavailable_without_pad_selection",
            note="joint coordinate, whole-finger surface clearance and pad clearance are different quantities")
    return json_value(dict(hands=hands, physics_step=env._world.physics_step, physics_steps_advanced=0,
                           coverage="current built collision surfaces; no force inference or contact attribution"))
