"""Check each recap (recaps/K.json, prompt recap-1) against the full log and add what a script knows. Every quote is
looked up in the full event list (or, for id "task", in the task text); a decision keeps only the `known` quotes that
come before it, and is "not supported" when none is left. Nothing is dropped: an item that fails a check stays, with
`ok: false` and the reason, so the page can show every proposal. Adds the time codes and the resources at each
decision (timing.py). usage: python -m pipeline check [--dir recaps] [--keys K ...]  ->  verified_<dir>/K.json"""
from __future__ import annotations
import argparse, json, os
from .paths import DATA, keys, jdump
from .logs import norm, instruction
from . import timing


class Log:
    def __init__(self, key):
        self.ev = timing.events(key)
        self.pos = {e["id"]: i for i, e in enumerate(self.ev)}
        self.txt = {e["id"]: norm(e["text"]) + " ¶ " + norm(e["out"]) for e in self.ev}
        self.task = norm(instruction(key))
        self.n = self.ok = 0

    def quote(self, q):
        """q with ok, the event id it was found under, its time and its position (-1 = the task text)."""
        if not isinstance(q, dict):
            return None
        self.n += 1
        s = norm(q.get("quote", "")).strip(" .…\"'")
        hit = None
        if len(s) >= 8:
            if q.get("id") == "task" and s in self.task:
                hit = "task"
            elif s in self.txt.get(q.get("id"), ""):
                hit = q["id"]
            else:
                hit = next((i for i, t in self.txt.items() if s in t), "task" if s in self.task else None)
        self.ok += hit is not None
        e = self.ev[self.pos[hit]] if hit not in (None, "task") else None
        return {**q, "ok": hit is not None, "found": hit, "t": e["t"] if e else (0.0 if hit == "task" else None),
                "pos": self.pos.get(hit, -1) if hit else None}


def check(key: str, r: dict, fx: dict) -> dict:
    log = Log(key)
    budget_resets = timing.reset_budget(instruction(key))
    res = timing.resources(log.ev, fx, budget_resets)

    def need(x, *fields):
        """the item with its quotes checked; ok when the listed quotes were found."""
        x = dict(x)
        for f in ("ev", "decision", "consequence"):
            if f in x:
                x[f] = log.quote(x[f])
        bad = [f for f in fields if not (x.get(f) or {}).get("ok")]
        return {**x, "ok": not bad, "problems": [f"{f} 的原文在日志里找不到" for f in bad]}
    out = {k: r.get(k) for k in ("key", "prompt", "task_zh", "result_zh", "fix", "unclear")}
    out["end"] = need(r.get("end") or {}, "ev")
    out["progress"] = {"level": (r.get("progress") or {}).get("level"),
                       "steps": [need(s, "ev") for s in (r.get("progress") or {}).get("steps") or []]}
    out["failures"] = [need(f, "ev") for f in r.get("failures") or []]
    nr = r.get("no_return") or {"type": "none"}
    out["no_return"] = need(nr, "ev") if nr.get("type") not in (None, "none") else {**nr, "ok": True, "problems": []}
    out["decisions"] = []
    for d in r.get("decisions") or []:
        d = need(d, "decision")
        known = [log.quote(q) for q in d.get("known") or []]
        at = (d.get("decision") or {}).get("pos")
        before = [q for q in known if q["ok"] and at is not None and q["pos"] < at]
        late = [q for q in known if q["ok"] and at is not None and q["pos"] >= at]
        d["known"] = before + [{**q, "ok": False, "late": True} for q in late] + [q for q in known if not q["ok"]]
        if d["ok"] and not before:
            d["ok"], d["problems"] = False, d["problems"] + ["没有早于这个决定的证据（「已经知道」不成立）"]
        found = (d.get("decision") or {}).get("found")
        d["at"] = res.get(found) if found not in (None, "task") else None
        out["decisions"].append(d)
    out["claim"] = need(r.get("claim") or {}, "ev")
    st = dict(r.get("style") or {})
    st["evidence"] = [log.quote(q) for q in st.get("evidence") or []]
    out["style"] = st
    out["time"] = timing.codes(log.ev, fx, (r.get("end") or {}).get("code"), budget_resets)
    out["resets"] = {"budget": budget_resets, "used": sum(1 for e in log.ev if e["kind"] not in ("message", "thought") and timing.RESET.search(e["text"]))}
    out["quotes"] = {"n": log.n, "ok": log.ok}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline check")
    ap.add_argument("--dir", default="recaps")
    ap.add_argument("--keys", nargs="*")
    a = ap.parse_args(argv)
    tot = {"n": 0, "ok": 0}
    for key in keys(a.keys):
        p = f"{DATA}/{a.dir}/{key}.json"
        if not os.path.exists(p):
            continue
        v = check(key, json.load(open(p)), json.load(open(f"{DATA}/facts/{key}.json")))
        jdump(v, f"{DATA}/verified_{a.dir}/{key}.json")
        bad = [x["id"] for x in v["failures"] + v["decisions"] if not x["ok"]]
        tot["n"] += v["quotes"]["n"]; tot["ok"] += v["quotes"]["ok"]
        print(f"引文 {v['quotes']['ok']}/{v['quotes']['n']} 失败 {len(v['failures'])} 决定 {len(v['decisions'])} "
              f"未通过 {bad} 时间 {[t['code'] for t in v['time']]}  {key}")
    print("合计引文", tot)
