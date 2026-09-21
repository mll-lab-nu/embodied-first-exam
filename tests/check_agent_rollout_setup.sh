#!/usr/bin/env bash
# Offline Linux preflight for the evaluation pipeline. Never calls a model API.
set -euo pipefail

rollout_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
rollout_python="${TOPOGYM_PY:-$rollout_repo_root/.venv-gs121-nyx/bin/python}"
rollout_regression=0

usage() {
    cat <<'HELP'
Usage: bash tests/check_agent_rollout_setup.sh [--python PATH] [--regression]

Check Python imports, Linux tools, a localhost proxy port, and sandboxed Codex CLI flags.
No API key is required. No model request or Genesis scene is started.

  --python PATH   Python executable; relative paths are resolved from the repo root.
                  Default: TOPOGYM_PY or .venv-gs121-nyx/bin/python in the repo.
  --regression    Also run the existing rollout and Cast Coil task-spec checks.
                  Includes token-budget tests with a local HTTP proxy and mocked API responses.
  -h, --help      Show this help.
HELP
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)
            if [[ -z "${2:-}" || "${2:-}" == --* ]]; then
                printf '[FAIL] --python requires an executable path.\n' >&2
                exit 2
            fi
            rollout_python="$2"
            shift 2
            ;;
        --regression) rollout_regression=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf '[FAIL] Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

cd -- "$rollout_repo_root"
if [[ "$(uname -s)" != Linux ]]; then
    printf '[FAIL] Run this check on the Linux evaluation host.\n' >&2
    exit 1
fi
if ! command -v -- "$rollout_python" >/dev/null 2>&1; then
    printf '[FAIL] Python not found: %s. Use --python /path/to/python.\n' "$rollout_python" >&2
    exit 1
fi

printf '[1/3] Checking system tools\n'
for rollout_tool in codex bwrap ffmpeg ffprobe; do
    if ! rollout_tool_path="$(command -v "$rollout_tool")"; then
        printf '[FAIL] %s was not found on PATH. Install it before evaluation.\n' "$rollout_tool" >&2
        exit 1
    fi
    printf '[OK] %s: %s\n' "$rollout_tool" "$rollout_tool_path"
done

printf '[2/3] Checking Python imports with %s\n' "$rollout_python"
"$rollout_python" - <<'PY'
import importlib
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

for name in ("genesis", "hydra", "numpy", "PIL", "topogym.agent_rollout.runtime"):
    try:
        importlib.import_module(name)
    except Exception as exc:
        raise SystemExit(f"[FAIL] Import {name}: {exc}") from exc
    print(f"[OK] Import {name}", flush=True)

from topogym.agent_rollout.isolation import sandbox_command

try:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
except OSError as exc:
    raise SystemExit(f"[FAIL] Cannot bind a localhost port for the token budget proxy: {exc}") from exc
print("[OK] Localhost budget proxy port available", flush=True)

print("[3/3] Checking Codex inside the rollout sandbox", flush=True)
with tempfile.TemporaryDirectory(prefix="topogym-cli-check-") as directory:
    root = Path(directory)
    public, agent_home, output = (root / name for name in ("public", "home", "output"))
    for path in (public, agent_home, output, public / "scratch"):
        path.mkdir()
    for command in (["codex", "--version"], ["codex", "exec", "--help"],
                    ["codex", "exec", "resume", "--help"]):
        args, env = sandbox_command(command, public, agent_home, output)
        label = " ".join(command)
        try:
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SystemExit(f"[FAIL] {label}: {exc}") from exc
        if result.returncode:
            print(result.stderr.strip(), file=sys.stderr)
            raise SystemExit(
                f"[FAIL] {label} exited {result.returncode}. Check bwrap permissions and make sure "
                "Codex and its dependencies are installed under mounted system paths such as /usr."
            )
        if command[-1] == "--version":
            print(f"[OK] {result.stdout.strip()}", flush=True)
            continue
        required = ["--ignore-user-config", "--output-schema", "--image", "--json",
                    "--model", "--skip-git-repo-check", "--output-last-message"]
        if "resume" not in command:
            required.append("--sandbox")
        missing = [flag for flag in required if flag not in result.stdout]
        if missing:
            raise SystemExit(f"[FAIL] {label} is missing {', '.join(missing)}. Upgrade Codex.")
        print(f"[OK] {label}: required flags available", flush=True)
PY

if [[ "$rollout_regression" == 1 ]]; then
    printf '[Regression] Running existing offline pipeline checks\n'
    "$rollout_python" -m unittest tests.check_agent_rollout tests.check_agent_task_spec tests.check_agent_rollout_budget tests.check_agent_rollout_tools -v
fi

printf '[PASS] Local rollout checks passed; no model API was called.\n'
printf 'API access and Genesis rendering/physics must still be checked by an actual evaluation.\n'
