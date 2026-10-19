"""Geometry helpers shared by the world, the hazard layer and the movers (0.5.1).

`distance` is `mujoco.mj_geomDistance` with a guard. MuJoCo returns 0 for some pairs of convex shapes that are apart
(box against box, box against mesh, mesh against mesh, box against ellipsoid: about 1 % of random pairs at `distmax`
1.0 and 0.1 % at 0.025, under 3.3.7 and 3.8.1 alike; never for spheres, capsules and cylinders against a box or each
other). `fromto` then holds two points on the shapes, but not the nearest ones: their distance is an upper bound, from
1.0 to 14 times the true one (a pair 1.5 mm apart read 21.6 mm). A true 0 (the shapes just touch) has the two points
together. MuJoCo can also return 0 with `fromto` left all zeros for a pair that is apart (a held bottle 40 mm from a
glass, found by the clearance audit; mesh against mesh in a random search, 3 of 12000 pairs). So a 0 is suspect
whenever the two points are apart or the pair is not among the contacts of the data (`d.contact`): then the query is
run again with the second shape moved by `NUDGE_M` (on scratch data, never on the caller's), which gives the true
distance (checked against an exact box-box distance on every false zero of 1500 random box pairs, and against a
separating plane on the mesh pairs). Should every rerun give 0 too, the distance between the `fromto` points is
returned, capped at `distmax` (0 when they are together). A negative return (the shapes overlap) is kept as it is.
"""
from __future__ import annotations

import weakref

import mujoco
import numpy as np

APART_M = 1e-6                  # m: two points of `fromto` further apart than this are no touch
NUDGE_M = (1e-9, 1e-7, 1e-5)    # m: how far the second shape is moved for the query again (tried in turn)
_SCRATCH: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _apart(ft) -> bool:
    return float(np.linalg.norm(ft[3:] - ft[:3])) > APART_M


def _in_contact(d, g1: int, g2: int) -> bool:
    n = int(d.ncon)
    if not n:
        return False
    g = d.contact.geom[:n]
    return bool(np.any(((g[:, 0] == g1) & (g[:, 1] == g2)) | ((g[:, 0] == g2) & (g[:, 1] == g1))))


def distance(m, d, g1: int, g2: int, distmax: float, fromto=None) -> float:
    """The signed distance between geoms `g1` and `g2` (at most `distmax`), as `mujoco.mj_geomDistance`, with its false
    zeros corrected. `fromto` (6 floats), when given, is filled with the nearest points as by MuJoCo."""
    g1, g2, distmax = int(g1), int(g2), float(distmax)
    ft = np.zeros(6) if fromto is None else fromto
    dist = float(mujoco.mj_geomDistance(m, d, g1, g2, distmax, ft))
    if dist != 0.0 or (not _apart(ft) and _in_contact(d, g1, g2)):
        return dist
    upper = min(float(np.linalg.norm(ft[3:] - ft[:3])), distmax)
    s = _SCRATCH.get(m)
    if s is None:
        s = _SCRATCH[m] = mujoco.MjData(m)
    ft2 = np.zeros(6)
    for eps in NUDGE_M:
        for g in (g1, g2):
            s.geom_xpos[g], s.geom_xmat[g] = d.geom_xpos[g], d.geom_xmat[g]
        s.geom_xpos[g2] = d.geom_xpos[g2] + np.array([eps, -0.7 * eps, 0.3 * eps])
        again = float(mujoco.mj_geomDistance(m, s, g1, g2, distmax, ft2))
        if again != 0.0:
            ft[:] = ft2
            return min(again, upper) if upper > 0.0 else again
    return upper
