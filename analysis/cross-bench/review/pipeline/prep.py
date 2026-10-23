"""Per trial: the full event list (events/K.jsonl), script facts and external-cause flags (facts/K.json), and the
evidence packet the annotator reads (packet/K.md). Messages and thoughts are never trimmed; commands and outputs are
trimmed in the packet only (the annotator searches the untrimmed events with search.py).
usage: python -m pipeline prep [--keys K ...]"""
from __future__ import annotations
import argparse, csv, json, os, re
from .paths import DATA, RAW, XB_DATA, keys, jdump
from .logs import load_events, instruction, stamp

KEY_LINE = re.compile(r"error|traceback|exception|fail|success|reward|score|distance|dist=|err=|reached|fell|fall|"
                      r"timeout|warning|done|ok\b|pass|submit|reset|grasp|contact", re.I)
TAG = {"message": "MSG", "thought": "THINK", "shell": "RUN", "write": "WRITE", "read": "READ", "image": "IMG",
       "plan": "PLAN", "other": "TOOL"}
LIMIT = 160_000          # packet size in characters; commands and outputs are trimmed harder until it fits


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def facts(key: str, ev: list[dict], feat: dict, trials: dict) -> dict:
    f, t = feat.get(key, {}), trials[key]
    p = f"{RAW}/{key}/verifier/reward.json"
    reward = json.load(open(p)) if os.path.exists(p) else {}
    budget, used = num(f.get("budget_min")) or num(t.get("timeout_min")), num(f.get("minutes")) or num(t.get("agent_min"))
    streak, best, prev = 1, 1, None
    for e in ev:
        if e["kind"] != "shell":
            continue
        c = re.sub(r"\s+", " ", e["text"])[:400]
        streak = streak + 1 if c == prev else 1
        best, prev = max(best, streak), c
    ext = {"exception": t.get("exception") or "", "end_reason": t.get("end_reason") or "",
           "provider_block": f.get("provider_block") not in ("", "0", None),
           "infra_error": bool(reward.get("infra_error")), "grader_error": bool(reward.get("grader_error"))}
    return {"key": key, "agent": t["agent"], "task": t["task"], "mode": t["mode"], "success": t["success"] == "1",
            "budget_min": budget, "used_min": used, "left_min": round(budget - used, 1) if budget and used else None,
            "first_output_min": num(f.get("first_output_min")), "first_submit_min": num(f.get("first_submit_min")),
            "clock_checks": num(f.get("clock_checks")), "resets": num(f.get("resets")), "submits": num(f.get("submits")),
            "images_seen": num(f.get("images_seen")), "max_same_command_streak": best,
            "external": ext, "external_any": any(v for k, v in ext.items() if k not in ("exception", "end_reason"))
            or ext["exception"] not in ("", "AgentTimeoutError"),
            "reward": {k: v for k, v in reward.items() if not isinstance(v, (list, dict))}}


def clip_lines(s, head, tail, width=300):
    lines = [l[:width] for l in s.splitlines()]
    if len(lines) <= head + tail:
        return "\n".join(lines)
    return "\n".join(lines[:head] + [f"… 省略 {len(lines) - head - tail} 行 …"] + lines[-tail:])


def out_digest(out, tail, keys_):
    """The key lines (errors, scores, success ...) and the last lines of an output."""
    lines = [l[:300] for l in out.splitlines() if l.strip()]
    if len("\n".join(lines)) <= 800:
        return "\n".join(lines)
    keep = [l for l in lines[:-tail] if KEY_LINE.search(l)][-keys_:]
    return "\n".join(keep + ([f"… 省略 {len(lines) - tail - len(keep)} 行 …"] if len(lines) > tail + len(keep) else []) + lines[-tail:])


def render(ev, cmd=(10, 4), out=(8, 8)):
    rows, prev, n = [], None, 0
    for e in ev:
        tag = TAG.get(e["kind"], "TOOL")
        head = f"[{stamp(e['t'])}] {e['id']} {tag}"
        if e["kind"] in ("message", "thought"):
            rows.append(f"{head} {e['text']}")
            prev = None
            continue
        text = e["text"]
        if e["kind"] == "write":
            body = clip_lines(text, 8, 0)
        elif e["kind"] == "image":
            body = "看图 " + " ".join(re.findall(r"[\w./-]+\.(?:png|jpe?g)", text)[:3])
        else:
            body = clip_lines(text, *cmd)
        sig = re.sub(r"\s+", " ", text)[:400]
        if sig == prev and rows:                      # the same command again: count it instead of repeating it
            n += 1
            rows[-1] = re.sub(r" ×\d+$", "", rows[-1].split("\n")[0]) + f" ×{n + 1}" + ("\n" + "\n".join(rows[-1].split("\n")[1:]) if "\n" in rows[-1] else "")
            continue
        prev, n = sig, 0
        o = out_digest(e["out"], *out) if e["out"] else ""
        rows.append(f"{head} {body}" + ("\n    → " + o.replace("\n", "\n      ") if o else ""))
    return "\n".join(rows)


def packet(key, ev, fx):
    hdr = (f"# {fx['task']} · {fx['agent']} · {fx['mode']} · {'成功' if fx['success'] else '失败'}\n\n"
           f"## 任务说明（全文）\n{instruction(key)}\n\n## 评分结果\n{json.dumps(fx['reward'], ensure_ascii=False)[:2500]}\n\n"
           f"## 脚本算出的事实\n- 时限 {fx['budget_min']} 分钟，用了 {fx['used_min']} 分钟，剩 {fx['left_min']} 分钟；结束原因 {fx['external']['end_reason'] or '—'}\n"
           f"- 首次存交付物 {fx['first_output_min']} 分钟；首次 submit {fx['first_submit_min']} 分钟\n"
           f"- 看时钟 {fx['clock_checks']} 次；reset {fx['resets']} 次；submit {fx['submits']} 次；看图 {fx['images_seen']} 次\n"
           f"- 外部原因标记：{json.dumps(fx['external'], ensure_ascii=False)}\n\n")
    for cmd, out in (((10, 4), (8, 8)), ((6, 2), (4, 4)), ((3, 1), (2, 2))):
        body = render(ev, cmd, out)
        if len(hdr) + len(body) <= LIMIT:
            break
    note = (f"## 事件（共 {len(ev)} 条；命令和输出已压缩，消息 MSG 和推理 THINK 是全文；"
            f"要查完整内容用 search.py）\n")
    return hdr + note + body + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline prep")
    ap.add_argument("--keys", nargs="*")
    a = ap.parse_args(argv)
    feat = {r["key"]: r for r in csv.DictReader(open(f"{XB_DATA}/features.csv"))}
    trials = {r["key"]: r for r in csv.DictReader(open(f"{XB_DATA}/trials.csv"))}
    for k in keys(a.keys):
        ev = load_events(k)
        os.makedirs(f"{DATA}/events", exist_ok=True)
        with open(f"{DATA}/events/{k}.jsonl", "w") as fh:
            for e in ev:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        fx = facts(k, ev, feat, trials)
        jdump(fx, f"{DATA}/facts/{k}.json")
        p = packet(k, ev, fx)
        os.makedirs(f"{DATA}/packet", exist_ok=True)
        open(f"{DATA}/packet/{k}.md", "w").write(p)
        print(f"{fx['agent']:15s} {'成功' if fx['success'] else '失败'} 事件 {len(ev):4d} 证据包 {len(p) // 1000:4d} k字 外部 {fx['external_any']}  {k}")
