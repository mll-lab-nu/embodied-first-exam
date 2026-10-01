#!/bin/sh
# Download, check (SHA-256) and unpack the object mesh archives into $1; one archive at a time to bound disk use.
set -eu
dest="$1"
mkdir -p "$dest"
fetch() {  # url sha256
  curl -fL --retry 3 "$1" -o /tmp/objects.zip
  echo "$2  /tmp/objects.zip" | sha256sum -c -
  python -m zipfile -e /tmp/objects.zip "$dest"
  rm /tmp/objects.zip
}
fetch https://huggingface.co/datasets/nvidia/PhysicalAI-DigitalCousin-Assets/resolve/1b018839a6da865dffecd3185fe054211bc71270/lightwheel.zip 8e42a0c835a205d7a0e7c33b5c33ab160b220fa9343b50c16526b7c712a2b6e2
fetch https://huggingface.co/datasets/nvidia/PhysicalAI-DigitalCousin-Assets/resolve/1b018839a6da865dffecd3185fe054211bc71270/sketchfab.zip 12af71e68a5c748f8531ce20c9db0ae9ed71ab1d46265388e05155a5b5352b5d
fetch https://utexas.box.com/shared/static/ejt1kc2v5vhae1rl4k5697i4xvpbjcox.zip 519f989588c7e67f818ee823e1abeb7e08a34d9ec4977395a712dc8ce80c284c
fetch https://utexas.box.com/shared/static/os3hrui06lasnuvwqpmwn0wcrduh6jg3.zip b6368da1f855b4844085794532965988fb4f6bfe71f4a1fead84002ef7fa0e5a
