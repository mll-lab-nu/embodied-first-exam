"""Shared ALOHA lab, fixed open rings, and an unpinned FEM rope."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .geometry import ThreadingLayout, generate_assets


@dataclass
class ThreadingScene:
    tabletop: Any
    layout: ThreadingLayout
    rope: Any
    backend: Any
    fixtures: dict
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

    @property
    def centerline(self):
        return self.layout.centerline()


class ThreadingSceneBuilder:
    def __init__(self, env_cfg, task_cfg, robot_cfg):
        self.env_cfg, self.task_cfg, self.robot_cfg = env_cfg, task_cfg, robot_cfg

    def build(self, *, asset_dir, show_viewer=False, include_robot=True, pre_build=None):
        import genesis as gs
        from omegaconf import OmegaConf
        from topogym.world import StandardTabletopSceneBuilder
        from topogym.world.rope import check_self_contact_clearance, tensor_to_numpy, tube_morph
        from topogym.world.rope_backends import rope_backend
        from topogym.world.genesis_ipc_vertex_constraints import _inverted_tets, _straighten_positions

        cfg = self.task_cfg
        if cfg.variant != "wang_reference_v1" or cfg.rope.model != "fem_ipc_tube" or cfg.rope.fem.rest_shape != "straight":
            raise ValueError("The threading baseline requires the Wang layout and straight-rest FEM+IPC rope")
        if not np.isclose(cfg.rope.radius, .004):
            raise ValueError("The reference rope radius is 4 mm")
        backend = rope_backend(cfg.rope)
        backend.pre_scene()
        options = backend.scene_options()
        if cfg.rope.fem.get("contact_eps_velocity") is not None:
            options["coupler_options"].contact_eps_velocity = float(cfg.rope.fem.contact_eps_velocity)
        builder = StandardTabletopSceneBuilder(self.env_cfg, self.robot_cfg,
            scene_options=options, debug_label="threading_build",
            rigid_options=gs.options.RigidOptions(**OmegaConf.to_container(cfg.robot_rigid_collision, resolve=True))
                if "robot_rigid_collision" in cfg else None)
        base = builder.create(show_viewer=show_viewer, include_robot=include_robot,
            robot_morph_options=dict(decimate=False),
            robot_material=gs.materials.Rigid(coup_type=str(cfg.get("robot_coupling", "two_way_soft_constraint")),
                                              gravity_compensation=1.),
            table_material=backend.static_rigid_material(), static_material=backend.static_rigid_material(),
            decoration_material=backend.decoration_rigid_material())
        table_z = base.frames.table_surface_origin[2]
        layout = ThreadingLayout(translation_m=(*cfg.origin_xy_m, table_z+.0009),
                                 **OmegaConf.to_container(cfg.geometry, resolve=True))
        asset_dir = Path(asset_dir).resolve()
        report = generate_assets(asset_dir, layout)
        centerline = layout.centerline()
        half_size = np.asarray(self.env_cfg.world.table.size)/2
        table_center = np.asarray(self.env_cfg.world.table.pos)
        # Include fixtures as well as rope in finite-table bounds checks.
        xy_low, xy_high = centerline[:, :2].min(0)-layout.radius, centerline[:, :2].max(0)+layout.radius
        for ring in layout.rings():
            center = np.asarray(ring["center_m"])
            extent = ring["radius_m"]*np.sqrt(1-np.asarray(ring["normal"])**2)+ring["tube_radius_m"]
            base_center = layout.transform(ring["base"]["position"])
            xy_low = np.minimum(xy_low, np.minimum((center-extent)[:2], (base_center-ring["base"]["size"])[:2]))
            xy_high = np.maximum(xy_high, np.maximum((center+extent)[:2], (base_center+ring["base"]["size"])[:2]))
        if np.any(xy_low < (table_center-half_size)[:2]) or np.any(xy_high > (table_center+half_size)[:2]):
            raise ValueError("Threading task must fit within the finite tabletop")
        fixtures = {}
        riser_height = float(self.robot_cfg.robot.get("base_riser_height_m", 0.))
        if include_robot and riser_height > 0:
            mount = np.asarray(self.env_cfg.robot_mount.pos)
            for side, sign in (("left", -1.), ("right", 1.)):
                name = f"{side}_base_riser"
                base.manifest.add(name, base.scene.add_entity(gs.morphs.Box(
                    pos=(mount[0]+sign*.519, mount[1]-.019, table_z+riser_height/2),
                    size=(.10, .12, riser_height), fixed=True), material=backend.static_rigid_material(),
                    surface=gs.surfaces.Rough(color=(.32, .34, .35)), name=name))
        for ring in layout.rings():
            for suffix, color in (("", ring["rgba"]), ("_stand", ring["stand"]["rgba"]), ("_base", ring["base"]["rgba"])):
                name = ring["name"]+suffix
                # Never convexify a complete ring: that would seal the aperture.
                fixtures[name] = base.manifest.add(name, base.scene.add_entity(gs.morphs.Mesh(
                    file=str(asset_dir/f"{name}.obj"), fixed=True, convexify=False, decimate=False,
                    file_meshes_are_zup=True), material=backend.static_rigid_material(),
                    surface=gs.surfaces.Rough(color=tuple(color[:3])), name=name))
        check_self_contact_clearance(radius=layout.radius, radial_segments=layout.radial_segments,
            ring_spacing=float(np.linalg.norm(np.diff(centerline, axis=0), axis=1).min()),
            contact_d_hat=float(cfg.rope.fem.contact_d_hat))
        rope = base.manifest.add("threading_rope", base.scene.add_entity(
            tube_morph(asset_dir/"rope.obj", cfg.rope), material=backend.material(),
            surface=gs.surfaces.Rough(color=(.95, .48, .15)), name="threading_rope"))
        spawn = np.asarray(tensor_to_numpy(rope.init_positions), dtype=float)
        straight = _straighten_positions(spawn, centerline)
        inverted = _inverted_tets(straight, spawn, rope.elems)
        if len(inverted):
            raise ValueError(f"Straight material reference inverts {len(inverted)} tetrahedra")
        backend.declare_rest_straight(rope, centerline)
        if pre_build is not None:
            pre_build(base, rope, centerline, backend)
        coupler = base.scene.sim.coupler
        original_build = coupler.build
        if include_robot:
            def build_at_neutral():
                robot = base.manifest.get("robot")
                initial_q = robot.init_qpos.copy()
                names = list(self.robot_cfg.robot.arm_joint_names)+list(self.robot_cfg.robot.finger_joint_names)
                for side in ("left", "right"):
                    for name, value in zip(names, self.robot_cfg.home[side]):
                        initial_q[robot.get_joint(f"{side}/{name}").qs_idx_local[0]] = value
                base.scene.sim.rigid_solver.set_qpos(initial_q, qs_idx=slice(robot.q_start, robot.q_end))
                if cfg.get("robot_coupling") == "external_articulation":
                    from topogym.tasks.knot_untying.ipc_compat import matching_revolute_axes
                    with matching_revolute_axes():
                        original_build()
                    coupler._articulation_data_by_entity[robot].ref_dof_prev[:] = initial_q
                else:
                    original_build()
            coupler.build = build_at_neutral
        try:
            builder.finalize(base)
        finally:
            coupler.build = original_build
        volume = dict(vertices=len(spawn), tetrahedra=len(rope.elems),
                      inverted_straight_reference_tetrahedra=0, rest_shape="straight",
                      pinned_vertices=0, endpoint_constraints=0)
        return ThreadingScene(base, layout, rope, backend, fixtures, report, volume)
