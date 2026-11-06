"""The striker's capability table: how likely a stroke option (blade centre p, face normal n, blade velocity v at the
contact, time T from the command to the contact; table frame of the receiver) is returned when this striker executes it.
Built offline on the training serve sets only (prototypes/tabletennis_h2: cap_mjx.py commands every robust lab option
of each serve in the training environment and records the blade's actual state at the strike; cap_label.py strikes the
serve's true flight with that state in the ball lab, plus two executions under the B9 scatter; cap_fit.py scales the
features). The estimate is the distance-weighted mean label of the 16 nearest table rows. Plain numpy; one table per
striker checkpoint (its sha256 is in the table)."""
from __future__ import annotations

import numpy as np


class Capability:
    """The table (x, y, scale: the nearest-neighbour estimate) or its network form (net{i}_w / net{i}_b, scale:
    prototypes/tabletennis_h2/cap_net.py, an MLP fitted to the same labels; fast enough for match play)."""

    def __init__(self, path):
        z = np.load(path)
        self.scale = z["scale"].astype(np.float32)
        self.net = []
        while f"net{len(self.net)}_w" in z:
            i = len(self.net)
            self.net.append((z[f"net{i}_w"].astype(np.float32), z[f"net{i}_b"].astype(np.float32)))
        if not self.net:
            self.x, self.y = z["x"].astype(np.float32), z["y"].astype(np.float32)
            self.k = min(16, len(self.x) - 1)

    def estimate(self, P, N, V, T):
        """Return chances of the options (arrays (m, 3), (m, 3), (m, 3), (m,))."""
        N = np.asarray(N, float)
        N = N / np.linalg.norm(N, axis=1, keepdims=True)
        q = (np.c_[np.asarray(P, float), N, np.asarray(V, float), np.asarray(T, float)] / self.scale).astype(np.float32)
        if self.net:
            h = q
            for i, (w, b) in enumerate(self.net):
                h = h @ w + b
                if i < len(self.net) - 1:
                    h = np.where(h > 0, h, np.expm1(np.minimum(h, 0)))
            return (1.0 / (1.0 + np.exp(-h[:, 0]))).astype(np.float32)
        out = np.empty(len(q), np.float32)
        for i0 in range(0, len(q), 256):
            d2 = ((q[i0:i0 + 256, None, :] - self.x[None, :, :]) ** 2).sum(-1)
            nn = np.argpartition(d2, self.k, axis=1)[:, :self.k]
            w = 1.0 / (0.25 + np.take_along_axis(d2, nn, 1))
            out[i0:i0 + 256] = (w * self.y[nn]).sum(1) / w.sum(1)
        return out
