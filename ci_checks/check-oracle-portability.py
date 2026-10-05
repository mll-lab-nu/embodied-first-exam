#!/usr/bin/env python3
"""Check private oracle input closure without Docker or physics; optional Git gate."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.planning.harbor_bridge.catalog import SESSION_CALLBACKS, TIERS, session_callback
from topogym.planning.harbor_bridge.contracts import digest
from topogym.planning.harbor_bridge.packaging import collect_helpers
from topogym.planning.harbor_bridge.references import reference_data


def check(root=ROOT, *, families=None, tiers=("easy", "medium", "hard"), check_git=False):
    root = Path(root).resolve()
    tracked = None
    unstaged = set()
    if check_git:
        tracked = set(subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).decode().split("\0"))
        unstaged = set(subprocess.check_output(["git", "-C", str(root), "diff", "--name-only", "-z"]).decode().split("\0"))
    rows = []
    for family in families or SESSION_CALLBACKS:
        for tier in tiers:
            row = dict(family=family, tier=tier, status="passed", files={}, errors=[])
            try:
                data, includes = reference_data(root, family, tier, 0)
                callback = session_callback(family, tier)
                if callback is None:
                    raise ValueError(f"No robot oracle for {family}/{tier}")
                files = collect_helpers(root, callback.split(":")[0], includes)
                files.update({name: Path(path) for name, path in data.items()})
                if data:
                    name = "topogym/planning/harbor_bridge/reference_data/manifest.json"
                    files[name] = root / name
                for name, path in sorted(files.items()):
                    if path.resolve() != root / name:
                        raise ValueError(f"Reference escapes the checkout: {name}")
                    row["files"][name] = digest(path)
                    if tracked is not None and name not in tracked:
                        row["errors"].append(f"Not in Git index: {name}")
                    elif name in unstaged:
                        row["errors"].append(f"Working copy differs from Git index: {name}")
            except (OSError, ValueError, KeyError) as error:
                row["errors"].append(str(error))
            if row["errors"]:
                row["status"] = "blocked"
            rows.append(row)
    return dict(schema_version=1, scope="seed-0 private source/data packaging only; no physics or grade claim",
                git_index_checked=check_git, all_passed=bool(rows) and all(r["status"] == "passed" for r in rows),
                tasks=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--families", nargs="+", choices=tuple(SESSION_CALLBACKS))
    parser.add_argument("--tiers", nargs="+", choices=TIERS, default=("easy", "medium", "hard"))
    parser.add_argument("--check-git", action="store_true", help="Require every private dependency and its current bytes in the Git index")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check(args.root, families=args.families, tiers=args.tiers, check_git=args.check_git)
    if args.output:
        with args.output.open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
    for row in result["tasks"]:
        print(f"{row['family']} {row['tier']}: {row['status']} ({len(row['files'])} files)")
        for error in row["errors"]:
            print(f"  {error}")
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
