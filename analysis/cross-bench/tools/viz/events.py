#!/usr/bin/env python3
"""Event list of one standard-mode trial: commands, looks, results, agent sentences, in wall-clock order.

usage: events.py RAWDIR OUT.json
Each event: {t (s from first agent step), kind: cmd|look|result|say, ...}.
`result` carries the cumulative physics step reported by the service; `look` carries the images the agent viewed
(saved next to OUT.json under looks/).
"""
import base64, datetime, json, os, re, sys

raw, out = sys.argv[1], sys.argv[2]
looks_dir = os.path.join(os.path.dirname(out), "looks")
os.makedirs(looks_dir, exist_ok=True)
steps = json.load(open(os.path.join(raw, "agent/trajectory.json")))["steps"]

CHARS = re.compile(r'write_stdin\(\{session_id:\d+,chars:"((?:[^"\\]|\\.)*)"')
VIEW = re.compile(r'view_image\(\{path:["`]([^"`]+)["`]')
LOOP = re.compile(r"for ?\(const cam of \[([^\]]+)\]\)")
RESULT = re.compile(r"RESULT (\d+) \{(.*?)\}\\\\r")
B64 = re.compile(r"data:image/jpeg;base64,([A-Za-z0-9+/=]+)")


def num(body, key):
    m = re.search(rf"\\'{key}\\': ([-\d.]+|None|True|False)", body)
    return None if not m or m.group(1) in ("None",) else m.group(1)


ev, t0 = [], None
for s in steps:
    if s.get("source") != "agent":
        continue
    ts = datetime.datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))
    t0 = t0 or ts
    t = round((ts - t0).total_seconds(), 1)
    msg = (s.get("message") or "").strip()
    if msg:
        ev.append({"t": t, "step": s["step_id"], "kind": "say", "text": msg})
    for c in s.get("tool_calls") or []:
        src = c["arguments"].get("input", "")
        # order inside one call: by position in the source
        items = []
        for m in CHARS.finditer(src):
            for line in m.group(1).encode().decode("unicode_escape").split("\n"):
                if line.strip():
                    items.append((m.start(), "cmd", line.strip()))
        paths = [m.group(1) for m in VIEW.finditer(src)]
        loop = LOOP.search(src)
        if loop:
            paths = [paths[0].replace("${cam}", x.strip(" '\"")) for x in loop.group(1).split(",")] if paths else []
        if paths:
            pos = src.find("view_image")
            items.append((pos, "look", paths))
        # the agent gets the images only when the whole call returns: every command written in the same call was
        # decided before it saw them, so the look goes after them
        for _, kind, val in sorted(items, key=lambda x: (x[1] == "look", x[0])):
            if kind == "cmd":
                ev.append({"t": t, "step": s["step_id"], "kind": "cmd", "text": val})
            else:
                ev.append({"t": t, "step": s["step_id"], "kind": "look", "paths": val, "files": []})
    obs = s.get("observation") or {}
    imgs, text = [], ""
    for r in obs.get("results", []):
        content = str(r.get("content", ""))
        imgs += B64.findall(content)
        text += content
    for m in RESULT.finditer(text):
        body = m.group(2)
        ev.append({"t": t, "step": s["step_id"], "kind": "result", "n": int(m.group(1)),
                   "physics_steps": int(num(body, "physics_steps")), "type": (re.search(r"\\'type\\': \\'(\w+)\\'", body) or [None, "obs"])[1],
                   "done": num(body, "done") == "True", "plan": re.findall(r"\\'(left|right)\\': \\'(\w+)\\'", body)})
    if imgs:
        look = next((e for e in reversed(ev) if e["kind"] == "look" and e["step"] == s["step_id"]), None)
        for i, b in enumerate(imgs):
            fn = os.path.join(looks_dir, f"{s['step_id']:03d}_{i}.jpg")
            open(fn, "wb").write(base64.b64decode(b))
            if look is not None:
                look["files"].append(os.path.basename(fn))

json.dump(ev, open(out, "w"), indent=1)
kinds = {}
for e in ev:
    kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
print(kinds, "last physics", max((e["physics_steps"] for e in ev if e["kind"] == "result"), default=None))
