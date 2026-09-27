"""The hand-written analysis, results/<bench>/analysis/: overview.md on the overview, <task>.md on each task page.

A file is Markdown: an optional **一句话** paragraph, then `## ` sections. A section named after a model ("GPT-6 Luna")
holds `### limited`, `### full` and `### 两种模式`; each mode's card opens with its measured numbers (on a task page its
main run, on the overview the column over every task it ran), so the prose only has to say why. Any other section
(总体结论, 模型对比, 改进意见) is shown as written, in the file's order; the overview can append a table to one."""
from __future__ import annotations

import os
import re
import statistics

from common import ANALYSIS, WHY, esc, num, usd
from data import notes_of
from widgets import md, pcell, status_chip

MODE = {"limited": "limited · 模拟真机", "full": "full · 完整状态"}
ACROSS = "两种模式"
ENDED = {"success": "通过", "resets_used_up": "reset 用完", "timeout": "时间用完", "quit_after_end": "自己停下",
         "quit_mid_episode": "自己停下"}


def load(name: str) -> tuple[str | None, list[dict]]:
    """analysis/<name>.md as (its 一句话 paragraph, [{"title", "body", "subs": {title: body}}]); (None, []) if absent."""
    path = os.path.join(ANALYSIS, f"{name}.md")
    if not os.path.exists(path):
        return None, []
    head, *parts = re.split(r"^## +", open(path).read(), flags=re.M)
    secs = []
    for part in parts:
        title, _, body = part.partition("\n")
        first, *subs = re.split(r"^### +", body, flags=re.M)
        secs.append({"title": title.strip(), "body": first.strip(),
                     "subs": {t.strip(): b.strip() for t, _, b in (s.partition("\n") for s in subs)}})
    return head.strip() or None, secs


def run_facts(r: dict) -> str:
    """One run's numbers, as its card opens: how far towards the bar, the return, resets, time, cost, how it ended."""
    d, res = r["d"], r["s"]["result"]
    prog = d.get("prog")
    ended = ENDED.get(res["why"], WHY.get(res["why"], res["why"])) if r["mode"] == "limited" else \
        "通过" if d["pass"] else "用满 60 min" if res.get("timed_out") else "自己结束"
    bits = [f"回报 <b>{num(d['score'], 1)}</b> / {num(d['bar'], 0)}"]
    if r["mode"] == "limited":
        bits.append(f"reset {d['resets_used']}/{d['resets']}")
    bits += [f"{d['agent_min']:.1f} min", usd(d["cost"]), ended]
    return (f'<div class="facts">{pcell(prog, "离及格线 " + ("—" if prog is None else f"{prog:.2f}"), "ok" if d["pass"] else "bad")}'
            + "".join(f"<span>{b}</span>" for b in bits) + "</div>")


def col_facts(tasks: list, col: tuple) -> str:
    """A column over every scored task it ran (each task's main run; not the fixture): passes, the median distance to the
    bar, time, cost, endings."""
    runs = [t["main"][col] for t in tasks if col in t["main"] and t["cls"] != "fixture"]
    if not runs:
        return ""
    progs = [r["d"]["prog"] for r in runs if r["d"].get("prog") is not None]
    n_pass = sum(r["d"]["pass"] for r in runs)
    if col[1] == "limited":
        ends = {}
        for r in runs:
            e = ENDED.get(r["s"]["result"]["why"], "其他")
            ends[e] = ends.get(e, 0) + 1
        ended = " · ".join(f"{k} {v}" for k, v in sorted(ends.items(), key=lambda kv: -kv[1]))
    else:
        ended = f"用满 60 min {sum(bool(r['s']['result'].get('timed_out')) for r in runs)}"
    med = statistics.median(progs) if progs else None
    bits = [f"<b>{n_pass}/{len(runs)}</b> 通过", f"离及格线中位数 {num(med)}",
            f"平均 {statistics.mean(r['d']['agent_min'] for r in runs):.0f} min", f"共 {usd(sum(r['d']['cost'] or 0 for r in runs))}", ended]
    return (f'<div class="facts">{pcell(med, f"{len(runs)} 个计分任务", "ok" if n_pass == len(runs) else "bad")}'
            + "".join(f"<span>{b}</span>" for b in bits) + "</div>")


def mode_card(mode: str, facts: str, chip: str, text: str | None, ok: bool | None) -> str:
    tone = "" if ok is None else " v-ok" if ok else " v-bad"
    body = md(text) if text else '<p class="mut">还没写分析。</p>'
    return f'<div class="mode{tone}"><div class="mh"><b>{esc(MODE.get(mode, mode))}</b>{chip}</div>{facts}<div class="notes">{body}</div></div>'


def model_panel(model: str, cards: list, sec: dict | None) -> str:
    across = (sec or {}).get("subs", {}).get(ACROSS)
    lead = md(sec["body"]) if sec and sec["body"] else ""
    return (f'<div class="panel model" id="m-{slug(model)}"><div class="hd"><h2>{esc(model)}</h2></div>{lead}'
            f'<div class="modes">{"".join(cards)}</div>'
            + (f'<div class="across"><div class="mh"><b>{ACROSS}</b></div><div class="notes">{md(across)}</div></div>' if across else "") + "</div>")


def section_panel(sec: dict, key: str, extra: str = "") -> str:
    cls = " advice" if "改进" in sec["title"] else ""
    return f'<div class="panel sec{cls}" id="{key}"><div class="hd"><h2>{esc(sec["title"])}</h2></div><div class="notes">{md(sec["body"])}</div>{extra}</div>'


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def models_of(cols: list) -> list:
    return list(dict.fromkeys(c[0] for c in cols))


def task_block(task: dict, cols: list) -> str:
    """A task page's analysis: the 一句话, one panel per model that ran the task (a card per mode), then the rest."""
    one, secs = load(task["task"])
    by = {s["title"]: s for s in secs}
    H = [f'<div class="panel one-line">{md(one)}</div>'] if one else []
    for m in models_of(cols):
        sec = by.get(m)
        cards = []
        for col in (c for c in cols if c[0] == m):
            r, text = task["main"].get(col), (sec or {}).get("subs", {}).get(col[1])
            if not r and not text:
                continue
            if r and not text:   # no analysis written yet: the run's own verdict
                text = notes_of(r["s"])[0]
            cards.append(mode_card(col[1], run_facts(r) if r else "", status_chip(r) if r else "", text, r["d"]["pass"] if r else None))
        if cards:
            H.append(model_panel(m, cards, sec))
    H += [section_panel(s, f"sec-{i}") for i, s in enumerate(secs) if s["title"] not in models_of(cols)]
    return "".join(H)


def overview_block(tasks: list, cols: list, extra: dict) -> tuple[str, list]:
    """The overview's analysis, and its table of contents [(anchor, title)]. extra: {section title: HTML appended to it}."""
    _, secs = load("overview")
    models = models_of(cols)
    H, toc = [], []
    for i, sec in enumerate(secs):
        if sec["title"] in models:
            m = sec["title"]
            cards = [mode_card(c[1], col_facts(tasks, c), "", sec["subs"].get(c[1]), None) for c in cols if c[0] == m
                     and (any(c in t["main"] for t in tasks) or c[1] in sec["subs"])]
            H.append(model_panel(m, cards, sec)); toc.append((f"m-{slug(m)}", m))
        else:
            H.append(section_panel(sec, f"sec-{i}", extra.get(sec["title"], ""))); toc.append((f"sec-{i}", sec["title"]))
    return "".join(H), toc
