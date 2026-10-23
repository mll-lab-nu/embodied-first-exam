"""Choose the trials to review and write DATA/sample.json. Per agent: n failures and m successes drawn with a fixed
seed from valid trials of one mode (optionally the core set) whose log is in the trial cache; extra keys can be added
by hand. Without --force an existing sample.json is kept.
usage: python -m pipeline sample --agents "GPT-6 Astra" "Opus 5.5" [--mode standard] [--core] [--fail 20] [--succ 10]
                                 [--seed 20261020] [--add KEY ...] [--force]"""
from __future__ import annotations
import argparse, csv, os, random, re
from .paths import DATA, RAW, XB, XB_DATA, jdump


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline sample")
    ap.add_argument("--agents", nargs="+", required=True)
    ap.add_argument("--mode", default="standard")
    ap.add_argument("--core", action="store_true", help="only tasks in tools/data/core_set.toml")
    ap.add_argument("--fail", type=int, default=20)
    ap.add_argument("--succ", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20261020)
    ap.add_argument("--add", nargs="*", default=[], help="extra trial keys to include")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    out_path = f"{DATA}/sample.json"
    if os.path.exists(out_path) and not a.force:
        raise SystemExit(f"{out_path} exists; pass --force to replace it")
    trials = {r["key"]: r for r in csv.DictReader(open(f"{XB_DATA}/trials.csv"))}
    core = set(re.findall(r'task = "([^"]+)"', open(f"{XB}/tools/data/core_set.toml").read())) if a.core else None
    rnd, out = random.Random(a.seed), []
    ok = lambda r: (r["mode"] == a.mode and r["validity"] == "valid" and (core is None or r["base"] in core)
                    and os.path.exists(f"{RAW}/{r['key']}/agent/trajectory.json"))
    for agent in a.agents:
        for outcome, n, flag in (("failure", a.fail, "0"), ("success", a.succ, "1")):
            pool = sorted(k for k, r in trials.items() if r["agent"] == agent and r["success"] == flag and ok(r))
            for k in rnd.sample(pool, min(n, len(pool))):
                out.append({"key": k, "agent": agent, "outcome": outcome, "why": f"random seed {a.seed}"})
            print(f"{agent} {outcome}: {min(n, len(pool))} / {len(pool)}")
    for k in a.add:
        r = trials[k]
        out.append({"key": k, "agent": r["agent"], "outcome": "success" if r["success"] == "1" else "failure", "why": "added"})
    for o in out:
        o["task"], o["bench"] = trials[o["key"]]["task"], trials[o["key"]]["bench"]
    jdump(out, out_path)
    print(f"{len(out)} 个 trial -> {out_path}")
