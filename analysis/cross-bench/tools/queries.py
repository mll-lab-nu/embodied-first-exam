"""Named queries over data/*.csv. Findings and pages cite these by name; numbers are never typed into prose."""
from __future__ import annotations
import csv, glob, json, os, re, statistics as S
from collections import Counter, defaultdict
import common
from common import AGENTS, HERE, LUNA, RAW, read_csv

MAIN_MODES = ("privileged", "standard")


_SKEL = re.compile(r"agent [\d.]+ of ([\d.]+) min")


def stated_cutoff(key: str) -> str:
    """The time limit the trial's own instruction stated, as the digest header records it ("agent 10.2 of 90.0 min");
    the catalog timeout can be stale (RoboWits: catalog 60, instruction and runs 90)."""
    p = os.path.join(RAW, key, "skeleton.md")
    if not os.path.exists(p):
        return ""
    m = _SKEL.search(open(p, encoding="utf-8", errors="replace").read(800))
    return str(round(float(m.group(1)))) if m else ""


# Task sets (user 10-18 night, meta/DESIGN.md → Data layer: sets). core = the tasks listed in embodied-first-exam
# docs/core_set.toml (copied to tools/data/core_set.toml; since 10-19 (#387/#388) one entry per task, `task` + its
# default mode, and every mode dir of a listed task counts: `--privileged` / `--standard` / `--standard-realtime` run the
# same tasks in another mode); all = every task. RoboSafeBench is now Embodied Safety Exam (ese, standard mode only):
# the success counts (load_perf) follow core_set.toml, its 50 core tasks included; the monitor's old rsb rows are left
# out of both sets. The sampled analyses (trial index, reviews, labels) leave rsb / ese out of both. XB_SET picks the
# set (default core); build.py --set / --both passes it explicitly. The core list and the Atlas below are inputs, not
# written by index.py, so they are read from tools/data and HERE/data whatever XB_DATA says (data/easy_bases.txt, the
# old easy set, is kept but not read; tools/data/core_set_1018.toml is the old per-dir list).
SETS = ("core", "all")
SET = os.environ.get("XB_SET", "core")
ACTIVE = SET              # the set being rendered (build.build sets it per build): text naming GPT-6 Luna is for the all set only
LEFT_OUT = ("rsb", "ese")
SUPERSEDED = ("rsb",)     # monitor benches replaced by a renamed one (rsb -> ese, 10-19): left out of the success counts
REMOVED_MODES = {("ese", "privileged")}   # task dirs the benchmark removed (#388: Embodied Safety Exam has no privileged mode)
CORE_TOML = os.path.join(HERE, "tools", "data", "core_set.toml")
CORE = frozenset(re.findall(r'^task = "([^"]+)"', open(CORE_TOML, encoding="utf-8").read(), re.M))
# The six agents every headline comparison is made on (user 10-18: one common subset, the core tasks graded for all six;
# GPT-6 Luna, the two Sol and Qwen stay out of headline charts). with=main stands for this list.
MAIN_AGENTS = ("GPT-6 Astra", "Gemini 4 Argon", "Opus 5.5", "GLM-5.3 Flash", "DeepSeek V4.1 Flash", "Gemini 3.8 Flash")


# Runs a set leaves out of every query (trials, cells, reviews and labels through them, perf rows): the core set's
# analysis has no GPT-6 Luna at all (user 10-18); the all set keeps it.
DROP_RUNS = {"core": (LUNA,), "all": ()}


def _toml_blocks(path: str) -> list[dict]:
    return [dict(re.findall(r'^(\w+) = "([^"]*)"', b, re.M)) for b in open(path, encoding="utf-8").read().split("[[task]]")[1:]]


# core dirs whose toml `luna` verdict is success (owner picks; the 10-19 toml has no `luna` field, so this is empty)
CORE_LUNA_PASSED = frozenset(b["task"] for b in _toml_blocks(CORE_TOML) if b.get("luna") == "success")


def task_base(task: str, mode: str) -> str:
    """A task dir without its mode suffix (-privileged / -standard / -standard-realtime)."""
    return task[:-len(mode) - 1] if mode and task.endswith("-" + mode) else task


CORE_ALL = "core 全部评测项，没结果的算失败"   # how the core set's headline batch is named (load_perf pads the main agents)


def batch_words(text: str) -> str:
    """Caption text naming the common subset of the main agents -> the core set's words when the core set is rendered."""
    if ACTIVE != "core":
        return text
    for a in ("六家都评过分的同一批", "六家主要 agent 都评过分的", "六家都评过分的"):
        text = text.replace(a, CORE_ALL)
    return text


def set_agents(which: str | None = None) -> list[str]:
    """ORDER without the agents set `which` leaves out (DROP_RUNS)."""
    gone = {AGENTS[r] for r in DROP_RUNS[_which(which)]}
    return [a for a in ORDER if a not in gone]


def agent_list(v: str) -> list[str]:
    """A with= / agent list: "main" = MAIN_AGENTS, else comma-separated names."""
    return list(MAIN_AGENTS) if v == "main" else v.split(",")
# EFE Task Atlas (data/atlas_tasks.json: base -> body, tt = task types, cap = capabilities); names and definitions in
# meta/codebook.json trial_zh (tasktype / body / cap). Not in the Atlas: unclassified; an Atlas task without any
# capability: cap none.
ATLAS = {a["base"]: a for a in json.load(open(os.path.join(HERE, "data", "atlas_tasks.json")))}
UNCLASSIFIED = "unclassified"
MULTI = ("tasktype", "cap")                                   # list fields: a trial counts in each of its values


RENAMED = ("roboolympics-fun", "roboolympics-match")      # benches whose task dirs now carry the bench name


def dir_name(row: dict) -> str:
    """Our index's task name -> the task dir name core_set.toml and the monitor use. They differ only for RoboOlympics:
    the dirs are now roboolympics-fun-… / roboolympics-match-…, the index (and the Atlas, findings, cases) still says
    roboolympics-… (checked 10-18 against the monitor's trial ids: the same rule for all 154 renamed dirs)."""
    t, b = row.get("task", ""), row.get("bench", "")
    return b + t[len("roboolympics"):] if b in RENAMED and t.startswith("roboolympics-") and not t.startswith(b + "-") else t


def index_name(task: str, bench: str) -> str:
    """The reverse of dir_name: a monitor / core_set.toml task dir -> our index's task name."""
    return "roboolympics-" + task[len(bench) + 1:] if bench in RENAMED and task.startswith(bench + "-") else task


def in_set(row: dict, which: str) -> bool:
    """A trial, cell or task (needs bench, mode and task = base + mode suffix) belongs to set `which`; core = its dir
    name (dir_name) without the mode suffix is listed in core_set.toml."""
    return row.get("bench") not in LEFT_OUT and (which == "all" or task_base(dir_name(row), row.get("mode", "")) in CORE)


def atlas(base: str) -> dict:
    """The Atlas fields of a task base: tasktype (list), body, cap (list)."""
    a = ATLAS.get(base)
    if not a:
        return {"tasktype": [UNCLASSIFIED], "body": UNCLASSIFIED, "cap": [UNCLASSIFIED]}
    return {"tasktype": list(a.get("tt") or []) or [UNCLASSIFIED], "body": a.get("body") or UNCLASSIFIED,
            "cap": list(a.get("cap") or []) or ["none"]}


def _which(which):
    which = which or SET
    if which not in SETS:
        raise SystemExit(f"XB_SET / --set must be one of {SETS}, not {which!r}")
    return which


def load_all(which: str | None = None):
    """Every finished trial of one task set (default XB_SET) with features, the Atlas fields and the refined validity
    (see load)."""
    which = _which(which)
    feats = {f["key"]: f for f in read_csv("features.csv")}
    out = []
    for t in read_csv("trials.csv"):
        if not in_set(t, which) or t["run"] in DROP_RUNS[which]:
            continue
        t.update({k: v for k, v in feats.get(t["key"], {}).items() if k not in t})
        t.update(atlas(t["base"]))
        if t["validity"] == "valid" and t["success"] == "0" and (str(t.get("live_success")) in ("1", "1.0", "True")
                                                                 or str(t.get("all_success")) in ("1", "1.0", "True")):
            t["validity"], t["validity_reason"] = "suspect", "live_success_but_failed"
        if t["validity"] == "valid" and t["success"] == "0" and t.get("provider_block") == "1":
            t["validity"], t["validity_reason"] = "infra", "provider_filter"
        t["cutoff_min"] = t.get("budget_min") or stated_cutoff(t["key"]) or t["timeout_min"]
        out.append(t)
    return out


def load(which: str | None = None):
    """Valid trials, cells and tasks of one task set (default XB_SET, see SETS); trials carry their features and Atlas
    fields. Refinements over the monitor record (all need the fetched files): a trial
    whose live episode (or every grader replay) passed but whose final verdict failed is `suspect` (grader-side); a
    failed trial whose last message is Gemini's filter notice is `infra`; the cutoff is the one the trial's own
    instruction stated (cutoffs changed over time; the monitor shows today's). Cells: index.py splits finished cells
    into done-valid / done-rerun / done-excluded (kept in `cell_status`); pages count all three as `done`."""
    which = _which(which)
    cells = [c for c in read_csv("cells.csv") if in_set(c, which) and c["run"] not in DROP_RUNS[which]]
    for c in cells:
        c["cell_status"] = c["status"]
        if c["status"].startswith("done-"):
            c["status"] = "done"
    tasks = [t for t in read_csv("tasks.csv") if in_set(t, which)]
    return [t for t in load_all(which) if t["validity"] == "valid"], cells, tasks


PERF = os.path.join(common.DATA, "perf.json")


def perf_time() -> str:
    """When data/perf.json was fetched ("" without a snapshot)."""
    return json.load(open(PERF)).get("time", "") if os.path.exists(PERF) else ""


def load_perf(which: str | None = None, all_trials=()) -> list[dict]:
    """Success rates come from here (user 10-18 night): the monitor's global results in data/perf.json (tools/perf.py),
    one row per agent x task dir, the latest counted run of each. The monitor's rule (its `magg`): a row counts when
    sc == 1 and is graded when s is success or failed; core = the task (dir without its mode suffix) is listed in
    core_set.toml, Embodied Safety Exam included (user 10-18: success counts follow the toml as it is; the sampled
    analyses still leave it out; the monitor's `e` flag no longer matches the 10-19 toml, so it is not read); the old
    rsb rows (SUPERSEDED) are left out; task names in the index's spelling (index_name). Each graded row of set
    `which` -> a trial-like dict (agent, run, bench, task, base, mode, success "1"/"0", the Atlas fields, key) joined
    with our index's trial of the same key when there is one (so trial filters such as exception= still apply) and
    `blocked` = our index flags it as a Gemini content-filter stop (provider_block / infra provider_filter; the monitor
    counts those as failures, and so do the rates unless filter=drop). In the core set every main agent (MAIN_AGENTS) gets
    a row for every core task dir: a dir with no graded row (infra_failed, not run yet) counts as a failure (`padded`), so
    each main agent's denominators are the core counts, privileged 372 / standard 432 / realtime 59 (user 10-19)."""
    which = _which(which)
    if not os.path.exists(PERF):
        raise SystemExit(f"{PERF} is missing: run BEL_TOKEN=… python3 tools/perf.py")
    by_key = {t["key"]: t for t in all_trials}
    out, rows = [], json.load(open(PERF))["rows"]
    gone = lambda r: r["b"] in SUPERSEDED or (r["b"], r["m"]) in REMOVED_MODES
    for r in rows:
        agent = AGENTS.get(r["u"])
        if (not agent or r["u"] in DROP_RUNS[which] or not r.get("sc") or r["s"] not in ("success", "failed")
                or gone(r) or (which == "core" and task_base(r["t"], r["m"]) not in CORE)):
            continue
        mode, key, task = r["m"], f'{r["u"]}__{str(r.get("id") or "").rsplit("/", 1)[-1]}', index_name(r["t"], r["b"])
        base = task[:-len(mode) - 1] if task.endswith("-" + mode) else task
        t = by_key.get(key, {})
        out.append({**t, "agent": agent, "run": r["u"], "bench": r["b"], "task": task, "base": base, "mode": mode, **atlas(base),
                    "success": "1" if r["s"] == "success" else "0", "key": key, "in_index": bool(t),
                    "blocked": r["s"] == "failed" and (t.get("validity_reason") == "provider_filter" or t.get("provider_block") == "1")})
    if which == "core":                                   # every main agent on every core dir (user 10-19: 372 / 432 / 59)
        dirs = {r["t"]: r for r in rows if not gone(r) and task_base(r["t"], r["m"]) in CORE}
        have = {(x["run"], dir_name(x)) for x in out}
        for run, agent in AGENTS.items():
            if agent not in MAIN_AGENTS:
                continue
            for d, r in dirs.items():
                if (run, d) not in have:                  # no graded row (infra_failed, not run yet): a failure
                    task, mode = index_name(d, r["b"]), r["m"]
                    base = task[:-len(mode) - 1] if task.endswith("-" + mode) else task
                    out.append({"agent": agent, "run": run, "bench": r["b"], "task": task, "base": base, "mode": mode, **atlas(base),
                                "success": "0", "key": "", "in_index": False, "blocked": False, "padded": True})
    return out


def perf_open(rows, which: str | None = None) -> list[dict]:
    """Perf rows on task dirs GPT-6 Luna did not pass (the 'Luna 没过的评测项' scope; Luna's own rows there too). The core
    set has no Luna rows (DROP_RUNS) and follows the toml as is (user 10-18: 根据 core toml 来), so every core dir
    counts, the owner picks Luna passed included (CORE_LUNA_PASSED is kept for reference only)."""
    if _which(which) == "core":
        return list(rows)
    passed = {r["task"] for r in rows if r["run"] == LUNA and r["success"] == "1"}
    return [r for r in rows if r["task"] not in passed]


def perf_pool(ctx, kv: dict) -> list[dict]:
    """The perf rows a rate query reads: scope=open (default) or all, filter=drop leaves out the content-filter stops."""
    rows = ctx.perf_open if kv.get("scope", "open") == "open" else ctx.perf
    return [r for r in rows if not r["blocked"]] if kv.get("filter") == "drop" else rows


def rate(rows) -> tuple[int, int]:
    return sum(int(r["success"]) for r in rows), len(rows)


def coverage(cells) -> dict:
    """agent -> Counter(status)."""
    out = defaultdict(Counter)
    for c in cells:
        out[c["agent"]][c["status"]] += 1
    return out


def by(trials, *keys) -> dict:
    g = defaultdict(list)
    for t in trials:
        g[tuple(t[k] for k in keys)].append(t)
    return g


def open_cells(trials, cells):
    """Trials on cells every non-Luna agent was meant to run (Luna did not pass them)."""
    skipped = {c["task"] for c in cells if c["status"] == "skipped"}
    return [t for t in trials if t["task"] not in skipped]


def common_subset(trials, agents, modes=MAIN_MODES):
    """Trials on tasks where every agent in `agents` has a valid finished trial (per mode)."""
    have = defaultdict(set)
    for t in trials:
        have[(t["task"], t["mode"])].add(t["agent"])
    keep = {k for k, v in have.items() if set(agents) <= v and k[1] in modes}
    return [t for t in trials if (t["task"], t["mode"]) in keep and t["agent"] in agents]


def mode_pairs(trials, a="privileged", b="standard"):
    """agent -> Counter of (pass_a, pass_b) over task bases run in both modes."""
    idx = {(t["agent"], t["base"], t["mode"]): int(t["success"]) for t in trials}
    out = defaultdict(Counter)
    for (agent, base, mode), s in idx.items():
        if mode == a and (agent, base, b) in idx:
            out[agent][(s, idx[(agent, base, b)])] += 1
    return out


def ending(t) -> str:
    """success / timeout / token-budget / fell / episode-over / self-stopped / other-fail. The harness's timeout exception and the
    minutes used decide; the episode's own end_reason says "timeout" even when the agent stopped early."""
    if t["success"] == "1":
        return "success"
    if t["exception"] == "TokenBudgetExceeded":
        return "token-budget"
    if t["exception"] == "AgentTimeoutError":
        return "timeout"
    if "fell" in t["end_reason"]:
        return "fell"
    if t["mode"] != "privileged" and t["end_reason"] not in ("", "failed", "timeout", "error", "done", "goal_held", "success"):
        return "episode-over"                     # the environment ended the only/last episode (limit, contact, drop, horizon)
    used, cut = _f(t["agent_min"]), _f(t.get("cutoff_min") or t["timeout_min"])
    if used is not None and cut and used < 0.9 * cut:
        return "self-stopped"
    return "timeout" if used is not None and cut and used >= 0.9 * cut else "other-fail"


def time_used(trials) -> dict:
    """agent -> median fraction of the cutoff used, split by success/failure."""
    out = {}
    for agent, rows in by(trials, "agent").items():
        fr = defaultdict(list)
        for t in rows:
            try:
                fr[t["success"]].append(min(float(t["agent_min"]) / float(t["cutoff_min"]), 1.0))
            except (ValueError, ZeroDivisionError):
                pass
        out[agent[0]] = {k: round(S.median(v), 2) for k, v in fr.items() if v}
    return out


def annotations(kind: str) -> dict:
    """key -> label JSON from annot/<kind>/ (approach: how the robot was driven; integrity: boundary crossings)."""
    import glob, json, os
    from common import HERE
    out = {}
    for p in glob.glob(os.path.join(HERE, "annot", kind, "*.json")):
        try:
            out[os.path.basename(p)[:-5]] = json.load(open(p))
        except ValueError:
            pass
    return out


C30_REASONS = ("coverage-30", "coverage-30-topup")


def stratum(t) -> tuple:
    return t["agent"], t["bench"], t["mode"], "success" if t["success"] == "1" else "failure"


def sample_frame(cells, all_trials) -> tuple[set, Counter]:
    """The random sample (meta/sample30.json): the current trial key of every cell selected in ledger.csv (reason
    coverage-30 / coverage-30-topup), and the number of done-valid cells per stratum (agent x bench x mode x outcome)."""
    cell_of = {r["key"]: (r["task"], r["run"]) for r in read_csv("superseded.csv")}
    cell_of.update({c["trial"]: (c["task"], c["run"]) for c in cells if c["trial"]})
    current = {(c["task"], c["run"]): c["trial"] for c in cells if c["trial"]}
    chosen = {cell_of[r["key"]] for r in csv.DictReader(open(os.path.join(HERE, "ledger.csv")))
              if r["reason"] in C30_REASONS and r["key"] in cell_of}
    by_key = {t["key"]: t for t in all_trials}
    frame = Counter(stratum(by_key[c["trial"]]) for c in cells if c.get("cell_status", c["status"]) == "done-valid" and c["trial"] in by_key)
    return {current[c] for c in chosen if c in current}, frame


def sampled(ctx, rows, sample=True) -> list[dict]:
    """The one filter for shares: tags each row `in_sample` (its trial is the current trial of a selected cell) and
    `weight` (done-valid cells in its stratum / sampled rows of this list in it) and returns the sampled rows;
    sample=False returns every row, tagged (cases, examples, deep-read packets)."""
    n = Counter(stratum(r) for r in rows if r["key"] in ctx.sample)
    for r in rows:
        r["in_sample"] = r["key"] in ctx.sample
        r["weight"] = (ctx.frame.get(stratum(r)) or n[stratum(r)]) / n[stratum(r)] if r["in_sample"] else 0.0
    return [r for r in rows if r["in_sample"]] if sample else rows


def tally(rows, values) -> Counter:
    """value -> count over rows, values(r) giving a row's values. Each row counts 1; with XB_WEIGHTS=1 it counts its
    weight, scaled so the rows still add up to len(rows): shares are weighted, n stays the plain count."""
    tot = sum(r["weight"] for r in rows) if common.WEIGHTS else 0
    c = Counter()
    for r in rows:
        w = r["weight"] * len(rows) / tot if tot else 1
        for v in values(r):
            c[v] += w
    return c


def count(rows, hit) -> float:
    """Rows where hit(r) is true (weighted with XB_WEIGHTS=1, see tally)."""
    return tally(rows, lambda r: (1,) if hit(r) else ())[1]


def share_text(k, n, fmt=None) -> str:
    return pct(k, n) if fmt == "pct" else f"{round(k)}/{n}"


class Context:
    """What metrics and figures may read: valid trials (`trials`, `open`), every finished trial (`all`), the monitor's
    graded rows (`perf`, `perf_open`: every success rate reads these, see load_perf), cells, tasks, current reviews, the approach / integrity labels and the random sample (`sample` keys, `frame` = done-valid cells
    per stratum) of one task set (`set`, see SETS: the rows given must come from load(set))."""
    def __init__(self, trials, cells, tasks, reviews, all_trials=None, which=None):
        self.trials, self.cells, self.tasks, self.reviews = trials, cells, tasks, reviews
        self.set = _which(which)
        self.open = open_cells(trials, cells)
        self.all = all_trials if all_trials is not None else trials
        self.perf = load_perf(self.set, self.all)                  # success rates: the monitor's global results
        self.perf_open = perf_open(self.perf, self.set)
        self.sample, self.frame = sample_frame(cells, self.all)
        self.approach, self.integrity, self.remedy = annotations("approach"), annotations("integrity"), annotations("remedy")
        self.grasp, self.reasoning = annotations("grasp"), annotations("reasoning")
        self.reasoning_when = annotations("reasoning_when")        # when-1: before / after / low for level-both failures
        self.progress = annotations("progress")
        self.progress2 = annotations("progress2")                  # progress-2 relabel: no_return + end of progress-1 records


def pct(s: int, n: int) -> str:
    return f"{100 * s / n:.0f}%" if n else "–"


def _agent_order() -> list[str]:
    """The one agent order for every chart row, table column, nav list and chip: meta/site.json `agent_order`, strongest
    first; an agent missing there follows in registry order."""
    names = json.load(open(os.path.join(HERE, "meta/site.json"))).get("agent_order", [])
    return names + [a for a in AGENTS.values() if a not in names]


ORDER = _agent_order()


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def med(vals):
    v = [x for x in (_f(x) for x in vals) if x is not None]
    return S.median(v) if v else None


def cell_html(s: int, n: int) -> str:
    """success/n with a small bar; the same markup as the site's .rate."""
    if not n:
        return '<span class="meta">–</span>'
    return f'<div class="rate"><span>{s}/{n}</span><span class="mini"><i style="width:{100 * s / n:.0f}%"></i></span></div>'


def table(head: list[str], rows: list[list[str]], num_from: int = 1) -> str:
    num = ' class="num"'
    th = "".join(f"<th{num if i >= num_from else ''}>{h}</th>" for i, h in enumerate(head))
    tr = "".join("<tr>" + "".join(f"<td{num if i >= num_from and not str(c).startswith('<div') else ''}>{c}</td>"
                                  for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="scroll"><table class="t"><tr>{th}</tr>{tr}</table></div>'


def agents_present(trials, min_n=30):
    have = Counter(t["agent"] for t in trials)
    return [a for a in ORDER if have[a] >= min_n]


def fig_rescue(ctx) -> str:
    """Success on the cells Luna did not pass, per agent and mode (perf rows)."""
    rows = []
    for a in agents_present(ctx.perf_open):
        if a == "GPT-6 Luna":
            continue                                  # these are exactly the cells Luna failed
        mine = [t for t in ctx.perf_open if t["agent"] == a]
        rows.append([a] + [cell_html(*rate([t for t in mine if t["mode"] == m])) for m in ("privileged", "standard", "standard-realtime")])
    return table(["Agent（Luna 没过的格子）", "privileged", "standard", "realtime"], rows)


def fig_common(ctx, agents=None) -> str:
    """Same tasks for every agent listed: the fair head-to-head (perf rows)."""
    agents = agents or [a for a in agents_present(ctx.perf_open, 300) if a != "GPT-6 Luna"]
    cs = common_subset(ctx.perf_open, agents)
    rows = []
    for a in agents:
        mine = [t for t in cs if t["agent"] == a]
        rows.append([a] + [cell_html(*rate([t for t in mine if t["mode"] == m])) for m in MAIN_MODES])
    return table(["Agent（同一批任务）", "privileged", "standard"], rows)


def fig_endings(ctx) -> str:
    keys = [("success", "成功"), ("timeout", "超时"), ("self-stopped", "自己停下"), ("fell", "摔倒"), ("token-budget", "token 上限"), ("other-fail", "其他失败")]
    rows = []
    for a in agents_present(ctx.open):
        mine = [t for t in ctx.open if t["agent"] == a]
        c = Counter(ending(t) for t in mine)
        rows.append([a, str(len(mine))] + [pct(c[k], len(mine)) for k, _ in keys])
    return table(["Agent", "trial"] + [l for _, l in keys], rows)


def fig_time(ctx) -> str:
    """How each agent spends the clock on failures: minutes used (all failures) and what reviewers saw (reviewed failures)."""
    revs = defaultdict(list)
    for r in review_rows(ctx):
        if r["outcome"] == "failure":
            revs[r["agent"]].append(r)
    rows = []
    for a in agents_present(ctx.open):
        fails = [t for t in ctx.open if t["agent"] == a and t["success"] == "0"]
        used = [min(_f(t["agent_min"]) / _f(t["cutoff_min"]), 1) for t in fails if _f(t["agent_min"]) and _f(t["cutoff_min"])]
        rv = revs.get(a, [])
        share = lambda pred: pct(count(rv, pred), len(rv)) if len(rv) >= 5 else "–"
        rows.append([a, str(len(fails)), f"{100 * S.median(used):.0f}%" if used else "–", pct(sum(u < 0.5 for u in used), len(used)),
                     str(len(rv)), share(lambda r: r["clock_aware"] == "True"), share(lambda r: r["planned_budget"] == "True"),
                     share(lambda r: "misjudged-time" in [r["primary"]] + r["secondary"] or "early-stop" in [r["primary"]] + r["secondary"])])
    return table(["Agent", "失败 trial", "用时中位数", "用了不到一半", "分析过的失败", "看过时钟", "按预算规划", "误判时间或提前停"], rows)


def fig_process(ctx) -> str:
    """Working style from the trajectory: medians per trial."""
    rows = []
    for a in agents_present(ctx.open):
        mine = [t for t in ctx.open if t["agent"] == a and t.get("has_traj") == "1"]
        if not mine:
            continue
        m = lambda k: med(t.get(k) for t in mine)
        rows.append([a, str(len(mine))] + [f"{m(k):.0f}" if m(k) is not None else "–" for k in ("calls", "py_runs", "n_write", "images_seen", "messages")])
    return table(["Agent", "trial", "工具调用", "跑脚本", "写文件", "看图", "发言"], rows)


def fig_code(ctx) -> str:
    """What the final code contains (regex flags over artifacts/app/output/*.py; share of trials with code)."""
    keys = [("model_ik", "IK/雅可比"), ("perception", "感知/相机"), ("search", "搜索/优化"), ("learning", "学习"), ("feedback", "反馈循环")]
    rows = []
    for a in agents_present(ctx.open):
        mine = [t for t in ctx.open if t["agent"] == a and (_f(t.get("code_lines")) or 0) > 20]
        if len(mine) < 10:
            continue
        rows.append([a, str(len(mine))] + [pct(sum(t.get(f"code_{k}") == "1" for t in mine), len(mine)) for k, _ in keys])
    return table(["Agent", "有代码的 trial"] + [l for _, l in keys], rows)


def fig_modes(ctx) -> str:
    rows = []
    for a, c in sorted(mode_pairs(ctx.perf_open).items(), key=lambda kv: ORDER.index(kv[0])):
        n = sum(c.values())
        if n < 15:
            continue
        priv, std = c[(1, 0)] + c[(1, 1)], c[(0, 1)] + c[(1, 1)]
        rows.append([a, str(n), str(c[(1, 1)]), str(c[(1, 0)]), str(c[(0, 1)]), str(c[(0, 0)]), f"{100 * (priv - std) / n:+.0f} pt"])
    return table(["Agent", "两种模式都跑的任务", "都成功", "只有 privileged 成功", "只有 standard 成功", "都失败", "差距"], rows)


def fig_bench_heat(ctx, mode="privileged") -> str:
    """Benchmark x agent, cells Luna did not pass (Luna: all cells; perf rows)."""
    agents = [a for a in agents_present(ctx.perf, 100)]
    benches = sorted({t["bench"] for t in ctx.perf})
    rows = []
    for b in benches:
        r = [b]
        for a in agents:
            pool = ctx.perf if a == "GPT-6 Luna" else ctx.perf_open
            r.append(cell_html(*rate([t for t in pool if t["agent"] == a and t["bench"] == b and t["mode"] == mode])))
        rows.append(r)
    return table(["Benchmark"] + agents, rows)


CATEGORY = {b: c["id"] for c in __import__("json").load(open(__import__("os").path.join(
    __import__("common").HERE, "meta/site.json")))["categories"] for b in c["benches"]}


def _match(t: dict, kv: dict) -> bool:
    for k, v in kv.items():
        if k in ("scope", "field", "value", "fmt", "flag", "filter", "show"):
            continue
        if k == "agent" and v == "main":               # agent=main: the six MAIN_AGENTS
            v = ",".join(MAIN_AGENTS)
        got = CATEGORY.get(t["bench"]) if k == "category" else t.get(k)
        if v == "+":                                   # any non-zero count (features such as int_grep_answers=+)
            if got in (None, "", "0", 0):
                return False
        elif v.startswith("!"):                        # !a,b = none of these values (crit=!none,time-out; a list: none of them in it)
            if (set(got) if isinstance(got, list) else {str(got)}) & set(v[1:].split(",")):
                return False
        elif isinstance(got, list):                    # list fields (paradigm, tech, any_fix, …) match by membership
            if not set(got) & set(v.split(",")):
                return False
        elif str(got) not in v.split(","):
            return False
    return True


def _rows_cache(fn):
    """Row builders (review_rows, ann_rows, …) compute their rows once per context: the first call builds every row
    (sample=False, tagged by sampled), later calls return a new list of the same rows, the sampled ones for sample=True.
    The rows are shared, so callers copy a row before changing it ({**r, …}), as every figure does."""
    def rows(ctx, sample=True):
        cache = ctx.__dict__.setdefault("_rows", {})
        if fn.__name__ not in cache:
            cache[fn.__name__] = fn(ctx, sample=False)
        return [r for r in cache[fn.__name__] if r["in_sample"]] if sample else list(cache[fn.__name__])
    rows.__doc__, rows.__name__ = fn.__doc__, fn.__name__
    return rows


_STYLE2 = None


def _style2(key: str, st: dict) -> dict:
    """on_failure / plan_vs_act in two classes (user review 10-18): style-2 labels from the analysis text (Opus, all core
    sampled trials; /data/pingyue/cross-bench/relabel/style/out) where present, else the review's own label; mixed is
    folded into pivot (换过方法) and act (先动手) — the middle class was where labellers disagreed."""
    global _STYLE2
    if _STYLE2 is None:
        _STYLE2 = {}
        for p in glob.glob("/data/pingyue/cross-bench/relabel/style/out/*.jsonl"):
            for line in open(p):
                if line.strip():
                    d = json.loads(line)
                    _STYLE2[d["key"]] = d
    s = _STYLE2.get(key) or st
    fold = {"on_failure": {"mixed": "pivot"}, "plan_vs_act": {"mixed": "act"}}
    return {f: fold[f].get(s.get(f, ""), s.get(f, "")) for f in fold}


@_rows_cache
def review_rows(ctx, sample=True) -> list[dict]:
    """Current reviews joined with their trial (deep preferred over skim for the same trial); the random sample only
    unless sample=False (see sampled). Besides the review's fields, each row has `reviewer` (opus when the review has none)
    and the approach labels loop / way / deliverable / offline_model (annot/approach), so filters can use them."""
    by_key = {t["key"]: t for t in ctx.trials}
    best = {}
    for (key, depth), r in ctx.reviews.items():
        if key in by_key and (key not in best or depth == "deep"):
            best[key] = r
    out = []
    for key, r in best.items():
        f, tm, st, ap = r.get("failure") or {}, r.get("time") or {}, r.get("style") or {}, ctx.approach.get(key) or {}
        out.append({**by_key[key], "outcome": r["outcome"], "paradigm": r["approach"].get("paradigm", []),
                    "reviewer": r.get("reviewer") or "opus",       # reviews without the field were written by Opus
                    "loop": ap.get("loop", ""), "way": way(ap), "deliverable": ap.get("deliverable", ""), "offline_model": ap.get("offline_model", ""),
                    "stage": f.get("stage", ""), "primary": f.get("primary", ""), "secondary": f.get("secondary") or [],
                    "claim": r.get("claim", ""), "clock_aware": str(tm.get("clock_aware")), "planned_budget": str(tm.get("planned_budget")),
                    **_style2(key, st), "verification": st.get("verification", ""),
                    "exploration": st.get("exploration", ""), "image_use": st.get("image_use", ""), "depth": r["depth"],
                    **_phases(f, tm, by_key[key])})
    return sampled(ctx, out, sample)


def _clock(stamp):
    """'mm:ss' or 'h:mm:ss' (review time stamps) -> minutes."""
    try:
        p = [float(x) for x in str(stamp).strip("[] ").split(":")]
    except ValueError:
        return None
    return p[0] * 60 + p[1] + p[2] / 60 if len(p) == 3 else p[0] + p[1] / 60 if len(p) == 2 else None


def _phases(f: dict, tm: dict, t: dict) -> dict:
    """Where in the trial the review's key moments fall (share of the minutes the agent used): *_frac in 0..1, and
    buckets dec_phase / nr_phase (q1–q4 = quarters) and window (share of the trial between decisive error and no return:
    short < 15%, mid 15–50%, long > 50%)."""
    used = _f(t.get("agent_min"))
    frac = lambda x: min(1.0, _clock(x) / used) if used and _clock(x) is not None else None
    dec, nr, fs = frac((f.get("decisive") or {}).get("t")), frac(f.get("no_return_t")), frac(f.get("first_symptom_t"))
    q = lambda x: "" if x is None else f"q{min(4, int(x * 4) + 1)}"
    w = None if dec is None or nr is None else nr - dec
    return {"dec_frac": dec, "nr_frac": nr, "fs_frac": fs, "dec_phase": q(dec), "nr_phase": q(nr),
            "window": "" if w is None else "short" if w < 0.15 else "mid" if w <= 0.5 else "long"}


REMEDY_FAMILY = {"grasp-check": "grasp", "hand-geometry": "grasp", "grasp-choice": "grasp", "closed-loop": "loop", "safety-guard": "loop",
                 "path-check": "loop", "perception-check": "percept", "verify-real": "verify", "debug-own-code": "verify", "read-spec": "verify",
                 "time-plan": "budget", "reset-plan": "budget", "pivot": "strategy", "feasibility-recheck": "strategy",
                 "harness-process": "harness", "harness-context": "harness", "task-side": "task", "skill-gap": "skill"}


@_rows_cache
def rem_rows(ctx, sample=True) -> list[dict]:
    """Remedy labels of failed trials joined with their review row (valid trials only; sample: see sampled)."""
    by_key = {r["key"]: r for r in review_rows(ctx, sample=False)}          # review fields too (primary, secondary, stage, …)
    by_key = {k: {**r, "any_cause": [c for c in [r["primary"]] + r["secondary"] if c]} for k, r in by_key.items()}
    return sampled(ctx, [{**by_key[k], "fix": a.get("fix", ""), "family": REMEDY_FAMILY.get(a.get("fix", ""), "other"), "who": a.get("who", ""),
                          "would_pass": a.get("would_pass", ""), "also": a.get("also") or [],
                          "any_fix": [a.get("fix", "")] + list(a.get("also") or [])} for k, a in ctx.remedy.items() if k in by_key], sample)


def q_fix(ctx, **kv) -> str:
    """{{q:fix|field=family|value=grasp|would_pass=likely,maybe|agent=…}} -> "k/n" among remedy labels (fields: fix, family,
    who, would_pass, any_fix = main or extra fix)."""
    rows = [r for r in rem_rows(ctx) if _match(r, kv)]
    f, v = kv.get("field"), kv.get("value", "").split(",")
    hit = lambda r: bool(set(r[f]) & set(v)) if isinstance(r.get(f), list) else str(r.get(f)) in v
    k = count(rows, hit) if f else len(rows)
    return share_text(k, len(rows), kv.get("fmt"))


@_rows_cache
def grasp_rows(ctx, sample=True) -> list[dict]:
    """Grasp-failure subtype labels (grasp-1) joined with their trial (valid trials only; sample: see sampled)."""
    by_key = {t["key"]: t for t in ctx.trials}
    return sampled(ctx, [{**by_key[k], "subtype": a.get("subtype", ""), "any_subtype": [x for x in (a.get("subtype"), a.get("also")) if x]}
                         for k, a in ctx.grasp.items() if k in by_key], sample)


def q_grasp(ctx, **kv) -> str:
    """{{q:grasp|field=subtype|value=slip-lift|agent=…}} -> "k/n" among grasp-failure labels (fields subtype, any_subtype)."""
    rows = [r for r in grasp_rows(ctx) if _match(r, kv)]
    f, v = kv.get("field"), kv.get("value", "").split(",")
    hit = lambda r: bool(set(r[f]) & set(v)) if isinstance(r.get(f), list) else str(r.get(f)) in v
    k = count(rows, hit) if f else len(rows)
    return share_text(k, len(rows))


CODEBOOK_CAUSE = json.load(open(os.path.join(HERE, "meta/codebook.json")))["cause"]


WHEN = ("before", "after", "low")


def level2(level: str, when: str) -> str:
    """Effective thinking-error level: high, before (事前想错), after (事后没挽回), low (纯低层, both→low included),
    external; a `both` label without a when-1 label stays `both` (not yet split)."""
    return when if level == "both" and when in WHEN else level


@_rows_cache
def reason_rows(ctx, sample=True) -> list[dict]:
    """Thinking-error labels (reasoning-1) of failed trials joined with their review row (valid trials only); `pgroup` is
    the codebook group of the review's primary cause (control, time, perception, …); `when` = the when-1 label of a
    level-both failure ("" when not labelled) and `level2` = the effective level (see level2); sample: see sampled."""
    rev = {r["key"]: r for r in review_rows(ctx, sample=False)}
    group = {c: g for g, cs in CODEBOOK_CAUSE.items() for c in cs}
    rg = {k: g for g, v in json.load(open(os.path.join(HERE, "meta/codebook.json")))["reason_zh"]["group"].items() for k in v[2]}
    when = lambda k, a: (ctx.reasoning_when.get(k) or {}).get("when", "") if a.get("level") == "both" else ""
    return sampled(ctx, [{**rev[k], "level": a.get("level", ""), "kinds": list(a.get("kinds") or []), "kind": (a.get("kinds") or [""])[0],
                          "groups": list(dict.fromkeys(rg[x] for x in a.get("kinds") or [] if x in rg)), "pgroup": group.get(rev[k]["primary"], "other"),
                          "when": when(k, a), "level2": level2(a.get("level", ""), when(k, a))}
                         for k, a in ctx.reasoning.items() if k in rev], sample)


def q_reason(ctx, **kv) -> str:
    """{{q:reason|field=level|value=high,both|agent=…}} -> "k/n" among thinking-error labels (fields level, level2 =
    effective level high / before / after / both (not yet split) / low / external, when, kind = the first kind,
    kinds = any kind, groups = any of the five groups understand / method / plan / check / adapt)."""
    rows = [r for r in reason_rows(ctx) if _match(r, kv)]
    f, v = kv.get("field"), kv.get("value", "").split(",")
    hit = lambda r: bool(set(r[f]) & set(v)) if isinstance(r.get(f), list) else str(r.get(f)) in v
    k = count(rows, hit) if f else len(rows)
    return share_text(k, len(rows), kv.get("fmt"))


def q_med(ctx, **kv) -> str:
    """{{q:med|field=dec_frac|outcome=failure|mode=standard}} -> "p%（n）": median of a review fraction field."""
    rows = [r for r in review_rows(ctx) if _match(r, kv) and r.get(kv["field"]) is not None]
    return f"{100 * S.median(r[kv['field']] for r in rows):.0f}%（n={len(rows)}）" if rows else "–"


def shared(pool, agents: list[str]) -> set:
    """(task, mode) pairs on which every listed agent has a valid trial: the fair head-to-head set."""
    have = defaultdict(set)
    for t in pool:
        have[(t["task"], t["mode"])].add(t["agent"])
    return {k for k, v in have.items() if set(agents) <= v}


def q_rate(ctx, **kv) -> str:
    """{{q:rate|agent=…|mode=…|bench=…|category=…|tasktype=…|body=…|task=…|scope=open|filter=drop|fmt=pct}} -> "s/n（p%）"
    over the monitor's graded rows (load_perf; scope=open, default: task dirs Luna did not pass; scope=all: every one).
    with=A,B,… keeps only the task dirs graded for every listed agent (so rates are on the same tasks; with=main = the six
    MAIN_AGENTS, the headline subset); agent=main = those six pooled; filter=drop also
    leaves out the rows our index flags as Gemini content-filter stops (by default they count as failures, as on the
    monitor)."""
    pool = perf_pool(ctx, kv)
    if kv.get("with"):
        both = shared(perf_pool(ctx, {**kv, "scope": "all"}), agent_list(kv["with"]))
        pool = [t for t in pool if (t["task"], t["mode"]) in both]
    s, n = rate([t for t in pool if _match(t, {k: v for k, v in kv.items() if k != "with"})])
    return pct(s, n) if kv.get("fmt") == "pct" else f"{s}/{n}（{pct(s, n)}）"


TRIO = {"astra": "GPT-6 Astra", "argon": "Gemini 4 Argon", "opus": "Opus 5.5"}     # combo keys of q:overlap / fig:overlap
COMBOS = ("all3", "astra+argon", "astra+opus", "argon+opus", "astra", "argon", "opus", "none")   # UpSet row order
BENCH_NAME = {b: v["name"] for b, v in json.load(open(os.path.join(HERE, "meta/site.json")))["benches"].items()}


def combo_of(solved) -> str:
    """The exclusive combination of TRIO keys that solved a cell: all3, a pair (astra+opus), one (astra) or none."""
    keys = [k for k in TRIO if k in solved]
    return "all3" if len(keys) == 3 else "none" if not keys else "+".join(keys)


def overlap_cells(ctx, **kv) -> dict:
    """(task, mode) -> {"solved": TRIO keys that solved it, "row": one perf row} on the headline subset: task dirs
    graded for all six MAIN_AGENTS (with=main; scope=open by default, filter=drop as in q_rate); mode= and task filters
    (tasktype=, bench=, …) pick the cells."""
    both = shared(perf_pool(ctx, {**kv, "scope": "all"}), MAIN_AGENTS)
    keep = {k: v for k, v in kv.items() if k not in ("combo", "n", "with", "by", "agent", "min", "show")}
    out = {}
    for t in perf_pool(ctx, kv):
        if (t["task"], t["mode"]) in both and _match(t, keep):
            c = out.setdefault((t["task"], t["mode"]), {"solved": set(), "row": t})
            if t["success"] == "1" and t["agent"] in TRIO.values():
                c["solved"].add(next(k for k, a in TRIO.items() if a == t["agent"]))
    return out


def overlap_hit(cells: dict, combo: str) -> list:
    """The cells a combo counts: an exclusive combination (COMBOS), union (at least one of the three) or best (the
    single agent that solved the most, all its cells)."""
    if combo == "union":
        return [c for c, v in cells.items() if v["solved"]]
    if combo == "best":
        k = max(TRIO, key=lambda a: sum(a in v["solved"] for v in cells.values()))
        return [c for c, v in cells.items() if k in v["solved"]]
    if combo not in COMBOS:
        raise SystemExit(f"q:overlap combo must be one of {COMBOS + ('union', 'best')}, not {combo!r}")
    return [c for c, v in cells.items() if combo_of(v["solved"]) == combo]


def task_parts(row: dict) -> tuple[str, str]:
    """(benchmark name, task name) as a reader names them: the base without the bench prefix and instance suffix."""
    pre = "roboolympics" if row["bench"] in RENAMED else re.escape(row["bench"])        # index names: roboolympics-…
    base = re.sub(r"-i\d+$", "", re.sub(rf"^{pre}[-_]", "", row["base"]))
    return BENCH_NAME.get(row["bench"], row["bench"]), base.replace("_", " ").replace("-", " ")


def task_label(row: dict) -> str:
    """A task as a reader names it: benchmark name · task name (task_parts)."""
    return " · ".join(task_parts(row))


def q_overlap(ctx, **kv) -> str:
    """{{q:overlap|mode=…|combo=all3}} -> "k/n": n = cells of the headline subset (overlap_cells), k = those of the combo
    (all3, astra+argon, astra+opus, argon+opus, astra, argon, opus = only that one, none, union, best)."""
    cells = overlap_cells(ctx, **kv)
    return f"{len(overlap_hit(cells, kv.get('combo', 'all3')))}/{len(cells)}"


def q_overlap_tasks(ctx, **kv) -> str:
    """{{q:overlap_tasks|mode=…|combo=…|n=5}} -> up to n task names (task_label, one per base) of the combo's cells."""
    cells = overlap_cells(ctx, **kv)
    names = sorted(dict.fromkeys(task_label(cells[c]["row"]) for c in overlap_hit(cells, kv.get("combo", "all3"))))
    n = int(kv.get("n", 5))
    return "、".join(names[:n]) + ("等" if len(names) > n else "") if names else "–"


def run_cells(ctx, **kv) -> dict:
    """(task, mode) -> graded perf rows (load_perf, every task dir; filter=drop as in q_rate) of the six MAIN_AGENTS (or
    the agents of agent=), for the cells in the headline subset: graded for all of them (default), for every agent of
    with=, or for at least min= of them. Other filters (mode=…, category=…) pick the rows before the agents are counted."""
    agents = agent_list(kv.get("agent") or "main")
    cells = defaultdict(list)
    for t in perf_pool(ctx, {**kv, "scope": "all"}):
        if t["agent"] in agents and _match(t, {k: v for k, v in kv.items() if k not in ("min", "agent", "with")}):
            cells[(t["task"], t["mode"])].append(t)
    need = set(agent_list(kv["with"])) if kv.get("with") else None
    k = int(kv["min"]) if kv.get("min") else len(agents)
    return {c: ts for c, ts in cells.items() if (need <= {t["agent"] for t in ts} if need else len({t["agent"] for t in ts}) >= k)}


def unsolved(ts) -> bool:
    """No trial of this cell succeeded."""
    return all(t["success"] != "1" for t in ts)


def q_unsolved(ctx, **kv) -> str:
    """{{q:unsolved|mode=…|category=…}} -> "k/n": n = cells (task x mode) of the headline subset (graded for all six
    MAIN_AGENTS; min=k: for at least k of them; with= / agent= other lists, see run_cells); k = those where none of them
    succeeded."""
    run = run_cells(ctx, **kv).values()
    return share_text(sum(unsolved(ts) for ts in run), len(run), kv.get("fmt"))


def q_rev(ctx, **kv) -> str:
    """{{q:rev|agent=…|outcome=failure|field=primary|value=early-stop}} -> "k/n" among current reviews matching the filter;
    list fields (paradigm, secondary) match by membership; field=any_cause matches primary or secondary."""
    rows = [r for r in review_rows(ctx) if _match(r, kv)]
    f, v = kv.get("field"), kv.get("value", "")
    def hit(r):
        if f == "any_cause":
            return r["primary"] in v.split(",") or bool(set(r["secondary"]) & set(v.split(",")))
        x = r.get(f)
        return bool(set(x) & set(v.split(","))) if isinstance(x, list) else str(x) in v.split(",")
    k = count(rows, hit) if f else len(rows)
    return share_text(k, len(rows), kv.get("fmt"))


def way(a: dict) -> str:
    """The v17 approach of one approach label (meta/codebook.json approach_zh way_family; user 10-18): train (训练模型)
    when its techniques list rl, whatever its loop; otherwise its loop code (code-open / code-closed / search = 代码控制,
    agent-segment = 直接控制, mixed, none); "" when unlabelled. figs_way.way applies the same rule."""
    return "train" if "rl" in (a.get("tech") or []) else a.get("loop", "") or ""


@_rows_cache
def ann_rows(ctx, sample=True) -> list[dict]:
    """Approach labels joined with their trial (valid trials only; sample: see sampled); `way` = the v17 approach (way)."""
    by_key = {t["key"]: t for t in ctx.trials}
    out = []
    for key, a in ctx.approach.items():
        if key in by_key:
            out.append({**by_key[key], "loop": a.get("loop", ""), "way": way(a), "tech": a.get("tech") or [], "perception": a.get("perception") or [],
                        "offline_model": a.get("offline_model", ""), "deliverable": a.get("deliverable", ""),
                        "integrity": [e.get("kind") for e in a.get("integrity") or []], "outcome": "success" if by_key[key]["success"] == "1" else "failure"})
    return sampled(ctx, out, sample)


def q_ann(ctx, **kv) -> str:
    """{{q:ann|mode=standard|field=loop|value=agent-segment}} -> "k/n" among approach labels; list fields by membership."""
    rows = [r for r in ann_rows(ctx) if _match(r, kv)]
    f, v = kv.get("field"), kv.get("value", "").split(",")
    hit = lambda r: bool(set(r[f]) & set(v)) if isinstance(r.get(f), list) else str(r.get(f)) in v
    k = count(rows, hit) if f else len(rows)
    return share_text(k, len(rows), kv.get("fmt"))


def q_feat(ctx, **kv) -> str:
    """{{q:feat|flag=tech_ik|mode=privileged}} -> "k/n（p%）" of valid trials with a trajectory whose feature is non-zero
    (scope=open: cells Luna did not pass; scope=all, default: every valid trial; scope=finished: rule-flagged too)."""
    pool = {"open": ctx.open, "finished": ctx.all}.get(kv.get("scope", "all"), ctx.trials)
    rows = [t for t in pool if t.get("has_traj") == "1" and _match(t, {k: v for k, v in kv.items() if k != "flag"})]
    k = sum(t.get(kv["flag"]) not in (None, "", "0") for t in rows)
    return pct(k, len(rows)) if kv.get("fmt") == "pct" else f"{k}/{len(rows)}（{pct(k, len(rows))}）"


def q_int(ctx, **kv) -> str:
    """{{q:int|field=severity|value=violation|agent=…}} -> "k/n" among integrity labels (fields: severity, intent, effect,
    kind = any event kind, got = any event result)."""
    by_key = {t["key"]: t for t in ctx.all}
    rows = []
    for key, a in ctx.integrity.items():
        if key in by_key:
            ev = a.get("events") or []
            rows.append({**by_key[key], "severity": a.get("severity"), "intent": a.get("intent"), "effect": a.get("effect"),
                         "kind": [e.get("kind") for e in ev], "got": [e.get("got") for e in ev]})
    rows = [r for r in rows if _match(r, kv)]   # integrity labels are their own frame (trials a detector flagged), not the random sample
    f, v = kv.get("field"), kv.get("value", "").split(",")
    hit = lambda r: bool(set(r[f]) & set(v)) if isinstance(r.get(f), list) else str(r.get(f)) in v
    k = count(rows, hit) if f else len(rows)
    return share_text(k, len(rows))


def _share(x, cut):
    """Minutes -> share of the time limit (capped at 1), None when either is missing."""
    return min(1.0, x / cut) if x is not None and cut else None


def progress_record(a: dict, trial: dict) -> dict:
    """One progress-1 label in minutes and shares of the time limit: milestones [(minutes, level, what)], best and stuck
    level, the critical point (kind, minutes, share of the limit, noticed, after) and the limit left after it.
    RETIRED (10-18): the progress-1 `critical` fields crit / crit_t / crit_min / noticed / after / left / left_min /
    crit_what are kept only so the current text still builds; progress-2 replaces them (progress2_record): time-out,
    resets used and bad deliverable are end types now, not critical points."""
    cut, ms = _f(trial.get("cutoff_min")) or _f(trial.get("timeout_min")), []
    for m in a.get("milestones") or []:
        t, lv = _clock(m.get("t")), m.get("level")
        if t is not None and isinstance(lv, int):
            ms.append((t, lv, m.get("what", "")))
    ms.sort(key=lambda m: m[0])
    st, cr, v1 = a.get("stuck") or {}, a.get("critical") or {}, "critical" in a      # v1: has the retired critical point
    end = _clock(a.get("end_t")) or _f(trial.get("agent_min"))
    frm, ct = _clock(st.get("from_t")), _clock(cr.get("t")) if cr.get("kind") not in (None, "none") else None
    stay = max(0.0, end - frm) / end if end and frm is not None else None
    return {"milestones": ms, "best": a.get("best_level"), "best_t": _share(_clock(a.get("best_t")), cut),
            "stuck": st.get("level", a.get("best_level")), "stuck_share": min(1.0, stay) if stay is not None else None,
            "v1": v1, "crit": (cr.get("kind") or "none") if v1 else None, "crit_min": ct, "crit_t": _share(ct, cut), "noticed": cr.get("noticed", ""),
            "after": cr.get("after", ""), "left": None if ct is None or not cut else max(0.0, 1 - min(1.0, ct / cut)),
            "left_min": None if ct is None or not cut else max(0.0, cut - ct), "end_min": end, "cutoff": cut,
            "reach": {lv: _share(min((t for t, l, _ in ms if l >= lv), default=None), cut) for lv in range(1, 6)},
            "basis": a.get("basis", ""), "crit_what": cr.get("what", ""), "stuck_what": st.get("what", "")}


V2_FIELDS = ("no_return", "nr_t", "nr_min", "nr_left", "nr_noticed", "nr_after", "wasted", "end")
V1_FIELDS = ("crit", "crit_t", "crit_min", "noticed", "after", "left", "left_min")      # retired progress-1 critical point
_NOT_LABELLED = {"v2": False, **{f: None for f in V2_FIELDS}, "nr_what": "", "end_what": ""}


def _fp_ok(a: dict | None, trial: dict) -> bool:
    return bool(a) and not (a.get("fingerprint") and trial.get("fingerprint") and a["fingerprint"] != trial["fingerprint"])


def progress2_record(a: dict, p2: dict | None, trial: dict) -> dict:
    """The progress-2 fields of one trial (meta/prompts/progress.md): the no-return event (kind fall / out-of-reach /
    terminated / none; minutes, share of the limit as crit_t computes it, minutes left, noticed, after = stopped /
    kept-trying / n/a, wasted minutes) and how the trial ended (end = goal-done / time-out / resets-used / deliverable /
    agent-stopped / crash). Source: the progress label itself when it is progress-2, else the relabel annot/progress2
    (fingerprint must match); a success without either is no_return none, end goal-done; otherwise v2 = False and every
    field is None (not labelled, never a value)."""
    src = a if (a.get("no_return") or a.get("end")) else p2 if _fp_ok(p2, trial) else None
    if src is None and trial["success"] == "1":
        src = {"no_return": {"kind": "none"}, "end": {"kind": "goal-done"}}
    if src is None:
        return dict(_NOT_LABELLED)
    cut = _f(trial.get("cutoff_min")) or _f(trial.get("timeout_min"))
    nr, en = src.get("no_return") or {}, src.get("end") or {}
    kind = nr.get("kind") or "none"
    t = _clock(nr.get("t")) if kind != "none" else None
    return {"v2": True, "no_return": kind, "nr_min": t, "nr_t": _share(t, cut),
            "nr_left": None if t is None or not cut else max(0.0, cut - t),
            "nr_noticed": nr.get("noticed") or "n/a", "nr_after": nr.get("after") or "n/a",
            "wasted": _f(nr.get("wasted_min")) if kind != "none" else None, "nr_what": nr.get("what", ""),
            "end": en.get("kind") or "", "end_what": en.get("what", "")}


@_rows_cache
def progress_rows(ctx, sample=True) -> list[dict]:
    """Progress labels joined with their trial: one row per labelled valid trial whose label fingerprint matches
    (outcome, agent, bench, mode, best / stuck level, share of the session at the last level, reach[L] = share of the
    limit when level >= L was first reached; progress-2: no_return, nr_t, nr_left, nr_noticed, nr_after, wasted, end,
    v2 = has them; retired progress-1 critical point: crit, crit_t, noticed, after, left); sample: see sampled."""
    by_key = {t["key"]: t for t in ctx.trials}
    out = []
    for key, a in ctx.progress.items():
        t = by_key.get(key)
        if not t or not _fp_ok(a, t):
            continue
        out.append({**t, **progress_record(a, t), **progress2_record(a, ctx.progress2.get(key), t),
                    "outcome": "success" if t["success"] == "1" else "failure"})
    return sampled(ctx, out, sample)


def prog_kv(kv: dict) -> dict:
    """The filters a progress query applies (queries and their hover tips): failures unless outcome= is given
    (field=reach takes both); a progress-2 field, as field or filter, keeps only trials with progress-2 labels;
    field=nr_noticed counts among failures with a no-return event, field=nr_after among those with time left after it
    (not n/a), field=wasted among kept-trying; a retired progress-1 field keeps only progress-1 records."""
    kv, f = {k: v for k, v in kv.items() if k != "at"}, kv.get("field")
    if "outcome" not in kv and f != "reach":
        kv["outcome"] = "failure"
    if f in V2_FIELDS or any(k in V2_FIELDS for k in kv):
        kv["v2"] = "True"
    if f in V1_FIELDS or any(k in V1_FIELDS for k in kv):               # retired fields: progress-1 records only
        kv["v1"] = "True"
    if f in ("nr_noticed", "nr_after") and "no_return" not in kv:
        kv["no_return"] = "!none"
    if f in ("nr_after", "wasted") and "nr_after" not in kv:
        kv["nr_after"] = "!n/a" if f == "nr_after" else "kept-trying"
    return kv


def _prog_filter(ctx, kv) -> list[dict]:
    """Rows of progress_rows matching kv with the defaults of prog_kv."""
    kv = prog_kv(kv)
    return [r for r in progress_rows(ctx) if _match(r, kv)]


def q_prog(ctx, **kv) -> str:
    """{{q:prog|field=no_return|value=fall|agent=…|mode=…}} -> "k/n" among sampled progress labels (failures unless
    outcome=success / outcome=success,failure). Fields: no_return (fall / out-of-reach / terminated / none), end (end
    type), nr_after (stopped / kept-trying, among failures with time left after a no-return event), nr_noticed (yes / no /
    unclear, among failures with one), stuck (last level reached), best (best level); value=!a,b counts the rest;
    field=reach|value=3|at=25 counts trials at level >= 3 by 25 % of the limit. Filters as elsewhere, !a,b = none of these
    (no_return=!none). Progress-2 fields count only trials that have progress-2 labels (prog_kv).
    RETIRED, kept for the current text: crit (critical kind), after, noticed (crit=!none,time-out)."""
    rows, f, v = _prog_filter(ctx, kv), kv.get("field"), kv.get("value", "").split(",")
    neg = v[0].startswith("!")
    v[0] = v[0].lstrip("!")
    if f == "reach":
        at, lv = float(kv.get("at", 100)) / 100, int(v[0])
        hit = lambda r: r["reach"].get(lv) is not None and r["reach"][lv] <= at
    else:
        hit = lambda r: (str(r.get(f)) in v) != neg
    k = count(rows, hit) if f else len(rows)
    return share_text(k, len(rows), kv.get("fmt"))


MINUTE_FIELDS = ("left_min", "nr_left", "wasted")


def q_progmed(ctx, **kv) -> str:
    """{{q:progmed|field=nr_t|no_return=fall|agent=…}} -> "p%（n=…）": median over sampled progress labels (failures
    unless outcome= is given) of nr_t (no-return event, share of the limit), best_t (best level first reached),
    stuck_share (share of the session at the last level reached), or in minutes ("m min（n=…）") nr_left (minutes left
    after the no-return event) and wasted (minutes of useless work after it, among kept-trying); fmt=iqr -> "q1–q3%"
    (minutes: "q1–q3 min"). RETIRED, kept for the current text: crit_t, left, left_min (critical point)."""
    f = kv["field"]
    vals = sorted(r[f] for r in _prog_filter(ctx, {k: v for k, v in kv.items() if k != "fmt"}) if r.get(f) is not None)
    if not vals:
        return "–"
    q1, q3, m = vals[len(vals) // 4], vals[3 * len(vals) // 4], S.median(vals)
    if f in MINUTE_FIELDS:
        return f"{q1:.0f}–{q3:.0f} min" if kv.get("fmt") == "iqr" else f"{m:.0f} min（n={len(vals)}）"
    return f"{100 * q1:.0f}–{100 * q3:.0f}%" if kv.get("fmt") == "iqr" else f"{100 * m:.0f}%（n={len(vals)}）"


_KN = re.compile(r"\s*(\d+(?:\.\d+)?)/(\d+)")


def pctkn(fn):
    """fmt=pctkn on any k/n placeholder (q:rate, q:overlap, q:unsolved, q:rev, …): 「37%（158/432）」, the integer
    percent first (user 10-19, main findings); other fmt values reach the metric unchanged."""
    def call(**kv):
        if kv.get("fmt") != "pctkn":
            return fn(**kv)
        v = str(fn(**{k: x for k, x in kv.items() if k != "fmt"}))
        if not (m := _KN.match(v)):
            raise SystemExit(f"fmt=pctkn needs a k/n value, got {v!r}")
        k, n = float(m.group(1)), int(m.group(2))
        return f"{pct(k, n)}（{round(k)}/{n}）" if n else "–"
    return call


def metrics(ctx: Context) -> dict:
    """name -> callable(**params) returning the text placed at {{q:name|k=v|…}} (every one takes fmt=pctkn, see pctkn)."""
    return {k: pctkn(f) for k, f in _metrics(ctx).items()}


def _metrics(ctx: Context) -> dict:
    return {"n_trials": lambda **kv: f"{len(ctx.trials):,}", "rate": lambda **kv: q_rate(ctx, **kv), "unsolved": lambda **kv: q_unsolved(ctx, **kv),
            "rev": lambda **kv: q_rev(ctx, **kv), "ann": lambda **kv: q_ann(ctx, **kv),
            "feat": lambda **kv: q_feat(ctx, **kv), "int": lambda **kv: q_int(ctx, **kv),
            "med": lambda **kv: q_med(ctx, **kv), "fix": lambda **kv: q_fix(ctx, **kv),
            "grasp": lambda **kv: q_grasp(ctx, **kv), "reason": lambda **kv: q_reason(ctx, **kv),
            "prog": lambda **kv: q_prog(ctx, **kv), "progmed": lambda **kv: q_progmed(ctx, **kv),
            "overlap": lambda **kv: q_overlap(ctx, **kv), "overlap_tasks": lambda **kv: q_overlap_tasks(ctx, **kv)}


def fig_review_dist(ctx, by: str, field: str, top: int = 8, outcome: str = "failure") -> str:
    """Share of reviews per value of `field` (top values), one row per value of `by` (agent / category / mode)."""
    rows = [r for r in review_rows(ctx) if r["outcome"] == outcome]
    getv = lambda r: r[field] if isinstance(r[field], list) else [r[field]]
    vals = [v for v, _ in tally(rows, lambda r: [v for v in getv(r) if v]).most_common(top)]
    groups = defaultdict(list)
    for r in rows:
        groups[CATEGORY.get(r["bench"]) if by == "category" else r[by]].append(r)
    order = ORDER if by == "agent" else sorted(groups)
    out = []
    for g in order:
        rs = groups.get(g)
        if not rs or len(rs) < 5:
            continue
        out.append([g, str(len(rs))] + [pct(count(rs, lambda r: v in getv(r)), len(rs)) for v in vals])
    return table([{"agent": "Agent", "category": "类别", "mode": "模式"}[by], "分析过的 trial 数"] + [f'<span class="mono">{v}</span>' for v in vals], out)


def figures(ctx: Context) -> dict:
    """name -> zero-arg callable returning an HTML fragment placed at {{fig:name}}."""
    return {"rescue": lambda **kv: fig_rescue(ctx), "common": lambda **kv: fig_common(ctx), "endings": lambda **kv: fig_endings(ctx),
            "time": lambda **kv: fig_time(ctx), "process": lambda **kv: fig_process(ctx), "code": lambda **kv: fig_code(ctx),
            "modes": lambda **kv: fig_modes(ctx), "bench_priv": lambda **kv: fig_bench_heat(ctx, "privileged"),
            "bench_std": lambda **kv: fig_bench_heat(ctx, "standard"),
            "dist": lambda by="agent", field="primary", top="8", outcome="failure": fig_review_dist(ctx, by, field, int(top), outcome)}
