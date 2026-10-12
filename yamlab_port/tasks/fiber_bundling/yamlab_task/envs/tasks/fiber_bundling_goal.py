"""Pure-numpy goal check of the fiber_bundling task (old terminal_v4_fiber_ring_plane).

Copied with minimal changes from the old RoboTangle sources (robot_coding_bench dev/jianwen @ 2dafa5f2b):
  - passage_initial / advance_passage: topogym/utils/geometry/passage.py (verbatim logic)
  - FiberGoal.evaluate: topogym/tasks/fiber_bundling/common.py FiberBundlingTask.evaluate_transition
The simulator-specific parts (link poses, contact evidence) are passed in as arrays.
"""
import numpy as np


def points3(points):
    p = np.asarray(points, float)
    if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all():
        raise ValueError("Expected finite (n, 3) points")
    return p


def passage_initial(points):
    """Stations must be tip-to-root; an already-passed birth gets no credit."""
    p = points3(points)
    return dict(previous=p.copy(), stages=np.zeros(len(p), dtype=np.int64))


def advance_passage(points, history, center, normal, radius, half_thickness):
    """Track entrance then exit, enforcing tip-to-root order at each boundary (old passage.py)."""
    p, old = points3(points), points3(history["previous"])
    stages = np.asarray(history["stages"]).copy()
    if p.shape != old.shape or stages.shape != (len(p),):
        raise ValueError("Invalid passage history")
    c, n = np.asarray(center, float), np.asarray(normal, float)
    n = n/np.linalg.norm(n)
    before, after = (old-c)@n, (p-c)@n
    events = []
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
    events.sort(key=lambda e: (e[0], e[1] if e[3] > 0 else -e[1], e[2] if e[3] > 0 else -e[2]))
    for _, i, boundary, direction, in_hole in events:
        if direction < 0:
            stages[i:] = np.minimum(stages[i:], boundary)
        elif not in_hole or stages[i] != boundary or (i and stages[i-1] < boundary+1):
            stages[i:] = 0
            ordered = False
        else:
            stages[i] = boundary+1
    stages[after <= -half_thickness] = 0
    complete = bool(np.all(stages == 2) and np.all(after > half_thickness))
    return complete, dict(previous=p.copy(), stages=stages), dict(ordered_this_tick=ordered, crossing_events=len(events))


def quat_wxyz_to_mat(q):
    q = np.asarray(q, float)
    q = q/np.linalg.norm(q, axis=-1, keepdims=True)
    w, x, y, z = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    R = np.empty(q.shape[:-1]+(3, 3))
    R[..., 0, 0] = 1-2*(y*y+z*z); R[..., 0, 1] = 2*(x*y-w*z); R[..., 0, 2] = 2*(x*z+w*y)
    R[..., 1, 0] = 2*(x*y+w*z); R[..., 1, 1] = 1-2*(x*x+z*z); R[..., 1, 2] = 2*(y*z-w*x)
    R[..., 2, 0] = 2*(x*z-w*y); R[..., 2, 1] = 2*(y*z+w*x); R[..., 2, 2] = 1-2*(x*x+y*y)
    return R


class FiberGoal:
    """Per-environment goal state + evaluation, fed with world link poses."""

    def __init__(self, layout, success_cfg):
        ring = layout["ring"]
        self.center = np.asarray(ring["center"], float)
        self.normal = np.asarray(ring["normal"], float)/np.linalg.norm(ring["normal"])
        self.tube_r = float(ring["tube_radius"])
        # passage radius: actual polygonal aperture + tube radius = tube centreline (old)
        self.radius = float(ring["min_aperture_radius"])+self.tube_r
        self.fiber_r = float(layout["fibers"]["radius"])
        self.trunk_r = float(layout["trunk"]["radius"])
        self.fiber_names = layout["fibers"]["names"]
        self.seg_len = {n: float(layout["links"][n]["length"]) for names in self.fiber_names for n in names}
        self.front_name = layout["trunk"]["names"][-1]
        self.front_len = float(layout["links"][self.front_name]["length"])
        self.max_bend = float(success_cfg["maximum_bend_deg"])
        self.half_thickness = float(success_cfg["ring_plane_half_thickness_m"])
        self.table_z = float(layout["table_z"])
        self.below = float(success_cfg["below_table_margin_m"])
        self.history = None
        self.start_pose = {n: (np.asarray(v["origin"], float), np.asarray(v["R"], float)) for n, v in layout["links"].items()}

    def strand_paths(self, pose):
        """pose: dict name -> (pos(3), R(3,3)). Returns tip-first station arrays (old _strand_points)."""
        paths = []
        for names in self.fiber_names:
            pts = [pose[n][0] for n in names]
            last = names[-1]
            pts.append(pose[last][0]+pose[last][1][:, 0]*self.seg_len[last])
            paths.append(np.array(pts)[::-1].copy())
        return paths

    def front_point(self, pose):
        p, R = pose[self.front_name]
        return p+R[:, 0]*self.front_len

    def reset(self, pose):
        self.history = dict(strands=[passage_initial(p) for p in self.strand_paths(pose)],
                            front=passage_initial([self.front_point(pose)]))

    def evaluate(self, pose, all_link_z):
        """Advance the passage history by one evaluation and return (reached, failure, metrics)."""
        if not np.isfinite(all_link_z).all() or any(not np.isfinite(v[0]).all() for v in pose.values()):
            return False, "non_finite_cable_state", {}
        if float(np.min(all_link_z)) < self.table_z-self.below:
            return False, "fiber_below_table", {}
        if self.history is None:
            self.reset(pose)
        paths = self.strand_paths(pose)
        c, n = self.center, self.normal
        half = self.tube_r+self.fiber_r
        completed, new_strands, bends, stages, min_exit = [], [], [], [], []
        for path, old in zip(paths, self.history["strands"]):
            done, new, _ = advance_passage(path, old, c, n, self.radius, self.half_thickness)
            ahead = (path-c) @ n
            completed.append(bool(done and np.all(ahead > half)))
            new_strands.append(new)
            stages.append(new["stages"].tolist())
            min_exit.append(float(ahead.min()))
            t = np.diff(path, axis=0)
            L = np.linalg.norm(t, axis=1)
            if np.any(L < 1e-10):
                return False, "degenerate_fiber_segment", {}
            t /= L[:, None]
            bends.extend(np.degrees(np.arccos(np.clip(np.sum(t[:-1]*t[1:], axis=1), -1, 1))))
        maximum = float(max(bends, default=0.))
        front = self.front_point(pose)
        front_ahead = float(np.dot(front-c, n))
        front_clear = front_ahead-self.trunk_r > self.tube_r
        front_passed, front_hist, _ = advance_passage([front], self.history["front"], c, n, self.radius, self.half_thickness)
        self.history = dict(strands=new_strands, front=front_hist)
        reached = bool(all(completed) and front_passed and front_clear and maximum <= self.max_bend)
        # diagnostics: radial distance of every strand station from the ring axis
        radial = [float(np.max(np.linalg.norm((p-c)-np.outer((p-c) @ n, n), axis=1))) for p in paths]
        fr = front-c
        metrics = dict(strands_complete=completed, maximum_bend_deg=maximum, front_sheath_clear=bool(front_clear),
                       front_passed=bool(front_passed), front_ahead_of_ring_m=front_ahead,
                       front_radial_offset_m=float(np.linalg.norm(fr-np.dot(fr, n)*n)),
                       strand_stages=stages, strand_min_ahead_m=min_exit, strand_max_radial_m=radial)
        return reached, None, metrics
