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
# TopoGym frozen packages and explicit v3/v4 generations are checked separately by
# check-topogym-tooling.py; the shared eai-standard layer below remains mandatory.
# Usage: check-tooling-identity.sh [tasks dir]   (repo-level; run_all.sh calls it once)
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "${1:-$root/tasks}" "$root" <<'PY'
import collections, hashlib, os, re, sys
tasks = sys.argv[1]
MODULE = {"behavior": "rcb_behavior.py", "robolab": "rcb_robolab.py", "robowits": "rcb_robowits.py", "topogym": "rcb_topogym.py"}
SHARED = {"environment/rcb_client.py", "environment/rcb1.py", "environment/sim/server.py", "environment/sim/finalize.sh",
          "environment/sim/run.sh", "environment/sim/rcb1.py", "environment/sim/rcb_limited.py", "environment/sim/replay.py",
          "tests/grade.py"}
LAYER = {"environment/rcb_client.py", "environment/rcb1.py", "environment/sim/rcb_limited.py", "environment/sim/rcb1.py"}
LAYER_BENCH = ("behavior", "robolab", "robowits", "robopaint", "topogym")
layer = collections.defaultdict(dict)   # role -> {sha: first copy}, across the pre-v1.0 2.2 dirs (the original -limited ones)
EAI = {"environment/rcb_client.py": "rcb_client.py", "environment/rcb1.py": "rcb1.py", "environment/sim/rcb_limited.py": "rcb_limited.py",
       "environment/sim/rcb1.py": "rcb1.py", "environment/sim/run.sh": "run.sh"}
eai_src = os.path.join(sys.argv[2], "scripts", "eai_standard")
eai = {f: hashlib.sha256(open(os.path.join(eai_src, f), "rb").read()).hexdigest()[:16] for f in set(EAI.values())}
v1_bad, n_v1 = [], 0


def sim_service(compose: str) -> str:
    """The `sim:` service block of a compose file (indentation-based, no YAML dependency)."""
    out, inside = [], False
    for line in open(compose).read().splitlines():
        ind = len(line) - len(line.lstrip())
        if line.strip() and ind <= 2 and inside:
            break
        if re.match(r"^  sim:\s*$", line):
            inside = True; continue
        if inside:
            out.append(line)
    return "\n".join(out)


seen = collections.defaultdict(lambda: collections.defaultdict(dict))   # benchmark -> role -> {sha: first copy}
dirs = collections.Counter()
for t in sorted(os.listdir(tasks)):
    bench = t.split("-")[0]
    if bench in LAYER_BENCH and t.endswith("-standard") and os.path.isfile(os.path.join(tasks, t, "task.toml")):
        n_v1 += 1
        for rel, f in sorted(EAI.items()):
            p = os.path.join(tasks, t, rel)
            if not os.path.isfile(p):
                v1_bad.append(f"{t}: {rel} missing (eai-standard/2.2 layer, scripts/eai_standard/{f})")
            elif hashlib.sha256(open(p, "rb").read()).hexdigest()[:16] != eai[f]:
                v1_bad.append(f"{t}: {rel} differs from scripts/eai_standard/{f} (regenerate the task)")
        cf = os.path.join(tasks, t, "environment/docker-compose.yaml")
        blk = sim_service(cf) if os.path.isfile(cf) else ""
        m = re.search(r"^\s*restart:\s*[\"']?on-failure:(\d+)", blk, re.M)
        if not m or int(m.group(1)) < 3:
            v1_bad.append(f"{t}: the sim service needs `restart: on-failure:N` with N >= 3 (crash recovery)")
        if not re.search(r"^\s*command:\s*[\"']?sh /srv/run\.sh[\"']?\s*$", blk, re.M):
            v1_bad.append(f"{t}: the sim service must run `sh /srv/run.sh` (it exits non-zero when the service crashes)")
    if bench in LAYER_BENCH and t.endswith("-limited") and os.path.isfile(os.path.join(tasks, t, "task.toml")):
        for rel in sorted(LAYER):
            p = os.path.join(tasks, t, rel)
            h = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16] if os.path.isfile(p) else "MISSING"
            layer[rel].setdefault(h, f"{t}/{rel}")
    if bench == "topogym":
        continue  # Versioned and frozen inventories are checked below.
    if bench not in MODULE or not os.path.isfile(os.path.join(tasks, t, "task.toml")):
        continue
    module = MODULE[bench]
    dirs[bench] += 1
    mode = "limited" if t.endswith(("-limited", "-standard")) else "unlimited"
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
bad += [f"pre-v1.0 rcb-limited/2.2 layer: {len(v)} versions of {role} across {', '.join(LAYER_BENCH)}: " + ", ".join(f"{h} ({p})" for h, p in sorted(v.items()))
        for role, v in sorted(layer.items()) if len(v) > 1]
bad += v1_bad
import json, subprocess
root = sys.argv[2]
topogym = subprocess.run([sys.executable, os.path.join(root, "ci_checks", "check-topogym-tooling.py"), tasks])
if topogym.returncode:
    bad.append("TopoGym tooling generation validation failed")
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
      + f"; the eai-standard/2.2 layer = scripts/eai_standard/ in {n_v1} standard dirs; the pre-v1.0 layer ({len(layer)} files) "
      f"one version across the original -limited dirs")
PY
