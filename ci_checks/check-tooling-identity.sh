#!/usr/bin/env bash
# Shared-source rules (PROTOCOL §2.1, D9: copies of shared sources are byte-identical). Two parts:
# 1. BEHAVIOR-1K, RoboLab, RoboWits, ManiGuard, MolmoSpaces, MyoSuite, DexJoCo, DexHand, RoboARC, BiGym 2.0, YAMLab, RoboDojo, LabUtopia, AutoBio, Panda Dynamic Scenes and AM-Bench: within one benchmark, every mode, every copy of a shared file is byte-identical
#    (the generators copy them from the benchmark's template task unchanged):
#    - the tooling module rcb_<sim>.py wherever it sits (privileged environment/ and tests/, standard environment/sim/);
#    - the standard agent side environment/rcb_client.py + rcb1.py and the sim service environment/sim/ (server.py,
#      finalize.sh, run.sh, rcb1.py);
#    - the graders, tests/grade.py (one version per mode).
#    A change to one of them is rolled out to every task of the benchmark at once. Same approach as check-robopaint-tooling.sh.
# 2. The eai-standard/2.2 layer (every task whose metadata.protocol is 2.2: BEHAVIOR, RoboLab, RoboWits, RoboPaint, MolmoSpaces, MyoSuite, DexJoCo, DexHand, YAMLab, RoboDojo, LabUtopia, AutoBio, Panda Dynamic Scenes): the
#    agent's client environment/rcb_client.py + rcb1.py and the service's environment/sim/rcb_limited.py + rcb1.py +
#    run.sh are byte-identical to their source in scripts/eai_standard/ (docs/STANDARD_MODE.md), and the sidecar is
#    set up for crash recovery: `command: sh /srv/run.sh` (run.sh exits non-zero when the service crashes) and
#    `restart: on-failure:N` with N >= 3 (PROTOCOL §4.1, §4.7).
#    The eai-standard/2.4 layer (metadata.protocol 2.4: RoboARC) is held to the same rules, with rcb_limited.py and
#    rcb_client.py from scripts/eai_standard/v2_4/ (docs/STANDARD_MODE.md) and 2.2's rcb1.py and run.sh.
# 3. The eai-standard/2.3 realtime layer (every task whose metadata.protocol is 2.3: HumanoidBench, RoboOlympics, BiGym 2.0
#    standard-realtime): the service's environment/sim/rcb_realtime.py and the agent's environment/rcb_client.py are
#    byte-identical to their one source, scripts/humanoidbench/shared/realtime/ (docs/STANDARD_MODE.md,
#    "Standard-realtime mode"), and so is every other copy of that source under scripts/*/shared/realtime/.
# 4. The benchmarks whose generators have no check mode (review round 3, M6: a hand edit of one task with a refreshed
#    digest passed every check): DexToolBench and the MuJoCo Playground tasks that serve the same service (ALOHA, Panda;
#    scripts/dtb_mk_task.py, mj_mk_limited.py), MetaWorld+ (scripts/metaworldplus/generate.py) and RoboTwin 2.0
#    (scripts/robotwin_mk_*.py). Every file their generator writes unchanged into each task of a mode is byte-identical
#    within the benchmark and mode (FAMILY_SHARED: service, client, graders, tests/test.sh, Dockerfiles, the oracle's
#    runner; the Playground ALOHA and Panda standard tasks count as DexToolBench's, their privileged twins as a
#    benchmark each), the tooling module is one version in every mode, and the service is the one under images/ (MetaWorld+:
#    unchanged; the MuJoCo service: as scripts/task_conventions.py replace_words spells it). RoboTwin's privileged
#    tests/test.sh and solution/solve.sh differ by the task's name only and are compared with the name replaced; its
#    other shared files are also held to the template tasks by scripts/robotwin_sync_shared.py --check.
#    Not covered here: the per-task texts of these benchmarks (instruction.md, README.md, task.toml), which only a check
#    mode of their generators could compare.
# Usage: check-tooling-identity.sh [tasks dir]   (repo-level; run_all.sh calls it once)
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "${1:-$root/tasks}" "$root/scripts/eai_standard" <<'PY'
import collections, hashlib, os, re, sys, tomllib
from pathlib import Path
tasks, src = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.dirname(os.path.abspath(src))); import task_conventions as tc   # the mode registry (§2.16)
MODULE = {"behavior": "rcb_behavior.py", "robolab": "rcb_robolab.py", "robowits": "rcb_robowits.py", "maniguard": "rcb_maniguard.py",
          "molmospaces": "rcb_molmospaces.py", "myosuite": "rcb_myosuite.py",
          "dexjoco": "rcb_dexjoco.py", "dexhand": "rcb_dexhand.py", "roboarc": "rcb_topogym.py", "bigym2": "rcb_bigym2.py", "yamlab": "rcb_yamlab.py", "robodojo": "rcb_robodojo.py",
          "labutopia": "rcb_labutopia.py", "autobio": "rcb_autobio.py", "robofunolympics": "rcb_rfo.py",
          "pandadyn": "rcb_pandadyn.py",
          "ambench": "rcb_ambench.py",
          "cell": "rcb_rsb.py"}   # cell-: RoboSafeBench
SHARED = {"environment/rcb_client.py", "environment/rcb1.py", "environment/sim/server.py", "environment/sim/finalize.sh",
          "environment/sim/run.sh", "environment/sim/rcb1.py", "environment/sim/rcb_limited.py", "tests/grade.py"}
LAYER = {"environment/rcb_client.py": "rcb_client.py", "environment/rcb1.py": "rcb1.py", "environment/sim/rcb_limited.py": "rcb_limited.py",
         "environment/sim/rcb1.py": "rcb1.py", "environment/sim/run.sh": "run.sh"}
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]  # noqa: E731
# 4. benchmarks without a generator check mode: (label, tooling module) by directory prefix; a task that serves
# environment/sim/server_mj.py belongs to the DexToolBench family whatever its prefix (MuJoCo Playground ALOHA / Panda)
FAMILY = {"dextoolbench_": ("dextoolbench", "rcb_dtb.py"), "metaworldplus-": ("metaworldplus", "mw_tool.py"),
          "robotwin_2_0_": ("robotwin_2_0", None), "mujoco_playground_aloha_": ("mujoco_playground_aloha", "rcb_aloha.py"),
          "mujoco_playground_panda_": ("mujoco_playground_panda", "rcb_panda.py")}
FAMILY_SHARED = SHARED | {"environment/Dockerfile", "tests/Dockerfile", "tests/test.sh", "solution/solve.sh", "solution/oracle_replay.py",
                          "environment/sim/server_mj.py", "environment/sim/server_mw.py", "environment/sim/rcb_live.py"}
BY_NAME = {("robotwin_2_0", "privileged"): {"tests/test.sh", "solution/solve.sh"}}   # the same but for the task's own name
sys.path.insert(0, os.path.dirname(src))
from task_conventions import replace_words  # noqa: E402  (what normalize rewrites in a task's text files)
images = os.path.join(os.path.dirname(os.path.dirname(src)), "images")
FAMILY_SOURCE = {"environment/sim/server_mj.py": ("images/mujoco/limited/server_mj.py", replace_words),
                 "environment/sim/server_mw.py": ("images/metaworld/standard/server_mw.py", lambda x: x)}
src_sha = {}
for rel, (f, spell) in FAMILY_SOURCE.items():
    p = os.path.join(os.path.dirname(images), f)
    if os.path.isfile(p):
        src_sha[rel] = hashlib.sha256(spell(open(p, encoding="utf-8").read()).encode()).hexdigest()[:16]
canon = {f: sha(os.path.join(src, f)) for f in set(LAYER.values()) if os.path.isfile(os.path.join(src, f))}
V24 = {"rcb_limited.py", "rcb_client.py"}   # the 2.4 layer's own files (scripts/eai_standard/v2_4/); the rest is 2.2's
canon24 = {f: sha(os.path.join(src, "v2_4" if f in V24 else "", f)) for f in set(LAYER.values())
           if os.path.isfile(os.path.join(src, "v2_4" if f in V24 else "", f))}
seen = collections.defaultdict(lambda: collections.defaultdict(dict))   # benchmark -> role -> {sha: first copy}
dirs = collections.Counter(); bad = []; n_layer = 0
# the 2.3 realtime layer: one source, copied unchanged
RT_SRC = os.path.join(os.path.dirname(src), "humanoidbench", "shared", "realtime")
RT_LAYER = {"environment/sim/rcb_realtime.py": "rcb_realtime.py", "environment/rcb_client.py": "rcb_client.py"}
rt_canon = {f: sha(os.path.join(RT_SRC, f)) for f in set(RT_LAYER.values()) if os.path.isfile(os.path.join(RT_SRC, f))}
n_rt = 0
scripts_dir = os.path.dirname(src)
for b in sorted(os.listdir(scripts_dir)):
    for f in sorted(rt_canon):
        p = os.path.join(scripts_dir, b, "shared", "realtime", f)
        if os.path.isfile(p) and sha(p) != rt_canon[f]:
            bad.append(f"scripts/{b}/shared/realtime/{f} differs from scripts/humanoidbench/shared/realtime/{f} "
                       "(the eai-standard/2.3 layer has one source)")


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
    if proto == "eai-standard/2.3":
        n_rt += 1
        for rel, f in sorted(RT_LAYER.items()):
            p = os.path.join(tasks, t, rel)
            if not os.path.isfile(p):
                bad.append(f"{t}: {rel} missing (eai-standard/2.3 layer, scripts/humanoidbench/shared/realtime/{f})")
            elif sha(p) != rt_canon.get(f):
                bad.append(f"{t}: {rel} differs from scripts/humanoidbench/shared/realtime/{f} (regenerate the task)")
    if v24 or proto == "eai-standard/2.2":
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
    mode = tc.mode_of(Path(t))
    own_fam, module = next((v for k, v in FAMILY.items() if t.startswith(k)), (None, None))
    fam = "dextoolbench" if os.path.isfile(os.path.join(tasks, t, "environment/sim/server_mj.py")) else own_fam
    if fam:
        dirs[own_fam or fam] += 1
        own = t[len("robotwin_2_0_"):-len("-" + mode)] if fam == "robotwin_2_0" else ""
        for dp, dns, fns in os.walk(os.path.join(tasks, t)):
            dns[:] = [d for d in dns if d not in ("results", "__pycache__")]
            for f in fns:
                rel = os.path.relpath(os.path.join(dp, f), os.path.join(tasks, t)).replace(os.sep, "/")
                if module and f == module:              # the tooling module: one version in every mode of its own benchmark
                    seen[own_fam][module].setdefault(sha(os.path.join(dp, f)), f"{t}/{rel}")
                    continue
                role = f"{mode} {rel}" if rel in FAMILY_SHARED else None
                if not role:
                    continue
                h = sha(os.path.join(dp, f))
                if rel in BY_NAME.get((fam, mode), ()):
                    h = hashlib.sha256(open(os.path.join(dp, f), "rb").read().replace(own.encode(), b"@TASK@")).hexdigest()[:16]
                seen[fam][role].setdefault(h, f"{t}/{rel}")
                if rel in src_sha and h != src_sha[rel]:
                    bad.append(f"{t}: {rel} differs from {FAMILY_SOURCE[rel][0]} (the service has one source: change it there and regenerate)")
    if bench not in MODULE:
        continue
    dirs[bench] += 1
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
    print("FAIL shared sources (byte-identical copies; the 2.2 / 2.4 layers as in scripts/eai_standard/, the 2.3 layer as in scripts/humanoidbench/shared/realtime/):")
    for b in bad[:60]:
        print("  -", b)
    if len(bad) > 60:
        print(f"  ... {len(bad) - 60} more")
    sys.exit(1)
print("ok shared sources: " + ("; ".join(f"{b} {dirs[b]} task dirs, {len(seen[b])} shared files" for b in sorted(seen)) or "no BEHAVIOR / RoboLab / RoboWits / ManiGuard / MolmoSpaces / MyoSuite / DexJoCo / DexHand / RoboARC / BiGym 2.0 / YAMLab / LabUtopia / AutoBio tasks")
      + f"; the eai-standard/2.2 / 2.4 layers in {n_layer} task dirs; the eai-standard/2.3 realtime layer in {n_rt}")
PY
