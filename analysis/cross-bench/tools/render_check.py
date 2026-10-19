#!/usr/bin/env python3
"""Print findings with every placeholder replaced by its value, as plain text (for review of claims vs numbers).

usage: [XB_SET=core|all] uv run --no-project --with markdown==3.7 --with pillow python tools/render_check.py 4.2 4.3 …
       (or a topic id, or note:agent/<slug> for an entity note; XB_SET picks the task set, default core)
Case marks print as [n:KEY]; figures print as their number table.
"""
from __future__ import annotations
import glob, os, re, sys
import build as B
import figs as FG
import packet
import queries as Q
from common import HERE
from review import current_reviews


def bars(spec: str, metrics: dict) -> str:
    """{{bars:…}} -> 〔全部 k/n · <row> k/n · …〕, the strip's rows as text."""
    rows = B.bar_rows(spec, metrics)[2]
    return "〔" + " · ".join(f"{label} {k}/{n}" for label, k, n, *_ in rows) + "〕" if rows else "〔MISSING BARS〕"


def main() -> int:
    trials, cells, tasks = Q.load()                       # the task set of XB_SET (default core; queries.SETS)
    ctx = Q.Context(trials, cells, tasks, current_reviews(), Q.load_all())
    metrics, figs = Q.metrics(ctx), B.figure_registry(ctx)      # the build's figures (figs_time, figs_way, figs_tools too)
    want = set(sys.argv[1:])
    for w in sorted(x for x in want if x.startswith(("note:", "file:"))):   # note:agent/gpt-6-astra, or file:<any .md path>
        want.discard(w)
        body = open(os.path.join(HERE, "notes", w[5:] + ".md") if w.startswith("note:") else w[5:]).read()
        body = B.BARS.sub(lambda m: bars(m.group(1), metrics), body)
        print(f"\n===== {w}")
        print(B.PLACEHOLDER.sub(lambda m: f"〔{metrics[m.group(2).split('|')[0].strip()](**dict(x.split('=', 1) for x in m.group(2).split('|')[1:] if '=' in x))}〕"
                                if m.group(1) == "q" else f"[{m.group(2)[:60]}]", body).strip())
    if not want and any(a.startswith(("note:", "file:")) for a in sys.argv[1:]):
        return 0
    for p in sorted(glob.glob(os.path.join(HERE, "findings", "[0-9]*.md")), key=lambda p: B.fnum(os.path.basename(p)[:-3])):
        meta, body = B.front(p)
        if want and meta.get("id") not in want and meta.get("topic") not in want:
            continue
        n = [0]

        def sub(m):
            kind, spec = m.group(1), m.group(2).strip()
            name, *params = [x.strip() for x in spec.split("|")]
            kv = dict(x.split("=", 1) for x in params if "=" in x)
            if kind == "q":
                return f"〔{metrics[name](**kv)}〕" if name in metrics else "〔MISSING〕"
            if kind == "fig":
                return "\n[figure " + name + "]\n" + packet.text(figs[name](**kv)) + "\n" if name in figs else "[MISSING FIG]"
            n[0] += 1
            return f"[{n[0]}:{name}]"
        print(f"\n===== {meta.get('id')} ({meta.get('topic')} · {meta.get('section')} · {meta.get('status')})\nTITLE: {meta.get('title')}")
        print(B.PLACEHOLDER.sub(sub, B.BARS.sub(lambda m: bars(m.group(1), metrics), body)).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
