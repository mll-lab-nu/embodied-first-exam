#!/usr/bin/env python3
"""Check fiber_bundling's per-tick fast paths (image 0.2.15-dev) against the code they replaced (dev/jianwen 51156f3f6).

    python scripts/check_fiber_fast_paths.py [--trials 3000] [--seed 0]
    python scripts/check_fiber_fast_paths.py --instance <instance.json> --trajectory <trajectory.npz> [--rows 2000]

1. topogym.evaluation.task_metrics.body_points_batch vs body_points per body: bit-identical points on random poses for
   vertices with at most one nonzero coordinate (the batched path), and for general vertices (the per-body path); the
   same exception type and message for invalid poses.
2. FiberBundlingTask._strand_points (one batched rotation) vs the per-link loop it replaced: bit-identical strands.
3. topogym.utils.geometry.passage.advance_passage (the per-station loop skipped when no station crossed a boundary plane)
   vs the previous function: identical results (array bytes) on random station histories, with and without crossings.
With --instance / --trajectory, 2 and 3 also run at every physics tick of a recorded fiber trajectory replayed in one
Session (inside the TopoGym image with the task tooling importable). Exit 1 on any difference."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.evaluation.task_metrics import body_points, body_points_batch  # noqa: E402
from topogym.utils.geometry import passage  # noqa: E402
from topogym.utils.geometry.regions import points3  # noqa: E402


def reference_strand_points(layout, state):
    """FiberBundlingTask._strand_points before the batched rotation."""
    links = state["articulations"]["fiber_bundle"]["links"]
    length = layout.fiber_length_m/layout.fiber_segments
    paths = []
    for strand in range(layout.fiber_count):
        segments = [body_points(links[f"fiber_{strand:02d}_{segment:02d}"], [[0, 0, 0], [length, 0, 0]])
                    for segment in range(layout.fiber_segments)]
        paths.append(np.vstack([s[0] for s in segments]+[segments[-1][1]])[::-1].copy())
    return paths


def reference_advance_passage(points, history, center, normal, radius, half_thickness):
    """topogym.utils.geometry.passage.advance_passage before the crossing pre-check."""
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
    for station in range(len(p)):
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


def canon(value):
    """Bit-level canonical form of nested results (floats and arrays by their bytes)."""
    if isinstance(value, dict):
        return tuple(sorted((k, canon(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(canon(v) for v in value)
    if isinstance(value, np.ndarray):
        return (value.dtype.str, value.shape, value.tobytes())
    if isinstance(value, (float, np.floating)):
        return ("f", np.float64(value).tobytes())
    return value


def outcome(fn, *args):
    try:
        return ("ok", canon(fn(*args)))
    except Exception as error:  # noqa: BLE001 - the exception itself is compared
        return ("error", type(error).__name__, str(error))


def random_quaternion(rng):
    kind = rng.integers(5)
    if kind == 0:
        return rng.normal(size=4)                              # unnormalised
    if kind == 1:
        q = rng.normal(size=4)
        return q/np.linalg.norm(q)
    if kind == 2:
        return np.array([1.0, 0, 0, 0]) + rng.normal(scale=1e-9, size=4)   # near identity
    if kind == 3:
        return np.array([0.0, *rng.normal(size=3)])           # 180 degrees
    return -np.abs(rng.normal(size=4))                         # negative scalar part


def random_vertices(rng, general):
    rows = []
    for _ in range(rng.integers(1, 4)):
        v = np.zeros(3)
        if general:
            v = rng.normal(size=3)*10.0**rng.integers(-3, 1)
        elif rng.random() < .8:
            v[rng.integers(3)] = rng.normal()*10.0**rng.integers(-3, 1)
        rows.append(v)
    return np.array(rows)


def check_body_points(rng, trials):
    bad = 0
    for trial in range(trials):
        n = int(rng.integers(1, 40))
        bodies = [dict(position_m=rng.normal(size=3), quaternion_wxyz=random_quaternion(rng)) for _ in range(n)]
        if trial % 10 == 9:                                    # an invalid pose somewhere
            k, kind = int(rng.integers(n)), int(rng.integers(4))
            if kind == 0:
                bodies[k]["position_m"] = np.array([np.nan, 0, 0])
            elif kind == 1:
                bodies[k]["quaternion_wxyz"] = np.zeros(4)
            elif kind == 2:
                bodies[k]["position_m"] = np.zeros(2)
            else:
                bodies[k]["quaternion_wxyz"] = np.array([np.inf, 0, 0, 0])
        vertices = random_vertices(rng, general=trial % 4 == 3)
        ref = outcome(lambda: np.array([body_points(b, vertices) for b in bodies]).reshape(n, len(vertices), 3))
        new = outcome(body_points_batch, bodies, vertices)
        bad += int(ref != new)
    return bad


class Layout:
    def __init__(self, count, segments, length):
        self.fiber_count, self.fiber_segments, self.fiber_length_m = count, segments, length


def check_strands(rng, trials):
    from topogym.tasks.fiber_bundling.common import FiberBundlingTask
    bad = 0
    for _ in range(trials):
        layout = Layout(int(rng.integers(1, 17)), int(rng.integers(1, 11)), float(rng.uniform(.05, .3)))
        links = {f"fiber_{i:02d}_{j:02d}": dict(position_m=rng.normal(size=3)*.2, quaternion_wxyz=random_quaternion(rng))
                 for i in range(layout.fiber_count) for j in range(layout.fiber_segments)}
        state = dict(articulations=dict(fiber_bundle=dict(links=links)))
        task = type("T", (), {})()
        task.layout = layout
        bad += int(outcome(reference_strand_points, layout, state) != outcome(FiberBundlingTask._strand_points, task, state))
    return bad


def random_passage_case(rng):
    m = int(rng.integers(1, 12))
    half = float(rng.uniform(.002, .02))
    center, normal = rng.normal(size=3)*.1, rng.normal(size=3)
    unit = normal/np.linalg.norm(normal)
    old = center + rng.normal(size=(m, 3))*.03
    # move a few stations across the boundary planes (or onto them) in some cases
    new = old + rng.normal(size=(m, 3))*10.0**rng.integers(-5, -1)
    if rng.random() < .5:
        k = rng.integers(m)
        plane = half if rng.random() < .5 else -half
        new[k] = center + unit*(plane + rng.choice([-1, 0, 1])*rng.uniform(0, .003)) + rng.normal(size=3)*.001
        if rng.random() < .3:
            old[k] = center + unit*plane                       # exactly on the plane
    stages = rng.integers(0, 3, size=m).astype(np.int64)
    radius = float(rng.uniform(.005, .05))
    return new, dict(previous=old, stages=stages), center, normal, radius, half


def check_passage(rng, trials):
    bad = crossings = 0
    for _ in range(trials):
        args = random_passage_case(rng)
        ref = outcome(reference_advance_passage, *args)
        new = outcome(passage.advance_passage, *args)
        crossings += int(ref[0] == "ok" and dict(ref[1][2])["crossing_events"] > 0)
        bad += int(ref != new)
    return bad, crossings


def check_replay(instance, trajectory, rows):
    """At every physics tick of a recorded trajectory: the task's strands and every advance_passage call, new vs old."""
    import shutil
    import tempfile
    src = Path(instance).parent
    inst = json.loads(Path(instance).read_text())
    inst["simulator"] = {**inst["simulator"], "enable_rgb": False, "enable_depth": False}
    work = Path(tempfile.mkdtemp(prefix="cffp_"))
    for item in src.iterdir():
        if item.name not in ("instance.json", "runtime_binding.json"):
            (shutil.copytree if item.is_dir() else shutil.copy2)(item, work / item.name)
    (work / "instance.json").write_text(json.dumps(inst))
    sys.path.insert(0, str(work))                              # the instance's task tooling (rcb_topogym.py)
    from rcb_topogym import Session
    import topogym.tasks.fiber_bundling.common as fiber
    session = Session(inst["task"], instance=str(work / "instance.json"), strict=False)
    task = session.env._task
    counts = dict(strands=0, strand_mismatch=0, passage=0, passage_mismatch=0, crossing_ticks=0)
    original_strands = type(task)._strand_points
    original_advance = fiber.advance_passage

    def strands(self, state):
        new = original_strands(self, state)
        counts["strands"] += 1
        counts["strand_mismatch"] += int(canon(new) != canon(reference_strand_points(self.layout, state)))
        return new

    def advance(*args):
        new = original_advance(*args)
        ref = reference_advance_passage(*args)
        counts["passage"] += 1
        counts["passage_mismatch"] += int(canon(new) != canon(ref))
        counts["crossing_ticks"] += int(ref[2]["crossing_events"] > 0)
        return new

    type(task)._strand_points = strands
    fiber.advance_passage = advance
    data = np.load(trajectory)
    actions = data["actions"][:rows]
    ticks = data["physics_steps_per_action"] if "physics_steps_per_action" in data.files else None
    for i, action in enumerate(actions):
        if session.step(action, _physics_steps=None if ticks is None else int(ticks[i])):
            break
    shutil.rmtree(work, ignore_errors=True)
    return dict(counts, rows=session.n_steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trials", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--instance")
    parser.add_argument("--trajectory")
    parser.add_argument("--rows", type=int, default=2000)
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)
    report = dict(body_points_mismatch=check_body_points(rng, args.trials),
                  strand_mismatch=check_strands(rng, max(1, args.trials//10)))
    report["passage_mismatch"], report["passage_cases_with_crossings"] = check_passage(rng, args.trials)
    if args.instance and args.trajectory:
        report["replay"] = check_replay(args.instance, args.trajectory, args.rows)
    failed = (report["body_points_mismatch"] or report["strand_mismatch"] or report["passage_mismatch"]
              or report.get("replay", {}).get("strand_mismatch") or report.get("replay", {}).get("passage_mismatch"))
    print(json.dumps(dict(report, passed=not failed), indent=1))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
