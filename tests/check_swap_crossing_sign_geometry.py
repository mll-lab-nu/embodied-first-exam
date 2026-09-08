"""Offline gate for `swap_crossing_sign` (docx 3.2, two cables crossing once).

No Genesis, no GPU: numpy + PyYAML. Everything is computed on the literal
values in `configs/task_configs/swap_crossing_sign_topogym_tabletop_v1.yaml`
so the two cannot drift. Four parts:

1. **Frozen layout** -- the eight `braid_checks` rows on the default config
   read what the deployment record says (plug separation 0.085, swap window
   0.303, free tail 0.072, lift 0.280 ...), and the control polyline is still
   the 0.4376 m the planner gate was measured against: adding the
   `crossing_frac` / `crossing_sign` leaves changed nothing at their defaults.

2. **The two new generator inputs** -- a crossing pushed to `crossing_frac`
   0.30 / 0.75 keeps its swap window inside `braid_span` (the anchored lead-in
   and the free tail survive) and flatter than the steepness rule, and sits
   where it was asked; `crossing_sign` +1 / -1 gives the braid word (+1,) /
   (-1,) with the over strand flipped and the geometry otherwise identical.
   The evenly spaced default and a length-3 word still come out as before.

3. **Variation envelope** -- every corner of the yaml's `variation:` block
   (sign at both values x four uniform axes at both ends = 32 corners): the
   eight rows pass, the braid self-check (`verify_braid_spec`) is clean, and
   the worst predicted lift stays under the workspace ceiling with the margin
   the record claims (0.361 vs 0.40).

4. **Negatives** -- the rows must actually bite: a plug past the workspace
   edge (`x_end` 0.23) fails `footprint_x`; a ceiling at 0.25 fails
   `lift_height`; lanes 0.060 apart fail `end_separation` (the builder would
   refuse the plugs); a crossing at 0.90 is outside `braid_span` and raises.

    python tests/check_swap_crossing_sign_geometry.py

Prints one line per check and exits non-zero if any fails.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.generation.braid import (  # noqa: E402  (Genesis-free package)
    BraidLayout,
    build_braid_spec,
    crossing_window,
    verify_braid_spec,
)


def load_by_path(name: str, relative: str):
    """Import a Genesis-free module without running its package's `__init__`
    (`topogym.tasks` imports Genesis)."""

    path = REPO / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


geometry = load_by_path(
    "swap_crossing_sign_geometry", "topogym/tasks/entangle/_swap_crossing_sign_geometry.py"
)

YAML = REPO / "configs" / "task_configs" / "swap_crossing_sign_topogym_tabletop_v1.yaml"
COMMON = REPO / "configs" / "common_configs" / "manipulation_space_tabletop_v1.yaml"

# What the deployment record (docs/develop/tasks/swap_crossing_sign_zh.md) states
# for the frozen layout; part 1 pins them.
FROZEN_ROWS = {
    "end_separation": 0.085,
    "crossing_window": 0.3028,
    "free_tail": 0.0717,
    "footprint_x": 0.021,
    "footprint_y": 0.2425,
    "strip_cover": 0.0875,
    "lift_height": 0.280,
    # lane_overshoot 0.130 x (swap end 0.128 + 0.225) / (place 0.175 + 0.225)
    "lane_entry_gap": 0.1147,
}
FROZEN_ARC = 0.4376
# Worst predicted lift over the 32 corners, and the margin to the ceiling the
# record claims for it.
WORST_LIFT = 0.361
MIN_LIFT_MARGIN = 0.035


class Gate:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, ok: bool, text: str) -> None:
        self.failures += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {text}")


# ------------------------------------------------------------------ config


def load_task() -> dict:
    with open(YAML, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def braid_layout(task: dict) -> BraidLayout:
    braid = task["braid"]
    return BraidLayout(
        x_start=float(braid["x_start"]),
        x_end=float(braid["x_end"]),
        center_y=float(braid["center_y"]),
        channel_spacing=float(braid["channel_spacing"]),
        base_z=float(braid["base_z"]),
        over_lift=float(braid["over_lift"]),
        braid_span=tuple(float(v) for v in braid["braid_span"]),
        crossing_fill=float(braid["crossing_fill"]),
        crossing_frac=None if braid.get("crossing_frac") is None else float(braid["crossing_frac"]),
    )


def braid_spec(task: dict, *, seed: int = 0):
    braid = task["braid"]
    sign = int(braid.get("crossing_sign", 0) or 0)
    return build_braid_spec(
        n_strands=int(braid["n_strands"]),
        length=int(braid["length"]),
        seed=seed,
        layout=braid_layout(task),
        word=None if sign == 0 else (sign,),
    )


def checks_for(task: dict) -> list:
    """Same arguments `UntangleContinuousLayout.checks()` passes, from the raw yaml."""

    braid, ws = task["braid"], task["workspace"]
    connector = task["rope"]["free_end_connector"]
    return geometry.braid_checks(
        braid_spec(task),
        tube_radius=float(braid["tube_radius"]),
        min_clearance=float(connector.get("min_clearance", 0.07)),
        plug_ahead=(
            0.5 * float(connector["column_height"])
            + float(connector["flange_height"])
            + float(connector["pin_depth"])
        ),
        flange_radius=float(connector["flange_radius"]),
        strip_half_length=0.5 * float(task["power_strip"]["size"][1]),
        workspace_x=tuple(float(v) for v in ws["x"]),
        workspace_y=tuple(float(v) for v in ws["y"]),
        workspace_z_max=float(ws["z_max"]),
        workspace_margin=float(ws["margin"]),
        lift_clearance=float(task["pinch"]["lift_clearance"]),
        lane_overshoot=float(task["pinch"]["lane_overshoot"]),
        place_pullback=float(task["pinch"]["place_pullback"]),
        separation_threshold=float(task["success"]["separation_threshold"]),
    )


def with_leaves(task: dict, **leaves) -> dict:
    """Copy of the task dict with dotted leaves overwritten (`braid__x_end=0.23`)."""

    out = yaml.safe_load(yaml.safe_dump(task))
    for key, value in leaves.items():
        node = out
        parts = key.split("__")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    return out


def rows_line(rows) -> str:
    return " ".join(f"{n}={m:+.4f}/{l:+.4f}/{'ok' if ok else 'FAIL'}" for n, m, l, ok in rows)


def verify(task: dict, spec) -> object:
    ws = task["workspace"]
    return verify_braid_spec(
        spec,
        rope_radius=float(task["braid"]["tube_radius"]),
        particle_size=0.004,  # prefabs.rope_pbd.particle_size, literal here on purpose
        x_bounds=tuple(float(v) for v in ws["x"]),
        y_bounds=tuple(float(v) for v in ws["y"]),
    )


def polyline_arc(points: np.ndarray) -> float:
    return float(np.linalg.norm(np.diff(np.asarray(points, dtype=float), axis=0), axis=1).sum())


# ------------------------------------------------------------------ 1. frozen layout


def check_frozen(gate: Gate, task: dict) -> None:
    with open(COMMON, encoding="utf-8") as handle:
        common_ws = yaml.safe_load(handle)["manipulation_space"]["workspace"]
    ws = task["workspace"]
    gate.check(
        list(ws["x"]) == list(common_ws["x"]) and list(ws["y"]) == list(common_ws["y"])
        and float(ws["z_max"]) == float(common_ws["z"][1]),
        "task yaml's workspace box copies manipulation_space.workspace",
    )
    gate.check(
        int(task["braid"]["crossing_sign"]) == 0
        and abs(float(task["braid"]["crossing_frac"]) - 0.475) < 1e-12,
        "defaults: crossing_sign 0 (seed draw), crossing_frac 0.475 (= 0.10 + 0.75 x 0.5)",
    )
    rows = checks_for(task)
    print("    " + rows_line(rows))
    for name, measured, _limit, ok in rows:
        want = FROZEN_ROWS[name]
        gate.check(
            ok and abs(measured - want) < 5e-4,
            f"frozen {name} = {measured:.4f} (record {want:.4f})",
        )
    spec = braid_spec(task)
    arc = polyline_arc(spec.control_points[0])
    gate.check(abs(arc - FROZEN_ARC) < 5e-4, f"frozen control polyline arc {arc:.4f} m (planner gate: {FROZEN_ARC})")
    # The same geometry through the evenly spaced default (no crossing_frac)
    # and through the sampled word: byte-identical control points.
    default_spec = build_braid_spec(
        n_strands=2, length=1, seed=0, layout=replace(braid_layout(task), crossing_frac=None)
    )
    same = all(
        np.allclose(default_spec.control_points[s], spec.control_points[s])
        for s in spec.control_points
    )
    gate.check(same and default_spec.word == spec.word, "crossing_frac 0.475 reproduces the evenly spaced default exactly")
    report = verify(task, spec)
    gate.check(report.ok, f"frozen braid self-check: {report}")


# ------------------------------------------------------------------ 2. crossing position and sign


def check_generator_inputs(gate: Gate, task: dict) -> None:
    layout = braid_layout(task)
    total = layout.x_end - layout.x_start
    span_lo, span_hi = layout.braid_span
    for frac in (0.30, 0.75):
        spec = build_braid_spec(n_strands=2, length=1, layout=replace(layout, crossing_frac=frac), word=(1,))
        crossing = spec.crossings[0]
        over = spec.control_points[crossing.over_strand]
        x_center = layout.x_start + frac * total
        mid = int(np.argmin(np.abs(over[:, 0] - x_center)))
        window = over[mid + 1, 0] - over[mid - 1, 0]
        inside = (
            over[mid - 1, 0] >= layout.x_start + span_lo * total - 1e-9
            and over[mid + 1, 0] <= layout.x_start + span_hi * total + 1e-9
        )
        gate.check(
            abs(crossing.position_frac - frac) < 1e-12 and abs(over[mid, 0] - x_center) < 1e-9,
            f"crossing_frac {frac}: crossing sits at x={x_center:+.4f}",
        )
        gate.check(
            inside and window <= crossing_window(1, layout) + 1e-9,
            f"crossing_frac {frac}: swap window {window:.4f} clipped inside braid_span "
            f"(full {crossing_window(1, layout):.4f})",
        )
        gate.check(
            window >= geometry.MIN_WINDOW_PER_LANE * layout.channel_spacing - 1e-9,
            f"crossing_frac {frac}: window {window:.4f} >= 0.6 x spacing {0.6 * layout.channel_spacing:.4f} "
            f"(swap angle {np.degrees(np.arctan2(layout.channel_spacing, window)):.1f} deg)",
        )
        gate.check(verify(task, spec).ok, f"crossing_frac {frac}: braid self-check ok")

    plus = build_braid_spec(n_strands=2, length=1, layout=layout, word=(1,))
    minus = build_braid_spec(n_strands=2, length=1, layout=layout, word=(-1,))
    gate.check(
        plus.word == (1,) and minus.word == (-1,)
        and plus.crossings[0].over_strand == 0 and minus.crossings[0].over_strand == 1
        and plus.crossings[0].position_frac == minus.crossings[0].position_frac,
        "crossing_sign +1 / -1: word (+1,) / (-1,), over strand 0 / 1, same position",
    )
    # Flipping the sign lifts the other strand and nothing else moves in xy.
    xy_same = all(
        np.allclose(plus.control_points[s][:, :2], minus.control_points[s][:, :2])
        for s in plus.control_points
    )
    lifted = (
        plus.control_points[0][:, 2].max() > layout.base_z
        and minus.control_points[1][:, 2].max() > layout.base_z
        and plus.control_points[1][:, 2].max() == layout.base_z
        and minus.control_points[0][:, 2].max() == layout.base_z
    )
    gate.check(xy_same and lifted, "crossing_sign flips only which strand carries the over_lift bump")

    for bad_word in ((1, 1), (1, -1)):
        try:
            build_braid_spec(n_strands=2, length=1, layout=layout, word=bad_word)
        except ValueError:
            gate.check(True, f"word {bad_word} is refused for length 1")
        else:
            gate.check(False, f"word {bad_word} was accepted for length 1")
    try:
        build_braid_spec(n_strands=2, length=3, seed=1, layout=layout)
    except ValueError:
        gate.check(True, "crossing_frac with a 3-letter word is refused (only defined for one crossing)")
    else:
        gate.check(False, "crossing_frac with a 3-letter word was accepted")
    three = build_braid_spec(n_strands=2, length=3, seed=1, layout=replace(layout, crossing_frac=None))
    gate.check(
        [round(c.position_frac, 3) for c in three.crossings] == [0.225, 0.475, 0.725],
        "no crossing_frac: a 3-letter word keeps its evenly spaced slots",
    )


# ------------------------------------------------------------------ 3. envelope corners


def envelope(task: dict) -> tuple[dict, list]:
    """`{path: [values]}` from the yaml's variation block, plus the validate entry."""

    axes: dict[str, list] = {}
    for entry in task["variation"]:
        kind = entry["kind"]
        if kind == "choice":
            axes[entry["path"]] = list(entry["values"])
        elif kind == "uniform":
            axes[entry["path"]] = [float(entry["lo"]), float(entry["hi"])]
        elif kind in ("derived", "validate"):
            continue
        else:
            raise SystemExit(f"unexpected variation kind {kind}")
    return axes, task["variation"]


def check_envelope(gate: Gate, task: dict) -> None:
    axes, _ = envelope(task)
    want = ["braid.crossing_sign", "braid.crossing_frac", "braid.channel_spacing", "braid.center_y", "braid.x_end"]
    gate.check(list(axes) == want, f"variation block samples {list(axes)}")
    gate.check(
        not any(e["kind"] == "derived" for e in task["variation"]),
        "no derived leaf: every axis is independent inside the envelope",
    )
    paths = list(axes)
    n_ok, worst_lift, tightest = 0, 0.0, {}
    corners = list(itertools.product(*(axes[p] for p in paths)))
    for values in corners:
        leaves = {p.replace(".", "__"): v for p, v in zip(paths, values)}
        corner = with_leaves(task, **leaves)
        rows = checks_for(corner)
        report = verify(corner, braid_spec(corner))
        ok = all(r[3] for r in rows) and report.ok
        n_ok += int(ok)
        if not ok:
            print(f"    corner {values}: {rows_line(rows)} {report}")
        for name, measured, limit, _ in rows:
            margin = (limit - measured) if name == "lift_height" else (measured - limit)
            tightest[name] = min(tightest.get(name, float("inf")), margin)
        worst_lift = max(worst_lift, [r for r in rows if r[0] == "lift_height"][0][1])
    gate.check(n_ok == len(corners), f"{n_ok}/{len(corners)} envelope corners pass the eight rows and the braid self-check")
    print("    tightest margins: " + " ".join(f"{k}={v:+.4f}" for k, v in tightest.items()))
    gate.check(
        abs(worst_lift - WORST_LIFT) < 5e-4 and worst_lift <= float(task["workspace"]["z_max"]) - MIN_LIFT_MARGIN,
        f"worst predicted lift over the corners {worst_lift:.3f} m (record {WORST_LIFT}; ceiling {task['workspace']['z_max']} "
        f"minus {MIN_LIFT_MARGIN} margin)",
    )
    # The sign axis reaches both words at every geometry corner.
    signs = {int(with_leaves(task, braid__crossing_sign=s)["braid"]["crossing_sign"]) for s in axes["braid.crossing_sign"]}
    gate.check(signs == {1, -1}, "crossing_sign axis takes both values")


# ------------------------------------------------------------------ 4. negatives


def check_negatives(gate: Gate, task: dict) -> None:
    def failing(corner: dict) -> list[str]:
        return [name for name, _, _, ok in checks_for(corner) if not ok]

    gate.check(
        failing(with_leaves(task, braid__x_end=0.23)) == ["footprint_x"],
        "x_end 0.23 puts the plug's pin past the workspace edge: footprint_x fails, nothing else",
    )
    gate.check(
        failing(with_leaves(task, workspace__z_max=0.25)) == ["lift_height"],
        "a 0.25 ceiling fails lift_height on the frozen layout (predicted 0.280)",
    )
    gate.check(
        failing(with_leaves(task, braid__channel_spacing=0.060)) == ["end_separation"],
        "lanes 0.060 apart fail end_separation (the builder would refuse the plugs)",
    )
    # The 2026-09-06 incident, as a row: the old 0.040 overshoot with the
    # crossing at 0.30 leaves 21 mm where the other rope enters the lane.
    gate.check(
        failing(with_leaves(task, pinch__lane_overshoot=0.040, braid__crossing_frac=0.30)) == ["lane_entry_gap"],
        "lane_overshoot 0.040 with the crossing at 0.30 fails lane_entry_gap (21 mm < 32), nothing else",
    )
    gate.check(
        failing(with_leaves(task, braid__center_y=0.22)) == ["footprint_y", "strip_cover"],
        "center_y 0.22 fails footprint_y and strip_cover (lanes past the strip and within 0.04 of the edge)",
    )
    try:
        checks_for(with_leaves(task, braid__crossing_frac=0.90))
    except ValueError:
        gate.check(True, "crossing_frac 0.90 (outside braid_span) raises")
    else:
        gate.check(False, "crossing_frac 0.90 (outside braid_span) was accepted")
    # A window clipped so hard it breaks the steepness rule: frac 0.84 with the
    # widest lanes leaves a 0.0085 m window against a 0.057 m floor.
    rows = checks_for(with_leaves(task, braid__crossing_frac=0.84, braid__channel_spacing=0.095))
    bad = [name for name, _, _, ok in rows if not ok]
    gate.check("crossing_window" in bad, f"crossing_frac 0.84 fails crossing_window ({bad})")


def main() -> int:
    gate = Gate()
    task = load_task()
    print("== 1. frozen layout")
    check_frozen(gate, task)
    print("== 2. crossing position and sign")
    check_generator_inputs(gate, task)
    print("== 3. variation envelope")
    check_envelope(gate, task)
    print("== 4. negatives")
    check_negatives(gate, task)
    print(f"\n{'PASS' if gate.failures == 0 else f'{gate.failures} FAILED'}")
    return 1 if gate.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
