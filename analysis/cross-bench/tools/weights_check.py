#!/usr/bin/env python3
"""Unweighted vs weighted review shares (XB_WEIGHTS) for every figure and review placeholder in the current findings.

usage: XB_DATA=… tools/weights_check.py [--top 20] [-q]     # -q: only the largest differences and the summary

Every share of sampled reviews goes through queries.tally; this tool records each tally call while a figure or a
{{q:…}} value is drawn twice (weights off, then on) and compares value by value: share = count / n of that call, in %.
Sources: findings/[0-9]*.md (not retired), findings/_summary.md, meta/site.json home charts.
"""
from __future__ import annotations
import argparse, glob, os, statistics as S
import build as B
import common
import queries as Q
from review import current_reviews

REVIEW_Q = {"rev", "ann", "fix", "grasp", "reason", "int"}      # placeholder kinds over sampled reviews / labels
LOG = []
_tally = Q.tally


def _rec(rows, values):
    c = _tally(rows, values)
    same = [str(rows[0][k]) for k in ("agent", "mode", "bench") if rows and len({r[k] for r in rows}) == 1]
    LOG.append((" · ".join(same) or "all rows", len(rows), c))
    return c


Q.tally = _rec


def specs() -> tuple[list, list]:
    """Distinct (kind, spec) placeholders: figures and review-based q values."""
    texts = [B.front(p)[1] for p in glob.glob(os.path.join(B.HERE, "findings", "[0-9]*.md")) if B.front(p)[0].get("status") != "retired"]
    texts.append(B.front(os.path.join(B.HERE, "findings", "_summary.md"))[1] if os.path.exists(os.path.join(B.HERE, "findings", "_summary.md")) else "")
    figs, qs = [], []
    for kind, spec in (m.groups() for t in texts for m in B.PLACEHOLDER.finditer(t)):
        spec = spec.strip()
        if kind == "fig" and spec not in figs:
            figs.append(spec)
        if kind == "q" and spec.split("|")[0].strip() in REVIEW_Q and spec not in qs:
            qs.append(spec)
    figs += [h["fig"] for h in B.SITE["home"] if h.get("fig") and h["fig"] not in figs]
    return figs, qs


def call(fn, spec: str, weighted: bool) -> tuple[str, list]:
    name, *params = [x.strip() for x in spec.split("|")]
    kv = {k: v for k, v in (p.split("=", 1) for p in params if "=" in p) if k != "say"}
    common.WEIGHTS = weighted
    del LOG[:]
    try:
        out = str(fn[name](**kv)) if name in fn else "missing"
    except Exception as e:                                       # report and go on (partial data)
        out = f"error: {e!r}"
    return out, list(LOG)


def compare(spec: str, fn: dict) -> tuple[str, str, list]:
    """-> (unweighted text, weighted text, [(group, value, n, unweighted %, weighted %)])."""
    tu, lu = call(fn, spec, False)
    tw, lw = call(fn, spec, True)
    out = []
    for (grp, n, cu), (_, _, cw) in zip(lu, lw):
        if n:
            out += [(grp, v, n, 100 * cu[v] / n, 100 * cw[v] / n) for v in cu.keys() & cw.keys()]
    return tu, tw, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("-q", action="store_true", help="only the largest differences and the summary")
    a = ap.parse_args()
    trials, cells, tasks = Q.load()
    ctx = Q.Context(trials, cells, tasks, current_reviews(), Q.load_all())
    import figs as FG
    fig_fn, q_fn = {**Q.figures(ctx), **FG.figures(ctx)}, Q.metrics(ctx)
    rows = Q.review_rows(ctx, sample=False)
    n_in = sum(r["in_sample"] for r in rows)
    print(f"current reviews on valid trials: {len(rows)}; in the random sample {n_in}, out {len(rows) - n_in}; data {common.DATA}")
    figs, qs = specs()
    items = []                                                   # (|Δ|, where, unweighted, weighted, n)
    for spec in figs:
        _, _, sh = compare(spec, fig_fn)
        if not sh:
            continue                                             # not drawn from sampled reviews (trial-based chart)
        items += [(abs(w - u), f"fig:{spec} · {g} · {v}", u, w, n) for g, v, n, u, w in sh]
        if not a.q:
            g, v, n, u, w = max(sh, key=lambda x: abs(x[4] - x[3]))
            print(f"fig:{spec}: {len(sh)} shares, max |Δ| {abs(w - u):.1f} pt ({g} · {v}: {u:.1f}% -> {w:.1f}%, n={n})")
    nq = 0
    for spec in qs:
        tu, tw, sh = compare(spec, q_fn)
        for g, v, n, u, w in sh[:1]:                             # a review placeholder makes one tally call
            nq += 1
            items.append((abs(w - u), f"q:{spec}", u, w, n))
            if not a.q:
                print(f"q:{spec}: {tu} -> {tw} ({u:.1f}% -> {w:.1f}%, {w - u:+.1f} pt, n={n})")
    print(f"\nlargest differences (top {a.top}):")
    for d, where, u, w, n in sorted(items, key=lambda x: -x[0])[:a.top]:
        print(f"  {w - u:+6.1f} pt  {u:5.1f}% -> {w:5.1f}%  n={n:<4} {where}")
    big = [x for x in items if x[4] >= 20]
    fq = lambda xs: f"median {S.median(x[0] for x in xs):.1f} pt, max {max(x[0] for x in xs):.1f} pt" if xs else "none"
    print(f"\nsummary: {len(items)} shares ({nq} placeholders, {len(items) - nq} figure values): {fq(items)}; "
          f"with n >= 20 ({len(big)}): {fq(big)}; placeholders only: {fq([x for x in items if x[1].startswith('q:')])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
