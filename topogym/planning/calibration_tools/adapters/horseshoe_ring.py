"""Detached Horseshoe modeling candidates; never changes installed task assets."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from ..contracts import UnsupportedCapability, digest


ALLOWED = {
    "target_ring": {"centerline_radii", "wire_radius"},
    "horseshoe": {"band_width", "thickness", "edge_bevel"},
}


@contextmanager
def declaration(task, parameters):
    """Override asset generation only during a disposable owner's declaration.

    The original layout is an unqualified candidate starting pose. A changed
    shape must be settled and checked again before any physical qualification.
    This context belongs in the isolated calibration worker, not a policy.
    """
    from topogym.tasks.horseshoe_ring import common
    from topogym.assets import variation_resources
    original, record = template_candidate(task, parameters)
    generate = common.generate_assets
    read = variation_resources.read_json
    layout = None
    if task.layout_resource:
        layout = read(task.layout_resource)
        rebased = rebase_poses(task, parameters, layout["poses"])
        layout = dict(layout, poses={name: dict(value, **rebased["poses"][name])
                                     for name, value in layout["poses"].items()})

    def candidate_assets(output, *, template=None, scale=2.):
        if template != original:
            raise ValueError("Geometry candidate source template changed")
        return generate(output, template=record, scale=scale)

    common.generate_assets = candidate_assets
    def candidate_resource(resource):
        return deepcopy(layout) if layout is not None and resource == task.layout_resource else read(resource)

    variation_resources.read_json = candidate_resource
    try:
        yield dict(source_resource=task.template_resource, base_sha256=digest(original),
                   candidate_sha256=digest(record), parameters=deepcopy(parameters),
                   layout_material_frame_preserved=True,
                   settled_layout_requalified=False, formal_qualification=False)
    finally:
        common.generate_assets = generate
        variation_resources.read_json = read


def template_candidate(task, parameters):
    from topogym.assets.variation_resources import read_json
    from topogym.assets.geometry.horseshoe_ring import HorseshoeAssembly
    if task.task_id != "horseshoe_ring" or not task.template_resource:
        raise UnsupportedCapability("Requires a frozen Horseshoe variation")
    if not isinstance(parameters, dict) or set(parameters) - ALLOWED.keys():
        raise ValueError("Horseshoe parameters support target_ring and horseshoe sections")
    original = read_json(task.template_resource)
    record = deepcopy(original)
    for section, patch in parameters.items():
        if not isinstance(patch, dict) or set(patch) - ALLOWED[section]:
            raise ValueError(f"Unsupported {section} geometry parameter")
        for name, value in patch.items():
            values = np.asarray(value, dtype=float)
            shape = (2,) if name == "centerline_radii" else ()
            if values.shape != shape or not np.isfinite(values).all() or (values <= 0).any():
                raise ValueError(f"Invalid positive finite dimension: {section}.{name}")
        record[section].update(deepcopy(patch))
    HorseshoeAssembly(record, scale=float(task.config["scale"]))
    return original, record


def preview(task, parameters, output):
    from topogym.assets.geometry.horseshoe_ring import generate_assets
    from topogym.utils.io import sha256_file, write_json_atomic
    original, record = template_candidate(task, parameters)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    assembly, report = generate_assets(output, template=record, scale=float(task.config["scale"]))
    sections = dict(units="m", ring_centerline_radii_m=assembly.loops["target_ring"].radii.tolist(),
                    ring_wire_radius_m=float(assembly.loops["target_ring"].wire_radius),
                    shoe_width_m=record["horseshoe"]["band_width"]*assembly.unit,
                    shoe_thickness_m=record["horseshoe"]["thickness"]*assembly.unit)
    write_json_atomic(output / "sections.json", sections)
    # Match the common preview comparison contract, retaining the exact native
    # conservative bound under its original name as well.
    geometry = dict(report, minimum_initial_surface_clearance_m=report["minimum_clearance_lower_bound_m"],
                    clearance_measure="conservative native template bound, not a measured surface distance")
    manifest = dict(candidate_id=output.name, source_resource=task.template_resource,
                    base_sha256=digest(original), candidate_sha256=digest(record), parameters=parameters,
                    geometry=geometry, bodies=report["bodies"], sections=sections,
                    requires_rebuild=True, settled_layout_requalified=False,
                    physical_execution_verified=False, formal_qualification=False,
                    assets={str(p.relative_to(output)): sha256_file(p)
                            for p in sorted(output.rglob("*")) if p.is_file()})
    manifest["normal_passage"] = normal_passage_guard(task, parameters)
    write_json_atomic(output / "manifest.json", manifest)
    return dict(manifest, output=str(output))


def normal_passage_guard(task, parameters):
    """Sufficient obstruction proof for a face-on, straight normal passage.

    The shoe's XY projection is invariant under translation and in-plane
    rotation. Two projected material points farther apart than ANY chord of
    the aperture cannot both fit inside it. Use the ring centerline's enclosing
    disk as a deliberately loose aperture bound, ignoring wire thickness.
    A failed sufficient test is inconclusive; it does not establish passage.
    Tilted maneuvers and chain-constrained motion need independent planning.
    """
    from scipy.spatial import ConvexHull, distance
    from topogym.assets.geometry.horseshoe_ring import HorseshoeAssembly
    original, record = template_candidate(task, parameters)
    assembly = HorseshoeAssembly(record, scale=float(task.config["scale"]))
    ring = assembly.loops["target_ring"]
    bound = 2 * float(max(ring.radii))
    shoes = {}
    for body in assembly.bodies:
        if not body.name.startswith("horseshoe_"):
            continue
        points = body.visual.vertices[:, :2]
        hull = points[ConvexHull(points).vertices]
        distances = distance.cdist(hull, hull)
        i, j = np.unravel_index(distances.argmax(), distances.shape)
        chord = float(distances[i, j])
        shoes[body.name] = dict(projected_material_chord_m=chord,
            witness_points_authored_xy_m=hull[[i, j]].tolist(),
            obstruction_margin_lower_bound_m=chord-bound,
            obstruction_proven=chord > bound + 1e-9)
    return dict(status="blocked_proven" if all(s["obstruction_proven"] for s in shoes.values()) else "inconclusive",
        scope="shoe plane parallel to ring plane; any in-plane rotation/translation; straight translation along normal",
        method="projected material chord exceeds enclosing disk of ring centerline",
        aperture_diameter_upper_bound_m=bound,
        nominal_major_inner_diameter_m=2 * float(max(ring.radii)-ring.wire_radius),
        shoes=shoes, source_resource=task.template_resource,
        base_sha256=digest(original), candidate_sha256=digest(record),
        tilted_passage_checked=False, physical_execution_verified=False)


def rebase_poses(task, parameters, poses):
    """Preserve the authored material frame when a candidate moves its COM.

    Stored settled/recorded positions are body COMs. Reusing those numbers for
    a differently weighted shoe would translate its eyes and band inadvertently.
    This returns a detached pose hypothesis, not a new physical observation.
    """
    from topogym.assets.geometry.horseshoe_ring import HorseshoeAssembly
    from ..geometry import pose
    from topogym.planning.rigid_reference.geometry import pose_dict
    original, record = template_candidate(task, parameters)
    before = HorseshoeAssembly(original, scale=float(task.config["scale"]))
    after = HorseshoeAssembly(record, scale=float(task.config["scale"]))
    origins = {b.name: b.visual.center_mass for b in before.bodies}
    result, shifts = {}, {}
    for body in after.bodies:
        p, r = pose({k: poses[body.name][k] for k in ("position_m", "quaternion_wxyz")})
        shift = body.visual.center_mass - origins[body.name]
        result[body.name] = pose_dict((p + r.apply(shift), r))
        shifts[body.name] = shift.tolist()
    return dict(poses=result, com_shift_local_m=shifts,
                scope="detached hypothesis with unchanged authored material frames",
                physical_execution_verified=False)


def plot_geometry_comparison(task, parameters, poses, output):
    """Exact mesh engineering figure, explicitly not a simulator RGB frame."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from topogym.assets.geometry.horseshoe_ring import HorseshoeAssembly
    from topogym.planning.rigid_reference.feedback import body_pose
    from topogym.utils.io import write_json_atomic
    original, record = template_candidate(task, parameters)
    rebased = rebase_poses(task, parameters, poses)
    assemblies = [HorseshoeAssembly(t, scale=float(task.config["scale"])) for t in (original, record)]
    point_sets = []
    for assembly, state in zip(assemblies, (poses, rebased["poses"])):
        points = {}
        for body in assembly.bodies:
            p, r = body_pose(state[body.name])
            points[body.name] = 1000 * (p + r.apply(body.visual.vertices-body.visual.center_mass))
        point_sets.append(points)
    all_points = np.vstack([points for part in point_sets for points in part.values()])
    center = (all_points.min(axis=0)+all_points.max(axis=0))/2
    width = max(np.ptp(all_points, axis=0)) * .55
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    views = {}
    radii = [a.loops["target_ring"].radii*1000 for a in assemblies]
    dimensions = (f"Ring semi-axes: {radii[0][0]:.2f} / {radii[0][1]:.2f} mm"
                  f" -> {radii[1][0]:.2f} / {radii[1][1]:.2f} mm. "
                  f"Candidate wire diameter: {assemblies[1].loops['target_ring'].wire_radius*2000:.2f} mm.")
    for name, elevation, azimuth in (("front", 20, -65), ("side", 25, 30)):
        fig = plt.figure(figsize=(13, 6), dpi=160, facecolor="white")
        for index, (assembly, points) in enumerate(zip(assemblies, point_sets)):
            ax = fig.add_subplot(1, 2, index+1, projection="3d", computed_zorder=True)
            for body in assembly.bodies:
                vertices = points[body.name]-center
                faces = vertices[body.visual.faces]
                color = "#c18b35" if body.name == "target_ring" else "#a9b1b8"
                ax.add_collection3d(Poly3DCollection(faces, facecolors=color, linewidths=0,
                    shade=True, lightsource=LightSource(azdeg=315, altdeg=40)))
            ax.set(xlim=(-width,width), ylim=(-width,width), zlim=(-width,width))
            ax.set_box_aspect((1,1,1)); ax.set_proj_type("ortho"); ax.view_init(elevation, azimuth)
            ax.set_axis_off()
            ax.set_title("Original" if index == 0 else "Candidate", fontsize=15)
        fig.suptitle("Frozen mesh comparison | same scale, material frames and camera | NOT a physics frame", fontsize=11)
        fig.text(.5,.04,dimensions,ha="center",fontsize=11)
        fig.subplots_adjust(left=0,right=1,bottom=.08,top=.87,wspace=-.10)
        path=output/(name+".png");fig.savefig(path,facecolor="white");plt.close(fig)
        views[name]=str(path)
    report=dict(scope="engineering projection of exact generated visual meshes; not Nyx or a physics screenshot",
                parameters=parameters, body_pose_rebase=rebased, source_resource=task.template_resource,
                base_sha256=digest(original), candidate_sha256=digest(record), frames=views,
                physics_steps_advanced=0, formal_qualification=False)
    write_json_atomic(output / "figure.json", report)
    return report


def render_preview(config, parameters, output, *, observation=None,
                   cameras=("cam_high", "cam_low"), camera_poses=None):
    """Nyx screenshots in a disposable scene; never advances a physical policy.

    Optional recorded poses are used only as a modeling reference. The rendered
    candidate is not a recorded physical state and cannot inherit its success.
    Caller must use an isolated development process with a resource watchdog.
    """
    from topogym.simulator import Env, SimulatorConfig
    from topogym.utils.arrays import to_numpy
    from topogym.utils.io import write_json_atomic, to_jsonable
    from ..candidates import build_candidate
    from ..rendering import DevelopmentSensors, capture
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    values = dict(config, task_id="horseshoe_ring", enable_rgb=True,
                  work_dir=str(output / "scene"), reset_physics_steps=0)
    candidate = dict(geometry=dict(parameters=parameters))
    with Env(SimulatorConfig(**values), sensor_factory=DevelopmentSensors) as env:
        with build_candidate(env, candidate) as declaration_report:
            env.reset(seed=values.get("seed") or 0)
        if observation is not None:
            rebased = rebase_poses(env._task, parameters, observation["privileged"]["world"]["bodies"])
            for name in env._task.placement_vertices:
                body = rebased["poses"][name]
                env._world.entities[name].set_pos(body["position_m"], zero_velocity=True)
                env._world.entities[name].set_quat(body["quaternion_wxyz"], zero_velocity=True)
            q = to_numpy(env._robot.entity.get_qpos()).reshape(-1).copy()
            for side, state in observation["robot"].items():
                indices = env._robot._q_indices[side]
                q[indices[:6]] = state["joint_position_rad"]
                q[indices[6:]] = state["finger_position_m"]
            env._robot.entity.set_qpos(q, zero_velocity=True)
            env._world.scene.visualizer.update_visual_states(force_render=True)
            env._sensors.invalidate()
        for name, camera_pose in (camera_poses or {}).items():
            if name not in cameras or set(camera_pose) != {"pos", "lookat", "up"}:
                raise ValueError("Preview camera needs pos/lookat/up and must be selected")
            camera = env._world.cameras[name]
            if getattr(camera, "_attached_link", None) is not None:
                raise ValueError("Only free preview cameras can be reframed")
            values = np.asarray(list(camera_pose.values()), dtype=float)
            if values.shape != (3, 3) or not np.isfinite(values).all():
                raise ValueError("Preview camera coordinates must be finite 3-vectors")
            camera.set_pose(**camera_pose)
            camera.invalidate_frame()
        frames = {camera: capture(env, output / "frames", camera, near="target_ring")
                  for camera in cameras}
        report = dict(scope="modeling preview; recorded poses are hypothetical for modified geometry",
                      physics_steps_advanced=0, formal_qualification=False,
                      robot_execution_verified=False, source_state=observation.get("state") if observation else None,
                      preview_episode_id=env._episode_id, declaration=declaration_report,
                      pose_rebase=rebased if observation is not None else None,
                      config=to_jsonable(env.config), frames=frames)
        write_json_atomic(output / "preview.json", report)
    return report
