"""Detached Orbits modeling candidates; never changes installed task assets.

A candidate changes the fixture layout (ring radius, post spacing, base size, the layout's
nominal handle position) and, for the compact profile, the explicit handle placement and cord
length that the Task's compact cord profile sets. Geometry values are template values (before
``linear_scale``), as in the Task's ``geometry`` mapping; ``cord_profile`` values are metres after
scaling, as in ``topogym.tasks.orbits.common.CORD_PROFILES``.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from ..contracts import UnsupportedCapability, digest


GEOMETRY = {"ring_radius_m", "post_spacing_m", "ring_step_m", "lowest_ring_z_m",
            "base_length_m", "base_width_m", "handle_x_m"}
PROFILE = {"handle_x_m", "cord_length_m"}


def compact_profile(task):
    """The task's own compact profile values: (handle_x_m, cord_length_m for its ring count)."""
    from topogym.assets.geometry.orbits import OrbitsLayout
    from topogym.tasks.orbits.common import CORD_PROFILES, profile_value
    if task.config["cord_profile"] not in CORD_PROFILES:
        raise UnsupportedCapability("Orbits candidates are defined for the compact cord profiles")
    profile = CORD_PROFILES[task.config["cord_profile"]]
    ring_count = OrbitsLayout(**task.config["geometry"]).ring_count
    return dict(handle_x_m=profile_value(profile, "handle_x_m", ring_count),
                cord_length_m=profile_value(profile, "cord_length_m", ring_count))


def checked(task, parameters):
    """Validated (geometry overrides, profile values, base layout, candidate layout)."""
    from topogym.assets.geometry.orbits import OrbitsLayout
    from topogym.assets.geometry.orbits_initial import natural_working_state
    if task.task_id != "orbits":
        raise UnsupportedCapability("This adapter only builds Orbits candidates")
    if set(parameters)-{"geometry", "cord_profile"}:
        raise ValueError("Orbits candidate takes 'geometry' and 'cord_profile' mappings")
    geometry, profile = dict(parameters.get("geometry", {})), dict(parameters.get("cord_profile", {}))
    if set(geometry)-GEOMETRY or set(profile)-PROFILE:
        raise ValueError(f"Orbits candidate supports geometry {sorted(GEOMETRY)}, cord_profile {sorted(PROFILE)}")
    for value in [*geometry.values(), *profile.values()]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
            raise ValueError("Orbits candidate values must be positive finite numbers")
    scale = task.config["linear_scale"]
    base = OrbitsLayout(**task.config["geometry"]).scaled(scale)
    layout = OrbitsLayout(**dict(task.config["geometry"], **geometry)).scaled(scale)   # validates
    used = dict(compact_profile(task), **profile)
    natural_working_state(layout, handle_x_m=used["handle_x_m"], cord_length_m=used["cord_length_m"],
                          spacing=.002)                                                  # checks the cord
    return geometry, used, base, replace(layout, handle_x_m=used["handle_x_m"])


def summary(layout):
    t = layout.ring_tube_radius_m
    return dict(ring_count=layout.ring_count, ring_radius_m=layout.ring_radius_m,
                aperture_inner_diameter_m=2*(layout.ring_radius_m-t), post_spacing_m=layout.post_spacing_m,
                base_length_m=layout.base_length_m, base_width_m=layout.base_width_m,
                handle_x_m=layout.handle_x_m, post_x_m=np.asarray(layout.post_x).tolist(),
                ring_x_m=np.asarray(layout.ring_x).tolist(), ring_z_m=np.asarray(layout.ring_z).tolist(),
                ball_z_m=layout.ball_z, ball_radius_m=layout.ball_radius_m)


@contextmanager
def declaration(task, parameters):
    """Override the layout and compact cord profile only while this owner declares a scene.

    The candidate shape needs its own settling and checks; it inherits no qualification.
    """
    from topogym.tasks.orbits import common
    from topogym.assets.geometry import orbits_initial
    geometry, used, base, layout = checked(task, parameters)
    original_geometry = deepcopy(task.config["geometry"])
    natural, generate, meshes = orbits_initial.natural_working_state, common.generate_assets, common.make_meshes

    def candidate_natural(layout_, **kwargs):
        if "cord_length_m" in kwargs:            # the compact profile call
            kwargs.update(handle_x_m=used["handle_x_m"], cord_length_m=used["cord_length_m"])
        return natural(layout_, **kwargs)

    def placed(layout_):
        return replace(layout_, handle_x_m=used["handle_x_m"])

    task.config["geometry"] = dict(original_geometry, **geometry)
    orbits_initial.natural_working_state = candidate_natural
    common.generate_assets = lambda asset_dir, layout_, **kw: generate(asset_dir, placed(layout_), **kw)
    common.make_meshes = lambda layout_, **kw: meshes(placed(layout_), **kw)
    try:
        yield dict(parameters=deepcopy(parameters), cord_profile_used=used,
                   base_sha256=digest(asdict(base)), candidate_sha256=digest(asdict(layout)),
                   base_layout=summary(replace(base, handle_x_m=compact_profile(task)["handle_x_m"])),
                   candidate_layout=summary(layout), settled_layout_requalified=False,
                   formal_qualification=False)
    finally:
        task.config["geometry"] = original_geometry
        orbits_initial.natural_working_state = natural
        common.generate_assets, common.make_meshes = generate, meshes


def render_preview(config, parameters, output, *, cameras=("cam_high", "cam_low"), camera_poses=None):
    """Nyx frames of a disposable candidate scene at its birth state (zero physics steps).

    Without ``parameters`` the unchanged task is rendered with the same cameras, for comparison.
    Run in an isolated development process with a resource watchdog, never inside a policy.
    """
    from topogym.simulator import Env, SimulatorConfig
    from topogym.utils.io import write_json_atomic, to_jsonable
    from ..candidates import build_candidate
    from ..rendering import DevelopmentSensors, capture
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    values = dict(config, task_id="orbits", enable_rgb=True, work_dir=str(output / "scene"), reset_physics_steps=0)
    candidate = dict(geometry=dict(parameters=parameters)) if parameters else {}
    with Env(SimulatorConfig(**values), sensor_factory=DevelopmentSensors) as env:
        with build_candidate(env, candidate) as declaration_report:
            env.reset(seed=values.get("seed") or 0)
        for name, pose in (camera_poses or {}).items():
            if name not in cameras or set(pose) != {"pos", "lookat", "up"}:
                raise ValueError("Preview camera needs pos/lookat/up and must be selected")
            camera = env._world.cameras[name]
            if getattr(camera, "_attached_link", None) is not None:
                raise ValueError("Only free preview cameras can be reframed")
            camera.set_pose(**pose)
            camera.invalidate_frame()
        frames = {camera: capture(env, output / "frames", camera) for camera in cameras}
        report = dict(scope="modeling preview of the birth state; no physics advanced",
                      physics_steps_advanced=0, formal_qualification=False, robot_execution_verified=False,
                      preview_episode_id=env._episode_id, declaration=declaration_report,
                      layout=summary(env._task.layout), config=to_jsonable(env.config), frames=frames)
        write_json_atomic(output / "preview.json", report)
    return report


def plot_layout_comparison(task, parameters, output):
    """Same-scale top and side engineering views of the base and candidate layouts (not Nyx)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _, used, base, layout = checked(task, parameters)
    base = replace(base, handle_x_m=compact_profile(task)["handle_x_m"])
    fig, axes = plt.subplots(2, 1, figsize=(11, 8.5))
    th = np.linspace(0, 2*np.pi, 200)
    for lay, color, label in ((base, "0.55", "current"), (layout, "tab:red", "candidate")):
        t = lay.ring_tube_radius_m
        top, side = axes
        top.add_patch(plt.Rectangle((-lay.base_length_m/2, -lay.base_width_m/2), lay.base_length_m,
                                    lay.base_width_m, fill=False, ec=color, ls="--", lw=1))
        for k, (cx, cz) in enumerate(zip(lay.ring_x, lay.ring_z)):
            for r in (lay.ring_radius_m-t, lay.ring_radius_m+t):
                top.plot(cx+r*np.cos(th), r*np.sin(th), color=color, lw=1.2)
            side.plot([cx-lay.ring_radius_m, cx+lay.ring_radius_m], [cz, cz], color=color, lw=3,
                      solid_capstyle="round")
        for k, x in enumerate(lay.post_x):
            z = lay.ball_z if k == 0 else lay.ring_z[k-1]
            top.add_patch(plt.Circle((x, 0), lay.post_radius_m, color=color))
            side.plot([x, x], [lay.base_height_m, z], color=color, lw=2)
        top.add_patch(plt.Circle((lay.post_x[0], 0), lay.ball_radius_m, fill=False, ec=color, lw=1))
        side.add_patch(plt.Circle((lay.post_x[0], lay.ball_z), lay.ball_radius_m, fill=False, ec=color, lw=1.5))
        side.add_patch(plt.Rectangle((-lay.base_length_m/2, 0), lay.base_length_m, lay.base_height_m,
                                     fill=False, ec=color, ls="--", lw=1))
        top.plot([lay.handle_x_m], [0], marker="s", color=color, ms=8, label=f"{label} handle")
        side.plot([], [], color=color, lw=2,
                  label=f"{label}: aperture {200*(lay.ring_radius_m-t):.1f} cm, post spacing {100*lay.post_spacing_m:.1f} cm")
    axes[0].set_title("Top view (task frame, m)")
    axes[1].set_title("Side view (x-z, m)")
    for ax in axes:
        ax.set_aspect("equal")
        ax.grid(alpha=.3)
        ax.legend(loc="upper right", fontsize=8)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output, dpi=140)
    plt.close(fig)
    return dict(path=str(output), base=summary(base), candidate=summary(layout), cord_profile_used=used,
                scope="engineering drawing from layout parameters; not a Nyx frame or physical state")
