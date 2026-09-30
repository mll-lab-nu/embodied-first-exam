"""Render the first frame of seeded scene variants and collect them into one HTML report.

For each task and seed, a separate process builds
``topogym.make(task, variation_id="seeded", seed=seed)``, resets it (no physics step)
and saves every fixed camera's RGB frame plus the tier and the seeded draw. Seeds
0/1/2 cover easy/medium/hard; seed 3 is easy again, so seeds 0 and 3 show the
variation inside one tier. The parent stops (and ends a running render) when
system memory or GPU memory use exceeds --limit; rerunning resumes and skips
successful renders (failed ones are retried). The report embeds downscaled JPEGs, so it is one file.

Usage (shared host: cap CPU with taskset):
  PYTHONPATH=. taskset -c 28-31 .venv-gs121-nyx/bin/python scripts/render_seeded_initial_frames.py \\
      --out runs/test_results/seeded_initial_frames_20260929 [--tasks horseshoe_ring ...] [--seeds 0 1 2 3]
  ... --report-only    # rebuild report.html from what is already rendered
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Rigid tasks first (small GPU footprint); FEM/IPC and the frozen-PBD blanket last.
TASKS = ("horseshoe_ring", "cast_coil", "cast_keyhole", "hedgehog_in_cage", "lock_picking", "buzz_wire_3d",
         "fiber_bundling", "interlocked_claws", "knot_untying", "rope_threading", "slotted_post_ring", "orbits",
         "blanket_flatten")
PRIMARY_CAMERA = ("cam_high", "agentview")


def usage():
    """(system memory fraction in use, largest GPU memory fraction in use)."""
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        info[key] = int(value.split()[0])
    ram = 1 - info["MemAvailable"]/info["MemTotal"]
    try:
        rows = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
        gpu = max(float(u)/float(t) for u, t in (row.split(",") for row in rows))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        gpu = 0.
    return ram, gpu


def worker(task, seed, out):
    import numpy as np
    from PIL import Image
    import topogym
    from topogym.config.registry import task_definition
    from topogym.tasks.base import _parameter_at
    from topogym.tasks.scene_variation import axes, draw
    folder = out/task/f"seed_{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    cls = task_definition(task, "seeded", seed)
    draws = draw(cls, seed)
    changes = []
    for axis in axes(cls):
        value, base = _parameter_at(draws, axis["path"]), _parameter_at(cls.defaults, axis["path"])
        if axis["kind"] == "offset":
            delta = np.atleast_1d(np.asarray(value, float)-np.asarray(base, float))
            if "deg" in axis["path"]:
                text = ", ".join(f"{d:+.1f}°" for d in delta)
            elif "tint" in axis["path"] or "shade" in axis["path"]:
                text = ", ".join(f"×{v:.2f}" for v in np.atleast_1d(value))
            else:
                text = ", ".join(f"{d*100:+.1f} cm" for d in delta if abs(d) > 0 or len(delta) < 3)
            changes.append(dict(path=axis["path"], change=f"Δ {text}" if "×" not in text else text))
        else:
            changes.append(dict(path=axis["path"], change=json.dumps(value)))
    meta = dict(task_id=task, seed=seed, variation=cls.variation_id, difficulty=cls.difficulty, changes=changes)
    start = time.time()
    try:
        env = topogym.make(task, variation_id="seeded", seed=seed, enable_rgb=True, enable_depth=False,
                           history_storage="memory", max_physics_steps=None)
        try:
            env.reset()
            frame = env.sensor_frame()
            meta["instance_id"] = env.episode_metadata["instance_id"]
            meta["frames"] = {}
            for name, pixels in frame.rgb.items():
                if "wrist" in name:
                    continue
                Image.fromarray(np.asarray(pixels)).save(folder/f"{name}.png")
                meta["frames"][name] = f"{name}.png"
        finally:
            env.close()
    except Exception as error:  # noqa: BLE001 - reported per render, e.g. a blanket seed not yet prepared
        meta["error"] = f"{type(error).__name__}: {error}"
    meta["seconds"] = round(time.time()-start, 1)
    (folder/"meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))


def thumbnail(path, width=640):
    from PIL import Image
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((width, width))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def build_report(out, tasks, seeds):
    sections = []
    for task in tasks:
        cards = []
        for seed in seeds:
            meta_path = out/task/f"seed_{seed}"/"meta.json"
            if not meta_path.exists():
                cards.append(f'<figure class="card missing"><div class="ph">not rendered</div>'
                             f'<figcaption><b>seed {seed}</b></figcaption></figure>')
                continue
            meta = json.loads(meta_path.read_text())
            frames = meta.get("frames") or {}
            primary = next((n for n in PRIMARY_CAMERA if n in frames), next(iter(frames), None))
            image = (f'<img src="{thumbnail(meta_path.parent/frames[primary])}" alt="{html.escape(task)} seed {seed}">'
                     if primary else f'<div class="ph">{html.escape(meta.get("error", "no frame"))}</div>')
            rows = "".join(f"<li><code>{html.escape(c['path'])}</code> {html.escape(c['change'])}</li>"
                           for c in meta["changes"])
            cards.append(f'<figure class="card{" failed" if "error" in meta else ""}">{image}<figcaption>'
                         f'<b>seed {seed}</b> · {html.escape(str(meta["difficulty"]))} · '
                         f'{html.escape(primary or "")}<ul>{rows}</ul></figcaption></figure>')
        sections.append(f'<section><h2>{html.escape(task)}</h2><div class="grid">{"".join(cards)}</div></section>')
    page = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Seeded Variant Frames</title>
<style>
:root{{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e2e2dc;--bad:#b3261e}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#161615;--fg:#ececea;--muted:#a3a39c;--card:#21211f;--line:#34342f;--bad:#f2b8b5}}}}
:root[data-theme="dark"]{{--bg:#161615;--fg:#ececea;--muted:#a3a39c;--card:#21211f;--line:#34342f;--bad:#f2b8b5}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif}}
main{{max-width:1400px;margin:0 auto}} h1{{font-size:22px;margin:0 0 4px}} p.lead{{color:var(--muted);margin:0 0 20px}}
h2{{font-size:17px;margin:28px 0 10px}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}}
.card{{margin:0;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}}
.card img{{display:block;width:100%;height:auto}} .card figcaption{{padding:8px 10px}}
.card ul{{margin:4px 0 0;padding-left:16px;color:var(--muted)}} .ph{{aspect-ratio:848/480;display:flex;align-items:center;
justify-content:center;padding:12px;color:var(--muted);text-align:center;font-size:12px}} .failed .ph{{color:var(--bad)}}
code{{font-size:12px}}
</style></head><body><main>
<h1>Seeded variant first frames</h1>
<p class="lead"><code>variation_id="seeded"</code>: tier = seed % 3 (0 easy, 1 medium, 2 hard; seed 3 is easy again), plus the seed's
position/orientation/appearance draw. Frames are taken right after reset, before any physics step. Δ is relative to the tier's nominal scene.</p>
{"".join(sections)}
</main></body></html>"""
    (out/"report.html").write_text(page)
    return out/"report.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tasks", nargs="*", default=list(TASKS))
    parser.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2, 3])
    parser.add_argument("--limit", type=float, default=.90, help="stop when system or GPU memory use exceeds this")
    parser.add_argument("--timeout", type=float, default=1800, help="seconds per render")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--worker", nargs=2, metavar=("TASK", "SEED"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.worker:
        worker(args.worker[0], int(args.worker[1]), out)
        return
    out.mkdir(parents=True, exist_ok=True)
    stopped = None
    for task in [] if args.report_only else args.tasks:
        for seed in args.seeds:
            done = out/task/f"seed_{seed}"/"meta.json"
            if done.exists() and "error" not in json.loads(done.read_text()):
                continue  # failed renders (e.g. CUDA OOM, blanket seed not prepared) are retried
            ram, gpu = usage()
            if ram > args.limit or gpu > args.limit:
                stopped = f"before {task} seed {seed}: memory {ram:.0%}, GPU memory {gpu:.0%} > {args.limit:.0%}"
                break
            print(f"[render] {task} seed {seed} (memory {ram:.0%}, GPU memory {gpu:.0%})", flush=True)
            child = subprocess.Popen([sys.executable, __file__, "--out", str(out), "--worker", task, str(seed)],
                                     stdin=subprocess.DEVNULL, env=os.environ.copy())
            start = time.time()
            while child.poll() is None:
                time.sleep(2)
                ram, _ = usage()
                if ram > args.limit:
                    child.terminate()
                    child.wait(60)
                    stopped = f"during {task} seed {seed}: memory {ram:.0%} > {args.limit:.0%}"
                    break
                if time.time()-start > args.timeout:
                    child.terminate()
                    child.wait(60)
                    print(f"[timeout] {task} seed {seed} after {args.timeout:.0f} s", flush=True)
                    break
            if stopped:
                break
            meta = out/task/f"seed_{seed}"/"meta.json"
            if meta.exists():
                result = json.loads(meta.read_text())
                print(f"[done] {task} seed {seed}: {result.get('error', 'ok')} ({result['seconds']} s)", flush=True)
        if stopped:
            break
    report = build_report(out, args.tasks, args.seeds)
    print(f"[report] {report}")
    if stopped:
        print(f"[stopped] {stopped}; rerun the same command to resume")
        sys.exit(3)


if __name__ == "__main__":
    main()
