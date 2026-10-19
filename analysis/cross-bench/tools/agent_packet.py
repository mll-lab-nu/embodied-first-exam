#!/usr/bin/env python3
"""Writer input for one agent page (notes-4): the page's charts as number tables, per topic section, plus this agent's
labelled examples (thinking errors, grasp failures, approach notes, remedies) and the findings that tag it.

usage: uv run --no-project --with markdown==3.7 --with pillow python tools/agent_packet.py "GPT-6 Astra"
"""
from __future__ import annotations
import glob, os, sys
import build as B
import packet
import queries as Q
from common import HERE
from review import current_reviews


def main() -> int:
    name = sys.argv[1]
    trials, cells, tasks = Q.load()
    ctx = Q.Context(trials, cells, tasks, current_reviews(), Q.load_all())
    prof = B.agent_profile(ctx, name)
    sec = {str(i + 1): t["name"] for i, t in enumerate(B.SITE["topics"])}
    print(f"# {name}\n")
    print("## 1 结果\n" + "  ".join(f"{m}: {Q.rate([t for t in ctx.open if t['agent'] == name and t['mode'] == m])}"
                                   for m in ("privileged", "standard", "standard-realtime")) + "\n")
    for n, blocks in prof.items():
        print(f"## {n} {sec[n]}")
        for b in blocks:
            print(f"### {b['title']}\n" + "".join(f"- {s}（例：{k}）\n" for s, k, _ in b["items"]) + packet.text(b["html"]) + "\n")
    mine = lambda rows: [r for r in rows if r["agent"] == name]
    print("## examples: thinking errors (reasoning-1; level · kinds · bench · mode · key · belief)")
    for r in sorted(mine(Q.reason_rows(ctx)), key=lambda r: (r["level"] != "high", r["mode"]))[:30]:
        a = ctx.reasoning[r["key"]]
        print(f"- {r['level']} · {','.join(r['kinds'])} · {r['bench']} · {r['mode']} · {r['key']} · {a.get('belief', '')}")
    print("\n## examples: grasp failures (subtype · key · why)")
    for r in mine(Q.grasp_rows(ctx, sample=False))[:12]:
        print(f"- {r['subtype']} · {r['key']} · {ctx.grasp[r['key']].get('why', '')}")
    print("\n## examples: how it drove the robot (loop · outcome · mode · key · loop_note)")
    for r in sorted(mine(Q.ann_rows(ctx, sample=False)), key=lambda r: (r["mode"], r["success"]))[:20]:
        print(f"- {r['loop']} · {'成功' if r['success'] == '1' else '失败'} · {r['mode']} · {r['key']} · {ctx.approach[r['key']].get('loop_note', '')}")
    print("\n## examples: smallest change that would flip a failure (fix · would_pass · key · fix_note)")
    for r in mine(Q.rem_rows(ctx))[:15]:
        print(f"- {r['fix']} · {r['would_pass']} · {r['key']} · {ctx.remedy[r['key']].get('fix_note', '')}")
    print("\n## findings that tag this agent")
    for p in sorted(glob.glob(os.path.join(HERE, "findings", "[0-9]*.md")), key=lambda p: B.fnum(os.path.basename(p)[:-3])):
        meta, _ = B.front(p)
        if f"agent:{name}" in meta.get("entities", ""):
            print(f"- §{meta['id']}: {meta['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
