"""Reference-only tuner. Copy to solution/, never the agent image.

Only the actual delivered noisy feedback enters fit(); deployment metrics are not inputs.
"""

import json
import numpy as np
from ..control_public.anycar import BOUNDS, validate


def fit(policy, feedbacks):
    blocks = []
    for feedback in feedbacks:
        rows = feedback["telemetry"]
        # Discard start-up. Encoder steering is a noisy estimate, not ground truth.
        x = np.array([r["values"] for r in rows if r["t"] >= 2.0])
        if len(x) > 10:
            blocks.append(x)
    result = dict(policy)
    if not blocks:
        return result, "Insufficient noisy telemetry; retain the existing controller."
    x = np.concatenate(blocks)
    # Fit fixed transport + actuator lag on recorded requested steer vs encoder steer.
    best = None
    for lag in range(4):
        pairs = []
        for block in blocks:
            pairs.append((block[: len(block) - lag or None, 17], block[lag:, 10]))
        u = np.concatenate([p[0] for p in pairs])
        y = np.concatenate([p[1] for p in pairs])
        A = np.column_stack([u, np.ones(len(u))])
        coeff = np.linalg.lstsq(A, y, rcond=None)[0]
        loss = float(np.mean((A @ coeff - y) ** 2))
        if best is None or loss < best[0]:
            best = (loss, coeff, lag)
    gain, bias = best[1]
    if 0.5 < gain < 1.5:
        result["steering_scale"] = float(1.0 / gain)
        result["steering_bias"] = float(-bias / gain)
    mask = (x[:, 16] > 0.5) & (np.abs(x[:, 4]) < 0.3)
    # Fixed wheel-radius conversion from reported noisy wheel angular speeds.
    wheel_speed = 0.04 * np.mean(x[:, 6:10], axis=1)
    if np.sum(mask) > 20:
        drive_gain = float(np.median(wheel_speed[mask] / x[mask, 16]))
        if 0.5 < drive_gain < 1.5:
            result["drive_scale"] = float(1.0 / drive_gain)
    result["preview"] = float(np.clip(best[2] * 0.1 + 0.03, 0, 0.3))
    for k, (lo, hi) in BOUNDS.items():
        result[k] = float(np.clip(result[k], lo, hi))
    validate(result)
    diagnosis = "Noisy steering encoders show command-response gain, offset and lag; update inverse steering calibration, wheel-speed drive calibration and preview. Predict reduced timed-path lag and heading error."
    return result, diagnosis


def iterate(client, initial_policy, out):
    """Native service client with describe/deploy/seal; exact response objects retained."""
    from pathlib import Path

    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    policy = dict(initial_policy)
    diagnosis = "Evaluate the nominal controller to measure tracking and command-response mismatch."
    for iteration in range(3):
        (out / f"policy-{iteration}.json").write_bytes(validate(policy))
        result = client.call("deploy", {"policy": policy, "diagnosis": diagnosis})
        (out / f"feedback-{iteration}.json").write_text(json.dumps(result, sort_keys=True, allow_nan=False))
        if "error" in result:
            raise RuntimeError("Deployment rejected")
        if iteration < 2:
            policy, diagnosis = fit(policy, result["feedback"])
    return client.call(
        "seal",
        {
            "round_id": result["round_id"],
            "summary": "Selected final sensor-calibrated controller after three deployment rounds.",
        },
    )


def public_feedback(record, folder):
    """Fixed-schedule observation projection, usable by the shared adapter."""
    import base64
    import hashlib
    import math
    from pathlib import Path
    import subprocess

    folder = Path(folder)
    rows = record["feedback"]["telemetry"]
    if set(record["feedback"]) != {"telemetry"} or len(rows) != 241:
        raise ValueError("Unexpected feedback schema")
    for i, row in enumerate(rows):
        if set(row) != {"t", "values"} or len(row["values"]) != 18 or abs(row["t"] - i * 0.1) > 1e-9:
            raise ValueError("Unexpected sensor schedule")
        if not all(type(v) in (int, float) and math.isfinite(v) for v in [row["t"], *row["values"]]):
            raise ValueError("Invalid feedback")
    images = []
    if (folder / "video.mp4").exists():
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(folder / "video.mp4"),
                "-vf",
                r"select=not(mod(n\,10))",
                "-vsync",
                "vfr",
                "-threads",
                "1",
                "-q:v",
                "3",
                str(folder / "sample-%03d.jpg"),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        for i, p in enumerate(sorted(folder.glob("sample-*.jpg"))):
            raw = p.read_bytes()
            images.append(
                dict(
                    time_s=float(i),
                    mime_type="image/jpeg",
                    sha256=hashlib.sha256(raw).hexdigest(),
                    base64=base64.b64encode(raw).decode(),
                )
            )
        if len(images) != 25:
            raise ValueError("Unexpected image schedule")
    return dict(telemetry=rows, images=images)
