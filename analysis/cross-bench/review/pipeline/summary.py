"""Tables from the checked recaps: one row per trial, the totals, and (when the cross-bench report's earlier labels
are on this machine: reviews/, annot/progress, progress2, remedy, reasoning) how often the recap agrees with them.
usage: python -m pipeline summary [--recaps verified_recaps] [--out FILE.md]"""
from __future__ import annotations
import argparse, json
from .paths import DATA, XB, CODES as CODES_PATH, sample, load
from .timing import NAMES as TIME

CODES = json.load(open(CODES_PATH))
OLD_GROUP = {"task-reading": "understand", "world-model": "understand", "strategy": "method", "planning": "plan",
             "diagnosis": "check", "self-check": "check", "persistence": "adapt", "giving-up": "adapt"}
GN = {g: v["name"] for g, v in CODES["decision_group"].items()}
nm = lambda t, c: (CODES[t].get(c) or {}).get("name", c or "—")
group_of_cause = lambda c: (CODES["cause"].get(c) or {}).get("group")
group_of_kind = lambda k: next((g for g, v in CODES["decision_group"].items() if k in v["kinds"]), "?")


def old_labels(key: str) -> dict:
    """The report's earlier labels of this trial (empty when they are not on this machine)."""
    a = f"{XB}/annot"
    rv, pg, p2, rm, rs = (load(f"{XB}/reviews/{key}.skim.json", {}), load(f"{a}/progress/{key}.json", {}), load(f"{a}/progress2/{key}.json", {}),
                          load(f"{a}/remedy/{key}.json", {}), load(f"{a}/reasoning/{key}.json", {}))
    nr, lv = p2.get("no_return"), pg.get("best_level")
    return {"primary": (rv.get("failure") or {}).get("primary"), "level": str(lv) if lv is not None else None,
            "no_return": nr.get("kind") if isinstance(nr, dict) else None, "fix": rm.get("fix"),
            "groups": sorted({OLD_GROUP.get(k, k) for k in rs.get("kinds", [])}) if rs else None}


def short(agent: str) -> str:
    w = agent.split()
    return w[-1] if not w[-1][0].isdigit() else w[0]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline summary")
    ap.add_argument("--recaps", default="verified_recaps")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rows, quotes, n_dec, dec = [], [0, 0], [0, 0], {"fail": {}, "succ": {}}
    agree = {k: [0, 0] for k in ("primary", "pgroup", "level", "no_return", "fix", "groups")}
    linked = [0, 0]
    for s in sample():
        k = s["key"]
        r = load(f"{DATA}/{a.recaps}/{k}.json")
        if r is None:
            continue
        fx, o = json.load(open(f"{DATA}/facts/{k}.json")), old_labels(k)
        quotes[0] += r["quotes"]["ok"]; quotes[1] += r["quotes"]["n"]
        prim = next((f for f in r["failures"] if f.get("primary")), None)
        ok_dec = [d for d in r["decisions"] if d["ok"]]
        groups = sorted({group_of_kind(d.get("kind")) for d in ok_dec})
        n_dec[0] += len(ok_dec); n_dec[1] += len(r["decisions"])
        side = "succ" if fx["success"] else "fail"
        for g in groups:
            dec[side][g] = dec[side].get(g, 0) + 1
        if not fx["success"] and prim:
            linked[1] += 1; linked[0] += any(d.get("failure") == prim["id"] for d in ok_dec)
        new = {"primary": prim and prim.get("cause"), "level": str(r["progress"].get("level")), "no_return": r["no_return"].get("type"),
               "fix": (r.get("fix") or {}).get("code"), "groups": groups}
        for f in ("primary", "level", "no_return", "fix"):
            if o.get(f) is not None and new[f] is not None:
                agree[f][1] += 1; agree[f][0] += o[f] == new[f]
        if o.get("primary") and new["primary"]:
            agree["pgroup"][1] += 1; agree["pgroup"][0] += group_of_cause(o["primary"]) == group_of_cause(new["primary"])
        if o.get("groups") is not None and not fx["success"]:
            agree["groups"][1] += 1; agree["groups"][0] += bool(set(o["groups"]) & set(groups)) or (not o["groups"] and not groups)
        bad = sum(not d["ok"] for d in r["decisions"])
        rows.append(f"| {short(s['agent'])} · {fx['task'].replace('-standard', '')[:34]} | {'成功' if fx['success'] else '失败'} | "
                    f"{nm('end', (r['end'] or {}).get('code'))} | {new['level']} | {len(r['failures'])}" + (f"（主因：{nm('cause', new['primary'])}）" if prim else "") +
                    f" | {nm('no_return', new['no_return']) if new['no_return'] not in (None, 'none') else '—'} | "
                    f"{'、'.join(GN.get(g, g) for g in groups) or '—'}" + (f"（另有 {bad} 条没通过）" if bad else "") +
                    f" | {'、'.join(TIME.get(t['code'], t['code']) for t in r['time']) or '—'} | {nm('fix', new['fix']) if new['fix'] else '—'} |")
    lines = ["| trial | 结果 | 结局 | 进展 | 失败（主因） | 不可挽回 | 背后的决定（核对通过） | 时间（脚本） | 补救 |", "|---|---|---|---|---|---|---|---|---|", *rows, "",
             f"- 引文核对：{quotes[0]}/{quotes[1]}；决策点通过「当时已知更早」检查：{n_dec[0]}/{n_dec[1]}；失败的主因连到一个决策点：{linked[0]}/{linked[1]}。",
             "- 失败里出现的高层错误：" + ("、".join(f"{GN.get(g, g)} {v}" for g, v in sorted(dec['fail'].items())) or "无") +
             "；成功里：" + ("、".join(f"{GN.get(g, g)} {v}" for g, v in sorted(dec['succ'].items())) or "无") + "。"]
    if any(n for _, n in agree.values()):
        lines += ["", "| 和报告原标签比 | 一致 |", "|---|---|"] + [
            f"| {lab} | {agree[f][0]}/{agree[f][1]} |" for f, lab in (("primary", "主因代码"), ("pgroup", "主因大类"), ("level", "进展级别"),
                                                                    ("no_return", "不可挽回点类型"), ("fix", "最该补的一步"), ("groups", "高层错误（至少一类相同，失败）"))]
    text = "\n".join(lines) + "\n"
    if a.out:
        open(a.out, "w").write(text)
    print(text)
