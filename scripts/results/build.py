#!/usr/bin/env python3
"""The results pages, built from results/<bench>/ (README.md's table, runs.csv) and the trials under jobs/:
  python3 scripts/results/build.py [--refresh] [--cameras DIR]        # -> jobs/results/humanoidbench/index.html
  python3 scripts/results/build.py --add jobs/<job> [--note "..."]    # after a run: its runs.csv line, then the pages

index.html          every task: run or not, the result, money, tokens, time, per column of the README's table (a model
                    in a mode, "GPT-6 Luna · limited"); limited next to full; charts across the runs
tasks/<task>.html   each column's main run (its latest standard-config run) in detail, with its analysis, and every
                    other run of the task
runs/<job>.html     one page per run, shorter, plus the full trajectory and Harbor's records
Runs are runs.csv's rows. A run whose job is still under jobs/ is measured by collect.py, once: the result is cached
in <trial>/report/summary.json (--refresh measures again), and <trial>/report/notes.md is its analysis, written
from digest.py's one-page view of the trial as NOTES_GUIDE.md says.
Modules: common (paths, standard configs, labels, formatting), data (README, runs.csv, summaries), calls (tool calls),
charts (SVG), pages (HTML); site.css and site.js are copied next to the pages.
  --cameras DIR   the t=0 images `gen_tasks.py measure-limited --images DIR` wrote, copied in for the task pages
Everything a page shows is under jobs/results/humanoidbench/ (the trials' videos and images are hard-linked into
media/), so `python -m http.server` there serves it all. Not in git.
"""
from __future__ import annotations

import argparse
import os
import shutil

from common import HERE, OUT
from data import add_run, check_readme, derive, load_runs, load_tasks
from pages import overview, run_page, task_page


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true", help="measure every trial again (collect.py), not only new ones")
    ap.add_argument("--cameras", help="a `gen_tasks.py measure-limited --images` directory: <task>/t0_<camera>.png")
    ap.add_argument("--add", metavar="JOB", help="first append JOB's trial(s) to runs.csv, measured (then build as usual)")
    ap.add_argument("--note", default="", help="with --add: the note column (one line, English)")
    args = ap.parse_args()
    tasks, cols = load_tasks()
    if args.add:
        add_run(args.add, args.note, tasks)
    tasks_by = {t["task"]: t for t in tasks}
    runs = load_runs(args.refresh)
    for r in runs:
        t = tasks_by.get(r["task"])
        r["d"] = derive(r, t)
        if t:
            t["runs"].append(r)
    for t in tasks:   # a column's main run on a task: its latest standard-config run that is still under jobs/
        for col in cols:
            std = [r for r in t["runs"] if r["standard"] and r["col"] == col and r["s"]]
            if std:
                t["main"][col] = std[-1]
    for d in ("tasks", "runs", "media"):   # the site shows runs.csv as it is now: nothing left from runs no longer in it
        shutil.rmtree(f"{OUT}/{d}", ignore_errors=True)
        os.makedirs(f"{OUT}/{d}")
    os.makedirs(f"{OUT}/assets", exist_ok=True)
    for f in ("site.css", "site.js"):
        shutil.copyfile(os.path.join(HERE, f), os.path.join(OUT, "assets", f))
    if args.cameras:
        for t in tasks:
            for c in ("left_eye_camera", "right_eye_camera", "room_camera"):
                src = os.path.join(args.cameras, t["task"], f"t0_{c}.png")
                if os.path.exists(src):
                    os.makedirs(os.path.join(OUT, "assets", "cameras", t["task"]), exist_ok=True)
                    shutil.copyfile(src, os.path.join(OUT, "assets", "cameras", t["task"], f"{c}.png"))
    open(f"{OUT}/index.html", "w").write(overview(tasks, cols, runs))
    for t in tasks:
        open(f"{OUT}/tasks/{t['task']}.html", "w").write(task_page(t, cols))
    for r in runs:
        if r["s"] and r["task"] in tasks_by:
            open(f"{OUT}/runs/{r['id']}.html", "w").write(run_page(r, tasks_by[r["task"]]))
    check_readme(tasks, cols)
    print(f"{OUT}/index.html: {len(tasks)} tasks, {sum(1 for r in runs if r['s'])} runs with pages, {len(runs)} in runs.csv")


if __name__ == "__main__":
    main()
