#!/usr/bin/env python3
"""One trial on one page, for whoever writes its analysis (<trial>/report/notes.md, see NOTES_GUIDE.md):
  python3 scripts/results/digest.py jobs/<job> [...]          # every trial in each job
  python3 scripts/results/digest.py jobs/<job>/<trial>

Writes <trial>/report/digest.md: the numbers (result, bar, all-zero score, time, cost), in limited mode every episode
as the verifier-side replay scored it, in full mode the agent's own NOTES.md and gen.py, collect.py's leak flags, then
everything the agent said and ran, in order, with times (and in limited mode the episode it belongs to). Measures the
trial first if it has no report/summary.json yet (as build.py does).
"""
from __future__ import annotations

import argparse
import json
import os

try:
    import tomllib
except ModuleNotFoundError:   # Python < 3.11
    import tomli as tomllib

import collect
from calls import kind_label, tool_kinds
from common import HB, REPO, pretty_output
from data import summary


def digest(trial: str) -> str:
    s = summary(trial, False)
    meta = tomllib.load(open(f"{REPO}/tasks/{s['task_name']}/task.toml", "rb"))["metadata"]
    f = json.load(open(f"{HB}/facts.json")).get(meta["family"], {})
    a0, r, rq = s["a0"], s["result"], s["requests"]
    cost = (s["billed"]["usd"] if s["billed"]["found"] else s["billed"]["harbor_usd"]) or 0
    at = lambda t: f"{(t - a0) / 60:5.2f}"
    num = lambda v: f"{v:.2f}" if isinstance(v, float) else v
    L = [f"# {meta['family']} · {s['mode']} mode · {s['model']} (effort {s['effort']})", "",
         (f"- result: {'PASS' if r['success'] else 'FAIL'} ({r['why']}); graded return {num(r['return'])} / bar {num(r['bar'])}; "
          f"the all-zero action scores {f.get('nop_return')} ({f.get('nop_steps')} steps); episode limit {f.get('max_steps')} steps"),
         (f"- agent time {(s['a1'] - a0) / 60:.1f} / {(s['budget_s'] or 0) / 60:.0f} min{' (stopped by the timeout)' if r.get('timed_out') else ''}; "
          f"cost ${cost:.4f}; {len(rq)} requests; {sum(x['in'] + x['out'] for x in rq):,} tokens; "
          f"{len(s['calls'])} tool calls; {len(s['views'])} images viewed")]
    if s["mode"] == "limited":
        eps = s["episodes"]
        top = next((e for e in eps if e["ep"] == r["best_ep"]), None)
        longest = max(eps, key=lambda e: e["steps"], default=None)
        L += [(f"- resets used {r['resets']} / {s['spec']['reset_budget']}; control steps sent {r['steps']}; graded episode "
               f"ep{r['graded_ep']}; highest return ep{r['best_ep']} ({num(r['best_return'])}"
               + (f", {top['steps']} steps" if top else "") + ")"
               + (f"; longest ep{longest['ep']} ({longest['steps']} steps, return {num(longest.get('return'))})" if longest else "")), "",
              "## Episodes (return and displacement from the verifier-side replay, which the agent never saw)", "",
              "| ep | start min | steps | ended | return | max_dx m | final_dx m | final_z m | images viewed |",
              "|---|---|---|---|---|---|---|---|---|"]
        L += [(f"| {e['ep']} | {at(e['t0'] or a0)} | {e['steps']} | {e['end'] or 'reset by the agent, or running'} | "
               f"{num(e.get('return'))} | {e.get('max_dx')} | {e.get('final_dx')} | {e.get('final_z')} | {e.get('views')} |")
              for e in s["episodes"]]
    else:
        d = collect.jload(f"{trial}/verifier/diagnostics.json", {})
        L.append(f"- submitted trajectory: {r['steps']} actions; verifier replays: returns {[num(x) for x in d.get('episode_return') or []]}, "
                 f"deterministic {r['grading'].get('deterministic')}")
        for name in ("NOTES.md", "gen.py"):
            p = f"{trial}/artifacts/app/output/{name}"
            if os.path.exists(p):
                txt = open(p, errors="replace").read()
                L += ["", f"## /app/output/{name} (the agent's own)", "", "```", txt[:9000] + ("\n...(truncated)" if len(txt) > 9000 else ""), "```"]
    flags = ([f"- {at(t)} min [{k}] matched `{w}`: {x[:200]}" for t, k, w, x in s["leaks"]]
             + [f"- {at(t)} min input tokens {a:,} -> {b:,}" for t, a, b in s["spikes"]])
    L += ["", "## Leak check flags (collect.py's grep: a flag asks for a look, it is not proof)", ""] + (flags or ["- none"])
    L += ["", "## The session, in order", ""]
    ep_of = lambda t: max([e["ep"] for e in s["episodes"] if (e["t0"] or a0) <= t] or [0])
    items = sorted([(t, "msg", txt) for t, txt in s["msgs"]] + [(c["t0"], "call", c) for c in s["calls"]], key=lambda z: z[0])
    for t, kind, x in items:   # a call belongs to the episode running when it returned (a reset inside it starts that one)
        tag = f"[{at(t)} min" + (f" · ep{ep_of(t if kind == 'msg' else x['t1'])}" if s["episodes"] else "") + "]"
        if kind == "msg":
            L.append(f"{tag} SAYS: {x}")
            continue
        rb = x.get("robot") or {}
        bg = rb.get("after") or {}
        robot = (f" · robot {rb.get('steps', 0)} steps, {rb.get('resets', 0)} resets" if rb.get("steps") or rb.get("resets") else "") + (
            f" · then in the background {bg.get('steps', 0)} steps, {bg.get('resets', 0)} resets" if bg.get("steps") or bg.get("resets") else "")
        cmd = "\n".join(x.get("cmds") or [x.get("label") or ""])
        L.append(f"{tag} CALL ({' + '.join(kind_label(k, s) for k in tool_kinds(x))}; {x['t1'] - x['t0']:.1f} s{robot}; "
                 f"exit {x.get('exit')}):\n    " + cmd[:1500].replace("\n", "\n    ") + ("\n    ...(command truncated)" if len(cmd) > 1500 else ""))
        out = pretty_output(x.get("out") or "").strip()
        if out:
            L.append("  OUTPUT: " + out[:600].replace("\n", "\n    "))
    L += ["", "## Files", f"- summary: {trial}/report/summary.json", f"- trajectory (ATIF): {trial}/agent/trajectory.json",
          f"- images the model viewed: {trial}/report/agent_views/",
          (f"- videos: {trial}/report/episodes/ (limited) or {trial}/verifier/replay.mp4 (full); stills: report/episodes/*.png "
           "or verifier/replay.last.png")]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="jobs/<job> or jobs/<job>/<trial>")
    for trial in collect.trials_under(ap.parse_args().paths):
        out = f"{trial}/report/digest.md"
        open(out, "w").write(digest(trial))
        print(os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
