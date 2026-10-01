#!/usr/bin/env bash
# Shared-file convention for BEHAVIOR-1K, RoboLab and RoboWits (AGENTS.md: "keep the tooling file identical across a
# benchmark's tasks"; the generators copy these files from the benchmark's template task unchanged). Within one
# benchmark, both modes, every copy of a shared file is byte-identical:
#   - the tooling module rcb_<sim>.py wherever it sits (unlimited environment/ and tests/, limited environment/sim/);
#   - the limited agent side environment/rcb_client.py + rcb1.py and the sim service environment/sim/ (server.py,
#     finalize.sh, run.sh, rcb1.py);
#   - the graders, tests/grade.py (one version per mode).
# A change to one of them is rolled out to every task of the benchmark at once. Same approach as check-robopaint-tooling.sh.
# Across the rcb-limited/2.2 benchmarks (BEHAVIOR, RoboLab, RoboWits, RoboPaint) the limited layer is ONE version: the agent's
# client environment/rcb_client.py + rcb1.py and the services' environment/sim/rcb_limited.py + rcb1.py
# (docs/LIMITED_MODE_PROTOCOL.md).
# TopoGym (adapted from robot_coding_bench fa59c1a6): topogym is one more benchmark (tooling rcb_topogym.py) and part of the
# 2.2 layer; the files copied from robot_coding_bench (ci_checks/rcb_vendor.json "verbatim") must still be byte-identical
# to the reference blobs recorded there.
# TopoGym has two tooling generations (2026-09-30): the tier dirs topogym-<family>-{easy,medium,hard}-i00[-limited] carry
# the current template byte for byte (his grasp configuration, float32 joint limits, the live-end replay); Jianwen's original
# frozen instances topogym-<family>-i00[-limited] keep HIS template as at 76583213 (his own re-render in 76583213; their
# grasp behaviour stays as authored): each group is checked on its own, against its own template.
# The interlocked_claws tier dirs (topogym-interlocked-claws-*) are a third group (user decision 2026-10-01, option i): their
# rcb_topogym.py is common/rcb_topogym_interlocked.py (the template + the pre-weld gripper fix); every other shared file of
# theirs is the common template's.
# Usage: check-tooling-identity.sh [tasks dir]   (repo-level; run_all.sh calls it once)
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "${1:-$root/tasks}" "$root" <<'PY'
import collections, hashlib, os, re, sys
tasks = sys.argv[1]
TOPOGYM_TIER = re.compile(r"topogym-.+-(easy|medium|hard)-i\d\d(-limited)?$")
# His template as at 76583213 (sha256[:16]), which the original topogym-<family>-i00[-limited] dirs keep.
TOPOGYM_ORIGINAL = {"rcb_topogym.py": "4b3d078c9cad5752", "unlimited tests/grade.py": "3e8f49637224dd2a",
                    "limited environment/sim/server.py": "7cd7f56234ce2471", "limited tests/grade.py": "f4456130fa54f816",
                    "limited environment/rcb_client.py": "75bc7dffc6e49ecf", "limited environment/rcb1.py": "a930d8eb6619b669",
                    "limited environment/sim/rcb1.py": "a930d8eb6619b669", "limited environment/sim/rcb_limited.py": "4a2f98d1f94b167f"}
MODULE = {"behavior": "rcb_behavior.py", "robolab": "rcb_robolab.py", "robowits": "rcb_robowits.py", "topogym": "rcb_topogym.py"}
SHARED = {"environment/rcb_client.py", "environment/rcb1.py", "environment/sim/server.py", "environment/sim/finalize.sh",
          "environment/sim/run.sh", "environment/sim/rcb1.py", "environment/sim/rcb_limited.py", "tests/grade.py"}
LAYER = {"environment/rcb_client.py", "environment/rcb1.py", "environment/sim/rcb_limited.py", "environment/sim/rcb1.py"}
LAYER_BENCH = ("behavior", "robolab", "robowits", "robopaint", "topogym")
layer = collections.defaultdict(dict)   # role -> {sha: first copy}, across the 2.2 benchmarks
seen = collections.defaultdict(lambda: collections.defaultdict(dict))   # benchmark -> role -> {sha: first copy}
dirs = collections.Counter()
for t in sorted(os.listdir(tasks)):
    bench = t.split("-")[0]
    if bench in LAYER_BENCH and t.endswith("-limited") and os.path.isfile(os.path.join(tasks, t, "task.toml")):
        for rel in sorted(LAYER):
            p = os.path.join(tasks, t, rel)
            h = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16] if os.path.isfile(p) else "MISSING"
            layer[rel].setdefault(h, f"{t}/{rel}")
    if bench not in MODULE or not os.path.isfile(os.path.join(tasks, t, "task.toml")):
        continue
    module = MODULE[bench]
    if bench == "topogym" and not TOPOGYM_TIER.match(t):
        bench = "topogym (original i00)"
    elif bench == "topogym" and t.startswith("topogym-interlocked-claws-"):
        bench = "topogym (interlocked)"
    dirs[bench] += 1
    mode = "limited" if t.endswith("-limited") else "unlimited"
    for dp, dns, fns in os.walk(os.path.join(tasks, t)):
        dns[:] = [d for d in dns if d not in ("results", "__pycache__")]
        for f in fns:
            rel = os.path.relpath(os.path.join(dp, f), os.path.join(tasks, t)).replace(os.sep, "/")
            role = module if f == module else f"{mode} {rel}" if rel in SHARED else None
            if role:
                h = hashlib.sha256(open(os.path.join(dp, f), "rb").read()).hexdigest()[:16]
                seen[bench][role].setdefault(h, f"{t}/{rel}")
bad = [f"{b}: {len(v)} versions of {role}: " + ", ".join(f"{h} ({p})" for h, p in sorted(v.items()))
       for b, roles in sorted(seen.items()) for role, v in sorted(roles.items()) if len(v) > 1]
bad += [f"rcb-limited/2.2 layer: {len(v)} versions of {role} across {', '.join(LAYER_BENCH)}: " + ", ".join(f"{h} ({p})" for h, p in sorted(v.items()))
        for role, v in sorted(layer.items()) if len(v) > 1]
import json, subprocess
root = sys.argv[2]
template = os.path.join(root, "harbor_templates", "topogym")
canonical = {"rcb_topogym.py": "common/rcb_topogym.py",
             "unlimited tests/grade.py": "unlimited/tests/grade.py"}
canonical.update({"limited " + rel: "limited/" + rel for rel in SHARED
                  if os.path.isfile(os.path.join(template, "limited", rel))})
VARIANT_TOOL = {"topogym (interlocked)": "common/rcb_topogym_interlocked.py"}
for group in ("topogym", "topogym (interlocked)"):
    for role, rel in canonical.items():
        rel = VARIANT_TOOL.get(group, rel) if role == "rcb_topogym.py" else rel
        with open(os.path.join(template, rel), "rb") as f:
            expected = hashlib.sha256(f.read()).hexdigest()[:16]
        for actual, path in seen.get(group, {}).get(role, {}).items():
            if actual != expected:
                bad.append(f"{path}: differs from public template {rel}")
for role, versions in seen.get("topogym (original i00)", {}).items():
    for actual, path in versions.items():
        if actual != TOPOGYM_ORIGINAL.get(role):
            bad.append(f"{path}: differs from his 76583213 template ({role})")
vendor = json.load(open(os.path.join(root, "ci_checks", "rcb_vendor.json")))
for rel in vendor["verbatim"]:
    p = os.path.join(root, rel)
    got = subprocess.run(["git", "hash-object", p], capture_output=True, text=True).stdout.strip() if os.path.isfile(p) else "MISSING"
    if got != vendor["blobs"].get(rel):
        bad.append(f"{rel}: blob {got[:12]} != robot_coding_bench {vendor['commit'][:8]} blob {vendor['blobs'].get(rel, '?')[:12]}")
if bad:
    print("FAIL tooling identity (every copy of a shared file byte-identical within a benchmark):")
    for b in bad:
        print("  -", b)
    sys.exit(1)
print("ok tooling identity: " + "; ".join(f"{b} {dirs[b]} task dirs, {len(seen[b])} shared files" for b in sorted(seen))
      + f"; the rcb-limited/2.2 layer ({len(layer)} files) one version across {', '.join(LAYER_BENCH)}")
PY
