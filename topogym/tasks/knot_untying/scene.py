"""Shared lab and one unpinned FEM rope with an explicit straight reference."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .geometry import KnotLayout, generate_assets
from .families import template_variant


def scene_options(backend, rope_cfg):
    options = backend.scene_options()
    epsilon = rope_cfg.fem.get('contact_eps_velocity')
    if epsilon is not None:
        options['coupler_options'].contact_eps_velocity = float(epsilon)
    return options


@dataclass
class KnotScene:
    tabletop: Any
    layout: KnotLayout
    rope: Any
    backend: Any
    centerline: np.ndarray
    asset_report: dict
    volume_report: dict

    @property
    def scene(self):
        return self.tabletop.scene

    @property
    def cameras(self):
        return self.tabletop.cameras

    @property
    def manifest(self):
        return self.tabletop.manifest


class KnotSceneBuilder:
    def __init__(self, env_cfg, task_cfg, robot_cfg):
        self.env_cfg, self.task_cfg, self.robot_cfg = env_cfg, task_cfg, robot_cfg

    def build(self, *, asset_dir, show_viewer=False, include_robot=True, pre_build=None):
        import genesis as gs
        from omegaconf import OmegaConf
        from topogym.world import StandardTabletopSceneBuilder
        from topogym.world.rope import check_self_contact_clearance, tensor_to_numpy, tube_morph, write_obj
        from topogym.world.rope_backends import rope_backend
        from topogym.world.genesis_ipc_vertex_constraints import _inverted_tets, _straighten_positions

        cfg = self.task_cfg
        family = str(cfg.geometry.get('family', 'overhand_trefoil'))
        if (cfg.variant != template_variant(family, cfg.get('route_profile')) or cfg.rope.model != "fem_ipc_tube"
                or cfg.rope.fem.rest_shape != "straight"):
            raise ValueError("Registered open-knot template requires FEM+IPC and a straight reference")
        try:
            import uipc  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("Install the FEM backend with: uv pip install --python .venv-gs121-nyx/bin/python "
                               "-r requirements/uv-topogym-fem-ipc.txt") from exc
        layout, report = generate_assets(asset_dir, KnotLayout(**OmegaConf.to_container(cfg.geometry, resolve=True)))
        backend = rope_backend(cfg.rope)
        backend.pre_scene()
        builder = StandardTabletopSceneBuilder(self.env_cfg, self.robot_cfg,
            scene_options=scene_options(backend, cfg.rope), debug_label="knot_build",
            rigid_options=gs.options.RigidOptions(**OmegaConf.to_container(cfg.robot_rigid_collision, resolve=True))
                if 'robot_rigid_collision' in cfg else None)
        base = builder.create(show_viewer=show_viewer, include_robot=include_robot,
            robot_morph_options=OmegaConf.to_container(cfg.robot_collision, resolve=True)
                if 'robot_collision' in cfg else None,
            robot_material=gs.materials.Rigid(coup_type=str(cfg.get('robot_coupling', 'two_way_soft_constraint')),
                                              gravity_compensation=1.),
            table_material=backend.static_rigid_material(), static_material=backend.static_rigid_material(),
            decoration_material=backend.decoration_rigid_material())
        origin = np.array([*cfg.origin_xy_m, base.frames.table_surface_origin[2]])
        centerline = layout.centerline()
        yaw = np.radians(float(cfg.get('yaw_deg', 0.)))
        c, s = np.cos(yaw), np.sin(yaw)
        centerline[:, :2] = centerline[:, :2] @ np.array([[c, s], [-s, c]])
        centerline += origin
        table_min = np.asarray(self.env_cfg.world.table.pos)-np.asarray(self.env_cfg.world.table.size)/2
        table_max = np.asarray(self.env_cfg.world.table.pos)+np.asarray(self.env_cfg.world.table.size)/2
        if np.any(centerline[:, :2].min(axis=0)-layout.rope_radius_m < table_min[:2]) or np.any(
                centerline[:, :2].max(axis=0)+layout.rope_radius_m > table_max[:2]):
            raise ValueError("Rope must lie entirely over the table")
        check_self_contact_clearance(radius=layout.rope_radius_m, radial_segments=layout.radial_segments,
            ring_spacing=float(np.linalg.norm(np.diff(centerline, axis=0), axis=1).min()),
            contact_d_hat=float(cfg.rope.fem.contact_d_hat))
        # Store world mesh separately: local reference assets retain their frame.
        from topogym.world.rope import make_elastic_tube_mesh
        vertices, faces = make_elastic_tube_mesh(centerline, radius=layout.rope_radius_m,
                                               radial_segments=layout.radial_segments)
        path = Path(asset_dir).resolve()/"rope_world.obj"
        write_obj(path, vertices, faces)
        rope = base.manifest.add("knotted_rope", base.scene.add_entity(tube_morph(path, cfg.rope),
            material=backend.material(), surface=gs.surfaces.Rough(
                color=tuple(cfg.get('rope_color_rgb', (.86, .43, .12)))), name="knotted_rope"))
        # The shared legacy patch can fall back to spawn rest on invalid tets.
        # Reject BEFORE build so this task can never quietly accept that fallback.
        spawn = np.asarray(tensor_to_numpy(rope.init_positions), dtype=float)
        straight = _straighten_positions(spawn, centerline)
        inverted = _inverted_tets(straight, spawn, rope.elems)
        if len(inverted):
            raise ValueError(f"Straight reference would invert {len(inverted)} tetrahedra")
        volume_report = dict(vertices=len(spawn), tetrahedra=len(rope.elems),
                             inverted_straight_reference_tetrahedra=len(inverted), rest_shape="straight",
                             pinned_vertices=0, endpoint_constraints=0)
        backend.declare_rest_straight(rope, centerline)
        if pre_build is not None:
            pre_build(base, rope, centerline, backend)
        coupler = base.scene.sim.coupler
        original_build = coupler.build
        if include_robot and cfg.get('robot_coupling') == 'external_articulation':
            # Set the initial neutral configuration after the rigid solver is
            # built, before IPC constructs its articulation reference. Changing
            # joint.init_qpos would change the joint coordinate reference and
            # would not physically pose the imported model at these angles.
            def build_at_neutral():
                robot = base.manifest.get('robot')
                initial_q = robot.init_qpos.copy()
                names = list(self.robot_cfg.robot.arm_joint_names)+list(self.robot_cfg.robot.finger_joint_names)
                for side in ('left', 'right'):
                    for name, value in zip(names, self.robot_cfg.home[side]):
                        initial_q[robot.get_joint(f'{side}/{name}').qs_idx_local[0]] = value
                base.scene.sim.rigid_solver.set_qpos(initial_q, qs_idx=slice(robot.q_start, robot.q_end))
                from .ipc_compat import matching_revolute_axes
                with matching_revolute_axes():
                    original_build()
                # The stock external-articulation adapter initializes this
                # previous coordinate to zero. Match the declared initial pose
                # so the first step represents a delta from neutral.
                coupler._articulation_data_by_entity[robot].ref_dof_prev[:] = initial_q
            coupler.build = build_at_neutral
        try:
            builder.finalize(base)
        finally:
            coupler.build = original_build
        return KnotScene(base, layout, rope, backend, centerline, report, volume_report)
