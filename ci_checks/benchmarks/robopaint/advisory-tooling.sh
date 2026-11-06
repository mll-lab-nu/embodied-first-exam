#!/usr/bin/env bash
# RoboPaint tooling convention: every family of the suite runs one version of the shared tooling (rcb_brush.py,
# rcb_brush_score.py, rcb_brush_strict.py, the graders, the scoring service and the standard sim service). Its one source is
# embodied_first_exam/benchmarks/robopaint/, served by the pinned files-only image images/robopaint-files/ (the exemplar
# pictures by images/robopaint-pictures-files/); `python3 scripts/files_image.py check robopaint-files` ties the sources to
# FILES.json. This hook checks the task side:
#   - every RoboPaint task is found (none in the folder is a failure, not a pass);
#   - every Dockerfile of every task (environment/, environment/sim/, environment/scorer/, tests/) that copies from a
#     RoboPaint files image names exactly the image FILES.json pins (tag and digest), and only files FILES.json lists;
#   - the images that run the tooling copy it from robopaint-files: every task's verifier (tests/Dockerfile), a privileged
#     task's agent image and scorer sidecar, a standard task's sim sidecar (no task runs a tooling copy of its own);
#   - a task dir holds no copy of a shared file (rcb_brush*.py, rcb_scorer.py, rcb_client.py) unless it is byte-identical to
#     its source.
# ADVISORY hook of RoboPaint: ci_checks/run_all.sh runs every ci_checks/benchmarks/*/advisory-* hook with the task
# directories in scope; this one checks the folder the first RoboPaint task among them is in (none among them: the
# repository's tasks/robopaint/).
# Usage: advisory-tooling.sh [task dirs]   (default: the repository's tasks/robopaint/)
set -uo pipefail
root="$(cd "$(dirname "$0")/../../.." && pwd)"
tdir="$root/tasks/robopaint"
for a in "$@"; do case "$(basename "${a%/}")" in robopaint-*) tdir="$(cd "$(dirname "${a%/}")" && pwd)"; break ;; esac; done
python3 - "$tdir" "$root" <<'PY'
import hashlib, json, os, re, sys
tasks, root = sys.argv[1:3]
IMAGES = ("robopaint-files", "robopaint-pictures-files")
spec = {n: json.load(open(os.path.join(root, "images", n, "FILES.json"))) for n in IMAGES}
src = os.path.join(root, spec["robopaint-files"]["source"])
SHARED = {f: hashlib.sha256(open(os.path.join(src, f), "rb").read()).hexdigest() for f in spec["robopaint-files"]["files"]
          if "/" not in f}                                   # rcb_brush.py, rcb_brush_score.py, rcb_brush_strict.py
NAMES = set(SHARED) | {"rcb_scorer.py", "rcb_client.py"}
bad, n_tasks, n_lines = [], 0, 0
for t in sorted(os.listdir(tasks)):
    tp = os.path.join(tasks, t)
    if not t.startswith("robopaint-") or not os.path.isfile(os.path.join(tp, "task.toml")):
        continue
    n_tasks += 1
    mode = t.rsplit("-", 1)[1]
    need = {"tests/Dockerfile"} | ({"environment/sim/Dockerfile"} if mode == "standard" else
                                   {"environment/Dockerfile", "environment/scorer/Dockerfile"})
    for dp, dns, fns in os.walk(tp):
        dns[:] = [d for d in dns if d not in ("results", "__pycache__")]
        for f in fns:
            rel = os.path.relpath(os.path.join(dp, f), tp)
            if f in NAMES:                                   # a copy left in the task dir
                h = hashlib.sha256(open(os.path.join(dp, f), "rb").read()).hexdigest()
                if SHARED.get(f) != h:
                    bad.append(f"{t}/{rel}: a copy of a shared file in the task dir"
                               + (" that differs from its source" if f in SHARED else " (it comes from robopaint-files)"))
            if f != "Dockerfile":
                continue
            text = re.sub(r"\\\n", " ", open(os.path.join(dp, f), errors="replace").read())
            for line in text.splitlines():
                w = line.split()
                if len(w) < 2 or w[0].upper() != "COPY":
                    continue
                ref = next((x[len("--from="):] for x in w[1:] if x.startswith("--from=")), "")
                if not any(n in ref for n in IMAGES):
                    continue
                n_lines += 1
                name = next((n for n in IMAGES if re.search(r"/efe(-private)?:" + re.escape(n) + r"-\d", ref)), None)
                if name is None or ref != spec[name]["image"]:
                    bad.append(f"{t}/{rel}: COPY --from={ref}: not the pinned image of images/{name or '?'}/FILES.json "
                               f"({spec[name]['image'] if name else ', '.join(spec[n]['image'] for n in IMAGES)})")
                    continue
                if name == "robopaint-files":
                    need.discard(rel)
                files = spec[name]["files"]
                for a in [x for x in w[1:] if not x.startswith("--")][:-1]:
                    p = a.strip("/")
                    if p and p not in files and not any(k.startswith(p + "/") for k in files):
                        bad.append(f"{t}/{rel}: copies /{p}, which images/{name}/FILES.json does not list")
    bad += [f"{t}/{r}: takes nothing from robopaint-files (its own copy of the tooling?)" for r in sorted(need)]
if n_tasks == 0 or n_lines == 0:
    bad.append(f"{tasks}: {n_tasks} RoboPaint tasks and {n_lines} COPY lines from a RoboPaint files image found: nothing checked")
if bad:
    print("FAIL robopaint tooling (one pinned files-image version in every task):")
    for b in bad:
        print("  -", b)
    sys.exit(1)
print(f"ok robopaint tooling: {n_tasks} tasks, {n_lines} COPY lines, all from {spec['robopaint-files']['image'].split('@')[0]} "
      f"and {spec['robopaint-pictures-files']['image'].split('@')[0]} as pinned in FILES.json")
PY
