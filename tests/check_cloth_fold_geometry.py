"""Offline gate for the cloth_fold judges (docx 1.1).

Runs the REAL evaluator against the REAL task config on synthetic cloth, so a
threshold edit that stops separating a good fold from a bad one is caught without
a GPU run (a full fold episode is a 4-minute scene build plus the motion).

What it proves:
  - a clean fold passes every gate, and the readings land where the measured run
    put them (two layers everywhere, outline on target, crease on the line);
  - the two wrong executions docx 1.1 names -- bunching the cloth up, and pushing
    it around without lifting -- fail, and fail on the gate that is supposed to
    catch them rather than by accident;
  - **the crease gate earns its place**: a fold that is geometrically perfect but
    put down 12 mm off still fails, while coverage and layer count both pass it.
    That case is why docx lists 折线位置误差 as a separate criterion, and it is
    the one a single area threshold cannot see;
  - the fold target is half the cloth's own outline, not a box around it;
  - the config's thresholds sit between the measured right and wrong answers, so
    each gate has room on both sides rather than clinging to one.

    python tests/check_cloth_fold_geometry.py

Needs numpy + PyYAML only (no hydra, no genesis): the evaluator is plain NumPy
over particle arrays, which is the point of keeping it independent of the scene.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]

# Loaded by path, not by `from topogym.verification... import`: every other
# verifier in that package imports its task module, which imports Genesis, so the
# package __init__ would drag the whole simulator in. This one is deliberately
# plain NumPy, and loading the file directly is what keeps this check runnable
# without a GPU environment.
_spec = importlib.util.spec_from_file_location(
    "cloth_fold_verifier", REPO / "topogym/verification/cloth_fold_verifier.py"
)
_verifier = importlib.util.module_from_spec(_spec)
# Registered before exec: `@dataclass` resolves string annotations through
# `sys.modules[cls.__module__]`, which is absent for a module loaded by path.
sys.modules[_spec.name] = _verifier
_spec.loader.exec_module(_verifier)
ClothFoldEvaluator = _verifier.ClothFoldEvaluator
fold_targets = _verifier.fold_targets
fold_target_cells = _verifier.fold_target_cells
occupied_cells = _verifier.occupied_cells

TASK_CFG = REPO / "configs/task_configs/cloth_fold_topogym_tabletop_v1.yaml"

TABLE_Z = 0.0
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def rest_sheet(cfg) -> np.ndarray:
    """The cloth as Genesis lays it out: a flat grid one particle-radius up.

    65x65 rather than the config's 33x33 because Genesis subdivides the control
    mesh once -- that is the combination the spike measured as order-preserving,
    and vertex order is what makes the crease measurable at all.
    """

    size = np.asarray(cfg["cloth"]["size"], dtype=float)
    centre = np.asarray(cfg["cloth"]["center"], dtype=float)
    side = 2 * int(cfg["cloth"]["mesh"]["cols"]) - 1
    xs = np.linspace(centre[0] - size[0] / 2, centre[0] + size[0] / 2, side)
    ys = np.linspace(centre[1] - size[1] / 2, centre[1] + size[1] / 2, side)
    grid_x, grid_y = np.meshgrid(xs, ys, indexing="ij")
    z = np.full(grid_x.size, TABLE_Z + float(cfg["cloth"]["z"]))
    return np.column_stack([grid_x.ravel(), grid_y.ravel(), z])


def folded(rest: np.ndarray, fold_point, normal, thickness: float) -> np.ndarray:
    """Mirror the lifted half across the fold line and lay it on top."""

    out = rest.copy()
    along = (rest[:, :2] - np.asarray(fold_point, dtype=float)) @ np.asarray(
        normal, dtype=float
    )
    lifted = along > 0.0
    out[lifted, :2] -= 2.0 * along[lifted, None] * np.asarray(normal, dtype=float)
    out[lifted, 2] += thickness
    return out


def crumpled(rest: np.ndarray, seed: int = 0) -> np.ndarray:
    """Gathered into a bunch: pulled in towards the middle, piled up, no order."""

    rng = np.random.default_rng(seed)
    centre = rest[:, :2].mean(axis=0)
    out = rest.copy()
    out[:, :2] = centre + (rest[:, :2] - centre) * 0.45
    out[:, 2] = TABLE_Z + rng.uniform(0.002, 0.030, size=len(rest))
    return out


def dragged(rest: np.ndarray, fold_point, normal, thickness: float) -> np.ndarray:
    """Pushed along without being lifted: the outline moves, the sheet wrinkles.

    Half the material ends up roughly where a fold would put it, but it stays in
    one layer and the surface buckles instead of creasing.
    """

    rng = np.random.default_rng(1)
    out = rest.copy()
    along = (rest[:, :2] - np.asarray(fold_point, dtype=float)) @ np.asarray(
        normal, dtype=float
    )
    pushed = along > 0.0
    out[pushed, :2] -= 1.1 * along[pushed, None] * np.asarray(normal, dtype=float)
    out[:, 2] = TABLE_Z + 0.002 + rng.uniform(0.0, 0.006, size=len(rest))
    return out


def lumped(nodes: np.ndarray, seed: int = 7) -> np.ndarray:
    """A fold that is right nearly everywhere, with one region badly wrong.

    The reason the mean particle distance cannot stand alone: this reads 2.6 mm
    on average, comfortably inside any threshold worth setting, while a twentieth
    of the cloth is 60 mm from where it belongs.
    """

    rng = np.random.default_rng(seed)
    out = nodes.copy()
    picked = rng.choice(len(out), size=int(0.05 * len(out)), replace=False)
    out[picked, :2] += rng.normal(0.0, 0.043, (len(picked), 2))
    return out


def main(argv=None) -> int:
    cfg = yaml.safe_load(TASK_CFG.read_text(encoding="utf-8"))
    evaluator = ClothFoldEvaluator.from_config(cfg)
    limits = evaluator.thresholds

    rest = rest_sheet(cfg)
    centre = np.asarray(cfg["cloth"]["center"], dtype=float)
    # docx 1.1: grasp the middle of the right edge and take it to the far side,
    # so the fold line is the cloth's centre line and the normal points +x.
    fold_point = centre
    normal = np.array([1.0, 0.0])
    thickness = float(cfg["cloth"]["particle_size"])
    cell = evaluator.cell

    print(f"config: {TASK_CFG.relative_to(REPO)}")
    print(
        f"cloth {cfg['cloth']['size']} particles={len(rest)} cell_mm={cell * 1e3:.1f} "
        f"fold_line x={fold_point[0]:+.3f}"
    )

    print("\n目标 footprint 是布自己轮廓的一半，不是外接矩形")
    target = fold_target_cells(rest, fold_point, normal, cell)
    whole = occupied_cells(rest, cell)
    ratio = len(target) / len(whole)
    check(
        "target is half the rest outline",
        0.45 <= ratio <= 0.55,
        f"{len(target)}/{len(whole)} cells = {ratio:.3f}",
    )

    cases = {
        "perfect": folded(rest, fold_point, normal, thickness),
        "unfolded": rest.copy(),
        "crumpled": crumpled(rest),
        "dragged": dragged(rest, fold_point, normal, thickness),
        # Geometrically a clean fold, but the whole sheet ended up 12 mm off.
        "slid": folded(rest, fold_point, normal, thickness) + np.array([0.012, 0.0, 0.0]),
        # 95% of the sheet perfect, 5% balled up. The case that decides whether
        # the companion to the mean is the right shape of measure.
        "lumped": lumped(folded(rest, fold_point, normal, thickness)),
    }
    states = {}
    print("\n六种终态的读数")
    for name, nodes in cases.items():
        state = evaluator.classify(
            rest, nodes, table_z=TABLE_Z, fold_point=fold_point, fold_normal=normal
        )
        states[name] = state
        print(f"  {name:9s} {state.summary()}")

    print("\n判定")
    check("a clean fold passes", states["perfect"].is_terminal)
    for name in ("unfolded", "crumpled", "dragged", "slid", "lumped"):
        check(f"{name} is rejected", not states[name].is_terminal)

    print("\n每种错法是被该管它的那一条拦住的")
    check(
        "crumpling is caught by the layer count as well as by distance",
        not states["crumpled"].gates["two_layer_frac"],
        f"two_layer_frac={states['crumpled'].two_layer_frac:.3f} "
        f"< {limits.two_layer_frac_min}",
    )
    check(
        "dragging is caught by the layer count as well as by distance",
        not states["dragged"].gates["two_layer_frac"],
        f"two_layer_frac={states['dragged'].two_layer_frac:.3f}",
    )
    # Putting the targets in world coordinates is what makes this work: the
    # pairwise form SoftGym uses is blind to a bodily shift and needs a separate
    # displacement penalty to see it.
    slid = states["slid"]
    check(
        "a fold put down in the wrong place is caught by distance alone",
        not slid.gates["particle_error_mean"]
        and slid.gates["two_layer_frac"]
        and slid.gates["particle_off_target_frac"],
        f"mean={slid.particle_error_mean * 1e3:.1f}mm over the "
        f"{limits.particle_error_mean_max * 1e3:.1f}mm limit, while "
        f"two_layer_frac={slid.two_layer_frac:.3f} and "
        f"off_target_frac={slid.particle_off_target_frac:.3f} both pass",
    )
    # The demoted readings still say WHICH failure it was, which is why they are
    # still computed.
    check(
        "the demoted readings still identify the failure mode",
        states["crumpled"].max_layers > 3
        and slid.crease_offset > 0.01
        and states["unfolded"].fold_iou < 0.55,
        f"crumpled stacks {states['crumpled'].max_layers} deep; "
        f"slid's crease is {slid.crease_offset * 1e3:.1f}mm off; "
        f"unfolded covers the wrong outline (IoU {states['unfolded'].fold_iou:.3f})",
    )

    print("\n读数落在该落的地方")
    good = states["perfect"]
    check(
        "a clean fold puts two layers over essentially all of its footprint",
        good.two_layer_frac >= 0.95,
        f"two_layer_frac={good.two_layer_frac:.3f}",
    )
    check(
        "a clean fold lands on the target outline",
        good.fold_iou >= 0.95,
        f"fold_iou={good.fold_iou:.3f}",
    )
    check(
        "a clean fold's crease sits on the fold line and is straight",
        good.crease_offset < 1e-4 and good.crease_straightness < 1e-4,
        f"offset={good.crease_offset * 1e3:.3f}mm "
        f"straightness={good.crease_straightness * 1e3:.3f}mm",
    )
    check(
        "the half that stays put is measured as not having moved",
        good.anchor_shift < 1e-6,
        f"anchor_shift={good.anchor_shift * 1e3:.3f}mm",
    )
    check(
        "the displaced fold's crease offset reads the displacement",
        abs(slid.crease_offset - 0.012) < 1e-4,
        f"{slid.crease_offset * 1e3:.2f}mm for a 12.00mm shift",
    )

    print("\n没有一条判据是多余的")
    # Not "every gate rejects every wrong answer" -- they are a conjunction
    # precisely because each one sees a different failure. `dragged` puts the
    # outline almost exactly on target (fold_iou 0.94) and is caught only by the
    # layer count; `slid` stacks two clean layers and is caught only by the
    # crease. What has to hold is that no gate is dead weight.
    wrong = ("unfolded", "crumpled", "dragged", "slid", "lumped")
    for gate in good.gates:
        decisive = [name for name in wrong if not states[name].gates[gate]]
        check(
            f"{gate} is the deciding judge for at least one wrong answer",
            bool(decisive),
            f"catches {', '.join(decisive) if decisive else 'nothing'}",
        )
    for name in wrong:
        rejecting = [g for g, ok in states[name].gates.items() if not ok]
        check(
            f"{name} is rejected on a stated criterion",
            bool(rejecting),
            f"fails {', '.join(rejecting)}",
        )

    print("\n层数是真的在数层，不是「有没有断层」")
    # The reading that makes bunching separable at all: a fold is two layers deep
    # everywhere, a pile is many. Counting "is there a gap" instead would score
    # the pile as two-layered, which is docx 1.1's first named shortcut.
    check(
        "a fold is exactly two deep, a pile is deeper",
        good.max_layers == 2 and states["crumpled"].max_layers > 3,
        f"perfect={good.max_layers} crumpled={states['crumpled'].max_layers} "
        f"unfolded={states['unfolded'].max_layers}",
    )
    check(
        "a flat sheet is one deep",
        states["unfolded"].max_layers == 1,
    )
    check(
        "bunching shows up as cells stacked more than two deep",
        states["crumpled"].over_layer_cells > 0.8 * states["crumpled"].covered_cells
        and good.over_layer_cells == 0,
        f"crumpled {states['crumpled'].over_layer_cells}/"
        f"{states['crumpled'].covered_cells} cells, perfect {good.over_layer_cells}",
    )

    print()
    if failures:
        print(f"== 失败 {len(failures)} 项 ==")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("== 通过：主判据与结构判据合起来挡住全部五种错法 ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
