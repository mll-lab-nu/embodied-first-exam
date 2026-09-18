"""Does the derived bar_through_hole geometry reproduce the hand-placed baseline?

2026-09-04: the four carry heights (`primitive.grasp_z / lift_z / insert_z /
seat_z`) and the three cradle x positions stopped being config numbers and
became `BarThroughHoleLayout` formulas, so the variation axes can move the
shaft, the panel and the aperture and have everything follow. The formulas are
only right if, on the baseline yaml, they land where the hand-placed numbers
were -- that config threaded 16/16 phases on GPU, and this file pins the two
together so a later edit cannot silently move the working baseline.

Also checks the push window (the z range the shaft's axis may occupy while it
is pushed through: above every cradle's jaw tops, below the aperture's upper
edge) at the envelope's ends, and the derived length / grasp-offset ranges at
the worst corner of the layout axes.

    python tests/check_bar_through_hole_geometry.py

Needs the project venv (the layout module imports Genesis). Exits non-zero on
failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

from omegaconf import OmegaConf

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.tasks_legacy.routing.bar_through_hole import (  # noqa: E402
    BarThroughHoleLayout,
    derive_task_cfg,
)

CFG = REPO / "configs" / "task_configs" / "bar_through_hole_topogym_tabletop_v1.yaml"

# The hand-placed heights the derivation replaces (task frame, hand-link z).
# `insert` moved 0.193 -> 0.1889 on 2026-09-08: the push height is the midpoint of
# the window the shaft's axis may occupy, and that window's floor used to be the
# far cradle's ramp top. With the cradle retired -- the bore holds the shaft on its
# own -- the window is symmetric about the aperture's centre, so the push runs
# through the middle of the bore instead of riding above a ramp.
BASELINE_HAND_Z = {"grasp": 0.158, "lift": 0.203, "insert": 0.1889, "seat": 0.183}
BASELINE_CRADLE_X = {"near_a": -0.070, "near_b": 0.020}


def _fail(fails: list[str], msg: str) -> None:
    fails.append(msg)
    print(f"  FAIL {msg}")


def check_baseline(fails: list[str]) -> None:
    task = OmegaConf.load(CFG)
    layout = BarThroughHoleLayout(task)
    got = {
        "grasp": layout.grasp_hand_z(),
        "lift": layout.lift_hand_z(),
        "insert": layout.insert_hand_z(),
        "seat": layout.seat_hand_z(),
    }
    for name, want in BASELINE_HAND_Z.items():
        # insert moves from 0.193 to the push window's midpoint (0.192): the old
        # value split the 7.9 mm window 4.9 / 3.0, the midpoint splits it evenly.
        tol = 0.002 if name == "insert" else 0.001
        print(f"  {name}_hand_z {got[name]:.4f} (baseline {want:.3f})")
        if abs(got[name] - want) > tol:
            _fail(fails, f"{name}_hand_z {got[name]:.4f} is off the baseline {want:.3f} by > {tol}")

    # The derivation hooks, run on the baseline fracs, must give the baseline back.
    derived = OmegaConf.create(OmegaConf.to_container(task))
    derive_task_cfg(derived)
    for name, want in BASELINE_CRADLE_X.items():
        got_x = float(derived.cradles[name].x)
        if abs(got_x - want) > 1e-9:
            _fail(fails, f"derived cradles.{name}.x {got_x:+.4f} != baseline {want:+.4f}")
    for path, want in (("bar.length", 0.200), ("bar.grasp_offset", 0.075)):
        got_v = float(OmegaConf.select(derived, path))
        if abs(got_v - want) > 1e-9:
            _fail(fails, f"derived {path} {got_v:.4f} != baseline {want:.4f}")
    print("  derived length / grasp_offset / near cradle x reproduce the baseline")

    bad = [name for name, _, _, ok in layout.checks() if not ok]
    if bad:
        _fail(fails, f"baseline layout fails checks {bad}")
    for name, measured, limit, ok in layout.checks():
        print(f"  {name}: {measured:+.4f} vs {limit:+.4f} {'ok' if ok else 'FAIL'}")


def check_push_window(fails: list[str]) -> None:
    """Window width = across_flats - bar across_flats, once the bore alone sets it.

    Until 2026-09-08 the far cradle's ramp top raised the window's floor, leaving
    only ``across_flats - 0.0241``. The cradle is gone and the two near ones sit at
    the shaft's rest height, far below the bore, so the window is now the bore's
    own clearance top and bottom: ``across_flats - 0.018``, more than twice as wide
    at every hole size. That is what lets the hole shrink to 24 mm (the axis's new
    floor) instead of stopping at 29 mm.
    """
    for across_flats, want_mm in ((0.024, 6.0), (0.029, 11.0), (0.032, 14.0), (0.038, 20.0)):
        task = OmegaConf.load(CFG)
        task.aperture.across_flats = across_flats
        derive_task_cfg(task)
        lo, hi = BarThroughHoleLayout(task).push_window()
        width_mm = (hi - lo) * 1e3
        print(f"  across_flats {across_flats:.3f}: push window {width_mm:.2f} mm (expected ~{want_mm})")
        if abs(width_mm - want_mm) > 0.15:
            _fail(fails, f"push window at {across_flats} is {width_mm:.2f} mm, expected ~{want_mm}")


def check_worst_corner(fails: list[str]) -> None:
    """Shaft nearest the panel, panel nearest the shaft: the length range must
    close to [0.170, 0.204] and the grasp range to [0.060, 0.070]; the corner
    must still pass every check after derivation.

    The upper bound was 0.190 until 2026-09-08, when the panel went from 30 mm to
    16 mm thick so the open bore reads as open from an angled camera. A thinner
    panel puts its near face 7 mm further from the shaft, and the bound is
    "the shaft's near end must not reach that face" -- so the shaft may grow by
    twice that. A loosening, and the only place the thinner panel is visible in
    the numbers."""
    task = OmegaConf.load(CFG)
    task.bar.rest_x = -0.020
    task.panel.x = 0.100
    task.bar.length_frac = 0.0
    task.bar.grasp_frac = 1.0
    layout = BarThroughHoleLayout(task)
    lo, hi = layout.length_bounds()
    print(f"  worst corner length bounds [{lo:.3f}, {hi:.3f}]")
    if abs(lo - 0.170) > 1e-9 or abs(hi - 0.204) > 1e-9:
        _fail(fails, f"length bounds at worst corner {lo:.3f}..{hi:.3f}, expected 0.170..0.204")
    derive_task_cfg(task)
    glo, ghi = layout.grasp_offset_bounds()
    print(f"  shortest shaft grasp bounds [{glo:.3f}, {ghi:.3f}]")
    if abs(glo - 0.060) > 1e-9 or abs(ghi - 0.070) > 1e-9:
        _fail(fails, f"grasp bounds for the shortest shaft {glo:.3f}..{ghi:.3f}, expected 0.060..0.070")
    # The near grooves follow the shaft sideways; the far one stays on the bore's
    # centreline. A hard-coded 0.0 here dropped the shaft on the table at the
    # first corner with rest_y != 0 (GPU, 2026-09-04).
    task.bar.rest_y = 0.030
    for name, want in (("near_a", 0.030), ("near_b", 0.030), ("far", 0.0)):
        if abs(layout.cradle_y(name) - want) > 1e-12:
            _fail(fails, f"cradle_y({name}) {layout.cradle_y(name):+.3f} != {want:+.3f}")
    print("  cradle y: near blocks follow rest_y, far block on the panel centreline")
    bad = [name for name, _, _, ok in layout.checks() if not ok]
    if bad:
        _fail(fails, f"worst corner fails checks {bad}")
    for name, measured, limit, ok in layout.checks():
        print(f"  {name}: {measured:+.4f} vs {limit:+.4f} {'ok' if ok else 'FAIL'}")


def main() -> int:
    fails: list[str] = []
    for title, fn in (
        ("baseline", check_baseline),
        ("push window", check_push_window),
        ("worst corner", check_worst_corner),
    ):
        print(f"[{title}]")
        fn(fails)
    if fails:
        print(f"\n{len(fails)} failure(s)")
        return 1
    print("\nall bar_through_hole geometry checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
