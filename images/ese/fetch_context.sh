#!/usr/bin/env bash
# Prepare the build context of ese, images/ese/context/ (images/ese/BUILD_CONTEXT):
#   context/robosafe-src/          Embodied Safety Exam at the commit pinned in source.env, with the exact public metadata
#                                  projection in PUBLIC_SOURCE_PROJECTION.json replayed before checksumming: the
#                                  package `robosafebench/`, pyproject.toml, README.md, LICENSE, LICENSE-assets and
#                                  assets/third_party/ without the MuJoCo Menagerie robot models (their README and the
#                                  DejaVu font stay)
#   context/menagerie.sha256       the Menagerie files Embodied Safety Exam vendors (path under assets/third_party/
#                                  mujoco_menagerie/ and sha256); the image takes them from MuJoCo Menagerie's public
#                                  repository at MENAGERIE_COMMIT and checks every one
#   context/robosafe-src.sha256    every file of context/robosafe-src/
#   context/requirements.txt, context/robosafe-commit
# The context is vendored: committed in this repository, so that anyone can build the image. This script is how it was
# made, and how a maintainer with a clone of Embodied Safety Exam checks it (`--check`) or refreshes it for a new commit.
# README.md's sentence about the repository's own documents is rewritten (they are not in the snapshot).
# Keep the complete native package, including its server, CLI, diagnostics and
# optional harness modules. Merely shipping these modules starts no API/model
# process. Context savings come from verified duplicate assets, not code pruning.
# Usage: images/ese/fetch_context.sh [--check] /path/to/a/Embodied Safety Exam/clone
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/source.env"
check=0; [ "${1:-}" = "--check" ] && { check=1; shift; }
SRC="${1:?usage: fetch_context.sh [--check] /path/to/a/Embodied Safety Exam/clone}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
full="$(git -C "$SRC" rev-parse --verify "$ROBOSAFEBENCH_COMMIT^{commit}")"
OUT="$TMP/context"; mkdir -p "$OUT/robosafe-src" "$TMP/all"
PATHS=(robosafebench assets pyproject.toml README.md LICENSE LICENSE-assets)
# the release gate's double-build check (Embodied Safety Exam 0.5.1: tools/double_build_check.py) runs inside the image
if git -C "$SRC" cat-file -e "$full:tools/double_build_check.py" 2>/dev/null; then PATHS+=(tools/double_build_check.py); fi
git -C "$SRC" archive "$full" "${PATHS[@]}" | tar -x -C "$TMP/all"
# The installed package keeps its exact third-party assets. The committed build
# context needs one copy only; reconstruct the package copy after fetching the
# pinned Menagerie files and before wheel installation.
python3 "$HERE/third_party_context.py" stage "$TMP/all" "$OUT/third-party-duplicates.json"
cp "$HERE/third_party_context.py" "$OUT/third_party_context.py"
( cd "$TMP/all/assets/third_party/mujoco_menagerie" && find . -type f | LC_ALL=C sort | sed 's|^\./||' | xargs sha256sum ) > "$OUT/menagerie.sha256"
rm -rf "$TMP/all/assets/third_party/mujoco_menagerie"
cp -a "$TMP/all/." "$OUT/robosafe-src/"
# README.md: its pointers to the repository's own documents (not in the snapshot) become a pointer to this benchmark's doc
python3 - "$OUT/robosafe-src/README.md" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
old = ("Status: under construction. `STATUS.md` says what exists today; `docs/CONTRACTS.md` holds the interfaces;\n"
       "`docs/DESIGN.md` the design.\n")
new = ("This copy is a pinned snapshot of the simulator package for robot_coding_bench's image `ese`; for the\n"
       "contracts that matter there, see `docs/benchmarks/embodied-safety-exam.md` in robot_coding_bench.\n")
if old not in s:
    sys.exit("README.md changed upstream: update the rewrite in fetch_context.sh")
open(p, "w").write(s.replace(old, new))
PY
cp "$HERE/requirements.txt" "$OUT/requirements.txt"
python3 "$HERE/public_source_projection.py" "$OUT/robosafe-src" "$HERE/PUBLIC_SOURCE_PROJECTION.json"
printf '%s\n' "$full" > "$OUT/robosafe-commit"
printf 'MENAGERIE_REPO=%s\nMENAGERIE_COMMIT=%s\n' "$MENAGERIE_REPO" "$MENAGERIE_COMMIT" > "$OUT/menagerie.env"
( cd "$OUT/robosafe-src" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum ) > "$OUT/robosafe-src.sha256"   # names may hold spaces (0.5.2: the G1 licence)
if [ $check = 1 ]; then
  if diff -r "$OUT" "$HERE/context" >/dev/null; then echo "context matches Embodied Safety Exam $full"; exit 0; fi
  echo "context differs from Embodied Safety Exam $full:"; diff -rq "$OUT" "$HERE/context" | head -20; exit 1
fi
rm -rf "${HERE:?}/context"; cp -a "$OUT" "$HERE/context"
echo "context: $HERE/context ($(du -sh "$HERE/context" | cut -f1)), Embodied Safety Exam $full"
