"""Two straight strands: normal blocking, tangential slide, then full release."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .geometry import KnotLayout
from .probe_actions import smoothstep


class CrossedStrandActions:
    def __init__(self):
        self.grasps, self.origins, self.events, self.samples = [], None, [], []

    def declare(self, rope, centerline):
        from topogym.primitives.fem_attachment import FEMRopeAttachment
        for point in (centerline[4], centerline[-5]):
            self.grasps.append(FEMRopeAttachment(rope, point, radius=.008, strength=100.))

    def specification(self):
        return dict(kind='explicit_soft_target_fixture', strength=100., band_radius_m=.008,
                    motion=[dict(start_s=1., end_s=3., upper_z_m=-.006),
                            dict(start_s=3., end_s=5.5, upper_x_m=.03),
                            dict(start_s=5.5, end_s=8., upper_x_m=0.),
                            dict(start_s=8., end_s=10., upper_z_m=0.)],
                    release_s=10., post_release_s=5.,
                    acceptance=dict(minimum_normal_deflection_m=.002,
                                    minimum_tangential_travel_m=.025))

    def update(self, t):
        if self.origins is None:
            self.origins = [g.attach().copy() for g in self.grasps]
            self.events.append(dict(time_s=t, event='engage_four_endpoint_bands'))
        if t >= 10.:
            if any(g.active for g in self.grasps):
                for g in self.grasps:
                    g.release()
                self.events.append(dict(time_s=t, event='release_all_fixtures'))
            return
        z = -.006*smoothstep((t-1.)/2.)
        if t >= 8.:
            z *= 1.-smoothstep((t-8.)/2.)
        x = .03*smoothstep((t-3.)/2.5)
        if t >= 5.5:
            x = .03*(1.-smoothstep((t-5.5)/2.5))
        for i, (grasp, origin) in enumerate(zip(self.grasps, self.origins)):
            grasp.drive_to(origin+(np.array([x, 0., z]) if i >= 2 else 0.))

    def observe(self, t, monitor):
        lower, upper = [monitor.last_centers[a:b] for a, b in monitor.material_slices]
        middle = upper[len(upper)//2]
        lower_z = np.interp(middle[0], lower[:, 0], lower[:, 2])
        upper_end_z = np.mean([grasp.band_center()[2] for grasp in self.grasps[2:]])
        self.samples.append(dict(time_s=t, upper_middle=middle.tolist(),
                                 center_gap_m=float(middle[2]-lower_z),
                                 normal_deflection_m=float(middle[2]-upper_end_z)))

    def report(self):
        pressed = [s for s in self.samples if 3. <= s['time_s'] <= 8.]
        positions = np.array([s['upper_middle'] for s in pressed])
        travel = float(np.ptp(positions[:, 0])) if len(positions) else 0.
        blocked = max((s['normal_deflection_m'] for s in pressed), default=0.)
        gaps = [s['center_gap_m'] for s in pressed]
        checks = dict(normal_blocking=blocked >= .002,
                      tangential_sliding=travel >= .025,
                      released=not any(g.active for g in self.grasps),
                      post_release_observed=bool(self.samples and self.samples[-1]['time_s'] >= 15.-1e-8))
        return dict(kind='declared_translation_only_soft_grasp_fixture', events=self.events,
                    material_vertices=[g.indices.tolist() for g in self.grasps],
                    final_active_constraints=sum(g.active for g in self.grasps),
                    max_normal_deflection_m=blocked, tangential_travel_m=travel,
                    minimum_pressed_center_gap_m=min(gaps, default=None),
                    checks=checks, passed=all(checks.values()), robot_grasp_executed=False)


def build_contact_scene(cfg, output, actions):
    import genesis as gs
    from omegaconf import OmegaConf
    from topogym.world import StandardTabletopSceneBuilder
    from topogym.world.rope import make_elastic_tube_mesh, tube_morph, write_obj
    from topogym.world.rope_backends import rope_backend
    from .scene import scene_options

    layout = KnotLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True))
    backend = rope_backend(cfg.task.rope)
    backend.pre_scene()
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control,
                                          scene_options=scene_options(backend, cfg.task.rope))
    base = builder.create(show_viewer=False, include_robot=False,
                          table_material=backend.static_rigid_material(),
                          static_material=backend.static_rigid_material(),
                          decoration_material=backend.decoration_rigid_material())
    origin = np.array([*cfg.task.origin_xy_m, base.frames.table_surface_origin[2]])
    s = np.linspace(-.08, .08, int(np.ceil(.16/layout.segment_length_m))+1)
    parts = []
    Path(output).mkdir(parents=True, exist_ok=True)
    for i in range(2):
        points = np.zeros((len(s), 3))
        points[:, i] = s
        points[:, 2] = layout.rope_radius_m+.001+i*(2*layout.rope_radius_m+.001)
        points += origin
        vertices, faces = make_elastic_tube_mesh(points, radius=layout.rope_radius_m,
                                               radial_segments=layout.radial_segments)
        path = Path(output).resolve()/f'strand_{i}.obj'
        write_obj(path, vertices, faces)
        rope = base.scene.add_entity(tube_morph(path, cfg.task.rope), material=backend.material(),
                                     surface=gs.surfaces.Rough(color=(.86, .43, .12)))
        backend.declare_rest_straight(rope, points)
        actions.declare(rope, points)
        parts.append((rope, points))
    builder.finalize(base)
    return SimpleNamespace(tabletop=base, scene=base.scene, manifest=base.manifest,
                           rope=parts[0][0], layout=layout, centerline=np.vstack([p for _, p in parts]),
                           diagnostic_parts=parts, backend=backend)
