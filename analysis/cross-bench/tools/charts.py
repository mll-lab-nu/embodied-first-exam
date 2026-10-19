"""HTML chart fragments (CSS bars, no library). Every chart carries a legend, hover tips (`data-tip`) and a table view.

Every chart starts with a 怎么读 line (`howto`): what one row is, what the bar or cell shows, what the number counts
and who judged it. Colours come from palette.py (meta/DESIGN.md → Colours): a chart's categories take the palette slots
in fixed order (`--cat1`, `--cat2`, …), `--c0` is other / none, valence charts keep success `--ok` green and failure
`--n1` red; heat tables shade by magnitude (`p` / `w` / `q`). The page template styles `.chart`.

Labels and hover notes give counts, k/n (user 10-18 night: 「分析过的 140 个失败里，主因是抓取的有 41 个」), never a percent;
bars and shading are still drawn by share. Each 怎么读 line says what one unit is and what the bar is a share of.
fmt=pct (user 10-19, main findings): a chart's visible value is the integer percent; tips and 看数字 keep k/n.
"""
from __future__ import annotations
import html
import re
import common

esc = lambda s: html.escape(str(s), quote=True)
MODE_CLS = {"privileged": " m-priv", "standard": " m-std", "realtime": " m-rt"}        # mode rows wear the mode tint


def _pct(k, n) -> str:
    return f"{round(100 * k / n)}%" if n else "–"


def kn(k, n) -> str:
    """A count label: "k/n" (k rounded: weighted tallies may be fractional), "–" without a denominator."""
    return f"{round(k)}/{round(n)}" if n else "–"


def value(k, n, fmt: str = "") -> str:
    """A chart's visible value label: "k/n" (default) or, fmt=pct, the integer percent ("37%"); the hover tip and the
    看数字 table keep k/n either way."""
    return f"{100 * k / n:.0f}%" if fmt == "pct" and n else kn(k, n)


PCT_MIN = .08                                                # fmt=pct stacks: narrower segments keep their number in the tip only
SMALL = 20                                                   # rows sampled from fewer reviews are marked 样本少 (colours stay full)
FEW_AGENTS = ("GPT-6 Sol", "GPT-6.1 Sol", "Qwen3.8 27B")     # ran only a small batch of the evaluation items


def _ncell(n: int, sample: bool) -> str:
    """The count column: for sampled rows, the tip says how far a share can be off (95% interval half-width at 50%)."""
    if not sample:
        return f'<span class="cv">{n}</span>'
    tip = f"抽样分析过 {n} 个 trial；比例的抽样误差约 ±{round(98 / n ** 0.5)} 个百分点" + ("，样本少，仅供参考" if n < SMALL else "")
    few = '<small class="few">样本少</small>' if n < SMALL else ""
    return f'<span class="cv deflab" data-tip="{tip}">{n}{few}</span>'


def _head(unit: str, count: bool = True) -> str:
    """Scale row above 100% bars: every bar is the whole row (0–100%), whatever its n; count=False: no count column."""
    return (f'<div class="crow axis chead"><span class="cl"></span><span class="ticks"><span>0%</span><span>50%</span>'
            f'<span>100%</span></span>' + (f'<span class="cv">{esc(unit)}</span>' if count else "") + '</div>')


def _few_text(rows: list) -> str:
    """The note for 样本少 rows: what the tag means, and (once) why the Sol / Qwen rows have few trials.
    rows: [(label, n)] of the sampled rows."""
    few = [lab for lab, n in rows if n < SMALL]
    if not few:
        return ""
    why = "两版 Sol 和 Qwen 只跑了一小批评测项，抽到的 trial 少。" if any(a in lab for lab in few for a in FEW_AGENTS) else ""
    return f"标「样本少」的行少于 {SMALL} 个 trial，误差大，仅供参考。{why}"


def _small_note(rows: list, sample: bool) -> str:
    """What the 怎么读 line does not say: weighting and 样本少 rows (the row, bar and count are in the 怎么读 line)."""
    parts = (["占比按层加权。"] if sample and common.WEIGHTS else []) + ([_few_text(rows)] if sample and _few_text(rows) else [])
    return f'<p class="note">{"".join(parts)}</p>' if parts else ""


def howto(text: str) -> str:
    """The 怎么读 line right under a chart's title: what one row is, what the bar or cell shows, what the number counts
    and who judged it. Every figure passes one (figs.py builds it from the figure and its rows)."""
    return f'<p class="howto"><b>怎么读</b>{esc(text)}</p>' if text else ""


def legend(items: list[tuple]) -> str:
    """items: (label, color var) or (label, color var, definition). With definitions the legend is a visible glossary
    (name：definition per item), so no term needs a hover to be understood."""
    if any(len(it) > 2 and it[2] for it in items):
        return '<dl class="legend defs">' + "".join(f'<div><dt><i style="background:var({it[1]})"></i>{esc(it[0])}</dt>'
                                                     f'<dd>{esc(it[2]) if len(it) > 2 else ""}</dd></div>' for it in items) + "</dl>"
    return '<div class="legend">' + "".join(f'<span><i style="background:var({it[1]})"></i>{esc(it[0])}</span>' for it in items) + "</div>"


def bars(blocks: list[tuple[str, list[tuple]]], note: str = "", color: str = "--cat1", read: str = "",
         colors: dict | None = None, keys: list[tuple] | None = None, fmt: str = "", label: bool = True, cls: str = "") -> str:
    """Small multiples of 0–100% bars. blocks: [(metric title, [(row label, share 0..1, value text, tip)])].
    colors: {row label: colour var} (default `color` for every row); keys: legend items (label, colour var).
    fmt=pct: the visible value is the integer percent; value text (k/n) stays in the tip and the table.
    label=False: no value column at all (class nocount; the tip and the table keep the value).
    cls: extra classes on the chart (" compact": thin bars, tight rows)."""
    out, table = [], []
    shown = lambda v, txt: f"{100 * v:.0f}%" if fmt == "pct" else txt
    for title, rows in blocks:
        if not rows:
            continue
        body = "".join(f'<div class="crow"><span class="cl{MODE_CLS.get(lab, "")}" title="{esc(lab)}">{esc(lab)}</span><span class="btrack">'
                       f'<span class="bfill" style="width:{100 * v:.1f}%;background:var({(colors or {}).get(lab, color)})" data-tip="{esc(tip)}"></span></span>'
                       + (f'<span class="cv">{esc(shown(v, txt))}</span>' if label else "") + '</div>' for lab, v, txt, tip in rows)
        head = f'<p class="rtitle">{esc(title)}</p>' if title else ""         # no title: a panel's only block
        out.append(f'<div class="rblock">{head}{body}</div>')
        table += [[esc(title), esc(lab), esc(txt)] for lab, v, txt, tip in rows]
    if not out:
        return ""
    return (howto(read) + f'<div class="chart{cls}{"" if label else " nocount"}">{legend(keys) if keys else ""}{"".join(out)}{f"<p class=note>{esc(note)}</p>" if note else ""}</div>'
            + numbers(["指标", "", "值"], table))


def numbers(head: list[str], rows: list[list[str]]) -> str:
    """The table view behind a chart (folded)."""
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td{' class=num' if i else ''}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<details class="more"><summary>看数字</summary><div class="scroll"><table class="t"><tr>{th}</tr>{tr}</table></div></details>'


def stack(rows: list[tuple[str, dict]], keys: list[tuple[str, str, str]], note: str = "", min_n: int = 1,
          unit: str = "n", sample: bool = False, read: str = "", side: tuple | None = None, extra: dict | None = None,
          fmt: str = "", label: bool = True, cls: str = "", count: bool = True) -> str:
    """100% stacked bars. rows: [(label, {key: count})]; keys: [(key, label, color var)] in stacking order.
    sample=True: the rows come from sampled reviews (rows below SMALL are tagged 样本少, error margin in the count tip).
    side: (column head, {row label: (short text, tip)}): a second number printed under each row's count (e.g. a
    median), and a table column.
    extra: {(row label, key): text}: a clause added to that segment's tip and table cell (e.g. its success share).
    fmt=pct: each segment of at least PCT_MIN of the row prints its integer percent inside (k/n stays in tip and table).
    label=False: no value inside the segments (tip and table keep k/n).
    cls: extra classes on the chart (" compact": thin bars, tight rows). count=False: no count column (class nocount;
    for rows that all have the same n, which the caller says once; the table keeps it)."""
    body, table, ns = [], [], []
    show_values = label                                       # the loop below reuses the name `label` for the row label
    more = lambda label, k: f"；{extra[(label, k)]}" if extra and (label, k) in extra else ""
    keys3 = [(k[0], k[1], k[2]) for k in keys]
    for label, counts in rows:
        n = round(sum(counts.get(k, 0) for k, _, _ in keys3))     # counts may be weighted (queries.tally)
        if n < min_n:
            continue
        inside = lambda k: f'<b class="sv">{value(counts[k], n, fmt)}</b>' if show_values and fmt == "pct" and counts[k] / n >= PCT_MIN else ""
        segs = "".join(f'<span class="seg" style="width:{100 * counts[k] / n:.2f}%;background:var({c})" '
                       f'data-tip="{esc(label)} · {esc(l)} {kn(counts[k], n)}{esc(more(label, k))}">{inside(k)}</span>'
                       for k, l, c in keys3 if counts.get(k))
        ns.append((label, n))
        cell, (st, stip) = _ncell(n, sample), (side[1] if side else {}).get(label, ("", ""))
        if st:
            cell = cell[:-len("</span>")] + f'<small class="cside" data-tip="{esc(stip)}">{esc(st)}</small></span>'
        body.append(f'<div class="crow{" small" if sample and n < SMALL else ""}"><span class="cl{MODE_CLS.get(label, "")}" title="{esc(label)}">{esc(label)}</span><span class="track">{segs}</span>{cell if count else ""}</div>')
        table.append([esc(label), str(n)] + ([esc(st)] if side else []) + [f"{kn(counts.get(k, 0), n)}{esc(more(label, k))}" for k, _, _ in keys3])
    if not body:
        return ""
    return (howto(read) + f'<div class="chart{" pct" if fmt == "pct" else ""}{cls}{"" if count else " nocount"}">{legend([(k[1], k[2], k[3] if len(k) > 3 else "") for k in keys])}{_head(unit, count)}{"".join(body)}'
            f'{_small_note(ns, sample)}{f"<p class=note>{esc(note)}</p>" if note else ""}</div>'
            + numbers(["", unit] + ([esc(side[0])] if side else []) + [esc(k[1]) for k in keys], table))


def heat(rows: list[tuple[str, int, dict]], cols: list[tuple[str, str]], note: str = "", unit: str = "n", sample: bool = False,
         tone: str = "", read: str = "") -> str:
    """Share table shaded by magnitude (multi-label shares that do not sum to 100%). rows: [(label, n, {col: k})]."""
    th = "".join(f'<th>{esc(c[1])}</th>' for c in cols)
    cols_def, cols = cols, [(c[0], c[1]) for c in cols]
    out = []
    for label, n, counts in rows:
        tds = []
        for c, l in cols:
            k = counts.get(c, 0)
            p = k / n if n else 0
            step = 0 if not k else min(5, 1 + int(p * 5))
            ramp = {"pos": "p", "neg": "w"}.get(tone, "q") if step else "q"        # green for good shares, warm for failures
            tds.append(f'<td class="hc {ramp}{step}" data-tip="{esc(label)} · {esc(l)} {kn(k, n)}">{kn(k, n) if k else "·"}</td>')
        small = " small" if sample and n < SMALL else ""
        out.append(f'<tr class="{small.strip()}"><th scope="row"{" class=" + chr(34) + MODE_CLS[label].strip() + chr(34) if label in MODE_CLS else ""}>{esc(label)}</th><td class="num">{_ncell(n, sample).replace("span class=" + chr(34) + "cv", "span class=" + chr(34))}</td>{"".join(tds)}</tr>')
    gloss = [(c[1], "--q3", c[2]) for c in cols_def if len(c) > 2 and c[2]]
    note = (("占比按层加权。" if common.WEIGHTS else "") + _few_text([(lab, n) for lab, n, _ in rows]) + note) if sample else note
    return (howto(read) + f'<div class="scroll"><table class="t heat"><tr><th></th><th class="num">{esc(unit)}</th>{th}</tr>{"".join(out)}</table></div>'
            + (legend(gloss).replace('<i style="background:var(--q3)"></i>', "") if gloss else "")
            + (f'<p class="note">{esc(note)}</p>' if note else ""))


def hist(rows: list[tuple[str, list[tuple[float, str]]]], keys: list[tuple], bins: int = 10,
         axis: tuple[str, str] = ("0", "时限"), note: str = "", read: str = "") -> str:
    """Small-multiple histograms on a shared 0–1 axis, stacked by category. rows: [(label, [(x in 0..1, key)])]."""
    body, table = [], []
    for label, pts in rows:
        if not pts:
            continue
        grid = [{k[0]: 0 for k in keys} for _ in range(bins)]
        for x, k in pts:
            grid[min(bins - 1, max(0, int(x * bins)))][k] = grid[min(bins - 1, max(0, int(x * bins)))].get(k, 0) + 1
        top = max(sum(g.values()) for g in grid) or 1
        cols = []
        for i, g in enumerate(grid):
            segs = "".join(f'<i style="height:{100 * g[k] / top:.1f}%;background:var({c})"></i>' for k, _, c, *_ in keys if g.get(k))
            tip = f'{esc(label)} · {i * 100 // bins}–{(i + 1) * 100 // bins}%：' + "，".join(f"{l} {g[k]}" for k, l, *_ in keys if g.get(k))
            cols.append(f'<span class="hb" data-tip="{tip}">{segs}</span>')
        body.append(f'<div class="crow"><span class="cl{MODE_CLS.get(label, "")}" title="{esc(label)}">{esc(label)}</span><span class="htrack">{"".join(cols)}</span><span class="cv">{len(pts)}</span></div>')
        table.append([esc(label), str(len(pts))] + [str(sum(1 for _, k in pts if k == kk[0])) for kk in keys])
    if not body:
        return ""
    ax = f'<div class="crow axis"><span class="cl"></span><span class="ticks"><span>{esc(axis[0])}</span><span>50%</span><span>{esc(axis[1])}</span></span><span class="cv"></span></div>'
    return (howto(read) + f'<div class="chart">{legend([(k[1], k[2], k[3] if len(k) > 3 else "") for k in keys])}{"".join(body)}{ax}'
            f'{f"<p class=note>{esc(note)}</p>" if note else ""}</div>' + numbers(["", "n"] + [esc(k[1]) for k in keys], table))


def lanes(rows: list[tuple[str, int, dict, tuple | None]], marks: list[tuple[str, str, str]], axis=("0", "时限"), note: str = "",
          read: str = "") -> str:
    """Timeline lanes: per row, median positions (0..1) of events; band = interquartile range of the end.
    rows: [(label, n, {mark: median or None}, (q1, q3) or None)]; marks: [(key, label, color var)]."""
    body, table = [], []
    for label, n, med, band in rows:
        b = f'<span class="band" style="left:{100 * band[0]:.1f}%;width:{100 * (band[1] - band[0]):.1f}%" data-tip="{esc(label)} · 结束时刻的中间一半：{round(100 * band[0])}–{round(100 * band[1])}%"></span>' if band else ""
        pins = "".join(f'<span class="pin" style="left:{100 * med[k]:.1f}%;background:var({c})" data-tip="{esc(label)} · {esc(l)}：中位数 {round(100 * med[k])}%"></span>'
                       for k, l, c in marks if med.get(k) is not None)
        body.append(f'<div class="crow"><span class="cl{MODE_CLS.get(label, "")}" title="{esc(label)}">{esc(label)}</span><span class="ltrack">{b}{pins}</span><span class="cv">{n}</span></div>')
        table.append([esc(label), str(n)] + [f"{round(100 * med[k])}%" if med.get(k) is not None else "–" for k, _, _ in marks])
    if not body:
        return ""
    ax = f'<div class="crow axis"><span class="cl"></span><span class="ticks"><span>{esc(axis[0])}</span><span>50%</span><span>{esc(axis[1])}</span></span><span class="cv"></span></div>'
    lg = legend([(l, c) for _, l, c in marks]).replace("</div>", '<span><i class="bandkey"></i>结束时刻（中间一半）</span></div>')
    return (howto(read) + f'<div class="chart">{lg}{"".join(body)}{ax}{f"<p class=note>{esc(note)}</p>" if note else ""}</div>'
            + numbers(["", "n"] + [esc(l) for _, l, _ in marks], table))


def ranges(blocks: list[tuple[str, list[tuple[str, int, tuple]]]], note: str = "", read: str = "") -> str:
    """Small multiples of median + interquartile range on a log axis (counts per trial).
    blocks: [(metric label, [(row label, n, (q1, median, q3))])]."""
    import math
    vals = [v for _, rows in blocks for _, _, q in rows for v in q if v and v > 0]
    if not vals:
        return ""
    lo, hi = 0, math.ceil(math.log10(max(vals) + 1))
    pos = lambda v: 100 * (math.log10(max(v, 1)) - lo) / (hi - lo or 1)
    ticks = "".join(f'<span style="left:{pos(10 ** e):.1f}%">{10 ** e:,}</span>' for e in range(lo, hi + 1))
    out, table = [], []
    for title, rows in blocks:
        body = []
        for label, n, (q1, m, q3) in rows:
            body.append(f'<div class="crow"><span class="cl{MODE_CLS.get(label, "")}" title="{esc(label)}">{esc(label)}</span><span class="rtrack">'
                        f'<span class="rbar" style="left:{pos(q1):.1f}%;width:{max(pos(q3) - pos(q1), 0.6):.1f}%"></span>'
                        f'<span class="rdot" style="left:{pos(m):.1f}%" data-tip="{esc(label)} · {esc(title)}：中位数 {m:.0f}，中间一半 {q1:.0f}–{q3:.0f}（{n} 个 trial）"></span>'
                        f'</span><span class="cv">{m:.0f}</span></div>')
            table.append([esc(title), esc(label), str(n), f"{q1:.0f}", f"{m:.0f}", f"{q3:.0f}"])
        out.append(f'<div class="rblock"><p class="rtitle">{esc(title)}</p>{"".join(body)}'
                   f'<div class="crow axis"><span class="cl"></span><span class="lticks">{ticks}</span><span class="cv"></span></div></div>')
    lg = '<div class="legend"><span><i style="background:var(--ink)"></i>中位数</span><span><i class="bandkey"></i>中间一半的 trial</span><span>横轴是对数刻度</span></div>'
    return (howto(read) + f'<div class="chart">{lg}{"".join(out)}{f"<p class=note>{esc(note)}</p>" if note else ""}</div>'
            + numbers(["指标", "", "n", "下四分位", "中位数", "上四分位"], table))


def phased(rows: list[tuple[str, int, dict]], groups: list[tuple[str, list[tuple]]], note: str = "", unit: str = "抽样 trial",
           sample: bool = True, read: str = "") -> str:
    """100% stacked bars whose keys fall into ordered groups (e.g. 动手之前 | 动手时 | 收尾): each row draws its own
    dividers where its groups meet and prints each group's share above its span. rows: [(label, n, {key: count})];
    groups: [(group label, [(key, label, color var, definition)])]."""
    body, table, ns = [], [], []
    for label, n, c in rows:
        if not n:
            continue
        ns.append((label, n))
        segs, marks, x = [], [], 0.0
        for g, ks in groups:
            k_g = sum(c.get(k[0], 0) for k in ks)
            w = 100 * k_g / n
            segs += [f'<span class="seg" style="width:{100 * c[k[0]] / n:.2f}%;background:var({k[2]})" '
                     f'data-tip="{esc(label)} · {esc(g)} · {esc(k[1])} {kn(c[k[0]], n)}"></span>' for k in ks if c.get(k[0])]
            if k_g and w >= 11:                              # room for a "k/n" label
                marks.append(f'<span class="gpct" style="left:{x:.2f}%;width:{w:.2f}%" data-tip="{esc(label)} · {esc(g)} {kn(k_g, n)}">{kn(k_g, n)}</span>')
            x += w
            if k_g and 0.5 < x < 99.5:
                marks.append(f'<span class="gline" style="left:{x:.2f}%"></span>')
        body.append(f'<div class="crow phrow{" small" if sample and n < SMALL else ""}"><span class="cl{MODE_CLS.get(label, "")}" title="{esc(label)}">{esc(label)}</span>'
                    f'<span class="phwrap"><span class="track">{"".join(segs)}</span>{"".join(marks)}</span>{_ncell(n, sample)}</div>')
        table.append([esc(label), str(n)] + [kn(sum(c.get(k[0], 0) for k in ks), n) for _, ks in groups])
    if not body:
        return ""
    lg = "".join(f'<div class="pleg"><b>{esc(g)}</b>{legend([(k[1], k[2], k[3] if len(k) > 3 else "") for k in ks])}</div>' for g, ks in groups)
    return (howto(read) + f'<div class="chart"><div class="plegs">{lg}</div>{_head(unit)}{"".join(body)}'
            f'{_small_note(ns, sample)}{f"<p class=note>{esc(note)}</p>" if note else ""}</div>' + numbers(["", unit] + [esc(g) for g, _ in groups], table))


def counts(rows: list[tuple[str, dict, str]], keys: list[tuple], note: str = "", read: str = "", total: int = 0) -> str:
    """Horizontal bars of absolute counts, stacked by key, on one scale (for rankings). rows: [(label, {key: count}, tip)].
    total > 0: each count also shows that total, as 178/640."""
    top = max([sum(c.values()) for _, c, _ in rows] + [1])
    body, table = [], []
    for label, c, tip in rows:
        n = round(sum(c.get(k[0], 0) for k in keys))
        segs = "".join(f'<span class="seg" style="width:{100 * c[k[0]] / top:.2f}%;background:var({k[2]})" data-tip="{esc(label)} · {esc(k[1])} {round(c[k[0]])}"></span>'
                       for k in keys if c.get(k[0]))
        lab = f'<span class="cl deflab" data-tip="{esc(tip)}" title="{esc(label)}">' if tip else f'<span class="cl" title="{esc(label)}">'
        shown = kn(n, total) if total else str(n)
        body.append(f'<div class="crow{" wide" if total else ""}">{lab}{esc(label)}</span><span class="ctrack">{segs}</span><span class="cv">{shown}</span></div>')
        table.append([esc(label), shown] + [str(round(c.get(k[0], 0))) for k in keys])
    if not body:
        return ""
    gloss = [(label, "--q3", tip) for label, _, tip in rows if tip]          # what each row means, printed, not hover-only
    return (howto(read) + f'<div class="chart">{legend([(k[1], k[2], k[3] if len(k) > 3 else "") for k in keys])}{"".join(body)}'
            + (legend(gloss).replace('<i style="background:var(--q3)"></i>', "") if gloss else "")
            + f'{f"<p class=note>{esc(note)}</p>" if note else ""}</div>' + numbers(["", "合计"] + [esc(k[1]) for k in keys], table))


def lines(panels: list[tuple[str, list[tuple]]], xs: list[float], note: str = "", read: str = "", hover: int = 5,
          ticks: tuple = ("0", "25%", "50%", "75%", "时限"), table_at: tuple = (0.1, 0.25, 0.5, 0.75, 1.0)) -> str:
    """Small-multiple line charts: x = 0..1 (share of the time limit), one y axis 0–100% (share of trials).
    panels: [(title, [(series label, color var, n, [y 0..1 at each x of xs])])]. Marks follow the dataviz spec: 2px
    lines, end dots with a surface ring, direct end labels when ≤ 4 series end at least 12 points apart (else the legend
    and tooltip carry them), a crosshair column every `hover` % whose tip lists every series there, a line-key legend
    with each series' n, and the numbers at `table_at` in the table view."""
    at = lambda ys, x: ys[min(range(len(xs)), key=lambda i: abs(xs[i] - x))]
    series = {}
    out, table = [], []
    for title, ss in panels:
        if not ss:
            continue
        paths = "".join(f'<path d="M{" L".join(f"{100 * x:.2f},{100 - 100 * y:.2f}" for x, y in zip(xs, ys))}" '
                        f'style="stroke:var({c})" vector-effect="non-scaling-stroke"/>' for _, c, _, ys in ss)
        ends = sorted(ys[-1] for _, _, _, ys in ss)
        direct = len(ss) <= 4 and all(b - a >= 0.12 for a, b in zip(ends, ends[1:]))
        dots = "".join(f'<span class="ldot" style="top:{100 - 100 * ys[-1]:.1f}%;background:var({c})"></span>' for _, c, _, ys in ss)
        labs = "".join(f'<span class="llab" style="top:{100 - 100 * ys[-1]:.1f}%">{esc(lab)} {kn(ys[-1] * n, n)}</span>' for lab, _, n, ys in ss) if direct else ""
        cols = []
        for i in range(0, 101, hover):
            x = i / 100
            tip = f"{esc(title)} · 到时限的 {i}% 时：" + "；".join(f"{esc(lab)} {kn(at(ys, x) * n, n)}" for lab, _, n, ys in ss)
            lo, hi = max(0.0, x - hover / 200), min(1.0, x + hover / 200)
            cols.append(f'<span class="lhit" style="left:{100 * lo:.2f}%;width:{100 * (hi - lo):.2f}%" data-tip="{tip}">'
                        f'<i style="left:{100 * (x - lo) / (hi - lo):.1f}%"></i></span>')
        grid = "".join(f'<span class="lgrid" style="top:{t}%"></span>' for t in (0, 50, 100))
        yax = '<span class="lyt" style="top:0">100%</span><span class="lyt" style="top:50%">50%</span><span class="lyt" style="top:100%">0</span>'
        xax = "".join(f"<span>{esc(t)}</span>" for t in ticks)
        out.append(f'<div class="lpanel"><p class="rtitle">{esc(title)}</p><div class="lplot">{yax}<div class="lbox">{grid}'
                   f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{paths}</svg>{dots}{"".join(cols)}</div>{labs}</div>'
                   f'<div class="lax">{xax}</div></div>')
        for lab, c, n, ys in ss:
            series.setdefault(lab, (c, n))
            table.append([esc(title), esc(lab), str(n)] + [kn(at(ys, x) * n, n) for x in table_at])
    if not out:
        return ""
    lg = '<div class="legend">' + "".join(f'<span><i class="lkey" style="background:var({c})"></i>{esc(lab)}</span>' for lab, (c, _) in series.items()) + "</div>"
    note = note + "线末和提示里的数字 = 到这个时刻已发生的 trial 数/这条线的 trial 数。"     # the 怎么读 line stays one sentence
    return (howto(read) + f'<div class="chart">{lg}<div class="lpanels">{"".join(out)}</div>{f"<p class=note>{esc(note)}</p>" if note else ""}</div>'
            + numbers(["", "", "n"] + [f"时限的 {round(100 * x)}%" for x in table_at], table))


_HOWTO = re.compile(r'<p class="howto">.*?</p>', re.S)
_LEGEND = re.compile(r'<div class="legend">.*?</div>|<dl class="legend defs">.*?</dl>', re.S)
_TABLE = re.compile(r'<details class="more"><summary>看数字</summary>(.*?)</details>', re.S)


def panels(parts: list[tuple[str, str]], read: str = "", note: str = "") -> str:
    """Charts of one kind side by side (one per mode; they stack at phone width): parts = [(panel title html, chart html
    as stack / bars / … return it)]. One 怎么读 line and one legend (the first chart's) above the panels, the note under
    them, and one 看数字 with each panel's table under its title."""
    parts = [(t, h) for t, h in parts if h]
    if not parts:
        return ""
    lg = _LEGEND.search(parts[0][1])
    body, tables = [], []
    for title, h in parts:
        t = _TABLE.search(h)
        tables.append(f'<p class="rtitle">{title}</p>{t.group(1)}' if t else "")
        h = _LEGEND.sub("", _HOWTO.sub("", _TABLE.sub("", h), count=1), count=1)
        body.append(f'<div class="mpanel"><p class="rtitle">{title}</p>{h}</div>')
    return (howto(read) + f'<div class="chart mcharts">{lg.group(0) if lg else ""}<div class="mpanels">{"".join(body)}</div>'
            + (f'<p class="note">{esc(note)}</p>' if note else "") + "</div>"
            + f'<details class="more"><summary>看数字</summary>{"".join(tables)}</details>')
