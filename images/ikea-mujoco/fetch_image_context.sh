#!/usr/bin/env bash
# Prepare the eai-ikea-mujoco build context images/ikea-mujoco/context/ (images/ikea-mujoco/BUILD_CONTEXT):
#   - the scenes' meshes, <task>/assets/<file>, from the private Hugging Face dataset at the revision pinned in
#     images/ikea-mujoco/assets.json ("repo", "revision"); every file's sha256 is checked against the same file's
#     per-task "files" entries;
#   - the scene code from git, images/ikea-mujoco/scenes/<task>/;
#   - then images/ikea-mujoco/stage_context.py on the two together, which checks every staged file again and writes the
#     context (scenes/, assets.json, bytepatch_libmujoco.py).
# Needs read access to the dataset: `hf auth login`, or HF_TOKEN in the environment (never printed); huggingface_hub
# (pip install huggingface_hub).
# usage: images/ikea-mujoco/fetch_image_context.sh [<download dir>]   (default: $RCB_IKEA_ASSETS or ~/.cache/ikea-mujoco-assets)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; HERE="$ROOT/images/ikea-mujoco"
DL="${1:-${RCB_IKEA_ASSETS:-$HOME/.cache/ikea-mujoco-assets}}"
python3 - "$HERE/assets.json" "$DL" <<'PY'
import hashlib, json, pathlib, re, sys
pin, dl = json.load(open(sys.argv[1])), pathlib.Path(sys.argv[2])
if not re.fullmatch(r"[0-9a-f]{40}", pin.get("revision", "")):
    sys.exit(f"images/ikea-mujoco/assets.json: revision {pin.get('revision')!r} is not a commit of {pin['repo']}")
want = {f"{t}/{f}": h for t, rec in pin["tasks"].items() for f, h in rec["files"].items() if f.startswith("assets/")}
try:
    from huggingface_hub import snapshot_download
except ImportError:
    sys.exit("needs huggingface_hub: pip install huggingface_hub (then `hf auth login`)")
dl.mkdir(parents=True, exist_ok=True)
try:
    snapshot_download(repo_id=pin["repo"], repo_type=pin["repo_type"], revision=pin["revision"], local_dir=str(dl),
                      allow_patterns=[f"{t}/assets/**" for t in pin["tasks"]])
except Exception as e:  # noqa: BLE001  the message names the repository, never the token
    sys.exit(f"download of {pin['repo']}@{pin['revision'][:12]} failed ({type(e).__name__}): this needs read access to "
             "the private dataset (`hf auth login` or HF_TOKEN)")


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


bad = [rel for rel, h in sorted(want.items()) if not (dl / rel).is_file() or sha(dl / rel) != h]
extra = sorted(str(p.relative_to(dl)) for t in pin["tasks"] for p in (dl / t / "assets").rglob("*")
               if p.is_file() and str(p.relative_to(dl)) not in want)
if bad or extra:
    sys.exit("FAIL meshes differ from images/ikea-mujoco/assets.json: " + ", ".join((bad + extra)[:10])
             + (f" ... ({len(bad) + len(extra)} files)" if len(bad) + len(extra) > 10 else ""))
print(f"ok {pin['repo']}@{pin['revision'][:12]}: {len(want)} mesh files match images/ikea-mujoco/assets.json ({dl})")
PY
TREE="$(mktemp -d)"; trap 'rm -rf "$TREE"' EXIT
for d in "$ROOT"/images/ikea-mujoco/scenes/*/; do
  t="$(basename "$d")"; mkdir -p "$TREE/scenes/$t"
  cp -r "$d." "$TREE/scenes/$t/"; cp -r "$DL/$t/assets" "$TREE/scenes/$t/assets"
done
python3 "$HERE/stage_context.py" "$TREE"
