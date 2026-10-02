#!/bin/sh
# Download, check (SHA-256) and unpack the GR1 tasks' asset archives under $1 (the package's models/assets); one archive
# at a time to bound disk use. Same archives and hashes as the PR #4 build (scripts/robot24/asset-lock.json, "gr1" and
# "gr1-legacy").
set -eu
assets="$1"
fetch() {  # url sha256 destination
  mkdir -p "$3"
  curl -fL --retry 3 "$1" -o /tmp/asset.zip
  echo "$2  /tmp/asset.zip" | sha256sum -c -
  python -m zipfile -e /tmp/asset.zip "$3"
  rm /tmp/asset.zip
}
box=https://utexas.box.com/shared/static
nv=https://huggingface.co/datasets/nvidia/PhysicalAI-DigitalCousin-Assets/resolve/1b018839a6da865dffecd3185fe054211bc71270
fetch $box/otdsyfjontk17jdp24bkhy2hgalofbh4.zip d36bf23cec4ce33c83eb59dfd34faeb13d8f45f9844866a654569659fc9be23d "$assets"
fetch $box/pobhbsjyacahg2mx8x4rm5fkz3wlmyzp.zip 27905b494e7bf12826a8d67c167c73d95eade467841f5d2ddbdd87efc15b4c5a "$assets"
fetch $box/ejt1kc2v5vhae1rl4k5697i4xvpbjcox.zip 519f989588c7e67f818ee823e1abeb7e08a34d9ec4977395a712dc8ce80c284c "$assets/objects"
fetch $box/os3hrui06lasnuvwqpmwn0wcrduh6jg3.zip b6368da1f855b4844085794532965988fb4f6bfe71f4a1fead84002ef7fa0e5a "$assets/objects"
fetch $nv/lightwheel.zip 8e42a0c835a205d7a0e7c33b5c33ab160b220fa9343b50c16526b7c712a2b6e2 "$assets/objects"
fetch $nv/sketchfab.zip 12af71e68a5c748f8531ce20c9db0ae9ed71ab1d46265388e05155a5b5352b5d "$assets/objects"
