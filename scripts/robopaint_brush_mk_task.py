#!/usr/bin/env python3
"""Generate a RoboPaint brush task pair (privileged task + its standard twin): families kaishu (楷书 臨帖), xingshu (行书 臨帖), lettering
(broad nib, pointed pen), acrylic / oil (libmypaint paintings: a hidden stroke program / a reference picture).

    python scripts/robopaint_brush_mk_task.py --family kaishu --target yong --graphics /path/to/makemeahanzi/graphics.txt
    python scripts/robopaint_brush_mk_task.py --family kaishu --target tiandaochouqin --graphics ...        # a work (targets.json)
    python scripts/robopaint_brush_mk_task.py --family xingshu --target <slug> --graphics <slug>.graphics.txt --max-strokes N --plans plans.json
        # 行书 臨帖 (連筆) from a public-domain rubbing: --graphics = the task's own exemplar file (graphics.txt format, one line per
        # character, "strokes" = the regions of its ink); --max-strokes = the connected contacts (the cap), --plans = one plan per contact
    python scripts/robopaint_brush_mk_task.py --family lettering --word minim --hand italic --template minim
    python scripts/robopaint_brush_mk_task.py --family acrylic --painting <name> --template redfuji   # a program entry (programs_json/)
    python scripts/robopaint_brush_mk_task.py --family oil --painting <name> --reference-png <picture.png> --difficulty extreme
    python scripts/robopaint_brush_mk_task.py --refresh [tasks/robopaint-<family>-<target>-i00 ...]   # regenerate committed pairs

--template names the family's template pair under --template-root (default tasks/; the defaults: kaishu / xingshu yong, lettering
minim, acrylic redfuji, oil cypresses); any committed pair of the family serves (the code is identical within a family,
ci_checks/check-robopaint-tooling.sh). A painting's program is read from the template's solution/programs_json/, where a pair's
own entry is its current program: a painting pair is remade with itself as the template.

-> tasks/robopaint-<family>-<target>-i00-privileged/ and ...-i00-standard/ (mode standard, eai-standard/2.2), family
robopaint_<family>_<target>; every task ends with scripts/task_conventions.py's normalize (the repository's conventions).

--refresh regenerates committed pairs from their own frozen files (no docker, no GPU): the template pair's code, the
eai-standard/2.2 layer, the base image of images/robopaint/VERSION and the rendered texts around the frozen instance, the
reference plan and its records. Rerunning it on the committed tasks leaves `git diff tasks/` empty.

Files: the code of the template pair (tasks/robopaint-<family>-<template>-i00*, or --template-root) is copied (tooling, graders,
sidecars and solution code stay byte-identical within a family); the standard twin's client and service layer come from
scripts/eai_standard/ (byte-identical everywhere); the texts are rendered from scripts/robopaint_templates/<family>/
({u,l}_{instruction.md,README.md,task.toml} with {{PLACEHOLDERS}}, values from the frozen files: derive_values); the frozen files
are made inside the base image (docker, GPU):
the graders' instance + target.png (rcb_brush_score.py make-instance), the agent's copy (make-agent-instance: scene + rule only),
the reference oracle (kaishu: solution/opt_calli.py per-stroke optimisation + solution/ref_calli.py on the robot; lettering:
solution/ref_nib.py; paintings: solution/ref_oil.py paints the hidden program, the painted sheet becomes the exemplar), and a
self-test of the scoring path (the scoring service on the graders' copy; the oracle through it on the agent's copy; its metrics
must equal the graders' own score of the same trajectory). What each container gets follows the leak rule (the agent: scene,
picture, tooling; the scorer / verifier / sim sidecar: the graders' copy). Then: bash ci_checks/run_all.sh <dirs>, harbor oracle /
nop runs in both modes, `harbor add <dirs>` from tasks/.
"""
from __future__ import annotations
import argparse, json, math, os, re, shlex, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.dont_write_bytecode = True                 # the solution modules imported from task dirs (letters.py, programs.py) leave no caches
ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DEFAULT = ROOT / "scripts" / "robopaint_templates"
TPL = {"dir": TEMPLATES_DEFAULT}                              # set from --templates-dir
IMAGE = "ghcr.io/embodied-agent-interface-v2-internal/eai-robopaint:" + (ROOT / "images" / "robopaint" / "VERSION").read_text().strip()
SHEET_MM = 227.1845
IDENTICAL = ("instance.json", "rcb_brush.py", "rcb_brush_score.py", "rcb_scorer.py", "rcb1.py", "server.py", "rcb_client.py", "ARPHICPL.TXT")
FAMILIES = {"kaishu": {"medium": "calligraphy", "template": "yong"}, "lettering": {"medium": "broad_nib", "template": "minim"},
            "acrylic": {"medium": "mypaint", "template": "redfuji"}, "oil": {"medium": "mypaint", "template": "cypresses"},
            "xingshu": {"medium": "calligraphy", "template": "yong"}}
LAYER = {"environment/rcb_client.py": "rcb_client.py", "environment/rcb1.py": "rcb1.py", "environment/sim/rcb_limited.py": "rcb_limited.py",
         "environment/sim/rcb1.py": "rcb1.py", "environment/sim/run.sh": "run.sh"}   # standard twin <- scripts/eai_standard/
_CLIENT = dict(l.split("=", 1) for l in (ROOT / "scripts" / "eai_standard" / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
CLIENT_IMAGE = _CLIENT["CLIENT_IMAGE"].strip()                 # the one client base of every standard task (PROTOCOL §2.4)
CLIENT_PINS = [x for x in (l.split("#", 1)[0].strip() for l in (ROOT / "scripts" / "eai_standard" / _CLIENT["CLIENT_REQUIREMENTS"].strip())
                           .read_text().splitlines()) if x]
SUCCESS_KAISHU = {"iou": 0.80, "boundary_f": 0.75, "min_stroke_coverage": 0.80, "max_stray_frac": 0.04, "register_mm": 5.0}   # §17 + registration (snapshot 21)
SUCCESS_LETTERING = {"iou": 0.85, "boundary_f": 0.80, "min_stroke_coverage": 0.75, "max_stray_frac": 0.04, "register_mm": 5.0}   # §18 + L/6
SUCCESS_PAINT = {"de_mean": 3.5, "de_p90": 12.0, "ssim_L": 0.90, "paint_iou": 0.88, "blur_mm": 1.0}              # DESIGN §19

SELFTEST = r"""
RCB_INSTANCE=/work/full/instance.json RCB_TOOL_MODULE=rcb_brush RCB_SCORER_PORT=8001 RCB_RENDER=0 PYTHONPATH=/work python -u rcb_scorer.py > scorer.log 2>&1 &
SP=$!
RCB_SCORER_URL=http://localhost:8001 RCB_SOLUTION_DIR=/work RCB_ORACLE_METRICS_OUT=/work/scorer_metrics.json \
  python rcb_brush.py run-oracle --instance agent/instance.json --code oracle_paint.py --out agent_traj.npz > agent_oracle.json
kill $SP || true
python rcb_brush.py replay --instance full/instance.json --traj agent_traj.npz > full_replay.json
python - <<'PY'
import json, numpy as np, rcb_brush as R
sm = json.load(open("scorer_metrics.json"))
full = [json.loads(l) for l in open("full_replay.json") if l.startswith("{")][-1]["replays"][0]
fm = R.agent_metrics(full)
diff = {k: (sm.get(k), fm.get(k)) for k in set(sm) | set(fm) if sm.get(k) != fm.get(k) and k != "success"}
ok = not diff and bool(sm.get("success")) == bool(full.get("success"))
a = np.load("agent_traj.npz")["actions"]; o = np.load("oracle_qpos.npy")
json.dump({"scorer_equals_graders": ok, "differences": diff, "agent_actions_equal_oracle": bool(np.array_equal(a, o)), "scorer_metrics": sm},
          open("selftest.json", "w"), indent=1)
print(json.dumps({"scorer_equals_graders": ok, "n_diff": len(diff)}))
PY
"""


def render(template: str, values: dict) -> str:
    s = template
    for k, v in values.items():
        s = s.replace("{{" + k + "}}", str(v))
    left = re.findall(r"\{\{[A-Z_]+\}\}", s)
    if left:
        raise SystemExit(f"unfilled placeholders {sorted(set(left))}")
    return s


def pad(s: str, width: int) -> str:
    return " " * max(1, width - len(s))


# --------------------------------------------------------------------------- family handlers: spec, texts, docker steps
def kaishu_target(a) -> dict:
    cat = json.load(open(TPL["dir"] / "kaishu" / "targets.json"))
    works = {s: c for s, c in cat["works"]}
    singles = {s: (c, st) for s, c, st in cat["singles"]}
    if a.target in singles:
        ch, structure = singles[a.target]; chars = ch
    elif a.target in works:
        chars = works[a.target]; structure = "work"
    else:
        raise SystemExit(f"unknown kaishu target {a.target!r} (scripts/robopaint_templates/kaishu/targets.json)")
    n = 0
    for line in open(a.graphics, encoding="utf-8"):
        d = json.loads(line)
        if d["character"] in chars:
            n += len(d["strokes"]) * chars.count(d["character"])
    if structure == "work":
        # two columns read right to left, top to bottom; one 96 mm box per character, 12 mm gaps, centred on the sheet
        S, gap = 96.0, 12.0
        m = (SHEET_MM - 2 * S - gap) / 2
        cols = [m + S + gap, m]                                      # right column first
        boxes = [[round(cols[i // 2], 4), round(m + (i % 2) * (S + gap), 4), S] for i in range(len(chars))]
        target = {"characters": chars, "boxes": boxes}
        difficulty = "extreme"
        task_md = f"the exemplar work **{chars}** ({len(chars)} characters in regular script, 楷书, in two columns read right to left)"
        task_plain = f"the exemplar work {chars} ({len(chars)} characters in regular script, two columns read right to left)"
    else:
        X0 = (SHEET_MM - a.box_mm) / 2
        target = {"character": chars, "box_mm": [X0, X0, a.box_mm]}
        difficulty = "medium" if n <= 5 else "hard"
        task_md = f"the exemplar character **{chars}** in regular script (楷书)"
        task_plain = f"the exemplar character {chars} in regular script"
    spec = {"task": None, "medium": "calligraphy",
            "target": {**target, "graphics": "/mmah/graphics.txt", "stroke_slack": 0, "success": SUCCESS_KAISHU}}
    return {"slug": a.target, "spec": spec, "n": n, "mounts": ["-v", f"{Path(a.graphics).resolve().parent}:/mmah:ro"],
            "values": {"TITLE": chars, "TASK_MD": task_md, "TASK_PLAIN": task_plain, "N": n, "DIFFICULTY": difficulty,
                       "DPAD": pad(f'"{difficulty}"', 19), "NPAD": pad(str(n), 19), "STRUCTURE": structure, "NCHARS": len(chars)},
            "sol_files": ("opt_calli.py", "ref_calli.py", "plan_oracle.py", "oracle_paint.py"),
            "steps": ("python rcb_brush_score.py make-instance --spec spec.json --out full/instance.json"
                      " && python rcb_brush_score.py make-agent-instance --instance full/instance.json --out-dir agent"
                      + ("" if a.plans else f" && RCB_TOOLS=/work python opt_calli.py --instance full/instance.json --graphics /mmah/graphics.txt --out plans.json --nfev {a.nfev}") +
                      " && RCB_SOLUTION_DIR=/work python rcb_brush.py run-oracle --instance full/instance.json --code plan_oracle.py --out plan_traj.npz > plan.json"
                      " && python -c \"import numpy as np; np.save('oracle_qpos.npy', np.load('plan_traj.npz')['actions'].astype(np.float32))\""),
            "keep": {"plans.json": "solution/plans.json"}}


def xingshu_target(a) -> dict:
    """行书 臨帖 (the kaishu machinery: medium calligraphy, same scorer and solution code). The exemplar is a public-domain rubbing /
    scan: --graphics is the task's own file in Make Me a Hanzi's graphics.txt format (one JSON line per character; its "strokes"
    are the regions its ink was split into), mounted as /mmah/graphics.txt; success.max_strokes = --max-strokes (default: the number
    of regions, NREG). Works: the kaishu layout (two columns read right to left, 96 mm boxes, 12 mm gaps)."""
    cat = json.load(open(TPL["dir"] / "xingshu" / "targets.json"))
    works = {s: c for s, c in cat["works"]}
    singles = {s: (c, st) for s, c, st in cat["singles"]}
    if a.target in singles:
        ch, structure = singles[a.target]; chars = ch
    elif a.target in works:
        chars = works[a.target]; structure = "work"
    else:
        raise SystemExit(f"unknown xingshu target {a.target!r} ({TPL['dir'] / 'xingshu' / 'targets.json'})")
    sources = (cat.get("sources") or {}).get(a.target) or (cat.get("sources") or {}).get("*")   # the README's SOURCES (licence record)
    if not sources:
        raise SystemExit(f"{TPL['dir'] / 'xingshu' / 'targets.json'}: no sources entry for {a.target!r} (or '*')")
    if not a.graphics or not Path(a.graphics).is_file():
        raise SystemExit("xingshu: --graphics <the task's exemplar file, graphics.txt format> needed")
    if len(set(chars)) != len(chars):
        raise SystemExit(f"xingshu work {chars!r} repeats a character: the exemplar file holds one line per character")
    recs = {}
    for line in open(a.graphics, encoding="utf-8"):
        if line.strip():
            d = json.loads(line)
            if d["character"] in recs:
                raise SystemExit(f"{a.graphics}: two lines for {d['character']!r}")
            recs[d["character"]] = d
    missing = [c for c in chars if c not in recs]
    if missing:
        raise SystemExit(f"{missing!r} not in {a.graphics}")
    nreg = sum(len(recs[c]["strokes"]) for c in chars)             # the regions of the exemplar's ink (min_stroke_coverage units)
    n = int(a.max_strokes) if a.max_strokes else nreg              # the contact limit (success.max_strokes)
    if n < 1:
        raise SystemExit("--max-strokes must be >= 1")
    if structure == "work":
        S, gap = 96.0, 12.0                                          # the kaishu layout
        m = (SHEET_MM - 2 * S - gap) / 2
        cols = [m + S + gap, m]                                      # right column first
        boxes = [[round(cols[i // 2], 4), round(m + (i % 2) * (S + gap), 4), S] for i in range(len(chars))]
        target = {"characters": chars, "boxes": boxes}
        difficulty = "extreme"
        task_md = f"the exemplar work **{chars}** ({len(chars)} characters in running script, 行书, in two columns read right to left)"
        task_plain = f"the exemplar work {chars} ({len(chars)} characters in running script, two columns read right to left)"
    else:
        X0 = (SHEET_MM - a.box_mm) / 2
        target = {"character": chars, "box_mm": [X0, X0, a.box_mm]}
        difficulty = "hard"
        task_md = f"the exemplar character **{chars}** in running script (行书)"
        task_plain = f"the exemplar character {chars} in running script"
    spec = {"task": None, "medium": "calligraphy",
            "target": {**target, "graphics": "/mmah/graphics.txt", "stroke_slack": 0, "success": {**SUCCESS_KAISHU, "max_strokes": n}}}
    return {"slug": a.target, "spec": spec, "n": nreg, "max_strokes": n, "licence": cat.get("licence"), "mounts": ["-v", f"{Path(a.graphics).resolve()}:/mmah/graphics.txt:ro"],
            "values": {"TITLE": chars, "TASK_MD": task_md, "TASK_PLAIN": task_plain, "N": n, "NREG": nreg, "SOURCES": sources, "DIFFICULTY": difficulty,
                       "DPAD": pad(f'"{difficulty}"', 19), "NPAD": pad(str(n), 19), "STRUCTURE": structure, "NCHARS": len(chars)},
            "sol_files": ("opt_calli.py", "ref_calli.py", "plan_oracle.py", "oracle_paint.py"),
            "steps": ("python rcb_brush_score.py make-instance --spec spec.json --out full/instance.json"
                      " && python rcb_brush_score.py make-agent-instance --instance full/instance.json --out-dir agent"
                      + ("" if a.plans else f" && RCB_TOOLS=/work python opt_calli.py --instance full/instance.json --graphics /mmah/graphics.txt --out plans.json --nfev {a.nfev}") +
                      " && RCB_SOLUTION_DIR=/work python rcb_brush.py run-oracle --instance full/instance.json --code plan_oracle.py --out plan_traj.npz > plan.json"
                      " && python -c \"import numpy as np; np.save('oracle_qpos.npy', np.load('plan_traj.npz')['actions'].astype(np.float32))\""),
            "keep": {"plans.json": "solution/plans.json"}}


def lettering_target(a) -> dict:
    """Lettering (agent L, L/2): the word's authored letter skeletons (solution/letters.py of the template pair, CC0) placed by
    letters.layout(); broad-edge hands -> medium broad_nib, pointed hands (copperplate) -> medium pointed_pen (per-point widths);
    the pair is named by the word (robopaint-lettering-<word>-i00); the texts come from templates/lettering (broad) or
    templates/lettering_pointed; the oracle = solution/ref_lettering.py (both pens)."""
    sys.path.insert(0, str(a._src_u / "solution"))
    import letters as LT
    if a.hand not in LT.HANDS or not re.fullmatch(r"[a-z]+( [a-z]+)*", a.word or ""):
        raise SystemExit(f"--word (lowercase letters; words of a phrase separated by single spaces) and --hand in {sorted(LT.HANDS)} needed")
    pointed = LT.HANDS[a.hand].get("pen") == "pointed"
    strokes, lay, box = LT.layout(a.word, a.hand, SHEET_MM)
    n = len(strokes)
    spec = {"task": None, "medium": "pointed_pen" if pointed else "broad_nib",
            "target": {"word": a.word, "hand": a.hand, "box_mm": box, "strokes": strokes, "stroke_slack": 0,
                       "success": dict(LT.HANDS[a.hand].get("success", SUCCESS_LETTERING))}}
    return {"slug": a.word.replace(" ", ""), "spec": spec, "n": n, "mounts": [], "tdir": "lettering_pointed" if pointed else "lettering",
            "values": {"TITLE": a.word, "WORD": a.word, "HAND": a.hand, "N": n, "DIFFICULTY": a.difficulty or "medium", "NLETTERS": len(a.word.replace(" ", "")),
                       "IOU": f'{spec["target"]["success"]["iou"]:.2f}',
                       "DPAD": pad(f'"{a.difficulty or "medium"}"', 19), "NPAD": pad(str(n), 19)},
            "sol_files": ("ref_lettering.py", "plan_oracle.py", "oracle_paint.py", "letters.py"),
            "steps": ("python rcb_brush_score.py make-instance --spec spec.json --out full/instance.json"
                      " && python rcb_brush_score.py make-agent-instance --instance full/instance.json --out-dir agent"
                      " && RCB_SOLUTION_DIR=/work python rcb_brush.py run-oracle --instance full/instance.json --code plan_oracle.py --out plan_traj.npz > plan.json"
                      " && python -c \"import numpy as np; np.save('oracle_qpos.npy', np.load('plan_traj.npz')['actions'].astype(np.float32))\""),
            "keep": {}}


PAINT_STEPS = r"""
python - <<'PY'
import json, numpy as np
from PIL import Image
import rcb_brush as B
S = B.default_sheets()[0]
import os; os.makedirs("blank", exist_ok=True)
Image.fromarray(np.full((S["rows"], S["cols"], 3), np.round(np.asarray(B.PAPER_RGB) * 255).astype(np.uint8), np.uint8)).save("blank/target.png")
np.savez_compressed("blank/truth_alpha.npz", alpha=np.zeros((S["rows"], S["cols"]), np.uint8))
PY
python rcb_brush_score.py make-instance --spec spec.json --out blank/instance.json
RCB_SOLUTION_DIR=/work python rcb_brush.py run-oracle --instance blank/instance.json --code plan_oracle.py --out plan_traj.npz > plan.json
python rcb_brush.py replay --instance blank/instance.json --traj plan_traj.npz --canvas-out painted.png > /dev/null
mkdir -p full && cp painted.png full/target.png
python -c "import numpy as np; np.savez_compressed('full/truth_alpha.npz', alpha=np.load('painted_alpha.npz')['alpha']); np.save('oracle_qpos.npy', np.load('plan_traj.npz')['actions'].astype(np.float32))"

python - <<'PY'
import json, numpy as np
from PIL import Image
from scipy import ndimage
import rcb_brush as B, rcb_brush_score as S
spec = json.load(open("spec.json"))
img = np.asarray(Image.open("full/target.png").convert("RGB"), np.float64) / 255.0
px = B.PAPER_SIDE_M / 1024 * 1000.0
lab = ndimage.gaussian_filter(S.srgb_to_lab(img), (1.0 / px, 1.0 / px, 0))
pal = S.srgb_to_lab(np.asarray([B.hex_rgb(h) for _, h in spec["palette"]])[None])[0]
k = np.argmin(((lab[:, :, None, :] - pal[None, None]) ** 2).sum(-1), -1)
alpha = np.load("full/truth_alpha.npz")["alpha"]
reg = np.zeros(k.shape, np.uint16); r = 0; minpx = int(float(spec.get("region_min_mm2", 30.0)) / px ** 2)
for c in range(len(pal)):
    lb, n = ndimage.label(k == c, structure=np.ones((3, 3)))
    if n == 0:
        continue
    sizes = np.bincount(lb.ravel())
    for j in np.nonzero(sizes >= minpx)[0]:
        if j:
            r += 1; reg[lb == j] = r
np.savez_compressed("full/truth_alpha.npz", alpha=alpha, regions=reg)
print(json.dumps({"regions": r, "min_px": minpx}))
PY
python rcb_brush_score.py make-instance --spec spec.json --out full/instance.json
python rcb_brush_score.py make-agent-instance --instance full/instance.json --out-dir agent
"""


REG_STEPS = r"""
python - <<'PY'
import json, numpy as np
from PIL import Image
from scipy import ndimage
import rcb_brush as B, rcb_brush_score as S
spec = json.load(open("spec.json"))
img = np.asarray(Image.open("full/target.png").convert("RGB"), np.float64) / 255.0
px = B.PAPER_SIDE_M / 1024 * 1000.0
lab = ndimage.gaussian_filter(S.srgb_to_lab(img), (1.0 / px, 1.0 / px, 0))
pal = S.srgb_to_lab(np.asarray([B.hex_rgb(h) for _, h in spec["palette"]])[None])[0]
k = np.argmin(((lab[:, :, None, :] - pal[None, None]) ** 2).sum(-1), -1)
alpha = np.load("full/truth_alpha.npz")["alpha"]
reg = np.zeros(k.shape, np.uint16); r = 0; minpx = int(float(spec.get("region_min_mm2", 30.0)) / px ** 2)
for c in range(len(pal)):
    lb, n = ndimage.label(k == c, structure=np.ones((3, 3)))
    if n == 0:
        continue
    sizes = np.bincount(lb.ravel())
    for j in np.nonzero(sizes >= minpx)[0]:
        if j:
            r += 1; reg[lb == j] = r
np.savez_compressed("full/truth_alpha.npz", alpha=alpha, regions=reg)
print(json.dumps({"regions": r, "min_px": minpx}))
PY
"""

OIL_STEPS = r"""
mkdir -p full && cp reference.png full/target.png
python -c "import numpy as np; np.savez_compressed('full/truth_alpha.npz', alpha=np.full((1024, 1024), 255, np.uint8))"
""" + REG_STEPS + r"""
python rcb_brush_score.py make-instance --spec spec.json --out full/instance.json
RCB_SOLUTION_DIR=/work python rcb_brush.py run-oracle --instance full/instance.json --code plan_oracle.py --out plan_traj.npz > plan.json
python rcb_brush.py replay --instance full/instance.json --traj plan_traj.npz > base_replay.json
python - <<'PY'
import json, math
spec = json.load(open("spec.json"))
b = [json.loads(l) for l in open("base_replay.json") if l.startswith("{")][-1]["replays"][0]
cal = spec.get("calibration")
if cal is None:
    import sys; json.dump({"rule": spec["target"]["success"], "baseline": {k: b[k] for k in ("de_mean", "de_p90", "ssim_L", "edge_corr", "region_cov_min", "region_cov_mean", "de_mean_coarse", "ssim_L_fine", "paint_iou", "n_strokes") if k in b}}, open("calibration.json", "w"), indent=1); sys.exit(0)
up = lambda v, f, q: math.ceil(v * f / q) * q
dn = lambda v, d, q: math.floor((v - d) / q) * q
r = dict(spec["target"]["success"])
r["de_mean"] = round(up(b["de_mean"], cal["de_factor"], 0.1), 2)
r["de_p90"] = round(up(b["de_p90"], cal["de_factor"], 0.5), 2)
r["ssim_L"] = round(dn(b["ssim_L"], cal["ssim_margin"], 0.01), 2)
if "edge_corr" in cal:
    r["edge_corr"] = round(dn(b["edge_corr"], cal["edge_corr"], 0.01), 2)
if "region_cov_mean" in cal:
    r["region_cov_mean"] = round(dn(b["region_cov_mean"], cal["region_cov_mean"], 0.01), 2)
r["paint_iou"] = round(dn(b["paint_iou"], 0.03, 0.01), 2)
spec["target"]["success"] = r
spec["baseline"] = {k: b[k] for k in ("de_mean", "de_p90", "ssim_L", "edge_corr", "region_cov_min", "region_cov_mean", "de_mean_coarse", "ssim_L_fine", "paint_iou", "n_strokes") if k in b}
json.dump(spec, open("spec.json", "w"), indent=1)
json.dump({"rule": r, "baseline": spec["baseline"]}, open("calibration.json", "w"), indent=1)
print(json.dumps({"rule": r, "baseline": spec["baseline"]}))
PY
python rcb_brush_score.py make-instance --spec spec.json --out full/instance.json
python -c "import numpy as np; np.save('oracle_qpos.npy', np.load('plan_traj.npz')['actions'].astype(np.float32))"
python rcb_brush_score.py make-agent-instance --instance full/instance.json --out-dir agent
"""



def painting_target(a) -> dict:
    sys.path.insert(0, str(a._src_u / "solution"))
    from programs import PROGRAMS
    if a.painting not in PROGRAMS:
        raise SystemExit(f"unknown painting {a.painting!r}: {sorted(PROGRAMS)}")
    prog = PROGRAMS[a.painting]
    n = len(prog["strokes"]); budget = int(math.ceil(a.budget_factor * n))
    spec = {"task": None, "medium": "mypaint", "palette": prog["palette"], "brush": prog.get("brush", {}), "wells_layout": prog.get("wells_layout", {}),
            "region_min_mm2": prog.get("region_min_mm2", 30.0),
            "target": {"name": a.painting, "n_strokes": n, "stroke_budget_factor": prog.get("budget_factor", a.budget_factor),
                       "success": prog.get("success", SUCCESS_PAINT), "source": prog.get("source"), "license": prog.get("license", "CC0-1.0")}}
    budget = int(math.ceil(spec["target"]["stroke_budget_factor"] * n))
    if "reference" in prog:
        spec["target"]["reference"] = prog["reference"]
    if "calibration" in prog:
        spec["calibration"] = prog["calibration"]
    return {"slug": a.painting, "spec": spec, "n": n, "mounts": [], "program": prog,
            "values": {"TITLE": a.painting, "DESC": prog.get("description", a.painting).split(":")[0], "N": n, "BUDGET": budget,
                       "NCOLORS": len(prog["palette"]), "DIFFICULTY": a.difficulty or "hard", "DPAD": pad(f'"{a.difficulty or "hard"}"', 19),
                       **prog.get("text", {})},
            "sol_files": ("ref_oil.py", "plan_oracle.py", "oracle_paint.py", "programs.py"),
            "steps": OIL_STEPS if a.family == "oil" else PAINT_STEPS,
            "keep": {"calibration.json": "solution/calibration.json"} if a.family == "oil" else {},
            "reference_png": getattr(a, "reference_png", None)}


# --------------------------------------------------------------------------- assembling a pair (both modes of the generator)
STATS_LINE = re.compile(r"^\d+ control steps, \d+ strokes, .*$", re.M)      # the oracle's stats sentence (README.md, ORACLE_STATS)
FROZEN_NAMES = ("instance.json", "target.png", "truth_alpha.npz")               # the frozen instance, wherever a container gets it
FROZEN_SOLUTION = ("oracle_qpos.npy", "plans.json", "calibration.json", "program.json")
OIL_METRICS = [("de_mean", r"(mean (?:CIELAB )?ΔE (?:<=|≤) )(-?\d+(?:\.\d+)?)"), ("de_p90", r"(p90 ΔE (?:<=|≤) )(-?\d+(?:\.\d+)?)"),
               ("ssim_L", r"(SSIM(?: of L\*)? (?:>=|≥) )(-?\d+(?:\.\d+)?)"), ("edge_corr", r"(edge correlation (?:>=|≥) )(-?\d+(?:\.\d+)?)"),
               ("paint_iou", r"(paint IoU (?:>=|≥) )(-?\d+(?:\.\d+)?)")]


def pair_dirs(root: Path, base: str) -> tuple[Path, Path]:
    """The pair's two task directories (docs/PROTOCOL.md §2.2): <base>-privileged and <base>-standard."""
    return root / f"{base}-privileged", root / f"{base}-standard"


def committed_pair(root: Path, base: str) -> tuple[Path, Path]:
    """The pair as committed, under its v1.0 names or the earlier ones (privileged without a suffix, standard -limited), which
    a regeneration replaces."""
    found = []
    for names in ((f"{base}-privileged", base), (f"{base}-standard", f"{base}-limited")):
        d = next((root / n for n in names if (root / n / "task.toml").is_file()), None)
        if d is None:
            raise SystemExit(f"{root / names[0]}: missing")
        found.append(d)
    return found[0], found[1]


def base_of(d: Path) -> str:
    return re.sub(r"-(privileged|standard|limited)$", "", d.name)


def normalize(d: Path) -> None:
    """The repository's conventions (scripts/task_conventions.py), the last step of every generated task."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import task_conventions
    sys.path.pop(0)
    task_conventions.normalize(d)


def is_frozen(rel: str) -> bool:
    """Per-instance files: the frozen instance (every container's copy), the reference solution's frozen plan and its records."""
    p = Path(rel)
    return (p.name in FROZEN_NAMES or (p.parts[0] == "solution" and p.name in FROZEN_SOLUTION + ("oracle_meta.json",))
            or rel.startswith("solution/programs_json/"))


def read_frozen(d: Path) -> dict:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*"))
            if p.is_file() and "results" not in p.relative_to(d).parts and "__pycache__" not in p.parts and is_frozen(str(p.relative_to(d)))
            and not str(p.relative_to(d)).endswith("oracle_meta.json")}


def template_copy(root: Path, base: str) -> tuple[Path, Path]:
    """A temporary copy of the template pair (it may be the pair being written)."""
    src_u, src_l = committed_pair(root, base)
    tmp = Path(tempfile.mkdtemp(prefix="mkbrush_tpl_"))
    ign = shutil.ignore_patterns("results", "__pycache__")
    shutil.copytree(src_u, tmp / "privileged", ignore=ign); shutil.copytree(src_l, tmp / "standard", ignore=ign)
    return tmp / "privileged", tmp / "standard"


def oil_calibrated_text(text: dict, cal: dict, factors: dict) -> dict:
    """The oil program's texts carry placeholder thresholds (the rule is calibrated on the reference solution's own execution, at
    generation time): put in the calibrated rule (solution/calibration.json), say how it was calibrated (README goal), and record
    the reference execution's mean ΔE and SSIM among the difficulty axes (task.toml)."""
    r, b = cal["rule"], cal["baseline"]; out = {}
    for k, s in text.items():
        for m, rx in OIL_METRICS:
            s = re.sub(rx, lambda mm: mm.group(1) + str(r[m]), s)
        out[k] = s
    out["GOAL_MD"] += (f" The thresholds are the reference solution's execution by this robot ({int(b['n_strokes'])} strokes: mean ΔE "
                       f"{b['de_mean']:.2f}, p90 {b['de_p90']:.2f}, SSIM {b['ssim_L']:.3f}, edge correlation {b['edge_corr']:.3f}, paint IoU "
                       f"{b['paint_iou']:.3f}) with a margin (ΔE x {factors['de_factor']}, SSIM - {factors['ssim_margin']}, edge correlation - "
                       f"{factors['edge_corr']}, paint IoU - 0.03).")
    out["AXES"] = re.sub(r"(palette_floor_de = [^\n]*\n)",
                         lambda mm: mm.group(1) + f"reference_de_mean = {b['de_mean']:.2f}\nreference_ssim_L = {b['ssim_L']:.3f}\n", out["AXES"])
    return out


def oracle_values(family: str, slug: str) -> dict:
    """The oracle label and its evidence for both modes, from scripts/robopaint_templates/oracle_evidence.json (the recorded
    oracle runs; PROTOCOL §2.7): ORACLE, ORACLE_EVIDENCE_U (privileged), ORACLE_EVIDENCE_L (standard)."""
    R = json.load(open(TPL["dir"] / "oracle_evidence.json", encoding="utf-8")); F = R["families"][family]; rel = R["release"]
    out = {"ORACLE": R["label"]}
    for side, key in (("u", "ORACLE_EVIDENCE_U"), ("l", "ORACLE_EVIDENCE_L")):
        if slug not in F["targets"]:
            out[key] = ("Reference solution in solution/; at generation the graders' tooling replayed it and scored 1 (the generator's self-test). "
                        "No recorded Harbor oracle run yet.")
            continue
        job, nop = (rel[k].format(family=family, side=side) for k in ("jobs", "nop_jobs"))
        pair = f"{family}-{slug}"; v2 = " and ".join(F["v2_pairs"])
        t = (f"Reference solution in solution/. Oracle 1 and nop 0 in the release validation ({rel['host']}, {rel['date']}: {job}, {nop}), "
             f"on earlier scoring and tooling. Changed since: the v2 registered scoring ({F['v2']}: scorer and success rule; the saved "
             f"oracle trajectories re-scored, all pass; Harbor oracle and nop on {v2}{', this pair included' if slug in F['v2_pairs'] else ''})")
        if F["snapshot23"] != F["v2"]:
            t += f", tooling snapshot 23 ({F['snapshot23']}: the scorer; re-scores bit-identical)"
        t += f", {R['later_tooling']}"
        t += f"; {R['standard_change']}." if side == "l" else "."
        P = R["p22"]
        if pair in P["targets"]:
            name = f"{pair}-i00" + ("-limited" if side == "l" else "")
            t += (f" This pair: oracle 1 and nop 0 again {P['when']} ({P['host']}, {P['date']}: {P['jobs'].format(name=name)}, "
                  f"{P['nop_jobs'].format(name=name)}).")
        V = R["v22"].get(pair)
        if V and (V["mode"] == "standard") == (side == "l"):
            t += f" This pair: oracle 1 and nop 0 {V['when']} ({V['host']}, {V['date']}: {V['jobs']}, {V['nop_jobs']})."
        out[key] = t + " Not re-run on this version (static validation only)."
    return out


def derive_values(family: str, slug: str, dst_u: Path, difficulty: str | None) -> tuple[dict, str]:
    """The template values of a pair, from its frozen files (tests/instance.json, solution/program.json, solution/calibration.json)
    and the family's catalogue (targets.json): the same values whether the pair was just made or is regenerated (--refresh)."""
    inst = json.load(open(dst_u / "tests" / "instance.json", encoding="utf-8")); tg, tr = inst["target"], inst["truth"]
    v = {"NAME": f"robopaint-{family}-{slug}-i00", "FAMILY": f"robopaint_{family}_{slug.replace('-', '_')}", "IMAGE": IMAGE,
         **oracle_values(family, slug)}
    tdir = family
    if family in ("kaishu", "xingshu"):
        cat = json.load(open(TPL["dir"] / family / "targets.json", encoding="utf-8"))
        works = {s: c for s, c in cat["works"]}; singles = {s: (c, st) for s, c, st in cat["singles"]}
        if slug in singles:
            chars, structure = singles[slug]
        elif slug in works:
            chars, structure = works[slug], "work"
        else:
            raise SystemExit(f"unknown {family} target {slug!r} ({TPL['dir'] / family / 'targets.json'})")
        script = ("regular script", "楷书") if family == "kaishu" else ("running script", "行书")
        n = int(tg["success"]["max_strokes"])                     # kaishu: the exemplar's strokes; xingshu: the contact limit
        if structure == "work":
            difficulty = "extreme"
            task_md = f"the exemplar work **{chars}** ({len(chars)} characters in {script[0]}, {script[1]}, in two columns read right to left)"
            task_plain = f"the exemplar work {chars} ({len(chars)} characters in {script[0]}, two columns read right to left)"
        else:
            difficulty = ("medium" if n <= 5 else "hard") if family == "kaishu" else "hard"
            task_md = f"the exemplar character **{chars}** in {script[0]} ({script[1]})"
            task_plain = f"the exemplar character {chars} in {script[0]}"
        v.update({"TITLE": chars, "TASK_MD": task_md, "TASK_PLAIN": task_plain, "N": n, "DIFFICULTY": difficulty,
                  "DPAD": pad(f'"{difficulty}"', 19), "NPAD": pad(str(n), 19), "STRUCTURE": structure, "NCHARS": len(chars)})
        if family == "xingshu":
            v["NREG"] = int(tr["n_strokes"])                       # the regions of the exemplar's ink (min_stroke_coverage units)
            src = cat.get("sources") or {}
            v["SOURCES"] = src.get(slug) or src.get("*")
            if not v["SOURCES"]:
                raise SystemExit(f"{TPL['dir'] / 'xingshu' / 'targets.json'}: no sources entry for {slug!r} (or '*')")
    elif family == "lettering":
        sys.path.insert(0, str(dst_u / "solution"))
        import letters as LT
        sys.path.pop(0)
        tdir = "lettering_pointed" if LT.HANDS[tr["hand"]].get("pen") == "pointed" else "lettering"
        n = int(tr["n_strokes"]); d = difficulty or "medium"
        v.update({"TITLE": tr["word"], "WORD": tr["word"], "HAND": tr["hand"], "N": n, "DIFFICULTY": d, "NLETTERS": len(tr["word"].replace(" ", "")),
                  "IOU": f'{tg["success"]["iou"]:.2f}', "DPAD": pad(f'"{d}"', 19), "NPAD": pad(str(n), 19)})
    else:
        prog = json.load(open(dst_u / "solution" / "program.json", encoding="utf-8")); n = len(prog["strokes"]); d = difficulty or "hard"
        text = prog.get("text", {})
        if family == "oil" and "calibration" in prog:              # the program's thresholds are placeholders, calibrated at generation
            text = oil_calibrated_text(text, json.load(open(dst_u / "solution" / "calibration.json")), prog["calibration"])
        v.update({"TITLE": slug, "DESC": prog.get("description", slug).split(":")[0], "N": n,
                  "BUDGET": int(math.ceil(prog.get("budget_factor", 1.5) * n)), "NCOLORS": len(prog["palette"]),
                  "DIFFICULTY": d, "DPAD": pad(f'"{d}"', 19), **text})
    return v, tdir


def set_image(d: Path) -> None:
    """Every base-image reference of the pair = IMAGE (eai-robopaint at images/robopaint/VERSION)."""
    for f in [d / "environment" / "Dockerfile", d / "tests" / "Dockerfile", d / "environment" / "docker-compose.yaml"]:
        if f.is_file():
            s = f.read_text()
            s2 = re.sub(r"ghcr\.io/embodied-agent-interface-v2-internal/(?:rcb|eai)-robopaint:[\w.-]+", IMAGE, s)
            if s2 != s:
                f.write_text(s2)


def set_client(d: Path) -> None:
    """The standard twin's agent container and verifier: FROM the client base of scripts/eai_standard/client.env, and the agent
    side installs the exact pins of client-requirements.txt, inline (ci_checks/check-standard-client.sh)."""
    for f in (d / "environment" / "Dockerfile", d / "tests" / "Dockerfile"):
        s = f.read_text()
        s2 = re.sub(r"^FROM docker\.io/library/python:\S+", "FROM " + CLIENT_IMAGE, s, flags=re.M)
        s2 = re.sub(r"^RUN pip install --no-cache-dir .*$", "RUN pip install --no-cache-dir " + " ".join(CLIENT_PINS), s2, flags=re.M)
        if s2 != s:
            f.write_text(s2)


def assemble(family: str, slug: str, tpl: str, template_root: Path, out_root: Path, frozen_u: dict, frozen_l: dict, stats: str,
             difficulty: str | None, keep_programs: bool) -> tuple[Path, Path]:
    """Write the pair robopaint-<family>-<slug>-i00-privileged / -standard under out_root: the template pair's code (tooling,
    graders, sidecars, solution code: byte-identical within a family), the eai-standard/2.2 layer from scripts/eai_standard/
    (byte-identical everywhere), the base image IMAGE, the pair's frozen files, the texts rendered from
    scripts/robopaint_templates/, and last the repository's conventions (scripts/task_conventions.py normalize)."""
    name = f"robopaint-{family}-{slug}-i00"; fam = f"robopaint_{family}_{slug.replace('-', '_')}"
    tpl_name = f"robopaint-{family}-{tpl}-i00"; tpl_fam = f"robopaint_{family}_{tpl.replace('-', '_')}"
    src_u, src_l = template_copy(template_root, tpl_name)
    dst_u, dst_l = pair_dirs(out_root, name)
    for d in (dst_u, out_root / name, dst_l, out_root / f"{name}-limited"):   # the pair, under its v1.0 names or the earlier ones
        if d.exists():
            shutil.rmtree(d)
    shutil.copytree(src_u, dst_u); shutil.copytree(src_l, dst_l)
    shutil.rmtree(src_u.parent, ignore_errors=True)
    for d in (dst_u, dst_l):
        for f in sorted(d.rglob("*")):                             # the template's own frozen files go: the pair gets its own
            rel = str(f.relative_to(d))
            if f.is_file() and is_frozen(rel) and not (keep_programs and rel.startswith("solution/programs_json/")):
                f.unlink()
        for f in d.rglob("*"):                                     # code files that name the task's family
            if f.is_file() and f.suffix in (".sh", ".yaml", ".json") and f.name not in IDENTICAL:
                s = f.read_text(); s2 = s.replace(tpl_fam, fam).replace(tpl_name, name)
                if s2 != s:
                    f.write_text(s2)
        set_image(d)
    for rel, src in LAYER.items():                                 # the eai-standard/2.2 layer (ci_checks/check-tooling-identity.sh)
        shutil.copy(ROOT / "scripts" / "eai_standard" / src, dst_l / rel)
    set_client(dst_l)
    for d, frozen in ((dst_u, frozen_u), (dst_l, frozen_l)):
        for rel, b in frozen.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True); (d / rel).write_bytes(b)
    import numpy as np
    n_acts = int(np.load(dst_u / "solution" / "oracle_qpos.npy").shape[0])
    (dst_l / "solution" / "oracle_meta.json").write_text(json.dumps({"K": 1, "interpolate": "hold", "source": f"{name} oracle trajectory ({n_acts} control steps)"}) + "\n")
    values, tdir = derive_values(family, slug, dst_u, difficulty)
    for side, d in (("u", dst_u), ("l", dst_l)):
        for f in ("instruction.md", "README.md", "task.toml"):
            (d / f).write_text(render((TPL["dir"] / tdir / f"{side}_{f}").read_text(), values).replace("ORACLE_STATS", stats))
    import tomllib
    budget = tomllib.load(open(dst_l / "task.toml", "rb"))["agent"]["timeout_sec"]
    m = re.search(r'RCB_WALL_CLOCK_S: "(\d+)"', (dst_l / "environment" / "docker-compose.yaml").read_text())
    if not m or float(m.group(1)) != float(budget) or tomllib.load(open(dst_u / "task.toml", "rb"))["agent"]["timeout_sec"] != budget:
        raise SystemExit(f"{name}: the agent budget differs between the two task.toml files and the sim's RCB_WALL_CLOCK_S")
    for d in (dst_u, dst_l):
        normalize(d)
    return dst_u, dst_l


def refresh(dirs: list[Path], a) -> int:
    """Regenerate committed pairs from their frozen files: no docker, no GPU; a committed pair comes out byte-identical."""
    import tomllib
    for d in dirs:
        m = re.fullmatch(r"robopaint-([a-z]+)-([a-z0-9]+(?:-[a-z0-9]+)*)-i00", base_of(d))
        if not m or m.group(1) not in FAMILIES:
            raise SystemExit(f"{d}: not a brush-family pair (robopaint-<family>-<target>-i00-privileged)")
        family, slug = m.groups()
        du, dl = committed_pair(d.parent, base_of(d))
        stats = STATS_LINE.search((du / "README.md").read_text())
        if not stats:
            raise SystemExit(f"{du}/README.md: no oracle stats line")
        meta = tomllib.load(open(du / "task.toml", "rb"))["metadata"]
        assemble(family, slug, a.template or FAMILIES[family]["template"], Path(a.template_root), Path(a.out_root), read_frozen(du), read_frozen(dl),
                 stats.group(0), meta.get("difficulty") if family not in ("kaishu", "xingshu") else None, keep_programs=False)
        print(f"refreshed {base_of(d)}-privileged (+ -standard)", flush=True)
    return 0


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--family", choices=sorted(FAMILIES))
    ap.add_argument("--target", help="kaishu / xingshu: a slug of scripts/robopaint_templates/<family>/targets.json")
    ap.add_argument("--graphics", help="kaishu: Make Me a Hanzi graphics.txt (github.com/skishore/makemeahanzi); xingshu: the task's "
                                       "exemplar file in that format (one line per character, \"strokes\" = the regions of its ink)")
    ap.add_argument("--max-strokes", type=int, help="xingshu: the contact limit (success.max_strokes; default: the number of regions)")
    ap.add_argument("--box-mm", type=float, default=150.0); ap.add_argument("--nfev", type=int, default=25)
    ap.add_argument("--plans", help="kaishu: precomputed robot-free plans (solution/opt_calli.py output for exactly this instance, e.g. from a "
                                    "parallel run); skips the in-container optimisation; checked against the instance's stroke count")
    ap.add_argument("--word"); ap.add_argument("--hand")
    ap.add_argument("--painting"); ap.add_argument("--budget-factor", type=float, default=1.5)
    ap.add_argument("--reference-png", help="oil: the reference picture (1024 px RGB; becomes target.png)")
    ap.add_argument("--difficulty", choices=("easy", "medium", "hard", "extreme"))
    ap.add_argument("--template", help="the template pair's target (default: the family's)")
    ap.add_argument("--refresh", nargs="*", metavar="PAIR", help="regenerate committed pairs (tasks/robopaint-<family>-<target>-i00-privileged) "
                    "from their frozen files; no directory = every brush-family pair under --out-root")
    ap.add_argument("--template-root", default=str(ROOT / "tasks")); ap.add_argument("--out-root", default=str(ROOT / "tasks"))
    ap.add_argument("--templates-dir", default=str(TEMPLATES_DEFAULT)); ap.add_argument("--image", default=IMAGE); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    TPL["dir"] = Path(a.templates_dir)
    if a.refresh is not None:
        dirs = [Path(d.rstrip("/")) for d in a.refresh] or sorted(p for p in Path(a.out_root).iterdir() if p.is_dir() and re.fullmatch(
            rf"robopaint-({'|'.join(FAMILIES)})-[a-z0-9-]+-i00(-privileged)?", p.name))
        return refresh(dirs, a)
    if not a.family:
        ap.error("--family is required (or --refresh)")
    fam_cfg = FAMILIES[a.family]
    tpl = a.template or fam_cfg["template"]
    a._src_u = committed_pair(Path(a.template_root), f"robopaint-{a.family}-{tpl}-i00")[0]
    h = {"kaishu": kaishu_target, "lettering": lettering_target, "acrylic": painting_target, "oil": painting_target,
         "xingshu": xingshu_target}[a.family](a)
    slug = h["slug"]
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        raise SystemExit(f"bad slug {slug!r}")
    name = f"robopaint-{a.family}-{slug}-i00"; fam = f"robopaint_{a.family}_{slug.replace('-', '_')}"
    h["spec"]["task"] = fam
    dst_u, dst_l = pair_dirs(Path(a.out_root), name)
    if (dst_u.exists() or dst_l.exists()) and not a.force:
        sys.exit(f"{dst_u} exists (use --force to overwrite)")
    work = Path(tempfile.mkdtemp(prefix="mkbrush_"))
    for f in ("rcb_brush.py", "rcb_brush_score.py", "rcb_scorer.py"):
        shutil.copy(a._src_u / "environment" / "scorer" / f, work / f)
    for f in h["sol_files"]:
        shutil.copy(a._src_u / "solution" / f, work / f)
    if "program" in h:
        (work / "program.json").write_text(json.dumps(h["program"], indent=1))
    (work / "spec.json").write_text(json.dumps(h["spec"], ensure_ascii=False, indent=1))
    if getattr(a, "plans", None):
        pl = json.load(open(a.plans))
        need = h["max_strokes"] if a.family == "xingshu" else h["n"]          # xingshu: one plan per brush contact (the contact limit)
        if a.family not in ("kaishu", "xingshu") or len(pl["plans"]) != need:
            sys.exit(f"--plans: {len(pl['plans'])} plans for {need} contacts (kaishu / xingshu only)")
        shutil.copy(a.plans, work / "plans.json")
    if a.family == "oil":                                            # oil: the reference picture (P/2)
        ref = a.reference_png or h.get("reference_png")
        if not ref or not Path(ref).is_file():
            sys.exit("oil: --reference-png <the reference picture, 1024 px RGB> needed")
        shutil.copy(ref, work / "reference.png")
    (work / "gen.sh").write_text("set -e\n" + h["steps"] + "\n" + SELFTEST)
    cmd = f"bash gen.sh; rc=$?; chown -R {os.getuid()}:{os.getgid()} /work; exit $rc"
    extra = shlex.split(os.environ.get("RCB_GEN_DOCKER_ARGS", ""))      # e.g. "--network none" on a host without free docker networks
    docker = ["docker", "run", "--rm", "--gpus", os.environ.get("RCB_GEN_GPUS", "all"), "--cpus", "4", "--memory", "8g", "-e", "RCB_SESSION_LOG=",
              "-e", "OMP_NUM_THREADS=4", "-e", "RCB_TORCH_THREADS=4", *extra, *h["mounts"], "-v", f"{work}:/work", "-w", "/work", a.image, "bash", "-c", cmd]
    print("+", " ".join(docker[:10]), "...", flush=True)
    subprocess.run(docker, check=True)
    st = json.loads((work / "selftest.json").read_text())
    if not st["scorer_equals_graders"] or not st["agent_actions_equal_oracle"]:
        sys.exit(f"self-test failed: {json.dumps(st)[:2000]}")
    full, agent = work / "full", work / "agent"
    truth = {f: (full / f).read_bytes() for f in FROZEN_NAMES if (full / f).exists()}
    if h.get("licence"):          # xingshu: the exemplar's public-domain record replaces the calligraphy default (Make Me a Hanzi /
        import io                 # Arphic) in the graders' truth and in target.png's PNG comment; no hashed field changes (K/5 issue 1 (b))
        import numpy as np
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
        L = h["licence"]
        d = json.loads(truth["instance.json"])
        d["truth"]["source"], d["truth"]["license"], d["truth"]["notice"] = L["source"], L["license"], L["notice"]
        truth["instance.json"] = (json.dumps(d, indent=1, ensure_ascii=False)).encode()
        arr = np.asarray(Image.open(full / "target.png").convert("RGB")).copy()
        meta = PngInfo(); meta.add_text("Comment", L["picture"]); buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG", pnginfo=meta)
        assert np.array_equal(np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB")), arr)
        truth["target.png"] = buf.getvalue()
    import numpy as np
    acts = np.load(work / "oracle_qpos.npy").astype(np.float32)
    buf = __import__("io").BytesIO(); np.save(buf, acts)
    frozen_u = {**{f"tests/{f}": b for f, b in truth.items()}, **{f"environment/scorer/{f}": b for f, b in truth.items()},
                "environment/instance.json": (agent / "instance.json").read_bytes(), "environment/target.png": truth["target.png"],
                "solution/oracle_qpos.npy": buf.getvalue()}
    frozen_l = {**{f"environment/sim/{f}": b for f, b in truth.items()}, "environment/target.png": truth["target.png"],
                "solution/oracle_qpos.npy": buf.getvalue()}
    if h.get("licence"):          # the agent's copy of the picture carries the same PNG comment
        frozen_u["environment/target.png"] = truth["target.png"]
    for src, rel in h["keep"].items():
        frozen_u[rel] = (work / src).read_bytes()
    if "program" in h:
        frozen_u["solution/program.json"] = json.dumps(h["program"], indent=1).encode()
    r = [json.loads(l) for l in (work / "full_replay.json").read_text().splitlines() if l.startswith("{")][-1]["replays"][0]
    if "de_mean" in r:
        stats = (f"{len(acts)} control steps, {int(r['n_strokes'])} strokes, mean ΔE {r['de_mean']:.3f}, p90 ΔE {r['de_p90']:.3f}, SSIM {r['ssim_L']:.4f}, "
                 f"paint IoU {r['paint_iou']:.4f}.")
        keys = ("success", "de_mean", "de_p90", "ssim_L", "paint_iou", "n_strokes")
    else:
        iou = r.get("iou_registered", r["iou"])
        stats = (f"{len(acts)} control steps, {int(r['n_strokes'])} strokes, IoU {iou:.3f}, boundary F {r['boundary_f']:.3f}, min stroke coverage "
                 f"{r.get('min_stroke_coverage_registered', r['min_stroke_coverage']):.3f}, stray {r['stray_frac']:.4f}.")
        keys = ("success", "iou", "iou_registered", "boundary_f", "min_stroke_coverage", "stray_frac", "n_strokes")
    difficulty = a.difficulty if a.family not in ("kaishu", "xingshu") else None
    dst_u, dst_l = assemble(a.family, slug, tpl, Path(a.template_root), Path(a.out_root), frozen_u, frozen_l, stats, difficulty, keep_programs=True)
    summary = {"privileged": str(dst_u), "standard": str(dst_l), "family": fam, "n_strokes": h["n"], **({"max_strokes": h["max_strokes"]} if "max_strokes" in h else {}),
               "instance_sha": json.loads((full / "instance.json").read_text())["instance_sha"],
               "oracle": {k: r[k] for k in keys if k in r} | {"n_actions": int(len(acts))},
               "selftest": {k: st[k] for k in ("scorer_equals_graders", "agent_actions_equal_oracle")}}
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
