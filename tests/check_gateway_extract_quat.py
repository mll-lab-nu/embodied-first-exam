"""Offline gate: does the extraction's wrist turn actually align the opening?

`primitives/gateway_extract.py` builds the aligned wrist pose as
``quat_mul(quat_about_axis(axis, angle), base_quat)``, and
`tasks/entangle/_c_ring_geometry.py` builds the same turn as a 3x3 matrix inside
`apply_phases`. Those are two independent expressions of one rotation, written in two
different conventions, and a sign error in either produces a run that looks plausible
and turns the C ring the wrong way -- straight into the closed ring, which under an
assisted carry tunnels rather than jams, so nothing downstream would catch it.

So this checks the property, not the components: take the resting ring, apply the turn
the way the primitive would build it, and require the opening to end up pointing at the
bar. `tests/check_axial_insert_tilt.py` makes the same argument for `axial_insert` --
"testing the quaternion's components instead would pass for a correction that is off by
a sign and still fail in the scene".

Both modules are imported by path, so this needs numpy and PyYAML only and runs on a
checkout with no solver installed.

    python tests/check_gateway_extract_quat.py

"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
TASK_CONFIG = REPO / "configs/task_configs/unlink_c_ring_topogym_tabletop_v1.yaml"

# The opening has to finish pointing at the bar. Anything above this and the ring's
# body, not its opening, is what the bar meets on the way out.
MAX_ALIGN_DEG = 0.001
# The wrist must not take the long way round: the turn it is asked for is the turn
# the geometry says, not that angle plus a lap.
MAX_TURN_SLACK_DEG = 0.001


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def quat_mul(a, b) -> np.ndarray:
    aw, ax, ay, az = np.asarray(a, dtype=float)
    bw, bx, by, bz = np.asarray(b, dtype=float)
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        dtype=float,
    )


def quat_about_axis(axis, angle: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    return np.concatenate(([np.cos(0.5 * angle)], np.sin(0.5 * angle) * axis))


def matrix(quat) -> np.ndarray:
    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(4))
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def opening_to_bar_deg(geometry, frame) -> float:
    """Duplicated from the verifier on purpose: that module imports Genesis."""

    opening = frame.point(np.deg2rad(geometry.c_ring.gap_azimuth_deg), 1.0)[0] - frame.center
    to_bar = geometry.tube_point - frame.center
    cosine = float(np.dot(opening, to_bar)) / float(
        np.linalg.norm(opening) * np.linalg.norm(to_bar)
    )
    return float(np.rad2deg(np.arccos(np.clip(cosine, -1.0, 1.0))))


def main() -> int:
    cg = load_module("c_ring_geometry", "topogym/tasks/entangle/_c_ring_geometry.py")
    cfg = yaml.safe_load(TASK_CONFIG.read_text(encoding="utf-8"))
    failures: list[str] = []

    print("gateway_extract rotation gate\n")

    for yaw in (0.0, 45.0, 90.0, 180.0, 270.0):
        cfg["stand"]["hang_yaw_deg"] = yaw
        geometry = cg.scene_geometry(cfg)
        axis, degrees = geometry.align_rotation()

        # The primitive's construction, component for component.
        turn = quat_about_axis(axis, np.deg2rad(degrees))
        rest = geometry.c_rest_frame
        turned = rest.transformed(rotation=matrix(turn))

        before = opening_to_bar_deg(geometry, rest)
        after = opening_to_bar_deg(geometry, turned)
        # 2*arccos|w| is the turn the wrist is actually asked for.
        wrist_deg = float(np.rad2deg(2.0 * np.arccos(np.clip(abs(turn[0]), -1.0, 1.0))))
        slack = abs(wrist_deg - abs(degrees))

        ok = after <= MAX_ALIGN_DEG and slack <= MAX_TURN_SLACK_DEG
        print(
            f"  [{'ok  ' if ok else 'FAIL'}] hang yaw {yaw:5.1f}deg   "
            f"opening_to_bar {before:6.2f} -> {after:6.4f} deg   "
            f"wrist turn {wrist_deg:6.2f}deg (asked {abs(degrees):.2f})"
        )
        if after > MAX_ALIGN_DEG:
            failures.append(
                f"yaw {yaw}: the turn leaves the opening {after:.3f} deg off the bar"
            )
        if slack > MAX_TURN_SLACK_DEG:
            failures.append(
                f"yaw {yaw}: the wrist turns {wrist_deg:.2f} deg for a {abs(degrees):.2f} deg job"
            )

    # The two builders must agree: the quaternion the primitive composes and the
    # matrix `apply_phases` applies are the same rotation, or the demo and the gate
    # that certified its clearance are running different trajectories.
    cfg["stand"]["hang_yaw_deg"] = float(yaml.safe_load(
        TASK_CONFIG.read_text(encoding="utf-8"))["stand"]["hang_yaw_deg"])
    geometry = cg.scene_geometry(cfg)
    axis, degrees = geometry.align_rotation()
    from_quat = matrix(quat_about_axis(axis, np.deg2rad(degrees)))
    from_phases = cg.rotation_about(
        geometry.c_rest_frame.normal, -np.deg2rad(geometry.c_ring.gap_azimuth_deg)
    )
    disagreement = float(np.max(np.abs(from_quat - from_phases)))
    print(
        f"\n  [{'ok  ' if disagreement < 1e-9 else 'FAIL'}] the primitive's quaternion and "
        f"apply_phases' matrix agree to {disagreement:.2e}"
    )
    if disagreement >= 1e-9:
        failures.append(
            "the wrist turn and the trajectory the clearance gate measured are different "
            f"rotations (max element difference {disagreement:.2e})"
        )

    print()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[pass] the wrist turn aligns the opening, at every stand yaw, the short way.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
