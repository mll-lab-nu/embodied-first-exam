"""Photo-inspired continuous track: horizontal folds, vertical folds, spiral.

Nominal coordinates use a 45 mm base. These are authored dimensions, not
measurements inferred from the reference photo. All junctions share endpoints.
"""

import numpy as np


def reference_maze_controls(valley_lift=0.0, robot_friendly=False):
    p = []
    stages = {}

    def add(v):
        for q in v:
            if not p or np.linalg.norm(np.asarray(q) - p[-1]) > 1e-8:
                p.append(np.asarray(q, dtype=float))

    def line(q):
        if not p:
            add([q])
            return
        add(
            np.linspace(
                p[-1], q, max(2, int(np.linalg.norm(np.asarray(q) - p[-1]) / 0.025) + 1)
            )
        )

    def arc(c, u, v, r, a, b, n=16):
        ts = np.linspace(a, b, n)
        add(
            [
                np.asarray(c)
                + r * (np.cos(t) * np.asarray(u) + np.sin(t) * np.asarray(v))
                for t in ts
            ]
        )

    line([-0.49, -0.28, 0.055])
    line([-0.49, -0.28, 0.46])
    arc([-0.49, -0.215, 0.46], [0, -1, 0], [0, 0, 1], 0.065, 0, np.pi / 2)
    line([-0.49, 0.20, 0.525])
    arc([-0.43, 0.20, 0.525], [1, 0, 0], [0, 1, 0], 0.06, np.pi, 0)
    line([-0.37, -0.20, 0.525])
    arc([-0.31, -0.20, 0.525], [1, 0, 0], [0, 1, 0], 0.06, np.pi, 2 * np.pi)
    line([-0.25, 0.20, 0.525])
    arc([-0.19, 0.20, 0.525], [1, 0, 0], [0, 1, 0], 0.06, np.pi, 0)
    line([-0.13, -0.12, 0.525])
    stages["horizontal_switchbacks"] = len(p) - 1
    if robot_friendly:
        spiral_shift = 0.0
        # An inclined vertical fold retains the down/up height reversal and
        # fore/aft travel for a finite robot wrist at the bottoms of the folds.
        arc([-0.065, -0.12, 0.525], [1, 0, 0], [0, 1, 0], 0.065, np.pi, 1.5 * np.pi)
        u = np.linspace(0, 1, 101)
        blend = u * u * (3 - 2 * u)
        add(
            np.c_[
                -0.065 + 0.155 * u,
                -0.185 + (0.165 + spiral_shift) * blend,
                0.525 + 0.020 * blend - 0.12 * np.sin(np.pi * u) ** 2,
            ]
        )
        stages["vertical_switchbacks"] = len(p) - 1
        arc(
            [0.09, 0.045 + spiral_shift, 0.545],
            [0, -1, 0],
            [1, 0, 0],
            0.065,
            0,
            np.pi / 2,
        )
    else:
        spiral_shift = 0.0
        _vertical_controls(add, line, arc, stages, p, valley_lift)
    turns = 1.0 if robot_friendly else 1.35
    theta = np.linspace(np.pi, np.pi - 2 * np.pi * turns, 101)
    radius = np.linspace(0.185, 0.065, len(theta))
    xyz = np.c_[
        0.34 + radius * np.cos(theta),
        0.045 + spiral_shift + radius * np.sin(theta),
        np.linspace(0.545, 0.58, len(theta)),
    ]
    add(xyz)
    end = xyz[-1]
    t = xyz[-1] - xyz[-2]
    t[2] = 0
    t /= np.linalg.norm(t)
    # Quarter-turn the end into a downward support, keeping it below the spiral.
    arc(end + [0, 0, -0.055], [0, 0, 1], t, 0.055, 0, np.pi / 2)
    line([*p[-1][:2], 0.055])
    stages["spiral"] = len(p) - 1
    return np.array(p), stages


def _vertical_controls(add, line, arc, stages, p, valley_lift):
    arc([-0.13, -0.12, 0.46], [0, 0, 1], [0, -1, 0], 0.065, 0, np.pi / 2)
    line([-0.13, -0.185, 0.16 + valley_lift])
    arc(
        [-0.0825, -0.185, 0.16 + valley_lift],
        [1, 0, 0],
        [0, 0, 1],
        0.0475,
        np.pi,
        2 * np.pi,
    )
    line([-0.035, -0.185, 0.42])
    arc([0.0125, -0.185, 0.42], [1, 0, 0], [0, 0, 1], 0.0475, np.pi, 0)
    line([0.06, -0.185, 0.19 + valley_lift])
    arc(
        [0.1075, -0.185, 0.19 + valley_lift],
        [1, 0, 0],
        [0, 0, 1],
        0.0475,
        np.pi,
        2 * np.pi,
    )
    line([0.155, -0.185, 0.48])
    stages["vertical_switchbacks"] = len(p) - 1
    arc([0.155, -0.12, 0.48], [0, -1, 0], [0, 0, 1], 0.065, 0, np.pi / 2)
    line([0.155, 0.045, 0.545])
