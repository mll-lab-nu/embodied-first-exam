#!/usr/bin/env bash
# Shared-source rules (PROTOCOL §2.1, D9: copies of shared sources are byte-identical). Two parts:
# 1. BEHAVIOR-1K, RoboLab, RoboWits, ManiGuard, MolmoSpaces, MyoSuite, DexJoCo, RoboTangle, BiGym 2.0 and YAMLab: within one benchmark, every mode, every copy of a shared file is byte-identical
#    (the generators copy them from the benchmark's template task unchanged):
#    - the tooling module rcb_<sim>.py wherever it sits (privileged environment/ and tests/, standard environment/sim/);
#    - the standard agent side environment/rcb_client.py + rcb1.py and the sim service environment/sim/ (server.py,
#      finalize.sh, run.sh, rcb1.py);
#    - the graders, tests/grade.py (one version per mode).
#    A change to one of them is rolled out to every task of the benchmark at once. Same approach as check-robopaint-tooling.sh.
# 2. The eai-standard/2.2 layer (every task whose metadata.protocol is 2.2: BEHAVIOR, RoboLab, RoboWits, RoboPaint, MolmoSpaces, MyoSuite, DexJoCo, YAMLab): the
#    agent's client environment/rcb_client.py + rcb1.py and the service's environment/sim/rcb_limited.py + rcb1.py +
#    run.sh are byte-identical to their source in scripts/eai_standard/ (docs/STANDARD_MODE_2_2.md), and the sidecar is
#    set up for crash recovery: `command: sh /srv/run.sh` (run.sh exits non-zero when the service crashes) and
#    `restart: on-failure:N` with N >= 3 (PROTOCOL §4.1, §4.7).
#    The eai-standard/2.4 layer (metadata.protocol 2.4: RoboTangle) is held to the same rules, with rcb_limited.py and
#    rcb_client.py from scripts/eai_standard/v2_4/ (docs/STANDARD_MODE_2_4.md) and 2.2's rcb1.py and run.sh.
# Usage: check-tooling-identity.sh [tasks dir]   (repo-level; run_all.sh calls it once)
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "${1:-$root/tasks}" "$root/scripts/eai_standard" <<'PY'
import collections, hashlib, os, re, sys, tomllib
tasks, src = sys.argv[1], sys.argv[2]
MODULE = {"behavior": "rcb_behavior.py", "robolab": "rcb_robolab.py", "robowits": "rcb_robowits.py", "maniguard": "rcb_maniguard.py",
          "molmospaces": "rcb_molmospaces.py", "myosuite": "rcb_myosuite.py",
          "dexjoco": "rcb_dexjoco.py", "robotangle": "rcb_topogym.py", "bigym2": "rcb_bigym2.py", "yamlab": "rcb_yamlab.py"}
SHARED = {"environment/rcb_client.py", "environment/rcb1.py", "environment/sim/server.py", "environment/sim/finalize.sh",
          "environment/sim/run.sh", "environment/sim/rcb1.py", "environment/sim/rcb_limited.py", "tests/grade.py"}
LAYER = {"environment/rcb_client.py": "rcb_client.py", "environment/rcb1.py": "rcb1.py", "environment/sim/rcb_limited.py": "rcb_limited.py",
         "environment/sim/rcb1.py": "rcb1.py", "environment/sim/run.sh": "run.sh"}
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]  # noqa: E731
canon = {f: sha(os.path.join(src, f)) for f in set(LAYER.values()) if os.path.isfile(os.path.join(src, f))}
V24 = {"rcb_limited.py", "rcb_client.py"}   # the 2.4 layer's own files (scripts/eai_standard/v2_4/); the rest is 2.2's
canon24 = {f: sha(os.path.join(src, "v2_4" if f in V24 else "", f)) for f in set(LAYER.values())
           if os.path.isfile(os.path.join(src, "v2_4" if f in V24 else "", f))}
seen = collections.defaultdict(lambda: collections.defaultdict(dict))   # benchmark -> role -> {sha: first copy}
dirs = collections.Counter(); bad = []; n_layer = 0


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


for t in sorted(os.listdir(tasks)):
    tt = os.path.join(tasks, t, "task.toml")
    if not os.path.isfile(tt):
        continue
    bench = t.split("-")[0]
    proto = str(tomllib.load(open(tt, "rb")).get("metadata", {}).get("protocol", ""))
    v24 = proto == "eai-standard/2.4"
    if v24 or re.fullmatch(r"(eai-standard|rcb-limited)/2\.2", proto):
        n_layer += 1
        ver, ref = ("2.4", canon24) if v24 else ("2.2", canon)
        for rel, f in sorted(LAYER.items()):
            p = os.path.join(tasks, t, rel)
            srcf = f"scripts/eai_standard/{'v2_4/' if v24 and f in V24 else ''}{f}"
            if not os.path.isfile(p):
                bad.append(f"{t}: {rel} missing (eai-standard/{ver} layer, {srcf})")
            elif sha(p) != ref.get(f):
                bad.append(f"{t}: {rel} differs from {srcf} (regenerate the task)")
        cf = os.path.join(tasks, t, "environment/docker-compose.yaml")
        blk = sim_service(cf) if os.path.isfile(cf) else ""
        m = re.search(r"^\s*restart:\s*[\"']?on-failure:(\d+)", blk, re.M)
        if not m or int(m.group(1)) < 3:
            bad.append(f"{t}: the sim service needs `restart: on-failure:N` with N >= 3 (crash recovery)")
        if not re.search(r"^\s*command:\s*[\"']?sh /srv/run\.sh[\"']?\s*$", blk, re.M):
            bad.append(f"{t}: the sim service must run `sh /srv/run.sh` (it exits non-zero when the service crashes)")
    if bench not in MODULE:
        continue
    dirs[bench] += 1
    mode = ("standard-realtime" if t.endswith("-standard-realtime") else "standard" if t.endswith(("-standard", "-limited"))
            else "privileged")
    for dp, dns, fns in os.walk(os.path.join(tasks, t)):
        dns[:] = [d for d in dns if d not in ("results", "__pycache__")]
        for f in fns:
            rel = os.path.relpath(os.path.join(dp, f), os.path.join(tasks, t)).replace(os.sep, "/")
            role = MODULE[bench] if f == MODULE[bench] else f"{mode} {rel}" if rel in SHARED else None
            if role:
                seen[bench][role].setdefault(sha(os.path.join(dp, f)), f"{t}/{rel}")
bad += [f"{b}: {len(v)} versions of {role}: " + ", ".join(f"{h} ({p})" for h, p in sorted(v.items()))
        for b, roles in sorted(seen.items()) for role, v in sorted(roles.items()) if len(v) > 1]
if bad:
    print("FAIL shared sources (byte-identical copies; the 2.2 / 2.4 layers as in scripts/eai_standard/):")
    for b in bad[:60]:
        print("  -", b)
    if len(bad) > 60:
        print(f"  ... {len(bad) - 60} more")
    sys.exit(1)
print("ok shared sources: " + ("; ".join(f"{b} {dirs[b]} task dirs, {len(seen[b])} shared files" for b in sorted(seen)) or "no BEHAVIOR / RoboLab / RoboWits / ManiGuard / MolmoSpaces / MyoSuite / DexJoCo / RoboTangle / BiGym 2.0 tasks")
      + f"; the eai-standard/2.2 / 2.4 layers in {n_layer} task dirs")
PY
