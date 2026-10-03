"""Programmatic PBD blanket with material-aware flattening and settling goals."""

from copy import deepcopy
from dataclasses import asdict, fields
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay

from topogym.assets.geometry.blanket_flatten import (
    BlanketLayout,
    generate,
    generate_flat_binding,
    material_coordinates,
    write_obj,
)
from topogym.assets.textures import fabric_weave
from topogym.assets.surfaces import ROLE_ROUGHNESS
from topogym.tasks.base import EntitySpec, InitialStateSpec, TaskDefinition, TaskSpec


class BlanketFlattenTask(TaskDefinition):
    task_id = "blanket_flatten"
    terminal_revision = "release_settling_v1"
    physics_model = "pbd_cloth"
    defaults = dict(
        length_m=0.60,
        width_m=0.48,
        mesh_spacing_m=0.012,
        particle_size_m=0.008,
        fold_count=5,
        fold_angle_deg=105.0,
        drop_clearance_m=0.1,
        center_xy_m=[-0.1356786, 0.05],
        stable_duration_s=0.5,
        minimum_coverage_ratio=0.90,
        maximum_stretch_ratio=1.15,
        maximum_height_m=0.03,
        maximum_speed_m_s=0.03,
        maximum_drift_m=0.003,
        material={"rho": 4.0, "stretch_compliance": 1e-7, "bending_compliance": 1e-5},
        color=[0.22, 0.46, 0.70],
        texture=dict(
            pattern="grid",
            accent_color=[0.76, 0.84, 0.87],
            stripe_pitch_m=0.06,
            thread_pitch_m=0.002,
        ),
    )

    # Include all existing geometry fields, including the curled-tail hinges.
    defaults = {**asdict(BlanketLayout()), **defaults}
    defaults.pop("seed")
    defaults.update(initialization_mode="authored", initial_state_path=None,
                    initial_state_resource=None, initial_state_sha256=None, table_friction=None)

    def final_settling_spec(self):
        from topogym.evaluation.terminal import SettlingSpec
        return SettlingSpec(particle_targets=("blanket",), particle_radius_m=self.config["particle_size_m"],
            maximum_speed_m_s=self.config["maximum_speed_m_s"], maximum_drift_m=self.config["maximum_drift_m"])

    def frozen_initial_state(self):
        from topogym.assets.library import resource_path
        from topogym.utils.io import sha256_file
        cfg = self.config
        path, resource = cfg["initial_state_path"], cfg["initial_state_resource"]
        if bool(path) == bool(resource):
            raise ValueError("Frozen Blanket requires exactly one initial-state path or resource")
        path = resource_path(resource) if resource else Path(path).expanduser().resolve()
        digest = sha256_file(path)
        if cfg["initial_state_sha256"] is None or digest != cfg["initial_state_sha256"]:
            raise ValueError("Frozen Blanket requires the matching initial-state manifest SHA-256")
        return InitialStateSpec(path, digest,
            acceptance=cfg.get("initial_state_acceptance", "released_stable"))

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        cfg = self.config
        layout_keys = tuple(f.name for f in fields(BlanketLayout) if f.name != "seed")
        self.layout = BlanketLayout(
            **{key: cfg[key] for key in layout_keys}, seed=self.seed
        )
        mode = cfg["initialization_mode"]
        if mode not in ("authored", "flat_for_preparation", "frozen"):
            raise ValueError("Unknown Blanket initialization mode")
        initial_state = None
        if mode == "frozen":
            initial_state = self.frozen_initial_state()
        vertices, faces, uv, panels, report = (
            generate(self.layout) if mode == "authored" else generate_flat_binding(self.layout))
        center = np.asarray(cfg["center_xy_m"], dtype=float)
        if center.shape != (2,) or not np.isfinite(center).all():
            raise ValueError("center_xy_m must be a finite XY vector")
        for key in (
            "minimum_coverage_ratio",
            "maximum_stretch_ratio",
            "maximum_height_m",
            "maximum_speed_m_s",
            "maximum_drift_m",
        ):
            if not np.isfinite(cfg[key]) or cfg[key] <= 0:
                raise ValueError(f"{key} must be finite and positive")
        if cfg["minimum_coverage_ratio"] > 1:
            raise ValueError("minimum_coverage_ratio cannot exceed one")
        vertices = vertices + [*center, self.table_height_m]
        path = Path(asset_dir) / "blanket.obj"
        write_obj(path, vertices, faces, uv, self.layout)
        surface = dict(color=tuple(cfg["color"]))
        if cfg["texture"] is not None:
            texture_options = dict(cfg["texture"])
            reserved = {
                "color",
                "size_m",
                "seed",
                "preview_path",
            } & texture_options.keys()
            if reserved:
                raise ValueError(
                    f"Blanket owns texture dimensions, color, seed and output: {sorted(reserved)}"
                )
            texture_path = path.with_name("blanket_diffuse.png")
            fabric_weave(
                color=cfg["color"],
                size_m=(self.layout.length_m, self.layout.width_m),
                seed=self.seed,
                preview_path=texture_path,
                **texture_options,
            )
            surface = dict(
                diffuse_texture_path=str(texture_path.resolve()),
                roughness=ROLE_ROUGHNESS["deformable"],
                vis_mode="visual",
            )
        self.birth_vertices, self.birth_uv, self.birth_panels = vertices, uv, panels
        self.birth_faces = faces.copy()
        entity = EntitySpec(
            "blanket",
            "mesh",
            path,
            physics_model="pbd_cloth",
            material=deepcopy(cfg["material"]),
            morph_options={
                "decimate": False,
                "convexify": False,
                "file_meshes_are_zup": True,
            },
            surface=surface,
        )
        return TaskSpec(
            (entity,),
            {
                **({"pbd_table_friction": {"entity_names": ("blanket",), **dict(cfg["table_friction"])}}
                   if cfg["table_friction"] is not None else {}),
                "pbd": {
                    "particle_size": self.layout.particle_size_m,
                    "max_stretch_solver_iterations": 8,
                }
            },
            dict(
                task_id=self.task_id,
                instance_id=self.instance_id,
                layout=asdict(self.layout),
                birth_report=report,
                initial_state_source="frozen_numeric_state" if initial_state else "seeded_programmatic_geometry",
                grasp_assistance=False,
            ),
            initial_state=initial_state,
        )

    def bind(self, entities):
        super().bind(entities)
        value = entities["blanket"].get_particles_pos()
        positions = (
            value.detach().cpu().numpy()
            if hasattr(value, "detach")
            else np.asarray(value)
        )
        uv, distances = material_coordinates(
            positions, self.birth_vertices, self.birth_uv, self.birth_panels
        )
        if not np.isfinite(uv).all() or np.max(distances) > self.layout.particle_size_m:
            raise ValueError(
                "PBD material-coordinate binding differs from authored cloth"
            )
        self.particle_faces = Delaunay(uv).simplices
        self.material_uv = uv.copy()
        if self.config["initialization_mode"] != "authored":
            from topogym.world.physics.pbd_binding import read_birth_visual_binding
            from topogym.evaluation.cloth_binding import audit_visual_binding
            binding = read_birth_visual_binding(entities["blanket"])
            vuv, vdistance = material_coordinates(binding.visual_birth_positions_m,
                self.birth_vertices, self.birth_uv, self.birth_panels)
            if vdistance.max() > self.layout.particle_size_m:
                raise ValueError("Visual birth surface differs from authored cloth")
            self.binding = binding
            self.binding_report = audit_visual_binding(binding.particle_birth_positions_m,
                binding.visual_birth_positions_m, uv, vuv, binding.support_indices,
                binding.support_weights, material_distance_limit_m=4*self.layout.particle_size_m,
                reconstruction_tolerance_m=1e-6, material_reconstruction_tolerance_m=1e-6)
            if not self.binding_report["passed"]:
                raise ValueError(f"Invalid Blanket visual binding: {self.binding_report}")
        self.particle_edges = np.unique(
            np.sort(
                np.concatenate(
                    (
                        self.particle_faces[:, :2],
                        self.particle_faces[:, 1:],
                        self.particle_faces[:, [2, 0]],
                    )
                ),
                axis=1,
            ),
            axis=0,
        )
        self.rest_lengths = np.linalg.norm(
            uv[self.particle_edges[:, 1]] - uv[self.particle_edges[:, 0]], axis=1
        )
        if np.any(self.rest_lengths <= 0):
            raise ValueError("Degenerate material-coordinate triangulation")

    def evaluate_state(self, state):
        from topogym.evaluation.cloth_metrics import footprint_area, footprint_area_slabs

        particle_state = state["particles"]["blanket"]
        positions = np.asarray(particle_state["position_m"])
        velocity = np.asarray(particle_state["velocity_m_s"])
        if not np.isfinite(positions).all() or not np.isfinite(velocity).all():
            return False, "Non-finite cloth particle state", {}
        heights = positions[:, 2] - self.table_height_m
        if heights.min() < -0.1:
            return False, "Cloth fell below the table", {}
        cfg = self.config
        stretch = (
            np.linalg.norm(
                positions[self.particle_edges[:, 1]]
                - positions[self.particle_edges[:, 0]],
                axis=1,
            )
            / self.rest_lengths
        )
        speed = float(np.linalg.norm(velocity, axis=1).max())
        cheap = dict(
            flat=float(heights.max()) <= cfg["maximum_height_m"],
            above_table=float(heights.min()) >= -self.layout.particle_size_m,
            material_intact=float(stretch.max()) <= cfg["maximum_stretch_ratio"],
            settled=speed <= cfg["maximum_speed_m_s"],
        )
        # The footprint union is ~88 % of a control step at every 2.5 ms tick. It only decides the goal when every cheap
        # gate holds, so it is computed then, and on each control step's last tick (complete_metrics, set by Env.step) so the
        # metrics a step reports stay complete; on the other ticks the goal is false either way (identical predicate).
        coverage = None
        if all(cheap.values()) or getattr(self, "complete_metrics", True):
            area = self.layout.length_m * self.layout.width_m
            coverage = footprint_area_slabs(positions, self.particle_faces) / area
            # The slab sum equals the union to ~1e-15 on cloth states; on extreme synthetic folds GEOS' one-shot union
            # itself drifts by up to ~3e-4 (the slab sum then agrees with a 10 nm grid union). Within 1e-3 of the
            # threshold the shipped union decides, so the gate is identical (scripts/check_blanket_coverage_slabs.py).
            if abs(coverage - cfg["minimum_coverage_ratio"]) < 1e-3:
                coverage = footprint_area(positions, self.particle_faces) / area
        gates = dict(covered=coverage is not None and coverage >= cfg["minimum_coverage_ratio"], **cheap)
        return (
            all(gates.values()),
            None,
            dict(
                gates=gates,
                coverage_ratio=None if coverage is None else float(coverage),
                maximum_height_m=float(heights.max()),
                maximum_speed_m_s=speed,
                maximum_stretch_ratio=float(stretch.max()),
            ),
        )

    def initialize(self, state):
        super().initialize(state)
        if self.config["initialization_mode"] == "frozen" and self.evaluate_state(state)[0]:
            raise ValueError("Frozen Blanket initial state already satisfies the flattening goal")
