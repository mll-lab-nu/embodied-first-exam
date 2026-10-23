"""The images the agent received (the camera views it asked for), saved per event, so the review page and the
full-trial video show what the agent saw at that moment. Walks trajectory.json in the same order as atif.events, so
event ids match events/K.jsonl. Images are in the log only when the harness keeps them (Codex, Claude Code; not
Antigravity). usage: python -m pipeline looks [--keys K ...]  ->  looks/K/<eid>-<n>.jpg, looks/K/index.json"""
from __future__ import annotations
import argparse, base64, io, json, os, re
from PIL import Image
from .paths import DATA, keys, jdump
from .logs import trajectory
import atif

B64 = re.compile(r"data:image/(?:png|jpe?g|webp);base64,([A-Za-z0-9+/=]+)")
RAWB64 = re.compile(r'"data": ?"([A-Za-z0-9+/=]{400,})"')     # Claude Code: {"type": "image", "source": {"data": ...}}
WIDTH = 640


def blobs(content) -> list[bytes]:
    s = atif._text(content)
    out = []
    for b in B64.findall(s) or RAWB64.findall(s):
        try:
            out.append(base64.b64decode(b))
        except ValueError:
            pass
    return out


def per_event(traj: dict) -> list[list[bytes]]:
    """One list of images per event, in atif.events order."""
    out = []
    for s in traj.get("steps") or []:
        obs = s.get("observation") or {}
        results = {r.get("source_call_id"): r.get("content") for r in obs.get("results", []) if isinstance(r, dict)}
        if s.get("source") == "agent" and atif._text(s.get("reasoning_content")).strip():
            out.append([])
        if s.get("source") == "agent" and atif._text(s.get("message")).strip():
            out.append([])
        for c in s.get("tool_calls") or []:
            out.append(blobs(results.get(c.get("tool_call_id"))))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline looks")
    ap.add_argument("--keys", nargs="*")
    a = ap.parse_args(argv)
    for k in keys(a.keys):
        ev = [json.loads(l) for l in open(f"{DATA}/events/{k}.jsonl")]
        imgs = per_event(trajectory(k))
        assert len(imgs) == len(ev), (k, len(imgs), len(ev))
        d, index = f"{DATA}/looks/{k}", {}
        os.makedirs(d, exist_ok=True)
        for e, bs in zip(ev, imgs):
            for n, b in enumerate(bs):
                im = Image.open(io.BytesIO(b)).convert("RGB")
                if im.width > WIDTH:
                    im = im.resize((WIDTH, round(im.height * WIDTH / im.width)))
                im.save(f"{d}/{e['id']}-{n}.jpg", quality=82)
                index.setdefault(e["id"], []).append(f"{e['id']}-{n}.jpg")
        jdump(index, f"{d}/index.json")
        print(f"有图的事件 {len(index):3d}，图 {sum(map(len, index.values())):3d}  {k}")
