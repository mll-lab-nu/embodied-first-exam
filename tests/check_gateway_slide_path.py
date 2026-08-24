"""Offline gate: does the slide actually bring the opening onto the bar, and is the
arc split finely enough to stay off the closed ring on the way?

The extraction aligns the C ring by SLIDING it, not by turning it: the bar pierces the
C's plane at one point, and walking the ring's centre round that point on an arc
carries the bar from the top of the interior to the opening while the wrist holds
still. `tasks/entangle/_c_ring_geometry.slide_waypoints` owns that path; both the
clearance gate and the runtime primitive consume it, so an error there is an error
everywhere and nothing downstream would contradict it.

Two properties, and neither is a check on the components:

  - **The path ends aligned.** Walk the waypoints and require the opening to finish
    pointing at the bar. A sign error in the arc direction sends the ring the long way
    round; it still ends aligned, so this is paired with the clearance gate rather
    than trusted alone.
  - **The chord count is not decoration.** The centre travels an ARC. Approximating it
    with one straight chord cuts 3.35 mm inside the true path, which is more than the
    trajectory's whole clearance budget; the configured count has to bring that under
    a tenth of a millimetre. The negative control is the point: this asserts that ONE
    chord is bad, so a future edit that quietly drops the subdivision fails here
    instead of in the scene.

Both are checked at four `stand.hang_yaw_deg` values, because that angle turns the C's
plane in world and everything derived from it -- the bar's tangent, the opening's
direction, the arc's axis -- turns with it. A path that only works at the shipped
layout is a path that happens to work.

This replaced `check_gateway_extract_quat.py`, whose subject was the quaternion
composition of the wrist roll the slide removed. See `slide_waypoints` for why the
roll went: a 134 mm lever from hand origin to ring centre against a controller that
holds orientation to 14 degrees.

Imported by path, so this needs numpy and PyYAML only and runs on a checkout with no
solver installed.

    python tests/check_gateway_slide_path.py

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
# What the configured chord count must achieve, and what a single chord must fail.
MAX_CHORD_SAG = 0.0001
MIN_SINGLE_CHORD_SAG = 0.003
HANG_YAWS = (0.0, 90.0, 180.0, 270.0)


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def chord_sag(cg, geometry, frame, chords: int) -> float:
    """How far inside the true arc the chord approximation cuts, in metres.

    Every waypoint sits ON the arc by construction, so the sag is entirely between
    them: the deepest point of a chord is its midpoint, and it falls short of the
    radius by the sagitta. Measured rather than derived so a change to how the
    waypoints are spaced shows up here.
    """

    bar = np.asarray(geometry.tube_point, dtype=float)
    points = cg.slide_waypoints(geometry, frame, chords=chords)
    radius = float(np.linalg.norm(bar - np.asarray(frame.center, dtype=float)))
    worst = 0.0
    for before, after in zip(points[:-1], points[1:]):
        midpoint = 0.5 * (before + after)
        worst = max(worst, radius - float(np.linalg.norm(midpoint - bar)))
    return worst


def main() -> int:
    cg = load_module("c_ring_geometry", "topogym/tasks/entangle/_c_ring_geometry.py")
    base = yaml.safe_load(TASK_CONFIG.read_text(encoding="utf-8"))
    chords = int(base["primitive"]["align_chords"])

    print(f"unlink_c_ring slide-path gate -- {TASK_CONFIG.relative_to(REPO)}")
    print(f"chords = {chords}\n")
    print(f"{'hang_yaw':>9} {'travel':>9} {'end align':>11} {'sag@N':>9} {'sag@1':>9}  verdict")

    failures: list[str] = []
    for hang_yaw in HANG_YAWS:
        cfg = yaml.safe_load(TASK_CONFIG.read_text(encoding="utf-8"))
        cfg["stand"]["hang_yaw_deg"] = float(hang_yaw)
        geometry = cg.scene_geometry(cfg)
        frame = geometry.c_rest_frame

        points = cg.slide_waypoints(geometry, frame, chords=chords)
        travel = sum(
            float(np.linalg.norm(b - a)) for a, b in zip(points[:-1], points[1:])
        )
        landed = cg.RingFrame(
            center=points[-1], normal=frame.normal, ref=frame.ref
        )
        align = cg.opening_to_bar_deg(geometry, landed)
        sag_n = chord_sag(cg, geometry, frame, chords)
        sag_1 = chord_sag(cg, geometry, frame, 1)

        ok = (
            align <= MAX_ALIGN_DEG
            and sag_n <= MAX_CHORD_SAG
            and sag_1 >= MIN_SINGLE_CHORD_SAG
        )
        print(
            f"{hang_yaw:9.0f} {travel * 1000:8.1f}mm {align:10.4f}d "
            f"{sag_n * 1000:8.3f}mm {sag_1 * 1000:8.3f}mm  {'ok  ' if ok else 'FAIL'}"
        )
        if align > MAX_ALIGN_DEG:
            failures.append(
                f"hang_yaw {hang_yaw:.0f}: the slide ends {align:.4f} deg off the bar"
            )
        if sag_n > MAX_CHORD_SAG:
            failures.append(
                f"hang_yaw {hang_yaw:.0f}: {chords} chords cut {sag_n * 1000:.3f} mm "
                "inside the arc"
            )
        if sag_1 < MIN_SINGLE_CHORD_SAG:
            failures.append(
                f"hang_yaw {hang_yaw:.0f}: a single chord only cuts "
                f"{sag_1 * 1000:.3f} mm, so this gate is not testing anything"
            )

    print()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[pass] the slide lands the opening on the bar, and the arc is split finely enough.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
