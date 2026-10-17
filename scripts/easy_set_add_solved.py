#!/usr/bin/env python3
"""Append "solved by <run>" entries to docs/easy_set.toml (owner 10-17, board 0155: a base the reference run solved in
ANY mode it ships goes to the easy set, out of the headline statistics).

    python3 scripts/easy_set_add_solved.py BASES.csv [--solved-by luna] [--date 2026-10-17] [--dry-run]

BASES.csv: a header `base,modes`, then one row per base, its solved modes joined by ';' (e.g.
`robodojo-x-i00,privileged;standard`); computed outside the repository (the pool's Luna verdicts). Bases already in the
easy set (any reason) are skipped, so the same file, refreshed, can be applied again as the run solves more. Each new
entry goes after the last entry of its benchmark's block (append-only per block), or at the end of the file for a
benchmark without one:

    [[task]]
    base = "<base>"
    benchmark = "<label>"
    reason = "solved"
    solved_by = "luna"
    note = "solved by luna (codex-gpt6_luna-xhigh): privileged, standard, as of <date>"

Then `python3 scripts/task_conventions.py easy-set --check`. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402


def entry(base: str, label: str, who: str, modes: list[str], date: str) -> str:
    return (f'\n[[task]]\nbase = "{base}"\nbenchmark = "{label}"\nreason = "solved"\nsolved_by = "{who}"\n'
            f'note = "solved by {who} ({tc.SOLVED_BY[who]}): {", ".join(modes)}, as of {date}"\n')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("csv", type=Path)
    ap.add_argument("--solved-by", default="luna", choices=sorted(tc.SOLVED_BY))
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--easy-set", type=Path, default=tc.EASY_SET_FILE)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    listed = tc.easy_set(a.easy_set)
    have = {tc.base_of(p) for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file()}
    order = list(tc.MODE_REGISTRY)
    new: dict[str, list[tuple[str, str]]] = {}        # label -> [(base, entry text)]
    skipped, bad = 0, []
    with a.csv.open(newline="") as f:
        for row in csv.DictReader(f):
            base = (row.get("base") or "").strip()
            modes = sorted({m.strip() for m in (row.get("modes") or "").split(";") if m.strip()},
                           key=lambda m: order.index(m) if m in order else len(order))
            if not base:
                continue
            if base in listed:
                skipped += 1
                continue
            label = tc.bench_of(Path(base))
            if base not in have or not label or not modes or any(m not in order for m in modes):
                bad.append(f"{base}: {'no task directory' if base not in have else 'no benchmark label' if not label else 'modes ' + repr(modes)}")
                continue
            listed[base] = {}
            new.setdefault(label, []).append((base, entry(base, label, a.solved_by, modes, a.date)))
    for b in bad:
        print(f"SKIP {b}", file=sys.stderr)
    text = a.easy_set.read_text(encoding="utf-8")
    text = text if text.endswith("\n") else text + "\n"
    last: dict[str, int] = {}                         # label -> the end of its block's last entry ([[task]] + key lines)
    for m in re.finditer(r"(?m)^\[\[task\]\][ \t]*\n(?:[^\s#\[][^\n]*\n)*", text):
        lab = re.search(r'(?m)^benchmark\s*=\s*"([^"]*)"', m.group(0))
        if lab:
            last[lab.group(1)] = m.end()
    for pos, chunk in sorted(((last.get(lab, len(text)), "".join(e for _, e in sorted(es))) for lab, es in new.items()),
                             reverse=True):
        text = text[:pos] + chunk + text[pos:]
    n = sum(len(es) for es in new.values())
    for lab in sorted(new):
        print(f"{lab}: +{len(new[lab])}")
    print(f"{n} entries added, {skipped} already listed, {len(bad)} skipped" + (" (dry run)" if a.dry_run else ""))
    if not a.dry_run and n:
        a.easy_set.write_text(text, encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
