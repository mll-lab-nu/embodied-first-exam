#!/usr/bin/env bash
# ADVISORY (docs/protocol/tasks.md#instructionmd: world-frame information in the texts is decided per benchmark, consistent within
# it). The benchmarks that declare "no world coordinates in the standard tasks' texts" (their tasks/<benchmark>/README.md,
# "World-frame information") are the folders of scripts/task_conventions.py NO_WORLD_FRAME_TEXTS; run_all.sh runs this
# once with the task directories in scope. Such a benchmark's standard tasks never say WHERE things are in the
# world: no object poses or positions and no world coordinates of workspace items (table / sheet heights, sheet or well
# centres, a pixel-to-world formula, a camera's distance to the scene), in anything that describes the task:
# instruction.md, README.md, the task.toml description. Names, inventories, categories, sizes, colours and a detailed goal
# are provided; so are the robot (its base pose included), camera calibration and world conventions ("the floor is the
# plane z = 0" defines a world frame and stays). Only what a pattern can see is checked; a review covers the rest.
# Usage: check-world-frame-texts.sh <task dirs...>   (the -standard ones of those benchmarks are checked)
set -uo pipefail
python3 - "$(cd "$(dirname "$0")/.." && pwd)" "$@" <<'PY'
import os, re, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
import task_conventions as tc  # noqa: E402
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


def check(t: str) -> bool:
    name = os.path.basename(t)
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
        return False
    return True


n, rc = 0, 0
for a in sys.argv[2:]:
    t = a.rstrip("/")
    if (not t.endswith("-standard") or not os.path.isfile(os.path.join(t, "task.toml"))
            or tc.bench_dir(t) not in tc.NO_WORLD_FRAME_TEXTS):
        continue
    n += 1
    rc |= 0 if check(t) else 1
if rc == 0:
    print(f"ok world-frame texts: {n} standard task(s) of {len(tc.NO_WORLD_FRAME_TEXTS)} benchmarks give no world coordinates")
sys.exit(rc)
PY
