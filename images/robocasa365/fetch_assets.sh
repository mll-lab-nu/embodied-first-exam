#!/bin/sh
# Download, check (SHA-256) and unpack RoboCasa365's asset archives under $1 (the package's models/assets); one archive
# at a time to bound disk use. Same archives and hashes as the PR #4 build (scripts/robot24/asset-lock.json, "365");
# four of them are fetched from RoboCasa's Hugging Face mirror, which carries byte-identical files.
set -eu
assets="$1"
fetch() {  # url sha256 destination
  mkdir -p "$3"
  curl -fL --retry 3 "$1" -o /tmp/asset.zip
  echo "$2  /tmp/asset.zip" | sha256sum -c -
  python -m zipfile -e /tmp/asset.zip "$3"
  rm /tmp/asset.zip
}
hf=https://huggingface.co/datasets/robocasa/robocasa-assets/resolve/1b92c3d02ca4354984fec961357db0bff7b32166
fetch $hf/textures.zip ba3a4dcef96e199cbd601c7cdb7eb46077fb6672611b7ac74c25a191bf0be392 "$assets"
fetch $hf/generative_textures.zip bc05095af306222d9a799a9b0b5b16662aa546998622ee8fd3072566ea4c31ec "$assets"
fetch https://utexas.box.com/shared/static/idbncsadpnaz1jfl4i6m8qejawk7p9pi.zip 62c1c87776edda9b7c42dda7b00781a1e5a7f90acc3e49d06c39c9545cbd6c3e "$assets"
fetch $hf/objaverse.zip 66a7eebef3bac855301964d35d905fc2cb44d691f007f97af08d96e83db5cc08 "$assets/objects"
fetch $hf/aigen_objs.zip 1f88792322ccce79f775e88482626c324c6e07d002adf23320a124b72764dd19 "$assets/objects"
fetch https://utexas.box.com/shared/static/vckqvvkh1z8t69k8qcpcmee6k66stii4.zip a1db739b0e80fc4d56d4be27d89dba3aa60000e9648c5607874700e0f14b7955 "$assets/objects"
