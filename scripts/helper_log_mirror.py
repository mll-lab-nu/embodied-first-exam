"""Strict, bounded-memory helper adapter for the pinned upstream log mirror."""
import argparse
import glob
import json
import os
import time
import log_mirror as upstream

SRC = MIRROR = STATE = ""
STRICT = True
APPEND_EXT = upstream.APPEND_EXT
event = upstream.event
tail_hash = upstream.tail_hash
def sync_version(src, rel, st, state):
    value = upstream.sync_version(src, rel, st, state)
    # copy2 preserves root-only source modes; mirror versions must be readable
    # by the receiver without changing the original agent-owned file.
    os.chmod(os.path.join(MIRROR, rel) + f".v{value['n']}", 0o644)
    return value

def walk_error(error):
    raise error

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
            remaining = st.st_size - s["off"]
            while remaining:
                data = fi.read(min(1024 * 1024, remaining))
                if not data:
                    break
                fo.write(data)
                s["off"] += len(data)
                remaining -= len(data)
        s["tail"] = tail_hash(src, s["off"])
    return s


def once(state: dict) -> None:
    seen = set()
    for agent_dir in glob.glob(os.path.join(SRC, "*", "*", "agent")):
        if any(os.path.islink(p) for p in (agent_dir, os.path.dirname(agent_dir), os.path.dirname(os.path.dirname(agent_dir)))):
            if STRICT: raise ValueError("symlinked agent directory")
            continue
        for root, dirs, files in os.walk(agent_dir, onerror=walk_error):
            if any(os.path.islink(os.path.join(root, d)) for d in dirs):
                raise ValueError("symlinked agent subdirectory")
            for name in files:
                src = os.path.join(root, name)
                rel = os.path.relpath(src, SRC)
                seen.add(rel)
                try:
                    if os.path.islink(src):
                        if STRICT: raise ValueError("symlinked agent record")
                        continue
                    st = os.stat(src)
                    fn = sync_append if name.endswith(APPEND_EXT) else sync_version
                    state[rel] = fn(src, rel, st, state.get(rel))
                    state[rel].pop("gone", None)
                except FileNotFoundError:
                    continue
                except PermissionError:
                    if STRICT: raise
    for rel, s in state.items():
        if rel not in seen and not s.get("gone"):
            s["gone"] = True
            event(f"{rel}: disappeared from the trial directory; its mirror is kept")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--mirror", required=True)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--ready-file")
    ap.add_argument("--protect-root", action="store_true", help="trusted native batch: root-only raw history")
    a = ap.parse_args()
    global SRC, MIRROR, STATE, STRICT
    STRICT = a.strict
    os.umask(0o022)
    SRC, MIRROR = os.path.abspath(a.src), os.path.abspath(a.mirror); STATE = os.path.join(MIRROR, ".state.json")
    upstream.MIRROR = MIRROR
    os.makedirs(MIRROR, exist_ok=True)
    if a.protect_root:
        if os.geteuid() != 0: raise ValueError('protected mirror requires root')
        os.chown(MIRROR, 0, 0); os.chmod(MIRROR, 0o700)
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    while True:
        once(state)
        tmp = STATE + ".tmp"
        json.dump(state, open(tmp, "w"))
        os.replace(tmp, STATE)
        if a.ready_file:
            with open(a.ready_file, "w") as ready: ready.write("ready\n")
            a.ready_file = None
        if a.once:
            return
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
