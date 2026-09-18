"""Offline gate: does the lift-and-swing actually bring the opening onto the bar,
and does it keep the clearance the lift was supposed to buy?

The extraction aligns the C ring with two straight legs (`slide_waypoints`): raise
the ring so the bar moves from the top of its interior toward its centre, then one
straight swing that puts the bar toward the opening. The whole point of that shape
is that the motion runs through the hole's empty middle -- every millimetre of lift
is supposed to be a millimetre of clearance under the swing. This gate holds the
path to that promise:

  - **The path ends aligned.** Walk the waypoints and require the opening to finish
    pointing at the bar.
  - **The swing is as clear as the lift says.** Sample the swing leg against the
    closed ring's tube and require the clearance to stay near ``slide_lift``
    (measured: lift 20 mm gives 19.8 mm). A regression that routes the swing near
    the tube again -- the arc this replaced hugged it at 0 mm and needed four layers
    of compensation that still clipped -- fails here, not in the scene.

Both are checked at four `stand.hang_yaw_deg` values, because that angle turns the
C's plane in world and everything derived from it turns with it.

Imported by path, so this needs numpy and PyYAML only and runs on a checkout with
no solver installed.

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

# The opening has to finish pointing at the bar.
MAX_ALIGN_DEG = 0.001
# The swing's clearance may fall short of the lift by at most this much -- chord
# discretisation of the two rings costs a fraction of a millimetre.
CLEARANCE_SHORTFALL = 0.002
HANG_YAWS = (0.0, 90.0, 180.0, 270.0)


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    cg = load_module("c_ring_geometry", "topogym/tasks_legacy/entangle/_c_ring_geometry.py")
    base = yaml.safe_load(TASK_CONFIG.read_text(encoding="utf-8"))
    lift = float(base["primitive"]["slide_lift"])

    print(f"unlink_c_ring slide-path gate -- {TASK_CONFIG.relative_to(REPO)}")
    print(f"lift = {lift * 1000:.0f} mm\n")
    print(f"{'hang_yaw':>9} {'lift leg':>9} {'swing':>8} {'end align':>11} {'swing clearance':>16}  verdict")

    failures: list[str] = []
    for hang_yaw in HANG_YAWS:
        cfg = yaml.safe_load(TASK_CONFIG.read_text(encoding="utf-8"))
        cfg["stand"]["hang_yaw_deg"] = float(hang_yaw)
        geometry = cg.scene_geometry(cfg)
        frame = geometry.c_rest_frame
        fixed = geometry.fixed_axes()

        points = cg.slide_waypoints(geometry, frame, lift=lift)
        landed = cg.RingFrame(center=points[-1], normal=frame.normal, ref=frame.ref)
        align = cg.opening_to_bar_deg(geometry, landed)
        swing_clear = min(
            cg.surface_gap(
                fixed,
                geometry.c_axes(
                    cg.RingFrame(
                        center=(1.0 - t) * points[1] + t * points[2],
                        normal=frame.normal,
                        ref=frame.ref,
                    )
                ),
            )
            for t in np.linspace(0.0, 1.0, 40)
        )

        ok = align <= MAX_ALIGN_DEG and swing_clear >= lift - CLEARANCE_SHORTFALL
        print(
            f"{hang_yaw:9.0f} {np.linalg.norm(points[1] - points[0]) * 1000:8.1f}mm "
            f"{np.linalg.norm(points[2] - points[1]) * 1000:7.1f}mm "
            f"{align:10.4f}d {swing_clear * 1000:15.2f}mm  {'ok  ' if ok else 'FAIL'}"
        )
        if align > MAX_ALIGN_DEG:
            failures.append(
                f"hang_yaw {hang_yaw:.0f}: the swing ends {align:.4f} deg off the bar"
            )
        if swing_clear < lift - CLEARANCE_SHORTFALL:
            failures.append(
                f"hang_yaw {hang_yaw:.0f}: the swing passes {swing_clear * 1000:.2f} mm "
                f"from the tube, short of the {lift * 1000:.0f} mm the lift bought"
            )

    print()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[pass] the swing lands the opening on the bar, with the lift's clearance intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
