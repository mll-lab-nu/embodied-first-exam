#!/usr/bin/env python3
"""Write per-task agent results into the task directory: tasks/<task>/results/<run id>/README.md (+ replay.mp4,
replay.last.png). One folder per agent+model; unlimited and limited twins each get their own.
usage: write_task_results.py <jobs_dir> <job_name> <agent-slug> "<agent label>" [--analysis <make_two_mode_report_zh.py>]"""
import json, pathlib, shutil, sys, re, glob, datetime as dt, ast
jobs, job, slug, label = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
root = pathlib.Path(__file__).resolve().parents[1]
analysis = {}
if "--analysis" in sys.argv:
    src = pathlib.Path(sys.argv[sys.argv.index("--analysis") + 1]).read_text()
    m = re.search(r"ANALYSIS = (\{.*?\n\})\n", src, re.S)
    if m: analysis = ast.literal_eval(m.group(1))
def span(x):
    try:
        a = dt.datetime.fromisoformat(x["started_at"].replace("Z", "+00:00")); b = dt.datetime.fromisoformat(x["finished_at"].replace("Z", "+00:00")); return round((b - a).total_seconds())
    except Exception: return None
def last_msgs(trial, k=3):
    try:
        d = json.load(open(glob.glob(str(trial / "agent/trajectory.json"))[0]))
        return [s["message"].strip().replace("\n", " ") for s in d.get("steps", []) if s.get("source") == "agent" and (s.get("message") or "").strip()][-k:]
    except Exception: return []
n = 0
for trial in sorted((jobs / job).glob("*__*")):
    if not (trial / "result.json").exists(): continue
    r = json.load(open(trial / "result.json")); task = r["task_name"].split("/")[-1]
    tdir = root / "tasks" / task
    if not tdir.is_dir(): continue
    rw = json.load(open(trial / "verifier/reward.json")) if (trial / "verifier/reward.json").exists() else {}
    ar = r.get("agent_result") or {}; limited = task.endswith("-limited"); fam = task.replace("robotwin_2_0_", "").replace("-limited", "")
    out = tdir / "results" / slug; out.mkdir(parents=True, exist_ok=True)
    for f in ("replay.mp4", "replay.last.png"):
        if (trial / "verifier" / f).exists(): shutil.copy(trial / "verifier" / f, out / f)
    ok = rw.get("success") == 1
    an = analysis.get(fam, {}).get("L" if limited else "U", "")
    lines = [f"# {label} — {task}\n",
             f"Run: Harbor job `{job}`, trial `{trial.name}`, {(r.get('started_at') or '')[:10]}. Mode: **{'limited (robot as a service)' if limited else 'unlimited'}**.\n",
             "| | |", "|---|---|",
             f"| result | {'**1 (success)**' if ok else '**0**' + (' — no trajectory handed in' if rw.get('missing_trajectory') else '')} |",
             f"| agent time | {span(r.get('agent_execution') or {})} s |",
             f"| actions / physics steps | {rw.get('steps') or rw.get('n_actions') or '—'} / {rw.get('sim_steps') or '—'} |",
             f"| tokens in / out | {ar.get('n_input_tokens')} / {ar.get('n_output_tokens')} |",
             f"| verifier | `{json.dumps({k: v for k, v in rw.items() if k not in ('agent_sessions','agent_records','agent_replays')})}` |",
             f"| verifier sandbox | {r.get('verifier_environment_mode')} |\n"]
    if not limited and rw.get("agent_resets") is not None:
        lines.append(f"Debugging footprint (self-reported by the agent's tooling log): {rw.get('agent_sessions')} sessions, {rw.get('agent_resets')} resets, {rw.get('agent_sim_steps')} physics steps.\n")
    if (out / "replay.mp4").exists():
        lines += ["## Replay (verifier's six-camera video)\n", f"![last frame](replay.last.png)\n", "[replay.mp4](replay.mp4) — top: world / observer / head; bottom: front / left wrist / right wrist.\n"]
    if an:
        lines += ["## Analysis\n", an + "\n"]
    msgs = last_msgs(trial)
    if msgs:
        lines += ["## Agent's last messages\n"] + [f"- {m[:600]}" for m in msgs] + [""]
    (out / "README.md").write_text("\n".join(lines)); n += 1
print(f"{job}: wrote {n} result folders for {slug}")
