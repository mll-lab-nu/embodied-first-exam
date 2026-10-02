#!/usr/bin/env bash
# Standard mode (PROTOCOL §4.1: no simulator or simulation code in the agent container): the agent's image is built
# from environment/, but never takes environment/sim/, which compose mounts into the sim sidecar only (and which may
# hold the scoring code). Every COPY / ADD source of environment/Dockerfile is therefore a named path outside sim/:
# not `.` or `..`, not a wildcard. Sources from another stage or image (--from) and ADD URLs are not from environment/.
# Usage: check-standard-agent-image.sh tasks/<task-dir>
set -uo pipefail
t="${1%/}"
case "$(basename "$t")" in *-standard) ;; *) exit 0 ;; esac
python3 - "$t" <<'PY'
import json, pathlib, posixpath, re, sys
t = pathlib.Path(sys.argv[1]); rc = 0
lines = [ln for ln in (t / "environment/Dockerfile").read_text().splitlines() if not ln.lstrip().startswith("#")]
text = re.sub(r"\\[ \t]*\n", " ", "\n".join(lines))   # join continued lines (comment lines are not part of them)
for line in text.splitlines():
    m = re.match(r"\s*(COPY|ADD)\s+((?:--\S+\s+)*)(.*)", line, re.I)
    if not m or "--from" in m.group(2):
        continue
    body = m.group(3).strip()
    srcs = (json.loads(body) if body.startswith("[") else body.split())[:-1]
    for src in srcs:
        if "://" in src:
            continue  # ADD <url>
        p = posixpath.normpath("/" + src).lstrip("/")   # inside the context: ".", "..", "x/.." are its root
        if not p or any(c in p for c in "*?[") or p.split("/")[0] == "sim":
            print(f"FAIL {t}: environment/Dockerfile: {m.group(1)} {src}: name files outside sim/ only")
            rc = 1
sys.exit(rc)
PY
