#!/usr/bin/env bash
# Docker bootstrap only. Experiment stages remain in scripts/difficulty_eval.py.
# --cuda-flavor cu128|cu130 is forwarded to Python (cu128 by default).
set +x
set -euo pipefail
umask 077
START_DIR="$PWD"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR"
if [[ "${SCRIPT_DIR##*/}" == bash_scripts && -f "$SCRIPT_DIR/../scripts/difficulty_eval.py" ]]; then
  ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
fi
backend=docker
work_dir="$START_DIR/topogym-work"
work_dir_set=0
controller_image="${TOPOGYM_CONTROLLER_IMAGE:-}"
gpu_device=0
phase=all
help_only=0
route=eval
provider=openai
api_var=
run_id=
resume=0
hf_enabled=0
hf_dry_run=0
hf_token_file=
hf_token_env=
hf_file_set=0
hf_env_set=0
args=()
files=()
# Parse only launcher concerns and host paths. Python validates experiment options.
while (($#)); do
  case "$1" in
    --resume) resume=1; args+=("$1"); shift ;;
    --results_to_hf|--results-to-hf) hf_enabled=1; args+=("$1"); shift ;;
    --hf-dry-run) hf_dry_run=1; args+=("$1"); shift ;;
    --hf-token-file) hf_token_file="${2:?--hf-token-file needs a path}"; hf_file_set=1; shift 2 ;;
    --hf-token-file=*) hf_token_file="${1#*=}"; hf_file_set=1; shift ;;
    --hf-token-env) hf_token_env="${2:?--hf-token-env needs a variable name}"; hf_env_set=1; shift 2 ;;
    --hf-token-env=*) hf_token_env="${1#*=}"; hf_env_set=1; shift ;;
    --backend) backend="${2:?--backend needs a value}"; shift 2 ;;
    --backend=*) backend="${1#*=}"; shift ;;
    --controller-image) controller_image="${2:?--controller-image needs a digest}"; shift 2 ;;
    --controller-image=*) controller_image="${1#*=}"; shift ;;
    --work-dir) work_dir="${2:?--work-dir needs a path}"; work_dir_set=1; shift 2 ;;
    --work-dir=*) work_dir="${1#*=}"; work_dir_set=1; shift ;;
    --gpu-device) gpu_device="${2:?--gpu-device needs an index or UUID}"; args+=("$1" "$2"); shift 2 ;;
    --gpu-device=*) gpu_device="${1#*=}"; args+=("$1"); shift ;;
    --phase) phase="${2:?--phase needs a value}"; args+=("$1" "$2"); shift 2 ;;
    --phase=*) phase="${1#*=}"; args+=("$1"); shift ;;
    --run-id) run_id="${2:?--run-id needs a value}"; args+=("$1" "$2"); shift 2 ;;
    --run-id=*) run_id="${1#*=}"; args+=("$1"); shift ;;
    --provider) provider="${2:?--provider needs a value}"; args+=("$1" "$2"); shift 2 ;;
    --provider=*) provider="${1#*=}"; args+=("$1"); shift ;;
    --api-key-env) api_var="${2:?--api-key-env needs a value}"; args+=("$1" "$2"); shift 2 ;;
    --api-key-env=*) api_var="${1#*=}"; args+=("$1"); shift ;;
    --setting|--env-file|--auth-json|--release-lock)
      opt="$1"; path="${2:?option requires a file}"; shift 2
      files+=("$path"); args+=("$opt" "/run/topogym-launch/file-${#files[@]}") ;;
    --setting=*|--env-file=*|--auth-json=*|--release-lock=*)
      opt="${1%%=*}"; files+=("${1#*=}"); args+=("$opt" "/run/topogym-launch/file-${#files[@]}"); shift ;;
    check) [[ ${#args[@]} -ne 0 ]] || route=check; args+=("$1"); shift ;;
    auth) [[ ${#args[@]} -ne 0 ]] || route=auth; args+=("$1"); shift ;;
    --help|-h) phase=plan; help_only=1; args+=("$1"); shift ;;
    --list-tasks) phase=plan; args+=("$1"); shift ;;
    *) args+=("$1"); shift ;;
  esac
done
if ((hf_file_set && hf_env_set)); then printf 'ERROR: --hf-token-file and --hf-token-env are mutually exclusive\n' >&2; exit 2; fi
if ((hf_env_set)) && [[ ! "$hf_token_env" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  printf 'ERROR: invalid HF token environment variable name\n' >&2; exit 2
fi
if [[ "$backend" == local ]]; then
  # Explicit compatibility mode preserves the old repository-relative run layout.
  for ((i=0; i<${#files[@]}; i++)); do
    for ((j=0; j<${#args[@]}; j++)); do
      [[ "${args[j]}" != "/run/topogym-launch/file-$((i+1))" ]] || args[j]="${files[i]}"
    done
  done
  PY="${TOPOGYM_EVAL_PYTHON:-$ROOT/.venv-gs121-nyx/bin/python}"
  [[ "$work_dir_set" == 0 ]] || args+=(--work-dir "$work_dir")
  ((hf_file_set == 0)) || args+=(--hf-token-file "$hf_token_file")
  ((hf_env_set == 0)) || args+=(--hf-token-env "$hf_token_env")
  exec "$PY" "$ROOT/scripts/difficulty_eval.py" "${args[@]}"
fi
hf_active=0
hf_value=
if [[ "$hf_enabled" == 1 && "$hf_dry_run" == 0 && "$help_only" == 0 && "$route" == eval && "$phase" =~ ^(all|run|collect|upload)$ ]]; then
  hf_active=1
  if ((hf_file_set == 0)); then
    hf_selected_env="${hf_token_env:-HF_TOKEN}"
    hf_value="${!hf_selected_env-}"
  fi
fi
# Do not expose injected HF credentials to Docker/build subprocess environments.
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN HF_TOKEN_PATH HF_HOME TOPOGYM_HF_AUTH_DIR
[[ -z "$hf_token_env" ]] || unset "$hf_token_env"
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
if ((hf_file_set)); then
  hf_credential_abs="$(realpath -m -- "$hf_token_file")"
  case "$hf_credential_abs" in
    "$ROOT/.secrets/"*) ;;
    "$ROOT/"*) fail 'put HF token outside the source repository or in its root .secrets directory' ;;
  esac
  [[ "$hf_token_file" != *$'\n'* && "$hf_token_file" != *$'\r'* ]] || fail 'HF token path cannot contain newline'
fi
log() { printf '[%(%F %T%z)T] === bootstrap: %s ===\n' -1 "$*"; }
guarded_build() {
  local logfile="$1"; shift
  local child previous_total=0 previous_idle=0 total idle_delta delta memory cpu=0 peak_cpu=0 peak_memory=0
  "$@" > >(tee "$logfile") 2>&1 & child=$!
  trap 'kill -TERM "$child" 2>/dev/null || true; wait "$child" || true; exit 130' INT TERM
  while kill -0 "$child" 2>/dev/null; do
    read -r _ usr nice sys idle iowait irq softirq steal _ < /proc/stat
    total=$((usr+nice+sys+idle+iowait+irq+softirq+steal))
    delta=$((total-previous_total)); idle_delta=$((idle+iowait-previous_idle))
    memory="$(awk '/MemTotal:/{t=$2} /MemAvailable:/{a=$2} END{if(t>0)print int(100*(t-a)/t);else print 100}' /proc/meminfo)"
    if ((previous_total>0 && delta>0)); then cpu=$((100*(delta-idle_delta)/delta)); fi
    if ((cpu>peak_cpu)); then peak_cpu=$cpu; fi
    if ((memory>peak_memory)); then peak_memory=$memory; fi
    if ((memory>=90)); then
      kill -TERM "$child" 2>/dev/null || true; wait "$child" || true
      printf '{"cpu_percent":%s,"memory_percent":%s}\n' "$peak_cpu" "$peak_memory" > "$logfile.resources.json"
      fail 'Memory reached 90%; owned image build stopped'
    fi
    previous_total=$total; previous_idle=$((idle+iowait))
    sleep 2
  done
  local result=0
  wait "$child" || result=$?
  printf '{"cpu_percent":%s,"memory_percent":%s}\n' "$peak_cpu" "$peak_memory" > "$logfile.resources.json"
  trap - INT TERM
  return "$result"
}
[[ "$backend" == docker ]] || fail '--backend must be docker or local'
[[ "$(uname -s)/$(uname -m)" == Linux/x86_64 ]] || fail 'this release requires Linux x86_64'
for tool in docker realpath sha256sum tar flock stat; do command -v "$tool" >/dev/null || fail "required host tool missing: $tool"; done
[[ "$gpu_device" =~ ^([0-9]+|GPU-[A-Za-z0-9-]+)$ ]] || fail 'invalid --gpu-device'
[[ -z "$run_id" || "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$ ]] || fail 'invalid --run-id'
[[ -z "$api_var" || "$api_var" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || fail 'invalid --api-key-env'
work_dir="$(realpath -m -- "$work_dir")"
[[ "$work_dir" != *[:,]* && "$work_dir" != *$'\n'* ]] || fail 'work-dir cannot contain colon, comma or newline'
mkdir -p -- "$work_dir/logs" "$work_dir/cache/build-locks"
[[ -w "$work_dir" ]] || fail 'work-dir is not writable'
log "work directory: $work_dir"
# Bind mounts must be resolved by the same local Linux daemon.
endpoint="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}"
[[ "$endpoint" == unix://* ]] || fail 'only a local Unix Docker socket is supported'
socket="${endpoint#unix://}"
[[ -S "$socket" ]] || fail 'Docker socket is missing; install/start Docker Engine'
docker info >/dev/null 2>&1 || fail 'Docker daemon is inaccessible; check service and socket permissions'
security="$(docker info --format '{{json .SecurityOptions}}')"
[[ "$security" != *rootless* ]] || fail 'rootless Docker is not supported in this release'
if [[ -z "$controller_image" && -f "$ROOT/controller-image.txt" ]]; then read -r controller_image < "$ROOT/controller-image.txt"; fi
if [[ -n "$controller_image" ]]; then
  [[ "$controller_image" =~ ^([A-Za-z0-9./:_-]+@)?sha256:[a-f0-9]{64}$ ]] || fail '--controller-image must be a registry digest or local image ID'
  if ! docker image inspect "$controller_image" >/dev/null 2>&1; then
    [[ "$controller_image" != sha256:* ]] || fail 'the specified local controller image is not available'
    log 'pulling the pinned controller image'
    docker pull "$controller_image"
  fi
else
  [[ -f "$ROOT/images/difficulty-eval/Dockerfile" ]] || fail 'source build recipe missing; use a complete source bundle or --controller-image'
  docker buildx version >/dev/null || fail 'local builds require Docker Buildx'
  # GNU tar hashes the allowlisted source without timestamps/ownership. No host Python.
  bootstrap_sha="$(bash "$ROOT/images/difficulty-eval/source_hash.sh" "$ROOT")"
  controller_image="topogym-local/difficulty-eval:$bootstrap_sha"
  exec {build_lock}>"$work_dir/cache/build-locks/controller-$bootstrap_sha.lock"
  flock "$build_lock"
  if ! docker image inspect "$controller_image" >/dev/null 2>&1; then
    log "building controller; log: $work_dir/logs/controller-build-$bootstrap_sha.log"
    guarded_build "$work_dir/logs/controller-build-$bootstrap_sha.log" \
      docker build --build-arg "BOOTSTRAP_SHA=$bootstrap_sha" --tag "$controller_image" \
      --file "$ROOT/images/difficulty-eval/Dockerfile" "$ROOT"
  fi
  actual_sha="$(docker image inspect --format '{{index .Config.Labels "topogym.bootstrap-sha"}}' "$controller_image")"
  [[ "$actual_sha" == "$bootstrap_sha" ]] || fail 'cached controller does not match the source inputs'
  flock -u "$build_lock"
fi
# Explicit controller images also have to match the chosen release. A resumed
# v15 run keeps its original controller/source; its manifest is checked inside.
if [[ "$route" == eval && "$help_only" == 0 && -f "$ROOT/ci_checks/topogym_active_release.json" ]]; then
  docker run --rm --network none --entrypoint python \
    --mount "type=bind,src=$ROOT,dst=/requested-release,readonly" "$controller_image" -c '
import sys
sys.path.insert(0, "/opt/topogym/scripts")
from topogym_versions import identity
actual, expected = identity("/opt/topogym"), identity("/requested-release")
if actual["tooling_version"] != expected["tooling_version"] or (sys.argv[1] == "0" and actual != expected):
    raise SystemExit("Controller does not match the active release; rebuild it, or resume the original v15 run")
' "$resume" || fail 'controller release validation failed'
fi
# Credentials/argv cross the Docker boundary through a private read-only file mount,
# never Docker Config.Cmd/Env. Do not print this directory's content.
launch_dir="$(mktemp -d "${TMPDIR:-/tmp}/topogym-launch.XXXXXXXX")"
controller="tg-controller-$(id -u)-$$-$RANDOM"
cleanup() {
  code=$?
  trap - EXIT
  docker rm -f "$controller" >/dev/null 2>&1 || true
  rm -rf -- "$launch_dir"
  exit "$code"
}
trap cleanup EXIT
stop() { trap '' INT TERM; docker stop -t 180 "$controller" >/dev/null 2>&1 || true; exit 130; }
trap stop INT TERM
if [[ "$hf_active" == 1 ]]; then
  if ((hf_file_set)); then
    [[ -f "$hf_token_file" && -r "$hf_token_file" && ! -L "$hf_token_file" ]] || fail 'HF token file must be a readable regular file, not a symlink'
    hf_mode="$(stat -c %a -- "$hf_token_file")"
    [[ "$(stat -c %u -- "$hf_token_file")" == "$(id -u)" ]] || fail 'HF token file must be owned by the current user'
    (( (8#$hf_mode & 077) == 0 )) || fail 'HF token file must have mode 0600 or 0400'
    [[ "$(stat -c %s -- "$hf_token_file")" -le 4096 ]] || fail 'HF token file is too large'
    cp --no-dereference -- "$hf_token_file" "$launch_dir/hf-token"
    chmod 600 "$launch_dir/hf-token"
    realpath -- "$hf_token_file" | tr -d '\n' > "$launch_dir/hf-host-token-file"
  else
    [[ -n "$hf_value" ]] || fail 'provide HF_TOKEN, --hf-token-env or --hf-token-file; no interactive HF login'
    printf '%s' "$hf_value" > "$launch_dir/hf-token"
    unset hf_value
    printf '%s' "$hf_selected_env" > "$launch_dir/hf-host-token-env"
  fi
  printf '%s' "$SCRIPT_DIR/run_difficulty_trials.sh" > "$launch_dir/hf-host-launcher"
  args+=(--hf-token-file /run/topogym-launch/hf-token)
else
  # Validate options in Python, but never read credentials for offline phases.
  ((hf_file_set == 0)) || args+=(--hf-token-file "$hf_token_file")
  ((hf_env_set == 0)) || args+=(--hf-token-env "$hf_token_env")
fi
printf '%s\0' "${args[@]}" > "$launch_dir/args"
printf '%s' "$work_dir" > "$launch_dir/work-dir"
if [[ -f "$ROOT/release.lock.json" ]]; then cp -- "$ROOT/release.lock.json" "$launch_dir/release.lock.json"; fi
for ((i=0; i<${#files[@]}; i++)); do
  [[ -f "${files[i]}" && -r "${files[i]}" ]] || fail 'an explicitly supplied input file is unreadable'
  cp -- "${files[i]}" "$launch_dir/file-$((i+1))"
done
if [[ -z "$api_var" ]]; then
  api_var=OPENAI_API_KEY; [[ "$provider" != openrouter ]] || api_var=OPENROUTER_API_KEY
fi
if [[ "$phase" == upload ]]; then
  : > "$launch_dir/api-key"
else
  printf '%s' "${!api_var-}" > "$launch_dir/api-key"
fi
# Auth is independent of work-dir, so logging in once serves later experiments.
auth_dir="${TOPOGYM_AUTH_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/topogym/codex}"
workspace="$(printf '%s' "$work_dir" | sha256sum)"; workspace="${workspace%% *}"
mounts=(--mount "type=bind,src=$work_dir,dst=$work_dir" \
  --mount "type=bind,src=$launch_dir,dst=/run/topogym-launch,readonly")
if [[ "$phase" != upload ]]; then
  mkdir -p -- "$auth_dir"
  chmod 700 "$auth_dir"
  auth_dir="$(realpath -- "$auth_dir")"
  mounts+=(--mount "type=bind,src=$auth_dir,dst=/var/lib/topogym/codex")
fi
if [[ "$route" != auth ]]; then
  mounts+=(--mount "type=bind,src=$socket,dst=/var/run/docker.sock" --group-add "$(stat -c %g "$socket")" \
    --mount 'type=bind,src=/proc,dst=/host/proc,readonly')
fi
if [[ "$help_only" == 0 && ( "$route" == check || ( "$route" == eval && "$phase" != plan && "$phase" != collect && "$phase" != upload ) ) ]]; then
  [[ "$(docker info --format '{{json .Runtimes}}')" == *nvidia* ]] || fail 'NVIDIA Container Toolkit is not configured for this Docker daemon'
  mounts+=(--gpus "device=$gpu_device" -e NVIDIA_DRIVER_CAPABILITIES=utility)
fi
tty=(); [[ ! -t 0 || ! -t 1 ]] || tty=(-t)
log 'starting controller'
docker create --name "$controller" --init --stop-timeout 180 -i "${tty[@]}" --user "$(id -u):$(id -g)" \
  --label topogym.role=controller --label "topogym.workspace=$workspace" --label "topogym.difficulty-run=$run_id" \
  -e "TOPOGYM_CONTROLLER=$controller" -e "TOPOGYM_WORKSPACE=$workspace" \
  -e HOME=/tmp/topogym-home -e CODEX_HOME=/var/lib/topogym/codex \
  "${mounts[@]}" "$controller_image" --launch-input /run/topogym-launch >/dev/null
# Background wait lets Bash forward Ctrl-C/TERM to the container with cleanup grace.
docker start -ai "$controller" <&0 &
attach_pid=$!
set +e
wait "$attach_pid"
code=$?
set -e
exit "$code"
