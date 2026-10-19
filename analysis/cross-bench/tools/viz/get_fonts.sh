#!/bin/bash
# The overlay fonts (Inter 4.0, JetBrains Mono 2.304; both SIL OFL) into viz/fonts/, which git ignores.
set -euo pipefail
F=$(cd "$(dirname "$0")" && pwd)/fonts; mkdir -p "$F"; cd "$F"
[ -s Inter-Bold.ttf ] || { curl -sL -o inter.zip https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip
  unzip -o -q -j inter.zip extras/ttf/Inter-Regular.ttf extras/ttf/Inter-SemiBold.ttf extras/ttf/Inter-Bold.ttf -d .; rm inter.zip; }
[ -s JetBrainsMono-Regular.ttf ] || { curl -sL -o jbm.zip https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip
  unzip -o -q -j jbm.zip fonts/ttf/JetBrainsMono-Regular.ttf fonts/ttf/JetBrainsMono-Bold.ttf fonts/ttf/JetBrainsMono-Italic.ttf -d .; rm jbm.zip; }
ls "$F"
