#!/usr/bin/env bash
# Shared-source rules (docs/protocol/tasks.md: copies of shared sources are byte-identical). Two parts:
# 1. BEHAVIOR-1K, RoboLab, RoboWits, ManiGuard, MolmoSpaces, MyoSuite, DexJoCo, DexHand, RoboARC, BiGym 2.0, YAMLab, RoboDojo, Panda Dynamic Scenes, AM-Bench, LabUtopia, AutoBio and EmbodiedSWE: within one benchmark (RoboARC's IKEA suite, roboarc-ikea-*, is a group of its own), every mode, every copy of a shared file is byte-identical
#    (one source per benchmark, copied unchanged):
#    - the tooling module rcb_<sim>.py wherever it sits (privileged environment/ and tests/, standard environment/sim/);
#    - the standard agent side environment/rcb_client.py + rcb1.py and the sim service environment/sim/ (server.py,
#      finalize.sh, run.sh, rcb1.py);
#    - the graders, tests/grade.py (one version per mode).
#    A file a task's Dockerfile takes from a files-only image (`COPY --from=<image@digest> /<file> <dest>`, images/<name>/
#    FILES.json, scripts/files_image.py) counts as a copy at <context>/<basename of dest> with FILES.json's sha256, and
#    the line must name the image FILES.json pins (contexts: environment/, tests/ and a sidecar's own environment/sim/ or
#    environment/scorer/).
#    A change to one of them is rolled out to every task of the benchmark at once. Same approach as ci_checks/benchmarks/robopaint/advisory-tooling.sh.
#    Tasks the benchmark's own exporter wrote (task.toml [metadata] exporter: Embodied Olympics, docs/protocol/tasks.md#modes) are a group of their own,
#    one per exporter and [metadata] skill_in_loop.
# 2. The shared layer (every task whose sim image takes rcb_limited.py, task_conventions.service_layer: BEHAVIOR, RoboLab, RoboWits, RoboPaint, MolmoSpaces, MyoSuite, DexJoCo, DexHand, YAMLab, RoboDojo, LabUtopia, AutoBio, EmbodiedSWE): the
#    agent's client environment/rcb_client.py + rcb1.py and the service's environment/sim/rcb_limited.py + rcb1.py +
#    run.sh are byte-identical to their source in embodied_first_exam/standard/ (docs/protocol/eai-standard.md), and the sidecar is
#    set up for crash recovery: `command: sh /srv/run.sh` (run.sh exits non-zero when the service crashes) and
#    `restart: on-failure:N` with N >= 3 (embodied_first_exam/standard/README.md#crash-recovery).
#    The operations layer (RoboARC, its IKEA suite included) is held to the same rules, with rcb_limited.py and
#    rcb_client.py from embodied_first_exam/standard/operations/ (docs/protocol/eai-standard.md) and the shared layer's rcb1.py and run.sh.
# 3. The realtime layer (every task on realtime/rcb_realtime.py: HumanoidBench, BiGym 2.0
#    realtime): the service's environment/sim/rcb_realtime.py and the agent's environment/rcb_client.py are
#    byte-identical to their one source, embodied_first_exam/standard/realtime/ (docs/protocol/eai-standard.md,
#    "Realtime mode").
# 4. DexToolBench and the MuJoCo Playground tasks that serve the same service (ALOHA, Panda), MetaWorld+ and RoboTwin
#    2.0. Every file shared by the tasks of a mode is byte-identical
#    within the benchmark and mode (FAMILY_SHARED: service, client, graders, tests/test.sh, Dockerfiles, the oracle's
#    runner; the Playground ALOHA and Panda standard tasks count as DexToolBench's, their privileged twins as a
#    benchmark each), the tooling module is one version in every mode, and the service is its one source,
#    embodied_first_exam/benchmarks/dextoolbench/sim/server_mj.py (the MuJoCo Playground copy is the same file) or
#    embodied_first_exam/benchmarks/metaworldplus/sim/server_mw.py. RoboTwin's privileged
#    tests/test.sh and solution/solve.sh differ by the task's name only and are compared with the name replaced.
#    Not covered here: the per-task texts of these benchmarks (instruction.md, README.md, task.toml).
# 5. The sidecar service rcb_service.py (docs/protocol/eai-standard.md; under the realtime layer too) and the live
#    video live_video.py have one source each, embodied_first_exam/standard/sidecar/rcb_service.py and
#    embodied_first_exam/standard/live_video.py (the tasks take them from the files-only image standard-files): no
#    benchmark carries a copy (embodied_first_exam/benchmarks/**), and a base image's copy (images/*/tools/**: abc-sim's,
#    built into its image) is byte-identical to the source.
# Usage: check-tooling-identity.sh [tasks dir]   (repo-level; run_all.sh calls it once)
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "${1:-$root/tasks}" "$root/embodied_first_exam/standard" <<'PY'
import collections, hashlib, os, re, sys, tomllib
from pathlib import Path
tasks, src = sys.argv[1], sys.argv[2]
ROOTD = os.path.dirname(os.path.dirname(os.path.abspath(src)))   # the repository (src: embodied_first_exam/standard)
sys.path.insert(0, os.path.join(ROOTD, "scripts")); import task_conventions as tc   # the mode registry (§3)
MODULE = {"behavior": "rcb_behavior.py", "robolab": "rcb_robolab.py", "robowits": "rcb_robowits.py", "maniguard": "rcb_maniguard.py",
          "molmospaces": "rcb_molmospaces.py", "myosuite": "rcb_myosuite.py",
          "dexjoco": "rcb_dexjoco.py", "dexhand": "rcb_dexhand.py", "roboarc": "rcb_topogym.py", "bigym2": "rcb_bigym2.py", "yamlab": "rcb_yamlab.py", "robodojo": "rcb_robodojo.py",
          "labutopia": "rcb_labutopia.py", "autobio": "rcb_autobio.py",
          "embodied-olympics": "rcb_rfo.py",
          "pandadyn": "rcb_pandadyn.py",
          "ambench": "rcb_ambench.py", "ispatialgym": "rcb_ispatialgym.py",
          "roboarc-ikea": "rcb_ikea.py",   # RoboARC's IKEA suite (roboarc-ikea-*)
          "ese": "rcb_ese.py",   # ese-: Embodied Safety Exam
          "embodiedswe": "rcb_embodiedswe.py"}
SHARED = {"environment/rcb_client.py", "environment/rcb1.py", "environment/sim/server.py", "environment/sim/finalize.sh",
          "environment/sim/run.sh", "environment/sim/rcb1.py", "environment/sim/rcb_limited.py", "tests/grade.py"}
LAYER = {"environment/rcb_client.py": "rcb_client.py", "environment/rcb1.py": "rcb1.py", "environment/sim/rcb_limited.py": "rcb_limited.py",
         "environment/sim/rcb1.py": "rcb1.py", "environment/sim/run.sh": "run.sh"}
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]  # noqa: E731
# 4. (label, tooling module) by directory prefix; a task that serves
# environment/sim/server_mj.py belongs to the DexToolBench family whatever its prefix (MuJoCo Playground ALOHA / Panda)
FAMILY = {"dextoolbench_": ("dextoolbench", "rcb_dtb.py"), "metaworldplus-": ("metaworldplus", "mw_tool.py"),
          "robotwin_2_0_": ("robotwin_2_0", None), "mujoco_playground_aloha_": ("mujoco_playground_aloha", "rcb_aloha.py"),
          "mujoco_playground_panda_": ("mujoco_playground_panda", "rcb_panda.py")}
FAMILY_SHARED = SHARED | {"environment/Dockerfile", "tests/Dockerfile", "tests/test.sh", "solution/solve.sh", "solution/oracle_replay.py",
                          "environment/sim/server_mj.py", "environment/sim/server_mw.py", "environment/sim/rcb_live.py"}
BY_NAME = {("robotwin_2_0", "privileged"): {"tests/test.sh", "solution/solve.sh"}}   # the same but for the task's own name
images = os.path.join(ROOTD, "images")
FAMILY_SOURCE = {"environment/sim/server_mj.py": "embodied_first_exam/benchmarks/dextoolbench/sim/server_mj.py",
                 "environment/sim/server_mw.py": "embodied_first_exam/benchmarks/metaworldplus/sim/server_mw.py"}
src_sha = {rel: sha(os.path.join(ROOTD, f)) for rel, f in FAMILY_SOURCE.items() if os.path.isfile(os.path.join(ROOTD, f))}
OPS_OWN = {"rcb_limited.py", "rcb_client.py"}   # the operations layer's own files (embodied_first_exam/standard/operations/); the rest is the shared layer's
src_shared = lambda f: f  # noqa: E731  (each layer: its file's path under embodied_first_exam/standard/)
src_ops = lambda f: f"operations/{f}" if f in OPS_OWN else f  # noqa: E731
canon_of = lambda files, at: {f: sha(os.path.join(src, at(f))) for f in set(files) if os.path.isfile(os.path.join(src, at(f)))}  # noqa: E731
canon, canon_ops = canon_of(LAYER.values(), src_shared), canon_of(LAYER.values(), src_ops)
# files-only images (scripts/files_image.py): a file's one source -> the sha256 FILES.json pins for it
import files_image  # noqa: E402
PINNED = {}
for fj in sorted(Path(images).glob("*/FILES.json")):
    s = files_image.spec(fj.parent.name)
    PINNED.update({Path(ROOTD) / s["source"] / f: h for f, h in s["files"].items()})


def from_files_image(task_dir: str) -> dict:
    """{<context>/<basename of dest>: sha} of the files the task's Dockerfiles take from a files-only image (FILES.json's
    sha256 of each: what the pinned image holds); a line files_image.copied_from cannot resolve is a failure. A sidecar
    built from its own directory (environment/sim/, environment/scorer/: its Dockerfile, the directory at /srv) counts
    at environment/<dir>/<its path under /srv>: where the directory's copy would be."""
    got = {}
    for ctx in ("environment", "tests", "environment/sim", "environment/scorer"):
        out, problems = files_image.copied_from(Path(task_dir) / ctx / "Dockerfile")
        bad.extend(f"{os.path.basename(task_dir)}: {p} (regenerate the task)" for p in problems)
        for dest, f in out.items():
            side = ctx.count("/") and dest.startswith("/srv/")
            got[f"{ctx}/{dest[len('/srv/'):] if side else os.path.basename(dest)}"] = PINNED[f][:16]
    return got


seen = collections.defaultdict(lambda: collections.defaultdict(dict))   # benchmark -> role -> {sha: first copy}
dirs = collections.Counter(); bad = []; n_layer = 0
# the realtime layer: one source, copied unchanged
RT_LAYER = {"environment/sim/rcb_realtime.py": "rcb_realtime.py", "environment/rcb_client.py": "rcb_client.py"}
src_rt = lambda f: f"realtime/{f}"  # noqa: E731
rt_canon = canon_of(RT_LAYER.values(), src_rt)
n_rt = 0


def check_layer(t: str, layer: dict, ref: dict, at, name: str, img: dict) -> None:
    """Every file of a layer (task path -> source file) is in the task, or taken from a files-only image, byte-identical
    to its source under embodied_first_exam/standard/ (`at`: the file's path there)."""
    for rel, f in sorted(layer.items()):
        p = os.path.join(TDIR[t], rel)
        srcf = f"embodied_first_exam/standard/{at(f)}"
        if not os.path.isfile(p) and rel in img:
            if img[rel] != (ref.get(f) or "")[:16]:
                bad.append(f"{t}: {rel} (from a files-only image) differs from {srcf}")
        elif not os.path.isfile(p):
            bad.append(f"{t}: {rel} missing ({name} layer, {srcf})")
        elif sha(p) != ref.get(f):
            bad.append(f"{t}: {rel} differs from {srcf} (regenerate the task)")


# task dirs: tasks/<benchmark folder>/<task>/ (task_conventions.iter_tasks), or a flat tree of task dirs
TDIR = {p.name: str(p) for p in tc.iter_tasks(tasks)} or {d: os.path.join(tasks, d) for d in os.listdir(tasks)}
for t in sorted(TDIR):
    tt = os.path.join(TDIR[t], "task.toml")
    if not os.path.isfile(tt):
        continue
    bench = ("embodied-olympics" if t.startswith("embodied-olympics-")   # a two-word prefix
             else "roboarc-ikea" if t.startswith("roboarc-ikea-")         # RoboARC's IKEA suite: its own sources (rcb_ikea.py)
             else t.split("-")[0])
    meta = tomllib.load(open(tt, "rb")).get("metadata", {})
    layer = tc.service_layer(Path(TDIR[t]))
    img = from_files_image(TDIR[t])     # layer files the image build takes from a files-only image
    if layer == "realtime":
        n_rt += 1
        check_layer(t, RT_LAYER, rt_canon, src_rt, "realtime", img)
    if layer in ("shared", "operations"):
        n_layer += 1
        check_layer(t, LAYER, *((canon_ops, src_ops, "operations") if layer == "operations" else (canon, src_shared, "shared")), img)
        cf = os.path.join(TDIR[t], "environment/docker-compose.yaml")
        blk = tc.service_block(open(cf).read(), "sim") if os.path.isfile(cf) else ""
        m = re.search(r"^\s*restart:\s*[\"']?on-failure:(\d+)", blk, re.M)
        if not m or int(m.group(1)) < 3:
            bad.append(f"{t}: the sim service needs `restart: on-failure:N` with N >= 3 (crash recovery)")
        if not re.search(r"^\s*command:\s*[\"']?sh /srv/run\.sh[\"']?\s*$", blk, re.M):
            bad.append(f"{t}: the sim service must run `sh /srv/run.sh` (it exits non-zero when the service crashes)")
    mode = tc.mode_of(Path(t))
    own_fam, module = next((v for k, v in FAMILY.items() if t.startswith(k)), (None, None))
    fam = "dextoolbench" if os.path.isfile(os.path.join(TDIR[t], "environment/sim/server_mj.py")) else own_fam
    if fam:
        dirs[own_fam or fam] += 1
        own = t[len("robotwin_2_0_"):-len("-" + mode)] if fam == "robotwin_2_0" else ""
        for dp, dns, fns in os.walk(TDIR[t]):
            dns[:] = [d for d in dns if d not in ("results", "__pycache__")]
            for f in fns:
                rel = os.path.relpath(os.path.join(dp, f), TDIR[t]).replace(os.sep, "/")
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
                    bad.append(f"{t}: {rel} differs from {FAMILY_SOURCE[rel]} (the service has one source: change it there and regenerate)")
        for rel, h in sorted(img.items()):     # the copies the image builds put in place (a sidecar's from its Dockerfile)
            if module and os.path.basename(rel) == module:
                seen[own_fam][module].setdefault(h, f"{t}/{rel} (files image)")
            elif rel in FAMILY_SHARED and rel not in BY_NAME.get((fam, mode), ()):
                seen[fam][f"{mode} {rel}"].setdefault(h, f"{t}/{rel} (files image)")
                if rel in src_sha and h != src_sha[rel][:16]:
                    bad.append(f"{t}: {rel} (from a files-only image) differs from {FAMILY_SOURCE[rel]} (the service has one source)")
    if bench not in MODULE:
        continue
    module = MODULE[bench]
    if meta.get("exporter"):   # written by the benchmark's own exporter (Embodied Olympics, docs/protocol/tasks.md#modes; Embodied Safety Exam 0.5.4): its own sources
        # one group per exporter and skill-in-the-loop setting: Embodied Olympics - Match's table-tennis privileged twins come
        # from their own simulator's exporter (tools.tt_fullsim, #282 / #325) and the low-level matches with the agent's
        # skill in the loop have their own realtime grader (#300); each is shared within its group
        bench += f" (exported: {meta['exporter']}" + (f", {meta['skill_in_loop']}" if meta.get("skill_in_loop") else "") + ")"
    dirs[bench] += 1
    for dp, dns, fns in os.walk(TDIR[t]):
        dns[:] = [d for d in dns if d not in ("results", "__pycache__")]
        for f in fns:
            rel = os.path.relpath(os.path.join(dp, f), TDIR[t]).replace(os.sep, "/")
            role = module if f == module else f"{mode} {rel}" if rel in SHARED else None
            if role:
                seen[bench][role].setdefault(sha(os.path.join(dp, f)), f"{t}/{rel}")
    for rel, h in sorted(img.items()):   # copies the image build puts in place
        f = os.path.basename(rel)
        role = module if f == module else f"{mode} {rel}" if rel in SHARED else None
        if role:
            seen[bench][role].setdefault(h, f"{t}/{rel} (files image)")
# 5. the sidecar service and the live video: one source each; a base image's copy is the same bytes
n_one = 0
for one in ("sidecar/rcb_service.py", "live_video.py"):
    srcp = Path(src, one)
    if not srcp.is_file():
        bad.append(f"embodied_first_exam/standard/{one}: missing (the one source)")
        continue
    for p in sorted(Path(ROOTD, "embodied_first_exam/benchmarks").glob(f"**/{srcp.name}")):
        bad.append(f"{os.path.relpath(p, ROOTD)}: a copy of embodied_first_exam/standard/{one} (take it from standard-files)")
    for p in sorted(Path(images).glob(f"*/tools/**/{srcp.name}")):
        n_one += 1
        if sha(p) != sha(srcp):
            bad.append(f"{os.path.relpath(p, ROOTD)}: not byte-identical to embodied_first_exam/standard/{one}")
bad += [f"{b}: {len(v)} versions of {role}: " + ", ".join(f"{h} ({p})" for h, p in sorted(v.items()))
        for b, roles in sorted(seen.items()) for role, v in sorted(roles.items()) if len(v) > 1]
if bad:
    print("FAIL shared sources (byte-identical copies; the shared / operations layers as in embodied_first_exam/standard/, the realtime layer as in embodied_first_exam/standard/realtime/):")
    for b in bad[:60]:
        print("  -", b)
    if len(bad) > 60:
        print(f"  ... {len(bad) - 60} more")
    sys.exit(1)
print("ok shared sources: " + ("; ".join(f"{b} {dirs[b]} task dirs, {len(seen[b])} shared files" for b in sorted(seen)) or "no BEHAVIOR / RoboLab / RoboWits / ManiGuard / MolmoSpaces / MyoSuite / DexJoCo / DexHand / RoboARC / BiGym 2.0 / YAMLab tasks")
      + f"; the shared / operations layers in {n_layer} task dirs; the realtime layer in {n_rt}"
      + f"; rcb_service.py and live_video.py one source each ({n_one} base-image copy(ies) identical)")
PY
