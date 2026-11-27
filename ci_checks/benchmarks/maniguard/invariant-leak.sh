#!/usr/bin/env bash
# INVARIANT hook (docs/protocol/README.md Appendix H.2: no answer or pointer to one in the agent's reach), this benchmark's
# own: ci_checks/run_invariants.sh runs it with every task directory in scope; it checks its benchmark's tasks
# (maniguard-*) in one pass.
# ManiGuard only (tasks/maniguard-*): ManiGuard publishes 40 scripted safe demonstrations per task, its data generator
# (scripted skeletons, grasp annotations) and its policy servers. None of it may be in reach of the agent (PROTOCOL Appendix H.2):
#  1. the agent's build context environment/ holds only the files the generator writes there (privileged: the Dockerfile,
#     compose file, the tooling and the frozen instance; standard: the client, its pins and the sim/ sidecar, the build
#     context of the sidecar's own image (its Dockerfile, .dockerignore));
#  2. nothing the agent reads (instruction.md, environment/ text files, and the files the sidecar takes from a files-only
#     image) names the demonstrations, the generator or the grasp annotations;
#  3. the frozen instance is exactly ManiGuard-Bench's two files plus our instance.json and NOTICE.
# Usage: invariant-leak.sh <task dirs...>   (the maniguard-* ones are checked)
set -uo pipefail
python3 - "$(cd "$(dirname "$0")/../../.." && pwd)" "$@" <<'PY'
import os, re, sys
from pathlib import Path
root = sys.argv[1]


def check(t: str) -> bool:
    name = os.path.basename(t); env = os.path.join(t, "environment"); bad = []
    INSTANCE = {"scene_ep1.json", "diagnostics.jsonl", "instance.json", "NOTICE"}
    if name.endswith("-privileged"):
        allowed = {"Dockerfile", "docker-compose.yaml", "rcb_maniguard.py"}
        dirs = {"instance": INSTANCE}
    else:
        allowed = {"Dockerfile", "docker-compose.yaml", "client-requirements.txt", "rcb_client.py", "rcb1.py"}
        dirs = {"sim": {"server.py", "finalize.sh", "run.sh", "rcb_limited.py", "rcb1.py", "rcb_maniguard.py", "live_video.py", "instance",
                 "Dockerfile", ".dockerignore"}}   # the sidecar's image: images/maniguard/Dockerfile (the recipe, normalize writes it),
                                                   # then sim/ at /srv and its shared files from files-only images
    dirs["rcb_monitor"] = {"limits.json"}   # the resource monitor sidecar's limits, mounted only into it (its code is in the image; check-monitor.py)
    if not name.endswith("-privileged"):    # the robot's MCP tools (docs/protocol/standard_mode.md "MCP tools"): the task's
        dirs["efe_mcp"] = {"manifest.json"}  # manifest.json; the server's files come from the files-only image standard-files
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
    sys.path.insert(0, os.path.join(root, "scripts")); import files_image   # noqa: E402
    got, problems = files_image.copied_from(Path(env) / "sim" / "Dockerfile")   # the sidecar's files from a files-only image
    bad.extend(f"environment/sim/Dockerfile: {x}" for x in problems)
    agent, problems = files_image.copied_from(Path(env) / "Dockerfile")   # the agent's: the client, the MCP server's files
    bad.extend(f"environment/Dockerfile: {x}" for x in problems)
    got.update(agent)
    texts += [str(src) for dest, src in sorted(got.items()) if dest.endswith((".py", ".md", ".txt", ".yaml", ".sh", ".json"))
              and os.path.basename(dest) not in ("rcb_limited.py", "rcb_client.py", "rcb1.py", "run.sh")]
    for p in texts:
        s = open(p, encoding="utf-8", errors="replace").read()
        for m in LEAK.finditer(s):
            line = s[:m.start()].count("\n") + 1
            bad.append(f"{os.path.relpath(p, t)}:{line}: names a reference solution source ({m.group(0)!r})")
    if bad:
        print(f"FAIL {name}: ManiGuard's public solutions must stay out of the agent's reach:")
        for b in bad[:40]:
            print("  -", b)
        return False
    return True


n, rc = 0, 0
for a in sys.argv[2:]:
    t = a.rstrip("/")
    if not os.path.basename(t).startswith("maniguard-") or not os.path.isfile(os.path.join(t, "task.toml")):
        continue
    n += 1
    if not check(t):
        rc = 1
if rc == 0:
    print(f"ok maniguard leak check: {n} task(s)")
sys.exit(rc)
PY
