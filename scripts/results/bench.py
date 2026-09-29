"""A benchmark, as the results pages see it.

Everything that differs between benchmarks is a `Bench` subclass in benches/<name>.py; every other module here is
written against the active one, `B`, and never names a benchmark. The defaults fit a benchmark that judges an episode
by success alone (KinDER); one that scores a return against a pass mark sets `scored` (HumanoidBench). A new benchmark
needs its tasks under tasks/, results/<name>/README.md (the `## Results` table: `#`, `task`, its own columns, then one
column per model and mode), results/<name>/runs.csv, a subclass, and scripts/<name>/replay.py, run in the sim image:
a limited trial's episodes replayed from the service's log, `<trial> <task's sim dir> <out> [--no-render]` ->
<out>/episodes.json and episodes/epN.mp4, .jpg. `use(name)` picks the active benchmark; build.py, collect.py,
digest.py and session_video.py call it before reading anything.
"""
from __future__ import annotations

import glob
import importlib
import json
import os
import re

from common import CAMS, REPO, SITE, WHY


class Bench:
    name = ""               # results/<name>/, jobs/results/<name>/, scripts/<name>/, and the tasks' [metadata] simulator
    title = ""              # the site's name
    short = ""              # what the job names of its standard runs start with
    scored = False          # True: an episode has a return and a run passes at a bar; False: it succeeds or not
    standard: dict = {}     # per mode, the runs.csv columns a standard-config run matches (limited obs: common.SENSORS)
    cameras: dict = {}      # the cameras a limited run serves, in the pages' order: name -> (label, colour in site.css:
                            # left, right or room)
    camera_files = ()       # (camera, regex on an image's file name): which camera an image the model viewed came from
    leak_words = ""         # regex alternatives: this benchmark's words that should not appear in what the agent ran
    episode_fields = ("exact", "video", "poster")   # what summary.json keeps from each replayed episode
    video_note = ""         # how the episode videos are rendered, for the video panel
    video_every = 1         # the replay renders a frame every this many control steps (session_video.py)
    texts: dict = {}        # the task text's versions: job-name suffix -> (name, date, commit)
    retired: set = set()    # versions whose runs were taken out of runs.csv
    why: dict = {}          # how a run ended, where this benchmark words it differently from common.WHY
    diag_what = "验证端的诊断"   # what verifier/diagnostics.json holds
    info_example = ""       # the task whose values illustrate the overview's "what limited gives" table

    @property
    def results(self) -> str:
        return os.path.join(REPO, "results", self.name)

    @property
    def out(self) -> str:
        return os.path.join(REPO, "jobs", "results", self.name)

    @property
    def analysis(self) -> str:
        return os.path.join(self.results, "analysis")

    @property
    def scripts(self) -> str:
        return os.path.join(REPO, "scripts", self.name)

    def cam_label(self, c: str) -> str:
        return self.cameras[c][0] if c in self.cameras else CAMS.get(c, c)

    def cam_color(self, c: str) -> str:
        return self.cameras[c][1] if c in self.cameras else c   # made, unknown: their own colours

    def why_text(self, k: str) -> str:
        return self.why.get(k) or WHY.get(k, k)

    # ------------------------------------------------------------------ tasks
    def task_dir(self, family: str, limited: bool) -> str | None:
        """The task directory of `family` (the README's task name) in one mode."""
        found = sorted(glob.glob(f"{REPO}/tasks/{self.name}-{family.replace('_', '-')}-i00{'-limited' if limited else ''}"))
        return found[0] if found else None

    def task_info(self, family: str, row: dict, readme: str) -> dict:
        """What the pages know of a task beyond its name, statement and directories: its README row's own columns
        (`row`, by header) and whatever this benchmark keeps elsewhere. Keys the generic pages read: max_steps and
        fixture and screening (neither counted) when present; a scored benchmark's bar and nop (the all-zero action's return), always,
        and nop_steps (how long the all-zero action lasts)."""
        return {}

    def task_label(self, t: dict, full: bool = True) -> str:
        """HTML under a task's name in the tables (`full`: the task table's, else the shorter one of the result matrix)."""
        return ""

    def hero(self, t: dict) -> tuple[list[str], str]:
        """A task page's head: its chips, and notes (HTML) under the statement."""
        return [f'<span class="chip">{t["max_steps"]} 步 / episode</span>'] if t.get("max_steps") else [], ""

    def intro(self, tasks: list) -> str:
        """The overview's opening paragraph (HTML)."""
        return ""

    def limited_info(self, cam) -> tuple[list[tuple], str]:
        """The overview's "what limited gives" table, as (rows, footer HTML): each row (what, what exactly, its real-robot
        counterpart, an example from `info_example`); `cam(name)` is that task's t=0 image of a camera, as HTML."""
        return [], ""

    def obs(self, spec: dict) -> str:
        """A limited run's observations as runs.csv writes them, from the spec its sim service served."""
        return "+".join(["cams"] + [k for k in ("proprio", "imu", "depth") if spec.get(k)]
                        + (["room"] if "room_camera" in spec.get("cameras", []) else []))

    # ------------------------------------------------------------------ episodes
    def down(self, e: dict) -> bool | None:
        """Whether the robot was down when episode `e` ended (None: this benchmark does not say)."""
        return None

    def progress_text(self, p: dict | None) -> str:
        """How far a multi-stage task got, in words; "" where a benchmark has no stages."""
        return ""

    def ep_lines(self, e: dict) -> tuple[str, str]:
        """An episode's tooltip, below its title: the line of numbers, and one more (may be "")."""
        return f"{e['steps']} 步", ""

    def episode_columns(self) -> list[tuple]:
        """The episode table's columns beyond the generic ones: (header HTML, e -> cell HTML)."""
        return []

    def episode_note(self) -> str:
        """HTML under the episode table."""
        return ""

    def episode_rows(self, task: dict, eps: list) -> list[tuple]:
        """Rows of the per-episode chart beyond return and steps: (title, height, lo, hi, e -> value)."""
        return []

    def digest_facts(self, t: dict) -> str:
        """digest.md's facts about the task, after the result."""
        nop = f"the all-zero action scores {t['nop']} ({t.get('nop_steps')} steps); " if self.scored else ""
        return nop + (f"episode limit {t['max_steps']} steps" if t.get("max_steps") else "")

    def digest_episodes(self, s: dict, at) -> list[str]:
        """digest.md's episode table (limited mode), as lines; `at(t)` formats a time as minutes into the session."""
        L = ["## Episodes (from the sim service's log and the verifier-side replay, which the agent never saw)", "",
             "| ep | start min | steps | ended | images viewed |", "|---|---|---|---|---|"]
        return L + [f"| {e['ep']} | {at(e['t0'] or s['a0'])} | {e['steps']} | {e['end'] or 'reset by the agent, or running'} | "
                    f"{e.get('views')} |" for e in s["episodes"]]

    def family(self, task_name: str) -> str:
        """A task directory's name as the README's task name."""
        return re.sub(rf"^{self.name}-|-i\d+(-limited)?$", "", task_name)


class _Active:
    """The benchmark in use: `B.x` is the chosen Bench's `x`."""
    bench: Bench | None = None

    def __getattr__(self, k):
        if _Active.bench is None:
            raise RuntimeError("no benchmark chosen: call bench.use(name) first")
        return getattr(_Active.bench, k)


B = _Active()


def use(name: str) -> Bench:
    """Make benches/<name>.py's BENCH the active benchmark (its pages go to jobs/results/<name>/)."""
    try:
        _Active.bench = importlib.import_module(f"benches.{name}").BENCH
    except ModuleNotFoundError as e:
        if e.name != f"benches.{name}":
            raise
        raise SystemExit(f"no results adapter for {name!r}: scripts/results/benches/{name}.py (see bench.py)")
    SITE.update(out=_Active.bench.out, bundle=False, media=set())
    return _Active.bench


def names() -> list[str]:
    """Every benchmark with an adapter and a results directory."""
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benches")
    have = [f[:-3] for f in os.listdir(here) if f.endswith(".py") and not f.startswith("_")]
    return sorted(n for n in have if os.path.exists(os.path.join(REPO, "results", n, "README.md")))


def of_trial(trial: str) -> str:
    """The benchmark a Harbor trial belongs to: its task's [metadata] simulator."""
    cfg = (json.load(open(os.path.join(trial, "result.json"))).get("config") or {})
    task = (cfg.get("task") or {}).get("path") or ""
    toml = os.path.join(task if os.path.isabs(task) else os.path.join(REPO, task), "task.toml")
    m = re.search(r'^simulator *= *"([^"]+)"', open(toml).read(), re.M)
    if not m:
        raise SystemExit(f"{toml} names no simulator")
    return m.group(1)

