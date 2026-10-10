#!/usr/bin/env bash
# RoboPaint tooling convention (integrator, 2026-09-28; across families since 05:35): every copy of the shared tooling is
# byte-identical within one family (tasks/robopaint-<family>-*) AND across all families of the brush stack (kaishu, xingshu,
# caoshu, lettering, acrylic, oil): rcb_brush.py / rcb_brush_score.py,
# rcb_scorer.py, environment/rcb_client.py and the standard sim service environment/sim/server.py. A tooling change is rolled out
# to every family of the stack at once, each with its own re-validation (new rule features are opt-in per task through the
# instance's success rule, so an unchanged rule scores exactly as before). The process rules' module rcb_brush_strict.py (graders'
# side: tests/, environment/scorer/ or environment/sim/) is one more shared file.
# Usage: check-robopaint-tooling.sh [tasks dir]   (repo-level; run_all.sh calls it once)
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "${1:-$root/tasks}" <<'PY'
import collections, hashlib, os, sys
tasks = sys.argv[1]
NAMES = {"rcb_brush.py", "rcb_brush_score.py", "rcb_scorer.py", "rcb_client.py", "rcb_brush_strict.py"}
seen = collections.defaultdict(lambda: collections.defaultdict(dict))   # family -> role -> {sha: first task}
for t in sorted(os.listdir(tasks)):
    if not t.startswith("robopaint-") or not os.path.isfile(os.path.join(tasks, t, "task.toml")):
        continue
    fam = t.split("-")[1]
    for dp, dns, fns in os.walk(os.path.join(tasks, t)):
        dns[:] = [d for d in dns if d not in ("results", "__pycache__")]
        for f in fns:
            rel = os.path.relpath(os.path.join(dp, f), os.path.join(tasks, t))
            role = f if f in NAMES else ("environment/sim/server.py" if rel == os.path.join("environment", "sim", "server.py") else None)
            if role:
                h = hashlib.sha256(open(os.path.join(dp, f), "rb").read()).hexdigest()[:16]
                seen[fam][role].setdefault(h, f"{t}/{rel}")
bad = [f"robopaint-{fam}: {len(v)} versions of {role}: " + ", ".join(f"{h} ({p})" for h, p in sorted(v.items()))
       for fam, roles in sorted(seen.items()) for role, v in sorted(roles.items()) if len(v) > 1]
# across families of one stack (brush: rcb_brush.py): one version of every shared file (lead, 2026-09-28 05:35)
stacks = collections.defaultdict(list)
for fam, roles in seen.items():
    stacks["brush" if "rcb_brush.py" in roles else "other"].append(fam)
for stack, fams in sorted(stacks.items()):
    roles = sorted({r for f in fams for r in seen[f]})
    for role in roles:
        vers = {h: f"robopaint-{f}" for f in fams for h in seen[f].get(role, {})}
        if len(vers) > 1:
            bad.append(f"{stack} families ({', '.join(sorted(fams))}): {len(vers)} versions of {role}: "
                       + ", ".join(f"{h} ({f})" for h, f in sorted(vers.items())))
if bad:
    print("FAIL robopaint tooling (byte-identical within a family and across the families of a stack):")
    for b in bad:
        print("  -", b)
    sys.exit(1)
print(f"ok robopaint tooling: {len(seen)} families; shared files byte-identical within each family and across the families of "
      f"each stack ({', '.join(f'{k}: {len(v)}' for k, v in sorted(stacks.items()))})")
PY
