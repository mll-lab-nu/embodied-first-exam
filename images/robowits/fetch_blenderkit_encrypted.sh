#!/usr/bin/env bash
# Fetch our ENCRYPTED bundle of the BlenderKit models the RoboWits tasks load: the alternative to fetching them with your
# own BlenderKit key (images/robowits/fetch_blenderkit.sh). The bundle is a gated Hugging Face dataset:
#   https://huggingface.co/datasets/eai-v2-internal/robowits-blenderkit-encrypted
# 1. Request access on that page (log in, accept the research terms). 2. `hf auth login` here. 3. Run
#   images/robowits/fetch_blenderkit_encrypted.sh [--accept-terms] [<dir>]      (default: $RCB_ROBOWITS_BLENDERKIT)
# 4. `export RCB_ROBOWITS_BLENDERKIT=<dir>`. The tasks mount the folder read-only at /opt/robowits/assets/blender_kit; the
# tooling decrypts only the models a family loads, at scene build, into a private tmpfs dir it deletes right after the
# build (images/robowits/NOTICE). The files are checked against images/robowits/blenderkit_encrypted.sha256.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPO=eai-v2-internal/robowits-blenderkit-encrypted
PAGE="https://huggingface.co/datasets/$REPO"
ACCEPT=0; DEST=""
for a in "$@"; do
  case "$a" in
    --accept-terms) ACCEPT=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) DEST="$a" ;;
  esac
done
DEST="${DEST:-${RCB_ROBOWITS_BLENDERKIT:-}}"
[ -n "$DEST" ] || { echo "usage: $0 [--accept-terms] <dir>   (or set RCB_ROBOWITS_BLENDERKIT)" >&2; exit 2; }
[ ! -e "$DEST" ] || [ -z "$(ls -A "$DEST")" ] || { echo "$DEST exists and is not empty" >&2; exit 2; }

cat <<EOF
Terms of use of the encrypted RoboWits model bundle (full text: $PAGE):
  1. Non-commercial academic research only, and only through the RoboWits / robot-coding-bench tooling.
  2. Do not decrypt the files by any other means; do not extract, convert, export or reverse-engineer the models.
  3. Do not share, sell, sublicense or re-upload the files or the key: everyone requests access on the dataset page.
  4. The models belong to their authors under their Blendkit (formerly BlenderKit) licences, Royalty Free or CC0
     (ATTRIBUTION.csv); these terms grant no other rights to them.
  5. Delete the files and the key when you no longer need them for this research, or when asked to.
  6. Provided as is, without warranty.
EOF
if [ "$ACCEPT" != 1 ]; then
  read -r -p "Do you accept these terms? [y/N] " ans
  case "$ans" in y|Y|yes|YES) ;; *) echo "not accepted: nothing downloaded" >&2; exit 1 ;; esac
fi

HF="${HF:-hf}"
command -v "$HF" >/dev/null || { echo "the hf CLI (pip install -U huggingface_hub) is needed; then run: hf auth login" >&2; exit 2; }
"$HF" auth whoami >/dev/null 2>&1 || { echo "not logged in to Hugging Face: run 'hf auth login' first" >&2; exit 2; }

mkdir -p -m 700 "$DEST"
if ! "$HF" download "$REPO" --repo-type dataset --local-dir "$DEST" \
     --include "models/*" "robowits_blenderkit.key" "ATTRIBUTION.csv"; then
  echo "download failed: request access first at $PAGE (log in and accept the terms), then retry" >&2; exit 1
fi
# the dataset keeps the models under models/; the tasks read <dir>/<uuid>/obj.glb.enc next to the key
( cd "$DEST" && for d in models/*/; do mv "$d" .; done && rmdir models )
chmod -R go-rwx "$DEST"; chmod 600 "$DEST/robowits_blenderkit.key"

if (cd "$DEST" && sha256sum --quiet -c "$ROOT/images/robowits/blenderkit_encrypted.sha256"); then
  echo "OK: all $(wc -l < "$ROOT/images/robowits/blenderkit_encrypted.sha256") files match images/robowits/blenderkit_encrypted.sha256." \
       "export RCB_ROBOWITS_BLENDERKIT=$DEST"
else
  echo "ERROR: the files listed above differ from images/robowits/blenderkit_encrypted.sha256 (a broken download?)" >&2
  exit 1
fi
