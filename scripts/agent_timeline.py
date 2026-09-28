#!/usr/bin/env python3
"""One timeline per Harbor trial: what the agent said, thought (reasoning summaries, if the run had
`--ak reasoning_summary=detailed`), ran and saw, merged by wall-clock time with what the robot service recorded
(limited mode: every /submit and /observe from episode.jsonl; unlimited: the tooling's session log).

usage: scripts/agent_timeline.py <trial_dir> [--out <dir>] [--max-chars 400]
writes <out>/timeline.md (readable) and <out>/timeline.jsonl (one event per line). Default out: <trial_dir>/analysis.
Account identifiers from Codex's session_meta are never copied.
"""
from __future__ import annotations
import argparse, datetime as dt, glob, json, os, sys


def _ts(x) -> float | None:
    if isinstance(x, (int, float)): return float(x)
    try: return dt.datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp()
    except Exception: return None


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s).split()); return s if len(s) <= n else s[: n - 1] + "…"


def codex_events(trial: str, n: int) -> list[dict]:
    ev = []
    files = sorted(glob.glob(os.path.join(trial, "agent/sessions/**/*.jsonl"), recursive=True))
    calls = {}
    for f in files:
        for line in open(f, errors="replace"):
            try: d = json.loads(line)
            except Exception: continue
            t = _ts(d.get("timestamp")); p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
            typ, ptyp = d.get("type"), p.get("type")
            if typ == "response_item" and ptyp == "message" and p.get("role") == "assistant":
                txt = " ".join(c.get("text", "") for c in p.get("content", []) if isinstance(c, dict))
                if txt.strip(): ev.append({"t": t, "src": "agent", "kind": "say", "text": _clip(txt, n)})
            elif typ == "response_item" and ptyp == "reasoning":
                summ = " ".join(s.get("text", "") for s in (p.get("summary") or []) if isinstance(s, dict))
                ev.append({"t": t, "src": "agent", "kind": "think", "text": _clip(summ, n) if summ.strip() else "", "hidden": not summ.strip()})
            elif typ == "response_item" and ptyp in ("custom_tool_call", "function_call"):
                inp = p.get("input") or p.get("arguments") or ""
                calls[p.get("call_id")] = t
                ev.append({"t": t, "src": "agent", "kind": "tool", "name": p.get("name"), "text": _clip(inp, n)})
            elif typ == "response_item" and ptyp in ("custom_tool_call_output", "function_call_output"):
                out = p.get("output"); img = 0; txt = ""
                if isinstance(out, list):
                    for c in out:
                        if not isinstance(c, dict): continue
                        if c.get("type") in ("input_image", "image"): img += 1
                        else: txt += c.get("text", "")
                else: txt = str(out or "")
                ev.append({"t": t, "src": "env", "kind": "result", "text": _clip(txt, n), "images": img,
                           "latency_s": round(t - calls[p.get("call_id")], 2) if t and calls.get(p.get("call_id")) else None})
            elif typ == "event_msg" and ptyp == "token_count":
                info = p.get("info") or {}; tot = (info.get("total_token_usage") or {})
                if tot: ev.append({"t": t, "src": "meta", "kind": "tokens", "input": tot.get("input_tokens"), "output": tot.get("output_tokens"),
                                   "reasoning": tot.get("reasoning_output_tokens")})
    return ev


def service_events(trial: str, n: int) -> list[dict]:
    ev = []
    for f in glob.glob(os.path.join(trial, "artifacts/data/episode.jsonl")):          # limited mode (sidecar)
        for line in open(f, errors="replace"):
            try: e = json.loads(line)
            except Exception: continue
            k = e.get("ev")
            if k == "submit":
                txt = f"submit {e.get('type')} x{e.get('rows')} dt={e.get('dt')} phys={e.get('physics_steps')} clipped={e.get('n_clipped')} success={e.get('success')}"
                plan = [p for p in (e.get("plan") or []) if "Fail" in json.dumps(p)]
                if plan: txt += f" plan_fail={len(plan)}"
                if e.get("note"): txt += f" note={_clip(e['note'], 80)}"
            elif k == "observe": txt = f"observe {e.get('seconds')} s cams={len(e.get('cameras') or [])}"
            else: txt = _clip(json.dumps({x: y for x, y in e.items() if x != 'ts'}), n)
            ev.append({"t": e.get("ts"), "src": "robot", "kind": k, "text": txt})
    for f in glob.glob(os.path.join(trial, "artifacts/app/output/rcb_session_log.jsonl")):  # unlimited (self-reported)
        for line in open(f, errors="replace"):
            try: e = json.loads(line)
            except Exception: continue
            ev.append({"t": e.get("ts"), "src": "sim(self-reported)", "kind": e.get("ev"), "text": _clip(json.dumps({x: y for x, y in e.items() if x not in ('ts', 'ev')}), n)})
    return ev


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("trial"); ap.add_argument("--out"); ap.add_argument("--max-chars", type=int, default=400)
    a = ap.parse_args(); trial = a.trial.rstrip("/"); out = a.out or os.path.join(trial, "analysis"); os.makedirs(out, exist_ok=True)
    ev = [e for e in codex_events(trial, a.max_chars) + service_events(trial, a.max_chars) if e.get("t")]
    ev.sort(key=lambda e: e["t"])
    if not ev: print("no events found", file=sys.stderr); return 1
    t0 = ev[0]["t"]
    for e in ev: e["t_rel_s"] = round(e["t"] - t0, 2)
    with open(os.path.join(out, "timeline.jsonl"), "w") as f:
        for e in ev: f.write(json.dumps(e, ensure_ascii=False) + "\n")
    task = ""; rw = {}
    try: task = json.load(open(os.path.join(trial, "result.json")))["task_name"].split("/")[-1]
    except Exception: pass
    try: rw = json.load(open(os.path.join(trial, "verifier/reward.json")))
    except Exception: pass
    k = lambda kind, src=None: [e for e in ev if e["kind"] == kind and (src is None or e["src"] == src)]
    th = k("think"); tok = k("tokens"); last_tok = tok[-1] if tok else {}
    L = [f"# Agent timeline — {task or os.path.basename(trial)}", "",
         f"trial `{os.path.basename(trial)}` · duration {ev[-1]['t_rel_s'] / 60:.1f} min · reward `{json.dumps(rw)[:300]}`", "",
         f"- messages: {len(k('say'))} · tool calls: {len(k('tool'))} · images returned to the model: {sum(e.get('images', 0) for e in k('result'))}",
         f"- reasoning items: {len(th)} ({sum(1 for e in th if not e.get('hidden'))} with a summary; the rest are encrypted — run with `--ak reasoning_summary=detailed` to get summaries)",
         f"- tokens (cumulative at the end): input {last_tok.get('input')}, output {last_tok.get('output')}, reasoning {last_tok.get('reasoning')}",
         f"- robot service events: {len([e for e in ev if e['src'].startswith(('robot', 'sim'))])}", "",
         "| t (mm:ss) | who | what | detail |", "|---|---|---|---|"]
    for e in ev:
        if e["kind"] == "tokens": continue
        if e["kind"] == "think" and e.get("hidden"): continue
        m, s = divmod(e["t_rel_s"], 60)
        det = e.get("text", "").replace("|", "\\|")
        if e["kind"] == "result":
            det = (f"[{e['images']} image(s)] " if e.get("images") else "") + det + (f" ({e['latency_s']} s)" if e.get("latency_s") is not None else "")
        L.append(f"| {int(m):02d}:{s:04.1f} | {e['src']} | {e['kind'] if e['kind'] != 'tool' else 'tool:' + str(e.get('name'))} | {det} |")
    open(os.path.join(out, "timeline.md"), "w").write("\n".join(L) + "\n")
    print(f"{out}/timeline.md: {len(ev)} events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
