#!/usr/bin/env python3
"""Measure one trial, limited or full mode, for the results pages (scripts/results/build.py runs this for every trial
that has no summary yet, so it is rarely needed by hand):
  python3 scripts/results/collect.py jobs/<job> [...]         # every trial in each job
  python3 scripts/results/collect.py jobs/<job>/<trial> [--no-replay] [--no-billing] [--no-harbor]

Writes <trial>/report/summary.json -- everything that can be measured -- and the media next to it: the OpenRouter
bill, looked up per generation; every tool call and every image the model looked at; in limited mode, every episode
replayed and scored verifier-side from the sim service's log (replay_episodes.py, in the task's sim image), each with
a video. A full-mode trial has no such log (the simulator runs inside the agent's own process): its result is the
verifier's replay of the submitted trajectory. The lookups and the replay are cached in report/,
so a rerun takes seconds. The strategy summary is prose, not a measurement: <trial>/report/notes.md (Markdown),
whose optional phase table colours the timeline (episode ranges, one per line):
  <!-- phases
  0-2 标定
  3-13 站姿与平衡
  -->
It also puts two files where `harbor view` looks for them -- agent/recording.mp4 (the graded replay, "Recording"
tab) and analysis.json (the summary and the checks, "Analysis" tab); neither overwrites a file it did not write.
  --no-replay   skip the replay (it needs docker and the sim image; on this machine docker may need `sg docker`)
  --no-billing  skip OpenRouter (it needs OPENROUTER_API_KEY, from the environment or the repo's .env)
  --no-harbor   do not write agent/recording.mp4 or analysis.json into the trial dir
"""
from __future__ import annotations

import argparse
import base64
import collections
import datetime as dt
import glob
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
VERSION = 3   # of summary.json; build.py re-collects a trial whose summary is older
# words that should not show up in what the agent wrote or ran: the answer key, upstream's code, the network
LEAK = re.compile(r"curl |wget |pip (install|download)|github|raw\.githubusercontent|humanoid_?bench|\bmujoco\b|dm_control|"
                  r"get_reward|rewards\.tolerance|_STAND_HEIGHT|_WALK_SPEED|_RUN_SPEED|stand_reward|small_control|dont_move", re.I)
GENERATED_BY = "scripts/results/collect.py"


def ts(s: str) -> float:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def jload(path, default=None):
    return json.load(open(path)) if os.path.exists(path) else default


# ------------------------------------------------------------------------------------------------ inputs
def sidecar(trial: str):
    """The sim service's own log: the spec it served, and one record per episode (when it started, its last step,
    when and how it ended; `end` None = reset by the agent, or still running when the agent stopped)."""
    events = [json.loads(line) for line in open(f"{trial}/artifacts/data/episode.jsonl")]
    start = next((e for e in events if e["ev"] == "start"), {})
    new = lambda i, t: {"ep": i, "t0": t, "t_last": None, "t_end": None, "steps": 0, "observes": 0, "observe_images": 0,
                        "cameras": collections.Counter(), "end": None, "end_step": None}
    eps = [new(0, None)]   # episode 0 starts with the service; its first request is what counts on the timeline
    for e in events:
        c = eps[-1]
        if e["ev"] == "step":
            c["steps"] = e["step"]; c["t_last"] = e["ts"]
        elif e["ev"] == "observe":
            c["observes"] += 1; c["observe_images"] += bool(e.get("images")); c["t_last"] = e["ts"]
            c["cameras"].update(e.get("images") or [])
        elif e["ev"] == "end":
            c["end"], c["end_step"], c["t_end"] = e["reason"], e["step"], e["ts"]
        elif e["ev"] == "reset":
            eps.append(new(len(eps), e["ts"]))
    first = next((e["ts"] for e in events if e["ev"] in ("step", "observe", "reset")), None)
    eps[0]["t0"] = first
    for c in eps:
        c["cameras"] = dict(c["cameras"])
    return start, eps, events


def unquote(js: str) -> str:
    """The body of a JS/JSON string literal, as text."""
    try:
        return json.loads(f'"{js}"')
    except ValueError:
        return js


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


def codex_session(trial: str):
    """codex's session log: per-request usage, the agent's messages, its tool calls (with when their output came
    back), and the images it viewed."""
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
                entry = {"t": t, "kind": "call", "text": code, "cmds": cmds, "tools": used or [p.get("name") or "other"], "done": t}
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
                    c = open_calls.pop(p.get("call_id")); c["done"] = t
                    c["exit"] = [int(x) for x in re.findall(r'"exit_code":\s*(-?\d+)', text)]
                    c["out"] = text[:600]
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


def robot_during(events: list, t0: float, t1: float) -> dict:
    """What the sim service did while one tool call ran: control steps, observations (with images), resets."""
    ev = [e for e in events if t0 - 0.05 <= e["ts"] <= t1 + 0.05]
    return {"steps": sum(e["ev"] == "step" for e in ev), "observes": sum(e["ev"] == "observe" for e in ev),
            "images": sum(len(e.get("images") or []) for e in ev if e["ev"] == "observe"), "resets": sum(e["ev"] == "reset" for e in ev)}


def png_size(raw: bytes) -> list | None:
    return list(struct.unpack(">II", raw[16:24])) if raw[:8] == b"\x89PNG\r\n\x1a\n" else None


def camera_of(path: str | None, size: list | None, cameras: dict) -> str:
    """Which camera an image the model looked at came from, as far as its file name says; a picture of another size
    than the cameras' is something the agent made (a montage, a crop)."""
    hw = next(iter(cameras.values()), {}).get("hw") if cameras else None
    if size and hw and size != [hw[1], hw[0]]:
        return "made"
    name = os.path.basename(path or "").lower()
    for cam, key in (("room_camera", "room"), ("left_eye_camera", "left"), ("right_eye_camera", "right")):
        if key in name:
            return cam
    return "unknown"


# ------------------------------------------------------------------------------------------------ the summary
def collect(trial: str, args) -> dict:
    trial = os.path.abspath(trial.rstrip("/"))
    out = os.path.join(trial, "report"); os.makedirs(f"{out}/agent_views", exist_ok=True)
    res = json.load(open(f"{trial}/result.json"))
    cfg = res.get("config") or {}
    model = (cfg.get("agent") or {}).get("model_name") or ((res.get("agent_info") or {}).get("model_info") or {}).get("name") or "?"
    agent_name = (cfg.get("agent") or {}).get("name", "?")
    task_rel = ((cfg.get("task") or {}).get("path") or "")
    task_dir = task_rel if os.path.isabs(task_rel) else os.path.join(REPO, task_rel)
    a0, a1 = ts(res["agent_execution"]["started_at"]), ts(res["agent_execution"]["finished_at"])
    span = lambda k: [ts(res[k]["started_at"]), ts(res[k]["finished_at"])] if res.get(k) else None
    toml = open(f"{task_dir}/task.toml").read() if os.path.exists(f"{task_dir}/task.toml") else ""
    m = re.search(r"\[agent\][^\[]*?timeout_sec\s*=\s*([\d.]+)", toml)
    budget_s = float(m.group(1)) if m else None

    limited = os.path.exists(f"{trial}/artifacts/data/episode.jsonl")
    start, eps, events = sidecar(trial) if limited else ({}, [], [])
    spec = start.get("spec") or {}
    final = jload(f"{trial}/artifacts/data/final.json", {})
    reward = jload(f"{trial}/verifier/reward.json", {})
    diag = jload(f"{trial}/verifier/diagnostics.json", {})
    reqs, msgs, timeline, views, calls = codex_session(trial)
    bill = billing(reqs, model, f"{out}/billing.json") if not args.no_billing else jload(f"{out}/billing.json", {"generations": {}, "pricing": None})
    if not limited:
        replayed, replay_err = [], None
    elif args.no_replay:
        replayed, replay_err = jload(f"{out}/episodes.json", []), "skipped (--no-replay)"
    else:
        replayed, replay_err = replay(trial, task_dir, out)
    by_ep = {r["ep"]: r for r in replayed}

    # what the agent said and ran, and the images it looked at, placed in the episode running at that moment
    # (a command by when it finished: `--reset` inside it starts the episode it belongs to)
    bounds = [e["t0"] or a0 for e in eps] + [float("inf")]
    ep_at = lambda t: max(0, next(i for i in range(len(eps)) if bounds[i + 1] > t)) if eps else None
    ep_did = collections.defaultdict(list)
    for x in timeline:
        if x["kind"] == "msg":
            ep_did[ep_at(x["t"])].append([x["t"], "msg", x["text"]])
        elif x["kind"] == "call":
            for c in x["cmds"]:
                ep_did[ep_at(x["done"])].append([x["t"], "cmd", c[:600]])
    state = [(e["ts"], e.get("step", 0)) for e in events if e["ev"] in ("step", "observe", "reset")]
    for n, v in enumerate(views, 1):
        v["n"], v["ep"] = n, ep_at(v["t"])
        before = [s for s in state if s[0] <= v["t"]]
        v["step"] = before[-1][1] if before else (0 if limited else None)
        v["file"] = f"agent_views/{n:02d}_{os.path.basename(v['path'] or 'image.png')}"
        raw = base64.b64decode(v.pop("b64"))
        with open(os.path.join(out, v["file"]), "wb") as f:
            f.write(raw)
        v["size"] = png_size(raw)
        v["camera"] = camera_of(v["path"], v["size"], spec.get("cameras") or {})

    gens = [bill["generations"].get(r["id"]) for r in reqs]
    requests = [{"t": r["t"], "in": r.get("input_tokens") or 0, "cached": r.get("cached_input_tokens") or 0,
                 "write": r.get("cache_write_input_tokens") or 0, "out": r.get("output_tokens") or 0,
                 "reason": r.get("reasoning_output_tokens") or 0, "cost": (g or {}).get("usage"),
                 "gen_s": ((g or {}).get("generation_time") or 0) / 1000 or None, "lat_s": ((g or {}).get("latency") or 0) / 1000 or None,
                 "provider": (g or {}).get("provider_name")} for r, g in zip(reqs, gens)]
    price = bill.get("pricing") or {}

    def listed(r, k):   # a request's list price per token, with the long-context tier where the model has one
        tier = [o for o in price.get("overrides") or [] if (r.get("input_tokens") or 0) >= o.get("min_prompt_tokens", 1e18)]
        return float((tier[-1] if tier else price).get(k) or price.get(k) or 0)
    kinds = [("output", "completion", lambda r: r.get("output_tokens") or 0),
             ("cache read", "input_cache_read", lambda r: r.get("cached_input_tokens") or 0),
             ("cache write", "input_cache_write", lambda r: r.get("cache_write_input_tokens") or 0),
             ("uncached input", "prompt", lambda r: (r.get("input_tokens") or 0) - (r.get("cached_input_tokens") or 0) - (r.get("cache_write_input_tokens") or 0))]
    parts = [{"name": name, "usd": sum(n(r) * listed(r, k) for r in reqs), "per_m": float(price.get(k) or 0) * 1e6} for name, k, n in kinds] if price else []
    long_ctx = sum(any((r.get("input_tokens") or 0) >= o.get("min_prompt_tokens", 1e18) for o in price.get("overrides") or []) for r in reqs)

    success = bool(reward.get("success"))
    exc = (res.get("exception_info") or {}).get("exception_type")
    timed_out = bool(exc and "timeout" in exc.lower())
    budget_r = start.get("reset_budget")
    grading = {k: reward.get(k) for k in ("success", "finalized", "deterministic", "n_actions", "grader_error")}
    if limited:
        n_resets = sum(e["ev"] == "reset" for e in events)
        graded = eps[-1]; g_rep = by_ep.get(graded["ep"], {})
        best = max(replayed, key=lambda r: r.get("return", -1e18), default={})
        if graded["end"] == "success":
            why = "success"
        elif timed_out:
            why = "timeout"
        elif budget_r is not None and n_resets >= budget_r and graded["end"]:
            why = "resets_used_up"
        elif graded["end"]:
            why = "quit_after_end"
        else:
            why = "quit_mid_episode"
        result = {"success": success, "graded_ep": graded["ep"], "return": g_rep.get("return"), "bar": g_rep.get("bar") or best.get("bar"),
                  "best_ep": best.get("ep"), "best_return": best.get("return"), "why": why, "exception": exc, "timed_out": timed_out,
                  "resets": n_resets, "steps": sum(e["ev"] == "step" for e in events), "grading": grading,
                  "final": {k: final.get(k) for k in ("reason", "elapsed_s", "replay_success", "deterministic", "video")}}
        video = "artifacts/data/replay.mp4"
    else:   # the verifier replayed the one trajectory the agent submitted
        rets = diag.get("episode_return") or []
        why = ("success" if success else "no_trajectory" if reward.get("missing_trajectory") else
               "grader_error" if reward.get("grader_error") else "below_bar")
        result = {"success": success, "graded_ep": None, "return": rets[0] if rets else None, "bar": diag.get("success_bar"),
                  "best_ep": None, "best_return": None, "why": why, "exception": exc, "timed_out": timed_out,
                  "resets": None, "steps": reward.get("n_actions"), "grading": grading, "final": {}}
        video = "verifier/replay.mp4"
    spikes, prev = [], None
    for r in reqs:
        if prev and r.get("input_tokens", 0) > 1.8 * prev and r["input_tokens"] - prev > 15000:
            spikes.append([r["t"], prev, r["input_tokens"]])
        prev = r.get("input_tokens") or prev
    leaks = [[x["t"], x["kind"], LEAK.search(x["text"]).group(0), x["text"][:240]] for x in timeline
             if x["kind"] in ("msg", "call") and LEAK.search(x["text"])]

    episodes = []
    for e in eps:
        r = by_ep.get(e["ep"], {})
        episodes.append({**e, **{k: r.get(k) for k in ("return", "max_dx", "final_dx", "final_z", "video", "poster", "exact")},
                         "views": sum(v["ep"] == e["ep"] for v in views), "did": ep_did.get(e["ep"], [])})
    summary = {
        "version": VERSION, "generated_by": GENERATED_BY, "trial": res.get("trial_name"), "trial_dir": trial,
        "job": os.path.basename(os.path.dirname(trial)), "task_name": res.get("task_name", "").split("/")[-1],
        "task_dir": task_dir, "mode": "limited" if limited else "full", "model": model, "agent": agent_name,
        "effort": ((cfg.get("agent") or {}).get("kwargs") or {}).get("reasoning_effort"), "a0": a0, "a1": a1, "budget_s": budget_s,
        "stages": {k: span(k) for k in ("environment_setup", "agent_setup", "agent_execution", "verifier")} | {"trial": [ts(res["started_at"]), ts(res["finished_at"])]},
        "spec": {"reset_budget": budget_r, "proprio": bool(spec.get("proprio")), "imu": bool(spec.get("imu")),
                 "cameras": list((spec.get("cameras") or {}).keys()), "control_hz": spec.get("control_hz"),
                 "max_steps": spec.get("max_episode_steps"), "task_text": spec.get("task_text")},
        "result": result, "video": video if os.path.exists(f"{trial}/{video}") else None,
        "episodes": episodes, "replay_error": replay_err,
        "requests": requests, "billed": {"usd": sum(r["cost"] or 0 for r in requests), "found": sum(g is not None for g in gens),
                                         "harbor_usd": (res.get("agent_result") or {}).get("cost_usd"), "parts": parts, "long_context": long_ctx},
        "calls": [{"t0": x["t"], "t1": x["done"], "tools": x["tools"], "label": call_label(x["text"])[:300],
                   "cmds": [c[:800] for c in x["cmds"]], "exit": x.get("exit", []), "out": x.get("out", ""),
                   "robot": robot_during(events, x["t"], x["done"])} for x in timeline if x["kind"] == "call"],
        "tool_counts": dict(calls.most_common()),
        "msgs": [[t, txt] for t, txt in msgs], "views": views, "spikes": spikes, "leaks": leaks,
    }
    json.dump(summary, open(f"{out}/summary.json", "w"), ensure_ascii=False, indent=1)
    if not args.no_harbor:
        harbor_files(trial, summary, os.path.join(out, "notes.md"))
    return summary


def harbor_files(trial, s, notes) -> list:
    """The two files `harbor view` looks for, written only where they are missing or were written by this script."""
    said = []
    vid, rec = f"{trial}/{s['video']}", f"{trial}/agent/recording.mp4"
    if s["video"] and not os.path.exists(rec):
        shutil.copyfile(vid, rec); said.append("agent/recording.mp4")
    path = f"{trial}/analysis.json"
    if not os.path.exists(path) or (jload(path, {}) or {}).get("generated_by") == GENERATED_BY:
        r = s["result"]
        fmt = lambda v: "—" if v is None else f"{v:,.2f}"
        head = (f"**{'PASS' if r['success'] else 'FAIL'}** · {s['mode']} mode · graded return {fmt(r['return'])} / {fmt(r['bar'])} · "
                + (f"{len(s['episodes'])} episodes · " if s["episodes"] else "")
                + f"agent {(s['a1'] - s['a0']) / 60:.1f} min · ${s['billed']['usd'] or s['billed']['harbor_usd'] or 0:.4f}")
        if s["episodes"]:
            g = s["episodes"][-1]
            graded = (f"Episode {g['ep']} (the last) was graded: {g['steps']} steps, ended {g['end'] or 'by the agent'}, "
                      f"return {fmt(r['return'])}, pass mark {fmt(r['bar'])}")
        else:
            graded = (f"The submitted trajectory ({r['steps'] or 0} actions) replayed to return {fmt(r['return'])}, pass mark {fmt(r['bar'])}"
                      if r["why"] != "no_trajectory" else "No trajectory.npz was submitted")
        body = open(notes).read() if os.path.exists(notes) else "(No strategy summary yet: report/notes.md)"
        flagged = s["spikes"] or s["leaks"]
        checks = {
            "leak_grep": {"outcome": "fail" if flagged else "pass",   # fail = flagged for a human look, not proof of a leak
                          "explanation": "Flagged for a human look (not necessarily a leak): "
                          + "; ".join([f"{(t - s['a0']) / 60:.2f} min {w}" for t, _, w, _ in s["leaks"][:5]]
                                      + [f"{(t - s['a0']) / 60:.2f} min input {a:,} → {b:,}" for t, a, b in s["spikes"]])
                          if flagged else "No input-token jumps, no suspicious words in what the agent wrote or ran (LEAK in scripts/results/collect.py)"},
            "graded": {"outcome": "pass" if r["success"] else "fail", "explanation": graded},
        }
        json.dump({"trial_name": s["trial"], "summary": head + "\n\n" + body, "checks": checks,
                   "estimated_cost_usd": None, "generated_by": GENERATED_BY}, open(path, "w"), ensure_ascii=False, indent=2)
        said.append("analysis.json")
    return said


def trials_under(paths: list[str]) -> list[str]:
    trials = []
    for p in (os.path.abspath(x.rstrip("/")) for x in paths):
        trials += [p] if os.path.isdir(f"{p}/agent") else sorted(d.rstrip("/") for d in glob.glob(f"{p}/*/") if os.path.isdir(f"{d}/agent"))
    return trials


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="job dirs (every trial in each) or trial dirs")
    ap.add_argument("--no-replay", action="store_true")
    ap.add_argument("--no-billing", action="store_true")
    ap.add_argument("--no-harbor", action="store_true")
    args = ap.parse_args()
    trials = trials_under(args.paths)
    if not trials:
        sys.exit(f"no trial under {args.paths}")
    for t in trials:
        if not os.path.exists(f"{t}/result.json"):
            print(f"skip {t}: no result.json (still running?)"); continue
        s = collect(t, args)
        print(f"{t}/report/summary.json: {s['mode']} mode, {len(s['episodes'])} episodes, {len(s['requests'])} requests"
              + (f"; replay: {s['replay_error']}" if s["replay_error"] else ""))


if __name__ == "__main__":
    main()
