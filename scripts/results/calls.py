"""Tool calls: what each one did (TOOLS), and the per-category table, the call-by-call grid and the command list."""
from __future__ import annotations

import math
import os
import re

from common import CLOCK, NET, READ, TOOLS, WRITE, esc, pretty_output, tip


def shell_heads(cmd: str) -> list[tuple[str, str]]:
    """(program, segment) for each command a shell line runs, heredoc bodies skipped: `cd x && timeout 60 python -
    <<'PY' ... PY` -> [("python", "python - <<'PY'")]."""
    out, skip = [], None
    for ln in cmd.splitlines():
        if skip is not None:
            skip = None if ln.strip() == skip else skip
            continue
        for seg in re.split(r"&&|\|\||;|\|", ln):
            w = seg.split()
            while w and (w[0] in ("timeout", "nohup", "time", "sudo", "exec", "env") or re.fullmatch(r"\w+=\S*|-\S+|\d+[smh]?", w[0])):
                w = w[1:]
            if w and w[0] not in ("cd", "export", "set", "source", ".", "{", "}", "(", ")", "do", "done", "then", "fi"):
                out.append((os.path.basename(w[0]), seg.strip()))
        m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", ln)
        skip = m.group(1) if m else None
    return out


def kind_label(k: str, s: dict) -> str:
    """A category's name on this run's pages: full mode has no sim-service log, so its Python is just Python."""
    return "Python" if k == "python" and s.get("mode") == "full" else TOOLS[k][0]


def kind_how(k: str, s: dict) -> str:
    return "跑 python（full 模式里仿真就在 agent 的进程里，驱动机器人的调用也在这类）" if k == "python" and s.get("mode") == "full" else TOOLS[k][2]


def tool_kind(c: dict) -> str:
    """One tool call's main category (TOOLS)."""
    return tool_kinds(c)[0]


def tool_kinds(c: dict) -> list:
    """Everything one tool call did, most telling first (codex's code mode often patches a file and runs it in one
    call): the robot if the sim service logged anything while it ran, then by program."""
    r = c.get("robot") or {}
    kinds = set()
    if r.get("steps") or r.get("observes") or r.get("resets"):
        kinds.add("robot")
    if "apply_patch" in c["tools"]:
        kinds.add("write")
    if "view_image" in c["tools"]:
        kinds.add("view")
    for head, seg in (h for cmd in c.get("cmds") or [] for h in shell_heads(cmd)):
        if head.startswith("python") or head.endswith(".py"):
            kinds.add("python")
        elif head in NET:
            kinds.add("net")
        elif head in WRITE or (head in ("cat", "echo", "printf") and re.search(r"(?<![<>&\d])>>?\s*[^\s&|]", seg)):
            kinds.add("write")
        elif head in READ:
            kinds.add("read")
        else:
            kinds.add("other")
    if "robot" in kinds:
        kinds.discard("python")
    return [k for k in TOOLS if k in kinds] or ["other"]


def thinking_before(s: dict) -> list:
    """For each tool call, how long the model generated the response that made it (the request logged right after)."""
    rq = sorted(s["requests"], key=lambda r: r["t"])
    out = []
    for c in s["calls"]:
        r = next((r for r in rq if r["t"] >= c["t0"] - 0.3), None)
        out.append(r["gen_s"] if r and r["t"] - c["t0"] < 5 else None)
    return out


def call_tip(i: int, c: dict, s: dict) -> str:
    ks = tool_kinds(c); r = c.get("robot") or {}; a0 = s["a0"]
    cmd = " ⏎ ".join((c.get("cmds") or [c.get("label") or ""])[0].splitlines())[:260]
    out = " ".join(pretty_output(c.get("out") or "").split())[:220]
    bad = [e for e in c.get("exit") or [] if e != 0]
    robot = (f"机器人 {r.get('steps', 0)} 步" + (f"、reset {r['resets']} 次" if r.get("resets") else "")
             + (f"、取图 {r['images']} 张" if r.get("images") else "")) if "robot" in ks else ""
    bg = r.get("after") or {}
    if bg.get("steps") or bg.get("resets"):   # a process this call left running
        robot += ("；" if robot else "") + f"返回后后台又走 {bg.get('steps', 0)} 步" + (f"、reset {bg['resets']} 次" if bg.get("resets") else "")
    return tip(f"#{i + 1} · {(c['t0'] - a0) / 60:.2f} min · " + " + ".join(kind_label(x, s) for x in ks),
               f"用时 {c['t1'] - c['t0']:.2f} s" + (f" · {robot}" if robot else "") + (f" · 退出码 {bad}" if bad else ""),
               "命令：" + cmd if cmd else "", "输出：" + out if out else "", "点击看完整命令和输出")


def tool_summary(s: dict) -> str:
    agg = {k: [0, 0.0, 0, 0] for k in TOOLS}
    for c in s["calls"]:
        ks = tool_kinds(c)
        a = agg[ks[0]]; a[0] += 1; a[1] += max(0, c["t1"] - c["t0"]); a[2] += (c.get("robot") or {}).get("steps", 0)
        for k in ks:
            agg[k][3] += 1
    n = sum(a[0] for a in agg.values()) or 1
    bar = '<div class="stack lg">' + "".join(f'<i style="width:{a[0] / n * 100:.2f}%;background:{TOOLS[k][1]}" data-tip="{tip(kind_label(k, s), f"{a[0]} 次")}"></i>'
                                            for k, a in agg.items() if a[0]) + "</div>"
    rows = "".join(f'<tr><td><span class="legend"><span><b style="background:{TOOLS[k][1]}"></b>{kind_label(k, s)}</span></span></td>'
                   f'<td class="mut" style="font-size:12px">{esc(kind_how(k, s))}</td><td class="n">{a[0]}</td>'
                   f'<td class="n">{a[3]}</td><td class="n">{a[1]:.1f} s</td><td class="n">{a[2]:,}</td></tr>' for k, a in agg.items() if a[3])
    return (f"{bar}<table class='plain' style='margin-top:10px'><thead><tr><th>类别</th><th>怎么算</th><th class='n'>以它为主的调用</th>"
            f"<th class='n'>含它的调用</th><th class='n'>总用时（按主类别）</th><th class='n'>其间机器人走的步数</th></tr></thead><tbody>{rows}</tbody></table>")


def tool_sequence(s: dict) -> str:
    """Every tool call in order, one cell each: above it how long the model thought before making it, in it what kind
    of call it was, below it how many control steps the robot took while it ran, and where an episode began."""
    calls = s["calls"]
    if not calls:
        return "<p class='mut'>没有工具调用。</p>"
    think = thinking_before(s)
    W, L = CLOCK[0], CLOCK[1]
    PER = min(58, max(len(calls), 30))
    cw = (W - L) / PER; TH, CH, SH, LH = 22, 24, 10, 12
    RH = TH + 2 + CH + 2 + SH + LH + 8
    svg, ep, last_lab = [], 0, -9
    for y0, name in ((TH / 2 + 4, "调用前思考"), (TH + 2 + CH / 2 + 4, "调用"), (TH + CH + 4 + SH / 2 + 4, "机器人步数")):
        svg.append(f'<text x="{L - 8}" y="{y0}" text-anchor="end" style="font-size:10.5px">{name}</text>')
    for i, c in enumerate(calls):
        y0 = (i // PER) * RH; x = L + (i % PER) * cw
        ks = tool_kinds(c); r = c.get("robot") or {}
        g = think[i]
        if g:
            h = (min(g, 60) / 60) ** 0.5 * TH
            gt = tip(f"调用 #{i + 1} 之前", f"模型生成了 {g:.1f} s")
            svg.append(f'<rect x="{x + 2:.1f}" y="{y0 + TH - h:.1f}" width="{cw - 4:.1f}" height="{max(h, 1):.1f}" class="gen" data-tip="{gt}"/>')
        t = call_tip(i, c, s)
        bad = any(e != 0 for e in c.get("exit") or [])
        edge = ' stroke="var(--bad)" stroke-width="2"' if bad else ' stroke="var(--card)" stroke-width="1"'
        cell = [f'<rect x="{x + 1:.1f}" y="{y0 + TH + 2 + j * CH / len(ks):.1f}" width="{cw - 2:.1f}" height="{CH / len(ks):.1f}" fill="{TOOLS[kk][1]}"/>'
                for j, kk in enumerate(ks)]   # one band per kind of thing the call did
        cell.append(f'<rect class="fr" x="{x + 1:.1f}" y="{y0 + TH + 2}" width="{cw - 2:.1f}" height="{CH}" rx="3" fill="none"{edge}/>')
        svg.append(f'<g data-call="{i}" data-tip="{t}">{"".join(cell)}</g>')
        if r.get("steps"):
            h = math.log10(1 + r["steps"]) / 3 * SH
            st = tip(f"#{i + 1} 期间机器人", f"{r['steps']} 步")
            svg.append(f'<rect x="{x + 3:.1f}" y="{y0 + TH + CH + 4}" width="{cw - 6:.1f}" height="{max(h, 1.5):.1f}" fill="var(--ink)" opacity=".55" data-tip="{st}"/>')
        if r.get("resets"):
            ep += r["resets"]
            svg.append(f'<line x1="{x + 0.5:.1f}" x2="{x + 0.5:.1f}" y1="{y0 + TH}" y2="{y0 + TH + CH + SH + 6}" stroke="var(--ink)" stroke-width="1" opacity=".5"/>')
            if i - last_lab >= (2 if cw >= 24 else 3) or i // PER != last_lab // PER:   # a label where there is room for it
                svg.append(f'<text x="{x + 2:.1f}" y="{y0 + TH + CH + SH + LH + 2}" style="font-size:9.5px;fill:var(--ink)">ep{ep}</text>')
                last_lab = i
    H = ((len(calls) - 1) // PER + 1) * RH
    lg = ('<div class="legend" style="margin-top:6px"><span>颜色同上表；一格分几色 = 这次调用做了几件事（如先改文件再运行）</span>'
          '<span>思考：平方根刻度，满格 = 60 s</span><span>步数：对数刻度</span><span>红框：命令出错（退出码非 0）</span>'
          '<span>竖线 + epN：这次调用里 reset，开始第 N 段（挤的地方省略标签）</span><span>点一格看完整命令和输出</span></div>')
    return f'<svg class="chart" viewBox="0 0 {W} {H}">{"".join(svg)}</svg>{lg}'


def tool_table(s: dict) -> str:
    a0 = s["a0"]; rows = []
    for i, c in enumerate(s["calls"]):
        ks = tool_kinds(c); r = c.get("robot") or {}
        cmd = "\n".join(c.get("cmds") or [c.get("label") or ""])
        bad = [e for e in c.get("exit") or [] if e != 0]
        kinds = "".join(f'<span><b style="background:{TOOLS[k][1]}"></b>{kind_label(k, s)}</span>' for k in ks)
        rows.append(f'<tr data-call="{i}"><td class="n">{i + 1}</td><td class="n">{(c["t0"] - a0) / 60:.2f}</td><td><span class="legend">{kinds}</span></td>'
                    f'<td class="n">{c["t1"] - c["t0"]:.2f} s</td><td class="n">{r.get("steps", 0) or ""}{" · R" * r.get("resets", 0)}</td>'
                    f'<td class="n{" bad" if bad else ""}">{",".join(map(str, c.get("exit") or [])) or ""}</td>'
                    f'<td><details><summary><code>{esc(" ".join(cmd.split())[:150])}</code></summary><pre>{esc(cmd[:3000])}</pre>'
                    f'<pre>{esc(pretty_output(c.get("out") or "")[:1500])}</pre></details></td></tr>')
    return ('<div class="tw"><table class="plain"><thead><tr><th class="n">#</th><th class="n">min</th><th>类别</th><th class="n">用时</th><th class="n">机器人步数</th>'
            '<th class="n">退出码</th><th>命令（点开看完整命令和输出）</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")
