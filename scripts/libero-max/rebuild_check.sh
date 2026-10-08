#!/usr/bin/env bash
# Check that this host rebuilds every frozen LIBERO-MAX instance bit-exactly and replays every reference to its recorded
# final state (run it once per new host type: the frozen hashes depend on the CPU's numeric kernels, see
# docs/benchmarks/libero-max.md). One fresh container per case, in the eai-libero-max image, without network.
#   bash scripts/libero-max/rebuild_check.sh [parallel] [out.jsonl]      # exit 1 unless every case matches
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
jobs="${1:-4}"
out="$(realpath -m "${2:-rebuild_check.jsonl}")"
image="ghcr.io/mll-lab-nu/eai-libero-max:$(cat "$root/images/libero-max/VERSION")"
ls "$here/frozen" |
  xargs -P "$jobs" -I{} docker run --rm --network none -u "$(id -u):$(id -g)" --tmpfs /tmp:exec,mode=1777 -e HOME=/tmp \
    -v "$here:/work:ro" -w /work -e PYTHONPATH=/work/shared:/opt/libero-max/overlay:/opt/libero-max/src \
    "$image" sh -c 'python rebuild_check.py frozen/{} 2>/dev/null | grep "^{" || echo "{\"case_id\": \"{}\", \"error\": true}"' >"$out"
python3 - "$out" <<'PY'
import collections, json, sys
rs = [json.loads(l) for l in open(sys.argv[1])]
bad = [r["case_id"] for r in rs if not (r.get("initial_ok") and r.get("final_ok"))]
kern = collections.Counter(json.dumps(r.get("numerics"), sort_keys=True) for r in rs)
print(f"{len(rs) - len(bad)}/{len(rs)} cases rebuild bit-exactly and replay their reference; numerics: {dict(kern)}")
print("\n".join(f"  differs: {c}" for c in bad))
sys.exit(1 if bad or not rs else 0)
PY
