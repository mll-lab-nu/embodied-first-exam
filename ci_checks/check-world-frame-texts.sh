#!/usr/bin/env bash
# ADVISORY helper (docs/protocol/README.md §5: world-frame information in the texts is decided per benchmark, consistent within
# it). A benchmark that declares "no world coordinates in the standard tasks' texts" (its tasks/<benchmark>/README.md,
# "World-frame information") runs this from its own hook, ci_checks/benchmarks/<bench>/advisory-world-frame.sh, with its directory
# prefix; shared CI names no benchmark (board 0124). Such a benchmark's standard tasks never say WHERE things are in the
# world: no object poses or positions and no world coordinates of workspace items (table / sheet heights, sheet or well
# centres, a pixel-to-world formula, a camera's distance to the scene), in anything that describes the task:
# instruction.md, README.md, the task.toml description. Names, inventories, categories, sizes, colours and a detailed goal
# are provided; so are the robot (its base pose included), camera calibration and world conventions ("the floor is the
# plane z = 0" defines a world frame and stays). Only what a pattern can see is checked; a review covers the rest.
# Usage: check-world-frame-texts.sh --prefix <dir prefix> <task dirs...>   (the -standard ones with the prefix are checked)
set -uo pipefail
[ "${1:-}" = --prefix ] && [ $# -ge 2 ] || { echo "usage: check-world-frame-texts.sh --prefix <dir prefix> <task dirs...>"; exit 2; }
prefix="$2"; shift 2; rc=0
for t in "$@"; do
t="${t%/}"; n="$(basename "$t")"
case "$n" in "$prefix"*-standard) ;; *) continue ;; esac
python3 - "$t" <<'PY'
import os, re, sys
t = sys.argv[1]; name = os.path.basename(t)
NUM = r"-?\d+(?:\.\d+)?"
PATTERNS = [
    ("workspace height", re.compile(r"table[ _-]?top[ _-]?z|table[ _-]?top\s+(?:is\s+)?at\b|table surface is the plane|plane z\b", re.I)),
    ("height / plane", re.compile(r"\bz\s*=\s*\**" + NUM)),
    ("coordinates", re.compile(r"\(\s*" + NUM + r"\s*,\s*" + NUM + r"\s*(?:,\s*" + NUM + r"\s*)?\)")),
    ("world formula", re.compile(r"\bworld\s+[xyz]\s*=", re.I)),
    ("camera distance", re.compile(NUM + r"\s?m\s+(?:straight\s+)?(?:above|below|over|behind|in front of|beside|away from)\b", re.I)),
    ("camera scale on the scene", re.compile(r"per\s+pixel\s+on\b", re.I)),
]
ALLOWED_BEFORE = {"coordinates": re.compile(r"base|origin|robot", re.I),        # the robot's own pose stays
                  "height / plane": re.compile(r"floor", re.I),                   # BEHAVIOR: the floor z = 0 defines the frame
                  "workspace height": re.compile(r"floor", re.I)}
texts = {}
for f in ("instruction.md", "README.md"):
    p = os.path.join(t, f)
    if os.path.exists(p):
        texts[f] = open(p, encoding="utf-8").read()
m = re.search(r'^description\s*=\s*"(.*)"\s*$', open(os.path.join(t, "task.toml"), encoding="utf-8").read(), re.M)
texts["task.toml description"] = m.group(1) if m else ""
bad = []
for where, s in texts.items():
    for kind, rx in PATTERNS:
        for mm in rx.finditer(s):
            before = s[max(0, mm.start() - 40):mm.start()]
            if kind == "coordinates" and "." not in mm.group(0):
                continue                                   # array shapes such as (224,224,3)
            if kind in ALLOWED_BEFORE and ALLOWED_BEFORE[kind].search(before):
                continue
            line = s[:mm.start()].count("\n") + 1
            ctx = s[max(0, mm.start() - 50):mm.end() + 30].replace("\n", " ")
            bad.append(f"{where}:{line}: {kind}: ...{ctx}...")
if bad:
    print(f"FAIL {name}: a standard task of this benchmark never says where things are (object positions, world coordinates of the workspace):")
    for b in bad[:40]:
        print("  -", b)
    if len(bad) > 40:
        print(f"  ... {len(bad) - 40} more")
    sys.exit(1)
PY
[ $? -eq 0 ] || rc=1
done
exit $rc
