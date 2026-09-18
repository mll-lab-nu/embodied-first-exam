"""Offline gate for `swap_crossing_sign` after the 2026-09-11 rework (2-3 ropes x 1-2 crossings).

No Genesis, no GPU: numpy + PyYAML plus two Genesis-free modules loaded by path
(`topogym.tasks_legacy` imports Genesis). Everything is computed on the literal values
in the task yaml, through the same functions the layout and the variation hooks
call (`topogym/tasks_legacy/entangle/_swap_crossing_sign_scene.py`), so nothing here is a
second copy that could drift. Five parts:

1. **Frozen layout.** The swap default is still today's geometry: control points
   bit-identical to `braid_to_control_points` with ``crossing_frac`` 0.475, the
   control polyline 0.4376 m long, all ten check rows passing. And the eight
   frozen `braid_checks` rows untangle_continuous still builds with read what they
   read before the rework (its layout does not go through any of the new code).
2. **Word table.** The two words the feasibility study rejected are not in it;
   every word is freely reduced, has one letter per crossing, and for 3 ropes x 2
   crossings uses both lane pairs; ``word_index`` 0..11 hits every word of every
   cell equally often; and the crossing code read off the control polylines is
   the code the generator promises, for every word, bent or straight.
3. **Derivation.** Over a grid of unit leaves x lane pitch x plug x x rope count:
   crossing positions inside their bounds, two crossings at least 5.5 cm apart,
   every window at least the steepness floor, the left-right shift inside the
   power strip limit.
4. **Envelope.** Every analytic vertex of the yaml's `variation:` block (each
   choice at every value, each uniform axis at both ends): the ten rows pass.
   Prints the tightest margin per row and where it occurs.
5. **Negatives.** The rows bite: bends past their cap, a plug past the workspace
   edge, lanes closer than the gripper span, two crossings on top of each other,
   outlets off the power strip.

    python tests/check_swap_crossing_sign_geometry.py

Prints one line per check and exits non-zero if any fails.
"""

from __future__ import annotations

import copy
import importlib.util
import itertools
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.generation.braid import BraidLayout, braid_to_control_points, build_braid_spec, reduce_braid_word  # noqa: E402
from topogym.planning.rope_crossings import crossing_code, find_crossings  # noqa: E402


def load_by_path(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scene = load_by_path("swap_crossing_sign_scene", "topogym/tasks_legacy/entangle/_swap_crossing_sign_scene.py")
geometry = load_by_path("swap_crossing_sign_geometry", "topogym/tasks_legacy/entangle/_swap_crossing_sign_geometry.py")
crossed = load_by_path("swap_crossed_pair_scene", "topogym/tasks_legacy/entangle/_swap_crossed_pair_scene.py")

YAML = REPO / "configs" / "task_configs" / "swap_crossing_sign_topogym_tabletop_v1.yaml"
UNTANGLE_YAML = REPO / "configs" / "task_configs" / "untangle_continuous_topogym_tabletop_v1.yaml"
FROZEN_ARC = 0.4376
# untangle_continuous's default layout through the frozen rows, as read before
# the rework (run 2026-09-11 against a snapshot of seeds 0-9: bit-identical).
UNTANGLE_ROWS = {
    "end_separation": 0.085, "crossing_window": 0.3028, "free_tail": 0.0717, "footprint_x": 0.021,
    "footprint_y": 0.2425, "strip_cover": 0.0875, "lift_height": 0.280, "lane_entry_gap": 0.0353,
}


class Gate:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, ok: bool, label: str) -> None:
        print(f"[{'ok' if ok else 'FAIL'}] {label}")
        self.failures += 0 if ok else 1


def load(path: Path) -> dict:
    """The whole task config (the yaml's top level; its `task:` key is just id + difficulty)."""

    return yaml.safe_load(path.read_text())


def rows_for(task: dict, braid: dict) -> list:
    spec = scene.spec_from_leaves(braid)
    connector = task["rope"]["free_end_connector"]
    ws = task["workspace"]
    return scene.scene_checks(
        spec.control_points, spec.crossings, spec.layout,
        tube_radius=float(braid["tube_radius"]),
        min_plug_gap=float(connector["min_clearance"]),
        plug_ahead=0.5 * float(connector["column_height"]) + float(connector["flange_height"]) + float(connector["pin_depth"]),
        flange_radius=float(connector["flange_radius"]),
        strip_half_length=0.5 * float(task["power_strip"]["size"][1]),
        workspace_x=tuple(ws["x"]), workspace_y=tuple(ws["y"]), workspace_margin=float(ws["margin"]),
        merge_radius=float(task["success"]["crossing_merge_radius"]),
    )


def crossed_pair_leaves(task: dict, **leaves) -> dict:
    """The ``crossed_pair:`` block with these unit draws, derived the way the hook does."""

    cfg = copy.deepcopy(task["crossed_pair"])
    cfg.update(leaves)
    ws = task["workspace"]
    crossed.derive_leaves(
        cfg,
        strip_half_length=0.5 * float(task["power_strip"]["size"][1]),
        workspace_x=tuple(ws["x"]), workspace_y=tuple(ws["y"]), workspace_margin=float(ws["margin"]),
    )
    return cfg


def crossed_pair_rows(task: dict, cfg: dict) -> list:
    connector = task["rope"]["free_end_connector"]
    ws = task["workspace"]
    return crossed.scene_checks(
        crossed.spec_from_leaves(cfg), cfg,
        min_plug_gap=float(connector["min_clearance"]),
        plug_ahead=0.5 * float(connector["column_height"]) + float(connector["flange_height"]) + float(connector["pin_depth"]),
        flange_radius=float(connector["flange_radius"]),
        workspace_x=tuple(ws["x"]), workspace_y=tuple(ws["y"]), workspace_margin=float(ws["margin"]),
        merge_radius=float(task["success"]["crossing_merge_radius"]),
    )


def with_leaves(task: dict, derive: bool = True, **leaves) -> dict:
    braid = copy.deepcopy(task["braid"])
    braid.update(leaves)
    if derive:
        scene.derive_leaves(braid, strip_half_length=0.5 * float(task["power_strip"]["size"][1]))
    return braid


def failed(rows) -> list[str]:
    return [name for name, _m, _l, ok in rows if not ok]


def check_frozen(gate: Gate, task: dict) -> None:
    braid = task["braid"]
    spec = scene.spec_from_leaves(braid)
    ref_layout = BraidLayout(
        x_start=float(braid["x_start"]), x_end=float(braid["x_end"]), center_y=float(braid["center_y"]),
        channel_spacing=float(braid["channel_spacing"]), base_z=float(braid["base_z"]), over_lift=float(braid["over_lift"]),
        braid_span=tuple(braid["braid_span"]), crossing_fill=float(braid["crossing_fill"]), crossing_frac=float(braid["crossing_frac"]),
    )
    ref, _ = braid_to_control_points((1,), n_strands=2, layout=ref_layout)
    gate.check(spec.word == (1,) and all(np.array_equal(ref[k], spec.control_points[k]) for k in ref),
               "frozen default: word (+1,), control points bit-identical to the generator's single-crossing layout")
    arc = float(np.linalg.norm(np.diff(spec.control_points[0], axis=0), axis=1).sum())  # 3-D, as recorded
    gate.check(abs(arc - FROZEN_ARC) < 5e-4, f"frozen control polyline {arc:.4f} m (record {FROZEN_ARC})")
    rows = rows_for(task, braid)
    gate.check(not failed(rows), "frozen default passes all ten rows: " + " ".join(f"{n}={m:+.4f}" for n, m, _l, _o in rows))

    untangle = load(UNTANGLE_YAML)
    ub = untangle["braid"]
    ulayout = BraidLayout(
        x_start=float(ub["x_start"]), x_end=float(ub["x_end"]), center_y=float(ub["center_y"]),
        channel_spacing=float(ub["channel_spacing"]), base_z=float(ub["base_z"]), over_lift=float(ub["over_lift"]),
        braid_span=tuple(ub["braid_span"]), crossing_fill=float(ub["crossing_fill"]),
    )
    uspec = build_braid_spec(n_strands=int(ub["n_strands"]), length=int(ub["length"]), seed=0, layout=ulayout, word=(1,))
    connector = untangle["rope"]["free_end_connector"]
    urows = geometry.braid_checks(
        uspec, tube_radius=float(ub["tube_radius"]), min_clearance=float(connector.get("min_clearance", 0.07)),
        plug_ahead=0.5 * float(connector["column_height"]) + float(connector["flange_height"]) + float(connector["pin_depth"]),
        flange_radius=float(connector["flange_radius"]), strip_half_length=0.5 * float(untangle["power_strip"]["size"][1]),
        workspace_x=tuple(untangle["workspace"]["x"]), workspace_y=tuple(untangle["workspace"]["y"]),
        workspace_z_max=float(untangle["workspace"]["z_max"]), workspace_margin=float(untangle["workspace"]["margin"]),
        lift_clearance=float(untangle["pinch"]["lift_clearance"]), lane_overshoot=float(untangle["pinch"]["lane_overshoot"]),
        place_pullback=float(untangle["pinch"]["place_pullback"]), separation_threshold=float(untangle["success"]["separation_threshold"]),
    )
    got = {name: measured for name, measured, _l, _o in urows}
    gate.check(all(abs(got[k] - v) < 5e-4 for k, v in UNTANGLE_ROWS.items()),
               "untangle_continuous default: the eight frozen rows unchanged " + " ".join(f"{k}={got[k]:.4f}" for k in UNTANGLE_ROWS))


def check_words(gate: Gate, task: dict) -> None:
    table = scene.WORDS
    gate.check((2, -1) not in table[(3, 2)] and (-1, 2) not in table[(3, 2)], "3x2 table leaves out (+2,-1) and (-1,+2)")
    ok = True
    for (n, length), words in table.items():
        for word in words:
            ok &= reduce_braid_word(word) == word and len(word) == length and all(1 <= abs(w) <= n - 1 for w in word)
            if (n, length) == (3, 2):
                ok &= {abs(w) for w in word} == {1, 2}
    gate.check(ok, "every word freely reduced, one letter per crossing, 3x2 words use both lane pairs")
    uniform = all(len(set(Counter(scene.braid_word(n, length, i) for i in range(scene.WORD_INDEX_COUNT)).values())) == 1
                  for (n, length) in table)
    gate.check(uniform, f"word_index 0..{scene.WORD_INDEX_COUNT - 1} hits every word of every cell equally often")
    bad = []
    for (n, length), words in table.items():
        for index in range(len(words)):
            for bows in ((0.0, 0.0, 0.0), (1.0, -1.0, 1.0), (-1.0, 1.0, -1.0)):
                braid = with_leaves(task, n_strands=n, length=length, word_index=index, crossing_u=0.5, crossing_gap_u=0.5,
                                    center_y_u=0.5, bow_u_0=bows[0], bow_u_1=bows[1], bow_u_2=bows[2])
                spec = scene.spec_from_leaves(braid)
                got = crossing_code(find_crossings({k: scene.densify(v, 0.005) for k, v in spec.control_points.items()}, merge_radius=0.012))
                if got != scene.expected_code(spec.crossings):
                    bad.append((n, length, words[index], bows))
    gate.check(not bad, f"read crossing code == promised code for every word, straight and bent ({bad[:2]})")


def check_derivation(gate: Gate, task: dict) -> None:
    worst = {"frac_out": 0, "gap": np.inf, "window": np.inf, "center_out": 0, "rewritten": 0}
    for n, length, spacing, x_end, u, gu, cu in itertools.product((2, 3), (1, 2), (0.072, 0.095), (0.16, 0.20),
                                                                  np.linspace(0, 1, 5), np.linspace(0, 1, 5), (0.0, 1.0)):
        braid = with_leaves(task, n_strands=n, length=length, channel_spacing=spacing, x_end=x_end,
                            crossing_u=float(u), crossing_gap_u=float(gu), center_y_u=cu)
        total = x_end - float(braid["x_start"])
        # Two crossings need three ropes (2026-09-12): the derivation rewrites a
        # two-crossing draw on two ropes to one crossing, so read the count back
        # from the leaves rather than from what was asked for.
        length = int(braid["length"])
        worst["rewritten"] += int(n == 2 and length != 1)
        fracs = (braid["crossing_frac"],) if length == 1 else (braid["crossing_frac"], braid["crossing_frac_2"])
        lo, hi = scene.ONE_CROSSING_FRACS if length == 1 else scene.two_crossing_bounds(spacing, total)[:2]
        worst["frac_out"] += sum(not lo - 1e-9 <= f <= hi + 1e-9 for f in fracs)
        if length == 2:
            worst["gap"] = min(worst["gap"], (fracs[1] - fracs[0]) * total)
        windows = scene.sampled_windows(fracs, 0.0, spacing=spacing, x_start=float(braid["x_start"]), x_end=x_end)
        worst["window"] = min(worst["window"], min(windows) / spacing)
        limit = scene.center_limit(n, spacing, strip_half_length=0.13, tube_radius=float(braid["tube_radius"]))
        worst["center_out"] += abs(braid["center_y"]) > limit + 1e-9
    gate.check(worst["frac_out"] == 0, "derived crossing positions inside their bounds")
    gate.check(worst["gap"] >= scene.CROSSING_GAP_MIN - 1e-9, f"two crossings at least {scene.CROSSING_GAP_MIN} apart (min {worst['gap']:.4f})")
    gate.check(worst["window"] >= scene.MIN_WINDOW_PER_LANE - 1e-9, f"narrowest window {worst['window']:.3f} x pitch >= {scene.MIN_WINDOW_PER_LANE}")
    gate.check(worst["center_out"] == 0, "left-right shift inside the power-strip limit")
    gate.check(worst["rewritten"] == 0, "two ropes never keep a two-crossing draw (rewritten to one crossing)")


def envelope(task: dict, prefix: str = "braid.") -> list[tuple[str, list]]:
    """The variation block's axes under one config block, as (path, corner values)."""

    axes = []
    for d in task["variation"]:
        if d.get("path", "").split(".", 1)[0] + "." != prefix:
            continue
        if d["kind"] == "choice":
            axes.append((d["path"], list(d["values"])))
        elif d["kind"] == "uniform":
            axes.append((d["path"], [d["lo"], d["hi"]]))
        elif d["kind"] not in ("derived", "validate"):
            raise SystemExit(f"unexpected variation kind {d['kind']}")
    return axes


def check_envelope(gate: Gate, task: dict) -> None:
    """Every analytic vertex of the lane-swap block, for the cells it still builds.

    Three ropes crossing twice are built by the other construction since
    2026-09-12 (`check_crossed_pair_envelope`), so those vertices are not the
    lane-swap rows' business; two ropes crossing twice is rewritten to one
    crossing by the derivation, so it stays here.
    """

    axes = envelope(task)
    started = time.time()
    count, bad, tightest = 0, [], {}
    for values in itertools.product(*(v for _p, v in axes)):
        leaves = {path.split(".", 1)[1]: value for (path, _v), value in zip(axes, values)}
        braid = with_leaves(task, **leaves)
        if int(braid["n_strands"]) == 3 and int(braid["length"]) == 2:
            continue
        rows = rows_for(task, braid)
        count += 1
        if failed(rows):
            bad.append((leaves, failed(rows)))
        for name, measured, limit, _ok in rows:
            margin = measured - limit
            if name not in tightest or margin < tightest[name][0]:
                tightest[name] = (margin, leaves)
    gate.check(not bad, f"all {count} analytic vertices pass the ten rows ({time.time() - started:.0f}s){'' if not bad else ' e.g. ' + str(bad[0])}")
    for name, (margin, leaves) in tightest.items():
        where = " ".join(f"{k}={v}" for k, v in leaves.items() if k in ("n_strands", "length", "word_index", "channel_spacing", "x_end", "window_u"))
        print(f"    tightest {name:>15s} margin {margin:+.4f} @ {where}")


def check_crossed_pair_envelope(gate: Gate, task: dict) -> None:
    """Every analytic vertex of the three-rope two-crossing block: the eight rows pass.

    That cell is built by `_swap_crossed_pair_scene`: one rope straight out of the
    strip, two more crossing it from the same side. Its derivation solves each
    constraint rather than rejecting a draw, so a vertex that fails here is a
    constraint the construction does not actually enforce.
    """

    axes = envelope(task, prefix="crossed_pair.")
    plug_axis = [d for d in task["variation"] if d.get("path") == "braid.x_end"]
    x_ends = [plug_axis[0]["lo"], plug_axis[0]["hi"]] if plug_axis else [float(task["braid"]["x_end"])]
    started = time.time()
    count, bad, tightest = 0, [], {}
    for values in itertools.product(*(v for _p, v in axes)):
        for x_end in x_ends:
            leaves = {path.split(".", 1)[1]: value for (path, _v), value in zip(axes, values)}
            leaves["x_end"] = x_end
            cfg = crossed_pair_leaves(task, **leaves)
            rows = crossed_pair_rows(task, cfg)
            count += 1
            if failed(rows):
                bad.append((leaves, failed(rows)))
            for name, measured, limit, _ok in rows:
                margin = measured - limit
                if name not in tightest or margin < tightest[name][0]:
                    tightest[name] = (margin, leaves)
    gate.check(not bad, f"all {count} analytic vertices pass the eight rows ({time.time() - started:.0f}s)"
                        f"{'' if not bad else ' e.g. ' + str(bad[0])}")
    for name, (margin, leaves) in tightest.items():
        where = " ".join(f"{k}={v:.2f}" for k, v in leaves.items() if k.endswith(("_u", "_u_1", "_u_2", "x_end")))
        print(f"    tightest {name:>15s} margin {margin:+.4f} @ {where}")


def check_negatives(gate: Gate, task: dict) -> None:
    cases = [
        ("bends past their cap", dict(n_strands=3, length=1, window_u=0.0, bow_u_0=2.0, bow_u_1=-2.0, bow_u_2=2.0, channel_spacing=0.072), "spawn_clearance"),
        ("plug past the workspace edge", dict(x_end=0.23), "footprint_x"),
        ("lanes 6 cm apart", dict(channel_spacing=0.060), "plug_gap"),
        # The strip is 0.44 m long since 2026-09-12, so it takes a bigger shift than it
        # used to before an outlet hangs off its end.
        ("outlets off the power strip", dict(n_strands=3, channel_spacing=0.095, center_y=0.15), "strip_cover"),
    ]
    for label, leaves, row in cases:
        braid = with_leaves(task, derive=False, **leaves)
        gate.check(row in failed(rows_for(task, braid)), f"negative: {label} fails {row}")
    braid = with_leaves(task, derive=False, n_strands=2, length=2, crossing_frac=0.55, crossing_frac_2=0.60)
    gate.check("crossing_gap" in failed(rows_for(task, braid)), "negative: two crossings 2 cm apart fail crossing_gap")


def main() -> int:
    task = load(YAML)
    gate = Gate()
    print("== 1. frozen layout")
    check_frozen(gate, task)
    print("== 2. word table")
    check_words(gate, task)
    print("== 3. derivation")
    check_derivation(gate, task)
    print("== 4. variation envelope (all analytic vertices)")
    check_envelope(gate, task)
    print("== 5. variation envelope (three ropes, two crossings)")
    check_crossed_pair_envelope(gate, task)
    print("== 6. negatives")
    check_negatives(gate, task)
    print(f"\n{'PASS' if gate.failures == 0 else f'{gate.failures} FAILED'}")
    return 0 if gate.failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
