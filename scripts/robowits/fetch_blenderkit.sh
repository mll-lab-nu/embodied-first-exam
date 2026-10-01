#!/usr/bin/env bash
# Fetch the BlenderKit models the RoboWits tasks load into a host folder; the 26 BlenderKit families mount it read-only at
# /opt/robowits/assets/blender_kit (`export RCB_ROBOWITS_BLENDERKIT=<dir>`). The models are licensed to the account that
# downloads them: keep the folder private, never publish it or put it into an image (images/robowits/NOTICE).
#   scripts/robowits/fetch_blenderkit.sh [<dir>]      (default: $RCB_ROBOWITS_BLENDERKIT)
# Needs BLENDERKIT_API_KEY (a Full Plan key: 62 of the 127 models need one) in ENV_FILE (default <repo>/../.env); it is
# read in-process, handed to BuildKit as a secret and never printed. Recipe: images/robowits/blenderkit/Dockerfile. The
# result is checked against images/robowits/blenderkit.sha256, the files our frozen instances were built with.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; ENV_FILE="${ENV_FILE:-$(dirname "$ROOT")/.env}"
DEST="${1:-${RCB_ROBOWITS_BLENDERKIT:-}}"
[ -n "$DEST" ] || { echo "usage: $0 <dir>   (or set RCB_ROBOWITS_BLENDERKIT)" >&2; exit 2; }
[ ! -e "$DEST" ] || [ -z "$(ls -A "$DEST")" ] || { echo "$DEST exists and is not empty" >&2; exit 2; }
key() { python3 - "$ENV_FILE" <<'PY'
import sys, pathlib
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    line = line.strip()
    if line.startswith(("BLENDERKIT_API_KEY=", "export BLENDERKIT_API_KEY=")):
        v = line.split("=", 1)[1].strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'": v = v[1:-1]
        print(v, end="")
PY
}
BLENDERKIT_API_KEY="$(key)"; export BLENDERKIT_API_KEY
[ -n "$BLENDERKIT_API_KEY" ] || { echo "BLENDERKIT_API_KEY is not set in $ENV_FILE" >&2; exit 2; }
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
mkdir -p -m 700 "$DEST"
# the build fails unless every model in RoboWits' assets/metadata.json arrived (a Full Plan key is needed); MIN_MODELS is
# only the download pass's sanity floor (67 = the free models); PASS=<anything new> re-downloads
cmd="docker build --secret id=blenderkit_api_key,env=BLENDERKIT_API_KEY --build-arg MIN_MODELS=${MIN_MODELS:-67} --build-arg PASS=${PASS:-1} --output type=local,dest=$DEST -f $ROOT/images/robowits/blenderkit/Dockerfile $ROOT/images/robowits/blenderkit"
echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi
if (cd "$DEST" && sha256sum --quiet -c "$ROOT/images/robowits/blenderkit.sha256"); then
  echo "OK: all $(wc -l < "$ROOT/images/robowits/blenderkit.sha256") models match images/robowits/blenderkit.sha256. export RCB_ROBOWITS_BLENDERKIT=$DEST"
else
  echo "WARNING: the models listed above differ from the ones our instances were frozen with (changed on BlenderKit since?):" \
       "the families that load them may not rebuild their frozen scene exactly (the verifier reports instance_exact = 0)" >&2
  exit 1
fi
