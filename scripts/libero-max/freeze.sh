#!/usr/bin/env bash
# Freeze every case of cases.json and record its scripted reference (freeze.py), one fresh container per case (one
# simulator per process), in the eai-libero-max image, without network. Writes frozen/<case_id>/{instance.json,
# oracle.npy, report.json}. reference.py is mounted for this step only; it is never part of a task.
#   bash scripts/libero-max/freeze.sh [cases.json] [out dir] [parallel]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
cases="$(realpath "${1:-$here/cases.json}")"
out="$(realpath -m "${2:-$here/frozen}")"
jobs="${3:-8}"
image="ghcr.io/mll-lab-nu/eai-libero-max:$(cat "$root/images/libero-max/VERSION")"
mkdir -p "$out"
python3 -c 'import json,sys; [print(c["case_id"]) for c in json.load(open(sys.argv[1]))["cases"]]' "$cases" |
  xargs -P "$jobs" -I{} docker run --rm --network none -u "$(id -u):$(id -g)" --tmpfs /tmp:exec,mode=1777 -e HOME=/tmp \
    -v "$here:/work:ro" -v "$(dirname "$cases"):/cases:ro" -v "$out:/out" -w /work \
    -e PYTHONPATH=/work/shared:/work:/opt/libero-max/overlay:/opt/libero-max/src \
    "$image" python freeze.py "/cases/$(basename "$cases")" {} /out/{}
python3 - "$out" <<'PY'
import json, sys
from pathlib import Path
reps = [json.loads(p.read_text()) for p in sorted(Path(sys.argv[1]).glob("*/report.json"))]
print(f"{sum(r.get('ok', False) for r in reps)}/{len(reps)} verified")
PY
