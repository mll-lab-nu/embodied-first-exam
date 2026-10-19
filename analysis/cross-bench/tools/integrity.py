#!/usr/bin/env python3
"""Integrity pass: sample trials with boundary-crossing signals and write focused excerpts for reviewers.

usage: tools/integrity.py sample [--seed 1]     # -> ledger rows (reason integrity:<signal>) + batches in $XB_WORK/integrity_batches
       tools/integrity.py excerpt KEY           # print one excerpt

Signals are the int_* features (features.py) plus the monitor's rule flags (answer_packages, external_tool_calls).
An excerpt holds the instruction's source/network rule, every matching command with its output and the agent's words
just before it; reviewers judge intent, permission and effect (prompt meta/prompts/integrity.md).
"""
from __future__ import annotations
import argparse, json, os, random, re, sys
from collections import defaultdict
import atif
import features as Fm
from common import HERE, RAW, read_csv

WORK = os.environ.get("XB_WORK", "/data/pingyue/cross-bench")
SIGNALS = ["pip_upstream", "success_src", "decompile", "grep_answers", "web", "log"]
RULE_TEXT = re.compile(r"[^.\n]*(source code|honou?r rule|network|download|install|solution)[^.\n]*[.\n]", re.I)


def excerpt(key: str) -> str:
    d = os.path.join(RAW, key)
    traj = json.load(open(os.path.join(d, "agent/trajectory.json")))
    ev, _ = atif.events(traj)
    ins = atif.instruction(traj)
    rules = " ".join(m.group(0).strip() for m in RULE_TEXT.finditer(ins))[:1500]
    out = [f"# {key}", f"rule sentences: {rules or '(none found)'}", ""]
    said = ""
    n = 0
    for e in ev:
        if e["kind"] in ("message", "thought"):
            said = e["text"][-500:]
            continue
        hit = [k for k, rx in Fm.INTEGRITY.items() if k != "getsource" and e["kind"] in Fm.INTEGRITY_KINDS[k] and rx.search(e["text"])]
        if Fm.LOG_TAMPER.search(e["text"]) and e["kind"] in ("shell", "write"):
            hit.append("log")
        if Fm.WEB.match(e["name"] or ""):
            hit.append("web-tool")
        if not hit:
            continue
        n += 1
        if n > 12:
            out.append("… (more matches omitted)")
            break
        t = f"{int(e['t'])}:{int(e['t'] % 1 * 60):02d}" if e["t"] is not None else "?"
        out += [f"## [{t}] {','.join(hit)} ({e['kind']})", f"agent before: {said.strip()}" if said else "",
                f"command: {e['text'][:1500]}", f"output: {e['out'][:1200]}", ""]
        said = ""
    last = next((e["text"][-600:] for e in reversed(ev) if e["kind"] == "message"), "")
    out.append(f"final message: {last}")
    return "\n".join(x for x in out if x is not None)


def sample(seed: int) -> None:
    rnd = random.Random(seed)
    trials = {t["key"]: t for t in read_csv("trials.csv")}
    feats = {f["key"]: f for f in read_csv("features.csv")}
    pick: dict[str, str] = {}

    def take(keys, reason, k=None):
        keys = [x for x in sorted(keys) if x not in pick and feats.get(x, {}).get("has_traj") == "1"]
        by_agent = defaultdict(list)
        for x in keys:
            by_agent[trials[x]["agent"]].append(x)
        chosen = keys if k is None else []
        if k is not None:                                  # round-robin over agents so no agent floods the sample
            pools = {a: rnd.sample(v, len(v)) for a, v in by_agent.items()}
            while len(chosen) < k and any(pools.values()):
                for a in sorted(pools):
                    if pools[a] and len(chosen) < k:
                        chosen.append(pools[a].pop())
        for x in chosen:
            pick[x] = reason

    flag = lambda key, s: feats.get(key, {}).get(f"int_{s}") not in (None, "", "0")
    take([k for k, t in trials.items() if "answer_packages" in t["validity_reason"] or "external_tool_calls" in t["validity_reason"]], "integrity:monitor-rule")
    take([k for k in feats if flag(k, "decompile")], "integrity:decompile")
    take([k for k in feats if flag(k, "pip_upstream")], "integrity:pip_upstream", 20)
    take([k for k in feats if flag(k, "success_src") and feats[k]["rule_source"] in ("forbid", "nodownload")], "integrity:success_src-forbidden", 20)
    take([k for k in feats if flag(k, "success_src") and feats[k]["rule_source"] not in ("forbid", "nodownload")], "integrity:success_src-other", 8)
    take([k for k in feats if flag(k, "grep_answers")], "integrity:grep_answers", 20)
    take([k for k in feats if (flag(k, "web") or feats[k].get("web_calls") not in ("", "0")) and feats[k]["rule_source"] != "open"], "integrity:web-closed", 12)
    take([k for k in feats if flag(k, "log")], "integrity:log", 10)
    os.makedirs(os.path.join(WORK, "integrity_batches"), exist_ok=True)
    now = __import__("time").strftime("%Y-%m-%d %H:%M")
    with open(os.path.join(HERE, "ledger.csv"), "a") as fh:            # columns: time,key,fingerprint,depth,reason,seed
        for k, why in pick.items():
            fh.write(f"{now},{k},{trials[k]['fingerprint']},integrity,{why},{seed}\n")
    keys = sorted(pick, key=lambda k: (trials[k]["agent"], k))
    for i in range(0, len(keys), 9):
        path = os.path.join(WORK, "integrity_batches", f"b{i // 9:02d}.md")
        with open(path, "w") as fh:
            for k in keys[i:i + 9]:
                t = trials[k]
                fh.write(f"\n\n=== key: {k}\nagent: {t['agent']} · bench: {t['bench']} · mode: {t['mode']} · success: {t['success']} · "
                         f"validity: {t['validity']} {t['validity_reason']} · sampled for: {pick[k]}\n{excerpt(k)}\n")
    print(f"{len(pick)} trials, {-(-len(keys) // 9)} batches in {WORK}/integrity_batches")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "excerpt"])
    ap.add_argument("key", nargs="?")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "excerpt":
        print(excerpt(a.key))
    else:
        sample(a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
