"""The data behind the pages: the README's task table, runs.csv, each trial's measured summary (collect.py)."""
from __future__ import annotations

import argparse
import csv
import decimal
import glob
import json
import os
import re
import sys
import datetime as dt

try:
    import tomllib
except ModuleNotFoundError:   # Python < 3.11
    import tomli as tomllib

import collect

from common import HB, MODELS, REPO, RESULTS, STANDARD


def load_tasks():
    """The README's table gives the order and the columns, one per model and mode ("GPT-6 Luna · limited");
    subset.toml, facts.json and the task dirs the rest."""
    readme = open(f"{RESULTS}/README.md").read()
    sec = readme.split("## Results", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in sec.splitlines() if line.startswith("|")]
    head = [c.strip() for c in rows[0].strip().strip("|").split("|")]
    cols = [tuple(h.rsplit(" · ", 1)) for h in head[6:]]
    legend = dict(re.findall(r"(C\d+) ([^·.\n]+?)(?= ·|\.)", readme.split("Classes", 1)[1].split("\n\n", 1)[0]))
    subset = tomllib.load(open(f"{HB}/subset.toml", "rb"))
    by_fam = {t["family"]: t for t in subset["task"]}
    facts = json.load(open(f"{HB}/facts.json"))
    tasks = []
    for line in rows[2:]:
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        fam = c[1]; t = by_fam.get(fam, {}); f = facts.get(fam, {})
        d = sorted(glob.glob(f"{REPO}/tasks/humanoidbench-*-{fam.replace('_', '-')}-i00-limited"))
        d = d[0] if d else None
        instr = open(f"{d}/instruction.md").read() if d else ""
        m = re.search(r"\*\*Task:\*\*\s*(.+?)\n\n", instr, re.S)
        compose = open(f"{d}/environment/docker-compose.yaml").read() if d else ""
        pose = re.search(r'RCB_ROOM_CAMERA_POSE:\s*"([^"]*)"', compose)
        tasks.append({"n": int(c[0]), "task": fam, "robot": c[2], "cls": c[3], "readme": dict(zip(head, c)),
                      "cls_name": legend.get(c[3], "fixture" if c[3] == "fixture" else ""), "cls_long": (t.get("capability_class") or "").split("·", 1)[-1].strip(), "one_liner": t.get("one_liner", ""),
                      "bar": f.get("success_bar"), "nop": f.get("nop_return"), "nop_steps": f.get("nop_steps"),
                      "max_steps": f.get("max_steps"), "hold": f.get("hold_return"), "dir": d, "full_dir": d[:-len("-limited")] if d else None,
                      "statement": " ".join(m.group(1).split()) if m else "", "pose": pose.group(1) if pose else "",
                      "camera_note": (t.get("limited") or {}).get("camera_note", ""), "runs": [], "main": {}})
    return tasks, cols


def load_runs(refresh: bool) -> list[dict]:
    runs = []
    for i, r in enumerate(csv.DictReader(open(f"{RESULTS}/runs.csv"))):
        r = dict(r)
        r["i"] = i
        r["standard"] = r["mode"] in STANDARD and all(r[k] == v for k, v in STANDARD[r["mode"]].items())
        r["model_name"] = MODELS.get(r["model"], r["model"].split("/")[-1])
        r["col"] = (r["model_name"], r["mode"])
        job = r["job"].split(" ")[0]
        path = os.path.join(REPO, job) if job.startswith("jobs/") else None
        trials = collect.trials_under([path]) if path and os.path.isdir(path) else []
        if len(trials) > 1:
            print(f"note: {job} has {len(trials)} trials; the page shows the first")
        r["s"] = summary(trials[0], refresh) if trials else None
        r["id"] = os.path.basename(job) if trials else None
        runs.append(r)
    return runs


def summary(trial: str, refresh: bool) -> dict:
    s = collect.jload(f"{trial}/report/summary.json")
    if refresh or not s or s.get("version") != collect.VERSION:
        print(f"measuring {os.path.relpath(trial, REPO)}")
        s = collect.collect(trial, argparse.Namespace(no_replay=False, no_billing=False, no_harbor=False))
    return s


def notes_of(s) -> tuple[str | None, str | None, list]:
    """report/notes.md: (the one-line verdict, the rest, the phase table)."""
    p = f"{s['trial_dir']}/report/notes.md"
    if not os.path.exists(p):
        return None, None, []
    txt, phases = open(p).read(), []
    m = re.search(r"<!--\s*phases\s*\n(.*?)-->", txt, re.S)
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"\s*(?:ep)?(\d+)(?:\s*[-–]\s*(?:ep)?(\d+))?\s+(.+?)\s*$", line)
            if mm:
                phases.append((int(mm.group(1)), int(mm.group(2) or mm.group(1)), mm.group(3)))
        txt = (txt[:m.start()] + txt[m.end():]).strip()
    first, _, rest = txt.partition("\n\n")
    return (first, rest, phases) if first.startswith("**一句话**") else (None, txt, phases)


def derive(r: dict, task: dict | None) -> dict:
    """The numbers a run is shown with: measured where the trial is still here, runs.csv's where it is not."""
    f = lambda k, cast=float: cast(r[k]) if r.get(k) not in (None, "") else None
    d = {"score": f("score"), "bar": f("bar"), "pass": r["result"] == "pass", "cost": f("cost_usd"), "agent_min": f("agent_min"),
         "resets_used": f("resets_used", int), "resets": f("resets", int), "budget_min": f("budget_min"), "requests": f("requests", int)}
    s = r["s"]
    if s:
        rq = s["requests"]; res = s["result"]
        d.update(score=res["return"] if res["return"] is not None else d["score"], bar=res["bar"] or d["bar"],
                 cost=s["billed"]["usd"] if s["billed"]["found"] else s["billed"]["harbor_usd"], agent_min=(s["a1"] - s["a0"]) / 60,
                 resets_used=res["resets"], requests=len(rq), budget_min=(s["budget_s"] or 0) / 60 or d["budget_min"],
                 tok_in=sum(x["in"] for x in rq), tok_cached=sum(x["cached"] for x in rq), tok_out=sum(x["out"] for x in rq),
                 tok_reason=sum(x["reason"] for x in rq), gen_s=sum(x["gen_s"] or 0 for x in rq),
                 tool_s=sum(max(0, c["t1"] - c["t0"]) for c in s["calls"]), agent_s=s["a1"] - s["a0"], views=len(s["views"]),
                 episodes=len(s["episodes"]))
        d["tokens"] = d["tok_in"] + d["tok_out"]
        for k, v in (("score", f("score")), ("cost_usd", f("cost_usd"))):
            if v is not None and (d["score" if k == "score" else "cost"] or 0) and abs(v - d["score" if k == "score" else "cost"]) > (0.02 if k == "score" else 0.002):
                print(f"warning: runs.csv row {r['i'] + 2} ({r['task']}, {r['model_name']}) has {k} {v}, the trial says "
                      f"{d['score' if k == 'score' else 'cost']:.4f}")
    nop = task["nop"] if task else None
    d["prog"] = ((d["score"] - nop) / (d["bar"] - nop)) if None not in (d["score"], nop, d["bar"]) and d["bar"] != nop else None
    return d


def add_run(job: str, note: str, tasks: list) -> None:
    """Append one runs.csv line per trial of `job`, every column but the note measured from the trial."""
    rows = list(csv.DictReader(open(f"{RESULTS}/runs.csv")))
    rel_job = "jobs/" + os.path.basename(os.path.abspath(job.rstrip("/")))
    if any(r["job"].split(" ")[0] == rel_job for r in rows):
        sys.exit(f"{rel_job} is already in runs.csv")
    by_dir = {os.path.basename(d or ""): t["task"] for t in tasks for d in (t["dir"], t["full_dir"])}
    new = []
    for trial in collect.trials_under([job]):
        s = summary(trial, False); res, sp = s["result"], s["spec"]
        cost = s["billed"]["usd"] if s["billed"]["found"] else s["billed"]["harbor_usd"]
        limited = s["mode"] == "limited"
        obs = ("head+joints" + ("+imu" if sp["imu"] else "") + ("+room" if "room_camera" in sp["cameras"] else "")) if limited else "state"
        new.append({"date": dt.datetime.fromtimestamp(s["a0"]).strftime("%Y-%m-%d"), "task": by_dir.get(s["task_name"], s["task_name"]),
                    "mode": s["mode"], "agent": "codex" if "codex" in s["agent"].lower() else s["agent"],
                    "model": s["model"].split("openrouter/", 1)[-1], "effort": s["effort"] or "", "budget_min": f"{(s['budget_s'] or 0) / 60:g}",
                    "resets": sp["reset_budget"] if limited else "", "obs": obs,
                    "result": "pass" if res["success"] else "fail", "score": f"{res['return']:.2f}" if res["return"] is not None else "",
                    "bar": f"{res['bar']:g}" if res["bar"] is not None else "", "resets_used": res["resets"] if limited else "",
                    "agent_min": f"{(s['a1'] - s['a0']) / 60:.1f}", "cost_usd": f"{cost:.4g}" if cost is not None else "",
                    "requests": len(s["requests"]), "job": rel_job, "note": note})
    with open(f"{RESULTS}/runs.csv", "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(csv.DictReader(open(f"{RESULTS}/runs.csv")).fieldnames), lineterminator="\n")
        for r in new:
            w.writerow(r); print("runs.csv +", ",".join(str(v) for v in r.values()))


def check_readme(tasks: list, cols: list) -> None:
    """The README's cells are written by hand from runs.csv: say where one no longer matches."""
    half_up = lambda v, q: str(decimal.Decimal(str(v)).quantize(decimal.Decimal(q), decimal.ROUND_HALF_UP))
    for t in tasks:
        for col in cols:
            mine = [r for r in t["runs"] if r["standard"] and r["col"] == col]
            cell = t["readme"].get(" · ".join(col), "")
            if not mine:
                if cell:
                    print(f"README: {t['task']} / {' · '.join(col)} says {cell!r}, runs.csv has no standard-config run")
                continue
            if len(mine) == 1:
                d = mine[0]["d"]
                want = f"{'✅' if d['pass'] else '❌'} {half_up(d['score'], '0.1') if d['score'] is not None else '—'} · ${half_up(d['cost'] or 0, '0.01')}"
                if cell != want:
                    print(f"README: {t['task']} / {' · '.join(col)} says {cell!r}, runs.csv gives {want!r}")
