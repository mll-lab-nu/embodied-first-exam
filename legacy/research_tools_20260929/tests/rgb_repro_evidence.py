"""Lossless evidence for seed-reset RGB comparisons; no simulator imports."""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def save_rgb_comparison(folder, expected, actual):
    """Save every camera before the caller enforces strict equality.

    A changed pixel has at least one changed channel. Threshold fractions use
    max channel absolute error per pixel; MAE uses all channels and pixels.
    """
    if not expected or expected.keys() != actual.keys():
        raise ValueError("RGB camera sets must be nonempty and identical")
    for name, reference in expected.items():
        candidate = actual[name]
        if (reference.dtype != np.uint8 or candidate.dtype != np.uint8
                or reference.shape != candidate.shape or reference.ndim != 3
                or reference.shape[2] != 3 or reference.size == 0):
            raise ValueError(f"Expected matching nonempty uint8 HxWx3 RGB: {name}")
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError(f"Invalid camera name: {name}")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    report = dict(
        schema_version=1,
        units="uint8 channel levels (0..255); fractions in [0, 1]",
        threshold_definition="fraction of pixels with max(abs(A - A_again), axis=RGB) > threshold",
        bbox_definition="[x_min, y_min, x_max_exclusive, y_max_exclusive]; null if equal",
        heatmap_definition="grayscale max channel error multiplied by 16, clipped at 255; fixed scale",
        cameras={},
    )
    for name, reference in expected.items():
        candidate = actual[name]
        # Widen before subtraction to avoid uint8 wraparound.
        delta = np.abs(reference.astype(np.int16) - candidate.astype(np.int16))
        per_pixel = delta.max(axis=2)
        changed = per_pixel > 0
        ys, xs = np.nonzero(changed)
        camera_folder = folder / name
        camera_folder.mkdir()
        files = {}
        for label, pixels in (
            ("A", reference), ("A_again", candidate),
            ("absdiff", delta.astype(np.uint8)),
            ("changed_mask", changed.astype(np.uint8) * 255),
            ("max_error_x16", np.minimum(per_pixel * 16, 255).astype(np.uint8)),
        ):
            path = camera_folder / f"{label}.png"
            Image.fromarray(pixels).save(path)
            files[label] = dict(path=str(path.relative_to(folder)),
                                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        report["cameras"][name] = dict(
            shape=list(reference.shape),
            bitwise_equal=bool(np.array_equal(reference, candidate)),
            changed_pixel_count=int(changed.sum()),
            changed_pixel_fraction=float(changed.mean()),
            mean_absolute_channel_error=float(delta.mean()),
            max_absolute_channel_error=int(delta.max()),
            pixel_fraction_above={str(t): float((per_pixel > t).mean()) for t in (1, 2, 5, 10)},
            changed_bbox_xyxy=([int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
                               if xs.size else None),
            files=files,
        )
    (folder / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
