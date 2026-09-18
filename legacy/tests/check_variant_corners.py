"""Boundary-value gate for a task's variation envelope, and the corner manifest
the GPU harness runs.

``tests/check_variant_rng.py`` draws interior points of the envelope; the random
sweeps (``bash_scripts/tests/<task>_variation_sweep.sh``) run ten of them through
physics. Neither reaches the envelope's boundary, and the solvability checks are
tightest there (reach, timing slack, bypass gap). This script builds the
boundary explicitly -- classic boundary-value testing over the domain
randomization's parameter box:

* every ``uniform`` axis at its two endpoints, every ``choice`` axis at each of
  its values, ``distinct_choice`` axes fixed to their first two keys, and a
  ``spaced_pair`` axis walked over the named pairs in ``PAIRS`` below (a pair is
  not a box, so its corners are chosen by hand);
* the full product of those, deduplicated -- 2^k times the discrete combinations.

Each corner goes through the same ``derived`` and ``validate`` hooks the task's
yaml names, then ``Layout.checks()`` prints every margin. A corner the hooks
reject or a check fails is a failure: the declared envelope has an infeasible
vertex. Finally every corner is composed through Hydra exactly as the harness
runs it (``run.randomize_layout=false`` plus ``task.<path>=<value>`` overrides,
the demo's fixed-layout path) and the composed layout must reproduce the same
readings, so the manifest is known to feed the demo what was checked here.

Test-only by construction: no ``VariantRng``, no ``randomize_task_cfg``; the
production sampler is untouched and the seed -> variant mapping cannot move.

    python tests/check_variant_corners.py                       # all registered tasks
    python tests/check_variant_corners.py --task gate_cage_ball
    python tests/check_variant_corners.py --task diverter_route_ball --manifest runs/x/corners.tsv

Needs the project venv (the task modules import Genesis; nothing is built).
Exits non-zero if any corner is rejected, fails a check, or does not survive
Hydra composition unchanged.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

from omegaconf import OmegaConf

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import topogym.generation.layout_randomization as lr  # noqa: E402

CONFIGS = REPO / "configs"
TASK_CONFIGS = CONFIGS / "task_configs"


@dataclass(frozen=True)
class TaskSpec:
    yaml: str  # task config under configs/task_configs/
    physical_config: str  # top-level Hydra config the physical demo runs
    layout: str  # "module:Class"
    pairs: dict  # spaced_pair path tuple -> {name: (low, high)}
    checks: object = None  # callable(layout) -> [(name, measured, limit, ok)]; None = layout.checks()
    # Axes that only matter for one value of a choice axis (band_untwist: each
    # shape reads its own block). ``(choice path, shared paths, {value: path
    # prefix})``: one stratum per value, varying only the shared axes and that
    # value's block; the other blocks stay at their yaml defaults. None = one
    # product over every axis.
    strata: object = None


def _linkbar_checks(layout) -> list[tuple[str, float, float, bool]]:
    """The four inequalities ``LinkbarRotateLayout.validate`` raises on, as margins,
    plus the sweep the oracle has to make (the +/-90 rail is the working area)."""
    import math

    cfg = layout.cfg
    half = float(cfg.zones.half_width_deg)
    keep_out = half + float(cfg.zones.pin_start_margin_deg)
    rail_lo, rail_hi = float(cfg.rail.start_deg), float(cfg.rail.end_deg)
    init = float(cfg.linkbar.init_angle_deg)
    c1, c2 = (math.degrees(layout.zone_angle(z)) for z in ("color_1", "color_2"))
    on_rail = min(c1 - half - rail_lo, rail_hi - c2 - half)
    pin_clear = min(abs(c1 - init), abs(c2 - init)) - keep_out
    separation = abs(c2 - c1) - 2.0 * half
    target = math.degrees(layout.zone_angle(layout.target_zone()))
    sweep = abs(target - init)
    return [
        ("zones_on_rail", on_rail, 0.0, on_rail >= -1e-9),
        ("pin_start_clear", pin_clear, 0.0, pin_clear >= -1e-9),
        ("zone_separation", separation, 0.0, separation >= -1e-9),
        ("sweep_deg", sweep, rail_hi - rail_lo, sweep <= rail_hi - rail_lo + 1e-9),
    ]


# Named corners for the one spaced_pair axis (linkbar's two zone centres on the
# +/-90 rail, 12 deg half width, centres >= 24 apart, color_1 the smaller).
# Chosen for what the sweep must survive: the rail's ends (longest sweep),
# touching zones on either side (the pin must stop on the near one, 24 deg wide),
# both zones straddling the start (init span cut to exactly [-15, 15] minus
# nothing), and both on one side far out (93 deg sweep from init -15 to +78).
# Updated 2026-09-10 with the half width: the bounds are the rail's +/-90 minus
# the half width, and touching means centres exactly 2 * half_width apart.
_LINKBAR_PAIRS = {
    ("zones.color_1.angle_deg", "zones.color_2.angle_deg"): {
        "rail_ends": (-78.0, 78.0),
        "touching_pos": (30.0, 54.0),
        "touching_neg": (-54.0, -30.0),
        "straddle_near": (-25.0, 25.0),
        "same_side_far": (54.0, 78.0),
    }
}

TASKS = {
    "linkbar_rotate_to_zone": TaskSpec(
        yaml="linkbar_rotate_to_zone_topogym_tabletop_v1.yaml",
        physical_config="linkbar_rotate_to_zone_rotate",
        layout="topogym.tasks_legacy.connectivity.linkbar_rotate_to_zone:LinkbarRotateLayout",
        pairs=_LINKBAR_PAIRS,
        checks=_linkbar_checks,  # validate() only raises; no checks() yet
    ),
    "diverter_route_ball": TaskSpec(
        yaml="diverter_route_ball_topogym_tabletop_v1.yaml",
        physical_config="diverter_route_ball_route",
        layout="topogym.tasks_legacy.connectivity.diverter_route_ball:DiverterRouteBallLayout",
        pairs={},
    ),
    "gate_cage_ball": TaskSpec(
        yaml="gate_cage_ball_topogym_tabletop_v1.yaml",
        physical_config="gate_cage_ball_gate",
        layout="topogym.tasks_legacy.connectivity.gate_cage_ball:GateCageBallLayout",
        pairs={},
    ),
    # Four spawn shapes, each with its own block of axes: strata per band.shape.
    # Corners: 256 (eight) + 256 (six) + 1024 (twist) + 256 (curls) = 1792; the
    # physics layer is a covering array per stratum (FEM rope, 6-15 min a cell).
    "band_untwist": TaskSpec(
        yaml="band_untwist_topogym_tabletop_v1.yaml",
        physical_config="band_untwist_pinch",
        layout="topogym.tasks_legacy.entangle.band_untwist:BandUntwistLayout",
        pairs={},
        strata=(
            "band.shape",
            ("band.heading_deg", "band.center_x_frac", "band.center_y_frac"),
            {"eight": "band.eight.", "six": "band.six.", "twist": "band.twist.", "curls": "band.curls."},
        ),
    ),
    # 24,576 corners since the 2026-09-11 rework (rope count x crossing count x
    # 12 word indices x nine continuous axes), so the physics sweep runs a
    # covering array (4-way: 244 rows); FEM rope, 2-5 moves per cell. Crossing
    # positions and the left-right shift are derived leaves.
    "swap_crossing_sign": TaskSpec(
        yaml="swap_crossing_sign_topogym_tabletop_v1.yaml",
        physical_config="swap_crossing_sign_pinch",
        layout="topogym.tasks_legacy.entangle.swap_crossing_sign:SwapCrossingSignLayout",
        pairs={},
    ),
    # 32 corners; rigid bodies only, seconds to a couple of minutes per GPU cell,
    # so the sweep runs them all.
    "unlink_c_ring": TaskSpec(
        yaml="unlink_c_ring_topogym_tabletop_v1.yaml",
        physical_config="unlink_c_ring_extract",
        layout="topogym.tasks_legacy.entangle.unlink_c_ring:UnlinkCRingLayout",
        pairs={},
    ),
    # 64 corners (six continuous axes); rigid bodies only, ~10-20 s per GPU cell.
    "bar_through_hole": TaskSpec(
        yaml="bar_through_hole_topogym_tabletop_v1.yaml",
        physical_config="bar_through_hole",
        layout="topogym.tasks_legacy.routing.bar_through_hole:BarThroughHoleLayout",
        pairs={},
    ),
    # 1536 corners (eight continuous axes x 3 turn counts x 2 senses); FEM rope,
    # 7-18 min per GPU cell, so the physics sweep runs a CORNERS= subset only.
    "rope_unwinding": TaskSpec(
        yaml="rope_unwinding_topogym_tabletop_v1.yaml",
        physical_config="rope_unwinding",
        layout="topogym.tasks_legacy.routing.rope_unwinding:RopeUnwindingLayout",
        pairs={},
    ),
    # 1536 corners (eight continuous axes x 3 turn counts x 2 senses); FEM rope,
    # 10-40 min per GPU cell (one to three turns), so the physics sweep runs a
    # CORNERS= subset only.
    "rope_winding": TaskSpec(
        yaml="rope_winding_topogym_tabletop_v1.yaml",
        physical_config="rope_winding",
        layout="topogym.tasks_legacy.routing.rope_winding:RopeWindingLayout",
        pairs={},
    ),
    # 256 corners (seven continuous axes x 2 start posts); FEM closed band,
    # ~5-10 min per GPU cell (carry = 2000 steps), so the physics sweep runs a
    # CORNERS= subset only.
    "ring_transfer": TaskSpec(
        yaml="ring_transfer_topogym_tabletop_v1.yaml",
        physical_config="ring_transfer",
        layout="topogym.tasks_legacy.routing.ring_transfer:RingTransferLayout",
        pairs={},
    ),
    # Three layouts, each a different scene: a band with one pleat, a band with
    # two parallel pleats, and a square sheet folded once each way. Most axes
    # belong to only one of them, so strata per `cloth.pleat.layout` --
    # single 768 + parallel 6144 + cross 4096 = 11,008 corners, against the
    # 2.4 million the full product of all 20 axes would give. PBD cloth; a band
    # cell is about a minute, a cross cell 10-25 (16x the particles, 4x the
    # substeps), so the physics sweep runs a CORNERS= subset or a covering array.
    # `layout_for` picks the band or the cross Layout off the drawn value; both
    # take the task config alone (origin defaults to zero, every row is
    # task-frame arithmetic).
    "cloth_unpleat": TaskSpec(
        yaml="cloth_unpleat_topogym_tabletop_v1.yaml",
        physical_config="cloth_unpleat",
        layout="topogym.tasks_legacy.deformation.cloth_unpleat:layout_for",
        pairs={},
        strata=(
            "cloth.pleat.layout",
            ("cloth.band_flip", "cloth.center_x_frac", "cloth.center_y_frac",
             "physical.pull_scale", "grasp.edge_inset_frac"),
            {
                "single": ("cloth.pleat.a.", "cloth.lead_frac", "cloth.tail_frac"),
                "parallel": ("cloth.pleat.", "cloth.lead_frac", "cloth.tail_frac"),
                "cross": ("cloth.cross.",),
            },
        ),
    ),
    # 96 corners (two pull sides x three turn counts x four continuous axes);
    # PBD cloth, about 20 s per GPU cell (cloth_unpleat measured), so the
    # physics sweep can run them all. The layer pitch, the bar's along-axis
    # position and the start-state guard are derived. The layout takes the task
    # config alone (origin defaults to zero).
    "cloth_unroll": TaskSpec(
        yaml="cloth_unroll_topogym_tabletop_v1.yaml",
        physical_config="cloth_unroll",
        layout="topogym.tasks_legacy.deformation.cloth_unroll:ClothUnrollLayout",
        pairs={},
    ),
    # 96 corners (four grasp corners x three fold fractions x three continuous axes);
    # PBD cloth, expected 20-40 s per GPU cell, so the physics sweep can run
    # them all. The sheet's x position is derived. The layout takes the task
    # config alone (origin defaults to zero).
    "cloth_fold": TaskSpec(
        yaml="cloth_fold_topogym_tabletop_v1.yaml",
        physical_config="cloth_fold",
        layout="topogym.tasks_legacy.deformation.cloth_fold:ClothFoldLayout",
        pairs={},
    ),
}


@dataclass(frozen=True)
class Corner:
    name: str
    values: tuple  # ((path, value), ...) over every sampled path


# ------------------------------------------------------------------ corners


def _axis_values(task_cfg, directives, pairs) -> list[tuple[tuple[str, ...], list]]:
    """Per axis: the paths it fills and the list of value tuples to visit."""
    axes = []
    for d in directives:
        if isinstance(d, lr._ScalarJitter):
            axes.append(((d.path,), [(float(d.lo),), (float(d.hi),)]))
        elif isinstance(d, lr._ChoiceJitter):
            axes.append(((d.path,), [(v,) for v in d.values]))
        elif isinstance(d, lr._DistinctChoiceJitter):
            keys = list(lr._get_node(task_cfg, d.keys_of).keys())
            axes.append((tuple(d.paths), [tuple(keys[: len(d.paths)])]))
        elif isinstance(d, lr._SpacedPairJitter):
            named = pairs.get(tuple(d.paths))
            if not named:
                raise SystemExit(f"no named pairs for spaced_pair axis {d.paths}; add them to PAIRS")
            for name, (lo, hi) in named.items():
                if not (d.lo <= lo and hi <= d.hi and hi - lo >= d.min_gap):
                    raise SystemExit(f"pair {name}={lo, hi} is outside the axis [{d.lo}, {d.hi}] / min_gap {d.min_gap}")
            axes.append((tuple(d.paths), [(name, lo, hi) for name, (lo, hi) in named.items()]))
    return axes


def _short_names(paths: list[str]) -> dict[str, str]:
    """Shortest dotted suffix that is unique among ``paths``."""
    out = {}
    for p in paths:
        parts = p.split(".")
        for n in range(min(2, len(parts)), len(parts) + 1):
            suffix = ".".join(parts[-n:])
            if sum(1 for q in paths if q.endswith(suffix) and (q == suffix or q.endswith("." + suffix))) == 1:
                out[p] = suffix
                break
        else:
            out[p] = p
    return out


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(float(value))
    return str(value)


def _assemble(axes, combos) -> list[Corner]:
    """Turn chosen value tuples into `Corner`s, de-duplicated."""

    all_paths = [p for paths, _ in axes for p in paths]
    short = _short_names(all_paths)
    corners: list[Corner] = []
    seen = set()
    for combo in combos:
        assigned: list[tuple[str, object]] = []
        labels: list[str] = []
        for (paths, _), chosen in zip(axes, combo):
            if len(chosen) == len(paths) + 1:  # named pair: (name, lo, hi)
                labels.append(f"{'+'.join(short[p] for p in paths)}={chosen[0]}")
                chosen = chosen[1:]
            else:
                labels.extend(f"{short[p]}={_fmt(v)}" for p, v in zip(paths, chosen))
            assigned.extend(zip(paths, chosen))
        key = tuple(assigned)
        if key in seen:
            continue
        seen.add(key)
        corners.append(Corner(",".join(labels), key))
    return corners


def build_corners(task_cfg, directives, pairs) -> list[Corner]:
    axes = _axis_values(task_cfg, directives, pairs)
    return _assemble(axes, itertools.product(*(values for _, values in axes)))


def build_covering(task_cfg, directives, pairs, strength: int = 4) -> list[Corner]:
    """A ``strength``-way covering array over the same axis values as `build_corners`.

    Same cells, far fewer of them: every combination of any ``strength`` axes'
    values appears at least once, instead of every combination of ALL of them.
    Once a task's axis count puts the full product past what a GPU can run in a
    night, this is the set that still supports a statement about coverage --
    see `tests/covering_array.py` for why ``strength`` may be small.
    """

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from covering_array import build as build_array

    axes = _axis_values(task_cfg, directives, pairs)
    rows = build_array([len(values) for _, values in axes], strength)
    return _assemble(axes, [
        [values[pick] for (_, values), pick in zip(axes, row)] for row in rows
    ])


def build_strata(task_cfg, directives, spec, plan: str, strength: int) -> list[Corner]:
    """`build_corners` / `build_covering` once per value of the strata choice
    axis, over the shared axes plus that value's block only; the value itself
    is fixed and named first."""

    choice_path, shared, blocks = spec.strata

    # The stratum leaf is pinned below, never enumerated: cloth_unpleat's
    # `parallel` block is the prefix `cloth.pleat.`, which also matches
    # `cloth.pleat.layout` itself and would otherwise multiply that stratum by
    # the three layouts (18,432 corners instead of 6,144, each naming a layout
    # twice). band_untwist never hit it -- `band.shape` is outside every block.

    def paths_of(d) -> tuple[str, ...]:
        return tuple(getattr(d, "paths", None) or (getattr(d, "path", None),))

    corners: list[Corner] = []
    for value, prefixes in blocks.items():
        # One string or several: cloth_unpleat's band layouts own two branches of
        # the tree (`cloth.pleat.` and the two end runs), not one subtree.
        prefixes = (prefixes,) if isinstance(prefixes, str) else tuple(prefixes)
        keep = [
            d for d in directives
            if not isinstance(d, (lr._Derived, lr._Validate))
            and choice_path not in paths_of(d)
            and all(p is not None and (p in shared or p.startswith(prefixes)) for p in paths_of(d))
        ]
        layer = (
            build_corners(task_cfg, keep, spec.pairs)
            if plan == "corners"
            else build_covering(task_cfg, keep, spec.pairs, strength)
        )
        for corner in layer:
            corners.append(Corner(f"{value}:{corner.name}", ((choice_path, value),) + corner.values))
    return corners


# ------------------------------------------------------------------ resolve


def _leaves(node, prefix="") -> dict:
    """Dotted path -> value over every leaf, without resolving interpolations
    (a task yaml may carry ``${prefabs...}`` leaves that only resolve under Hydra)."""
    if OmegaConf.is_config(node):
        node = OmegaConf.to_container(node, resolve=False)
    out = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(_leaves(v, f"{prefix}{k}."))
    elif isinstance(node, list):
        out[prefix[:-1]] = tuple(node)
    else:
        out[prefix[:-1]] = node
    return out


def resolve_corner(base_task_cfg, corner: Corner, derive_fn, validate_fn):
    """Write the corner's values, run the yaml's hooks; return (task_cfg, derived paths)."""
    task = OmegaConf.create(OmegaConf.to_container(base_task_cfg, resolve=False))
    for path, value in corner.values:
        OmegaConf.update(task, path, lr._same_type(lr._get_node(task, path), value), merge=False)
    before = _leaves(task)
    if derive_fn is not None:
        derive_fn(task)
    derived = [p for p, v in _leaves(task).items() if p not in before or before[p] != v]
    if validate_fn is not None:
        validate_fn(task)
    return task, derived


def overrides_for(task, corner: Corner, derived: list[str]) -> list[str]:
    """Hydra tokens that rebuild this corner on the demo's fixed-layout path."""
    tokens = [f"task.{p}={_fmt(v)}" for p, v in corner.values]
    tokens += [f"task.{p}={_fmt(lr._get_node(task, p))}" for p in derived]
    return tokens


def margins_line(checks) -> str:
    return " ".join(f"{name}={measured:+.4f}/{limit:+.4f}/{'ok' if ok else 'FAIL'}"
                    for name, measured, limit, ok in checks)


# ------------------------------------------------------------------ main


def check_task(task_id: str, manifest_rows: list[str], *, plan: str = "corners",
               strength: int = 4) -> list[str]:
    spec = TASKS[task_id]
    base = OmegaConf.load(TASK_CONFIGS / spec.yaml)
    directives = lr._parse_directives(base)
    if not directives:
        return [f"{task_id}: no variation block"]
    derived_d = next((d for d in directives if isinstance(d, lr._Derived)), None)
    validate_d = next((d for d in directives if isinstance(d, lr._Validate)), None)
    derive_fn = lr._resolve_fn(derived_d.fn) if derived_d else None
    validate_fn = lr._resolve_fn(validate_d.fn) if validate_d else None
    Layout = lr._resolve_fn(spec.layout)
    run_checks = spec.checks or (lambda layout: layout.checks())

    corners = build_strata(base, directives, spec, plan, strength) if spec.strata else (
        build_corners(base, directives, spec.pairs)
        if plan == "corners"
        else build_covering(base, directives, spec.pairs, strength)
    )
    sampled = set(lr.sampled_leaves(base))
    covered = {p for c in corners for p, _ in c.values}
    fails: list[str] = []
    if covered != sampled:
        fails.append(f"corner paths {sorted(covered ^ sampled)} do not match sampled_leaves")

    from hydra import compose, initialize_config_dir

    resolved = []
    with initialize_config_dir(version_base="1.3", config_dir=str(CONFIGS)):
        for idx, corner in enumerate(corners):
            try:
                task, derived = resolve_corner(base, corner, derive_fn, validate_fn)
            except ValueError as exc:
                fails.append(f"c{idx:03d} {corner.name}: rejected: {str(exc).splitlines()[0][:100]}")
                print(f"  c{idx:03d} {corner.name}: REJECT {str(exc).splitlines()[0][:80]}", flush=True)
                continue
            checks = run_checks(Layout(task))
            line = margins_line(checks)
            print(f"  c{idx:03d} {corner.name}: {line}", flush=True)
            bad = [name for name, _, _, ok in checks if not ok]
            if bad:
                fails.append(f"c{idx:03d} {corner.name}: checks failed {bad}")

            # The harness's exact path: fixed layout + overrides, through Hydra.
            tokens = overrides_for(task, corner, derived)
            cfg = compose(config_name=spec.physical_config,
                          overrides=["run.randomize_layout=false", *tokens])
            composed = run_checks(Layout(cfg.task))
            for (n1, m1, l1, ok1), (n2, m2, l2, ok2) in zip(checks, composed):
                if n1 != n2 or abs(m1 - m2) > 1e-9 or abs(l1 - l2) > 1e-9 or ok1 != ok2:
                    fails.append(f"c{idx:03d} {corner.name}: composed {n2}={m2:+.4f} != offline {m1:+.4f}")
                    break
            resolved.append((idx, corner, tokens, line))

    for idx, corner, tokens, line in resolved:
        manifest_rows.append("\t".join((task_id, f"c{idx:03d}", corner.name, " ".join(tokens), line)))
    print(f"  {task_id}: {plan} plan, {len(corners)} cells, {len(resolved)} feasible, "
          f"{len(corners) - len(resolved)} rejected", flush=True)
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--task", choices=sorted(TASKS), action="append",
                    help="restrict to one task (repeatable); default all")
    ap.add_argument("--manifest", type=Path,
                    help="write the feasible corners as TSV: task, id, name, hydra overrides, margins")
    ap.add_argument("--plan", choices=("corners", "covering"), default="corners",
                    help="which cells to visit: every vertex of the envelope box (default), "
                         "or a t-way covering array over the same values")
    ap.add_argument("--strength", type=int, default=4,
                    help="t for --plan covering (default 4: every four-way combination)")
    args = ap.parse_args()
    tasks = args.task or sorted(TASKS)

    rows: list[str] = []
    all_ok = True
    for task_id in tasks:
        print(f"[{task_id}]", flush=True)
        fails = check_task(task_id, rows, plan=args.plan, strength=args.strength)
        print(f"[{'FAIL' if fails else 'PASS'}] {task_id}", flush=True)
        for f in fails:
            print(f"    - {f}", flush=True)
        all_ok &= not fails

    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
        print(f"manifest: {args.manifest} ({len(rows)} rows)", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
