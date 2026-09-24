"""The HTML: page pieces, a run in detail, its trajectory and records, and the three kinds of page."""
from __future__ import annotations

import ast
import base64
import glob
import json
import os
import re
import datetime as dt

import collect

from common import BENCH, CAMS, HERE, KIND, MODELS, OUT, REPO, RUN_COLORS, STANDARD, TOOLS, WHY, esc, num, pretty_output, stamp, tip, tok, url, usd
from data import notes_of
from calls import kind_label, tool_kind, tool_sequence, tool_summary, tool_table
from charts import agent_timeline, cost_chart, ep_kind, episode_chart, hbars, line_chart, mini_timeline, reset_series, robot_timeline, stage_chart, strip_chart


def md(src: str) -> str:
    """Enough Markdown for notes.md: headings, paragraphs, lists, tables, code blocks, `code`, **bold**, [links]()."""
    def inline(s):
        s = esc(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    out, L, i = [], src.splitlines(), 0
    item = re.compile(r"\s*([-*]|\d+\.)\s+")
    while i < len(L):
        line = L[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(L) and not L[j].startswith("```"):
                j += 1
            out.append(f"<pre>{esc(chr(10).join(L[i + 1:j]))}</pre>"); i = j + 1
        elif m := re.match(r"(#{1,4})\s+(.*)", line):
            h = max(3, len(m.group(1))); out.append(f"<h{h}>{inline(m.group(2))}</h{h}>"); i += 1
        elif item.match(line):
            items = []
            while i < len(L) and (item.match(L[i]) or (items and L[i].startswith("  ") and L[i].strip())):
                if item.match(L[i]):
                    items.append(item.sub("", L[i], count=1))
                else:
                    items[-1] += " " + L[i].strip()
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
        elif line.startswith("|"):
            rows = []
            while i < len(L) and L[i].startswith("|"):
                rows.append([c.strip() for c in L[i].strip().strip("|").split("|")]); i += 1
            body = [r for r in rows[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
            out.append('<div class="tw"><table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table></div>")
        elif not line.strip():
            i += 1
        else:
            buf = []
            while i < len(L) and L[i].strip() and not re.match(r"#{1,4}\s|```|\|", L[i]) and not item.match(L[i]):
                buf.append(L[i].strip()); i += 1
            out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out)


def page(title: str, body: str, depth: int, crumbs=()) -> str:
    up = "../" * depth
    nav = "".join(f'<span>›</span><a href="{h}">{esc(t)}</a>' if h else f"<span>›</span><span>{esc(t)}</span>" for t, h in crumbs)
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(title)}</title>"
            '<script>try{var t=localStorage.getItem("rcb-theme");if(t)document.documentElement.dataset.theme=t}catch(e){}</script>'
            f'<link rel="stylesheet" href="{up}assets/site.css{stamp(os.path.join(HERE, "site.css"))}"><script src="{up}assets/site.js{stamp(os.path.join(HERE, "site.js"))}"></script></head><body>'
            f'<header class="top"><div class="wrap"><a class="brand" href="{up}index.html">HumanoidBench 结果</a><nav class="crumbs">{nav}</nav>'
            '<button class="theme" onclick="toggleTheme()">◐ 深浅</button></div></header>'
            f'<main class="wrap">{body}<div class="foot">由 <code>scripts/results/build.py</code> 生成于 {dt.datetime.now():%Y-%m-%d %H:%M}；'
            f"数据：<code>results/{BENCH}/runs.csv</code>、各 trial 的 <code>report/summary.json</code> 和 <code>notes.md</code>。</div></main>"
            '<div id="tip"></div></body></html>')


def kpi(k: str, v: str, s: str = "", bar=None, cls: str = "", wide: bool = False, extra: str = "") -> str:
    b = ""
    if bar is not None:
        frac, bc = bar
        b = f'<div class="pbar lg {bc}"><i style="width:{max(0.0, min(1.0, frac)) * 100:.1f}%"></i></div>'
    return f'<div class="kpi{" wide" if wide else ""}"><div class="k">{k}</div><div class="v {cls}">{v}</div>{b}{extra}<div class="s">{s}</div></div>'


def pcell(frac, text: str, cls: str = "", t: str = "") -> str:
    w = 0.0 if frac is None else max(0.0, min(1.0, frac)) * 100
    if frac is not None and frac > 0 and w < 1.5:
        w = 1.5   # a sliver stays visible
    return f'<div class="cell"{f" data-tip={chr(34)}{t}{chr(34)}" if t else ""}><div class="pbar {cls}"><i style="width:{w:.1f}%"></i></div><span class="t">{text}</span></div>'


def stackbar(parts: list, total: float | None = None, lg: bool = False) -> str:
    tot = total or sum(v for v, _, _ in parts) or 1
    return (f'<div class="stack{" lg" if lg else ""}">' + "".join(f'<i class="{c}" style="width:{v / tot * 100:.2f}%" data-tip="{t}"></i>'
                                                           for v, c, t in parts if v > 0) + "</div>")


def status_chip(r: dict | None, big: bool = False) -> str:
    b = " big" if big else ""
    if r is None:
        return f'<span class="chip na{b}">未跑</span>'
    return f'<span class="chip ok{b}">✓ 通过</span>' if r["d"]["pass"] else f'<span class="chip bad{b}">✗ 未通过</span>'


def config_chips(r: dict) -> str:
    c = [f'<span class="chip">{esc(r["mode"])}</span>', f'<span class="chip">{r["budget_min"]} min</span>']
    if r.get("effort"):
        c.append(f'<span class="chip">effort {esc(r["effort"])}</span>')
    if r["mode"] == "limited":
        obs = r["obs"].split("+")
        c += [f'<span class="chip">reset {r["resets"]}</span>', f'<span class="chip">{"IMU" if "imu" in obs else "无 IMU"}</span>',
              f'<span class="chip">{"外部相机" if "room" in obs else "无外部相机"}</span>']
    else:
        c.append('<span class="chip">reset 不限 · 完整状态</span>')
    if r["standard"]:
        c.insert(0, '<span class="chip acc">标准配置</span>')
    return " ".join(c)


def tok_stack(d: dict, top: float) -> str:
    if d.get("tokens") is None:
        return ""
    parts = [(d["tok_cached"], "i-cached", tip("输入（命中缓存）", f"{d['tok_cached']:,}")),
             (d["tok_in"] - d["tok_cached"], "i-uncached", tip("输入（未缓存）", f"{d['tok_in'] - d['tok_cached']:,}")),
             (d["tok_out"], "i-out", tip("输出", f"{d['tok_out']:,}（推理 {d['tok_reason']:,}）"))]
    return (f'<div class="cell"><div style="width:{max(d["tokens"] / top, 0.02) * 100:.0f}%">{stackbar(parts)}</div>'
            f'<span class="t">{tok(d["tokens"])}</span></div>')


def run_command(task: dict, model: str, mode: str) -> str:
    """The standard-config run of one task in one mode, then its line in runs.csv and the pages."""
    std = STANDARD[mode]
    slug = re.sub(r"[^a-z0-9]", "", model.split("/")[-1].lower())
    fam = task["task"].replace("_", "-")
    if mode == "limited":
        d, env = task["dir"], f"RCB_RESET_BUDGET={std['resets']} RCB_OBS_IMU=1 RCB_OBS_ROOM_CAMERA=1 "
        job = f"hb-limited-{fam}-codex-{slug}-{std['effort']}-{std['budget_min']}min-reset{std['resets']}-imu-roomcam"
    else:
        d, env = task["full_dir"], ""
        job = f"hb-full-{fam}-codex-{slug}-{std['effort']}-{std['budget_min']}min"
    d = os.path.relpath(d, REPO) if d else f"tasks/<{fam}>"
    return (f"sg docker -c '{env}RCB_MODEL=openrouter/{model} scripts/run_deepseek_openrouter.sh {d} --job-name {job} "
            f"--ak reasoning_effort={std['effort']}'\npython3 scripts/results/build.py --add jobs/{job}")


def run_kpis(r: dict, task: dict) -> str:
    d, s = r["d"], r["s"]
    res = s["result"]
    prog = d.get("prog")
    limited = s["mode"] == "limited"
    k = [kpi("结果", "通过" if d["pass"] else "未通过", WHY.get(res["why"], res["why"]), cls="ok" if d["pass"] else "bad"),
         kpi("被评分段回报" if limited else "交的轨迹回放的回报", f'{num(d["score"])} <small>/ {num(d["bar"], 0)}</small>',
             f"离及格线 {prog:.3f}（全零 = 0，及格 = 1）" if prog is not None else "", bar=(prog or 0, "ok" if d["pass"] else "bad"))]
    if limited:
        k.append(kpi("reset", f'{d["resets_used"]} <small>/ {d["resets"]}</small>', f"{len(s['episodes'])} 段 episode，{res['steps']:,} 步",
                     bar=(d["resets_used"] / d["resets"] if d["resets"] else 1, "warn" if d["resets"] and d["resets_used"] >= d["resets"] else "")))
    else:
        steps, ms = res["steps"] or 0, task.get("max_steps") or 0
        k.append(kpi("轨迹长度", f"{steps:,} <small>/ {ms:,} 步</small>" if ms else f"{steps:,}", "验证端在新进程里回放两次，结果须一致",
                     bar=(steps / ms if ms else 0, "")))
    k += [kpi("agent 用时", f'{d["agent_min"]:.1f} <small>/ {d["budget_min"]:.0f} min</small>',
              f"用了预算的 {d['agent_min'] / d['budget_min']:.0%}" + ("（到时被停）" if res.get("timed_out") else ""), bar=(d["agent_min"] / d["budget_min"], "")),
          kpi("花费", usd(d["cost"]), f"{d['requests']} 次请求 · 模型生成 {d['gen_s'] / 60:.1f} min（{d['gen_s'] / d['agent_s']:.0%}）"),
          kpi("tokens", tok(d["tokens"]), f"缓存命中 {d['tok_cached'] / max(d['tok_in'], 1):.0%} · 输出 {tok(d['tok_out'])}",
              extra=stackbar([(d["tok_cached"], "i-cached", tip("命中缓存的输入", f"{d['tok_cached']:,}")),
                              (d["tok_in"] - d["tok_cached"], "i-uncached", tip("未缓存的输入", f"{d['tok_in'] - d['tok_cached']:,}")),
                              (d["tok_out"], "i-out", tip("输出", f"{d['tok_out']:,}"))], lg=True)),
          kpi("看过的图", str(d["views"]), " · ".join(f"{CAMS.get(c, c)} {n}" for c, n in _count(v["camera"] for v in s["views"])) or "一张没看")]
    return '<div class="kpis">' + "".join(k) + "</div>"


def _count(xs) -> list:
    out = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return sorted(out.items(), key=lambda kv: -kv[1])


def time_split(r: dict) -> str:
    d = r["d"]
    other = max(d["agent_s"] - d["gen_s"] - d["tool_s"], 0)
    parts = [(d["gen_s"], "i-gen", tip("等模型生成", f"{d['gen_s'] / 60:.1f} min")), (d["tool_s"], "i-tool", tip("跑工具（命令、看图、改文件）", f"{d['tool_s'] / 60:.1f} min")),
             (other, "i-other", tip("其他（harness 往返）", f"{other / 60:.1f} min"))]
    rows = "".join(f'<span><b class="{c.replace("i-", "sw-")}" style="{"background:var(--e-prelude)" if c == "i-other" else ""}"></b>{lab} {v / 60:.1f} min（{v / d["agent_s"]:.0%}）</span>'
                   for (v, c, _), lab in zip(parts, ("等模型", "跑工具", "其他")))
    return stackbar(parts, lg=True) + f'<div class="legend" style="margin-top:8px">{rows}</div>'


def video_panel(s: dict, page_dir: str) -> str:
    base = os.path.join(s["trial_dir"], "report")
    eps = [e for e in s["episodes"] if e.get("video")]
    if not eps:
        vid = os.path.join(s["trial_dir"], s["video"]) if s.get("video") else None
        if not vid or not os.path.exists(vid):
            return "<p class='mut'>没有视频。</p>"
        what = "验证端在新进程里回放 agent 交的 trajectory.npz" if s["mode"] == "full" else "sidecar 录的被评分段"
        return (f'<div class="player"><video class="pv" src="{esc(url(s, vid, page_dir))}" controls loop muted preload="metadata"></video>'
                f"<div><div style='font-weight:600'>{what}</div><p class='mut' style='font-size:12.5px'>回报 {num(s['result']['return'])} · "
                f"及格线 {num(s['result']['bar'], 0)}</p></div></div>")
    n, ms = len(s["episodes"]), s["spec"]["max_steps"]
    cap = lambda e: (f"ep{e['ep']}{'（被评分）' if e['ep'] == s['result']['graded_ep'] else ''} · {e['steps']} 步 · 回报 {num(e.get('return'))} · "
                     f"{KIND[ep_kind(e, e['ep'] == n - 1, ms)][0]}")
    src = lambda e: esc(url(s, os.path.join(base, e["video"]), page_dir))
    graded = next((e for e in eps if e["ep"] == s["result"]["graded_ep"]), eps[-1])
    picks, seen = [], set()
    for e, why in ([(graded, "被评分段")] + [(e, f"回报第 {k} 高") for k, e in enumerate(sorted(eps, key=lambda e: -(e.get("return") or -1e18))[:3], 1)]
                   + [(max(eps, key=lambda e: e["steps"]), "撑得最久")]):
        if e["ep"] not in seen and len(picks) < 5:
            picks.append((e, why)); seen.add(e["ep"])
    opts = "".join(f'<option value="{src(e)}"{" selected" if e is graded else ""}>{esc(cap(e))}</option>' for e in eps)
    cards = "".join(f'<figure data-video="{src(e)}" data-label="{esc(cap(e))}"><img loading="lazy" src="{esc(url(s, os.path.join(base, e["poster"]), page_dir))}" alt="">'
                    f"<figcaption><b>{why}</b><br>{esc(cap(e))}</figcaption></figure>" for e, why in picks if e.get("poster"))
    return (f'<div class="player"><video class="pv" src="{src(graded)}" poster="{esc(url(s, os.path.join(base, graded.get("poster") or ""), page_dir))}" controls loop muted preload="metadata"></video>'
            f'<div><div class="pcap" style="font-weight:600">{esc(cap(graded))}</div><select class="pick" onchange="play(this.value, null, this)">{opts}</select>'
            "<p class='mut' style='font-size:12.5px'>每段都是验证端事后回放重渲染的（25 fps，实时速度）；点时间轴或柱状图里的任一段也会在这里播放。"
            "被评分段按精确轨迹回放，其他段按日志里保留 5 位小数的动作回放（近似）。</p>"
            f'<div class="picks">{cards}</div></div></div>')


def views_gallery(s: dict, page_dir: str) -> str:
    if not s["views"]:
        return "<p class='mut'>模型一张图都没看。</p>"
    base = os.path.join(s["trial_dir"], "report")
    a0 = s["a0"]
    return '<div class="gal">' + "".join(
        f'<figure><a href="{esc(url(s, os.path.join(base, v["file"]), page_dir))}"><img loading="lazy" src="{esc(url(s, os.path.join(base, v["file"]), page_dir))}" alt=""></a>'
        f'<figcaption><span class="dot" style="background:var(--cam-{v["camera"].split("_")[0] if v["camera"] in ("room_camera",) else {"left_eye_camera": "left", "right_eye_camera": "right"}.get(v["camera"], v["camera"])})"></span>'
        f'#{v["n"]} · {CAMS.get(v["camera"], v["camera"])} · {(v["t"] - a0) / 60:.2f} min · ep{v["ep"]} 第 {v["step"]} 步<br>{esc(os.path.basename(v["path"] or ""))}</figcaption></figure>'
        for v in s["views"]) + "</div>"


def episode_table(s: dict, page_dir: str) -> str:
    a0, n, ms = s["a0"], len(s["episodes"]), s["spec"]["max_steps"]
    base = os.path.join(s["trial_dir"], "report")
    rows = []
    for e in s["episodes"]:
        did = e.get("did") or []
        said = ""
        if did:
            lead = next((x for x in did if x[1] == "msg"), did[0])
            short = lead[2][:160] + ("…" if len(lead[2]) > 160 else "")
            first = esc(short) if lead[1] == "msg" else f"<code>{esc(short)}</code>"
            more = "".join(f"<p><span class='mut'>{(t - a0) / 60:.2f} min</span> " + (esc(x) if k == "msg" else f"<code>{esc(x)}</code>") + "</p>" for t, k, x in did)
            said = first if len(did) == 1 and len(lead[2]) <= 160 else f"<details><summary>{first}</summary>{more}</details>"
        kind = ep_kind(e, e["ep"] == n - 1, ms)
        video = f'<a href="#" data-video="{esc(url(s, os.path.join(base, e["video"]), page_dir))}" data-label="ep{e["ep"]}" onclick="return false">▶</a>' if e.get("video") else "—"
        rows.append(f'<tr{" class=graded" if e["ep"] == s["result"]["graded_ep"] else ""}><td><b>{e["ep"]}</b></td><td class="n">{(e["t0"] - a0) / 60 if e["t0"] else 0:.2f}</td>'
                    f'<td class="n">{e["steps"]}</td><td><span class="legend"><span><b class="{KIND[kind][1].replace("e-", "sw-")}"></b>{KIND[kind][0]}</span></span></td>'
                    f'<td class="n">{num(e.get("return"))}</td><td class="n">{num(e.get("max_dx"))}</td><td class="n">{num(e.get("final_dx"))}</td>'
                    f'<td class="n">{e.get("views") or 0}</td><td>{video}</td><td style="max-width:520px">{said}</td></tr>')
    return ('<div class="tw"><table class="plain"><thead><tr><th>ep</th><th class="n">开始 (min)</th><th class="n">步数</th><th>怎么结束</th><th class="n">回报</th>'
            '<th class="n">最远前进 (m)</th><th class="n">最终 x (m)</th><th class="n">看图</th><th>视频</th><th>这段里它说了什么、跑了什么</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div><p class='mut' style='font-size:12.5px'>回报和位移来自验证端事后回放，agent 看不到。x 是骨盆沿任务前进方向的位移。</p>")


def leak_panel(s: dict) -> str:
    a0 = s["a0"]
    rows = [("输入 token 突增（>1.8 倍且 >15k）", "无" if not s["spikes"] else "; ".join(f"{(t - a0) / 60:.2f} min: {a:,} → {b:,}" for t, a, b in s["spikes"])),
            ("agent 写的、跑的里面出现可疑词", "无" if not s["leaks"] else "<br>".join(
                f"{(t - a0) / 60:.2f} min [{k}] <code>{esc(w)}</code>: {esc(x)}" for t, k, w, x in s["leaks"][:20]))]
    return '<table class="plain"><tbody>' + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows) + "</tbody></table>"


def run_detail(r: dict, task: dict, page_dir: str, phases: list, notes_rest: str | None, full: bool) -> str:
    s, d = r["s"], r["d"]
    limited = s["mode"] == "limited"
    H = [run_kpis(r, task)]
    if limited:
        clock = (f'<h3 style="margin-top:0">机器人：每段 episode</h3>{robot_timeline(s, phases, page_dir)}'
                 f"<h3>agent：每一刻在做什么</h3>{agent_timeline(s)}")
        sub = "两张图横轴相同，悬停看细节"
    else:
        clock, sub = agent_timeline(s), "full 模式里仿真在 agent 自己的进程里，没有逐步日志，只有 agent 这一侧；悬停看细节"
    H.append(f'<div class="panel"><div class="hd"><h2>会话时间轴</h2><span class="mut">agent 开始 → 结束，共 {d["agent_min"]:.1f} min；{sub}</span></div>{clock}</div>')
    tools = (f'<h3 style="margin-top:0">按类别</h3>{tool_summary(s)}<h3>按顺序的每一次调用</h3>{tool_sequence(s)}'
             f'<details class="fold" style="margin-top:12px;box-shadow:none"><summary>每一次调用的命令和输出<span class="mut">{len(s["calls"])} 次</span></summary>{tool_table(s)}</details>')
    if full:
        H.append(f'<div class="panel"><div class="hd"><h2>工具调用</h2><span class="mut">{len(s["calls"])} 次，按调用顺序（上面按时间）；'
                 f"悬停一次调用，时间轴上的同一次也会高亮</span></div>{tools}</div>")
    else:
        H.append(f'<details class="fold"><summary>工具调用<span class="mut">{len(s["calls"])} 次</span></summary>{tools}</details>')
    mine = agent_notes(s)
    if full:
        toks = stackbar([(d["tok_cached"], "i-cached", tip("命中缓存的输入", f"{d['tok_cached']:,}")),
                         (d["tok_in"] - d["tok_cached"], "i-uncached", tip("未缓存的输入", f"{d['tok_in'] - d['tok_cached']:,}")),
                         (d["tok_out"], "i-out", tip("输出", f"{d['tok_out']:,}"))], lg=True)
        spend = (f'<div class="panel"><div class="hd"><h2>时间和 token 花在哪</h2></div><h3 style="margin-top:0">agent 的 {d["agent_min"]:.1f} min</h3>{time_split(r)}'
                 f'<h3>{tok(d["tokens"])} tokens</h3>{toks}'
                 f'<div class="legend" style="margin-top:8px"><span><b class="sw-cached"></b>命中缓存 {tok(d["tok_cached"])}</span>'
                 f'<span><b class="sw-uncached"></b>未缓存 {tok(d["tok_in"] - d["tok_cached"])}</span>'
                 f'<span><b class="sw-out"></b>输出 {tok(d["tok_out"])}（推理 {tok(d["tok_reason"])}）</span></div></div>')
        if limited:
            curve = line_chart([reset_series(r, "var(--acc)", "这次")], d["budget_min"], max(d["resets"], 1), "agent 时间 (min)", "已用 reset",
                               h=210, caps=[(d["resets"], f"上限 {d['resets']} 次")])
            side = f'<div class="panel"><div class="hd"><h2>reset 与时间</h2><span class="mut">reset 用了多少（纵轴）随 agent 时间（横轴）</span></div>{curve}</div>'
        else:
            side = (f'<div class="panel notes"><div class="hd"><h2>agent 自己写的 NOTES.md</h2><span class="mut">交付物之一，不计分</span></div>{mine}</div>'
                    if mine else '<div class="panel"><div class="hd"><h2>agent 自己写的 NOTES.md</h2></div><p class="mut">没留 NOTES.md。</p></div>')
        H.append(f'<div class="grid2">{side}{spend}</div>')
    elif mine:
        H.append(f'<details class="fold"><summary>agent 自己写的 NOTES.md<span class="mut">交付物之一，不计分</span></summary><div class="notes">{mine}</div></details>')
    if limited:
        H.append(f'<div class="panel"><div class="hd"><h2>每段 episode</h2><span class="mut">颜色 = 怎么结束；黑框 = 被评分段；点柱子播放视频</span></div>{episode_chart(s, task, page_dir)}</div>')
    if notes_rest:
        H.append(f'<div class="panel notes"><div class="hd"><h2>{"分析" if full else "总结"}</h2><span class="mut">notes.md（人工写的）</span></div>{md(notes_rest)}</div>')
    H.append(f'<div class="panel"><div class="hd"><h2>视频</h2></div>{video_panel(s, page_dir)}</div>')
    if full:
        H.append(f'<div class="panel"><div class="hd"><h2>模型看过的图</h2><span class="mut">view_image 发给模型的原图（来自 codex 的会话日志）</span></div>{views_gallery(s, page_dir)}</div>')
        H.append(f'<div class="panel"><div class="hd"><h2>花费和 token</h2><span class="mut">{len(s["requests"])} 次请求，OpenRouter 账单逐条对上 {s["billed"]["found"]} 条</span></div>{cost_chart(s)}</div>')
    else:
        H.append(f'<details class="fold"><summary>模型看过的图<span class="mut">{len(s["views"])} 张</span></summary>{views_gallery(s, page_dir)}</details>')
        H.append(f'<details class="fold"><summary>花费和 token<span class="mut">{usd(d["cost"])} · {tok(d["tokens"])}</span></summary>{cost_chart(s)}</details>')
    if limited:
        H.append(f'<details class="fold"><summary>每段 episode 的明细<span class="mut">{len(s["episodes"])} 段</span></summary>{episode_table(s, page_dir)}</details>')
    H.append(f'<details class="fold"><summary>泄露检查<span class="mut">{"有标记，需要人看" if s["spikes"] or s["leaks"] else "无标记"}</span></summary>{leak_panel(s)}</details>')
    return "".join(H)


def atif_steps(trial: str) -> list[dict]:
    """agent/trajectory.json (ATIF): the trajectory Harbor writes for every agent, and what `harbor view` shows."""
    t = collect.jload(f"{trial}/agent/trajectory.json")
    steps = []
    for s in (t or {}).get("steps", []):
        calls = []
        for c in s.get("tool_calls") or []:
            a = c.get("arguments")
            if isinstance(a, dict) and len(a) == 1:
                a = next(iter(a.values()))
            calls.append((c.get("function_name") or "tool", a if isinstance(a, str) else json.dumps(a, ensure_ascii=False, indent=1)))
        results = []
        for r in (s.get("observation") or {}).get("results", []):
            items = r.get("content")
            if isinstance(items, str) and items.startswith("["):
                try:
                    items = ast.literal_eval(items)   # codex's content parts arrive as a Python repr
                except (ValueError, SyntaxError):
                    pass
            if not isinstance(items, list):
                items = [{"type": "text", "text": str(items)}]
            text = "".join(i.get("text", "") for i in items if isinstance(i, dict))
            imgs = [str(i.get("image_url"))[str(i.get("image_url")).find(",") + 1:] for i in items
                    if isinstance(i, dict) and "image" in str(i.get("type")) and str(i.get("image_url", "")).startswith("data:")]
            results.append((text, imgs))
        msg = s.get("message") or ""
        if isinstance(msg, list):
            msg = " ".join(m.get("text", "") for m in msg if isinstance(m, dict))
        steps.append({"id": s.get("step_id"), "t": collect.ts(s["timestamp"]) if s.get("timestamp") else None, "source": s.get("source"),
                      "message": msg, "calls": calls, "results": results, "metrics": s.get("metrics") or {}})
    return steps


def trajectory_html(s: dict, page_dir: str) -> str:
    """Every step the agent took, each tagged with where the robot was once the step's commands had run."""
    trial = s["trial_dir"]; out = os.path.join(trial, "report"); a0, a1 = s["a0"], s["a1"]
    steps = atif_steps(trial)
    if not steps:
        return "<p class='mut'>没有 agent/trajectory.json。</p>"
    limited = s["mode"] == "limited"
    _, eps, events = collect.sidecar(trial) if limited else ({}, [], [])
    bounds = [e["t0"] or a0 for e in eps] + [float("inf")]
    ep_at = lambda t: max(0, next(i for i in range(len(eps)) if bounds[i + 1] > t)) if eps else 0
    state = [(e["ts"], e.get("step", 0)) for e in events if e["ev"] in ("step", "observe", "reset")]
    os.makedirs(f"{out}/trajectory", exist_ok=True)
    cards, prev_ep, n_agent = [], 0, 0
    for i, st in enumerate(steps):
        if st["source"] != "agent":
            label = "任务说明（instruction.md，agent 收到的原样）" if st["source"] == "user" and st["message"].startswith("#") else \
                {"system": "系统提示", "user": "用户消息 / 环境信息"}.get(st["source"], str(st["source"]))
            cards.append(f"<details class='step sys'><summary>#{st['id']} · {label} · {len(st['message']):,} 字符</summary><pre>{esc(st['message'])}</pre></details>")
            continue
        n_agent += 1
        t_after = next((x["t"] for x in steps[i + 1:] if x["t"]), a1)   # the next step starts once this one's commands are back
        ep = ep_at(t_after); before = [x for x in state if x[0] <= t_after]; stp = before[-1][1] if before else 0
        badge = ("" if not limited else f"<span class='badge reset'>reset → ep{ep} 第 {stp} 步</span> · " if ep != prev_ep
                 else f"<span class='badge'>ep{ep} 第 {stp} 步</span> · ")
        prev_ep = ep
        m = st["metrics"]; imgs = sum(len(x[1]) for x in st["results"])
        lead = st["message"] or next((x for x in (collect.call_label(code) for _, code in st["calls"]) if x), ", ".join(n for n, _ in st["calls"]))
        lead = " ".join(lead.split())
        head = (f"#{st['id']} · {(st['t'] - a0) / 60:.2f} min · {badge}输入 {num(m.get('prompt_tokens'), 0)} / 输出 {num(m.get('completion_tokens'), 0)}"
                + (f" · ${m['cost_usd']:.4f}" if m.get("cost_usd") is not None else "") + (f" · {imgs} 张图" if imgs else "")
                + f" · {esc(lead[:140])}{'…' if len(lead) > 140 else ''}")
        body = [f"<p>{esc(st['message'])}</p>"] if st["message"] else []
        for name, code in st["calls"]:
            body.append(f"<div class='call'>调用 {esc(name)}</div><pre>{esc(code[:8000])}</pre>")
        for text, b64s in st["results"]:
            text = pretty_output(text)
            if text.strip():
                body.append(f"<div class='call'>输出</div><pre>{esc(text[:6000])}{'…（截断）' if len(text) > 6000 else ''}</pre>")
            for k, b in enumerate(b64s):
                f = f"trajectory/step{st['id']}_{k}.png"
                if not os.path.exists(os.path.join(out, f)):
                    with open(os.path.join(out, f), "wb") as fh:
                        fh.write(base64.b64decode(b))
                src = esc(url(s, os.path.join(out, f), page_dir))
                body.append(f"<a href='{src}'><img src='{src}' loading='lazy' alt=''></a>")
        cards.append(f"<details class='step'><summary>{head}</summary>{''.join(body)}</details>")
    where = "；每步都标了它的命令跑完后机器人在哪一段、第几步" if limited else ""
    return (f"<p class='mut'>来自 <code>agent/trajectory.json</code>（ATIF 格式：Harbor 把每种 agent 的原生日志都转成它，harbor view 的 Trajectory 页渲染的也是它）。"
            f"共 {len(steps)} 步，其中 agent 的 {n_agent} 步{where}。</p>{''.join(cards)}")


def records_html(s: dict, page_dir: str) -> str:
    """The rest of what `harbor view` shows for a trial: files, each folded."""
    trial = s["trial_dir"]

    def block(title, path, tail=None, limit=60000):
        if not os.path.isfile(path):
            return ""
        txt = open(path, errors="replace").read()
        if path.endswith(".json"):
            try:
                txt = json.dumps(json.loads(txt), ensure_ascii=False, indent=1)
            except ValueError:
                pass
        note, lines = "", txt.splitlines()
        if tail and len(lines) > tail:
            txt, note = "\n".join(lines[-tail:]), f"，最后 {tail} / {len(lines):,} 行"
        body = f"<pre>{esc(txt[:limit])}{chr(10) + '…（截断）' if len(txt) > limit else ''}</pre>" if txt.strip() else "<p class='mut'>（空文件）</p>"
        return (f"<details class='step'><summary>{title} <span class='mut'>· <a href='{esc(url(s, path, page_dir))}'>{esc(os.path.relpath(path, trial))}</a> · "
                f"{os.path.getsize(path):,} B{note}</span></summary>{body}</details>")
    parts = ["<h3>agent 留下的</h3>", block("驱动脚本 gen.py", f"{trial}/artifacts/app/output/gen.py"),
             block("NOTES.md（full 模式的交付物之一）", f"{trial}/artifacts/app/output/NOTES.md")]
    outs = sorted(p for p in glob.glob(f"{trial}/artifacts/app/output/**/*", recursive=True) if os.path.isfile(p))
    if outs:
        parts.append(f"<details class='step'><summary>/app/output 里的全部文件 <span class='mut'>· {len(outs)}</span></summary><p>"
                     + "<br>".join(f"<a href='{esc(url(s, p, page_dir))}'>{esc(os.path.relpath(p, f'{trial}/artifacts/app/output'))}</a> "
                                   f"<span class='mut'>{os.path.getsize(p):,} B</span>" for p in outs) + "</p></details>")
    parts += ["<h3>验证</h3>", block("reward.json", f"{trial}/verifier/reward.json"), block("diagnostics.json（回报、及格线、回放用时）", f"{trial}/verifier/diagnostics.json"),
              block("test-stdout.txt", f"{trial}/verifier/test-stdout.txt"),
              block("grade.log", f"{trial}/verifier/grade.log")]
    parts += ["<h3>Harbor</h3>", block("result.json（各阶段时间、token、异常）", f"{trial}/result.json"), block("config.json", f"{trial}/config.json"),
              block("lock.json", f"{trial}/lock.json"), block("exception.txt", f"{trial}/exception.txt"), block("trial.log", f"{trial}/trial.log", tail=400)]
    parts += ["<h3>agent 日志</h3>"] + [block(os.path.relpath(p, f"{trial}/agent"), p, tail=400)
                                         for p in sorted(glob.glob(f"{trial}/agent/*.txt") + glob.glob(f"{trial}/agent/setup/**/*.txt", recursive=True))]
    files = [("被评分的回放视频", f"{trial}/{s['video']}" if s.get("video") else ""), ("每段的视频", f"{trial}/report/episodes"),
             ("模型看过的图", f"{trial}/report/agent_views"), ("agent 留在 /app/output 的", f"{trial}/artifacts/app/output"),
             ("sidecar 的事件日志、轨迹、final.json", f"{trial}/artifacts/data"), ("agent 的原始日志", f"{trial}/agent"),
             ("验证输出", f"{trial}/verifier"), ("策略总结（人工写的）", f"{trial}/report/notes.md"), ("测量结果", f"{trial}/report/summary.json")]
    parts += ["<h3>文件（绝对路径）</h3><table class='plain'><tbody>" + "".join(f"<tr><th>{k}</th><td><code>{esc(v)}</code></td></tr>" for k, v in files
                                                                              if v and os.path.exists(v)) + "</tbody></table>"]
    return "".join(parts)


def task_page(task: dict, cols: list) -> str:
    page_dir = os.path.join(OUT, "tasks")
    runs, mains = task["runs"], task["main"]
    H = []
    cls = task["cls"] if task["cls_name"] in ("", task["cls"]) else f'{task["cls"]} · {task["cls_name"]}'
    chips = [f'<span class="chip">{esc(task["robot"])}</span>', f'<span class="chip" data-tip="{tip(task["cls_long"] or cls, task["one_liner"])}">{esc(cls)}</span>',
             f'<span class="chip">及格线 {num(task["bar"], 0)}</span>', f'<span class="chip">全零动作 {num(task["nop"])}</span>',
             f'<span class="chip">{task["max_steps"]} 步 / episode</span>']
    cams = ""
    cam_dir = os.path.join(OUT, "assets", "cameras", task["task"])
    if os.path.isdir(cam_dir):
        shots = [(c, stamp(os.path.join(cam_dir, f"{c}.png"))) for c in ("left_eye_camera", "right_eye_camera", "room_camera")
                 if os.path.exists(os.path.join(cam_dir, f"{c}.png"))]
        cams = '<div class="cams">' + "".join(
            f'<figure><a href="../assets/cameras/{task["task"]}/{c}.png{v}"><img src="../assets/cameras/{task["task"]}/{c}.png{v}" alt=""></a><figcaption>{CAMS[c]} · t=0</figcaption></figure>'
            for c, v in shots) + "</div>"
    pose = f"外部相机位姿 <code>{esc(task['pose'])}</code>（lookat x,y,z · 距离 · 方位角 · 俯仰角）" if task["pose"] else "外部相机：录像相机在 t=0 的位姿"
    H.append(f'<div class="hero"><div><div class="mut">#{task["n"]}</div><h1>{esc(task["task"])}</h1><div class="row">{"".join(chips)}</div>'
             f'<p class="statement"><b>任务：</b>{esc(task["statement"])}</p><p class="mut" style="font-size:12.5px;margin:6px 0 0">limited 模式的相机（t=0 的三张图在右边）：{pose}</p>'
             f'<p class="mut" style="font-size:12.5px;margin:2px 0 0;max-width:760px">{esc(task["camera_note"])}</p></div>{cams}</div>')
    verdicts = []
    for col in cols:
        main = mains.get(col)
        if main:
            one, _, _ = notes_of(main["s"])
            d = main["d"]
            verdicts.append(f'<div class="panel verdict {"v-ok" if d["pass"] else "v-bad"}"><div>{status_chip(main, big=True)}</div><div class="one">'
                            f'<div style="font-weight:600;margin-bottom:2px">{esc(col_name(col))} · 回报 {num(d["score"])} / {num(d["bar"], 0)}</div>'
                            f'{md(one) if one else "<p class=mut>还没写总结（notes.md）。</p>"}</div></div>')
        else:
            mid = next((k for k, v in MODELS.items() if v == col[0]), col[0])
            cmd = run_command(task, mid, col[1])
            verdicts.append(f'<div class="panel verdict"><div>{status_chip(None, big=True)}</div><div class="one">'
                            f"<div style='font-weight:600'>{esc(col_name(col))}：还没在标准配置下跑过。</div>"
                            f'<div class="cmd" style="margin-top:8px"><pre>{esc(cmd)}</pre><button class="btn" data-copy="{esc(cmd)}">复制</button></div></div></div>')
    H.append(f'<div class="grid2" style="margin-top:18px">{"".join(verdicts)}</div>')
    if runs:
        H.append(f'<div class="sect"><h2>所有运行</h2><span class="mut">{len(runs)} 次；runs.csv 里的每一行</span></div>')
        H.append(compare_table(runs, list(mains.values()), page_dir))
    have = [c for c in cols if c in mains]
    if have:
        H.append('<div class="sect"><h2>主运行</h2><span class="mut">每一列最新的标准配置运行</span></div>')
        H.append('<div class="tabs" data-tabs="main">' + "".join(f'<button data-tab="{k}" class="{"on" if k == 0 else ""}">{esc(col_name(c))}</button>'
                                                                 for k, c in enumerate(have)) + "</div>")
        for k, col in enumerate(have):
            main = mains[col]; s = main["s"]
            _, rest, phases = notes_of(s)
            date = dt.datetime.fromtimestamp(s["a0"]).strftime("%Y-%m-%d %H:%M")
            H.append(f'<section data-pane="main:{k}" class="{"on" if k == 0 else ""}"><p class="mut" style="margin:0 0 12px">{config_chips(main)} · {date} · '
                     f'<a href="../runs/{main["id"]}.html">完整轨迹和 Harbor 记录 →</a></p>{run_detail(main, task, page_dir, phases, rest, full=True)}</section>')
    return page(f"{task['task']} · HumanoidBench", "".join(H), 1, [(task["task"], None)])


def compare_table(runs: list, mains: list, page_dir: str) -> str:
    top_cost = max((r["d"]["cost"] or 0 for r in runs), default=1) or 1
    rows = []
    for r in sorted(runs, key=lambda r: (r not in mains, not r["standard"], r["mode"], r["date"], r["i"])):
        d, s = r["d"], r["s"]
        name = f'<b>{esc(r["model_name"])}</b>' + (' <span class="chip acc">主运行</span>' if r in mains else "")
        link = f'<a href="../runs/{r["id"]}.html">{name}</a>' if r["id"] else name
        res = status_chip(r) if r["result"] in ("pass", "fail") else f'<span class="chip na">{esc(r["result"])}</span>'
        prog, used, amin = d.get("prog"), d["resets_used"], d["agent_min"]
        prog_c = pcell(prog, ("—" if prog is None else f"{prog:.3f}") + f" <small>{num(d['score'])}/{num(d['bar'], 0)}</small>", "ok" if d["pass"] else "bad")
        reset_c = pcell((used or 0) / d["resets"] if d["resets"] else None, f"{'—' if used is None else used}/{d['resets']}", "warn") if r["mode"] == "limited" else "<span class='mut'>不限</span>"
        time_c = pcell(amin / d["budget_min"] if amin else None, f"{amin:.1f} min" if amin else "—")
        cost_c = pcell((d["cost"] or 0) / top_cost if d["cost"] is not None else None, usd(d["cost"]) + (f" <small>{tok(d['tokens'])}</small>" if d.get("tokens") else ""), "na",
                       tip("花费和 tokens", usd(d["cost"]), f"{d['tokens']:,} tokens（缓存命中 {d['tok_cached'] / max(d['tok_in'], 1):.0%}）") if d.get("tokens") else "")
        v = lambda x: "" if x is None else x
        rows.append(f'<tr class="{"main" if r in mains else "" if s else "dim"}"><td class="run">{link}<div class="row" style="margin-top:3px">{config_chips(r)}</div>'
                    f'<div class="mut" style="font-size:12px;margin-top:3px;max-width:420px">{esc(r["date"])} · {esc(r["note"])}{"" if s else "（原始数据已删）"}</div></td>'
                    f'<td>{res}</td><td data-v="{v(prog)}" style="min-width:190px">{prog_c}</td>'
                    f'<td data-v="{v(used)}">{reset_c}</td><td data-v="{v(amin)}">{time_c}</td><td data-v="{v(d["cost"])}" style="min-width:150px">{cost_c}</td>'
                    f'<td class="sess" style="min-width:186px">{mini_timeline(s, (d["budget_min"] or 60) * 60, 180) if s else ""}</td></tr>')
    return ('<div class="panel"><div class="tw"><table class="data"><thead><tr><th>运行</th><th>结果</th><th data-sort>离及格线 <span class="faint">回报/及格线</span></th>'
            '<th data-sort>reset</th><th data-sort>agent 用时</th><th data-sort>花费 <span class="faint">tokens</span></th><th>会话（整个预算）</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div></div>")


def run_page(r: dict, task: dict) -> str:
    page_dir = os.path.join(OUT, "runs")
    s = r["s"]
    one, rest, phases = notes_of(s)
    notes = "\n\n".join(x for x in (one, rest) if x)
    date = dt.datetime.fromtimestamp(s["a0"]).strftime("%Y-%m-%d %H:%M")
    H = [f'<div class="mut">{esc(task["task"])} · {esc(s["mode"])} 模式 · {date} · trial <code>{esc(s["trial"])}</code></div>'
         f'<h1>{esc(task["task"])} · {esc(r["model_name"])}</h1><div class="row" style="margin-bottom:14px">{status_chip(r)} {config_chips(r)}</div>']
    if r in task["main"].values():
        H.append(f'<p class="mut">这是 {esc(task["task"])} 在这一列的主运行，完整分析在<a href="../tasks/{task["task"]}.html">任务页</a>；这里多了完整轨迹和 Harbor 记录。</p>')
    H.append(run_detail(r, task, page_dir, phases, notes, full=False))
    H.append(f'<details class="fold"><summary>完整轨迹<span class="mut">agent/trajectory.json</span></summary>{trajectory_html(s, page_dir)}</details>')
    H.append(f'<details class="fold"><summary>Harbor 的其他记录<span class="mut">脚本、验证、result/config/lock、日志、文件</span></summary>{records_html(s, page_dir)}</details>')
    return page(f"{task['task']} · {r['model_name']} · {s['mode']} · {date}", "".join(H), 1,
                [(task["task"], f"../tasks/{task['task']}.html"), (f"{r['model_name']} · {s['mode']} · {date}", None)])


def overview(tasks: list, cols: list, runs: list) -> str:
    lim = STANDARD["limited"]
    H = ['<h1>HumanoidBench 结果</h1><p class="sub">coding agent 在 24 个选出来的 HumanoidBench 任务上的表现（23 个计分 + sit_simple 夹具）。'
         "两种模式：limited 里 agent 只有头部相机、关节角和角速度、IMU 和外部相机，reset 有上限；full 里它有完整的物理状态，reset 不限，"
         "交一条轨迹由验证端回放打分。两种都没有 reward。</p>"
         '<div class="row" style="margin-bottom:16px"><span class="chip acc">标准配置</span><span class="chip">Codex（经 OpenRouter）</span>'
         f'<span class="chip">effort {lim["effort"]}</span><span class="chip">{lim["budget_min"]} min</span>'
         f'<span class="chip">limited：{lim["resets"]} 次 reset · IMU · 外部相机</span><span class="chip">full：reset 不限 · 完整状态</span><span class="chip">无 reward</span></div>']
    H.append(mode_compare(tasks, cols))
    have = [c for c in cols if any(r["standard"] and r["col"] == c for r in runs)] or cols[:1]
    H.append('<div class="sect"><h2>每一列</h2><span class="mut">一个模型在一种模式下，每个任务最新的标准配置运行</span></div>')
    H.append('<div class="tabs" data-tabs="m">' + "".join(f'<button data-tab="{k}" class="{"on" if k == 0 else ""}">{esc(col_name(c))}</button>' for k, c in enumerate(have)) + "</div>")
    tasks_by = {t["task"]: t for t in tasks}
    for k, col in enumerate(have):
        mode = col[1]
        per = {t["task"]: t["main"].get(col) or next((r for r in reversed(t["runs"]) if r["standard"] and r["col"] == col), None) for t in tasks}
        done = [(t, per[t["task"]]) for t in tasks if per[t["task"]]]
        live = [r for _, r in done if r["s"]]
        n_pass = sum(r["d"]["pass"] for _, r in done)
        cost = sum(r["d"]["cost"] or 0 for _, r in done)
        toks = sum(r["d"].get("tokens") or 0 for r in live)
        cached = sum(r["d"].get("tok_cached") or 0 for r in live); tin = sum(r["d"].get("tok_in") or 0 for r in live)
        amin = sum(r["d"]["agent_min"] or 0 for _, r in done)
        used = [r["d"]["agent_min"] / r["d"]["budget_min"] for _, r in done if r["d"]["agent_min"]]
        state = lambda t: "未跑" if not per[t["task"]] else "通过" if per[t["task"]]["d"]["pass"] else "未通过"
        seg = "".join(f'<i class="{ {"通过": "ok", "未通过": "bad"}.get(state(t), "")}" data-tip="{tip("#" + str(t["n"]) + " " + t["task"], state(t))}"></i>'
                      for t in tasks)
        nxt = next((t for t in tasks if not per[t["task"]]), None)
        mid = next((kk for kk, v in MODELS.items() if v == col[0]), col[0])
        if mode == "limited":
            out_of = sum(1 for _, r in done if r["d"]["resets_used"] is not None and r["d"]["resets_used"] >= (r["d"]["resets"] or 1e9))
            last = kpi("reset 用完", f'{out_of} <small>/ {len(done)}</small>', "reset 用完才停下的运行")
        else:
            late = sum(1 for _, r in done if r["s"] and r["s"]["result"].get("timed_out"))
            last = kpi("用满 60 min", f'{late} <small>/ {len(done)}</small>', "到时被停的运行（轨迹照样打分）")
        P = [f'<section data-pane="m:{k}" class="{"on" if k == 0 else ""}">', '<div class="kpis">',
             kpi("已跑", f'{len(done)} <small>/ {len(tasks)}</small>', f"通过 {n_pass} · 未通过 {len(done) - n_pass} · 未跑 {len(tasks) - len(done)}", wide=True, extra=f'<div class="seg">{seg}</div>'),
             kpi("通过", f'{n_pass} <small>/ {len(done)}</small>', "跑过的任务里", cls="ok" if n_pass else ""),
             kpi("花费", usd(cost), f"平均每个任务 {usd(cost / len(done))}" if done else ""),
             kpi("tokens", tok(toks), f"缓存命中 {cached / tin:.0%}" if tin else ""),
             kpi("agent 用时", f'{amin:.1f} <small>min</small>', f"每次用了预算的 {min(used):.0%}–{max(used):.0%}" if used else ""), last, "</div>"]
        if nxt:
            cmd = run_command(nxt, mid, mode)
            P.append(f'<div class="panel"><div class="next"><div><div class="mut" style="font-size:12.5px">下一个（按表格顺序）</div><div class="big">#{nxt["n"]} {esc(nxt["task"])}'
                     f' <span class="chip">{esc(nxt["robot"])}</span> <span class="chip">{esc(nxt["cls"])} · {esc(nxt["cls_name"])}</span></div></div>'
                     f'<div class="cmd" style="flex:1;min-width:320px"><pre>{esc(cmd)}</pre><button class="btn" data-copy="{esc(cmd)}">复制</button></div></div></div>')
        P.append(main_table(tasks, per, mode))
        if live:
            order = [r for t, r in done if r["s"]]
            cols_c = {r["task"]: RUN_COLORS[i % len(RUN_COLORS)] for i, r in enumerate(order)}
            P.append('<div class="grid2">')
            if mode == "limited":
                cap = int(lim["resets"])
                P.append(f'<div class="panel"><div class="hd"><h2>reset 用得有多快</h2><span class="mut">每条线一个任务：已用 reset 随 agent 时间</span></div>'
                         f'{line_chart([reset_series(r, cols_c[r["task"]], r["task"]) for r in order], float(lim["budget_min"]), cap, "agent 时间 (min)", "已用 reset", h=230, caps=[(cap, f"上限 {cap} 次")])}</div>')
            P.append('<div class="panel"><div class="hd"><h2>时间花在哪</h2><span class="mut">等模型生成 · 跑工具 · 其他</span></div>'
                     + hbars([(r["task"], f"tasks/{r['task']}.html", [(r["d"]["gen_s"], "gen", tip("等模型生成", f"{r['d']['gen_s'] / 60:.1f} min")),
                                                                      (r["d"]["tool_s"], "tool", tip("跑工具", f"{r['d']['tool_s'] / 60:.1f} min")),
                                                                      (max(r["d"]["agent_s"] - r["d"]["gen_s"] - r["d"]["tool_s"], 0), "e-prelude", tip("其他", ""))],
                               f"{r['d']['agent_min']:.1f} min · 模型 {r['d']['gen_s'] / r['d']['agent_s']:.0%}") for r in order])
                     + '<div class="legend"><span><b class="sw-gen"></b>等模型生成</span><span><b class="sw-tool"></b>跑工具</span><span><b class="sw-prelude"></b>其他</span></div></div>')
            P.append('<div class="panel"><div class="hd"><h2>token 和花费</h2><span class="mut">输入（命中缓存 / 未缓存）和输出</span></div>'
                     + hbars([(r["task"], f"tasks/{r['task']}.html", [(r["d"]["tok_cached"], "f-cached", tip("命中缓存的输入", f"{r['d']['tok_cached']:,}")),
                                                                      (r["d"]["tok_in"] - r["d"]["tok_cached"], "f-uncached", tip("未缓存的输入", f"{r['d']['tok_in'] - r['d']['tok_cached']:,}")),
                                                                      (r["d"]["tok_out"], "f-out", tip("输出", f"{r['d']['tok_out']:,}（推理 {r['d']['tok_reason']:,}）"))],
                               f"{tok(r['d']['tokens'])} · {usd(r['d']['cost'])}") for r in order])
                     + '<div class="legend"><span><b class="sw-cached"></b>命中缓存</span><span><b class="sw-uncached"></b>未缓存</span><span><b class="sw-out"></b>输出</span></div></div>')
            label = lambda kk: kind_label(kk, {"mode": mode})
            P.append('<div class="panel"><div class="hd"><h2>工具调用构成</h2><span class="mut">每次运行的调用次数，按类别</span></div>'
                     + hbars([(r["task"], f"tasks/{r['task']}.html", [(sum(tool_kind(c) == kk for c in r["s"]["calls"]), TOOLS[kk][1],
                                                                       tip(label(kk), f"{sum(tool_kind(c) == kk for c in r['s']['calls'])} 次")) for kk in TOOLS],
                               f"{len(r['s']['calls'])} 次") for r in order])
                     + '<div class="legend">' + "".join(f'<span><b style="background:{v[1]}"></b>{label(kk)}</span>' for kk, v in TOOLS.items()
                                                       if mode == "limited" or kk != "robot") + "</div></div>")
            if mode == "limited":
                P.append(f'<div class="panel"><div class="hd"><h2>每段 episode 撑了多少步</h2><span class="mut">一个点一段，◆ 被评分段，竖线 = 全零动作</span></div>{strip_chart(order, tasks_by)}</div>')
            P.append("</div>")
        P.append("</section>")
        H.append("".join(P))
    local = [r for r in runs if r["s"]]
    if local:
        H.append(f'<div class="sect"><h2>每次运行的各阶段</h2><span class="mut">Harbor 的 trial，从开始算起</span></div><div class="panel">{stage_chart(local)}</div>')
    other = [r for r in runs if not r["standard"]]
    if other:
        H.append(f'<div class="sect"><h2>不在标准配置下的运行</h2><span class="mut">{len(other)} 次，详见 runs.csv</span></div>')
        rows = []
        for r in other:
            d = r["d"]
            link = f'<a href="runs/{r["id"]}.html">{esc(r["model_name"])}</a>' if r["id"] else esc(r["model_name"])
            rows.append(f'<tr class="{"" if r["s"] else "dim"}"><td class="n">{esc(r["date"])}</td><td class="task"><a href="tasks/{r["task"]}.html">{esc(r["task"])}</a></td>'
                        f'<td>{link}</td><td style="min-width:290px"><div class="row" style="gap:4px">{config_chips(r)}</div></td><td>{status_chip(r) if r["result"] in ("pass", "fail") else esc(r["result"])}</td>'
                        f'<td class="n">{num(d["score"])}</td><td class="n">{usd(d["cost"])}</td><td class="n">{num(d["agent_min"], 1)}</td>'
                        f'<td class="mut" style="font-size:12.5px;max-width:380px">{esc(r["note"])}</td></tr>')
        H.append('<div class="panel"><div class="tw"><table class="data"><thead><tr><th>日期</th><th>任务</th><th>模型</th><th>配置</th><th>结果</th><th class="n">回报</th>'
                 '<th class="n">花费</th><th class="n">min</th><th>备注</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div></div>")
    return page("HumanoidBench 结果", "".join(H), 0)


def main_table(tasks: list, per: dict, mode: str) -> str:
    done = [r for r in per.values() if r]
    top_cost = max((r["d"]["cost"] or 0 for r in done), default=1) or 1
    top_tok = max((r["d"].get("tokens") or 0 for r in done), default=1) or 1
    limited = mode == "limited"
    rows = []
    for t in tasks:
        r = per[t["task"]]
        head = (f'<td class="n" data-v="{t["n"]}">{t["n"]}</td><td class="task"><a href="tasks/{t["task"]}.html">{esc(t["task"])}</a>'
                f'<div class="mut" data-tip="{tip(t["cls"] + " · " + t["cls_long"], t["one_liner"])}">{esc(t["robot"])} · {esc(t["cls"])}{"" if t["cls_name"] in ("", t["cls"]) else " " + esc(t["cls_name"])}</div></td>')
        if not r:
            rows.append(f'<tr class="dim">{head}<td data-v="-1">{status_chip(None)}</td>'
                        f'<td class="sub" colspan="{6 if limited else 5}" data-v="">及格线 {num(t["bar"], 0)} · 全零动作 {num(t["nop"])}</td></tr>')
            continue
        d, s = r["d"], r["s"]
        prog = d.get("prog")
        how = tip("离及格线", f"({num(d['score'])} − 全零 {num(t['nop'])}) / (及格线 {num(t['bar'], 0)} − 全零)")
        prog_c = pcell(prog, ("—" if prog is None else f"{prog:.3f}") + f" <small>{num(d['score'])}/{num(d['bar'], 0)}</small>", "ok" if d["pass"] else "bad", how)
        used = f"{d['resets_used']}/{d['resets']}"
        reset_c = f'<td data-v="{d["resets_used"]}">{pcell(d["resets_used"] / d["resets"] if d["resets"] else 1, used, "warn")}</td>' if limited else ""
        time_c = pcell(d["agent_min"] / d["budget_min"], f"{d['agent_min']:.1f} min")
        rows.append(f"<tr>{head}<td data-v=\"{1 if d['pass'] else 0}\">{status_chip(r)}</td>"
                    f'<td data-v="{"" if prog is None else prog}" style="min-width:200px">{prog_c}</td>'
                    f'{reset_c}<td data-v="{d["agent_min"]}">{time_c}</td>'
                    f'<td data-v="{d["cost"]}">{pcell(d["cost"] / top_cost, usd(d["cost"]), "na")}</td>'
                    f'<td data-v="{d.get("tokens") or ""}">{tok_stack(d, top_tok)}</td>'
                    f'<td class="sess">{mini_timeline(s, d["budget_min"] * 60) if s else ""}</td></tr>')
    if limited:
        lg = ('<div class="legend" style="margin:10px 2px 0">' + "".join(f'<span><b class="sw-{c}"></b>{n}</span>' for c, n in
              (("prelude", "读文档"), ("failed", "倒下 / 失败"), ("reset", "agent 主动 reset"), ("success", "成功"), ("timeout", "步数到上限"), ("wrapup", "收尾"), ("unused", "没用到的预算")))
              + "<span>会话列：整个预算，一块是一段 episode，浅色是它结束后到下一次 reset</span></div>")
    else:
        lg = ('<div class="legend" style="margin:10px 2px 0"><span><b class="sw-running"></b>agent 运行</span><span><b class="sw-unused"></b>没用到的预算</span>'
              "<span>会话列：整个预算；full 模式没有 episode 日志</span></div>")
    reset_h = "<th data-sort>reset</th>" if limited else ""
    return ('<div class="panel"><div class="tw"><table class="data"><thead><tr><th class="n" data-sort="asc">#</th><th data-sort="asc">任务</th><th data-sort>状态</th>'
            f'<th data-sort>离及格线 <span class="faint">全零=0，及格=1 · 回报/及格线</span></th>{reset_h}<th data-sort>agent 用时</th>'
            '<th data-sort>花费</th><th data-sort>tokens</th><th>会话（整个预算）</th></tr></thead><tbody>' + "".join(rows) + f"</tbody></table></div>{lg}</div>")



def agent_notes(s: dict) -> str:
    """The NOTES.md a full-mode agent leaves next to its trajectory (at most 20 lines, its own account)."""
    p = os.path.join(s["trial_dir"], "artifacts", "app", "output", "NOTES.md")
    return md(open(p, errors="replace").read()) if os.path.exists(p) else ""


def col_name(col: tuple) -> str:
    return f"{col[0]} · {col[1]}"


def mode_compare(tasks: list, cols: list) -> str:
    """For each model with both modes: every task run in either, the two results side by side."""
    models = [m for m in dict.fromkeys(c[0] for c in cols) if (m, "limited") in cols and (m, "full") in cols]
    out = []
    for m in models:
        rows = []
        for t in tasks:
            a, b = t["main"].get((m, "limited")), t["main"].get((m, "full"))
            if not (a or b):
                continue
            cell = lambda r: (pcell(r["d"].get("prog"), f'{status_chip(r)} {num(r["d"]["score"])}', "ok" if r["d"]["pass"] else "bad")
                              if r else '<span class="mut">未跑</span>')
            rows.append(f'<tr><td class="task"><a href="tasks/{t["task"]}.html">{esc(t["task"])}</a><div class="mut">{esc(t["robot"])} · {esc(t["cls"])}</div></td>'
                        f'<td style="min-width:230px">{cell(a)}</td><td style="min-width:230px">{cell(b)}</td>'
                        f'<td class="n">{num(t["bar"], 0)}</td><td class="n">{num(t["nop"])}</td></tr>')
        if rows:
            out.append(f'<div class="sect"><h2>两种模式对比</h2><span class="mut">{esc(m)}，标准配置；条长 = 离及格线（全零 = 0，及格 = 1）</span></div>'
                       '<div class="panel"><div class="tw"><table class="data"><thead><tr><th>任务</th><th>limited</th><th>full</th><th class="n">及格线</th>'
                       '<th class="n">全零动作</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div></div>")
    return "".join(out)
