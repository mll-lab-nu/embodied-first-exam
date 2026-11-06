#!/usr/bin/env python3
"""Base-image recipes copied into other base images' recipes (PROTOCOL §1: copies of shared sources are byte-identical).

A base image built on another one's recipe (images/<name>/Dockerfile starting with another image's stages) holds that
recipe between `# >>> images/<other>/Dockerfile` and `# <<< images/<other>/Dockerfile`, as task Dockerfiles do
(scripts/task_conventions.py normalize_base_stages writes those; this check covers the images/ side). Every such block
must be the current images/<other>/Dockerfile byte for byte; `--fix` rewrites the blocks. A change to the inner recipe
then shows up here, and the outer image needs a new VERSION once its built layers change. Standard library only.
Usage: check-recipe-copies.py [--fix]   (repo-level; run_all.sh calls it once)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCK_RE = re.compile(r"(?ms)^# >>> (images/[A-Za-z0-9_.-]+/Dockerfile)\n.*?^# <<< \1\n")


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    bad = n = 0
    for df in sorted((ROOT / "images").glob("*/Dockerfile")):
        s = df.read_text()
        if "# >>> images/" not in s:
            continue
        def block(m: "re.Match[str]") -> str:
            nonlocal bad, n
            n += 1
            src = ROOT / m.group(1)
            if not src.is_file() or src == df:
                bad += 1
                print(f"FAIL {df.relative_to(ROOT)}: recipe block {m.group(1)}: no such other image recipe")
                return m.group(0)
            body = src.read_text()
            want = f"# >>> {m.group(1)}\n{body}{'' if body.endswith(chr(10)) else chr(10)}# <<< {m.group(1)}\n"
            if m.group(0) != want and not fix:
                bad += 1
                print(f"FAIL {df.relative_to(ROOT)}: its copy of {m.group(1)} differs from the file "
                      f"(python3 ci_checks/check-recipe-copies.py --fix, then a new VERSION if the built layers change)")
            return want
        t = BLOCK_RE.sub(block, s)
        if fix and t != s:
            df.write_text(t)
            print(f"fixed {df.relative_to(ROOT)}")
    if bad:
        return 1
    print(f"ok recipe copies: {n} block(s) in images/*/Dockerfile match their source")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
