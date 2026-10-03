"""Pure cloth measurements and explicit threshold predicates; no engine access."""
import numpy as np


def _projected_triangles(positions, faces):
    triangles = positions[faces, :2]
    cross = ((triangles[:, 1, 0]-triangles[:, 0, 0])*(triangles[:, 2, 1]-triangles[:, 0, 1])
             -(triangles[:, 1, 1]-triangles[:, 0, 1])*(triangles[:, 2, 0]-triangles[:, 0, 0]))
    return triangles[np.abs(cross) > 1e-12]


def _triangle_polygons(triangles):
    """shapely.polygons(triangles) in one call (rings closed by their first vertex): the same geometries."""
    import shapely
    count = len(triangles)
    coords = np.empty((count, 4, 2), dtype=np.float64)
    coords[:, :3], coords[:, 3] = triangles, triangles[:, 0]
    offsets = (np.arange(0, 4*count+1, 4, dtype=np.int64), np.arange(0, count+1, dtype=np.int64))
    return shapely.from_ragged_array(shapely.GeometryType.POLYGON, coords.reshape(-1, 2), offsets)


def _union_area(polygons):
    import shapely
    try:
        return float(shapely.area(shapely.union_all(polygons)))
    except shapely.errors.GEOSException:
        # Near-vertical touching triangles occasionally produce non-noded
        # linework. Use a 10 nm precision grid only for this numerical fallback;
        # applying it to every frame is substantially more expensive.
        return float(shapely.area(shapely.union_all(polygons, grid_size=1e-8)))


def footprint_area(positions, faces):
    """Union of projected simulation triangles: folds and holes count correctly."""
    triangles = _projected_triangles(positions, faces)
    if not len(triangles):
        return 0.
    return _union_area(_triangle_polygons(triangles))


_SLAB_POOLS = {}


def footprint_area_slabs(positions, faces, *, slabs=8, threads=4):
    """footprint_area as a sum over vertical slabs, each slab's union on a thread (GEOS releases the GIL): ~3x faster on
    the 8181-particle blanket. The same area mathematically; numerically within ~1e-15 on cloth states (another noding
    order), but GEOS' one-shot union can itself drift on extreme folds (~3e-4 of the area), so a decision at a threshold
    must recompute footprint_area when this value is near it (blanket_flatten: within 1e-3)."""
    import shapely
    from concurrent.futures import ThreadPoolExecutor
    triangles = _projected_triangles(positions, faces)
    if not len(triangles):
        return 0.
    polygons = _triangle_polygons(triangles)
    xmin, xmax = triangles[:, :, 0].min(axis=1), triangles[:, :, 0].max(axis=1)
    cuts = np.quantile((xmin+xmax)/2, np.linspace(0, 1, slabs+1))
    cuts[0], cuts[-1] = xmin.min()-1., xmax.max()+1.
    ylo, yhi = triangles[:, :, 1].min()-1., triangles[:, :, 1].max()+1.

    def slab(k):
        a, b = cuts[k], cuts[k+1]
        chosen = np.flatnonzero((xmax > a) & (xmin < b))
        if not len(chosen):
            return 0.
        geometries = polygons[chosen]
        spanning = ~((xmin[chosen] >= a) & (xmax[chosen] <= b))
        if spanning.any():
            geometries = geometries.copy()
            geometries[spanning] = shapely.clip_by_rect(geometries[spanning], a, ylo, b, yhi)
        return float(shapely.area(shapely.union_all(geometries)))
    pool = _SLAB_POOLS.get(threads) or _SLAB_POOLS.setdefault(threads, ThreadPoolExecutor(threads))
    try:
        return float(sum(pool.map(slab, range(slabs))))
    except shapely.errors.GEOSException:
        return _union_area(polygons)


def measure(positions, velocities, faces, edges, rest_lengths, *, table_z, table_bounds,
            material_area, visual_positions=None, visual_edges=None, visual_rest_lengths=None):
    positions, velocities = np.asarray(positions), np.asarray(velocities)
    if not np.isfinite(positions).all() or not np.isfinite(velocities).all():
        return dict(finite=False)
    z = positions[:, 2]-table_z
    strain = np.linalg.norm(positions[edges[:, 1]]-positions[edges[:, 0]], axis=1)/rest_lengths
    speeds = np.linalg.norm(velocities, axis=1)
    outside = np.any((positions[:, :2] < table_bounds[0]) | (positions[:, :2] > table_bounds[1]), axis=1)
    result = dict(finite=True, particles=len(positions), coverage_ratio=footprint_area(positions, faces)/material_area,
                  coverage_fallback_precision_grid_m=1e-8,
                  minimum_height_m=float(z.min()), maximum_height_m=float(z.max()),
                  p95_height_m=float(np.quantile(z, .95)), maximum_speed_m_s=float(speeds.max()),
                  p99_speed_m_s=float(np.quantile(speeds, .99)),
                  mean_speed_m_s=float(speeds.mean()), outside_table_particles=int(outside.sum()),
                  maximum_edge_stretch=float(strain.max()), minimum_edge_stretch=float(strain.min()))
    if visual_positions is not None:
        visual_lengths = np.linalg.norm(visual_positions[visual_edges[:, 1]]-visual_positions[visual_edges[:, 0]], axis=1)
        result["maximum_visual_edge_stretch"] = float(np.max(visual_lengths/visual_rest_lengths))
    return result


def health_gates(metrics, limits):
    if not metrics.get("finite", False):
        return {"finite": False}
    return dict(finite=True, all_on_table=metrics["outside_table_particles"] == 0,
                no_table_penetration=metrics["minimum_height_m"] >= -limits["penetration_tolerance_m"],
                material_intact=metrics["maximum_edge_stretch"] <= limits["maximum_edge_stretch"],
                visual_intact=metrics.get("maximum_visual_edge_stretch", float("inf")) <= limits["maximum_visual_edge_stretch"])


def settled(metrics, limits):
    return bool(metrics.get("finite", False) and metrics["mean_speed_m_s"] <= limits["mean_speed_m_s"]
                and metrics["p99_speed_m_s"] <= limits["p99_speed_m_s"]
                and metrics["maximum_speed_m_s"] <= limits["maximum_speed_m_s"])


def initial_gates(metrics, limits):
    gates = health_gates(metrics, limits)
    if metrics.get("finite", False):
        gates.update(settled=settled(metrics, limits),
                     crumpled=limits["minimum_coverage_ratio"] <= metrics["coverage_ratio"] <= limits["maximum_coverage_ratio"],
                     landed=metrics["maximum_height_m"] <= limits["maximum_height_m"])
    return gates


def flatten_gates(metrics, limits, *, released):
    """Call over a sustained released window, not while corners are held taut."""
    gates = health_gates(metrics, limits)
    if metrics.get("finite", False):
        gates.update(released=bool(released), settled=settled(metrics, limits),
                     covered=metrics["coverage_ratio"] >= limits["minimum_coverage_ratio"],
                     flat=metrics["p95_height_m"] <= limits["p95_height_m"],
                     no_raised_corner=metrics["maximum_height_m"] <= limits["maximum_height_m"])
    return gates


class AcceptanceWindow:
    """Require all gates plus bounded movement throughout a sampled time window."""

    def __init__(self, seconds, maximum_drift_m):
        if not np.isfinite([seconds, maximum_drift_m]).all() or min(seconds, maximum_drift_m) <= 0:
            raise ValueError("Acceptance window and drift limit must be positive and finite")
        self.seconds, self.maximum_drift_m = seconds, maximum_drift_m
        self.start = self.origin = self.previous_time = None
        self.duration = self.drift_m = 0.

    def update(self, now, positions, gates):
        if not np.isfinite(now) or (self.previous_time is not None and now <= self.previous_time):
            raise ValueError("Acceptance observations must have strictly increasing finite times")
        self.previous_time = now
        positions = np.asarray(positions)
        if not gates or not all(gates.values()) or not np.isfinite(positions).all():
            self.start = self.origin = None
            self.duration = self.drift_m = 0.
            return False
        if self.start is not None:
            self.drift_m = max(self.drift_m, float(np.linalg.norm(positions-self.origin, axis=1).max()))
        if self.start is None or self.drift_m > self.maximum_drift_m:
            self.start, self.origin = now, positions.copy()
            self.drift_m = 0.
        self.duration = now-self.start
        return self.duration+1e-9 >= self.seconds
