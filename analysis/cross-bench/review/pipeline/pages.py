"""One review page per trial (pages/K.json) for the web app, from a checked recap (check.py): header facts, the
video and its map to the wall clock, the log grouped into turns, and the recap as cards in the report's order (end,
progress, failures, point of no return, decisions, time, fix, claim, style). Every proposal of the annotator becomes
a card; the ones that failed a check keep `ok: false` and the reason. The page JSON is the contract with the web app
(docs/data.md). usage: python -m pipeline pages [--recaps verified_recaps] [--keys K ...]"""
from __future__ import annotations
import argparse, json, os, re
from .paths import DATA, RAW, CODES as CODES_PATH, sample, load, jdump
from .logs import instruction
from .prep import out_digest
from .timing import SUBMIT, RESET, NAMES as TIME

CODES = json.load(open(CODES_PATH))
ERR = re.compile(r"Traceback \(most recent call last\)|^\w*(Error|Exception): |\[exit [1-9]", re.M)
TEXT_CAP = 4000
KIND = {"message": "消息", "thought": "推理", "shell": "命令", "write": "写文件", "read": "读文件", "image": "看图", "plan": "计划", "other": "工具"}
SRC = {"msg": "消息", "think": "推理", "action": "动作", "output": "输出"}
STYLE = {"plan": "先计划", "act": "先动手", "mixed": "交替", "tweak": "原路微调", "pivot": "换过方法", "none": "不验证",
         "light": "轻度验证", "thorough": "充分验证", "n/a": "不适用"}
NOTICED = {"yes": "agent 察觉了", "no": "agent 没察觉", "unclear": "看不出是否察觉"}


def name(table, code):
    return (CODES[table].get(code) or {}).get("name", code or "—")


def readable(e: dict) -> str:
    """A file write that the harness logged as JSON (Antigravity: {"TargetFile": ..., "CodeContent": ...}) shown as the file."""
    if e["kind"] == "write" and e["text"].lstrip().startswith("{"):
        try:
            d = json.loads(e["text"])
        except ValueError:
            return e["text"]
        body = d.get("CodeContent") or d.get("content") or d.get("new_string")
        if isinstance(body, str):
            return f"{d.get('TargetFile') or d.get('file_path') or ''}\n{body}".strip()
    return e["text"]


def turns(ev: list[dict], looks: dict, cited: dict) -> list[dict]:
    """One turn per model step (events with the same time); the title is its message, else its first command line."""
    out = []
    for e in ev:
        txt, kind = readable(e), e["kind"]
        tags = [t for t, rx in (("submit", SUBMIT), ("reset", RESET)) if kind not in ("message", "thought") and rx.search(txt)]
        if e["out"] and ERR.search(e["out"][-3000:]):
            tags.append("err")
        row = {"id": e["id"], "t": e["t"], "kind": kind, "label": KIND.get(kind, kind),
               "text": txt if kind in ("message", "thought") else txt[:TEXT_CAP], "cut": kind not in ("message", "thought") and len(txt) > TEXT_CAP,
               "out": out_digest(e["out"], 8, 8) if e["out"] else "", "out_len": len(e["out"]),
               "imgs": looks.get(e["id"], []), "tags": tags, "cited": sorted(cited.get(e["id"], []))}
        if out and out[-1]["t"] == e["t"]:
            out[-1]["events"].append(row)
        else:
            out.append({"n": len(out) + 1, "t": e["t"], "events": [row]})
    for tn in out:
        head = next((x for x in tn["events"] if x["kind"] == "message"), None) or next((x for x in tn["events"] if x["kind"] != "thought"), tn["events"][0])
        lines = [l for l in head["text"].splitlines() if l.strip()]
        tn["title"] = (lines[0].strip() if lines else head["label"])[:220]
    return out


def slot(x, label, t_of):
    """a quote slot for the page"""
    if not x:
        return None
    i = x.get("found") or x.get("id")
    return {"label": label, "id": i, "t": x.get("t") if x.get("t") is not None else t_of.get(i), "src": SRC.get(x.get("src"), x.get("src", "")),
            "text": x.get("quote", ""), "ok": bool(x.get("ok")), "late": bool(x.get("late"))}


def cards(r: dict, fx: dict, t_of: dict) -> list[dict]:
    out = []
    add = lambda **c: out.append({"ok": True, "problems": [], "slots": [], "facts": [], "note": "", **c})
    sl = lambda x, label: slot(x, label, t_of)
    keep = lambda xs: [x for x in xs if x]
    end = r["end"]
    add(id="end", section="end", kind="end", title=f"结局 · {name('end', end.get('code'))}", text=r.get("result_zh") or "",
        slots=keep([sl(end.get("ev"), "证据")]), ok=end.get("ok", True), problems=end.get("problems", []),
        facts=[f"用时 {fx.get('used_min')} / {fx.get('budget_min')} 分钟"])
    cl = r.get("claim") or {}
    add(id="claim", section="end", kind="end", title=f"自述 · {name('claim', cl.get('code'))}", text=(CODES["claim"].get(cl.get("code")) or {}).get("def", ""),
        slots=keep([sl(cl.get("ev"), "最终消息")]), ok=cl.get("ok", True), problems=cl.get("problems", []))
    pr = r["progress"]
    add(id="progress", section="progress", kind="progress", title=f"最高第 {pr.get('level')} 级 · {name('level', str(pr.get('level')))}", text="",
        ladder=[{"level": s.get("level"), "name": name("level", str(s.get("level"))), "what": s.get("what", ""), "ok": s.get("ok"),
                 "slot": sl(s.get("ev"), f"第 {s.get('level')} 级")} for s in pr["steps"]],
        ok=all(s.get("ok") for s in pr["steps"]), problems=[p for s in pr["steps"] for p in s.get("problems", [])])
    for f in r["failures"]:
        group = (CODES["cause"].get(f.get("cause")) or {}).get("group")
        add(id=f["id"], section="failure", kind="primary" if f.get("primary") else "failure",
            title=f"{'主因' if f.get('primary') else '失败'} · {name('cause', f.get('cause'))}", tag=CODES["cause_group"].get(group, ""),
            text=f.get("what", ""), slots=keep([sl(f.get("ev"), "出事"), sl(f.get("consequence"), "后果")]),
            facts=["后来挽回了" if f.get("recovered") else "没有挽回"], ok=f["ok"], problems=f["problems"])
    nr = r["no_return"]
    if nr.get("type") not in (None, "none"):
        t = (nr.get("ev") or {}).get("t")
        left = round(fx["budget_min"] - t, 1) if t is not None and fx.get("budget_min") else None
        add(id="no_return", section="no_return", kind="no_return", title=f"{name('no_return', nr.get('type'))} · 之后{name('nr_after', nr.get('after'))}",
            text=nr.get("note", ""), slots=keep([sl(nr.get("ev"), "不可挽回")]),
            facts=[f"之后还剩 {left} 分钟" if left is not None else "", NOTICED.get(nr.get("noticed"), "")], ok=nr["ok"], problems=nr["problems"])
    for d in r["decisions"]:
        kind = d.get("kind")
        group = next((g for g, v in CODES["decision_group"].items() if kind in v["kinds"]), "")
        at = d.get("at") or {}
        add(id=d["id"], section="decision", kind=group or "decision",
            title=f"{CODES['decision_group'].get(group, {}).get('name', '决定')} · {name('decision_kind', kind)}", text=d.get("what", ""),
            slots=keep([sl(d.get("decision"), "决定")] + [sl(k, "当时已知") for k in d.get("known") or []] + [sl(d.get("consequence"), "后果")]),
            facts=[f"当时还剩 {at['left_min']} 分钟" if at.get("left_min") is not None else "",
                   (f"reset 已用 {at['resets_used']}" + (f" / {at['resets_used'] + at['resets_left']}" if at.get("resets_left") is not None else "")) if at.get("resets_used") else "",
                   f"导致 {d['failure']}" if d.get("failure") else ""], ok=d["ok"], problems=d["problems"])
    for t in r.get("time") or []:
        add(id=f"time-{t['code']}", section="time", kind="time", title=f"{TIME.get(t['code'], t['code'])}（脚本）", text=t["note"],
            slots=[{"label": "事件", "id": i, "t": t_of.get(i), "src": "", "text": "", "ok": True, "late": False} for i in t["events"]])
    fix = r.get("fix")
    if fix:
        add(id="fix", section="fix", kind="fix", title=f"{name('fix', fix.get('code'))} · 翻盘{CODES['would_pass'].get(fix.get('would_pass'), '')}（推断）",
            text=fix.get("what", ""), note=fix.get("why", ""), facts=[f"由{CODES['who'].get(fix.get('who'), fix.get('who', ''))}改"])
    st = r.get("style") or {}
    add(id="style", section="style", kind="style", title="做事方式",
        text=" · ".join(f"{lab}：{STYLE.get(st.get(k), st.get(k) or '—')}" for k, lab in (("plan_vs_act", "开局"), ("on_failure", "受挫后"), ("verification", "验证"))),
        slots=keep([sl(x, "证据") for x in st.get("evidence") or []]))
    for c in out:
        c["facts"] = [f for f in c["facts"] if f]
    return out


def page(s: dict, r: dict) -> dict:
    k = s["key"]
    fx = json.load(open(f"{DATA}/facts/{k}.json"))
    ev = [json.loads(l) for l in open(f"{DATA}/events/{k}.jsonl")]
    cs = cards(r, fx, {e["id"]: e["t"] for e in ev})
    cited = {}
    for c in cs:
        for x in c["slots"] + [x["slot"] for x in c.get("ladder", []) if x.get("slot")]:
            if x and x.get("id"):
                cited.setdefault(x["id"], set()).add(c["kind"])
    return {"key": k, "agent": s["agent"], "bench": s["bench"], "task": fx["task"].replace("-standard", ""), "mode": fx["mode"],
            "success": fx["success"], "budget_min": fx["budget_min"], "used_min": fx["used_min"], "left_min": fx["left_min"],
            "end_reason": fx["external"]["end_reason"], "resets": r.get("resets"), "submits": fx["submits"],
            "task_zh": r.get("task_zh") or "", "result_zh": r.get("result_zh") or "", "task_text": instruction(k), "reward": fx["reward"],
            "replay": os.path.exists(f"{RAW}/{k}/verifier/replay.mp4"), "replay_map": load(f"{DATA}/videomap/{k}.json"),
            "full": load(f"{DATA}/fullvideo/{k}.json"), "level": r["progress"].get("level"),
            "cards": cs, "unclear": r.get("unclear") or [], "turns": turns(ev, load(f"{DATA}/looks/{k}/index.json", {}), cited), "n_events": len(ev)}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline pages")
    ap.add_argument("--recaps", default="verified_recaps")
    ap.add_argument("--keys", nargs="*")
    a = ap.parse_args(argv)
    for s in sample():
        r = load(f"{DATA}/{a.recaps}/{s['key']}.json")
        if r is None or (a.keys and s["key"] not in a.keys):
            continue
        p = page(s, r)
        jdump(p, f"{DATA}/pages/{s['key']}.json")
        print(f"回合 {len(p['turns']):4d} 卡片 {len(p['cards']):3d}（未通过 {sum(not c['ok'] for c in p['cards'])}）"
              f" 全程视频 {'有' if p['full'] else '无'}  {s['key']}")
