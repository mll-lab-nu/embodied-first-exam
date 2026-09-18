"""``build_variant_episode``: does one seed produce an EpisodeSpec that says what it chose?

The pipeline's first break was that a recorded episode could not say which variant it
was: the H5's ``setup`` group carried the seed but nothing about what that seed
drew, so "this demonstration grasped the far-left corner with a 10 mm inset" could
only be recovered by re-running the randomization. ``topogym/generation/
variant_episode.py`` closes that, and this test is the evidence.

Four claims, per task, over three seeds:

1. **Every declared axis is recorded.** ``sampled_leaves`` lists what the yaml's
   ``variation:`` block declares; all of it must appear in ``variant.parameters``.
   A ``choice`` axis that happens to draw the value already in the yaml is the
   case a naive before/after diff would miss.
2. **Derived leaves are recorded too.** ``sampled_leaves`` deliberately omits them
   (``check_variant_rng.py`` guards that), yet they are half the identity --
   ring_transfer's post positions, cloth_fold's cloth centre, rope_winding's
   target position are all written by a ``derived`` hook. Every task that declares
   one must contribute at least one path beyond the declared axes, and the three
   named above are spot-checked by name.
3. **Same seed, same spec.** Two calls agree field for field; two seeds do not.
4. **The input config is not consumed.** ``build_variant_episode`` returns a new
   config; the caller's own is untouched, so a demo can still read its pre-random
   values.

Then an instruction inventory: every task must state one, because it is what a
language-conditioned policy reads as its prompt. Tasks with none are listed.

    python tests/check_variant_episode.py
    python tests/check_variant_episode.py --task cloth_fold

Needs the project venv (composing pulls in the task modules). Nothing is built and
no physics runs; a few seconds per task.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from omegaconf import OmegaConf

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import topogym.generation.layout_randomization as lr  # noqa: E402
from check_variant_corners import CONFIGS, TASKS  # noqa: E402
from topogym.generation.variant_episode import build_variant_episode  # noqa: E402

SEEDS = (0, 3, 4)

#: Seeds the instruction inventory renders over. Cheap -- no physics, no scene.
INSTRUCTION_SEEDS = tuple(range(10))

#: Tasks whose instruction MUST change with the seed, because a sampled axis
#: decides the goal and the picture cannot show it: which of four identical
#: corners to fold, which of two identical posts to move the loop onto, which
#: way round the post to wind. A constant sentence here would make the training
#: set self-contradictory -- one image, two different correct actions.
MUST_VARY = {"cloth_fold", "ring_transfer", "rope_winding"}

#: rope_unwinding names its turn count and direction too, but for a different
#: reason: `cw` mirrors the whole layout and the rope spawns already wound, so
#: the direction is visible. Naming it is harmless, so this task is required
#: neither to vary nor to stay constant.
MAY_VARY = {"rope_unwinding"}

#: Leaves a task's ``derived`` hook writes that ``sampled_leaves`` cannot report.
#: Spot-checks, not an exhaustive list -- claim 2 already requires *some* derived
#: leaf from every task that declares a hook; these name the ones the pipeline
#: plan calls out, so a hook that silently stops writing them is caught here.
DERIVED_SPOT_CHECKS = {
    # Not goal.on_post: the hook sets it to the post ring.on_post did not draw,
    # so on about half the seeds it equals the yaml default and shows up in
    # neither source. See the variant_episode module docstring -- the goal post
    # stays recoverable from the recorded ring.on_post and from the instruction.
    "ring_transfer": ("posts.A.x", "posts.B.x", "pair.mid_x"),
    "cloth_fold": ("cloth.center_x",),
    "rope_winding": ("fixtures.C.x", "fixtures.C.y"),
    "linkbar_rotate_to_zone": ("linkbar.init_angle_deg",),
    # The spawn centre is drawn as a fraction of the window the shape and its
    # oracle's landings fit in; the hook turns it into metres.
    "band_untwist": ("band.center_x", "band.center_y"),
}


def _has_derived(task_cfg) -> bool:
    return any(isinstance(d, lr._Derived) for d in lr._parse_directives(task_cfg))


def check_task(task_id: str, spec_entry) -> list[str]:
    from hydra import compose, initialize_config_dir

    fails: list[str] = []
    with initialize_config_dir(version_base="1.3", config_dir=str(CONFIGS)):
        cfg = compose(
            config_name=spec_entry.physical_config,
            overrides=["run.randomize_layout=false"],
        )
    before = OmegaConf.to_container(cfg.task, resolve=True)
    declared = set(lr.sampled_leaves(cfg.task))
    expects_derived = _has_derived(cfg.task)

    specs = {}
    for seed in SEEDS:
        _, spec = build_variant_episode(cfg, task_id, seed)
        specs[seed] = spec
        recorded = set(spec.variant.parameters)

        missing = sorted(declared - recorded)
        if missing:
            fails.append(f"seed {seed}: declared axes missing from parameters: {missing}")

        extra = sorted(recorded - declared)
        if expects_derived and not extra:
            fails.append(
                f"seed {seed}: task declares a derived hook but no leaf beyond the "
                f"declared axes was recorded"
            )
        for path in DERIVED_SPOT_CHECKS.get(task_id, ()):
            if path not in recorded:
                fails.append(f"seed {seed}: derived leaf {path!r} not recorded")

        print(
            f"  seed {seed}: {len(recorded)} leaves "
            f"({len(declared)} declared + {len(extra)} derived) "
            f"instruction={spec.variant.instruction!r}",
            flush=True,
        )

    _, again = build_variant_episode(cfg, task_id, SEEDS[1])
    if again.variant.parameters != specs[SEEDS[1]].variant.parameters:
        fails.append(f"seed {SEEDS[1]} is not deterministic: two calls differ")
    if specs[SEEDS[1]].variant.parameters == specs[SEEDS[2]].variant.parameters:
        fails.append(f"seeds {SEEDS[1]} and {SEEDS[2]} produced the same parameters")

    if OmegaConf.to_container(cfg.task, resolve=True) != before:
        fails.append("build_variant_episode mutated the caller's config")

    if not specs[SEEDS[0]].variant.instruction:
        fails.append("no instruction: the policy would read an empty prompt")
        return fails

    rendered = {}
    for seed in INSTRUCTION_SEEDS:
        _, spec = build_variant_episode(cfg, task_id, seed)
        rendered.setdefault(spec.variant.instruction, []).append(seed)
    if "{" in "".join(rendered):
        fails.append(f"instruction still holds a placeholder: {sorted(rendered)[0]!r}")
    if task_id in MUST_VARY and len(rendered) < 2:
        fails.append(
            f"instruction is the same on all {len(INSTRUCTION_SEEDS)} seeds, but this "
            "task's goal is only knowable from the sentence"
        )
    if task_id not in MUST_VARY and task_id not in MAY_VARY and len(rendered) > 1:
        fails.append(
            f"instruction varies across seeds ({len(rendered)} texts) although the "
            "information is in the picture; a per-seed sentence here leaks the answer"
        )
    print(
        f"  {len(rendered)} distinct instruction(s) over {len(INSTRUCTION_SEEDS)} seeds"
        + (f": {sorted(rendered)[0]!r} ..." if len(rendered) > 1 else ""),
        flush=True,
    )

    return fails


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", action="append", choices=sorted(TASKS), default=None)
    args = parser.parse_args()

    selected = args.task or sorted(TASKS)
    all_ok = True
    no_instruction: list[str] = []
    for task_id in selected:
        print(f"\n{task_id}", flush=True)
        fails = check_task(task_id, TASKS[task_id])
        if fails:
            print("  FAIL", flush=True)
            for f in fails:
                print(f"    - {f}", flush=True)
            if any("no instruction" in f for f in fails):
                no_instruction.append(task_id)
        all_ok &= not fails

    if no_instruction:
        print(
            f"\n没有指令文本的任务（{len(no_instruction)} 个）：{', '.join(no_instruction)}",
            flush=True,
        )
    print("\nOK" if all_ok else "\nFAILED", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
