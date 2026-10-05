#!/usr/bin/env bash
# Install only runner tooling; simulator/agent images come from the maintainer.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
P="${AGENT_BATCH_BOOTSTRAP_PYTHON:-python3.12}"
if ! command -v "$P" >/dev/null && [ -z "${AGENT_BATCH_BOOTSTRAP_PYTHON:-}" ] && command -v uv >/dev/null; then
  P="$(uv python find 3.12)"
fi
"$P" -c 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 required"'
command -v npm >/dev/null || { echo 'npm required to install the private Node/Codex tools.' >&2; exit 2; }
test ! -e "$R/.venv-agent-batch" || { echo 'Preserve the existing .venv-agent-batch; setup is one-time.' >&2; exit 2; }
"$P" -m venv "$R/.venv-agent-batch"
"$R/.venv-agent-batch/bin/python" -m pip install --require-hashes -r "$R/requirements/difficulty-eval-controller.lock"
PYTHONPATH="$R" "$R/.venv-agent-batch/bin/python" "$R/images/difficulty-eval/patch_harbor.py"
"$R/.venv-agent-batch/bin/python" - "$R" <<'PY'
import hashlib, importlib.util, json, pathlib, sys
root=pathlib.Path(sys.argv[1])
files={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
       ('images/difficulty-eval/patch_harbor.py','requirements/difficulty-eval-controller.lock')}
modules={name:hashlib.sha256(pathlib.Path(importlib.util.find_spec(name).origin).read_bytes()).hexdigest() for name in
         ('harbor.agents.installed.codex','harbor.environments.docker.docker')}
(pathlib.Path(sys.prefix)/'topogym-runner.json').write_text(json.dumps(dict(files=files,modules=modules),indent=2)+'\n')
PY
# Keep the host's Node unchanged; the runner prepends this private bin directory.
npm install --prefix "$R/.tools/agent-batch" node@22.14.0 @openai/codex@0.157.0
export PATH="$R/.tools/agent-batch/node_modules/.bin:$PATH"
node -e 'if (process.versions.node !== "22.14.0") process.exit(2)'
"$R/.tools/agent-batch/node_modules/.bin/codex" --version
"$R/.venv-agent-batch/bin/harbor" --version
docker compose version
echo "Ready. export PATH=\"$R/.venv-agent-batch/bin:$R/.tools/agent-batch/node_modules/.bin:\$PATH\""
