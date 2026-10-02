#!/usr/bin/env bash
# RoboPaint only (tasks/robopaint-*): the agent's container may hold nothing derived from the target except target.png
# (lead, 2026-09-28), and the task texts describe the target as the picture only.
#  1. environment/ (the agent image's build context) holds only whitelisted files; sidecar dirs (sim/, scorer/) are mounted into
#     their own services by docker-compose.yaml and never COPYed by the Dockerfile;
#  2. every Dockerfile COPY/ADD source is whitelisted (no wildcards, no sidecar paths);
#  3. environment/instance.json (the agent's copy) has only scene / rule keys: no truth, no target geometry, masks or counts;
#  4. the agent-visible tooling (environment/rcb_*.py) carries no grader code (target parsing, scoring);
#  5. instruction.md, README.md, the task.toml description and the standard service's spec texts use none of the words that
#     describe the target as anything but a picture (vector, SVG, centre line, skeleton, outline, median, stroke order, ...).
# Usage: check-robopaint-leak.sh tasks/<task-dir>
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"
case "$n" in robopaint-*) ;; *) exit 0 ;; esac
python3 - "$t" <<'PY'
import json, os, re, sys
t = sys.argv[1]; name = os.path.basename(t); env = os.path.join(t, "environment"); bad = []
ALLOWED = {"Dockerfile", "docker-compose.yaml", "instance.json", "target.png", "rcb_paint.py", "rcb_brush.py", "rcb_client.py", "rcb1.py",
           "client-requirements.txt", "NOTICE-exemplar.md", "ARPHICPL.TXT"}
SIDECARS = {"sim", "scorer"}
for f in sorted(os.listdir(env)):
    p = os.path.join(env, f)
    if os.path.isdir(p):
        if f not in SIDECARS:
            bad.append(f"environment/{f}/: unexpected directory")
    elif f not in ALLOWED:
        bad.append(f"environment/{f}: not an allowed agent-side file")
# 2. the Dockerfile copies whitelisted files only
df = open(os.path.join(env, "Dockerfile")).read()
for m in re.finditer(r"^\s*(COPY|ADD)\s+(.+)$", df, re.M):
    parts = [x for x in m.group(2).split() if not x.startswith("--")]
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
              "score_inset_mm"}                                             # the scored window's inset from the sheet edges (O/4)
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
elif not name.endswith(("-standard", "-limited")):
    bad.append("environment/instance.json missing (privileged twin)")
# 4. agent-visible tooling: simulation only
for f in ("rcb_paint.py", "rcb_brush.py"):
    p = os.path.join(env, f)
    if os.path.exists(p):
        s = open(p).read()
        for w in (r"def score_canvas", r"def score_ink", r"def score_paint", r"class Target\b(?!Picture)", r"class GlyphTarget",
                  r"class LetterTarget", r"class PaintTarget", r"svgpathtools", r"graphics\.txt", r"parse_path"):
            if re.search(w, s):
                bad.append(f"environment/{f}: grader code ({w!r}) in the agent's tooling")
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
