#!/usr/bin/env bash
# Prepare the ikea-mujoco build context images/ikea-mujoco/context/ (images/ikea-mujoco/BUILD_CONTEXT):
#   - the robot meshes (assets/panda/, assets/aloha/: 828 of the 2,078 mesh files) from their public upstream, MuJoCo
#     Menagerie (github.com/google-deepmind/mujoco_menagerie, Panda Apache-2.0, ALOHA BSD-3-Clause), at the commit
#     pinned in images/ikea-mujoco/assets.json ("upstream"); anonymous download;
#   - the furniture part meshes (assets/parts/) from the Hugging Face dataset pinned in assets.json ("repo",
#     "revision", "path_prefix"); a private dataset needs `hf auth login` or HF_TOKEN in the environment (never printed);
#   - every file's sha256 is checked against the same file's per-task "files" entry of assets.json;
#   - the scene code from git, images/ikea-mujoco/scenes/<task>/;
#   - then images/ikea-mujoco/stage_context.py on the two together, which checks every staged file again and writes the
#     context (scenes/, assets.json, bytepatch_libmujoco.py).
# Needs python3 and huggingface_hub (pip install huggingface_hub).
# usage: images/ikea-mujoco/fetch_image_context.sh [<download dir>]   (default: $RCB_IKEA_ASSETS or ~/.cache/ikea-mujoco-assets)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; HERE="$ROOT/images/ikea-mujoco"
DL="${1:-${RCB_IKEA_ASSETS:-$HOME/.cache/ikea-mujoco-assets}}"
python3 - "$HERE/assets.json" "$DL" <<'PY'
import hashlib, json, pathlib, re, shutil, sys, urllib.request
pin, dl = json.load(open(sys.argv[1])), pathlib.Path(sys.argv[2])
want = {f"{t}/{f}": h for t, rec in pin["tasks"].items() for f, h in rec["files"].items() if f.startswith("assets/")}
up = pin.get("upstream", {})


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def source(rel):   # "<task>/assets/panda/x.obj" -> (upstream entry, path in the upstream repo) or None (dataset)
    f = rel.split("/", 1)[1]
    for pre, u in up.items():
        if f.startswith(pre):
            name = f[len(pre):]
            return u, (u["LICENSE"] if name == "LICENSE" else u["path"] + name)
    return None


# 1. robot meshes from the public upstream; one download per distinct file, copied to every scene that uses it
dl.mkdir(parents=True, exist_ok=True)
cache, n_up = {}, 0
for rel, h in sorted(want.items()):
    s = source(rel)
    if s is None:
        continue
    n_up += 1
    dst = dl / rel
    if dst.is_file() and sha(dst) == h:
        continue
    u, path = s
    if h not in cache:
        if not re.fullmatch(r"[0-9a-f]{40}", u["commit"]):
            sys.exit(f"assets.json upstream {u['repo']}: commit {u['commit']!r} is not a full commit id")
        url = f"https://raw.githubusercontent.com/{u['repo']}/{u['commit']}/{path}"
        data = urllib.request.urlopen(url, timeout=60).read()
        if hashlib.sha256(data).hexdigest() != h:
            sys.exit(f"FAIL {url}: sha256 differs from images/ikea-mujoco/assets.json ({rel})")
        cache[h] = data
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(cache[h])
print(f"ok {n_up} robot mesh files from the public upstream ({', '.join(sorted({u['repo'] for u in up.values()}))})")

# 2. the furniture parts from the pinned Hugging Face dataset
if not re.fullmatch(r"[0-9a-f]{40}", pin.get("revision", "")):
    sys.exit(f"images/ikea-mujoco/assets.json: revision {pin.get('revision')!r} is not a commit of {pin['repo']}")
pre = pin.get("path_prefix", "")
rest = sorted(rel for rel in want if source(rel) is None)
if any(not (dl / rel).is_file() or sha(dl / rel) != want[rel] for rel in rest):
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit("needs huggingface_hub: pip install huggingface_hub")
    tmp = dl / ".dataset"
    try:
        snapshot_download(repo_id=pin["repo"], repo_type=pin["repo_type"], revision=pin["revision"], local_dir=str(tmp),
                          allow_patterns=[f"{pre}{t}/assets/parts/**" for t in pin["tasks"]])
    except Exception as e:  # noqa: BLE001  the message names the repository, never the token
        sys.exit(f"download of {pin['repo']}@{pin['revision'][:12]} failed ({type(e).__name__})"
                 + (": it is a private dataset (`hf auth login` or HF_TOKEN with read access)" if pin.get("private") else ""))
    for rel in rest:
        src = tmp / (pre + rel)
        if src.is_file():
            (dl / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dl / rel)
bad = [rel for rel, h in sorted(want.items()) if not (dl / rel).is_file() or sha(dl / rel) != h]
extra = sorted(str(p.relative_to(dl)) for t in pin["tasks"] for p in (dl / t / "assets").rglob("*")
               if p.is_file() and str(p.relative_to(dl)) not in want)
if bad or extra:
    sys.exit("FAIL meshes differ from images/ikea-mujoco/assets.json: " + ", ".join((bad + extra)[:10])
             + (f" ... ({len(bad) + len(extra)} files)" if len(bad) + len(extra) > 10 else ""))
print(f"ok {len(rest)} part mesh files from {pin['repo']}@{pin['revision'][:12]}; all {len(want)} mesh files match "
      f"images/ikea-mujoco/assets.json ({dl})")
PY
TREE="$(mktemp -d)"; trap 'rm -rf "$TREE"' EXIT
for d in "$ROOT"/images/ikea-mujoco/scenes/*/; do
  t="$(basename "$d")"; mkdir -p "$TREE/scenes/$t"
  cp -r "$d." "$TREE/scenes/$t/"; cp -r "$DL/$t/assets" "$TREE/scenes/$t/assets"
done
python3 "$HERE/stage_context.py" "$TREE"
