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
    original, record = template_candidate(task, parameters)
    generate = common.generate_assets

    def candidate_assets(output, *, template=None, scale=2.):
        if template != original:
            raise ValueError("Geometry candidate source template changed")
        return generate(output, template=record, scale=scale)

    common.generate_assets = candidate_assets
    try:
        yield dict(source_resource=task.template_resource, base_sha256=digest(original),
                   candidate_sha256=digest(record), parameters=deepcopy(parameters),
                   settled_layout_requalified=False, formal_qualification=False)
    finally:
        common.generate_assets = generate


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
    write_json_atomic(output / "manifest.json", manifest)
    return dict(manifest, output=str(output))


def render_preview(config, parameters, output, *, observation=None,
                   cameras=("cam_high", "cam_low")):
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
            for name in env._task.placement_vertices:
                body = observation["privileged"]["world"]["bodies"][name]
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
        frames = {camera: capture(env, output / "frames", camera, near="target_ring")
                  for camera in cameras}
        report = dict(scope="modeling preview; recorded poses are hypothetical for modified geometry",
                      physics_steps_advanced=0, formal_qualification=False,
                      robot_execution_verified=False, source_state=observation.get("state") if observation else None,
                      preview_episode_id=env._episode_id, declaration=declaration_report,
                      config=to_jsonable(env.config), frames=frames)
        write_json_atomic(output / "preview.json", report)
    return report
