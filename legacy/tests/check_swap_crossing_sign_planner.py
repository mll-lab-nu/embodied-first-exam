"""Can the swap_crossing_sign oracle flip every sampled layout? (offline, no GPU)

Physical picture: 2-3 ropes from a power strip cross 1-2 times; the oracle
re-lays plug-held rope tails, the rope laid last lying on top, until every
crossing has the other rope on top. `planning/swap_crossing_sign_sequence.py`
searches those moves on geometry alone; this gate checks the pieces the oracle
and the verifier share, then the one number the variation envelope owes:

1. **Crossing code.** Two ropes crossing twice read differently before and after
   both crossings flip (the old sorted signature read them the same); the reader
   agrees with untangle's `count_crossings` crossing for crossing; `flip_code`
   and `failure_label` say what they should.
2. **Modes.** For one layout of every word the oracle's target is reachable;
   `restack_same` reaches "no crossings" and from there the spawn again;
   `flip_nearest` reaches its one-flip target.
3. **Envelope.** Layouts drawn by the real variation block (the task yaml's
   directives, `VariantRng`, the derivation hook) for ``--seeds`` seeds: at most
   2 % may have no plan (the first-draw rule every task's envelope keeps). The
   plan search is seconds per layout, which is why it lives here and not in the
   variation block's validate step (plan valiant-soaring-pretzel, stage C).

The 2 % held over the whole envelope again from 2026-09-12, once two constants the
planner had borrowed rather than measured were replaced by measured ones (the
daylight a rope needs over another rope, 1.5 cm not the hand's 4 cm; the hand
carried within the lifted tail's own length). Two ropes crossing twice was dropped
the same day -- that cell's only routes strip the table bare and rebuild two
crossings, which the 12-17 cm error of a laid rope takes away -- so the cells here
are 2x1, 3x1 and 3x2. See `docs/develop/tasks/swap_crossing_sign_zh.md` 7.6-7.9.

    python tests/check_swap_crossing_sign_planner.py [--seeds 300] [--jobs 12]
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import yaml
from omegaconf import OmegaConf

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from topogym.generation import layout_randomization as lr  # noqa: E402
from topogym.generation.braid import BraidLayout, braid_to_control_points  # noqa: E402
from topogym.generation.variant_rng import VariantRng  # noqa: E402
from topogym.planning.rope_crossings import crossing_code, failure_label, find_crossings, flip_code  # noqa: E402
from topogym.tasks_legacy.entangle.swap_crossing_sign import SwapCrossingSignLayout, derive_task_cfg  # noqa: E402
from topogym.planning.swap_crossing_sign_sequence import (  # noqa: E402
    SequenceParams,
    code_of,
    plan_sequence,
    rope_lays,
    target_for,
)

_spec = importlib.util.spec_from_file_location("swap_scene", REPO / "topogym/tasks_legacy/entangle/_swap_crossing_sign_scene.py")
scene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scene)

YAML = REPO / "configs" / "task_configs" / "swap_crossing_sign_topogym_tabletop_v1.yaml"
MAX_NO_PLAN = 0.02


class Gate:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, ok: bool, label: str) -> None:
        print(f"[{'ok' if ok else 'FAIL'}] {label}")
        self.failures += 0 if ok else 1


def task_dict() -> dict:
    return yaml.safe_load(YAML.read_text())


def params_for(task: dict) -> SequenceParams:
    ws, pinch, connector = task["workspace"], task["pinch"], task["rope"]["free_end_connector"]
    plug_ahead = 0.5 * connector["column_height"] + connector["flange_height"] + connector["pin_depth"]
    return SequenceParams(
        rope_over_rope_clearance=float(pinch.get("rope_over_rope_clearance", pinch["lift_clearance"])),
        z_max=float(ws["z_max"]), tau_max=float(pinch["max_taut_ratio"]),
        place_clearance=float(pinch["place_clearance"]), plug_clearance=float(connector["min_clearance"]),
        x_min=float(ws["x"][0]) + ws["margin"], x_max=float(ws["x"][1]) - plug_ahead, y_limits=(float(ws["y"][0]) + ws["margin"], float(ws["y"][1]) - ws["margin"]),
        merge_radius=float(task["success"]["crossing_merge_radius"]),
    )


def state_for(task_node) -> dict:
    """The ropes the builder will build, through the layout that chooses the construction.

    Going through the layout rather than straight to one construction is what makes
    this gate test the scene: the three-rope two-crossing cell is built by
    `_swap_crossed_pair_scene` since 2026-09-12, the rest by the lane swaps.
    """

    spec = SwapCrossingSignLayout(task_node).braid_spec()
    return rope_lays({k: scene.densify(v, 0.01) for k, v in spec.control_points.items()})


def dense_polys(word, n: int) -> dict:
    layout = BraidLayout(x_start=-0.225, x_end=0.2, center_y=0.0, channel_spacing=0.085, base_z=0.007,
                         over_lift=0.012, braid_span=(0.10, 0.85), crossing_fill=0.95)
    points, _ = braid_to_control_points(word, n_strands=n, layout=layout)
    return {k: scene.densify(v, 0.005) for k, v in points.items()}


def check_code(gate: Gate) -> None:
    from topogym.verification.untangle_continuous_verifier import count_crossings  # Genesis import, read-only use

    twist = crossing_code(find_crossings(dense_polys((1, 1), 2), merge_radius=0.012))
    flipped = crossing_code(find_crossings(dense_polys((-1, -1), 2), merge_radius=0.012))
    gate.check(twist != flipped and flip_code(twist) == flipped,
               "two ropes crossing twice: code differs from its full flip, and flip_code maps one onto the other")
    agree = True
    for n, word in ((2, (1,)), (2, (1, 1)), (3, (1, 2)), (3, (-2, 1)), (3, (1, -2, 1, 2, -1))):
        polys = dense_polys(word, n)
        mine = sorted((c.over_strand, c.under_strand, round(c.position[0], 4), round(c.position[1], 4)) for c in find_crossings(polys, merge_radius=0.012))
        theirs = sorted((g.over_strand, g.under_strand, round(g.position[0], 4), round(g.position[1], 4)) for g in count_crossings(polys, merge_radius=0.012))
        agree &= mine == theirs
    gate.check(agree, "reader agrees with untangle_continuous count_crossings on five words (up to 5 crossings, 3 ropes)")
    gate.check(
        failure_label(flipped, twist) is None and failure_label(twist, twist) == "unchanged"
        and failure_label(twist[:1], twist) == "missing_crossing"
        and failure_label(tuple(sorted(twist + ((0, 2, 1, 2, 0),))), twist) == "extra_crossing"
        and failure_label(tuple(sorted((flip_code(twist[:1]) + twist[1:]))), twist) == "partial_flip",
        "failure labels: success / unchanged / missing_crossing / extra_crossing / partial_flip",
    )


def check_modes(gate: Gate, task: dict) -> None:
    params = params_for(task)
    bad = []
    for (n, length), words in scene.WORDS.items():
        # Two ropes crossing twice is no longer sampled (2026-09-12): the
        # derivation rewrites such a draw to one crossing, so its words are dead
        # entries in the table rather than something this gate has to plan for.
        if (n, length) == (2, 2):
            continue
        for index in range(len(words)):
            node = OmegaConf.create(task)
            node["braid"].update(n_strands=n, length=length, word_index=index, crossing_u=0.5,
                                 crossing_gap_u=0.5, center_y_u=0.5, window_u=1.0)
            derive_task_cfg(node)
            state = state_for(node)
            spawn = code_of(state, params)
            missing = [
                mode for mode in ("oracle", "flip_nearest")
                if plan_sequence(state, target_for(mode, spawn), params) is None
            ]
            if plan_sequence(state, (), params) is None:
                missing.append("restack: take apart")
            bad.extend((n, length, words[index], mode) for mode in missing)
    gate.check(not bad, f"every sampled word (default position): oracle, flip_nearest and restack's take-apart all plan ({bad[:3]})")


def _one(seed: int):
    task = task_dict()
    node = OmegaConf.create({"task": task})
    directives = lr._parse_directives(node["task"])
    lr._apply(node["task"], directives, VariantRng(seed), "swap_crossing_sign", 0)
    derive_task_cfg(node["task"])
    braid = node["task"]["braid"]
    params = params_for(task)
    state = state_for(node["task"])
    spawn = code_of(state, params)
    plan = plan_sequence(state, target_for("oracle", spawn), params)
    return seed, (int(braid["n_strands"]), int(braid["length"])), None if plan is None else len(plan.moves), plan.max_hand_height if plan else np.nan


def check_envelope(gate: Gate, seeds: int, jobs: int) -> None:
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        rows = list(pool.map(_one, range(seeds), chunksize=1))
    no_plan = [r for r in rows if r[2] is None]
    per_cell = Counter(r[1] for r in rows)
    miss = Counter(r[1] for r in no_plan)
    moves = Counter((r[1], r[2]) for r in rows if r[2] is not None)
    print("    per cell (no plan / drawn): " + "  ".join(f"{c[0]}x{c[1]} {miss[c]}/{per_cell[c]}" for c in sorted(per_cell)))
    print("    moves: " + "  ".join(f"{c[0]}x{c[1]}:{m}={k}" for (c, m), k in sorted(moves.items())))
    print(f"    highest planned hand height {np.nanmax([r[3] for r in rows]):.3f} m; no-plan seeds {[r[0] for r in no_plan][:12]}")
    gate.check(len(no_plan) / seeds <= MAX_NO_PLAN, f"{len(no_plan)}/{seeds} sampled layouts without a plan (<= {MAX_NO_PLAN:.0%})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=300)
    parser.add_argument("--jobs", type=int, default=12)
    args = parser.parse_args()
    task = task_dict()
    gate = Gate()
    print("== 1. crossing code")
    check_code(gate)
    print("== 2. modes")
    check_modes(gate, task)
    print(f"== 3. envelope ({args.seeds} seeds)")
    check_envelope(gate, args.seeds, args.jobs)
    print(f"\n{'PASS' if gate.failures == 0 else f'{gate.failures} FAILED'}")
    return 0 if gate.failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
