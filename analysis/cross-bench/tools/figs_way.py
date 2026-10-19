"""Solving approach and outcome ({{fig:wayrate|by=mode}}, {{fig:waypair|by=mode}}), on the v17 approach families
(user decision 10-18, meta/OUTLINE.md): Code to Control (开环 / 闭环 / 搜索参数), Direct Control (the agent issues
commands step by step), Train Model to Control (a learned policy), 混合, 无. Names and definitions: figs.LOOP and the
codebook approach_zh.way_family (English family names from embodied-first-exam.ai, user 10-18), so every chart, legend
and hover note uses the same words.

Source: the approach labels (annot/approach, queries.ann_rows: valid trials of queries.load, the random sample).
A trial is Train Model to Control when its label lists the technique `rl` (codebook: 强化学习或训练神经网络策略),
whatever its loop; otherwise its `loop` decides. RoboSafeBench (rsb) is left out (OUTLINE v17).

Colours (a grouped set): the Code to Control members are one blue family (the --cat1 blue and a lighter and a deeper step,
--way-open / --way-search); the other families take clearly different slots (rust, magenta, gold), none is grey.
validate_palette.js in display order passes in both themes (light: adjacent normal ΔE ≥ 16.1, CVD ≥ 15.1; dark:
normal ≥ 15.6, CVD ≥ 11.1; every pair of the seven ≥ 15.6 apart). In the dark theme the band (L 0.48–0.67) is too
narrow for three steps of one blue, so the family runs teal → blue → indigo there."""
from __future__ import annotations
from collections import Counter, defaultdict
from itertools import combinations
import charts as C
import common
import figs as FG
import queries as Q

EXCLUDE = ("rsb", "ese")
NAMES = {"wayrate": "各种做法的成功率", "waypair": "同一任务上两种做法的成败对比"}      # chart titles (build.FIG_NAME)
_WF = FG.CB["approach_zh"]["way_family"]                                                  # {family: [name, definition, members]}
WAYS = FG.LOOP                                     # (code, name, colour, definition) in drawing order: the one source of names
FAMILY = {k: fk for fk, (_, _, ks) in _WF.items() for k in ks}
FAMILIES = [(fk, name, dict((x[0], x[2]) for x in WAYS)[ks[1] if len(ks) > 1 else ks[0]]) for fk, (name, _, ks) in _WF.items()]
GROUPS = [(_WF["code"][0], tuple(_WF["code"][2]))]                                        # the declared group (one hue family)
TRAIN = _WF["train"][0]
_sp = lambda name: name + " " if name[-1:].isascii() else name             # a space where a Latin name meets Chinese text
# (token, light, dark): the two steps of the blue family that are not a palette slot
TOKENS = [("--way-open", "#50c1fa", "#13a7a6"), ("--way-search", "#224fa7", "#4744d2")]


def css() -> str:
    """The way tokens (light, then the two dark-theme blocks) and the pair chart's middle line."""
    light, dark = "".join(f"{n}:{lo};" for n, lo, _ in TOKENS), "".join(f"{n}:{hi};" for n, _, hi in TOKENS)
    return (f':root{{{light}}}@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{{dark}}}}}'
            f':root[data-theme="dark"]{{{dark}}}'
            ".wayrate .crow{grid-template-columns:minmax(84px,190px) minmax(0,1fr) 118px}"
            "@media (max-width:860px){.wayrate .crow{grid-template-columns:96px minmax(0,1fr) 104px}}"
            ".wpwrap{position:relative;display:block}.wpmid{position:absolute;left:50%;top:-3px;bottom:-3px;width:0;"
            "border-left:1px dashed var(--ink-2)}")


def way(r: dict) -> str:
    """The approach of one approach row: Train Model to Control if its techniques list rl, else its loop ('' when unlabelled)."""
    if "rl" in (r.get("tech") or []):
        return "train"
    return r.get("loop") if r.get("loop") in FAMILY else ""


def way_rows(ctx, **kv) -> list[dict]:
    """Sampled approach rows (valid trials, rsb left out) matching the figure's filters, each with `way` and `family`."""
    rows = [{**r, "way": way(r)} for r in FG._filter(Q.ann_rows(ctx), kv) if r["bench"] not in EXCLUDE]
    return [{**r, "family": FAMILY[r["way"]]} for r in rows if r["way"]]


def _groups(rows, by, min_n):
    return FG._groups(rows, by, min_n) if by else [("全部", rows)]


def _rate_row(label, rs, color, tip_head) -> tuple[str, list]:
    """One bar row of a success rate: label · bar = k/n · "p%（k/n）" (样本少 under rows with n < SMALL)."""
    n, k = len(rs), Q.count(rs, lambda r: r["success"] == "1")
    p = k / n if n else 0
    small = n < C.SMALL
    tip = f"{tip_head}：{round(k)}/{n} 个抽样 trial 评分通过；比例的抽样误差约 ±{round(98 / n ** 0.5)} 个百分点"
    html = (f'<div class="crow wide{" small" if small else ""}"><span class="cl" title="{C.esc(label)}">{C.esc(label)}</span>'
            f'<span class="btrack"><span class="bfill" style="width:{100 * p:.1f}%;background:var({color})" data-tip="{C.esc(tip)}"></span></span>'
            f'<span class="cv deflab" data-tip="{C.esc(tip)}">{round(k)}/{n}{"<small class=few>样本少</small>" if small else ""}</span></div>')
    return html, [C.esc(label), str(n), f"{round(k)}/{n}"]


def fig_wayrate(ctx, by="mode", **kv):
    """Success rate by solving approach: one small chart per `by` group (mode by default), one row per approach with
    at least `min` (default 3) sampled trials; the table view adds each family's total."""
    rows, min_n = way_rows(ctx, **kv), int(kv.get("min", 3))
    blocks, table, few, lead = [], [], [], []
    for lab, rs in _groups(rows, by, 5):
        body, by_way = [], defaultdict(list)
        for r in rs:
            by_way[r["way"]].append(r)
        for k, name, color, _ in WAYS:
            mine = by_way.get(k, [])
            if len(mine) >= min_n:
                h, cells = _rate_row(name, mine, color, f"{lab} · {name}")
                body.append(h)
                table.append([C.esc(lab)] + cells)
                few += [name] if len(mine) < C.SMALL else []
            elif mine:
                few.append(f"{lab} 的{' ' if name[:1].isascii() else ''}{_sp(name)}只有 {len(mine)} 个，不画")
        for fk, fname, _ in FAMILIES[:1]:                   # the declared group's total, in the table view only
            fam = [r for r in rs if r["family"] == fk]
            if fam:
                k = Q.count(fam, lambda r: r["success"] == "1")
                table.append([C.esc(lab), f"{fname}（合计）", str(len(fam)), f"{round(k)}/{len(fam)}"])
        if body:
            axis = ('<div class="crow wide axis chead"><span class="cl"></span><span class="ticks"><span>0%</span><span>50%</span>'
                    '<span>100%</span></span><span class="cv">通过/抽样</span></div>')
            blocks.append(f'<div class="rblock"><p class="rtitle">{C.esc(lab)}（{len(rs)} 个抽样 trial）</p>{axis}{"".join(body)}</div>')
            fam_rate = lambda fk: (lambda fs: f"{round(Q.count(fs, lambda r: r['success'] == '1'))}/{len(fs)}" if len(fs) >= 5 else "")(
                [r for r in rs if r["family"] == fk])
            parts = [f"{n} {fam_rate(k)}" for k, n, _ in FAMILIES[:2] if fam_rate(k)]
            lead += [f"{lab}：" + "，".join(parts)] if parts else []
    if not blocks:
        return ""
    trained = sum(r["way"] == "train" for r in rows)
    drawn = [w for w in WAYS if w[1] in {row[1] for row in table}]
    grouped = {k for _, ks in GROUPS for k in ks}
    legs = [(g, [w for w in drawn if w[0] in ks]) for g, ks in GROUPS] + [("其他做法", [w for w in drawn if w[0] not in grouped])]
    lg = '<div class="plegs">' + "".join(f'<div class="pleg"><b>{C.esc(g)}</b>{C.legend([(w[1], w[2], w[3]) for w in ws])}</div>'
                                         for g, ws in legs if ws) + "</div>"
    note = ("这是相关，不是因果：难的任务本来就更常用某些做法；同一任务上的对比见下一张图。"
            f"{TRAIN} 按做法标签的技术字段 rl 认定，抽样里只有 {trained} 个。"
            + ("占比按层加权。" if common.WEIGHTS else "")
            + (f"标「样本少」的行少于 {C.SMALL} 个 trial，误差大，仅供参考。" if any("不画" not in x for x in few) else "")
            + "".join(f"{x}。" for x in few if "不画" in x))
    read = "条长 = 通过数/用这种做法的抽样 trial 数；做法由分析认定。"
    say = f'<p class="figsay">成功率 · {"；".join(lead)}。</p>' if kv.get("lead") and lead else ""
    return (say + C.howto(read) + f'<div class="chart wayrate">{lg}{"".join(blocks)}<p class="note">{C.esc(note)}</p></div>'
            + C.numbers(["", "做法", "抽样 trial", "通过"], table))


def pairs(rows) -> dict:
    """{(group, family a, family b): Counter(a = a passed and b failed, b = the reverse, same = both passed or both
    failed, tasks = tasks with a pair)} over every pair of trials on the same task (base + mode) whose families differ;
    a comes before b in FAMILIES. rows: [(group label, row)]."""
    order = [f[0] for f in FAMILIES]
    by_task = defaultdict(list)
    for g, r in rows:
        by_task[(g, r["base"], r["mode"])].append(r)
    out = defaultdict(Counter)
    for (g, _, _), rs in by_task.items():
        seen = set()
        for x, y in combinations(rs, 2):
            if x["family"] == y["family"]:
                continue
            if order.index(x["family"]) > order.index(y["family"]):
                x, y = y, x
            c = out[(g, x["family"], y["family"])]
            sx, sy = x["success"] == "1", y["success"] == "1"
            c["a" if sx and not sy else "b" if sy and not sx else "same"] += 1
            seen.add((x["family"], y["family"]))
        for a, b in seen:
            out[(g, a, b)]["tasks"] += 1
    return out


def fig_waypair(ctx, by="mode", **kv):
    """Within-task comparison: for each pair of approach families, among pairs of sampled trials on the same task
    (base + mode) that used the two families and had different outcomes, the share where each family passed. Bar =
    first family passed (its colour, from the left) | second family passed (its colour); the dashed line is 50 %."""
    rows = way_rows(ctx, **kv)
    groups = _groups(rows, by, 5)
    cnt = pairs([(lab, r) for lab, rs in groups for r in rs])
    fam = {k: (n, c) for k, n, c in FAMILIES}
    blocks, table, few, lead, drawn, skipped, min_n = [], [], False, [], set(), 0, int(kv.get("min", 3))
    for lab, _ in groups:
        body = []
        for (a, _, _), (b, _, _) in combinations(FAMILIES, 2):
            c = cnt.get((lab, a, b))
            if not c:
                continue
            n = c["a"] + c["b"]
            (na, ca), (nb, cb) = fam[a], fam[b]
            name = f"{na} vs {nb}"
            if n < min_n:
                table.append([C.esc(lab), C.esc(name), str(n), f"{c['a']}/{n}", f"{c['b']}/{n}",
                              str(c["same"]), str(c["tasks"])])
                skipped += 1
                continue
            drawn |= {a, b}
            small = n < C.SMALL
            few |= small
            ta = f"{lab} · {name}：{_sp(na)}通过、{_sp(nb)}没过 {c['a']}/{n} 对"
            tb = f"{lab} · {name}：{_sp(nb)}通过、{_sp(na)}没过 {c['b']}/{n} 对"
            side = f"同成败 {c['same']} 对"
            tip = f"成败不同的 {n} 对，来自 {c['tasks']} 个任务；另有 {c['same']} 对两个都过或都没过（不计入条）"
            body.append(f'<div class="crow wide{" small" if small else ""}"><span class="cl" title="{C.esc(name)}">{C.esc(name)}</span>'
                        f'<span class="wpwrap"><span class="track">'
                        + (f'<span class="seg" style="width:{100 * c["a"] / n:.2f}%;background:var({ca})" data-tip="{C.esc(ta)}"></span>' if c["a"] else "")
                        + (f'<span class="seg" style="width:{100 * c["b"] / n:.2f}%;background:var({cb})" data-tip="{C.esc(tb)}"></span>' if c["b"] else "")
                        + f'</span><span class="wpmid"></span></span>'
                        f'<span class="cv deflab" data-tip="{C.esc(tip)}">{n}{"<small class=few>样本少</small>" if small else ""}'
                        f'<small class="cside">{C.esc(side)}</small></span></div>')
            table.append([C.esc(lab), C.esc(name), str(n), f"{c['a']}/{n}", f"{c['b']}/{n}",
                          str(c["same"]), str(c["tasks"])])
            if a == "code" and b == "direct" and n >= 5:
                lead.append(f"{lab}：{_sp(na)}过、{_sp(nb)}没过 {c['a']} 对，反过来 {c['b']} 对")
        if body:
            axis = ('<div class="crow wide axis chead"><span class="cl"></span><span class="ticks"><span>前者通过</span><span>50%</span>'
                    '<span>后者通过</span></span><span class="cv">成败不同的对数</span></div>')
            blocks.append(f'<div class="rblock"><p class="rtitle">{C.esc(lab)}</p>{axis}{"".join(body)}</div>')
    if not blocks:
        return ""
    lg = C.legend([(n, c) for k, n, c in FAMILIES if k in drawn])
    read = "左段 = 前一种做法赢的对数/成败不同的对数，右段反之。"
    note = ("一对 = 同一任务（含模式）上分别用了这两种做法、成败不同的两个抽样 trial；虚线 = 50%；右侧 = 成败不同的对数，"
            "其下 = 两个都过或都没过的对数；做法由分析认定，成败由评分程序判定。同一任务上比较，任务难度相同；但同一任务上的两个 trial 通常来自不同的 agent，agent 的强弱没有排除。"
            f"一个任务上有多个 trial 时每两个都配对，trial 多的任务分量大；对数不加权。{_WF['code'][0]} 包括开环、闭环和搜索参数。"
            + (f"标「样本少」的行少于 {C.SMALL} 对，误差大，仅供参考。" if few else "")
            + (f"成败不同的不到 {min_n} 对的 {skipped} 行不画，数字在「看数字」里。" if skipped else ""))
    say = f'<p class="figsay">{"；".join(lead)}。</p>' if kv.get("lead") and lead else ""
    return (say + C.howto(read) + f'<div class="chart">{lg}{"".join(blocks)}<p class="note">{C.esc(note)}</p></div>'
            + C.numbers(["", "两种做法", "成败不同的对数", "前者通过", "后者通过", "同成败的对数", "任务数"], table))


def figures(ctx) -> dict:
    return {"wayrate": lambda **kv: fig_wayrate(ctx, **kv), "waypair": lambda **kv: fig_waypair(ctx, **kv)}
