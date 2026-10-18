"""Operator-only source/flight-log audit; never execute upstream notebook code.

Downloads are pinned and hash checked. Flight errors are in-sample diagnostics:
the release does not identify an independent flight holdout for its checkpoint.
"""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import numpy as np
from .prepare_assets import COMMIT, SHA256
from .public.model import AIR_DENSITY, CT, GRAVITY, MASS, PROPELLER_DIAMETER, PWM_TO_RPM, THRUST_COEFFICIENT
from .trusted.residual import Residual

BASE = f"https://raw.githubusercontent.com/GuanyaShi/neural_lander_sim_1d/{COMMIT}/"
FILES = {
    "realdata/learning_fa.ipynb": "5b83fa2749be8d75862ccd29f55cb0b790cda20d30416f21c6f98dfdbde1e038",
    "1d_landing_simulator.ipynb": "2975420b874c991ed110fd176153d111b8dff989b2d5c447fc81b98dfa8608c7",
    "realdata/free_flying_low/_slash_mavros_slash_local_position_slash_pose.csv": "2f24317265dba7fb16db1c0ea0a073d55710ad4717486eeda3940cf39ec3336f",
    "realdata/free_flying_low/_slash_mavros_slash_local_position_slash_velocity.csv": "0d7c535ed50e20f7afd0f35d99b345e3bf189d005ccc9ac49b71427e9180c167",
    "realdata/free_flying_low/_slash_mavros_slash_rc_slash_out.csv": "e5611807eaf817c235915083cde7bc3c52c581b20e4607b7e21fbaf1144b551d",
    "Fa_net_12_3_full_Lip16.pth": SHA256,
}


def obtain(cache, name, sha):
    path = cache / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        data = urllib.request.urlopen(BASE + name, timeout=60).read()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError("Source download hash mismatch")
        path.write_bytes(data)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("Cached source hash mismatch")
    return data


def audit(cache, residual):
    import ast
    import torch

    blobs = {name: obtain(cache, name, sha) for name, sha in FILES.items()}
    notebook = json.loads(blobs["realdata/learning_fa.ipynb"])
    constants = {}
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        for node in ast.walk(ast.parse("".join(cell["source"]))):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try:
                    constants[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    expected = {
        "m": MASS,
        "g": GRAVITY,
        "rho": AIR_DENSITY,
        "D": PROPELLER_DIAMETER,
        "C_t_fixed": THRUST_COEFFICIENT,
        **dict(zip(("a1", "a2", "a3"), PWM_TO_RPM)),
    }
    for name, value in expected.items():
        if constants.get(name) != value:
            raise ValueError(f"Calibration mismatch: {name}")

    streams = {}
    for name, data in blobs.items():
        if name.endswith(".csv"):
            rows = list(csv.reader(io.StringIO(data.decode())))[1:]
            streams[name.rsplit("/", 1)[1]] = rows
    pwm = streams["_slash_mavros_slash_rc_slash_out.csv"]
    bias = int(pwm[0][4])
    times = np.linspace(35, 325, 29001)  # exact released preprocessing interval

    def interpolate(rows, columns):
        t = np.array([int(r[4]) - bias + int(r[5]) / 1e9 for r in rows])
        if np.any(np.diff(t) <= 0) or times[0] < t[0] or times[-1] > t[-1]:
            raise ValueError("Invalid flight timestamps")
        values = np.array([columns(r) for r in rows], dtype=float)
        return np.column_stack([np.interp(times, t, c) for c in values.T])

    pose = interpolate(streams["_slash_mavros_slash_local_position_slash_pose.csv"], lambda r: r[9:12] + r[13:17])
    velocity = interpolate(streams["_slash_mavros_slash_local_position_slash_velocity.csv"], lambda r: r[9:12])
    commands = interpolate(pwm, lambda r: json.loads(r[7])[:4])
    a1, a2, a3 = PWM_TO_RPM
    rpm = a1 * commands**2 + a2 * commands + a3
    acceleration = (-velocity[4:] + 8 * velocity[3:-1] - 8 * velocity[1:-3] + velocity[:-4]) / 0.12
    q = pose[:, 3:]  # ROS xyzw; retain exact notebook input for flight diagnostics
    thrust_axis = np.column_stack(
        [
            2 * (q[:, 0] * q[:, 2] + q[:, 1] * q[:, 3]),
            2 * (q[:, 1] * q[:, 2] - q[:, 0] * q[:, 3]),
            -(q[:, 0] ** 2) - q[:, 1] ** 2 + q[:, 2] ** 2 + q[:, 3] ** 2,
        ]
    )
    observed = (
        MASS * (acceleration + [0, 0, GRAVITY]) - (CT * np.sum(rpm[2:-2] ** 2, axis=1))[:, None] * thrust_axis[2:-2]
    )
    inputs = np.column_stack([pose[:, 2], velocity, q, rpm / 8000])
    source = torch.load(io.BytesIO(blobs["Fa_net_12_3_full_Lip16.pth"]), map_location="cpu", weights_only=True)

    def original_forward(x):
        t = torch.from_numpy(x.copy()).double()
        for i in range(1, 5):
            t = torch.nn.functional.linear(t, source[f"fc{i}.weight"].double(), source[f"fc{i}.bias"].double())
            if i < 4:
                t = torch.relu(t)
        return t.detach().numpy()

    predicted = original_forward(inputs)
    errors = predicted[2:-2] - observed
    plant = Residual(residual)
    # Compare runtime inference to original checkpoint on real flight states,
    # normalizing quaternion consistently for the rigid-body simulator adapter.
    sample = np.arange(2, len(inputs) - 2, 29)
    canonical = inputs[sample].copy()
    canonical[:, 4:8] /= np.linalg.norm(canonical[:, 4:8], axis=1)[:, None]
    canonical[canonical[:, 7] > 0, 4:8] *= -1
    actual = np.array([plant.force(pose[k, :3], velocity[k], q[k, [3, 0, 1, 2]], rpm[k]) for k in sample])
    parity = float(np.max(np.abs(actual - original_forward(canonical))))
    if parity > 1e-10:
        raise ValueError("Runtime residual disagrees with author checkpoint")
    return {
        "commit": COMMIT,
        "source_sha256": FILES,
        "calibration_literals_match": True,
        "thrust_N_per_RPM_squared": CT,
        "runtime_vs_original_max_abs_error_N": parity,
        "parity_samples": len(sample),
        "flight_samples": len(errors),
        "flight_interval_s": [35, 325],
        "quaternion_negative_w_fraction": float(np.mean(q[:, 3] < 0)),
        "residual_force_rmse_xyz_N": np.sqrt(np.mean(errors**2, axis=0)).tolist(),
        "zero_residual_rmse_xyz_N": np.sqrt(np.mean(observed**2, axis=0)).tolist(),
        "flight_diagnostic_is_independent_holdout": False,
        "fully_calibrated_6dof_airframe": False,
        "missing_calibration": [
            "inertia",
            "rotor arm geometry and channel ordering",
            "yaw torque coefficient",
            "measured motor response",
            "contact geometry/friction",
        ],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--residual", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    report = audit(a.cache, a.residual)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
