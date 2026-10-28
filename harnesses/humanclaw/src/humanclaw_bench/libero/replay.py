"""Three explicit operations: inspect logs, replay controls, or rerun an agent."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import uuid

import numpy as np


def log_replay(directory):
    """Build an offline timeline linking original events, images and controls."""
    directory = Path(directory)
    rows = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    if (directory / "motion.sqlite").exists():
        with sqlite3.connect(f"file:{directory / 'motion.sqlite'}?mode=ro", uri=True) as db:
            commands = {ident: json.loads(action) for ident, action in db.execute("SELECT id,action FROM steps")}
        for row in rows:
            if row["event"] == "control.step.end":
                row["data"]["actual_controller_command"] = commands.get(row["data"].get("row_id"))
    data = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c")
    page = r"""<!doctype html><meta charset="utf-8"><title>LIBERO-Pro run log</title>
<style>body{font:15px system-ui;margin:24px}table{border-collapse:collapse;width:100%}td,th{padding:7px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:400px}button{cursor:pointer}#detail{padding:18px;background:#f5f5f5}</style>
<h1>LIBERO-Pro log replay</h1><p>This view reads recorded events only. It makes no model requests and executes no robot actions.</p>
<input id="filter" placeholder="Filter event, operation or span"><table><thead><tr><th>Sequence</th><th>Time</th><th>Event</th><th>Operation</th><th>Span / parent</th></tr></thead><tbody id="rows"></tbody></table><div id="detail"></div>
<script type="application/json" id="data">REPLACE_DATA</script><script>
const rows=JSON.parse(document.getElementById('data').textContent), body=document.getElementById('rows'),detail=document.getElementById('detail');
function show(e){detail.replaceChildren();const p=document.createElement('pre');p.textContent=JSON.stringify(e,null,2);detail.append(p);function visit(v){if(!v||typeof v!=='object')return;if(typeof v.artifact==='string'&&v.media_type?.startsWith('image/')&&/^artifacts\/[a-f0-9]+\.(png|jpg|webp|gif)$/.test(v.artifact)){const i=document.createElement('img');i.src=v.artifact;detail.append(i)}else Object.values(v).forEach(visit)}visit(e);detail.scrollIntoView({block:'start'})}
function render(){body.replaceChildren();const q=document.getElementById('filter').value.toLowerCase();for(const e of rows){if(q&&!JSON.stringify([e.event,e.name,e.span_id,e.parent_span_id]).toLowerCase().includes(q))continue;const tr=document.createElement('tr');for(const value of [e.sequence,e.timestamp_utc,e.event,e.name,(e.span_id||'')+' / '+(e.parent_span_id||'')]){const td=document.createElement('td');td.textContent=value;tr.append(td)}tr.onclick=()=>show(e);body.append(tr)}}document.getElementById('filter').oninput=render;render();</script>"""
    path = directory / "replay.html"
    path.write_text(page.replace("REPLACE_DATA", data))
    return path


def physics_replay(directory, *, roboroot, tolerance=1e-6):
    """Restore state and compare recorded control execution without model calls."""
    from .backend import RoboBackend
    from .provenance import framework_identity
    directory = Path(directory)
    with sqlite3.connect(f"file:{directory / 'motion.sqlite'}?mode=ro", uri=True) as db:
        initial = json.loads(db.execute("SELECT value FROM metadata WHERE key='initial'").fetchone()[0])
        controls = db.execute("SELECT id,action,after_state,status FROM steps WHERE phase='episode' ORDER BY id").fetchall()
    if any(row[3] != "completed" for row in controls):
        raise ValueError("Cannot certify physical replay: original execution includes incomplete control steps")
    output = directory / "physics_replays" / uuid.uuid4().hex
    output.mkdir(parents=True)
    framework = framework_identity()
    (output / "framework.json").write_text(json.dumps(framework, indent=2))
    backend = RoboBackend(initial["task"], initial["seed"], output, roboroot=roboroot,
                         resolution=initial["resolution"], settle_steps=initial["settle_steps"])
    differences = []
    try:
        original_runtime = json.loads((directory / "capabilities.json").read_text())
        current_runtime = backend.manifest()
        drift = {key: {"recorded": original_runtime.get(key), "replay": current_runtime.get(key)}
                 for key in ("versions", "scene_sha256", "controller", "action_dimension", "bddl", "catalog_hash")
                 if original_runtime.get(key) != current_runtime.get(key)}
        backend.restore(initial["snapshot"])
        backend.phase = "replay"
        for ident, action, expected, _ in controls:
            backend.env._env.step(np.asarray(json.loads(action), dtype=np.float64))
            observed, expected = backend.state(), json.loads(expected)
            errors = {k: (float(np.max(np.abs(np.asarray(observed[k])-np.asarray(expected[k])), initial=0))
                          if np.asarray(observed[k]).shape == np.asarray(expected[k]).shape else None)
                      for k in ("qpos", "qvel", "act")}
            differences.append({"row_id": ident, **errors})
        success = backend.success()
        original = json.loads((directory / "run.json").read_text())["outcome"].get("benchmark_success")
        maximum = {key: (max((d[key] for d in differences), default=0.0)
                        if all(d[key] is not None for d in differences) else None)
                   for key in ("qpos", "qvel", "act")}
        result = {"mode": "physics_replay", "model_requests": 0, "control_steps": len(controls),
                  "replay_framework_source_sha256": framework["actual_source_sha256"],
                  "tolerance": tolerance, "max_absolute_error": maximum,
                  "state_consistent": all(x is not None and x <= tolerance for x in maximum.values()),
                  "original_success": original, "replay_success": success,
                  "success_consistent": success == original if original is not None else None,
                  "configuration_drift": drift,
                  "differences": differences, "runtime": backend.manifest(),
                  "note": "Tolerance comparison, not a bitwise-reproducibility guarantee across machines/dependencies."}
        (output / "report.json").write_text(json.dumps(result, indent=2))
        return result, output
    finally:
        backend.close()
