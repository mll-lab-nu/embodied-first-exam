#!/usr/bin/env python3
"""Topic packets for finding synthesis: $XB_WORK/packets/<topic>.md (figures as text + review lines). No LLM.

usage: tools/packet.py [topic ...]      # default: every topic in meta/site.json
"""
from __future__ import annotations
import html, json, os, re, sys
from collections import Counter, defaultdict
import figs as FG
import queries as Q
from common import HERE
from review import current_reviews

WORK = os.environ.get("XB_WORK", "/data/pingyue/cross-bench")
SITE = json.load(open(os.path.join(HERE, "meta/site.json")))


def text(fragment: str) -> str:
    """HTML table -> pipe table."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", fragment, re.S)
    out = []
    for r in rows:
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def lines(rows, reviews, fields=("primary", "headline")) -> str:
    out = []
    for r in rows:
        rv = reviews.get((r["key"], r["depth"]))
        extra = []
        if "approach" in fields:
            extra.append("approach: " + rv["approach"].get("summary", "")[:120])
        if "time" in fields:
            t = rv.get("time") or {}
            extra.append(f'time: stop={str(t.get("stop_reason", ""))[:140]}; wasted={str(t.get("wasted", ""))[:100]}; first_deliverable={t.get("first_deliverable_t", "")}')
        if "style" in fields:
            st = rv.get("style") or {}
            extra.append("style: " + " ".join(f"{k}={st.get(k)}" for k in ("plan_vs_act", "exploration", "on_failure", "image_use", "verification")) + " · " + str(st.get("notes", ""))[:80])
        if "decisive" in fields and rv.get("failure"):
            extra.append("decisive: " + str((rv["failure"].get("decisive") or {}).get("what", ""))[:160])
        notable = " / ".join(str(n)[:150] for n in (rv.get("notable") or [])[:3]) if "notable" in fields else ""
        out.append(f'- `{r["key"]}` · {r["agent"]} · {r["bench"]} · {r["mode"]} · {r["outcome"]} · {r["primary"] or "-"} · '
                   f'{str(rv["headline"])[:120]}' + ("".join(f"\n  {e}" for e in extra)) + (f"\n  notable: {notable}" if notable else ""))
    return "\n".join(out)


def build(topic: str, ctx, reviews) -> str:
    t = next(x for x in SITE["topics"] if x["id"] == topic)
    figs = Q.figures(ctx)
    rows = Q.review_rows(ctx, sample=False)                  # review lines: every current review (shares in figs: sample)
    fail = [r for r in rows if r["outcome"] == "failure"]
    dist = lambda by, field, outcome="failure": text(figs["dist"](by=by, field=field, outcome=outcome))
    parts = [f"# Packet: {t['name']} ({topic})\n\nQuestion: {t['question']}\n",
             f"{len(ctx.trials)} valid trials; {len(rows)} reviewed trials ({sum(r['depth'] == 'deep' for r in rows)} deep).\n"
             "Non-Luna agents ran only the cells Luna did not pass; their rates are on that harder subset.\n"]
    sec = lambda title, body: parts.append(f"\n## {title}\n{body}\n")
    if topic == "outcomes":
        sec("Success on cells Luna did not pass", text(figs["rescue"]()))
        sec("Same tasks for every main agent", text(figs["common"]()))
        sec("Benchmark x agent, privileged", text(figs["bench_priv"]()))
        sec("Benchmark x agent, standard", text(figs["bench_std"]()))
        solved = defaultdict(set)
        for x in ctx.trials:
            if x["success"] == "1":
                solved[x["base"]].add(x["agent"])
        bases = {x["base"]: x["bench"] for x in ctx.trials}
        never = Counter(b for base, b in bases.items() if not solved.get(base))
        sec("Task bases no agent solved in any mode, per benchmark", "\n".join(f"- {b}: {n}" for b, n in never.most_common()))
        sec("Reviews (failures)", lines(fail, reviews))
    elif topic == "paradigms":
        sec("Final-code flags", text(figs["code"]()))
        sec("Paradigm by category (successes)", dist("category", "paradigm", "success"))
        sec("Paradigm by category (failures)", dist("category", "paradigm"))
        sec("Paradigm by agent (successes)", dist("agent", "paradigm", "success"))
        sec("Reviews", lines(rows, reviews, ("approach",)))
    elif topic == "styles":
        sec("Process medians", text(figs["process"]()))
        for f in ("plan_vs_act", "on_failure", "verification", "exploration", "image_use", "claim"):
            sec(f"{f} by agent (all reviews)", dist("agent", f, "failure") + "\n\nsuccesses:\n" + dist("agent", f, "success"))
        sec("Reviews", lines(rows, reviews, ("style",)))
    elif topic == "failures":
        sec("Primary cause by agent", dist("agent", "primary"))
        sec("Primary cause by category", dist("category", "primary"))
        sec("Stage by agent", dist("agent", "stage"))
        sec("Secondary causes by agent", dist("agent", "secondary"))
        sec("Primary cause by mode", dist("mode", "primary"))
        sec("Reviews (failures)", lines(fail, reviews, ("decisive",)))
    elif topic == "time":
        sec("Clock use on failures", text(figs["time"]()))
        sec("How trials end", text(figs["endings"]()))
        sec("clock_aware / planned_budget by agent", dist("agent", "clock_aware") + "\n\n" + dist("agent", "planned_budget"))
        sec("Secondary causes by agent (time codes appear here too)", dist("agent", "secondary"))
        sec("Reviews (failures)", lines(fail, reviews, ("time",)))
    elif topic == "modes":
        sec("Paired tasks by mode", text(figs["modes"]()))
        sec("Primary cause by mode", dist("mode", "primary"))
        sec("Stage by mode", dist("mode", "stage"))
        pairs = {(r["agent"], r["base"], r["mode"]): r for r in rows}
        flip = [r for r in fail if r["mode"] != "privileged" and any(
            x["agent"] == r["agent"] and x["base"] == r["base"] and x["mode"] == "privileged" and x["success"] == "1" for x in ctx.trials)]
        sec("Reviewed standard/realtime failures whose privileged twin passed", lines(flip, reviews, ("decisive",)))
        sec("Other non-privileged failures", lines([r for r in fail if r["mode"] != "privileged" and r not in flip], reviews))
    elif topic == "validity":
        all_t = Q.read_csv("trials.csv")
        sec("Validity classes per agent", "\n".join(f"- {a}: {dict(Counter(t['validity'] for t in all_t if t['agent'] == a))}" for a in Q.ORDER))
        sec("Reasons", "\n".join(f"- {k}: {v}" for k, v in Counter(t["validity_reason"] for t in all_t if t["validity"] != "valid").most_common()))
        ext = [r for r in rows if r["stage"] == "external" or any(w in " ".join(reviews[(r["key"], r["depth"])].get("notable") or []).lower()
                                                                  for w in ("benchmark", "grader", "verifier", "instruction", "spec", "infra"))]
        sec("Reviews mentioning grader / task / infra issues", lines(ext, reviews, ("notable",)))
    return "".join(parts)


def entities(ctx, reviews) -> str:
    """One section per benchmark and per agent: results, top causes, a few review headlines (for <= 3-line notes)."""
    rows = Q.review_rows(ctx, sample=False)
    out = ["# Packet: entity notes\n"]
    for b, meta in SITE["benches"].items():
        rs = [r for r in rows if r["bench"] == b]
        if not rs:
            continue
        tr = [t for t in ctx.trials if t["bench"] == b]
        res = "; ".join(f"{a} {m[:4]} {s}/{n}" for (a, m), v in sorted(Q.by(tr, "agent", "mode").items()) for s, n in [Q.rate(v)])
        causes = Counter(r["primary"] for r in rs if r["primary"]).most_common(5)
        heads = [f"{r['agent']}·{r['mode'][:4]}·{r['outcome']}: {str(reviews[(r['key'], r['depth'])]['headline'])[:110]}" for r in rs[:8]]
        out.append(f"\n## bench:{b} ({meta['name']})\nresults (valid trials; non-Luna = Luna-failed cells): {res}\n"
                   f"top causes: {causes}\n" + "\n".join("- " + h for h in heads))
    time_tbl = text(Q.figures(ctx)["time"]())
    out.append("\n## agents: time table\n" + time_tbl)
    for a in Q.ORDER:
        rs = [r for r in rows if r["agent"] == a]
        if not rs:
            continue
        causes = Counter(r["primary"] for r in rs if r["primary"]).most_common(6)
        st = {f: dict(Counter(r[f] for r in rs if r[f]).most_common(3)) for f in ("plan_vs_act", "on_failure", "verification", "image_use", "claim")}
        heads = [f"{r['bench']}·{r['mode'][:4]}·{r['outcome']}: {str(reviews[(r['key'], r['depth'])]['headline'])[:110]}" for r in rs[:6]]
        out.append(f"\n## agent:{a}\nreviews {len(rs)}; top causes {causes}\nstyle {st}\n" + "\n".join("- " + h for h in heads))
    return "\n".join(out)


def overview(ctx) -> str:
    """Chart numbers behind the topic overviews (approach labels, code signals, process and time features)."""
    out = ["# Packet: overview figures (approach labels approach-1; features v12)\n",
           "Approach labels cover reviewed trials only (review sampling: per cell one failure + one success, so shares are "
           "not population rates). Code signals and process features cover every valid trial with a trajectory.\n"]
    sec = lambda title, frag: out.append(f"\n## {title}\n{text(frag)}\n")
    for by in ("mode", "category"):
        sec(f"loop (who decides each action) by {by}", FG.fig_loop(ctx, by=by))
    for m in ("privileged", "standard", "standard-realtime"):
        sec(f"loop by agent, {m}", FG.fig_loop(ctx, by="agent", mode=m, min=3))
        sec(f"loop by outcome, {m}", FG.fig_loop(ctx, by="outcome", mode=m, min=3))
        sec(f"techniques in code by agent, {m}", FG.fig_tech(ctx, by="agent", mode=m))
        sec(f"techniques (labels) by agent, {m}", FG.fig_tech(ctx, by="agent", src="ann", mode=m))
        sec(f"perception (labels) by agent, {m}", FG.fig_perception(ctx, by="agent", mode=m))
        sec(f"tool-call mix by agent, {m}", FG.fig_tools(ctx, by="agent", mode=m))
        sec(f"process medians by agent, {m}", FG.fig_calls(ctx, by="agent", mode=m))
        sec(f"where trials end in the time limit, by agent, {m}", FG.fig_timeuse(ctx, by="agent", mode=m))
        sec(f"event times (median share of limit), by agent, {m}", FG.fig_lanes(ctx, by="agent", mode=m))
    sec("techniques in code by category", FG.fig_tech(ctx, by="category"))
    sec("techniques (labels) by mode", FG.fig_tech(ctx, by="mode", src="ann"))
    rows = Q.ann_rows(ctx)
    for f in ("deliverable", "offline_model"):
        c = Counter((r["mode"], r["outcome"], r[f]) for r in rows)
        out.append(f"\n## {f} by mode x outcome\n" + "\n".join(f"- {m} · {o} · {v}: {n}" for (m, o, v), n in sorted(c.items())))
    ex = defaultdict(list)
    for r in rows:
        ex[(r["mode"], r["loop"])].append(r)
    out.append("\n## examples per mode x loop (key · agent · bench · outcome · loop_note)")
    for (m, l), rs in sorted(ex.items()):
        out.append(f"\n### {m} · {l} ({len(rs)})")
        for r in rs[:8]:
            out.append(f"- `{r['key']}` · {r['agent']} · {r['bench']} · {r['outcome']} · {ctx.approach[r['key']].get('loop_note', '')[:140]}")
    return "\n".join(out)


def integrity(ctx) -> str:
    """Boundary-crossing signals over all finished trials, the integrity reviews, and approach-label events."""
    out = ["# Packet: integrity (features v12 int_* signals; reviews integrity-1; approach labels approach-1)\n",
           "Signals are regex hits on agent commands (attempts count, blocked or not). Rule = what the trial's instruction "
           "said about reading source / downloading (allow / forbid / nodownload / open / none). The monitor marks "
           "answer_packages, external_tool_calls and resource-limit violations as `rule` and excludes them from rates.\n"]
    out.append("\n## share of trials with each signal, by agent (all finished trials with a trajectory)\n" + text(FG.fig_integrity(ctx, by="agent")))
    out.append("\n## by mode\n" + text(FG.fig_integrity(ctx, by="mode")))
    sig = ["pip_upstream", "success_src", "decompile", "grep_answers", "web", "log"]
    rows = [t for t in ctx.all if t.get("has_traj") == "1"]
    has = lambda t, k: t.get(f"int_{k}") not in (None, "", "0") or (k == "web" and t.get("web_calls") not in (None, "", "0"))
    c = Counter((k, t.get("rule_source", "")) for t in rows for k in sig if has(t, k))
    out.append("\n## signal x instruction rule (trials)\n" + "\n".join(f"- {k} · {r}: {n}" for (k, r), n in sorted(c.items())))
    out.append("\n## success rate with vs without the signal, per agent (valid trials; same agent)")
    for k in sig:
        for a in Q.ORDER:
            mine = [t for t in ctx.trials if t["agent"] == a and t.get("has_traj") == "1"]
            w = [t for t in mine if has(t, k)]
            if len(w) >= 8:
                wo = [t for t in mine if not has(t, k)]
                out.append(f"- {k} · {a}: with {Q.rate(w)[0]}/{len(w)}, without {Q.rate(wo)[0]}/{len(wo)}")
    rule = [t for t in ctx.all if t["validity"] == "rule"]
    out.append("\n## monitor rule flags (excluded from rates)\n" + "\n".join(
        f"- {a} · {why}: {n} trials, {s} had success=1" for (a, why), n in Counter((t["agent"], t["validity_reason"]) for t in rule).most_common()
        for s in [sum(t["success"] == "1" for t in rule if t["agent"] == a and t["validity_reason"] == why)]))
    by_key = {t["key"]: t for t in ctx.all}
    out.append("\n## integrity reviews (one line per reviewed trial)")
    sev = Counter()
    for key, a in sorted(ctx.integrity.items(), key=lambda kv: (by_key.get(kv[0], {}).get("agent", ""), kv[0])):
        t = by_key.get(key)
        if not t:
            continue
        sev[(t["agent"], a.get("severity"))] += 1
        ev = "; ".join(f'{e.get("kind")}[{e.get("t", "")}] got={e.get("got")} allowed={e.get("allowed")} rule={e.get("rule")}: {str(e.get("what", ""))[:90]}' for e in (a.get("events") or [])[:4])
        out.append(f'- `{key}` · {t["agent"]} · {t["bench"]} · {t["mode"]} · success={t["success"]} · {t["validity"]} {t["validity_reason"]} · '
                   f'severity={a.get("severity")} intent={a.get("intent")} effect={a.get("effect")}\n  events: {ev}\n  note: {a.get("note", "")}')
    out.append("\n## severity per agent (reviewed sample)\n" + "\n".join(f"- {a} · {s}: {n}" for (a, s), n in sorted(sev.items())))
    out.append("\n## integrity events in the approach labels of the 657 ordinary reviews (secondary source)")
    for key, a in sorted(ctx.approach.items()):
        for e in a.get("integrity") or []:
            t = by_key.get(key, {})
            if e.get("kind") in ("exploit-predicate", "grep-answers", "install-upstream", "decompile", "web-search", "disable-log", "delete-log", "other"):
                out.append(f'- `{key}` · {t.get("agent")} · {t.get("bench")} · {t.get("mode")} · success={t.get("success")} · {e.get("kind")}: {str(e.get("detail", ""))[:140]}')
    return "\n".join(out)


def realtime(ctx, reviews) -> str:
    """Everything about standard-realtime: results, pairing with standard, endings, approach, realtime review fields."""
    rt = [t for t in ctx.trials if t["mode"] == "standard-realtime"]
    out = ["# Packet: realtime (standard-realtime mode)\n",
           f"{len(rt)} valid realtime trials; benches: {dict(Counter(t['bench'] for t in rt))}. Non-Luna agents ran only Luna-failed cells.\n"]
    rows = []
    for (b, a), v in sorted(Q.by(rt, "bench", "agent").items()):
        rows.append(f"- {b} · {a}: {Q.rate(v)[0]}/{len(v)}")
    out.append("\n## success per bench x agent (valid realtime trials)\n" + "\n".join(rows))
    idx = {(t["agent"], t["base"], t["mode"]): t for t in ctx.trials}
    pair = Counter()
    for t in rt:
        st = idx.get((t["agent"], t["base"], "standard"))
        if st:
            pair[(t["bench"], int(st["success"]), int(t["success"]))] += 1
    out.append("\n## same agent, same task base: (standard, realtime) outcome pairs per bench\n" + "\n".join(f"- {b} · std={s} rt={r}: {n}" for (b, s, r), n in sorted(pair.items())))
    out.append("\n## how realtime trials end, per agent\n" + text(FG.fig_endings(ctx, by="agent", mode="standard-realtime")))
    out.append("\n## loop by bench (realtime, labelled trials)\n" + text(FG.fig_loop(ctx, by="bench", mode="standard-realtime", min=2)))
    out.append("\n## loop by outcome (realtime)\n" + text(FG.fig_loop(ctx, by="outcome", mode="standard-realtime", min=2)))
    out.append("\n## process medians (realtime vs standard)\n" + text(FG.fig_calls(ctx, by="mode")))
    out.append("\n## reviews of realtime trials")
    for r in [r for r in Q.review_rows(ctx, sample=False) if r["mode"] == "standard-realtime"]:
        rv = reviews[(r["key"], r["depth"])]
        rtf = rv.get("realtime") or {}
        f = rv.get("failure") or {}
        out.append(f'- `{r["key"]}` · {r["agent"]} · {r["bench"]} · {r["outcome"]} · {r["primary"] or "-"} · {str(rv["headline"])[:160]}'
                   + (f'\n  realtime: control={rtf.get("control")} · idle={str(rtf.get("idle", ""))[:120]} · latency={str(rtf.get("latency", ""))[:120]} · episodes={str(rtf.get("episodes", ""))[:100]} · specific={str(rtf.get("realtime_specific", ""))[:140]}' if rtf else "")
                   + (f'\n  decisive: {str((f.get("decisive") or {}).get("what", ""))[:160]}' if f else ""))
    return "\n".join(out)


def improve(ctx) -> str:
    """Remedy labels (remedy-1) of failed trials: distributions and one line per failure."""
    rows = Q.rem_rows(ctx)
    out = ["# Packet: improvement directions (remedy-1 labels on failed reviewed trials)\n",
           f"{len(rows)} failed trials with a remedy label. Review sampling is per cell, so shares are not population rates.\n"]
    for by in ("agent", "mode", "category"):
        out.append(f"\n## main remedy family by {by}\n" + text(FG.fig_remedy(ctx, by=by)))
    out.append("\n## remedy codes (main or extra) by agent\n" + text(FG.fig_fixes(ctx, by="agent")))
    out.append("\n## remedy codes by mode\n" + text(FG.fig_fixes(ctx, by="mode")))
    c = Counter((r["fix"], r["would_pass"]) for r in rows)
    out.append("\n## main fix x would_pass\n" + "\n".join(f"- {f} · {w}: {n}" for (f, w), n in sorted(c.items())))
    out.append("\n## who\n" + "\n".join(f"- {w}: {n}" for w, n in Counter(r["who"] for r in rows).most_common()))
    out.append("\n## one line per failure (key · agent · bench · mode · fix [also] · would_pass · fix_note · general rule)")
    for r in sorted(rows, key=lambda r: (r["fix"], r["agent"])):
        a = ctx.remedy[r["key"]]
        out.append(f'- `{r["key"]}` · {r["agent"]} · {r["bench"]} · {r["mode"]} · {r["fix"]} {r["also"]} · {r["would_pass"]} · {a.get("fix_note", "")[:120]} · {a.get("general", "")[:100]}')
    return "\n".join(out)


def main() -> int:
    trials, cells, tasks = Q.load()
    reviews = current_reviews()
    ctx = Q.Context(trials, cells, tasks, reviews, Q.load_all())
    os.makedirs(os.path.join(WORK, "packets"), exist_ok=True)
    for name, fn in (("overview", overview), ("integrity", integrity), ("realtime", lambda c: realtime(c, reviews)), ("improve", improve)):
        if name not in sys.argv[1:]:
            continue
        p = os.path.join(WORK, "packets", name + ".md")
        open(p, "w").write(fn(ctx))
        print(p, os.path.getsize(p) // 1000, "KB")
        return 0
    if "entities" in sys.argv[1:]:
        p = os.path.join(WORK, "packets", "entities.md")
        open(p, "w").write(entities(ctx, reviews))
        print(p, os.path.getsize(p) // 1000, "KB")
        return 0
    for topic in sys.argv[1:] or [t["id"] for t in SITE["topics"]]:
        p = os.path.join(WORK, "packets", topic + ".md")
        open(p, "w").write(build(topic, ctx, reviews))
        print(p, os.path.getsize(p) // 1000, "KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
