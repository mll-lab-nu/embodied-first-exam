#!/usr/bin/env python3
"""Source folders of the DexHand families, with the files that only the generated task directories carry.

A family folder (`families/<family>/`, `task_library/<family>/`) holds what the generator interprets or what never
reaches a task: `family.json`, the instruction and README templates, authoring notes, `tools/`, tests, asset manifests
and provenance. The files `generate.py` copies unchanged into the tasks (runtime code, the frozen `task.json` a
plugin family ships, assets, reference trajectories, `wuji_reset.json`, the essential scene modules) are committed
once, in the family's generated task directories:

| Family file | Canonical copy (`tasks/dexhand-<family>-i00-<mode>/`) |
|---|---|
| plugin `runtime.files` / `runtime.dirs` | privileged `environment/<path>` |
| plugin `solution[mode]` (`.npz`, or `.json` + parts) | that mode's `solution/trajectory.npz` (or `trajectory.json` + parts) |
| `<solution dir>/<hand>/trajectory.*` | privileged `solution/<hand>/` |
| essential `scene.py` | privileged `environment/<module>.py` (module: `task_library/index.json`) |
| essential `assets/<runtime file>` | privileged `environment/object_assets/<family>/<file>` (`.obj` without the converter's URL line) |
| essential `wuji_reset.json`, `offered_hands.json` | privileged `environment/<name>` |
| essential `solution/...` | privileged `solution/...` |

`folder()` stages a family's source folder: its committed files plus every canonical copy that the folder does not
hold itself. A file present in the family folder wins, which is how a new family, or a changed file, enters: put it
in the family folder, regenerate, then `python3 scripts/dexhand/sources.py --clean` removes every family-folder file
that is now byte-identical to its canonical copy (`generate.py --check` fails while such a duplicate is left). A
solution slot (`<solution dir>/<stem>.npz`, or `<stem>.json` with its parts, and each `<hand>/` folder) is replaced as
a whole: once the family folder holds either form, none of the slot's canonical files is staged, and a slot holding
both forms is an error. A file deleted or renamed in a family (a `runtime.dirs` file, say) must be deleted or renamed
in its task directories too, or its old canonical copy is staged again.

Authoring tools, the family tests and the MuJoCo suites under `tests/` read the runtime from the family folder:
`python3 scripts/dexhand/sources.py --unpack [family ...]` writes the canonical copies into the family folders first,
and `--clean` removes them again after the edit has been regenerated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TASKS = ROOT / "tasks"
FAMILIES = HERE / "families"
LIBRARY = HERE / "task_library"
HANDS = ("wuji",)   # hands with an optional per-hand reference solution (the default hand's rows are solution/ itself)
TRIMESH_HEADER = b"# https://github.com/mikedh/trimesh"

_STAGE: tempfile.TemporaryDirectory | None = None
_STAGED: dict[Path, Path] = {}
_COUNT = [0]   # staged folders so far (a fresh subdirectory each, across resets)


def task_dir(family: str, mode: str) -> Path:
    return TASKS / f"dexhand-{family.replace('_', '-')}-i00-{mode}"


def runtime_bytes(path: Path) -> bytes:
    """A packaged asset's bytes: an `.obj` loses the converter's automatic code-URL first line (geometry unchanged)."""
    data = path.read_bytes()
    if path.suffix.lower() == ".obj":
        first, separator, geometry = data.partition(b"\n")
        if separator and first.rstrip(b"\r") == TRIMESH_HEADER:
            return geometry
    return data


def slot(declared: Path) -> tuple[str, str]:
    """A solution slot: the two names one set of rows can have (`<stem>.npz`, or `<stem>.json` with its parts)."""
    return (declared.with_suffix(".npz").as_posix(), declared.with_suffix(".json").as_posix())


def _solution(task_solution: Path, declared: Path) -> dict[str, tuple[Path, tuple | None]]:
    """A task's `solution/trajectory.npz` (or `trajectory.json` and its parts) under the family's declared name,
    as one slot: staged only as a whole (`folder`)."""
    if declared.suffix == ".json":
        manifest = task_solution / "trajectory.json"
        if not manifest.is_file():
            return {}
        copies = {declared.as_posix(): (manifest, slot(declared))}
        for part in json.loads(manifest.read_text())["parts"]:
            copies[(declared.parent / part["file"]).as_posix()] = (task_solution / part["file"], slot(declared))
        return copies
    return {declared.as_posix(): (task_solution / "trajectory.npz", slot(declared))}


def _hand_solutions(task_solution: Path, solution_dir: Path) -> dict[str, tuple[Path, tuple | None]]:
    copies = {}
    for hand in HANDS:
        name = "trajectory.json" if (task_solution / hand / "trajectory.json").is_file() else "trajectory.npz"
        copies.update(_solution(task_solution / hand, solution_dir / hand / name))
    return copies


def _plugin_entries(folder: Path) -> dict[str, tuple[Path, tuple | None]]:
    """{family-relative path: (canonical task copy, solution slot or None)} of a plugin family."""
    manifest = json.loads((folder / "family.json").read_text())
    family = manifest["id"]
    privileged, standard = task_dir(family, "privileged"), task_dir(family, "standard")
    runtime = manifest.get("runtime", {})
    copies = {relative: (privileged / "environment" / relative, None) for relative in runtime.get("files", [])}
    for relative in runtime.get("dirs", []):
        base = privileged / "environment" / relative
        for file in sorted(base.rglob("*")) if base.is_dir() else []:
            if file.is_file() and "__pycache__" not in file.parts:
                copies[(Path(relative) / file.relative_to(base)).as_posix()] = (file, None)
    solution = manifest.get("solution") or {}
    if solution:
        copies.update(_solution(standard / "solution", Path(solution["standard"])))
        copies.update(_solution(privileged / "solution", Path(solution["privileged"])))   # the privileged rows win
        copies.update(_hand_solutions(privileged / "solution", Path(solution["privileged"]).parent))
    return copies


def _essential_entries(family: str) -> dict[str, tuple[Path, tuple | None]]:
    """{family-relative path: (canonical task copy, solution slot or None)} of an essential family."""
    module = next(entry["module"] for entry in json.loads((LIBRARY / "index.json").read_text())["tasks"]
                  if entry["id"] == family)
    task = task_dir(family, "privileged")
    environment = task / "environment"
    copies = {"scene.py": (environment / f"{module}.py", None)}
    for name in ("wuji_reset.json", "offered_hands.json"):
        copies[name] = (environment / name, None)
    manifest = LIBRARY / family / "assets/manifest.json"
    if manifest.is_file():
        for name in json.loads(manifest.read_text()).get("runtime_files", []):
            copies[f"assets/{name}"] = (environment / "object_assets" / family / name, None)
    name = "trajectory.json" if (task / "solution/trajectory.json").is_file() else "trajectory.npz"
    copies.update(_solution(task / "solution", Path("solution") / name))
    copies.update(_hand_solutions(task / "solution", Path("solution")))
    return copies


def entries(folder: Path) -> dict[str, tuple[Path, tuple | None]]:
    """The canonical copies a family folder can take from tasks/: {family-relative path: (task file, slot)}."""
    if (folder / "family.json").is_file():
        found = _plugin_entries(folder)
    elif folder.parent == LIBRARY:
        found = _essential_entries(folder.name)
    else:
        found = {}
    return {relative: value for relative, value in found.items() if value[0].is_file()}


def copies_of(folder: Path) -> dict[str, Path]:
    """The canonical copies `folder` takes: every entry, except a solution slot the folder fills itself (a
    family-folder `trajectory.npz` or `trajectory.json` replaces the slot's rows as a whole, never file by file)."""
    return {relative: path for relative, (path, rows) in entries(folder).items()
            if rows is None or not any((folder / name).is_file() for name in rows)}


def origin(path: Path) -> Path:
    """A staged file's family-folder path (for messages); any other path unchanged."""
    for source, target in _STAGED.items():
        if path.is_relative_to(target):
            return source / path.relative_to(target)
    return path


def reset() -> None:
    """Drop the staged folders (the generator stages afresh for every render)."""
    for target in _STAGED.values():
        shutil.rmtree(target.parent, ignore_errors=True)
    _STAGED.clear()


def folder(source: Path) -> Path:
    """The staged source folder of a family: a temporary copy of `source` plus the canonical copies it lacks.

    Staged once per `reset()`, so a render that rewrites tasks/ in place reads the canonical copies before it
    removes them."""
    global _STAGE
    key = source.resolve()
    if key not in _STAGED:
        if _STAGE is None:
            try:   # next to the checkout (a large data disk here), else the system's temporary directory
                _STAGE = tempfile.TemporaryDirectory(prefix="dexhand-sources-", dir=ROOT.parent)
            except OSError:
                _STAGE = tempfile.TemporaryDirectory(prefix="dexhand-sources-")
        _COUNT[0] += 1
        target = Path(_STAGE.name) / str(_COUNT[0]) / source.name
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for relative, canonical in copies_of(source).items():
            if not (target / relative).exists():
                (target / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(canonical, target / relative)
        for rows in {rows for _, rows in entries(source).values() if rows}:
            if all((target / name).is_file() for name in rows):
                raise ValueError(f"{source.name}: solution slot holds both {rows[0]} and {rows[1]}; keep one")
        _STAGED[key] = target
    return _STAGED[key]


def family_folders(names: list[str] | None = None) -> list[Path]:
    folders = sorted(path.parent for path in FAMILIES.glob("*/family.json"))
    folders += [LIBRARY / entry["id"] for entry in json.loads((LIBRARY / "index.json").read_text())["tasks"]]
    return [path for path in folders if not names or path.name in names]


def duplicates(source: Path) -> list[Path]:
    """Family-folder files that are byte-identical to their canonical task copy (left over from --unpack or a
    regenerated edit; an `.obj` also when it differs only by the converter's URL line): keep only the canonical copy."""
    found = []
    for relative, (canonical, _) in sorted(entries(source).items()):
        path = source / relative
        if path.is_file() and canonical.read_bytes() in (path.read_bytes(), runtime_bytes(path)):
            found.append(path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--unpack", action="store_true", help="write the canonical copies into the family folders")
    action.add_argument("--clean", action="store_true", help="remove family-folder files identical to their canonical copy")
    parser.add_argument("families", nargs="*", help="family ids (default: every family)")
    args = parser.parse_args()
    folders = family_folders(args.families)
    missing = sorted(set(args.families) - {path.name for path in folders})
    if missing:
        print("unknown family: " + ", ".join(missing), file=sys.stderr)
        return 1
    count = 0
    for source in folders:
        if args.unpack:
            for relative, canonical in sorted(copies_of(source).items()):
                if not (source / relative).exists():
                    (source / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(canonical, source / relative)
                    count += 1
        else:
            for path in duplicates(source):
                path.unlink()
                count += 1
                parent = path.parent
                while parent != source and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
    print(f"{'unpacked' if args.unpack else 'removed'} {count} files in {len(folders)} family folders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
