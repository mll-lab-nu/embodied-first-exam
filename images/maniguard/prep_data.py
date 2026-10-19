#!/usr/bin/env python3
"""Prepare $RCB_MANIGUARD_DATA, the host's BEHAVIOR-1K 3.7.2 data root that every ManiGuard task mounts read-only at /data
(tasks/maniguard/README.md). Host side, Python 3 standard library only; never run inside a task.

    python3 images/maniguard/prep_data.py --root /path/maniguard_data --key /path/to/omnigibson.key            # task subset
    python3 images/maniguard/prep_data.py --root /path/maniguard_data --key /path/to/omnigibson.key --full     # every member
    python3 images/maniguard/prep_data.py --root /path/maniguard_data --check                                  # verify only

What it writes (the layout OmniGibson 3.7.2 reads with OMNIGIBSON_DATA_PATH=/data):
  behavior-1k-assets/       members of behavior-1k-assets-3.7.2rc1.zip (Hugging Face behavior-1k/zipped-datasets, pinned
                            revision; the file BEHAVIOR-1K v3.7.2's asset_utils downloads). Default: only the members the
                            selected ManiGuard tasks load (VERSION, metadata/, objects/<category>/<model>/ of every
                            DatasetObject in their scene snapshots, and every particle system: objects' abilities name
                            systems by name, e.g. a pepper shaker's black_pepper), read from the zip by HTTP range requests;
                            --full: every member, streamed (no zip is stored either way).
  omnigibson-robot-assets/  every member of omnigibson-robot-assets.zip (the 2025-09-02 file BEHAVIOR-1K 3.7.2 downloads),
                            plus ManiGuard's long-finger Franka at models/franka/franka_panda_longfinger/ (Hugging Face
                            IDEAS-Lab-Northwestern/franka-panda-longfinger, pinned revision, Apache-2.0).
  omnigibson.key            copied from --key: the BEHAVIOR Data Bundle key of a licence the user already accepted. This
                            script never downloads a key and never accepts a licence on anyone's behalf.
  MANIGUARD_DATA.json       what is there: pins, member counts and digests, the tasks the subset covers.
Every member is checked against the zip's own CRC-32 and size; the long-finger files against Hugging Face's sha256 / git
blob ids. --check re-verifies an existing root against MANIGUARD_DATA.json (sizes and CRC-32 of every file)."""
from __future__ import annotations
import argparse, binascii, hashlib, json, os, pathlib, shutil, struct, sys, time, urllib.request, zlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]   # the repository (this file: images/maniguard/prep_data.py)
HF = "https://huggingface.co/datasets"
ASSETS = {"url": f"{HF}/behavior-1k/zipped-datasets/resolve/9922e2ffabbdc881e7ba1db72db91097c74cadf7/behavior-1k-assets-3.7.2rc1.zip",
          "size": 31280662307, "sha256": "3bd7cdc1a8c5621768c2aaaf57c12a024560ab4f49d0162e540e769d8b165e8b", "dest": "behavior-1k-assets"}
ROBOT = {"url": f"{HF}/behavior-1k/zipped-datasets/resolve/015e37a26823a110fedb6a0c3d943f573de00ffe/omnigibson-robot-assets.zip",
         "size": 501401227, "sha256": "5e9fe726172c8b4beb4ba4e12dbf5cf6c5791553a05c52be661eb2d6a3d241b8", "dest": "omnigibson-robot-assets"}
LONGFINGER_REV = "5f65ec0a715bc88ea865c2c69133b08b395c66bc"
LONGFINGER = {  # path in the HF repo -> ("sha256", hex) for LFS files, ("git", blob sha1) for the others
    "usd/franka_panda_longfinger.usda": ("sha256", "49424b434343b544266e49274f7a5eb0f4b3d16673d2e19100045a3988616b9b"),
    "curobo/franka_panda_longfinger_description_curobo_default.yaml": ("git", "dba47c37c3cc572881aabe724421a723143ab822"),
    "misc/metadata.json": ("git", "f747e3396445b9c959e59e24bc773089fae816d6"),
    "LICENSE": ("git", "d8184a62e171197f62c5423712dbf37090e3476f"),
    "LICENSE-OmniGibson.txt": ("git", "3883c7d16fc54952b28c4ad57e3c3f8e8e85a9e2"),
    "NOTICE": ("git", "792ed208263d24ad34dde89a9299c9a3973223e7"),
    "README.md": ("git", "d98e88464253b0d327d8ff5848616763c770edbb"),
}
LONGFINGER_DEST = "omnigibson-robot-assets/models/franka/franka_panda_longfinger"


def log(*a) -> None:
    print("[prep]", *a, file=sys.stderr, flush=True)


def get(url: str, start: int | None = None, end: int | None = None, tries: int = 6) -> bytes:
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"} if start is not None else {})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            if start is not None and len(data) != end - start + 1:
                raise IOError(f"short range read {len(data)} != {end - start + 1}")
            return data
        except Exception as exc:  # noqa: BLE001
            if k == tries - 1:
                raise
            log(f"retry {k + 1} after {exc!r}"); time.sleep(5 * (k + 1))
    raise RuntimeError("unreachable")


def central_directory(z: dict) -> list[dict]:
    """The zip's members (name, method, crc, compressed and file size, local header offset) from its central directory,
    read by range requests (zip64 aware)."""
    size = z["size"]; tail = get(z["url"], size - 65536, size - 1); base = size - len(tail)
    i = tail.rfind(b"PK\x05\x06")
    _, _, _, _, n, cd_size, cd_off, _ = struct.unpack("<IHHHHIIH", tail[i:i + 22])
    if cd_off == 0xFFFFFFFF or n == 0xFFFF:
        j = tail.rfind(b"PK\x06\x07"); _, _, z64, _ = struct.unpack("<IIQI", tail[j:j + 20])
        f = struct.unpack("<IQHHIIQQQQ", tail[z64 - base:z64 - base + 56]); n, cd_size, cd_off = f[7], f[8], f[9]
    cd = get(z["url"], cd_off, cd_off + cd_size - 1)
    out, p = [], 0
    while p < len(cd):
        if cd[p:p + 4] != b"PK\x01\x02":
            raise IOError(f"bad central directory entry at {p}")
        (_, _, _, flag, meth, _, _, crc, cs, us, nl, xl, cl, _, _, _, off) = struct.unpack("<IHHHHHHIIIHHHHHII", cd[p:p + 46])
        name = cd[p + 46:p + 46 + nl].decode("utf-8"); extra = cd[p + 46 + nl:p + 46 + nl + xl]
        q = 0
        while q + 4 <= len(extra):
            hid, hl = struct.unpack("<HH", extra[q:q + 4]); body = extra[q + 4:q + 4 + hl]
            if hid == 1:
                r = 0
                if us == 0xFFFFFFFF: us = struct.unpack("<Q", body[r:r + 8])[0]; r += 8
                if cs == 0xFFFFFFFF: cs = struct.unpack("<Q", body[r:r + 8])[0]; r += 8
                if off == 0xFFFFFFFF: off = struct.unpack("<Q", body[r:r + 8])[0]; r += 8
            q += 4 + hl
        out.append({"name": name, "method": meth, "crc": crc, "csize": cs, "usize": us, "offset": off, "flag": flag})
        p += 46 + nl + xl + cl
    if len(out) != n:
        raise IOError(f"central directory has {len(out)} entries, the end record says {n}")
    return out


def write_member(root: pathlib.Path, m: dict, raw: bytes) -> None:
    """raw = the member's local header + data; inflate, check CRC-32 and size, write (directories just made)."""
    dest = root / m["name"]
    if m["name"].endswith("/"):
        dest.mkdir(parents=True, exist_ok=True); return
    if raw[:4] != b"PK\x03\x04":
        raise IOError(f"{m['name']}: no local header")
    nl, xl = struct.unpack("<HH", raw[26:30]); data = raw[30 + nl + xl:30 + nl + xl + m["csize"]]
    body = data if m["method"] == 0 else zlib.decompress(data, -15) if m["method"] == 8 else None
    if body is None:
        raise IOError(f"{m['name']}: compression method {m['method']}")
    if len(body) != m["usize"] or (binascii.crc32(body) & 0xFFFFFFFF) != m["crc"]:
        raise IOError(f"{m['name']}: size or CRC-32 differs from the zip's central directory")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part"); tmp.write_bytes(body); os.replace(tmp, dest)


def have(root: pathlib.Path, m: dict) -> bool:
    p = root / m["name"]
    if m["name"].endswith("/"):
        return p.is_dir()
    return p.is_file() and p.stat().st_size == m["usize"] and (binascii.crc32(p.read_bytes()) & 0xFFFFFFFF) == m["crc"]


def extract_members(z: dict, members: list[dict], root: pathlib.Path, gap: int = 1 << 20) -> None:
    """Range requests over runs of nearby members (each read with its local header: 30 bytes + its name + up to 1 KiB of
    extra fields); members already present and correct are skipped, so an interrupted run resumes."""
    todo = sorted((m for m in members if not have(root, m)), key=lambda m: m["offset"])
    log(f"{z['dest']}: {len(members)} members selected, {len(todo)} to fetch")
    span = lambda m: m["offset"] + 30 + len(m["name"].encode()) + 1024 + m["csize"]  # noqa: E731
    i = 0
    while i < len(todo):
        j = i; start = todo[i]["offset"]; end = span(todo[i])
        while j + 1 < len(todo) and todo[j + 1]["offset"] - end < gap and end - start < (64 << 20):
            j += 1; end = max(end, span(todo[j]))
        blob = get(z["url"], start, min(end, z["size"]) - 1)
        for m in todo[i:j + 1]:
            write_member(root, m, blob[m["offset"] - start:])
        i = j + 1
        if i % 200 == 0 or i == len(todo):
            log(f"{z['dest']}: {i}/{len(todo)}")


def stream_all(z: dict, members: list[dict], root: pathlib.Path) -> None:
    """--full: one sequential GET of the whole zip, every member written as it passes, its sha256 checked at the end."""
    order = sorted(members, key=lambda m: m["offset"]); h = hashlib.sha256(); pos = 0; buf = b""
    with urllib.request.urlopen(z["url"], timeout=600) as r:
        for k, m in enumerate(order):
            need = (order[k + 1]["offset"] if k + 1 < len(order) else z["size"]) - m["offset"]
            while len(buf) < (m["offset"] - pos) + need:
                chunk = r.read(8 << 20)
                if not chunk:
                    break
                h.update(chunk); buf += chunk
            raw = buf[m["offset"] - pos:m["offset"] - pos + need]
            if not have(root, m):
                write_member(root, m, raw)
            buf = buf[m["offset"] - pos + need:]; pos = m["offset"] + need
            if k % 5000 == 0:
                log(f"{z['dest']}: {k}/{len(order)}")
        while True:
            chunk = r.read(8 << 20)
            if not chunk:
                break
            h.update(chunk)
    if h.hexdigest() != z["sha256"]:
        raise IOError(f"{z['dest']}: the zip's sha256 {h.hexdigest()} != {z['sha256']}")


def instance_dir(task: str) -> pathlib.Path:
    """A task's instance files in the repository's tasks/maniguard/<task>/: the privileged task's environment/instance/,
    the standard task's environment/sim/instance/."""
    t = ROOT / "tasks" / "maniguard" / task
    for d in (t / "environment/instance", t / "environment/sim/instance"):
        if (d / "instance.json").is_file():
            return d
    raise RuntimeError(f"{task}: no instance files in tasks/maniguard/{task}/")


def all_tasks() -> list[str]:
    return sorted(d.name for d in (ROOT / "tasks" / "maniguard").iterdir() if d.is_dir())


def subset_prefixes(tasks: list[str], extra_scenes: list[str] = ()) -> tuple[set, list]:
    # every particle system: objects' abilities name systems their scene never holds (a pepper shaker's black_pepper), and
    # OmniGibson checks a system name against the systems/ directories of the dataset (0.83 GB)
    pre = {"VERSION", "metadata/", "systems/"}; used = []
    for key in list(tasks) + list(extra_scenes):
        f = pathlib.Path(key) if key in extra_scenes else instance_dir(key) / "scene_ep1.json"
        scene = json.loads(f.read_text())
        for name, o in scene["objects_info"]["init_info"].items():
            if o.get("class_name") == "DatasetObject":
                a = o["args"]; pre.add(f"objects/{a['category']}/{a['model']}/")
        for sysname in (scene["state"]["registry"].get("system_registry") or {}):
            pre.add(f"systems/{sysname}/")
        used.append(key)
    return pre, used


def blob_sha1(b: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def longfinger(root: pathlib.Path) -> dict:
    out = {}
    for rel, (kind, digest) in LONGFINGER.items():
        dest = root / LONGFINGER_DEST / rel
        ok = dest.is_file() and ((hashlib.sha256(dest.read_bytes()).hexdigest() if kind == "sha256" else blob_sha1(dest.read_bytes())) == digest)
        if not ok:
            b = get(f"{HF}/IDEAS-Lab-Northwestern/franka-panda-longfinger/resolve/{LONGFINGER_REV}/{rel}")
            got = hashlib.sha256(b).hexdigest() if kind == "sha256" else blob_sha1(b)
            if got != digest:
                raise IOError(f"long-finger {rel}: {kind} {got} != {digest}")
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(b)
        out[rel] = {kind: digest}
    return out


def manifest_files(root: pathlib.Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name not in ("MANIGUARD_DATA.json", "omnigibson.key"):
            out[p.relative_to(root).as_posix()] = [p.stat().st_size, binascii.crc32(p.read_bytes()) & 0xFFFFFFFF]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="the data root to create or complete ($RCB_MANIGUARD_DATA)")
    ap.add_argument("--key", help="an existing omnigibson.key (the BEHAVIOR Data Bundle key of a licence already accepted)")
    ap.add_argument("--full", action="store_true", help="every member of behavior-1k-assets-3.7.2rc1 (34.7 GB) instead of the task subset")
    ap.add_argument("--tasks", nargs="*", default=None, help="ManiGuard task dirs (tasks/maniguard/<task>) for the subset (default: every one)")
    ap.add_argument("--extra-scenes", nargs="*", default=[], help="more scene_ep1.json files whose objects the subset includes (e.g. a smoke-test task)")
    ap.add_argument("--check", action="store_true", help="verify an existing root against its MANIGUARD_DATA.json; write nothing")
    a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    if a.check:
        man = json.loads((root / "MANIGUARD_DATA.json").read_text())
        files = manifest_files(root)
        bad = [f for f, v in man["files"].items() if files.get(f) != v] + [f for f in files if f not in man["files"]]
        ok = not bad and (root / "omnigibson.key").is_file()
        print(json.dumps({"root": str(root), "ok": ok, "files": len(files), "bad": bad[:20], "key": (root / "omnigibson.key").is_file()}))
        return 0 if ok else 1
    if not a.key or not pathlib.Path(a.key).is_file():
        raise SystemExit("--key: the path of an existing omnigibson.key is required (this script never downloads one or accepts a licence)")
    root.mkdir(parents=True, exist_ok=True)
    tasks = a.tasks if a.tasks is not None else all_tasks()
    t0 = time.time()
    cd = central_directory(ASSETS)
    if a.full:
        stream_all(ASSETS, cd, root / ASSETS["dest"]); covered = "all"
    else:
        pre, covered = subset_prefixes(tasks, a.extra_scenes)
        sel = [m for m in cd if any(m["name"] == p or m["name"].startswith(p) for p in pre)]
        missing = [p for p in pre if not any(m["name"] == p or m["name"].startswith(p) for m in cd)]
        if missing:
            raise SystemExit(f"the 3.7.2rc1 zip has no {missing}")
        extract_members(ASSETS, sel, root / ASSETS["dest"])
    rcd = central_directory(ROBOT)
    extract_members(ROBOT, rcd, root / ROBOT["dest"])
    lf = longfinger(root)
    shutil.copyfile(a.key, root / "omnigibson.key"); os.chmod(root / "omnigibson.key", 0o644)
    man = {"created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "behavior_1k_assets": {**{k: ASSETS[k] for k in ("url", "size", "sha256")}, "members": "all" if a.full else "task subset",
           "tasks": covered}, "omnigibson_robot_assets": {k: ROBOT[k] for k in ("url", "size", "sha256")},
           "longfinger": {"repo": "IDEAS-Lab-Northwestern/franka-panda-longfinger", "revision": LONGFINGER_REV, "files": lf},
           "key": "omnigibson.key (copied from --key; not in this manifest)", "files": manifest_files(root)}
    (root / "MANIGUARD_DATA.json").write_text(json.dumps(man, indent=1) + "\n")
    du = sum(v[0] for v in man["files"].values())
    print(json.dumps({"root": str(root), "files": len(man["files"]), "bytes": du, "wall_s": round(time.time() - t0, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
