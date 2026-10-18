import numpy as np
from .models import Robot

MOVING_MODES = ["coordinated", "world_lock", "height_sweep"]
MODES = ["fixed", *MOVING_MODES]
BALANCED_MODES = ["fixed", "coordinated", "fixed", "world_lock", "fixed", "height_sweep"]
EVALUATION_PROTOCOL = "fixed-moving-v1"


def evaluation_class(mode):
    if mode not in MODES:
        raise ValueError("Unknown tracking mode")
    return "fixed" if mode == "fixed" else "moving"


DT = 0.02
DURATION = 12.0
REFERENCE_VERSION = "offset-start-v2"
LEGACY_VERSION = "home-start-v1"


class Reference:
    def __init__(self, robot, seed, mode="coordinated", version=REFERENCE_VERSION):
        if version not in (REFERENCE_VERSION, LEGACY_VERSION):
            raise ValueError("Unknown reference version")
        self.version = version
        if mode not in MODES:
            raise ValueError("Unknown tracking mode")
        self.r = Robot(robot)
        self.mode = mode
        rng = np.random.default_rng(seed)
        self.phase = rng.uniform(-np.pi, np.pi, self.r.n)
        self.freq = rng.uniform(0.22, 0.42, self.r.n)
        self.amp = rng.uniform(0.06, 0.16, self.r.n)
        self.amp[:3] = [0.22, 0.14, 0.16]
        for i, n in enumerate(self.r.names):
            if n == "joint9":
                self.amp[i] = 0.07
            elif n.startswith("torso"):
                self.amp[i] = 0.07
        self.anchor = self.r.home.copy()
        if version == REFERENCE_VERSION:
            # Sample a feasible nominal configuration before rollout, independent of the plant.
            # Reject anchors whose public Cartesian targets are too close to home.
            home = self.r.poses()
            for _ in range(1000):
                q = self.r.home.copy()
                angle = rng.uniform(-np.pi, np.pi)
                distance = rng.uniform(0.45, 0.60)
                q[self.r.qids[:3]] = [
                    distance * np.cos(angle),
                    distance * np.sin(angle),
                    rng.choice([-1, 1]) * rng.uniform(0.25, 0.45),
                ]
                q[self.r.qids[3:]] += rng.uniform(-0.18, 0.18, self.r.n - 3)
                q[self.r.qids] = np.clip(q[self.r.qids], self.r.limits[:, 0] + 0.03, self.r.limits[:, 1] - 0.03)
                self.r.set(q)
                e = errors(home, self.r.poses())
                if (
                    0.4 <= e[0] <= 0.65
                    and np.all((e[2:4] >= 0.30) & (e[2:4] <= 0.85))
                    and np.all((e[4:] >= 0.20) & (e[4:] <= 0.90))
                ):
                    self.anchor = q.copy()
                    self.initial_errors = e.tolist()
                    break
            else:
                raise RuntimeError("Could not sample separated reachable reference anchor")

    def target(self, t):
        if self.mode == "fixed":
            t = 0.0
        r = self.r
        q = self.anchor.copy()
        offset = self.amp * (np.sin(self.freq * t + self.phase) - np.sin(self.phase))
        q[r.qids] = np.clip(q[r.qids] + offset, r.limits[:, 0] + 0.03, r.limits[:, 1] - 0.03)
        # Public Cartesian references are feasible forward-kinematic trajectories, not joint targets supplied to the actor.
        base = q[r.qids[:3]].copy()
        if self.mode == "world_lock":
            q[:] = self.anchor
        if self.mode == "height_sweep":
            q[r.qids[3:]] = self.anchor[r.qids[3:]] + 0.5 * (q[r.qids[3:]] - self.anchor[r.qids[3:]])
        r.set(q)
        _, hands = r.poses()
        if self.mode == "height_sweep":
            hands = [(p + np.array([0, 0, 0.04 * np.sin(0.4 * t)]), rot) for p, rot in hands]
        return base, hands

    def sample(self, t):
        a = self.target(t)
        b = self.target(t + 0.001)
        twist = np.r_[
            (b[0] - a[0]) / 0.001,
            *[
                np.r_[(pb - pa) / 0.001, 0.5 * sum(np.cross(ra[:, i], rb[:, i]) for i in range(3)) / 0.001]
                for (pa, ra), (pb, rb) in zip(a[1], b[1])
            ],
        ]
        return a, twist


def errors(actual, target):
    b, h = actual
    bt, ht = target
    angles = [float(np.arccos(np.clip((np.trace(rt @ r.T) - 1) / 2, -1, 1))) for (_, r), (_, rt) in zip(h, ht)]
    return np.r_[
        np.linalg.norm(b[:2] - bt[:2]),
        abs(np.arctan2(np.sin(b[2] - bt[2]), np.cos(b[2] - bt[2]))),
        *[np.linalg.norm(p - pt) for (p, _), (pt, _) in zip(h, ht)],
        *angles,
    ]
