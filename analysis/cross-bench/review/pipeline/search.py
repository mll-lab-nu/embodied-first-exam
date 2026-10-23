"""Search one trial's FULL event list (the packet is trimmed). The annotator uses it for every "did not" statement.
usage: python -m pipeline search <key> <regex> [--kind shell,message,...] [--max 40]
Prints id, time, kind and up to 160 characters around each hit (in the command / message text or in the output)."""
from __future__ import annotations
import argparse, json, re
from .paths import DATA
from .logs import stamp


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline search")
    ap.add_argument("key"); ap.add_argument("pattern"); ap.add_argument("--kind", default=""); ap.add_argument("--max", type=int, default=40)
    a = ap.parse_args(argv)
    rx, kinds, n = re.compile(a.pattern, re.I), set(filter(None, a.kind.split(","))), 0
    for line in open(f"{DATA}/events/{a.key}.jsonl"):
        e = json.loads(line)
        if kinds and e["kind"] not in kinds:
            continue
        for field in ("text", "out"):
            m = rx.search(e[field])
            if m:
                s = e[field][max(0, m.start() - 80):m.end() + 80].replace("\n", " ⏎ ")
                print(f"{e['id']:>6} [{stamp(e['t'])}] {e['kind']:7s} {'输出' if field == 'out' else '内容'}: …{s}…")
                n += 1
                break
        if n >= a.max:
            print(f"(只显示前 {a.max} 条)")
            break
    print(f"共 {n} 条命中" if n < a.max else "")
