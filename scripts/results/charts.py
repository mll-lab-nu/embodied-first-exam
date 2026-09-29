"""The SVG charts: the session on a clock (robot and agent), per-episode bars, lines, bars, strips, stages, cost."""
from __future__ import annotations

import math
import os
import datetime as dt

from bench import B
from common import CLOCK, KIND, PHASE_COLORS, TOOLS, clip_text, esc, num, tip, tok, url, usd
from calls import call_tip, kind_label, tool_kinds


def ep_kind(e: dict, last: bool, max_steps: int | None) -> str:
    if e["end"] == "failed" and max_steps and (e["end_step"] or 0) >= max_steps:
        return "downlimit" if B.down(e) is True else "steplimit"   # lying or sitting is no fall to the task
    if e["end"] == "failed" and B.down(e) is False:
        return "endup"   # ended without a fall: a tool or an object dropped, or the robot left its seat
    if e["end"] in KIND:
        return e["end"]
    return "running" if last else "reset"


def blocks(s: dict) -> list[tuple]:
    """The run as consecutive blocks on the agent's clock: reading before the first request to the robot, each
    episode (while it ran, then the time after it ended until the next reset), and the wrap-up after the last."""
    a0, a1, eps, ms = s["a0"], s["a1"], s["episodes"], s["spec"]["max_steps"]
    first = eps[0]["t0"] or a1
    out = [("prelude", a0, first, None, False)]
    for i, e in enumerate(eps):
        last = i == len(eps) - 1
        t0 = e["t0"] or first
        k = ep_kind(e, last, ms)
        if not last:
            nxt = eps[i + 1]["t0"]
            if e["t_end"] and e["t_end"] < nxt:
                out += [(k, t0, e["t_end"], e, False), (k, e["t_end"], nxt, e, True)]
            else:
                out.append((k, t0, nxt, e, False))
        else:
            stop = max(t0, e["t_end"] or e["t_last"] or t0)
            out += [(k, t0, stop, e, False), ("wrapup", stop, a1, None, False)]
    return out


def ep_tip(e: dict, s: dict, kind: str) -> str:
    a0 = s["a0"]; t1 = e["t_end"] or e["t_last"]
    graded = e["ep"] == s["result"]["graded_ep"]
    numbers, more = B.ep_lines(e)
    return tip(f"ep{e['ep']}{' · 被评分' if graded else ''} · {KIND[kind][0]}", numbers,
               f"{(e['t0'] - a0) / 60 if e['t0'] else 0:.2f}–{(t1 - a0) / 60 if t1 else 0:.2f} min" + (f" · 看了 {e['views']} 张图" if e.get("views") else ""),
               more)


def mini_timeline(s: dict, span_s: float, w: int = 220, h: int = 14) -> str:
    """The whole budget as one bar: each episode a block (full mode: the agent's time), grey for what was not used."""
    a0 = s["a0"]; X = lambda t: max(0.0, min(w, (t - a0) / span_s * w))
    unused = tip("没用到的预算", f"{span_s / 60:.0f} min 里用了 {(s['a1'] - a0) / 60:.1f} min")
    parts = [f'<rect x="0" y="0" width="{w}" height="{h}" rx="3" class="e-unused" data-tip="{unused}"/>']
    if not s["episodes"]:   # full mode: no sim-service log, one block for the agent's time
        t = tip("agent 运行", f"{(s['a1'] - a0) / 60:.1f} min")
        parts.append(f'<rect x="0" y="0" width="{max(X(s["a1"]), 0.6):.2f}" height="{h}" rx="3" class="e-running" data-tip="{t}"/>')
    for kind, t0, t1, e, after in blocks(s) if s["episodes"] else ():
        x0, x1 = X(t0), X(t1)
        if x1 <= x0:
            continue
        cls = {"prelude": "e-prelude", "wrapup": "e-wrapup"}.get(kind) or KIND[kind][1] + (" after" if after else "")
        t = tip("读文档、准备", f"{(t1 - t0) / 60:.1f} min") if kind == "prelude" else tip("收尾", f"{(t1 - t0) / 60:.1f} min") if kind == "wrapup" else ep_tip(e, s, kind)
        parts.append(f'<rect x="{x0:.2f}" y="0" width="{max(x1 - x0, 0.6):.2f}" height="{h}" class="{cls}" data-tip="{t}"/>')
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" style="display:block">{"".join(parts)}</svg>'


def nice_step(span: float, target: int = 8) -> float:
    for st in (0.25, 0.5, 1, 2, 5, 10, 15, 20, 30, 60, 120, 300, 600, 1000, 2000, 5000):
        if span / st <= target:
            return st
    return span / target


def clock_x(s: dict):
    """Session time -> x on the charts that share the session clock (CLOCK)."""
    a0, dur = s["a0"], max(s["a1"] - s["a0"], 1)
    W, L, R = CLOCK; P = W - L - R
    return lambda t: L + max(0.0, min(P, (t - a0) / dur * P))


def clock_svg(s: dict, X, rows: list, body: list, H: float) -> str:
    """The minute ticks along the top and a label per row ((y, height, label)), under the chart's own marks."""
    dur = max(s["a1"] - s["a0"], 1) / 60; st = nice_step(dur, 10)
    ax, m = [], 0.0
    while m <= dur + 1e-9:
        x = X(s["a0"] + m * 60)
        ax.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="16" y2="{H - 4}" class="grid"/><text x="{x:.1f}" y="11" text-anchor="middle">{m:g}</text>')
        m += st
    ax.append(f'<text x="{CLOCK[1] - 8}" y="11" text-anchor="end">min</text>')
    ax += [f'<text x="{CLOCK[1] - 8}" y="{y + h / 2 + 4}" text-anchor="end" class="lbl">{esc(lab)}</text>' for y, h, lab in rows]
    return f'<svg class="chart" viewBox="0 0 {CLOCK[0]} {H}">{"".join(ax)}{"".join(body)}</svg>'


def robot_timeline(s: dict, phases: list, page_dir: str) -> str:
    """The robot's side of the session: the phases (from notes.md) and each episode, how it ended."""
    a0 = s["a0"]; X = clock_x(s); bl = blocks(s)
    by_ep = {}
    for kind, t0, t1, e, after in bl:
        if e is not None:
            lo, hi = by_ep.get(e["ep"], (t0, t1)); by_ep[e["ep"]] = (min(lo, t0), max(hi, t1))
    rows, svg, y = [], [], 20
    if phases:
        TH = 20; rows.append((y, TH, "阶段"))
        for k, (a, b, name) in enumerate(phases):
            if a not in by_ep:
                continue
            t0 = by_ep[a][0]; t1 = by_ep.get(min(b, max(by_ep)), by_ep[a])[1]
            x0, x1 = X(t0), X(t1)
            col = PHASE_COLORS[k % len(PHASE_COLORS)]
            svg.append(f'<rect x="{x0:.1f}" y="{y}" width="{max(x1 - x0 - 1, 1):.1f}" height="{TH}" rx="4" fill="{col}" '
                       f'data-tip="{tip(name, f"ep{a}" + (f"–ep{b}" if b != a else ""), f"{(t0 - a0) / 60:.1f}–{(t1 - a0) / 60:.1f} min")}"/>')
            lab = clip_text(name, x1 - x0 - 8)
            if lab:
                svg.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{y + TH / 2 + 4}" text-anchor="middle" class="lbl-in">{esc(lab)}</text>')
        y += TH + 6
    TH = 24; rows.append((y, TH, "episode"))
    graded = s["result"]["graded_ep"]
    for kind, t0, t1, e, after in bl:
        x0, x1 = X(t0), X(t1)
        if x1 - x0 <= 0:
            continue
        w = max(x1 - x0 - (0.8 if x1 - x0 > 2 else 0), 0.8)
        if kind in ("prelude", "wrapup"):
            name = "读文档、准备" if kind == "prelude" else "收尾"
            svg.append(f'<rect x="{x0:.2f}" y="{y}" width="{w:.2f}" height="{TH}" rx="3" class="e-{kind}" data-tip="{tip(name, f"{(t1 - t0) / 60:.1f} min")}"/>')
            continue
        vid = url(s, os.path.join(s["trial_dir"], "report", e["video"]), page_dir) if e.get("video") else ""
        attrs = f' data-video="{esc(vid)}" data-label="ep{e["ep"]}"' if vid else ""
        g = " graded" if e["ep"] == graded and not after else ""
        svg.append(f'<rect x="{x0:.2f}" y="{y}" width="{w:.2f}" height="{TH}" rx="2" class="{KIND[kind][1]}{" after" if after else ""}{g}{" click" if vid else ""}"'
                   f' data-tip="{ep_tip(e, s, kind)}"{attrs}/>')
        if not after and x1 - x0 > 20:
            svg.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{y + TH / 2 + 4}" text-anchor="middle" class="lbl-in">{e["ep"]}</text>')
    H = y + TH + 8
    kinds = []
    for kind, *_ in bl:
        if kind not in kinds:
            kinds.append(kind)
    items = [("prelude", "读文档、准备")] + [(k, KIND[k][0]) for k in kinds if k in KIND] + [("wrapup", "收尾")]
    lg = "".join(f'<span><b class="sw-{"timeout" if k == "steplimit" else k}"></b>{esc(n)}</span>' for k, n in items)
    lg += ('<span><b style="opacity:.35" class="sw-failed"></b>结束后到下一次 reset</span><span><b style="outline:1.6px solid var(--ink)" class="sw-reset"></b>被评分段</span>'
           '<span>点一段播放它的视频</span>')
    return f'{clock_svg(s, X, rows, svg, H)}<div class="legend">{lg}</div>'


def agent_timeline(s: dict) -> str:
    """The agent's side of the same clock, one row per kind of thing: the model generating, each kind of tool call
    (a call that did several things shows in each of their rows), the images it looked at, what it said."""
    a0 = s["a0"]; X = clock_x(s); calls = s["calls"]
    kinds = [tool_kinds(c) for c in calls]
    views = {}   # call -> the images it showed the model
    for v in s["views"]:
        i = next((i for i, c in enumerate(calls) if "view" in kinds[i] and c["t0"] - 1 <= v["t"] <= c["t1"] + 1), None)
        views.setdefault(i, []).append(v)
    used = [k for k in TOOLS if any(k in ks for ks in kinds)]
    RH, GAP = 14, 6
    order = ["gen"] + used + (["msg"] if s["msgs"] else [])
    top = {k: 20 + j * (RH + GAP) for j, k in enumerate(order)}
    H = 20 + len(order) * (RH + GAP) + 2
    names = {"gen": "模型生成", "msg": "说的话", **{k: kind_label(k, s) for k in TOOLS}}
    rows = [(top[k], RH, names[k]) for k in order]
    svg = [f'<line x1="{X(e["t0"]):.1f}" x2="{X(e["t0"]):.1f}" y1="16" y2="{H - 4}" class="ep-line"/>' for e in s["episodes"][1:] if e["t0"]]
    for r in s["requests"]:
        if r["gen_s"]:
            x0, x1 = X(r["t"] - r["gen_s"]), X(r["t"])
            t = tip("模型生成", f"{r['gen_s']:.1f} s（首 token {r['lat_s'] or 0:.1f} s）",
                    f"输入 {tok(r['in'])}（缓存 {tok(r['cached'])}）· 输出 {tok(r['out'])}", usd(r["cost"]))
            svg.append(f'<rect x="{x0:.2f}" y="{top["gen"]}" width="{max(x1 - x0, 0.6):.2f}" height="{RH}" class="gen" data-tip="{t}"/>')
    for i, c in enumerate(calls):
        x0 = X(c["t0"]); w = max(X(c["t1"]) - x0, 2)
        t = call_tip(i, c, s)
        for k in kinds[i]:
            if k == "view" and views.get(i):
                for j, v in enumerate(views[i]):   # the images this call showed, each in its camera's colour
                    vt = tip(f"看图 #{v['n']} · {B.cam_label(v['camera'])}", f"ep{v['ep']} 第 {v['step']} 步 · {(v['t'] - a0) / 60:.2f} min",
                             os.path.basename(v["path"] or ""), "点击看这次调用")
                    svg.append(f'<rect x="{x0 + 3 * j:.2f}" y="{top[k]}" width="3" height="{RH}" rx="1" class="cam-{B.cam_color(v["camera"])}" data-call="{i}" data-tip="{vt}"/>')
                continue
            svg.append(f'<rect x="{x0:.2f}" y="{top[k]}" width="{w:.2f}" height="{RH}" rx="1" fill="{TOOLS[k][1]}" data-call="{i}" data-tip="{t}"/>')
    for t, txt, *_ in s["msgs"]:   # [t, text, ep, step]
        svg.append(f'<circle cx="{X(t):.1f}" cy="{top["msg"] + RH / 2}" r="3.6" class="msg" data-tip="{tip(f"{(t - a0) / 60:.2f} min", txt[:320] + ("…" if len(txt) > 320 else ""))}"/>')
    cams = []
    for v in s["views"]:
        if v["camera"] not in cams:
            cams.append(v["camera"])
    lg = ("<span>一行一类；一次调用做了几件事，就在几行里各出现一次</span>"
          + ("<span>看图按相机着色：" + "".join(f'<span style="margin-left:6px"><b class="sw-{B.cam_color(c)}"></b>{B.cam_label(c)}</span>' for c in cams) + "</span>" if cams else "")
          + ('<span><i class="sw-ep"></i>竖虚线 = reset，下一段 episode 开始（和上图对齐）</span>' if len(s["episodes"]) > 1 else "")
          + "<span>点一条看这次调用的命令和输出</span>")
    return f'{clock_svg(s, X, rows, svg, H)}<div class="legend">{lg}</div>'


def episode_chart(s: dict, task: dict, page_dir: str) -> str:
    """Per episode: the return where the benchmark scores one (with the all-zero line and, where it fits, the pass
    mark), how many steps it lasted, and the benchmark's own rows (HumanoidBench's gait tasks: how far forward the
    pelvis got)."""
    eps = s["episodes"]; n = len(eps)
    W, L, R = 1160, 64, 150
    P = W - L - R; bw = min(P / max(n, 1), 40)
    nop, bar, ms = task.get("nop"), s["result"]["bar"], s["spec"]["max_steps"]
    graded, best = s["result"]["graded_ep"], s["result"]["best_ep"]
    rets = [e.get("return") for e in eps]
    vals = [v for v in rets if v is not None] + ([nop] if nop is not None else [])
    lo, hi = min([0.0] + vals), max([0.0] + vals)
    bar_in = bar is not None and bar <= max(hi, 1e-9) * 1.6 + 1e-9 and bar >= lo
    if bar_in:
        hi = max(hi, bar)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - (pad if lo < 0 else 0), hi + pad
    rows = [("回报", 150, lo, hi, lambda e: e.get("return"))] if B.scored else []
    smax = max([e["steps"] for e in eps] + [task.get("nop_steps") or 0]) * 1.12 or 1
    rows.append(("撑了多少步", 86, 0, smax, lambda e: e["steps"]))
    rows += B.episode_rows(task, eps)
    svg, y = [], 8
    for title, h, a, b, get in rows:
        Y = lambda v: y + h - (v - a) / ((b - a) or 1) * h
        st = nice_step(b - a, 4)
        g = (a // st) * st
        while g <= b + 1e-9:
            if g >= a:
                svg.append(f'<line x1="{L}" x2="{L + P}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" class="grid"/>'
                           f'<text x="{L - 6}" y="{Y(g) + 3.5:.1f}" text-anchor="end">{num(g, 0 if st >= 1 else 2)}</text>')
            g += st
        note = ""
        if title == "回报" and bar is not None and not bar_in:
            note = f"　及格线 {num(bar, 0)} 在图外（是这里最高值的 {bar / max(hi, 1e-9):.0f} 倍）"
        svg.append(f'<text x="{L}" y="{y - 1}" class="lbl" style="font-weight:600">{esc(title)}<tspan style="font-weight:400;fill:var(--ok)">{esc(note)}</tspan></text>')
        for i, e in enumerate(eps):
            v = get(e)
            if v is None:
                continue
            kind = ep_kind(e, i == n - 1, ms)
            x = L + i * bw + bw * 0.14; w = bw * 0.72
            y0, y1 = sorted((Y(0 if a <= 0 <= b else a), Y(v)))
            vid = url(s, os.path.join(s["trial_dir"], "report", e["video"]), page_dir) if e.get("video") else ""
            attrs = f' data-video="{esc(vid)}" data-label="ep{e["ep"]}"' if vid else ""
            svg.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{max(y1 - y0, 0.8):.1f}" rx="1.5" '
                       f'class="{KIND[kind][1]}{" graded" if e["ep"] == graded else ""}{" click" if vid else ""}" data-tip="{ep_tip(e, s, kind)}"{attrs}/>')
        if title == "回报":
            refs = [(nop, "全零动作 " + num(nop), "ref", "var(--mut)")] if nop is not None else []
            if bar_in:
                refs.append((bar, "及格线 " + num(bar, 0), "bar-line", "var(--ok)"))
            for v, lab, cls, col in refs:
                svg.append(f'<line x1="{L}" x2="{L + P}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="{cls}"/>'
                           f'<text x="{L + P + 8}" y="{Y(v) + 4:.1f}" style="fill:{col}">{esc(lab)}</text>')
            marks = [(best, "最高"), (graded, "评分")] if best != graded else [(graded, "最高 · 评分")]
            for k, lab in marks:
                if k is not None and k < n and eps[k].get("return") is not None:
                    svg.append(f'<text x="{L + k * bw + bw / 2:.1f}" y="{min(Y(eps[k]["return"]), Y(0) if lo <= 0 else y + h) - 4:.1f}" text-anchor="middle" '
                               f'style="font-size:10px;fill:var(--ink)">{lab}</text>')
        if title == "撑了多少步" and task.get("nop_steps"):
            svg.append(f'<line x1="{L}" x2="{L + P}" y1="{Y(task["nop_steps"]):.1f}" y2="{Y(task["nop_steps"]):.1f}" class="ref"/>'
                       f'<text x="{L + P + 8}" y="{Y(task["nop_steps"]) + 4:.1f}">全零动作 {task["nop_steps"]} 步</text>'
                       f'<text x="{L + P + 8}" y="{Y(task["nop_steps"]) + 18:.1f}" style="font-size:10px">（上限 {ms}）</text>')
        y += h + 30
    step = 1 if n <= 32 else 5
    for i in range(0, n, step):
        svg.append(f'<text x="{L + i * bw + bw / 2:.1f}" y="{y - 14}" text-anchor="middle" style="font-size:10px">{i}</text>')
    svg.append(f'<text x="{L - 6}" y="{y - 14}" text-anchor="end" style="font-size:10px">ep</text>')
    return f'<svg class="chart" viewBox="0 0 {W} {y - 4}">{"".join(svg)}</svg>'


def line_chart(series: list, x_max: float, y_max: float, x_label: str, y_label: str, h: int = 250, caps: list = (),
               W: int = 560, R: int = 104) -> str:
    """Step lines: series = [(label, colour, [(x, y), ...], tip)]; caps = [(y, label)] drawn as dashed lines."""
    L, T, B = 40, 16, 30
    P, Q = W - L - R, h - T - B
    X = lambda v: L + v / (x_max or 1) * P
    Y = lambda v: T + Q - v / (y_max or 1) * Q
    svg = []
    st = nice_step(y_max, 5); g = 0.0
    while g <= y_max + 1e-9:
        svg.append(f'<line x1="{L}" x2="{L + P}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" class="grid"/><text x="{L - 6}" y="{Y(g) + 3.5:.1f}" text-anchor="end">{g:g}</text>')
        g += st
    st = nice_step(x_max, 10); g = 0.0
    while g <= x_max + 1e-9:
        svg.append(f'<text x="{X(g):.1f}" y="{T + Q + 16}" text-anchor="middle">{g:g}</text>')
        g += st
    svg.append(f'<line x1="{L}" x2="{L + P}" y1="{T + Q}" y2="{T + Q}" class="axis"/>')
    svg.append(f'<text x="{L + P}" y="{T + Q + 28}" text-anchor="end">{esc(x_label)}</text>')
    for yv, lab in caps:
        svg.append(f'<line x1="{L}" x2="{L + P}" y1="{Y(yv):.1f}" y2="{Y(yv):.1f}" class="ref"/><text x="{L + P}" y="{Y(yv) - 5:.1f}" text-anchor="end">{esc(lab)}</text>')
    ends = []
    for label, col, pts, t in series:
        d = f"M{X(pts[0][0]):.1f},{Y(pts[0][1]):.1f}"
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            d += f" H{X(x1):.1f} V{Y(y1):.1f}"
        svg.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round" data-tip="{t}"/>')
        ex, ey = pts[-1]
        svg.append(f'<circle cx="{X(ex):.1f}" cy="{Y(ey):.1f}" r="4" fill="{col}" data-tip="{t}"/>')
        ends.append([Y(ey), X(ex), label, col, t])
    ends.sort()
    for i in range(1, len(ends)):   # keep the end labels apart
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 13)
    for yy, xx, label, col, t in ends:
        svg.append(f'<text x="{L + P + 8}" y="{yy + 4:.1f}" style="fill:{col};font-weight:600" data-tip="{t}">{esc(label)}</text>')
    return f'<svg class="chart" viewBox="0 0 {W} {h}">{"".join(svg)}</svg>'


def reset_series(r: dict, col: str, label: str) -> tuple:
    s = r["s"]; a0 = s["a0"]
    pts = [(0.0, 0)] + [((e["t0"] - a0) / 60, k) for k, e in enumerate(s["episodes"][1:], 1)] + [((s["a1"] - a0) / 60, len(s["episodes"]) - 1)]
    d = r["d"]
    t = tip(label, f"{d['resets_used']}/{d['resets']} 次 reset，{d['agent_min']:.1f} min 结束（预算 {d['budget_min']:.0f} min）")
    return (label, col, pts, t)


def hbars(rows: list, w_label: int = 104, W: int = 560, R: int = 150) -> str:
    """Horizontal stacked bars on one scale: rows = [(label, href, [(value, css class, tip)], right text)]."""
    BH, GAP = 18, 10
    P = W - w_label - R
    top = max((sum(v for v, _, _ in parts) for _, _, parts, _ in rows), default=1) or 1
    svg, y = [], 4
    for label, href, parts, right in rows:
        lab = f'<text x="{w_label - 8}" y="{y + BH / 2 + 4}" text-anchor="end" class="lbl">{esc(label)}</text>'
        svg.append(f'<a href="{esc(href)}">{lab}</a>' if href else lab)
        x = w_label
        for v, cls, t in parts:
            w = v / top * P
            if w > 0:
                paint = f'fill="{cls}"' if cls.startswith("#") else f'class="{cls}"'
                svg.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{BH}" {paint} data-tip="{t}"/>')
            x += w
        svg.append(f'<text x="{x + 6:.1f}" y="{y + BH / 2 + 4}" class="lbl">{esc(right)}</text>')
        y += BH + GAP
    return f'<svg class="chart" viewBox="0 0 {W} {y}">{"".join(svg)}</svg>'


def strip_chart(runs: list, tasks_by: dict, W: int = 560, LW: int = 104) -> str:
    """How long each episode lasted, one row per run, on a log axis: a dot per episode, the graded one a diamond,
    and a bar where the all-zero action falls."""
    R, RH = 16, 26
    P = W - LW - R
    xmax = max((r["s"]["spec"]["max_steps"] or 1000 for r in runs), default=1000)
    X = lambda v: LW + math.log10(1 + max(v, 0)) / math.log10(1 + xmax) * P
    svg, y = [], 20
    for g in (0, 10, 30, 100, 300, 1000, 3000):
        if g <= xmax:
            svg.append(f'<line x1="{X(g):.1f}" x2="{X(g):.1f}" y1="14" y2="{14 + len(runs) * RH + 4}" class="grid"/><text x="{X(g):.1f}" y="10" text-anchor="middle">{g}</text>')
    svg.append(f'<text x="{LW - 8}" y="10" text-anchor="end">步数</text>')
    for r in runs:
        s, task = r["s"], tasks_by.get(r["task"], {})
        svg.append(f'<line x1="{LW}" x2="{LW + P}" y1="{y + RH / 2}" y2="{y + RH / 2}" class="grid"/>'
                   f'<a href="tasks/{r["task"]}.html"><text x="{LW - 8}" y="{y + RH / 2 + 4}" text-anchor="end" class="lbl">{esc(r["task"])}</text></a>')
        if task.get("nop_steps"):
            xs, t = X(task["nop_steps"]), tip("全零动作", f"撑 {task['nop_steps']} 步")
            svg.append(f'<line x1="{xs:.1f}" x2="{xs:.1f}" y1="{y + 3}" y2="{y + RH - 3}" stroke="var(--ink)" stroke-width="2" data-tip="{t}"/>')
        n = len(s["episodes"])
        for i, e in enumerate(s["episodes"]):
            kind = ep_kind(e, i == n - 1, s["spec"]["max_steps"])
            cx, cy = X(e["steps"]), y + RH / 2 + ((i * 7) % 11 - 5) * 0.9
            if e["ep"] == s["result"]["graded_ep"]:
                svg.append(f'<path d="M{cx:.1f},{cy - 6:.1f} l6,6 l-6,6 l-6,-6z" class="{KIND[kind][1]}" stroke="var(--ink)" stroke-width="1.2" data-tip="{ep_tip(e, s, kind)}"/>')
            else:
                svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.6" class="{KIND[kind][1]}" fill-opacity=".8" data-tip="{ep_tip(e, s, kind)}"/>')
        y += RH
    return f'<svg class="chart" viewBox="0 0 {W} {y + 4}">{"".join(svg)}</svg>'


def stage_chart(runs: list) -> str:
    """Harbor's stages for each run, from the trial's start: environment, agent install, the agent, the sidecar's
    wrap-up (trajectory, replay, video) and the verifier."""
    W, LW, R, BH, GAP = 1160, 250, 70, 16, 9
    P = W - LW - R
    spans = []
    for r in runs:
        st = r["s"]["stages"]; t0 = st["trial"][0]
        seg = [("环境启动", st["environment_setup"], "#94a3b8"), ("agent 安装", st["agent_setup"], "#38bdf8"),
               ("agent 运行", st["agent_execution"], "#6366f1"),
               ("收尾（存轨迹、回放、录像）", [st["agent_execution"][1], (st["verifier"] or st["trial"])[0]] if st["agent_execution"] else None, "#f59e0b"),
               ("验证", st["verifier"], "#22c55e")]
        spans.append((r, t0, [(n, a, c) for n, a, c in seg if a], st["trial"][1] - t0))
    xmax = max((d for *_, d in spans), default=1)
    X = lambda v: LW + v / xmax * P
    svg, y = [], 18
    stp = nice_step(xmax / 60, 10); g = 0.0
    while g <= xmax / 60 + 1e-9:
        svg.append(f'<line x1="{X(g * 60):.1f}" x2="{X(g * 60):.1f}" y1="14" y2="{14 + len(spans) * (BH + GAP)}" class="grid"/><text x="{X(g * 60):.1f}" y="10" text-anchor="middle">{g:g}</text>')
        g += stp
    svg.append(f'<text x="{LW - 8}" y="10" text-anchor="end">min</text>')
    for r, t0, segs, total in spans:
        date = dt.datetime.fromtimestamp(t0).strftime("%m-%d %H:%M")
        svg.append(f'<a href="runs/{r["id"]}.html"><text x="{LW - 8}" y="{y + BH / 2 + 4}" text-anchor="end" class="lbl">{esc(r["task"])} · {esc(r["model_name"])} · {date}</text></a>')
        for name, (a, b), col in segs:
            svg.append(f'<rect x="{X(a - t0):.1f}" y="{y}" width="{max(X(b - t0) - X(a - t0), 0.8):.1f}" height="{BH}" fill="{col}" data-tip="{tip(name, f"{(b - a) / 60:.1f} min")}"/>')
        svg.append(f'<text x="{X(total) + 6:.1f}" y="{y + BH / 2 + 4}">{total / 60:.0f} min</text>')
        y += BH + GAP
    lg = "".join(f'<span><b style="background:{c}"></b>{n}</span>' for n, c in (("环境启动", "#94a3b8"), ("agent 安装", "#38bdf8"), ("agent 运行", "#6366f1"),
                                                                              ("收尾（存轨迹、回放、录像）", "#f59e0b"), ("验证", "#22c55e")))
    return f'<svg class="chart" viewBox="0 0 {W} {y}">{"".join(svg)}</svg><div class="legend" style="margin-top:6px">{lg}</div>'


def cost_chart(s: dict) -> str:
    """Per request: the input (cached / not) and output tokens, and the bill adding up."""
    rq = s["requests"]; n = len(rq)
    if not n:
        return "<p class='mut'>没有请求记录。</p>"
    W, L, R, H1, H2 = 1160, 60, 70, 150, 110
    P = W - L - R; bw = P / n
    top = max(x["in"] + x["out"] for x in rq) * 1.1 or 1
    svg = []
    Y = lambda v: 10 + H1 - v / top * H1
    st = nice_step(top, 4); g = 0.0
    while g <= top:
        svg.append(f'<line x1="{L}" x2="{L + P}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" class="grid"/><text x="{L - 6}" y="{Y(g) + 3.5:.1f}" text-anchor="end">{tok(g)}</text>')
        g += st
    for i, x in enumerate(rq):
        xs = L + i * bw + bw * 0.1; w = max(bw * 0.8, 0.8)
        t = tip(f"请求 {i + 1} · {(x['t'] - s['a0']) / 60:.2f} min", f"输入 {x['in']:,}（缓存 {x['cached']:,}）", f"输出 {x['out']:,}（推理 {x['reason']:,}）",
                f"{usd(x['cost'])} · 生成 {x['gen_s'] or 0:.1f} s")
        y0 = Y(0)
        for v, cls in ((x["cached"], "i-cached"), (x["in"] - x["cached"], "i-uncached"), (x["out"], "i-out")):
            h = v / top * H1
            if h > 0:
                svg.append(f'<rect x="{xs:.1f}" y="{y0 - h:.1f}" width="{w:.1f}" height="{h:.1f}" style="fill:var(--tok-{cls[2:]})" data-tip="{t}"/>')
                y0 -= h
    svg.append(f'<text x="{L}" y="6" class="lbl" style="font-weight:600">每次请求的 token</text>')
    base = 10 + H1 + 34
    tot = sum(x["cost"] or 0 for x in rq) or 1e-9
    YC = lambda v: base + H2 - v / tot * H2
    acc, d = 0.0, f"M{L},{base + H2}"
    for i, x in enumerate(rq):
        acc += x["cost"] or 0
        d += f" L{L + (i + 1) * bw:.1f},{YC(acc):.1f}"
    svg.append(f'<text x="{L}" y="{base - 6}" class="lbl" style="font-weight:600">累计花费</text>')
    for frac in (0, 0.5, 1):
        svg.append(f'<line x1="{L}" x2="{L + P}" y1="{YC(tot * frac):.1f}" y2="{YC(tot * frac):.1f}" class="grid"/><text x="{L - 6}" y="{YC(tot * frac) + 3.5:.1f}" text-anchor="end">{usd(tot * frac)}</text>')
    svg.append(f'<path d="{d}" fill="none" stroke="var(--acc)" stroke-width="2.2"/>')
    svg.append(f'<text x="{L + P + 6}" y="{YC(tot) + 4:.1f}" class="lbl">{usd(tot)}</text>')
    for i in range(0, n, max(1, round(n / 12))):
        svg.append(f'<text x="{L + i * bw + bw / 2:.1f}" y="{base + H2 + 14}" text-anchor="middle" style="font-size:10px">{i + 1}</text>')
    svg.append(f'<text x="{L + P}" y="{base + H2 + 28}" text-anchor="end">第几次请求</text>')
    lg = '<div class="legend"><span><b class="sw-cached"></b>输入（命中缓存）</span><span><b class="sw-uncached"></b>输入（未缓存）</span><span><b class="sw-out"></b>输出（含推理）</span></div>'
    return f'<svg class="chart" viewBox="0 0 {W} {base + H2 + 32}">{"".join(svg)}</svg>{lg}'
