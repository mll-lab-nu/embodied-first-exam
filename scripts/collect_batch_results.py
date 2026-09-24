#!/usr/bin/env python3
"""Collect a two-mode batch (unlimited + limited Harbor jobs) into a results folder: per task and mode the verifier's
replay.mp4 / replay.last.png / reward.json plus agent cost, and a summary.md table.
usage: collect_batch_results.py <jobs_dir> <unlimited_job> <limited_job> <out_dir> [<oracle_job_unlimited> <oracle_job_limited>]"""
import json, pathlib, shutil, sys, datetime as dt
jobs, ju, jl, out = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], pathlib.Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
def span(x):
    try:
        a=dt.datetime.fromisoformat(x["started_at"].replace("Z","+00:00")); b=dt.datetime.fromisoformat(x["finished_at"].replace("Z","+00:00")); return round((b-a).total_seconds())
    except Exception: return None
rows={}
for mode, job in (("unlimited", ju), ("limited", jl)):
    for trial in sorted((jobs/job).glob("robotwin_2_0_*")):
        if not trial.is_dir(): continue
        r=json.load(open(trial/"result.json")) if (trial/"result.json").exists() else {}
        name=(r.get("task_name") or trial.name.split("__")[0]).split("/")[-1].replace("robotwin_2_0_","").replace("-limited","")  # dir names are truncated
        rw=json.load(open(trial/"verifier/reward.json")) if (trial/"verifier/reward.json").exists() else {}
        ar=r.get("agent_result") or {}
        d=out/name/mode; d.mkdir(parents=True, exist_ok=True)
        for f in ("replay.mp4","replay.last.png","reward.json","episode.jsonl","trajectory.npz"):
            if (trial/"verifier"/f).exists(): shutil.copy(trial/"verifier"/f, d/f)
        for f in ("gen.py",):
            src=trial/"artifacts/app/output"/f
            if src.exists(): shutil.copy(src, d/f)
        info={"success": rw.get("success"), "agent_s": span(r.get("agent_execution") or {}), "verifier_s": span(r.get("verifier") or {}),
              "tokens_in": ar.get("n_input_tokens"), "tokens_out": ar.get("n_output_tokens"), "cost_usd_api_price": ar.get("cost_usd"),
              "n_actions": rw.get("n_actions"), "sim_steps": rw.get("sim_steps"), "steps": rw.get("steps"),
              "agent_resets": rw.get("agent_resets"), "agent_sim_steps": rw.get("agent_sim_steps"),
              "exception": ((r.get("exception_info") or {}).get("exception_type")), "trial": str(trial)}
        json.dump(info, open(d/"agent_summary.json","w"), indent=1)
        prev=rows.setdefault(name,{}).get(mode)
        if prev and (prev.get("started_at") or "") > (r.get("started_at") or ""):   # several trials of one task: keep the latest
            continue
        info["started_at"]=r.get("started_at"); rows[name][mode]=info
L=[f"# RoboTwin 2.0 × Codex (GPT-6 Luna, ChatGPT subscription) — unlimited vs limited\n", f"Collected {dt.date.today().isoformat()} from `{ju}` and `{jl}`. Videos and rewards per task under `<task>/<mode>/`.\n",
   "| task | unlimited | agent s | tokens in/out | actions | limited | agent s | tokens in/out | actions |","|---|---|---|---|---|---|---|---|---|"]
def cell(i):
    if not i: return "—","","",""
    s={1:"✅ 1",0:"❌ 0"}.get(i.get("success"), "⚠ err" if i.get("exception") else "?")
    return s, str(i.get("agent_s") or ""), f"{(i.get('tokens_in') or 0)/1000:.0f}k / {(i.get('tokens_out') or 0)/1000:.1f}k", str(i.get("n_actions") or i.get("steps") or "")
tot={"unlimited":[0,0],"limited":[0,0]}
for name in sorted(rows):
    u,l=rows[name].get("unlimited"),rows[name].get("limited")
    for m,i in (("unlimited",u),("limited",l)):
        if i: tot[m][1]+=1; tot[m][0]+=int(i.get("success")==1)
    cu,cl=cell(u),cell(l); L.append(f"| {name} | {cu[0]} | {cu[1]} | {cu[2]} | {cu[3]} | {cl[0]} | {cl[1]} | {cl[2]} | {cl[3]} |")
L.append(f"\n**Totals:** unlimited {tot['unlimited'][0]}/{tot['unlimited'][1]} · limited {tot['limited'][0]}/{tot['limited'][1]}\n")
(out/"summary.md").write_text("\n".join(L)); print("\n".join(L))
