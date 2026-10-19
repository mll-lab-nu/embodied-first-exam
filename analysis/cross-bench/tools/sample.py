#!/usr/bin/env python3
"""Pick trials to review and append them to ledger.csv (one row per selection, with reason and seed).

usage: tools/sample.py coverage [--round 1]       # per cell (bench x agent x mode): 1 failure, skim; per bench x agent:
                                                  # 1 success, skim, and 1 trial (a failure if any), deep
       tools/sample.py targeted --round 2               # deep: mode flips, agent flips, near-misses (seeded)
       tools/sample.py add KEY... --depth deep --reason contrast|all-fail|near-miss|anomaly|hypothesis:<id>
       tools/sample.py queue [--depth skim|deep]  # selected trials that have no current review yet
       tools/sample.py c30 [--dry] [--apply]      # coverage to 30 % of done-valid cells (rule: meta/sample30.json);
                                                  # --dry (default) writes $XB_DATA/c30_plan.csv, --apply logs it
       tools/sample.py prn                        # $XB_DATA/prn.csv: the fixed random number u of every catalog cell

Selections are seeded by cell and round, so rerunning a round picks the same trials; trials that a rerun replaced
(fingerprint changed) are re-picked from the same cell.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os, random, sys, time
from collections import Counter, defaultdict
from common import AGENTS, HERE, RAW, read_csv, write_csv

LEDGER = os.path.join(HERE, "ledger.csv")
COLS = ["time", "key", "fingerprint", "depth", "reason", "seed"]


def ledger() -> list[dict]:
    return list(csv.DictReader(open(LEDGER))) if os.path.exists(LEDGER) else []


def append(rows: list[dict]) -> None:
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", newline="") as f:
        w = csv.DictWriter(f, COLS)
        if new:
            w.writeheader()
        w.writerows(rows)


def reviewable(trials: list[dict]) -> list[dict]:
    return [t for t in trials if t["validity"] == "valid" and os.path.exists(os.path.join(RAW, t["key"], "agent/trajectory.json"))]


def coverage(rnd: int, benches: set | None = None) -> list[dict]:
    trials = [t for t in reviewable(read_csv("trials.csv")) if not benches or t["bench"] in benches]
    taken = {(r["key"], r["depth"]) for r in ledger()}
    cell, pair = defaultdict(list), defaultdict(list)
    for t in trials:
        cell[(t["bench"], t["agent"], t["mode"])].append(t)
        pair[(t["bench"], t["agent"])].append(t)
    now, out = time.strftime("%Y-%m-%d %H:%M"), []

    def pick(pool, seed, depth, reason):
        rng = random.Random(seed)
        t = rng.choice(sorted(pool, key=lambda x: x["key"]))
        if (t["key"], depth) not in taken:
            out.append({"time": now, "key": t["key"], "fingerprint": t["fingerprint"], "depth": depth, "reason": reason, "seed": seed})
            taken.add((t["key"], depth))

    seed = lambda *parts: hashlib.sha1("|".join(map(str, (rnd,) + parts)).encode()).hexdigest()[:8]
    for k, rows in sorted(cell.items()):                     # every cell: one failure (failures carry the analysis)
        pool = [t for t in rows if t["success"] == "0"]
        if pool:
            pick(pool, seed(k, "0"), "skim", f"coverage-r{rnd}")
    for k, rows in sorted(pair.items()):                     # every bench x agent: one success (how it is solved) + one deep
        pool = [t for t in rows if t["success"] == "1"]
        if pool:
            pick(pool, seed(k, "1"), "skim", f"coverage-r{rnd}")
        pick([t for t in rows if t["success"] == "0"] or rows, seed(k, "deep"), "deep", f"coverage-r{rnd}")
    return out


def targeted(rnd: int) -> list[dict]:
    """Round 2+: deep reviews where a comparison is informative. Seeded; skips trials already deep-reviewed or selected."""
    trials = reviewable(read_csv("trials.csv"))
    feats = {f["key"]: f for f in read_csv("features.csv")}
    taken = {r["key"] for r in ledger() if r["depth"] == "deep"}
    idx = {(t["agent"], t["base"], t["mode"]): t for t in trials}
    now, out = time.strftime("%Y-%m-%d %H:%M"), []
    def add(pool, n, reason):
        pool = sorted((t for t in pool if t["key"] not in taken), key=lambda t: t["key"])
        for t in random.Random(f"{rnd}|{reason}").sample(pool, min(n, len(pool))):
            out.append({"time": now, "key": t["key"], "fingerprint": t["fingerprint"], "depth": "deep", "reason": reason, "seed": rnd})
            taken.add(t["key"])
    for agent in ("GPT-6 Astra", "Opus 5.5", "GPT-6 Luna", "GLM-5.3 Flash", "DeepSeek V4.1 Flash", "Gemini 3.8 Flash"):
        flips = [idx[(a, b, "standard")] for (a, b, m), t in idx.items()
                 if a == agent and m == "privileged" and t["success"] == "1" and idx.get((a, b, "standard"), {}).get("success") == "0"]
        add(flips, 3, f"contrast:mode:{agent}")
    for win, lose in (("GPT-6 Astra", "Opus 5.5"), ("Opus 5.5", "GPT-6 Astra")):
        pool = [idx[(lose, b, m)] for (a, b, m), t in idx.items()
                if a == win and m == "standard" and t["success"] == "1" and idx.get((lose, b, m), {}).get("success") == "0"]
        add(pool, 3, f"contrast:agent:{win}>{lose}")
    near = [t for t in trials if t["success"] == "0" and (lambda q: q is not None and q >= 0.7)(
        (lambda v: float(v) if v not in ("", None) else None)(feats.get(t["key"], {}).get("q_score")))]
    add(near, 6, "near-miss")
    return out


def queue(depth: str | None) -> list[str]:
    from review import current_reviews                      # reviews keyed by (key, depth) with a matching fingerprint
    done = current_reviews()
    fp = {t["key"]: t["fingerprint"] for t in read_csv("trials.csv")}
    return sorted({r["key"] for r in ledger()
                   if (depth is None or r["depth"] == depth) and r["key"] in fp and (r["key"], r["depth"]) not in done})


# ---------- coverage to 30 % (c30) ----------

C30 = json.load(open(os.path.join(HERE, "meta", "sample30.json")))
C30_REASONS = ("coverage-30", "coverage-30-topup")


def prn(task: str, run: str) -> float:
    return int(hashlib.sha1(f'{C30["seed"]}|{task}|{run}'.encode()).hexdigest()[:12], 16) / 16 ** 12


def write_prn(cells: list[dict]) -> None:
    write_csv("prn.csv", [{"task": c["task"], "run": c["run"], "agent": c["agent"], "bench": c["bench"], "mode": c["mode"],
                           "u": f'{prn(c["task"], c["run"]):.12f}'} for c in cells])


def c30_plan() -> list[dict]:
    """One row per selected done-valid cell (see meta/sample30.json), plus cells selected earlier that left the frame."""
    from review import current_reviews
    cells, trials = read_csv("cells.csv"), {t["key"]: t for t in read_csv("trials.csv")}
    write_prn(cells)
    cell_of = {r["key"]: (r["task"], r["run"]) for r in read_csv("superseded.csv")} | {k: (t["task"], t["run"]) for k, t in trials.items()}
    led = ledger()
    depth = {k: d for k, d in sorted(current_reviews(), key=lambda kd: kd[1] == "deep")}   # deep wins over skim
    cov_r = {r["key"] for r in led if r["reason"].startswith("coverage-r")}
    logged = {r["key"] for r in led if r["reason"] in C30_REASONS}
    before = {}                                                  # cell -> reason of its earlier c30 selection
    for r in led:
        if r["reason"] in C30_REASONS and r["key"] in cell_of:
            before.setdefault(cell_of[r["key"]], r["reason"])
    rate = C30["rate"]
    strata = defaultdict(list)
    for c in cells:
        if c["status"] == "done-valid":
            c["u"], c["outcome"] = prn(c["task"], c["run"]), "success" if trials[c["trial"]]["success"] == "1" else "failure"
            strata[(c["agent"], c["bench"], c["mode"], c["outcome"])].append(c)
    out = []
    for s, cs in sorted(strata.items()):
        need = max(1, math.floor(rate * len(cs) + 0.5))
        why = {id(c): "u" if c["u"] < rate else "kept" for c in cs if c["u"] < rate or (c["task"], c["run"]) in before}
        rest = sorted((c for c in cs if id(c) not in why), key=lambda c: (c["trial"] not in cov_r, c["u"]))
        for c in rest[:max(0, need - len(why))]:
            why[id(c)] = "topup"
        for c in cs:
            if id(c) in why:
                out.append({"task": c["task"], "run": c["run"], "agent": c["agent"], "bench": c["bench"], "mode": c["mode"],
                            "outcome": c["outcome"], "stratum_n": len(cs), "stratum_need": need, "u": f'{c["u"]:.6f}',
                            "why": why[id(c)], "key": c["trial"], "fingerprint": trials[c["trial"]]["fingerprint"],
                            "reviewed": depth.get(c["trial"], ""), "coverage_r": int(c["trial"] in cov_r),
                            "logged": int(c["trial"] in logged),
                            "reason": "coverage-30-topup" if why[id(c)] == "topup" or before.get((c["task"], c["run"])) == C30_REASONS[1]
                            else "coverage-30"})
    inside = {(r["task"], r["run"]) for r in out}
    for cell, reason in sorted(before.items()):                 # selected once, not done-valid now: stays selected
        if cell not in inside:
            out.append({"task": cell[0], "run": cell[1], "agent": AGENTS.get(cell[1], cell[1]), "why": "kept-outside-frame", "reason": reason})
    return out


def c30(apply: bool) -> None:
    plan = c30_plan()
    write_csv("c30_plan.csv", plan)
    sel = [r for r in plan if r.get("key")]
    tot = Counter()
    for r in sel:
        tot["selected"] += 1
        tot["reused under threshold" if r["reviewed"] and r["why"] in ("u", "kept") else
            "reused as top-up" if r["reviewed"] else "new to review"] += 1
        tot["top-up (all)"] += r["why"] == "topup"
    tot["kept, outside the frame now"] = len(plan) - len(sel)
    print(f'frame: {len({(r["agent"], r["bench"], r["mode"], r["outcome"]) for r in sel})} strata with a selection; '
          + "; ".join(f"{k}: {v}" for k, v in tot.items()))
    modes = sorted({r["mode"] for r in sel})
    tab = Counter((r["agent"], r["mode"], bool(r["reviewed"])) for r in sel)
    print("\nselected (new to review) by agent x mode")
    print(f'{"agent":22}' + "".join(f"{m:>26}" for m in modes))
    for a in [a for a in AGENTS.values() if any(r["agent"] == a for r in sel)]:
        print(f"{a:22}" + "".join(f'{f"{tab[(a, m, True)] + tab[(a, m, False)]} ({tab[(a, m, False)]})":>26}' for m in modes))
    if apply:
        now = time.strftime("%Y-%m-%d %H:%M")
        rows = [{"time": now, "key": r["key"], "fingerprint": r["fingerprint"], "depth": r["reviewed"] or "skim",
                 "reason": r["reason"], "seed": C30["seed"]} for r in sel if not r["logged"]]
        append(rows)
        print(len(rows), "rows appended to", LEDGER)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["coverage", "targeted", "add", "queue", "c30", "prn"])
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--depth", choices=["skim", "deep"])
    ap.add_argument("--reason", default="")
    ap.add_argument("--bench", nargs="*", help="coverage: only these benchmarks (e.g. those fully fetched)")
    ap.add_argument("--dry", action="store_true", help="c30: plan only (the default)")
    ap.add_argument("--apply", action="store_true", help="c30: append the plan to ledger.csv")
    a = ap.parse_args()
    if a.cmd == "coverage":
        rows = coverage(a.round, set(a.bench or []))
        append(rows)
        print(f'{len(rows)} selected: {sum(r["depth"] == "skim" for r in rows)} skim, {sum(r["depth"] == "deep" for r in rows)} deep')
    elif a.cmd == "targeted":
        rows = targeted(a.round)
        append(rows)
        from collections import Counter
        print(len(rows), "selected:", dict(Counter(r["reason"].split(":")[0] + ":" + r["reason"].split(":")[1] if ":" in r["reason"] else r["reason"] for r in rows)))
    elif a.cmd == "c30":
        c30(a.apply and not a.dry)
    elif a.cmd == "prn":
        write_prn(read_csv("cells.csv"))
    elif a.cmd == "add":
        fp = {t["key"]: t["fingerprint"] for t in read_csv("trials.csv")}
        rows = [{"time": time.strftime("%Y-%m-%d %H:%M"), "key": k, "fingerprint": fp[k], "depth": a.depth or "deep",
                 "reason": a.reason, "seed": ""} for k in a.keys]
        append(rows)
        print(len(rows), "added")
    else:
        print("\n".join(queue(a.depth)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
