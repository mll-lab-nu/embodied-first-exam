#!/usr/bin/env bash
# ManiGuard only (tasks/maniguard-*): ManiGuard publishes 40 scripted safe demonstrations per task, its data generator
# (scripted skeletons, grasp annotations) and its policy servers. None of it may be in reach of the agent (PROTOCOL §2.7):
#  1. the agent's build context environment/ holds only the files the generator writes there (privileged: the Dockerfile,
#     compose file, the tooling and the frozen instance; standard: the client, its pins and the sim/ sidecar, which compose
#     mounts into the sidecar only);
#  2. nothing the agent reads (instruction.md, environment/ text files) names the demonstrations, the generator or the
#     grasp annotations;
#  3. the frozen instance is exactly ManiGuard-Bench's two files plus our instance.json and NOTICE.
# Usage: check_leak.sh tasks/<task-dir>   (moved from ci_checks/check-maniguard-leak.sh, board 0124; run by invariant-leak.sh)
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"
case "$n" in maniguard-*) ;; *) exit 0 ;; esac
python3 - "$t" <<'PY'
import os, re, sys
t = sys.argv[1]; name = os.path.basename(t); env = os.path.join(t, "environment"); bad = []
INSTANCE = {"scene_ep1.json", "diagnostics.jsonl", "instance.json", "NOTICE"}
if name.endswith("-privileged"):
    allowed = {"Dockerfile", "docker-compose.yaml", "rcb_maniguard.py"}
    dirs = {"instance": INSTANCE}
else:
    allowed = {"Dockerfile", "docker-compose.yaml", "client-requirements.txt", "rcb_client.py", "rcb1.py"}
    dirs = {"sim": {"server.py", "finalize.sh", "run.sh", "rcb_limited.py", "rcb1.py", "rcb_maniguard.py", "live_video.py", "instance"}}
dirs["rcb_monitor"] = {"limits.json"}   # the resource monitor sidecar's limits, mounted only into it (its code is in the image; check-monitor.py)
for f in sorted(os.listdir(env)):
    p = os.path.join(env, f)
    if os.path.isdir(p):
        if f not in dirs:
            bad.append(f"environment/{f}/: unexpected directory")
            continue
        for g in sorted(os.listdir(p)):
            if g not in dirs[f]:
                bad.append(f"environment/{f}/{g}: not a file the generator writes")
    elif f not in allowed:
        bad.append(f"environment/{f}: not a file the generator writes")
inst = os.path.join(env, "instance") if name.endswith("-privileged") else os.path.join(env, "sim", "instance")
if not os.path.isdir(inst) or set(os.listdir(inst)) != INSTANCE:
    bad.append(f"{os.path.relpath(inst, t)}: must hold exactly {sorted(INSTANCE)}")
LEAK = re.compile(r"datagen-[a-z]+-v\d|maniguard-grasp-annotations|grasp_db|grasp annotation|datagen/(?:families|executor|driver)|"
                  r"skeleton|lerobot|episodes\.jsonl|oracle_trajectory|oracle_qpos|/solution/", re.I)
texts = [os.path.join(t, "instruction.md")]
for dp, dns, fns in os.walk(env):
    for f in fns:
        if f.endswith((".py", ".md", ".txt", ".yaml", ".sh", "Dockerfile")) and f not in ("rcb_limited.py", "rcb_client.py", "rcb1.py", "run.sh"):
            texts.append(os.path.join(dp, f))
for p in texts:
    s = open(p, encoding="utf-8", errors="replace").read()
    for m in LEAK.finditer(s):
        line = s[:m.start()].count("\n") + 1
        bad.append(f"{os.path.relpath(p, t)}:{line}: names a reference solution source ({m.group(0)!r})")
if bad:
    print(f"FAIL {name}: ManiGuard's public solutions must stay out of the agent's reach:")
    for b in bad[:40]:
        print("  -", b)
    sys.exit(1)
print(f"ok {name}: agent side = tooling + frozen instance; no reference-solution sources named")
PY
