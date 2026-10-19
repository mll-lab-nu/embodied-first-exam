#!/usr/bin/env python3
"""Pre-publish checks of the report standard (meta/DESIGN.md → Report standard) on the findings and the built page.

usage: python3 tools/check.py [PAGE] [--audience internal|share]
PAGE defaults to ~/Work/cross-bench-artifact/index.html (internal) or …/share/index.html (share). The share check also
makes sure no internal item reached the page: no internal finding, issue, data status or samples in the data, and none
of 待核对 / 问题清单 / internal IDs / issue texts / internal-only case IDs anywhere in the HTML.
Bars captions and q hover notes must not show code ids of label values or field names (code_notes).
Every chart's legend colours must be clearly apart in both themes (colour_checks; meta/DESIGN.md → Colours).
A page that says 第 N 级 should also name that level somewhere (level_names; codebook progress_zh level).
The report writes counts, not percentages (user 10-18 night): pct_lines WARNs about the findings / notes lines whose own
text (placeholders dropped) still has a percent sign or a share word (约三成, 过半, 不到一成, 两成, …) and writes them to
PCT_TSV for the writers.
"""
from __future__ import annotations
import argparse, glob, html, json, os, re, sys
from build import FID, SITE, fnum, for_audience, front, internal_ids, internal_topics
from common import HERE, read_csv
import figs as FG
import palette as PL
import qtips
import queries as Q

LIMITS = {"title": 30, "要点": 40, "证据": 70, "解读": 40, "适用范围": 40, "案例": 40, "图意": 50}
# The chart's own 怎么读 line says what a row, a bar and a number are; a 图意 carries only the takeaway.
READING = re.compile(r"^(每行|每条|每格|每个 trial|同一种图)|条长(是|=)|n 为条数|最右是|色块为|色段是")
BANNED = "判读"                                              # no reader sees this word: the term is 分析 (glossary_zh)
# user rules 10-18: never say which model wrote an analysis; never label agents as strong (the three lead by default)
WHO = re.compile(r"(Opus|Sonnet|Haiku)( 5\.5)? ?(写|标|复核|核对)的[^，。；]{0,6}(分析|标注)|Sonnet|Haiku|(强|最强的?) ?agent|三家强|三强")
TOL = 1.15                                                   # names and numbers make strict counts run a little long
# English a reader may see in a bars caption or q hover note (meta/prompts/findings.md → Writing rules), besides agent,
# benchmark and mode names
ALLOWED = {"trial", "agent", "benchmark", "harness", "reset", "token", "privileged", "standard", "realtime", "standard-realtime",
           "IK", "FK", "PD", "MPC", "RL",
           "Code", "to", "Control", "Direct", "Train", "Model"}      # approach names Code to Control / Direct Control / Train Model to Control
CODE = re.compile(r"[A-Za-z][A-Za-z0-9_:/+-]*")
NOTES = re.compile(r'<p class="qbcap">(.*?)</p>|class="(?:qv|qbrow[^"]*)" data-tip="([^"]*)"', re.S)


def code_ids() -> set[str]:
    """ASCII ids a caption or hover note must not show: label values and field names (every key and code list of
    meta/codebook.json, the figs tables, the q filter names), trial and feature columns and the coded values of trial
    columns. Agent, benchmark and mode names and ALLOWED are not ids; task names are not in the set."""
    ids = set()
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                ids.add(str(k))
                walk(v)
        elif isinstance(x, list):
            for v in x:
                if isinstance(v, str) and CODE.fullmatch(v):
                    ids.add(v)
                walk(v)
    walk({k: v for k, v in FG.CB.items() if k != "glossary_zh"})
    for table in (FG.LOOP, FG.TECH, FG.TECH_ANN, FG.PERCEPTION, FG.INTEGRITY, FG.DELIV, FG.GRASP, FG.FAMILIES, FG.STAGES, FG.ENDS, FG.TOOLS):
        ids |= {t[0] for t in table}
    ids |= set(FG.CLAIM) | set(FG.CAT_NAME) | set(SITE["benches"]) | set(qtips.FLAG) | set(qtips.PROG_MED) | set(qtips.MED) | set(qtips.PROG_NAMES)
    ids |= set(qtips.PHASE) | set(qtips.WINDOW) | set(qtips.CAUSE_GROUP) | set(Q.REMEDY_FAMILY.values()) | qtips.SKIP | {"by", "reviewer", "v1", "v2"}
    for name in ("trials.csv", "features.csv"):
        rows = read_csv(name)
        ids |= set(rows[0]) if rows else set()
        if name == "trials.csv":
            ids |= {v for r in rows for k in ("validity", "validity_reason", "exception", "end_reason") for v in r[k].split(",") if CODE.fullmatch(v)}
    names = {w for a in Q.ORDER for w in a.split()} | {w for b in SITE["benches"].values() for w in b["name"].split()} | set(FG.MODE_NAME.values())
    return {i for i in ids if CODE.fullmatch(i)} - ALLOWED - names - {"1", "0"}


def code_notes(D: dict, say) -> None:
    """FAIL where a rendered {{bars:…}} caption or {{q:…}} hover note shows a code id (qtips.counted / qtips.tip must
    say every field and value in plain Chinese: meta/codebook.json *_zh maps)."""
    ids, hits = code_ids(), {}
    def walk(x, where):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, f"{where}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{where}[{i}]")
        elif isinstance(x, str) and ("qbcap" in x or "data-tip" in x):
            for m in NOTES.finditer(x):
                t = html.unescape(re.sub(r"<[^>]+>", "", m.group(1) or m.group(2)))
                bad = {w.rstrip("/:+-") for w in CODE.findall(t)} & ids
                if bad:
                    loc = "§" + where[len("data.findings."):].rsplit(".", 1)[0] if where.startswith("data.findings.") else where[5:]
                    h = hits.setdefault(loc, [set(), t])
                    h[0].update(bad)
    walk(D, "data")
    for loc, (bad, t) in sorted(hits.items(), key=lambda x: (not x[0].startswith("§"), fnum(x[0][1:]) if x[0].startswith("§") else (0,), x[0])):
        say("FAIL", f"{loc}: a bars caption or hover note shows code ids {', '.join(sorted(bad))} (qtips.py, meta/codebook.json *_zh): {t[:70]}…")


LEGEND = re.compile(r'<div class="legend">(.*?)</div>|<dl class="legend defs">(.*?)</dl>', re.S)
SWATCH = re.compile(r'<i (?:class="[^"]*" )?style="background:var\((--[\w-]+)\)[^"]*"></i>(.*?)(?:</span>|</dt>)', re.S)
CHART = re.compile(r'<div class="(?:chart(?: [\w-]+)*|profile)">')          # chart swim / chart wayrate start a chart too
CAPTION = re.compile(r'class="figcap">(.*?)</p>|<h3 class="ctitle">(.*?)</h3>')


def chart_legends(x, where="data"):
    """Every coloured chart in the page data: (where, title, groups), groups = the legend as one [(label, token)] list
    per declared group (a phased chart's .pleg groups), or a single list; a profile table's loop dots count as one
    legend. Charts without colour swatches (bars, heat tables) yield nothing."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield from chart_legends(v, f"{where}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from chart_legends(v, f"{where}[{i}]")
    elif isinstance(x, str) and CHART.search(x):
        plain = lambda t: html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
        swatches = lambda block: [(plain(lab), tok) for tok, lab in SWATCH.findall(block)]
        starts = [m.start() for m in CHART.finditer(x)] + [len(x)]
        for a, b in zip(starts, starts[1:]):
            chunk, caps = x[a:b], list(CAPTION.finditer(x, 0, a))
            title = plain(caps[-1].group(1) or caps[-1].group(2)) if caps else ""
            if chunk.startswith('<div class="profile">'):
                groups = [[(t, t) for t in dict.fromkeys(re.findall(r'class="dot" style="background:var\((--[\w-]+)\)', chunk))]]
            elif '<div class="plegs">' in chunk:
                groups = [swatches(m.group(0)) for g in re.finditer(r'<div class="pleg"><b>.*?</b>', chunk)
                          if (m := LEGEND.match(chunk, g.end()))]
            else:
                groups = [[it for m in LEGEND.finditer(chunk) for it in swatches(m.group(0))]]
            groups = [g for g in groups if g]
            if sum(map(len, groups)) > 1:
                yield where, title, groups


def colour_checks(s: str, D: dict, say) -> None:
    """FAIL where a chart's legend colours read as one in either theme: below palette.FLOOR (validate_palette.js'
    normal-vision floor) for any pair of an ungrouped legend, or, with declared groups, for adjacent members of a group
    or any pair across groups; WARN where touching entries fall below the colour-blind floor (palette.CVD_FLOOR)."""
    themes = dict(zip(("light", "dark"), PL.page_tokens(s)))
    agents = {f"data.agents[{i}]": f"agent {a['id']}" for i, a in enumerate(D.get("agents", []))}
    def loc(where):
        m = re.match(r"data\.findings\.([\d.]+?)\.(?:html|children)", where)
        if m:
            return f"§{m.group(1)}"
        head = re.match(r"data\.agents\[\d+\]", where)
        return agents.get(head.group(0), where[5:]) + where[head.end():] if head else where[5:]
    for where, title, groups in chart_legends(D):
        for theme, tokens in themes.items():
            close = sorted(PL.too_close(groups, tokens))
            for kind, level, floor in (("normal", "FAIL", PL.FLOOR), ("cvd", "WARN", PL.CVD_FLOOR)):
                pairs = [c for c in close if c[3] == kind]
                if pairs:
                    shown = "；".join(f"{a} ~ {b} ΔE {d:.1f}" for d, a, b, _ in pairs[:3]) + (f"（共 {len(pairs)} 对）" if len(pairs) > 3 else "")
                    say(level, f"{loc(where)} 「{title}」: {theme} legend colours closer than {'colour-blind ' if kind == 'cvd' else ''}ΔE {floor:.0f}"
                               f"{' (declared groups)' if len(groups) > 1 else ''}: {shown} (tools/palette.py, meta/DESIGN.md → Colours)")


LEVEL_REF = re.compile(r"第\s*([0-5零一二三四五])\s*级")
ZH_DIGIT = dict(zip("零一二三四五", "012345"))


def level_names(D: dict, say) -> None:
    """WARN where a page says 第 N 级 (N = 0–5, digits or 一…五) but the level's name (codebook progress_zh level, e.g.
    关键动作做成一次 for 3) appears nowhere on it. A page: a finding with its children, an agent page (all its notes), a
    benchmark note, the three-agent comparison, the home page. Visible text only (hover notes and tags dropped); a name
    inside a longer level name does not count (做成 inside 关键动作做成一次)."""
    names = {k: v[0] for k, v in FG.PROG["level"].items()}
    F, pages = D["findings"], {}
    for fid, f in F.items():
        top = fid
        while F[top].get("parent") in F:
            top = F[top]["parent"]
        pages.setdefault(f"§{top}", []).append(f["html"])
    for a in D["agents"]:
        pages[f"agent {a['id']}"] = list(a["notes"].values())
    for k, b in D["benches"].items():
        pages[f"bench {k}"] = [b["note"]]
    if D.get("compare"):
        pages["compare"] = [D["compare"]["summary"]] + [h for _, _, h in D["compare"]["secs"]]
    pages["home"] = [b["html"] + b["fig"] for b in D["summary"]]
    for where, parts in sorted(pages.items(), key=lambda x: (not x[0].startswith("§"), fnum(x[0][1:]) if x[0].startswith("§") else (0,), x[0])):
        text = html.unescape(re.sub(r"<[^>]+>", " ", " ".join(p or "" for p in parts)))
        said = sorted({ZH_DIGIT.get(n, n) for n in LEVEL_REF.findall(text)})
        for n in said:
            rest = text
            for m, nm in names.items():
                if m != n and names[n] in nm:
                    rest = rest.replace(nm, " ")
            if names[n] not in rest:
                say("WARN", f"{where}: says 第 {n} 级 but never names it 「{names[n]}」 (meta/codebook.json progress_zh level)")


PCT_TSV = "/data/pingyue/cross-bench/rewrite/v21_pct_hits.tsv"
SHARE_WORD = re.compile(r"[%％]|(?:约|近|不到|超过|多于|少于|逾)?[一二两三四五六七八九十]成(?:多|半)?|过半|近半|大半|一半|半数|[二三四五六七八九十]分之[一二三四五六七八九]")
FRONT_KEYS = re.compile(r"^(id|topic|section|entities|cases|star|status|top|parent|order|audience):")


def pct_lines() -> list[tuple]:
    """(file, finding id or note name, line, snippet) for every findings / notes line whose own text (placeholders and
    front matter other than the title dropped) has a percent sign or a share word (SHARE_WORD)."""
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, "findings", "*.md")) + glob.glob(os.path.join(HERE, "notes", "*", "*.md"))):
        name = os.path.basename(p)[:-3]
        if name.startswith("_") and name != "_summary":
            continue
        rel = os.path.relpath(p, HERE)
        fid = (front(p)[0].get("id") or name) if rel.startswith("findings/") else "note:" + rel[len("notes/"):-3]
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            if FRONT_KEYS.match(line):
                continue
            text = re.sub(r"\{\{[^}]*\}\}", " ", line).rstrip("\n")
            for m in SHARE_WORD.finditer(text):
                out.append((rel, fid, i, text[max(0, m.start() - 25):m.end() + 15].strip().replace("\t", " ")))
    return out


def visible(text: str) -> int:
    """Characters a reader sees: placeholders and case marks dropped, each ASCII word counted once."""
    t = re.sub(r"\{\{[^}]*\}\}", "", text)
    t = re.sub(r"[*`#>\[\]()（）]|§\d[\d.]*|问题 \d+", "", t)
    t = re.sub(r"[A-Za-z0-9_.\-+/:%]+", "a", t)
    return len(re.sub(r"\s+", "", t))


def bullets(body: str) -> dict:
    """Top-level bullets of each part of a findings-3/5 body: {要点: [...], 证据: [...], 解读: [...], 适用范围: [...], 图意: [...]}."""
    parts, cur = {"要点": [], "证据": [], "解读": [], "适用范围": [], "案例": [], "图意": []}, "要点"
    for line in body.splitlines():
        m = re.match(r"^\*\*(证据|解读|适用范围|案例)\*\*", line)
        if m:
            cur = m.group(1)
        elif line.startswith("图意："):
            parts["图意"].append(line[3:])
        elif line.startswith("- "):
            parts[cur].append(line[2:])
    return parts


def legend_names(fig_html: str) -> list[str]:
    """Category names printed in the legends of the first figure in `fig_html` (none for a chart without a legend)."""
    fig = fig_html.split('<div class="fig">')[1:2]
    if not fig:
        return []
    names = [n for b in re.findall(r'<dl class="legend defs">(.*?)</dl>', fig[0], re.S) for n in re.findall(r"<dt>(?:<i[^>]*></i>)?(.*?)</dt>", b)]
    names += [n for b in re.findall(r'<div class="legend">(.*?)</div>', fig[0], re.S) for n in re.findall(r"<span>(?:<i[^>]*></i>)?(.*?)</span>", b)]
    return [html.unescape(re.sub(r"<[^>]+>", "", n)).strip() for n in names]


def data(page: str) -> tuple[str, dict]:
    s = open(page, encoding="utf-8").read()
    return s, json.loads(re.search(r"const DATA = (\{.*?\});\n", s, re.S).group(1).replace("<\\/", "</"))


def share_checks(s: str, D: dict, page: str, say) -> None:
    """Nothing internal reached the share page: not in the data, not as text anywhere in the HTML (template code too)."""
    metas = {p: front(p) for p in glob.glob(os.path.join(HERE, "findings", "[0-9]*.md"))}
    hidden = internal_ids(metas)
    issues = json.load(open(os.path.join(HERE, "findings", "_issues.json")))
    if D["site"].get("audience") != "share":
        say("FAIL", "page is not a share build (site.audience)")
    for f in sorted(hidden & set(D["findings"]), key=fnum):
        say("FAIL", f"internal finding §{f} is in the data")
    if D["issues"] or any(b["issues"] for b in D["benches"].values()):
        say("FAIL", "issues are in the data")
    if any(t["id"] in internal_topics() for t in D["topics"]) or "samples" in D or set(D["method"]) != {"codebook"} or any("status" in a for a in D["agents"]):
        say("FAIL", "internal topic, samples, method data status or agent status is in the data")
    for word in ("待核对", "问题清单"):
        if word in s:
            say("FAIL", f"'{word}' appears in the page")
    for m in re.finditer(r"(?:^|(?<=[\s（(、，,；见和与及>\"]))问题 ?\d{1,2}(?![\d./%])|#issue-|issueList", s):
        say("FAIL", f"issue ID in the page: …{s[max(0, m.start() - 30):m.end() + 10]}…")
    for f in sorted(hidden, key=fnum):
        for m in re.finditer(rf"§{re.escape(f)}(?![\d]|\.\d)|#f-{re.escape(f)}\"", s):
            say("FAIL", f"internal ID §{f} in the page: …{s[max(0, m.start() - 30):m.end() + 10]}…")
    plain = lambda t: re.sub(r"\{\{[^}]*\}\}|<[^>]+>|[*`]", "", t or "")
    for m, _ in metas.values():
        if m.get("id") in hidden and m.get("title") and html.escape(m["title"], quote=False) in s or m.get("id") in hidden and m.get("title", "") in s:
            say("FAIL", f"title of internal §{m['id']} in the page")
    for i in issues:
        for part in re.split(r"[。；]", plain(i.get("what"))):
            if len(part) >= 16 and (part in s or html.escape(part, quote=False) in s):
                say("FAIL", f"text of {i['id']} in the page: {part[:30]}…")
                break
    internal_page = os.path.join(os.path.dirname(os.path.abspath(page)), "..", "index.html")
    if not os.path.exists(internal_page):
        say("WARN", f"no internal build at {internal_page}; internal-only case IDs not checked")
        return
    _, DI = data(internal_page)
    only = set(DI["cases"]) - set(D["cases"])
    left = sorted(c for c in only if re.search(rf"\b{c}\b", s))
    if left:
        say("FAIL", f"{len(left)} internal-only case IDs in the page, e.g. {left[:3]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("page", nargs="?")
    ap.add_argument("--audience", choices=("internal", "share"), default="internal")
    a = ap.parse_args()
    page = a.page or os.path.expanduser("~/Work/cross-bench-artifact/" + ("share/index.html" if a.audience == "share" else "index.html"))
    out, fail = [], False
    s, D = data(page)
    F = D["findings"]

    def say(level, msg):
        nonlocal fail
        fail |= level == "FAIL"
        out.append(f"{level} {msg}")

    bars = s.count("⟨missing bars") + s.count("{{bars:")     # a kind without k/n, or a spec the build did not match
    if s.count("⟨missing") - s.count("⟨missing bars"):
        say("FAIL", f"{s.count('⟨missing') - s.count('⟨missing bars')} placeholders did not resolve")
    if bars:
        say("FAIL", f"{bars} bars placeholders did not resolve (meta/prompts/findings.md → Placeholders)")
    if re.search("(?i)oracle", s):
        say("FAIL", "the word 'oracle' appears in the page")
    if BANNED in s:
        say("FAIL", f"the word '{BANNED}' appears in the page ({s.count(BANNED)} times): write 分析 (meta/prompts/findings.md)")
    who = sorted({m.group(0) for m in WHO.finditer(re.sub(r"<[^>]+>", "", s))})
    if who:
        say("FAIL", f"the page names who wrote an analysis or labels agents as strong: {who} (meta/prompts/findings.md)")
    code_notes(D, say)
    colour_checks(s, D, say)
    level_names(D, say)
    # every link resolves, and every § in any rendered text (findings, notes, summary, issues) is a link
    texts = {f"§{k}": f["html"] for k, f in F.items()} | {f"home {b['name']}": b["html"] + b["fig"] for b in D["summary"]} | {f"bench {k}": b["note"] for k, b in D["benches"].items()} \
        | {"home set note": D["site"].get("set_note", "")} \
        | {f"agent {x['id']} {n}": v for x in D["agents"] for n, v in x["notes"].items()} | {i["id"]: i["what"] + i["impact"] for i in D["issues"]} \
        | ({f"compare {n}": h for n, _, h in [["0", "", D["compare"]["summary"]]] + D["compare"]["secs"]} if D.get("compare") else {})
    known = {"f": set(F), "case": set(D["cases"]), "issue": {i["id"] for i in D["issues"]}, "bench": set(D["benches"]),
             "agent": {x["id"] for x in D["agents"]} | ({"compare"} if D.get("compare") else set()), "topic": {t["id"] for t in D["topics"]}}
    for where, h in texts.items():
        for m in re.finditer(r'href="#(f|case|issue|bench|agent|topic)-([^"]+)"', h):
            if m.group(2) not in known[m.group(1)]:
                say("FAIL", f"{where}: link #{m.group(1)}-{m.group(2)} does not resolve")
        if not where.startswith("§"):
            for m in re.finditer(r"§(\d\.\d{1,2}(?:\.\d{1,2})?)(?!\d)", re.sub(r"<a [^>]*>.*?</a>", "", h)):
                say("FAIL", f"{where}: reference §{m.group(1)} is not a link")
    if a.audience == "share":
        share_checks(s, D, page, say)
    hits = pct_lines()
    os.makedirs(os.path.dirname(PCT_TSV), exist_ok=True)
    with open(PCT_TSV, "w", encoding="utf-8") as f:
        f.write("file\tfinding\tline\tsnippet\n" + "".join(f"{a_}\t{b_}\t{c_}\t{d_}\n" for a_, b_, c_, d_ in hits))
    if hits:
        ids = list(dict.fromkeys(h[1] for h in hits))
        say("WARN", f"{len(hits)} findings / notes lines still give a percent or share word instead of a count, in {len(ids)} items "
                    f"({', '.join(ids[:8])}{'…' if len(ids) > 8 else ''}) -> {PCT_TSV}")
    rated = json.load(open(os.path.join(HERE, "meta/ratings.json"))) if os.path.exists(os.path.join(HERE, "meta/ratings.json")) else {}
    for fid, v in rated.items():
        if fid not in F and a.audience == "internal" or v not in ("high", "mid", "low"):
            say("WARN", f"meta/ratings.json: {fid!r} → {v!r} is not a finding of this page or not high / mid / low")
    for fid, f in F.items():
        if f["html"].count('<div class="fig">') != f["html"].count('class="figsay"'):
            say("FAIL", f"§{fid}: a figure has no 图意 line")
    def walk(x, where):                                    # every figure anywhere in the data has its 怎么读 line
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, f"{where}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{where}[{i}]")
        elif isinstance(x, str) and '<div class="fig">' in x:
            for part in x.split('<div class="fig">')[1:]:
                if 'class="howto"' not in part:
                    cap = re.search(r'class="figcap">(.*?)</p>', part)
                    say("FAIL", f"{where}: figure {cap.group(1) if cap else ''} has no 怎么读 line")
    walk(D, "data")
    for b in SITE.get("home", []):
        if b.get("say") and READING.search(b["say"]):
            say("FAIL", f"meta/site.json home '{b['block']}': say repeats how to read the chart (the 怎么读 line says it): {b['say'][:20]}…")
    for b in D["summary"]:
        if b["fig"].count('<div class="fig">') != b["fig"].count('class="figsay"'):
            say("FAIL", f"home {b['name']}: the chart has no 图意 line")
        for m in re.finditer(r"§(\d\.\d{1,2}(?:\.\d{1,2})?)(?!\d)", re.sub(r"<a [^>]*>.*?</a>", "", f["html"])):
            say("FAIL", f"§{fid}: reference §{m.group(1)} does not resolve")
    # numbering follows reading order, children numbered 1..k under their parent
    for t in D["topics"]:
        shown = []
        for sec in t["sections"] or [""]:
            shown += [f for f in t["findings"] if (F[f]["section"] or "") == sec]
        nums = [fnum(f) for f in shown]
        if nums != sorted(nums):
            say("FAIL", f"topic {t['id']}: numbers do not follow reading order: {shown}")
        for f in shown:
            kids = F[f]["children"]
            if kids and [fnum(k)[-1] for k in kids] != list(range(1, len(kids) + 1)):
                say("FAIL", f"§{f}: children are not numbered 1..{len(kids)}: {kids}")
    # a child's title starts with a category name of its parent's first figure (only when that figure has a legend)
    for fid, f in F.items():
        names = legend_names(F[f["parent"]]["html"]) if f["parent"] in F else []
        if names and not any(f["title"].startswith(n) for n in names):
            say("WARN", f"§{fid}: title does not start with a legend name of §{f['parent']}'s figure ({', '.join(names)[:90]})")
    # entity notes follow the topics: an agent note's `## n name` is topic n of meta/site.json (build.py drops a part whose
    # number is no topic, and puts a part under topic n whatever its heading says)
    names = {str(i + 1): t["name"] for i, t in enumerate(SITE["topics"])}
    for p in sorted(glob.glob(os.path.join(HERE, "notes", "agent", "[!_]*.md"))):
        for n, name in re.findall(r"^## (\d)\s*([^\n]*)", open(p).read(), re.M):
            if names.get(n) != name.strip():
                say("WARN", f"notes/agent/{os.path.basename(p)}: section '## {n} {name.strip()}' is not topic {n} "
                            f"({names.get(n, 'none: left out of the page')})")
    # lengths and child sections, from the sources
    for p in sorted(glob.glob(os.path.join(HERE, "findings", "[0-9]*.md")), key=lambda p: fnum(os.path.basename(p)[:-3])):
        meta, body = front(p)
        body = for_audience(body, "internal")                 # lengths are measured on the internal text
        fid = meta.get("id")
        if meta.get("status") == "retired":
            continue
        if visible(meta.get("title", "")) > LIMITS["title"] * TOL:
            say("WARN", f"§{fid}: title {visible(meta['title'])} > {LIMITS['title']} 字")
        for t in bullets(body)["图意"]:
            if READING.search(t):
                say("FAIL", f"§{fid}: 图意 repeats how to read the chart (the 怎么读 line says it): {t[:20]}…")
        if meta.get("parent"):
            if not re.search(r"^- 是什么|^- 每条", body, re.M) or len(re.findall(r"\{\{case:", body)) < 2:
                say("WARN", f"§{fid}: child section lacks 是什么 or 2+ examples")
            continue
        for part, items in bullets(body).items():
            for b in items:
                if visible(b) > LIMITS[part] * TOL:
                    say("WARN", f"§{fid}: {part} bullet {visible(b)} > {LIMITS[part]} 字: {html.unescape(b)[:30]}…")
    print("\n".join(out) or "all checks passed")
    print(f"{sum(l.startswith('FAIL') for l in out)} FAIL, {sum(l.startswith('WARN') for l in out)} WARN")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
