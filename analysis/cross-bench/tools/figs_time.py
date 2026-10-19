"""Progress over time (progress labels, meta/prompts/progress.md): arrival curves of one event
({{fig:arrive|event=deliverable|by=mode}}; events level1 / level3 / level5 / deliverable / noreturn / end; by=agent draws
one line per agent; level=3 is the old spelling of event=level3), the best level of every sampled trial
({{fig:best|by=mode}}, successes and failures in their own rows), swimlanes of concrete trials ({{fig:swim|keys=k1,k2}} /
{{fig:swim|task=<base>|mode=<mode>}}) and sets of swimlanes picked by rule ({{fig:swimset|mode=standard|n=3}}).

Read-only on the shared helpers: rows from queries.progress_rows (valid trials of queries.load; the random sample for
shares, every labelled trial for the swimlanes, which show cases), the review's time.first_deliverable_t for the
deliverable event, charts from charts.py, category names, colours and row grouping from figs.py (LEVELS = --lv0…--lv5,
NORETURN, END, _groups, _filter). Time is a share of the trial's own limit (cutoff_min, the limit its instruction
stated). RoboSafeBench (rsb) is left out (OUTLINE v17).

Colours: success / failure lines --ok / --n1 (valence); agent lines take the palette slots in the order drawn (--cat1
blue, --cat2 rust, --cat3 aqua, …), so the three default agents are blue, rust, aqua in every panel. validate_palette.js
on those three (and on the first seven slots, for agents=): ALL PASS light and dark.

`python3 tools/figs_time.py` writes the swimset candidates (swim_tasks; core set, privileged and standard) to
/data/pingyue/cross-bench/swim_candidates.md."""
from __future__ import annotations
import glob
import hashlib
import os
import re
from collections import defaultdict
import charts as C
import common
import figs as FG
import palette as PL
import queries as Q

EXCLUDE = ("rsb", "ese")                       # benches left out of the report (RoboSafeBench, user 10-18)
STRONG = Q.ORDER[:3]                     # GPT-6 Astra, Gemini 4 Argon, Opus 5.5 (meta/site.json agent_order)
MODES = list(FG.MODE_NAME)
NAMES = {"arrive": "事件的到达时刻（累计占比）", "best": FG.BEST_TITLE, "swim": "具体 trial 的进展时间线",
         "swimset": "具体 trial 的进展时间线（按规则选出的任务）"}      # chart titles (build.FIG_NAME)
CANDIDATES = "/data/pingyue/cross-bench/swim_candidates.md"
MEDIA = os.environ.get("XB_MEDIA", "/data/pingyue/cross-bench/media")      # media.MEDIA: <key>.mp4 = the case page has a video
OWN = ("event", "level", "agents", "n")                                  # figure parameters, not row filters


def _kept(rows):
    return [r for r in rows if r["bench"] not in EXCLUDE]


def _lvname(lv: int) -> str:
    """第 N 级（its codebook name）."""
    return f"第 {lv} 级（{FG.PROG['level'][str(lv)][0]}）"


def _mmss(minutes) -> str:
    if minutes is None:
        return "–"
    s = round(minutes * 60)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _wrap(chart: str) -> str:
    """A chart of this module in a box whose table view keeps its headers on one line on a phone (it scrolls instead)."""
    return f'<div class="ftime">{chart}</div>' if chart else ""


def _filt(rows, kv):
    return _kept(FG._filter(rows, {k: v for k, v in kv.items() if k not in OWN}))


# ---------------------------------------------------------------------------------------------------- arrival curves

UNKNOWN = "?"                            # an event time the labels do not give: the trial leaves that curve's count


def _review(ctx, key):
    return ctx.reviews.get((key, "deep")) or ctx.reviews.get((key, "skim"))


def _deliverable(ctx, r):
    """First deliverable saved (the review's time.first_deliverable_t: privileged = first save of something graded,
    standard = first submit of the graded episode) as a share of the limit; None = never saved; UNKNOWN = not stated."""
    rv = _review(ctx, r["key"])
    v = str(((rv or {}).get("time") or {}).get("first_deliverable_t") or "").strip().lstrip("≈~约 ")
    if rv is None or not v or v == "unclear":
        return UNKNOWN
    if v.startswith("none"):
        return None
    m = Q._clock(v)
    return UNKNOWN if m is None or not r.get("cutoff") else min(1.0, m / r["cutoff"])


def _noreturn(ctx, r):
    if not r["v2"]:
        return UNKNOWN
    return None if r["no_return"] in (None, "none") else (UNKNOWN if r["nr_t"] is None else r["nr_t"])


def _end(ctx, r):
    used = Q._f(r.get("agent_min")) or r.get("end_min")
    return min(1.0, used / r["cutoff"]) if used is not None and r.get("cutoff") else UNKNOWN


_LV = FG.PROG["level"]
_LEVEL_JUDGE = "到达时刻由分析认定（取第一次到达这一级或更高一级的时刻）"
# event -> (name, what "by then" means, definition, time of one row (share of its limit; None = never), failures only,
#           who judged the time)
EVENTS = {f"level{lv}": (f"到达{_lvname(lv)}", f"已到{_lvname(lv)}" + ("或更高" if lv < 5 else ""), _LV[str(lv)][1],
                         (lambda lv: lambda ctx, r: r["reach"][lv])(lv), False, _LEVEL_JUDGE) for lv in (1, 3, 5)}
EVENTS.update({
    "deliverable": ("第一次存下交付物", "已存下第一个交付物",
                    "privileged 是第一次存下会被评分的东西，standard 是第一次提交被评分的那一局", _deliverable, False,
                    "交付时刻由分析从日志认定"),
    "noreturn": ("不可挽回点", "已到不可挽回点", FG.NR_DEF + "；成功的 trial 没有不可挽回点，所以只画失败", _noreturn, True,
                 "不可挽回点由分析认定"),
    "end": ("会话结束", "会话已结束", "agent 的会话停下的时刻（agent 用掉的时间），时限到了会话也就结束", _end, False,
            "结束时刻取自运行记录")})


def _line(ctx, rs, get, xs):
    """(n, [share of rs with the event by x for x in xs]); rows whose time is UNKNOWN are left out of n."""
    w = (lambda r: r["weight"]) if common.WEIGHTS else (lambda r: 1.0)
    ts = [(get(ctx, r), w(r)) for r in rs]
    ts = [(t, wt) for t, wt in ts if t is not UNKNOWN]
    tot = sum(wt for _, wt in ts) or 1
    return len(ts), [sum(wt for t, wt in ts if t is not None and t <= x + 1e-9) / tot for x in xs]


def fig_arrive(ctx, event="", level="", by="mode", agents="", **kv):
    """Arrival curves of one event (EVENTS; level=N is the old spelling of event=levelN, default level3): x = share of
    each trial's own time limit, y = share of trials that had the event by then. Default: one small chart per `by`
    group (mode; by= empty pools them), one line for successes and one for failures. by=agent: one small chart per
    mode, one line per agent (the agents of agent= or agents=, else the three strongest), successes and failures
    together unless outcome= is given. A line needs >= 5 trials; under SMALL it is tagged 样本少. Sampled progress
    labels of valid trials; rsb left out."""
    ev = event or f"level{level or 3}"
    if ev not in EVENTS:
        return f"⟨missing fig arrive event {ev}⟩"
    name, did, define, get, fails_only, judge = EVENTS[ev]
    rows = _filt(Q.progress_rows(ctx), kv)
    if fails_only:
        rows = [r for r in rows if r["outcome"] == "failure"]
    unknown = sum(get(ctx, r) is UNKNOWN for r in rows)
    xs, min_n = [i / 100 for i in range(101)], int(kv.get("min", 5))
    panels = []
    if by == "agent":
        names = (agents or kv.get("agent") or "").split(",")
        names = [a for a in Q.ORDER if a in {x.strip() for x in names}] or STRONG
        color = {a: PL.CAT[i][0] for i, a in enumerate(names[:len(PL.CAT)])}
        for lab, rs in FG._groups([r for r in rows if r["agent"] in color], "mode", min_n):
            ss = [(a, color[a], *_line(ctx, [r for r in rs if r["agent"] == a], get, xs)) for a in color]
            panels.append((lab, [s for s in ss if s[2] >= 5]))
        outcome = {"success": "只算成功的", "failure": "只算失败的"}.get(kv.get("outcome"), "")
        who = outcome or ("只算失败" if fails_only else "成功和失败合在一起")
        row = f"每张小图是一种模式的抽样 trial（{who}），每条线是一个 agent"
        lines = "颜色 = agent（见图例）"
    else:
        groups = FG._groups(rows, by, min_n) if by else [("全部", rows)]
        for lab, rs in groups:
            ss = [(nm, col, *_line(ctx, [r for r in rs if r["outcome"] == oc], get, xs))
                  for oc, nm, col in (("success", "成功", "--ok"), ("failure", "失败", "--n1")) if not (fails_only and oc == "success")]
            panels.append((lab, [s for s in ss if s[2] >= 5]))
        row = (f"每张小图是{FG._row(by)}的抽样 trial" if by else "图里是全部抽样 trial") + ("（只算失败）" if fails_only else "")
        lines = "红线 = 失败的 trial" if fails_only else "绿线 = 成功的 trial，红线 = 失败的 trial"
    few = any(n < C.SMALL for _, ss in panels for _, _, n, _ in ss)
    titled = [(f"{lab}（" + "，".join(f"{nm} {n} 个" + ("·样本少" if n < C.SMALL else "") for nm, _, n, _ in ss) + "）", ss)
              for lab, ss in panels]
    note = ((FG.BASIS if ev.startswith("level") else "") + "会话结束时还没发生的 trial 一直算作没发生。"
            + (f"另有 {unknown} 个 trial 的这一时刻没有标注，不计入。" if unknown else "")
            + ("占比按层加权。" if common.WEIGHTS else "")
            + (f"标「样本少」的线少于 {C.SMALL} 个 trial，误差大，仅供参考。" if few else ""))
    chart = C.lines(titled, xs, note=f"{row}；{lines}，小图标题里是每条线的 trial 数；{judge}，成败由评分程序判定。" + note,
                    read=f"纵轴 = 到这个时刻{did}的 trial 占比，横轴 = 用时占时限。")
    if not chart:
        return ""
    head = f'<dl class="legend defs evdef"><div><dt>事件：{C.esc(name)}</dt><dd>{C.esc(define)}</dd></div></dl>'
    chart = _wrap(chart.replace('<div class="chart">', '<div class="chart">' + head, 1))
    if not kv.get("lead"):
        return chart
    half = [f"{lab}：到时限一半时，" + "，".join(f"{nm}{' ' if nm[-1:].isascii() else ''}的 {round(100 * ys[50])}%" for nm, _, _, ys in ss) + f" {did}"
            for lab, ss in panels if ss]
    return (f'<p class="figsay">{"；".join(half)}。</p>' if half else "") + chart


# ------------------------------------------------------------------------------------------------ best level reached

def fig_best(ctx, by="mode", **kv):
    """The best progress level every sampled trial reached (successes and failures alike): one row per `by` group
    (mode by default; agent, …) × outcome, 成功 then 失败, coloured by level (LEVELS). Rows need `min` (default 5)
    trials. fig:stuck is the failures-only view of the same labels (with the time spent at the last level)."""
    rows = [r for r in _filt(Q.progress_rows(ctx), kv) if isinstance(r["best"], int)]
    min_n, data = int(kv.get("min", 5)), []
    for lab, rs in (FG._groups(rows, by, 1) if by else [("全部", rows)]):
        for oc, nm in (("success", "成功"), ("failure", "失败")):
            mine = [r for r in rs if r["outcome"] == oc]
            if len(mine) >= min_n:
                data.append((f"{lab} · {nm}", Q.tally(mine, lambda r: [str(r["best"])])))
    row = f"{FG._row(by)}里成功或失败的" if by else ""
    low = sum(r["outcome"] == "success" and r["best"] < 5 for r in rows)
    chart = C.stack(data, FG.LEVELS, unit="抽样 trial", sample=True,
                    note=FG.BASIS + (f"有 {low} 个成功的 trial 没到第 5 级：agent 自己没看到做成，评分仍通过。" if low else ""),
                    read="每段 = 最高到这一级的抽样 trial 数/这一行的抽样 trial 数；分析认定。")
    return (FG._lead(data, FG.LEVELS, "最高到") if kv.get("lead") and chart else "") + _wrap(chart)


# --------------------------------------------------------------------------------------------------------- swimlanes

def case_id(key: str) -> str:
    """The case page id of a trial key (the same rule as build.case_id: #case-<id>)."""
    return "c" + hashlib.sha1(key.encode()).hexdigest()[:6]


def _order(r) -> tuple:
    """The three strongest agents first, then the others (agent_order); successes before failures inside each part."""
    rank = Q.ORDER.index(r["agent"]) if r["agent"] in Q.ORDER else len(Q.ORDER)
    return (r["agent"] not in STRONG, r["outcome"] != "success", rank, MODES.index(r["mode"]) if r["mode"] in MODES else 9, r["key"])


def _mode_of(mode: str) -> str:
    return {"realtime": "standard-realtime"}.get(mode, mode)


def swim_rows(ctx, keys: str = "", task: str = "", mode: str = "", **kv) -> list[dict]:
    """The trials a swimlane shows: the keys given (in that order of tasks), or every progress-labelled valid trial of
    one task base (or task name) and mode, ordered by _order. Not limited to the sample (the rows are cases)."""
    rows = _kept(Q.progress_rows(ctx, sample=False))
    if keys:
        by_key = {r["key"]: r for r in rows}
        pick = [by_key[k.strip()] for k in keys.split(",") if k.strip() in by_key]
    else:
        pick = [r for r in FG._filter(rows, kv) if task in (r["base"], r["task"]) and (not mode or r["mode"] == _mode_of(mode))]
    first = {}
    for r in pick:
        first.setdefault((r["base"], r["mode"]), len(first))
    return sorted(pick, key=lambda r: (first[(r["base"], r["mode"])],) + _order(r))


def swim_keys(ctx, text: str) -> set:
    """Trial keys shown by the {{fig:swim|…}} and {{fig:swimset|…}} placeholders in `text`, so the build gives each of
    them a case page."""
    out = set()
    for kind, spec in re.findall(r"\{\{fig:(swim|swimset)\|([^}]*)\}\}", text):
        kv = dict(p.strip().split("=", 1) for p in spec.split("|") if "=" in p)
        kv.pop("say", None)
        out |= set(swimset_keys(ctx, **kv)) if kind == "swimset" else {r["key"] for r in swim_rows(ctx, **kv)}
    return out


def _spans(r) -> list[tuple]:
    """[(start min, end min, level, what)] from 0 to the session end: the level held over each stretch."""
    end, cur, t0, what, out = r["end_min"], 0, 0.0, "", []
    for t, lv, w in r["milestones"]:
        t = min(t, end)
        if lv <= cur:
            continue
        if t > t0:
            out.append((t0, t, cur, what))
        t0, cur, what = t, lv, w
    if end > t0:
        out.append((t0, end, cur, what))
    return out


def _lane(r, names: dict) -> tuple[str, list[str], set]:
    """One row's HTML, its table cells and the legend codes it uses."""
    cut = r["cutoff"]
    pos = lambda m: 100 * min(1.0, m / cut)
    ok = r["outcome"] == "success"
    label = f"{r['agent']} · {FG.MODE_NAME.get(r['mode'], r['mode'])} · {'成功' if ok else '失败'}"
    used, segs = set(), []
    for a, b, lv, what in _spans(r):
        used.add(("lv", str(lv)))
        tip = (f"{label} · 第 {lv} 级（{names['lv'][str(lv)]}）：{_mmss(a)}–{_mmss(b)}，时限的 {round(pos(a))}–{round(pos(b))}%"
               + (f"；{what}" if what else ""))
        segs.append(f'<span class="swseg" style="left:{pos(a):.2f}%;width:{pos(b) - pos(a):.2f}%;background:var(--lv{lv})" data-tip="{C.esc(tip)}"></span>')
    end_name = names["end"].get(r["end"], r["end"] or "未标") if r["v2"] else "未标"
    if r["v2"] and r["end"]:
        used.add(("end", r["end"]))
    end_tip = (f"{label} · 结束：{end_name}，{_mmss(r['end_min'])}（时限的 {round(pos(r['end_min']))}%）" + (f"；{r['end_what']}" if r["end_what"] else "")
               if r["v2"] else f"{label} · 会话在 {_mmss(r['end_min'])} 结束；这个 trial 还没有标不可挽回点和结束方式")
    marks = f'<span class="swend" style="left:{pos(r["end_min"]):.2f}%" data-tip="{C.esc(end_tip)}"></span>'
    nr, side = "", ""
    if r["v2"] and r["no_return"] not in (None, "none") and r["nr_min"] is not None:
        used.add(("nr", r["no_return"]))
        nr_name = names["nr"].get(r["no_return"], r["no_return"])
        after = FG.PROG["nr_after"].get(r["nr_after"] or "n/a", [r["nr_after"]])[0]
        tip = (f"{label} · 不可挽回点：{nr_name}，{_mmss(r['nr_min'])}（时限的 {round(pos(r['nr_min']))}%）"
               + (f"；{r['nr_what']}" if r["nr_what"] else "") + f"；之后：{after}")
        marks += f'<span class="swnr" style="left:{pos(r["nr_min"]):.2f}%" data-tip="{C.esc(tip)}"></span>'
        nr = f"{nr_name} {_mmss(r['nr_min'])}"
        side = f'<small class="cside" data-tip="{C.esc(tip)}">◆ {C.esc(nr_name)}</small>'
    html = (f'<div class="crow"><a class="cl" href="#case-{case_id(r["key"])}" title="{C.esc(label)}（打开案例页）">{C.esc(label)}</a>'
            f'<span class="swtrack">{"".join(segs)}{marks}</span><span class="cv">{C.esc(end_name)}{side}</span></div>')
    reach = "，".join(f"{lv} 级 {round(100 * r['reach'][lv])}%" for lv in range(1, 6) if r["reach"].get(lv) is not None) or "–"
    cells = [f'<a href="#case-{case_id(r["key"])}">{C.esc(label)}</a>', str(r["best"]), C.esc(reach), C.esc(nr or "–"), C.esc(end_name),
             f"{_mmss(r['end_min'])} / {_mmss(cut)}"]
    return html, cells, used


def fig_swim(ctx, keys="", task="", mode="", **kv):
    """Swimlane timeline of concrete trials: one row per trial (agent · mode · 成功/失败, linked to its case page), a bar
    from 0 to its own time limit coloured by the progress level held at each moment, a diamond at the no-return event,
    a tick at the session end and the end type at the right. Blocks per task (base · mode)."""
    return _swim_html(swim_rows(ctx, keys, task, mode, **kv))


def _swim_html(rows, how: str = "") -> str:
    """The swimlane chart of `rows` (fig_swim); `how` is added to the note (how the trials were picked)."""
    rows = [r for r in rows if r.get("cutoff") and r.get("end_min") is not None]
    if not rows:
        return ""
    names = {"lv": {k: v[0] for k, v in FG.PROG["level"].items()},
             "end": {k[0]: k[1] for k in FG.END}, "nr": {k[0]: k[1] for k in FG.NORETURN}}
    blocks, table, used = defaultdict(list), [], set()
    for r in rows:
        html, cells, u = _lane(r, names)
        blocks[(r["base"], r["mode"])].append(html)
        table.append([C.esc(f"{r['base']} · {FG.MODE_NAME.get(r['mode'], r['mode'])}")] + cells)
        used |= u
    axis = ('<div class="crow axis"><span class="cl"></span><span class="ticks"><span>0</span><span>50%</span><span>时限</span></span>'
            '<span class="cv"></span></div>')
    body = "".join(f'<div class="rblock"><p class="rtitle">{C.esc(base)} · {C.esc(FG.MODE_NAME.get(m, m))}</p>{"".join(h)}{axis}</div>'
                   for (base, m), h in blocks.items())
    pick = lambda keys_, kind: [k for k in keys_ if (kind, k[0]) in used]
    marker = lambda cls, ks: ('<dl class="legend defs">' + "".join(f'<div><dt><i class="{cls}"></i>{C.esc(k[1])}</dt><dd>{C.esc(k[3])}</dd></div>'
                                                                   for k in ks) + "</dl>")
    legs = [("进展等级", C.legend([(k[1], k[2], k[3]) for k in pick(FG.LEVELS, "lv")])),
            ("不可挽回点", marker("swkey-nr", pick(FG.NORETURN, "nr")) if pick(FG.NORETURN, "nr") else ""),
            ("结束方式", marker("swkey-end", pick(FG.END, "end")) if pick(FG.END, "end") else "")]
    lg = "".join(f'<div class="pleg"><b>{C.esc(g)}</b>{h}</div>' for g, h in legs if h)
    read = "每行是一个 trial，颜色 = 那一刻已到达的进展等级；分析认定。"
    note = ("点行名打开它的案例页；条从 0 画到这个 trial 自己的时限，浅底 = 会话结束后没用到的时间；菱形 = 不可挽回点，竖线 = 会话结束处；"
            "右侧 = 结束方式，其下 ◆ = 不可挽回点的类型；成败由评分程序判定。" + FG.BASIS + "这些是具体 trial，不是抽样统计。" + how)
    body = f'<div class="swgrid">{body}</div>' if len(blocks) > 1 else body        # several tasks: blocks side by side, one legend
    return _wrap(C.howto(read) + f'<div class="chart swim"><div class="plegs">{lg}</div>{body}<p class="note">{C.esc(note)}</p></div>'
                 + C.numbers(["任务", "trial", "最高等级", "各级首次到达（占时限）", "不可挽回点", "结束方式", "用时 / 时限"], table))


def css() -> str:
    """Swimlane marks (the page adds it next to the palette tokens)."""
    return (".swim .crow{grid-template-columns:minmax(120px,270px) minmax(0,1fr) 76px}"
            ".swim a.cl{color:var(--ink-2)}.swim a.cl:hover{color:var(--accent)}"
            ".swtrack{position:relative;display:block;height:14px;background:var(--sunk);border-radius:3px}"
            ".swseg{position:absolute;top:0;bottom:0;min-width:2px;box-shadow:inset -2px 0 0 var(--surface)}"
            ".swseg:first-child{border-radius:3px 0 0 3px}"
            ".swend{position:absolute;top:-3px;bottom:-3px;width:3px;margin-left:-1.5px;border-radius:2px;background:var(--ink);"
            "box-shadow:0 0 0 1px var(--surface)}"
            ".swnr{position:absolute;top:1px;width:11px;height:11px;margin-left:-5.5px;transform:rotate(45deg);border-radius:2px;"
            "background:var(--ink);box-shadow:0 0 0 2px var(--surface)}"
            "dl.legend.defs dt i.swkey-nr{width:8px;height:8px;margin:0 7px 0 1px;transform:rotate(45deg);background:var(--ink)}"
            "dl.legend.defs dt i.swkey-end{width:3px;height:12px;margin:0 8px 0 3px;vertical-align:-2px;background:var(--ink)}"
            ".swseg:hover,.swnr:hover,.swend:hover{filter:brightness(1.12)}"
            "dl.legend.defs.evdef{display:block;margin:4px 0 8px}dl.legend.defs.evdef dt{font-weight:600}"
            ".ftime table.t th,.ftime table.t td:nth-child(2){white-space:nowrap}.ftime table.t td{min-width:5em}"
            ".ftime table.t td:first-child{min-width:9em}"
            "@media (max-width:860px){.swim .crow{grid-template-columns:minmax(0,1fr) 80px;row-gap:1px}"
            ".swim .crow .cl{grid-column:1/-1}.swim .crow.axis .cl{display:none}.swim .cv{white-space:normal}"
            ".swim dl.legend.defs{grid-template-columns:minmax(0,1fr)}}")


# --------------------------------------------------------------------------------------------- swimlane candidates

def has_video(key: str) -> bool:
    """The trial's case page will play a replay video (media.py video made <key>.mp4)."""
    return os.path.exists(os.path.join(MEDIA, key + ".mp4"))


# Benches whose task progress is one continuous motion with no natural steps (brush strokes that build a picture): a
# level timeline says little there, so fig:swimset never picks them.
CONTINUOUS = ("robopaint",)
NEVER = 1.2                              # time to level 3 (share of the limit) of a trial that never reached it
STALL_BONUS = 0.5                        # added to a task's contrast when a failure reached level 3 and stopped at 3–4


def _t3(r) -> float:
    """Share of its time limit at which a trial first reached level 3 or higher (NEVER when it did not)."""
    v = r["reach"].get(3)
    return v if v is not None else NEVER


def _cited() -> set:
    """Trial keys the findings and notes cite ({{case:…}}), read when the page is built."""
    out = set()
    for p in glob.glob(os.path.join(common.HERE, "findings", "*.md")) + glob.glob(os.path.join(common.HERE, "notes", "*", "*.md")):
        out |= {k.strip() for k in re.findall(r"\{\{case:([^}]+)\}\}", open(p).read())}
    return out


def swim_tasks(ctx, mode: str) -> list[dict]:
    """Every core task (base + mode) fig:swimset may draw, best first. A task qualifies when GPT-6 Astra, Gemini 4 Argon
    and Opus 5.5 each have a progress label on it (one trial each: a trial the findings or notes cite first, then one with
    a replay video, then by key) and the three outcomes differ; benches in CONTINUOUS (and rsb) are left out. Contrast =
    the failures' mean time to level 3 (NEVER when not reached) minus the successes', plus STALL_BONUS when a failure
    reached level 3 and stalled there or at level 4 (§4.6); ties: trials with a video, then the task name. Uses whatever
    progress labels exist when the page is built."""
    cited = _cited()
    groups = defaultdict(list)
    for r in _kept(Q.progress_rows(ctx, sample=False)):
        if (Q.in_set(r, "core") and r["bench"] not in CONTINUOUS and r["mode"] == _mode_of(mode) and r["agent"] in STRONG
                and r.get("cutoff") and r.get("end_min") is not None):
            groups[(r["base"], r["mode"])].append(r)
    out = []
    for (base, m), rs in sorted(groups.items()):
        one = {}
        for r in sorted(rs, key=lambda r: (r["key"] not in cited, not has_video(r["key"]), r["key"])):
            one.setdefault(r["agent"], r)
        pick = sorted(one.values(), key=_order)
        succ, fail = [r for r in pick if r["outcome"] == "success"], [r for r in pick if r["outcome"] != "success"]
        if len(pick) < 3 or not succ or not fail:
            continue
        mean = lambda xs: sum(map(_t3, xs)) / len(xs)
        stall = any(_t3(r) <= 1 and isinstance(r["best"], int) and 3 <= r["best"] <= 4 for r in fail)
        out.append({"base": base, "mode": m, "bench": pick[0]["bench"], "strong": pick, "stall": stall,
                    "contrast": round(mean(fail) - mean(succ) + (STALL_BONUS if stall else 0), 3),
                    "video": sum(has_video(r["key"]) for r in pick)})
    return sorted(out, key=lambda c: (-c["contrast"], -c["video"]))


def swimset_tasks(ctx, modes: list[str], n: int) -> list[dict]:
    """The tasks fig:swimset draws: per mode the first `n` of swim_tasks, at most one per bench."""
    out = []
    for mode in modes:
        seen = set()
        for c in swim_tasks(ctx, mode):
            if c["bench"] not in seen and len(seen) < n:
                seen.add(c["bench"])
                out.append(c)
    return out


def swimset_keys(ctx, mode: str = "standard", n: str = "3", **kv) -> list[str]:
    """The trials {{fig:swimset}} shows (swimset_tasks)."""
    return [r["key"] for c in swimset_tasks(ctx, mode.split(","), int(n)) for r in c["strong"]]


import json as _json
_SITE_BENCH = _json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "meta", "site.json")))["benches"]


def fig_swimset(ctx, mode="standard", n="3", **kv):
    """Swimlanes of the tasks swimset_tasks picks (mode=privileged,standard: both modes in one chart, one legend), each
    task under its own heading; the note states the rule in one sentence."""
    cs = swimset_tasks(ctx, mode.split(","), int(n))
    if not cs:
        return ""
    cont = "、".join(_SITE_BENCH.get(b, {}).get("name", b) for b in CONTINUOUS)
    how = (f"任务按规则选出（核心集）：GPT-6 Astra、Gemini 4 Argon、Opus 5.5 在同一任务上各取一个 trial 且成败不同，"
           f"按失败的比成功的晚多久到第 3 级（没到算时限的 {NEVER:g} 倍）排序、失败的到了第 3 级后停住再加 {STALL_BONUS:g}，"
           f"每个 benchmark 每种模式最多一个，进展是连续动作、没有自然步骤的 {cont} 不选。")
    return _swim_html([r for c in cs for r in c["strong"]], how)


def write_candidates(ctx, path: str = CANDIDATES, modes=("privileged", "standard"), n: int = 4) -> str:
    """Every task swim_tasks qualifies, per mode, best first; ✓ = drawn by {{fig:swimset|mode=…|n=n}}."""
    lines = ["# Swimlane candidates (core set)", "", swim_tasks.__doc__.split("\n\n")[0].replace("\n    ", " "), ""]
    for mode in modes:
        cs, drawn = swim_tasks(ctx, mode), {(c["base"], c["mode"]) for c in swimset_tasks(ctx, [mode], n)}
        lines += [f"## {mode}: {len(cs)} tasks qualify", "", "| # | drawn | task base | contrast | stall | trials (outcome, level 3 at, best, video) |",
                  "|---|---|---|---|---|---|"]
        for i, c in enumerate(cs, 1):
            trials = "; ".join(f"{r['agent']} {'成功' if r['outcome'] == 'success' else '失败'} t3={_t3(r):.2f} L{r['best']}{' ▶' if has_video(r['key']) else ''}"
                               for r in c["strong"])
            lines.append(f"| {i} | {'✓' if (c['base'], c['mode']) in drawn else ''} | {c['base']} | {c['contrast']} | {'yes' if c['stall'] else ''} | {trials} |")
        lines.append("")
    open(path, "w").write("\n".join(lines))
    return path


def figures(ctx) -> dict:
    return {"arrive": lambda **kv: fig_arrive(ctx, **kv), "best": lambda **kv: fig_best(ctx, **kv),
            "swim": lambda **kv: fig_swim(ctx, **kv), "swimset": lambda **kv: fig_swimset(ctx, **kv)}


if __name__ == "__main__":
    from review import current_reviews
    trials, cells, tasks = Q.load("core")
    print(write_candidates(Q.Context(trials, cells, tasks, current_reviews(), Q.load_all("core"), which="core")))
