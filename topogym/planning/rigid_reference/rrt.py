"""Deterministic, budgeted bidirectional SE(3) search using certified edges."""
import numpy as np

from .geometry import interpolate, pose_dict


def connect_search(checker, start, goal, sample, *, rng, iterations=1000, step_m=.008, progress=None,
                   metric_radius_m=None, goal_candidates=None, local_sample=None):
    """Accepted edges bound rigid surface motion; finite failure is inconclusive."""
    # The search metric may emphasize the constrained payload rather than a
    # long attached tool. Edge certificates still use checker's full radius.
    metric_radius = checker.radius if metric_radius_m is None else float(metric_radius_m)
    if not np.isfinite(metric_radius) or metric_radius <= 0.:
        raise ValueError("The search metric radius must be finite and positive")
    goals = [goal] if goal_candidates is None else list(goal_candidates)
    if not goals:
        raise ValueError("At least one goal pose is required")
    trees = [[(start, -1)], [(pose, -1) for pose in goals]]
    positions, quats = [], []
    for tree in trees:
        capacity = max(1024, len(tree))
        p, q = np.empty((capacity, 3)), np.empty((capacity, 4))
        for index, (pose, _) in enumerate(tree):
            p[index], q[index] = pose[0], pose[1].as_quat()
        positions.append(p)
        quats.append(q)
    accepted = [0, 0]
    def nearest(which, target):
        count = len(trees[which])
        angles = 2*np.arccos(np.clip(np.abs(quats[which][:count]@target[1].as_quat()), 0., 1.))
        distances = np.linalg.norm(positions[which][:count]-target[0], axis=1)+metric_radius*angles
        return int(np.argmin(distances))

    def extend(which, target):
        tree = trees[which]
        index = nearest(which, target)
        current = tree[index][0]
        distance = np.linalg.norm(current[0]-target[0])+metric_radius*(current[1].inv()*target[1]).magnitude()
        if distance < 1e-10:
            return index, True
        candidate = interpolate(current, target, min(1., step_m/distance))
        if not checker.edge(current, candidate)["passed"]:
            return None, False
        count = len(tree)
        if count == len(positions[which]):
            positions[which] = np.concatenate([positions[which], np.empty_like(positions[which])])
            quats[which] = np.concatenate([quats[which], np.empty_like(quats[which])])
        positions[which][count], quats[which][count] = candidate[0], candidate[1].as_quat()
        tree.append((candidate, index))
        accepted[which] += 1
        return len(tree)-1, distance <= step_m

    def backtrace(which, index):
        path = []
        while index >= 0:
            node, index = trees[which][index]
            path.append(node)
        return path[::-1]

    def finish(path, count, connected):
        evidence = dict(iterations=count, accepted_nodes=accepted, connected=connected)
        if goal_candidates is not None:
            # Preserve the explored configuration components for diagnostics;
            # these nodes are not an execution or a proof of impossibility.
            evidence["explored_trees"] = [[dict(pose=pose_dict(pose), parent=parent)
                                           for pose, parent in tree] for tree in trees]
        return path, evidence

    for iteration in range(iterations):
        if progress and iteration%100==0:
            progress(dict(iteration=iteration,accepted_nodes=list(accepted)))
        which = iteration % 2
        if rng.random() < .15:
            target = (goals[int(rng.integers(len(goals)))] if which == 0 and len(goals) > 1
                      else trees[1-which][0][0])
        elif local_sample is not None and rng.random() < .5:
            target = local_sample(rng, trees[which][int(rng.integers(len(trees[which])))][0])
        else:
            target = sample(rng)
        index, _ = extend(which, target)
        if index is None:
            continue
        target = trees[which][index][0]
        for _ in range(32):
            other, reached = extend(1-which, target)
            if other is None:
                break
            if reached:
                a, b = backtrace(which, index), backtrace(1-which, other)
                if which:
                    a, b = b, a
                return finish(a+b[-2::-1], iteration+1, True)
    return finish(None, iterations, False)
