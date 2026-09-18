"""One seed -> one ``EpisodeSpec``, for any task that declares a ``variation:`` block.

This is the generic replacement for the per-task ``*_generator.py`` files. Those
seven are byte-for-byte the same control flow and differ only in which yaml
subtrees they copy by hand, so a task added today would be the eighth copy of the
same 125 lines. Here the task's own ``variation:`` block already says which leaves
this seed may rewrite, so one implementation serves every task and the task side
contributes no Python at all.

What a demo does with it::

    cfg, spec = build_variant_episode(cfg, TASK_ID, cfg.run.seed,
                                      difficulty=cfg.run.difficulty,
                                      sources=hydra_config_sources(),
                                      variant_id=cfg.run.variant_id)

in place of the bare ``cfg = randomize_task_cfg(...)`` line. The returned config is
the randomized one (same object ``randomize_task_cfg`` would have returned); the
spec records what that randomization chose.

**Recording the choice takes two sources, not one.** ``sampled_leaves`` lists the
paths the yaml declares, but it deliberately does not report leaves written by a
``derived`` hook -- ``tests/check_variant_rng.py`` has a guard asserting exactly
that. Yet derived leaves are half the identity: rope_winding's ``fixtures.C.x/y``,
ring_transfer's ``posts.A/B.x,y``, cloth_fold's ``cloth.center_x``. So this module
also diffs the task subtree before and after randomization, which catches them
(``randomize_task_cfg`` deep-copies and never mutates its input). Neither source
alone is enough: a ``choice`` axis can draw the value the yaml already had, in
which case it is absent from the diff but must still be recorded.

The one gap this leaves: a *derived* leaf whose drawn value equals the yaml's own
default is in neither source. Across the 13 tasks exactly one derived leaf is
discrete enough for that to happen -- ring_transfer's ``goal.on_post``, which the
hook sets to the post ``ring.on_post`` did not draw, so it matches the default on
about half the seeds. Nothing is lost: ``ring.on_post`` is a declared axis and is
always recorded, the goal post is the other one, and ``variant.instruction`` names
both posts in full. Every other derived leaf is a continuous position, angle or
gap, which does not land on its default. A per-task list of what each hook writes
would close the gap generically, but that is a yaml mechanism for a single leaf.

**Instruction text.** ``goal.instruction`` is a plain sentence for most tasks and a
``{placeholder}`` template for the three whose axis the picture cannot show. A
template names its renderer in ``goal.instruction_fn`` using the same
``"package.module:function"`` form ``derived`` and ``validate`` use, so this module
stays free of task imports. The sentence is never written back into a config leaf:
a value with spaces cannot ride the corner sweep's Hydra overrides (the
ring_transfer incident, 2026-09-05).

**Goal id.** ``goal.goal_id_fn`` is the same hook for the same fact as an integer,
so a baseline that takes no language still gets told which goal this episode has
(2026-09-09, for linkbar: the target zone's colour). A task without the hook gets
0. See `resolve_goal_id`.
"""

from __future__ import annotations

from typing import Any

from omegaconf import OmegaConf

from .episode_spec import EpisodeKey, EpisodeSpec, ScenePreset, TaskVariant
from .layout_randomization import (
    _get_node,  # the tree walkers and the "module:function" loader are the ones
    _resolve_fn,  # `derived`/`validate` already run on; a second copy would drift
    randomize_task_cfg,
    sampled_leaves,
)

#: Config groups whose resolved source file is recorded as episode provenance.
_SOURCE_KEYS = ("common", "env", "robot_control", "task")


def _plain(value: Any) -> Any:
    if OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


def _get(config: Any, name: str, default: Any = None) -> Any:
    getter = getattr(config, "get", None)
    if getter is not None:
        return getter(name, default)
    return getattr(config, name, default)


def _path_text(sources: dict | None, name: str) -> str | None:
    if not sources:
        return None
    value = sources.get(name)
    return None if value is None else str(value)


def _flat_leaves(node: Any, prefix: str = "") -> dict[str, Any]:
    """Every leaf under ``node`` as ``{dotted path: plain value}``.

    Lists are recorded whole rather than descended into: a varied leaf is always a
    scalar, and a waypoint list would otherwise flood the identity with indices.
    The ``variation:`` block itself is skipped -- it is the declaration, not a
    value this seed chose, and it never changes.
    """

    out: dict[str, Any] = {}
    if not hasattr(node, "items"):
        return out
    for key, value in node.items():
        if not prefix and key == "variation":
            continue
        path = f"{prefix}{key}"
        if hasattr(value, "items"):
            out.update(_flat_leaves(value, f"{path}."))
        else:
            out[path] = _plain(value)
    return out


def resolve_instruction(task_cfg) -> str:
    """The episode's instruction sentence, with any ``{placeholder}`` filled in.

    Looks for ``goal.instruction_fn`` first (a template's renderer), then
    ``goal.instruction``, then ``command.prompt`` -- the field name linkbar and
    diverter have used since before there was a ``goal:`` block. Returns ``""``
    when a task states no instruction, which is a gap to fill rather than an
    error: the recorder's own check is what should complain about it.
    """

    goal = _get(task_cfg, "goal")
    if goal is not None and hasattr(goal, "get"):
        renderer = _get(goal, "instruction_fn")
        if renderer:
            return str(_resolve_fn(renderer)(task_cfg))
        text = _get(goal, "instruction")
        if text is not None:
            return str(text)
    command = _get(task_cfg, "command")
    if command is not None:
        text = _get(command, "prompt")
        if text is not None:
            return str(text)
    return ""


def resolve_goal_id(task_cfg) -> int:
    """The episode's goal as an integer, for baselines that take no language.

    Same shape as `resolve_instruction`: ``goal.goal_id_fn`` names a
    ``"package.module:function"`` returning an int, and a task without one gets
    0. That default is honest rather than a placeholder -- a task whose
    ``goal.instruction`` is a constant sentence (diverter_route_ball with one
    destination, bar_through_hole where which hole is open is a fact of the
    picture) has exactly one goal, so one value is all its numbering needs.

    What the number means is per task and lives in that task's hook; the
    recorded episode carries the sentence alongside it, so a reader with the file
    and no repository can still tell what 0 meant.
    """

    goal = _get(task_cfg, "goal")
    if goal is not None and hasattr(goal, "get"):
        renderer = _get(goal, "goal_id_fn")
        if renderer:
            return int(_resolve_fn(renderer)(task_cfg))
    return 0


def variant_parameters(base_task_cfg, drawn_task_cfg) -> dict[str, Any]:
    """What this seed chose: every declared axis, plus every leaf that changed.

    ``base_task_cfg`` is the task subtree before randomization, ``drawn_task_cfg``
    after. See the module docstring for why both sources are needed.
    """

    before = _flat_leaves(base_task_cfg)
    after = _flat_leaves(drawn_task_cfg)
    chosen = {path: value for path, value in after.items() if before.get(path) != value}
    for path in sampled_leaves(drawn_task_cfg):
        chosen[path] = _plain(_get_node(drawn_task_cfg, path))
    return {path: chosen[path] for path in sorted(chosen)}


def build_variant_episode(
    cfg,
    task_id: str,
    seed: int,
    *,
    difficulty: str = "envelope",
    sources: dict | None = None,
    variant_id: str = "default",
    randomize: bool = True,
) -> tuple[Any, EpisodeSpec]:
    """Randomize ``cfg.task`` for ``seed`` and describe what that produced.

    Returns ``(randomized cfg, spec)``. The config is exactly what
    ``randomize_task_cfg`` returns, so swapping a demo's one-liner for this call
    cannot change the scene it builds.

    ``randomize=False`` is the demos' fixed-layout path (``run.randomize_layout``
    off, which the corner harness drives): the config is handed back untouched
    and the spec describes the layout as written, so a run down that path still
    records what it ran rather than nothing at all.
    """

    drawn = randomize_task_cfg(cfg, task_id, seed, difficulty=difficulty) if randomize else cfg
    parameters = variant_parameters(cfg["task"], drawn["task"])
    key = EpisodeKey(
        task_id=str(task_id),
        preset_id=str(_get(_get(cfg, "env"), "preset_id", "topogym_tabletop_v1")),
        seed=int(seed),
        variant_id=str(variant_id),
    )
    provenance = {name: _path_text(sources, name) for name in _SOURCE_KEYS}
    spec = EpisodeSpec(
        key=key,
        preset=ScenePreset(
            preset_id=key.preset_id,
            common_config=provenance["common"],
            env_config=provenance["env"],
            robot_config=provenance["robot_control"],
            description="TopoGym tabletop baseline shared by physical demos.",
            metadata={f"{name}_config": provenance[name] for name in _SOURCE_KEYS},
        ),
        variant=TaskVariant(
            key=key,
            difficulty=str(difficulty),
            parameters=parameters,
            instruction=resolve_instruction(drawn["task"]),
            goal_id=resolve_goal_id(drawn["task"]),
            notes=f"{len(parameters)} task leaves are this seed's; see the yaml's variation: block.",
        ),
        resolved_config={f"{name}_config": provenance[name] for name in _SOURCE_KEYS},
    )
    return drawn, spec
