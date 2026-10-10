#!/usr/bin/env bash
# PROTOCOL §2.4: the agent container and the verifier of every standard task share ONE client base image, pinned by
# digest, and pinned pip versions. The image and the pins are scripts/eai_standard/client.env (CLIENT_IMAGE) and
# scripts/eai_standard/client-requirements.txt. For each standard or standard-realtime task (mode standard /
# standard-realtime, or a -standard / -standard-realtime name), environment/Dockerfile and tests/Dockerfile:
#   - every FROM is CLIENT_IMAGE;
#   - every `pip install` installs the pins: `-r <file>` with a byte-identical copy of client-requirements.txt in the
#     build context, or the full pin list inline (name==version for every pin, nothing else).
# A failure for the eai-standard/2.2 and 2.4 tasks, whose generators copy client.env and the pins (BEHAVIOR-1K, RoboLab,
# RoboWits, RoboPaint; RoboTangle on 2.4). For every other task it only reports (a warning, never a failure) whether all standard tasks
# share the one client image of client.env (their own pip pins are their benchmark's business; PROTOCOL §7, open).
# Usage: check-standard-client.sh [tasks dir]   (repo-level; run_all.sh calls it once)
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "${1:-$root/tasks}" "$root/scripts/eai_standard" <<'PY'
import os, re, shlex, sys, tomllib
tasks, src = sys.argv[1], sys.argv[2]
env = dict(l.split("=", 1) for l in open(os.path.join(src, "client.env")).read().splitlines() if "=" in l and not l.startswith("#"))
IMAGE = env["CLIENT_IMAGE"].strip()
req_path = os.path.join(src, env.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip())
REQ_BYTES = open(req_path, "rb").read()
PINS = {}
for line in REQ_BYTES.decode().splitlines():
    line = line.split("#", 1)[0].strip()
    if line:
        name, ver = line.split("==", 1); PINS[re.sub(r"[-_.]+", "-", name).lower()] = ver.strip()
FLAGS_WITH_ARG = {"-r", "--requirement", "-c", "--constraint", "-i", "--index-url", "--extra-index-url", "-f", "--find-links"}


def pip_problems(dockerfile: str, context: str) -> list:
    text = re.sub(r"\\\n", " ", open(dockerfile).read())
    out = []
    for m in re.finditer(r"^\s*FROM\s+(\S+)", text, re.M | re.I):
        if m.group(1) != IMAGE:
            out.append(f"FROM {m.group(1)} (the client base is {IMAGE})")
    for line in re.findall(r"^\s*RUN\s+(.*)$", text, re.M | re.I):
        for seg in re.split(r"&&|;|\|\|", line):
            mm = re.search(r"(?:^|\s)(?:pip3?|python3?\s+-m\s+pip)\s+install\s+(.*)$", seg.strip())
            if not mm:
                continue
            try:
                toks = shlex.split(mm.group(1))
            except ValueError:
                out.append(f"unparsable pip install: {seg.strip()[:80]}"); continue
            specs, reqs, i = [], [], 0
            while i < len(toks):
                t = toks[i]
                if t in FLAGS_WITH_ARG or any(t.startswith(f + "=") for f in FLAGS_WITH_ARG if f.startswith("--")):
                    arg = toks[i + 1] if t in FLAGS_WITH_ARG and i + 1 < len(toks) else t.split("=", 1)[-1]
                    if t in ("-r", "--requirement") or t.startswith("--requirement="):
                        reqs.append(arg)
                    else:
                        out.append(f"pip option {t} (install from the pins only)")
                    i += 2 if t in FLAGS_WITH_ARG else 1; continue
                if not t.startswith("-"):
                    specs.append(t)
                i += 1
            for r in reqs:
                local = os.path.join(context, os.path.basename(r))
                if os.path.basename(r) != "client-requirements.txt" or not os.path.isfile(local) or open(local, "rb").read() != REQ_BYTES:
                    out.append(f"pip install -r {r}: needs a byte-identical copy of scripts/eai_standard/client-requirements.txt in the build context")
            if specs:
                got = {}
                for s in specs:
                    n, sep, v = s.partition("==")
                    got[re.sub(r"[-_.]+", "-", n).lower()] = v if sep else None
                if got != PINS:
                    out.append("pip install " + " ".join(specs)[:120] + " (install the full pin list of client-requirements.txt, or -r it)")
    return out


bad, v1, v1_off, n22 = [], 0, [], 0
for t in sorted(os.listdir(tasks)):
    tt = os.path.join(tasks, t, "task.toml")
    if not os.path.isfile(tt):
        continue
    meta = tomllib.load(open(tt, "rb")).get("metadata", {})
    if not (meta.get("mode") in ("standard", "standard-realtime") or t.endswith(("-standard", "-standard-realtime"))):
        continue
    probs, froms = [], []
    for sub in ("environment", "tests"):
        df = os.path.join(tasks, t, sub, "Dockerfile")
        if os.path.isfile(df):
            probs += [f"{sub}/Dockerfile: {p}" for p in pip_problems(df, os.path.join(tasks, t, sub))]
            froms += re.findall(r"^\s*FROM\s+(\S+)", re.sub(r"\\\n", " ", open(df).read()), re.M | re.I)
    is22 = bool(re.fullmatch(r"eai-standard/2\.[24]", str(meta.get("protocol", ""))))   # 2.2 and 2.4 layers
    n22 += is22
    v1 += 1
    if any(f != IMAGE for f in froms):
        v1_off.append((t, sorted(set(f for f in froms if f != IMAGE))))
    if probs and is22:
        bad.append((t, probs))
for t, probs in bad:
    for p in probs:
        print(f"FAIL {t}: {p}")
if v1_off:
    bases = sorted({f for _, fs in v1_off for f in fs})
    print(f"WARN one client image: {v1 - len(v1_off)} of {v1} standard task dirs FROM {IMAGE.split('@')[0]}@..., "
          f"{len(v1_off)} FROM another base ({', '.join(b[:70] for b in bases)}): " + ", ".join(t for t, _ in v1_off[:3])
          + (", ..." if len(v1_off) > 3 else ""))
else:
    print(f"ok one client image: all {v1} standard task dirs FROM {IMAGE}")
if not bad:
    print(f"ok standard client: {n22} eai-standard/2.2 / 2.4 task dirs on the client image with the shared pins")
sys.exit(1 if bad else 0)
PY
