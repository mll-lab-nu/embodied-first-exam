"""Operator-only propeller animation derived from archived motor force samples."""

import numpy as np


def landing_rotors(trajectory, frame_times, thrust_coefficient):
    times = np.asarray([row["t"] for row in trajectory], dtype=float)
    forces = np.asarray([row["motor_forces"] for row in trajectory], dtype=float)
    if (
        times.ndim != 1
        or len(times) < 2
        or forces.shape != (len(times), 4)
        or not np.isfinite(times).all()
        or not np.isfinite(forces).all()
        or np.any(np.diff(times) <= 0)
        or np.any(forces < 0)
        or not np.isfinite(thrust_coefficient)
        or thrust_coefficient <= 0
    ):
        raise ValueError(
            "Expected increasing timestamps and four nonnegative motor forces"
        )
    frame_times = np.asarray(frame_times, dtype=float)
    if (
        not np.isfinite(frame_times).all()
        or np.any(frame_times < times[0])
        or np.any(frame_times > times[-1])
    ):
        raise ValueError("Render timestamps must stay inside the recorded trajectory")
    rpm = np.sqrt(forces / thrust_coefficient)
    omega = rpm * (2 * np.pi / 60) * np.array([1, -1, 1, -1])
    # Integrate at the original 100 Hz before sampling the 25 Hz video. The
    # initial blade phase is cosmetic: blade angle was not a simulated DOF.
    phase = np.empty_like(omega)
    phase[0] = np.array([0, 0.6, 1.2, 1.8]) + omega[0] * times[0]
    phase[1:] = phase[0] + np.cumsum(
        (omega[:-1] + omega[1:]) * np.diff(times)[:, None] / 2, axis=0
    )
    return {
        "time": frame_times,
        "rpm": np.column_stack(
            [np.interp(frame_times, times, rpm[:, i]) for i in range(4)]
        ),
        "phase": np.column_stack(
            [np.interp(frame_times, times, phase[:, i]) for i in range(4)]
        ),
    }
