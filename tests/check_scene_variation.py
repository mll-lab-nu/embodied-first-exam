"""Offline geometry gate for seeded scene variation (CPU; no Genesis scene is built).

For each task x tier the nominal scene, every corner of the offset envelope, and the
first N seeds that ``variation_id="seeded"`` maps to that tier are declared and
finalized on CPU, then compared with the nominal scene:

1. table margin: the smallest horizontal distance from any vertex to the table edge
   stays >= min(2 cm, nominal margin);
2. goal side: placement tasks find their region on the pinned side (finalize_spec
   raises when no region fits);
3. reach proxy: over the free parts' vertices, the largest horizontal distance to
   the nearest arm base grows by at most 2 cm;
4. framing: in every fixed camera whose nominal view holds the whole scene, the
   largest normalized image coordinate of any vertex stays <= 0.98; cameras that
   already crop the nominal scene (e.g. the long lock fixture) are reported only;
5. rejection: a build that raises or fails 1-4 is a rejection; the rate must be 0
   (the envelope rule allows <= 2%).

Corners are test-only and never feed the seed -> variant mapping.

Usage: PYTHONPATH=. python tests/check_scene_variation.py [task ...] [--seeds 50] [--jobs 8] [--out DIR]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import json
from pathlib import Path
import sys
import tempfile
import traceback

import numpy as np

TABLE_MARGIN_M = .02
REACH_GROWTH_M = .02
FRAME_LIMIT = .98
# ALOHA arm bases sit at +-0.469 m along x and -0.019 m along y from the mount
# (assets/robots/aloha/aloha.xml, left/right base_link); the Panda base is the mount.
ALOHA_ARM_OFFSETS = ((-.469, -.019), (.469, -.019))


def _entity_points(entity):
    from topogym.evaluation.task_metrics import body_points, rigid_asset_vertices
    if entity.volume_path is not None:
        with np.load(entity.volume_path) as volume:
            local = volume["spawn"]
    else:
        try:
            local = rigid_asset_vertices(entity)
        except ValueError:  # articulated asset: its root position only
            local = np.zeros((1, 3))
    return body_points(dict(position_m=entity.position_m, quaternion_wxyz=entity.quaternion_wxyz), local)


def _frame_extent(points, camera):
    pos, forward = np.asarray(camera["pos"], float), np.asarray(camera["lookat"], float)-camera["pos"]
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, camera["up"]); right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    vertical = np.tan(np.radians(camera["fov"]/2))
    horizontal = vertical*camera["res"][0]/camera["res"][1]
    relative = points-pos
    depth = relative@forward
    if np.any(depth <= 0):
        return float("inf")
    return float(max(np.max(abs(relative@right)/(depth*horizontal)), np.max(abs(relative@up)/(depth*vertical))))


def evaluate(task_id, variation_id, label, overrides, seed):
    """Declare + finalize one scene and measure it; never raises."""
    from omegaconf import OmegaConf
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    row = dict(task_id=task_id, variation_id=variation_id, label=label, seed=seed, overrides=overrides)
    try:
        cfg = load_scene_config(SimulatorConfig(task_id=task_id, variation_id=variation_id))
        task = task_definition(task_id, variation_id)(overrides, seed=seed)
        table = cfg.env.world.table
        with tempfile.TemporaryDirectory() as folder:
            assets = Path(folder)/"assets"
            spec = task.declare(assets, float(table.pos[2]+table.size[2]/2))
            spec = task.finalize_spec(spec, asset_dir=assets, scene_config=cfg)
            entities = [e for e in spec.entities if e.name != "goal_region"]
            points = {e.name: _entity_points(e) for e in entities}
        every = np.vstack(list(points.values()))
        center, half = np.asarray(table.pos[:2], float), np.asarray(table.size[:2], float)/2
        row["table_margin_m"] = float(np.min(half-np.abs(every[:, :2]-center)))
        mount = np.asarray(cfg.env.robot_mount.pos[:2], float)
        bases = mount+np.asarray(ALOHA_ARM_OFFSETS) if cfg.robot_control.robot.name == "aloha" else mount[None]
        free = np.vstack([points[e.name] for e in entities if not e.fixed] or [every])
        row["reach_m"] = float(np.max(np.min(np.linalg.norm(free[:, None, :2]-bases[None], axis=2), axis=1)))
        cameras = OmegaConf.to_container(cfg.env.cameras, resolve=True)
        row["framing"] = {name: _frame_extent(every, cam) for name, cam in cameras.items()
                          if not (cam.get("attach") or {}).get("enabled")}
        region = getattr(task, "goal_region", None)
        row["goal_side"] = None if region is None else [float(v) for v in region.separator_normal_xy]
    except Exception as error:  # noqa: BLE001 - a raise is a rejection, reported with its message
        row["error"] = f"{type(error).__name__}: {error}"
        row["traceback"] = traceback.format_exc(limit=4)
    return row


def corner_overrides(task_class):
    """Every lo/hi combination of the offset components; choice axes keep their first value."""
    from topogym.tasks.base import _parameter_at
    from topogym.tasks.scene_variation import _assign, axes
    components = []
    for axis in axes(task_class):
        if axis["kind"] != "offset":
            continue
        base = _parameter_at(task_class.defaults, axis["path"])
        if np.ndim(base) == 0:
            components.append((axis["path"], None, axis["range"]))
        else:
            components += [(axis["path"], i, r) for i, r in enumerate(axis["range"]) if r is not None]
    for signs in product((0, 1), repeat=len(components)):
        values = {}
        for (path, index, bounds), side in zip(components, signs):
            current = values.get(path, _parameter_at(task_class.defaults, path))
            if index is None:
                current = float(current)+bounds[side]
            else:
                current = [float(v) for v in current]
                current[index] += bounds[side]
            values[path] = current
        tree = {}
        for path, value in values.items():
            _assign(tree, path, value)
        yield "corner " + "".join("-+"[s] for s in signs), tree


def check(row, nominal):
    """Failure reasons of one row against its tier's nominal row."""
    if "error" in row:
        return [row["error"]]
    reasons = []
    if row["table_margin_m"] < min(TABLE_MARGIN_M, nominal["table_margin_m"]) - 1e-9:
        reasons.append(f"table margin {row['table_margin_m']*100:.1f} cm")
    if row["goal_side"] != nominal["goal_side"]:
        reasons.append(f"goal side {row['goal_side']} != {nominal['goal_side']}")
    if row["reach_m"] > nominal["reach_m"] + REACH_GROWTH_M + 1e-9:
        reasons.append(f"reach +{(row['reach_m']-nominal['reach_m'])*100:.1f} cm")
    for name, value in row["framing"].items():
        if nominal["framing"][name] <= FRAME_LIMIT and value > FRAME_LIMIT + 1e-9:
            reasons.append(f"{name} framing {value:.3f}")
    return reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tasks", nargs="*")
    parser.add_argument("--seeds", type=int, default=50, help="seeded draws per tier")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    from topogym.config.registry import TIER_ORDER, task_definition, variation_catalog
    from topogym.tasks.scene_variation import AXES, draw
    tasks = args.tasks or sorted(AXES)
    jobs = []
    for task_id in tasks:
        tiers = sorted((r for r in variation_catalog(task_id) if r["pool"] == "tier"),
                       key=lambda r: TIER_ORDER.index(r["difficulty"]))
        for index, record in enumerate(tiers):
            cls = task_definition(task_id, record["variation_id"])
            jobs.append((task_id, record["variation_id"], "nominal", {}, 0))
            jobs += [(task_id, record["variation_id"], label, tree, 0) for label, tree in corner_overrides(cls)]
            # The seeds "seeded" maps to this tier: seed % 3 == tier index.
            jobs += [(task_id, record["variation_id"], "seed", draw(cls, s), s)
                     for s in range(index, 3*args.seeds, 3)]
    with ProcessPoolExecutor(args.jobs) as pool:
        rows = list(pool.map(evaluate, *zip(*jobs)))
    failed = 0
    for key in dict.fromkeys((r["task_id"], r["variation_id"]) for r in rows):
        group = [r for r in rows if (r["task_id"], r["variation_id"]) == key]
        nominal = next(r for r in group if r["label"] == "nominal")
        if "error" in nominal:
            print(f"{key[1]}: nominal failed: {nominal['error']}")
            failed += 1
            continue
        for row in group:
            row["failures"] = check(row, nominal)
        bad = [r for r in group if r["failures"]]
        seeds = [r for r in group if r["label"] == "seed"]
        rate = sum(bool(r["failures"]) for r in seeds)/max(1, len(seeds))
        tight = min(group, key=lambda r: r.get("table_margin_m", np.inf))
        far = max(group, key=lambda r: r.get("reach_m", -np.inf))
        print(f"{key[1]}: {len(group)-1} variants, {len(bad)} failed, seed rejection {rate:.1%}; "
              f"tightest table margin {tight.get('table_margin_m', np.nan)*100:.1f} cm @ {tight['label']} {tight['seed']}; "
              f"reach {nominal['reach_m']*100:.1f} -> max {far.get('reach_m', np.nan)*100:.1f} cm @ {far['label']} {far['seed']}; "
              f"framing max " + ", ".join(f"{n} {max(r['framing'][n] for r in group if 'framing' in r):.3f}"
                                           f" (nominal {v:.3f})" for n, v in nominal["framing"].items()))
        for row in bad[:5]:
            print(f"    FAIL {row['label']} seed={row['seed']} {row['overrides']}: {'; '.join(row['failures'])}")
        failed += len(bad)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out/"rows.json").write_text(json.dumps(rows, indent=1, default=str))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
