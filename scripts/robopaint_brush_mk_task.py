#!/usr/bin/env python3
"""Generate a RoboPaint brush task pair (privileged task + its standard twin): families kaishu (楷书 臨帖), xingshu (行书 臨帖), lettering
(臨摹 of engraved English round hand, pointed pen), acrylic / oil (libmypaint paintings: a hidden stroke program / a reference picture).

    python scripts/robopaint_brush_mk_task.py --family kaishu --target yongzibafa --graphics /path/to/makemeahanzi/graphics.txt
    python scripts/robopaint_brush_mk_task.py --family kaishu --target linfengguilong --graphics ... --entry diagonal   # a work (targets.json)
    python scripts/robopaint_brush_mk_task.py --family xingshu --target <slug> --graphics <slug>.graphics.txt --max-strokes N --plans plans.json
        # 行书 臨帖 (連筆) from a public-domain rubbing: --graphics = the task's own exemplar file (graphics.txt format, one line per
        # character, "strokes" = the regions of its ink); --max-strokes = the connected contacts (the cap), --plans = one plan per contact
    python scripts/robopaint_brush_mk_task.py --family caoshu --target <slug> --graphics <slug>.graphics.txt --max-strokes N --plans plans.json
        # 草书 臨帖 (the xingshu machinery; works keep the column as written in ONE frame shared by its characters); the exemplar file and
        # the plans come from scripts/robopaint_caoshu/ (cs_exemplar.py, cs_plan.py); the first pair of the family takes its code from a
        # xingshu pair: --template-family xingshu --template yong
    python scripts/robopaint_brush_mk_task.py --family lettering --target <slug> --exemplar <slug>.exemplar.json
        # 臨摹 of a public-domain engraved copybook plate: the exemplar file and its writing routes (one per contact) come from
        # scripts/robopaint_lettering/lt_exemplar.py; the family's first pair took its code from an earlier pair and its new reference
        # solution from --solution-dir (--template-family / --template)
    python scripts/robopaint_brush_mk_task.py --family acrylic --painting <name> --template redfuji   # a program entry (programs_json/)
    python scripts/robopaint_brush_mk_task.py --family oil --painting <name> --reference-png <picture.png> --difficulty extreme
    python scripts/robopaint_brush_mk_task.py --refresh [tasks/robopaint-<family>-<target>-i<NN> ...] --out-root <dir>   # rebuild committed pairs
    python scripts/robopaint_brush_mk_task.py --resolve tasks/robopaint-<kaishu|xingshu>-<target>-i<NN>-privileged --plans plans.json
        # re-solve a committed calligraphy pair: new robot-free plans (solution/opt_calli.py --profile print) written on the robot;
        # only the reference solution changes (resolve()), then scripts/robopaint_strict/mk_tasks.py

--template names the family's template pair under --template-root (default tasks/; the defaults: kaishu yongzibafa, xingshu yong,
caoshu wen, lettering liberty, acrylic redfuji, oil cypresses; --template-family takes the code from another family's pair, for a
family's first pair; --solution-dir replaces the template's solution code); any committed pair of the family serves (the code is
identical within a family,
scripts/robopaint_strict/ci/advisory-tooling.sh). A painting's program is read from the template's solution/programs_json/, where a pair's
own entry is its current program: a painting pair is remade with itself as the template.

-> tasks/robopaint-<family>-<target>-i00-privileged/ and ...-i00-standard/ (mode standard, eai-standard/2.2), family
robopaint_<family>_<target>; every task ends with scripts/task_conventions.py's normalize (the repository's conventions). A pair
whose frozen instance or verifier changes after publication is a new task (PROTOCOL §2.8): the next instance index (-i01, ...);
--refresh keeps each committed pair's own index.

The pairs this script writes have RoboPaint's picture rule only. The process rules (docs/benchmarks/robopaint.md) are added by
scripts/robopaint_strict/mk_tasks.py, the generator of the committed tasks: it runs --refresh into a temporary directory and writes
tasks/ from that. For a new pair: this script, then scripts/robopaint_strict/measure_reference.py (the reference solution's path and
mark width into rules.json), then mk_tasks.py.

--refresh rebuilds committed pairs from their own frozen files (no docker, no GPU, standard library only): the template pair's code,
the eai-standard/2.2 layer, the base image of images/robopaint/VERSION and the rendered texts around the frozen instance, the
reference plan and its records. It writes into --out-root, which must not be tasks/ (the texts lack the process rules); to regenerate
the committed tasks run scripts/robopaint_strict/mk_tasks.py.

Files: the code of the template pair (tasks/robopaint-<family>-<template>-i<NN>*, or --template-root) is copied (tooling, graders,
sidecars and solution code stay byte-identical within a family; the wiring of the process rules' module rcb_brush_strict.py comes
with them); the standard twin's client and service layer come from
scripts/eai_standard/ (byte-identical everywhere); the texts are rendered from scripts/robopaint_templates/<family>/
({u,l}_{instruction.md,README.md,task.toml} with {{PLACEHOLDERS}}, values from the frozen files: derive_values); the frozen files
are made inside the base image (docker, GPU):
the graders' instance + target.png (rcb_brush_score.py make-instance), the agent's copy (make-agent-instance: scene + rule only),
the reference oracle (kaishu: solution/opt_calli.py per-stroke optimisation + solution/ref_calli.py on the robot; lettering:
solution/ref_lettering.py; paintings: solution/ref_oil.py paints the hidden program, the painted sheet becomes the exemplar), and a
self-test of the scoring path (the scoring service on the graders' copy; the oracle through it on the agent's copy; its metrics
must equal the graders' own score of the same trajectory). What each container gets follows the leak rule (the agent: scene,
picture, tooling; the scorer / verifier / sim sidecar: the graders' copy). Then: scripts/robopaint_strict/mk_tasks.py, bash
ci_checks/run_all.sh <dirs>, harbor oracle / nop runs in both modes, `harbor add <dirs>` from tasks/.
"""
from __future__ import annotations
import argparse, ast, json, math, os, re, shlex, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.dont_write_bytecode = True                 # the solution modules imported from task dirs (letters.py, programs.py) leave no caches
ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DEFAULT = ROOT / "scripts" / "robopaint_templates"
TPL = {"dir": TEMPLATES_DEFAULT}                              # set from --templates-dir
IMAGE = "ghcr.io/mll-lab-nu/eai-robopaint:" + (ROOT / "images" / "robopaint" / "VERSION").read_text().strip()
SHEET_MM = 227.1845
IDENTICAL = ("instance.json", "rcb_brush.py", "rcb_brush_score.py", "rcb_scorer.py", "rcb1.py", "server.py", "rcb_client.py", "ARPHICPL.TXT")
FAMILIES = {"kaishu": {"medium": "calligraphy", "template": "yongzibafa"}, "lettering": {"medium": "pointed_pen", "template": "liberty"},
            "acrylic": {"medium": "mypaint", "template": "redfuji"}, "oil": {"medium": "mypaint", "template": "cypresses"},
            "xingshu": {"medium": "calligraphy", "template": "yong"}, "caoshu": {"medium": "calligraphy", "template": "wen"}}
SCRIPT_FAMILIES = ("kaishu", "xingshu", "caoshu")      # Chinese calligraphy: exemplar files + per-contact plans; difficulty from the target
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
                      + ("" if a.plans else f" && RCB_TOOLS=/work python opt_calli.py --instance full/instance.json --graphics /mmah/graphics.txt --out plans.json --nfev {a.nfev}"
                         + (f" --entry {a.entry}" if a.entry != "vertical" else "")) +
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


def caoshu_target(a) -> dict:
    """草书 臨帖 (the xingshu machinery: medium calligraphy, the same scorer and solution code). The exemplar is the task's own file in
    graphics.txt format, made from a public-domain scan by scripts/robopaint_caoshu/cs_exemplar.py ("strokes" = the regions of its
    ink, cut along each brush contact); success.max_strokes = --max-strokes = the exemplar's connected contacts (cs_exemplar.py's
    trails), and --plans holds one plan per contact (cs_plan.py). A single character: the 150 mm box of the other families. A work
    keeps the column as written: its characters share ONE frame (every box the same square of frame_mm, centred), so the ligatures
    between characters (連綿) stay on the sheet; targets.json works = [slug, characters, frame_mm]. Licence record: targets.json
    licences[slug] or licence."""
    cat = json.load(open(TPL["dir"] / "caoshu" / "targets.json"))
    works = {s: (c, float(f)) for s, c, f in cat["works"]}
    singles = {s: (c, st) for s, c, st in cat["singles"]}
    if a.target in singles:
        ch, structure = singles[a.target]; chars = ch
    elif a.target in works:
        chars, frame = works[a.target]; structure = "work"
    else:
        raise SystemExit(f"unknown caoshu target {a.target!r} ({TPL['dir'] / 'caoshu' / 'targets.json'})")
    sources = (cat.get("sources") or {}).get(a.target) or (cat.get("sources") or {}).get("*")
    if not sources:
        raise SystemExit(f"{TPL['dir'] / 'caoshu' / 'targets.json'}: no sources entry for {a.target!r} (or '*')")
    if not a.graphics or not Path(a.graphics).is_file():
        raise SystemExit("caoshu: --graphics <the task's exemplar file, graphics.txt format> needed")
    recs = {}
    for line in open(a.graphics, encoding="utf-8"):
        if line.strip():
            d = json.loads(line)
            if d["character"] in recs:
                raise SystemExit(f"{a.graphics}: two lines for {d['character']!r}")
            recs[d["character"]] = d
    missing = [c for c in chars if c not in recs]
    if missing or len(set(chars)) != len(chars):
        raise SystemExit(f"{a.graphics}: characters {missing!r} missing (or a work repeats a character)")
    nreg = sum(len(recs[c]["strokes"]) for c in chars)
    if not a.max_strokes:
        raise SystemExit("caoshu: --max-strokes <the exemplar's connected contacts> needed")
    n = int(a.max_strokes)
    if structure == "work":
        X0 = round((SHEET_MM - frame) / 2, 4)
        target = {"characters": chars, "boxes": [[X0, X0, frame]] * len(chars)}
    else:
        X0 = (SHEET_MM - a.box_mm) / 2
        target = {"character": chars, "box_mm": [X0, X0, a.box_mm]}
    spec = {"task": None, "medium": "calligraphy",
            "target": {**target, "graphics": "/mmah/graphics.txt", "stroke_slack": 0, "success": {**SUCCESS_KAISHU, "max_strokes": n}}}
    lic = (cat.get("licences") or {}).get(a.target) or cat.get("licence")
    return {"slug": a.target, "spec": spec, "n": nreg, "max_strokes": n, "licence": lic,
            "mounts": ["-v", f"{Path(a.graphics).resolve()}:/mmah/graphics.txt:ro"],
            "sol_files": ("opt_calli.py", "ref_calli.py", "plan_oracle.py", "oracle_paint.py"),
            "steps": ("python rcb_brush_score.py make-instance --spec spec.json --out full/instance.json"
                      " && python rcb_brush_score.py make-agent-instance --instance full/instance.json --out-dir agent"
                      " && RCB_SOLUTION_DIR=/work python rcb_brush.py run-oracle --instance full/instance.json --code plan_oracle.py --out plan_traj.npz > plan.json"
                      " && python -c \"import numpy as np; np.save('oracle_qpos.npy', np.load('plan_traj.npz')['actions'].astype(np.float32))\""),
            "keep": {"plans.json": "solution/plans.json"}}


def lettering_target(a) -> dict:
    """Lettering (臨摹 of engraved English round hand): the exemplar is the task's own file (--exemplar <slug>.exemplar.json), made by
    scripts/robopaint_lettering/lt_exemplar.py from a public-domain scan: the scan's ink re-drawn with this pointed pen ("pieces":
    the regions, at most 30 mm each along the strokes; rcb_brush_score's pointed-pen letters target) and one writing route per
    connected piece of its ink ("routes": the reference plan, solution/plans.json). success.max_strokes = the routes (the exemplar's
    own pen lifts, no margin). targets.json: [slug, text, structure (word | line)], the README's SOURCES and the licence record."""
    cat = json.load(open(TPL["dir"] / "lettering" / "targets.json", encoding="utf-8"))
    tg = {r[0]: r for r in cat["targets"]}
    if a.target not in tg:
        raise SystemExit(f"unknown lettering target {a.target!r} ({TPL['dir'] / 'lettering' / 'targets.json'})")
    if not a.exemplar or not Path(a.exemplar).is_file():
        raise SystemExit("lettering: --exemplar <the task's exemplar file (lt_exemplar.py)> needed")
    ex = json.load(open(a.exemplar, encoding="utf-8"))
    if ex["slug"] != a.target or ex["text"] != tg[a.target][1]:
        raise SystemExit(f"{a.exemplar}: made for {ex['slug']!r} / {ex['text']!r}, not {a.target!r} / {tg[a.target][1]!r}")
    n = len(ex["routes"])
    spec = {"task": None, "medium": "pointed_pen",
            "target": {"word": ex["text"], "hand": ex["hand"], "box_mm": ex["fidelity"]["target_bbox_mm"], "strokes": ex["pieces"],
                       "stroke_slack": 0, "success": {**SUCCESS_LETTERING, "max_strokes": n}}}
    plans = {"axis_deg": ex["axis_deg"], "source": f"{Path(a.exemplar).name}: the writing routes of the exemplar's {n} contacts",
             "routes": [{"points_mm": r["points_mm"], "widths_mm": r["widths_mm"]} for r in ex["routes"]]}
    lic = (cat.get("licences") or {}).get(a.target) or cat.get("licence")
    return {"slug": a.target, "spec": spec, "n": len(ex["pieces"]), "max_strokes": n, "licence": lic, "mounts": [], "plans": plans,
            "sol_files": ("ref_lettering.py", "plan_oracle.py", "oracle_paint.py"),
            "steps": ("python rcb_brush_score.py make-instance --spec spec.json --out full/instance.json"
                      " && python rcb_brush_score.py make-agent-instance --instance full/instance.json --out-dir agent"
                      " && RCB_SOLUTION_DIR=/work python rcb_brush.py run-oracle --instance full/instance.json --code plan_oracle.py --out plan_traj.npz > plan.json"
                      " && python -c \"import numpy as np; np.save('oracle_qpos.npy', np.load('plan_traj.npz')['actions'].astype(np.float32))\""),
            "keep": {"plans.json": "solution/plans.json"}}


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


def pair_base(root: Path, family: str, slug: str) -> str:
    """The committed pair robopaint-<family>-<slug>-i<NN> under root, whatever its instance index."""
    found = sorted({base_of(d) for d in root.glob(f"robopaint-{family}-{slug}-i[0-9][0-9]*")
                    if (d / "task.toml").is_file() and re.fullmatch(rf"robopaint-{family}-{re.escape(slug)}-i\d\d", base_of(d))})
    if len(found) != 1:
        raise SystemExit(f"{root}: expected one committed pair robopaint-{family}-{slug}-i<NN>, found {found or 'none'}")
    return found[0]


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


def derive_values(family: str, slug: str, dst_u: Path, difficulty: str | None, idx: str = "00") -> tuple[dict, str]:
    """The template values of a pair, from its frozen files (tests/instance.json, solution/program.json, solution/calibration.json)
    and the family's catalogue (targets.json): the same values whether the pair was just made or is regenerated (--refresh)."""
    inst = json.load(open(dst_u / "tests" / "instance.json", encoding="utf-8")); tg, tr = inst["target"], inst["truth"]
    v = {"NAME": f"robopaint-{family}-{slug}-i{idx}", "FAMILY": f"robopaint_{family}_{slug.replace('-', '_')}", "IMAGE": IMAGE,
         **oracle_values(family, slug)}
    tdir = family
    if family in SCRIPT_FAMILIES:
        cat = json.load(open(TPL["dir"] / family / "targets.json", encoding="utf-8"))
        works = {w[0]: w[1] for w in cat["works"]}; singles = {s: (c, st) for s, c, st in cat["singles"]}
        if slug in singles:
            chars, structure = singles[slug]
        elif slug in works:
            chars, structure = works[slug], "work"
        else:
            raise SystemExit(f"unknown {family} target {slug!r} ({TPL['dir'] / family / 'targets.json'})")
        script = {"kaishu": ("regular script", "楷书"), "xingshu": ("running script", "行书"), "caoshu": ("cursive script", "草书")}[family]
        n = int(tg["success"]["max_strokes"])                     # kaishu: the exemplar's strokes; xingshu, caoshu: the contact limit
        if structure == "work" and family == "caoshu":
            difficulty = "extreme"
            task_md = (f"the exemplar work **{chars}** ({len(chars)} characters in {script[0]}, {script[1]}, one column read top to bottom, "
                       f"its characters joined as in the original)")
            task_plain = f"the exemplar work {chars} ({len(chars)} characters in {script[0]}, one column read top to bottom)"
        elif structure == "work":
            difficulty = "extreme"
            task_md = f"the exemplar work **{chars}** ({len(chars)} characters in {script[0]}, {script[1]}, in two columns read right to left)"
            task_plain = f"the exemplar work {chars} ({len(chars)} characters in {script[0]}, two columns read right to left)"
        else:
            difficulty = {"kaishu": "medium" if n <= 5 else "hard", "xingshu": "hard", "caoshu": "extreme"}[family]
            task_md = f"the exemplar character **{chars}** in {script[0]} ({script[1]})"
            task_plain = f"the exemplar character {chars} in {script[0]}"
        v.update({"TITLE": chars, "TASK_MD": task_md, "TASK_PLAIN": task_plain, "N": n, "DIFFICULTY": difficulty,
                  "DPAD": pad(f'"{difficulty}"', 19), "NPAD": pad(str(n), 19), "STRUCTURE": structure, "NCHARS": len(chars)})
        if family in ("xingshu", "caoshu"):
            v["NREG"] = int(tr["n_strokes"])                       # the regions of the exemplar's ink (min_stroke_coverage units)
            src = cat.get("sources") or {}
            v["SOURCES"] = src.get(slug) or src.get("*")
            if not v["SOURCES"]:
                raise SystemExit(f"{TPL['dir'] / family / 'targets.json'}: no sources entry for {slug!r} (or '*')")
    elif family == "lettering":
        cat = json.load(open(TPL["dir"] / "lettering" / "targets.json", encoding="utf-8"))
        row = {r[0]: r for r in cat["targets"]}.get(slug)
        if row is None:
            raise SystemExit(f"unknown lettering target {slug!r} ({TPL['dir'] / 'lettering' / 'targets.json'})")
        text, structure = row[1], row[2]
        n = int(tg["success"]["max_strokes"]); d = "extreme"           # the contact cap (the exemplar's own pen lifts)
        what = {"word": "the flourished word", "line": "the line"}[structure]
        v.update({"TITLE": text, "TEXT": text, "HAND": tr["hand"], "N": n, "NREG": int(tr["n_strokes"]), "DIFFICULTY": d,
                  "STRUCTURE": structure, "TASK_MD": f"{what} **{text}** (engraved English round hand, 1741)",
                  "TASK_PLAIN": f"{what} {text} (engraved English round hand, 1741)",
                  "NLETTERS": sum(c.isalpha() for c in text), "NWORDS": len(text.split()),
                  "IOU": f'{tg["success"]["iou"]:.2f}', "DPAD": pad(f'"{d}"', 19), "NPAD": pad(str(n), 19)})
        src = cat.get("sources") or {}
        v["SOURCES"] = src.get(slug) or src.get("*")
        if not v["SOURCES"]:
            raise SystemExit(f"{TPL['dir'] / 'lettering' / 'targets.json'}: no sources entry for {slug!r} (or '*')")
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
            s2 = re.sub(r"ghcr\.io/(?:embodied-agent-interface-v2-internal|mll-lab-nu)/(?:rcb|eai)-robopaint:[\w.-]+", IMAGE, s)
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


def npy_rows(path: Path) -> int:
    """The number of rows of a .npy array (the shape in its header): --refresh needs only the standard library, no numpy."""
    with open(path, "rb") as f:
        if f.read(6) != b"\x93NUMPY":
            raise SystemExit(f"{path}: not a .npy file")
        major = f.read(2)[0]
        header = f.read(int.from_bytes(f.read(2 if major == 1 else 4), "little")).decode("latin1")
    return int(ast.literal_eval(header)["shape"][0])


def assemble(family: str, slug: str, tpl: str, template_root: Path, out_root: Path, frozen_u: dict, frozen_l: dict, stats: str,
             difficulty: str | None, keep_programs: bool, tpl_family: str | None = None, solution_dir: Path | None = None,
             idx: str = "00") -> tuple[Path, Path]:
    """Write the pair robopaint-<family>-<slug>-i<idx>-privileged / -standard under out_root: the template pair's code (tooling,
    graders, sidecars, solution code: byte-identical within a family), the eai-standard/2.2 layer from scripts/eai_standard/
    (byte-identical everywhere), the base image IMAGE, the pair's frozen files, the texts rendered from
    scripts/robopaint_templates/, and last the repository's conventions (scripts/task_conventions.py normalize)."""
    name = f"robopaint-{family}-{slug}-i{idx}"; fam = f"robopaint_{family}_{slug.replace('-', '_')}"
    tf = tpl_family or family                                     # another family's pair: a family's first pair (--template-family)
    tpl_name = name if (tf, tpl) == (family, slug) else pair_base(template_root, tf, tpl)
    tpl_fam = f"robopaint_{tf}_{tpl.replace('-', '_')}"
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
    if solution_dir is not None:                                   # a family's new reference solution (--solution-dir)
        for f in sorted((dst_u / "solution").iterdir()):
            if f.is_file() and not is_frozen(f"solution/{f.name}"):
                f.unlink()
        for f in sorted(Path(solution_dir).iterdir()):
            if f.is_file():
                shutil.copy2(f, dst_u / "solution" / f.name)
    notes = (json.load(open(TPL["dir"] / family / "targets.json", encoding="utf-8")).get("notices")
             if (TPL["dir"] / family / "targets.json").is_file() else None)
    if notes:                                                      # the exemplar's licence notices (agent's / graders' copies)
        for d in (dst_u, dst_l):
            for f in d.rglob("NOTICE-exemplar.md"):
                rel = f.relative_to(d).as_posix()
                f.write_text(notes["graders" if rel.startswith(("tests/", "environment/scorer/", "environment/sim/")) else "agent"])
    for rel, src in LAYER.items():                                 # the eai-standard/2.2 layer (ci_checks/check-tooling-identity.sh)
        shutil.copy(ROOT / "scripts" / "eai_standard" / src, dst_l / rel)
    set_client(dst_l)
    for d, frozen in ((dst_u, frozen_u), (dst_l, frozen_l)):
        for rel, b in frozen.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True); (d / rel).write_bytes(b)
    if family == "kaishu":        # NOTICE-exemplar.md (the template's) carries the day of the pair's own Arphic notice (its truth)
        day = re.search(r"\(APL section 2a\): (\d{4}-\d{2}-\d{2})",
                        json.loads((dst_u / "tests" / "instance.json").read_text(encoding="utf-8"))["truth"]["notice"]).group(1)
        for f in [*dst_u.rglob("NOTICE-exemplar.md"), *dst_l.rglob("NOTICE-exemplar.md")]:
            s = f.read_text(encoding="utf-8"); s2 = re.sub(r"\d{4}-\d{2}-\d{2}", day, s)
            if s2 != s:
                f.write_text(s2, encoding="utf-8")
    n_acts = npy_rows(dst_u / "solution" / "oracle_qpos.npy")
    (dst_l / "solution" / "oracle_meta.json").write_text(json.dumps({"K": 1, "interpolate": "hold", "source": f"{name} oracle trajectory ({n_acts} control steps)"}) + "\n")
    values, tdir = derive_values(family, slug, dst_u, difficulty, idx)
    for side, d in (("u", dst_u), ("l", dst_l)):
        for f in ("instruction.md", "README.md", "task.toml"):
            (d / f).write_text(render((TPL["dir"] / tdir / f"{side}_{f}").read_text(), values).replace("ORACLE_STATS", stats))
    # The agent's time limit: the templates' `[agent] timeout_sec` (3600 s in both modes, RoboPaint's number; PROTOCOL
    # §2.12), from which normalize writes the sim's RCB_WALL_CLOCK_S and the instructions' closing `## Time limit` section;
    # ci_checks/check-cutoffs.py checks they agree. To change it, edit the templates (an owner decision) and regenerate.
    for d in (dst_u, dst_l):
        normalize(d)
    return dst_u, dst_l


def refresh(dirs: list[Path], a) -> int:
    """Regenerate committed pairs from their frozen files: no docker, no GPU; a committed pair comes out byte-identical."""
    import tomllib
    for d in dirs:
        m = re.fullmatch(r"robopaint-([a-z]+)-([a-z0-9]+(?:-[a-z0-9]+)*)-i(\d\d)", base_of(d))
        if not m or m.group(1) not in FAMILIES:
            raise SystemExit(f"{d}: not a brush-family pair (robopaint-<family>-<target>-i<NN>-privileged)")
        family, slug, idx = m.groups()
        du, dl = committed_pair(d.parent, base_of(d))
        stats = STATS_LINE.search((du / "README.md").read_text())
        if not stats:
            raise SystemExit(f"{du}/README.md: no oracle stats line")
        meta = tomllib.load(open(du / "task.toml", "rb"))["metadata"]
        assemble(family, slug, a.template or FAMILIES[family]["template"], Path(a.template_root), Path(a.out_root), read_frozen(du), read_frozen(dl),
                 stats.group(0), meta.get("difficulty") if family not in SCRIPT_FAMILIES else None, keep_programs=False, idx=idx)
        print(f"refreshed {base_of(d)}-privileged (+ -standard)", flush=True)
    return 0


def resolve(pair: Path, plans_path: str, a) -> int:
    """Re-solve a committed calligraphy pair (kaishu / xingshu) with new robot-free plans (solution/opt_calli.py output for this
    instance, e.g. --profile print): the plans are written on the robot by the template pair's solution code (plan_oracle.py) in
    the base image, on the pair's own frozen graders' instance, followed by the generator's self-test of the scoring path. Only
    the reference solution changes: solution/plans.json and solution/oracle_qpos.npy of both twins and the README's oracle stats
    line. The frozen instance and the picture stay byte-identical (environment/ and tests/). Then scripts/robopaint_strict/
    mk_tasks.py rewrites the pair (its solution code from the template pair, the texts from rules.json)."""
    base = base_of(pair)
    m = re.fullmatch(r"robopaint-(kaishu|xingshu)-([a-z0-9]+(?:-[a-z0-9]+)*)-i\d\d", base)
    if not m:
        sys.exit(f"{pair}: --resolve takes a kaishu or xingshu pair (robopaint-<family>-<target>-i<NN>-privileged)")
    family = m.group(1)
    du, dl = committed_pair(pair.parent, base)
    tu, _ = committed_pair(Path(a.template_root), pair_base(Path(a.template_root), family, a.template or FAMILIES[family]["template"]))
    pl = json.load(open(plans_path, encoding="utf-8"))
    inst = json.load(open(du / "tests" / "instance.json", encoding="utf-8"))
    cap = int(inst["target"]["success"]["max_strokes"])
    if len(pl["plans"]) != cap:
        sys.exit(f"--plans: {len(pl['plans'])} plans for a cap of {cap} contacts")
    work = Path(tempfile.mkdtemp(prefix="mkbrush_resolve_"))
    for f in ("rcb_brush.py", "rcb_brush_score.py", "rcb_scorer.py"):
        shutil.copy(du / "environment" / "scorer" / f, work / f)
    for f in ("opt_calli.py", "ref_calli.py", "plan_oracle.py", "oracle_paint.py"):
        shutil.copy(tu / "solution" / f, work / f)
    shutil.copy(plans_path, work / "plans.json")
    for sub, src in (("full", du / "tests"), ("agent", du / "environment")):
        (work / sub).mkdir()
        for f in FROZEN_NAMES:
            if (src / f).is_file():
                shutil.copy(src / f, work / sub / f)
    steps = ("RCB_SOLUTION_DIR=/work python rcb_brush.py run-oracle --instance full/instance.json --code plan_oracle.py --out plan_traj.npz > plan.json"
             " && python -c \"import numpy as np; np.save('oracle_qpos.npy', np.load('plan_traj.npz')['actions'].astype(np.float32))\"")
    (work / "gen.sh").write_text("set -e\n" + steps + "\n" + SELFTEST)
    cmd = f"bash gen.sh; rc=$?; chown -R {os.getuid()}:{os.getgid()} /work; exit $rc"
    extra = shlex.split(os.environ.get("RCB_GEN_DOCKER_ARGS", ""))
    docker = ["docker", "run", "--rm", "--gpus", os.environ.get("RCB_GEN_GPUS", "all"), "--cpus", "4", "--memory", "8g", "-e", "RCB_SESSION_LOG=",
              "-e", "OMP_NUM_THREADS=4", "-e", "RCB_TORCH_THREADS=4", *extra, "-v", f"{work}:/work", "-w", "/work", a.image, "bash", "-c", cmd]
    print("+", " ".join(docker[:10]), "...", flush=True)
    subprocess.run(docker, check=True)
    st = json.loads((work / "selftest.json").read_text())
    if not st["scorer_equals_graders"] or not st["agent_actions_equal_oracle"]:
        sys.exit(f"self-test failed: {json.dumps(st)[:2000]}")
    import io
    import numpy as np
    acts = np.load(work / "oracle_qpos.npy").astype(np.float32)
    buf = io.BytesIO(); np.save(buf, acts)
    r = [json.loads(l) for l in (work / "full_replay.json").read_text().splitlines() if l.startswith("{")][-1]["replays"][0]
    iou = r.get("iou_registered", r["iou"])
    stats = (f"{len(acts)} control steps, {int(r['n_strokes'])} strokes, IoU {iou:.3f}, boundary F {r['boundary_f']:.3f}, min stroke coverage "
             f"{r.get('min_stroke_coverage_registered', r['min_stroke_coverage']):.3f}, stray {r['stray_frac']:.4f}.")
    (du / "solution" / "plans.json").write_bytes((work / "plans.json").read_bytes())
    (du / "solution" / "oracle_qpos.npy").write_bytes(buf.getvalue())
    (dl / "solution" / "oracle_qpos.npy").write_bytes(buf.getvalue())
    readme = (du / "README.md").read_text()
    if not STATS_LINE.search(readme):
        sys.exit(f"{du}/README.md: no oracle stats line")
    (du / "README.md").write_text(STATS_LINE.sub(stats, readme, count=1))
    print(json.dumps({"pair": base, "stats": stats, "success": r.get("success"), "selftest": {k: st[k] for k in ("scorer_equals_graders", "agent_actions_equal_oracle")}},
                     ensure_ascii=False))
    shutil.rmtree(work, ignore_errors=True)
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
    ap.add_argument("--entry", choices=("vertical", "diagonal"), default="vertical", help="kaishu: how the reference planner's brush "
                    "meets the paper (solution/opt_calli.py --entry; plans.json records it): a vertical touch-down and lift, or straight "
                    "entry and exit lines along the stroke")
    ap.add_argument("--plans", help="kaishu, and --resolve: precomputed robot-free plans (solution/opt_calli.py output for exactly this "
                                    "instance, e.g. from a parallel run); skips the in-container optimisation; checked against the "
                                    "instance's stroke count")
    ap.add_argument("--exemplar", help="lettering: the task's exemplar file (scripts/robopaint_lettering/lt_exemplar.py: <slug>.exemplar.json)")
    ap.add_argument("--painting"); ap.add_argument("--budget-factor", type=float, default=1.5)
    ap.add_argument("--reference-png", help="oil: the reference picture (1024 px RGB; becomes target.png)")
    ap.add_argument("--difficulty", choices=("easy", "medium", "hard", "extreme"))
    ap.add_argument("--template", help="the template pair's target (default: the family's)")
    ap.add_argument("--template-family", help="the template pair's family (default: --family; another family's pair for a family's first pair)")
    ap.add_argument("--solution-dir", help="replace the template pair's solution code with the files of this directory (a family's new "
                                           "reference solution; the frozen solution files stay the pair's own)")
    ap.add_argument("--refresh", nargs="*", metavar="PAIR", help="rebuild committed pairs (tasks/robopaint-<family>-<target>-i<NN>-privileged) "
                    "from their frozen files into --out-root (not tasks/: scripts/robopaint_strict/mk_tasks.py regenerates the committed "
                    "tasks); no directory = every brush-family pair under --out-root")
    ap.add_argument("--resolve", metavar="PAIR", help="kaishu / xingshu: re-solve this committed pair (tasks/robopaint-<family>-<target>-"
                    "i<NN>-privileged) with --plans: only its reference solution changes (resolve())")
    ap.add_argument("--template-root", default=str(ROOT / "tasks")); ap.add_argument("--out-root", default=str(ROOT / "tasks"))
    ap.add_argument("--templates-dir", default=str(TEMPLATES_DEFAULT)); ap.add_argument("--image", default=IMAGE); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    TPL["dir"] = Path(a.templates_dir)
    if a.refresh is not None:
        if Path(a.out_root).resolve() == (ROOT / "tasks").resolve():
            sys.exit("--refresh writes pairs without the process rules: regenerate tasks/ with scripts/robopaint_strict/mk_tasks.py "
                     "(or give --out-root another directory)")
        dirs = [Path(d.rstrip("/")) for d in a.refresh] or sorted(p for p in Path(a.out_root).iterdir() if p.is_dir() and re.fullmatch(
            rf"robopaint-({'|'.join(FAMILIES)})-[a-z0-9-]+-i\d\d(-privileged)?", p.name))
        return refresh(dirs, a)
    if a.resolve:
        if not a.plans:
            ap.error("--resolve needs --plans")
        return resolve(Path(a.resolve.rstrip("/")), a.plans, a)
    if not a.family:
        ap.error("--family is required (or --refresh)")
    if a.entry != "vertical" and a.family != "kaishu":
        ap.error("--entry: kaishu only (the other families' reference planners have no such option)")
    fam_cfg = FAMILIES[a.family]
    tpl = a.template or fam_cfg["template"]
    a._src_u = committed_pair(Path(a.template_root), pair_base(Path(a.template_root), a.template_family or a.family, tpl))[0]
    h = {"kaishu": kaishu_target, "lettering": lettering_target, "acrylic": painting_target, "oil": painting_target,
         "xingshu": xingshu_target, "caoshu": caoshu_target}[a.family](a)
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
        shutil.copy(Path(a.solution_dir) / f if a.solution_dir else a._src_u / "solution" / f, work / f)
    if "plans" in h:                                                 # lettering: the exemplar's writing routes (one per contact)
        (work / "plans.json").write_text(json.dumps(h["plans"], indent=1))
    if "program" in h:
        (work / "program.json").write_text(json.dumps(h["program"], indent=1))
    (work / "spec.json").write_text(json.dumps(h["spec"], ensure_ascii=False, indent=1))
    if getattr(a, "plans", None):
        pl = json.load(open(a.plans))
        need = h["max_strokes"] if a.family in ("xingshu", "caoshu") else h["n"]   # xingshu, caoshu: one plan per brush contact (the limit)
        if a.family not in SCRIPT_FAMILIES or len(pl["plans"]) != need:
            sys.exit(f"--plans: {len(pl['plans'])} plans for {need} contacts (kaishu / xingshu / caoshu only)")
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
    elif a.family == "kaishu":    # the Arphic notices (APL 2a) date the change: rcb_brush_score.py writes the family's first day,
        import datetime, io       # a new pair gets the day it is made, in the graders' truth and target.png's PNG comment (not hashed)
        import numpy as np
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
        first, day = "2026-09-28", datetime.date.today().isoformat()
        d = json.loads(truth["instance.json"])
        d["truth"]["notice"] = d["truth"]["notice"].replace(first, day)
        truth["instance.json"] = (json.dumps(d, indent=1, ensure_ascii=False)).encode()
        im = Image.open(full / "target.png"); arr = np.asarray(im.convert("RGB")).copy()
        meta = PngInfo(); meta.add_text("Comment", im.info["Comment"].replace(first, day)); buf = io.BytesIO()
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
    difficulty = a.difficulty if a.family not in SCRIPT_FAMILIES + ("lettering",) else None
    dst_u, dst_l = assemble(a.family, slug, tpl, Path(a.template_root), Path(a.out_root), frozen_u, frozen_l, stats, difficulty, keep_programs=True,
                            tpl_family=a.template_family, solution_dir=Path(a.solution_dir) if a.solution_dir else None)
    summary = {"privileged": str(dst_u), "standard": str(dst_l), "family": fam, "n_strokes": h["n"], **({"max_strokes": h["max_strokes"]} if "max_strokes" in h else {}),
               "instance_sha": json.loads((full / "instance.json").read_text())["instance_sha"],
               "oracle": {k: r[k] for k in keys if k in r} | {"n_actions": int(len(acts))},
               "selftest": {k: st[k] for k in ("scorer_equals_graders", "agent_actions_equal_oracle")}}
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
