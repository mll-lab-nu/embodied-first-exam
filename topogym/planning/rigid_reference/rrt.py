"""Deterministic, budgeted bidirectional SE(3) search using certified edges."""
import numpy as np

from .geometry import interpolate


def connect_search(checker, start, goal, sample, *, rng, iterations=1000, step_m=.008):
    """Accepted edges bound rigid surface motion; finite failure is inconclusive."""
    trees = [[(start, -1)], [(goal, -1)]]
    accepted = [0, 0]
    def nearest(tree, target):
        positions = np.array([node[0][0] for node in tree])
        quats = np.array([node[0][1].as_quat() for node in tree])
        angles = 2*np.arccos(np.clip(np.abs(quats@target[1].as_quat()), 0., 1.))
        distances = np.linalg.norm(positions-target[0], axis=1)+checker.radius*angles
        return int(np.argmin(distances))

    def extend(which, target):
        tree = trees[which]
        index = nearest(tree, target)
        current = tree[index][0]
        distance = np.linalg.norm(current[0]-target[0])+checker.radius*(current[1].inv()*target[1]).magnitude()
        if distance < 1e-10:
            return index, True
        candidate = interpolate(current, target, min(1., step_m/distance))
        if not checker.edge(current, candidate)["passed"]:
            return None, False
        tree.append((candidate, index))
        accepted[which] += 1
        return len(tree)-1, distance <= step_m

    def backtrace(which, index):
        path = []
        while index >= 0:
            node, index = trees[which][index]
            path.append(node)
        return path[::-1]

    for iteration in range(iterations):
        which = iteration % 2
        target = trees[1-which][0][0] if rng.random() < .15 else sample(rng)
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
                return a+b[-2::-1], dict(iterations=iteration+1, accepted_nodes=accepted, connected=True)
    return None, dict(iterations=iterations, accepted_nodes=accepted, connected=False)
