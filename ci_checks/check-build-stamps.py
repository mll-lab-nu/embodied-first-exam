#!/usr/bin/env python3
"""Advisory (issue #258): every repository script or workflow that builds images (`harbor run`, `harbor trial`,
`docker build`, `docker compose ... build`, or the same as a Python argument list) mentions scripts/stamp_mtimes.py:
it builds from a stamped copy of the task (`stamp_mtimes.py stage`, `stamp_tree`), or says in a comment why it needs
none (a base image under images/, not a task). Docker's BuildKit can otherwise put another task's equal-size,
equal-mtime file into the image (docs/protocol/running.md "Building task images").

Usage: check-build-stamps.py   (repo-level; scans scripts/, ci_checks/ and .github/workflows/)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHELL = re.compile(r"\bharbor\s+(run|trial)\b|\bdocker\s+(buildx\s+)?build\b|\bdocker[ -]compose\b[^#\n]*\sbuild\b")
PY = re.compile(r"""["']docker["']\s*,\s*["']build["']|["']harbor["']\s*,\s*["'](run|trial)["']""")


def builds(path: Path) -> list[int]:
    out = []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return out
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if path.suffix == ".py":
            if PY.search(s):
                out.append(i)
        elif SHELL.search(s.split(" #", 1)[0]):
            out.append(i)
    return out


def main() -> int:
    files = [p for p in sorted((ROOT / "scripts").rglob("*")) if p.suffix in (".sh", ".py") and p.is_file()]
    files += [p for p in sorted((ROOT / "ci_checks").glob("*")) if p.suffix in (".sh", ".py")]
    files += sorted((ROOT / ".github/workflows").glob("*.yml"))
    me = Path(__file__).resolve()
    bad = []
    for p in files:
        if p.resolve() == me or ("/tests/" in p.as_posix() and p.name.startswith("test_")):
            continue
        hits = builds(p)
        if hits and "stamp_mtimes" not in p.read_text(errors="replace"):
            bad.append(f"{p.relative_to(ROOT)}:{hits[0]}")
    if bad:
        print(f"FAIL {len(bad)} file(s) build images without scripts/stamp_mtimes.py (issue #258; build from "
              f"`stamp_mtimes.py stage <task> <dir>`, or say in a comment naming stamp_mtimes why no task is built):")
        for b in bad:
            print(f"  {b}")
        return 3
    print(f"ok check-build-stamps: {len(files)} files scanned, every image build uses or names scripts/stamp_mtimes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
