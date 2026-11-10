#!/usr/bin/env python3
"""Base-image recipes copied into other base images' recipes (PROTOCOL §1: copies of shared sources are byte-identical).

A base image built on another one's recipe (images/<name>/Dockerfile starting with another image's stages) holds that
recipe between `# >>> images/<other>/Dockerfile` and `# <<< images/<other>/Dockerfile`, as task Dockerfiles do
(scripts/task_conventions.py normalize_base_stages writes those; this check covers the images/ side). Every such block
must be the current images/<other>/Dockerfile byte for byte; `--fix` rewrites the blocks. A change to the inner recipe
then shows up here, and the outer image needs a new VERSION once its built layers change.
A recipe that checks a package state by a literal sha256 (`echo "<sha256>  /tmp/<x>.state" | sha256sum -c -`, so it needs
no build context) must name the hash of a committed lock file, images/<name>/*.lock: a hash nobody can reproduce makes
every build from public sources fail. Standard library only.
Usage: check-recipe-copies.py [--fix]   (repo-level; run_all.sh calls it once)
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCK_RE = re.compile(r"(?ms)^# >>> (images/[A-Za-z0-9_.-]+/Dockerfile)\n.*?^# <<< \1\n")
STATE_HASH_RE = re.compile(r'echo "([0-9a-f]{64})  /tmp/[A-Za-z0-9_.-]+\.state" \| sha256sum -c')


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    bad = n = 0
    locks = {hashlib.sha256(f.read_bytes()).hexdigest(): f for f in sorted((ROOT / "images").glob("*/*.lock"))}
    for df in sorted((ROOT / "images").glob("*/Dockerfile")):
        for h in STATE_HASH_RE.findall(df.read_text()):
            n += 1
            if h not in locks:
                bad += 1
                print(f"FAIL {df.relative_to(ROOT)}: checks a package state against sha256 {h[:12]}..., which is no "
                      f"committed images/*/*.lock (commit the tested image's list as the lock its message names)")
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
    print(f"ok recipe copies: {n} block(s) and state hash(es) in images/*/Dockerfile match their source")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
