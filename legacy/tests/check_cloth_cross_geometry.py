"""Cross fold metric, layer-order and two-axis anti-shortcut checks."""
from pathlib import Path
import sys

import numpy as np
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.tasks_legacy.deformation._cloth_cross_geometry import cross_dimensions, fold_flat_nodes, rounded_pleat, cross_spawn_checks
from topogym.tasks_legacy.deformation.cloth_unpleat import ClothCrossLayout, apply_layout_solver
from topogym.planning.cloth_unpleat_planner import plan_cloth_unpleat, CrossCornerExtender
from topogym.verification.cloth_unpleat_verifier import ClothUnpleatEvaluator


def main():
    with initialize_config_dir(version_base="1.3", config_dir=str(Path(__file__).resolve().parents[1] / "configs")):
        cfg = compose(config_name="cloth_unpleat_cross")
    # Same first step the demo takes: the cross runs under its own solver preset
    # (1 mm particles, 16 substeps), and reading the composed config without it
    # would measure a 4 mm band's numbers against a cross sheet's geometry.
    apply_layout_solver(cfg)
    task = cfg.task
    # The fixed entry reproduces the recorded acceptance, which is the corner
    # path with its corrective re-pull: 4/4 on random crosses against 0/6 for the
    # two-edge sequence (2026-09-11 A/B). Both paths are still exercised further
    # down as planner diagnostics; this pins which one the sample runs.
    assert str(task.cloth.cross.grasp) == "corner"
    assert bool(task.cloth.cross.repair_corners)
    dims = cross_dimensions(task)
    layout = ClothCrossLayout(task)
    layout.validate()
    for key, (length, _) in zip(("first", "second"), dims):
        s = np.linspace(0, length, 30001)
        x, z, _ = rounded_pleat(s, task.cloth.cross[key])
        np.testing.assert_allclose(np.hypot(np.diff(x), np.diff(z)).sum(), length, atol=1e-7)
    axes = [np.linspace(-d[0] / 2, d[0] / 2, 151) for d in dims]
    y, x = np.meshgrid(axes[0], axes[1])
    flat = np.c_[x.ravel() + task.cloth.center_x, y.ravel() + task.cloth.center_y,
                 np.full(x.size, task.cloth.z)]
    born = fold_flat_nodes(flat, task)
    assert all(row[3] for row in cross_spawn_checks(born, born, flat, task))
    # Both authored axes and all mirror combinations preserve the nine-panel
    # stack. This checks geometry only; it does not claim robot reachability.
    for material_axis in ("x", "y"):
        for first_flip in (-1, 1):
            for second_flip in (-1, 1):
                trial = OmegaConf.create(OmegaConf.to_container(task, resolve=True))
                trial.cloth.material_axis = material_axis
                trial.cloth.band_flip = first_flip
                trial.cloth.cross.flip = second_flip
                a = "xy".index(material_axis)
                reference = flat.copy()
                reference[:, a] = y.ravel() + float(trial.cloth[["center_x", "center_y"][a]])
                reference[:, 1-a] = x.ravel() + float(trial.cloth[["center_x", "center_y"][1-a]])
                folded = fold_flat_nodes(reference, trial)
                assert all(row[3] for row in cross_spawn_checks(folded, folded, reference, trial))
    collapsed = born.copy()
    collapsed[:, 2] = task.cloth.z
    gates = {row[0]: row[3] for row in cross_spawn_checks(born, collapsed, flat, task)}
    assert not gates["cross_layer_order"]
    drifting = born.copy()
    drifting[:, 0] *= 1.03
    gates = {row[0]: row[3] for row in cross_spawn_checks(born, drifting, flat, task)}
    assert not gates["unforced_span_drift"]
    # A fixed plan point inside both strips has three panels on each axis.
    # Verify all nine levels and reversed first-fold order in the middle stack.
    first, second = task.cloth.cross.first, task.cloth.cross.second
    coords = []
    for f in (first, second):
        a, w, r = float(f.lead), float(f.depth), float(f.radius)
        coords.append([a - w / 2, a + np.pi * r + w / 2,
                       a + 2 * np.pi * r + 1.5 * w])
    y, x = np.meshgrid(coords[0], coords[1])
    probes = np.c_[-(x.ravel() - dims[1][0] / 2) + task.cloth.center_x,
                   y.ravel() - dims[0][0] / 2 + task.cloth.center_y, np.full(9, task.cloth.z)]
    stacked = fold_flat_nodes(probes, task)
    # Layer-aware hinge radii let the inner and outer sheets take their own
    # arclength.  They therefore need not be exactly coincident at the
    # intersection before PBD settles them; the authored overlap window is the
    # meaningful birth invariant.
    assert np.ptp(stacked[:, :2], axis=0).max() <= min(float(first.depth), float(second.depth))
    levels = stacked[:, 2].reshape(3, 3)
    assert np.all(np.diff(levels[0]) > 0) and np.all(np.diff(levels[1]) < 0)
    # Layer-aware arcs intentionally perturb the exact neutral-surface heights;
    # only order and one-particle separation are invariants before settling.
    assert np.diff(np.sort(levels.ravel())).min() >= task.cloth.particle_size - 1e-12
    judge = ClothUnpleatEvaluator.from_config(task, material_nodes=flat)
    assert not judge.classify(born, born, table_z=0).is_terminal
    assert judge.classify(born, flat, table_z=0).is_terminal
    rotation = np.array([[1, -1], [1, 1]]) / np.sqrt(2)
    rotated = flat.copy()
    rotated[:, :2] = flat[:, :2] @ rotation.T
    assert judge.classify(born, rotated, table_z=0).is_terminal
    compressed = rotated.copy()
    compressed[:, :2] *= 0.75
    shortcut = judge.classify(born, compressed, table_z=0)
    assert not shortcut.gates["recovered_frac"] and not shortcut.gates["width_recovered_frac"]
    # Flattening or restoring only length must not pass the width gate.
    partial = born.copy()
    partial[:, 1], partial[:, 2] = flat[:, 1], flat[:, 2]
    verdict = judge.classify(born, partial, table_z=0)
    assert verdict.gates["recovered_frac"] and not verdict.gates["width_recovered_frac"]
    partial = born.copy()
    partial[:, 0], partial[:, 2] = flat[:, 0], flat[:, 2]
    verdict = judge.classify(born, partial, table_z=0)
    assert verdict.gates["width_recovered_frac"] and not verdict.gates["recovered_frac"]
    OmegaConf.update(task, "cloth.cross.grasp", "edges")
    legs, plan = plan_cloth_unpleat(layout)
    assert len(legs) == len(plan.subgoals) == 2
    assert layout.pull_direction(0) @ layout.pull_direction(1) == 0
    assert len(plan_cloth_unpleat(layout, motion="single_pull")[0]) == 1
    OmegaConf.update(task, "cloth.cross.grasp", "corner", force_add=True)
    corner = ClothCrossLayout(task)
    corner.material_nodes = flat
    corner.validate()
    grasp = corner.observe(born)
    legs, plan = plan_cloth_unpleat(corner)
    assert len(legs) == 1 and plan.waypoint_plan.metadata["continuous_grasp"]
    np.testing.assert_allclose(np.asarray(legs[0][-1].position) - grasp,
                               sum(corner.pull_distance(i) * corner.pull_direction(i) for i in range(2)))
    extender = CrossCornerExtender(corner, born, legs[0], index=1, start_point=grasp,
                                  material_nodes=flat, max_scale=1.5)
    assert extender(flat) is None
    partial = flat.copy()
    partial[:, 0] *= 0.8
    extra = extender(partial)
    assert extra and extra[0].metadata["axis"] == 0
    OmegaConf.update(task, "cloth.cross.corner_path", "diagonal", force_add=True)
    diagonal, _ = plan_cloth_unpleat(corner)
    direction = np.asarray(diagonal[0][-1].position) - grasp
    for point in diagonal[0]:
        delta = np.asarray(point.position) - grasp
        assert np.linalg.norm(np.cross(direction, delta)) < 1e-12
    OmegaConf.update(task, "cloth.cross.pull_lift", 0.03, force_add=True)
    peeled, _ = plan_cloth_unpleat(corner)
    assert peeled[0][0].position[2] > grasp[2]
    assert peeled[0][-1].position[2] == grasp[2]
    print("PASS cross arclength, nine-layer order, both-axis recovery, orthogonal sequence")


if __name__ == "__main__":
    main()
