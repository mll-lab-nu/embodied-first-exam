"""Script-measured time and budget facts of one trial: the report's time codes that need no model (no-clock,
late-deliverable, overlong-command, idle-wait, early-stop, timeout-no-deliverable, budget-exhausted) and the
resources left at any moment (minutes, resets). Thresholds are fixed here, before looking at results."""
from __future__ import annotations
import json, re
from .paths import DATA
from .logs import stamp as mmss

CLOCK = re.compile(r"(^|[\s;&|(`])date(\s|$|[;)|`'\"+])|clock__curr_time|curr_time\(|rcb-limits/usage\.json|/status\b|elapsed_s|time_left|remaining", re.I)
SUBMIT, RESET = re.compile(r"/submit\b|\.submit\("), re.compile(r"/reset\b|\.reset\(")
RESET_BUDGET = re.compile(r"(\d+)\s+resets?\b", re.I)
NAMES = {"no-clock": "从不看时钟", "late-deliverable": "很晚才第一次提交", "overlong-command": "命令比剩余时间长", "idle-wait": "长时间空等",
         "early-stop": "时间还多就收工", "timeout-no-deliverable": "超时还没有交付", "budget-exhausted": "reset 用完"}
LATE = 0.5          # first deliverable after half the budget
IDLE_MIN = 5.0      # 5 minutes or more spent only waiting (sleeping, polling a log or a background process)
WAIT = re.compile(r'轮询后台进程|"duration_ms"|^\$ (sleep|tail|ls)\b|^\$ cat \S+\.log\s*$|^sleep \d', re.M)
EARLY = 0.25        # ended by itself with a quarter of the budget left


def events(key: str) -> list[dict]:
    return [json.loads(l) for l in open(f"{DATA}/events/{key}.jsonl")]


def reset_budget(instruction: str) -> int | None:
    m = RESET_BUDGET.search(instruction)
    return int(m.group(1)) if m else None


def resources(ev: list[dict], fx: dict, budget_resets: int | None) -> dict:
    """event id -> {left_min, resets_used, resets_left} at the moment the event started."""
    out, used = {}, 0
    for e in ev:
        t = e["t"]
        out[e["id"]] = {"t": t, "left_min": round(fx["budget_min"] - t, 1) if fx.get("budget_min") and t is not None else None,
                        "resets_used": used, "resets_left": budget_resets - used if budget_resets is not None else None}
        if e["kind"] != "message" and e["kind"] != "thought" and RESET.search(e["text"]):
            used += 1
    return out


def codes(ev: list[dict], fx: dict, end_code: str | None, budget_resets: int | None) -> list[dict]:
    """The time codes that fire, each with its numbers and the events it rests on."""
    budget, used = fx.get("budget_min"), fx.get("used_min")
    out = []
    add = lambda code, note, ids=(): out.append({"code": code, "note": note, "events": list(ids)[:5]})
    clocks = [e for e in ev if e["kind"] not in ("message", "thought") and CLOCK.search(e["text"])]
    if not clocks:
        add("no-clock", "整个会话没有查看已用或剩余时间")
    first = fx.get("first_submit_min") if str(fx.get("mode", "")).startswith("standard") else fx.get("first_output_min")
    if budget and (first is None or first > LATE * budget):
        add("late-deliverable", f"第一次提交在 {first} 分钟（时限 {budget:.0f} 分钟）" if first is not None else "没有提交过")
    steps = [e for e in ev if e["t"] is not None and e["kind"] not in ("message", "thought")]
    run = []                                        # consecutive steps that only wait
    for a, b in zip(steps, steps[1:] + [None]):
        end = b["t"] if b else (used or a["t"])
        dur, left = end - a["t"], (budget - a["t"] if budget else None)
        if left is not None and dur >= 1 and dur >= 0.9 * left:
            add("overlong-command", f"{a['id']} 在剩 {left:.1f} 分钟时开始，跑了 {dur:.1f} 分钟", [a["id"]])
        waiting = bool(WAIT.search(a["text"][:300]))     # a long gap after any other step may be the model thinking: not counted
        run = run + [a] if waiting else []
        if run and (not waiting or b is None or not (WAIT.search(b["text"][:300]))):
            span = end - run[0]["t"]
            if span >= IDLE_MIN:
                add("idle-wait", f"{mmss(run[0]['t'])}–{mmss(end)} 只在等待（{len(run)} 步，{span:.1f} 分钟）", [run[0]["id"], run[-1]["id"]])
            run = []
    timed_out = "Timeout" in (fx["external"].get("exception") or "") or end_code == "time-out"
    if timed_out and first is None:
        add("timeout-no-deliverable", "到时限时还没有提交过")
    resets_used = sum(1 for e in ev if e["kind"] not in ("message", "thought") and RESET.search(e["text"]))
    if (budget_resets is not None and resets_used >= budget_resets) or end_code == "resets-used":
        add("budget-exhausted", f"reset 用了 {resets_used}" + (f" / {budget_resets}" if budget_resets is not None else ""))
    if not fx["success"] and end_code == "agent-stopped" and budget and fx.get("left_min") and fx["left_min"] >= EARLY * budget:
        add("early-stop", f"自己停下时还剩 {fx['left_min']:.1f} 分钟（时限 {budget:.0f} 分钟）")
    merged = {}
    for c in out:                                   # one row per code: the first case's note, the count, the events pooled
        m = merged.setdefault(c["code"], {**c, "n": 0, "events": []})
        m["n"] += 1
        m["events"] = (m["events"] + c["events"])[:5]
    for m in merged.values():
        if m["n"] > 1:
            m["note"] += f"（共 {m['n']} 次）"
    return list(merged.values())
