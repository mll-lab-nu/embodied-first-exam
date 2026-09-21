"""Standard tabletop with one unpinned suspended PBD blanket."""
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np

from .geometry import BlanketLayout, generate, generate_flat_binding, write_obj


@dataclass
class BlanketScene:
    tabletop: Any
    cloth: Any
    layout: BlanketLayout
    birth_report: dict
    binding_report: dict
    supports: np.ndarray
    weights: np.ndarray
    material_uv: np.ndarray
    faces: np.ndarray
    edges: np.ndarray
    rest_lengths: np.ndarray
    visual_edges: np.ndarray
    visual_rest_lengths: np.ndarray
    table_bounds: np.ndarray
    table_friction: Any

    @property
    def scene(self):
        return self.tabletop.scene

    def measure(self):
        from topogym.supervision.pbd_probe import probe_particles, probe_velocities
        from .diagnostics import measure
        positions = probe_particles(self.cloth)
        visual = np.einsum("nk,nkj->nj", self.weights, positions[self.supports])
        return measure(positions, probe_velocities(self.cloth), self.faces, self.edges, self.rest_lengths,
                       table_z=self.tabletop.frames.table_surface_origin[2], table_bounds=self.table_bounds,
                       material_area=self.layout.length_m*self.layout.width_m, visual_positions=visual,
                       visual_edges=self.visual_edges, visual_rest_lengths=self.visual_rest_lengths)


class BlanketSceneBuilder:
    def __init__(self, env_cfg, task_cfg, robot_cfg):
        self.env_cfg, self.task_cfg, self.robot_cfg = env_cfg, task_cfg, robot_cfg

    def build(self, *, asset_dir, show_viewer=False, include_robot=True):
        import genesis as gs
        from omegaconf import OmegaConf
        from topogym.world import StandardTabletopSceneBuilder, materials, textures
        from topogym.world.rope import TabletopParticleFriction
        from .diagnostics import binding_audit

        if int(self.env_cfg.sim.n_envs) != 0:
            raise ValueError("Blanket birth audit currently requires an unbatched scene")
        cfg = self.task_cfg
        if cfg.variant not in ("suspended_irregular_folds_v1", "suspended_fold_and_roll_v2",
                               "staged_corner_cross_twist_v3", "staged_gathered_twist_v4"):
            raise ValueError("Unknown blanket initialization variant")
        layout = BlanketLayout(**OmegaConf.to_container(cfg.geometry, resolve=True))
        if (cfg.variant == "suspended_fold_and_roll_v2") != (layout.roll_fold_count > 0):
            raise ValueError("Fold-and-roll variant must have roll hinges; v1 must not")
        factory = generate_flat_binding if cfg.variant in ('staged_corner_cross_twist_v3', 'staged_gathered_twist_v4') else generate
        vertices, faces, uv, panels, report = factory(layout)
        builder = StandardTabletopSceneBuilder(self.env_cfg, self.robot_cfg,
            pbd_options=gs.options.PBDOptions(particle_size=layout.particle_size_m,
                                              max_stretch_solver_iterations=int(cfg.stretch_iterations)))
        base = builder.create(show_viewer=show_viewer, include_robot=include_robot,
                              robot_material=gs.materials.Rigid(needs_coup=False,
                                  gravity_compensation=float(cfg.get('robot_gravity_compensation', 0.))))
        if str(self.env_cfg.renderer.type) == "rasterizer":
            # The closed lab ceiling blocks exterior directional lights. Reuse
            # the preset's interior point lights for readable fold shading.
            base.scene.vis_options.lights.clear()
            for light in self.env_cfg.renderer.lights:
                if light.type == "point":
                    base.scene.vis_options.lights.append(gs.options.vis.PointLight(
                        pos=tuple(light.pos), color=tuple(light.color), intensity=float(light.intensity)))
        table_z = base.frames.table_surface_origin[2]
        vertices += np.array([*cfg.origin_xy_m, table_z])
        bounds = np.array([np.asarray(self.env_cfg.world.table.pos)[:2]-np.asarray(self.env_cfg.world.table.size)[:2]/2,
                           np.asarray(self.env_cfg.world.table.pos)[:2]+np.asarray(self.env_cfg.world.table.size)[:2]/2])
        if np.any(vertices[:, :2] < bounds[0]+layout.particle_size_m) or np.any(vertices[:, :2] > bounds[1]-layout.particle_size_m):
            raise ValueError("Suspended blanket must fit over the table with particle clearance")
        path = Path(asset_dir).resolve()/"blanket_birth.obj"
        write_obj(path, vertices, faces, uv, layout)
        np.savez_compressed(path.with_suffix(".npz"), vertices=vertices, faces=faces, material_uv=uv, panel_quads=panels)
        texture = textures.fabric_weave(color=list(cfg.color), size_m=(layout.length_m, layout.width_m),
                                       pattern="grid", accent_color=[.76, .84, .87], stripe_pitch_m=.06,
                                       seed=layout.seed, thread_pitch_m=.002,
                                       preview_path=path.parent/"fabric.png")
        cloth = base.manifest.add("blanket", base.scene.add_entity(
            gs.morphs.Mesh(file=str(path), decimate=False, convexify=False, fixed=False, file_meshes_are_zup=True),
            material=gs.materials.PBD.Cloth(**OmegaConf.to_container(cfg.material, resolve=True)),
            surface=materials.plastic("deformable", cfg.color, vis_mode=str(cfg.vis_mode), texture=texture), name="blanket"))
        builder.finalize(base)
        binding, supports, weights, puv = binding_audit(cloth, vertices, uv, panels, layout.particle_size_m)
        (path.parent/"binding_report.json").write_text(json.dumps(binding, indent=2)+"\n")
        if not binding["passed"]:
            raise ValueError(f"Birth binding rejected: {binding}")
        gap = report["minimum_nonadjacent_panel_gap_m"]
        report["minimum_gap_over_measured_particle_spacing"] = gap/binding["measured_median_spacing_m"] if gap is not None else None
        friction = TabletopParticleFriction(base.scene, [cloth], surface_z=table_z,
            contact_band=float(cfg.table_friction.contact_band_m), static_mu=float(cfg.table_friction.static_mu),
            kinetic_mu=float(cfg.table_friction.kinetic_mu), dt=float(self.env_cfg.sim.dt),
            gravity=float(self.env_cfg.sim.gravity[2])).install()
        # These arrays are the backend's remeshed connectivity, not control-grid indices.
        visual_edges = np.asarray(cloth._vmesh.get_unique_edges())
        visual_lengths = np.linalg.norm(cloth._vverts[visual_edges[:, 1]]-cloth._vverts[visual_edges[:, 0]], axis=1)
        return BlanketScene(base, cloth, layout, report, binding, supports, weights, puv,
                            np.asarray(cloth._mesh.faces), np.asarray(cloth._edges),
                            np.asarray(cloth._edges_len_rest), visual_edges, visual_lengths, bounds, friction)
