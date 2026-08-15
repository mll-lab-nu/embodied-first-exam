"""Does `_axis_tilt` measure the tilt of the axis the caller actually named?

Regression for the 2026-08-15 bar_through_hole failure. `AxialInsertPrimitive`
takes a `part_axis` and gates the grasp on `lift_tilt <= max_grasp_tilt`
(2 deg for that task). `_axis_tilt` read the rotation matrix's third column
unconditionally -- the part's local +z. That is right for a Genesis Cylinder,
the shape it was first written against, but the hex shaft's axis is local +x
(`hex_prism_mesh` generates it axis-along-X), so a flat, perfectly aligned shaft
measured 90 deg and the gate could never pass. Every episode died at phase 8 of
15 with `grasp_check_failed: ... lift_tilt=89.99deg`.

Both shapes are covered below, so the fix cannot regress the cylinder caller.

    python tests/check_axial_insert_tilt.py

Exits non-zero on failure. Imports the module by path rather than through
`topogym.primitives`, whose `__init__` pulls in Genesis -- this file needs numpy
only, so it runs outside the project venv.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "axial_insert", REPO / "topogym" / "primitives" / "axial_insert.py"
)
axial_insert = importlib.util.module_from_spec(_spec)
sys.modules["axial_insert"] = axial_insert  # @dataclass resolves the module by name
_spec.loader.exec_module(axial_insert)

X_AXIS = (1.0, 0.0, 0.0)  # the hex shaft
Z_AXIS = (0.0, 0.0, 1.0)  # a Genesis Cylinder


def quat(axis, degrees: float) -> np.ndarray:
    """(w, x, y, z) for a rotation about ``axis`` -- Genesis' component order."""

    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    half = np.radians(degrees) / 2.0
    return np.concatenate([[np.cos(half)], np.sin(half) * axis])


IDENTITY = quat(Z_AXIS, 0.0)

CASES = (
    # (description, quat, part_axis, expected degrees)
    ("shaft at rest", IDENTITY, X_AXIS, 0.0),
    ("shaft pitched 5deg about y", quat((0, 1, 0), 5.0), X_AXIS, 5.0),
    ("shaft yawed 1.5deg about z", quat(Z_AXIS, 1.5), X_AXIS, 1.5),
    # Roll about the shaft's own axis is not tilt: the hex bore has 7 mm of
    # clearance per side, so any roll angle threads.
    ("shaft rolled 40deg about its own axis", quat(X_AXIS, 40.0), X_AXIS, 0.0),
    # End-for-end is the same physical state -- threading_count is unsigned.
    ("shaft flipped end for end", quat(Z_AXIS, 180.0), X_AXIS, 0.0),
    ("shaft stood on end", quat((0, 1, 0), 90.0), X_AXIS, 90.0),
    ("cylinder at rest", IDENTITY, Z_AXIS, 0.0),
    ("cylinder tipped 3deg", quat(X_AXIS, 3.0), Z_AXIS, 3.0),
)


# The wrist-alignment correction (2026-08-16). `align_axis` turns the hand by
# `_rotation_between(shaft axis now, bore axis)` and the shaft, held rigidly in
# the hand's frame, turns with it. The property that has to hold is end-to-end:
# applying the correction to the shaft's own orientation must leave its axis on
# the bore's axis. Testing the quaternion's components instead would pass for a
# correction that is off by a sign and still fail in the scene.
BORE_AXIS = (1.0, 0.0, 0.0)

ALIGN_CASES = (
    ("already aligned", IDENTITY),
    ("yawed 3.3deg, the measured closing disturbance", quat(Z_AXIS, 3.3)),
    ("yawed the other way", quat(Z_AXIS, -3.3)),
    ("pitched 4deg", quat((0, 1, 0), 4.0)),
    ("yawed and pitched together", axial_insert._quat_mul(quat(Z_AXIS, 3.0), quat((0, 1, 0), 2.0))),
    # End-for-end is the same alignment. A correction that took the short way to
    # the *signed* axis would ask the wrist for a 180-degree turn here.
    ("flipped end for end", quat(Z_AXIS, 180.0)),
    ("flipped and yawed 2deg", axial_insert._quat_mul(quat(Z_AXIS, 178.0), IDENTITY)),
    ("rolled about its own axis", quat(X_AXIS, 40.0)),
)


def main() -> int:
    failures: list[str] = []
    for description, rotation, part_axis, expected in CASES:
        actual = float(np.degrees(axial_insert._axis_tilt(rotation, part_axis)))
        ok = abs(actual - expected) < 1e-6
        print(f"[{'ok' if ok else 'error'}] {description}: {actual:.3f}deg (want {expected:.1f})")
        if not ok:
            failures.append(description)

    print()
    for description, rotation in ALIGN_CASES:
        axis_now = axial_insert._rotate(rotation, X_AXIS)
        correction = axial_insert._rotation_between(axis_now, BORE_AXIS)
        corrected = axial_insert._quat_mul(correction, rotation)
        residual = float(np.degrees(axial_insert._axis_tilt(corrected, X_AXIS)))
        turn = float(np.degrees(2.0 * np.arccos(np.clip(abs(correction[0]), -1.0, 1.0))))
        ok = residual < 1e-6 and turn <= 90.0
        print(
            f"[{'ok' if ok else 'error'}] align {description}: "
            f"residual={residual:.6f}deg wrist_turn={turn:.2f}deg"
        )
        if not ok:
            failures.append(f"align {description}")

    for failure in failures:
        print(f"[error] {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
