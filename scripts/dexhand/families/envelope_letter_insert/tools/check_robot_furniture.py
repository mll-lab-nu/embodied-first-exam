#!/usr/bin/env python3
"""Authoring only (not shipped): exact robot-vs-furniture check at reset and over a trajectory (stand_check).

Robot = every geom (collision and visual) of the Marvin subtree `base_link`: base plate, stand, torso, both arms,
flanges, the parked left hand, and the active right hand. Furniture = every static world geom that is not a task
object (desk top, desk legs; the floor plane separately). For each robot/furniture pair `mujoco.mj_geomDistance` is
computed (meshes as convex hulls, i.e. conservative); a negative hull distance of a mesh geom against a furniture box is
refined by an exact triangle-vs-box separating-axis test (tools/tri_box.py), which decides. The floor test uses the
lowest mesh vertex / primitive point. The active hand (mount subtree `wrist_stage`) touching the desk is a physical
contact of a dynamic body, reported separately with its contact depth.

  python tools/check_robot_furniture.py --traj solution/trajectory.npz --every 5 --out check.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import mujoco

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.path.append(str(HERE.parents[1] / "shared"))

from runtime import Session  # noqa: E402
from replay import load_trajectory  # noqa: E402
from tri_box import tris_overlap_box, mesh_triangles  # noqa: E402


def subtree(m, root):
    out = set()
    for b in range(m.nbody):
        p = b
        while p:
            if p == root:
                out.add(b)
                break
            p = int(m.body_parentid[p])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", required=True)
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows, hand, _ = load_trajectory(a.traj)
    s = Session(hand=hand)
    m, d = s.model, s.data
    robot_bodies = subtree(m, m.body("base_link").id)
    active_hand = subtree(m, m.body("wrist_stage").id)
    robot = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in robot_bodies and int(m.geom_bodyid[g]) not in active_hand]
    hand_geoms = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in active_hand]
    static = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) == 0]
    floor = [g for g in static if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE]
    furniture = [g for g in static if g not in floor]
    assert all(m.geom_type[f] == mujoco.mjtGeom.mjGEOM_BOX for f in furniture)

    def name(g):
        return m.geom(g).name or f"{m.body(int(m.geom_bodyid[g])).name}/geom{g}"

    def lowest(g):
        if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
            return float(mesh_triangles(m, d, g)[:, :, 2].min())
        return float(d.geom_xpos[g][2] - m.geom_rbound[g])

    floor_z = float(d.geom_xpos[floor[0]][2]) if floor else None
    min_dist, exact_hits, min_floor, hand_contact = {}, [], (np.inf, None, None), 0.0
    samples = 0
    s.reset()
    for k in range(-1, len(rows)):
        if k >= 0:
            s.step(rows[k])
            if k % a.every and not s.done:
                continue
        samples += 1
        for r in robot:
            for f in furniture:
                dist = mujoco.mj_geomDistance(m, d, int(r), int(f), 0.2, None)
                if dist < 0 and m.geom_type[r] == mujoco.mjtGeom.mjGEOM_MESH:
                    tri = mesh_triangles(m, d, r)
                    hit = tris_overlap_box(tri, d.geom_xpos[f], d.geom_xmat[f].reshape(3, 3), m.geom_size[f])
                    if hit.any():
                        exact_hits.append(dict(control=k, robot=name(r), furniture=name(f), triangles=int(hit.sum())))
                    dist = max(dist, 0.0)  # hull overlaps, exact geometry does not
                elif dist < 0:
                    exact_hits.append(dict(control=k, robot=name(r), furniture=name(f), dist_m=round(dist, 5)))
                key = (r, f)
                if key not in min_dist or dist < min_dist[key][0]:
                    min_dist[key] = (dist, k)
            if floor_z is not None:
                z = lowest(r) - floor_z
                if z < min_floor[0]:
                    min_floor = (z, k, name(r))
        for i in range(d.ncon):
            c = d.contact[i]
            if (c.geom1 in hand_geoms and c.geom2 in furniture) or (c.geom2 in hand_geoms and c.geom1 in furniture):
                hand_contact = min(hand_contact, float(c.dist))
        if s.done:
            break
    best = sorted(((v[0], v[1], name(r), name(f)) for (r, f), v in min_dist.items()), key=lambda t: t[0])
    report = dict(
        method="mj_geomDistance on every robot geom (collision and visual; meshes as convex hulls) vs every static "
               "furniture box, refined by an exact triangle-vs-box SAT test where a hull distance is negative; floor: "
               "lowest mesh vertex vs the floor plane",
        hand=hand, base=s.config.get("marvin"), samples=samples, every=a.every, last_control=k,
        episode=s.status()["reason"], robot_geoms=len(robot), furniture=[name(f) for f in furniture],
        exact_overlaps=exact_hits[:20], n_exact_overlaps=len(exact_hits),
        min_hull_distance_m=round(best[0][0], 5),
        closest=[dict(dist_m=round(b[0], 5), control=b[1], robot=b[2], furniture=b[3]) for b in best[:5]],
        floor_z=floor_z, min_height_above_floor_m=round(min_floor[0], 5), lowest=dict(control=min_floor[1], geom=min_floor[2]),
        active_hand_desk_contact_min_dist_m=round(hand_contact, 5))
    Path(a.out).write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k_: report[k_] for k_ in ("base", "episode", "samples", "n_exact_overlaps", "min_hull_distance_m",
                                                  "min_height_above_floor_m", "lowest", "active_hand_desk_contact_min_dist_m")}, indent=1))


if __name__ == "__main__":
    main()
