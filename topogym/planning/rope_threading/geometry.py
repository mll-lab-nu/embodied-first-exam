"""Frozen Rope Threading geometry in world coordinates, without an engine.

The rigid fixtures (rings, stands, bases) are rebuilt with the same authoring
functions as the task assets, then placed at the shared table height. The rope
is represented by its 321 material stations from the task's own centerline.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import fcl
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.rope_threading import ring_mesh, route_crossings
from topogym.utils.geometry.passage import aperture_crossings


@dataclass(frozen=True)
class FrozenProblem:
    task: object
    variation: str
    table_height_m: float
    layout: object
    rings: list            # layout rings with world centres/axes
    stations_m: np.ndarray  # material arc length of each centerline station
    initial_m: np.ndarray   # world initial centerline (stations x 3)
    fixtures: trimesh.Trimesh
    fixture_names: list
    identity: dict
    risers: list

    @property
    def rope_radius_m(self):
        return float(self.layout.rope_radius_m)

    @property
    def required(self):
        return list(self.layout.required_crossings())


def _fixture_meshes(layout, table_height_m):
    meshes, names = [], []
    yaw = Rotation.from_euler("z", layout.yaw_deg, degrees=True)
    lift = np.array([0., 0., table_height_m])
    for ring in layout.rings():
        # layout.rings() already returns world-frame (yawed, translated) centres.
        torus = ring_mesh(ring, layout.ring_radial_segments)
        torus.apply_translation(lift)
        meshes.append(torus); names.append(ring["name"])
        for kind in ("stand", "base"):
            geom = ring[kind]
            if kind == "stand":
                support = trimesh.creation.capsule(height=2*geom["size"][1], radius=geom["size"][0], count=[16, 16])
                support.apply_translation(-support.bounds.mean(axis=0))
            else:
                support = trimesh.creation.box(extents=2*np.asarray(geom["size"]))
            m = np.eye(4); m[:3, :3] = yaw.as_matrix()
            support.apply_transform(m)
            support.apply_translation(layout.transform(geom["position"])+lift)
            meshes.append(support); names.append(f'{ring["name"]}_{kind}')
    for mesh in meshes:
        if not mesh.is_watertight:
            raise ValueError("Fixture meshes must be closed")
    return meshes, names


def frozen_problem(output, *, variation="medium", seed=0):
    """Declare the registered task on CPU, no physics; return world geometry."""
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    variation = variation.removeprefix("rope_threading_")
    if variation not in ("easy", "medium", "hard"):
        raise ValueError("Unknown rope_threading variation")
    directory = Path(output)/"assets"
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Use a fresh asset directory")
    directory.mkdir(parents=True, exist_ok=True)
    config = SimulatorConfig(task_id="rope_threading", variation_id="rope_threading_"+variation,
                             enable_rgb=False, compute_backend="cpu")
    scene = load_scene_config(config)
    table = scene.env.world.table
    height = float(table.pos[2]+table.size[2]/2)
    task = task_definition("rope_threading", "rope_threading_"+variation)(seed=seed)
    spec = task.declare(directory, height)
    spec = task.finalize_spec(spec, asset_dir=directory, scene_config=scene)
    layout = task.layout
    initial = layout.centerline()+[0., 0., height]
    stations = np.r_[0., np.cumsum(np.linalg.norm(np.diff(initial, axis=0), axis=1))]
    meshes, names = _fixture_meshes(layout, height)
    risers = []
    for entity in spec.entities:
        if entity.name.endswith("_base_riser"):
            mesh = trimesh.creation.box(extents=entity.morph_options["size"])
            transform = np.eye(4)
            transform[:3, :3] = Rotation.from_quat(np.roll(entity.quaternion_wxyz, -1)).as_matrix()
            transform[:3, 3] = entity.position_m
            mesh.apply_transform(transform)
            risers.append(mesh)
    fixtures = trimesh.util.concatenate(meshes)
    assets = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(directory.iterdir()) if p.suffix in (".obj", ".glb", ".mtl", ".npy", ".npz")}
    rings = layout.rings()
    identity = dict(task_id=task.task_id, variation_id=task.variation_id, family_id=task.family_id,
        model_revision=task.model_revision, terminal_revision=task.terminal_revision, seed=seed,
        instance_id=task.instance_id, table_height_m=height, asset_sha256=assets,
        required_crossings=[n+("+" if s > 0 else "-") for n, s in layout.required_crossings()],
        rings=[dict(name=r["name"], center_world_m=(np.asarray(r["center_m"])+[0, 0, height]).tolist(),
                    normal=list(r["normal"]), radius_m=r["radius_m"], tube_radius_m=r["tube_radius_m"])
               for r in rings],
        rope_radius_m=float(layout.rope_radius_m), rope_stations=len(initial),
        rope_length_m=float(stations[-1]), terminal=dict(task.config["terminal"]),
        robot_mount_world_m=list(map(float, scene.env.robot_mount.pos)),
        robot_scene=robot_scene_identity(scene),
        geometry_report=spec.metadata["geometry_report"])
    for ring in rings:
        ring["center_world_m"] = (np.asarray(ring["center_m"])+[0, 0, height]).tolist()
    return FrozenProblem(task, variation, height, layout, rings, stations, initial, fixtures, names, identity, risers)


def robot_scene_identity(scene):
    """Pin home, mount, controller and authored robot assets across plan/replay."""
    from omegaconf import OmegaConf
    robot = OmegaConf.to_container(scene.robot_control, resolve=True)
    root = Path(__file__).resolve().parents[3]
    asset_root = root / Path(robot["robot"]["asset"]).parent
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(asset_root.rglob("*")) if p.is_file()}
    return dict(control=robot, mount=OmegaConf.to_container(scene.env.robot_mount, resolve=True),
                asset_sha256=hashes)


def world_rings(problem):
    """Ring dictionaries usable by route_crossings/aperture_crossings (world centres)."""
    return [dict(r, center_m=r["center_world_m"]) for r in problem.rings]


def task_like_evaluation(points, problem):
    """Replica of RopeThreadingTask.evaluate_state geometry on a polyline.

    Uses the same aperture, thickness and ambiguity rules with the task's own
    terminal margins. Quiet/velocity and FEM integrity are physics-only and
    remain unverified here.
    """
    layout, terminal = problem.layout, problem.identity["terminal"]
    expected = problem.required
    hits, ambiguous, thickness_ok = [], False, True
    for ring in world_rings(problem):
        center, normal = np.asarray(ring["center_m"]), np.asarray(ring["normal"])
        radius = ring["radius_m"]-ring["tube_radius_m"]-layout.rope_radius_m-terminal["aperture_margin_m"]
        crossings, uncertain = aperture_crossings(points, center, normal, radius)
        nominal, _ = aperture_crossings(points, center, normal, ring["radius_m"]-ring["tube_radius_m"])
        thickness_ok &= len(nominal) == len(crossings)
        ambiguous |= uncertain
        for offset in (-ring["tube_radius_m"], ring["tube_radius_m"]):
            boundary, unsure = aperture_crossings(points, center+offset*normal, normal, radius)
            ambiguous |= unsure
            thickness_ok &= [h["sign"] for h in boundary] == [h["sign"] for h in crossings]
        hits.extend(dict(hit, ring=ring["name"]) for hit in crossings)
    hits.sort(key=lambda h: h["material_coordinate"])
    sequence = [(h["ring"], h["sign"]) for h in hits]
    return dict(sequence_matches=bool(sequence == expected and thickness_ok and not ambiguous),
                crossing_sequence=sequence, expected=expected, ambiguous=bool(ambiguous),
                thickness_clear=bool(thickness_ok), quiet_verified=False, fem_integrity_verified=False)


def geometric_crossings(points, problem):
    return route_crossings(points, world_rings(problem), problem.rope_radius_m)


class FixtureDistance:
    """FCL distances from the rope tube or a hand sphere to all fixtures."""

    def __init__(self, fixtures):
        model = fcl.BVHModel()
        model.beginModel(len(fixtures.vertices), len(fixtures.faces))
        model.addSubModel(np.asarray(fixtures.vertices), np.asarray(fixtures.faces, dtype=np.int32))
        model.endModel()
        self.fixtures = fcl.CollisionObject(model)
        self.queries = 0

    def tube(self, vertices, faces):
        model = fcl.BVHModel()
        model.beginModel(len(vertices), len(faces))
        model.addSubModel(np.asarray(vertices), np.asarray(faces, dtype=np.int32))
        model.endModel()
        obj = fcl.CollisionObject(model)
        self.queries += 1
        if fcl.collide(self.fixtures, obj, fcl.CollisionRequest(), fcl.CollisionResult()):
            return -1.
        return float(fcl.distance(self.fixtures, obj, fcl.DistanceRequest(), fcl.DistanceResult()))

    def sphere(self, center, radius):
        obj = fcl.CollisionObject(fcl.Sphere(float(radius)), fcl.Transform(np.asarray(center, float)))
        self.queries += 1
        if fcl.collide(self.fixtures, obj, fcl.CollisionRequest(), fcl.CollisionResult()):
            return -1.
        return float(fcl.distance(self.fixtures, obj, fcl.DistanceRequest(), fcl.DistanceResult()))
