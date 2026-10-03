"""Task generators (read-only) -> bodies with visual and collision meshes, cached.

Task-local frame: table top at z = 0, task centred at the origin. Collision items are
body-frame trimesh pieces (model.py splits concave ones) or ("capsule", a, b, radius).
The cache key hashes the generator sources and the packaged resource catalog, so a
changed task rebuilds by itself.
"""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import pickle
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from shapely.geometry import box
import trimesh

import topogym
from topogym.config.registry import task_definition, variation_catalog

CACHE = Path(__file__).parent/".cache"
TASKS = ("hedgehog_in_cage", "horseshoe_ring", "slotted_post_ring")


@dataclass
class Body:
    name: str
    visual: trimesh.Trimesh
    collision: list
    pos: np.ndarray
    quat: np.ndarray  # wxyz
    rgba: tuple
    free: bool = True
    density: float = 1000.


@dataclass
class Scene:
    name: str
    bodies: list
    extras: dict = field(default_factory=dict)

    def body(self, name):
        return next(b for b in self.bodies if b.name == name)


def list_scenes():
    return [row["variation_id"] for task in TASKS for row in variation_catalog(task) if row["status"] == "integrated"]


def build(name):
    task_id = next((t for t in TASKS if name.startswith(t)), None)
    if task_id is None:
        raise ValueError(f"{name}: not a variation of {TASKS}")
    task = task_definition(task_id, name)(None, seed=0)
    path = CACHE/name/f"{_key(name, task)}.pkl"
    if path.exists():
        try:
            return pickle.loads(path.read_bytes())
        except (EOFError, pickle.UnpicklingError):  # interrupted write: rebuild
            pass
    with tempfile.TemporaryDirectory() as folder:
        scene = {"hedgehog_in_cage": _hedgehog, "horseshoe_ring": _horseshoe,
                 "slotted_post_ring": _slotted}[task_id](name, task, Path(folder))
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(f".{os.getpid()}.tmp")
    partial.write_bytes(pickle.dumps(scene))
    os.replace(partial, path)  # a reader never sees half a file
    return scene


def _key(name, task):
    package = Path(topogym.__file__).parent
    digest = hashlib.sha256(json.dumps([name, task.config], sort_keys=True, default=str).encode())
    for source in (*sorted((package/"tasks"/task.task_id).glob("*.py")), *sorted((package/"assets"/"geometry").glob("*.py")),
                   *sorted((package/"utils"/"geometry").glob("*.py")), package/"assets"/"resources"/"catalog.json",
                   Path(__file__)):
        digest.update(source.read_bytes())
    return digest.hexdigest()[:16]


def _hedgehog(name, task, folder):
    cage, ball, cage_bottom, report = task.build_assets(folder)
    pad, width = float(task.config["mount_height_m"]), float(task.config["mount_width_m"])
    origin = np.array([0., 0., pad-cage_bottom])
    pose = report["initial_pose"]
    mount = trimesh.creation.box(extents=[width, width, pad])
    identity = np.array([1., 0, 0, 0])
    return Scene(name, [
        Body("mount", mount, [mount], np.array([0, 0, pad/2]), identity, (.35, .37, .4, 1), free=False),
        Body("cage", cage, _urdf_collision(folder, "cage"), origin, identity, (.45, .3, .2, 1), free=False),
        Body("ball", ball, _urdf_collision(folder, "hedgehog"), origin+pose["position_m"],
             np.asarray(pose["quaternion_wxyz"], float), (.9, .62, .3, 1))])


def _urdf_collision(folder, name):
    # The URDF list is the authority: medium unpacks an older bundle and rewrites only piece 000.
    files = [m.get("filename") for c in ET.parse(folder/f"{name}.urdf").getroot().iter("collision")
             for m in c.iter("mesh")]
    return [trimesh.load(folder/f, force="mesh", process=False) for f in files]


def _horseshoe(name, task, folder):
    from topogym.assets.geometry.horseshoe_ring import HorseshoeAssembly
    # The task's own accessors: a tier may build its template in code and carry its own rest poses.
    assembly = HorseshoeAssembly(template=task.template(), scale=float(task.config["scale"]))
    origins = {b.name: b.visual.center_mass for b in assembly.bodies}
    poses = task.rest_poses()  # settled rest poses
    if poses is None:  # authored layout lowered onto the table, as common.py does before settling
        lift = float(task.config["initial_floor_clearance_m"])-min(b.visual.vertices[:, 2].min() for b in assembly.bodies)
        poses = {n: {"position_m": o+[0, 0, lift], "quaternion_wxyz": [1, 0, 0, 0]} for n, o in origins.items()}
    bodies = []
    for b in assembly.bodies:
        o = origins[b.name]
        collision = [p.copy().apply_translation(-o) for p in b.convex]
        for loop in b.loops:
            pts = loop.points()-o
            collision += [("capsule", p, q, loop.wire_radius) for p, q in zip(pts, np.roll(pts, -1, axis=0))]
        rgba = (.9, .5, .2, 1) if b.name == "target_ring" else (*b.color[:3], 1)
        bodies.append(Body(b.name, b.visual.copy().apply_translation(-o), collision,
                           np.asarray(poses[b.name]["position_m"], float),
                           np.asarray(poses[b.name]["quaternion_wxyz"], float), rgba,
                           density=float(assembly.template["density_kg_m3"])))
    return Scene(name, bodies, dict(timestep=.001))


def _slotted(name, task, folder):
    from topogym.assets.geometry.slotted_post_ring import make_meshes
    layout = task.make_layout().validate()  # a tier may re-route the cord (a layout subclass)
    parts, cord = make_meshes(layout)
    zero, identity = np.zeros(3), np.array([1., 0, 0, 0])
    wood, light = (.45, .25, .14, 1), (.85, .7, .5, 1)
    bodies = [Body("base", parts["base"], [parts["base"]], zero, identity, light, free=False),
              Body("post", parts["post"], _post_pieces(layout), zero, identity, wood, free=False)]
    centre = np.array([0, 0, layout.ring_z])
    a = np.linspace(0, 2*np.pi, 24, endpoint=False)
    loop = layout.ring_major_radius_m*np.c_[np.cos(a), np.sin(a), np.zeros_like(a)]
    bodies.append(Body("target_ring", parts["target_ring"].copy().apply_translation(-centre),
                       [("capsule", p, q, layout.ring_tube_radius_m) for p, q in zip(loop, np.roll(loop, -1, axis=0))],
                       centre, identity, (.9, .5, .2, 1), density=7800.))
    for side, index in zip(("left", "right"), layout.bead_controls()):
        k = np.argmin(np.linalg.norm(cord-layout.cord_controls()[index], axis=1))  # as make_meshes places it
        bodies.append(Body(f"bead_{side}", parts[f"bead_{side}"].copy().apply_translation(-cord[k]),
                           _bead_sectors(layout, cord[k+1]-cord[k-1]), cord[k], identity, light, density=700.))
        disc = parts[f"disc_{side}"]
        c = disc.bounds.mean(0)
        bodies.append(Body(f"disc_{side}", disc.copy().apply_translation(-c), [disc.convex_hull.apply_translation(-c)],
                           c, identity, wood, density=700.))
    return Scene(name, bodies, dict(layout=layout, cord=cord, timestep=.002))


def _post_pieces(layout, arc_levels=9):
    """Exact convex prisms of the slotted post: left/right halves cut into z strips, dense only
    across the rounded slot ends, where a hull bulges into the slot by ~0.1 mm."""
    polygon, r = layout.post_polygon(), layout.slot_width_m/2
    rise = r*(1-np.cos(np.linspace(0, np.pi/2, arc_levels)))
    _, bottom, _, top = polygon.bounds
    levels = np.unique(np.r_[bottom, layout.slot_bottom_m+rise, layout.slot_top_m-rise, top])
    half_depth, pieces = layout.post_depth_m/2, []
    for x0, x1 in ((-1, 0), (0, 1)):
        for z0, z1 in zip(levels[:-1], levels[1:]):
            part = polygon.intersection(box(x0, z0, x1, z1))
            for poly in getattr(part, "geoms", [part]):
                if poly.area > 1e-9:
                    pts = [[x, y, z] for x, z in np.asarray(poly.exterior.coords) for y in (-half_depth, half_depth)]
                    pieces.append(trimesh.convex.convex_hull(np.array(pts)))
    return pieces


def _bead_sectors(layout, axis, sectors=12):
    """Bead (a sphere with an axial bore) as convex sectors around the bore, built from the shape
    itself so neighbouring sectors share their faces: the bore stays open for the cord and no gap
    lets the cord slip out sideways (sectors cut from mesh vertices left 5.6 deg gaps)."""
    big, bore = layout.bead_radius_m, layout.bead_hole_radius_m
    axis = axis/np.linalg.norm(axis)
    ref = np.cross(axis, [1, 0, 0] if abs(axis[0]) < .9 else [0, 1, 0])
    ref /= np.linalg.norm(ref)
    other = np.cross(axis, ref)
    zs = np.linspace(-1, 1, 9)*np.sqrt(big**2-bore**2)
    hulls = []
    for k in range(sectors):
        points = [z*axis+r*(np.cos(a)*ref+np.sin(a)*other)
                  for a in np.linspace(k, k+1, 4)*2*np.pi/sectors for z in zs for r in (bore, np.sqrt(big**2-z**2))]
        hulls.append(trimesh.convex.convex_hull(np.array(points)))
    return hulls
