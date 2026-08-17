"""Which capability category each task belongs to.

The authority is the directory layout under ``topogym/tasks/`` -- a task's
category IS the subpackage it lives in. The table below mirrors that layout so
callers can ask the question without importing ``topogym.tasks`` (which pulls in
Genesis).

``python topogym/core/taxonomy.py`` checks the two agree, and exits non-zero when
they diverge. Run it as a *file*, not ``-m``: this module needs only ``pathlib``,
so running it directly skips ``topogym/core/__init__.py`` and works outside the
project venv.

See ``docs/develop/framework/task_taxonomy_zh.md`` for what each category means
and what its verifiers must expose.
"""

from __future__ import annotations

from pathlib import Path

TASKS_ROOT = Path(__file__).resolve().parents[1] / "tasks"

# category slug -> task ids. Empty tuple = category reserved, nothing built yet.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "deformation": (),
    "routing": ("bar_through_hole", "cable_routing", "rope_winding"),
    "entangle": ("untangle", "untangle_continuous"),
    "connectivity": ("gate_cage_ball", "stacked_plate"),
}

# Predate the taxonomy, not yet placed on the capability axis. Not a deprecation
# marker -- see topogym/tasks/legacy/README.md for each task's actual status.
LEGACY: tuple[str, ...] = (
    "swap",
    "onestroke",
    "maze_wall_removal",
    "peeling",
    "peeling_physical",
)


def category_of(task_id: str) -> str:
    """Return the category slug for ``task_id``, or ``"legacy"``."""

    for category, task_ids in CATEGORIES.items():
        if task_id in task_ids:
            return category
    if task_id in LEGACY:
        return "legacy"
    known = ", ".join(sorted([*LEGACY, *(t for ids in CATEGORIES.values() for t in ids)]))
    raise KeyError(f"Unknown task {task_id!r}. Known: {known}")


def tasks_in(category: str) -> tuple[str, ...]:
    if category == "legacy":
        return LEGACY
    try:
        return CATEGORIES[category]
    except KeyError as exc:
        raise KeyError(
            f"Unknown category {category!r}. Known: {', '.join([*CATEGORIES, 'legacy'])}"
        ) from exc


def _on_disk(category: str) -> tuple[str, ...]:
    directory = TASKS_ROOT / category
    return tuple(
        sorted(p.stem for p in directory.glob("*.py") if not p.stem.startswith("_"))
    )


def _check() -> int:
    """Compare the table above against the actual tasks/<category>/ contents."""

    problems: list[str] = []
    for category in [*CATEGORIES, "legacy"]:
        declared = tuple(sorted(tasks_in(category)))
        on_disk = _on_disk(category)
        if declared != on_disk:
            problems.append(
                f"{category}: declared {list(declared)} but tasks/{category}/ holds {list(on_disk)}"
            )
        else:
            print(f"[ok] {category}: {list(declared) or '(reserved, empty)'}")

    # Shared helper modules are underscore-prefixed (`_visuals`, `_fixtures`), the
    # same convention `_on_disk` filters on. Naming them one by one here meant every
    # new shared module failed this check until someone extended the list.
    stray = sorted(
        p.stem
        for p in TASKS_ROOT.glob("*.py")
        if p.stem != "__init__" and not p.stem.startswith("_")
    )
    if stray:
        problems.append(f"tasks/ root holds uncategorised modules: {stray}")

    for problem in problems:
        print(f"[error] {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(_check())
