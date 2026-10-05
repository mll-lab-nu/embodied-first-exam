"""Finite aperture crossings and reversible material-station passage history."""
import numpy as np
from .regions import points3


def aperture_crossings(points, center, normal, radius, *, tolerance=1e-9):
    """Open polyline hits, with no artificial closure or signed cancellation.

    Tangencies/coplanar runs touching the aperture are reported as ambiguous.
    Radius is the usable aperture after tube/rope/clearance margins.
    """
    p = points3(points)
    c = np.asarray(center, float)
    n = np.asarray(normal, float)
    if len(p) < 2 or c.shape != (3,) or n.shape != (3,) or not np.isfinite(np.r_[c, n, radius, tolerance]).all():
        raise ValueError("Invalid aperture")
    if radius <= 0 or tolerance <= 0 or np.linalg.norm(n) <= 1e-12:
        raise ValueError("Invalid aperture dimensions")
    n = n / np.linalg.norm(n)
    d = (p-c) @ n
    away = np.flatnonzero(abs(d) > tolerance)
    hits, ambiguous = [], False
    for i in np.flatnonzero(abs(d) <= tolerance):
        if np.linalg.norm(p[i]-c) <= radius+tolerance:
            if i == 0 or i == len(p)-1 or d[i-1]*d[i+1] >= 0 or abs(d[i-1]) <= tolerance or abs(d[i+1]) <= tolerance:
                ambiguous = True
    # Coplanar segments can span the disk even when both vertices are outside it.
    for i in range(len(p)-1):
        if abs(d[i]) <= tolerance and abs(d[i+1]) <= tolerance:
            edge = p[i+1]-p[i]
            t = np.clip(np.dot(c-p[i], edge)/max(np.dot(edge, edge), 1e-30), 0, 1)
            ambiguous |= bool(np.linalg.norm(p[i]+t*edge-c) <= radius+tolerance)
    for left, right in zip(away[:-1], away[1:]):
        if d[left]*d[right] >= 0 or right-left > 2:
            continue
        t = -d[left]/(d[left+1]-d[left])
        point = p[left]+t*(p[left+1]-p[left])
        distance = np.linalg.norm(point-c)
        if abs(distance-radius) <= tolerance:
            ambiguous = True
        if distance < radius-tolerance:
            hits.append(dict(material_coordinate=float(left+t), sign=1 if d[right] > 0 else -1,
                             point_m=point.tolist()))
    return hits, bool(ambiguous)


def passage_initial(points):
    """Stations must be tip-to-root; an already-passed birth gets no credit."""
    p = points3(points)
    return dict(previous=p.copy(), stages=np.zeros(len(p), dtype=np.int64))


def advance_passage(points, history, center, normal, radius, half_thickness):
    """Track entrance then exit, enforcing tip-to-root order at each boundary.

    Crossing times are linear interpolation within one physics tick. Missing
    intermediate motion cannot be certified by this sampled-state contract.
    """
    p, old = points3(points), points3(history["previous"])
    stages = np.asarray(history["stages"]).copy()
    if p.shape != old.shape or stages.shape != (len(p),) or stages.dtype.kind not in "iu" or np.any((stages < 0) | (stages > 2)):
        raise ValueError("Invalid passage history")
    c, n = np.asarray(center, float), np.asarray(normal, float)
    if c.shape != (3,) or n.shape != (3,) or not np.isfinite(np.r_[c, n, radius, half_thickness]).all() or np.linalg.norm(n) < 1e-12 or radius <= 0 or half_thickness <= 0:
        raise ValueError("Invalid passage aperture")
    n = n/np.linalg.norm(n)
    before, after = (old-c)@n, (p-c)@n
    events = []
    # The per-station loop below only records crossings; most ticks have none, which the same comparisons on whole
    # arrays show at once (identical results: scripts/check_fiber_fast_paths.py).
    crossed = any(np.any(((before-plane) <= 0) & (0 < (after-plane))) or np.any(((after-plane) <= 0) & (0 < (before-plane)))
                  for plane in (-half_thickness, half_thickness))
    for station in range(len(p) if crossed else 0):
        for boundary, plane in enumerate((-half_thickness, half_thickness)):
            a, b = before[station]-plane, after[station]-plane
            direction = 1 if a <= 0 < b else -1 if b <= 0 < a else 0
            if direction:
                t = -a/(b-a)
                x = old[station]+t*(p[station]-old[station])-c
                in_hole = np.linalg.norm(x-n*np.dot(x, n)) < radius
                events.append((float(t), station, boundary, direction, bool(in_hole)))
    ordered = True
    # Simultaneous crossings are processed tip first forward, root first backward.
    events.sort(key=lambda e: (e[0], e[1] if e[3] > 0 else -e[1], e[2] if e[3] > 0 else -e[2]))
    for _, i, boundary, direction, in_hole in events:
        if direction < 0:
            stages[i:] = np.minimum(stages[i:], boundary)
        elif not in_hole or stages[i] != boundary or (i and stages[i-1] < boundary+1):
            stages[i:] = 0
            ordered = False
        else:
            stages[i] = boundary+1
    # Prevent a prior completion surviving a retreat; crossing credit is historical.
    stages[after <= -half_thickness] = 0
    complete = bool(np.all(stages == 2) and np.all(after > half_thickness))
    return complete, dict(previous=p.copy(), stages=stages), dict(ordered_this_tick=ordered, crossing_events=len(events))


def segment_distance_2d(a, b, c, d):
    a, b, c, d = (np.asarray(x, float) for x in (a, b, c, d))
    def cross(u, v):
        return u[0]*v[1]-u[1]*v[0]
    u, v = b-a, d-c
    den = cross(u, v)
    if abs(den) > 1e-15:
        t, s = cross(c-a, v)/den, cross(c-a, u)/den
        if 0 <= t <= 1 and 0 <= s <= 1:
            return 0.
    def point_segment(p, x, y):
        edge = y-x
        t = np.clip(np.dot(p-x, edge)/max(np.dot(edge, edge), 1e-30), 0, 1)
        return np.linalg.norm(p-(x+t*edge))
    return float(min(point_segment(a,c,d), point_segment(b,c,d), point_segment(c,a,b), point_segment(d,a,b)))


def planar_clearance(points, material_s, diameter):
    p = points3(points)
    s = np.asarray(material_s, float)
    if len(p) < 2 or s.shape != (len(p),) or not np.isfinite(s).all() or np.any(np.diff(s) <= 0) or not np.isfinite(diameter) or diameter <= 0:
        raise ValueError("Invalid planar rope/material coordinates")
    if np.any(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1) < 1e-9):
        return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=None)
    edges = np.diff(p[:, :2], axis=0)
    for a, b in zip(edges[:-1], edges[1:]):
        cross = a[0]*b[1]-a[1]*b[0]
        if abs(cross) <= 1e-12*np.linalg.norm(a)*np.linalg.norm(b) and np.dot(a,b) < 0:
            return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=0.)
    minimum = None
    for i in range(len(p)-1):
        for j in range(i+2, len(p)-1):
            distance = segment_distance_2d(*p[i:i+2, :2], *p[j:j+2, :2])
            # Local material neighbours may lie closer than the tube diameter;
            # actual intersections are never excused by material adjacency.
            if distance < 1e-10:
                return False, dict(projected_degenerate=False, minimum_nonlocal_distance_m=0.)
            if s[j]-s[i+1] < 2*diameter:
                continue
            minimum = distance if minimum is None else min(minimum, distance)
    return minimum is None or minimum >= diameter, dict(projected_degenerate=False, minimum_nonlocal_distance_m=minimum)
