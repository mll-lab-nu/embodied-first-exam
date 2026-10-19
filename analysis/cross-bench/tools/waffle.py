"""fig:waffle: the headline subset (queries.overlap_cells: graded for all six main agents), one 10 x 10 panel per mode;
one square = about 1 % of that mode's evaluation items (squares()). A square's style says which of the three agents
(queries.TRIO) solved its group: all three soft charcoal (style.css --wf-all3); two agents a diagonal split of their
colours; one agent its colour; none light grey. Groups run in GROUPS order (the ones with Astra first), row by row.
Above each grid: the three agents' totals as small bars. Hover a square: its group, k/n and a few of its tasks; click
a square: the group's tasks are listed under the panels, by benchmark (app.js wafShow)."""
from __future__ import annotations
import html
import json
import charts as C
import figs as FG
import palette as PL
import queries as Q

NAMES = {"waffle": "三家各做成了哪些评测项（六家都评过分的同一批）"}   # build.py captions through Q.batch_words
GROUPS = [("all3", "三家都做成"), ("astra+opus", "Astra + Opus"), ("astra+argon", "Astra + Argon"), ("astra", "只有 Astra"),
          ("argon+opus", "Argon + Opus"), ("opus", "只有 Opus"), ("argon", "只有 Argon"), ("none", "都没做成")]
CELLS = 100                                              # 10 x 10 squares per panel (style.css .wgrid)
SHOWN = 3                                                # task names in a square's hover note
TT = list(FG.ATLAS_ZH["tasktype"])                       # Atlas task types: task order within a group
esc = lambda s: html.escape(str(s), quote=True)


def color() -> dict:
    """TRIO key -> the agent's own chart colour token (palette.AGENT, as figs.TRIO_COLOR)."""
    return {k: PL.AGENT[a][0] for k, a in Q.TRIO.items()}


def square(combo: str, extra: str = "") -> str:
    return f'<i class="wq g-{combo.replace("+", "-")}"{extra}></i>'


def by_type(row: dict) -> tuple:
    t = (row.get("tasktype") or [Q.UNCLASSIFIED])[0]
    return (TT.index(t) if t in TT else len(TT), Q.task_parts(row))


def squares(count: dict) -> dict:
    """Group -> squares out of CELLS by largest-remainder rounding (sum exactly CELLS). A group with at least one item
    whose share rounds to 0 squares (under about 0.5 %) still gets 1 square so that it stays visible; that square is
    taken from the largest group."""
    n = sum(count.values())
    exact = {g: CELLS * c / n for g, c in count.items()}
    got = {g: int(x) for g, x in exact.items()}
    for g in sorted(exact, key=lambda g: got[g] - exact[g])[:CELLS - sum(got.values())]:
        got[g] += 1
    for g in [g for g, c in count.items() if c and not got[g]]:
        got[g], top = 1, max(got, key=got.get)
        got[top] -= 1
    return got


def panel(m: str, cells: dict) -> tuple[str, list]:
    """One mode's panel (title, total bars, the 10 x 10 grid) and its row of the numbers table."""
    mode, n = FG.MODE_NAME.get(m, m), len(cells)
    groups = {g: [] for g, _ in GROUPS}
    for v in cells.values():
        groups[Q.combo_of(v["solved"])].append(v["row"])
    for rows in groups.values():
        rows.sort(key=by_type)
    total = {k: sum(k in v["solved"] for v in cells.values()) for k in Q.TRIO}
    bars = "".join(f'<div class="wbar"><span class="wn">{k.capitalize()}</span><span class="wtr"><i style="width:'
                   f'{100 * total[k] / n:.1f}%;background:var(--wf-{k})"></i></span><b>{total[k]}</b></div>'
                   for k in sorted(Q.TRIO, key=lambda k: -total[k]))
    got = squares({g: len(r) for g, r in groups.items()})
    grid = []
    for g, lab in GROUPS:
        rows = groups[g]
        if not got[g]:
            continue
        names = "、".join(Q.task_label(r) for r in rows[:SHOWN]) + ("等" if len(rows) > SHOWN else "")
        tip = f"{lab}：{len(rows)}/{n} 项 · {names}" if rows else f"{lab}：0/{n} 项"
        data = esc(json.dumps([list(Q.task_parts(r)) for r in rows], ensure_ascii=False))
        grid.append(f'<span class="wgrp" data-g="{g}" data-title="{esc(lab + " · " + mode)}" data-tasks="{data}">'
                    + square(g, f' data-tip="{esc(tip)}"') * got[g] + "</span>")
    html_ = (f'<div class="wpanel" data-mode="{esc(m)}"><p class="rtitle">{esc(mode)} · {n} 项</p>{bars}'
             f'<div class="wgrid" role="img" aria-label="{esc(mode)}：{n} 个评测项，每格约 1%，按做成情况分组">{"".join(grid)}</div></div>')
    return html_, [esc(mode), str(n)] + [str(total[k]) for k in Q.TRIO] + [str(len(groups[g])) for g, _ in GROUPS]


def fig_waffle(ctx, **kv) -> str:
    """The waffle panels for mode= (default all three modes); other parameters go to queries.overlap_cells."""
    modes = kv["mode"].split(",") if kv.get("mode") else list(FG.MODE_NAME)
    cells = {m: Q.overlap_cells(ctx, **{**kv, "mode": m}) for m in modes}
    modes = [m for m in modes if cells[m]]
    if not modes:
        return ""
    key = "".join(f'<span>{square(g)}{esc(lab)}</span>' for g, lab in GROUPS)
    panels, table = zip(*(panel(m, cells[m]) for m in modes))
    style = ";".join(f"--wf-{k}:var({c})" for k, c in color().items())
    return (C.howto("每格约 1% 的评测项，颜色 = 哪几家做成。")
            + f'<div class="chart waffle" style="{style}"><div class="wkey">{key}</div>'
            f'<div class="wpanels">{"".join(panels)}</div><div class="wlist" aria-live="polite"></div></div>'
            + C.numbers(["模式", "评测项", *[f"{Q.TRIO[k]} 做成" for k in Q.TRIO], *[lab for _, lab in GROUPS]], list(table)))


def figures(ctx) -> dict:
    return {"waffle": lambda **kv: fig_waffle(ctx, **kv)}
