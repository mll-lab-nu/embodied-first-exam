"""Detached Buzz Wire layout candidates; never changes registered resources.

The final bend blends a small XY displacement with zero first/second endpoint
derivatives. The final straight post translates rigidly. Tool dimensions,
contact roles, task thresholds and all preceding route controls stay unchanged.
"""
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from ..contracts import digest


def patched_layout(layout, parameters):
    if not isinstance(parameters, dict) or set(parameters) - {"finish_offset_xy_m"}:
        raise ValueError("Buzz geometry accepts finish_offset_xy_m only")
    delta = np.asarray(parameters.get("finish_offset_xy_m", [0., 0.]), dtype=float)
    if delta.shape != (2,) or not np.isfinite(delta).all() or np.linalg.norm(delta) > .06:
        raise ValueError("Finish offset needs two finite metres, norm <= 0.06")
    controls = np.asarray(layout.authored_controls_m, dtype=float).copy()
    sections = list(layout.authored_section_ends)
    names = [row[0] for row in sections]
    if "exit_bend" not in names or names[-1] != "finish_post":
        raise ValueError("Buzz candidate requires authored exit_bend and finish_post sections")
    index = names.index("exit_bend")
    start, end = int(sections[index-1][1]), int(sections[index][1])
    segment = controls[start:end+1]
    length = np.r_[0., np.cumsum(np.linalg.norm(np.diff(segment, axis=0), axis=1))]
    u = length / length[-1]
    blend = 10*u**3-15*u**4+6*u**5
    controls[start:end+1, :2] += blend[:, None]*delta
    controls[end+1:, :2] += delta
    # The entire connector must still be supported by the existing deck.
    if np.any(abs(controls[-1, :2])+np.asarray(layout.mount_size_m[:2])/2
              > np.asarray(layout.base_size_m[:2])/2):
        raise ValueError("Candidate finish connector would leave the deck")
    result = replace(layout, authored_controls_m=tuple(map(tuple, controls)))
    result.validate()
    return result


def preview(task, parameters, output):
    from topogym.assets.geometry.buzz_wire_3d import generate_assets, endpoint_pose
    from topogym.utils.io import write_json_atomic, sha256_file
    original = task.build_layout()
    layout = patched_layout(original, parameters)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    route, geometry = generate_assets(output / "assets", layout)
    write_json_atomic(output / "layout.json", asdict(layout))
    endpoints = {}
    for end in (0, 1):
        p, r = endpoint_pose(route, end)
        endpoints[str(end)] = dict(position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist())
    manifest = dict(candidate_id=output.name, source_resource=task.layout_resource,
        base_sha256=digest(asdict(original)), candidate_sha256=digest(asdict(layout)),
        parameters=parameters, geometry=geometry, endpoints_local=endpoints,
        minimum_curvature_radius_m=float(route.minimum_curvature_radius),
        route_length_m=float(route.length), requires_rebuild=True,
        physical_execution_verified=False, formal_qualification=False,
        assets={str(p.relative_to(output)): sha256_file(p) for p in sorted(output.rglob("*")) if p.is_file()})
    write_json_atomic(output / "manifest.json", manifest)
    return dict(manifest, output=str(output))


def install_collision_candidate(kin, route, origin, base_objects):
    """Replace only detached query obstacles with conservative analytic solids.

    The built robot, tool and scene are untouched. Capsules contain the faceted
    native capsule surfaces; this is a sampled planning check, not physics.
    Wooden connectors remain obstacles here and are separately labelled.
    """
    import fcl
    from scipy.spatial.transform import Rotation
    from topogym.planning.buzz_wire_3d.kinematics import manager
    obstacles, names = [], []
    for index, (a, b, radius, part) in enumerate(route.fixed_capsules()):
        a, b = np.asarray(a)+origin, np.asarray(b)+origin
        delta = b-a
        length = np.linalg.norm(delta)
        if part == "stop":
            shape, rotation = fcl.Box(*route.layout.mount_size_m), np.eye(3)
        elif length < 1e-12:
            shape, rotation = fcl.Sphere(radius), np.eye(3)
        else:
            shape = fcl.Capsule(radius, length)
            rotation = Rotation.align_vectors([delta/length], [[0., 0., 1.]])[0].as_matrix()
        obstacles.append(fcl.CollisionObject(shape, fcl.Transform(rotation, (a+b)/2)))
        names.append(dict(part=part, index=index, center_world_m=((a+b)/2).tolist()))
    # Base collision surfaces already contain world vertices, unchanged by the
    # local final-bend edit. Keep them when replacing detached wire obstacles.
    kin.fixed_objects = obstacles + list(base_objects)
    kin.fixed = manager(kin.fixed_objects)
    kin.wire_fixed = manager(obstacles)
    return names


def fixture_task(task_class, parameters, *, initial_wand_pose=None):
    """Fresh owner-only declaration for a candidate or local terminal probe.

    Select this class before Env.reset. No buffers or route progress are edited.
    A supplied pose is a local experiment birth, never a restored checkpoint.
    """
    if task_class.task_id != "buzz_wire_3d":
        raise ValueError("Expected Buzz Wire task")
    from copy import deepcopy
    from ..geometry import pose
    parameters = deepcopy(parameters)
    if initial_wand_pose is not None:
        pose(initial_wand_pose)
        initial_wand_pose = deepcopy(initial_wand_pose)

    class BuzzWireCandidate(task_class):
        model_revision = task_class.model_revision + "_development_candidate"

        def build_layout(self):
            return patched_layout(super().build_layout(), parameters)

        def declare(self, asset_dir, table_height_m):
            from topogym.utils.io import write_json_atomic
            spec = super().declare(asset_dir, table_height_m)
            metadata = dict(parameters=parameters, initial_wand_pose=initial_wand_pose,
                formal_qualification=False, requires_user_review=True,
                scope="fresh candidate scene; no velocity, grasp or route history injected")
            write_json_atomic(Path(asset_dir)/"buzz_development_candidate.json", metadata)
            if initial_wand_pose is not None:
                spec = replace(spec, entities=tuple(replace(e,
                    position_m=tuple(initial_wand_pose["position_m"]),
                    quaternion_wxyz=tuple(initial_wand_pose["quaternion_wxyz"]))
                    if e.name == "wand" else e for e in spec.entities))
            return replace(spec, metadata=dict(spec.metadata, development_candidate=metadata))

    return BuzzWireCandidate
