#!/usr/bin/env python3
"""Render the site: data + reviews + findings -> <out>/index.html (+ media/). No LLM.

usage: uv run --no-project --with markdown==3.7 --with pillow python tools/build.py [--out ~/Work/cross-bench-artifact]
       [--set core|all] [--audience internal|share | --both] [--no-switch]

Two audiences (meta/DESIGN.md → Audience): internal (everything, for the authors) -> <out>/index.html; share (for other
readers; internal items are left out of the data, not hidden) -> <out>/share/index.html, media linked to <out>/media.
Two task sets (meta/DESIGN.md → Data layer: sets; queries.SETS): --set picks one (default XB_SET, else core) for one
audience; --both builds core into <out> (internal + share/) and all into <out>/all/ (internal + all/share/), each page
with a 核心集 ⇄ 全部任务 switch, and writes the findings whose numbers differ between the sets (compare_sets) to
/data/pingyue/cross-bench/core_vs_all.md and the all build's home page.

Sources (single source each): meta/site.json (structure, home charts), meta/codebook.json (codes, glossary), data/*.csv
(numbers), reviews/*.json (cases), findings/<t.n>.md (claims), notes/{bench,agent}/*.md (entity notes), findings/_summary.md
(home summary). Placeholders in markdown: {{q:name|k=v…}} -> queries.metrics(), {{fig:name|k=v…}} -> figs.figures(),
{{case:KEY}} -> case link.
"""
from __future__ import annotations
import argparse, glob, hashlib, html, json, os, re, shutil, statistics as S, sys
from collections import Counter, defaultdict
import markdown
import atif
import charts as C
import figs as FG
import figs_time as FT, figs_way as FW
import qtips
import queries as Q
import common
try:                                    # tool-use charts, written separately; the build works without them
    import figs_tools as FX
except ImportError:
    FX = None
from common import AGENTS, DATA, HERE, LUNA, RAW
from review import current_reviews
from features import CLOCK as FEAT_CLOCK

SITE = json.load(open(os.path.join(HERE, "meta/site.json")))
RATINGS_PATH = os.path.join(HERE, "meta/ratings.json")    # {"<finding id>": "high" | "mid" | "low"}: the user's importance rating


def ratings() -> dict:
    """Finding id -> "high" / "mid" from meta/ratings.json (user 10-18 night: tag the important findings after the
    rating pass): high shows 「重点」, mid 「次要」, low nothing; a missing or empty file tags nothing."""
    try:
        r = json.load(open(RATINGS_PATH))
    except (OSError, ValueError):
        return {}
    return {str(k): v for k, v in r.items() if v in ("high", "mid")}


# The method line on the 数据与方法 page (user 10-18 night): where the success rates come from.
PERF_NOTE = ("成功数取自评测看板的全量结果（每个 agent 每个评测项取最新一次合规运行，{set}），不是抽样；成功数含 Embodied Safety Exam（原 RoboSafeBench），抽样分析还不含它。"
             "其余分析的数字来自随机抽样，约三成的 trial。")
MEDIA = os.environ.get("XB_MEDIA", "/data/pingyue/cross-bench/media")
SITE_DIR = os.path.join(HERE, "tools/site")   # shell.html + style.css + app.js, inlined into one index.html
HARNESS = {"codex": "Codex", "claude_code": "Claude Code", "dsh": "dsh (ACP)", "antigravity_cli": "Antigravity CLI"}


def fnum(fid: str) -> tuple:
    """'4.12' -> (4, 12): findings sort by topic, then number."""
    try:
        return tuple(int(x) for x in fid.split("."))
    except ValueError:
        return (99, 99)


def slug(agent: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", agent.lower()).strip("-")


def case_id(key: str) -> str:
    return "c" + hashlib.sha1(key.encode()).hexdigest()[:6]


def front(path: str) -> tuple[dict, str]:
    text = open(path).read()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


PLACEHOLDER = re.compile(r"\{\{(q|fig|case):([^}]+)\}\}")
BARS = re.compile(r"\{\{bars:([^}]+)\}\}")              # {{bars:<q kind>|<filters>|by=agent3|mode|agent}}: a strip of k/n bars
FIGSAY = re.compile(r"\{\{fig:([^}]*)\}\}[ \t]*\n+图意[：:][ \t]*([^\n]+)((?:\n[ \t]*[-*] [^\n]*)*)")   # a figure's one-line takeaway, written right under it,
# then optionally bullets with no blank line between: they print inside the figure's card, under the takeaway (user 10-19)
PARTS = re.compile(r"^\*\*(证据|解读|适用范围)\*\*(（推断）)?[：:]?[ \t]*", re.M)
# A **案例** block: bullets "- 〔组名〕label {{case:…}}" that only feed the finding's video strip (each bullet's first clause is
# its card label, 〔组名〕 its sub-heading); the block is not printed as text (user 10-19: findings without 证据 / 解读 / 适用范围).
CASE_BLOCK = re.compile(r"^\*\*案例\*\*[ \t]*\n+((?:[ \t]*[-*][^\n]*(?:\n|$))+)", re.M)
FID = re.compile(r"\{\{[^}]*\}\}|`[^`]*`|§(\d\.\d{1,2}(?:\.\d{1,2})?)(?!\d)|问题 ?(\d{1,2})(?![\d.])")      # §4.3 = finding, 问题 12 = issue
ISSUE_NO = re.compile(r"^#(\d)", re.M)                  # "#244 …" at a line start is an issue number, not a heading
md = lambda t: markdown.markdown(t, extensions=["tables", "sane_lists"])

# Audience. The share build leaves out internal findings (`audience: internal`, internal topics, their children), the
# issues register, data status and the note parts that list issues. Markdown can mark text for one build only:
# <!-- internal -->…<!-- /internal --> and <!-- share -->…<!-- /share -->. Template code only the internal build keeps
# sits between /* audience-switch:internal */ and /* end */ in app.js.
AUD = re.compile(r"<!-- (internal|share) -->(.*?)<!-- /\1 -->", re.S)
BRACKET = re.compile(r"（([^（）]*)）|\(([^()]*)\)")
CODE_AUD = re.compile(r"/\* audience-switch:internal \*/.*?/\* end \*/", re.S)


def for_audience(text: str, audience: str, hidden=frozenset()) -> str:
    """The markdown one build shows. In the share build a bracketed reference to a hidden item (an internal finding's §,
    any 问题 N) goes with its separator, and a bracket left empty goes too; a reference in running text stays for
    check.py to flag, so mark that text instead."""
    text = AUD.sub(lambda m: m.group(2) if m.group(1) == audience else "", text)
    if audience != "share":
        return text

    def hide(m):
        return "\0" if (m.group(1) and m.group(1) in hidden) or m.group(2) else m.group(0)

    def bracket(m):
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        t = FID.sub(hide, inner)
        if "\0" not in t:
            return m.group(0)
        t = re.sub(r"\0\s*[–—~-]\s*\0", "\0", t)
        t = re.sub(r"\s*[、，,；]\s*\0|\0\s*[、，,；]?\s*", "", t).strip()
        if not re.sub(r"^(另见|参见|见)\s*", "", t):
            return ""
        return f"（{t}）" if m.group(1) is not None else f"({t})"
    return BRACKET.sub(bracket, text)


# The #samples page of the internal build shows each chart kind once: the first finding figure drawn with it.
KINDS = ("stack", "heat", "phased", "counts", "bars", "hist", "lanes", "ranges", "lines", "legend")
# The progress charts (topic 4, 关键点与进展) are shown on #samples even before a finding draws them.
NEW_SAMPLES = ("crit|by=agent", "crit_time|by=mode", "after|by=agent", "stuck|by=agent", "reach", "grasp3|by=agent",
               "common|by=tasktype", "unsolved", "deliv|mode=privileged", "venn", "trio", "overlap|by=tasktype", "overlap")
SAMPLES, _DRAWN = {}, []


def _traced(kind, fn):
    def draw(*args, **kw):
        out = fn(*args, **kw)
        _DRAWN.append((kind, out))
        return out
    return draw


for _k in KINDS:
    setattr(C, _k, _traced(_k, getattr(C, _k)))


FIG_NAME = {"grasp": "抓取/接触是怎么失败的", "remedy": "最可能让失败变成功的改动（按大类）", "fixes": "各项改动覆盖的失败占比", "profile": "agent 画像", "loop": "谁在决定每一步动作", "tech": "用到的技术", "perception": "位置信息从哪来", "tools": "工具调用的构成",
            "calls": "每个 trial 的过程计数（中位数）", "timeuse": "在时限的什么位置结束", "lanes": "关键事件的时刻（中位数，占时限）",
            "endings": "结束方式", "dist": "分析分布", "integrity": "越界信号", "rescue": "同一批评测项（Luna 没过的）上各 agent 的成功率",
            "common": "同一批任务上的成功率", "modes": "同一任务两种模式的成败", "bench_priv": "各 benchmark 成功率（privileged）",
            "bench_std": "各 benchmark 成功率（standard）", "time": "失败里时间起了什么作用", "process": "过程计数（中位数）", "code": "最终代码里的技术",
            "excluded": "抽样分析不计入的 trial（看板的结果记作失败）",
            "fixrank": "失败最常缺的那一处改动", "reason": "失败背后有没有高层错误", "reasonkinds": "高层错误的类型",
            "crit": "失败的关键点是什么", "crit_time": "关键点落在时限的什么位置", "after": "关键点之后 agent 做了什么",
            "stuck": "失败最后停在第几级", "reach": "到达各级的时刻（进展曲线）", "progress": "到达各级的时刻（进展曲线）",
            "grasp3": "抓取/接触失败的三类", "unsolved": "无人做成的评测项（六家主要 agent 都评过分的）", "deliv": "交付物是怎么生成的",
            "overlap": "三家做成了哪些评测项（六家都评过分的同一批）", "venn": "三家各做成了哪些评测项（六家都评过分的同一批）",
            "trio": "三家各自的做成数（六家都评过分的同一批）", "dots": "三家各自做成的比例（六家都评过分的同一批）"}
PANEL_FIGS = ("venn", "overlap", "trio", "dots")                 # one panel per mode, each titled: the caption leaves the modes out
FIG_NAME.update({"end": "失败的" + FG.CB["field_zh"]["end"], "noreturn": "失败的" + FG.CB["field_zh"]["no_return"],
                 "nrafter": FG.CB["field_zh"]["nr_after"], **FT.NAMES, **FW.NAMES,
                 **(getattr(FX, "NAMES", {}) if FX else {})})
import waffle as WA; FIG_NAME.update(WA.NAMES)          # fig:waffle (waffle.py): caption here, chart in figure_registry
FIG_BY = {"agent": "按 agent", "agent_mode": "按 agent 和模式", "mode": "按模式", "category": "按类别", "bench": "按 benchmark", "outcome": "按成败",
          "tasktype": "按任务类型", "body": "按机器人形态", "cap": "按能力要求"}
FIELD_NAME = {"primary": "失败主因", "stage": "决定性错误在哪个阶段", "secondary": "次要原因", "claim": "最终声明", "on_failure": "受挫后怎么办",
              "plan_vs_act": "先计划还是先动手", "verification": "结束前验证多少"}


def fig_caption(name: str, kv: dict) -> str:
    """A one-line title for a chart from its name and parameters, so several charts in one finding stay distinguishable."""
    head = Q.batch_words(FIELD_NAME.get(kv.get("field"), FIG_NAME.get(name, name)) if name == "dist" else FIG_NAME.get(name, name))
    if name == "overlap" and (kv.get("show") == "none" or kv.get("by") == "bench"):   # only the 三家都没做成 bars
        head = "三家都没做成的评测项"
    if name == "tech":
        head += "（分析标注）" if kv.get("src") == "ann" else "（代码信号）"
    if name == "dist" and kv.get("outcome") == "success":
        head += "（成功的 trial）"
    name_of = {"category": lambda v: FG.CAT_NAME.get(v, v), "bench": lambda v: SITE["benches"].get(v, {}).get("name", v),
               **{k: (lambda t: lambda v: t.get(v, [v])[0])(t) for k, t in FG.ATLAS_ZH.items()}}
    vals = lambda k: "、".join(name_of.get(k, str)(v) for v in kv[k].split(",") if not (k == "bench" and v in Q.LEFT_OUT))
    shown = [k for k in ("mode", "category", "bench", "agent", *FG.ATLAS_ZH) if kv.get(k) and not (k == "mode" and name in PANEL_FIGS)]
    parts = [head] + ([FIG_BY[kv["by"]]] if kv.get("by") in FIG_BY else []) + [vals(k) for k in shown]
    return f'<p class="figcap">{html.escape(" · ".join(parts))}</p>'


def task_name(c: dict) -> str:
    """A case's task without its benchmark prefix and instance suffix."""
    return re.sub(r"-i\d+$", "", re.sub(rf"^{re.escape(c['bench'])}[-_]", "", c["task"]))


def case_mark(cid: str, cases: dict, refs: list) -> str:
    """A numbered case mark [n]; `refs` holds the page's case order, so a case keeps one number on the page."""
    c = cases.get(cid)
    if not c:
        return ""
    if cid not in refs:
        refs.append(cid)
    tip = html.escape(f'{c["agent"]} · {c["bench"]} · {task_name(c)} · {c["mode"]}：{c["title"]}', quote=True)
    return f'<a class="cref" href="#case-{cid}" data-tip="{tip}">{refs.index(cid) + 1}</a>'


SHOW_KN = re.compile(r"\s*(\d+(?:\.\d+)?)/(\d+)(?:（[^）]*）)?\s*")
SHOW_N = re.compile(r"（n=(\d+)）")


def as_count(v: str, show: str = "") -> str:
    """A q value as the report prints it (user 10-18 night: counts, not percentages — 「分析过的 140 个失败里，主因是抓取的有
    41 个」): "k/n（p%）" / "k/n" -> "k/n"; show=k -> "k", show=n -> "n". A median "p%（n=…）" / "m min（n=…）" prints its
    value, show=n its n. fmt=pct, asked for explicitly, still gives the metric's percent."""
    if m := SHOW_KN.fullmatch(v):
        k, n = round(float(m.group(1))), m.group(2)
        return str(k) if show == "k" else n if show == "n" else f"{k}/{n}"
    if show == "n" and (m := SHOW_N.search(v)):
        return m.group(1)
    return SHOW_N.sub("", v)


def bar_rows(spec: str, metrics: dict) -> tuple[str, dict, list]:
    """A bars placeholder's spec -> (q kind, its filters, rows [(label, k, n, value text, row filters)]): the q:<kind>
    value for 全部, then with one more filter per row: by=agent3 (default; the first three of agent_order, then the rest
    pooled in one row), by=mode, by=agent (all of agent_order), or by=tasktype / body / cap (each Atlas group; a trial
    counts in each of its task types and capabilities). Rows with n = 0 are left out; no rows when the kind gives no k/n."""
    name, *params = [x.strip() for x in spec.split("|")]
    kv = dict(p.split("=", 1) for p in params if "=" in p)
    by = kv.pop("by", "agent3")
    kv.pop("fmt", None), kv.pop("show", None)
    rest = [a for a in Q.ORDER[3:] if a in (metrics.get("_agents") or Q.set_agents())]   # the agents of this set (queries.set_agents)
    extra = {"agent3": [(a, {"agent": a}) for a in Q.ORDER[:3]] + [(f"其余 {len(rest)} 家", {"agent": ",".join(rest)})],
             "mode": [(label, {"mode": m}) for m, label in FG.MODE_NAME.items()],
             "agent": [(a, {"agent": a}) for a in Q.ORDER],
             **{f: [(name, {f: code}) for code, (name, *_) in FG.ATLAS_ZH[f].items()] for f in FG.ATLAS_ZH}}.get(by)
    if name not in metrics or extra is None:
        return name, kv, []
    rows = []
    for label, add in [("全部", {})] + extra:
        row = {**kv, **add}
        v = str(metrics[name](**row))
        m = re.match(r"\s*(\d+)/(\d+)", v)
        if not m:
            return name, kv, []
        if int(m.group(2)):
            rows.append((label, int(m.group(1)), int(m.group(2)), v, row))
    return name, kv, rows


def bars_block(spec: str, metrics: dict) -> str:
    """{{bars:…}} -> a caption (what is counted, out of what: qtips.counted) and one item per group: label, a short bar
    filled to k/n, "k/n" (counts: charts module note); the items sit on one line (wrapping at phone width). Each item
    carries the hover note its q: number would. Items under charts.SMALL are italic with the 样本少 tag. Styles: .qbars in
    tools/site/style.css."""
    name, kv, rows = bar_rows(spec, metrics)
    if not rows:
        return f"⟨missing bars {html.escape(spec)}⟩"
    cap = qtips.counted(name, kv)
    multi = FG.MULTI_WHAT.get(dict(p.split("=", 1) for p in spec.split("|")[1:] if "=" in p).get("by"))
    if cap and multi:
        cap = cap[:-1] + f"；一个任务可属于几种{multi}，各算一次。"
    out = []
    for i, (label, k, n, v, row) in enumerate(rows):
        few = '<small class="few">样本少</small>' if n < C.SMALL else ""
        cls = "qbrow" + (" qball" if i == 0 else "") + (" small" if few else "")
        out.append(f'<div class="{cls}" data-tip="{html.escape(qtips.tip(name, row, v), quote=True)}"><span class="qbl">{html.escape(label)}</span>'
                   f'<span class="qbt"><span class="qbf" style="width:{100 * k / n:.1f}%"></span></span><span class="qbv">{k}/{n}{few}</span></div>')
    return '<div class="qbars">' + (f'<p class="qbcap">{html.escape(cap)}</p>' if cap else "") + "".join(out) + "</div>"


def render_md(text: str, metrics: dict, figs: dict, cases: dict, fids=(), refs=None, claim=False) -> tuple[str, list]:
    """Markdown with placeholders -> (html, case ids in citation order). Cases render as numbered marks [n]; bare finding
    IDs become links; a finding body's 证据 / 解读 / 适用范围 paragraphs become labelled rows. Pass a parent's `refs` list
    to continue its case numbering (a child §4.2.1 shares the numbers of §4.2's case cards). claim: a body without those
    parts is still one claim block (every bullet shown), not a child section's fold."""
    refs = [] if refs is None else refs
    says = []

    def keep_say(m):
        says.append((m.group(2).strip(), m.group(3).strip("\n")))
        return "{{fig:" + m.group(1) + f"|say={len(says) - 1}" + "}}"

    def sub(m):
        kind, spec = m.group(1), m.group(2).strip()
        name, *params = [x.strip() for x in spec.split("|")]
        kv = dict(p.split("=", 1) for p in params if "=" in p)
        if kind == "q":
            if name not in metrics:
                return f"⟨missing {name}⟩"
            show = kv.pop("show", "")
            v = str(metrics[name](**kv))
            t = qtips.tip(name, kv, v)
            return f'<span class="qv" data-tip="{html.escape(t, quote=True)}">{as_count(v, show)}</span>' if t else as_count(v, show)
        if kind == "fig":
            if name not in figs:
                return f"⟨missing fig {name}⟩"
            say, notes = says[int(kv.pop("say"))] if "say" in kv else ("", "")
            say_html = re.sub(r"^<p>|</p>$", "", md(PLACEHOLDER.sub(sub, FID.sub(link, say))).strip()) if say else ""
            note_html = f'<div class="fignote">{md(PLACEHOLDER.sub(sub, FID.sub(link, notes))).replace(chr(10), "")}</div>' if notes else ""
            del _DRAWN[:]
            block = (f'<div class="fig">' + (f'<p class="figsay">{say_html}</p>' if say_html else "") + note_html   # takeaway above the chart
                     + f'{fig_caption(name, kv)}{figs[name](**kv)}</div>')
            shown = re.sub(r"\|say=\d+", "", spec)
            for chart, out in _DRAWN:
                if chart != "legend":
                    SAMPLES.setdefault(chart, {"kind": chart, "fig": shown, "html": block})
                elif "legend defs" in out:
                    SAMPLES.setdefault(chart, {"kind": chart, "fig": shown, "html": out})
            return f"\n\n{block}\n\n"
        return case_mark(case_id(name), cases, refs)
    def link(m):
        if m.group(1) and m.group(1) in fids:
            return f"[§{m.group(1)}](#f-{m.group(1)})"
        if m.group(2) and f"I{m.group(2)}" in fids:
            return f"[问题 {m.group(2)}](#issue-I{m.group(2)})"
        return m.group(0)
    text = FIGSAY.sub(keep_say, text)
    text = FID.sub(link, text)
    text = ISSUE_NO.sub(r"\\#\1", text)
    text = BARS.sub(lambda m: f"\n\n{bars_block(m.group(1), metrics)}\n\n", text)   # a block: as a body's first line it sits under the title
    text = PLACEHOLDER.sub(sub, text)
    pieces = PARTS.split(text)
    if len(pieces) == 1:
        return (f'<div class="claim">{md(text)}</div>' if claim else md(text)), refs
    unhead = lambda b: "\\" + b if b.startswith("#") else b          # "#243 …" is an issue number, not a heading
    rows = "".join(f'<div class="part"><div class="pl">{name}{"<small>推断</small>" if inferred else ""}</div><div class="pb">{md(unhead(body.strip()))}</div></div>'
                   for name, inferred, body in zip(pieces[1::3], pieces[2::3], pieces[3::3]))
    return f'<div class="claim">{md(pieces[0])}</div><div class="parts">{rows}</div>', refs


SUMMARY_HEAD = re.compile(r"^\*\*([^*\n]+)\*\*[ \t]*$", re.M)        # a bold line on its own = one home block


def home_blocks(text: str, audience: str, render) -> list:
    """findings/_summary.md (as this build shows it) -> one block per bold heading: its bullets and the chart that
    meta/site.json `home` picks for it (`fig` spec, `from` finding, `say` takeaway; without `say`, the 图意 that the same
    figure carries in that finding). An entry with `audience` belongs to that build only."""
    parts = SUMMARY_HEAD.split(text)
    out = [{"name": "", "html": render(parts[0])[0], "fig": "", "from": ""}] if parts[0].strip() else []
    for name, body in zip(parts[1::2], parts[2::2]):
        pick = next((h for h in SITE.get("home", []) if h["block"] == name and h.get("audience", audience) == audience), None)
        fig = ""
        if pick:
            say = pick.get("say") or next((m.group(2) for m in FIGSAY.finditer(front(os.path.join(HERE, "findings", pick["from"] + ".md"))[1])
                                           if m.group(1).strip() == pick["fig"]), "")
            if not say:
                sys.exit(f"meta/site.json home '{name}': no say, and §{pick['from']} has no figure {pick['fig']} with a 图意")
            fig = render("{{fig:" + pick["fig"] + "}}\n图意：" + say)[0].strip()
        out.append({"name": name, "html": render(body)[0], "fig": fig, "from": pick["from"] if pick else ""})
    return out


def cell_block(trials, cells):
    """bench -> agent -> mode -> {s, n, other: {status: count}}; `trials` = the monitor's graded rows (queries.load_perf)."""
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"s": 0, "n": 0, "other": Counter()})))
    for t in trials:
        c = out[t["bench"]][t["agent"]][t["mode"]]
        c["s"] += int(t["success"])
        c["n"] += 1
    for c in cells:
        if c["status"] != "done":
            out[c["bench"]][c["agent"]][c["mode"]]["other"][c["status"]] += 1
    return out


def neutral(x):
    """Report wording rule: observations of agents hunting for answer files are kept, the word itself is not used; the
    review texts' old word 判读 reads 分析, the term the report uses."""
    if isinstance(x, str):
        return re.sub(r"(?i)oracle", "答案文件", x).replace("判读", "分析")
    if isinstance(x, list):
        return [neutral(v) for v in x]
    if isinstance(x, dict):
        return {k: neutral(v) for k, v in x.items()}
    return x


STAMP = re.compile(r"\[(\d{1,3}:\d{2}(?::\d{2})?)\](?:\s*[-–—]\s*\[(\d{1,3}:\d{2}(?::\d{2})?)\])?")


def _minutes(stamp: str):
    try:
        p = [float(x) for x in str(stamp).strip("[] ").split(":")]
    except ValueError:
        return None
    return p[0] * 60 + p[1] + p[2] / 60 if len(p) == 3 else p[0] + p[1] / 60 if len(p) == 2 else None


def story_steps(story: str) -> list:
    """Split a review's timeline paragraph at its [mm:ss] stamps -> [[stamp label, text], …] (empty if unstamped)."""
    ms = list(STAMP.finditer(story or ""))
    if len(ms) < 2:
        return []
    out = [["", story[:ms[0].start()].strip(" ；;。")]] if story[:ms[0].start()].strip(" ；;。") else []
    for i, m in enumerate(ms):
        body = story[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(story)].strip(" ；;，,。")
        if not body:
            continue
        out.append([m.group(1) + (f"–{m.group(2)}" if m.group(2) else ""), body])
    return out


_ACTIVITY = {}


def activity(key: str, trial: dict, r: dict, bins: int = 60) -> dict:
    """Memoised, so both builds of one run read each trajectory once."""
    if key not in _ACTIVITY:
        _ACTIVITY[key] = _activity(key, trial, r, bins)
    return _ACTIVITY[key]


def _activity(key: str, trial: dict, r: dict, bins: int = 60) -> dict:
    """Tool calls binned over the time limit, clock checks, and the review's key moments (minutes)."""
    try:
        traj = json.load(open(os.path.join(RAW, key, "agent/trajectory.json")))
        detail = json.load(open(os.path.join(RAW, key, "trial.json")))["detail"]
    except (OSError, ValueError, KeyError):
        return {}
    ev, approx = atif.events(traj, atif.request_times(detail))
    cut = Q._f(trial.get("cutoff_min")) or Q._f(trial.get("timeout_min")) or max([e["t"] or 0 for e in ev] + [1])
    span = max(cut, max([e["t"] or 0 for e in ev] + [0]))
    kinds = {k: [0] * bins for k in ("shell", "write", "read", "image")}
    for e in ev:
        if e["t"] is not None and e["kind"] in kinds:
            kinds[e["kind"]][min(bins - 1, int(e["t"] / span * bins))] += 1
    clock = [round(e["t"], 1) for e in ev if e["t"] is not None and e["kind"] == "shell" and FEAT_CLOCK.search(e["text"])][:200]
    f, tm = r.get("failure") or {}, r.get("time") or {}
    marks = [(lab, _minutes(v)) for lab, v in (("第一个交付物", tm.get("first_deliverable_t")), ("第一个征兆", f.get("first_symptom_t")),
                                               ("决定性错误", (f.get("decisive") or {}).get("t")), ("不可挽回", f.get("no_return_t")))]
    return {"span": round(span, 1), "cutoff": round(cut, 1), "used": Q._f(trial.get("agent_min")), "approx": approx,
            "kinds": kinds, "clock": clock, "marks": [[lab, round(t, 1)] for lab, t in marks if t is not None]}


EXAMPLE_LINE = re.compile(r"^(?:例子?|案例|示例|典型|同类)\s*\d*\s*[：:]|^[^：:，。；]*·[^：:，。；]*[：:]")   # "例子：…", "agent · task：…"
STRUCT_LABELS = ("是什么", "多常见", "常见原因", "怎么避免", "总量", "规模", "计数", "类别", "做法", "模式")           # a bullet's field name, not a claim
CLAUSE_END = re.compile(r"[，。；：:！？]")
ENTITY_NAME = re.compile("(?:" + "|".join(map(re.escape, sorted({*Q.ORDER, *HARNESS.values(), *HARNESS, "Astra", "Argon", "Opus", "Luna", "Sol", "GLM", "DeepSeek",
                                                                "Gemini", "Qwen", "Antigravity", "privileged", "standard", "realtime", "standard-realtime",
                                                                *SITE["benches"], *(b["name"] for b in SITE["benches"].values())}, key=len, reverse=True)))
                         + r"|[\s\d.、和与及·/-])+", re.I)                  # a label that only names agents, harnesses, benchmarks or modes


def first_clause(text: str, limit: int = 24) -> str:
    """The text up to its first comma, colon or stop, without brackets, cut to `limit` characters."""
    c = CLAUSE_END.split(re.sub(r"（[^）]*）", "", text), 1)[0].strip()
    return c if len(c) <= limit else c[:limit - 1] + "…"


EXAMPLE_WORD = re.compile(r"^(?:(?:例子?|案例|示例|典型|同类)\s*\d*\s*[：:]|(?:例如|比如)\s*[：:，,]?)\s*")   # "例子：…", "例如，…"
BARE_EXAMPLE = re.compile(r"(?:例子?|例如|比如|案例|示例)?\s*\d*")


def lead_clause(text: str) -> str:
    """A case card's bold label: the first clause (first_clause) of `text` after a leading 例子 / 例如 word; "" when
    nothing else is left, so a card never shows a bare 例 / 例子 / 例如."""
    text = EXAMPLE_WORD.sub("", text.strip())
    if m := re.match(r"(〔[^〕]{1,20}〕)", text):              # 〔组名〕: the case strip groups cards by it (app.js videoStrip)
        return m.group(1) + first_clause(text[m.end():])
    c = first_clause(text)
    return "" if BARE_EXAMPLE.fullmatch(c) else c


def case_labels(body: str, title: str) -> dict:
    """case id -> the claim the example shows, printed as the card's lead line: the first clause (<= 24 characters) of the
    bullet that cites it. An example line ("例子：…", "agent · task：…") says no claim of its own, so its parent bullet's
    claim stands; the top of the finding's list falls back to the title's (lead_clause: a leading 例子 / 例如 word is
    dropped, and a card gets no label rather than a bare 例子). A label of up to 3 characters
    ("代价：…"), a field name ("多常见：…") or one that only names agents, benchmarks or modes ("Luna：…") gives way to the
    clause after its colon."""
    lines = body.splitlines()
    bullets = [(len(m.group(1)), m.group(2)) if (m := re.match(r"^(\s*)[-*]\s+(.*)$", ln)) else None for ln in lines]

    def claim(i: int) -> str:
        indent, text = bullets[i]
        text = re.sub(r"^[-*\s]+", "", re.sub(r"\{\{[^}]*\}\}", "", text.split("{{case:")[0])).replace("**", "").replace("`", "")
        text = re.sub(r"（[^）]*）", "", text).strip()                  # brackets may hold commas and colons: "agent · task（mode，outcome）：…"
        if not EXAMPLE_LINE.match(text):
            head, _, rest = text.partition("：")
            if rest and (len(head.strip()) <= 3 or head.strip() in STRUCT_LABELS or ENTITY_NAME.fullmatch(head.strip() or "-")):   # a field name or entity name is no claim: the clause after it is
                text = rest
            if (c := lead_clause(text)) and not ENTITY_NAME.fullmatch(c):
                return c
        for j in range(i - 1, -1, -1):
            if bullets[j] and bullets[j][0] < indent:
                return claim(j)
        return lead_clause(title)

    out = {}
    for i, line in enumerate(lines):
        for k in re.findall(r"\{\{case:([^}]+)\}\}", line) if bullets[i] else []:
            out.setdefault(case_id(k.strip()), claim(i))
    return out


def no_video_reason(key: str) -> str:
    """Why a case has no replay video, in the reader's words (the grader's reward.json says when no trajectory was saved)."""
    reward = next(iter(glob.glob(os.path.join(RAW, key, "**/reward.json"), recursive=True)), None)
    try:
        if reward and json.load(open(reward)).get("missing_trajectory"):
            return "agent 没有存下能评分的轨迹，评分方没有东西可回放"
        vn = json.load(open(os.path.join(RAW, key, "trial.json")))["detail"].get("video_note") or ""
    except (OSError, ValueError, KeyError):
        return "这个 trial 没有评分回放"
    return ("评分时回放还没跑完，没有录到视频" if "before the episode's replay finished" in vn else
            "评分回放没有渲染出视频" if "did not render" in vn else "这个 trial 没有评分回放")


def thumb(key: str, src: str) -> str:
    """A 480 px JPEG of the poster as a data URI (cached in $XB_MEDIA/thumbs)."""
    import base64
    from PIL import Image
    d = os.path.join(MEDIA, "thumbs")
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, key + ".jpg")
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        im = Image.open(src).convert("RGB")
        im.thumbnail((480, 300))
        im.save(dst, "JPEG", quality=68, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(open(dst, "rb").read()).decode()


def case_record(key: str, r: dict, trial: dict, out_dir: str) -> dict:
    r = neutral(r)
    cid = case_id(key)
    media = {}
    src_v, src_p = os.path.join(MEDIA, key + ".mp4"), os.path.join(MEDIA, key + ".jpg")
    if os.path.exists(src_v):
        if not os.path.islink(os.path.join(out_dir, "media")):   # a linked media/ belongs to another build
            shutil.copy2(src_v, os.path.join(out_dir, "media", cid + ".mp4"))
        media["video"] = f"media/{cid}.mp4"
        meta = os.path.join(MEDIA, key + ".json")
        media["speed"] = json.load(open(meta)).get("speed", 1) if os.path.exists(meta) else 1
    poster = src_p if os.path.exists(src_p) else next(iter(sorted(glob.glob(os.path.join(RAW, key, "frames/f6.jpg")) +
                                                             glob.glob(os.path.join(RAW, key, "**/replay.last.png"), recursive=True))), None)
    agent_img = next(iter(glob.glob(os.path.join(MEDIA, key + ".agent.*"))), None)
    if not poster and agent_img:
        poster, media["poster_kind"] = agent_img, "agent"
    if "video" not in media:
        media["note"] = no_video_reason(key)
    if poster:
        media["poster"] = thumb(key, poster)                 # inline: one version may hold at most 511 files
        if "video" not in media:                            # no replay video: the full image is the case's only picture
            ext = os.path.splitext(poster)[1]
            if not os.path.islink(os.path.join(out_dir, "media")):
                shutil.copy2(poster, os.path.join(out_dir, "media", cid + ext))
            media["image"] = f"media/{cid}{ext}"
    f = r.get("failure") or {}
    run, trial_name = key.split("__", 1)                    # key = run id + "__" + the monitor's trial name
    host = (trial.get("trial_id") or trial["id"]).split("|")[0]   # both id formats start with the host (the monitor's `host`)
    return {"id": cid, "key": key, "ref": f"{run} · {host} · {trial_name}", "title": r["headline"], "bench": trial["bench"], "agent": trial["agent"],
            "agent_id": slug(trial["agent"]), "mode": trial["mode"], "task": trial["base"], "outcome": r["outcome"],
            "end": Q.ending(trial), "minutes": trial["agent_min"], "cutoff": trial.get("cutoff_min") or trial["timeout_min"],
            "paradigm": r["approach"].get("paradigm", []), "approach": r["approach"].get("summary", ""),
            "story": r["story"], "steps": story_steps(r["story"]), "activity": activity(key, trial, r),
            "stage": f.get("stage", ""), "primary": f.get("primary", ""),
            "secondary": f.get("secondary") or [], "decisive": f.get("decisive") or {}, "evidence": f.get("evidence", ""),
            "best": r.get("best_progress", ""), "claim": r["claim"], "time": r.get("time") or {}, "style": r.get("style") or {},
            "notable": r.get("notable") or [], "depth": r["depth"], "score": (r.get("case_worthy") or {}).get("score", 0),
            "validity": trial["validity"], "validity_reason": trial["validity_reason"], "media": media, "findings": []}


def progress_case(a: dict | None, p2: dict | None, trial: dict) -> dict:
    """A case's progress staircase from its progress label (one whose fingerprint matches): milestones [minutes, level,
    what], the session end and the limit; progress-2 (queries.progress2_record: the label itself or its relabel p2): the
    no-return event (kind, minutes, what, noticed, after, wasted minutes; kind "" when not labelled) and the end type,
    each with its chart colour (figs.NORETURN / figs.END); {} without a label."""
    if not a or (a.get("fingerprint") and trial.get("fingerprint") and a["fingerprint"] != trial["fingerprint"]):
        return {}
    p, q = Q.progress_record(a, trial), Q.progress2_record(a, p2, trial)
    r1 = lambda x: round(x, 1) if x is not None else None
    color = lambda keys, k: next((x[2] for x in keys if x[0] == k), "--c0")
    return {"ms": [[r1(t), lv, neutral(w)] for t, lv, w in p["milestones"]], "end": r1(p["end_min"]),
            "cutoff": r1(p["cutoff"]), "basis": p["basis"],
            "nr": q["no_return"] or "", "nr_t": r1(q["nr_min"]), "nr_what": neutral(q["nr_what"]), "nr_noticed": q["nr_noticed"] or "",
            "nr_after": q["nr_after"] or "", "wasted": r1(q["wasted"]), "nr_color": color(FG.NORETURN, q["no_return"]),
            "end_kind": q["end"] or "", "end_what": neutral(q["end_what"]), "end_color": color(FG.END, q["end"])}


def integrity_case(key: str, ia: dict, trial: dict, out_dir: str) -> dict:
    """A case page for a trial that only has an integrity label (no ordinary review)."""
    shell = {"headline": ia.get("note") or "越界行为分析", "outcome": "success" if trial["success"] == "1" else "failure",
             "approach": {}, "story": "", "claim": "", "depth": "integrity"}
    rec = case_record(key, shell, trial, out_dir)
    rec["integrity"] = neutral(ia)
    return rec


def bench_examples(ctx, b: str, cases: dict) -> list:
    """Every reviewed trial of a benchmark as one row: who, mode, outcome, how it drove the robot, the case page if any."""
    cid_of = {c["key"]: cid for cid, c in cases.items()}
    order = {m: i for i, m in enumerate(("privileged", "standard", "standard-realtime"))}
    rows = [r for r in Q.ann_rows(ctx, sample=False) if r["bench"] == b]
    rows.sort(key=lambda r: (order.get(r["mode"], 9), Q.ORDER.index(r["agent"]) if r["agent"] in Q.ORDER else 99, r["success"] != "1"))
    return [{"agent": r["agent"], "mode": r["mode"], "ok": r["success"] == "1", "loop": r["way"], "task": r["base"],
             "note": neutral(ctx.approach[r["key"]].get("loop_note", "")), "case": cid_of.get(r["key"], "")} for r in rows]


# Entity-page charts. A chart's computed lead ("privileged：最多是「X」（k/n）；standard：…") becomes one bullet per row,
# each with one sampled example of that row's largest part, so every claim on the page carries its example.
LEAD_PART = re.compile(r"^(?P<lab>[^：]+)：.*「(?P<name>[^」]+)」（\d+/\d+）$")
MODE_OF = {v: k for k, v in FG.MODE_NAME.items()}
PHASE_OF = {k: g for g, ks in FG.PHASES for k in ks}
LOOP_NAME = {x[0]: x[1] for x in FG.LOOP}


def _shown(ctx, field: str, r: dict) -> str:
    """The category name a chart draws for one row (the name its lead quotes)."""
    if field == "loop":
        return LOOP_NAME.get(r["way"], "")                 # v17 approach (queries.way)
    if field == "stage":
        return PHASE_OF.get(r["stage"], "")
    return FG._code_label(field, FG.display_cause(ctx, r) if field == "primary" else r[field])[0]


def _review(ctx, key: str) -> dict:
    return ctx.reviews.get((key, "deep")) or ctx.reviews.get((key, "skim")) or {}


def _setback(r: dict) -> str:
    """The sentence of a review's style note that says how the agent met setbacks ("" if none does)."""
    said = [x.strip().removeprefix("但") for x in re.split(r"[；。]", (r.get("style") or {}).get("notes", ""))]
    return next((x for x in said if re.search(r"微调|换|重试|放弃|同一", x)), "")


def _example_text(ctx, field: str, key: str) -> str:
    """What the example shows: how it drove the robot (loop), the decisive error (cause, stage), else the headline."""
    r = _review(ctx, key)
    if field == "loop":
        return (ctx.approach.get(key) or {}).get("loop_note") or r.get("headline", "")
    if field in ("primary", "stage"):
        return ((r.get("failure") or {}).get("decisive") or {}).get("what") or r.get("headline", "")
    if field == "on_failure" and _setback(r):
        return _setback(r)
    return re.sub(rf"^(?:{'|'.join(map(re.escape, Q.ORDER))})\s*(?:在\s*)?", "", r.get("headline", ""))


def brief(text: str, n: int = 56) -> str:
    """The first clause of a review text, cut at a comma before n characters, so an example stays within two lines."""
    t = STAMP.sub(lambda m: m.group(1), re.sub(r"\s+", " ", neutral(text or ""))).strip()
    t = re.split(r"[；。]", t)[0].rstrip("，、：: ")
    if len(t) > n:
        cut = max(t.rfind(c, 0, n) for c in "，、：,")
        t = (t[:cut] if cut > n // 2 else t[:n - 1]) + "…"
    if t.count("（") > t.count("）"):                      # never leave a bracket open
        t = t[:t.rfind("（")].rstrip("，、 ") + "…"
    return t


def takeaways(ctx, chart: str, field: str, kv: dict, used: set, known: set) -> tuple[list, str]:
    """Split a chart's computed lead into (sentence, example key, example text) per row; the example is a sampled review
    of the same rows showing the row's largest part, preferring one that already has a case page (`known`, so the site
    does not grow), then one whose text shows the pattern, not used on this page yet, with a replay video, case-worthy, deep."""
    m = re.match(r'<p class="figsay">(.*?)</p>', chart or "", re.S)
    if not m:
        return [], chart
    pool_of = (lambda kv: FG._filter(Q.ann_rows(ctx), kv)) if field == "loop" else \
              (lambda kv: [r for r in FG._filter(Q.review_rows(ctx), kv) if r["outcome"] == "failure"])
    reviewed = {k for k, _ in ctx.reviews}
    fits = lambda k: field != "on_failure" or bool(_setback(_review(ctx, k)))    # its text shows the pattern
    rank = lambda k: (k not in known, not fits(k), k in used, not os.path.exists(os.path.join(MEDIA, k + ".mp4")),
                      -((_review(ctx, k).get("case_worthy") or {}).get("score", 0)), (k, "deep") not in ctx.reviews, k)
    items = []
    for part in m.group(1).rstrip("。").split("；"):
        p, key = LEAD_PART.match(part), None
        if p and p["lab"] in MODE_OF:
            pool = [r["key"] for r in pool_of({**kv, "mode": MODE_OF[p["lab"]]}) if r["key"] in reviewed and _shown(ctx, field, r) == p["name"]]
            key = min(pool, key=rank, default=None)
        if key is None:
            print(f"warning: no example for the takeaway {part!r} ({kv})")
        else:
            used.add(key)
        items.append((part, key, brief(_example_text(ctx, field, key)) if key else ""))
    return items, chart[m.end():]


def chart_block(ctx, title: str, chart: str, field: str = "", kv=None, used=None, known=frozenset()) -> dict:
    items, body = takeaways(ctx, chart, field, kv, used, known) if field and chart else ([], chart)
    return {"title": title, "items": items, "html": body}


def render_block(b: dict, cases: dict, refs: list, who) -> str:
    """One chart on an entity page: title, takeaway bullets (each with its example sub-bullet), chart. `who(case)` names
    the example's source (bench · task on an agent page, agent · task on a bench page)."""
    if not b["html"]:
        return ""
    lis = []
    for sentence, key, text in b["items"]:
        c = cases.get(case_id(key)) if key else None
        ex = f'<ul><li>例：<span class="exsrc">{html.escape(who(c))}</span> {html.escape(text)}{case_mark(c["id"], cases, refs)}</li></ul>' if c else ""
        lis.append(f"<li>{html.escape(sentence)}{ex}</li>")
    return (f'<div class="fig efig"><h3 class="ctitle">{html.escape(b["title"])}</h3>'
            + (f'<ul class="takeaways">{"".join(lis)}</ul>' if lis else "") + f'{b["html"]}</div>')


def agent_profile(ctx, name: str, used=None, known=frozenset()) -> dict:
    """Charts of one agent, keyed by the number of the topic they belong to (the agent page mirrors the v17 topics of
    meta/site.json: 1 结果, 2 解题方式, 3 做事方式, 4 失败模式, 5 改进方向); `used`: case keys the page already shows (its
    note's cases), so a takeaway's example adds a new one where it can; `known`: keys that have a case page anyway."""
    used = set() if used is None else used
    scope = "all" if name == "GPT-6 Luna" else "open"      # Luna ran every cell; the others only the cells Luna did not pass
    blk = lambda title, chart, field="", **kv: chart_block(ctx, title, chart, field, {"agent": name, **kv}, used, known)
    return {
        "1": [blk("同一任务两种模式的成败", FG.fig_modes_chart(ctx, agent=name, scope=scope))],
        "2": [blk("谁在决定每一步动作 · 按模式", FG.fig_loop(ctx, by="mode", agent=name, min=3, lead=1), "loop"),
              blk("工具调用的构成 · 按模式", FG.fig_tools(ctx, by="mode", agent=name))],
        "3": [blk("受挫后怎么办（分析过的失败）· 按模式", FG.fig_dist(ctx, by="mode", field="on_failure", agent=name, min=3, lead=1), "on_failure"),
              blk("失败里时间起了什么作用 · 按模式", FG.fig_time_chart(ctx, by="mode", agent=name, min=3)),
              blk("在时限的什么位置结束 · 按模式", FG.fig_timeuse(ctx, by="mode", agent=name, scope=scope))],
        "4": [blk("低层：失败主因 · 按模式", FG.fig_dist(ctx, by="mode", field="primary", agent=name, top="6", min=3, lead=1), "primary"),
              blk("高层：失败背后的高层错误 · 按模式", FG.fig_reasonkinds(ctx, by="mode", agent=name, min=3)),
              blk("决定性错误在哪个阶段 · 按模式", FG.fig_dist(ctx, by="mode", field="stage", agent=name, min=3, lead=1), "stage")],
        "5": [blk("失败最常缺的那一处改动", FG.fig_fixrank(ctx, agent=name, top="8"))],
    }


def bench_charts(ctx, b: str, used=None, known=frozenset()) -> dict:
    """The two charts of a benchmark page (how it was driven: topic 2 解题方式; why it failed: topic 4 失败模式), with an
    example per takeaway."""
    used = set() if used is None else used
    return {"methods": chart_block(ctx, "谁在决定每一步动作 · 按模式", FG.fig_loop(ctx, by="mode", bench=b, min=1, lead=1), "loop", {"bench": b}, used, known),
            "fails": chart_block(ctx, "失败主因 · 按模式", FG.fig_dist(ctx, by="mode", field="primary", bench=b, top="6", lead=1), "primary", {"bench": b}, used, known)}


def example_keys(blocks) -> set:
    return {k for b in blocks for _, k, _ in b["items"] if k}


def bench_facts(b: str, tasks, trials) -> dict:
    """Robots, simulator and the time limits the trials actually ran under (from the instructions)."""
    mine = [t for t in tasks if t["bench"] == b]
    cut = defaultdict(list)
    for t in trials:
        if t["bench"] == b and Q._f(t.get("cutoff_min")):
            cut[t["mode"]].append(Q._f(t["cutoff_min"]))
    return {"robots": sorted({t["robot"] for t in mine if t["robot"]})[:4], "sim": sorted({t["simulator"] for t in mine if t["simulator"]}),
            "cutoff": {m: round(S.median(v)) for m, v in cut.items()}, "trials": sum(t["bench"] == b for t in trials)}


def results_data(trials, open_trials, cells) -> dict:
    """Success counts for the results table: bench -> agent -> mode -> {all: [s, n], open: [s, n], other: {status: n}};
    `trials` / `open_trials` = the monitor's graded rows (queries.load_perf, perf_open)."""
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"all": [0, 0], "open": [0, 0], "other": Counter()})))
    open_keys = {t["key"] for t in open_trials}
    for t in trials:
        c = out[t["bench"]][t["agent"]][t["mode"]]
        for scope in ("all",) + (("open",) if t["key"] in open_keys else ()):
            c[scope][0] += int(t["success"])
            c[scope][1] += 1
    for c in cells:
        if c["status"] in ("in-progress", "held", "not-scheduled"):
            out[c["bench"]][c["agent"]][c["mode"]]["other"][c["status"]] += 1
    agents = [a for a in Q.ORDER if any(a in v for v in out.values())]
    # row order: the categories' benches, then a bench they do not list (Embodied Safety Exam: success counts include it, it has
    # no page) under its RESULTS_CAT category
    order = [[b, c["id"]] for c in SITE["categories"] for b in c["benches"] if b in out]
    order += [[b, RESULTS_CAT.get(b, "")] for b in sorted(out) if b not in {x for x, _ in order}]
    return {"agents": agents, "order": order, "names": {b: SITE["benches"].get(b, {}).get("name", b) for b, _ in order},
            "cells": {b: {a: {m: {**v, "other": dict(v["other"])} for m, v in md.items()} for a, md in ad.items()} for b, ad in out.items()}}


RESULTS_CAT = {"rsb": "safety", "ese": "safety"}                                 # results-table category of a bench the nav categories leave out


def sample_status(ctx) -> dict:
    """Data status of the review shares: how many current reviews are in the random sample, and whether weights are on."""
    rows = Q.review_rows(ctx, sample=False)
    n_in = sum(r["in_sample"] for r in rows)
    note = (f"图和文中分析的数字只用随机抽样的 {n_in:,} 条分析记录（约三成的 trial；每行的分母是抽样数），{'按层加权' if common.WEIGHTS else '未加权'}；"
            f"另外 {len(rows) - n_in:,} 条是按目的挑的，只作案例。成功数不用抽样，取自评测看板的全量结果。")
    bench = {t["key"]: t["bench"] for t in ctx.all}
    have = {r["key"] for r in rows}
    sel, got = Counter(bench.get(k, "") for k in ctx.sample), Counter(bench.get(k, "") for k in ctx.sample if k in have)
    todo = sorted(b for b in sel if b and got[b] < 0.9 * sel[b])
    if todo:                                           # the 30 % round is still filling: say where the sample is thin
        note += (f"30% 抽样还在分析中：抽中的 {len(ctx.sample):,} 个评测项已分析 {sum(got.values()):,} 个；"
                 f"{len(todo)} 个 benchmark 分析了不到九成（{'、'.join(todo)}），这些 benchmark 在合并的数字里分量偏小。")
    return {"n_sample": n_in, "n_purposive": len(rows) - n_in, "weights": common.WEIGHTS, "sample_note": note, "interim": bool(todo)}


def memo(fns: dict) -> dict:
    """A metric registry whose values are computed once per (name, parameters): the two audiences and compare_sets of
    one set read the same numbers."""
    cache = {}
    def wrap(name, fn):
        def call(**kv):
            key = (name, tuple(sorted(kv.items())))
            if key not in cache:
                cache[key] = fn(**kv)
            return cache[key]
        return call
    return {k: wrap(k, f) for k, f in fns.items()}


def figure_registry(ctx) -> dict:
    """{{fig:…}} name -> callable: queries tables, figs charts, the time (figs_time) and approach (figs_way) charts and,
    when present, the tool charts (figs_tools); with_multi adds the multi-label sentence to by=tasktype / cap charts."""
    extra = FX.figures(ctx) if FX and hasattr(FX, "figures") else {}
    return FG.with_multi({**Q.figures(ctx), **FG.figures(ctx), **FT.figures(ctx), **FW.figures(ctx), **WA.figures(ctx), **extra})


def load_inputs(which: str | None = None, reviews=None) -> dict:
    """Trials, reviews and the metric / figure registries of one task set (queries.SETS; default XB_SET): loaded once
    per run, shared by both audiences. `reviews` (current_reviews) can be shared by both sets."""
    trials, cells, tasks = Q.load(which)
    all_trials = Q.load_all(which)
    reviews = current_reviews() if reviews is None else reviews
    ctx = Q.Context(trials, cells, tasks, reviews, all_trials, which)
    metrics = memo(Q.metrics(ctx))
    metrics["_agents"] = Q.set_agents(ctx.set)                # not a placeholder: the agents bar strips may name (bar_rows)
    return {"trials": trials, "cells": cells, "tasks": tasks, "all_trials": all_trials, "reviews": reviews, "ctx": ctx,
            "set": ctx.set, "metrics": metrics, "figs": figure_registry(ctx)}


def internal_topics() -> dict:
    """Topic id -> topic number for the topics only the internal build shows (they come last, so numbers match)."""
    return {t["id"]: str(i + 1) for i, t in enumerate(SITE["topics"]) if t.get("audience") == "internal"}


def internal_ids(metas: dict) -> set:
    """Finding IDs only the internal build shows: `audience: internal`, any finding of an internal topic, their children."""
    out = {m["id"] for m, _ in metas.values() if m.get("audience") == "internal" or m.get("topic") in internal_topics()}
    while more := {m["id"] for m, _ in metas.values() if m.get("parent") in out} - out:
        out |= more
    return out


def note_source(kind: str, name: str, audience: str, hidden) -> str:
    """A note's markdown as one build shows it. The share build leaves out the parts that list task-side issues: a bench
    note's **注意** bullet with its sub-bullets (notes-4) and an agent note's sections of internal topics."""
    p = os.path.join(HERE, "notes", kind, name + ".md")
    if not os.path.exists(p):
        return ""
    text = open(p).read()
    if audience == "share" and kind == "bench":                  # the **注意** bullet goes with its sub-bullets
        text = re.sub(r"(?m)^- \*\*注意\*\*.*\n?(?:[ \t]+\S.*\n?)*", "", text)
    elif audience == "share":
        drop = set(internal_topics().values())
        text = "".join(part for part in re.split(r"(?m)^(?=## \d)", text) if not (part.startswith("## ") and part[3] in drop))
    return for_audience(text, audience, hidden)


def samples_data(findings: dict, cases: dict, figs: dict) -> dict:
    """The #samples page: each chart kind's first finding figure, one of each progress chart (NEW_SAMPLES), plus one
    finding (figure and cases, no children, not on the results topic), one child section, one starred case card with its
    label and one legend with definitions."""
    order = sorted(findings, key=fnum)
    tops = [f for f in order if not findings[f]["parent"] and '<div class="fig">' in findings[f]["html"] and findings[f]["cases"]]
    plain = next((f for f in tops if findings[f]["topic"] != "outcomes" and not findings[f]["children"]), tops[0])   # most tops have children now
    child = next(f for f in order if findings[f]["parent"])
    case = next((c for f in order for c in findings[f]["cases"] if cases[c]["key_case"] and cases[c]["media"].get("video")), findings[plain]["cases"][0])
    label = next((findings[f]["labels"][case] for f in order if case in findings[f]["labels"]), "")
    def block(spec):
        name, *params = spec.split("|")
        kv = dict(p.split("=", 1) for p in params)
        return {"kind": name, "fig": spec, "html": f'<div class="fig">{fig_caption(name, kv)}{figs[name](**kv)}</div>'}
    return {"charts": [SAMPLES[k] for k in KINDS if k in SAMPLES and k != "legend"] + [block(s) for s in NEW_SAMPLES],
            "legend": SAMPLES.get("legend", {}).get("html", ""),
            "finding": plain, "child": child, "case": case, "case_label": label}


def no_luna(x):
    """The core build's copy of site texts: sentences naming GPT-6 Luna dropped (the core set has no Luna at all)."""
    if isinstance(x, dict):
        return {k: no_luna(v) for k, v in x.items()}
    return re.sub(r"[^。]*Luna[^。]*。", "", x) if isinstance(x, str) else x


def build(inp: dict, audience: str, out: str, media_link: str | None, switch: str, site_dir: str, set_switch: str = "",
          set_note: list | None = None) -> None:
    """One build of the site into <out>/index.html. `switch`: relative link to the other audience's build, `set_switch`:
    to the other task set's build ("" = no switch); `set_note`: the findings whose numbers differ between the sets
    (compare_sets; shown on the all build's home page)."""
    share = audience == "share"
    Q.ACTIVE = inp["set"]                                    # qtips words the scope by the set (no Luna text in core)
    os.makedirs(out, exist_ok=True)
    if media_link:
        dst = os.path.join(out, "media")
        if not os.path.islink(dst):
            os.symlink(os.path.relpath(os.path.join(media_link, "media"), out), dst)
        if not os.path.isdir(os.path.join(media_link, "media")):
            print(f"warning: {media_link}/media does not exist yet; build the internal version there first")
    else:
        os.makedirs(os.path.join(out, "media"), exist_ok=True)
        for p in glob.glob(os.path.join(out, "media", "*")):
            os.remove(p)                               # media is rebuilt from the current case set every time
    SAMPLES.clear()

    trials, cells, tasks, all_trials, reviews, ctx = (inp[k] for k in ("trials", "cells", "tasks", "all_trials", "reviews", "ctx"))
    by_key = {t["key"]: t for t in all_trials}               # cases may show grader- or infra-side trials too
    metrics, figs = inp["metrics"], inp["figs"]

    # findings this build shows (share: internal ones left out), their markdown as this build shows it
    finding_files = sorted(glob.glob(os.path.join(HERE, "findings", "[0-9]*.md")), key=lambda p: fnum(os.path.basename(p)[:-3]))
    metas = {p: front(p) for p in finding_files}
    hidden = internal_ids(metas) if share else set()
    shown = {p: (m, for_audience(b, audience, hidden)) for p, (m, b) in metas.items() if m.get("id") not in hidden}
    ip = os.path.join(HERE, "findings", "_issues.json")
    all_issues = json.load(open(ip)) if os.path.exists(ip) else []
    raw_issues = [] if share else all_issues                  # the issues register is internal
    note_files = [(os.path.basename(os.path.dirname(p)), os.path.basename(p)[:-3]) for p in sorted(glob.glob(os.path.join(HERE, "notes", "*", "*.md")))]

    # cases: every deep review scored >= 3 that nothing cites, plus every review an item of this build cites
    case_keys = lambda meta, body: ({k.strip() for k in meta.get("cases", "").split(",") if k.strip()} | set(re.findall(r"\{\{case:([^}]+)\}\}", body))
                                    | FT.swim_keys(inp["ctx"], body))      # trials in a swimlane get case pages
    note_cases = lambda kind, name: set(re.findall(r"\{\{case:([^}]+)\}\}", note_source(kind, name, audience, hidden)))
    cited = set().union(*(case_keys(m, b) for m, b in shown.values()), *(note_cases(k, n) for k, n in note_files),
                        *(set(i.get("cases", [])) for i in raw_issues))
    cited_any = set().union(*(case_keys(m, b) for m, b in metas.values()), *(set(re.findall(r"\{\{case:([^}]+)\}\}", open(os.path.join(HERE, "notes", k, n + ".md")).read())) for k, n in note_files),
                            *(set(i.get("cases", [])) for i in all_issues))
    # entity-page charts: the example under each chart takeaway gets a case page (one that has a page anyway if it can)
    known = cited | {k for (k, d), r in reviews.items() if d == "deep" and (r.get("case_worthy") or {}).get("score", 0) >= 3 and k not in cited_any}
    profiles = {name: agent_profile(ctx, name, note_cases("agent", slug(name)), known) for name in Q.ORDER if any(t["agent"] == name for t in trials)}
    bcharts = {b: bench_charts(ctx, b, note_cases("bench", b), known) for cat in SITE["categories"] for b in cat["benches"]}
    examples = set().union(*(example_keys(x for blocks in p.values() for x in blocks) for p in profiles.values()), *(example_keys(c.values()) for c in bcharts.values()))
    cited |= examples
    cited_any |= examples
    cases = {}
    for (key, depth), r in sorted(reviews.items(), key=lambda kv: kv[0][1] != "deep"):
        if key in by_key and case_id(key) not in cases and (key in cited or (depth == "deep" and (r.get("case_worthy") or {}).get("score", 0) >= 3 and key not in cited_any)):
            cases[case_id(key)] = case_record(key, r, by_key[key], out)
    for key, ia in ([] if share else ctx.integrity.items()):  # integrity labels belong to the validity topic: internal
        cid = case_id(key)
        if cid in cases:
            cases[cid]["integrity"] = neutral(ia)
        elif key in cited and key in by_key:
            cases[cid] = integrity_case(key, ia, by_key[key], out)
    for cid, c in cases.items():                           # how it drove the robot (approach label, v17 way), in the chart's words
        L = next((x for x in FG.LOOP if x[0] == Q.way(ctx.approach.get(c["key"]) or {})), None)
        c["loop"] = [L[1], L[2], L[3]] if L else []
        c["progress"] = progress_case(ctx.progress.get(c["key"]), ctx.progress2.get(c["key"]), by_key[c["key"]])
        c["key_case"] = False

    findings, topic_f, rated = {}, defaultdict(list), ratings()
    fids = {m["id"] for m, _ in shown.values() if m.get("status", "current") != "retired"} | {i["id"] for i in raw_issues}
    for p in finding_files:
        if p not in shown:
            continue
        meta, body = shown[p]
        fid = meta["id"]
        if meta.get("status") == "retired":
            continue
        listed = [case_id(k.strip()) for k in meta.get("cases", "").split(",") if k.strip()]
        star = [case_id(k.strip()) for k in meta.get("star", "").split(",") if k.strip() and case_id(k.strip()) in cases]
        for c in star:                                      # the case(s) the writer marked as the most telling
            cases[c]["key_case"] = True
        parent = meta.get("parent", "")
        shared = findings[parent]["refs"] if parent in findings else []
        drawn = set(SAMPLES)
        block = (m.group(1) if (m := CASE_BLOCK.search(body)) else "")
        body_html, refs = render_md(CASE_BLOCK.sub("", body), metrics, figs, cases, fids, refs=shared, claim=bool(block))
        shown_ids = [case_id(k) for k in re.findall(r"\{\{case:([^}]+)\}\}", block)]
        listed = list(dict.fromkeys(shown_ids + listed))       # the 案例 block's order first
        for k in set(SAMPLES) - drawn:
            SAMPLES[k]["from"] = fid
        own = [case_id(k) for k in re.findall(r"\{\{case:([^}]+)\}\}", body) if case_id(k) in cases]
        swim = {case_id(k) for k in FT.swim_keys(ctx, body)}   # a trial only a swimlane row shows keeps its case page, no card here
        listed = [c for c in listed if c not in swim or c in own]
        if parent in findings:
            findings[parent]["listed"] += listed
        findings[fid] = {"id": fid, "title": meta["title"], "topic": meta["topic"], "section": meta.get("section", ""),
                         "parent": meta.get("parent", ""), "children": [],
                         "order": int(meta.get("order", 99) or 99),
                         "status": meta.get("status", "current"), "top": int(meta.get("top", 0) or 0),
                         **({"rating": rated[fid]} if fid in rated else {}),
                         "entities": [e.strip() for e in meta.get("entities", "").split(",") if e.strip()],
                         "html": body_html, "refs": refs, "listed": listed,
                         "text": re.sub(r"\s+", " ", re.sub(r"\{\{[^}]*\}\}|^图意[：:].*$|[*#`]", " ", body, flags=re.M)).strip(),   # for search
                         "labels": case_labels(body, meta["title"]), "star": star,   # star: first in the page's video strip
                         "cases": (list(dict.fromkeys(own + listed)) if parent else refs + [c for c in listed if c in cases and c not in refs])}
        findings[fid]["cases"] = [c for c in findings[fid]["cases"] if c in cases]
        findings[fid]["labels"] = {c: findings[fid]["labels"].get(c) or lead_clause(meta["title"]) for c in findings[fid]["cases"]}   # a listed case no bullet cites
        if not meta.get("parent"):                          # a child (§4.2.1) is shown inside its parent, not in the topic list
            topic_f[meta["topic"]].append(fid)
        for c in findings[fid]["cases"]:
            cases[c]["findings"].append(fid)

    for fid, f in findings.items():
        if f["parent"] in findings:
            findings[f["parent"]]["children"].append(fid)
    for f in findings.values():
        f["children"].sort(key=fnum)
        if f["children"]:                                   # numbers follow the shared mark order; each child shows its own cards
            f["nums"] = {c: i + 1 for i, c in enumerate(f["refs"])}
            shown_cases = set()                             # one card per case in the whole block: the first child that cites it
            for k in f["children"]:
                findings[k]["cases"] = [c for c in findings[k]["cases"] if c not in shown_cases]
                shown_cases |= set(findings[k]["cases"])
                findings[k]["nums"] = f["nums"]
            f["cases"] = list(dict.fromkeys(c for c in f["refs"] + [x for x in f["listed"] if x in cases] if c not in shown_cases))
        f.pop("refs", None), f.pop("listed", None)

    sections = {"0"} | {str(i + 1) for i, t in enumerate(SITE["topics"]) if not (share and t["id"] in internal_topics())}

    def entity_page(kind, name, blocks: dict, who) -> tuple[dict, dict]:
        """notes-4: a note's part before the first `## n …` heading is the summary ("0"); each `## n` part belongs to
        page section n = topic n of this build, and so do `blocks[n]` (charts). Rendered in reading order (note n, then
        its charts), so one case numbering runs down the page; a part whose number is no topic of this build is left out
        (check.py warns where a note's heading is not its topic's name)."""
        text = note_source(kind, name, audience, hidden)
        parts = re.split(r"^## (\d)[^\n]*\n", text, flags=re.M) if text else [""]
        body = {"0": parts[0], **dict(zip(parts[1::2], parts[2::2]))}
        refs, notes, charts = [], {}, {}
        for n in sorted((set(body) | set(blocks)) & sections, key=int):    # a section with no topic of this build is left out
            if body.get(n, "").strip():
                notes[n] = render_md(body[n], metrics, figs, cases, fids, refs=refs)[0]
            if blocks.get(n):
                charts[n] = "".join(render_block(b, cases, refs, who) for b in blocks[n])
        return notes, charts

    issues = []
    for i in raw_issues:
        inline = lambda t: re.sub(r"^<p>|</p>$", "", render_md(t or "", metrics, figs, cases, fids)[0].strip())
        issues.append({**i, "what": inline(i.get("what")), "impact": inline(i.get("impact")),
                       "findings": [f for f in i.get("findings", []) if f in findings],
                       "cases": [case_id(k) for k in i.get("cases", []) if case_id(k) in cases]})
    results = results_data(ctx.perf, ctx.perf_open, cells)     # success rates: the monitor's global results (load_perf)
    open_trials = Q.open_cells(trials, cells)

    blocks = cell_block(ctx.perf, cells)
    benches = {}
    for cat in SITE["categories"]:
        for b in cat["benches"]:
            if not any(t["bench"] == b for t in trials):          # a bench with no trials in this set (core: all easy) gets no page
                continue
            rows = blocks.get(b, {})
            ent = f"bench:{b}"
            note, charts = entity_page("bench", b, {"2": [bcharts[b]["methods"]], "4": [bcharts[b]["fails"]]}, lambda c: f'{c["agent"]} · {task_name(c)}')
            benches[b] = {**SITE["benches"][b], "id": b, "cat": cat["id"],
                          "tasks": len({t["base"] for t in tasks if t["bench"] == b}),
                          "facts": bench_facts(b, tasks, trials),
                          "modes": sorted({t["mode"] for t in tasks if t["bench"] == b}, key=["privileged", "standard", "standard-realtime"].index),
                          "rows": [{"agent": ag, "agent_id": slug(ag), "cells": {m: {"s": v["s"], "n": v["n"], "other": dict(v["other"])} for m, v in md.items()}}
                                   for ag, md in sorted(rows.items(), key=lambda kv: Q.ORDER.index(kv[0]))],
                          "findings": [f for f, v in findings.items() if ent in v["entities"]],
                          "cases": [c for c, v in cases.items() if v["bench"] == b], "note": note.get("0", ""),
                          "methods": charts.get("2", ""), "examples": bench_examples(ctx, b, cases), "fails": charts.get("4", ""),
                          "issues": [i["id"] for i in issues if b in i["bench"]]}

    agents = []
    run_of = {name: run for run, name in AGENTS.items()}
    for name in Q.ORDER:
        run = run_of.get(name)
        mine = [t for t in trials if t["agent"] == name]
        if not mine:
            continue
        mine_open = mine if run == LUNA else [t for t in open_trials if t["agent"] == name]   # Luna ran every cell
        perf = [t for t in (ctx.perf if run == LUNA else ctx.perf_open) if t["agent"] == name]   # rates: load_perf
        ent = f"agent:{name}"
        notes, charts = entity_page("agent", slug(name), profiles[name], lambda c: f'{SITE["benches"].get(c["bench"], {}).get("name", c["bench"])} · {task_name(c)}')
        agents.append({
            "id": slug(name), "name": name, "harness": HARNESS.get(run.split("-")[0], run.split("-")[0]),
            "open": {m: Q.rate([t for t in perf if t["mode"] == m]) for m in ("privileged", "standard", "standard-realtime")},
            "endings": dict(Counter(Q.ending(t) for t in mine_open)),
            **({} if share else {"status": dict(Counter(c["status"] for c in cells if c["agent"] == name))}),   # data status: internal
            "time": Q.time_used(mine_open).get(name, {}),
            "findings": [f for f, v in findings.items() if ent in v["entities"]],
            "cases": [c for c, v in cases.items() if v["agent"] == name], "notes": notes, "profile": charts})

    def topic_data(t):
        fs = sorted(topic_f.get(t["id"], []), key=lambda f: (findings[f].get("order", 99), fnum(f)))
        secs = t.get("sections") or list(dict.fromkeys(findings[f]["section"] for f in fs))
        if share:                                          # a section whose findings are all internal (benchmark 侧) goes
            secs = [x for x in secs if any(findings[f]["section"] == x for f in fs)]
        return {**t, "findings": fs, "sections": secs}

    summary = os.path.join(HERE, "findings", "_summary.md")
    codebook = json.load(open(os.path.join(HERE, "meta/codebook.json")))
    if inp["set"] == "core":                                 # the core set has no GPT-6 Luna: no term about it either
        codebook["glossary_zh"] = {k: v for k, v in codebook["glossary_zh"].items() if "Luna" not in k + v}
    data = {
        "site": {"title": SITE["title"], "snapshot": json.load(open(os.path.join(DATA, "changes.json")))["time"],
                 "n_trials": len(all_trials), "n_valid": len(trials), "n_reviews": sum(k in by_key for k, _ in reviews),   # reviews of this set's trials
                 "n_deep": sum(d == "deep" and k in by_key for k, d in reviews), "n_cases": len(cases), "audience": audience, "switch": switch,
                 "set": inp["set"], "sets": no_luna(SITE["sets"]) if inp["set"] == "core" else SITE["sets"], "set_switch": set_switch, "set_note": set_note_html(set_note, findings),
                 "perf_time": Q.perf_time(), "perf_note": PERF_NOTE.format(set=SITE["sets"][inp["set"]]["name"]),
                 **sample_status(ctx)},
        "loop": [list(x) for x in FG.LOOP],                 # approach names and colours (case pills, bench examples)
        "summary": home_blocks(for_audience(open(summary).read(), audience, hidden), audience,
                               lambda t: render_md(t, metrics, figs, cases, fids)) if os.path.exists(summary) else [],
        "topics": [topic_data(t) for t in SITE["topics"] if not (share and t["id"] in internal_topics())],
        "categories": [{**c, "benches": [b for b in c["benches"] if b in benches]} for c in SITE["categories"]], "benches": benches, "agents": agents,
        "findings": findings, "cases": cases,
        "results": results, "issues": issues,
        "top": [f for f, _ in sorted(((f, v["top"]) for f, v in findings.items() if v["top"]), key=lambda x: x[1])],
        "method": {"codebook": codebook} if share else {    # validity classes, cell status and changes: internal
            "validity": dict(Counter(t["validity"] for t in all_trials)),
            "reasons": [[cls, why, n] for (cls, why), n in sorted(Counter((t["validity"], t["validity_reason"]) for t in all_trials if t["validity"] != "valid").items(), key=lambda kv: (kv[0][0], -kv[1]))],
            "status": dict(Counter(c["status"] for c in cells)),
            "codebook": codebook,
            "changes": {k: (len(v) if isinstance(v, list) else v) for k, v in json.load(open(os.path.join(DATA, "changes.json"))).items()}},
    }
    if not share:
        data["samples"] = samples_data(findings, cases, figs)
    read = lambda n: open(os.path.join(site_dir, n)).read().rstrip("\n")
    app = CODE_AUD.sub("", read("app.js")) if share else read("app.js")
    page = open(os.path.join(site_dir, "shell.html")).read().replace("/*STYLE*/", read("style.css")).replace("/*APP*/", app)
    page = page.replace("/*CAUSE_CSS*/", FG.PL.css() + FW.css() + FT.css() + (FX.css() if FX and hasattr(FX, "css") else ""))   # chart colour tokens and the module charts' styles
    page = page.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    open(os.path.join(out, "index.html"), "w").write(page)
    print(f'{audience}: {out}/index.html: {os.path.getsize(os.path.join(out, "index.html")) // 1000} KB, '
          f'{len(findings)} findings, {len(cases)} cases, {len(issues)} issues, media {len(os.listdir(os.path.join(out, "media")))} files')


# core vs all (build.py --both): the text is written on the core set; a finding is flagged for the all build when the
# top group of one of its bar strips changes or one of its shares moves by more than SHIFT points between the sets.
# Values (bar rows, q numbers) from fewer than MIN_N in either set are not compared (样本少).
SHIFT, MIN_N = 10, C.SMALL
CORE_VS_ALL = "/data/pingyue/cross-bench/core_vs_all.md"
_KN = re.compile(r"\s*(\d+(?:\.\d+)?)/(\d+)")
_PN = re.compile(r"\s*(\d+)%（n=(\d+)）")


def share_of(v: str):
    """(share in points, n) of a q value — "k/n…" or a median "p%（n=…）" — or None (minutes, counts, empty)."""
    if m := _KN.match(v):
        return (100 * float(m.group(1)) / int(m.group(2)), int(m.group(2))) if int(m.group(2)) else None
    if m := _PN.match(v):
        return float(m.group(1)), int(m.group(2))
    return None


def compare_sets(core: dict, every: dict) -> list[dict]:
    """Every current finding (internal text) whose numbers may change its claim on the all set: [{id, title, items:
    [{spec, what}]}], items = a bar strip whose top group (the row with the largest share, 全部 aside) changes, a bar row
    or a q value whose share moves by more than SHIFT points. Writes CORE_VS_ALL."""
    out, n_cmp, n_small = [], 0, 0
    for p in sorted(glob.glob(os.path.join(HERE, "findings", "[0-9]*.md")), key=lambda p: fnum(os.path.basename(p)[:-3])):
        meta, body = front(p)
        if meta.get("status") == "retired":
            continue
        body, items, seen = for_audience(body, "internal"), [], set()
        for spec in BARS.findall(body):
            if spec in seen:
                continue
            seen.add(spec)
            A, B = ({lab: (k, n) for lab, k, n, *_ in bar_rows(spec, x["metrics"])[2]} for x in (core, every))
            ok = [lab for lab in A if lab in B and min(A[lab][1], B[lab][1]) >= MIN_N]
            n_cmp += len(ok)
            n_small += len([lab for lab in A if lab not in ok])
            sh = lambda R, lab: 100 * R[lab][0] / R[lab][1]
            groups = [lab for lab in ok if lab != "全部"]
            if len(groups) > 1:
                ta, tb = max(groups, key=lambda g: sh(A, g)), max(groups, key=lambda g: sh(B, g))
                if ta != tb and sh(B, tb) > sh(B, ta) and sh(A, ta) > sh(A, tb):
                    items.append({"spec": "bars:" + spec, "what": f"条形图最高的一组：核心集是「{ta}」（{sh(A, ta):.0f}%），全部任务是「{tb}」（{sh(B, tb):.0f}%）"})
            for lab in ok:
                d = sh(B, lab) - sh(A, lab)
                if abs(d) > SHIFT:
                    items.append({"spec": "bars:" + spec, "what": f"条形图「{lab}」一行：核心集 {A[lab][0]}/{A[lab][1]}，"
                                                                    f"全部任务 {B[lab][0]}/{B[lab][1]}，占比差 {d:+.0f} 个百分点"})
        for kind, spec in PLACEHOLDER.findall(body):
            name, *params = [x.strip() for x in spec.split("|")]
            if kind != "q" or name not in core["metrics"] or spec in seen:
                continue
            seen.add(spec)
            kv = {k: v for k, v in (x.split("=", 1) for x in params if "=" in x) if k not in ("fmt", "show")}   # k/n whatever the text shows
            va, vb = (str(x["metrics"][name](**kv)) for x in (core, every))
            a, b = share_of(va), share_of(vb)
            if not (a and b):
                continue
            if min(a[1], b[1]) < MIN_N:
                n_small += 1
                continue
            n_cmp += 1
            if abs(b[0] - a[0]) > SHIFT:
                items.append({"spec": "q:" + spec, "what": f"正文里的一个数：核心集 {as_count(va)}，全部任务 {as_count(vb)}，占比差 {b[0] - a[0]:+.0f} 个百分点"})
        if items:
            out.append({"id": meta["id"], "title": meta.get("title", ""), "items": items})
    lines = ["# 核心集与全部任务的差别（build.py --both 生成）", "",
             "正文按核心集写成（核心集 = embodied-first-exam docs/core_set.toml 的任务；抽样分析的两个集合都不含 Embodied Safety Exam）。下面列出的结论，在全部任务上"
             f"有条形图最高的一组变了，或有占比变了 {SHIFT} 个百分点以上，结论可能要改。少于 {MIN_N} 的值不比较。", "",
             f"共 {len(out)} 条结论被标出；比较了 {n_cmp} 个值，{n_small} 个因样本少没有比较。", ""]
    for f in out:
        lines += [f"## §{f['id']} {f['title']}", ""] + [f"- {it['what']}（`{it['spec']}`）" for it in f["items"]] + [""]
    os.makedirs(os.path.dirname(CORE_VS_ALL), exist_ok=True)
    open(CORE_VS_ALL, "w").write("\n".join(lines))
    print(f"core vs all: {len(out)} findings flagged ({n_cmp} values compared, {n_small} small) -> {CORE_VS_ALL}")
    return out


def set_note_html(flags: list | None, findings: dict) -> str:
    """The all build's home note: the text is written on the core set, then the findings of this build that compare_sets
    flagged, folded ("" on the core build)."""
    if flags is None:
        return ""
    shown = [f for f in flags if f["id"] in findings]
    head = (f'<p><b>全部任务版</b>：数字按全部任务重算，文字是按核心集写的。'
            + (f"下面 {len(shown)} 条结论的数字在两个集合之间差得较多（条形图最高的一组变了，或某个占比变了 {SHIFT} 个百分点以上），结论可能要改。"
               if shown else "没有哪条结论的数字在两个集合之间差得很多。") + "</p>")
    li = "".join(f'<li><a class="fid" href="#f-{f["id"]}">§{f["id"]}</a> {html.escape(f["title"])}<ul>'
                 + "".join(f"<li>{html.escape(it['what'])}</li>" for it in f["items"]) + "</ul></li>" for f in shown)
    return head + (f'<details class="more"><summary>看这 {len(shown)} 条</summary><ul class="setflags">{li}</ul></details>' if shown else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/Work/cross-bench-artifact"))
    ap.add_argument("--site", default=SITE_DIR, help="template dir (shell.html, style.css, app.js)")
    ap.add_argument("--media-link", help="symlink media/ to this built site's media instead of rebuilding it")
    ap.add_argument("--set", choices=Q.SETS, default=Q.SET, help="task set of a single build (default XB_SET, else core)")
    ap.add_argument("--audience", choices=("internal", "share"), default="internal",
                    help="internal -> <out>/index.html; share -> <out>/share/index.html with media linked to <out>/media")
    ap.add_argument("--both", action="store_true",
                    help="both sets and both audiences: core into <out> (internal + share/), all into <out>/all/ (internal + all/share/)")
    ap.add_argument("--switch", action=argparse.BooleanOptionalAction, default=True,
                    help="the 内部版 ⇄ 分享版 (and with --both 核心集 ⇄ 全部任务) links at the top right; --no-switch for a page sent elsewhere")
    a = ap.parse_args()
    reviews = current_reviews()
    sets = Q.SETS if a.both else (a.set,)
    inputs = {s: load_inputs(s, reviews) for s in sets}
    flags = compare_sets(inputs["core"], inputs["all"]) if a.both else None
    # relative links to the other set's build of the same audience: (internal, share)
    other = {"core": ("all/index.html", "../all/share/index.html"), "all": ("../index.html", "../../share/index.html")}
    for s in sets:
        out = os.path.join(a.out, "all") if a.both and s == "all" else a.out
        sw = other[s] if a.both and a.switch else ("", "")
        note = flags if s == "all" else None
        for audience in (("internal", "share") if a.both else (a.audience,)):
            if audience == "share":
                build(inputs[s], "share", os.path.join(out, "share"), a.media_link or out, "../index.html" if a.switch else "", a.site, sw[1], note)
            else:
                build(inputs[s], "internal", out, a.media_link, "share/index.html" if a.switch else "", a.site, sw[0], note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
