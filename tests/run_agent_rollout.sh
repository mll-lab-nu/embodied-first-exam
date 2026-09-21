#!/usr/bin/env bash
# Tutorial workflow. Only the explicit evaluate subcommand can call a model.
set -euo pipefail
# Do not trace credential handling even when invoked with bash -x.
set +x
rollout_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
rollout_python="${TOPOGYM_PY:-$rollout_repo_root/.venv-gs121-nyx/bin/python}"
rollout_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)
            if [[ -z "${2:-}" || "$2" == --* ]]; then
                printf 'Missing executable path for --python\n' >&2
                exit 2
            fi
            rollout_python="$2"
            shift 2
            ;;
        *) rollout_args+=("$1"); shift ;;
    esac
done
cd -- "$rollout_repo_root"
exec "$rollout_python" -m tests.agent_rollout_workflow "${rollout_args[@]}"
