#!/usr/bin/env bash
# RoboPaint only (tasks/robopaint/robopaint-*): the agent's container may hold nothing derived from the target except target.png
# (lead, 2026-09-28), and the task texts describe the target as the picture only.
#  1. environment/ (the agent image's build context) holds only whitelisted files; sidecar dirs (sim/, scorer/) are mounted into
#     their own services by docker-compose.yaml and never COPYed by the Dockerfile;
#  2. every Dockerfile COPY/ADD source is whitelisted (no wildcards, no sidecar paths); a COPY --from names the pinned
#     files-only image (images/robopaint-files/FILES.json) and one of its whitelisted agent-side files, or the pinned
#     pictures image (images/robopaint-pictures-files/FILES.json) and this task's own /<task>/target.png to /app/target.png;
#  3. environment/instance.json (the agent's copy) has only scene / rule keys: no truth, no target geometry, masks or counts;
#  4. the agent-visible tooling (environment/rcb_brush.py, and its source in embodied_first_exam/benchmarks/robopaint/ when the
#     Dockerfile takes it from the files-only image: that source must hash to FILES.json) carries no grader code (target
#     parsing, scoring);
#  5. instruction.md, README.md, the task.toml description and the standard service's spec texts use none of the words that
#     describe the target as anything but a picture (vector, SVG, centre line, skeleton, outline, median, stroke order, ...).
# Usage: check_leak.sh tasks/robopaint/<task-dir>   (moved from ci_checks/check-robopaint-leak.sh, board 0124; run by invariant-leak.sh)
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"
case "$n" in robopaint-*) ;; *) exit 0 ;; esac
root="$(cd "$(dirname "$0")/../../.." && pwd)"
python3 - "$t" "$root" <<'PY'
import hashlib, json, os, re, sys
t, root = sys.argv[1:3]; name = os.path.basename(t); env = os.path.join(t, "environment"); bad = []
FILES = json.load(open(os.path.join(root, "images", "robopaint-files", "FILES.json")))   # the files-only image (scripts/files_image.py)
STD = json.load(open(os.path.join(root, "images", "standard-files", "FILES.json")))       # the standard client (rcb_client.py, rcb1.py)
IMAGES = {"--from=" + d["image"]: d for d in (FILES, STD)}
PICS = json.load(open(os.path.join(root, "images", "robopaint-pictures-files", "FILES.json")))   # the exemplar pictures
stem = re.sub(r"-(privileged|standard)$", "", name.removeprefix("robopaint-"))
ALLOWED = {"Dockerfile", "docker-compose.yaml", "instance.json", "target.png", "rcb_brush.py", "rcb_client.py", "rcb1.py",
           "client-requirements.txt", "NOTICE-exemplar.md", "ARPHICPL.TXT"}
SIDECARS = {"sim", "scorer"}
MONITOR = "rcb_monitor"   # the resource monitor sidecar's limits, mounted only into it (check-monitor.py)
for f in sorted(os.listdir(env)):
    p = os.path.join(env, f)
    if os.path.isdir(p):
        if f not in SIDECARS and f != MONITOR:
            bad.append(f"environment/{f}/: unexpected directory")
    elif f not in ALLOWED:
        bad.append(f"environment/{f}: not an allowed agent-side file")
# 2. the Dockerfile copies whitelisted files only
df = open(os.path.join(env, "Dockerfile")).read()
tooling = {}   # agent-side tooling file -> where its bytes are (the task dir, or the files-only image's source)
for m in re.finditer(r"^\s*(COPY|ADD)\s+(.+)$", df, re.M):
    parts = [x for x in m.group(2).split() if not x.startswith("--")]
    frm = [x for x in m.group(2).split() if x.startswith("--from")]
    if frm and frm[0] == "--from=" + PICS["image"]:   # the pictures image: this task's own target.png, nothing else
        if m.group(1) != "COPY" or len(frm) != 1 or parts != [f"/{stem}/target.png", "/app/target.png"] \
                or f"{stem}/target.png" not in PICS["files"]:
            bad.append(f"Dockerfile: COPY --from of {' '.join(parts)}: only /{stem}/target.png of the pinned {PICS['image']}"
                       " to /app/target.png")
        continue
    if frm:   # only a pinned files-only image (robopaint-files, or standard-files' client), only whitelisted agent-side files of it
        img = IMAGES.get(frm[0]) if len(frm) == 1 else None
        srcs = [x.lstrip("/") for x in parts[:-1]]
        if (m.group(1) != "COPY" or img is None or not srcs
                or any(f not in img["files"] or "/" in f or f not in ALLOWED for f in srcs)):
            bad.append(f"Dockerfile: COPY --from of {' '.join(parts)}: only an allowed agent-side file of the pinned {FILES['image']}"
                       f" (or of {STD['image']})")
        else:
            for f in srcs:
                src = os.path.join(root, img["source"], f)
                # the source is what the pinned image carries (the hook stands alone: no generator check needed)
                if not os.path.isfile(src) or hashlib.sha256(open(src, "rb").read()).hexdigest() != img["files"][f]:
                    bad.append(f"{os.path.relpath(src, root)}: not the file its images/*-files/FILES.json pins (sha256)")
                tooling[f] = src
        continue
    for src in parts[:-1]:
        if src not in ALLOWED or any(c in src for c in "*?[") or "/" in src:
            bad.append(f"Dockerfile: {m.group(1)} {src} is not an allowed agent-side file")
# 1b. sidecar dirs are mounted by compose (and only there)
dc = open(os.path.join(env, "docker-compose.yaml")).read()
for d in SIDECARS:
    if os.path.isdir(os.path.join(env, d)) and f"./{d}:/srv" not in dc:
        bad.append(f"environment/{d}/ exists but docker-compose.yaml does not mount it into a sidecar")
# 3. the agent's copy of the instance
TOP_OK = {"task", "family", "medium", "target", "palette", "canvas", "sheets", "wells", "brush", "robot_qpos", "robot_base", "control_hz",
          "sim_hz", "max_steps", "instance_sha", "frida_learned", "frida_adapted", "versions", "scorer_urls"}
TARGET_OK = {"kind", "image", "tol_mm", "success", "success_precision", "success_recall", "success_color_recall"}
SUCCESS_OK = {"iou", "boundary_f", "min_stroke_coverage", "max_stray_frac", "register_mm", "max_strokes", "de_mean", "de_p90", "ssim_L",
              "paint_iou", "blur_mm", "tol_mm", "de_mean_coarse", "ssim_L_fine", "edge_corr", "region_cov_min", "region_cov_mean",
              "coarse_mm", "fine_mm", "region_de",                          # the painting rule's optional terms (P/1)
              "score_inset_mm",                                             # the scored window's inset from the sheet edges (O/4)
              "max_path_mm", "min_mark_width_mm", "max_scribble", "max_scribble_share", "scribble_min_mm"}   # the process rules
ip = os.path.join(env, "instance.json")
if os.path.exists(ip):
    inst = json.load(open(ip))
    for k in inst:
        if k not in TOP_OK:
            bad.append(f"environment/instance.json: key {k!r} is not scene / rule data")
    tg = inst.get("target", {})
    for k in tg:
        if k not in TARGET_OK:
            bad.append(f"environment/instance.json: target.{k} is not allowed in the agent's copy")
    for k in (tg.get("success") or {}):
        if k not in SUCCESS_OK:
            bad.append(f"environment/instance.json: target.success.{k} is not a rule threshold")
    txt = json.dumps(inst).lower()
    for w in ("svg", "<path", "medians", "outline", "strokes\": [", "points_mm", "center_k", "truth"):
        if w in txt:
            bad.append(f"environment/instance.json contains {w!r}")
elif not name.endswith("-standard"):
    bad.append("environment/instance.json missing (privileged twin)")
# 4. agent-visible tooling: simulation only
for f, p in [(f, p) for f in ("rcb_brush.py",) for p in (os.path.join(env, f), tooling.get(f)) if p]:
    if os.path.exists(p):   # the task dir's copy and the files-only image's source, both (either may reach the image)
        s = open(p).read()
        for w in (r"def score_canvas", r"def score_ink", r"def score_paint", r"class Target\b(?!Picture)", r"class GlyphTarget",
                  r"class LetterTarget", r"class PaintTarget", r"svgpathtools", r"graphics\.txt", r"parse_path"):
            if re.search(w, s):
                bad.append(f"{os.path.relpath(p, t if p.startswith(t) else root)}: grader code ({w!r}) in the agent's tooling")
# 5. wording
WORDS = [r"\bsvg\b", r"vector", r"cent(re|er)[ -]?lines?", r"skeleton", r"\boutlines?\b", r"\bmedians?\b", r"stroke order", r"stroke list",
         r"sub-?paths?", r"decompos", r"vectori[sz]", r"target_masks", r"\bmasks?\b", r"per-element", r"element coverage",
         r"(target|drawing|exemplar)(\'s)? geometry", r"\bextract", r"\btrac(e|es|ed|ing)\b"]
texts = {"instruction.md": open(os.path.join(t, "instruction.md")).read(), "README.md": open(os.path.join(t, "README.md")).read()}
tm = re.search(r'^description\s*=\s*"(.*)"\s*$', open(os.path.join(t, "task.toml")).read(), re.M)
texts["task.toml description"] = tm.group(1) if tm else ""
sp = os.path.join(env, "sim", "server.py")
if os.path.exists(sp):                       # the limited service's /spec texts: every string literal of server.py
    import ast
    lits = [n.value for n in ast.walk(ast.parse(open(sp).read())) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    texts["environment/sim/server.py (string literals)"] = "\n".join(lits)
for where, s in texts.items():
    for w in WORDS:
        m = re.search(w, s, re.I)
        if m:
            line = s[:m.start()].count("\n") + 1
            bad.append(f"{where}:{line}: wording {m.group(0)!r}")
if bad:
    print(f"FAIL {name}:"); [print("  -", b) for b in bad]; sys.exit(1)
print(f"ok {name}: agent side = target.png + scene data only; neutral texts")
PY
