"""Repository generators -> plain scene description (read-only calls), cached.

Bodies use task-local frames: table top at z = 0, task centred at the origin
(no robot here, so center_xy_m and yaw_deg are ignored). Collision items are
body-frame trimesh pieces (possibly concave; mjcf.py decomposes those) or
("capsule", a, b, radius) tuples.

python -m scripts.design_viewer.scenes --list
python -m scripts.design_viewer.scenes --scene hedgehog_in_cage_easy --set window_widths=28
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import pickle
import tempfile
import time
import xml.etree.ElementTree as ET

import numpy as np
from shapely.geometry import box
import trimesh

import topogym
from topogym.config.registry import task_definition, variation_catalog

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT/"runs"/"design_viewer"
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
    task_id: str
    bodies: list
    extras: dict = field(default_factory=dict)

    def body(self, name):
        return next(b for b in self.bodies if b.name == name)


def list_scenes():
    return [row["variation_id"] for task in TASKS for row in variation_catalog(task) if row["status"] == "integrated"]


def parse_sets(items):
    """['window_widths=28', ...] -> {'window_widths': 28, ...}; values are JSON when they parse."""
    result = {}
    for item in items or ():
        key, value = item.split("=", 1)
        try:
            result[key] = json.loads(value)
        except json.JSONDecodeError:
            result[key] = value
    return result


def build(name, overrides=None):
    overrides = dict(overrides or {})
    task = _task(name)
    path = cache_path(name, overrides)
    if path.exists():
        return pickle.loads(path.read_bytes())
    builder = {"hedgehog_in_cage": _hedgehog, "horseshoe_ring": _horseshoe, "slotted_post_ring": _slotted}[task.task_id]
    with tempfile.TemporaryDirectory() as folder:
        scene = builder(name, task, overrides, Path(folder))
    scene.extras["overrides"] = overrides
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(scene))
    return scene


def _task(name):
    task_id = next((t for t in TASKS if name.startswith(t)), None)
    if task_id is None:
        raise ValueError(f"{name}: not a variation of {TASKS}")
    return task_definition(task_id, name)(None, seed=0)


def cache_path(name, overrides=None):
    """Keyed by variation, overrides, config and every generator source / packaged resource hash."""
    task, package = _task(name), Path(topogym.__file__).parent
    digest = hashlib.sha256(json.dumps([name, dict(overrides or {}), task.config], sort_keys=True, default=str).encode())
    for source in (*sorted((package/"tasks"/task.task_id).glob("*.py")),
                   *sorted((package/"assets"/"geometry").glob("*.py")),
                   package/"assets"/"resources"/"catalog.json", Path(__file__)):
        digest.update(source.read_bytes())
    return RUNS/"cache"/name/f"{digest.hexdigest()[:16]}.pkl"


def _apply(fields, overrides):
    """Set dotted or unique bare keys in a nested dict; a scalar fills a list field."""
    for key, value in overrides.items():
        *path, leaf = key.split(".")
        parent = fields
        for part in path:
            parent = parent[part]
        if leaf not in parent:
            hits = [v for v in parent.values() if isinstance(v, dict) and leaf in v]
            if len(hits) != 1:
                raise KeyError(f"{key}: {'ambiguous' if hits else 'unknown'} field")
            parent = hits[0]
        old = parent[leaf]
        parent[leaf] = [value]*len(old) if isinstance(old, list) and not isinstance(value, list) else value
    return fields


def _hedgehog(name, task, overrides, folder):
    if overrides:
        if task.asset_resource:
            raise KeyError(f"{name}: overrides need a template-generated variant (no asset_resource)")
        from topogym.assets.geometry.hedgehog_in_cage import (cage_meshes, generate_assets, hedgehog_meshes,
                                                              load_template)
        template = folder/"override_template.json"
        template.write_text(json.dumps(_apply(load_template(), overrides)))
        layout, report = generate_assets(folder, float(task.config["scale"]), template, task.config["finish"])
        cage, _ = cage_meshes(layout)
        ball, _ = hedgehog_meshes(layout)
        cage_bottom = -layout.template["cage"]["height"]*layout.unit/2
    else:
        cage, ball, cage_bottom, report = task.build_assets(folder)
    pad, width = float(task.config["mount_height_m"]), float(task.config["mount_width_m"])
    origin = np.array([0., 0., pad-cage_bottom])
    pose = report["initial_pose"]
    mount = trimesh.creation.box(extents=[width, width, pad])
    return Scene(name, task.task_id, [
        Body("mount", mount, [mount], np.array([0, 0, pad/2]), np.array([1., 0, 0, 0]), (.35, .37, .4, 1), free=False),
        Body("cage", cage, _urdf_collision(folder, "cage"), origin, np.array([1., 0, 0, 0]), (.45, .3, .2, 1), free=False),
        Body("ball", ball, _urdf_collision(folder, "hedgehog"), origin+pose["position_m"],
             np.asarray(pose["quaternion_wxyz"], float), (.9, .62, .3, 1)),
    ], dict(cage_pos=origin, initial_pose=pose))


def _urdf_collision(folder, name):
    # The URDF list is the authority: medium unpacks an older bundle and rewrites only piece 000.
    files = [m.get("filename") for c in ET.parse(folder/f"{name}.urdf").getroot().iter("collision")
             for m in c.iter("mesh")]
    return [trimesh.load(folder/f, force="mesh", process=False) for f in files]


def _horseshoe(name, task, overrides, folder):
    from topogym.assets.geometry.horseshoe_ring import HorseshoeAssembly, load_template
    from topogym.assets.variation_resources import read_json
    template = copy.deepcopy(read_json(task.template_resource) if task.template_resource else load_template())
    assembly = HorseshoeAssembly(template=_apply(template, overrides), scale=float(task.config["scale"]))
    origins = {b.name: b.visual.center_mass for b in assembly.bodies}
    if task.layout_resource and not overrides:
        poses = read_json(task.layout_resource)["poses"]  # settled rest poses
    else:  # authored layout lowered onto the table, as common.py does before settling
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
                           density=float(template["density_kg_m3"])))
    return Scene(name, task.task_id, bodies,
                 dict(loops=assembly.loops, edges=assembly.edges, origins=origins, timestep=.001))


def _slotted(name, task, overrides, folder):
    from topogym.assets.geometry.slotted_post_ring import SlottedPostLayout, make_meshes
    layout = SlottedPostLayout(**_apply(asdict(SlottedPostLayout(**task.config["geometry"])), overrides)).validate()
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
    for side, index in (("left", 2), ("right", 15)):
        mesh = parts[f"bead_{side}"]
        c = mesh.bounds.mean(0)
        k = np.argmin(np.linalg.norm(cord-layout.cord_controls()[index], axis=1))
        bodies.append(Body(f"bead_{side}", mesh.copy().apply_translation(-c),
                           [h.apply_translation(-c) for h in _sector_hulls(mesh, cord[k+1]-cord[k-1], c)],
                           c, identity, light, density=700.))
        disc = parts[f"disc_{side}"]
        c = disc.bounds.mean(0)
        bodies.append(Body(f"disc_{side}", disc.copy().apply_translation(-c), [disc.convex_hull.apply_translation(-c)],
                           c, identity, wood, density=700.))
    return Scene(name, task.task_id, bodies, dict(layout=layout, cord=cord, timestep=.002))


def _post_pieces(layout, arc_levels=9):
    """Exact convex prisms of the slotted post: left/right halves cut into z strips.

    Strips are dense only across the rounded slot ends, where a hull bulges into
    the slot by the arc sagitta of its strip (about 0.1 mm here).
    """
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
                    xz = np.asarray(poly.exterior.coords)
                    pts = np.array([[x, y, z] for x, z in xz for y in (-half_depth, half_depth)])
                    pieces.append(trimesh.convex.convex_hull(pts))
    return pieces


def _sector_hulls(mesh, axis, centre, sectors=12):
    """Bead as convex sectors around its bore, so the bore stays open for the cord."""
    axis = axis/np.linalg.norm(axis)
    ref = np.cross(axis, [1, 0, 0] if abs(axis[0]) < .9 else [0, 1, 0])
    ref /= np.linalg.norm(ref)
    other = np.cross(axis, ref)
    v = mesh.vertices-centre
    angle = np.arctan2(v@other, v@ref) % (2*np.pi)
    width = 2*np.pi/sectors
    hulls = []
    for k in range(sectors):
        d = (angle-k*width) % (2*np.pi)
        hulls.append(trimesh.convex.convex_hull(mesh.vertices[(d <= width+1e-3) | (d >= 2*np.pi-1e-3)]))
    return hulls


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="build every registered scene and print one line each")
    parser.add_argument("--scene")
    parser.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE")
    args = parser.parse_args()
    names = list_scenes() if args.list or not args.scene else [args.scene]
    for name in names:
        start = time.perf_counter()
        scene = build(name, parse_sets(args.set) if args.scene else None)
        items = sum(len(b.collision) for b in scene.bodies)
        faces = sum(len(b.visual.faces) for b in scene.bodies)
        print(f"{name:34s} bodies {len(scene.bodies):2d} (free {sum(b.free for b in scene.bodies)}), "
              f"collision items {items:4d}, visual faces {faces:6d}, {time.perf_counter()-start:5.1f} s")


if __name__ == "__main__":
    # Run the imported module so cached pickles name scripts.design_viewer.scenes.Scene, not __main__.Scene.
    from scripts.design_viewer.scenes import main as module_main
    module_main()
