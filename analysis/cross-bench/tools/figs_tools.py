"""Tool calls by group (tools/tooluse.py GROUPS): what the calls go to ({{fig:tooluse|by=agent_mode}}), when in the time
limit ({{fig:tooltime|agent=<name>|mode=<mode>}}, {{fig:tooltime|by=agent|mode=standard}}) and whether successes and
failures differ ({{fig:toolsucc|by=mode}}).

Source: $XB_DATA/tooluse.csv (one row per valid trial with a raw trajectory, rsb left out; each call in one group,
overall and per tenth of the trial's stated limit; calls after the limit count in the last tenth). Like the other
log-count figures (figs.fig_tools, fig_calls, fig_tech src=code) these count every valid trial of queries.load that
made at least one call, not the review sample; every 怎么读 line says so. Groups are counted by the log, not judged.

Colours (meta/DESIGN.md → Colours): the groups are ungrouped categories, so each takes a palette slot (PL.slots) in
the declared order, fixed for the whole build (a filter never repaints a group); groups under FOLD in every agent ×
mode row of all trials fold into the grey 其他 for good, and a chart folds further the groups under FOLD in all its
rows. validate_palette.js on the seven slots in stacking order: ALL PASS in both themes (light: adjacent CVD ≥ 9.4,
normal ≥ 16.7; dark: CVD ≥ 9.0, normal ≥ 16.5; the grey is the neutral 其他 by design). The time strip shades cells
with its own one-hue ramp --tt1…--tt5 (blue 250/350/450/550/700 light, 600/500/400/300/150 dark): --ordinal ALL PASS
in both themes (monotone, ΔL ≥ 0.06, light end 2.11:1 / 2.15:1). Successes vs failures keep --ok / --n1."""
from __future__ import annotations
import math
import statistics as S
from collections import Counter, defaultdict
import charts as C
import figs as FG
import palette as PL
import queries as Q
from common import read_csv
from tooluse import GROUPS, NBIN

EXCLUDE = ("rsb", "ese")
NAMES = {"tooluse": "工具调用的构成（按用途）", "tooltime": "各段时间里的工具调用", "toolsucc": "成功和失败的工具调用构成"}
FOLD = 0.02                          # a group under 2 % of the calls in every row of a chart folds into 其他
MIN_AGENT = 10                       # toolsucc: an agent enters the same-agent difference with >= 10 successes and >= 10 failures
OTHER = "_other"
DEF = {"run_python": "运行 Python 脚本、测试或代码片段，包括经客户端驱动机器人或仿真的代码",
       "robot_api": "在命令行里直接调机器人服务或仿真客户端（本机 curl、game 命令、/opt/tools 下的工具）",
       "search": "grep、find、ls 等找文件或列目录",
       "read": "读文件、打印源码或帮助文本",
       "write": "写、改、复制、移动或删除文件",
       "view_image": "打开图片给模型看",
       "web": "访问外部网站、下载包或克隆仓库",
       "plan": "写计划或待办清单",
       "other_shell": "装包、查进程、等待或轮询正在跑的程序等",
       "other": "本统计不认识的工具"}
NAME = dict(GROUPS)
STEPS = [(0.05, "不到 5%"), (0.15, "5–15%"), (0.30, "15–30%"), (0.50, "30–50%"), (2.0, "50% 及以上")]
TOKENS = [("--tt1", "#86b6ef", "#184f95"), ("--tt2", "#5598e7", "#256abf"), ("--tt3", "#2a78d6", "#3987e5"),
          ("--tt4", "#1c5cab", "#6da7ec"), ("--tt5", "#0d366b", "#b7d3f6")]
ALL_NOTE = "全部有日志的有效 trial（不是抽样）"
WHO = "工具类别按运行日志自动归类，不是分析认定"

_cache: dict = {}


# ------------------------------------------------------------------------------------------------------------- rows

def _all(ctx) -> list[dict]:
    """Every valid trial of ctx with a tooluse row and at least one call: the trial's fields plus tu_n (calls),
    tu (calls per group) and tu_b (calls per group per tenth of the limit)."""
    if _cache.get("ctx") is not ctx:
        tu = {r["key"]: r for r in read_csv("tooluse.csv")}
        rows = []
        for t in ctx.trials:
            u = tu.get(t["key"])
            if not u or t["bench"] in EXCLUDE or not int(u["n_calls"]):
                continue
            rows.append({**t, "tu_n": int(u["n_calls"]), "tu": {g: int(u[g]) for g, _ in GROUPS},
                         "tu_b": {g: [int(u[f"{g}_b{i}"]) for i in range(NBIN)] for g, _ in GROUPS}})
        _cache.clear()
        _cache.update(ctx=ctx, rows=rows, slot=_slots(rows))
    return _cache["rows"]


def _slots(rows) -> dict:
    """{group: colour token}: groups that reach FOLD in some agent × mode row (>= SMALL trials) of all trials take the
    palette slots in declared order; the rest are 其他 (grey) everywhere."""
    by = defaultdict(Counter)
    for r in rows:
        by[(r["agent"], r["mode"])].update(r["tu"])
    n = Counter((r["agent"], r["mode"]) for r in rows)
    live = [g for g, _ in GROUPS if g != "other" and any(c[g] >= FOLD * sum(c.values()) for k, c in by.items() if n[k] >= C.SMALL)]
    keys = PL.slots([(g, NAME[g]) for g in live[:len(PL.CAT)]] + [(OTHER, "其他")], grey=(OTHER,))
    return {k: c for k, _, c in keys}


def tool_rows(ctx, **kv) -> list[dict]:
    """The rows a figure counts: _all filtered by the figure's trial filters (mode=realtime means standard-realtime)."""
    rows = _all(ctx)
    kv = {k: v for k, v in kv.items() if k not in ("top",)}
    if kv.get("mode"):
        kv["mode"] = ",".join({"realtime": "standard-realtime"}.get(m, m) for m in kv["mode"].split(","))
    return FG._filter(rows, kv)


def _fold(c: Counter, keep) -> Counter:
    out = Counter()
    for g, v in c.items():
        out[g if g in keep else OTHER] += v
    return out


def _keys(counters, folded_label=True) -> list[tuple]:
    """The chart's keys [(key, label, token, definition)]: groups with a slot that reach FOLD in at least one of the
    chart's rows (counters: per-row Counter of calls or of mean shares), then 其他 for the rest (when it holds any)."""
    slot = _cache["slot"]
    keep = [g for g, _ in GROUPS if g in slot and any(c[g] >= FOLD * (sum(c.values()) or 1) for c in counters)]
    rest = [g for g, _ in GROUPS if g not in keep and any(c[g] for c in counters)]
    keys = [(g, NAME[g], slot[g], DEF[g]) for g in keep]
    if rest:
        names = "、".join("本统计不认识的工具" if g == "other" else NAME[g] for g in rest)
        keys.append((OTHER, "其他", slot[OTHER], f"{names}（每一行都不到 {round(100 * FOLD)}%）"))
    return keys


def _blocks(rows, by, min_n) -> list[tuple[str, list]]:
    """[(block title, [(row label, rows)])]: by=agent_mode draws one block per mode with the agents as rows."""
    if by == "agent_mode":
        return [(FG.MODE_NAME[m], FG._groups([r for r in rows if r["mode"] == m], "agent", min_n)) for m in FG.MODE_NAME]
    return [("", FG._groups(rows, by, min_n) if by else [("全部", rows)])]


def _few(labels_n) -> str:
    few = [lab for lab, n in labels_n if n < C.SMALL]
    if not few:
        return ""
    why = "两版 Sol 和 Qwen 只跑了一小批评测项。" if any(a in lab for lab in few for a in C.FEW_AGENTS) else ""
    return f"标「样本少」的行少于 {C.SMALL} 个 trial，误差大，仅供参考。{why}"


def _ncell(calls: int, n: int, tip: str) -> str:
    few = '<small class="few">样本少</small>' if n < C.SMALL else ""
    return f'<span class="cv deflab" data-tip="{C.esc(tip)}">{calls}<small class="cside">{n} 个 trial</small>{few}</span>'


def _head(unit: str, left="0%", mid="50%", right="100%") -> str:
    return (f'<div class="crow wide axis chead"><span class="cl"></span><span class="ticks"><span>{left}</span><span>{mid}</span>'
            f'<span>{right}</span></span><span class="cv">{C.esc(unit)}</span></div>')


# ------------------------------------------------------------------------------------- 1. share of calls by group

def fig_tooluse(ctx, by="agent_mode", **kv):
    """100 % stacked bars: per row (agent × mode by default, one block per mode), the share of all its calls in each
    tool group; the count column gives calls and trials."""
    rows, min_n = tool_rows(ctx, **kv), int(kv.get("min", 5))
    blocks = [(title, [(lab, rs, sum((Counter(r["tu"]) for r in rs), Counter())) for lab, rs in groups])
              for title, groups in _blocks(rows, by, min_n)]
    blocks = [(t, g) for t, g in blocks if g]
    if not blocks:
        return ""
    keys = _keys([c for _, g in blocks for _, _, c in g])
    keep = {k[0] for k in keys}
    html, table, ns, lead = [], [], [], []
    for title, groups in blocks:
        body = []
        for lab, rs, raw in groups:
            c, n, calls = _fold(raw, keep), len(rs), sum(raw.values())
            full = f"{title} · {lab}" if title else lab
            segs = "".join(f'<span class="seg" style="width:{100 * c[k] / calls:.2f}%;background:var({col})" '
                           f'data-tip="{C.esc(full)} · {C.esc(name)} {c[k]}/{calls} 次调用"></span>'
                           for k, name, col, _ in keys if c.get(k))
            tip = (f"{full}：{n} 个 trial，共 {calls} 次工具调用，每个 trial 中位数 {S.median(r['tu_n'] for r in rs):.0f} 次"
                   + ("；样本少，仅供参考" if n < C.SMALL else ""))
            body.append(f'<div class="crow wide{" small" if n < C.SMALL else ""}"><span class="cl" title="{C.esc(lab)}">{C.esc(lab)}</span>'
                        f'<span class="track">{segs}</span>{_ncell(calls, n, tip)}</div>')
            ns.append((lab, n))
            table.append([C.esc(full), str(n), str(calls)] + [f"{c.get(k, 0)}/{calls}" for k, _, _, _ in keys])
        html.append(f'<div class="rblock">{f"<p class=rtitle>{C.esc(title)}</p>" if title else ""}{_head("调用数")}{"".join(body)}</div>')
        lead += _spread(title, [(lab, _fold(raw, keep), len(rs)) for lab, rs, raw in groups], keys)
    row = "每张小图是一种模式，每行是一个 agent 在这种模式下" if by == "agent_mode" else f"每行是{FG._row(by)}" if by else "图里是"
    read = "每段 = 一类调用数/这一行的调用总数；按运行日志归类。"
    note = (f"{row}{ALL_NOTE}；右侧 = 调用数，其下 = trial 数。" + _few(ns) + "各 agent 跑的评测项不全相同" + ("（Luna 以外的 agent 只跑 Luna 没过的评测项）" if ctx.set != "core" else "") + "，构成的差别里有任务的份。"
            "Codex 的 agent（GPT 各版）轮询正在跑的程序也是一次调用，记在其他命令里。")
    say = f'<p class="figsay">{"；".join(lead)}。</p>' if kv.get("lead") and lead else ""
    return (say + C.howto(read) + f'<div class="chart">{C.legend([(k[1], k[2], k[3]) for k in keys])}{"".join(html)}'
            f'<p class="note">{C.esc(note)}</p></div>' + C.numbers(["", "trial 数", "调用数"] + [C.esc(k[1]) for k in keys], table))


def _spread(title, data, keys) -> list[str]:
    """One clause per block: the group whose share differs most between rows (rows with >= SMALL trials)."""
    data = [(lab, c, n) for lab, c, n in data if n >= C.SMALL]
    if len(data) < 2:
        return []
    best = None
    for k, name, _, _ in keys:
        if k == OTHER:
            continue
        sh = sorted(((c[k] / sum(c.values()), lab, c[k], sum(c.values())) for lab, c, n in data), reverse=True)
        if best is None or sh[0][0] - sh[-1][0] > best[0]:
            best = (sh[0][0] - sh[-1][0], name, sh[0], sh[-1])
    _, name, hi, lo = best
    head = f"{title}：" if title else ""
    return [f"{head}「{name}」占调用的比例最高是 {hi[1]}（{hi[2]}/{hi[3]} 次调用），最低是 {lo[1]}（{lo[2]}/{lo[3]}）"]


# --------------------------------------------------------------------------------------- 2. time strip per group

def _step(p: float) -> int:
    return 0 if p <= 0 else next(i for i, (hi, _) in enumerate(STEPS, 1) if p < hi)


def _strip(title: str, rs: list[dict], keys: list[tuple], numbers: bool) -> tuple[str, list[list[str]], dict]:
    """One strip: header (start of each tenth), the 调用次数 row, one row per key; plus its table rows and summary."""
    keep = {k[0] for k in keys}
    cells = defaultdict(lambda: [0] * NBIN)
    for r in rs:
        for g, b in r["tu_b"].items():
            k = g if g in keep else OTHER
            cells[k] = [x + y for x, y in zip(cells[k], b)]
    per_bin = [sum(cells[k][i] for k in cells) for i in range(NBIN)]
    active = [sum(1 for r in rs if any(b[i] for b in r["tu_b"].values())) for i in range(NBIN)]
    n, total = len(rs), sum(per_bin)
    span = lambda i: f"时限的 {10 * i}–{10 * (i + 1)}%"
    few_bin = [a < C.SMALL for a in active]
    head = "".join(f'<span class="{"fewbin" if f else ""}">{10 * i}{"*" if f else ""}</span>' for i, f in enumerate(few_bin))
    top = max(per_bin) or 1
    bars = "".join(f'<span class="tub" data-tip="{C.esc(f"{title} · {span(i)}：{per_bin[i]} 次调用，来自 {active[i]}/{n} 个 trial" + ("；样本少" if few_bin[i] else ""))}">'
                   f'<i style="height:{100 * per_bin[i] / top:.1f}%"></i></span>' for i in range(NBIN))
    rows_html = [f'<div class="trow tuhead"><span class="cl"></span><span class="tucells tuax">{head}</span><span class="cv">全程</span></div>',
                 f'<div class="trow tucalls"><span class="cl">调用次数</span><span class="tucells">{bars}</span><span class="cv">{total}</span></div>']
    table = [[C.esc(title), "调用次数"] + [f"{per_bin[i]}（{active[i]} 个 trial）" for i in range(NBIN)] + [str(total)]]
    shares = {}
    for k, name, _, _ in keys:
        row = cells.get(k, [0] * NBIN)
        out = []
        for i in range(NBIN):
            p = row[i] / per_bin[i] if per_bin[i] else 0
            s = _step(p)
            txt = ("<1" if p < 0.005 else str(round(100 * p))) if row[i] and numbers else ("·" if not row[i] else "")
            tip = (f"{title} · {span(i)} · {name}：{row[i]}/{per_bin[i]} 次调用；"
                   f"这一段有 {active[i]} 个 trial 在调用" + ("，样本少" if few_bin[i] else ""))
            out.append(f'<span class="tuc t{s}" data-tip="{C.esc(tip)}">{txt}</span>')
        all_k = sum(row)
        tip = f"{title} · {name}：全程 {all_k}/{total} 次调用"
        rows_html.append(f'<div class="trow"><span class="cl" title="{C.esc(name)}">{C.esc(name)}</span><span class="tucells">{"".join(out)}</span>'
                         f'<span class="cv deflab" data-tip="{C.esc(tip)}">{C._pct(all_k, total)}</span></div>')
        table.append([C.esc(title), C.esc(name)] + [C._pct(row[i], per_bin[i]) if per_bin[i] else "–" for i in range(NBIN)] + [C._pct(all_k, total)])
        shares[k] = (row, per_bin)
    late = sum(1 for r in rs if any(sum(b[NBIN // 2:]) for b in r["tu_b"].values()))
    return f'<div class="tustrip">{"".join(rows_html)}</div>', table, {"shares": shares, "late": late, "n": n, "few_bin": any(few_bin)}


def _shift(title, info, keys) -> str:
    """The group whose share moves most between the first tenth and the second half of the limit."""
    best = None
    for k, name, _, _ in keys:
        row, per_bin = info["shares"][k]
        if not per_bin[0] or not sum(per_bin[NBIN // 2:]):
            continue
        a, b = row[0] / per_bin[0], sum(row[NBIN // 2:]) / sum(per_bin[NBIN // 2:])
        if best is None or abs(a - b) > abs(best[0] - best[1]):
            best = (a, b, name)
    if not best:
        return ""
    a, b, name = best
    return (f"{title}：「{name}」在前 10% 的时间里占调用的 {round(100 * a)}%，后一半时间占 {round(100 * b)}%；"
            f"后一半时间还在调用的 trial {info['late']}/{info['n']}")


def _title(kv) -> str:
    """A single strip's title from its filters (agent · mode · bench · category), else 全部."""
    mode = lambda m: FG.MODE_NAME.get({"realtime": "standard-realtime"}.get(m, m), m)
    parts = [mode(kv[k]) if k == "mode" else FG.CAT_NAME.get(kv[k], kv[k]) if k == "category" else kv[k]
             for k in ("agent", "mode", "bench", "category") if kv.get(k)]
    return " · ".join(parts) or "全部"


def fig_tooltime(ctx, by="", **kv):
    """Time strip: columns = the ten tenths of each trial's own limit, rows = tool groups, cell = that group's share of
    the calls made in that tenth (all calls of the rows' trials pooled), shaded by one blue ramp; a 调用次数 row of
    thin bars shows the calls per tenth. by=agent draws one strip per agent (small multiples, numbers in the tips)."""
    rows, min_n = tool_rows(ctx, **kv), int(kv.get("min", 5))
    groups = FG._groups(rows, by, min_n) if by else ([("全部", rows)] if rows else [])
    if not groups:
        return ""
    keys = _keys([sum((Counter(r["tu"]) for r in rs), Counter()) for _, rs in groups])
    multi = len(groups) > 1
    panels, table, lead, few_bins, ns = [], [], [], False, []
    for lab, rs in groups:
        calls = sum(r["tu_n"] for r in rs)
        title = lab if by else _title(kv)
        html, rows_t, info = _strip(title, rs, keys, numbers=not multi)
        few = '<small class="few">样本少</small>' if len(rs) < C.SMALL else ""
        panels.append(f'<div class="tupanel{" small" if len(rs) < C.SMALL else ""}"><p class="rtitle">{C.esc(title)}'
                      f'（{len(rs)} 个 trial · {calls} 次调用）{few}</p>{html}</div>')
        table += rows_t
        few_bins |= info["few_bin"]
        ns.append((lab, len(rs)))
        if (s := _shift(title, info, keys)) and len(rs) >= C.SMALL:
            lead.append(s)
    scale = ('<div class="tuscale"><span>格子颜色 = 这一段调用里该类的占比：</span><span><i class="tuc t0">·</i>没有</span>'
             + "".join(f'<span><i class="tuc t{i}"></i>{C.esc(lab)}</span>' for i, (_, lab) in enumerate(STEPS, 1))
             + '<span><i class="tubkey"></i>调用次数（每张图按自己的最高一段画）</span></div>')
    gloss = C.legend([(k[1], "--c0", k[3]) for k in keys]).replace('<i style="background:var(--c0)"></i>', "")
    row = f"每张小图是{FG._row(by)}的" if multi else "图里是"
    read = "格子 = 这段时间里这一类调用的占比，一列合计 100%；按日志归类。"
    note = (f"{row}{ALL_NOTE}；每列是时限的十分之一（列头是这一段的起点，0 = 前 10%，90 = 最后 10%）"
            + ("，格子里的数字是百分数" if not multi else "，数字在提示和「看数字」里") + "；顶上的细条 = 这一段的调用次数；右侧 = 全程占比。"
            "时限按这个 trial 自己说明里写的算；超过时限后的调用算在最后一段。"
            + (f"列头带 * 的段里在调用的 trial 少于 {C.SMALL} 个，比例不稳。" if few_bins else "") + _few(ns))
    say = f'<p class="figsay">{"；".join(lead)}。</p>' if kv.get("lead") and lead else ""
    return (say + C.howto(read) + f'<div class="chart">{scale}<div class="tupanels{" multi" if multi else ""}">{"".join(panels)}</div>'
            f'{gloss}<p class="note">{C.esc(note)}</p></div>'
            + C.numbers(["", "", *[f"{10 * i}–{10 * (i + 1)}%" for i in range(NBIN)], "全程"], table))


# ------------------------------------------------------------------------------ 3. successes vs failures per group

def _mean_share(rs, g, keep) -> float:
    pick = (lambda r: r["tu"][g]) if g != OTHER else (lambda r: sum(v for k, v in r["tu"].items() if k not in keep))
    return S.mean(pick(r) / r["tu_n"] for r in rs) if rs else 0.0


def _same_agent(rs, g, keep) -> tuple[float | None, list[tuple]]:
    """Mean over agents (equal weight) of success mean share minus failure mean share, for agents with >= MIN_AGENT
    of each outcome in rs: (difference or None, [(agent, difference, n success, n failure)])."""
    per = []
    for a in Q.ORDER:
        s = [r for r in rs if r["agent"] == a and r["success"] == "1"]
        f = [r for r in rs if r["agent"] == a and r["success"] == "0"]
        if len(s) >= MIN_AGENT and len(f) >= MIN_AGENT:
            per.append((a, _mean_share(s, g, keep) - _mean_share(f, g, keep), len(s), len(f)))
    return (S.mean(d for _, d, _, _ in per) if per else None), per


def fig_toolsucc(ctx, by="mode", **kv):
    """Per group, the mean share of a trial's calls in successes (green) vs failures (red), one small chart per `by`
    group (mode by default); the right column adds the same-agent difference (agent mix held fixed)."""
    rows, min_n = tool_rows(ctx, **kv), int(kv.get("min", 5))
    groups = []
    for lab, rs in (FG._groups(rows, by, 1) if by else [("全部", rows)]):
        s, f = [r for r in rs if r["success"] == "1"], [r for r in rs if r["success"] == "0"]
        if len(s) >= min_n and len(f) >= min_n:
            groups.append((lab, rs, s, f))
    if not groups:
        return ""
    keys = _keys([Counter({g: _mean_share(x, g, ()) for g, _ in GROUPS}) for _, _, s, f in groups for x in (s, f)])
    keep = {k[0] for k in keys}
    if keys[-1][0] == OTHER and all(_mean_share(x, OTHER, keep) < FOLD for _, _, s, f in groups for x in (s, f)):
        keys = keys[:-1]                                   # no 100 % to fill here: drop a 其他 that is under FOLD everywhere
    means = {(lab, k[0]): (_mean_share(s, k[0], keep), _mean_share(f, k[0], keep), *_same_agent(rs, k[0], keep))
             for lab, rs, s, f in groups for k in keys}
    top = math.ceil(10 * max(max(a, b) for a, b, _, _ in means.values())) / 10 or 1
    blocks, table, worst, ns = [], [], [], []
    for lab, rs, s, f in groups:
        body = []
        for k, name, _, _ in keys:
            ps, pf, d, per = means[(lab, k)]
            ts = f"{lab} · {name}：成功的 {len(s)} 个 trial 里，这一类平均占调用的 {100 * ps:.1f}%"
            tf = f"{lab} · {name}：失败的 {len(f)} 个 trial 里，这一类平均占调用的 {100 * pf:.1f}%"
            if d is not None and len(per) < 2:                 # one agent is that agent's own contrast, not a same-agent average
                d1 = per[0]
                d = None
            v = round(100 * d) if d is not None else None
            dtxt = "–" if v is None else "0 点" if v == 0 else f"{v:+d} 点"
            dtip = (f"同一 agent 内成功减失败（{len(per)} 家，各自至少 {MIN_AGENT} 个成功和 {MIN_AGENT} 个失败，各家等权平均）：{100 * d:+.1f} 个百分点；"
                    + "，".join(f"{a} {100 * x:+.1f}（{ns_}/{nf}）" for a, x, ns_, nf in per)) if d is not None else \
                (f"只有 {d1[0]} 同时有 {MIN_AGENT} 个以上成功和失败（{d1[2]}/{d1[3]}），它自己的差是 {100 * d1[1]:+.1f} 个百分点；不到 2 家，不算平均"
                 if per else f"没有哪家 agent 在这里同时有 {MIN_AGENT} 个以上成功和失败，算不了同一 agent 内的差")
            body.append(f'<div class="crow wide"><span class="cl" title="{C.esc(name)}">{C.esc(name)}</span><span class="tupair">'
                        f'<span class="btrack"><span class="bfill" style="width:{100 * ps / top:.1f}%;background:var(--ok)" data-tip="{C.esc(ts)}"></span></span>'
                        f'<span class="btrack"><span class="bfill" style="width:{100 * pf / top:.1f}%;background:var(--n1)" data-tip="{C.esc(tf)}"></span></span></span>'
                        f'<span class="cv deflab" data-tip="{C.esc(dtip)}">{round(100 * ps)}% / {round(100 * pf)}%<small class="cside">同 agent {dtxt}</small></span></div>')
            table.append([C.esc(lab), C.esc(name), f"{100 * ps:.1f}%", f"{100 * pf:.1f}%", f"{100 * (ps - pf):+.1f}",
                          f"{100 * d:+.1f}" if d is not None else "–", str(len(per))])
            if d is not None:
                worst.append((abs(d), d, lab, name))
        ns += [(f"{lab} 成功", len(s)), (f"{lab} 失败", len(f))]
        few = "".join(f"<small class=few>{x}样本少</small>" for x, n in (("成功", len(s)), ("失败", len(f))) if n < C.SMALL)
        blocks.append(f'<div class="rblock"><p class="rtitle">{C.esc(lab)}（成功 {len(s)} 个 · 失败 {len(f)} 个 trial）{few}</p>'
                      f'{_head("成功 / 失败", "0", f"{round(50 * top)}%", f"{round(100 * top)}%")}{"".join(body)}</div>')
    lg = C.legend([("成功的 trial（评分通过）", "--ok"), ("失败的 trial", "--n1")])
    row = f"每张小图是{FG._row(by)}的" if by else "图里是"
    read = "绿条、红条 = 成功、失败 trial 里这一类调用占比的平均值；按日志归类。"
    note = (f"{row}{ALL_NOTE}；每个 trial 等权；右侧 = 两个平均值，其下 = 同一 agent 内成功减失败的差（百分点，各家等权平均）；成败由评分程序判定。"
            "合在一起比时，成功多的 agent 的习惯会被当成成功的特征（例如 GPT 各版的轮询记在其他命令里）；同一 agent 内的差排除了这一点，但没排除任务难度。"
            f"横轴到 {round(100 * top)}% 为止。" + (f"少于 {C.SMALL} 个 trial 的成功或失败组标「样本少」。" if any(n < C.SMALL for _, n in ns) else ""))
    worst.sort(reverse=True)
    say = ""
    if kv.get("lead") and worst:
        _, d, lab, name = worst[0]
        say = (f'<p class="figsay">同一 agent 内比较，成功和失败的各类调用占比相差最多 {abs(100 * d):.0f} 个百分点'
               f'（{lab} 的「{name}」，成功{"高" if d > 0 else "低"}）。</p>')
    return (say + C.howto(read) + f'<div class="chart">{lg}{"".join(blocks)}<p class="note">{C.esc(note)}</p></div>'
            + C.numbers(["", "工具类别", "成功（平均占比）", "失败（平均占比）", "差（百分点）", "同一 agent 内的差", "参与的 agent 数"], table))


# ------------------------------------------------------------------------------------------------------- page CSS

def css() -> str:
    """The time strip's ramp tokens (light, then the two dark-theme blocks) and the strip / pair-bar layout."""
    light, dark = "".join(f"{n}:{lo};" for n, lo, _ in TOKENS), "".join(f"{n}:{hi};" for n, _, hi in TOKENS)
    return (f':root{{{light}}}@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{{dark}}}}}'
            f':root[data-theme="dark"]{{{dark}}}'
            ".tupanels.multi{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:4px 26px}"
            ".tupanel{min-width:0;margin:6px 0 10px}.tupanel.small .rtitle{font-style:italic}.tupanel .rtitle .few{display:inline;margin-left:6px}"
            ".trow{display:grid;grid-template-columns:minmax(76px,130px) minmax(0,1fr) 52px;gap:8px;align-items:center;margin:2px 0}"
            ".tucells{display:grid;grid-template-columns:repeat(10,minmax(0,1fr));gap:2px}"
            ".tuc{display:block;height:20px;border-radius:2px;background:var(--sunk);color:var(--muted);text-align:center;"
            "font:10.5px/20px var(--f-mono);overflow:hidden;white-space:nowrap}"
            ".tuc.t1{background:var(--tt1);color:var(--ink)}.tuc.t2{background:var(--tt2);color:var(--ink)}"
            ".tuc.t3{background:var(--tt3);color:var(--q-ink-hi)}.tuc.t4{background:var(--tt4);color:var(--q-ink-hi)}"
            ".tuc.t5{background:var(--tt5);color:var(--q-ink-hi)}.tuc:hover,.tub:hover i{filter:brightness(1.12)}"
            ".tucalls .tub{display:flex;align-items:flex-end;height:16px;border-bottom:1px solid var(--line)}"
            ".tub i{display:block;width:100%;min-height:1px;background:var(--muted);border-radius:2px 2px 0 0}"
            ".tuax span{font-size:10.5px;color:var(--muted);text-align:center}.tuax .fewbin{font-style:italic}"
            ".tuhead .cv{font-family:var(--f-body);font-size:11px}"
            ".tuscale{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;font-size:12px;color:var(--ink-2);margin:6px 0}"
            ".tuscale i.tuc{display:inline-block;width:18px;height:12px;line-height:12px;margin-right:4px;vertical-align:-2px}"
            ".tuscale i.tubkey{display:inline-block;width:5px;height:12px;margin-right:4px;vertical-align:-2px;background:var(--muted);border-radius:2px 2px 0 0}"
            ".tupair{display:flex;flex-direction:column;gap:2px}.tupair .btrack{height:7px}"
            "@media (max-width:860px){.trow{grid-template-columns:78px minmax(0,1fr) 38px;gap:5px}.tuc{font-size:9.5px}}")


def figures(ctx) -> dict:
    return {"tooluse": lambda **kv: fig_tooluse(ctx, **kv), "tooltime": lambda **kv: fig_tooltime(ctx, **kv),
            "toolsucc": lambda **kv: fig_toolsucc(ctx, **kv)}
