#!/usr/bin/env python3
"""Live board of batch evaluations: one web page with every trial under Harbor jobs directories and its state, refreshed
every few seconds while the batch runs. A runner-side tool (stdlib only); it only reads.

    scripts/live_board.py [--jobs jobs/agents] [--jobs jobs] [--port N] [--bind 127.0.0.1]
    # prints its address (default: the first free port from 8765); from a laptop: ssh -N -L 8765:127.0.0.1:<port> <host>,
    # then open http://localhost:8765

States: pending (in a batch's plan, not started; scripts/run_agent_batch.sh writes <jobs>/.plan/<batch>.json), setup
(environment and agent install), running (with the agent's time limit), verifying, then success / failed, or aborted
(the job ended without finishing the trial). Per trial: tokens (live from the usage gateway's totals.json when it runs,
else Harbor's count at the end), reward, exception, the replay / live videos, and the tail of the agent's output.

It serves the agent's output and the videos, which can hold the whole conversation: keep it on 127.0.0.1 (the default)
and reach it through an SSH tunnel; bind elsewhere only on a trusted network. There is no login: on a shared host every
local user can open it, and files of a running trial are served before the runner's secret scan has redacted them. On
127.0.0.1 it answers only requests addressed to localhost / 127.0.0.1 / [::1] (a web page cannot reach it through DNS
rebinding).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import threading
import time
import tomllib
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = pathlib.Path(__file__).resolve().parents[1]
SKIP = {"agent", "artifacts", "verifier", "gateway", "sessions", "_logs", "node_modules"}
MEDIA = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".md": "text/plain; charset=utf-8",
         ".json": "application/json", ".txt": "text/plain; charset=utf-8", ".log": "text/plain; charset=utf-8"}
ARGS: argparse.Namespace
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
LOOPBACK_BIND = True          # bound to a loopback address: answer only requests addressed to one (main sets it)
CACHE: dict = {"t": 0.0, "state": None}
LOCK = threading.Lock()


def jload(p: pathlib.Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.astimezone()).timestamp()      # job-level times are local, trial-level UTC


_TASKS: dict[str, dict] = {}


def task_info(task: str) -> dict:
    """Benchmark (the task name's prefix: robocasa-gr1-..., robotwin_2_0_..., kinder-...) and agent time limit."""
    if task not in _TASKS:
        try:
            t = tomllib.loads((REPO / "tasks" / task / "task.toml").read_text())
        except (OSError, ValueError):
            t = {}
        m = re.match(r"(robocasa-gr1|robocasa365|mujoco_playground|robotwin_2_0|[a-z0-9]+)", task)
        bench = m.group(1) if m else task
        _TASKS[task] = {"bench": bench, "timeout": (t.get("agent") or {}).get("timeout_sec")}
    return _TASKS[task]


def run_id(agent: dict) -> str:
    """<harness>-<model>-<effort> as scripts/run_agent_batch.sh derives it, except that an Azure deployment replica's
    suffix is dropped (gpt-6-luna-3 -> gpt6_luna; claude-fable-5-1 stays fable_5_1)."""
    f = lambda s: re.sub(r"^_+|_+$", "", re.sub(r"[^a-z0-9]+", "_", s.lower()))
    model = (agent.get("model_name") or "").split("/")[-1].lower()
    model = re.sub(r"^(gpt-\d+(?:\.\d+)?-[a-z]+)-\d+$", r"\1", model)
    model = re.sub(r"^gpt-(\d+)", r"gpt\1", re.sub(r"^claude-", "", model))
    effort = (agent.get("kwargs") or {}).get("reasoning_effort") or "default"
    return f"{f(agent.get('name') or '?')}-{f(model)}-{f(effort)}"


def walk(root: pathlib.Path, depth: int = 0):
    """Job directories (a config.json, no __ in the name) below root."""
    try:
        entries = [e for e in os.scandir(root) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return
    for e in entries:
        if e.name.startswith((".", "_")) or e.name in SKIP:    # _superseded/, _logs/: set aside, not shown
            continue
        p = pathlib.Path(e.path)
        if (p / "config.json").exists() and "__" not in e.name:
            yield p
        elif depth < 5:
            yield from walk(p, depth + 1)


def newest(paths: list[pathlib.Path]) -> float:
    m = 0.0
    for p in paths:
        try:
            m = max(m, p.stat().st_mtime)
        except OSError:
            pass
    return m


def trial_state(t: pathlib.Path, job: dict, ri: int, root: pathlib.Path, plan_run: str | None) -> dict:
    cfg = jload(t / "config.json")
    r = jload(t / "result.json")
    task = pathlib.Path((cfg.get("task") or {}).get("path") or t.name.split("__")[0]).name
    info = task_info(task)
    gw = jload(t / "gateway" / "totals.json")
    ae = r.get("agent_execution") or {}
    ver = r.get("verifier") or {}
    rewards = (r.get("verifier_result") or {}).get("rewards") or {}
    reward = rewards.get("reward")
    if reward is None and (t / "verifier" / "reward.txt").exists():
        try:
            reward = float((t / "verifier" / "reward.txt").read_text().strip())
        except ValueError:
            pass
    agent_dir = t / "agent"
    agent_files = list(agent_dir.glob("*.txt")) if agent_dir.is_dir() else []
    now = time.time()
    a0, a1 = ts(ae.get("started_at")), ts(ae.get("finished_at"))
    if r.get("finished_at"):
        state = "success" if reward is not None and reward >= 1 and not gw.get("over_token_budget") else "failed"
    elif job.get("finished_at"):
        state = "aborted"
    elif ver.get("started_at") or (a1 and not ver.get("finished_at")):
        state = "verifying"
    elif a0 or agent_files:
        state = "running"
    else:
        state = "setup"
    if a0 is None and agent_files and state == "running":
        a0 = min(p.stat().st_ctime for p in agent_files)
    ar = r.get("agent_result") or {}
    tok_in = gw.get("input") if gw else ar.get("n_input_tokens")
    tok_out = gw.get("output") if gw else ar.get("n_output_tokens")
    media = []
    for d in ("verifier", "artifacts/data"):
        for p in sorted((t / d).glob("*")) if (t / d).is_dir() else []:
            if p.suffix in (".mp4", ".png") and p.name not in {m.split("/")[-1] for m in media}:
                media.append(str(p.relative_to(root)))
    exc = (r.get("exception_info") or {}).get("exception_type") or ""
    return {
        "id": f"{ri}:{t.relative_to(root)}", "task": task, "bench": info["bench"],
        "mode": next((m for m in ("standard", "realtime") if task.endswith(f"-{m}")), "privileged"),
        "run": plan_run or run_id((cfg.get("agent") or {})), "job": job.get("job_name") or t.parent.name,
        "trial": t.name, "state": state, "reward": reward, "exception": exc,
        "agent_start": a0, "agent_end": a1 or (now if state == "running" else None), "timeout": info["timeout"],
        "tok_in": tok_in, "tok_out": tok_out, "requests": gw.get("requests"), "gateway": bool(gw),
        "over_budget": bool(gw.get("over_token_budget")),
        "updated": newest([t / "result.json", t / "trial.log", t / "gateway" / "totals.json", *agent_files]),
        "media": media, "summary": str((t.parent / "summary.md").relative_to(root)) if (t.parent / "summary.md").exists() else None,
    }


def collect() -> dict:
    trials, plans = [], []
    for ri, root in enumerate(ARGS.jobs):
        plan_of: dict[str, str] = {}
        for pf in sorted((root / ".plan").glob("*.json")) if (root / ".plan").is_dir() else []:
            p = jload(pf)
            for j in p.get("jobs") or []:
                plan_of[j["job"]] = p.get("run_id")
                plans.append((ri, p, j))
        for jd in walk(root):
            jc = jload(jd / "config.json")
            jr = jload(jd / "result.json")
            name = jc.get("job_name") or jd.name
            try:
                tds = sorted(jd.iterdir())
            except OSError:                        # the job directory moved away (archived) during the scan
                continue
            for t in tds:
                try:
                    if t.is_dir() and "__" in t.name and (t / "config.json").exists():
                        trials.append(trial_state(t, {"job_name": name, **jr}, ri, root,
                                                  plan_of.get(name) or plan_of.get(jd.name)))
                except OSError:                    # a file vanished mid-scan: the next refresh picks the trial up
                    continue
    started = {(t["job"], t["task"]) for t in trials}
    for ri, p, j in plans:
        if (j["job"], j["task"]) in started:
            continue
        info = task_info(j["task"])
        trials.append({"id": None, "task": j["task"], "bench": info["bench"], "mode": j.get("mode"),
                       "run": p.get("run_id"), "job": j["job"], "trial": None, "state": "pending",
                       "timeout": info["timeout"], "batch": p.get("batch")})
    return {"now": time.time(), "roots": [str(r) for r in ARGS.jobs], "trials": trials}


def state() -> dict:
    with LOCK:
        if CACHE["state"] is None or time.time() - CACHE["t"] > 3:
            CACHE["state"], CACHE["t"] = collect(), time.time()
        return CACHE["state"]


def resolve(tid: str) -> tuple[pathlib.Path, pathlib.Path] | None:
    ri, _, rel = tid.partition(":")
    try:
        root = ARGS.jobs[int(ri)]
    except (ValueError, IndexError):
        return None
    p = (root / rel).resolve()
    return (root, p) if p.is_relative_to(root.resolve()) and p.exists() else None


def tail(p: pathlib.Path, n: int = 80, maxb: int = 64_000) -> str:
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - maxb))
            return "\n".join(f.read().decode("utf-8", "replace").splitlines()[-n:])
    except OSError:
        return ""


def detail(tid: str) -> dict:
    rp = resolve(tid)
    if rp is None:
        return {"error": "no such trial"}
    _, t = rp
    r = jload(t / "result.json")
    out = sorted((t / "agent").glob("*.txt"), key=lambda p: p.stat().st_size, reverse=True) if (t / "agent").is_dir() else []
    exc = r.get("exception_info") or {}
    return {"reward": jload(t / "verifier" / "reward.json") or (r.get("verifier_result") or {}).get("rewards"),
            "gateway": jload(t / "gateway" / "totals.json"),
            "exception": ((exc.get("exception_type") or "") + ": " + (exc.get("exception_message") or "")[:2000]) if exc else "",
            "agent_log": out[0].name if out else None, "agent_tail": tail(out[0]) if out else "",
            "trial_log_tail": tail(t / "trial.log", 25)}


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Live Board</title><style>
:root{--bg:#f7f7f5;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#e3e2dd;--ok:#1f8a4c;--bad:#c2410c;--run:#2563eb;--ver:#7c3aed;--pend:#9ca3af;--warn:#b45309;--on:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141413;--fg:#ecebe6;--mut:#9b9a93;--card:#1e1e1c;--line:#33332f;--ok:#4ade80;--bad:#fb923c;--run:#60a5fa;--ver:#a78bfa;--pend:#6b7280;--warn:#fbbf24;--on:#111}}
:root[data-theme=dark]{--bg:#141413;--fg:#ecebe6;--mut:#9b9a93;--card:#1e1e1c;--line:#33332f;--ok:#4ade80;--bad:#fb923c;--run:#60a5fa;--ver:#a78bfa;--pend:#6b7280;--warn:#fbbf24;--on:#111}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:16px;display:flex;flex-wrap:wrap;gap:12px;align-items:baseline}h1{font-size:18px;margin:0}.mut{color:var(--mut)}
main{padding:0 16px 32px}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}.card h2{font-size:14px;margin:0 0 6px;font-family:ui-monospace,monospace}
.bar{display:flex;height:8px;border-radius:4px;overflow:hidden;background:var(--line);margin:8px 0}.bar span{display:block}
.legend{display:flex;flex-wrap:wrap;gap:10px;font-size:12px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}
.tools{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}select,input,button{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{font-size:12px;color:var(--mut);font-weight:600;position:sticky;top:0;background:var(--card)}
tr.row{cursor:pointer}tr.row:hover{background:color-mix(in srgb,var(--run) 6%,transparent)}td.num{text-align:right;font-variant-numeric:tabular-nums}
.st{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;color:var(--on)}
.st.success{background:var(--ok)}.st.failed{background:var(--bad)}.st.running{background:var(--run)}.st.verifying{background:var(--ver)}
.st.setup{background:var(--warn)}.st.pending{background:var(--pend)}.st.aborted{background:#6b7280}
.prog{width:90px;height:6px;background:var(--line);border-radius:3px;display:inline-block;vertical-align:middle;margin-right:6px}.prog i{display:block;height:100%;background:var(--run);border-radius:3px}
.mx td,.mx th{text-align:center}.mx td:first-child,.mx th:first-child{text-align:left}
#drawer{position:fixed;top:0;right:0;height:100%;width:min(720px,100%);background:var(--card);border-left:1px solid var(--line);transform:translateX(100%);visibility:hidden;transition:transform .2s,visibility .2s;overflow-y:auto;padding:16px;z-index:5}
#drawer.open{transform:none;visibility:visible;box-shadow:-8px 0 24px #0003}#drawer pre{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px;overflow-x:auto;font-size:12px;white-space:pre-wrap;word-break:break-word;max-height:420px}
video,img{max-width:100%;border-radius:6px;border:1px solid var(--line)}.close{float:right}
</style></head><body>
<header><h1>Live Board</h1><span class="mut" id="meta"></span></header>
<main><div class="cards" id="cards"></div>
<div class="tools"><select id="run"><option value="">all runs</option></select><select id="st"><option value="">all states</option></select>
<select id="mode"><option value="">all modes</option><option>privileged</option><option>standard</option><option>realtime</option></select>
<input id="q" placeholder="filter task / benchmark"><button id="view">matrix view</button></div>
<div class="wrap" id="table"></div></main>
<aside id="drawer"></aside>
<script>
const ORDER=["running","verifying","setup","pending","aborted","failed","success"],COL={success:"--ok",failed:"--bad",running:"--run",verifying:"--ver",setup:"--warn",pending:"--pend",aborted:"--mut"};
const LABEL={success:"✓ success",failed:"✗ failed",running:"running",verifying:"verifying",setup:"setup",pending:"pending",aborted:"aborted"};
let S=null,matrix=false,open=null;const $=id=>document.getElementById(id);
try{matrix=localStorage.getItem("lb.matrix")==="1"}catch(e){}
const fmtT=n=>n==null?"":n>=1e6?(n/1e6).toFixed(1)+"M":n>=1e3?(n/1e3).toFixed(0)+"k":String(n);
const fmtM=s=>s==null?"":s<3600?Math.floor(s/60)+"m":(s/3600).toFixed(1)+"h";
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const st=s=>`<span class="st ${s}">${LABEL[s]||s}</span>`;
function filt(){const r=$("run").value,s=$("st").value,m=$("mode").value,q=$("q").value.toLowerCase();
 return S.trials.filter(t=>(!r||t.run===r)&&(!s||t.state===s)&&(!m||t.mode===m)&&(!q||(t.task+" "+t.bench).toLowerCase().includes(q)))}
function cards(){const by={};for(const t of S.trials)(by[t.run]??={})[t.state]=((by[t.run]??{})[t.state]||0)+1;
 $("cards").innerHTML=Object.keys(by).sort().map(r=>{const c=by[r],n=Object.values(c).reduce((a,b)=>a+b,0),done=(c.success||0)+(c.failed||0)+(c.aborted||0);
 return `<div class="card"><h2>${esc(r)}</h2><div><b>${c.success||0}</b> / ${done} succeeded · ${done} / ${n} done</div>
 <div class="bar">${ORDER.slice().reverse().map(s=>c[s]?`<span style="width:${100*c[s]/n}%;background:var(${COL[s]})"></span>`:"").join("")}</div>
 <div class="legend">${ORDER.filter(s=>c[s]).map(s=>`<span><i class="dot" style="background:var(${COL[s]})"></i>${LABEL[s]} ${c[s]}</span>`).join("")}</div></div>`}).join("")||'<div class="mut">no trials yet</div>'}
function selects(){const runs=[...new Set(S.trials.map(t=>t.run))].sort(),r=$("run"),v=r.value;
 r.innerHTML='<option value="">all runs</option>'+runs.map(x=>`<option${x===v?" selected":""}>${esc(x)}</option>`).join("");
 const s=$("st"),sv=s.value;s.innerHTML='<option value="">all states</option>'+ORDER.map(x=>`<option value="${x}"${x===sv?" selected":""}>${LABEL[x]}</option>`).join("")}
function elapsed(t){if(t.agent_start==null)return"";const e=(t.agent_end??S.now)-t.agent_start;
 if(t.state==="running"&&t.timeout){const p=Math.min(100,100*e/t.timeout);return `<span class="prog"><i style="width:${p}%"></i></span>${fmtM(e)} / ${fmtM(t.timeout)}`}return fmtM(e)}
function table(){const rows=filt().sort((a,b)=>ORDER.indexOf(a.state)-ORDER.indexOf(b.state)||a.task.localeCompare(b.task)||a.run.localeCompare(b.run));
 $("view").textContent=matrix?"list view":"matrix view";
 if(matrix){const runs=[...new Set(rows.map(t=>t.run))].sort(),tasks=[...new Set(rows.map(t=>t.task))].sort(),cell={};
  for(const t of rows){const k=t.task+"|"+t.run,o=cell[k];if(!o||ORDER.indexOf(t.state)<ORDER.indexOf(o.state))cell[k]=t}
  $("table").innerHTML=`<table class="mx"><tr><th>task</th>${runs.map(r=>`<th>${esc(r)}</th>`).join("")}</tr>`+tasks.map(k=>`<tr><td>${esc(k)}</td>${runs.map(r=>{const t=cell[k+"|"+r];
  return `<td>${t?`<span class="${t.id?"row":""}" data-id="${esc(t.id||"")}" style="cursor:${t.id?"pointer":"default"}">${st(t.state)}</span>`:""}</td>`}).join("")}</tr>`).join("")+"</table>"}
 else $("table").innerHTML=`<table><tr><th>state</th><th>task</th><th>benchmark</th><th>mode</th><th>run</th><th>agent time</th><th class="num">input tok</th><th class="num">output tok</th><th class="num">requests</th><th class="num">reward</th><th>exception</th></tr>`+
  rows.map(t=>`<tr class="${t.id?"row":""}" data-id="${esc(t.id||"")}"><td>${st(t.state)}${t.over_budget?' <span class="st failed">over budget</span>':""}</td><td>${esc(t.task)}</td><td>${esc(t.bench)}</td><td>${esc(t.mode)}</td><td class="mut">${esc(t.run)}</td>
  <td>${elapsed(t)}</td><td class="num">${fmtT(t.tok_in)}</td><td class="num">${fmtT(t.tok_out)}</td><td class="num">${t.requests??""}</td><td class="num">${t.reward??""}</td><td class="mut">${esc((t.exception||"").replace(/Error$/,""))}</td></tr>`).join("")+"</table>";
 for(const el of document.querySelectorAll("[data-id]"))if(el.dataset.id)el.onclick=()=>show(el.dataset.id)}
async function show(id){open=id;const t=S.trials.find(x=>x.id===id);if(!t)return;
 const d=await (await fetch("api/trial?id="+encodeURIComponent(id))).json(),f=p=>"file?p="+encodeURIComponent(t.id.split(":")[0]+":"+p);
 const vids=t.media.filter(m=>m.endsWith(".mp4")),imgs=t.media.filter(m=>m.endsWith(".png"));
 $("drawer").innerHTML=`<button class="close" onclick="closeD()">close</button><h2 style="margin-top:0">${esc(t.task)}</h2>
 <p>${st(t.state)} <span class="mut">${esc(t.run)} · ${esc(t.trial)}</span></p><p>agent time ${elapsed(t)} · tokens ${fmtT(t.tok_in)} in / ${fmtT(t.tok_out)} out${t.requests?` · ${t.requests} requests`:""}${t.summary?` · <a href="${f(t.summary)}" target="_blank">summary.md</a>`:""}</p>
 ${vids.map(v=>`<p class="mut">${esc(v.split("/").pop())}</p><video src="${f(v)}" controls preload="metadata"></video>`).join("")}${!vids.length?imgs.map(v=>`<img src="${f(v)}">`).join(""):""}
 ${d.exception?`<h3>exception</h3><pre>${esc(d.exception)}</pre>`:""}${d.reward&&Object.keys(d.reward).length?`<h3>reward</h3><pre>${esc(JSON.stringify(d.reward,null,1))}</pre>`:""}
 ${d.agent_tail?`<h3>agent output (${esc(d.agent_log)}, last lines)</h3><pre>${esc(d.agent_tail)}</pre>`:""}${d.trial_log_tail?`<h3>trial.log</h3><pre>${esc(d.trial_log_tail)}</pre>`:""}`;
 $("drawer").classList.add("open")}
function closeD(){open=null;$("drawer").classList.remove("open")}
async function tick(){try{S=await (await fetch("api/state")).json();
 const c={};for(const t of S.trials)c[t.state]=(c[t.state]||0)+1;
 $("meta").textContent=`${S.trials.length} trials · ${ORDER.filter(s=>c[s]).map(s=>c[s]+" "+s).join(" · ")} · updated ${new Date(S.now*1000).toLocaleTimeString()}`;
 cards();selects();table();const t=open&&S.trials.find(x=>x.id===open);if(t&&["running","verifying","setup"].includes(t.state))show(open)}catch(e){$("meta").textContent="board unreachable: "+e}}
for(const id of["run","st","mode","q"])$(id).addEventListener("input",table);
$("view").onclick=()=>{matrix=!matrix;try{localStorage.setItem("lb.matrix",matrix?"1":"0")}catch(e){}table()};
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeD()});tick();setInterval(tick,5000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        host = (self.headers.get("Host") or "").lower()
        host = host[1:].split("]")[0] if host.startswith("[") else host.rsplit(":", 1)[0]
        if LOOPBACK_BIND and host not in LOOPBACK:
            return self.send(403, b"use http://localhost:<port>/ (or 127.0.0.1)", "text/plain")
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/":
            return self.send(200, PAGE.encode(), "text/html; charset=utf-8")
        if u.path == "/api/state":
            return self.send(200, json.dumps(state()).encode(), "application/json")
        if u.path == "/api/trial":
            return self.send(200, json.dumps(detail(q.get("id", [""])[0])).encode(), "application/json")
        if u.path == "/file":
            rp = resolve(q.get("p", [""])[0])
            if rp is None or rp[1].suffix not in MEDIA or not rp[1].is_file():
                return self.send(404, b"not found", "text/plain")
            return self.file(rp[1])
        self.send(404, b"not found", "text/plain")

    def file(self, p: pathlib.Path) -> None:
        """The file, or one byte range of it (video seeking), streamed in 1 MB pieces."""
        size = p.stat().st_size
        a, b, partial = 0, size - 1, False
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", "").strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                a, b = int(m.group(1)), int(m.group(2)) if m.group(2) else size - 1
            else:
                a = max(0, size - int(m.group(2))) if int(m.group(2)) else size
            b, partial = min(b, size - 1), True
            if a > b:
                return self.send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", MEDIA[p.suffix])
        self.send_header("Content-Length", str(b - a + 1))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(p, "rb") as f:
            f.seek(a)
            left = b - a + 1
            while left > 0:
                chunk = f.read(min(left, 1 << 20))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except OSError:                    # the browser hung up (seeking elsewhere)
                    return
                left -= len(chunk)


def main() -> int:
    global ARGS, LOOPBACK_BIND
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jobs", type=pathlib.Path, action="append", help="a Harbor -o directory (repeatable; default jobs/agents)")
    p.add_argument("--port", type=int, help="default: the first free port from 8765")
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--once", action="store_true", help="print the state as JSON and exit")
    ARGS = p.parse_args()
    ARGS.jobs = [j.resolve() for j in (ARGS.jobs or [REPO / "jobs" / "agents"])]
    LOOPBACK_BIND = ARGS.bind in LOOPBACK or ARGS.bind.startswith("127.")
    if ARGS.once:
        json.dump(collect(), sys.stdout, indent=1)
        return 0
    for port in [ARGS.port] if ARGS.port is not None else range(8765, 8865):
        try:
            srv = ThreadingHTTPServer((ARGS.bind, port), Handler)
            break
        except OSError as e:
            if ARGS.port is not None or port == 8864:
                sys.exit(f"cannot listen on {ARGS.bind}:{port}: {e}")
    srv.daemon_threads = True
    print(f"live board on http://{ARGS.bind}:{srv.server_address[1]}/ for {', '.join(map(str, ARGS.jobs))}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
