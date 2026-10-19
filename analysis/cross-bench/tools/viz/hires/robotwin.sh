#!/bin/bash
# 2560x1440 Blender Cycles version of one clip of a RoboTwin standard-mode trial (optional backend; see ../README.md).
#   usage: BEL_TOKEN=... hires/robotwin.sh KEY TASK_COMMIT FROM TO      e.g. ... codex-gpt6_astra-high__robotwin_2_0_put_bottles_dustbin__YdHsp73 a800049d 06:00 08:45
# TASK_COMMIT: the main commit the trial ran (task files and image tag are taken from it). Needs events.json first
# (viz/events.py). The token is read from the environment only.
#  1. fetch trajectory.npz and the service log from the board
#  2. replay in the trial's image; stop unless the final state hash is final.json's live_sha; record every 25 steps
#  3. render the replay frames the clip shows: a studio view (film_blender's cinematic look) and the agent's cameras
#  4. composite with the annotations at 2x
set -euo pipefail
KEY=$1; COMMIT=$2; FROM=$3; TO=$4
HERE=$(cd "$(dirname "$0")" && pwd); VIZ=$(dirname "$HERE"); TOOLS=$(dirname "$VIZ"); XB=$(dirname "$TOOLS")
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
RAW=${XB_RAW:-/data/pingyue/cross-bench/raw}/$KEY
V=${XB_VIZ:-/data/pingyue/cross-bench/viz}/$KEY
read -r TID TASKDIR < <(python3 - "$XB/data/trials.csv" "$KEY" <<'EOF'
import csv, sys
r = next(r for r in csv.DictReader(open(sys.argv[1])) if r["key"] == sys.argv[2])
print(r["id"], r["task"])
EOF
)
SHA=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['live_sha'])" "$RAW/artifacts/data/final.json")
TASKPATH=$(git -C "$REPO" ls-tree -d -r --name-only "$COMMIT" | grep -E "(^|/)$TASKDIR\$" | head -1)
IMAGE=$(git -C "$REPO" show "$COMMIT:$TASKPATH/environment/docker-compose.yaml" | grep -o 'ghcr.io/[^ ]*robotwin[^ ]*' | head -1 \
        | sed 's|eai-robotwin:|efe:robotwin-|')   # the images were renamed eai-* -> efe:* (same digests)
mkdir -p "$V/hires/task" "$V/hires/film" "$V/service" "$V/clips"
[ -d "$V/hires/task/environment" ] || git -C "$REPO" archive "$COMMIT" "$TASKPATH" | tar -x -C "$V/hires/task" --strip-components=$(($(tr -cd / <<<"$TASKPATH" | wc -c) + 1))
SIMTASK=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['task'])" "$V/hires/task/environment/sim/instance.json")

for p in verifier/trajectory.npz verifier/episode.jsonl verifier/live_timeline.jsonl; do
  out=$V/$( [ "$p" = verifier/trajectory.npz ] && echo trajectory.npz || echo "service/$(basename "$p")" )
  [ -s "$out" ] || python3 -c "import sys; sys.path.insert(0, sys.argv[1]); import bel; open(sys.argv[3], 'wb').write(bel.get_file(sys.argv[2], sys.argv[4]))" "$TOOLS" "$TID" "$out" "$p"
done
if [ ! -s "$V/hires/film/poses.npz" ]; then
  cp "$HERE/sapien_film.py" "$V/hires/"
  sg docker -c "docker run --rm --name viz-film-${KEY: -7} --gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,graphics,utility \
    -e PYTHONPATH=/srv:/opt/RoboTwin -e RCB_SESSION_LOG= -v $V/hires/task/environment/sim:/srv:ro -v $V:/work -w /opt/RoboTwin \
    $IMAGE bash -c 'python /work/hires/sapien_film.py --task $SIMTASK --instance /srv/instance.json --traj /work/trajectory.npz \
    --out /work/hires/film --expect-sha $SHA; rc=\$?; chown -R $(id -u):$(id -g) /work/hires; exit \$rc'"
fi
TAG=${FROM/:/}-${TO/:/}
python3 "$VIZ/render.py" "$RAW" "$V/events.json" "$V/clips/$TAG.mp4" --from "$FROM" --to "$TO" \
  --service "$V/service/episode.jsonl" --list-frames "$V/clips/${TAG}_frames.json"
FRAMES=$(python3 -c "import json,sys; f=json.load(open(sys.argv[1])); print(f'{min(f)}:{max(f)+1}:1')" "$V/clips/${TAG}_frames.json")
blender -b --python-exit-code 1 -P "$HERE/cycles_studio.py" -- "$V/hires/film" "$V/hires/frames" --frames "$FRAMES" \
  --samples 256 --min-samples 64 --cams cinema:1920x1440,head_camera:640x480,front_camera:640x480,left_camera:640x480,right_camera:640x480 \
  > "$V/hires/blender.log" 2>&1
echo "rendered: $(grep -c ' done' "$V/hires/blender.log" || true) new frames (existing ones are kept)"
python3 "$VIZ/render.py" "$RAW" "$V/events.json" "$V/clips/${TAG}_2k.mp4" --from "$FROM" --to "$TO" --scale 2 \
  --views "$V/hires/frames" --main-cam cinema --service "$V/service/episode.jsonl"
