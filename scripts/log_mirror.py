"""Append-only mirror of every agent trial's log directory (<src>/<job>/<trial>/agent/ -> <mirror>/<same path>).

The agent runs as root in its container and /logs/agent is a writable bind mount, so it could delete or rewrite its own
record (the harness's stream, its session files, its trajectory). This process runs outside every trial container and
keeps a copy that is only ever added to (a runner-side tool, not task code):
  * append-type logs (.jsonl .txt .log .err): each new byte is appended to the mirror as it is written; if the source
    shrinks, is replaced (new inode) or has its already-mirrored tail rewritten, everything mirrored so far stays and the
    file continues in a new segment (<name>.seg1, ...);
  * any other file: every version it takes is kept (<name>.v0, .v1, ...);
  * a file that disappears keeps its mirror.
Every such event goes to <mirror>/TAMPER.log. Run it as root in a container so the host user cannot delete the mirror
either (scripts/run_agent_batch.sh starts one: rcb-log-mirror).

  python3 log_mirror.py --src jobs/agents --mirror jobs/agents_mirror [--interval 5] [--once]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import time

SRC, MIRROR, STATE = "", "", ""
APPEND_EXT = (".jsonl", ".txt", ".log", ".err")
TAIL = 4096


def event(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with open(os.path.join(MIRROR, "TAMPER.log"), "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def tail_hash(path: str, end: int) -> str:
    with open(path, "rb") as f:
        f.seek(max(0, end - TAIL))
        return hashlib.sha256(f.read(min(TAIL, end))).hexdigest()


def sync_append(src: str, rel: str, st: os.stat_result, s: dict | None) -> dict:
    if s is None:
        s = {"ino": st.st_ino, "off": 0, "seg": 0, "tail": ""}
    changed = st.st_ino != s["ino"] or st.st_size < s["off"]
    if not changed and s["off"] and tail_hash(src, s["off"]) != s["tail"]:
        changed = True
    if changed:
        event(f"{rel}: replaced, truncated or rewritten (mirrored {s['off']} bytes, now {st.st_size}, inode "
              f"{s['ino']} -> {st.st_ino}); kept, continuing in segment {s['seg'] + 1}")
        s = {"ino": st.st_ino, "off": 0, "seg": s["seg"] + 1, "tail": ""}
    if st.st_size > s["off"]:
        dst = os.path.join(MIRROR, rel) + (f".seg{s['seg']}" if s["seg"] else "")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as fi, open(dst, "ab") as fo:
            fi.seek(s["off"])
            data = fi.read(st.st_size - s["off"])
            fo.write(data)
        s["off"] += len(data)
        s["tail"] = tail_hash(src, s["off"])
    return s


def sync_version(src: str, rel: str, st: os.stat_result, s: dict | None) -> dict:
    sig = [st.st_ino, st.st_size, st.st_mtime_ns]
    if s is not None and s.get("sig") == sig:
        return s
    n = 0 if s is None else s["n"] + 1
    dst = os.path.join(MIRROR, rel) + f".v{n}"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return {"sig": sig, "n": n}


def once(state: dict) -> None:
    seen = set()
    for agent_dir in glob.glob(os.path.join(SRC, "*", "*", "agent")):
        for root, _, files in os.walk(agent_dir):
            for name in files:
                src = os.path.join(root, name)
                rel = os.path.relpath(src, SRC)
                seen.add(rel)
                try:
                    st = os.stat(src)
                    fn = sync_append if name.endswith(APPEND_EXT) else sync_version
                    state[rel] = fn(src, rel, st, state.get(rel))
                    state[rel].pop("gone", None)
                except (FileNotFoundError, PermissionError):
                    continue
    for rel, s in state.items():
        if rel not in seen and not s.get("gone"):
            s["gone"] = True
            event(f"{rel}: disappeared from the trial directory; its mirror is kept")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--mirror", required=True)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    global SRC, MIRROR, STATE
    SRC, MIRROR = os.path.abspath(a.src), os.path.abspath(a.mirror); STATE = os.path.join(MIRROR, ".state.json")
    os.makedirs(MIRROR, exist_ok=True)
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    while True:
        once(state)
        tmp = STATE + ".tmp"
        json.dump(state, open(tmp, "w"))
        os.replace(tmp, STATE)
        if a.once:
            return
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
