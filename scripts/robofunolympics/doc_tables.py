#!/usr/bin/env python3
"""Rewrite the generated tables of docs/benchmarks/robofunolympics.md (between the `<!-- families:begin -->` /
`<!-- evidence:begin -->` markers and their `:end` twins) from families.json, instances/, oracles/*/result.json and
nop.json. `--check` writes nothing and exits 1 when the document is stale. Python 3 only."""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
DOC = HERE.parents[1] / "docs/benchmarks/robofunolympics.md"
CATS = {"track-and-jumps": "Track and jumps", "football-and-volleyball": "Football and volleyball",
        "basketball-and-rackets": "Basketball and rackets", "throwing-catching-striking": "Throwing, catching, striking",
        "parkour-apparatus-balance": "Parkour, apparatus, balance"}


def tables() -> tuple[str, str]:
    fams = json.loads((HERE / "families.json").read_text())["families"]
    nop = json.loads((HERE / "nop.json").read_text())
    fam_rows, rev_rows, n_full, cat_now = [], [], 0, None
    for i, (fam, spec) in enumerate(fams.items(), 1):
        inst = json.loads((HERE / "instances" / f"{fam}-i00.json").read_text())
        full = spec["oracle"] == "full"
        n_full += full
        if inst["category"] != cat_now:
            cat_now = inst["category"]
            fam_rows.append(f"| | **{CATS[cat_now]}** | | | | | |")
        if full:
            r = json.loads((HERE / "oracles" / fam / "result.json").read_text())
            orc = f"full: {r['time_s']:g} s of {r['time_limit_s']:g} s"
        else:
            orc = "none"
        rob = {"unitree_g1": "G1", "unitree_h1": "H1-2"}[inst.get("robot", "unitree_g1")]
        book = (inst.get("rulebook") or "—").split(": ")[0].replace("|", "/")      # the book; its articles are in the task
        if book.count("(") > book.count(")"):
            book = book[:book.rindex("(")].rstrip()
        fam_rows.append(f"| {i} | `{fam}` | {rob} | {inst['texts']['sentence']} | {book} | {' → '.join(inst['stages'])} | {orc} |")
        rev_rows.append(f"| `{fam}` | {spec['evidence'] if not full else 'the reference controller (Harbor oracle: 1 in both modes)'} "
                        f"| 0: `{nop[fam]['failed']}` at {nop[fam]['time_s']:g} s |")
    head = (f"## The 50 families\n\n{n_full} with a reference controller (`oracle = \"full\"`), {len(fams) - n_full} without "
            "(`oracle = \"none\"`, human review). Every family's rule book, its deviations and every number are in its "
            "task's instruction and README; the stages are the events its referee requires, in order.\n\n"
            "| # | family | robot | task | rule book | stages | oracle (success after) |\n|---|---|---|---|---|---|---|\n")
    review = ("### Per family: the positive example and the do-nothing agent\n\nThe human-review table of PROTOCOL §2.7. "
              "\"By injection\" means the referee test (`scripts/robofunolympics/tests/test_<family>.py`) sets the "
              "simulator's state by hand so that the sport's events really happen in physics; it shows that the referee "
              "says yes to the right thing, not that a controller exists. The do-nothing agent holds the starting "
              "command to the end of the episode (`nop.json`).\n\n| family | positive example and negative controls | "
              "do-nothing agent |\n|---|---|---|\n")
    return head + "\n".join(fam_rows), review + "\n".join(rev_rows)


def main() -> int:
    s = DOC.read_text()
    fam, rev = tables()
    for key, body in (("families", fam), ("evidence", rev)):
        a, b = f"<!-- {key}:begin -->", f"<!-- {key}:end -->"
        if a not in s:
            raise SystemExit(f"{DOC}: no {a} marker")
        s = re.sub(re.escape(a) + r".*?" + re.escape(b), lambda _: a + "\n" + body + "\n" + b, s, flags=re.S)
    if "--check" in sys.argv:
        ok = s == DOC.read_text()
        print("docs/benchmarks/robofunolympics.md tables:", "current" if ok else "STALE (run scripts/robofunolympics/doc_tables.py)")
        return 0 if ok else 1
    DOC.write_text(s)
    print("wrote", DOC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
