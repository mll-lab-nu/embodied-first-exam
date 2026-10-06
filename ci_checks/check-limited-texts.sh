#!/usr/bin/env bash
# World-frame information in standard-mode texts (PROTOCOL §2.5, D7: decided per benchmark, consistent within it). This
# check enforces the declaration of FIVE benchmarks only: BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint and ManiGuard
# (docs/benchmarks/<bench>.md, "World-frame information"; eai-standard/2.2 § Never provided). Their standard tasks never
# say WHERE things are in the world: no object poses or positions and no world coordinates of workspace items (table /
# sheet heights, sheet or well centres, a pixel-to-world formula, a camera's distance to the scene), in anything that
# describes the task: instruction.md, README.md, the task.toml description. Names, inventories, categories, sizes,
# colours and a detailed goal are provided; so are the robot (its base pose included), camera calibration and world
# conventions (BEHAVIOR's "the floor is the plane z = 0" defines its world frame and stays). Only what a pattern can see
# is checked; a review covers the rest. Every other benchmark decides for itself and is not checked here; privileged
# tasks are privileged by design; the RoboPaint line family (excluded from the benchmark, still 2.0) is not checked.
# Task dirs: <bench>-...-standard (legacy spelling: -limited). Usage: check-limited-texts.sh tasks/<task-dir>
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"
case "$n" in
  robopaint-line-*) exit 0 ;;
  behavior-*-standard|robolab-*-standard|robowits-*-standard|robopaint-*-standard|maniguard-*-standard) ;;
  behavior-*-limited|robolab-*-limited|robowits-*-limited|robopaint-*-limited) ;;
  *) exit 0 ;;
esac
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
