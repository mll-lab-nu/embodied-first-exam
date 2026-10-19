"""Author's full 12-input, 3-output real-flight residual, evaluator only.

Feature order follows realdata/learning_fa.ipynb at the pinned asset commit:
world z, world vx/vy/vz, ROS quaternion xyzw, four RPM / 8000. Outputs are
world-frame forces in N. There is no clipping, thrust gate or upright reduction.
"""

import numpy as np


class Residual:
    def __init__(self, path, scale=1.0):
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("Invalid residual scale")
        self.scale = scale
        with np.load(path, allow_pickle=False) as data:
            self.weights = {k: data[k].copy() for k in data.files}
        for i, shape in enumerate([(25, 12), (30, 25), (15, 30), (3, 15)], 1):
            for key, dims in [(f"weight{i}", shape), (f"bias{i}", (shape[0],))]:
                if self.weights[key].shape != dims or not np.isfinite(self.weights[key]).all():
                    raise ValueError("Invalid residual artifact")

    def force(self, position, velocity, quaternion, rotor_rpm):
        q = np.asarray(quaternion, dtype=float)
        q = q / np.linalg.norm(q)
        # Match the near-upright negative-w convention of the released flights.
        if q[0] > 0:
            q = -q
        x = np.r_[position[2], velocity, q[1:], q[0], np.asarray(rotor_rpm) / 8000.0]
        if x.shape != (12,) or not np.isfinite(x).all():
            raise ValueError("Invalid residual input")
        for i in range(1, 5):
            x = self.weights[f"weight{i}"] @ x + self.weights[f"bias{i}"]
            if i < 4:
                x = np.maximum(x, 0)
        return self.scale * x
