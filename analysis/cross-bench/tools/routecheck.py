#!/usr/bin/env python3
"""Open every route of the built page at phone and desktop width; report script errors and page-level horizontal scroll.

usage: uv run --no-project --with playwright==1.48.0 python tools/routecheck.py [~/Work/cross-bench-artifact/index.html]
"""
from __future__ import annotations
import json, os, re, sys
from playwright.sync_api import sync_playwright


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Work/cross-bench-artifact/index.html")
    s = open(path, encoding="utf-8").read()
    D = json.loads(re.search(r"const DATA = (\{.*?\});\n", s, re.S).group(1).replace("<\\/", "</"))
    routes = ["home", "issues", "cases", "method", "search"] + [f"topic-{t['id']}" for t in D["topics"]] + [f"bench-{b}" for b in D["benches"]] \
             + [f"agent-{a['id']}" for a in D["agents"]] + (["agent-compare"] if D.get("compare") else []) + [f"case-{c}" for c in D["cases"]] + (["samples"] if D.get("samples") else [])
    bad = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in (400, 1280):
            pg = b.new_page(viewport={"width": w, "height": 900})
            errs, wide = [], []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"file://{path}#home")
            pg.wait_for_timeout(500)
            for r in routes:
                pg.evaluate(f"location.hash = '#{r}'")
                pg.wait_for_timeout(150)
                if (sw := pg.evaluate("document.documentElement.scrollWidth")) > w + 1:
                    wide.append((r, sw))
            print(f"width {w}: {len(routes)} routes, {len(errs)} errors {errs[:3]}, {len(wide)} too wide {wide[:8]}")
            bad += len(errs) + len(wide)
            pg.close()
        b.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
