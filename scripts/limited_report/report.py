#!/usr/bin/env python3
"""One HTML report per limited-mode trial (a "checkme"):
  python3 scripts/limited_report/report.py jobs/<job> [...]         # every trial in each job
  python3 scripts/limited_report/report.py jobs/<job>/<trial> [--no-replay] [--no-billing]

Fills in everything that can be measured and writes <trial>/report/index.html (with its media next to it):
the verdict; every episode, replayed and scored verifier-side (replay_episodes.py, in the task's sim image), each
with a video (one player; the graded episode and the best few are picked out, any other one is a click away);
time per phase; tokens; the OpenRouter bill, looked up per generation; what the agent said and ran in each
episode; every image the model looked at; the agent's whole trajectory (agent/trajectory.json, the ATIF file
`harbor view` renders), each step tagged with the robot's episode and step; Harbor's other records (the agent's
script, verifier output, result/config/lock, trial.log, agent logs, artifact manifest); a leak grep.
The strategy summary is prose, not a measurement: write it to <trial>/report/notes.md (Markdown) and rerun --
the lookups and the replay are cached in report/, so a rerun takes seconds.
`harbor view jobs` is then only needed to compare trials; the report still links to the trial's page there,
and puts two files where the viewer looks for them -- agent/recording.mp4 (the graded episode, "Recording" tab)
and analysis.json (the summary and the checks, "Analysis" tab); neither overwrites a file it did not write.
  --no-replay   skip the replay (it needs docker and the sim image; on this machine docker may need `sg docker`)
  --no-billing  skip OpenRouter (it needs OPENROUTER_API_KEY, from the environment or the repo's .env)
  --no-harbor   do not write agent/recording.mp4 or analysis.json into the trial dir
"""
from __future__ import annotations

import argparse
import ast
import base64
import collections
import datetime as dt
import glob
import hashlib
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
# words that should not show up in what the agent wrote or ran: the answer key, upstream's code, the network
LEAK = re.compile(r"curl |wget |pip (install|download)|github|raw\.githubusercontent|humanoid_?bench|\bmujoco\b|dm_control|"
                  r"get_reward|rewards\.tolerance|_STAND_HEIGHT|_WALK_SPEED|_RUN_SPEED|stand_reward|small_control|dont_move", re.I)
GENERATED_BY = "scripts/limited_report/report.py"
END = {"success": "success", "failed": "fell / failed", "timeout": "step limit", "error": "sim error", None: "reset by the agent"}
esc = html.escape


def ts(s: str) -> float:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def jload(path, default=None):
    return json.load(open(path)) if os.path.exists(path) else default


def num(v, nd=0) -> str:
    return "—" if v is None else f"{v + 0.0 if abs(v) >= 0.5 * 10 ** -nd else 0.0:,.{nd}f}"   # no "-0.00"


# ------------------------------------------------------------------------------------------------ inputs
def sidecar(trial: str):
    """The sim service's own log: the spec it served, and one record per episode."""
    events = [json.loads(line) for line in open(f"{trial}/artifacts/data/episode.jsonl")]
    start = next((e for e in events if e["ev"] == "start"), {})
    new = lambda i, t: {"ep": i, "t0": t, "steps": 0, "observes": 0, "observe_images": 0, "end": None, "end_step": None}
    eps = [new(0, start.get("ts"))]
    for e in events:
        c = eps[-1]
        if e["ev"] == "step":
            c["steps"] = e["step"]
        elif e["ev"] == "observe":
            c["observes"] += 1; c["observe_images"] += bool(e.get("images"))
        elif e["ev"] == "end":
            c["end"], c["end_step"] = e["reason"], e["step"]
        elif e["ev"] == "reset":
            eps.append(new(len(eps), e["ts"]))
    return start, eps, events


def codex_session(trial: str):
    """codex's session log: per-request usage, the agent's messages, its tool calls, and the images it viewed."""
    reqs, msgs, timeline, views, calls, pending, open_calls = [], [], [], [], collections.Counter(), {}, {}
    for f in sorted(glob.glob(f"{trial}/agent/sessions/**/*.jsonl", recursive=True)):
        for line in open(f):
            e = json.loads(line); p = e.get("payload") or {}; t = ts(e["timestamp"]); typ = p.get("type")
            if e.get("type") == "token_usage_record":
                reqs.append({"id": p.get("response_id"), "t": t, **(p.get("usage") or {})})
            if e.get("type") != "response_item":
                continue
            if typ == "message" and p.get("role") == "assistant":
                txt = " ".join(c.get("text", "") for c in p.get("content", []) if isinstance(c, dict)).strip()
                if txt:
                    msgs.append((t, txt)); timeline.append({"t": t, "kind": "msg", "text": txt})
            elif typ in ("custom_tool_call", "function_call"):
                code = p.get("input") or p.get("arguments") or ""
                used = re.findall(r"tools\.(\w+)\(", code)   # codex's code mode: one call can run several tools
                calls.update(used or [p.get("name") or "other"])
                paths = re.findall(r'view_image\(\{path:\s*"([^"]+)"', code)
                if paths:
                    pending[p.get("call_id")] = paths
                cmds = [unquote(c) for c in re.findall(r'cmd:\s*"((?:[^"\\]|\\.)*)"', code)]
                entry = {"t": t, "kind": "call", "text": code, "cmds": cmds, "done": t}
                open_calls[p.get("call_id")] = entry; timeline.append(entry)
            elif typ in ("custom_tool_call_output", "function_call_output"):
                output = p.get("output")
                items = output if isinstance(output, list) else [{"type": "text", "text": str(output)}]
                text = "".join(o.get("text", "") for o in items if isinstance(o, dict))
                imgs = [o for o in items if isinstance(o, dict) and o.get("type") == "input_image"]
                paths = pending.pop(p.get("call_id"), [])
                for k, o in enumerate(imgs):
                    views.append({"t": t, "path": paths[k] if k < len(paths) else None, "detail": o.get("detail"),
                                  "b64": o["image_url"].split(",", 1)[1]})
                if p.get("call_id") in open_calls:   # a command belongs to the episode running when it finished
                    open_calls.pop(p.get("call_id"))["done"] = t
                timeline.append({"t": t, "kind": "out", "text": text + (f"\n[{len(imgs)} image(s)]" if imgs else "")})
    return reqs, msgs, timeline, views, calls


def openrouter_key() -> str | None:
    """The repo's .env first: it is what `harbor run --env-file` gave the run (a shell may carry a stale key)."""
    env = os.path.join(REPO, ".env")
    lines = [line for line in open(env)] if os.path.exists(env) else []
    vals = [line.split("=", 1)[1].strip().strip("'\"") for line in lines if line.startswith("OPENROUTER_API_KEY=")]
    return vals[-1] if vals else os.environ.get("OPENROUTER_API_KEY")


def get_json(url: str, key: str | None = None, tries: int = 5):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {})
            return json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise SystemExit(f"OpenRouter refused the key ({e.code}): check OPENROUTER_API_KEY in {REPO}/.env, or pass --no-billing")
            time.sleep(2 + 2 * attempt)   # 404 while the generation stats lag a little behind the run: retry
        except OSError:
            time.sleep(2 + 2 * attempt)
    return None


def billing(reqs: list, model: str, cache: str) -> dict:
    """OpenRouter's billed cost per generation, and the model's list prices; cached in report/billing.json."""
    got = jload(cache, {"generations": {}, "pricing": None})
    key = openrouter_key()
    if key:
        for r in reqs:
            if r["id"] and r["id"] not in got["generations"]:
                g = get_json(f"https://openrouter.ai/api/v1/generation?id={r['id']}", key)
                if g and g.get("data"):
                    d = g["data"]
                    got["generations"][r["id"]] = {k: d.get(k) for k in ("usage", "generation_time", "latency", "provider_name")}
                time.sleep(0.15)
        if not got["pricing"]:
            models = get_json("https://openrouter.ai/api/v1/models") or {"data": []}
            mid = model.split("openrouter/", 1)[-1]
            got["pricing"] = next((m.get("pricing") for m in models["data"] if m["id"] == mid), None)
    json.dump(got, open(cache, "w"), indent=1)
    return got


def docker(cmd: list[str]) -> subprocess.CompletedProcess:
    """docker, or `sg docker -c` where the user is in the group but the login shell does not have it yet."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode and "permission denied" in (r.stderr + r.stdout).lower():
        r = subprocess.run(["sg", "docker", "-c", shlex.join(cmd)], capture_output=True, text=True)
    return r


def replay(trial: str, task_dir: str, out: str) -> tuple[list, str | None]:
    cached = jload(f"{out}/episodes.json")
    if cached is not None:
        return cached, None
    compose = open(f"{task_dir}/environment/docker-compose.yaml").read()
    m = re.search(r"^\s*sim:\s*\n\s*image:\s*(\S+)", compose, re.M)
    if not m:
        return [], "no sim image in the task's docker-compose.yaml"
    base = ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp",
            "-v", f"{trial}:/trial:ro", "-v", f"{task_dir}/environment/sim:/srv:ro", "-v", f"{HERE}:/tool:ro", "-v", f"{out}:/out"]
    run = [m.group(1), "python", "/tool/replay_episodes.py", "/trial", "/srv", "/out"]
    gpu = ["--gpus", "all", "-e", "NVIDIA_DRIVER_CAPABILITIES=compute,graphics,utility"]
    r = docker(base[:3] + gpu + base[3:] + run)
    if r.returncode:   # no GPU here: the image falls back to CPU rendering, slower but the same pictures
        r = docker(base + run)
    if r.returncode:
        return [], (r.stderr or r.stdout).strip()[-1500:]
    return jload(f"{out}/episodes.json", []), None


# ------------------------------------------------------------------------------------------------ html
def md(src: str) -> str:
    """Enough Markdown for notes.md: headings, paragraphs, lists, tables, code blocks, `code`, **bold**, [links]()."""
    def inline(s):
        s = esc(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    out, L, i = [], src.splitlines(), 0
    item = re.compile(r"\s*([-*]|\d+\.)\s+")
    while i < len(L):
        line = L[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(L) and not L[j].startswith("```"):
                j += 1
            out.append(f"<pre>{esc(chr(10).join(L[i + 1:j]))}</pre>"); i = j + 1
        elif m := re.match(r"(#{1,4})\s+(.*)", line):
            h = min(len(m.group(1)) + 2, 6); out.append(f"<h{h}>{inline(m.group(2))}</h{h}>"); i += 1
        elif item.match(line):
            items = []
            while i < len(L) and (item.match(L[i]) or (items and L[i].startswith("  ") and L[i].strip())):
                if item.match(L[i]):
                    items.append(item.sub("", L[i], count=1))
                else:
                    items[-1] += " " + L[i].strip()
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
        elif line.startswith("|"):
            rows = []
            while i < len(L) and L[i].startswith("|"):
                rows.append([c.strip() for c in L[i].strip().strip("|").split("|")]); i += 1
            body = [r for r in rows[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
            out.append(table([inline(c) for c in rows[0]], [[inline(c) for c in r] for r in body]))
        elif not line.strip():
            i += 1
        else:
            buf = []
            while i < len(L) and L[i].strip() and not re.match(r"#{1,4}\s|```|\|", L[i]) and not item.match(L[i]):
                buf.append(L[i].strip()); i += 1
            out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out)


def table(head: list, rows: list, marked: set = frozenset()) -> str:
    """rows[i] in `marked` is highlighted (the graded episode)."""
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join(f"<tr{' class=graded' if i in marked else ''}>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for i, r in enumerate(rows))
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--mut:#6e6e73;--line:#e3e3e0;--acc:#2f6fdb;--ok:#1f9d55;--bad:#d64545;--code:#f0f0ec}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#161618;--card:#1f1f22;--fg:#ececef;--mut:#9a9aa2;--line:#2e2e33;--acc:#6ea0ff;--ok:#4cc38a;--bad:#ff7070;--code:#29292d}}
:root[data-theme=dark]{--bg:#161618;--card:#1f1f22;--fg:#ececef;--mut:#9a9aa2;--line:#2e2e33;--acc:#6ea0ff;--ok:#4cc38a;--bad:#ff7070;--code:#29292d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"PingFang SC","Noto Sans CJK SC","Microsoft YaHei",system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 80px}h1{font-size:24px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3,h4,h5{font-size:16px;margin:20px 0 8px}.mut{color:var(--mut)}a{color:var(--acc)}code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:13px}
pre{background:var(--code);padding:10px 12px;border-radius:8px;overflow-x:auto;font-size:12.5px;line-height:1.45;white-space:pre-wrap;word-break:break-word}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.card .k{font-size:12.5px;color:var(--mut)}.card .v{font-size:20px;font-weight:600}.card .s{font-size:12.5px;color:var(--mut)}
.card .v.sm{font-size:14px;font-weight:500}.ok{color:var(--ok)}.bad{color:var(--bad)}.tw{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px;margin:8px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--mut);font-weight:500;white-space:nowrap}
tr:last-child td{border-bottom:0}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}.graded td{background:color-mix(in srgb,var(--acc) 9%,transparent)}
.notes{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:4px 18px}
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}.gal figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.gal img,.gal video{width:100%;display:block;image-rendering:pixelated;background:#000}.gal figcaption{font-size:12px;padding:6px 8px;color:var(--mut);word-break:break-all}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:8px 0}summary{cursor:pointer;font-weight:500}
.tl .msg{margin:10px 0;padding:8px 12px;border-left:3px solid var(--acc);background:var(--bg);border-radius:0 8px 8px 0}.tl .t{font-size:12px;color:var(--mut);font-variant-numeric:tabular-nums}
.player{display:grid;grid-template-columns:minmax(0,512px) minmax(0,1fr);gap:16px;align-items:start}.player video{width:100%;display:block;image-rendering:pixelated;border-radius:10px;background:#000}
.player select{margin-top:4px;max-width:100%;font:inherit;padding:4px 6px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
.step{padding:6px 10px;margin:6px 0}.step summary{font-weight:400;font-size:13.5px}.step.sys summary{color:var(--mut)}
.step pre{max-height:460px;overflow:auto}.step .call{font-size:12px;color:var(--mut);margin-top:8px}.step img{width:192px;image-rendering:pixelated;margin:4px 6px 0 0;border-radius:6px}
.badge{display:inline-block;font-size:12px;padding:0 6px;border-radius:6px;background:var(--code);font-variant-numeric:tabular-nums}.badge.reset{background:color-mix(in srgb,var(--acc) 22%,transparent)}
.tools button{font:inherit;font-size:13px;padding:3px 10px;margin-right:6px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
.pick{cursor:pointer}.pick:hover{border-color:var(--acc)}@media (max-width:700px){.player{grid-template-columns:1fr}}
"""
JS = """function play(src){const v=document.getElementById('player'),p=document.getElementById('pick');if(!v)return;v.src=src;v.play().catch(()=>{});
if(p){p.value=src;document.getElementById('cap').innerHTML='<b>'+p.selectedOptions[0].text+'</b>';}v.scrollIntoView({behavior:'smooth',block:'center'});}
function openAll(id,o){document.querySelectorAll('#'+id+' details').forEach(d=>d.open=o);}"""


def card(k: str, v: str, s: str = "", cls: str = "") -> str:
    return f'<div class="card"><div class="k">{k}</div><div class="v {cls}">{v}</div><div class="s">{s}</div></div>'


def build(trial: str, args) -> str:
    trial = os.path.abspath(trial.rstrip("/"))
    out = os.path.join(trial, "report"); os.makedirs(f"{out}/agent_views", exist_ok=True)
    res = json.load(open(f"{trial}/result.json"))
    cfg = res.get("config") or {}
    model = (cfg.get("agent") or {}).get("model_name") or (res.get("agent_info") or {}).get("model_info", {}).get("name", "?")
    agent_name = (cfg.get("agent") or {}).get("name", "?")
    task_rel = ((cfg.get("task") or {}).get("path") or "")
    task_dir = task_rel if os.path.isabs(task_rel) else os.path.join(REPO, task_rel)
    a0, a1 = ts(res["agent_execution"]["started_at"]), ts(res["agent_execution"]["finished_at"])
    phase = lambda k: ts(res[k]["finished_at"]) - ts(res[k]["started_at"]) if res.get(k) else None
    toml = open(f"{task_dir}/task.toml").read() if os.path.exists(f"{task_dir}/task.toml") else ""
    m = re.search(r"\[agent\][^\[]*?timeout_sec\s*=\s*([\d.]+)", toml)
    budget_s = float(m.group(1)) if m else None

    start, eps, events = sidecar(trial)
    spec = start.get("spec") or {}
    final = jload(f"{trial}/artifacts/data/final.json", {})
    reward = jload(f"{trial}/verifier/reward.json", {})
    reqs, msgs, timeline, views, calls = codex_session(trial)
    bill = billing(reqs, model, f"{out}/billing.json") if not args.no_billing else {"generations": {}, "pricing": None}
    replayed, replay_err = replay(trial, task_dir, out) if not args.no_replay else ([], "skipped (--no-replay)")
    by_ep = {r["ep"]: r for r in replayed}
    mins = lambda t: (t - a0) / 60

    # what the agent said and ran, and the images it looked at, placed in the episode running at that moment
    # (a command by when it finished: `--reset` inside it starts the episode it belongs to)
    bounds = [e["t0"] or a0 for e in eps] + [float("inf")]
    ep_at = lambda t: max(0, next(i for i in range(len(eps)) if bounds[i + 1] > t))
    ep_did = collections.defaultdict(list)
    for x in timeline:
        if x["kind"] == "msg":
            ep_did[ep_at(x["t"])].append((x["t"], "msg", x["text"]))
        elif x["kind"] == "call":
            for c in x["cmds"]:
                ep_did[ep_at(x["done"])].append((x["t"], "cmd", c))
    state = [(e["ts"], e.get("step", 0)) for e in events if e["ev"] in ("step", "observe", "reset")]
    for n, v in enumerate(views, 1):
        v["n"], v["ep"] = n, ep_at(v["t"])
        before = [s for s in state if s[0] <= v["t"]]
        v["step"] = before[-1][1] if before else 0
        v["file"] = f"agent_views/{n:02d}_{os.path.basename(v['path'] or 'image.png')}"
        with open(os.path.join(out, v["file"]), "wb") as f:
            f.write(base64.b64decode(v["b64"]))

    # ---------------------------------------------------------------- numbers
    S = lambda k: sum(r.get(k) or 0 for r in reqs)
    tok = {"in": S("input_tokens"), "cached": S("cached_input_tokens"), "write": S("cache_write_input_tokens"),
           "out": S("output_tokens"), "reason": S("reasoning_output_tokens")}
    tok["uncached"] = tok["in"] - tok["cached"] - tok["write"]
    gens = [bill["generations"].get(r["id"]) for r in reqs]
    billed = sum((g or {}).get("usage") or 0 for g in gens)
    found = sum(g is not None for g in gens)
    gen_s = sum((g or {}).get("generation_time") or 0 for g in gens) / 1000
    lat_s = sum((g or {}).get("latency") or 0 for g in gens) / 1000
    harbor_cost = (res.get("agent_result") or {}).get("cost_usd")
    price = bill.get("pricing") or {}

    def listed(r, k):   # a request's list price per token, with the long-context tier where the model has one
        tier = [o for o in price.get("overrides") or [] if (r.get("input_tokens") or 0) >= o.get("min_prompt_tokens", 1e18)]
        return float((tier[-1] if tier else price).get(k) or price.get(k) or 0)
    kinds = [("output", "completion", lambda r: r.get("output_tokens") or 0),
             ("cache read", "input_cache_read", lambda r: r.get("cached_input_tokens") or 0),
             ("cache write", "input_cache_write", lambda r: r.get("cache_write_input_tokens") or 0),
             ("uncached input", "prompt", lambda r: (r.get("input_tokens") or 0) - (r.get("cached_input_tokens") or 0) - (r.get("cache_write_input_tokens") or 0))]
    parts = [(name, sum(n(r) * listed(r, k) for r in reqs), float(price.get(k) or 0)) for name, k, n in kinds]
    long_ctx = sum(bool(o) for o in [[o for o in price.get("overrides") or [] if (r.get("input_tokens") or 0) >= o.get("min_prompt_tokens", 1e18)] for r in reqs])
    total_listed = sum(p[1] for p in parts)
    n_steps = sum(e["ev"] == "step" for e in events)
    n_resets = sum(e["ev"] == "reset" for e in events)
    graded = eps[-1]; g_rep = by_ep.get(graded["ep"], {})
    best = max(replayed, key=lambda r: r.get("return", -1), default={})
    bar = g_rep.get("bar") or best.get("bar")
    success = bool(reward.get("success"))
    exc = (res.get("exception_info") or {}).get("exception_type")
    budget_r = start.get("reset_budget")
    if graded["end"] == "success":
        why = f"success: the pass mark was reached at step {graded['steps']} and the service ended the episode ({(budget_r or 0) - n_resets} resets left)"
    elif exc and "timeout" in exc.lower():
        why = "time ran out (agent timeout)"
    elif budget_r and n_resets >= budget_r and graded["end"]:
        why = f"resets used up ({n_resets}/{budget_r}); the agent quit after the last episode ended"
    elif graded["end"]:
        why = f"the agent quit after the last episode ended ({(budget_r or 0) - n_resets} resets left)"
    else:
        why = f"the agent quit with the last episode still running, at step {graded['steps']}"
    agent_s = a1 - a0
    spikes, prev = [], None
    for r in reqs:
        if prev and r.get("input_tokens", 0) > 1.8 * prev and r["input_tokens"] - prev > 15000:
            spikes.append((mins(r["t"]), prev, r["input_tokens"]))
        prev = r.get("input_tokens") or prev
    leaks = [(mins(x["t"]), x["kind"], LEAK.search(x["text"]).group(0), x["text"][:240]) for x in timeline
             if x["kind"] in ("msg", "call") and LEAK.search(x["text"])]

    # ---------------------------------------------------------------- page
    rel = lambda p: os.path.relpath(p, out)
    H = []
    date = dt.datetime.fromtimestamp(a0).strftime("%Y-%m-%d %H:%M")
    H.append(f"<h1>{esc(res.get('task_name', '').split('/')[-1])}</h1>"
             f"<div class='mut'>{esc(model)} · {esc(agent_name.split(':')[-1])} · {date} · trial <code>{esc(res.get('trial_name', ''))}</code></div>")
    H.append("<h2>At a glance</h2><div class='cards'>" + "".join([
        card("Result", "PASS" if success else "FAIL", f"reward.json success = {reward.get('success')}", "ok" if success else "bad"),
        card("Graded episode's return", num(g_rep.get("return"), 2), f"pass mark {num(bar)}; {graded['steps']} steps, {END.get(graded['end'], graded['end'])}"),
        card("Best episode", num(best.get("return"), 2), f"ep{best.get('ep', '—')}, {best.get('n_actions', '—')} steps" if best else ""),
        card("Episodes", str(len(eps)), f"resets {n_resets}/{budget_r}; {n_steps:,} steps in all"),
        card("Agent time", f"{agent_s / 60:.1f} min", f"{agent_s / budget_s:.0%} of the budget" if budget_s else ""),
        card("Cost", f"${billed:.4f}" if found else (f"${harbor_cost:.4f}" if harbor_cost else "—"),
             f"OpenRouter bill, {found}/{len(reqs)} generations" if found else "Harbor's estimate"),
        card("Why it stopped", esc(why), "", "sm"),
    ]) + "</div>")

    notes = os.path.join(out, "notes.md")
    H.append("<h2>The agent's strategy</h2>")
    if os.path.exists(notes):
        H.append(f"<div class='notes'>{md(open(notes).read())}</div>")
    else:
        H.append(f"<p class='mut'>No summary yet: write it to <code>{esc(notes)}</code> and rerun this script. Meanwhile the last "
                 "column of the episode table has what the agent said and ran in each episode, and the full trajectory is further down.</p>")

    knobs = [("Model", f"<code>{esc(model)}</code>"), ("Agent", f"<code>{esc(agent_name)}</code>"),
             ("Time budget", f"{budget_s / 60:.0f} min" if budget_s else "—"), ("Resets allowed", str(budget_r)),
             ("Proprioception (joint angles / velocities)", "yes" if spec.get("proprio") else "no"),
             ("IMU", "yes (" + esc(spec["imu"].get("mounted", "")) + ")" if spec.get("imu") else "no"),
             ("Cameras", ", ".join(f"<code>{esc(c)}</code> ({esc(v.get('mounted', ''))}, {'×'.join(map(str, v.get('hw', [])))})" for c, v in (spec.get("cameras") or {}).items())),
             ("Control rate / steps per episode", f"{spec.get('control_hz')} Hz / {spec.get('max_episode_steps')}"),
             ("Grading", f"success {reward.get('success')}, finalized {reward.get('finalized')}, deterministic {reward.get('deterministic')}, "
                         f"n_actions {reward.get('n_actions')}, grader_error {reward.get('grader_error')}"),
             ("Exception", esc(exc) if exc else "none")]
    sec = {}
    sec["config"] = ("<h2>Configuration</h2>" + table(["Item", "Value"], knobs)
                     + "<p class='mut'>From the <code>/spec</code> the sim service recorded at start-up, and Harbor's result.json.</p>")

    rows = []
    for e in eps:
        r = by_ep.get(e["ep"], {})
        did = ep_did.get(e["ep"], [])
        said = ""
        if did:
            lead = next((x for x in did if x[1] == "msg"), did[0])   # its own words if it said something, else the first command
            short = lead[2][:180] + ("…" if len(lead[2]) > 180 else "")
            first = esc(short) if lead[1] == "msg" else f"<code>{esc(short)}</code>"
            rest = "".join(f"<p><span class='t'>{mins(t):.2f} min</span> " + (esc(x) if k == "msg" else f"<code>{esc(x[:600])}</code>") + "</p>"
                           for t, k, x in did)
            said = first if len(did) == 1 and len(lead[2]) <= 180 else f"<details><summary>{first}</summary>{rest}</details>"
        video = f"<a href='{r['video']}' onclick=\"play(this.getAttribute('href'));return false\">▶ play</a>" if r.get("video") else "—"
        t0 = "start" if e["ep"] == 0 else f"{mins(e['t0']):.2f}"
        rows.append(([f"<b>{e['ep']}</b>" + (" (graded)" if e["ep"] == graded["ep"] else ""), t0, str(e["steps"]),
                     END.get(e["end"], e["end"]), num(r.get("return"), 2), num(r.get("max_dx"), 2), num(r.get("final_dx"), 2),
                     str(sum(v["ep"] == e["ep"] for v in views)), video, said]))
    head = ["Episode", "Start (min)", "Steps", "How it ended", "Return", "Max x (m)", "Final x (m)", "Images viewed", "Video",
            "What the agent said and ran"]
    sec["episodes"] = ("<h2>Episodes</h2>" + table(head, rows, {len(rows) - 1})
                       + "<p class='mut'>Returns and displacements come from a verifier-side replay afterwards; the agent never saw them. "
                       "The graded episode is replayed from the exact trajectory, the others from the log's actions, rounded to 5 decimals "
                       "(approximate). x is the pelvis's displacement along the task's forward direction."
                       + (f" The replay did not run: {esc(replay_err)}" if replay_err else "") + "</p>")

    money = [("<b>Billed total</b>", f"<b>${billed:.6f}</b>" if found else "—",
              f"OpenRouter, per generation: {found}/{len(reqs)} found; Harbor's cost_usd = {num(harbor_cost, 6)}")]
    for name, usd, p in parts:
        money.append((name, f"${usd:.6f}" if price else "—", f"${p * 1e6:.3f}/M, {usd / total_listed:.0%}" if price and total_listed else ""))
    if long_ctx:
        money.append(("long context", "", f"{long_ctx} requests above the long-context threshold, priced at the higher tier"))
    tokens = [("Model requests", f"{len(reqs):,}", ""),
              ("Input, total", f"{tok['in']:,}", f"cached {tok['cached']:,} ({tok['cached'] / max(tok['in'], 1):.1%})"),
              ("Cache writes", f"{tok['write']:,}", ""), ("Uncached input", f"{tok['uncached']:,}", ""),
              ("Output, total", f"{tok['out']:,}", f"reasoning {tok['reason']:,} ({tok['reason'] / max(tok['out'], 1):.0%})"),
              ("Largest single input (context)", f"{max((r.get('input_tokens') or 0 for r in reqs), default=0):,}", "")]
    times = [("Trial, total", f"{ts(res['finished_at']) - ts(res['started_at']):.0f} s", ""),
             ("Environment start-up", f"{phase('environment_setup') or 0:.0f} s", ""),
             ("Agent install", f"{phase('agent_setup') or 0:.0f} s", ""),
             ("<b>Agent run</b>", f"<b>{agent_s:.0f} s</b>", f"{agent_s / 60:.1f} min" + (f", {agent_s / budget_s:.1%} of the budget" if budget_s else "")),
             ("Wrap-up (the sidecar saves the trajectory, replays, renders)", f"{ts(res['verifier']['started_at']) - a1:.0f} s" if res.get("verifier") else "—", ""),
             ("Verifier", f"{phase('verifier') or 0:.0f} s", ""),
             ("Model generation (OpenRouter)", f"{gen_s:.0f} s" if found else "—",
              f"{gen_s / agent_s:.0%} of the agent run; {lat_s:.0f} s of it waiting for first tokens; {agent_s / max(len(reqs), 1):.1f} s per turn on average"
              if found else "")]
    robot = [("Control steps", f"{n_steps:,}", f"= {n_steps / (spec.get('control_hz') or 50):.1f} s of sim time"),
             ("Resets", f"{n_resets} / {budget_r}", ""),
             ("observe calls", str(sum(e['observes'] for e in eps)), f"{sum(e['observe_images'] for e in eps)} of them with images"),
             ("Images the model looked at (view_image)", str(len(views)), ""),
             ("Tool calls", ", ".join(f"{k} {v}" for k, v in calls.most_common()), "")]
    sec["cost"] = ("<h2>Cost</h2><h3>Money</h3>" + table(["Item", "Amount", "Note"], money) + "<h3>Tokens</h3>" + table(["Item", "Count", "Note"], tokens)
                   + "<h3>Time</h3>" + table(["Phase", "Duration", "Note"], times) + "<h3>On the robot</h3>" + table(["Item", "Count", "Note"], robot))

    sec["views"] = "<h2>What the agent saw</h2>"
    if views:
        sec["views"] += ("<p class='mut'>Every image the model looked at through <code>view_image</code>, exactly as it was sent (from codex's session "
                         "log). The step shown is the sim's last logged step before the model looked.</p><div class='gal'>"
                 + "".join(f"<figure><a href='{v['file']}'><img src='{v['file']}' loading='lazy'></a><figcaption>#{v['n']} · {mins(v['t']):.2f} min · ep{v['ep']} step {v['step']}"
                           f" · detail {esc(str(v['detail']))}<br>{esc(v['path'] or '')}</figcaption></figure>" for v in views) + "</div>")
    else:
        sec["views"] += "<p class='mut'>The model did not look at any image.</p>"

    # one player: the graded episode first; a few picked out (best returns, longest alive); any other on demand
    vid = f"{trial}/verifier/replay.mp4"
    end_of = {e["ep"]: END.get(e["end"], e["end"]) for e in eps}
    cap = lambda r: f"ep{r['ep']}{' (graded)' if r['graded'] else ''} · {r['n_actions']} steps · return {num(r.get('return'), 2)} · {end_of.get(r['ep'], '')}"
    playable = [r for r in replayed if r.get("video")]
    picks, seen = [], set()
    by_return = sorted(playable, key=lambda r: -(r.get("return") or 0))
    for r, why in ([(g, "graded episode") for g in playable if g["graded"]] + [(r, f"#{k} by return") for k, r in enumerate(by_return[:3], 1)]
                   + [(max(playable, key=lambda r: r["n_actions"]), "longest alive")] if playable else []):
        if r["ep"] not in seen and len(picks) < 4:
            picks.append((r, why)); seen.add(r["ep"])
    sec["video"] = "<h2>Videos</h2>"
    if playable:
        first = picks[0][0]
        opts = "".join(f"<option value='{r['video']}'{' selected' if r is first else ''}>{esc(cap(r))}</option>" for r in playable)
        sec["video"] += (f"<div class='player'><video id='player' src='{first['video']}' poster='{first.get('poster', '')}' controls loop muted preload='metadata'></video>"
                         f"<div><p id='cap'><b>{esc(cap(first))}</b></p><label class='mut'>Pick an episode:<br><select id='pick' onchange='play(this.value)'>{opts}</select></label>"
                         "<p class='mut'>Every episode is re-rendered from a replay (25 fps, real time); ▶ in the episode table plays here too.</p>"
                         + (f"<p class='mut'>The sidecar's own recording of the graded episode: <a href='{rel(vid)}'>replay.mp4</a></p>" if os.path.exists(vid) else "")
                         + "</div></div><h3>Picked out</h3><div class='gal'>" + "".join(
                             f"<figure class='pick' onclick=\"play('{r['video']}')\"><img src='{r.get('poster', '')}' alt='' loading='lazy'>"
                             f"<figcaption><b>{why}</b><br>{esc(cap(r))}</figcaption></figure>" for r, why in picks) + "</div>")
    elif os.path.exists(vid):
        sec["video"] += f"<div class='player'><video id='player' src='{rel(vid)}' controls loop muted></video><div><p>The graded episode (the sidecar's own recording).</p></div></div>"
    else:
        sec["video"] += "<p class='mut'>No video.</p>"

    files = [("This report", os.path.join(out, "index.html")), ("Graded episode, the sidecar's recording", vid),
             ("Every episode's video", os.path.join(out, "episodes", "ep{0..%d}.mp4" % (len(eps) - 1))),
             ("Images the agent looked at", os.path.join(out, "agent_views")), ("What the agent left in /app/output", f"{trial}/artifacts/app/output"),
             ("Sidecar event log, trajectory, final.json", f"{trial}/artifacts/data"), ("The agent's raw logs", f"{trial}/agent"),
             ("Verifier output", f"{trial}/verifier"), ("Strategy summary (hand-written)", notes)]
    sec["files"] = ("<h2>Files (absolute paths)</h2>" + table(["What", "Path"], [(k, f"<code>{esc(v)}</code>") for k, v in files]))

    sec["leaks"] = ("<h2>Leak check</h2>" + table(["Check", "Result"], [
        ("Input-token jumps (>1.8x and >15k)", "none" if not spikes else "; ".join(f"{t:.2f} min: {a:,} → {b:,}" for t, a, b in spikes)),
        ("Suspicious words in what the agent wrote or ran", "none" if not leaks else
         "<br>".join(f"{t:.2f} min [{k}] <code>{esc(w)}</code>: {esc(x)}" for t, k, w, x in leaks[:20]))]))

    # harbor view: the same trial, from Harbor's side (the agent's full trajectory, logs, config)
    info = res.get("agent_info") or {}
    q = lambda v: urllib.parse.quote(str(v), safe="")
    hv = (f"http://127.0.0.1:8080/jobs/{q(os.path.basename(os.path.dirname(trial)))}/tasks/{q(res.get('source') or '_')}/{q(info.get('name') or '_')}"
          f"/{q((info.get('model_info') or {}).get('provider') or '_')}/{q((info.get('model_info') or {}).get('name') or '_')}/{q(res.get('task_name', ''))}"
          f"/trials/{q(res.get('trial_name', ''))}")
    sec["harbor"] = ("<h2>harbor view</h2><p class='mut'>The full trajectory and Harbor's other records above are what harbor view shows, so it "
                     "is rarely needed. To compare trials, run <code>harbor view jobs</code> from the repo root (port 8080 by default) and open "
                     f"<a href='{hv}'>this trial's page there</a> (the Recording tab has the graded episode, the Analysis tab the strategy summary).</p>")
    if not args.no_harbor:
        sec["harbor"] += harbor_files(trial, vid, res, notes, success, g_rep, bar, graded, eps, agent_s, billed if found else harbor_cost, spikes, leaks)

    sec["trajectory"] = trajectory_html(trial, out, views, state, ep_at, mins, a1)
    sec["records"] = records_html(trial, out)
    H += [sec[k] for k in ("video", "episodes", "views", "cost", "config", "trajectory", "records", "leaks", "files", "harbor")]
    title = f"{res.get('task_name', '').split('/')[-1]} · {model.split('/')[-1]}"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}</style><script>{JS}</script></head><body><main>{''.join(H)}</main></body></html>")
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(page)
    return os.path.join(out, "index.html")


def unquote(js: str) -> str:
    """The body of a JS/JSON string literal, as text."""
    try:
        return json.loads(f'"{js}"')
    except ValueError:
        return js


def pretty_output(text: str) -> str:
    """codex wraps each command's result in JSON ({"exit_code":..,"output":".."}, or a Promise.allSettled entry):
    show the output itself, with its line breaks."""
    lines = []
    for line in text.splitlines():
        try:
            d = json.loads(line) if line.startswith("{") else None
        except ValueError:
            d = None
        d = (d.get("value") or d.get("reason")) if isinstance(d, dict) and "status" in d and ("value" in d or "reason" in d) else d
        if isinstance(d, dict) and "output" in d:
            lines.append(f"[exit {d.get('exit_code', '?')}]" + ("" if d.get("output", "").startswith("\n") else "\n") + str(d["output"]).rstrip())
        elif isinstance(d, str):
            lines.append(d)
        else:
            lines.append(line)
    return "\n".join(lines)


def call_label(code: str) -> str:
    """One line for a step's tool calls: the shell command, the file patched, or the image viewed."""
    cmds = [unquote(c) for c in re.findall(r'cmd:\s*"((?:[^"\\]|\\.)*)"', code)]
    if cmds:
        return cmds[0]
    files = re.findall(r"\*\*\* (?:Add|Update|Delete) File: ([^\\\n]+)", code)
    if files:
        return "patch " + ", ".join(dict.fromkeys(f.strip() for f in files))
    views = re.findall(r'view_image\(\{path:\s*"([^"]+)"', code)
    if views:
        return "view image " + ", ".join(views)
    tools = re.findall(r"tools\.(\w+)\(", code)
    return ", ".join(dict.fromkeys(tools)) if tools else ""


def atif_steps(trial: str) -> list[dict]:
    """agent/trajectory.json (ATIF): the trajectory Harbor writes for every agent, and what `harbor view` shows."""
    t = jload(f"{trial}/agent/trajectory.json")
    steps = []
    for s in (t or {}).get("steps", []):
        calls = []
        for c in s.get("tool_calls") or []:
            a = c.get("arguments")
            if isinstance(a, dict) and len(a) == 1:
                a = next(iter(a.values()))
            calls.append((c.get("function_name") or "tool", a if isinstance(a, str) else json.dumps(a, ensure_ascii=False, indent=1)))
        results = []
        for r in (s.get("observation") or {}).get("results", []):
            items = r.get("content")
            if isinstance(items, str) and items.startswith("["):
                try:
                    items = ast.literal_eval(items)   # codex's content parts arrive as a Python repr
                except (ValueError, SyntaxError):
                    pass
            if not isinstance(items, list):
                items = [{"type": "text", "text": str(items)}]
            text = "".join(i.get("text", "") for i in items if isinstance(i, dict))
            imgs = [str(i.get("image_url"))[str(i.get("image_url")).find(",") + 1:] for i in items
                    if isinstance(i, dict) and "image" in str(i.get("type")) and str(i.get("image_url", "")).startswith("data:")]
            results.append((text, imgs))
        msg = s.get("message") or ""
        if isinstance(msg, list):
            msg = " ".join(m.get("text", "") for m in msg if isinstance(m, dict))
        steps.append({"id": s.get("step_id"), "t": ts(s["timestamp"]) if s.get("timestamp") else None, "source": s.get("source"),
                      "message": msg, "calls": calls, "results": results, "metrics": s.get("metrics") or {}})
    return steps


def trajectory_html(trial, out, views, state, ep_at, mins, a1) -> str:
    """Every step the agent took, each tagged with where the robot was once the step's commands had run."""
    steps = atif_steps(trial)
    if not steps:
        return "<h2>Full trajectory</h2><p class='mut'>No agent/trajectory.json.</p>"
    known = {hashlib.sha1(v["b64"].encode()).hexdigest(): v["file"] for v in views}   # images already exported
    os.makedirs(f"{out}/trajectory", exist_ok=True)
    cards, prev_ep, n_agent = [], 0, 0
    for i, s in enumerate(steps):
        if s["source"] != "agent":
            label = "Task instruction (instruction.md, as the agent received it)" if s["source"] == "user" and s["message"].startswith("#") else \
                {"system": "System prompt", "user": "User message / environment context"}.get(s["source"], str(s["source"]))
            cards.append(f"<details class='step sys card'><summary>#{s['id']} · {label} · {len(s['message']):,} chars</summary><pre>{esc(s['message'])}</pre></details>")
            continue
        n_agent += 1
        t_after = next((x["t"] for x in steps[i + 1:] if x["t"]), a1)   # the next step starts once this one's commands are back
        ep = ep_at(t_after); before = [x for x in state if x[0] <= t_after]; st = before[-1][1] if before else 0
        badge = (f"<span class='badge reset'>reset → ep{ep} step {st}</span>" if ep != prev_ep else f"<span class='badge'>ep{ep} step {st}</span>")
        prev_ep = ep
        m = s["metrics"]; imgs = sum(len(x[1]) for x in s["results"])
        lead = s["message"] or next((x for x in (call_label(code) for _, code in s["calls"]) if x), ", ".join(n for n, _ in s["calls"]))
        lead = " ".join(lead.split())
        head = (f"#{s['id']} · {mins(s['t']):.2f} min · {badge} · in {num(m.get('prompt_tokens'))} / out {num(m.get('completion_tokens'))}"
                + (f" · ${m['cost_usd']:.4f}" if m.get("cost_usd") is not None else "") + (f" · {imgs} image(s)" if imgs else "")
                + f" · {esc(lead[:140])}{'…' if len(lead) > 140 else ''}")
        body = [f"<p>{esc(s['message'])}</p>"] if s["message"] else []
        for name, code in s["calls"]:
            body.append(f"<div class='call'>call {esc(name)}</div><pre>{esc(code[:8000])}</pre>")
        for text, b64s in s["results"]:
            text = pretty_output(text)
            if text.strip():
                body.append(f"<div class='call'>output</div><pre>{esc(text[:6000])}{'… (truncated)' if len(text) > 6000 else ''}</pre>")
            for k, b in enumerate(b64s):
                h = hashlib.sha1(b.encode()).hexdigest()
                if h not in known:
                    known[h] = f"trajectory/step{s['id']}_{k}.png"
                    with open(os.path.join(out, known[h]), "wb") as f:
                        f.write(base64.b64decode(b))
                body.append(f"<a href='{known[h]}'><img src='{known[h]}' loading='lazy' alt=''></a>")
        cards.append(f"<details class='step card'><summary>{head}</summary>{''.join(body)}</details>")
    return ("<h2>Full trajectory</h2><p class='mut'>From <code>agent/trajectory.json</code>, in ATIF (Agent Trajectory Interchange Format): "
            "Harbor converts each agent's native log into it, and harbor view's Trajectory tab renders the same file. "
            f"{len(steps)} steps, {n_agent} of them the agent's; each is tagged with the robot's episode and step once its commands had run.</p>"
            "<div class='tools'><button onclick=\"openAll('traj',true)\">Expand all</button><button onclick=\"openAll('traj',false)\">Collapse all</button></div>"
            f"<div id='traj'>{''.join(cards)}</div>")


def records_html(trial, out) -> str:
    """The rest of what `harbor view` shows for a trial: files, each folded."""
    def block(title, path, tail=None, limit=60000):
        if not os.path.isfile(path):
            return ""
        txt = open(path, errors="replace").read()
        if path.endswith(".json"):
            try:
                txt = json.dumps(json.loads(txt), ensure_ascii=False, indent=1)
            except ValueError:
                pass
        note, lines = "", txt.splitlines()
        if tail and len(lines) > tail:
            txt, note = "\n".join(lines[-tail:]), f", last {tail} of {len(lines):,} lines"
        cut = len(txt) > limit
        body = f"<pre>{esc(txt[:limit])}{chr(10) + '… (truncated)' if cut else ''}</pre>" if txt.strip() else "<p class='mut'>(empty file)</p>"
        return (f"<details class='card step'><summary>{title} <span class='mut'>· <a href='{os.path.relpath(path, out)}'>"
                f"{esc(os.path.relpath(path, trial))}</a> · {os.path.getsize(path):,} B{note}</span></summary>{body}</details>")
    parts = ["<h3>What the agent left</h3>", block("Driver script gen.py", f"{trial}/artifacts/app/output/gen.py")]
    outs = sorted(p for p in glob.glob(f"{trial}/artifacts/app/output/**/*", recursive=True) if os.path.isfile(p))
    if outs:
        parts.append(f"<details class='card step'><summary>Every file in /app/output <span class='mut'>· {len(outs)}</span></summary><p>"
                     + "<br>".join(f"<a href='{os.path.relpath(p, out)}'>{esc(os.path.relpath(p, f'{trial}/artifacts/app/output'))}</a> "
                                   f"<span class='mut'>{os.path.getsize(p):,} B</span>" for p in outs) + "</p></details>")
    parts += ["<h3>Verifier</h3>", block("reward.json", f"{trial}/verifier/reward.json"), block("test-stdout.txt", f"{trial}/verifier/test-stdout.txt"),
              block("grade.log", f"{trial}/verifier/grade.log")]
    parts += ["<h3>Harbor</h3>", block("result.json (phase times, tokens, exception)", f"{trial}/result.json"), block("config.json", f"{trial}/config.json"),
              block("lock.json", f"{trial}/lock.json"), block("exception.txt", f"{trial}/exception.txt"), block("trial.log", f"{trial}/trial.log", tail=400)]
    parts += ["<h3>Agent logs</h3>"] + [block(os.path.relpath(p, f"{trial}/agent"), p, tail=400)
                                        for p in sorted(glob.glob(f"{trial}/agent/*.txt") + glob.glob(f"{trial}/agent/setup/**/*.txt", recursive=True))]
    man = jload(f"{trial}/artifacts/manifest.json", [])
    if man:
        parts.append("<h3>Artifact collection (artifacts/manifest.json)</h3>" + table(["Source", "Saved to", "Type", "Service", "Status"], [
            (f"<code>{esc(m.get('source', ''))}</code>", f"<code>{esc(m.get('destination', ''))}</code>", esc(str(m.get("type"))),
             esc(str(m.get("service") or "main")), esc(str(m.get("status")))) for m in man]))
    return ("<h2>Harbor's other records</h2><p class='mut'>What harbor view shows under Agent, Verifier, Artifacts, Config, Lock, Log and "
            "Exception; click one to open it.</p>" + "".join(parts))


def harbor_files(trial, vid, res, notes, success, g_rep, bar, graded, eps, agent_s, cost, spikes, leaks) -> str:
    """The two files `harbor view` looks for, written only where they are missing or were written by this script."""
    said = []
    rec = f"{trial}/agent/recording.mp4"
    if os.path.exists(vid) and not os.path.exists(rec):
        shutil.copyfile(vid, rec); said.append("agent/recording.mp4")
    path = f"{trial}/analysis.json"
    mine = (jload(path, {}) or {}).get("generated_by") == GENERATED_BY
    if mine or not os.path.exists(path):
        head = (f"**{'PASS' if success else 'FAIL'}** · graded episode's return {num(g_rep.get('return'), 2)} / {num(bar)} · {len(eps)} episodes · "
                f"agent {agent_s / 60:.1f} min · ${cost or 0:.4f}")
        body = open(notes).read() if os.path.exists(notes) else "(No strategy summary yet: report/notes.md)"
        checks = {
            "leak_grep": {"outcome": "fail" if spikes or leaks else "pass",   # fail = flagged for a human look, not proof of a leak
                          "explanation": "Flagged for a human look (not necessarily a leak): "
                          + "; ".join([f"{t:.2f} min {w}" for t, _, w, _ in leaks[:5]] + [f"{t:.2f} min input {a:,} → {b:,}" for t, a, b in spikes])
                          if spikes or leaks else "No input-token jumps, no suspicious words in what the agent wrote or ran (LEAK in scripts/limited_report/report.py)"},
            "graded_episode": {"outcome": "pass" if success else "fail",
                               "explanation": f"Episode {graded['ep']} (the last) was graded: {graded['steps']} steps, {END.get(graded['end'], graded['end'])}, "
                                              f"return {num(g_rep.get('return'), 2)}, pass mark {num(bar)}"},
        }
        json.dump({"trial_name": res.get("trial_name"), "summary": head + "\n\n" + body, "checks": checks,
                   "estimated_cost_usd": None, "generated_by": GENERATED_BY}, open(path, "w"), ensure_ascii=False, indent=2)
        said.append("analysis.json")
    return f"<p class='mut'>Written into the trial dir for harbor view this time: {', '.join(said) or 'nothing (both already there, not overwritten)'}.</p>"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="job dirs (every trial in each) or trial dirs")
    ap.add_argument("--no-replay", action="store_true")
    ap.add_argument("--no-billing", action="store_true")
    ap.add_argument("--no-harbor", action="store_true")
    args = ap.parse_args()
    trials = []
    for p in (os.path.abspath(x.rstrip("/")) for x in args.paths):
        trials += [p] if os.path.isdir(f"{p}/agent") else sorted(d.rstrip("/") for d in glob.glob(f"{p}/*/") if os.path.isdir(f"{d}/agent"))
    if not trials:
        sys.exit(f"no trial under {args.paths}")
    for t in trials:
        if not os.path.exists(f"{t}/artifacts/data/episode.jsonl"):
            print(f"skip {t}: no sidecar log (not a limited-mode trial, or it did not finish)"); continue
        print(build(t, args))


if __name__ == "__main__":
    main()
