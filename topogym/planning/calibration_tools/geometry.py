"""Detached rigid geometry probes. Edits here never teleport a running Env."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
import math

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.geometry import entity_mesh, matrix, interpolate, pose_dict
from topogym.utils.io import sha256_file, write_json_atomic
from .contracts import UnsupportedCapability, digest, identifier, positive_int


def pose(value):
    if not isinstance(value, dict) or set(value) != {"position_m", "quaternion_wxyz"}:
        raise ValueError("pose requires position_m and unit quaternion_wxyz")
    p, q = np.asarray(value["position_m"], dtype=float), np.asarray(value["quaternion_wxyz"], dtype=float)
    if p.shape != (3,) or q.shape != (4,) or not np.isfinite(p).all() or not np.isfinite(q).all():
        raise ValueError("Invalid pose dimensions or nonfinite coordinates")
    if not np.isclose(np.linalg.norm(q), 1., atol=1e-7):
        raise ValueError("A unit wxyz quaternion is required")
    return p, Rotation.from_quat(q[[1, 2, 3, 0]])


class RigidProbe:
    def __init__(self, config, output):
        from topogym.config.registry import task_definition, variation_registration
        from topogym.config.scene import load_scene_config
        from topogym.simulator.config import SimulatorConfig
        from topogym.utils.snapshots import thaw
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.config = config if isinstance(config, SimulatorConfig) else SimulatorConfig(**config)
        if self.config.task_id not in {"cast_keyhole", "horseshoe_ring"}:
            raise UnsupportedCapability("Rigid probe adapters support Cast Keyhole and Horseshoe Ring")
        if self.config.variation_id == "seeded":
            raise UnsupportedCapability("Probe requires an explicit frozen variation, not seeded scene perturbations")
        seed = self.config.seed or 0
        registration = variation_registration(self.config.task_id, self.config.variation_id, seed)
        scene = load_scene_config(self.config)
        self.task = task_definition(self.config.task_id, registration["variation_id"])(
            thaw(self.config.task_parameters), seed=seed)
        table = scene.env.world.table
        self.table_height = float(table.pos[2] + table.size[2]/2)
        spec = self.task.declare(self.output / "assets", self.table_height)
        spec = self.task.finalize_spec(spec, asset_dir=self.output / "assets", scene_config=scene)
        if spec.initial_state is not None:
            raise UnsupportedCapability("Probe needs an initial-state adapter for this frozen state")
        names = set(self.task.placement_targets) | set(self.task.placement_remainder)
        # Goal markings are visual meshes, not task obstacles.
        self.entities = {entity.name: entity for entity in spec.entities if entity.name in names}
        self.meshes = {name: entity_mesh(entity) for name, entity in self.entities.items()}
        self.poses = {name: pose(dict(position_m=entity.position_m, quaternion_wxyz=entity.quaternion_wxyz))
                      for name, entity in self.entities.items()}
        self.pins = {name for name, entity in self.entities.items() if entity.fixed}
        self.grasps = {}
        self.revision = 0
        self.candidates = {}
        self.source_state_ref = None
        self.assets = {str(p.relative_to(self.output)): sha256_file(p)
                       for p in sorted((self.output / "assets").rglob("*")) if p.is_file()}
        self.scene_revision = digest(self.assets)

    def inspect(self, entity=None):
        names = tuple(self.entities) if entity is None else (entity,)
        return dict(scope="detached_geometry_probe", probe_revision=self.revision,
                    scene_revision=self.scene_revision, source_state_ref=self.source_state_ref,
                    physics_steps=0, table_height_m=self.table_height,
                    bodies={name: dict(**pose_dict(self.poses[name]), pinned=name in self.pins,
                                       bounds_local_m=self.meshes[name].bounds.tolist()) for name in names},
                    probe_grasps=deepcopy(self.grasps))

    def snapshot(self):
        return deepcopy((self.poses, self.pins, self.grasps, self.source_state_ref))

    def restore(self, snapshot):
        self.poses, self.pins, self.grasps, self.source_state_ref = deepcopy(snapshot)
        self.revision += 1

    def sync(self, world, state_ref):
        proposed = {name: pose({key: world["bodies"][name][key] for key in ("position_m", "quaternion_wxyz")})
                    for name in self.entities}
        self.poses = proposed
        self.pins = {name for name, entity in self.entities.items() if entity.fixed}
        self.grasps = {}
        self.source_state_ref = deepcopy(state_ref)
        self.revision += 1
        return self.inspect()

    def set_pose(self, entity, value, *, frame="world", velocity_policy="not_applicable", scope="probe"):
        if scope != "probe" or velocity_policy != "not_applicable":
            raise UnsupportedCapability("Only detached geometric edits; dynamic teleport/velocity editing requires a qualified rebuild adapter")
        if entity not in self.poses:
            raise KeyError(entity)
        if entity in self.pins:
            raise ValueError("Unpin the object before moving it")
        if any(row["entity"] == entity for row in self.grasps.values()):
            raise ValueError("Clear the probe grasp before editing its object pose")
        p, r = pose(value)
        if frame != "world":
            base_p, base_r = self.poses[frame]
            p, r = base_p + base_r.apply(p), base_r * r
        self.poses[entity] = (p, r)
        self.revision += 1
        return self.inspect(entity)

    def pin(self, entity, enabled):
        if entity not in self.poses:
            raise KeyError(entity)
        if enabled and any(row["entity"] == entity for row in self.grasps.values()):
            raise ValueError("Clear probe grasp before pinning")
        self.pins.add(entity) if enabled else self.pins.discard(entity)
        self.revision += 1
        return self.inspect(entity)

    def grasp(self, hand, entity=None, transform=None, hand_pose=None):
        identifier(hand)
        if entity is None:
            self.grasps.pop(hand, None)
        else:
            if entity in self.pins or entity not in self.poses:
                raise ValueError("Probe grasp needs an unpinned known object")
            if any(k != hand and v["entity"] == entity for k, v in self.grasps.items()):
                raise ValueError("An object already has a probe grasp")
            offset = pose(transform)
            hp, hr = pose(hand_pose)
            self.poses[entity] = (hp + hr.apply(offset[0]), hr * offset[1])
            self.grasps[hand] = dict(entity=entity, transform=pose_dict(offset), hand_pose=hand_pose,
                                      contact_acquired=False)
        self.revision += 1
        return self.inspect()

    def sweep(self, entity, poses, *, obstacles=None, resolution=None, cancelled=lambda: False):
        from topogym.solvers.collision.triangle_meshes import TriangleMeshPair
        resolution = resolution or dict(translation_m=.001, rotation_rad=.01)
        if set(resolution) != {"translation_m", "rotation_rad"} or any(
                isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in resolution.values()):
            raise ValueError("resolution requires positive translation_m and rotation_rad")
        if not poses:
            raise ValueError("A nonempty path is required")
        path = [pose(p) for p in poses]
        names = list(self.meshes.keys() - {entity}) if obstacles is None else list(obstacles)
        if not names or entity in names or len(names) != len(set(names)):
            raise ValueError("Specify distinct obstacles excluding the moving entity")
        checks = {name: TriangleMeshPair((self.meshes[name], self.meshes[entity])) for name in names}
        # Bound both translation and rotation between submitted waypoints.
        samples = [path[0]]
        for a, b in zip(path, path[1:]):
            count = max(1, math.ceil(np.linalg.norm(b[0]-a[0])/resolution["translation_m"]),
                        math.ceil((b[1]*a[1].inv()).magnitude()/resolution["rotation_rad"]))
            if len(samples) + count > 100000:
                raise ValueError("Sweep sample budget exceeds 100000")
            samples.extend(interpolate(a, b, i/count) for i in range(1, count+1))
        minimum, witness, evaluated, stopped = None, None, 0, False
        for i, sample in enumerate(samples):
            if cancelled():
                stopped = True
                break
            moving = matrix(*sample)
            for name, checker in checks.items():
                gap = checker.clearance((matrix(*self.poses[name]), moving))
                # Triangle intersections alone miss a solid entirely inside another.
                relative = np.linalg.inv(matrix(*self.poses[name])) @ moving
                if gap >= 0:
                    moving_mesh = self.meshes[entity].copy().apply_transform(relative)
                    from topogym.assets.geometry.cast_keyhole import mesh_clearance
                    gap = mesh_clearance(self.meshes[name], moving_mesh)
                if gap <= 0:
                    witness = dict(sample=i, obstacle=name, pose=pose_dict(sample), intersection=True)
                    minimum = 0.
                    break
                minimum = gap if minimum is None else min(minimum, gap)
            evaluated += 1
            if witness:
                break
        return dict(passed=not stopped and witness is None and evaluated == len(samples),
                    status="cancelled" if stopped else "complete", first_collision=witness,
                    minimum_sampled_clearance_m=minimum, evaluated_samples=evaluated,
                    total_samples=len(samples), resolution=resolution, physics_steps=0,
                    scope="sampled object surfaces only; no continuous-path or robot-success certificate",
                    obstacles=names, scene_revision=self.scene_revision, probe_revision=self.revision)

    def preview(self, parameters):
        if self.task.task_id == "horseshoe_ring":
            from .adapters.horseshoe_ring import preview
        else:
            from .adapters.cast_keyhole import preview
        token = uuid4().hex
        result = preview(self.task, parameters, self.output / "candidates" / token)
        self.candidates[token] = result
        return result

    def compare(self, a, b):
        first, second = self.candidates[a], self.candidates[b]
        return dict(a=a, b=b, minimum_initial_clearance_delta_m=
                    second["geometry"]["minimum_initial_surface_clearance_m"] - first["geometry"]["minimum_initial_surface_clearance_m"],
                    bodies={left["name"]: dict(mass_delta_kg=right["mass_kg"]-left["mass_kg"],
                        inertia_delta_kg_m2=(np.asarray(right["inertia_kg_m2"])-left["inertia_kg_m2"]).tolist())
                        for left, right in zip(first["bodies"], second["bodies"])},
                    sections=[str(Path(row["output"]) / "sections.json") for row in (first, second)],
                    physical_execution_verified=False)

    def export_patch(self, candidate):
        row = self.candidates[candidate]
        path = self.output / "candidates" / candidate / "parameter_patch.json"
        write_json_atomic(path, dict(source_resource=row["source_resource"], base_sha256=row["base_sha256"],
                                    candidate_sha256=row["candidate_sha256"], parameters=row["parameters"],
                                    requires_rebuild=True, requires_oracle_requalification=True))
        return dict(patch=str(path), applied_to_official_assets=False)
