#!/usr/bin/env python3
"""The results pages, built from results/<bench>/ (README.md's table, runs.csv) and the trials under jobs/:
  python3 scripts/results/build.py [--refresh] [--cameras DIR]        # -> jobs/results/humanoidbench/index.html
  python3 scripts/results/build.py --add jobs/<job> [--note "..."]    # after a run: its runs.csv line, then the pages

index.html          every task: run or not, the result, money, tokens, time, per column of the README's table (a model
                    in a mode, "GPT-6 Luna · limited"); limited next to full; charts across the runs
tasks/<task>.html   the task's analysis, this round's runs (each column's main run: its latest standard-config run)
                    by mode and each in detail, and every run of each column by the version of the task text it had
runs/<job>.html     one page per run, shorter, plus the full trajectory and Harbor's records
Runs are runs.csv's rows. A run whose job is still under jobs/ is measured by collect.py, once: the result is cached
in <trial>/report/summary.json (--refresh measures again), and <trial>/report/notes.md is its analysis, written
from digest.py's one-page view of the trial as NOTES_GUIDE.md says.
Modules: common (paths, standard configs, labels, formatting), data (README, runs.csv, summaries), calls (tool calls),
attempts (what each robot command changed, for collect.py),
charts (SVG), widgets (small HTML pieces, Markdown), analysis (the hand-written analysis), pages (the pages); site.css
and site.js are copied next to the pages.
  python3 scripts/results/build.py --bundle DIR [--session JOB ...]   # a small copy to publish: see below
  --cameras DIR   the t=0 images `gen_tasks.py measure-limited --images DIR` wrote, copied in for the task pages
  --no-video      a trial measured now gets its episodes replayed and scored but no videos (a later build without it
                  renders them)
  --bundle DIR    the overview and the task pages only, in DIR, small enough to publish as one artifact (tens of MB):
                  no run pages, no per-call tables or galleries, and of the media only each main run's graded video
                  (limited: the graded episode; full: the replay) -- plus the whole-session video of each --session JOB
The analysis on the overview and at the top of each task page is results/<bench>/analysis/ (analysis.py).
Everything a page shows is under jobs/results/humanoidbench/ (the trials' videos and images are hard-linked into
media/), so `python -m http.server` there serves it all. Not in git.
"""
from __future__ import annotations

import argparse
import os
import shutil

from common import HERE, OUT, SITE
from data import add_run, check_readme, derive, load_runs, load_tasks
from pages import overview, run_page, task_page


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true", help="measure every trial again (collect.py), not only new ones")
    ap.add_argument("--cameras", help="a `gen_tasks.py measure-limited --images` directory: <task>/t0_<camera>.png")
    ap.add_argument("--add", metavar="JOB", help="first append JOB's trial(s) to runs.csv, measured (then build as usual)")
    ap.add_argument("--note", default="", help="with --add: the note column (one line, English)")
    ap.add_argument("--no-video", action="store_true", help="trials measured now: no episode or session videos yet")
    ap.add_argument("--bundle", metavar="DIR", help="write the small copy to publish (overview and task pages) to DIR instead")
    ap.add_argument("--session", metavar="JOB", action="append", default=[], help="with --bundle: also take this run's whole-session video")
    args = ap.parse_args()
    tasks, cols = load_tasks()
    if args.add:
        add_run(args.add, args.note, tasks, video=not args.no_video)
    tasks_by = {t["task"]: t for t in tasks}
    runs = load_runs(args.refresh, video=not args.no_video)
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
    if args.bundle:
        SITE.update(out=os.path.abspath(args.bundle), bundle=True, media=bundle_media(tasks, args.session))
    out = SITE["out"]
    for d in ("tasks", "media") if args.bundle else ("tasks", "runs", "media"):   # runs.csv as it is now: nothing left from runs no longer in it
        shutil.rmtree(f"{out}/{d}", ignore_errors=True)
        os.makedirs(f"{out}/{d}")
    os.makedirs(f"{out}/assets", exist_ok=True)
    for f in ("site.css", "site.js"):
        shutil.copyfile(os.path.join(HERE, f), os.path.join(out, "assets", f))
    if args.cameras:
        for t in tasks:
            for c in ("left_eye_camera", "right_eye_camera", "room_camera"):
                src = os.path.join(args.cameras, t["task"], f"t0_{c}.png")
                if os.path.exists(src):
                    os.makedirs(os.path.join(out, "assets", "cameras", t["task"]), exist_ok=True)
                    shutil.copyfile(src, os.path.join(out, "assets", "cameras", t["task"], f"{c}.png"))
    elif args.bundle and os.path.isdir(f"{OUT}/assets/cameras"):   # the ones the last full build copied in
        shutil.rmtree(f"{out}/assets/cameras", ignore_errors=True)
        shutil.copytree(f"{OUT}/assets/cameras", f"{out}/assets/cameras")
    open(f"{out}/index.html", "w").write(overview(tasks, cols, runs))
    for t in tasks:
        open(f"{out}/tasks/{t['task']}.html", "w").write(task_page(t, cols))
    for r in runs:
        if r["s"] and r["task"] in tasks_by and not args.bundle:
            open(f"{out}/runs/{r['id']}.html", "w").write(run_page(r, tasks_by[r["task"]]))
    check_readme(tasks, cols)
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(out) for f in fs)
    print(f"{out}/index.html: {len(tasks)} tasks, {0 if args.bundle else sum(1 for r in runs if r['s'])} runs with pages, "
          f"{len(runs)} in runs.csv; {size / 1e6:.1f} MB")


def bundle_media(tasks: list, sessions: list) -> set:
    """The trial files a bundle takes: each main run's graded video and its poster, and the whole-session video of the
    runs named (by job) in `sessions`."""
    keep = set()
    for t in tasks:
        for r in t["main"].values():
            s, base = r["s"], os.path.join(r["s"]["trial_dir"], "report")
            if s["mode"] == "full":
                if s.get("video"):
                    keep.add(os.path.join(s["trial_dir"], s["video"]))
                continue
            e = next((e for e in s["episodes"] if e["ep"] == s["result"]["graded_ep"] and e.get("video")), None)
            keep |= {os.path.join(base, e["video"]), os.path.join(base, e.get("poster") or "")} if e else set()
            if os.path.basename(s["job"]) in {os.path.basename(j.rstrip("/")) for j in sessions}:
                keep |= {os.path.join(base, "session.mp4"), os.path.join(base, "session.jpg")}
    return keep


if __name__ == "__main__":
    main()
